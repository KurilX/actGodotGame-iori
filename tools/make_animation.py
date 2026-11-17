"""程序化生成行走 / 跳跃 / 落地动画。

背景：48px 的 Q 版精灵腿部只有 10px 高，且两腿在原始待机姿势里并拢。
      若只做整块平移，观感仍是「滑行」而非行走（实测确实如此）。
      所以这里把两条腿**分别抠出来**，再按每帧的步态摆位：
      迈步 = 一腿前移抬起 + 另一腿后移，配合身体起伏。

腿部坐标由逐行像素剖面实测得出（见 tools/make_placeholder_art.py 的输出）：
  左腿 x5..13，右腿 x15..21，x22 以后是垂下的剑（不能算作腿）
  腿部纵向 y38..47

输出（横排图集，每帧 48x48，锚点帧底中心）：
  ori_idle.png 4 帧 / ori_run.png 6 帧 / ori_jump.png 3 帧 / ori_land.png 2 帧
"""

import math
import os

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "art", "characters", "ori", "ori_idle_src.png")
OUT_DIR = os.path.join(ROOT, "art", "characters", "ori")

FRAME_W = 48
FRAME_H = 48

Y_UPPER_BOT = 38      # 上段（头+躯干）下沿，也就是腿的起点
Y_LEG_BOT = 48        # 腿的底端

LEG_L_X0, LEG_L_X1 = 5, 14    # 左腿列范围（右开区间）
LEG_R_X0, LEG_R_X1 = 14, 22   # 右腿列范围
# 注意：x22..27 是垂下的剑，不参与摆位，跟随躯干一起动


def load_source():
    if not os.path.exists(SRC):
        raise FileNotFoundError(
            f"缺少源精灵 {SRC}，先运行 tools/make_placeholder_art.py")
    return Image.open(SRC).convert("RGBA")


def decompose(src):
    """拆成：上段（头+躯干+剑）、左腿、右腿。"""
    w, h = src.size

    upper = src.crop((0, 0, w, Y_UPPER_BOT))
    # 上段里把腿的区域挖空，避免腿被画两遍
    upper_px = upper.load()
    for y in range(Y_UPPER_BOT):
        for x in range(w):
            # 只挖最后几行里属于腿的列
            if y >= Y_UPPER_BOT - 2 and LEG_L_X0 <= x < LEG_R_X1:
                upper_px[x, y] = (0, 0, 0, 0)

    leg_l = src.crop((LEG_L_X0, Y_UPPER_BOT, LEG_L_X1, Y_LEG_BOT))
    leg_r = src.crop((LEG_R_X0, Y_UPPER_BOT, LEG_R_X1, Y_LEG_BOT))
    return upper, leg_l, leg_r


def shorten(leg, n):
    """从顶部裁掉 n 行，模拟抬腿时腿变短。

    注意：裁顶部会连带裁掉裤子/鞋的一部分，观感是「腿断了」。
    只在跳跃收腿时用很小的值，且必须配合下移让腿仍连着身体。
    """
    if n <= 0:
        return leg
    w, h = leg.size
    if n >= h:
        return Image.new("RGBA", (0, h), (0, 0, 0, 0))
    return leg.crop((0, n, w, h))


def compose(upper, leg_l, leg_r,
            body_dy=0, upper_dx=0,
            ll_dx=0, ll_dy=0, ll_cut=0,
            rl_dx=0, rl_dy=0, rl_cut=0,
            squeeze=0):
    """把三段贴到 48x48 帧。

    锚点：帧底中心。腿的**底边**贴帧底（或按 dy 抬起），上段叠在腿上。
    抬腿用 ll_dy/rl_dy 上移 + ll_cut/rl_cut 裁短组合，且裁短量要小，
    否则腿会和身体脱节。
    """
    base_x = (FRAME_W - 28) // 2
    ground_y = FRAME_H

    frame = Image.new("RGBA", (FRAME_W, FRAME_H), (0, 0, 0, 0))

    # 两条腿：底边对齐地面（或按 dy 抬起）
    for leg, x0, dx, dy, cut in [
        (leg_l, LEG_L_X0, ll_dx, ll_dy, ll_cut),
        (leg_r, LEG_R_X0, rl_dx, rl_dy, rl_cut),
    ]:
        part = shorten(leg, cut)
        if part.width == 0 or part.height == 0:
            continue
        ly = ground_y - part.height + dy
        frame.alpha_composite(part, (base_x + x0 + dx, ly))

    # 上段：底边固定接在腿顶（不被腿位移影响），只有 body_dy 整体动
    upper_y = ground_y - Y_LEG_BOT + body_dy + squeeze
    frame.alpha_composite(upper, (base_x + upper_dx, upper_y))
    return frame


def make_idle(upper, leg_l, leg_r):
    """4 帧待机：呼吸起伏 + 头部轻晃。"""
    specs = [
        dict(body_dy=0, upper_dx=0),
        dict(body_dy=-1, upper_dx=1),
        dict(body_dy=0, upper_dx=0),
        dict(body_dy=-1, upper_dx=-1),
    ]
    return [compose(upper, leg_l, leg_r, **s) for s in specs]


