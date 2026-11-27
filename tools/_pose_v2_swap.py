"""锚定版姿态切帧 + 替换游戏帧（V2 anchored 版本）。

姿态格子：poses_v2_anchored.png（2808x1584，3×3，每格 936x528）
顺序：站立/走路/跳跃/挥剑/重击/受伤/挥砍/闪避/胜利（按 prompt）
映射到游戏帧：
  stand  → idle_0
  walk   → run_0
  jump   → jump_0
  slash  → atk1_3
  heavy  → atk3_0
  hurt   → land_0（hurt 动画不存在，用 land 近似）— 实际跳过
  dash   → dash_1
"""
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "artqa"))
from artqa.palette import load_palette  # noqa: E402
from artqa.config import repo_path  # noqa: E402

SHEET = ROOT / "docs/refs/ai/poses/poses_v2_anchored.png"
OUT = ROOT / "art/characters/ori/frames_ark_poses_v2"
FRAMES = ROOT / "art/characters/ori/frames"
BACKUP = ROOT / "art/characters/ori/backup_pre_ark_v2"

PAL = load_palette(repo_path("art/palette.gpl"), repo_path("art/palette.hex.txt"))
pal_colors = [tuple(int(v) for v in c) for c in PAL.colors]
INK = (18, 20, 42)


def nearest(c):
    return min(pal_colors, key=lambda q: sum((q[i] - c[i]) ** 2 for i in range(3)))


def cell_to_frame(cell_rgba: Image.Image) -> Image.Image:
    a = np.array(cell_rgba)
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
    im = Image.open(SHEET).convert("RGB")
    W, H = im.size
    cell_w, cell_h = W // 3, H // 3
    OUT.mkdir(exist_ok=True)

    # 格子顺序与 prompt 一致
    order = ["stand", "walk", "jump", "slash", "heavy", "hurt", "dash", "victory"]
    # V2 prompt 顺序：站立、走路、跳跃、挥剑、重击、受伤后仰、闪避滑步、胜利举手
    # （9 词但只列了 8 个名字 → 第 9 格是"下落"被跳过）
    grid_names = ["stand", "walk", "jump", "slash", "heavy", "hurt",
                  "dash", "victory", "fall"]

    made = {}
    for idx, name in enumerate(grid_names):
        gx, gy = idx % 3, idx // 3
        cell = im.crop((gx * cell_w, gy * cell_h,
                        (gx + 1) * cell_w, (gy + 1) * cell_h)).convert("RGBA")
        fr = cell_to_frame(cell)
        if fr is None:
            print("empty cell", name)
            continue
        fr.save(OUT / f"pose_{name}_0.png")
        made[name] = fr
        print(f"cell {name}: {fr.size[0]}x48 sprite")

    # 替换游戏帧
    MAP = [
        ("stand", "idle", 0),
        ("walk", "run", 0),
        ("jump", "jump", 0),
        ("slash", "atk1", 3),
        ("heavy", "atk3", 0),
        ("dash", "dash", 1),
    ]
    for name, anim, idx in MAP:
        if name not in made:
            continue
        dst = FRAMES / f"ori_{anim}_{idx}.png"
        if not dst.exists():
            print("skip", dst.name)
            continue
        BACKUP.mkdir(exist_ok=True)
        bk = BACKUP / dst.name
        if not bk.exists():
            shutil.copy(dst, bk)
        shutil.copy(OUT / f"pose_{name}_0.png", dst)
        print(f"replaced {dst.name} <- pose_{name}_0")
    print("done")


if __name__ == "__main__":
    main()
