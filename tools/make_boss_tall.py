"""BOSS 比例改造：Q 版放大 → 威严比例（3.5 头身）。

## 输入

art/boss/src/warden.png（63x96，Q 版 2.5 头身——玩家比例的直接放大）

## 方法（V2.2：分区缩放 + 躯干拉伸，保细节不保比例）

简单的整图 resize 拉长（96→120）会把头也拉长，Q 版大头变得更卡通。
正确做法是**分区处理**：

  1. 头部（顶部 ~45%）：横向压扁 15%（大头→宽脸，更凶）、
     垂直压缩 12%（降头占比），NEAREST 保像素；
  2. 躯干（中段 ~25%）：垂直拉伸 1.35x（胸口/腰带拉长成躯干），
     横向拉伸 1.15x（宽肩）；
  3. 腿部（下段 ~30%）：垂直拉伸 1.5x（长腿），横向 1.1x。
  4. 披裙下摆（腿部区两侧的深紫区域）：横向拉伸 1.2x 加宽底盘。

分区边界按行扫描 alpha 确定（头部=瓷面区，腿部=最下两块白甲）。

输出：warden_tall.png（约 75x120，3.5 头身）
"""

import os
import sys

from PIL import Image
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "art", "boss", "src", "warden.png")
OUT = os.path.join(ROOT, "art", "boss", "src", "warden_tall.png")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    im = Image.open(SRC).convert("RGBA")
    W, H = im.size          # 63 x 96
    a = np.array(im)

    # ── 1. 行级 alpha 分析找分区边界 ──
    vis = a[..., 3] > 127
    row_w = vis.sum(axis=1)
    # 头部：最宽的连续区在顶部（瓷面+发）
    # 找最宽行
    widest_y = int(np.argmax(row_w))
    # 躯干/腿部边界：最下面一个"宽度突增"处（裙摆展开）
    # 简化：头部占顶部 45%（2.5 头身 → 头约 43/96）
    head_end = int(H * 0.45)          # y=43
    # 裙摆展开处：从底部向上找宽度 > 最宽行 60% 的起点
    leg_start = int(H * 0.70)         # y=67

    print(f"分区: 头部 0..{head_end}  躯干 {head_end}..{leg_start}  "
          f"腿部 {leg_start}..{H}")

    # ── 2. 分区缩放 ──
    head = im.crop((0, 0, W, head_end))
    torso = im.crop((0, head_end, W, leg_start))
    legs = im.crop((0, leg_start, W, H))

    # 头：横向压 0.92（微宽脸），纵向压 0.90（降占比）
    # （V2.3：0.85 压扁过度导致双眼变形、发型错位——头是细节密集区，
    #   只做轻微缩放，威严感主要靠躯干/腿部的纵向拉伸）
    hw, hh = head.size
    head2 = head.resize((max(1, int(hw * 0.95)), max(1, int(hh * 0.90))),
                        Image.NEAREST)
    # 躯干：纵向 1.35x（拉长成躯干）+ 横向 1.15x（宽肩）
    tw, th = torso.size
    torso2 = torso.resize((int(tw * 1.22), int(th * 1.35)), Image.NEAREST)
    # 腿：纵向 1.5x（长腿）+ 横向 1.08x
    lw, lh = legs.size
    legs2 = legs.resize((int(lw * 1.12), int(lh * 1.5)), Image.NEAREST)

    # ── 3. 拼接（水平居中对齐，按各区 alpha 重心）──
    out_w = max(head2.width, torso2.width, legs2.width) + 4
    out_h = head2.height + torso2.height + legs2.height

    def center_x(img, ref_w):
        # 按 alpha 重心对齐（防止各区重心不同导致错位）
        arr = np.array(img)
        vis = arr[..., 3] > 127
        if not vis.any():
            return (ref_w - img.width) // 2
        cx = np.where(vis)[1].mean()
        return int(round(ref_w / 2 - cx))

    out = Image.new("RGBA", (out_w, out_h), (0, 0, 0, 0))
    y = 0
    for img in (head2, torso2, legs2):
        ox = center_x(img, out_w)
        out.alpha_composite(img, (ox, y))
        y += img.height

    out.save(OUT)
    print(f"输出 {OUT} {out.size}（原 {W}x{H}，头占比 "
          f"{head2.height / out_h:.0%} → 目标 ~28%）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
