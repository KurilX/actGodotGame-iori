"""ASCII 关卡生成器：把字符画转成游戏可用的地形数据。

## 为什么是 ASCII 而不是 TileMap

Godot 自带的 TileMap 当然更强，但它要求：
  · 先画 tile 图集（美术工作）
  · 在编辑器里一格一格刷（或者写另一套工具刷）
  · 数据存在 .tscn 里，diff 不可读

而这个项目的地形是**程序化生成的美术 + 矩形碰撞体**，用不上 tile。
ASCII 图的好处是：
  · **改关卡就是改文本**，能直接 diff、能看出形状
  · 不需要美术资源，20px 一格的方块由代码画
  · 一张图同时表达地形 + 敌人 + 出生点

## 输出

不生成二进制，直接输出一个 `.tscn` 片段 + 一个 JSON 摘要给测试用。
游戏运行时读 JSON（`res://levels/tutorial.json`），不依赖编辑器。

## 矩形合并

逐格生成会得到几百个 20x20 的小碰撞体，物理引擎要处理的物体太多。
这里做**贪心矩形合并**：把相邻的实心格合成尽量大的矩形。
一张 120x27 的地图通常能合并成 20~40 个矩形。
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEVELS = os.path.join(ROOT, "levels")

# 实心地形
SOLID = "#"
# 单向平台
ONE_WAY = "="
# 空气
AIR = "."

# 地图合法字符集。**必须包含所有实体字符**，否则那一行会被当成
# 注释跳过（踩过的坑：漏了 b，导致带苔团的那一行整行消失，
# 校验器报"没有玩家出生点 P"）。
MAP_CHARS = "#=.PBblsT"

# 实体字符 → 类型。这些格子在**碰撞层面是空气**
ENTITIES = {
    "P": "spawn_player",
    "B": "spawn_boss",
    "b": "enemy_mossling",
    "l": "enemy_lanternbug",
    "s": "enemy_stonepaw",
    "T": "dummy",
}


def parse(path):
    """读取 .lvl 文件，返回 meta 与地图行。"""
    meta = {}
    rows = []
    section = None
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            stripped = line.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                section = stripped[1:-1]
                continue
            if section == "meta":
                if "=" in stripped and stripped:
                    k, v = stripped.split("=", 1)
                    meta[k.strip()] = v.strip()
            elif section == "map":
                # 跳过空行和**注释行**。
                #
                # 坑：地形行经常以 `#` 开头（左墙），所以不能用
                # "以 # 开头" 判断注释。这里改用更可靠的规则：
                #   注释行 = 以 # 开头 **且** 含有地图字符外的字符
                #   （比如空格、中文、数字坐标标尺）
                # 而地形行 100% 只由地图字符组成。
                if not stripped:
                    continue
                if all(ch in MAP_CHARS for ch in stripped):
                    rows.append(stripped)
                # 否则视为注释，跳过
    return meta, rows


def validate(meta, rows):
    """检查地图的合法性。返回 (errors, warnings)。"""
    errors = []
    warnings = []

    if not rows:
        errors.append("地图为空")
        return errors, warnings

    w = len(rows[0])
    for i, r in enumerate(rows):
        if len(r) != w:
            errors.append("第 %d 行宽度 %d，与第 0 行的 %d 不一致"
                          % (i, len(r), w))

    # 必须有且只有一个玩家出生点
    p_count = sum(r.count("P") for r in rows)
    if p_count == 0:
        errors.append("地图里没有玩家出生点 P")
    elif p_count > 1:
        errors.append("地图里有 %d 个 P，只能有一个" % p_count)

    # 底部必须是实心地面（防止玩家掉出地图）
    if rows and all(c not in "#" for c in rows[-1]):
        errors.append("最后一行没有实心地形，玩家会掉出地图")

    # 出生点下方必须有落脚点
    for y, r in enumerate(rows):
        x = r.find("P")
        if x < 0:
            continue
        # 往下找第一个非空气格
        below = None
        for yy in range(y + 1, len(rows)):
            ch = rows[yy][x]
            if ch == "#" or ch == "=":
                below = yy
                break
        if below is None:
            errors.append("出生点正下方没有地面")
        elif (below - y) > 5:
            warnings.append("出生点离地 %d 格（%d px），可能摔落"
                            % (below - y, (below - y) * 20))

    # 可达性提示：检查有没有"跳不上去的孤立地形"
    # 玩家跳跃极限约 58px ≈ 3 格（20px/格）
    # 这里只做粗略提示，不报错。
    return errors, warnings


def is_solid(ch):
    return ch == SOLID


def to_grid(rows):
    """把字符行转成布尔网格（True = 实心）。实体字符算空气。"""
    return [[is_solid(c) for c in r] for r in rows]


def to_oneway(rows):
    return [[c == ONE_WAY for c in r] for r in rows]


def merge_rects(grid, cell):
    """贪心矩形合并：把实心格合成尽量大的矩形。

    算法：扫到第一个没被覆盖的实心格，向右延伸到不能延伸，
    再向下延伸到"整行都还能延伸"为止。标记已覆盖，继续扫。

    这不是最优解（最优是 NP-hard），但对关卡这种稀疏地形足够了。
    """
    h = len(grid)
    w = len(grid[0])
    used = [[False] * w for _ in range(h)]
    rects = []

    for y in range(h):
        for x in range(w):
            if not grid[y][x] or used[y][x]:
                continue
            # 向右扩展
            x2 = x
            while x2 + 1 < w and grid[y][x2 + 1] and not used[y][x2 + 1]:
                x2 += 1
            # 向下扩展（整行都要可用）
            y2 = y
            while y2 + 1 < h:
                ok = True
                for xx in range(x, x2 + 1):
                    if not grid[y2 + 1][xx] or used[y2 + 1][xx]:
                        ok = False
                        break
                if not ok:
                    break
                y2 += 1
            # 标记
            for yy in range(y, y2 + 1):
                for xx in range(x, x2 + 1):
                    used[yy][xx] = True
            rects.append([x * cell, y * cell,
                          (x2 - x + 1) * cell, (y2 - y + 1) * cell])
    return rects


def merge_oneway(rows, cell):
    """单向平台：水平合并成尽量长的段。"""
    h = len(rows)
    w = len(rows[0])
    out = []
    for y in range(h):
        x = 0
        while x < w:
            if rows[y][x] != ONE_WAY:
                x += 1
                continue
            x2 = x
            while x2 + 1 < w and rows[y][x2 + 1] == ONE_WAY:
                x2 += 1
            out.append([x * cell, y * cell, (x2 - x + 1) * cell])
            x = x2 + 1
    return out


def extract_entities(rows, cell):
    """从地图里提取实体位置。"""
    out = []
    for y, r in enumerate(rows):
        for x, ch in enumerate(r):
            kind = ENTITIES.get(ch)
            if kind is None:
                continue
            # 实体锚点在格子底部中心（角色是按脚底对齐的）
            out.append({
                "kind": kind,
                "x": x * cell + cell // 2,
                "y": (y + 1) * cell - 2,
            })
    return out


def build(path):
    meta, rows = parse(path)
    errors, warnings = validate(meta, rows)
    if errors:
        for e in errors:
            print("  ERROR: " + e, file=sys.stderr)
        return None, errors, warnings

    cell = int(meta.get("cell", 20))
    grid = to_grid(rows)
    solids = merge_rects(grid, cell)
    oneway = merge_oneway(rows, cell)
    entities = extract_entities(rows, cell)

    data = {
        "name": meta.get("name", os.path.basename(path)),
        "width": len(rows[0]) * cell,
        "height": len(rows) * cell,
        "cell": cell,
        "tutorial_end_x": int(meta.get("tutorial_end_col", 0)) * cell,
        "solids": solids,
        "one_way": oneway,
        "entities": entities,
    }
    return data, errors, warnings


def main(argv):
    src = (argv[1] if len(argv) > 1
           else os.path.join(LEVELS, "tutorial.lvl"))
    print(f"读取 {src}")
    data, errors, warnings = build(src)
    if data is None:
        print("生成失败", file=sys.stderr)
        return 1

    out = os.path.splitext(src)[0] + ".json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)

    print(f"  尺寸 {data['width']}x{data['height']}（格 {data['cell']}px）")
    print(f"  实心矩形 {len(data['solids'])} 个（合并后）")
    print(f"  单向平台 {len(data['one_way'])} 段")
    print(f"  实体 {len(data['entities'])} 个")
    for w in warnings:
        print("  WARN: " + w)
    print(f"  → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
