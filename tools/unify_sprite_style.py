"""精灵风格统一：右上月光受光 + 描边瘦身。

## 为什么（统一风格 audit）

场景层（月光斑/瓦片）的受光来自**右上**（月亮在屏幕 x=60%），
但精灵（角色/怪物）是"顶部受光、无方向性侧光"——亮部重心 x≈0。
把它们放进月光场景时，精灵像自发光的贴纸，与场景光影脱节。

同时描边占比 22~33%（ink 像素 / 可见像素），参考素材通常 12~18%，
2~3px 的均匀描边在小尺寸精灵上"糊"成一圈黑框，吃掉内部细节。

## 两步处理（对已生成的单帧运行，可重复）

1. **描边瘦身**：外侧 ink 描边 2~3px 收到 1px（把外圈多余的
   ink 像素替换回其邻接的本体色）。只动"完全被 ink 包裹且邻接
   透明或 ink 的像素"——保留 1px 轮廓语义。
2. **右上月光受光**：对每个可见像素，
   右邻是透明/ink（即自己是右侧边缘）→ 提亮一档；
   左邻是透明/ink（左侧边缘）→ 压暗一档。
   提亮/压暗用色板档位近似（不做 alpha 混合）。

## 用法

    python tools/unify_sprite_style.py            # 处理全部三类
    python tools/unify_sprite_style.py --dry      # 只统计不写回
"""

import os
import sys
from pathlib import Path

from PIL import Image
import numpy as np

ROOT = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

INK = (18, 20, 42)

# 28 色板（art/palette.gpl）按亮度排序，用于提亮/压暗档位移动
PALETTE = [
    (18, 20, 42), (27, 34, 68), (42, 58, 99), (57, 64, 81),
    (61, 83, 133), (74, 107, 79), (79, 61, 116), (90, 100, 120),
    (95, 168, 130), (110, 154, 107), (122, 95, 168), (123, 134, 153),
    (143, 211, 232), (169, 143, 214), (185, 242, 255), (196, 216, 194),
    (216, 240, 248), (224, 145, 63), (226, 180, 155), (242, 248, 236),
    (251, 227, 210), (255, 122, 156), (255, 196, 107), (255, 233, 168),
    (255, 255, 255),
]
LUMS = [0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2] for c in PALETTE]


def _nearest_palette(r, g, b):
    best_i, best_d = 0, 1e9
    for i, c in enumerate(PALETTE):
        d = (c[0] - r) ** 2 + (c[1] - g) ** 2 + (c[2] - b) ** 2
        if d < best_d:
            best_i, best_d = i, d
    return best_i


def _shift(r, g, b, steps):
    """色板亮度档位移动 ±steps。"""
    i = _nearest_palette(r, g, b)
    i = max(0, min(len(PALETTE) - 1, i + steps))
    return PALETTE[i]


def is_ink(c):
    return (c[0], c[1], c[2]) == INK


def slim_outline(a):
    """外侧多余 ink 收到 1px：返回被改的像素数。

    只处理"ink 且 4 邻里没有非 ink 可见像素"的外圈环，反复剥离
    直到每个 ink 像素都邻接本体（保留 1px 语义）。
    """
    changed = 0
    H, W = a.shape[0], a.shape[1]
    vis = a[..., 3] > 127
    ink = (a[..., 0] == INK[0]) & (a[..., 1] == INK[1]) & \
          (a[..., 2] == INK[2]) & vis
    for _ in range(3):  # 最多剥 3 层
        peel = np.zeros_like(ink)
        ys, xs = np.where(ink)
        for y, x in zip(ys, xs):
            # 该 ink 像素的 4 邻里是否有"非 ink 的可见像素"（本体）
            touch_body = False
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ny, nx = y + dy, x + dx
                if 0 <= ny < H and 0 <= nx < W and vis[ny, nx] \
                        and not ink[ny, nx]:
                    touch_body = True
                    break
            if not touch_body:
                # 纯 ink 外环（邻接透明或别的 ink）→ 可剥
                # 但要保证剥掉后它旁边的本体还在（防止整条 ink 断开）
                peel[y, x] = True
        if not peel.any():
            break
        # 剥离：该像素取它 4 邻里最近的非 ink 可见色，否则变透明
        ys2, xs2 = np.where(peel)
        for y, x in zip(ys2, xs2):
            repl = None
            for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                ny, nx = y + dy, x + dx
                if 0 <= ny < H and 0 <= nx < W and vis[ny, nx] \
                        and not ink[ny, nx]:
                    repl = tuple(int(v) for v in a[ny, nx][:3])
                    break
            if repl is not None and _has_ink_neighbor_behind(a, y, x, ink):
                a[y, x, :3] = repl
            else:
                a[y, x, 3] = 0
            changed += 1
        vis = a[..., 3] > 127
        ink = (a[..., 0] == INK[0]) & (a[..., 1] == INK[1]) & \
              (a[..., 2] == INK[2]) & vis
    return changed


