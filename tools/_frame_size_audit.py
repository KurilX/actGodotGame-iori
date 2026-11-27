"""定量：每个动画帧的精灵宽高波动（锚定版 vs 原手绘备份）。"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent


def measure(d: Path):
    anims = {}
    for p in sorted(d.glob("ori_*.png")):
        stem = p.name[len("ori_"):-len(".png")]
        anim, idx = stem.rsplit("_", 1)
        a = np.array(Image.open(p).convert("RGBA"))
        vis = a[..., 3] > 127
        if not vis.any():
            anims.setdefault(anim, []).append((int(idx), 0, 0, 0))
            continue
        ys, xs = np.where(vis)
        anims.setdefault(anim, []).append(
            (int(idx), int(xs.max() - xs.min() + 1),
             int(ys.max() - ys.min() + 1), int(ys.min())))
    return anims


def report(tag, anims):
    print(f"== {tag} ==")
    for k in sorted(anims):
        ws = [w for _, w, h, t in anims[k]]
        hs = [h for _, w, h, t in anims[k]]
        spread_w = max(ws) - min(ws)
        spread_h = max(hs) - min(hs)
        flag = "  ← 波动大" if spread_w > 6 or spread_h > 6 else ""
        print(f"  {k:8s} w {min(ws)}~{max(ws)} (差{spread_w})  "
              f"h {min(hs)}~{max(hs)} (差{spread_h}){flag}")


report("锚定版（现行）", measure(ROOT / "art/characters/ori/frames"))
report("原手绘（backup）", measure(ROOT / "art/characters/ori/backup_pre_ark_v2"))
