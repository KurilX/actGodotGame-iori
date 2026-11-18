"""角色动画生成器 v4：保留原画身体 + 大画幅 + 明显肢体运动。

## 设计取舍（v3 的教训）

v3 试过「身体全部程序化绘制」，结果躯干是灰条、腿是灰棍，
和精细的像素头部严重不匹配，观感很差。所以 v4 回到 **保留源图像素**
的方案，只做三件事：

1. **画幅扩到 80x80**（角色仍 48px 高，不放大角色）
2. **剑加长到 30px**，可自由旋转，不出框
3. **手臂单独重绘**（源图手臂与躯干粘连，切不开），
   腿用源图部件做位移 + 抬脚

## 帧数与动作

- 基础动作：idle 4 / run 6 / jump 3 / land 2 / dash 3
- 四段攻击：**每段 6 帧**，幅度加大，手脚都动
- 第 4 段是**跳劈**：动画里腾空举起再下砸（不改实际物理）

## 坐标系

角色局部坐标：原点 = 双脚之间的地面点，+x 向右，+y 向上为负。
"""

import json
import math
import os

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARTS = os.path.join(ROOT, "art", "characters", "ori", "parts")
OUT_DIR = os.path.join(ROOT, "art", "characters", "ori")

FRAME = 80
# 脚底在画幅里的 y。
# 直接贴底（79），这样角色双脚与地面严丝合缝。
# 剑垂到脚下时会超出画幅被裁掉 —— 这是正常的，剑在挥砍中段不会朝下。
FEET_Y = 79
BODY_CX = 40

HEAD_H = 26
TORSO_H = 12
LEG_H = 10

SWORD_LEN = 30


def hex_rgba(h, a=255):
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a)


class Porter:
    def __init__(self, palette, head, torso, leg_l, leg_r):
        self.img = Image.new("RGBA", (FRAME, FRAME), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.img)
        self.p = {k: hex_rgba(v) for k, v in palette.items()}
        self.head = head
        self.torso = torso
        self.leg_l = leg_l
        self.leg_r = leg_r

    def P(self, x, y):
        return (int(round(BODY_CX + x)), int(round(FEET_Y + y)))

    def px(self, x, y, color):
        ax, ay = self.P(x, y)
        if 0 <= ax < FRAME and 0 <= ay < FRAME:
            self.img.putpixel((ax, ay), color)

    def rect(self, x0, y0, x1, y1, color):
        ax, ay = self.P(x0, y0)
        bx, by = self.P(x1, y1)
        x0p, x1p = min(ax, bx), max(ax, bx)
        y0p, y1p = min(ay, by), max(ay, by)
        if x1p <= x0p or y1p <= y0p:
            return
        self.d.rectangle([x0p, y0p, x1p - 1, y1p - 1], fill=color)

    def blit(self, part, x, y):
        """把像素部件贴到局部坐标 (x, y)（左上角）。"""
        ax, ay = self.P(x, y)
        ax, ay = int(round(ax)), int(round(ay))
        if ax >= FRAME or ay >= FRAME or ax + part.width <= 0:
            return
        self.img.alpha_composite(part, (ax, ay))


def draw_sword(porter, hx, hy, angle_deg, length=SWORD_LEN):
    """从握把点沿角度画剑。0=正右，-90=正上，90=正下。"""
    pal = porter.p
    rad = math.radians(angle_deg)
    dx, dy = math.cos(rad), math.sin(rad)

    # 剑柄（握把往后）
    for i in range(-4, 1):
        porter.px(int(round(hx + dx * i)), int(round(hy + dy * i)),
                  pal["hilt"])
    # 护手（垂直方向的短横）
    gx, gy = hx + dx, hy + dy
    for s in (-1, 1):
        porter.px(int(round(gx - dy * s)), int(round(gy + dx * s)), pal["ink"])
    # 剑身：两行（主色 + 刃口高光）
    for i in range(2, length):
        x = hx + dx * i
        y = hy + dy * i
        porter.px(int(round(x)), int(round(y)), pal["blade"])
        # 高光在「朝上」一侧
        nx = int(round(x - dy * 0.8))
        ny = int(round(y + dx * 0.8))
        porter.px(nx, ny, pal["blade_hi"])


