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
    # 深处岩体：**比 stone_dk 更暗，但不是 ink**。
    # ink 是描边色，大面积填会看起来像“未完成的洞”。
    "rock_deep": "#2A2C42",  # 深处岩体
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
    # （**全部落在 28 色板内**：artqa palette 锁逐色检查，
    #  旧 dusk_* 四色 delta 15~46 全部越界，scene/sky 的 style 被扣到 0.11）
    "dusk_sky":  "#7A5FA8",  # 23 暮色紫（=13_wisteria）
    "dusk_glow": "#FFB8D0",  # 24 霞光（=27_petal，粉阶）
    "dusk_mtn":  "#4F3D74",  # 25 暮山（=14_wisteria_d）
    "dusk_mtn_dk": "#4F3D74",  # 26 暮山暗（同上，山影合并为一档）

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


# AI 地形贴图（延迟加载）。缺失时为 None，退回原色阶逻辑。
_AI_TERRAIN = None


def _load_ai_terrain():
    """加载 AI 地形贴图（2400x540 全幅），返回 Image 或 None。

    ## 这张图干什么用

    原来地形是**纯色阶平涂**，实测最大单色占 52.1%、前 3 色合计 86.8%。
    AI 评审直接判「大面积灰蓝纯色块，缺少土/石纹理」，53 分。

    这张图由 tools/fix_ai_terrain_ground.py 从 AI 生成的
    地形带处理而来：1/8 缩像素、28 色量化、岩体段纵向循环 +
    每段横向偏移。它有真实的石缝、裂缝、土石过渡。
    """
    global _AI_TERRAIN
    path = os.path.join(ROOT, "art", "scene", "terrain_ai_ground.png")
    if not os.path.exists(path):
        print("  提示：没有 AI 地形贴图，退回色阶逻辑")
        _AI_TERRAIN = None
        return None
    _AI_TERRAIN = Image.open(path).convert("RGBA")
    print(f"  AI 地形贴图 {_AI_TERRAIN.size}")
    return _AI_TERRAIN


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
    """画一段单向平台：**悬空的残破石台**，不是一块木板。

    ## 为什么要重做两次

    第一版：3px 纯灰条 → AI 评「无纹理的灰色横条，像灰盒占位平台」。
    第二版：8px 加石纹 + 苔藓顶边 → AI 仍评「悬浮的木板长条，
    无支撑结构，像未完成的临时元素」。

    ## 根本问题：它看起来"轻"

    一块 8px 厚、几十像素长的薄片悬在半空，贴什么纹理都不像石头。
    能悬空的石体必须表现**断裂感** —— 它原本是从崖壁崩落的一段，
    断面是斜的、底部不平、两端有断茬。

    ## 现在做什么

    1. 厚度 14px（够厚才压得住）
    2. 两端**断茬**：一端厚一端薄，不是等宽矩形
    3. 底部**稀疏凹陷**（只约 40% 的列，幅度 ≤2px）
       —— 每列都凹会变成密密麻麻的黑色锯齿，像毛刺（实测）
    4. 表面从 AI 岩体纹理采样
    5. 顶面苔藓 + 少量垂根
    """
    thick = 14
    ai_tex = _AI_TERRAIN
    seed_base = (x * 13 + y * 7) % 97

    for i, xx in enumerate(range(x, x + w)):
        if not (0 <= xx < ROOM_W):
            continue
        t = i / max(1, w - 1)
        # 一端厚一端薄（断茬感）
        col_h = int(thick * (0.62 + 0.38 * (1.0 - abs(t - 0.35) * 1.3)))
        col_h = max(7, min(thick, col_h))
        # 稀疏凹陷：只 40% 的列，幅度 ≤2px
        notch = ((xx * 37 + seed_base) % 5)
        col_h -= notch if notch <= 1 else 0
        col_h = max(6, col_h)

        for dy in range(col_h):
            yy = y + dy
            if not (0 <= yy < ROOM_H):
                continue
            if ai_tex is not None:
                sc = ai_tex.getpixel((xx % ai_tex.width,
                                      (yy + 240) % ai_tex.height))
                px[xx, yy] = sc if sc[3] > 128 else hx("stone")
            else:
                px[xx, yy] = hx("stone")

        # 顶面：暗绿苔藓
        if 0 <= y < ROOM_H:
            px[xx, y] = hx("moss_dk")
        if 0 <= y + 1 < ROOM_H and (xx % 3 != 0):
            px[xx, y + 1] = hx("moss")
        # 底面压暗
        if 0 <= y + col_h - 1 < ROOM_H:
            px[xx, y + col_h - 1] = hx("ink")

    # 稀疏垂根（每 46px 一处）
    for k in range(0, w, 46):
        xx = x + k + 9
        if not (0 <= xx < ROOM_W):
            continue
        depth = 2 + (k * 11) % 3
        for dy in range(depth):
            yy = y + thick - 1 + dy
            if 0 <= yy < ROOM_H:
                px[xx, yy] = hx("moss_dk") if dy == 0 else hx("stone_dk")