def make_run(upper, leg_l, leg_r):
    """6 帧跑：两腿前后交替 + 身体起伏。

    只用横向位移 + 小幅度抬脚（dy 最多 -1，不裁短），
    保证腿始终连着身体、靴子完整——裁短会让腿「断掉」。
    """
    specs = [
        # (body_dy, upper_dx, 左腿(dx,dy,cut), 右腿(dx,dy,cut))
        (-1, 1, (4, -1, 0), (-3, 0, 0)),    # 左腿前迈
        (0, 1, (2, 0, 0), (-1, 0, 0)),      # 过渡
        (0, 0, (0, 0, 0), (0, 0, 0)),       # 并拢落地
        (-1, -1, (-3, 0, 0), (4, -1, 0)),   # 右腿前迈
        (0, -1, (-1, 0, 0), (2, 0, 0)),     # 过渡
        (0, 0, (0, 0, 0), (0, 0, 0)),       # 并拢落地
    ]
    return [compose(upper, leg_l, leg_r,
                    body_dy=d[0], upper_dx=d[1],
                    ll_dx=d[2][0], ll_dy=d[2][1], ll_cut=d[2][2],
                    rl_dx=d[3][0], rl_dy=d[3][1], rl_cut=d[3][2])
            for d in specs]


def make_jump(upper, leg_l, leg_r):
    """3 帧跳跃：上升收腿 / 顶点张开 / 下落伸直。

    收腿用小值 dy（-2），不做裁短——裁短会让腿与身体断开。
    """
    specs = [
        # 上升：双腿收起（整体上移）
        dict(body_dy=-1, ll_dy=-2, rl_dy=-2),
        # 顶点：双腿张开
        dict(body_dy=0, ll_dx=-3, ll_dy=-1, rl_dx=3, rl_dy=-1),
        # 下落：双腿伸直
        dict(body_dy=0, ll_dx=-1, ll_dy=0, rl_dx=2, rl_dy=0),
    ]
    return [compose(upper, leg_l, leg_r, **s) for s in specs]


def make_land(upper, leg_l, leg_r):
    """2 帧落地：先压扁，再回弹。"""
    specs = [
        dict(body_dy=2, squeeze=2, ll_dx=-1, rl_dx=1),
        dict(body_dy=0, squeeze=0, ll_dx=0, rl_dx=0),
    ]
    return [compose(upper, leg_l, leg_r, **s) for s in specs]


# ─────────────────────────── 攻击与闪避 ───────────────────────────

# 挥剑弧线色：色板 #B9F2FF（丝线光）+ #FF7A9C（危险/弹幕）
ARC_LIGHT = (0xB9, 0xF2, 0xFF)
ARC_HOT = (0xFF, 0x7A, 0x9C)


def _draw_arc(frame, cx, cy, r, deg0, deg1, color, thickness=2, dir_sign=1):
    """在帧上画一段圆弧，表现挥砍轨迹。

    Godot/PIL 坐标系 y 向下，所以：
      角度 0°  = 右
      角度 90° = 下
      角度 -90° = 上
    挥砍弧线应该落在角色**右手侧、身体中段高度**，
    所以弧心取角色躯干中心，角度范围围绕 0°（正右）展开。
    """
    px = frame.load()
    w, h = frame.size
    steps = max(12, int(abs(deg1 - deg0)) * 2)
    for i in range(steps + 1):
        t = i / float(steps)
        a = math.radians(deg0 + (deg1 - deg0) * t)
        for th in range(thickness):
            rr = r - th
            x = int(round(cx + math.cos(a) * rr * dir_sign))
            y = int(round(cy + math.sin(a) * rr))
            if 0 <= x < w and 0 <= y < h:
                # 弧线中段最亮，两端渐隐
                edge = 1.0 - abs(t - 0.5) * 1.6
                alpha = max(0.0, min(1.0, edge))
                if alpha <= 0.05:
                    continue
                px[x, y] = (color[0], color[1], color[2], int(255 * alpha))


