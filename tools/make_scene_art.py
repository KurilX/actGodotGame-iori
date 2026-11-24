"""场景美术生成器：把灰盒替换成有氛围的夜景。

## 设计思路

灰盒的问题是「所有东西都在同一个平面上」——地形是一块灰，背景是一块深蓝，
角色贴在中间，没有纵深、没有光源、没有材质。

这里按**三层大气透视**来重建：

  远景（sky）      夜空渐变 + 月亮 + 三层远山剪影，越远越暗越偏蓝
  中景（terrain）  石台有顶面/立面两级明暗 + 石块纹理 + 苔藓覆盖
  近景（deco）     草丛、紫藤垂挂、灯笼

## 关键约束（来自 docs/02-像素美术规范.md）

  · 28 色硬上限，只能从主色板取色，不许自己加色
  · 禁用纯黑描边，用 #12142A（最暗的夜色）
  · 抖动只允许用在大面积渐变（天空/远景），前景一律纯色块
  · 光源统一从左上

输出：art/scene/*.png
"""

import math
import os
import random
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "art", "scene")

# ── 主色板（严格取自 docs/02-像素美术规范.md）──
P = {
    # ── 墨与夜（4）──
    "ink":      "#12142A",   # 01 最暗：描边
    "night_far":  "#1B2244",  # 02 夜色远
    "night_mid":  "#2A3A63",  # 03 夜色中
    "night_near": "#3D5385",  # 04 夜色近

    # ── 月与光（2）──
    "moon_hi":  "#8FD3E8",   # 05 月光高光
    "moon":     "#D8F0F8",   # 06 月白

    # ── 石与土（4）──
    "stone_hi": "#7B8699",   # 07 石亮（顶面受光）
    "stone":    "#5A6478",   # 08 石中（立面）
    "stone_dk": "#394051",   # 09 石暗（阴影/砖缝）
    "ear":      "#3D3348",   # 10 泥土

    # ── 苔与草（4）──
    "moss_hi":  "#6E9A6B",   # 11 苔亮
    "moss":     "#4A6B4F",   # 12 苔中
    "moss_dk":  "#2E4634",   # 13 苔暗
    "grass":    "#5A8A5E",   # 14 草（比苔更黄一点）

    # ── 紫藤（3）──
    "wist_hi":  "#A98FD6",   # 15
    "wist":     "#7A5FA8",   # 16
    "wist_dk":  "#4F3D74",   # 17

    # ── 灯笼/暖光（3）──
    "lant_hi":  "#FFE9A8",   # 18
    "lant":     "#FFC46B",   # 19
    "lant_dk":  "#E0913F",   # 20

    # ── 空气透视（2）：越远的山越接近这两个色 ──
    "haze_far":  "#5A4A72",  # 21 远山薄雾
    "haze_near": "#6E5580",  # 22 近山薄雾

    # ── 黄昏（4）：教程关的暖调，替换夜色/山色 ──
    "dusk_sky":  "#8A5C86",  # 23 暮色紫红
    "dusk_glow": "#B8738C",  # 24 霞光
    "dusk_mtn":  "#5E4270",  # 25 暮山
    "dusk_mtn_dk": "#4A3560",  # 26 暮山暗

    # ── 花瓣（2）：风的可视化 ──
    "petal":    "#FFB8D0",   # 27
    "petal_dk": "#D98BA8",   # 28
}


# 树下/草根处的阴影色
SHADOW = "#1A1526"

# 4×4 Bayer 有序抖动矩阵（模块级：天空、月亮光晕、灯笼光晕都要用）
BAYER = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]

ROOM_W, ROOM_H = 2400, 540

# 教程关与主关卡的分界点（世界坐标 x）
TUTORIAL_END = 1560

