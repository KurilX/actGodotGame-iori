"""把 AI 生成的地形图修成游戏可用的瓦片。

## AI 生图的问题

实测这张（`docs/refs/ai/ai_terrain_01.png`，1536×1024）：

  · **28,335 种颜色** —— 全是抗锯齿产生的过渡色。
    像素风要求硬边纯色，必须量化。
  · **右下角有水印**（"AI生成"），要裁掉。
  · **白色背景**，游戏里需要透明。
  · 图片是"一整条地面"，游戏需要的是可平铺的瓦片。

## 处理流程

  1. 裁掉水印区域、取有效地形带
  2. 白色背景 → 透明
  3. **量化到 28 色硬色板**（最近邻映射，不做抖动，
     抖动会在像素画里产生噪点）
  4. 按 20px 网格切成瓦片，并做**无缝性检查**
     （左边缘和右边缘能否接上）

## 为什么要限 28 色

项目规范（docs/02-像素美术规范.md）要求 28 色硬上限。
AI 图几十万色，直接用会破坏整体统一感，也会和其他素材打架。
"""

import os
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "docs", "refs", "ai", "ai_terrain_01.png")
OUT_DIR = os.path.join(ROOT, "art", "ai_tiles")

CELL = 20

# ── 项目 28 色板（与 make_scene_art.py 的 P 保持一致）──
PALETTE = {
    "ink":        "#12142A",
    "night_far":  "#1B2244",
    "night_mid":  "#2A3A63",
    "night_near": "#3D5385",
    "moon_hi":    "#8FD3E8",
    "moon":       "#D8F0F8",
    "stone_hi":   "#7B8699",
    "stone":      "#5A6478",
    "stone_dk":   "#394051",
    # 泥土改成**冷调**：原色板里的 dirt 是暖褐，
    # 直接量化会让 AI 图的褐色泥土保留下来，和夜景紫调打架。
    "dirt_hi":    "#5E5470",
    "dirt":       "#453D58",
    "moss_hi":    "#6E9A6B",
    "moss":       "#4A6B4F",
    "moss_dk":    "#2E4634",
    "grass":      "#5A8A5E",
    "grass_hi":   "#7FA86E",
    "grass_dk":   "#3E5F42",
    "wist":       "#8A6FA8",
    "wist_dk":    "#5E4878",
    "lantern":    "#E8C078",
    "lantern_hi": "#F5DFA8",
    "petal_pink": "#E8A0B8",
    "petal_gold": "#E8D08A",
    "haze_far":   "#4A3D63",
    "haze_near":  "#6B5A85",
    "dusk_mtn_dk": "#4A355E",
    "dusk_mtn":   "#5E4478",
    "dusk_sky":   "#7A5A92",
}


def hex_rgb(h):
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def build_palette():
    """返回 [(rgb, name)]，并额外加入"透明"。"""
    return [(hex_rgb(v), k) for k, v in PALETTE.items()]