def _has_ink_neighbor_behind(a, y, x, ink):
    """剥掉这个 ink 后，它 8 邻里的本体像素仍会被 ink 包住吗？
    简化判定：本体在该位置的另一侧存在即可保留厚度。"""
    H, W = a.shape[0], a.shape[1]
    body_around = 0
    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        ny, nx = y + dy, x + dx
        if 0 <= ny < H and 0 <= nx < W and a[ny, nx, 3] > 127 \
                and not ink[ny, nx]:
            body_around += 1
    return body_around >= 2   # 两侧都有本体才回填，否则露缝


def moonlight_shade(a):
    """右上月光受光：右缘提亮一档、左缘压暗一档。返回改动数。"""
    changed = 0
    H, W = a.shape[0], a.shape[1]
    vis = a[..., 3] > 127
    ink = (a[..., 0] == INK[0]) & (a[..., 1] == INK[1]) & \
          (a[..., 2] == INK[2]) & vis
    for y in range(H):
        for x in range(W):
            if not vis[y, x] or ink[y, x]:
                continue
            r_edge = (x + 1 >= W) or (not vis[y, x + 1]) or ink[y, x + 1]
            l_edge = (x - 1 < 0) or (not vis[y, x - 1]) or ink[y, x - 1]
            if r_edge and not l_edge:
                c = a[y, x, :3]
                nc = _shift(int(c[0]), int(c[1]), int(c[2]), +1)
                if tuple(nc) != tuple(int(v) for v in c):
                    a[y, x, :3] = nc
                    changed += 1
            elif l_edge and not r_edge:
                c = a[y, x, :3]
                nc = _shift(int(c[0]), int(c[1]), int(c[2]), -1)
                if tuple(nc) != tuple(int(v) for v in c):
                    a[y, x, :3] = nc
                    changed += 1
    return changed


def process_file(path: Path, dry=False):
    im = Image.open(path).convert("RGBA")
    a = np.array(im).copy()
    n_slim = slim_outline(a)
    n_shade = moonlight_shade(a)
    if not dry and (n_slim or n_shade):
        Image.fromarray(a).save(path)
    return n_slim, n_shade


def main(argv):
    dry = "--dry" in argv
    groups = [
        ("player", ROOT / "art" / "characters" / "ori" / "frames"),
        ("enemy", ROOT / "art" / "enemies" / "frames"),
        ("boss", ROOT / "art" / "boss" / "frames"),
    ]
    total_slim = total_shade = n_files = 0
    for label, d in groups:
        if not d.exists():
            continue
        s = sh = 0
        cnt = 0
        for f in sorted(d.glob("*.png")):
            a, b = process_file(f, dry)
            s += a
            sh += b
            cnt += 1
        print(f"  {label:7s} {cnt:3d} 帧  描边剥离 {s:6d} px  受光调整 {sh:6d} px")
        total_slim += s
        total_shade += sh
        n_files += cnt
    print(f"  合计 {n_files} 帧  描边剥离 {total_slim}  受光调整 {total_shade}"
          f"  {'(dry run)' if dry else ''}")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    sys.exit(main(sys.argv[1:]))
