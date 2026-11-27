"""模仿 PixelLab 的骨骼控制思路（本地版）：

把角色拆成**持久化部件层**（head / torso / arm_l / arm_r / leg_l / leg_r），
每层单独 PNG 存盘（parts_v4/），之后 make_animation 管线按骨骼参数
（位移/旋转/压缩）合成任意动作帧——部件不变，只有骨架参数变，
帧间一致性由"同一部件文件"保证（正是 PixelLab 的"角色定义持久化"）。

与 style2/3 的区别：不再从立绘上"按区域裁切"（会把相邻部件切进来），
而是逐部件手工指定边界矩形 + 透明化处理，部件干净、可独立移动。
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "docs/refs/ai/ori_v4_base.jpeg"
OUT = ROOT / "art/characters/ori/parts_v4"
OUT.mkdir(exist_ok=True)

PALETTE = {
    "hair_lit": "#8A8FD6",
    "hair_dark": "#5A6BC0",
    "skin_lit": "#F5EFE0",
    "skin_dark": "#E8D5B5",
    "cape_lit": "#2A3A63",
    "cape_dark": "#1B2244",
    "shirt": "#E8E8E0",
    "shirt_dark": "#B8B8C0",
    "skirt": "#2A2E3E",
    "boot": "#1B2244",
    "ink": "#12142A",
    "ribbon": "#C2456A",
    "blade": "#A8D8E8",
    "blade_hi": "#D8F0F8",
    "hilt": "#C2456A",
    "danger": "#FF7A9C",
}


def snap(c):
    cr, cg, cb = int(c[0]), int(c[1]), int(c[2])
    best, bd = None, 10 ** 9
    for h in PALETTE.values():
        hh = h.lstrip("#")
        r, g, b = int(hh[0:2], 16), int(hh[2:4], 16), int(hh[4:6], 16)
        d = (r - cr) ** 2 + (g - cg) ** 2 + (b - cb) ** 2
        if d < bd:
            bd, best = d, (r, g, b)
    return best


def main():
    im = Image.open(SRC).convert("RGB")
    a = np.array(im)
    bg = (a[..., 0] < 40) & (a[..., 1] < 40) & (a[..., 2] < 50)
    vis = ~bg
    ys, xs = np.where(vis)
    body = im.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
    W, H = body.size
    print(f"主体 {W}x{H}")

    PX = max(2, H // 60)
    lw, lh = W // PX, H // PX
    small = body.resize((lw, lh), Image.NEAREST)
    sa = np.array(small)
    for y in range(lh):
        for x in range(lw):
            r, g, b = sa[y, x]
            if r < 40 and g < 40 and b < 40:
                sa[y, x] = (18, 20, 42)
                continue
            sa[y, x] = snap((int(r), int(g), int(b)))
    rgba = np.dstack([sa, np.full((lh, lw), 255, dtype=np.uint8)])
    # 黑底转透明
    dark = (rgba[..., 0] < 35) & (rgba[..., 1] < 35) & (rgba[..., 2] < 45)
    rgba[dark] = (0, 0, 0, 0)
    quant = Image.fromarray(rgba)
    quant.save(OUT / "_quant_full.png")
    print(f"量化 {quant.size}（PX={PX}）")

    # ── 部件矩形（比例坐标，基于 V4 立绘目测）──
    # 头：0 ~ 52%（含双马尾左右延伸，占全宽）
    # 躯干：52% ~ 72%（斗篷+衬衫，不含裙摆）
    # 裙：68% ~ 82%
    # 腿：80% ~ 100%
    HEAD_Y0, HEAD_Y1 = 0, int(lh * 0.52)
    TORSO_Y0, TORSO_Y1 = int(lh * 0.52), int(lh * 0.72)
    LEG_Y0, LEG_Y1 = int(lh * 0.78), lh

    head = quant.crop((0, HEAD_Y0, lw, HEAD_Y1))
    head.save(OUT / "head.png")
    print(f"head {head.size}")

    torso = quant.crop((int(lw * 0.30), TORSO_Y0, int(lw * 0.70), TORSO_Y1))
    torso.save(OUT / "torso.png")
    print(f"torso {torso.size}")

    # 裙（并入 torso 层下方，动画里随躯干移动）
    skirt = quant.crop((int(lw * 0.28), int(lh * 0.68),
                        int(lw * 0.72), int(lh * 0.80)))
    skirt.save(OUT / "skirt.png")
    print(f"skirt {skirt.size}")

    leg_l = quant.crop((int(lw * 0.36), LEG_Y0, int(lw * 0.48), LEG_Y1))
    leg_r = quant.crop((int(lw * 0.52), LEG_Y0, int(lw * 0.64), LEG_Y1))
    leg_l.save(OUT / "leg_l.png")
    leg_r.save(OUT / "leg_r.png")
    print(f"leg_l {leg_l.size} leg_r {leg_r.size}")

    # 手臂（斗篷两侧下垂部分）
    arm_l = quant.crop((int(lw * 0.24), TORSO_Y0, int(lw * 0.36), TORSO_Y1 + 4))
    arm_r = quant.crop((int(lw * 0.64), TORSO_Y0, int(lw * 0.76), TORSO_Y1 + 4))
    arm_l.save(OUT / "arm_l.png")
    arm_r.save(OUT / "arm_r.png")
    print(f"arm_l {arm_l.size} arm_r {arm_r.size}")

    with open(OUT / "palette.json", "w", encoding="utf-8") as f:
        json.dump(PALETTE, f, ensure_ascii=False, indent=1)
    print(f"palette 16 色 → {OUT}")


if __name__ == "__main__":
    main()