def make_terrain():
    _load_ai_terrain()
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

    # ── pixel-studio 瓦片化地形层（新生成端）──
    #
    # tools/make_terrain_tiles.py 用 pixel-studio 的 side_guides 生成
    # 18 配置 x 2 变体的瓦片图集，按本关卡 solids 砌出整层。
    # 瓦片系统保证：空气透明（无"纯黑缺口"）、平台有 thin_* 瓦片、
    # 每格从两种 body 变体里确定性挑选（不再"每个 tile 一模一样"）。
    # 缺文件时退回旧的 AI 贴图/色阶逻辑。
    tiles_layer = os.path.join(ROOT, "art", "tiles", "terrain_from_tiles.png")
    if os.path.exists(tiles_layer):
        print("  使用 pixel-studio 瓦片化地形层 terrain_from_tiles.png")
        globals()["_SOLIDS"] = solids
        return Image.open(tiles_layer).convert("RGBA")

    for (x, y, w, h) in solids:
        _draw_solid(px, rng, x, y, w, h, solids)

    # 单向平台。**之前完全没画**：ONE_WAY 只在游戏里生成了碰撞体，
    # 贴图上是空的 —— 玩家会踩到一片看起来不存在的地面。
    for (x, y, w) in one_ways:
        _draw_one_way(px, int(x), int(y), int(w))

    globals()["_SOLIDS"] = solids
    return img


