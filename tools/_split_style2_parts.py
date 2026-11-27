"""CaChiu 风格程序化动画重铺：用 AI 侧视基底立绘重切部件 + 新色板，
喂给 make_animation.py 的程序化骨架管线。

## 流程
1. 从 ori_side_raw.jpeg 切出 head / torso / leg_l / leg_r 四个部件
   （右侧四分之三侧视，与游戏朝向一致）
2. 用 CaChiu 量化标准建新色板（每区域 2~4 色阶，总 8~12 色）
3. 写入 art/characters/ori/parts_style2/（palette.json + 四部件）
4. 调 make_animation.py 的管线（改 PARTS 路径参数）重铺全部动画帧
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "docs/refs/ai/ori_side_raw.jpeg"
OUT = ROOT / "art/characters/ori/parts_style2"
OUT.mkdir(exist_ok=True)

# ── CaChiu 色板（从侧视立绘主色提取，符合每区域 2~4 色阶、总 9 色）──
PALETTE = {
    # 头发：本体/暗部/高光（绿发）
    "hair_lit": "#7CBF5A",
    "hair_dark": "#4A8A3A",
    "skin_lit": "#F5EFE0",
    "skin_dark": "#E8D5B5",
    # 斗篷：本体/暗部（深蓝）
    "cape_lit": "#2A3A63",
    "cape_dark": "#1B2244",
    # 内衬白
    "cloth_lit": "#E8E8E0",
    "cloth_dark": "#B8B8C0",
    "ink": "#12142A",
    "boot": "#1B2244",
    # 剑
    "blade": "#A8D8E8",
    "blade_hi": "#D8F0F8",
    "hilt": "#C2456A",
    "danger": "#FF7A9C",
}

# ── 1. 主体裁切 ──
im = Image.open(SRC).convert("RGB")
a = np.array(im)
bg = (a[..., 0] < 40) & (a[..., 1] < 40) & (a[..., 2] < 50)
vis = ~bg
ys, xs = np.where(vis)
x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
body = im.crop((x0, y0, x1 + 1, y1 + 1))
W, H = body.size
print(f"主体 {W}x{H}")

# 逻辑像素网格（立绘逻辑头身比 1:1.2，逻辑像素 ≈ H/60）
PX = max(2, H // 60)
print(f"逻辑像素 {PX} 实际px")


def snap_region(c):
    """把颜色 snap 到最近的色板色。c 可能是 np.uint8 数组。"""
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


# ── 2. 降采样到逻辑像素网格 ──
lw, lh = W // PX, H // PX
small = body.resize((lw, lh), Image.NEAREST)
sa = np.array(small)

# 量化 + ink 化深色
for y in range(lh):
    for x in range(lw):
        r, g, b = sa[y, x]
        if r < 40 and g < 40 and b < 40:
            sa[y, x] = (18, 20, 42)
            continue
        sa[y, x] = snap_region((int(r), int(g), int(b)))
quant = Image.fromarray(sa)
print(f"量化后 {quant.size}")

# ── 3. 切部件（按 CaChiu 头身比：头占上 ~55%，身体下半）──
# 先做 alpha：黑背景 → 透明（在量化图上按暗色 + 连通性抠）
rgba = quant.convert("RGBA")
ra = np.array(rgba)
dark_bg = (ra[..., 0] < 40) & (ra[..., 1] < 40) & (ra[..., 2] < 50)
ra[dark_bg] = (0, 0, 0, 0)
quant = Image.fromarray(ra)

# 头：从发髻顶到脸底
head_h = int(lh * 0.52)
head = quant.crop((max(0, lw // 2 - head_h // 2 - 2), 0,
                   min(lw, lw // 2 + head_h // 2 + 2), head_h))
head = head.resize((head.width * PX, head.height * PX), Image.NEAREST)
head.save(OUT / "head.png")
print(f"head.png {head.size}")

# 躯干：头底到腿顶（含斗篷）
torso_top = head_h - 2
torso_h = int(lh * 0.30)
torso = quant.crop((lw // 2 - head_h // 2 - 2, torso_top,
                    lw // 2 + head_h // 2 + 2, torso_top + torso_h))
torso = torso.resize((torso.width * PX, torso.height * PX), Image.NEAREST)
torso.save(OUT / "torso.png")
print(f"torso.png {torso.size}")

# 腿：最后 20%
leg_top = int(lh * 0.80)
leg_h = lh - leg_top
leg_w = lw // 2 // 2
leg_l = quant.crop((lw // 2 - leg_w - 1, leg_top,
                    lw // 2 - 1, leg_top + leg_h))
leg_r = quant.crop((lw // 2 + 1, leg_top,
                    lw // 2 + leg_w + 1, leg_top + leg_h))
leg_l = leg_l.resize((leg_l.width * PX, leg_l.height * PX), Image.NEAREST)
leg_r = leg_r.resize((leg_r.width * PX, leg_r.height * PX), Image.NEAREST)
leg_l.save(OUT / "leg_l.png")
leg_r.save(OUT / "leg_r.png")
print(f"leg_l {leg_l.size} leg_r {leg_r.size}")

# ── 4. palette.json ──
with open(OUT / "palette.json", "w", encoding="utf-8") as f:
    json.dump(PALETTE, f, ensure_ascii=False, indent=1)
print(f"palette.json {len(PALETTE)} 色 → {OUT}")
