"""敌人/BOSS 帧量化回 28 色板（hard_fail 修复）。

enemy/boss 全部 116 帧有越界色（unify_sprite_style 的档位移动在
板外色上继续移动，以及生成端本身的板外色）—— artqa palette 锁
按 sprite 类别是硬失败。逐像素映射到最近板内色后写回。
"""

import os
import sys
from pathlib import Path

from PIL import Image
import numpy as np

ROOT = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, str(ROOT / "artqa"))
from artqa.palette import load_palette  # noqa: E402
from artqa.config import repo_path  # noqa: E402

PAL = load_palette(repo_path("art/palette.gpl"),
                   repo_path("art/palette.hex.txt"))


def quantize(a):
    vis = a[..., 3] > 127
    changed = 0
    cols = np.unique(a[...,:3][vis].reshape(-1, 3), axis=0)
    # 逐色建立映射（只算一次每色）
    lut = {}
    for c in cols:
        key = tuple(int(v) for v in c)
        best = min(PAL.colors, key=lambda q: sum(
            (int(q[i]) - key[i]) ** 2 for i in range(3)))
        if max(abs(int(best[i]) - key[i]) for i in range(3)) > 0:
            lut[key] = tuple(int(v) for v in best)
    if not lut:
        return 0
    ys, xs = np.where(vis)
    for y, x in zip(ys, xs):
        key = (int(a[y, x, 0]), int(a[y, x, 1]), int(a[y, x, 2]))
        if key in lut:
            a[y, x, :3] = lut[key]
            changed += 1
    return changed


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    total = 0
    n = 0
    for d in ("art/enemies/frames", "art/boss/frames"):
        for f in sorted((ROOT / d).glob("*.png")):
            im = Image.open(f).convert("RGBA")
            a = np.array(im).copy()
            c = quantize(a)
            if c:
                Image.fromarray(a).save(f)
            total += c
            n += 1
    print(f"{n} 帧量化完成，改写 {total} px")
    return 0


if __name__ == "__main__":
    sys.exit(main())
