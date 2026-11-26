"""i2i 结果修帧：主体裁切 → 两段 NEAREST → 量化 → 描边重铸 → 帧 + 对比。"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(r"D:\Program Files\Projects\personal\actGame")
sys.path.insert(0, str(ROOT / "artqa"))
from artqa.palette import load_palette  # noqa: E402
from artqa.config import repo_path  # noqa: E402

SRC = ROOT / "docs" / "refs" / "ai" / "ori_ark_i2i_raw.jpeg"
OUT_DIR = ROOT / "art" / "characters" / "ori" / "frames_ark"

PAL = load_palette(repo_path("art/palette.gpl"),
                   repo_path("art/palette.hex.txt"))
pal_colors = [tuple(int(v) for v in c) for c in PAL.colors]
INK = (18, 20, 42)


def nearest(c):
    return min(pal_colors, key=lambda q: sum((q[i] - c[i]) ** 2 for i in range(3)))


im = Image.open(SRC).convert("RGBA")
a = np.array(im)
bg = (a[..., 0] < 45) & (a[..., 1] < 45) & (a[..., 2] < 55)
a[bg] = (0, 0, 0, 0)
im = Image.fromarray(a)
vis = a[..., 3] > 127
ys, xs = np.where(vis)
crop = im.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
print(f"主体裁切 {crop.size}")

# 两段 NEAREST：2048→341（1/6）→48
mid = crop.resize((crop.width // 6, crop.height // 6), Image.NEAREST)
tw = max(1, round(mid.width * 48 / mid.height))
small = mid.resize((tw, 48), Image.NEAREST)
sa = np.array(small).copy()
for y in range(sa.shape[0]):
    for x in range(sa.shape[1]):
        r, g, b, al = sa[y, x]
        if al < 128:
            sa[y, x] = (0, 0, 0, 0)
            continue
        if r < 40 and g < 40 and b < 40:
            sa[y, x] = (*INK, 255)
            continue
        sa[y, x] = (*nearest((int(r), int(g), int(b))), 255)

# 描边重铸
vis = sa[..., 3] > 127
lum = 0.299 * sa[..., 0].astype(int) + 0.587 * sa[..., 1] + 0.114 * sa[..., 2]
dark = vis & (lum < 60)
H, W = sa.shape[0], sa.shape[1]
edge_dark = np.zeros_like(dark)
ys, xs = np.where(dark)
for y, x in zip(ys, xs):
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            ny, nx = y + dy, x + dx
            if not (0 <= ny < H and 0 <= nx < W) or not vis[ny, nx]:
                edge_dark[y, x] = True
                break
        if edge_dark[y, x]:
            break
sa[edge_dark] = (0, 0, 0, 0)
vis2 = sa[..., 3] > 127
paint = []
for y in range(H):
    for x in range(W):
        if vis2[y, x]:
            continue
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < H and 0 <= nx < W and vis2[ny, nx]:
                paint.append((y, x))
                break
for y, x in paint:
    sa[y, x] = (*INK, 255)

spr = Image.fromarray(sa)
print(f"精灵 {spr.size}  抹暗杂 {int(edge_dark.sum())}  重建描边 {len(paint)}")

frame = Image.new("RGBA", (80, 80), (0, 0, 0, 0))
frame.alpha_composite(spr, ((80 - spr.width) // 2, 78 - 48))
frame.save(OUT_DIR / "ori_ark_i2i_idle_0.png")

old = Image.open(ROOT / "art/characters/ori/frames/ori_idle_0.png")
i2i = Image.open(OUT_DIR / "ori_ark_i2i_idle_0.png")
S = 4
cmp_img = Image.new("RGBA", ((80 * 3 + 40) * S, 84 * S), (26, 28, 42, 255))
cmp_img.alpha_composite(old.resize((80 * S, 80 * S), Image.NEAREST), (10, 10))
cmp_img.alpha_composite(i2i.resize((80 * S, 80 * S), Image.NEAREST),
                        ((80 + 20) * S, 10))
# Ark 直出（t2i）版也放进来对比
t2i = Image.open(OUT_DIR / "ori_ark_idle_0.png")
cmp_img.alpha_composite(t2i.resize((80 * S, 80 * S), Image.NEAREST),
                        ((80 * 2 + 30) * S, 10))
cmp_img.save(ROOT / "docs/refs/ai/ori_ark_compare.png")
print("三方对比图 docs/refs/ai/ori_ark_compare.png（左：手绘 U 系列 / 中：i2i 参考图版 / 右：t2i 直出版）")