# 教程关用黄昏暖调，主关卡保持深夜冷调 —— 色调差暗示"出发"vs"抵达"
# 黄昏配色。
# **必须比夜色明显亮**：第一版用了偏暗的紫，截图出来和主关卡几乎没区别，
# 玩家感受不到"这是另一个地方"。整体提亮 + 加橙调。
DUSK = {
    "sky_far":  P["dusk_mtn_dk"],   # 暮色远
    "sky_mid":  P["dusk_sky"],      # 暮色中
    "sky_near": P["dusk_glow"],     # 暮色近（霞光）
    "mtn_far":  P["dusk_mtn_dk"],
    "mtn_mid":  P["dusk_mtn"],
    "mtn_near": P["dusk_sky"],
    "sun":      P["lant"],
    "sun_hi":   P["lant_hi"],
}
# **把黄昏色登记进主色板**。
#
# 必要原因：DUSK 里最早是裸十六进制，天空/远山直接用 hex_rgb() 画，
# 绕过了 P —— 结果场景用色统计到 31~33 色，超出 28 色硬上限。
# 登记之后它们就是合法调色板成员。
for _dk, _dv in list(DUSK.items()):
    if not any(_existing.lower() == _dv.lower() for _existing in P.values()):
        P["dusk_" + _dk] = _dv

GROUND_Y = 480          # 地面顶部（与 SOLIDS 一致）


def hx(key, a=255):
    h = P[key].lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a)


def hex_rgb(h):
    """把 "#RRGGBB" 转成 (r, g, b)。DUSK 字典里放的是裸十六进制串。"""
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


# ─────────────────────── 远景：夜空 ───────────────────────


def _ridge_color(body, is_night):
    """给山脊取一个"比山体亮一档"的色。

    **必须从调色板里取**，不能计算 —— 计算出的色会让用色统计超标。
    优先找同色系里明度高一档的；找不到就返回原色（宁可不勾）。

    **必须区分黄昏/夜色**：第一版在全调色板里找"更亮且色相接近"的，
    结果夜色区的山脊选到了黄昏紫 (90,74,114)，夜幕上冒出一圈紫边。
    所以候选集要按区域过滤。
    """
    if is_night:
        # 夜色系：只允许**蓝色分量明显高于红色**的深色。
        # 不能用 haze_* ——haze_far 是 (90,74,114) 的紫，
        # 混进夜幕会有一条明显的紫边（实测 y=359~371）。
        keys = ["night_far", "night_mid", "night_near", "ink"]
    else:
        # 黄昏系：只允许偏紫的暖色
        keys = ["dusk_mtn_dk", "dusk_mtn", "dusk_sky",
                "haze_far", "haze_near"]
    pal = [hx(k)[:3] for k in keys if k in P]
    # 在山体色基础上，找"更亮且色相接近"的调色板成员
    best = body[:3]
    best_score = 0.0
    body_lum = 0.299 * body[0] + 0.587 * body[1] + 0.114 * body[2]
    for c in pal:
        lum = 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]
        # 只要稍微亮一点的
        if lum <= body_lum or lum > body_lum * 1.6:
            continue
        # 色相接近：三通道差值不能太大
        diff = max(abs(c[0] - body[0]), abs(c[1] - body[1]),
                   abs(c[2] - body[2]))
        if diff > 90:
            continue
        score = lum - diff * 0.3
        if score > best_score:
            best_score = score
            best = c
    return (best[0], best[1], best[2], 255)
