"""BOSS「瓷面的守夜人」：从概念图切出精灵，量化为游戏调色板。

尺寸决策：
  主角 48px、杂兵 30~36px，BOSS 定 **96px**（正好 2 倍主角）。
  这个比例关系很重要 —— 太小没有压迫感，太大又会挤满 480x270 的视口
  （96px 已占屏幕高度的 36%）。

输出：art/boss/src/warden.png
"""

import os

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "art", "boss", "00_concept.png")
OUT = os.path.join(ROOT, "art", "boss", "src")

TARGET_H = 96

# 游戏主色板（docs/02-像素美术规范.md）+ BOSS 额外需要的少数几个色
PALETTE_HEX = [
    "#12142A", "#1B2244", "#2A3A63", "#3D5385", "#8FD3E8", "#D8F0F8",
    "#5A6478", "#394051", "#7B8699", "#4A6B4F", "#2E4634", "#6E9A6B",
    "#7A5FA8", "#4F3D74", "#A98FD6", "#FFE9A8", "#FFC46B", "#E0913F",
    "#F2F8EC", "#C4D8C2", "#A8E8C6", "#5FA882", "#FBE3D2", "#E2B49B",
    "#FF7A9C", "#C2456A", "#B9F2FF", "#FFFFFF",
]

# BOSS 专属色：瓷面偏冷、和服偏深紫、眼睛是红裂缝、胸口暖光
EXTRA_HEX = [
    "#E8F0F2",  # 瓷面亮（比纯白冷）
    "#B9C8CE",  # 瓷面中
    "#8496A0",  # 瓷面暗
    "#2E2440",  # 和服深紫黑
    "#4A3A5E",  # 和服中紫
    "#7A2E48",  # 红裂缝暗
    "#FF8FA8",  # 红裂缝亮
    "#FF9A4A",  # 胸光暖橙
]


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def build_palette():
    flat = []
    for hv in PALETTE_HEX + EXTRA_HEX:
        flat.extend(hex_rgb(hv))
    flat.extend([0] * (256 * 3 - len(flat)))
    pal = Image.new("P", (1, 1))
    pal.putpalette(flat)
    return pal


def detect_bg(img):
    """在原图上取四角平均色作为背景。"""
    w, h = img.size
    px = img.load()
    pts = [px[0, 0], px[w - 1, 0], px[0, h - 1], px[w - 1, h - 1],
           px[w // 2, 0], px[w // 2, h - 1]]
    n = len(pts)
    return tuple(sum(p[i] for p in pts) / n for i in range(3))


def main():
    os.makedirs(OUT, exist_ok=True)
    img = Image.open(SRC).convert("RGB")
    bg = detect_bg(img)
    W, H = img.size
    px = img.load()

    def is_bg(c, tol=30):
        return (abs(c[0] - bg[0]) < tol and abs(c[1] - bg[1]) < tol
                and abs(c[2] - bg[2]) < tol)

    # 前景包围盒
    xs, ys = [], []
    for y in range(0, H, 2):
        for x in range(0, W, 2):
            if not is_bg(px[x, y]):
                xs.append(x)
                ys.append(y)
    if not xs:
        raise RuntimeError("找不到前景")
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    pad = 6
    crop = img.crop((max(0, x0 - pad), max(0, y0 - pad),
                     min(W, x1 + pad + 1), min(H, y1 + pad + 1)))
    print(f"前景裁切 {crop.size}（原图 {W}x{H}）")

    # 缩放到目标高度
    cw, ch = crop.size
    tw = max(1, round(cw * TARGET_H / ch))
    small = crop.resize((tw, TARGET_H), Image.BOX)

    # 边缘 flood-fill 抠背景（在量化前做，保护内部浅色）
    sw, sh = small.size
    spx = small.load()

    def is_bg_small(c):
        return (abs(c[0] - bg[0]) < 40 and abs(c[1] - bg[1]) < 40
                and abs(c[2] - bg[2]) < 40)

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
        if x < 0 or y < 0 or x >= sw or y >= sh or mask[y][x]:
            continue
        if not is_bg_small(spx[x, y]):
            continue
        mask[y][x] = True
        stack.extend([(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)])

    # 量化
    pal = build_palette()
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

    path = os.path.join(OUT, "warden.png")
    out.save(path)
    transparent = sum(1 for y in range(sh) for x in range(sw) if opx[x, y][3] == 0)
    print(f"warden.png {out.size}  透明率 {100 * transparent / (sw * sh):.0f}%")


if __name__ == "__main__":
    main()
