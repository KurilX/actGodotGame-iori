"""从概念图生成 48px 占位角色精灵，并输出 12x12 瓦片图集。

用途：Godot 工程 W1 灰盒阶段先用真实像素素材跑起来，之后再替换为手绘图。
流程：裁出概念图第一个姿势 → 降到 48px 高 → 量化到 28 色板 → 去背景（透明）

输出：
  art/characters/ori/ori_idle.png      48px 主角占位精灵（透明背景）
  art/tilesets/greybox_tiles.png       12x12 瓦片图集（4 种地形）
"""

import os

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_CONCEPT = os.path.join(ROOT, "art", "concept", "06-heroine-chibi-48px.png")
OUT_SPRITE = os.path.join(ROOT, "art", "characters", "ori", "ori_idle_src.png")
OUT_TILES = os.path.join(ROOT, "art", "tilesets", "greybox_tiles.png")

TARGET_H = 48
TILE = 12

# 28 色板（与 art/palette.gpl 一致）
PALETTE_HEX = [
    "#12142A", "#1B2244", "#2A3A63", "#3D5385", "#8FD3E8", "#D8F0F8",
    "#5A6478", "#394051", "#7B8699", "#4A6B4F", "#2E4634", "#6E9A6B",
    "#7A5FA8", "#4F3D74", "#A98FD6", "#FFE9A8", "#FFC46B", "#E0913F",
    "#F2F8EC", "#C4D8C2", "#A8E8C6", "#5FA882", "#FBE3D2", "#E2B49B",
    "#FF7A9C", "#C2456A", "#B9F2FF", "#FFFFFF",
]


def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def build_palette_image():
    flat = []
    for hv in PALETTE_HEX:
        flat.extend(hex_to_rgb(hv))
    flat.extend([0] * (256 * 3 - len(flat)))
    pal = Image.new("P", (1, 1))
    pal.putpalette(flat)
    return pal


