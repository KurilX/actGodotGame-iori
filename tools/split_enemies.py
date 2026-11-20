"""从三个敌人的概念图里切出单个敌人，缩放量化成游戏用精灵。

概念图里三个敌人并排，各自是**单个静态姿势**，没有动画帧。
所以这里只负责切图 + 统一尺寸 + 量化到 28 色板；
动画（待机/行走/攻击）由 make_enemy_anim.py 程序化生成。

输出：
  art/enemies/src/mossling.png   苔团（近战冲撞）
  art/enemies/src/lanternbug.png 灯笼虫（飞行弹幕）
  art/enemies/src/stonepaw.png   石守（重甲近战）
"""

import os

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "art", "enemies", "00_concept_three.png")
OUT = os.path.join(ROOT, "art", "enemies", "src")

# 三个敌人在概念图里的横向区间（实测）
REGIONS = {
    "mossling": (36, 524),      # 苔团怪：圆滚滚绿色苔藓球（左侧留量给叶子）
    "lanternbug": (572, 924),   # 灯笼虫：悬浮纸灯笼
    "stonepaw": (975, 1493),    # 石守：石狮子小像
}

# 目标高度（游戏内角色 48px 高，敌人略小一些以保持主角存在感）
TARGET_H = {
    "mossling": 30,
    "lanternbug": 34,
    "stonepaw": 36,
}

PALETTE_HEX = [
    "#12142A", "#1B2244", "#2A3A63", "#3D5385", "#8FD3E8", "#D8F0F8",
    "#5A6478", "#394051", "#7B8699", "#4A6B4F", "#2E4634", "#6E9A6B",
    "#7A5FA8", "#4F3D74", "#A98FD6", "#FFE9A8", "#FFC46B", "#E0913F",
    "#F2F8EC", "#C4D8C2", "#A8E8C6", "#5FA882", "#FBE3D2", "#E2B49B",
    "#FF7A9C", "#C2456A", "#B9F2FF", "#FFFFFF",
]

# 敌人的专属色需要并入调色板，否则会被量化成完全不相干的颜色：
# 苔团的绿、灯笼虫的橙、石守的青灰，在 28 色里没有对应位。
EXTRA_HEX = [
    "#7FB03A",  # 苔团亮绿
    "#4E7A24",  # 苔团暗绿
    "#FF9A3C",  # 灯笼亮橙
    "#C96A1E",  # 灯笼暗橙
    "#8FA0A8",  # 石守亮青灰
    "#5C6B73",  # 石守暗青灰
    "#D94B3A",  # 布条红
]


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def build_palette():
    flat = []
    for hv in PALETTE_HEX + EXTRA_HEX:
        flat.extend(hex_rgb(hv))
    flat.extend([0] * (256 * 3 - len(flat)))
    pal = Image.new("P", (1, 1))
    pal.putpalette(flat)
    return pal


def detect_bg(img):
    """取图像四角的平均色作为背景色。

    注意：**必须在原图上调用，不能在裁切件上调用**。
    石守几乎撑满裁切框，四角采样点会落在它的身体上，
    导致背景色被误判成浅灰（实测返回 208,210,213 而真实背景是 250,249,250），
    后续 flood-fill 判定全部失效、白底抠不掉。
    """
    w, h = img.size
    px = img.load()
    pts = [px[0, 0], px[w - 1, 0], px[0, h - 1], px[w - 1, h - 1],
           px[w // 2, 0], px[w // 2, h - 1]]
    n = len(pts)
    return tuple(sum(p[i] for p in pts) / n for i in range(3))


def crop_enemy(img, x0, x1, bg):
    """按给定横向区间裁出敌人，纵向按非背景包围盒。"""
    rgb = img.convert("RGB")
    W, H = rgb.size
    px = rgb.load()

    def is_bg(c):
        return (abs(c[0] - bg[0]) < 18 and abs(c[1] - bg[1]) < 18
                and abs(c[2] - bg[2]) < 18)

    ys = [y for y in range(H)
          if any(not is_bg(px[x, y]) for x in range(x0, x1 + 1, 2))]
    if not ys:
        raise RuntimeError(f"区间 {x0}..{x1} 内没有前景")
    y0, y1 = min(ys), max(ys)
    pad = 4
    return rgb.crop((max(0, x0 - pad), max(0, y0 - pad),
                     min(W, x1 + pad + 1), min(H, y1 + pad + 1)))


def to_sprite(crop, target_h, palette, bg):
    """缩放到目标高度 → 量化 → 背景转透明（flood-fill 保护内部白色）。"""
    w, h = crop.size
    tw = max(1, round(w * target_h / h))
    small = crop.resize((tw, target_h), Image.BOX)

    # 量化前先在原始色上做边缘 flood-fill，避免把角色内部的浅色也吃掉
    sw, sh = small.size
    spx = small.load()

    def is_bg(c):
        return (abs(c[0] - bg[0]) < 40 and abs(c[1] - bg[1]) < 40
                and abs(c[2] - bg[2]) < 40)

    mask = [[False] * sw for _ in range(sh)]
    stack = []
    for x in range(sw):
        stack.append((x, 0))
        stack.append((x, sh - 1))
    for y in range(sh):
        stack.append((0, y))
        stack.append((sw - 1, y))
    while stack:
        x, y = stack.pop()
        if x < 0 or y < 0 or x >= sw or y >= sh or mask[y][x]:
            continue
        if not is_bg(spx[x, y]):
            continue
        mask[y][x] = True
        stack.extend([(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)])

    quant = small.quantize(palette=palette, dither=Image.NONE).convert("RGB")
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


def main():
    os.makedirs(OUT, exist_ok=True)
    img = Image.open(SRC)
    pal = build_palette()
    bg = detect_bg(img.convert("RGB"))   # 在原图上取背景色

    for name, (x0, x1) in REGIONS.items():
        crop = crop_enemy(img, x0, x1, bg)
        spr = to_sprite(crop, TARGET_H[name], pal, bg)
        path = os.path.join(OUT, f"{name}.png")
        spr.save(path)
        print(f"{name}.png  {spr.size} (目标高 {TARGET_H[name]})")


if __name__ == "__main__":
    main()