def make_sky():
    """夜空 + 远山。

    ## 这一版为什么重做

    用户反馈「背景跟风格有点不搭配，月亮跟草地对味了」。
    月亮和草的特点是**小而精致**（有描边、有 2~3 级明暗、轮廓清晰），
    而山是**巨大而平坦**（撑满画面的 67%，每层只有 1~2 个纯色）。

    具体三个问题：

    1. **山太大**：基准高度 300~424，相机可见区间才 y=270~540，
       等于整块画面都是山，没有"天空"的呼吸感。
    2. **天空抖动太吵**：可视角内的渐变用 4×4 Bayer，但相邻两色
       明度差太大，抖动出来是可见噪点，像静态雪花。
       月亮周围明明是干净的，两者放一起就割裂。
    3. **原来的"山体色块扰动"是空操作**：写的是 px[x,yy] = color，
       而那里本来就是 color，整段代码什么也没做。

    ## 这版的做法

    · **天空以纯色为主，只有靠近地平线的一条窄带做抖动渐变**
      → 大面积干净，噪点消失，和月亮的干净感一致
    · **山整体下压**（340/378/412），留出上方 1/3 干净天空
    · **山脊加锯齿**（原来的纯正弦太圆滑，像布不是山）
    · **最近一层山脊加远景树线**，把"草"的语言延伸到远处
    · 山体加**受光/背光分界**（每层两种色），不再是一整片纯色
    """
    img = Image.new("RGBA", (ROOM_W, ROOM_H), (0, 0, 0, 0))
    px = img.load()

    # ══════════════ 1. 天空 ══════════════
    #
    # 结构：上方一大片纯色 → 靠近地平线一小段抖动渐变。
    # 渐变带宽只占可见高度的一部分，避免整片天空都是噪点。
    SKY_FLAT_END = 380      # 这个 y 之前是纯色
    HORIZON = GROUND_Y      # 480

    dusk_flat = hx("dusk_mtn_dk")
    dusk_glow = hx("dusk_sky")
    night_flat = hx("night_far")
    night_glow = hx("night_mid")

    # 黄昏/夜色的分界（和关卡分界一致，中间 120px 抖动混合）
    BLEND = 120

    for y in range(int(GROUND_Y)):
        for x in range(ROOM_W):
            # 先决定这一列用哪套配色（过渡带按抖动混合）
            if x < TUTORIAL_END - BLEND:
                flat, glow = dusk_flat, dusk_glow
            elif x >= TUTORIAL_END:
                flat, glow = night_flat, night_glow
            else:
                th_blend = (BAYER[y % 4][x % 4] + 0.5) / 16.0
                ratio = (x - (TUTORIAL_END - BLEND)) / BLEND
                if th_blend < ratio:
                    flat, glow = night_flat, night_glow
                else:
                    flat, glow = dusk_flat, dusk_glow

            if y < SKY_FLAT_END:
                px[x, y] = flat
            else:
                # 地平线渐变：从 flat 过渡到 glow
                t = (y - SKY_FLAT_END) / max(1.0, HORIZON - SKY_FLAT_END)
                # 用 2×2 抖动（比 4×4 粗一档）：
                # 在 480 宽的画面里，2×2 的颗粒更接近"色块"而不是"噪点"
                th = (BAYER[(y // 2) % 4][(x // 2) % 4] + 0.5) / 16.0
                px[x, y] = glow if t > th else flat

    # ══════════════ 2. 远山（三层 + 锯齿） ══════════════
    rng = random.Random(20261120)

    # (夜色, 黄昏色, 夜色高光, 黄昏高光, 基准高度, 起伏, 波长, 锯齿强度)
    #
    # 基准高度整体下压：340/378/412（原来 300~424）。
    # 这样 y=270 到第一层山之间留出约 70px 干净天空。
    # 山脊高光色**必须和山体同色系**：
    #   · 夜色区只能从 night_* 取
    #   · 黄昏区只能从 dusk_* 取
    # 第一版最远那层的高光写的是 haze_far（紫），结果夜幕上
    # 冒出一条紫边（实测 y=359~371 全是 (90,74,114)）。
    layers = [
        # 最远：几乎融进天空，不需要独立高光
        (hx("haze_far"),   hx("haze_far"),    hx("haze_far"),
         hx("haze_far"),   340, 26, 640, 0.0),
        # 中远
        (hx("night_far"),  hx("dusk_mtn_dk"), hx("night_mid"),
         hx("dusk_mtn"),   378, 30, 500, 0.6),
        # 近：最实、锯齿最强
        (hx("night_mid"),  hx("dusk_mtn"),    hx("night_near"),
         hx("dusk_sky"),   412, 34, 380, 1.0),
    ]

    for night_c, dusk_c, night_hi, dusk_hi, base, amp, wave, jag in layers:
        heights = []
        for x in range(ROOM_W):
            # 主起伏：多频正弦（保持山的大形）
            h = (math.sin(x / wave * math.tau) * amp
                 + math.sin(x / (wave * 0.43) * math.tau + 1.7) * amp * 0.45
                 + math.sin(x / (wave * 0.21) * math.tau + 3.1) * amp * 0.22)
            # 锯齿：让山脊不是光滑曲线。
            # 纯正弦看起来像"布褶"而不是山岩 —— 这是上一版最大的问题。
            if jag > 0.0:
                step = max(2, int(6 - jag * 3))
                if (x // step) % 2 == 0:
                    h += jag * 2.0
                h += rng.uniform(-jag * 1.2, jag * 1.2)
            heights.append(int(base + h))

        for x in range(ROOM_W):
            color = dusk_c if x < TUTORIAL_END else night_c
            top = heights[x]
            for y in range(max(0, top), int(GROUND_Y)):
                px[x, y] = color

            # 山体内部的**受光/背光分界**：
            # 左侧山坡受光（更亮），右侧背光（更深）。
            # 用相邻山脊的高度差判断坡向。
            if 0 < x < ROOM_W - 1:
                slope = heights[x + 1] - heights[x - 1]
                if slope < -1:      # 上升坡 = 受光面
                    hi = dusk_hi if x < TUTORIAL_END else night_hi
                    # 只给坡面上部 60% 上高光，下面保持原色
                    for k in range(3, min(40, int(GROUND_Y) - top)):
                        if 0 <= top + k < int(GROUND_Y):
                            px[x, top + k] = hi
                            break

            # 山脊线：顶端 1px 用更亮的色，勾出轮廓
            if 0 <= top < int(GROUND_Y):
                hi2 = dusk_hi if x < TUTORIAL_END else night_hi
                px[x, top] = hi2

    # ══════════════ 3. 最近一层山脊的远景树线 ══════════════
    #
    # 用户说"草地对味了"—— 把植被的语言延伸到远处山脊，
    # 让"远处的树"和"近处的草"形成呼应，比光秃秃的山脊亲切。
    near_base = 412
    for x in range(0, ROOM_W, 3):
        # 只在山坡较平缓的地方长树
        h = (math.sin(x / 380 * math.tau) * 34
             + math.sin(x / (380 * 0.43) * math.tau + 1.7) * 34 * 0.45
             + math.sin(x / (380 * 0.21) * math.tau + 3.1) * 34 * 0.22)
        ridge_y = int(near_base + h)
        # 用噪声决定这一棵多高，避免等间距
        if rng.random() > 0.55:
            continue
        tree_h = rng.randint(4, 9)
        tree_w = rng.randint(1, 2)
        # 树是深色剪影：比山脊更深一档，在云雾里静静站着
        tree_col = hx("night_far") if x >= TUTORIAL_END else hx("dusk_mtn_dk")
        for k in range(tree_h):
            yy = ridge_y - k
            if not (0 <= yy < int(GROUND_Y)):
                continue
            # 上窄下宽的树形
            w_here = tree_w if k < tree_h * 0.6 else max(1, tree_w - 1)
            for dx in range(-w_here + 1, w_here):
                xx = x + dx
                if 0 <= xx < ROOM_W:
                    px[xx, yy] = tree_col

    # ══════════════ 4. 月亮 ══════════════
    #
    # **保持不变** —— 用户明确说月亮对味了。
    moon_x, moon_y, moon_r = 470, 306, 22
    for y in range(moon_y - moon_r * 3, moon_y + moon_r * 3):
        if not (0 <= y < GROUND_Y):
            continue
        for x in range(moon_x - moon_r * 3, moon_x + moon_r * 3):
            if not (0 <= x < ROOM_W):
                continue
            d = math.hypot(x - moon_x, y - moon_y)
            if d <= moon_r:
                px[x, y] = hx("moon")
            elif d <= moon_r + 3:
                px[x, y] = hx("moon_hi")
            elif d <= moon_r + 7:
                th = (BAYER[y % 4][x % 4] + 0.5) / 16.0
                if th < 0.28 * (1.0 - (d - moon_r - 3) / 4.0):
                    px[x, y] = hx("moon_hi")

    # 月亮上的暗斑
    for dy, dx, r in [(-6, -8, 5), (5, 4, 6), (-2, 10, 4)]:
        for y in range(moon_y + dy - r, moon_y + dy + r):
            for x in range(moon_x + dx - r, moon_x + dx + r):
                if 0 <= x < ROOM_W and 0 <= y < GROUND_Y:
                    if math.hypot(x - moon_x - dx, y - moon_y - dy) <= r:
                        if math.hypot(x - moon_x, y - moon_y) <= moon_r - 1:
                            px[x, y] = hx("moon_hi")

    return img

# ─────────────────────── 中景：石台 ───────────────────────

def fill_rect(px, x0, y0, x1, y1, color):
    for y in range(y0, y1):
        for x in range(x0, x1):
            if 0 <= x < ROOM_W and 0 <= y < ROOM_H:
                px[x, y] = color


def _draw_one_way(px, x, y, w):
    """画一段单向平台：3px 厚木板。

    视觉上必须和实心地形区分开 —— 玩家要能一眼看出"这是能穿的板子"。
    做法：薄（3px）、两端有描边、底面有阴影线、顶面亮一档。
    """
    thick = 3
    # 底面阴影（更暗，让它看起来悬空）
    for xx in range(x, x + w):
        if 0 <= xx < ROOM_W and 0 <= y + thick < ROOM_H:
            px[xx, y + thick] = hx("stone_dk")
    # 板身
    for xx in range(x, x + w):
        for yy in range(y, min(y + thick, ROOM_H)):
            if 0 <= xx < ROOM_W:
                px[xx, yy] = hx("stone")
    # 顶面高光
    for xx in range(x, x + w):
        if 0 <= xx < ROOM_W:
            px[xx, y] = hx("stone_hi")
    # 两端描边
    for xx in (x, x + w - 1):
        if 0 <= xx < ROOM_W:
            for yy in range(y, min(y + thick + 1, ROOM_H)):
                px[xx, yy] = hx("ink")


def make_terrain():
    """地形层：石台 + 地面。

    ## 为什么要重做

    原来是"一块石色矩形 + 2px 顶面高光 + 几根砖缝"，截图出来就是
    **一条灰色带**，完全没有质地。用户明确指出"地板很敷衍"。

    ## 现在分四层画

      1. **基岩**：整块石色，但从上到下分 3 个明度台阶（受光→立面→阴影），
         不是一整块纯色。
      2. **岩层线**：每 18~26px 一条水平层理线（地质分层），
         左右错开半块，模拟沉积岩。
      3. **草皮**：地面顶部 5~7px 是一条草，边缘参差不齐（不是直线），
         下面挂 3~5px 的草根/垂须。
      4. **细节**：碎石颗粒、苔藓斑、顶面受光边、底部渐暗。

    所有颜色都从 28 色调色板取，抖动只用 BAYER。
    """
    img = Image.new("RGBA", (ROOM_W, ROOM_H), (0, 0, 0, 0))
    px = img.load()
    rng = random.Random(777)

    # ── 从关卡 JSON 读地形 ──
    #
    # 原来是手抄一份 SOLIDS 常量，必须和 room_greybox.gd 保持一致。
    # 抄错就贴图和碰撞体错位（踩空 / 撞到看不见的墙），而且极难发现。
    #
    # 现在直接读 levels/tutorial.json（由 tools/build_level.py 从
    # `.lvl` 字符画编译出来），**单一数据源**，不可能对不上。
    import json
    lvl_path = os.path.join(ROOT, "levels", "tutorial.json")
    if not os.path.exists(lvl_path):
        print("  关卡文件缺失，先跑 python tools/build_level.py",
              file=sys.stderr)
        return None
    with open(lvl_path, encoding="utf-8") as _f:
        _lvl = json.load(_f)
    solids = [tuple(r) for r in _lvl.get("solids", [])]
    one_ways = [tuple(r) for r in _lvl.get("one_way", [])]
    one_ways = [tuple(r) for r in _lvl.get("one_way", [])]
    print(f"  从 tutorial.json 读到 {len(solids)} 个地形矩形，"
          f"{len(one_ways)} 段单向平台")
    for (x, y, w, h) in solids:
        _draw_solid(px, rng, x, y, w, h)

    # 单向平台。**之前完全没画**：ONE_WAY 只在游戏里生成了碰撞体，
    # 贴图上是空的 —— 玩家会踩到一片看起来不存在的地面。
    for (x, y, w) in one_ways:
        _draw_one_way(px, int(x), int(y), int(w))

    return img


def _draw_solid(px, rng, x, y, w, h):

    # ── 0. 窄高的"墙"：走简化路径 ──
    #
    # 左墙/右墙是 20x520 的长条。按普通地形画会出两个问题：
    #   · 四段明暗在竖直方向上重复，变成一条条横纹
    #   · 岩层线横向铺开，在 20px 宽的墙上挤成一团
    # 结果就是画面上一条很显眼的竖直条纹（实测截图可见）。
    #
    # 墙不需要岩层质感 —— 它大部分时间在画面边缘，只要安静的纯色。
    # 判据要**严格**：只有真正的边界墙（宽 ≤ 2 格 = 40px）才走简化。
    # 一开始写成 h > w*1.8，结果 4 格宽 6 格高的台阶也被判成墙，
    # 变成一根没有草皮的暗色柱子（实测）。
    if w <= 40 and h > w * 3:
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                if 0 <= xx < ROOM_W and 0 <= yy < ROOM_H:
                    px[xx, yy] = hx("stone_dk")
        # 靠内的一侧加一条亮边，暗示体积
        inner = x + w - 2 if x < ROOM_W // 2 else x
        for yy in range(y, y + h):
            for k in range(2):
                xx = inner + k
                if 0 <= xx < ROOM_W and 0 <= yy < ROOM_H:
                    px[xx, yy] = hx("stone")
        return

    """画一块地形：岩层 + 明暗台阶 + 草皮 + 细节。"""

    # 草皮参数（实际绘制在函数末尾，这里只声明）
    #
    # **判断"顶部是否露天"不能只看 y 坐标**：左墙是 20x520 的长条，
    # y=20 也落在范围内，于是整面墙被当成"地面"，长出草皮 + 岩层线，
    # 画面上表现为一条竖直条纹（实测）。
    #
    # 正确判据：**地形是"扁的"（宽 > 高）才可能是玩家站的地面**。
    # 墙是"竖的"（高 >> 宽），不该长草。
    _is_flat = w >= 60
    is_surface = _is_flat and 20 < y < GROUND_Y + 40
    grass_h = rng.randint(4, 7)

    # ── 1. 基岩：**四段**明暗 ──
    #
    # 地面很厚（60px），只做"上亮下暗"两段会让下半个屏幕变成一大块死黑
    # （实测截图里地板下半几乎看不出任何东西）。改成四段，
    # 并在中段保留主色，避免过早变暗。
    top_zone = max(2, int(h * 0.30))
    bot_zone = max(2, int(h * 0.28))

    for yy in range(y, y + h):
        rel = (yy - y) / max(1, h)
        if rel < 0.10:
            col = hx("stone_hi")
        elif rel < 0.62:
            col = hx("stone")
        elif rel < 0.86:
            col = hx("stone_dk")
        else:
            col = hx("ink")
        for xx in range(x, x + w):
            px[xx, yy] = col

    # ── 2. 岩层线：水平层理，错开半块 ──
    layer_y = y + top_zone + rng.randint(0, 6)
    while layer_y < y + h - 4:
        off = rng.randint(0, 14)
        # 层理：**2px 暗线 + 1px 亮线**。对比要够 —— 第一版只画 1px、
        # 概率 0.82，在 480px 宽的地面上几乎看不见，截图里地板是一块纯灰。
        for xx in range(x + off, x + w):
            if xx < 0 or xx >= ROOM_W:
                continue
            if rng.random() < 0.90:
                px[xx, layer_y] = hx("stone_dk")
                if layer_y + 1 < y + h:
                    px[xx, layer_y + 1] = hx("stone_dk")
            # 层理下方 1px 高光：让每层看起来有厚度、上面受光
            if rng.random() < 0.55 and layer_y + 2 < y + h:
                px[xx, layer_y + 2] = hx("stone_hi")
        layer_y += rng.randint(12, 22)


    # ── 4. 顶面受光边（非草皮的地块，比如天花板/墙）──
    for xx in range(x, x + w):
        if 0 <= xx < ROOM_W and 0 <= y < ROOM_H:
            px[xx, y] = hx("stone_hi")

    # ── 5. 外轮廓描边（不是纯黑，用墨色）──
    for xx in range(x, x + w):
        for yy in (y - 1, y + h):
            if 0 <= xx < ROOM_W and 0 <= yy < ROOM_H:
                px[xx, yy] = hx("ink")
    for yy in range(y, y + h):
        for xx in (x - 1, x + w):
            if 0 <= xx < ROOM_W and 0 <= yy < ROOM_H:
                px[xx, yy] = hx("ink")

    # ── 6. 碎石与苔藓斑 ──
    n_pebbles = max(1, (w * h) // 900)
    for _ in range(n_pebbles):
        rx = x + rng.randint(2, max(3, w - 3))
        ry = y + rng.randint(top_zone, max(top_zone + 1, h - 3))
        if not (0 <= rx < ROOM_W and 0 <= ry < ROOM_H):
            continue
        rw = rng.randint(1, 3)
        for k in range(rw):
            if rx + k < min(ROOM_W, x + w) and ry < y + h:
                px[rx + k, ry] = hx("stone_hi")
            if rx + k < min(ROOM_W, x + w) and ry + 1 < y + h:
                px[rx + k, ry + 1] = hx("stone_dk")

    n_moss = max(1, w // 90)
    for _ in range(n_moss):
        mx = x + rng.randint(0, max(1, w - 1))
        my = y + rng.randint(grass_h + 2 if is_surface else 2, max(4, h - 3))
        for k in range(rng.randint(2, 5)):
            if 0 <= mx < ROOM_W and 0 <= my < ROOM_H and my < y + h:
                if rng.random() < 0.7:
                    px[mx, my] = hx("moss_dk")
            mx += rng.choice([-1, 0, 1])

    # ── 7. 草皮：**最后画** ──
    #
    # 必须放在所有岩体/描边/碎石之后。第一版放在描边之前，
    # 结果草皮被描边和相邻地块覆盖，地面上只剩 1px 草边
    # （实测 y=480 之后立刻变成纯石头色）。
    if is_surface:
        for xx in range(x, x + w):
            if xx < 0 or xx >= ROOM_W:
                continue
            # 多频噪声让草皮边缘参差，不是直线
            n = (math.sin(xx * 0.31) * 1.4 + math.sin(xx * 0.87 + 1.3) * 0.9
                 + rng.random() * 1.2)
            gh = max(3, grass_h + int(n))
            for k in range(gh):
                yy = y + k
                if yy < 0 or yy >= ROOM_H:
                    continue
                if k == 0:
                    px[xx, yy] = hx("moss_hi")
                elif k < gh - 2:
                    px[xx, yy] = hx("grass")
                else:
                    px[xx, yy] = hx("moss")
            # 垂下的草须
            if rng.random() < 0.12:
                ln = rng.randint(2, 5)
                for k in range(ln):
                    yy = y + gh + k
                    if 0 <= yy < ROOM_H:
                        px[xx, yy] = hx("moss_dk")


def make_deco():
    """装饰层：草丛、紫藤、灯笼。z 高于地形、低于角色。"""
    img = Image.new("RGBA", (ROOM_W, ROOM_H), (0, 0, 0, 0))
    px = img.load()
    rng = random.Random(4242)

    def grass(x, base_y, n=5, hmax=7):
        """一小簇草，从左往右长。"""
        for i in range(n):
            gx = x + i * 2
            h = rng.randint(max(2, hmax - 3), hmax)
            lean = rng.choice([-1, 0, 1])
            for k in range(h):
                yy = base_y - k
                xx = gx + (lean if k > h // 2 else 0)
                if 0 <= xx < ROOM_W and 0 <= yy < ROOM_H:
                    px[xx, yy] = hx("moss_hi") if k > h - 2 else hx("moss")

    # 地面草丛：沿地面顶部随机分布
    gx = 12
    while gx < ROOM_W - 12:
        grass(gx, GROUND_Y, n=rng.randint(3, 6), hmax=rng.randint(4, 8))
        gx += rng.randint(28, 76)

    # ── 紫藤：从上方垂挂 ──
    def wisteria(x, top_y, length):
        """紫藤：垂挂的细碎花串。

        踩过的两个坑：
          1. 版一 spread 只有 1~3px、随机只填 60% → 像紫色噪点
          2. 版二 spread 到 5px 且每行填满 → 变成实心紫椭圆

        正确做法：**中间是一条细的垂枝，两侧散落不连续的花粒**，
        花粒越往下越大越稀。关键是"不填满"，留出空隙。
        """
        for k in range(length):
            yy = top_y + k
            if not (0 <= yy < ROOM_H):
                continue
            # 中央垂枝（1px，只在中间段实心）
            if 0 <= x < ROOM_W:
                px[x, yy] = hx("wist_dk")

            # 花粒：沿枝条两侧散落，不连续
            t = k / max(1, length)
            spread = 1.0 + 3.2 * math.sin(t * math.pi)
            for dx in range(-int(spread) - 1, int(spread) + 2):
                if dx == 0:
                    continue
                # 关键：只有约 1/3 的位置长花，形成"串"而不是"块"
                seed = (x * 31 + yy * 17 + dx * 7) % 11
                if seed > 3:
                    continue
                # 越靠外越稀
                if abs(dx) > spread * 0.7 and seed > 1:
                    continue
                xx = x + dx
                if not (0 <= xx < ROOM_W):
                    continue
                # 内圈较暗（阴影），外圈亮点（受光）
                if abs(dx) <= 1:
                    px[xx, yy] = hx("wist")
                else:
                    px[xx, yy] = hx("wist_hi") if seed % 2 == 0 else hx("wist")

            # 每隔几行加一朵更大的花团
            if k % 7 == 3 and 0 <= x < ROOM_W:
                for ddx, ddy in [(-2, 0), (-1, 0), (1, 0), (2, 0),
                                 (-1, 1), (0, 1), (1, 1), (0, 2)]:
                    xx, yy2 = x + ddx, yy + ddy
                    if 0 <= xx < ROOM_W and 0 <= yy2 < ROOM_H:
                        px[xx, yy2] = hx("wist_hi")

    # 挂在左侧平台和右上平台边缘
    for wx, wy, wl in [(36, 300, 46), (92, 300, 30), (520, 246, 38), (556, 246, 24)]:
        wisteria(wx, wy, wl)

    # ── 灯笼：挂在上方，提供暖色光源 ──
    def lantern(cx, cy):
        """灯笼：放大到 13×17，并加光晕。

        早期只有 10×14，在 960 宽的房间里几乎看不见，
        完全起不到"暖色光源"的作用。
        """
        RX, RY = 6.5, 8.5
        # 光晕：用抖动做半透明，范围比灯体大一圈
        for dy in range(-16, 17):
            for dx in range(-14, 15):
                d = math.hypot(dx / (RX * 2.1), dy / (RY * 2.1))
                if d > 1.0 or d < 0.85:
                    continue
                xx, yy = cx + dx, cy + dy
                if 0 <= xx < ROOM_W and 0 <= yy < ROOM_H:
                    th = (BAYER[yy % 4][xx % 4] + 0.5) / 16.0
                    if th < 0.30 * (1.0 - d):
                        px[xx, yy] = hx("lant_dk")
        # 绳子
        for k in range(10):
            if 0 <= cy - 9 - k < ROOM_H:
                px[cx, cy - 9 - k] = hx("ink")
        # 灯体
        for dy in range(-9, 10):
            for dx in range(-7, 8):
                if (dx * dx) / (RX * RX) + (dy * dy) / (RY * RY) <= 1.0:
                    xx, yy = cx + dx, cy + dy
                    if 0 <= xx < ROOM_W and 0 <= yy < ROOM_H:
                        if dx < -1 and dy < -2:
                            px[xx, yy] = hx("lant_hi")
                        elif dy > 4:
                            px[xx, yy] = hx("lant_dk")
                        else:
                            px[xx, yy] = hx("lant")
        # 上下盖
        for dx in range(-5, 6):
            for k in range(2):
                if 0 <= cy - 9 - k < ROOM_H and 0 <= cx + dx < ROOM_W:
                    px[cx + dx, cy - 9 - k] = hx("ink")
                if 0 <= cy + 9 + k < ROOM_H and 0 <= cx + dx < ROOM_W:
                    px[cx + dx, cy + 9 + k] = hx("ink")

    lantern(200, 250)
    lantern(640, 200)

    return img


def main():
    os.makedirs(OUT, exist_ok=True)
    print("生成场景美术：")

    sky = make_sky()
    sky.save(os.path.join(OUT, "sky.png"))
    print(f"  sky.png      {sky.size}")

    terrain = make_terrain()
    terrain.save(os.path.join(OUT, "terrain.png"))
    print(f"  terrain.png  {terrain.size}")

    deco = make_deco()
    deco.save(os.path.join(OUT, "deco.png"))
    print(f"  deco.png     {deco.size}")

    # 合成预览
    comp = Image.new("RGBA", (ROOM_W, ROOM_H), hx("ink"))
    for layer in (sky, terrain, deco):
        comp.alpha_composite(layer)
    comp.convert("RGB").save(os.path.join(OUT, "preview.png"))
    print(f"  preview.png  {comp.size}  (三层合成)")

    # 色数检查（不许超过 28）
    used = set(comp.convert("RGB").getdata())
    print(f"\n用色数：{len(used)} / 28")


if __name__ == "__main__":
    main()


