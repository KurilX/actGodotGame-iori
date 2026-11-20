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
    "ink":      "#12142A",   # 01 最暗：描边
    "night_far":  "#1B2244",  # 02 夜色远
    "night_mid":  "#2A3A63",  # 03 夜色中
    "night_near": "#3D5385",  # 04 夜色近
    "moon_hi":  "#8FD3E8",   # 05 月光高光
    "moon":     "#D8F0F8",   # 06 月白
    "stone":    "#5A6478",   # 07 石中
    "stone_dk": "#394051",   # 08 石暗
    "stone_hi": "#7B8699",   # 09 石亮
    "moss":     "#4A6B4F",   # 10 苔中
    "moss_dk":  "#2E4634",   # 11 苔暗
    "moss_hi":  "#6E9A6B",   # 12 苔亮
    "wist":     "#7A5FA8",   # 13 紫藤中
    "wist_dk":  "#4F3D74",   # 14 紫藤暗
    "wist_hi":  "#A98FD6",   # 15 紫藤亮
    "lant_hi":  "#FFE9A8",   # 16 灯笼亮
    "lant":     "#FFC46B",   # 17 灯笼中
    "lant_dk":  "#E0913F",   # 18 灯笼暗
}

# 4×4 Bayer 有序抖动矩阵（模块级：天空、月亮光晕、灯笼光晕都要用）
BAYER = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]

ROOM_W, ROOM_H = 960, 540
GROUND_Y = 480          # 地面顶部（与 SOLIDS 一致）


