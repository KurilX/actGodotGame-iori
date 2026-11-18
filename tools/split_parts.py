"""角色部件拆分与重建（v3）。

## 为什么 v3 要重做

v2 的问题：
1. 画幅只有 48x48，角色占 28px，剑 20px —— 突刺/跳劈时剑必然出框或被身体盖住。
2. 躯干是一整块实心色块，手臂和身体分不开，所以四段动作只有身体倾斜度差异，
   **手臂完全不动**，玩家看不到「挥」这个动作。
3. 腿部只有横向位移，没有抬腿/屈膝。

v3 的做法：
- 画幅扩到 **80x80**（角色仍是 48px 高，不放大角色，只放大画布）
- 只从源图保留**头部**（发+脸），躯干/手臂/腿/剑全部按参数绘制
- 这样手臂能独立旋转，腿能独立抬屈，剑能加长到 30px 而不出框

## 输出

art/characters/ori/parts/
  head.png     头部（发+脸），28x26
  palette.json 配色表，供 make_animation.py 绘制身体用
"""

import json
import os

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "art", "characters", "ori", "ori_idle_src.png")
OUT = os.path.join(ROOT, "art", "characters", "ori", "parts")

Y_HEAD_BOT = 26     # 源图里头部下沿（含脖子起点）

# 28 色板里用到的角色配色
PALETTE = {
    "hair_lit":  "#A8E8C6",
    "hair_dark": "#5FA882",
    "skin_lit":  "#FBE3D2",
    "skin_dark": "#E2B49B",
    "cape_lit":  "#F2F8EC",
    "cape_dark": "#C4D8C2",
    "cloth":     "#5A6478",
    "cloth_dark": "#394051",
    "cloth_lit": "#7B8699",
    "ink":       "#12142A",
    "night":     "#1B2244",
    "moss":      "#4A6B4F",
    "moss_dark": "#2E4634",
    "boot":      "#2A3A63",
    "blade_hi":  "#D8F0F8",
    "blade":     "#7B8699",
    "hilt":      "#A98FD6",
    "danger":    "#FF7A9C",
}


def main():
    os.makedirs(OUT, exist_ok=True)
    src = Image.open(SRC).convert("RGBA")

    # 头部：源图 y0..25（含刘海、呆毛、脸）
    head = src.crop((0, 0, 28, Y_HEAD_BOT))
    head.save(os.path.join(OUT, "head.png"))
    print(f"head.png {head.size}")

    # 躯干（含手臂）：源图 y26..37。手臂与躯干在这张图里连成一片，
    # 无法按像素切开，所以整体保留 —— 这样至少保住原画的精细度。
    torso = src.crop((0, Y_HEAD_BOT, 28, 38))
    torso.save(os.path.join(OUT, "torso.png"))
    print(f"torso.png {torso.size}")

    # 腿：源图 y38..47，左右分开
    leg_l = src.crop((5, 38, 14, 48))
    leg_r = src.crop((14, 38, 22, 48))
    leg_l.save(os.path.join(OUT, "leg_l.png"))
    leg_r.save(os.path.join(OUT, "leg_r.png"))
    print(f"leg_l.png {leg_l.size}, leg_r.png {leg_r.size}")

    # 配色表（仍导出，供剑和特效绘制用）
    with open(os.path.join(OUT, "palette.json"), "w", encoding="utf-8") as f:
        json.dump(PALETTE, f, ensure_ascii=False, indent=2)
    print(f"palette.json ({len(PALETTE)} 色)")


if __name__ == "__main__":
    main()
