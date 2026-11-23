"""精灵轮廓清理：消除白边 + 重描轮廓。

## 问题

AI 生成的素材在抠图后，轮廓上会残留**亮色像素**（原始图的抗锯齿
过渡色被量化成接近白的灰）。实测白边占比：

    BOSS     26.8%   ← 最严重（300/1119 个边缘像素是亮的）
    玩家     18.7%
    苔团     15.2%
    灯笼虫   11.6%
    石守      7.1%

## 为什么不能只"加粗黑边盖住"

直接在外面加一圈黑边有两个副作用：
  1. 精灵整体**变胖 1~2px**，碰撞盒/动画对位会偏移
  2. 原来的亮边还在**描边内侧**，只是被压暗了一点，放大看仍发白

## 正确做法（两步）

1. **清扫**：把所有"贴着透明的亮色边缘像素"替换成该精灵的主色或深色，
   消除白边本身。
2. **重描**：在清理后的轮廓**外侧**补 1px（或 2px）`#12142A` 描边。

这样描边是"补"在透明区上的，不改变精灵本体的尺寸，
也不会留下亮边在里面。

## 用法

    python tools/clean_sprite_outline.py --dir art/enemies/frames \
        --prefix mossling --outline 2
"""

import argparse
import os
import sys
from collections import Counter

from PIL import Image

INK = (0x12, 0x14, 0x2A)          # 01 最暗（描边），禁用纯黑
NIGHT_FAR = (0x1B, 0x22, 0x44)    # 02 夜色远


def is_bright_fringe(c):
    """判断是否白边嫌疑：亮度高 + 低饱和（接近灰白/亮灰）。"""
    mx, mn = max(c[:3]), min(c[:3])
    return mx > 170 and (mx - mn) < 45


def edge_pixels(px, W, H, alpha_th=128):
    """返回所有"不透明且四邻域有透明"的像素坐标。"""
    out = []
    for y in range(H):
        for x in range(W):
            if px[x, y][3] < alpha_th:
                continue
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < W and 0 <= ny < H and px[nx, ny][3] < alpha_th:
                    out.append((x, y))
                    break
    return out


def dominant_dark(im):
    """找精灵里最常见的"非边缘"深色，用作白边的替换色。"""
    px = im.load()
    W, H = im.size
    cnt = Counter()
    for y in range(H):
        for x in range(W):
            c = px[x, y]
            if c[3] < 200:
                continue
            if is_bright_fringe(c):
                continue
            # 只统计偏暗的（描边/阴影系）
            if max(c[:3]) < 170:
                cnt[c[:3]] += 1
    if cnt:
        return cnt.most_common(1)[0][0]
    return INK


def clean_one(path, outline_width=2):
    im = Image.open(path).convert("RGBA")
    W, H = im.size
    px = im.load()

    # ── 1. 清扫白边 ──
    dark = dominant_dark(im)
    edges = edge_pixels(px, W, H)
    cleaned = 0
    for (x, y) in edges:
        c = px[x, y]
        if is_bright_fringe(c):
            px[x, y] = (dark[0], dark[1], dark[2], c[3])
            cleaned += 1

    # ── 2. 重描轮廓 ──
    #
    # **关键约束**：很多帧的精灵已经贴到画布边缘
    # （玩家 82 帧里有 67 帧贴边，因为挥剑时剑尖伸出）。
    # 无脑向外扩描边会被裁掉，导致描边缺失。
    #
    # 策略：
    #   · 优先向外扩（在透明区上画），不改本体尺寸、不吃细节
    #   · 向外扩会超出画布时，改成**向内压**（把最外层本体像素替换成描边色）
    # 这样无论贴不贴边，最终外观都是一圈完整描边。
    if outline_width > 0:
        alpha = [[px[x, y][3] >= 128 for x in range(W)] for y in range(H)]

        for _w in range(outline_width):
            to_paint = []
            out_of_bounds = False
            for y in range(H):
                for x in range(W):
                    if alpha[y][x]:
                        continue
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        nx, ny = x + dx, y + dy
                        if 0 <= nx < W and 0 <= ny < H and alpha[ny][nx]:
                            to_paint.append((x, y))
                            break

            if to_paint:
                for (x, y) in to_paint:
                    px[x, y] = (INK[0], INK[1], INK[2], 255)
                    alpha[y][x] = True
                continue

            # 没有可外扩的位置 → 说明精灵撑满了画布，改为向内压
            # 找出所有"不透明且邻接透明"的像素（最外层本体）
            inner = []
            for y in range(H):
                for x in range(W):
                    if not alpha[y][x]:
                        continue
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        nx, ny = x + dx, y + dy
                        if not (0 <= nx < W and 0 <= ny < H) \
                                or not alpha[ny][nx]:
                            inner.append((x, y))
                            break
            for (x, y) in inner:
                px[x, y] = (INK[0], INK[1], INK[2], 255)
                # 注意不改 alpha：本体像素已经被描边色覆盖，仍然不透明

    im.save(path)
    return cleaned


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--prefix", default="")
    ap.add_argument("--pattern", default="*.png")
    ap.add_argument("--outline", type=int, default=2,
                    help="描边宽度（0 = 只清扫不描边）")
    ap.add_argument("--dry", action="store_true",
                    help="只报告不写盘")
    args = ap.parse_args()

    files = []
    for fn in sorted(os.listdir(args.dir)):
        if not fn.endswith(".png"):
            continue
        if args.prefix and not fn.startswith(args.prefix):
            continue
        files.append(os.path.join(args.dir, fn))

    if not files:
        print("没找到文件", file=sys.stderr)
        return 1

    total_cleaned = 0
    for f in files:
        if args.dry:
            im = Image.open(f).convert("RGBA")
            px = im.load()
            W, H = im.size
            n = sum(1 for (x, y) in edge_pixels(px, W, H)
                    if is_bright_fringe(px[x, y]))
            total_cleaned += n
            print(f"  {os.path.basename(f)}: 白边 {n}")
        else:
            total_cleaned += clean_one(f, args.outline)

    print(f"共处理 {len(files)} 个文件，清理白边 {total_cleaned} 个像素，"
          f"描边 {args.outline}px")
    return 0


if __name__ == "__main__":
    sys.exit(main())
