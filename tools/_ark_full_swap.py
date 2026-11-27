"""全量批 → 对齐 → 切格 → 修帧 → 替换 82 帧。

每批 9 格（3×3），映射表把格子序号对到游戏 (anim, idx)。
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "artqa"))
from artqa.palette import load_palette  # noqa: E402
from artqa.config import repo_path  # noqa: E402

SRC = ROOT / "docs/refs/ai/poses_full"
OUT = ROOT / "art/characters/ori/frames_ark_full"
FRAMES = ROOT / "art/characters/ori/frames"
GRID = 18

PAL = load_palette(repo_path("art/palette.gpl"), repo_path("art/palette.hex.txt"))
pal_colors = [tuple(int(v) for v in c) for c in PAL.colors]
INK = (18, 20, 42)

# 批 → 9 个 (anim, idx)（与 _ark_full_frames.py 的动作顺序一一对应）
BATCH_MAP = {
    "b1_idle": [("idle", 0), ("idle", 1), ("idle", 2), ("idle", 3),
                ("idle", 4), ("idle", 5), ("idle", 6), ("idle", 7),
                ("land", 5)],
    "b2_run": [("run", 0), ("run", 1), ("run", 2), ("run", 3),
               ("run", 4), ("run", 5), ("run", 6), ("run", 7),
               ("jump", 1)],
    "b3_atk12": [("atk1", 0), ("atk1", 1), ("atk1", 2), ("atk1", 3),
                 ("atk1", 4), ("atk1", 5), ("atk2", 0), ("atk2", 1),
                 ("atk2", 2)],
    "b4_atk23": [("atk2", 3), ("atk2", 4), ("atk2", 5), ("atk3", 0),
                 ("atk3", 1), ("atk3", 2), ("atk3", 3), ("atk3", 4),
                 ("atk3", 5)],
    "b5_atk4dash": [("atk4", 0), ("atk4", 1), ("atk4", 2), ("atk4", 3),
                    ("atk4", 4), ("atk4", 5), ("dash", 0), ("dash", 1),
                    ("dash", 2)],
    "b6_heavy1": [("heavy1", 0), ("heavy1", 1), ("heavy1", 2),
                  ("heavy1", 3), ("heavy1", 4), ("heavy1", 5),
                  ("heavy1", 6), ("heavy1", 7), ("land", 0)],
    "b7_heavy2": [("land", 1), ("heavy2", 0), ("heavy2", 1), ("heavy2", 2),
                  ("heavy2", 3), ("heavy2", 4), ("heavy2", 5),
                  ("heavy2", 6), ("heavy2", 7)],
    "b8_heavy3": [("heavy3", 0), ("heavy3", 1), ("heavy3", 2),
                  ("heavy3", 3), ("heavy3", 4), ("heavy3", 5),
                  ("heavy3", 6), ("heavy3", 7), ("land", 2)],
    "b9_misc": [("gain", 0), ("gain", 1), ("gain", 2), ("gain", 3),
                ("gain", 4), ("gain", 5), ("land", 3), ("land", 4),
                ("jump", 2)],
}


def nearest(c):
    return min(pal_colors, key=lambda q: sum((q[i] - c[i]) ** 2 for i in range(3)))


def cell_to_frame(cell_rgb: Image.Image) -> Image.Image | None:
    rgba = cell_rgb.convert("RGBA")
    a = np.array(rgba)
    bg = (a[..., 0] < 45) & (a[..., 1] < 45) & (a[..., 2] < 55)
    a[bg] = (0, 0, 0, 0)
    cim = Image.fromarray(a)
    aa = np.array(cim)
    vis = aa[..., 3] > 127
    if not vis.any():
        return None
    ys, xs = np.where(vis)
    crop = cim.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
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
    return fr


def main():
    OUT.mkdir(exist_ok=True)
    swapped = 0
    missing = []
    for batch, mapping in BATCH_MAP.items():
        raw = SRC / f"{batch}_raw.jpeg"
        if not raw.exists():
            print("skip batch", batch)
            continue
        im = Image.open(raw).convert("RGB")
        w, h = im.size
        w2, h2 = (w // GRID) * GRID, (h // GRID) * GRID
        x0, y0 = (w - w2) // 2, (h - h2) // 2
        cropped = im.crop((x0, y0, x0 + w2, y0 + h2))
        small = cropped.resize((w2 // GRID, h2 // GRID), Image.NEAREST)
        aligned = small.resize((w2, h2), Image.NEAREST)
        cw, ch = aligned.width // 3, aligned.height // 3
        for gi, (anim, idx) in enumerate(mapping):
            gx, gy = gi % 3, gi // 3
            cell = aligned.crop((gx * cw, gy * ch,
                                 (gx + 1) * cw, (gy + 1) * ch))
            fr = cell_to_frame(cell)
            if fr is None:
                missing.append((batch, anim, idx))
                continue
            fr.save(OUT / f"ori_{anim}_{idx}.png")
            dst = FRAMES / f"ori_{anim}_{idx}.png"
            bk = ROOT / "art/characters/ori/backup_pre_ark_v2" / dst.name
            bk.parent.mkdir(exist_ok=True)
            if not bk.exists():
                import shutil
                shutil.copy(dst, bk)
            import shutil
            shutil.copy(OUT / f"ori_{anim}_{idx}.png", dst)
            swapped += 1
    print(f"swapped {swapped} frames; missing cells: {missing}")


if __name__ == "__main__":
    main()
