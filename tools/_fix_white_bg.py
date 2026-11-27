"""白底 flood-fill 抠底：从四角向外淹没连通背景，角色内部白脸不受影响。"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage  # noqa: F401  (fallback if available)

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
NEW = ROOT / "art/characters/ori/frames_side_st"
FRAMES = ROOT / "art/characters/ori/frames"


def flood_clear(arr):
    """从边缘的浅色背景像素 flood（角落是透明的，不能从角落起）。

    同时处理 alpha=0 的透明区和米白背景：背景定义 = 透明 OR 浅色低饱和。
    """
    h, w = arr.shape[0], arr.shape[1]
    lum = 0.299 * arr[..., 0].astype(int) + 0.587 * arr[..., 1] + 0.114 * arr[..., 2]
    mx = arr[..., :3].max(axis=2).astype(int)
    mn = arr[..., :3].min(axis=2).astype(int)
    light_bg = ((lum > 185) & ((mx - mn) < 30)) | (arr[..., 3] == 0)
    visited = np.zeros((h, w), dtype=bool)
    stack = []
    for x in range(w):
        stack.append((0, x))
        stack.append((h - 1, x))
    for y in range(h):
        stack.append((y, 0))
        stack.append((y, w - 1))
    while stack:
        y, x = stack.pop()
        if y < 0 or y >= h or x < 0 or x >= w or visited[y, x]:
            continue
        if not light_bg[y, x]:
            continue
        visited[y, x] = True
        stack.extend(((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)))
    n = int((visited & (arr[..., 3] > 0)).sum())
    arr[visited] = (0, 0, 0, 0)
    return n


def process_frame(p: Path):
    im = Image.open(p).convert("RGBA")
    a = np.array(im)
    n = flood_clear(a)
    Image.fromarray(a).save(p)
    return n


def main():
    total = 0
    for idx in range(8):
        for d in (NEW, FRAMES):
            p = d / f"ori_idle_{idx}.png"
            if p.exists():
                n = process_frame(p)
                total += n
    print(f"flood-cleared {total} bg px across 8 frames x2 dirs")


if __name__ == "__main__":
    main()
