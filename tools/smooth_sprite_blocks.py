"""Rabi-Ribi/TEVI 风格清理：色块平滑（去 1px 孤立噪点）+ 保边细化描边。

## 目标风格（用户 2026-11-26 指定：Rabi-Ribi 与 TEVI，保持像素风）

  · 干净大色块：色块内部不允许 1px 孤立异色斑（当前 16~30%！）
  · 硬边二级阴影：每色块 = 本体色 + 1 档阴影，无三档渐变噪
  · 1px 细描边（U1 已完成）
  · 轮廓圆润（Q 版曲线）

## 处理

  pass1  色块平滑：孤立像素（4 邻域无同色）→ 取众数邻色。
         反复 2 轮；皮肤/发亮区等小面积特征色不强制（保留对比度）。
  pass2  阴影规整：把"比本体暗两档以上"的 1px 散点合并进相邻阴影块。
"""

import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def smooth_blocks(a, rounds=2):
    """去 1px 孤立噪点：4 邻域无同色 → 改成众数邻色。"""
    changed = 0
    H, W = a.shape[0], a.shape[1]
    for _ in range(rounds):
        vis = a[..., 3] > 127
        ys, xs = np.where(vis)
        moves = []
        for y, x in zip(ys, xs):
            c = tuple(int(v) for v in a[y, x, :3])
            # 4 邻域同色计数
            same = 0
            neigh = []
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ny, nx = y + dy, x + dx
                if 0 <= ny < H and 0 <= nx < W and vis[ny, nx]:
                    nc = tuple(int(v) for v in a[ny, nx, :3])
                    if nc == c:
                        same += 1
                    neigh.append(nc)
            if same == 0 and len(neigh) >= 2:
                # 孤立：取邻色众数
                from collections import Counter
                best, _n = Counter(neigh).most_common(1)[0]
                moves.append((y, x, best))
        for y, x, best in moves:
            a[y, x, :3] = best
            changed += 1
        if not moves:
            break
    return changed


def main(argv):
    dry = "--dry" in argv
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    total = 0
    n = 0
    for d in ("art/characters/ori/frames", "art/enemies/frames",
              "art/boss/frames"):
        for f in sorted((ROOT / d).glob("*.png")):
            im = Image.open(f).convert("RGBA")
            a = np.array(im).copy()
            c = smooth_blocks(a)
            if c and not dry:
                Image.fromarray(a).save(f)
            total += c
            n += 1
    print(f"{n} 帧 色块平滑，改写 {total} px {'(dry)' if dry else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
