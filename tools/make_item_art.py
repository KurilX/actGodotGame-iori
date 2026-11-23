"""道具图标处理 + 获得道具的人物动画。

## 两部分

1. **图标**：从概念图切出梭芯，量化到游戏调色板，缩放到 32x32
   （UI 里显示的尺寸；技能树节点用 32px，飘字用 48px）。

2. **人物动画**：获得道具时角色抬手 → 道具从上方落入 → 吸收。
   复用 `make_animation.py` 的 Porter/compose，避免另写一套绘制逻辑。

输出：
  art/items/spool_32.png    图标（32x32）
  art/items/spool_48.png    大图标（48x48）
  art/characters/ori/frames/ori_gain_*.png   获得动画 6 帧
"""

import os
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_animation as M  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "art", "items", "00_concept_spool.png")
ITEMS = os.path.join(ROOT, "art", "items")
FRAMES = os.path.join(ROOT, "art", "characters", "ori", "frames")

PALETTE_HEX = [
    "#12142A", "#1B2244", "#2A3A63", "#3D5385", "#8FD3E8", "#D8F0F8",
    "#5A6478", "#394051", "#7B8699", "#4A6B4F", "#2E4634", "#6E9A6B",
    # 注意：**不要把紫色系放进道具调色板**。原图边缘有抗锯齿过渡色，
    # 量化时会就近匹配到紫色 #7A5FA8，在梭芯上长出紫色杂点（实测如此）。
    "#FFE9A8", "#FFC46B", "#E0913F",
    "#F2F8EC", "#C4D8C2", "#A8E8C6", "#5FA882", "#FBE3D2", "#E2B49B",
    "#FF7A9C", "#C2456A", "#B9F2FF", "#FFFFFF",
    # 道具专属：丝线的荧光青绿在原调色板里没有对应位
    "#3FE0C0",  # 丝线亮青
    "#2AA890",  # 丝线中青
    "#1C6B5E",  # 丝线暗青
]


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def build_palette():
    flat = []
    for hv in PALETTE_HEX:
        flat.extend(hex_rgb(hv))
    flat.extend([0] * (256 * 3 - len(flat)))
    pal = Image.new("P", (1, 1))
    pal.putpalette(flat)
    return pal


def detect_bg(img):
    w, h = img.size
    px = img.load()
    pts = [px[0, 0], px[w - 1, 0], px[0, h - 1], px[w - 1, h - 1]]
    return tuple(sum(p[i] for p in pts) / len(pts) for i in range(3))


def make_icon(target_h):
    img = Image.open(SRC).convert("RGB")
    bg = detect_bg(img)
    W, H = img.size
    px = img.load()

    def is_bg(c):
        return (abs(c[0] - bg[0]) < 26 and abs(c[1] - bg[1]) < 26
                and abs(c[2] - bg[2]) < 26)

    xs, ys = [], []
    for y in range(0, H, 2):
        for x in range(0, W, 2):
            if not is_bg(px[x, y]):
                xs.append(x)
                ys.append(y)
    if not xs:
        raise RuntimeError("找不到前景")
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    pad = 4
    crop = img.crop((max(0, x0 - pad), max(0, y0 - pad),
                     min(W, x1 + pad + 1), min(H, y1 + pad + 1)))

    cw, ch = crop.size
    tw = max(1, round(cw * target_h / ch))
    small = crop.resize((tw, target_h), Image.BOX)

    # 量化 + flood-fill 抠背景
    sw, sh = small.size
    spx = small.load()

    def is_bg_s(c):
        return (abs(c[0] - bg[0]) < 40 and abs(c[1] - bg[1]) < 40
                and abs(c[2] - bg[2]) < 40)

    mask = [[False] * sw for _ in range(sh)]
    stack = []
    for x in range(sw):
        stack += [(x, 0), (x, sh - 1)]
    for y in range(sh):
        stack += [(0, y), (sw - 1, y)]
    while stack:
        x, y = stack.pop()
        if x < 0 or y < 0 or x >= sw or y >= sh or mask[y][x]:
            continue
        if not is_bg_s(spx[x, y]):
            continue
        mask[y][x] = True
        stack.extend([(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)])

    pal = build_palette()
    quant = small.quantize(palette=pal, dither=Image.NONE).convert("RGB")
    qpx = quant.load()

    out = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
    opx = out.load()
    for y in range(sh):
        for x in range(sw):
            if mask[y][x]:
                continue
            r, g, b = qpx[x, y]
            opx[x, y] = (r, g, b, 255)
    return out


# ─────────────── 获得道具的人物动画 ───────────────

def make_gain_anim():
    """获得道具：6 帧。

    0 站立 → 1 抬头 → 2 抬手 → 3 接住（手在头顶）→ 4 收手 → 5 站定

    道具本身由代码在世界层绘制（跟着手掌位置），
    这里只画角色的姿态。手掌位置通过 hand 参数控制，
    代码侧用同样的坐标算道具位置就能对齐。
    """
    import json
    with open(os.path.join(M.PARTS, "palette.json"), encoding="utf-8") as f:
        pal = json.load(f)

    def op(n):
        return Image.open(os.path.join(M.PARTS, n)).convert("RGBA")

    parts = {
        "palette": pal,
        "head": op("head.png"),
        "torso": op("torso.png"),
        "leg_l": op("leg_l.png"),
        "leg_r": op("leg_r.png"),
    }

    specs = [
        # body_dy, lean, hand, sword_angle, crouch
        dict(body_dy=0, lean=0, hand=(8, -15), sword_angle=78, crouch=0.0),
        dict(body_dy=-1, lean=0, hand=(6, -18), sword_angle=80, crouch=0.10),
        # 抬手：手举到头顶
        dict(body_dy=-2, lean=1, hand=(4, -34), sword_angle=95, crouch=0.16),
        # 接住：手最高
        dict(body_dy=-2, lean=2, hand=(3, -40), sword_angle=100, crouch=0.14),
        # 收手
        dict(body_dy=-1, lean=1, hand=(6, -26), sword_angle=88, crouch=0.08),
        dict(body_dy=0, lean=0, hand=(8, -15), sword_angle=78, crouch=0.0),
    ]
    out = []
    for s in specs:
        pt = M.Porter(**parts)
        out.append(M.compose(pt, body_dy=s["body_dy"], lean=s["lean"],
                             hand=s["hand"], sword_angle=s["sword_angle"],
                             crouch=s["crouch"]))
    return out


def main():
    os.makedirs(ITEMS, exist_ok=True)
    os.makedirs(FRAMES, exist_ok=True)

    for h in (32, 48):
        ic = make_icon(h)
        p = os.path.join(ITEMS, f"spool_{h}.png")
        ic.save(p)
        print(f"spool_{h}.png {ic.size}")

    frames = make_gain_anim()
    for i, f in enumerate(frames):
        f.save(os.path.join(FRAMES, f"ori_gain_{i}.png"))
    print(f"ori_gain_*.png {len(frames)} 帧")


if __name__ == "__main__":
    main()