def make_attack(upper, leg_l, leg_r, index):
    """轻攻击四连，每段 3 帧：预备 → 挥出 → 收势。

    四段的差异（连段树的表现层）：
      1 段：平斩，弧线短而平，身体前倾 1px
      2 段：反手回斩，弧线反向，前倾 2px，站姿更稳
      3 段：下劈，弧线从上往下，前倾 3px + 下压
      4 段：收线终结，弧线最大且用高饱和色，前倾 4px + 前冲位移

    返回 3 帧列表。
    """
    # 每段的参数：(前倾, 下压, 弧心y, 半径, 起始角, 终止角, 方向, 弧色, 粗细)
    # 角度基准：0°=正右，90°=下，-90°=上（PIL/Godot 的 y 向下）
    #
    # 重要：挥砍弧线**不画进角色帧**。
    # 早期版本直接往帧上写像素，结果是弧线和角色重叠、把角色像素覆盖掉，
    # 看上去像描边而不是刀光。弧线改由 Godot 侧的独立特效节点绘制
    # （见 src/player/slash_fx.gd），这里只负责角色姿态。
    specs = [
        (-1, 0, 0.00, 0, 0, 0, 1, ARC_LIGHT, 3),      # 第1段 平斩
        (-2, 0, 0.00, 0, 0, 0, 1, ARC_LIGHT, 3),      # 第2段 回斩
        (-3, 1, 0.00, 0, 0, 0, 1, ARC_LIGHT, 3),      # 第3段 下劈
        (-4, 0, 0.00, 0, 0, 0, 1, ARC_HOT, 4),        # 第4段 终结
    ]
    tilt, press, cy, radius, a0, a1, sign, color, thick = specs[index]

    frames = []
    # 帧0：预备（身体后坐）
    f0 = compose(upper, leg_l, leg_r,
                 body_dy=0, upper_dx=-sign * 1,
                 ll_dx=-1, rl_dx=1)
    frames.append(f0)

    # 帧1：挥出（前倾 + 前跨，姿态要有明确的"甩出去"感）
    f1 = compose(upper, leg_l, leg_r,
                 body_dy=press, upper_dx=sign * abs(tilt) * -1,
                 ll_dx=-sign * 2, rl_dx=sign * 2)
    frames.append(f1)

    # 帧2：收势
    f2 = compose(upper, leg_l, leg_r,
                 body_dy=press, upper_dx=sign * abs(tilt) // 2 * -1,
                 ll_dx=-1, rl_dx=1)
    frames.append(f2)
    return frames


def make_dash(upper, leg_l, leg_r):
    """3 帧闪避：蓄势 → 冲刺（拉伸/前倾最大）→ 收势。

    像素图不做缩放（会破坏网格），改用：
      - 全身横向位移表现冲刺
      - 后腿大幅后拖 + 前腿前伸
      - 帧1 额外画 2 条速度线
    """
    frames = []

    # 帧0：蓄势，身体后坐
    f0 = compose(upper, leg_l, leg_r,
                 body_dy=1, upper_dx=-2,
                 ll_dx=-3, ll_dy=0, rl_dx=2, rl_dy=0)
    frames.append(f0)

    # 帧1：冲刺，身体大幅前压、腿极度前后张开
    f1 = compose(upper, leg_l, leg_r,
                 body_dy=-1, upper_dx=3,
                 ll_dx=-5, ll_dy=-1, rl_dx=5, rl_dy=-1)
    # 速度线：脚后方 3 条短横线，用半透明丝线光色
    px = f1.load()
    for (sy, ln, x0) in [(FRAME_H - 20, 8, 2), (FRAME_H - 15, 6, 4),
                         (FRAME_H - 25, 5, 6)]:
        for i in range(ln):
            x = x0 + i
            if 0 <= x < FRAME_W:
                a = int(190 * (1.0 - i / float(ln)))
                px[x, sy] = (ARC_LIGHT[0], ARC_LIGHT[1], ARC_LIGHT[2], a)
    frames.append(f1)

    # 帧2：收势，回到接近站姿
    f2 = compose(upper, leg_l, leg_r,
                 body_dy=0, upper_dx=1,
                 ll_dx=-2, rl_dx=3)
    frames.append(f2)
    return frames


def save_strip(frames, path):
    strip = Image.new("RGBA", (FRAME_W * len(frames), FRAME_H), (0, 0, 0, 0))
    for i, f in enumerate(frames):
        strip.alpha_composite(f, (i * FRAME_W, 0))
    strip.save(path)
    print(f"wrote {os.path.basename(path)} "
          f"({strip.width}x{strip.height}, {len(frames)} frames)")


def main():
    src = load_source()
    upper, leg_l, leg_r = decompose(src)
    print(f"source {src.size} -> upper {upper.size} "
          f"legL {leg_l.size} legR {leg_r.size}")

    save_strip(make_idle(upper, leg_l, leg_r),
               os.path.join(OUT_DIR, "ori_idle.png"))
    save_strip(make_run(upper, leg_l, leg_r),
               os.path.join(OUT_DIR, "ori_run.png"))
    save_strip(make_jump(upper, leg_l, leg_r),
               os.path.join(OUT_DIR, "ori_jump.png"))
    save_strip(make_land(upper, leg_l, leg_r),
               os.path.join(OUT_DIR, "ori_land.png"))

    # 轻攻击四连：每段一条独立图集，名字 atk1..atk4
    for i in range(4):
        save_strip(make_attack(upper, leg_l, leg_r, i),
                   os.path.join(OUT_DIR, f"ori_atk{i + 1}.png"))

    save_strip(make_dash(upper, leg_l, leg_r),
               os.path.join(OUT_DIR, "ori_dash.png"))


if __name__ == "__main__":
    main()
