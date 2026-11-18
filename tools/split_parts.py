"""把源精灵拆成可独立摆位的部件，并导出一把可旋转的剑。

背景：原始实现把整个下半身（含垂在身侧的剑）当成「腿部」段来摆位，
      结果攻击动画里**剑整个消失了**——玩家看到的只是身体换个倾斜角度，
      所以四连看起来一模一样。这是"四连单调"的真正根因。

本脚本负责：
  1. 抠出剑（源图里是从 (21,38) 到 (27,44) 的一条斜线）
  2. 生成一张水平方向的剑贴图，便于按任意角度旋转
  3. 输出各部件供 make_animation.py 使用

输出：
  art/characters/ori/parts/sword.png     水平剑（剑尖朝右）
  art/characters/ori/parts/upper.png     头+躯干（不含剑、不含腿）
  art/characters/ori/parts/leg_l.png
  art/characters/ori/parts/leg_r.png
"""

import os

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "art", "characters", "ori", "ori_idle_src.png")
OUT = os.path.join(ROOT, "art", "characters", "ori", "parts")

Y_UPPER_BOT = 38
LEG_L_X0, LEG_L_X1 = 5, 14
LEG_R_X0, LEG_R_X1 = 14, 22

# 剑的对角线端点（实测像素坐标）
SWORD_X0, SWORD_Y0 = 21, 38
SWORD_X1, SWORD_Y1 = 27, 44


def load():
    return Image.open(SRC).convert("RGBA")


def extract_sword(src):
    """生成一把用于挥砍的像素剑（水平，剑尖朝右）。

    源图里垂在身侧的剑只有 7px，太短——挥砍时根本看不出在挥什么。
    这里不照抄那 7px，而是按它的配色（#7B8699 剑身 / #A98FD6 剑柄 /
    #C4D8C2 高光）重建一把 20px 的细剑，符合 docs/02 里
    「针剑长 33px ≈ 身高 0.7 倍」的规范（当前角色 48px 高，取 20px 是
    保守值，保证旋转时不出画幅）。
    """
    BLADE = "#7B8699"      # 剑身主色（石亮，偏冷灰蓝）
    BLADE_HI = "#D8F0F8"   # 刃口高光（月白，冷白才有金属感）
    HILT = "#A98FD6"       # 剑柄（紫藤亮）
    INK = "#12142A"        # 描边

    def c(hexv):
        h = hexv.lstrip("#")
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 255)

    length = 20
    sword = Image.new("RGBA", (length, 3), (0, 0, 0, 0))
    sp = sword.load()

    # 针剑：细、有收尖。3 行高 —— 0 行的上半是刃口高光，1 行是剑身，2 行只在剑柄处有
    # 剑柄 0-3（两行厚，带描边）
    for x in range(0, 4):
        sp[x, 0] = c(HILT)
        sp[x, 1] = c(INK)
    # 护手：竖一道
    sp[4, 0] = c(INK)
    sp[4, 1] = c(INK)
    # 剑身 5..17：两行，上行高光下行主色；越靠剑尖越细
    for x in range(5, 18):
        sp[x, 0] = c(BLADE_HI)
        sp[x, 1] = c(BLADE)
    # 收尖 18-19
    sp[18, 0] = c(BLADE_HI)
    sp[19, 0] = c(BLADE)
    return sword


def split_bodies(src):
    """拆出头+躯干、左腿、右腿；躯干里把剑柄的位置挖掉。

    注意：剑在源图里是从 (21,36) 附近斜向右下的那条线。
    挖的时候**只能挖剑所占的窄列**，不能整行清空——
    早期版本写了 `if y >= 36 and x >= 21: 清空`，把 y36-37 整片
    衣服下摆一起挖掉了，结果角色头部和腿之间出现 3 行空隙。
    """
    w, h = src.size
    upper = src.crop((0, 0, w, Y_UPPER_BOT)).copy()
    upx = upper.load()

    # 剑柄在源图中占据的列（实测：x21..27，y36..37）
    SWORD_GRIP_MIN_X = 21
    for y in range(36, Y_UPPER_BOT):
        for x in range(SWORD_GRIP_MIN_X, w):
            # 只挖真正属于剑的颜色（石亮/紫藤亮），衣服的白色保留
            c = upx[x, y]
            if c[3] < 10:
                continue
            is_sword = (abs(c[0] - 0x7B) < 10 and abs(c[1] - 0x86) < 10
                        and abs(c[2] - 0x99) < 10) or \
                       (abs(c[0] - 0xA9) < 10 and abs(c[1] - 0x8F) < 10
                        and abs(c[2] - 0xD6) < 10)
            if is_sword:
                upx[x, y] = (0, 0, 0, 0)

    leg_l = src.crop((LEG_L_X0, Y_UPPER_BOT, LEG_L_X1, h))
    leg_r = src.crop((LEG_R_X0, Y_UPPER_BOT, LEG_R_X1, h))
    return upper, leg_l, leg_r


def main():
    os.makedirs(OUT, exist_ok=True)
    src = load()

    sword = extract_sword(src)
    sword.save(os.path.join(OUT, "sword.png"))
    print(f"sword.png ({sword.width}x{sword.height}) 剑尖朝右")

    # 剑柄锚点：水平剑里剑柄在 x=0，也就是剑的「左端中点」
    # 写进一个 sidecar 供 make_animation.py 读取，避免靠包围盒猜
    import json
    meta = {
        "width": sword.width,
        "height": sword.height,
        "grip_x": 0.5,               # 握把在贴图上的 x（像素，从左端起）
        "grip_y": sword.height / 2.0,
    }
    with open(os.path.join(OUT, "sword.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(f"sword.json grip=({meta['grip_x']}, {meta['grip_y']})")

    upper, leg_l, leg_r = split_bodies(src)
    upper.save(os.path.join(OUT, "upper.png"))
    leg_l.save(os.path.join(OUT, "leg_l.png"))
    leg_r.save(os.path.join(OUT, "leg_r.png"))
    print(f"upper.png ({upper.size[0]}x{upper.size[1]})")
    print(f"leg_l.png ({leg_l.size[0]}x{leg_l.size[1]})")
    print(f"leg_r.png ({leg_r.size[0]}x{leg_r.size[1]})")


if __name__ == "__main__":
    main()
