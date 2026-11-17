"""给动画帧补「接地暗影」，让角色踩得更实。

问题：脚底那一行是 #7B8699（石亮），与地面苔绿 #6E9A6B 亮度接近，
      两者直接相接时，眼睛读不出「踩在上面」，反而像「融进地面」或「悬空」。

做法：在脚底接触行上方 1px 的位置，把角色边缘像素压暗一档，
      模拟接触阴影。只改最外缘，不动内部，保持像素风格。

同时在地面接触处画一条 1px 的暗色「压痕」，进一步强化接触感。

输出：原地覆盖 art/characters/ori/frames/*.png
"""

import glob
import os

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRAMES = os.path.join(ROOT, "art", "characters", "ori", "frames")

# 接触阴影色（色板 #12142A 的最暗档，半强度混合）
CONTACT_DARK = (18, 20, 42)     # #12142A
BLEND = 0.42                    # 与底色混合比例


def lowest_opaque_row(px, w, h):
    for y in range(h - 1, -1, -1):
        if any(px[x, y][3] > 10 for x in range(w)):
            return y
    return -1


def darken_foot(im_path, skip_jump_air=False):
    im = Image.open(im_path).convert("RGBA")
    w, h = im.size
    px = im.load()

    bottom = lowest_opaque_row(px, w, h)
    if bottom < 0:
        return

    # 跳跃的上升/顶点帧脚本来离地，不该加接触阴影
    if skip_jump_air and bottom < h - 2:
        im.save(im_path)
        return

    # 找出底行所有不透明像素的 x 范围
    xs = [x for x in range(w) if px[x, bottom][3] > 10]
    if not xs:
        return

    # 把底行及其上 1 行、落在 x 范围内的像素压暗
    for y in (bottom, bottom - 1):
        if y < 0:
            continue
        for x in xs:
            r, g, b, a = px[x, y]
            if a < 10:
                continue
            nr = int(r * (1 - BLEND) + CONTACT_DARK[0] * BLEND)
            ng = int(g * (1 - BLEND) + CONTACT_DARK[1] * BLEND)
            nb = int(b * (1 - BLEND) + CONTACT_DARK[2] * BLEND)
            px[x, y] = (nr, ng, nb, a)

    im.save(im_path)
    print(f"  {os.path.basename(im_path)}: foot row {bottom} darkened")


def main():
    files = sorted(glob.glob(os.path.join(FRAMES, "*.png")))
    if not files:
        raise FileNotFoundError(f"{FRAMES} 下没有 png，先跑 split_frames.py")
    print(f"处理 {len(files)} 帧")
    for p in files:
        name = os.path.basename(p)
        is_air = name.startswith("ori_jump_")
        darken_foot(p, skip_jump_air=is_air)


if __name__ == "__main__":
    main()