def hx(key, a=255):
    h = P[key].lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a)


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
    stops = [
        (0.00, hx("night_far")),
        (0.50, hx("night_mid")),
        (1.00, hx("night_near")),
    ]

    for y in range(int(GROUND_Y)):
        t = max(0.0, (y - VIS_TOP)) / max(1.0, GROUND_Y - VIS_TOP)
        # 找所在区间
        seg = 0
        for i in range(len(stops) - 1):
            if stops[i][0] <= t <= stops[i + 1][0]:
                seg = i
                break
        t0, c0 = stops[seg]
        t1, c1 = stops[seg + 1]
        local = 0.0 if t1 <= t0 else (t - t0) / (t1 - t0)

        for x in range(ROOM_W):
            th = (BAYER[y % 4][x % 4] + 0.5) / 16.0
            c = c1 if local > th else c0
            px[x, y] = c

    # ── 远山三层：越远越暗、越平缓 ──
    rng = random.Random(20261120)
    # 波长要远大于画面宽容度才像"山"，早期用 120~210 导致每屏出现 5~8 个峰，
    # 看起来是锯齿不是山。改成波长 380~620，每屏只有 1~2 个主峰。
    # **重要**：相机被 limit_bottom=540 卡住，玩家站地面时
    # 可见区域只有 y=270~540（视口 270 高）。远山必须落在这个区间内，
    # 否则玩家永远看不到（第一版放在 y=150~288，结果整片山都在画面外）。
    layers = [
        # (颜色, 基准高度, 起伏幅度, 波长)
        (hx("night_far"),  318, 26, 620),
        (hx("night_mid"),  368, 32, 460),
        (hx("night_near"), 420, 38, 380),
    ]
    for color, base, amp, wave in layers:
        for x in range(ROOM_W):
            # 多频正弦叠加，避免呆板的规则山脉
            h = (math.sin(x / wave * math.tau) * amp
                 + math.sin(x / (wave * 0.43) * math.tau + 1.7) * amp * 0.45
                 + math.sin(x / (wave * 0.21) * math.tau + 3.1) * amp * 0.22)
            top = int(base + h)
            for y in range(max(0, top), int(GROUND_Y)):
                px[x, y] = color

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
    """地形层：石台。

    立体感来自**顶面/立面两级明暗**：
      · 顶面（受光）石亮 #7B8699
      · 立面（背光）石中 #5A6478
      · 底部阴影  石暗 #394051
      · 外轮廓    夜色最暗 #12142A（不是纯黑）

    再叠苔藓（顶面边缘）和石块纹理（立面随机砖缝）。
    """
    img = Image.new("RGBA", (ROOM_W, ROOM_H), (0, 0, 0, 0))
    px = img.load()
    rng = random.Random(777)

    # SOLIDS 的几何 —— **必须与 room_greybox.gd 的 SOLIDS 常量完全一致**。
    # 早期这里只写了 4 块（凭印象），实际有 8 块，导致贴图上的石台
    # 与碰撞体错位：玩家会踩空或撞到看不见的墙。
    solids = [
        (0, 480, 960, 60),      # 地面（整条）
        (0, 420, 96, 60),       # 左侧台阶 1
        (96, 372, 72, 48),      # 左侧台阶 2
        (168, 324, 60, 48),     # 左侧台阶 3
        (300, 340, 120, 24),    # 中间高台
        (720, 288, 48, 192),    # 右侧塔
        (768, 420, 192, 60),    # 右侧地面段
        (0, 0, 960, 20),        # 天花板
    ]

    for i, (x, y, w, h) in enumerate(solids):
        # 立面
        fill_rect(px, x, y, x + w, y + h, hx("stone"))
        # 顶面高光（2px）
        fill_rect(px, x, y, x + w, y + 2, hx("stone_hi"))
        # 底部阴影（渐变 3 行）
        for k in range(3):
            c = hx("stone_dk") if k == 2 else hx("stone")
            fill_rect(px, x, y + h - 3 + k, x + w, y + h - 2 + k, c)
        # 外轮廓：左侧和顶部
        fill_rect(px, x, y, x + 1, y + h, hx("ink"))
        fill_rect(px, x, y, x + w, y + 1, hx("ink"))
        # 右侧轮廓
        fill_rect(px, x + w - 1, y, x + w, y + h, hx("ink"))

        # 立面砖缝纹理
        if h > 10 and w > 40:
            n_bricks = max(1, h // 22)
            for b in range(n_bricks):
                by = y + 6 + b * 22
                if by >= y + h - 5:
                    break
                # 横向砖缝
                for bx in range(x + 2, x + w - 2):
                    if (bx + b * 7) % 23 < 18:
                        if 0 <= by < ROOM_H:
                            px[bx, by] = hx("stone_dk")
                # 竖向砖缝，错缝排列
                offset = 11 if b % 2 == 0 else 0
                for bx in range(x + 8 + offset, x + w - 4, 22):
                    for k in range(4):
                        if by + k < y + h - 4 and 0 <= by + k < ROOM_H:
                            px[bx + k - k, by + k] = hx("stone_dk")

    # ── 苔藓：覆在每块石台顶部边缘 ──
    # 天花板（y=0）不长苔藓，它的"顶面"在屏幕外，长了会显得奇怪
    for (x, y, w, h) in solids:
        if y <= 0:
            continue
        for bx in range(x + 1, x + w - 1):
            # 苔藓高度随机 1~3px，形成不规则边缘
            mh = 1 + (1 if (bx * 7919) % 3 == 0 else 0) + (1 if (bx * 104729) % 7 == 0 else 0)
            for k in range(mh):
                yy = y - 1 - k
                if 0 <= yy < ROOM_H:
                    px[bx, yy] = hx("moss_hi") if k == mh - 1 else hx("moss")
        # 苔藓垂下的几缕
        for _ in range(w // 40):
            bx = x + rng.randint(4, max(5, w - 6))
            drips = rng.randint(1, 4)
            for k in range(drips):
                yy = y + 2 + k
                if 0 <= yy < ROOM_H:
                    px[bx, yy] = hx("moss")
                    if 0 <= bx + 1 < ROOM_W:
                        px[bx + 1, yy] = hx("moss_dk")

    return img


# ─────────────────────── 近景：装饰 ───────────────────────

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
