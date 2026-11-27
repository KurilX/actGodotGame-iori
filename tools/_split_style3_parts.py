"""V3 部件切分：用 seedream 5.5 新基底（ori_side_v3_raw.jpeg）重切部件，
铺全量动画帧。沿用 _split_style2_parts.py 流程，SRC 换新图。
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "docs/refs/ai/ori_side_v3_raw.jpeg"
OUT = ROOT / "art/characters/ori/parts_style3"
OUT.mkdir(exist_ok=True)

PALETTE = {
    "hair_lit": "#7CBF5A",
    "hair_dark": "#4A8A3A",
    "skin_lit": "#F5EFE0",
    "skin_dark": "#E8D5B5",
    "cape_lit": "#2A3A63",
    "cape_dark": "#1B2244",
    "cloth_lit": "#E8E8E0",
    "cloth_dark": "#B8B8C0",
    "ink": "#12142A",
    "boot": "#1B2244",
    "blade": "#A8D8E8",
    "blade_hi": "#D8F0F8",
    "hilt": "#C2456A",
    "danger": "#FF7A9C",
}


def snap_region(c):
    cr, cg, cb = int(c[0]), int(c[1]), int(c[2])
    best = None
    best_d = 10 ** 9
    for h in PALETTE.values():
        hh = h.lstrip("#")
        r = int(hh[0:2], 16)
        g = int(hh[2:4], 16)
        b = int(hh[4:6], 16)
        d = (r - cr) ** 2 + (g - cg) ** 2 + (b - cb) ** 2
        if d < best_d:
            best_d = d
            best = (r, g, b)
    return best


im = Image.open(SRC).convert("RGB")
a = np.array(im)
bg = (a[..., 0] < 40) & (a[..., 1] < 40) & (a[..., 2] < 50)
vis = ~bg
ys, xs = np.where(vis)
body = im.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
W, H = body.size
print(f"主体 {W}x{H}")

PX = max(2, H // 60)
lw, lh = W // PX, H // PX
small = body.resize((lw, lh), Image.NEAREST)
sa = np.array(small)
for y in range(lh):
    for x in range(lw):
        r, g, b = sa[y, x]
        if r < 40 and g < 40 and b < 40:
            sa[y, x] = (18, 20, 42)
            continue
        sa[y, x] = snap_region((int(r), int(g), int(b)))
quant = Image.fromarray(sa)
print(f"量化后 {quant.size}")

# 黑底 → 透明
rgba = quant.convert("RGBA")
ra = np.array(rgba)
dark_bg = (ra[..., 0] < 40) & (ra[..., 1] < 40) & (ra[..., 2] < 50)
ra[dark_bg] = (0, 0, 0, 0)
quant = Image.fromarray(ra)

head_h = int(lh * 0.52)
head = quant.crop((max(0, lw // 2 - head_h // 2 - 2), 0,
                   min(lw, lw // 2 + head_h // 2 + 2), head_h))
head = head.resize((head.width * PX, head.height * PX), Image.NEAREST)
hw = round(head.width * 26 / head.height)
head = head.resize((hw, 26), Image.NEAREST)
head.save(OUT / "head.png")
print(f"head {head.size}")

torso_top = head_h - 2
torso_h = int(lh * 0.30)
torso = quant.crop((lw // 2 - head_h // 2 - 2, torso_top,
                    lw // 2 + head_h // 2 + 2, torso_top + torso_h))
torso = torso.resize((torso.width * PX, torso.height * PX), Image.NEAREST)
tw = round(torso.width * 12 / torso.height)
torso = torso.resize((tw, 12), Image.NEAREST)
torso.save(OUT / "torso.png")
print(f"torso {torso.size}")

leg_top = int(lh * 0.80)
leg_h = lh - leg_top
leg_w = lw // 2 // 2
leg_l = quant.crop((lw // 2 - leg_w - 1, leg_top,
                    lw // 2 - 1, leg_top + leg_h))
leg_r = quant.crop((lw // 2 + 1, leg_top,
                    lw // 2 + leg_w + 1, leg_top + leg_h))
leg_l = leg_l.resize((leg_l.width * PX, leg_l.height * PX), Image.NEAREST)
leg_r = leg_r.resize((leg_r.width * PX, leg_r.height * PX), Image.NEAREST)
for n, img in (("leg_l", leg_l), ("leg_r", leg_r)):
    lw2 = round(img.width * 10 / img.height)
    img.resize((lw2, 10), Image.NEAREST).save(OUT / f"{n}.png")
    print(f"{n} {(lw2, 10)}")

with open(OUT / "palette.json", "w", encoding="utf-8") as f:
    json.dump(PALETTE, f, ensure_ascii=False, indent=1)
print(f"palette 14 色 → {OUT}")
