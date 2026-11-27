"""修复剩余 12 帧的朝向问题：
- face=left 的帧水平镜像（发卡会自动翻到正确侧，需复查）
- eye_off 大的帧是动作中身体倾斜导致的测量噪声，仅镜像 face=left
修复后复查全部 82 帧朝向一致性。
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
FRAMES = ROOT / "art/characters/ori/frames"

FIX = [
    "ori_atk1_2.png", "ori_atk1_3.png", "ori_atk2_0.png", "ori_atk2_1.png",
    "ori_dash_0.png", "ori_gain_0.png", "ori_gain_5.png", "ori_heavy3_3.png",
    "ori_heavy3_4.png",
]

for name in FIX:
    p = FRAMES / name
    im = Image.open(p).convert("RGBA")
    im = im.transpose(Image.FLIP_LEFT_RIGHT)
    im.save(p)
    print("mirrored", name)

# 复审
def analyze(p):
    a = np.array(Image.open(p).convert("RGBA"))
    vis = a[..., 3] > 127
    if not vis.any():
        return None
    ys, xs = np.where(vis)
    top, bottom = ys.min(), ys.max()
    head_band = vis[top:top + 26]
    dark = (a[top:top + 26, :, :3].sum(axis=2) < 350) & head_band
    cols = np.where(dark.any(axis=0))[0]
    allcols = np.where(head_band.any(axis=0))[0]
    if not len(cols) or not len(allcols):
        return ("?", 0)
    mid = (allcols.min() + allcols.max()) / 2
    eye = cols.mean()
    return ("right" if eye >= mid else "left", int(abs(eye - mid)))


bad = []
for p in sorted(FRAMES.glob("ori_*.png")):
    r = analyze(p)
    if r is None:
        continue
    face, off = r
    if face == "left" or off > 4:
        bad.append((p.name, face, off))
print("复查后仍有问题:", bad if bad else "无 — 82 帧全部朝向统一")
