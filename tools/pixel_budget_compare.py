"""把 Q 版概念图按不同像素身高降采样并标注，用于定稿像素尺度。

注意：这是「硬降采样」的下限测试。真实手绘像素会在低分辨率下主动简化造型，
效果优于本图。本图只用于排除「再怎么画也救不回来」的尺度。

输出：art/concept/05-pixel-budget-comparison.png
"""

import os

from PIL import Image, ImageDraw

SRC = "art/concept/06-heroine-chibi-48px.png"
OUT = "art/concept/05-pixel-budget-comparison.png"

# (角色像素身高, 对应内部渲染分辨率, 窗口放大说明)
# v0.4 定稿 48px；其余档位用于验证下限
CANDIDATES = [
    (48, "480x270", "3x -> 1440x810"),
    (40, "400x225", "非整数倍"),
    (32, "320x180", "4x -> 1280x720"),
    (26, "256x144", "5x -> 1280x720"),
]

PALETTE_HEX = [
    "#12142A", "#1B2244", "#2A3A63", "#3D5385", "#8FD3E8", "#D8F0F8",
    "#5A6478", "#394051", "#7B8699", "#4A6B4F", "#2E4634", "#6E9A6B",
    "#7A5FA8", "#4F3D74", "#A98FD6", "#FFE9A8", "#FFC46B", "#E0913F",
    "#F2F8EC", "#C4D8C2", "#A8E8C6", "#5FA882", "#FBE3D2", "#E2B49B",
    "#FF7A9C", "#C2456A", "#B9F2FF", "#FFFFFF",
]

SCALE = 12
GAP = 26
LABEL_H = 42


def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def detection_bg(img):
    """用四角采样推断背景色，容忍带色偏的白底（如 (249,247,249)）。"""
    rgb = img.convert("RGB")
    w, h = rgb.size
    px = rgb.load()
    samples = [px[0, 0], px[w - 1, 0], px[0, h - 1], px[w - 1, h - 1],
               px[w // 2, 0], px[w // 2, h - 1], px[0, h // 2], px[w - 1, h // 2]]
    r = sum(s[0] for s in samples) / len(samples)
    g = sum(s[1] for s in samples) / len(samples)
    b = sum(s[2] for s in samples) / len(samples)
    return (r, g, b)


def crop_first_figure(img):
    """按空白列分割，取最左侧的第一个人物。

    直接按包围盒裁会把相邻人物一起带进来（概念图里多个姿势并排），
    所以先找出所有「有前景的列」，再按列缺口切分成若干段，取第一段。
    背景色用四角采样推断——AI 图的白底常带色偏，不能用纯白判定。
    """
    rgb = img.convert("RGB")
    w, h = rgb.size
    px = rgb.load()
    bg = detection_bg(rgb)
    tol = 12

    def bg_dist(c):
        return max(abs(c[0] - bg[0]), abs(c[1] - bg[1]), abs(c[2] - bg[2]))

    def is_fg(x, y):
        return bg_dist(px[x, y]) > tol

    filled = [any(is_fg(x, y) for y in range(0, h, 2)) for x in range(w)]

    runs = []
    start = None
    for x, f in enumerate(filled):
        if f and start is None:
            start = x
        elif not f and start is not None:
            runs.append((start, x - 1))
            start = None
    if start is not None:
        runs.append((start, w - 1))

    # 合并被细小空隙隔开的碎片，取最左侧一段
    merged = []
    for a, b in runs:
        if merged and a - merged[-1][1] <= 6:
            merged[-1] = (merged[-1][0], b)
        else:
            merged.append((a, b))
    if not merged:
        raise RuntimeError("未找到前景像素")

    x0, x1 = merged[0]
    ys = [y for y in range(h) if any(is_fg(x, y) for x in range(x0, x1 + 1, 2))]
    y0, y1 = min(ys), max(ys)
    pad = 3
    return rgb.crop((max(0, x0 - pad), max(0, y0 - pad),
                     min(w, x1 + pad + 1), min(h, y1 + pad + 1)))


def to_pixel_art(fig, target_h):
    w, h = fig.size
    tw = max(1, round(w * target_h / h))
    small = fig.resize((tw, target_h), Image.BOX)

    pal_img = Image.new("P", (1, 1))
    flat = []
    for hv in PALETTE_HEX:
        flat.extend(hex_to_rgb(hv))
    flat.extend([0] * (256 * 3 - len(flat)))
    pal_img.putpalette(flat)
    quant = small.convert("RGB").quantize(palette=pal_img, dither=Image.NONE)

    # 背景统一压成纯白，避免量化把白底染成月白
    q = quant.convert("RGB")
    qpx = q.load()
    for y in range(q.size[1]):
        for x in range(q.size[0]):
            r, g, b = qpx[x, y]
            if r > 230 and g > 235 and b > 228:
                qpx[x, y] = (255, 255, 255)

    return q.resize((tw * SCALE, target_h * SCALE), Image.NEAREST)


def main():
    fig = crop_first_figure(Image.open(SRC))
    print(f"cropped figure: {fig.size}")

    tiles = [(th, res, note, to_pixel_art(fig, th)) for th, res, note in CANDIDATES]

    total_w = sum(t.width for _, _, _, t in tiles) + GAP * (len(tiles) + 1)
    total_h = max(t.height for _, _, _, t in tiles) + GAP * 2 + LABEL_H
    canvas = Image.new("RGB", (total_w, total_h), (255, 255, 255))
    draw = ImageDraw.Draw(canvas)

    x = GAP
    for th, res, note, t in tiles:
        canvas.paste(t, (x, GAP + LABEL_H))
        draw.text((x, GAP), f"hero {th}px  {res}", fill=(20, 20, 30))
        draw.text((x, GAP + 16), note, fill=(110, 110, 125))
        x += t.width + GAP

    canvas.save(OUT)
    print(f"wrote {OUT} ({canvas.size[0]}x{canvas.size[1]})")


if __name__ == "__main__":
    main()