def draw_arm(porter, sh_x, sh_y, hand_x, hand_y, thick=5):
    """重绘一条手臂：青色披肩 + 深色袖口 + 白色手套。

    注意配色要与源图一致：源图的手臂是披肩的青绿色（#5FA882 系）
    加白色大手套（#F2F8EC），不是纯白。
    """
    pal = porter.p
    steps = max(abs(int(hand_x - sh_x)), abs(int(hand_y - sh_y)), 1)
    mx = (sh_x + hand_x) * 0.5
    my = (sh_y + hand_y) * 0.5
    ex = mx - (hand_x - sh_x) * 0.2
    ey = my

    for i in range(steps + 1):
        t = i / steps
        x = (1 - t) ** 2 * sh_x + 2 * (1 - t) * t * ex + t ** 2 * hand_x
        y = (1 - t) ** 2 * sh_y + 2 * (1 - t) * t * ey + t ** 2 * hand_y
        # 上半段用披肩绿，靠近手用深一档
        c = pal["hair_dark"] if t < 0.45 else pal["cloth_dark"]
        for d in range(-thick // 2, thick // 2 + 1):
            porter.px(int(round(x)), int(round(y)) + d, c)

    # 手套（白，带描边）
    porter.rect(hand_x - 3, hand_y - 2, hand_x + 2, hand_y + 2, pal["ink"])
    porter.rect(hand_x - 2, hand_y - 2, hand_x + 2, hand_y + 1,
                pal["cape_lit"])


def compose(porter, *,
            body_dy=0.0,
            lean=0.0,
            torso_dx=0.0,
            foot_l=(0.0, 0.0), foot_l_dx=0.0,
            foot_r=(0.0, 0.0), foot_r_dx=0.0,
            sh=(3.0, -21.0),
            hand=(-6.0, -15.0),
            sword_angle=75.0,
            show_sword=True,
            arm_front=True):
    """合成一帧。所有参数为角色局部坐标（y 向上为负）。"""
    base = 0.0

    # ── 腿（源图部件，按位移摆放）──
    # 关键：位移有上限。腿的宽度只有 9px，横移超过 6px 就会与躯干断开
    # （早期版本大跨步用了 ±9，腿整个飘出去了）。
    MAX_LEG_DX = 6.0
    ldx = max(-MAX_LEG_DX, min(MAX_LEG_DX, foot_l_dx))
    rdx = max(-MAX_LEG_DX, min(MAX_LEG_DX, foot_r_dx))
    # 抬脚上限 3px，再多就够不着身体
    ldy = max(-3.0, min(0.0, foot_l[1]))
    rdy = max(-3.0, min(0.0, foot_r[1]))

    porter.blit(porter.leg_l, -9.0 + ldx, -(LEG_H - 1) + body_dy + ldy)
    porter.blit(porter.leg_r, 0.0 + rdx, -(LEG_H - 1) + body_dy + rdy)

    # ── 躯干（源图部件）──
    # 源图躯干左上角在 (0, 26)，相对中轴 14 是 -14
    porter.blit(porter.torso, -14.0 + torso_dx + lean,
                -LEG_H - TORSO_H + body_dy)

    # ── 手臂（重绘，可独立动）──
    if arm_front:
        draw_arm(porter, sh[0] + torso_dx + lean, sh[1] + body_dy,
                 hand[0], hand[1] + body_dy)
        if show_sword:
            draw_sword(porter, hand[0], hand[1] + body_dy, sword_angle)

    # ── 头（源图部件，贴在躯干顶端）──
    porter.blit(porter.head, -14.0 + torso_dx + lean,
                -LEG_H - TORSO_H - HEAD_H + body_dy)

    if not arm_front:
        draw_arm(porter, sh[0] + torso_dx + lean, sh[1] + body_dy,
                 hand[0], hand[1] + body_dy)
        if show_sword:
            draw_sword(porter, hand[0], hand[1] + body_dy, sword_angle)

    return porter.img


# ─────────────────────────── 基础动作 ───────────────────────────

def make_idle(p):
    out = []
    for dy, sa in [(0, 78), (-1, 76), (0, 78), (-1, 80)]:
        pt = Porter(**p)
        out.append(compose(pt, body_dy=dy, hand=(8, -15), sword_angle=sa))
    return out


def make_run(p):
    specs = [
        (-1, -3, 4, (-7, -1), (7, 0), -8, 70),
        (0, -2, 2, (-5, 0), (5, 0), -6, 74),
        (0, 0, 0, (-3, 0), (3, 0), -4, 78),
        (-1, 3, -4, (-7, 0), (7, -1), -8, 70),
        (0, 2, -2, (-5, 0), (5, 0), -6, 74),
        (0, 0, 0, (-3, 0), (3, 0), -4, 78),
    ]
    out = []
    for dy, ldx, rdx, fl, fr, hx, sa in specs:
        pt = Porter(**p)
        out.append(compose(pt, body_dy=dy, foot_l_dx=ldx, foot_r_dx=rdx,
                           foot_l=(0, fl[1]), foot_r=(0, fr[1]),
                           hand=(hx, -15), sword_angle=sa))
    return out


def make_jump(p):
    out = []
    pt = Porter(**p)
    out.append(compose(pt, body_dy=-2, foot_l=(0, -4), foot_r=(0, -4),
                       foot_l_dx=-2, foot_r_dx=2,
                       hand=(-5, -20), sword_angle=45))
    pt = Porter(**p)
    out.append(compose(pt, body_dy=-1, foot_l=(0, -2), foot_r=(0, -2),
                       foot_l_dx=-4, foot_r_dx=4,
                       hand=(-6, -18), sword_angle=25))
    pt = Porter(**p)
    out.append(compose(pt, body_dy=0, foot_l_dx=-3, foot_r_dx=3,
                       hand=(-6, -14), sword_angle=62))
    return out


def make_land(p):
    out = []
    pt = Porter(**p)
    out.append(compose(pt, body_dy=2, foot_l_dx=-3, foot_r_dx=3,
                       hand=(9, -13), sword_angle=82))
    pt = Porter(**p)
    out.append(compose(pt, body_dy=0, hand=(8, -15), sword_angle=78))
    return out


def make_dash(p):
    out = []
    pt = Porter(**p)
    out.append(compose(pt, body_dy=1, lean=-2, foot_l_dx=-5, foot_r_dx=4,
                       hand=(-8, -16), sword_angle=-12))
    pt = Porter(**p)
    out.append(compose(pt, body_dy=-1, lean=4, foot_l_dx=-7, foot_r_dx=7,
                       foot_l=(0, -1), hand=(12, -18), sword_angle=0))
    pt = Porter(**p)
    out.append(compose(pt, body_dy=0, lean=1, foot_l_dx=-4, foot_r_dx=4,
                       hand=(6, -16), sword_angle=28))
    return out


# ─────────────────── 四段攻击（各 6 帧，幅度加大） ───────────────────

def make_attack(p, idx):
    fns = [_uppercut, _sideslash, _thrust, _jump_slash]
    return fns[idx](p)


def _uppercut(p):
    """第1段 上挑：剑沿身体**垂直**上撩，从脚边到头顶之上。

    与第 3 段（突刺，剑水平前指）的区别必须靠「剑的角度」拉开：
    上挑全程剑接近竖直（90~110 与 -90~-110），不出现 0° 水平。

    6 帧：蹲身垂剑 → 提剑 → 撩至身前 → 命中(过头顶) → 收势 → 回位
    """
    specs = [
        dict(body_dy=3, lean=-2, foot_l_dx=-5, foot_r_dx=4,
             hand=(7, -9), sword_angle=100),          # 蓄势：蹲、剑垂脚边
        dict(body_dy=2, lean=-1, foot_l_dx=-4, foot_r_dx=4,
             hand=(9, -13), sword_angle=115),         # 提剑：刃朝下
        dict(body_dy=0, lean=1, foot_l_dx=-3, foot_r_dx=5,
             hand=(8, -18), sword_angle=150),         # 撩到身前（斜上）
        dict(body_dy=-2, lean=3, foot_l_dx=-2, foot_r_dx=6,
             hand=(7, -27), sword_angle=-105),        # 命中：过头顶
        dict(body_dy=-1, lean=2, foot_l_dx=-3, foot_r_dx=5,
             hand=(6, -25), sword_angle=-80),         # 收势
        dict(body_dy=1, lean=0, foot_l_dx=-4, foot_r_dx=4,
             hand=(6, -14), sword_angle=100),         # 回位
    ]
    return [compose(Porter(**p), **s) for s in specs]


def _sideslash(p):
    """第2段 横斩：大跨步 + 扭身横扫，剑水平划过大半圆。"""
    specs = [
        dict(body_dy=1, lean=-5, foot_l_dx=-7, foot_r_dx=5,
             hand=(-10, -18), sword_angle=-50),       # 扭身蓄力
        dict(body_dy=0, lean=-2, foot_l_dx=-7, foot_r_dx=6,
             hand=(-4, -18), sword_angle=-20),        # 起扫
        dict(body_dy=0, lean=3, foot_l_dx=-8, foot_r_dx=8,
             hand=(10, -18), sword_angle=15),         # 命中：大跨步
        dict(body_dy=0, lean=4, foot_l_dx=-7, foot_r_dx=8,
             hand=(13, -17), sword_angle=40),         # 惯性
        dict(body_dy=0, lean=2, foot_l_dx=-5, foot_r_dx=6,
             hand=(9, -16), sword_angle=70),          # 收势
        dict(body_dy=1, lean=0, foot_l_dx=-4, foot_r_dx=4,
             hand=(5, -15), sword_angle=100),         # 回位
    ]
    return [compose(Porter(**p), **s) for s in specs]


def _thrust(p):
    """第3段 突刺：剑水平直刺，身体极限前倾，后腿蹬直。"""
    specs = [
        dict(body_dy=1, lean=-6, foot_l_dx=-4, foot_r_dx=4,
             hand=(-9, -18), sword_angle=-30),        # 收剑蓄力
        dict(body_dy=0, lean=-2, foot_l_dx=-6, foot_r_dx=6,
             hand=(2, -18), sword_angle=-12),         # 前送
        dict(body_dy=0, lean=9, foot_l_dx=-9, foot_r_dx=9,
             hand=(18, -18), sword_angle=0),          # 命中：极限前倾
        dict(body_dy=0, lean=9, foot_l_dx=-9, foot_r_dx=9,
             hand=(20, -18), sword_angle=0),          # 顿住
        dict(body_dy=0, lean=4, foot_l_dx=-7, foot_r_dx=7,
             hand=(9, -18), sword_angle=-10),         # 回抽
        dict(body_dy=1, lean=0, foot_l_dx=-4, foot_r_dx=4,
             hand=(2, -16), sword_angle=95),          # 回位
    ]
    return [compose(Porter(**p), **s) for s in specs]


def _jump_slash(p):
    """第4段 跳劈：动画里腾空 → 举剑过头 → 下砸。

    只是动画表现，**不改实际物理**：判定范围仍以地面为准。
    """
    specs = [
        dict(body_dy=4, lean=-2, foot_l_dx=-6, foot_r_dx=5,
             hand=(5, -8), sword_angle=110),          # 下蹲蓄力
        # 起跳：整身抬高 7px，双腿收起
        dict(body_dy=-7, lean=1, foot_l=(0, -6), foot_r=(0, -6),
             foot_l_dx=-2, foot_r_dx=2,
             hand=(8, -22), sword_angle=-30),
        # 顶点：举剑过头，腿收最紧
        dict(body_dy=-10, lean=-1, foot_l=(0, -8), foot_r=(0, -8),
             foot_l_dx=-1, foot_r_dx=1,
             hand=(7, -28), sword_angle=-110),
        # 下砸：落回地面，剑劈到身前下方
        dict(body_dy=2, lean=5, foot_l_dx=-7, foot_r_dx=7,
             hand=(15, -14), sword_angle=95),
        # 冲击：身体压到最低
        dict(body_dy=5, lean=3, foot_l_dx=-8, foot_r_dx=8,
             hand=(12, -11), sword_angle=105),
        dict(body_dy=1, lean=0, foot_l_dx=-4, foot_r_dx=4,
             hand=(3, -15), sword_angle=95),          # 回位
    ]
    return [compose(Porter(**p), **s) for s in specs]


# ─────────────────────────── 输出 ───────────────────────────

def save_strip(frames, path):
    strip = Image.new("RGBA", (FRAME * len(frames), FRAME), (0, 0, 0, 0))
    for i, f in enumerate(frames):
        strip.alpha_composite(f, (i * FRAME, 0))
    strip.save(path)
    print(f"wrote {os.path.basename(path)} "
          f"({strip.width}x{strip.height}, {len(frames)} frames)")


def main():
    with open(os.path.join(PARTS, "palette.json"), encoding="utf-8") as f:
        pal = json.load(f)

    def op(n):
        return Image.open(os.path.join(PARTS, n)).convert("RGBA")

    p = {
        "palette": pal,
        "head": op("head.png"),
        "torso": op("torso.png"),
        "leg_l": op("leg_l.png"),
        "leg_r": op("leg_r.png"),
    }
    print(f"palette {len(pal)} 色, frame {FRAME}x{FRAME}, "
          f"head {p['head'].size}, torso {p['torso'].size}")

    save_strip(make_idle(p), os.path.join(OUT_DIR, "ori_idle.png"))
    save_strip(make_run(p), os.path.join(OUT_DIR, "ori_run.png"))
    save_strip(make_jump(p), os.path.join(OUT_DIR, "ori_jump.png"))
    save_strip(make_land(p), os.path.join(OUT_DIR, "ori_land.png"))
    save_strip(make_dash(p), os.path.join(OUT_DIR, "ori_dash.png"))
    for i in range(4):
        save_strip(make_attack(p, i),
                   os.path.join(OUT_DIR, f"ori_atk{i + 1}.png"))


if __name__ == "__main__":
    main()
