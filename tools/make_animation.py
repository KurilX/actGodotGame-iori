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


def _squash_leg(sprite, rows):
    """从顶部裁掉 rows 行，模拟屈膝时腿变短。

    底部锚定：裁顶部而不是底部，这样脚仍然贴在地面上。
    保留至少 3 行，否则腿会完全消失。
    """
    if rows <= 0:
        return sprite
    h = sprite.size[1]
    cut = min(rows, h - 3)
    if cut <= 0:
        return sprite
    return sprite.crop((0, cut, sprite.size[0], h))


def compose(porter, *,
            body_dy=0.0,
            crouch=0.0,
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

    # ── 屈膝（crouch）──
    # 腿部部件只有 9~10px 高，没空间拆成大腿+小腿做真正的关节弯曲。
    # 所以用像素游戏的标准手法：**腿垂直压缩 + 脚保持贴地**。
    #   crouch=0  站立，腿 10px 全高
    #   crouch=1  最深屈膝，腿压到 7px，身体相应下沉 3px
    # 关键是"脚不离地"：压缩只从**顶部**裁，底部锚点不动。
    crouch = max(0.0, min(1.0, crouch))
    leg_squash = int(round(crouch * 3.0))      # 裁掉的行数（0..3）
    # 坐标 y 向下为正。腿裁短后底部仍贴地，
    # 所以**躯干要下移 leg_squash 行**（+y），腿本身位置不变。
    # 早期写成腿下移 + 躯干不动，结果腿被压低、身体没动，
    # 身高反而变大（实测 49→51），方向是反的。
    crouch_dy = leg_squash

    porter.blit(_squash_leg(porter.leg_l, leg_squash),
                -9.0 + ldx, -(LEG_H - 1) + body_dy + ldy)
    porter.blit(_squash_leg(porter.leg_r, leg_squash),
                0.0 + rdx, -(LEG_H - 1) + body_dy + rdy)

    # ── 躯干（源图部件）──
    # 源图躯干左上角在 (0, 26)，相对中轴 14 是 -14
    porter.blit(porter.torso, -14.0 + torso_dx + lean,
                -LEG_H - TORSO_H + body_dy + crouch_dy)

    # ── 手臂（重绘，可独立动）──
    if arm_front:
        draw_arm(porter, sh[0] + torso_dx + lean, sh[1] + body_dy,
                 hand[0], hand[1] + body_dy)
        if show_sword:
            draw_sword(porter, hand[0], hand[1] + body_dy, sword_angle)

    # ── 头（源图部件，贴在躯干顶端）──
    porter.blit(porter.head, -14.0 + torso_dx + lean,
                -LEG_H - TORSO_H - HEAD_H + body_dy + crouch_dy)

    if not arm_front:
        draw_arm(porter, sh[0] + torso_dx + lean, sh[1] + body_dy,
                 hand[0], hand[1] + body_dy)
        if show_sword:
            draw_sword(porter, hand[0], hand[1] + body_dy, sword_angle)

    return porter.img


# ─────────────────────────── 基础动作 ───────────────────────────

def make_idle(p):
    """待机：8 帧呼吸循环（原 4 帧太短，像是"抖动"而不是"呼吸"）。

    呼吸感的关键是**多维度同步变化**，只动身体会像上下弹跳：
      - body_dy   身体起伏（吸气时微微上升）
      - crouch    膝盖极轻微屈伸（配合呼吸，站姿不僵死）
      - sword_angle 剑随呼吸轻微摆动（手持物有余量）
      - head_bob  头部略微滞后于身体（延迟感是"活"的关键）

    用 ease_in_out 让循环两端平滑，避免首尾相接时"一顿"。
    """
    import keyframe as K

    # 振幅要够大才看得出来。
    # 第一版只有 body_dy -1.2 / crouch 0.16，实测身高只变化 1px，
    # 肉眼几乎看不到呼吸。现在拉到 body_dy -2.0 / crouch 0.35，
    # 身高变化 3px，配合剑的摆动才有"活的"感觉。
    # 呼吸 = 胸腔扩张 + 身体整体轻微上提。
    # 注意 body_dy 与 crouch 的方向关系：
    #   body_dy 为负 = 身体上移
    #   crouch 为正 = 腿变短、身体下沉
    # 两者符号相反！所以要"变高"必须 body_dy 负、crouch 略正（腿微弯但身体上提）。
    # 实测：纯 body_dy -2.0 + crouch 0 时身高变化最大，观感是"提气"。
    track = K.Track([
        # t,    缓动,          参数
        (0.00, None,          dict(body_dy=0.0, crouch=0.00,
                                   hand=(8.0, -15.0), sword_angle=78.0)),
        (0.32, K.ease_in_out, dict(body_dy=-2.0, crouch=0.10,
                                   hand=(8.0, -16.5), sword_angle=75.0)),
        (0.52, K.ease_in_out, dict(body_dy=-3.0, crouch=0.14,
                                   hand=(8.0, -17.5), sword_angle=72.5)),
        (0.74, K.ease_in_out, dict(body_dy=-1.6, crouch=0.07,
                                   hand=(8.0, -16.0), sword_angle=76.0)),
        (0.88, K.ease_in_out, dict(body_dy=-0.6, crouch=0.02,
                                   sword_angle=77.5)),
        (1.00, K.ease_in_out, dict(body_dy=0.0, crouch=0.00,
                                   hand=(8.0, -15.0), sword_angle=78.0)),
    ])

    out = []
    for params in K.bake(track, 8):
        pt = Porter(**p)
        out.append(compose(pt, **params))
    return out


def make_run(p):
    """跑动：8 帧一个完整步周期（原 6 帧，步频太碎像"小碎步"）。

    跑动要有"蹬地"的力量感，不能只是两条腿左右摆。三个要点：

      1. **身体上下起伏**：蹬地瞬间最低，腾空时最高（body_dy 摆动 2px）
      2. **屈膝差异**：蹬地腿伸直（crouch 小）、收起的腿屈曲（crouch 大）
      3. **脚部抬起**：后蹬的脚要真的离地（foot_l/r 的 y 为负）

    一个周期分为两个半周期（左脚蹬地 / 右脚蹬地），
    关键帧只写左半周期（0→0.5），右半周期镜像。这样改一处等于改两边。
    """
    import keyframe as K

    # 左半周期：左脚支撑蹬地 → 右脚前摆
    half = [
        (0.00, None,           dict(body_dy=0.0, crouch=0.45,
                                    foot_l_dx=-5.0, foot_r_dx=4.0,
                                    foot_l=(0.0, 0.0), foot_r=(0.0, -2.0),
                                    hand=(-7.0, -15.0), sword_angle=72.0)),
        (0.25, K.ease_out,     dict(body_dy=-2.0, crouch=0.10,
                                    foot_l_dx=-4.0, foot_r_dx=1.0,
                                    foot_l=(0.0, -2.0), foot_r=(0.0, 0.0),
                                    hand=(-5.0, -16.0), sword_angle=75.0)),
        (0.50, K.ease_in_out,  dict(body_dy=0.0, crouch=0.40,
                                    foot_l_dx=1.0, foot_r_dx=-4.0,
                                    foot_l=(0.0, 0.0), foot_r=(0.0, -2.0),
                                    hand=(-7.0, -15.0), sword_angle=72.0)),
    ]

    def mirror(keys):
        """把关键帧左右镜像，拼出完整周期。"""
        out = []
        for t, ease, params in keys:
            m = dict(params)
            m["foot_l_dx"] = -params["foot_r_dx"]
            m["foot_r_dx"] = -params["foot_l_dx"]
            m["foot_l"] = params["foot_r"]
            m["foot_r"] = params["foot_l"]
            out.append((t + 0.5, ease, m))
        return out

    # 拼完整周期：0→0.5 是原关键帧，0.5→1.0 是镜像。
    # **注意 0.5 这个点只保留一次**，镜像时跳过 half[0]（那正是 0.5 处）。
    # 早期在末尾又追加了一个 (1.0, ...)，导致时间点变成
    # [0, .25, .5, .75, 1.0, 1.0]，重复的 1.0 让 sample() 落进
    # span<=0 的分支，采样出错、一条腿被固定住。
    keys = list(half)
    for t, ease, params in mirror(half[1:]):
        if t < 1.0 - 1e-9:
            keys.append((t, ease, params))
    # 用镜像后的最后一帧（即右腿蹬地、左腿前摆）作为终点，
    # 它与起点是镜像关系，循环接起来才顺
    last = mirror([half[0]])[0]
    keys.append((1.0, K.ease_in_out, last[2]))

    track = K.Track(keys)
    out = []
    for params in K.bake(track, 8):
        pt = Porter(**p)
        out.append(compose(pt, **params))
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
    """落地：6 帧屈膝缓冲（原 2 帧，几乎没有缓冲感）。

    落地是动作游戏里"重量感"最重要的瞬间。设计要点：

      1. **深屈膝 + 身体猛沉**：第 1 帧 crouch 就到 0.85，
         腿压到最短、身体压到最低，这一帧决定"砸下来"的分量
      2. **腿部外张**：落地时双脚会自然分开吸收冲击（foot_dx ±5）
      3. **回弹过冲**：恢复阶段用 ease_out_back 轻微过冲再回正，
         没有过冲的落地会像"电梯停住"，很假
      4. **剑和手的滞后**：落地瞬间剑还在往下走，第 3 帧才收住，
         这个延迟是"物理感"的来源

    帧序：触地(最深) → 压实 → 回弹过冲 → 收 → 站定 → 平稳
    """
    import keyframe as K

    track = K.Track([
        (0.00, None,          dict(body_dy=3.0, crouch=0.85,
                                   foot_l_dx=-5.0, foot_r_dx=5.0,
                                   hand=(10.0, -11.0), sword_angle=86.0)),
        (0.18, K.ease_out,    dict(body_dy=3.5, crouch=0.95,
                                   foot_l_dx=-5.0, foot_r_dx=5.0,
                                   hand=(10.0, -10.0), sword_angle=88.0)),
        # 回弹过冲：身体弹起比站立更高一点，腿伸直
        (0.42, K.ease_out,    dict(body_dy=-1.5, crouch=0.0,
                                   foot_l_dx=-3.0, foot_r_dx=3.0,
                                   hand=(8.0, -17.0), sword_angle=74.0)),
        (0.62, K.ease_in_out, dict(body_dy=0.5, crouch=0.25,
                                   foot_l_dx=-4.0, foot_r_dx=4.0,
                                   hand=(8.0, -14.0), sword_angle=80.0)),
        (0.85, K.ease_in_out, dict(body_dy=-0.3, crouch=0.08,
                                   foot_l_dx=-3.5, foot_r_dx=3.5,
                                   sword_angle=77.0)),
        (1.00, K.ease_in_out, dict(body_dy=0.0, crouch=0.0,
                                   foot_l_dx=-3.0, foot_r_dx=3.0,
                                   hand=(8.0, -15.0), sword_angle=78.0)),
    ])

    out = []
    for params in K.bake(track, 6):
        pt = Porter(**p)
        out.append(compose(pt, **params))
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
    """第2段 横斩：**真正的水平横扫** —— 剑从身后扫到身前，纵向高度几乎不变。

    ## 为什么重写

    原版剑角是 -50 → -20 → 15 → 40 → 70 → 100，看起来像「从右上往右下劈」，
    原因有两个：
      1. 角度跨了 150°，但**起点在右上（-50）、终点在下方（100）**，
         轨迹是斜的，不是水平
      2. hand 的 y 从 -18 变到 -16，几乎没动 —— 手高度不变，
         但剑角一路往下，视觉上就是"劈"

    而且第 1 段上挑（100→115→150→-105）同样是垂直方向的弧，
    两段都是"竖着划"，所以观感重复。

    ## 正确做法

    横斩要做到三点：
      · **手的高度锁死不变**（y 恒为 -19），这是水平的物理保证
      · **剑角只在 180° 与 0° 附近摆动**，中间穿过 -90°（正上）或 90°（正下）都不对
      · **剑身后的蓄力角度是 -160°（左后方）**，扫过 -90° 再到 0°，
        但因为手在同一高度，视觉上是水平画过去的

    这里用「剑角从 -160° 扫到 -10°」——注意 **-160° 和 -10° 都在上半圈**，
    剑尖始终指向左上→右上，只在水平面内旋转，不会往下掉。
    """
    # 参数经过剑尖轨迹验证（tools 里算过）：
    #   旧版 剑尖 x跨度 29.7 / y跨度 53.2 → 比值 0.6，是**竖劈**
    #   新版 剑尖 x跨度 87.7 / y跨度 25.7 → 比值 3.4，是**横扫**
    # 关键不是"剑转多少度"，而是**手要横向大幅平移**。
    # 只转剑不移动手，剑尖是在原地画圆，永远看起来是劈。
    # 方案 B1：斜扫 + 转剑（左上 → 右下，全程剑自转 310°）
    #
    # 对比数据（剑尖轨迹）：
    #   第1段上挑   x跨度 29.2 / y跨度 76.5 → 比值 0.38（垂直）
    #   旧版横斩     x跨度 29.7 / y跨度 53.2 → 比值 0.56（其实是竖劈）
    #   本版 B1      x跨度 69.2 / y跨度 64.1 → 比值 1.08（斜扫）
    #
    # 单纯"让剑走水平线"（贴 ±25° 摆动）反而最不横向 ——
    # 那样剑是在原地打转，剑尖几乎不位移。
    # 真正让观感"横扫"的是 **手的大幅横向平移**；
    # 转剑则提供灵活感，两者结合才是这版。
    specs = [
        # 蓄力：扭身，剑收到身后左上方
        dict(body_dy=1, lean=-7, foot_l_dx=-6, foot_r_dx=5,
             hand=(-12, -21), sword_angle=-160),
        # 起扫：手开始前送，剑扫向左上
        dict(body_dy=0, lean=-4, foot_l_dx=-6, foot_r_dx=6,
             hand=(-5, -20), sword_angle=-100),
        # 命中：大跨步，手到身前中线，剑身横平（这一帧最像"扫"）
        dict(body_dy=0, lean=3, foot_l_dx=-8, foot_r_dx=8,
             hand=(3, -19), sword_angle=-30),
        # 惯性：手继续前伸，剑已甩到右前，继续自转
        dict(body_dy=0, lean=5, foot_l_dx=-7, foot_r_dx=8,
             hand=(10, -19), sword_angle=60),
        # 收势：剑落到右前下方，转势收住
        dict(body_dy=0, lean=3, foot_l_dx=-5, foot_r_dx=6,
             hand=(15, -18), sword_angle=120),
        # 回位
        dict(body_dy=1, lean=0, foot_l_dx=-4, foot_r_dx=4,
             hand=(5, -15), sword_angle=100),
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
    """第4段 跳劈：动画里腾空 → 举剑过头 → 垂直劈落。

    只是动画表现，**不改实际物理**：判定范围仍以地面为准。

    角度约定：0°=剑尖正右，-90°=剑尖正上，+90°=剑尖正下。
    跳劈必须满足两个条件，画面上才读得出「从上往下劈」：
      - 举剑阶段：剑尖朝上（约 -95），且握把抬到头顶上方
      - 劈落阶段：剑尖朝下（约 +85），握把落到腰高

    早期版本用的是 -110 → 95，但握把位置没跟着抬/落，
    结果视觉上剑一直斜指向右上，看起来像「从下往上撩」而不是劈。
    """
    specs = [
        # 0 下蹲：剑拖在身后下方
        dict(body_dy=4, lean=-2, foot_l_dx=-6, foot_r_dx=5,
             hand=(2, -10), sword_angle=120),
        # 1 起跳：身体抬高，剑收到身前
        dict(body_dy=-7, lean=1, foot_l=(0, -6), foot_r=(0, -6),
             foot_l_dx=-2, foot_r_dx=2,
             hand=(4, -22), sword_angle=-60),
        # 2 顶点：握把抬到头顶上方，剑尖竖直朝上
        dict(body_dy=-10, lean=-1, foot_l=(0, -8), foot_r=(0, -8),
             foot_l_dx=-1, foot_r_dx=1,
             hand=(3, -34), sword_angle=-95),
        # 3 下砸命中：握把落到腰高，剑尖竖直朝下劈到身前
        dict(body_dy=2, lean=3, foot_l_dx=-7, foot_r_dx=7,
             hand=(12, -16), sword_angle=85),
        # 4 冲击：剑压得更低，身体压到最低
        dict(body_dy=5, lean=2, foot_l_dx=-8, foot_r_dx=8,
             hand=(11, -12), sword_angle=100),
        # 5 回位
        dict(body_dy=1, lean=0, foot_l_dx=-4, foot_r_dx=4,
             hand=(6, -15), sword_angle=95),
    ]
    return [compose(Porter(**p), **s) for s in specs]


# ─────────────────────────── 输出 ───────────────────────────

# ─────────────── 重攻击三连（各 8 帧，幅度明显更大） ───────────────

def make_heavy(p, idx):
    fns = [_heavy_sweep, _heavy_uppercut, _heavy_meteor]
    return fns[idx](p)


def _heavy_sweep(p):
    """重1 蓄力横扫：扭身蓄力 → 大跨步横扫。

    与轻2「横斩」的区别：
      - 蓄力更长（前 3 帧都在扭身），身体后仰更多（lean 到 -10）
      - 跨步幅度翻倍（腿 ±9，已接近限位 6 的边界，用 6 保守处理）
      - 剑扫过 200° 以上，从身后扫到身前
    8 帧：扭身 → 蓄力 → 沉腰 → 起扫 → 命中 → 惯性 → 收势 → 回位
    """
    specs = [
        dict(body_dy=1, lean=-7, foot_l_dx=-6, foot_r_dx=5,
             hand=(-12, -20), sword_angle=-80),
        dict(body_dy=2, lean=-10, foot_l_dx=-6, foot_r_dx=5,
             hand=(-14, -22), sword_angle=-100),
        dict(body_dy=3, lean=-9, foot_l_dx=-6, foot_r_dx=6,
             hand=(-13, -21), sword_angle=-110),
        dict(body_dy=1, lean=-4, foot_l_dx=-6, foot_r_dx=6,
             hand=(-6, -20), sword_angle=-40),
        # 命中：大跨步 + 身体前压到最大
        dict(body_dy=0, lean=6, foot_l_dx=-6, foot_r_dx=6,
             hand=(14, -20), sword_angle=25),
        dict(body_dy=0, lean=7, foot_l_dx=-6, foot_r_dx=6,
             hand=(16, -19), sword_angle=45),
        dict(body_dy=1, lean=4, foot_l_dx=-5, foot_r_dx=5,
             hand=(11, -18), sword_angle=75),
        dict(body_dy=1, lean=0, foot_l_dx=-4, foot_r_dx=4,
             hand=(5, -16), sword_angle=95),
    ]
    return [compose(Porter(**p), **s) for s in specs]


def _heavy_uppercut(p):
    """重2 上挑重斩：深蹲 → 全身上撩，把剑从脚边撩到头顶之上。

    与轻1「上挑」的区别：
      - 蹲得更深（body_dy 到 5）
      - 撩得更高（剑角到 -125，握把抬到头顶之上）
      - 身体后仰幅度更大（lean 到 6）
    8 帧：起势 → 深蹲 → 蓄力 → 起撩 → 升至半空 → 命中(最高) → 落势 → 回位
    """
    specs = [
        dict(body_dy=2, lean=-3, foot_l_dx=-5, foot_r_dx=5,
             hand=(4, -12), sword_angle=115),
        dict(body_dy=5, lean=-5, foot_l_dx=-6, foot_r_dx=5,
             hand=(3, -9), sword_angle=130),
        dict(body_dy=5, lean=-6, foot_l_dx=-6, foot_r_dx=5,
             hand=(2, -8), sword_angle=140),
        dict(body_dy=2, lean=-2, foot_l_dx=-5, foot_r_dx=5,
             hand=(7, -14), sword_angle=95),
        dict(body_dy=-2, lean=2, foot_l_dx=-4, foot_r_dx=6,
             hand=(9, -24), sword_angle=20),
        # 命中：剑举到最高，身体后仰
        dict(body_dy=-5, lean=6, foot_l_dx=-3, foot_r_dx=6,
             hand=(7, -32), sword_angle=-125),
        dict(body_dy=-3, lean=4, foot_l_dx=-4, foot_r_dx=5,
             hand=(6, -28), sword_angle=-95),
        dict(body_dy=1, lean=0, foot_l_dx=-5, foot_r_dx=5,
             hand=(4, -16), sword_angle=95),
    ]
    return [compose(Porter(**p), **s) for s in specs]


def _heavy_meteor(p):
    """重3 泰山压顶：跃到最高 → 举剑 → 砸落。

    这是三段里最重的一击，动画上做了三件事：
      - 跃得很高（body_dy 到 -14，比轻攻击的跳劈 -10 更高）
      - 空中停留更久（连续 2 帧在最高点）
      - 落地压得极低（body_dy 到 7），形成强烈的高低对比
    8 帧：起势 → 起跳 → 升至顶点 → 顶点举剑 → 下落 → 砸中 → 余震 → 回位
    """
    specs = [
        dict(body_dy=3, lean=-3, foot_l_dx=-6, foot_r_dx=6,
             hand=(4, -12), sword_angle=115),
        # 起跳
        dict(body_dy=-8, lean=2, foot_l=(0, -6), foot_r=(0, -6),
             foot_l_dx=-3, foot_r_dx=3,
             hand=(6, -24), sword_angle=-20),
        # 顶点：收腿到最紧
        dict(body_dy=-14, lean=-1, foot_l=(0, -9), foot_r=(0, -9),
             foot_l_dx=-1, foot_r_dx=1,
             hand=(4, -32), sword_angle=-70),
        # 顶点举剑：剑尖竖直朝上
        dict(body_dy=-13, lean=-2, foot_l=(0, -8), foot_r=(0, -8),
             foot_l_dx=-1, foot_r_dx=1,
             hand=(3, -36), sword_angle=-100),
        # 下落
        dict(body_dy=-4, lean=3, foot_l=(0, -3), foot_r=(0, -3),
             foot_l_dx=-3, foot_r_dx=3,
             hand=(10, -22), sword_angle=30),
        # 砸中：剑竖直朝下砸到地面，身体压到最低
        dict(body_dy=7, lean=5, foot_l_dx=-6, foot_r_dx=6,
             hand=(14, -10), sword_angle=95),
        # 余震：压得更低一点
        dict(body_dy=8, lean=4, foot_l_dx=-6, foot_r_dx=6,
             hand=(12, -8), sword_angle=105),
        dict(body_dy=2, lean=0, foot_l_dx=-5, foot_r_dx=5,
             hand=(6, -15), sword_angle=95),
    ]
    return [compose(Porter(**p), **s) for s in specs]


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
    # 重攻击三连：各 8 帧
    for i in range(3):
        save_strip(make_heavy(p, i),
                   os.path.join(OUT_DIR, f"ori_heavy{i + 1}.png"))


if __name__ == "__main__":
    main()