def _draw_solid(px, rng, x, y, w, h, solids):

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
        # **墙也要有材质**，不能填纯色。
        #
        # AI 评审点名「右侧的灰色柱状结构是近乎纯色的无纹理矩形，
        # 像未完成的占位贴图」—— 就是这里。
        # 原来整面墙填 stone_dk 一个颜色，40px 宽 500px 高，
        # 等于画面边缘一大块死灰。
        _ai = _AI_TERRAIN
        for yy in range(y, y + h):
            if not (0 <= yy < ROOM_H):
                continue
            for xx in range(x, x + w):
                if not (0 <= xx < ROOM_W):
                    continue
                if _ai is not None:
                    sc = _ai.getpixel((xx % _ai.width, yy % _ai.height))
                    px[xx, yy] = sc if sc[3] > 128 else hx("stone_dk")
                else:
                    px[xx, yy] = hx("stone_dk")
        # 靠内的一侧亮边，暗示体积（受光面朝向场景内部）
        inner = x + w - 2 if x < ROOM_W // 2 else x
        for yy in range(y, y + h):
            if not (0 <= yy < ROOM_H):
                continue
            for k in range(2):
                xx = inner + k
                if 0 <= xx < ROOM_W:
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

    # **明暗必须按世界 y 算，不能按每块地形的相对高度算。**
    #
    # 原来用 rel = (yy - y) / h，意思是"这块地形从上往下 30% 是亮部"。
    # 问题：相邻两块地形高度不同（台阶 h=100，地面 h=60），
    # 同一个世界 y 在不同块里会落在不同的明暗段 ——
    # 三级台阶的每一级交界处都有色阶跳变，看起来像"拼起来的分块"。
    #
    # 改成以地面顶（GROUND_Y）为锚点的**绝对深度**：
    # 不管这块地形多高，同一世界 y 永远是同一个明暗。
    def _strata_color(yy):
        """按**世界 y** 返回该行的岩体主色。

        ## 为什么高台不能"越往上越暗"

        第一版写的是：高于地面 12px 用 stone_hi、40px 内用 stone、
        再高就用 stone_dk。看起来符合"越靠近地面越亮"的空气透视直觉，
        但实际效果很糟：

        +80px 的高台整块都是 stone_dk（一块均匀深灰），
        而紧挨着它的地面是 stone（浅一档）。两者并排放在一起，
        出现一条**非常明显的横向明暗分界**，高台像贴上去的另一块东西。

        正确的做法：**岩体本身的明暗由"离地表多深"决定**，
        而"这块地形有多高"只影响它的**顶面**（顶面单独受光）。
        所以这里只按 depth 分档，而且高台部分保持和地面同一套色阶 ——
        高台只是"地面被抬起来"，不是"另一种材质"。
        """
        # **深度要相对"这块地形的顶面"算，不是相对地面顶。**
        #
        # 用户反馈「如果往上垫了上面就全是空的」—— 指的就是这个：
        # 相对地面顶算深度时，任何高于地面的地形（台阶/高台）
        # 整体都落在 depth<8 这一档，里面是**一整片均匀的 stone_hi**，
        # 没有从受光到阴影的过渡，看起来像一块平板。
        #
        # 正确做法：用**距离本地形顶面多深**来分档。
        # 这样不管地形在什么高度，它的立面都有"顶亮→中→暗→底弧"的纵深感，
        # 而且同一块地形内部是渐变的，不会出现横向断层
        #（因为相邻地块顶面高度不同时，交界处本来就是不同的立面）。
        # **必须按绝对世界 y 分档，不能按"离本地形顶面的深度"。**
        #
        # 这两轮踩的坑正好相反，记下来避免再来一次：
        #
        #   第一版：按"离地面顶(GROUND_Y)的深度"，但只给了 4 个很粗的
        #           阈值 —— 高于地面的高台整体落进最亮一档，
        #           内部一片均匀，用户说"往上垫了上面全是空的"。
        #
        #   第二版：改成"离本地形顶面的深度" —— 高台有了渐变，
        #           但**相邻两块地形顶面高度不同时，同一个世界 y
        #           会算出不同颜色**，横向并排立刻出现明暗分界，
        #           用户说"过渡又不自然了"。
        #
        # 正解：**分档依据必须是绝对的、与"这块地形多高"无关的量**，
        # 这样同一世界 y 永远是同一颜色，横向不可能出现分界；
        # 同时把档位做**足够细**，高台因为自身跨了 100~160px，
        # 自然会跨过好几档，内部也就有了层次。
        #
        # 档位（以地面顶 GROUND_Y=480 为 0，向上为负）：
        #   d < -60  最亮（高台顶部/近光面）
        #   d < -8   亮
        #   d < 34   中
        #   d >= 34  暗（画面底部）
        # **高于地面的地形不能单独给"更亮"的色阶。**
        #
        # 之前写成 `d < -60 → stone_hi`，意思是"越高的地方越亮"。
        # 听上去符合光照直觉，实际效果是：每个台地顶部有一条
        # **20px 高的亮带**（如 y=400~420），下面突然变成 stone，
        # 中间一道硬边 —— 用户形容为"亮色的小山坡"，
        # 看起来像台地上又贴了一块浅色岩石。
        #
        # 正解：**台地的立面就是岩体，和地面用同一套色阶**。
        # "被照亮"只体现在**顶部 3px 的受光边**（在下面单独画），
        # 不需要整段提亮。
        #
        # 这样也彻底消除台地与地面之间的横向色差：
        # 同一世界 y 恒为同一档。
        # **深处不要用 ink（纯黑）。**
        #
        # AI 评审指出「右侧地形出现一块与整体色调脱节的纯黑缺口，
        # 像未完成的洞」—— 就是这里返回 ink 造成的。
        # ink 是描边色，用来勾轮廓，不该大面积填充。
        # 深处改用很暗的紫灰，保住"岩体"的语义。
        d = yy - GROUND_Y
        if d < 34:
            return hx("stone")
        elif d < 50:
            return hx("stone_dk")
        else:
            return hx("rock_deep")

    for yy in range(y, y + h):
        # **有 AI 贴图就采样，否则退回色阶**
        if _AI_TERRAIN is not None:
            tw, th = _AI_TERRAIN.size
            ap = _AI_TERRAIN.load()
            sy = yy if yy < th else (yy % th)
            for xx in range(x, x + w):
                if not (0 <= xx < ROOM_W):
                    continue
                sc = ap[xx % tw, sy]
                px[xx, yy] = sc if sc[3] > 128 else _strata_color(yy)
        else:
            col = _strata_color(yy)
            for xx in range(x, x + w):
                px[xx, yy] = col

    # ── 2. 岩层线：水平层理，错开半块 ──
    # **岩层线也必须用全局基准**：从地面顶往下每 16px 一条，
    # 每个地形块只画落在自己范围内的那些线。
    # 原来从 y + top_zone + rng 起步，每块各错开一次，
    # 相邻块的层理在交界处完全对不上。
    # **岩层线要覆盖整块地形，包括高于地面的高台**。
    #
    # 原来从 GROUND_Y+8 起步，只画地面以下 —— 高于地面的高台内部
    # 变成一整片没有任何纹理的平色（放大 3 倍看非常明显，像贴上去的色块）。
    #
    # 改成从地图顶部起、每 16px 一条，落在本块范围内的就画。
    # 这样高台内部也有层理，和地面是同一套材质。
    # **有 AI 纹理时不画手绘层理**：两者会打架。
    #
    # AI 贴图已有石块结构与裂缝；再叠手绘的"2px 暗线 + 1px 亮线"，
    # 实测高台顶部出现一整条黑色横带，像地形裂开了。
    _has_ai = _AI_TERRAIN is not None

    layer_y = 16
    while (not _has_ai) and layer_y < ROOM_H:
        if not (y + 2 <= layer_y < y + h - 4):
            layer_y += 16
            continue
        # **`off` 必须由 layer_y 决定，不能用 rng**。
        # rng 每块地形都会重新摇一次，横向相邻的两块各摇到不同的偏移，
        # 同一层岩层线在交界处就错开 0~14px —— 竖着看非常明显。
        # 用 (layer_y * 7) % 15 得到一个稳定但看着随机的偏移。
        off = (layer_y * 7) % 15
        # 层理：**2px 暗线 + 1px 亮线**。对比要够 —— 第一版只画 1px、
        # 概率 0.82，在 480px 宽的地面上几乎看不见，截图里地板是一块纯灰。
        for xx in range(x + off, x + w):
            if xx < 0 or xx >= ROOM_W:
                continue
            # **岩层线要断续**，但不能用 rng。
            #
            # 用 rng 有两个致命问题：
            #   1. 每块地形独立摇，横向相邻的块在同一 x 处给出不同结果，
            #      交界处必然断线（实测 y=520 这一行有 8 段断口）
            #   2. 结果不可复现，改一次代码整片纹理就变样
            #
            # 改用**像素坐标的确定性哈希**：同一 (xx, layer_y) 永远同一结果，
            # 所以相邻地块自动接上，而且纹理稳定可复现。
            import math as _m
            # **密度波要够长**：原来用 sin(xx/47)，周期只有约 300px，
            # 在 2400px 宽的地图上会重复 8 次，看起来像规则花纹。
            # 改成 200px 波长的叠加，配合更低的断线率，层理更像天然沉积。
            #
            # 断线率：原来 0.90*(0.45+0.55*wave) 平均约 0.65，
            # 断得太碎变成"短横线阵列"（放大看像砖块）。
            # 提到 0.97 基准，只在波谷处断开，形成连续的长层理。
            wave = 0.5 + 0.5 * _m.sin(xx / 197.0 + layer_y * 0.37)
            wave2 = 0.5 + 0.5 * _m.sin(xx / 61.0 + layer_y * 1.13)
            wave = wave * 0.7 + wave2 * 0.3
            # 哈希：把坐标搅成一个 0~1 的伪随机数
            hsh = ((xx * 73856093) ^ (layer_y * 19349663)) & 0xFFFF
            r1 = hsh / 65535.0
            hsh2 = ((xx * 83492791) ^ (layer_y * 2654435761)) & 0xFFFF
            r2 = hsh2 / 65535.0
            # **暗部要用"提亮"来画层理，不能一直压暗**。
            #
            # 原来层理一律用 stone_dk。在地面（主色 stone）上没问题，
            # 但在高台立面下半部（主色已经是 stone_dk 甚至 ink）时，
            # stone_dk 压上去等于没有对比 —— 放大看就是一片纯色，
            # 用户形容为"往上垫了上面就全是空的"。
            #
            # 判据：看这一行的底色，底色深就用亮线，底色浅就用暗线。
            base_c = _strata_color(layer_y)
            dark_base = base_c[0] + base_c[1] + base_c[2] < 260
            line_c = hx("stone_hi") if dark_base else hx("stone_dk")
            hi_c = hx("stone_dk") if dark_base else hx("stone_hi")
            if r1 < 0.97 * (0.72 + 0.28 * wave):
                px[xx, layer_y] = line_c
                if layer_y + 1 < y + h:
                    px[xx, layer_y + 1] = line_c
            # 层理下方 1px 高光（暗部则改为阴影）
            if r2 < 0.55 and layer_y + 2 < y + h:
                px[xx, layer_y + 2] = hi_c
        layer_y += 16


    # ── 4. 顶面受光边（非草皮的地块，比如天花板/墙）──
    for xx in range(x, x + w):
        if 0 <= xx < ROOM_W and 0 <= y < ROOM_H:
            px[xx, y] = hx("stone_hi")

    # ── 5. 外轮廓描边（不是纯黑，用墨色）──
    #
    # **只在"真正暴露"的边上描边**。
    #
    # 原来无条件给四条边都描，相邻地块各自描一次，
    # 拼在一起就成了一道双线接缝 —— 实测三级台阶的每一级交界
    # 都有一条 (18,20,42) 的墨线，看起来像"拼起来的分块"，
    # 而不是一整块地形。
    #
    # 判据：该边如果被另一块地形覆盖，就是内部接缝，不描。
    def _covered(cx, cy):
        for (ox, oy, ow, oh) in solids:
            if ox <= cx < ox + ow and oy <= cy < oy + oh:
                return True
        return False

    for xx in range(x, x + w):
        for yy in (y - 1, y + h):
            if 0 <= xx < ROOM_W and 0 <= yy < ROOM_H:
                if not _covered(xx, yy):
                    px[xx, yy] = hx("ink")
    for yy in range(y, y + h):
        for xx in (x - 1, x + w):
            if 0 <= xx < ROOM_W and 0 <= yy < ROOM_H:
                if not _covered(xx, yy):
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
            # **顶面起波**：原来草皮一律从 `y`（矩形顶面）开始，
            # 而矩形顶面是数学上的水平线 —— 实测全图 2420/2420
            # 个顶面像素在同一条水平线上，这是"生硬"的第一来源。
            #
            # 起伏只依赖世界 x（不含 rng），所以**相邻地块在交界处天然连续**，
            # 不会出现接缝。幅度 ±2px：够破掉直线感，
            # 又不会让碰撞体（仍是矩形）和视觉错位太多。
            # 起伏幅度收到 ±1px，并且**只向上不向下**（e <= 0）。
            #
            # 第一版用 ±2px 双向起伏，草皮会往上吃掉原本的岩石受光边，
            # 也会往下盖住岩层 —— 放大 4 倍看是"贴上去的一条绿边"，
            # 比旧版更生硬。改成只向上 1px，保留岩石原有层次。
            e = int(round(math.sin(xx * 0.043) * 1.3
                          + math.sin(xx * 0.109 + 1.7) * 0.8
                          + math.sin(xx * 0.231 + 3.1) * 0.4))
            e = min(0, e)
            base_y = y + e
            # 多频噪声让草皮边缘参差，不是直线
            n = (math.sin(xx * 0.31) * 1.4 + math.sin(xx * 0.87 + 1.3) * 0.9
                 + rng.random() * 1.2)
            gh = max(3, grass_h + int(n))
            for k in range(gh):
                yy = base_y + k
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
                    yy = base_y + gh + k
                    if 0 <= yy < ROOM_H:
                        px[xx, yy] = hx("moss_dk")

        # ── 顶面草皮向两侧"包边" ──
        #
        # 用户想要「草地是相连的话，竖着也生成一下草地，看起来衔接好点」。
        #
        # 第一版理解错了，把草一路挂在**垂直立面**上 ——
        # 结果台阶立面中途浮出一簇孤立的小草（放大 3 倍非常明显），
        # 因为立面上没有"土"，草不该长在那里。
        #
        # 正确做法：草只从**顶面往下包 1~2px**，沿着上边缘横向延伸出去，
        # 让相邻台地的草在视觉上连成一条边；立面本身保持干净的石头。


