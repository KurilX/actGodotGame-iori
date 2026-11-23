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

def make_sky():
    """夜空：垂直渐变 + 月亮 + 三层远山。

    渐变用**有序抖动**（4×4 Bayer），不是平滑渐变 ——
    平滑渐变在像素画里会产生上百种中间色，直接破坏 28 色约束。
    抖动让相邻两种纯色交错，远看是渐变，近看仍是纯色块。
    """
    img = Image.new("RGBA", (ROOM_W, ROOM_H), (0, 0, 0, 0))
    px = img.load()



    # 天空分三段：顶部夜色远 → 中部夜色中 → 底部夜色近
    # 每段之间用抖动过渡（16 级）
    # 渐变只在**可见区间**（相机看到的 y=270~480）内做，
    # 这样玩家眼前总有层次，而不是一整片纯色。
    VIS_TOP = 265
    # 两套配色：x < TUTORIAL_END 用黄昏，x >= 用夜色。
    # 在边界前后 120px 内做**抖动混合**：黄昏色和夜色按比例交错，
    # 远看是平滑过渡，近看仍是纯色块（不破坏像素感、不引入新颜色）。
    # **只从调色板取值，不计算中间色**。
    # 第一版用 hex_rgb() 直接算，产生了 7 个不在调色板里的色
    # （用色统计 29/28）。像素风要求所有颜色必须是调色板成员。
    dusk_stops = [
        (0.00, hx("dusk_mtn_dk")),
        (0.50, hx("dusk_sky")),
        (1.00, hx("dusk_glow")),
    ]
    night_stops = [
        (0.00, hx("night_far")),
        (0.50, hx("night_mid")),
        (1.00, hx("night_near")),
    ]

    def pick_stops(x):
        """返回该 x 位置应使用的配色。过渡区里按 x 决定，由抖动实现混合。"""
        return dusk_stops if x < TUTORIAL_END else night_stops
    BLEND = 120

    for y in range(int(GROUND_Y)):
        t = max(0.0, (y - VIS_TOP)) / max(1.0, GROUND_Y - VIS_TOP)

        for x in range(ROOM_W):
            # 过渡带：黄昏/夜色按 x 位置和抖动比例混合
            if x < TUTORIAL_END - BLEND:
                stops = dusk_stops
            elif x >= TUTORIAL_END:
                stops = night_stops
            else:
                # 过渡带内，抖动决定这一像素取哪套
                th_blend = (BAYER[y % 4][x % 4] + 0.5) / 16.0
                ratio = (x - (TUTORIAL_END - BLEND)) / BLEND
                stops = night_stops if th_blend < ratio else dusk_stops

            seg = 0
            for i in range(len(stops) - 1):
                if stops[i][0] <= t <= stops[i + 1][0]:
                    seg = i
                    break
            t0, c0 = stops[seg]
            t1, c1 = stops[seg + 1]
            local = 0.0 if t1 <= t0 else (t - t0) / (t1 - t0)

            th = (BAYER[y % 4][x % 4] + 0.5) / 16.0
            c = c1 if local > th else c0
            px[x, y] = c

    # ── 远山：**五层**（原 3 层）──
    #
    # 原来只有 3 层纯色山，看起来像剪纸。改进点：
    #   1. 加两层「薄雾山」做空气透视 —— 越远的山越接近天空色，
    #      这是产生"景深"最廉价也最有效的手段
    #   2. 每个山脊加**边缘高光**：山体顶部 1~2px 用亮一档的颜色，
    #      模拟天光照在山脊上，山的立体感立刻出来
    #   3. 山体内部加低频色块扰动，避免大面积纯色
    rng = random.Random(20261120)

    # (夜色, 黄昏色, 基准高度, 起伏幅度, 波长, 是否加脊线高光)
    # (夜色, 黄昏色, 夜色高光, 黄昏高光, 基准高度, 起伏, 波长, 是否加脊线)
    layers = [
        # 最远：薄雾山（贴着天空色，几乎融进去）
        (hx("haze_far"),   hx("haze_far"),   hx("haze_far"),   hx("haze_far"),   300, 30, 700, False),
        # 远
        (hx("night_far"),  hx("dusk_mtn_dk"), hx("haze_far"),  hx("haze_near"),  326, 34, 580, True),
        # 中远
        (hx("haze_near"),  hx("haze_near"),  hx("haze_near"),  hx("haze_near"),  352, 30, 480, False),
        # 中
        (hx("night_mid"),  hx("dusk_mtn"),   hx("night_far"),  hx("haze_near"),  382, 36, 420, True),
        # 近
        (hx("night_near"), hx("dusk_sky"),   hx("night_mid"),  hx("haze_near"),  424, 40, 340, True),
    ]

    # 每层用不同的高频多段叠加，做出山的"肩线"
    for night_c, dusk_c, night_hi, dusk_hi, base, amp, wave, rim in layers:
        heights = []
        for x in range(ROOM_W):
            h = (math.sin(x / wave * math.tau) * amp
                 + math.sin(x / (wave * 0.43) * math.tau + 1.7) * amp * 0.45
                 + math.sin(x / (wave * 0.21) * math.tau + 3.1) * amp * 0.22)
            heights.append(int(base + h))

        for x in range(ROOM_W):
            color = dusk_c if x < TUTORIAL_END else night_c
            top = heights[x]
            for y in range(max(0, top), int(GROUND_Y)):
                px[x, y] = color

            # 山体内部的低频色块扰动（每 24px 一块，错开避免规则感）
            if (x // 24 + (top // 18)) % 5 == 0:
                if y_ok := top + 30 < GROUND_Y:
                    for yy in range(top + 30, min(GROUND_Y, top + 70)):
                        px[x, yy] = color

            # 山脊高光：顶端 2px 用调色板内的更亮山色（不计算，避免越界）
            if rim:
                hi = dusk_hi if x < TUTORIAL_END else night_hi
                for k in range(2):
                    if 0 <= top + k < int(GROUND_Y):
                        px[x, top + k] = hi


    # ── 月亮（右上，柔光晕）──
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
                # 光晕：用抖动做半透明。
                # 原来铺到 moon_r+12 且密度 0.45，观感是一团发虚的白雾，
                # 收窄到 +7、密度降到 0.28，只留一圈薄晕。
                th = (BAYER[y % 4][x % 4] + 0.5) / 16.0
                if th < 0.28 * (1.0 - (d - moon_r - 3) / 4.0):
                    px[x, y] = hx("moon_hi")

    # 月亮上的暗斑（让它不是个纯白圆）
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

    # **必须与 room_greybox.gd 的 SOLIDS 完全一致** ——
    # 否则贴图上的石台会和碰撞体错位，玩家会踩空或撞到看不见的墙。
    solids = [
        (0, 480, 2400, 60),      # 地面（整条）
        # ① 移动教学：三级台阶
        (120, 440, 72, 40),
        (220, 400, 72, 40),
        (320, 360, 72, 40),
        (0, 250, 150, 20),
        # ③ 重攻击教学：石守的高台
        (930, 420, 130, 60),
        # ⑤ 综合段
        (1900, 440, 90, 40),
        # 主关卡：BOSS 房
        (2160, 288, 48, 192),
        (2208, 420, 192, 60),
        (1560, 0, 840, 12),
        # 边界
        (0, 0, 2400, 12),
    ]

    for (x, y, w, h) in solids:
        _draw_solid(px, rng, x, y, w, h)

    return img


def _draw_solid(px, rng, x, y, w, h):
    """画一块地形：岩层 + 明暗台阶 + 草皮 + 细节。"""

    # 草皮参数（实际绘制在函数末尾，这里只声明）
    # 判断"顶部是否露天"：地面和台阶算露天，天花板/墙不算
    is_surface = 20 < y < GROUND_Y + 40
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