def nearest(rgb, pal):
    """最近邻颜色。用加权欧氏距离（人眼对绿色更敏感）。"""
    r, g, b = rgb
    best = None
    best_d = 1e9
    for (pr, pg, pb), name in pal:
        dr = (r - pr) * 1.0
        dg = (g - pg) * 1.2
        db = (b - pb) * 1.0
        d = dr * dr + dg * dg + db * db
        if d < best_d:
            best_d = d
            best = (pr, pg, pb)
    return best


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    im = Image.open(SRC).convert("RGBA")
    W, H = im.size
    px = im.load()
    print(f"源图 {W}x{H}")

    # ── 1. 找有效区域 + 避开右下角水印 ──
    # 水印在右下角约 120x60 的区域
    WM_X0 = W - 260
    WM_Y0 = H - 110

    # **水印要额外裁掉一块**。
    #
    # 第一版只按"白色"找边界，水印是浅灰不会被判定成白，
    # 于是它被算进有效区域，跟着一起量化 —— 结果右下角留着
    # "AI生成"四个字（实测）。
    # 这里直接把右下角 340x70 的区域排除在边界计算之外，
    # 并且在裁剪后**再削掉右侧 200px**，确保水印不会进图。
    def is_white(c):
        return c[0] > 235 and c[1] > 235 and c[2] > 235

    top, bot = H, 0
    left, right = W, 0
    for y in range(0, H, 2):
        for x in range(0, W, 2):
            if WM_X0 <= x and WM_Y0 <= y:
                continue
            if not is_white(px[x, y]):
                top = min(top, y)
                bot = max(bot, y)
                left = min(left, x)
                right = max(right, x)
    print(f"有效区域 x={left}..{right}  y={top}..{bot}")
    # 右侧额外收 210px，确保水印彻底出画
    im = im.crop((left, top, max(left + 100, right + 1 - 210), bot + 1))
    W, H = im.size
    px = im.load()
    print(f"削掉水印后 {W}x{H}")

    # ── 1.5 色块归并（关键一步）──
    #
    # AI 图有大量相近色（比如同一块石头上有 200 种灰），
    # 直接量化到 28 色会把这些细微差异压成**碎玻璃一样的噪点**
    # （实测第一版石块纹理全散了，不如原图干净）。
    #
    # 做法：先做一次**中值滤波**把相似色抹平，再量化。
    # 3x3 中值能有效去掉孤立噪点，同时保留边缘。
    from PIL import ImageFilter
    im = im.filter(ImageFilter.MedianFilter(size=3))
    # 再来一次，力度更大（AI 图的噪点很密）
    im = im.filter(ImageFilter.MedianFilter(size=3))
    px = im.load()
    print("已做 2 轮 3x3 中值滤波")

    # ── 2. 白色→透明，并记录哪些像素是地形 ──
    pal = build_palette()
    q = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    qp = q.load()
    for y in range(H):
        for x in range(W):
            c = px[x, y]
            if is_white(c):
                qp[x, y] = (0, 0, 0, 0)
            else:
                r, g, b = nearest((c[0], c[1], c[2]), pal)
                qp[x, y] = (r, g, b, 255)

    # 统计量化后色数
    used = set()
    for y in range(H):
        for x in range(W):
            if qp[x, y][3] > 0:
                used.add(qp[x, y][:3])
    print(f"量化后用色 {len(used)} 种")

    q.save(os.path.join(OUT_DIR, "ai_terrain_quantized.png"))

    # ── 2.5 缩像素（**最关键的一步**）──
    #
    # AI 图看着是"像素画"，但它的像素颗粒其实是 **8px**：
    # 实测单行同色连续长度中位数 = 8。
    #
    # 直接把它贴进游戏（1px = 1 像素）会得到**巨大的色块**——
    # 实测放大 4 倍看，草皮变成一块块绿方块，完全没有细节。
    #
    # 正确做法：**缩小到 1/8**，让 8px 颗粒变成 1px 颗粒，
    # 也就是把 AI 图变成真正的像素画。缩小用 NEAREST 保持硬边。
    DOWNSCALE = 8
    sw = max(1, W // DOWNSCALE)
    sh = max(1, H // DOWNSCALE)
    small = q.resize((sw, sh), Image.NEAREST)
    small.save(os.path.join(OUT_DIR, "ai_terrain_pixel.png"))
    print(f"缩像素后 {sw}x{sh}（1/{DOWNSCALE}）")

    # ── 3. 切瓦片 ──
    cols = W // CELL
    rows = H // CELL
    print(f"可切 {cols}x{rows} 格")
    sheet = Image.new("RGBA", (max(1, cols) * CELL, max(1, rows) * CELL),
                      (0, 0, 0, 0))
    for ry in range(rows):
        for rx in range(cols):
            tile = q.crop((rx * CELL, ry * CELL,
                           (rx + 1) * CELL, (ry + 1) * CELL))
            sheet.alpha_composite(tile, (rx * CELL, ry * CELL))
    sheet.save(os.path.join(OUT_DIR, "ai_tileset.png"))

    # ── 3.5 做可平铺（**修接缝**）──
    #
    # AI 图的左右边缘完全无关，直接平铺会出现明显接缝
    # （实测平均差 183 / 255）。
    #
    # 做法：**镜像拼接**。取原图 + 它的水平镜像，合成一张两倍宽的图。
    # 镜像处天然无缝（因为边缘像素相同），而且镜像本身也看不出来
    # —— 石头纹理左右对称不违和，这是像素游戏常用的偷懒技巧。
    #
    # 代价：图案会重复，所以只适合"地面带"这种一眼扫过的东西。
    mirrored = Image.new("RGBA", (sw * 2, sh), (0, 0, 0, 0))
    mirrored.alpha_composite(small, (0, 0))
    mirrored.alpha_composite(small.transpose(Image.FLIP_LEFT_RIGHT), (sw, 0))
    mirrored.save(os.path.join(OUT_DIR, "ai_terrain_tileable.png"))
    print(f"可平铺版 {mirrored.width}x{mirrored.height}（镜像拼接）")

    # 验证镜像后接缝
    mp = mirrored.load()
    diffs = []
    for y in range(sh):
        a = mp[0, y]
        b = mp[mirrored.width - 1, y]
        if a[3] == 0 and b[3] == 0:
            continue
        diffs.append(abs(a[0] - b[0]) + abs(a[1] - b[1]) + abs(a[2] - b[2]))
    print(f"  镜像后左右差：平均 {sum(diffs)/max(1,len(diffs)):.1f}")

    # ── 4. 无缝性检查：左右边缘能否接上 ──
    print("\n无缝性检查（左边缘 vs 右边缘的像素差）:")
    diffs = []
    for y in range(H):
        a = qp[0, y]
        b = qp[W - 1, y]
        if a[3] == 0 and b[3] == 0:
            continue
        d = abs(a[0] - b[0]) + abs(a[1] - b[1]) + abs(a[2] - b[2])
        diffs.append(d)
    if diffs:
        avg = sum(diffs) / len(diffs)
        print(f"  平均差 {avg:.1f}（0 表示完全可接）")
        print(f"  差异行数 {len(diffs)} / {H}")
    else:
        print("  无有效行")

    print(f"\n输出: {OUT_DIR}/ai_terrain_quantized.png")
    print(f"      {OUT_DIR}/ai_tileset.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