def make_deco(solids):
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
            # **草根要落到 base_y 那一格**，不能只到 base_y-1。
            # 原来写 range(h) 让最底一像素在 base_y-(h-1)，
            # 草整体悬在地表上方 1px —— 实测 35 处草和地面之间有 1~2 行空隙，
            # 放大看就是"草浮在空中"。
            for k in range(h + 1):
                yy = base_y - k
                xx = gx + (lean if k > h // 2 else 0)
                if 0 <= xx < ROOM_W and 0 <= yy < ROOM_H:
                    px[xx, yy] = hx("moss_hi") if k > h - 2 else hx("moss")

    # 地面草丛：沿**真实地表**随机分布。
    #
    # **不能固定写 GROUND_Y**。用户反馈「这个花草怎么都到石头里了」——
    # 就是这个原因：装饰草一律种在 y=480（地面顶），
    # 但台阶顶面在 440/400/360，于是：
    #   · 台阶顶面完全没草
    #   · 种在 480 的草被台阶立面挡住 / 浮在石头中间
    # 现在改成查该 x 处最高的可站表面，种在真正的地上。
    def ground_top_at(x):
        best = None
        for (sx, sy, sw, sh) in solids:
            if sw < 40:
                continue          # 排除边界墙/天花板
            if sy < 100:
                continue
            if sx <= x < sx + sw:
                if best is None or sy < best:
                    best = sy
        return best

    # **草要密**：原来 28~76px 一簇、3~6 根，
    # 实测 deco 层覆盖率只有 0.2%。AI 评「近景反而比背景更空」。
    gx = 12
    while gx < ROOM_W - 12:
        gt = ground_top_at(gx)
        if gt is not None:
            grass(gx, gt, n=rng.randint(5, 9), hmax=rng.randint(4, 12))
        gx += rng.randint(10, 26)

    # ── 碎石堆：地表的颗粒感 ──
    def pebbles(x, base_y, n=3):
        for _ in range(n):
            ox = x + rng.randint(-5, 5)
            oy = base_y + rng.randint(-2, 1)
            rw = rng.randint(2, 5)
            rh = rng.randint(1, 3)
            for dy in range(rh):
                for dx in range(rw):
                    xx = ox + dx
                    yy = oy - dy
                    if 0 <= xx < ROOM_W and 0 <= yy < ROOM_H:
                        px[xx, yy] = hx("stone_hi" if dy == rh - 1
                                        else ("stone" if dy > 0
                                              else "stone_dk"))

    gx = 20
    while gx < ROOM_W - 20:
        gt = ground_top_at(gx)
        if gt is not None:
            pebbles(gx, gt - 1, n=rng.randint(1, 3))
        gx += rng.randint(34, 90)

    # ── 苔藓斑：把石面与草皮之间的硬边过渡掉 ──
    def moss_patch(x, base_y, pw, ph):
        for dy in range(ph):
            row_w = pw - dy
            for dx in range(max(0, row_w)):
                xx = x + dx
                yy = base_y - dy
                if 0 <= xx < ROOM_W and 0 <= yy < ROOM_H:
                    if dy > 0 and ((xx * 7 + yy * 13) % 5 == 0):
                        continue
                    px[xx, yy] = hx("moss_dk" if dy == ph - 1 else "moss")

    gx = 40
    while gx < ROOM_W - 40:
        gt = ground_top_at(gx)
        if gt is not None:
            moss_patch(gx, gt - 1, rng.randint(4, 11), rng.randint(1, 3))
        gx += rng.randint(60, 150)

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

    # ── BOSS 区道具：残柱 / 石堆 / 木桶 ──
    #
    # AI 评审三轮点名「BOSS 房空旷扁平，地面一整条无限平砖，没有起伏、
    # 落差或前景遮挡物」。关卡数据（levels/tutorial.json）里 BOSS 区只有
    # 一条 740px 的平地 —— 不能改关卡（平台即承诺原则 + verify_level
    # 断言锁死），所以道具只能长在 deco 层上：
    #
    #   · 残柱 3 根：断口不平、高度错落，柱身从 pixel-studio 瓦片图集的
    #     interior 瓦片采样（和地形同一块石头，材质不脱节）
    #   · 石堆 2 处：3~5 块碎石叠起来，顶面受光
    #   · 木桶 2 只：暖木色，和灯笼的暖光源呼应
    #
    # 位置避开 BOSS 出生点（1910, 478）与战斗动线中央。

    def _ground_shadow(px, x, base_y, width, strength=0.5):
        """接地阴影：大件底部一条 2px 半暗带 + 两侧渐散点。

        R4b（7 采样）三个 top_issue 共同指向"装饰物缺落点阴影、
        底座与草地衔接发虚"。阴影画在 base_y 行（草地顶），
        用 ink 抖动（BAYER 阈值）模拟半透明，不遮死草地纹理。
        """
        for i, xx in enumerate(range(x - width // 2, x + width + width // 2)):
            # 距中心越远越稀疏（渐散）
            edge_dist = abs(i - width / 2) / (width / 2 + 1)
            if edge_dist > 1.0:
                continue
            th = (BAYER[base_y % 4][xx % 4] + 0.5) / 16.0
            if th < strength * (1.0 - 0.55 * edge_dist):
                if 0 <= xx < ROOM_W and 0 <= base_y < ROOM_H:
                    px[xx, base_y] = hx("ink")
            # 第二行更稀
            if th < strength * 0.35 * (1.0 - 0.7 * edge_dist):
                if 0 <= xx < ROOM_W and 0 <= base_y + 1 < ROOM_H:
                    px[xx, base_y + 1] = hx("ink")

    def pillar(x, base_y, height, width=14):
        """残柱：从 pixel-studio 瓦片图集 interior 瓦片采样柱身。

        断口：顶部 2~4px 的锯齿（每列不同高），加 1px 描边。
        底部碎石基座让它"长"在地上，不是插上去的。
        """
        atlas_path = os.path.join(ROOT, "art", "tiles", "tiles_tileset_a.png")
        ax, ay, aw, ah = 80, 0, 20, 20   # interior 瓦片的 rect（第 5 格）
        tile = Image.open(atlas_path).convert("RGBA") if os.path.exists(atlas_path) else None
        for i, xx in enumerate(range(x, x + width)):
            # 断口锯齿：只顶部有，每列 0~3px
            jag = ((xx * 37 + x * 13) % 4)
            for yy in range(base_y - height + jag, base_y):
                if not (0 <= xx < ROOM_W and 0 <= yy < ROOM_H):
                    continue
                if tile is not None:
                    c = tile.getpixel((ax + (xx - x) % aw, ay + (yy % ah)))
                    if c[3] > 128:
                        px[xx, yy] = c[:3] + (255,)
                        continue
                px[xx, yy] = hx("stone")
            # 左侧受光边
            if 0 <= x < ROOM_W:
                yy0 = base_y - height + jag
                if 0 <= yy0 < ROOM_H:
                    px[x, yy0] = hx("stone_lit") if tile is None else px[x, yy0]
            # 描边
            for yy in (base_y - height + jag, base_y - 1):
                if 0 <= xx < ROOM_W and 0 <= yy < ROOM_H:
                    px[xx, yy] = hx("ink")
        # 底部基座：2px 外扩的碎石
        for dx in range(-3, width + 3):
            xx = x + dx
            for k in range(2):
                yy = base_y - k
                if 0 <= xx < ROOM_W and 0 <= yy < ROOM_H:
                    px[xx, yy] = hx("stone_dk" if k == 0 else "stone_hi")
        # 左缘整柱受光（R4b：缺受光面刻画）
        for yy in range(base_y - height, base_y):
            if 0 <= x < ROOM_W and 0 <= yy < ROOM_H:
                px[x, yy] = hx("stone_hi")

    def rock_pile(x, base_y, n=4):
        """石堆：n 块碎石叠成小丘，顶面受光，无描边（远景感）。"""
        for i in range(n):
            rw = rng.randint(4, 8)
            rh = rng.randint(2, 4)
            ox = x + rng.randint(-3, 3)
            oy = base_y - i * 2
            for dy in range(rh):
                for dx in range(rw):
                    xx, yy = ox + dx, oy - dy
                    if 0 <= xx < ROOM_W and 0 <= yy < ROOM_H:
                        px[xx, yy] = hx("stone_hi" if dy == rh - 1
                                        else ("stone" if dy > 0 else "stone_dk"))

    def barrel(x, base_y):
        """木桶：10x12，暖木色 + 两道铁箍 + 顶部椭圆盖。"""
        w, h = 10, 12
        wood_c = hx("lant_dk")          # 暖木色（和灯笼呼应）
        wood_hi = hx("lant")
        hoop = hx("stone_dk")
        for dy in range(h):
            for dx in range(w):
                xx, yy = x + dx, base_y - h + dy
                if not (0 <= xx < ROOM_W and 0 <= yy < ROOM_H):
                    continue
                # 桶身竖木纹
                if dx % 3 == 0 and 1 < dy < h - 1:
                    px[xx, yy] = wood_hi if dx < 3 else wood_c
                else:
                    px[xx, yy] = wood_c
                # 铁箍两道
                if dy in (2, h - 3):
                    px[xx, yy] = hoop
        # 描边 + 顶盖
        for k in range(w):
            if 0 <= x + k < ROOM_W:
                px[x + k, base_y - h] = hx("ink")
                px[x + k, base_y - 1] = hx("ink")
        for dy in range(h):
            if 0 <= base_y - h + dy < ROOM_H:
                if 0 <= x < ROOM_W:
                    px[x, base_y - h + dy] = hx("ink")
                if 0 <= x + w - 1 < ROOM_W:
                    px[x + w - 1, base_y - h + dy] = hx("ink")
        for dx in range(1, w - 1):
            if 0 <= x + dx < ROOM_W:
                px[x + dx, base_y - h + 1] = hx("lant")

    # 残柱：BOSS 区三根，错落（x=1650/1720/2100，高度 40~78）
    pillar(1650, 480, 62)
    pillar(1722, 480, 44)
    pillar(2104, 480, 78)
    # 石堆：台阶下与 BOSS 房中段
    rock_pile(1592, 479, 4)
    rock_pile(1980, 479, 3)
    # 木桶：BOSS 房边缘 + 跳跃段平台
    barrel(1660, 479)
    barrel(1996, 479)
    # 接地阴影：所有大件统一（R4b 三张截图的共同 top_issue）
    _ground_shadow(px, 1650, 480, 16, 0.55)
    _ground_shadow(px, 1722, 480, 16, 0.55)
    _ground_shadow(px, 2104, 480, 16, 0.55)
    _ground_shadow(px, 1592, 479, 26, 0.35)
    _ground_shadow(px, 1980, 479, 22, 0.35)
    _ground_shadow(px, 1660, 479, 14, 0.45)
    _ground_shadow(px, 1996, 479, 14, 0.45)

    # BOSS 房吊灯：房顶 y=40 有一条天花板（solids[2]），挂两盏暖灯
    # 打破"无限平砖"的水平节奏
    lantern(1620, 70)
    lantern(2250, 70)

    # ── 残破矮墙：跳跃段的中景过渡物 ──
    #
    # R2 评审：跳跃段"大面积区域缺乏变化，像程序生成的拼块"。
    # 台阶区（x=1160~1470）两侧加两段 1~2 格高的残墙：
    #  · 墙顶残缺（每列 0~2px 锯齿）
    #  · 墙身同样从瓦片图集 interior 采样
    #  · 位置全在可站表面边缘，不挡跳跃动线（玩家走 x=1200 时
    #    从高台跳下来，矮墙在 x=1500/1550 的地面边缘）

    def low_wall(x, base_y, width, height):
        """矮残墙：宽度向、1~2 格高，顶面锯齿，与地形同材质。"""
        atlas_path = os.path.join(ROOT, "art", "tiles", "tiles_tileset_a.png")
        tile = (Image.open(atlas_path).convert("RGBA")
                if os.path.exists(atlas_path) else None)
        ax, ay, aw, ah = 80, 0, 20, 20
        for i, xx in enumerate(range(x, x + width)):
            jag = ((xx * 53 + x * 7) % 3)   # 顶面锯齿 0~2px
            for yy in range(base_y - height + jag, base_y):
                if not (0 <= xx < ROOM_W and 0 <= yy < ROOM_H):
                    continue
                if tile is not None:
                    c = tile.getpixel((ax + (xx - x) % aw,
                                       ay + (yy % ah)))
                    if c[3] > 128:
                        px[xx, yy] = c[:3] + (255,)
                        continue
                px[xx, yy] = hx("stone")
            # 顶面锯齿描边 + 底部落地
            for yy in (base_y - height + jag, base_y - 1):
                if 0 <= xx < ROOM_W and 0 <= yy < ROOM_H:
                    px[xx, yy] = hx("ink")

    low_wall(1500, 479, 34, 22)
    low_wall(1548, 479, 26, 18)
    _ground_shadow(px, 1500, 479, 40, 0.45)
    _ground_shadow(px, 1548, 479, 32, 0.4)
    # 跳跃段高台顶面的杂草堆（破坏"整片同一纹理"）
    rock_pile(1256, 439, 3)
    rock_pile(1352, 439, 4)

    # ── BOSS 房大型装饰：断墙 + 门框 ──
    #
    # R3b（5 采样）确认 BOSS 房 69 的 top_issue 稳定：
    # 「中景缺石柱以外的道具，纵深只靠背景渐变支撑」。
    # 小石堆撑不起 740px 宽的房间，需要**大件**：
    #   · 断墙两段（x=1750/1880，高 90/70）：墙体同瓦片材质，
    #     顶部大锯齿 + 一块悬挑断砖（暗示坍塌瞬间）
    #   · 门框一组（x=2230）：两根立柱 + 顶梁，洞口透出背景
    #     —— 门洞是像素游戏BOSS 房的经典语言，制造"门后还有空间"的纵深
    # 位置全部避开 BOSS 出生点(1910)与战斗动线中央。

    def broken_wall(x, base_y, width, height):
        """断墙：大面积砖体 + 顶部大锯齿 + 悬挑断砖。"""
        atlas_path = os.path.join(ROOT, "art", "tiles", "tiles_tileset_a.png")
        tile = (Image.open(atlas_path).convert("RGBA")
                if os.path.exists(atlas_path) else None)
        ax, ay, aw, ah = 80, 0, 20, 20
        overhang_x = x + width - 6           # 悬挑断砖的列
        for i, xx in enumerate(range(x, x + width)):
            jag = ((xx * 71 + x * 5) % 5)    # 顶部锯齿 0~4px
            col_top = base_y - height + jag
            # 悬挑断砖：这一列比邻列多出 6px（断裂后凸出的部分）
            if xx == overhang_x:
                col_top -= 6
            elif xx == overhang_x + 1:
                col_top -= 3
            for yy in range(col_top, base_y):
                if not (0 <= xx < ROOM_W and 0 <= yy < ROOM_H):
                    continue
                if tile is not None:
                    c = tile.getpixel((ax + (xx - x) % aw, ay + (yy % ah)))
                    if c[3] > 128:
                        px[xx, yy] = c[:3] + (255,)
                        continue
                px[xx, yy] = hx("stone")
            # 左缘受光 + 右缘压暗（体积）
            if 0 <= x < ROOM_W and x < ROOM_W:
                for yy in range(col_top, base_y):
                    if x <= xx < ROOM_W and 0 <= yy < ROOM_H:
                        if xx == x:
                            px[xx, yy] = hx("stone_hi")
                        elif xx == x + width - 1:
                            px[xx, yy] = hx("stone_dk")
            # 顶部描边
            for yy in (col_top, col_top + 1):
                if 0 <= xx < ROOM_W and 0 <= yy < ROOM_H:
                    px[xx, yy] = hx("ink")
        # 底部基座
        for dx in range(-4, width + 4):
            xx = x + dx
            for k in range(2):
                yy = base_y - k
                if 0 <= xx < ROOM_W and 0 <= yy < ROOM_H:
                    px[xx, yy] = hx("stone_dk" if k == 0 else "stone_hi")

    def gate_frame(x, base_y, inner_w, height):
        """门框：两根立柱 + 顶梁，洞口透出背景（不填充）。"""
        atlas_path = os.path.join(ROOT, "art", "tiles", "tiles_tileset_a.png")
        tile = (Image.open(atlas_path).convert("RGBA")
                if os.path.exists(atlas_path) else None)
        ax, ay, aw, ah = 80, 0, 20, 20
        col_w = 14
        beam_h = 12

        def fill_col(cx0, w, y0, y1):
            for xx in range(cx0, cx0 + w):
                for yy in range(y0, y1):
                    if not (0 <= xx < ROOM_W and 0 <= yy < ROOM_H):
                        continue
                    if tile is not None:
                        c = tile.getpixel((ax + (xx - cx0) % aw,
                                           ay + (yy % ah)))
                        if c[3] > 128:
                            px[xx, yy] = c[:3] + (255,)
                            continue
                    px[xx, yy] = hx("stone")
            # 描边两侧
            for yy in range(y0, y1):
                for xx in (cx0, cx0 + w - 1):
                    if 0 <= xx < ROOM_W and 0 <= yy < ROOM_H:
                        px[xx, yy] = hx("ink")

        # 左柱 / 右柱
        fill_col(x, col_w, base_y - height, base_y)
        fill_col(x + col_w + inner_w, col_w, base_y - height, base_y)
        # 顶梁（横跨洞口）
        fill_col(x, col_w * 2 + inner_w, base_y - height - beam_h,
                 base_y - height)
        # 梁顶锯齿
        for xx in range(x, x + col_w * 2 + inner_w):
            jag = ((xx * 59 + x * 3) % 3)
            for yy in (base_y - height - beam_h + jag,
                       base_y - height - beam_h + jag + 1):
                if 0 <= xx < ROOM_W and 0 <= yy < ROOM_H:
                    px[xx, yy] = hx("ink")
        # 两柱底部基座
        for cx0 in (x, x + col_w + inner_w):
            for dx in range(-3, col_w + 3):
                xx = cx0 + dx
                for k in range(2):
                    yy = base_y - k
                    if 0 <= xx < ROOM_W and 0 <= yy < ROOM_H:
                        px[xx, yy] = hx("stone_dk" if k == 0 else "stone_hi")

    broken_wall(1750, 479, 46, 92)
    broken_wall(1885, 479, 34, 68)
    gate_frame(2200, 479, 40, 96)
    _ground_shadow(px, 1750, 479, 50, 0.6)
    _ground_shadow(px, 1885, 479, 38, 0.55)
    _ground_shadow(px, 2200, 479, 76, 0.6)

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

    deco = make_deco(globals().get("_SOLIDS", []))
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