def detect_bg(img):
    w, h = img.size
    px = img.load()
    pts = [px[0, 0], px[w - 1, 0], px[0, h - 1], px[w - 1, h - 1],
           px[w // 2, 0], px[w // 2, h - 1]]
    n = len(pts)
    return tuple(sum(p[i] for p in pts) / n for i in range(3))


def crop_first_figure(img):
    rgb = img.convert("RGB")
    w, h = rgb.size
    px = rgb.load()
    bg = detect_bg(rgb)
    tol = 14

    def is_fg(x, y):
        c = px[x, y]
        return max(abs(c[0] - bg[0]), abs(c[1] - bg[1]), abs(c[2] - bg[2])) > tol

    filled = [any(is_fg(x, y) for y in range(0, h, 2)) for x in range(w)]
    runs, start = [], None
    for x, f in enumerate(filled):
        if f and start is None:
            start = x
        elif not f and start is not None:
            runs.append((start, x - 1))
            start = None
    if start is not None:
        runs.append((start, w - 1))

    merged = []
    for a, b in runs:
        if merged and a - merged[-1][1] <= 6:
            merged[-1] = (merged[-1][0], b)
        else:
            merged.append((a, b))
    if not merged:
        raise RuntimeError("未找到前景")

    x0, x1 = merged[0]
    ys = [y for y in range(h) if any(is_fg(x, y) for x in range(x0, x1 + 1, 2))]
    y0, y1 = min(ys), max(ys)

    # 关键：四周留出 4px 纯背景边。
    # 若裁到贴边，flood-fill 的种子点会全部落在角色身上，背景清不掉。
    pad = 4
    canvas = Image.new("RGB", (x1 - x0 + 1 + pad * 2, y1 - y0 + 1 + pad * 2),
                       tuple(int(v) for v in bg))
    canvas.paste(rgb.crop((x0, y0, x1 + 1, y1 + 1)), (pad, pad))
    return canvas


def make_sprite():
    fig = crop_first_figure(Image.open(SRC_CONCEPT))
    w, h = fig.size
    tw = max(1, round(w * TARGET_H / h))
    small = fig.resize((tw, TARGET_H), Image.BOX)

    # 先从边缘 flood-fill 抠背景（必须在量化前做）。
    # 教训：如果先量化再判断，背景 (249,247,249) 会被吸附到色板里的
    # 披肩亮 #F2F8EC=(242,248,236)，与角色身上的白色部件混在一起，
    # 导致背景整片留下来变成白方块。所以判定必须在原始 RGB 上做。
    sw, sh = small.size
    spx = small.load()
    bg = detect_bg(small)
    tol = 26

    def is_bg(c):
        return max(abs(c[0] - bg[0]), abs(c[1] - bg[1]), abs(c[2] - bg[2])) <= tol

    # 洪水填充：只清除与边界连通的背景，角色身上的白色衬衣不会被误伤
    mask = [[False] * sw for _ in range(sh)]
    stack = []
    for x in range(sw):
        stack.append((x, 0))
        stack.append((x, sh - 1))
    for y in range(sh):
        stack.append((0, y))
        stack.append((sw - 1, y))

    while stack:
        x, y = stack.pop()
        if x < 0 or y < 0 or x >= sw or y >= sh:
            continue
        if mask[y][x]:
            continue
        if not is_bg(spx[x, y]):
            continue
        mask[y][x] = True
        stack.extend([(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)])

    # 量化（保留原始尺寸的 RGB）
    pal = build_palette_image()
    quant = small.quantize(palette=pal, dither=Image.NONE).convert("RGB")
    qpx = quant.load()

    out = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
    opx = out.load()
    for y in range(sh):
        for x in range(sw):
            if mask[y][x]:
                continue
            r, g, b = qpx[x, y]
            opx[x, y] = (r, g, b, 255)

    os.makedirs(os.path.dirname(OUT_SPRITE), exist_ok=True)
    out.save(OUT_SPRITE)
    removed = sum(sum(1 for v in row if v) for row in mask)
    print(f"wrote {OUT_SPRITE} ({out.size[0]}x{out.size[1]}, 抠除 {removed} 个背景像素)")
    return out.size


def make_tileset():
    """4 种 12x12 瓦片横排：0 实心石 1 草皮顶 2 平台 3 背景砖"""
    ink = hex_to_rgb("#12142A")
    stone = hex_to_rgb("#5A6478")
    stone_dark = hex_to_rgb("#394051")
    stone_lit = hex_to_rgb("#7B8699")
    moss = hex_to_rgb("#4A6B4F")
    moss_lit = hex_to_rgb("#6E9A6B")
    night = hex_to_rgb("#2A3A63")

    atlas = Image.new("RGBA", (TILE * 4, TILE), (0, 0, 0, 0))

    def px(x, y, c):
        atlas.putpixel((x, y), (c[0], c[1], c[2], 255))

    # 瓦片 0：实心石（左上亮、右侧暗、外框墨线）
    for y in range(TILE):
        for x in range(TILE):
            c = stone
            if x == 0 or y == 0:
                c = stone_lit
            if x == TILE - 1 or y == TILE - 1:
                c = stone_dark
            if x == 0 or y == 0 or x == TILE - 1 or y == TILE - 1:
                if x == 0 or y == 0:
                    c = ink if (x == 0 and y == 0) else c
            px(x, y, c)
    for i in range(TILE):
        px(0, i, ink)
        px(i, 0, ink)

    # 瓦片 1：草皮顶（上半绿，下半石）
    ox = TILE
    for y in range(TILE):
        for x in range(TILE):
            if y < 4:
                c = moss_lit if y < 2 else moss
            else:
                c = stone if y < TILE - 1 else stone_dark
            px(ox + x, y, c)
    for i in range(TILE):
        px(ox + i, 0, ink)
        px(ox, i, ink)

    # 瓦片 2：单向平台（薄板）
    ox = TILE * 2
    for y in range(TILE):
        for x in range(TILE):
            if y < 3:
                c = stone_lit if y == 0 else stone
            elif y == 3:
                c = stone_dark
            else:
                continue
            px(ox + x, y, c)

    # 瓦片 3：背景砖（低对比，只做装饰）
    ox = TILE * 3
    for y in range(TILE):
        for x in range(TILE):
            c = night
            if (x % 6 == 0) or (y % 6 == 0):
                c = stone_dark
            px(ox + x, y, c)

    os.makedirs(os.path.dirname(OUT_TILES), exist_ok=True)
    atlas.save(OUT_TILES)
    print(f"wrote {OUT_TILES} ({atlas.size[0]}x{atlas.size[1]})")


if __name__ == "__main__":
    make_sprite()
    make_tileset()
