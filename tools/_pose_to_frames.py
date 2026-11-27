"""切 9 姿态 → 修帧 → 游戏帧（RGBA 安全版）。"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "artqa"))
from artqa.palette import load_palette  # noqa: E402
from artqa.config import repo_path  # noqa: E402

im = Image.open(ROOT / "docs/refs/ai/poses/poses_v1_aligned.png").convert("RGB")
W, H = im.size
cell_w, cell_h = W // 3, H // 3
OUT = ROOT / "art/characters/ori/frames_ark_poses"
OUT.mkdir(exist_ok=True)

PAL = load_palette(repo_path("art/palette.gpl"), repo_path("art/palette.hex.txt"))
pal_colors = [tuple(int(v) for v in c) for c in PAL.colors]
INK = (18, 20, 42)


def nearest(c):
    return min(pal_colors, key=lambda q: sum((q[i] - c[i]) ** 2 for i in range(3)))


names = ["stand", "walk", "jump", "fall", "slash",
         "heavy", "hurt", "dash", "victory"]

for idx, name in enumerate(names):
    gx, gy = idx % 3, idx // 3
    cell = im.crop((gx * cell_w, gy * cell_h,
                    (gx + 1) * cell_w, (gy + 1) * cell_h)).convert("RGBA")
    a = np.array(cell)
    bg = (a[..., 0] < 45) & (a[..., 1] < 45) & (a[..., 2] < 55)
    a[bg] = (0, 0, 0, 0)
    cellim = Image.fromarray(a)
    aa = np.array(cellim)
    vis = aa[..., 3] > 127
    if not vis.any():
        print("empty", name)
        continue
    ys, xs = np.where(vis)
    crop = cellim.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
    mid = crop.resize((max(1, crop.width // 8), max(1, crop.height // 8)),
                      Image.NEAREST)
    tw = max(1, round(mid.width * 48 / mid.height))
    small = mid.resize((tw, 48), Image.NEAREST)
    sa = np.array(small).copy()
    for yy in range(sa.shape[0]):
        for xx in range(sa.shape[1]):
            r, g, b, al = sa[yy, xx]
            if al < 128:
                sa[yy, xx] = (0, 0, 0, 0)
                continue
            if r < 40 and g < 40 and b < 40:
                sa[yy, xx] = (*INK, 255)
                continue
            sa[yy, xx] = (*nearest((int(r), int(g), int(b))), 255)
    spr = Image.fromarray(sa)
    fr = Image.new("RGBA", (80, 80), (0, 0, 0, 0))
    fr.alpha_composite(spr, ((80 - spr.width) // 2, 78 - 48))
    fr.save(OUT / f"pose_{name}_0.png")
    print(f"frame {name}: {spr.width}x48")

print(f"done → {OUT}")
