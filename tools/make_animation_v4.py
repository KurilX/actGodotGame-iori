"""V4 部件层动画合成器（PixelLab 式骨骼控制，本地实现）。

复用 make_animation.py 的骨架参数（keyframe/track），但部件从
parts_v4/ 的 7 层持久化部件合成——部件文件永不变，只有骨架参数变。

部件布局（基于 parts_v4 网格，60 逻辑px 高）：
  head   : 全宽 39x31，y 0..31
  torso  : x 30..46, y 31..43
  skirt  : x 28..46, y 41..49
  arm_l  : x 24..29, y 31..47
  arm_r  : x 47..52, y 31..47
  leg_l  : x 36..40, y 47..61
  leg_r  : x 40..44, y 47..61

输出：80x80 帧（脚底 y=78），与现管线兼容。
"""
import math
import os
import sys

from PIL import Image

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARTS = os.path.join(ROOT, "art", "characters", "ori", "parts_v4")
OUT_DIR = os.path.join(ROOT, "art", "characters", "ori", "frames_v4_layers")
OUT_ANIM = os.path.join(ROOT, "art", "characters", "ori")

FRAME = 80
FEET_Y = 78
sys.path.insert(0, os.path.join(ROOT, "tools"))
import keyframe as K  # noqa: E402


def load_parts():
    p = {}
    for n in ("head", "torso", "skirt", "arm_l", "arm_r", "leg_l", "leg_r"):
        p[n] = Image.open(os.path.join(PARTS, f"{n}.png")).convert("RGBA")
    with open(os.path.join(PARTS, "palette.json"), encoding="utf-8") as f:
        p["palette"] = json.load(f)
    return p


import json  # noqa: E402

# 部件在"标准站姿"下的锚点（逻辑坐标，y 向上为负，原点=双脚间地面点）
# 头 31 逻辑px 高、躯干 12、裙 8、腿 14 → 总 61 逻辑px ≈ 48 显示px 的换算：
# 显示 1 逻辑px = 48/61 ≈ 0.79 帧 px。为简化：直接把逻辑网格映射到
# 帧坐标：foot=78, 身高 61*0.78≈48 ✓
SCALE = 48.0 / 61.0


def L(x, y):
    """逻辑坐标 → 帧坐标（x 相对中轴 20，y 相对脚底 78）。"""
    return (20 + x * SCALE, 78 + y * SCALE)


def blit_scaled(dst, part, ax, ay, scale=None):
    """部件按原生尺寸贴（部件已是 PX 倍显示分辨率，不再二次缩放）。

    ay = 部件**底边**的帧坐标。
    """
    w, h = part.size
    dst.alpha_composite(part, (int(round(ax - w / 2)), int(round(ay - h))))


def compose(p, *, body_dy=0.0, crouch=0.0, lean=0.0, torso_dx=0.0,
            foot_l=(0.0, 0.0), foot_l_dx=0.0,
            foot_r=(0.0, 0.0), foot_r_dx=0.0,
            hand=(11.0, -18.0), sword_angle=75.0,
            show_sword=True):
    img = Image.new("RGBA", (FRAME, FRAME), (0, 0, 0, 0))
    crouch = max(0.0, min(1.0, crouch))
    squash = round(crouch * 3)            # 腿压 0..3 逻辑px
    body_shift = squash                    # 躯干随之下沉

    # 部件显示高度（PX 倍放大后的实际像素）：腿 14 显示px、裙 8、躯干 12、头 31
    # 布局（显示px，脚底=78）：
    #   legs  底 78, 顶 64
    #   skirt 底 64, 顶 56
    #   torso 底 58, 顶 46   （裙顶与躯干底重叠 2px，保证衔接）
    #   head  底 48,  顶 17  （头底与躯干顶重叠 2px）
    # body_dy 负 = 上浮；crouch 腿压缩 + 身体下沉

    legs_h = 14 - squash                  # 显示px（部件原生高 14）

    # 腿（底部锚定 78）
    for key, xoff, dx, fy in (("leg_l", -4.0, foot_l_dx, foot_l[1]),
                              ("leg_r", 4.0, foot_r_dx, foot_r[1])):
        leg = p[key]
        if squash > 0:
            leg = leg.crop((0, squash, leg.width, leg.height))
        ax, ay = 20 + xoff + dx, FEET_Y - fy + body_dy
        blit_scaled(img, leg, ax, ay - fy + body_dy)

    # 裙（底 = 腿顶 64）
    ax, ay = 20 + torso_dx + lean, FEET_Y - legs_h - body_dy
    blit_scaled(img, p["skirt"], ax, ay)

    # 躯干（底 = 58，与裙顶 56 重叠衔接）
    ax, ay = 20 + torso_dx + lean, FEET_Y - legs_h - 6 - body_dy
    blit_scaled(img, p["torso"], ax, ay)

    # 手臂（左右，肩位随躯干）
    axl, ayl = 20 - 11 + torso_dx + lean, FEET_Y - legs_h - 6 + 2 - body_dy
    blit_scaled(img, p["arm_l"], axl, ayl)
    axr, ayr = 20 + 11 + torso_dx + lean, FEET_Y - legs_h - 6 + 2 - body_dy
    blit_scaled(img, p["arm_r"], axr, ayr)

    # 头（底 = 躯干顶 46 + 2 重叠）
    axh, ayh = 20 + torso_dx + lean, FEET_Y - legs_h - 12 - body_dy
    blit_scaled(img, p["head"], axh, ayh)

    # 剑
    if show_sword:
        draw_sword(img, p, hand, body_dy, sword_angle)

    return img


def draw_sword(img, p, hand, body_dy, angle_deg):
    pal = {k: v for k, v in p["palette"].items()}
    import PIL.ImageDraw as ID
    d = ID.Draw(img)
    hx = 20 + hand[0]
    hy = 78 + hand[1] + body_dy
    rad = math.radians(angle_deg)
    dx, dy = math.cos(rad), math.sin(rad)
    ink = hex_rgba(pal["ink"])
    blade = hex_rgba(pal["blade"])
    blade_hi = hex_rgba(pal["blade_hi"])
    hilt = hex_rgba(pal["hilt"])
    for i in range(-4, 1):
        d.point((hx + dx * i, hy + dy * i), fill=hilt)
    gx, gy = hx + dx, hy + dy
    for s in (-1, 1):
        d.point((gx - dy * s, gy + dx * s), fill=ink)
    for i in range(2, 22):
        x = hx + dx * i
        y = hy + dy * i
        d.point((x, y), fill=blade)
        d.point((x - dy * 0.8, y + dx * 0.8), fill=blade_hi)


def hex_rgba(h, a=255):
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a)


def save_strip(frames, path):
    if not frames:
        return
    w = FRAME * len(frames)
    strip = Image.new("RGBA", (w, FRAME), (0, 0, 0, 0))
    for i, f in enumerate(frames):
        strip.alpha_composite(f, (i * FRAME, 0))
    strip.save(path)
    print(f"wrote {os.path.basename(path)} ({w}x{FRAME}, {len(frames)} frames)")


# ── 动作定义（复用 make_animation 的节奏参数）──

def make_idle(p):
    track = K.Track([
        (0.00, None, dict(body_dy=0.0, crouch=0.00,
                          hand=(11.0, -18.0), sword_angle=78.0)),
        (0.32, K.ease_in_out, dict(body_dy=-2.0, crouch=0.10,
                                   hand=(11.0, -19.5), sword_angle=75.0)),
        (0.52, K.ease_in_out, dict(body_dy=-3.0, crouch=0.14,
                                   hand=(11.0, -20.5), sword_angle=72.5)),
        (0.74, K.ease_in_out, dict(body_dy=-1.6, crouch=0.07,
                                   hand=(11.0, -19.0), sword_angle=76.0)),
        (0.88, K.ease_in_out, dict(body_dy=-0.6, crouch=0.02,
                                   sword_angle=77.5)),
        (1.00, K.ease_in_out, dict(body_dy=0.0, crouch=0.00,
                                   hand=(11.0, -18.0), sword_angle=78.0)),
    ])
    return [compose(p, **params) for params in K.bake(track, 8)]


def make_run(p):
    track = K.Track([
        (0.00, None, dict(foot_l=(0, 0), foot_r=(0, -2), body_dy=-1,
                          hand=(11.0, -17.0), sword_angle=60)),
        (0.25, K.ease_in_out, dict(foot_l=(-3, -3), foot_r=(3, 0),
                                   body_dy=-2, hand=(12.0, -19.0),
                                   sword_angle=55)),
        (0.50, K.ease_in_out, dict(foot_l=(0, -2), foot_r=(0, 0),
                                   body_dy=-1, hand=(11.0, -17.0),
                                   sword_angle=60)),
        (0.75, K.ease_in_out, dict(foot_l=(3, 0), foot_r=(-3, -3),
                                   body_dy=-2, hand=(12.0, -19.0),
                                   sword_angle=55)),
        (1.00, K.ease_in_out, dict(foot_l=(0, 0), foot_r=(0, -2),
                                   body_dy=-1, hand=(11.0, -17.0),
                                   sword_angle=60)),
    ])
    return [compose(p, **params) for params in K.bake(track, 8)]


def make_jump(p):
    track = K.Track([
        (0.00, None, dict(crouch=0.8, body_dy=1, foot_l=(0, 0),
                          foot_r=(0, 0), hand=(11.0, -16.0), sword_angle=70)),
        (0.4, K.ease_in_out, dict(body_dy=-6, foot_l=(-2, -4),
                                  foot_r=(2, -4), hand=(11.0, -21.0),
                                  sword_angle=45)),
        (0.7, K.ease_in_out, dict(body_dy=-4, foot_l=(-2, -3),
                                  foot_r=(2, -3), hand=(11.0, -20.0),
                                  sword_angle=50)),
        (1.0, K.ease_in_out, dict(crouch=0.6, body_dy=1, foot_l=(0, 0),
                                  foot_r=(0, 0), hand=(11.0, -16.0),
                                  sword_angle=70)),
    ])
    return [compose(p, **params) for params in K.bake(track, 3)]


def make_land(p):
    track = K.Track([
        (0.00, None, dict(crouch=0.9, body_dy=2, foot_l=(0, 0),
                          foot_r=(0, 0), hand=(11.0, -15.0), sword_angle=72)),
        (0.5, K.ease_in_out, dict(crouch=0.4, body_dy=0.5, foot_l=(0, 0),
                                  foot_r=(0, 0), hand=(11.0, -17.0),
                                  sword_angle=74)),
        (1.0, K.ease_in_out, dict(crouch=0.0, body_dy=0, foot_l=(0, 0),
                                  foot_r=(0, 0), hand=(11.0, -18.0),
                                  sword_angle=76)),
    ])
    return [compose(p, **params) for params in K.bake(track, 6)]


def make_dash(p):
    track = K.Track([
        (0.00, None, dict(lean=1.5, body_dy=-1, foot_l=(-4, -1),
                          foot_r=(4, -1), hand=(14.0, -18.0), sword_angle=50)),
        (0.5, K.ease_in_out, dict(lean=2.0, body_dy=-2, foot_l=(4, -2),
                                  foot_r=(-4, -1), hand=(15.0, -17.0),
                                  sword_angle=48)),
        (1.0, K.ease_in_out, dict(lean=1.0, body_dy=-1, foot_l=(0, 0),
                                  foot_r=(0, 0), hand=(12.0, -18.0),
                                  sword_angle=52)),
    ])
    return [compose(p, **params) for params in K.bake(track, 3)]


def make_attack(p, seg):
    """四段轻攻击，每段 6 帧。"""
    angles = [(100, 40), (40, -30), (-30, 30), (30, 100)][seg]
    track = K.Track([
        (0.00, None, dict(hand=(9.0, -17.0), sword_angle=angles[0] + 20,
                          body_dy=0, lean=0.5)),
        (0.25, K.ease_in_out, dict(hand=(12.0, -19.0), sword_angle=angles[0],
                                   body_dy=-1, lean=1.0)),
        (0.45, K.ease_in_out, dict(hand=(15.0, -17.0), sword_angle=angles[1],
                                   body_dy=-1, lean=2.0)),
        (0.65, K.ease_in_out, dict(hand=(14.0, -16.0), sword_angle=angles[1] + 10,
                                   body_dy=0, lean=1.5)),
        (0.85, K.ease_in_out, dict(hand=(11.0, -17.0), sword_angle=angles[0],
                                   body_dy=0, lean=0.5)),
        (1.00, K.ease_in_out, dict(hand=(11.0, -18.0), sword_angle=angles[0],
                                   body_dy=0, lean=0.0)),
    ])
    return [compose(p, **params) for params in K.bake(track, 6)]


def make_heavy(p, seg):
    """三段重击，每段 8 帧。"""
    if seg == 0:
        track = K.Track([
            (0.00, None, dict(hand=(7.0, -16.0), sword_angle=95, body_dy=0)),
            (0.3, K.ease_in_out, dict(hand=(5.0, -22.0), sword_angle=130,
                                      body_dy=-1, crouch=0.3)),
            (0.5, K.ease_in_out, dict(hand=(5.0, -24.0), sword_angle=140,
                                      body_dy=-2, crouch=0.5)),
            (0.65, K.ease_in_out, dict(hand=(13.0, -18.0), sword_angle=40,
                                       body_dy=0)),
            (0.8, K.ease_in_out, dict(hand=(14.0, -15.0), sword_angle=55,
                                      body_dy=1, crouch=0.4)),
            (1.0, K.ease_in_out, dict(hand=(11.0, -17.0), sword_angle=70,
                                      body_dy=0)),
        ])
    elif seg == 1:
        track = K.Track([
            (0.00, None, dict(hand=(9.0, -16.0), sword_angle=80, body_dy=0)),
            (0.3, K.ease_in_out, dict(hand=(11.0, -24.0), sword_angle=30,
                                      body_dy=-2)),
            (0.5, K.ease_in_out, dict(hand=(13.0, -28.0), sword_angle=-20,
                                      body_dy=-4, foot_l=(-2, -3),
                                      foot_r=(2, -3))),
            (0.7, K.ease_in_out, dict(hand=(14.0, -20.0), sword_angle=10,
                                      body_dy=-1)),
            (1.0, K.ease_in_out, dict(hand=(11.0, -17.0), sword_angle=70,
                                      body_dy=0)),
        ])
    else:
        track = K.Track([
            (0.00, None, dict(hand=(11.0, -18.0), sword_angle=75, body_dy=0)),
            (0.25, K.ease_in_out, dict(hand=(10.0, -20.0), sword_angle=90,
                                       body_dy=-2, crouch=0.2)),
            (0.45, K.ease_in_out, dict(body_dy=-8, foot_l=(-3, -4),
                                       foot_r=(3, -4), hand=(11.0, -22.0),
                                       sword_angle=-90)),
            (0.6, K.ease_in_out, dict(body_dy=2, foot_l=(0, 0),
                                      foot_r=(0, 0), hand=(13.0, -14.0),
                                      sword_angle=80, crouch=0.7)),
            (0.75, K.ease_in_out, dict(body_dy=3, crouch=0.9, hand=(13.0, -13.0),
                                       sword_angle=85)),
            (1.0, K.ease_in_out, dict(body_dy=0, crouch=0, hand=(11.0, -17.0),
                                      sword_angle=75)),
        ])
    return [compose(p, **params) for params in K.bake(track, 8)]


def make_gain(p):
    track = K.Track([
        (0.00, None, dict(hand=(9.0, -16.0), sword_angle=95, show_sword=False)),
        (0.3, K.ease_in_out, dict(hand=(7.0, -22.0), sword_angle=95,
                                  show_sword=False, body_dy=-1)),
        (0.5, K.ease_in_out, dict(hand=(7.0, -26.0), sword_angle=95,
                                  show_sword=False, body_dy=-2)),
        (0.7, K.ease_in_out, dict(hand=(9.0, -22.0), sword_angle=95,
                                  show_sword=False, body_dy=-1)),
        (0.85, K.ease_in_out, dict(hand=(11.0, -18.0), sword_angle=95,
                                   show_sword=False)),
        (1.0, K.ease_in_out, dict(hand=(11.0, -17.0), sword_angle=80,
                                  show_sword=False)),
    ])
    return [compose(p, **params) for params in K.bake(track, 6)]


def save_all(p):
    os.makedirs(OUT_DIR, exist_ok=True)
    save_strip(make_idle(p), os.path.join(OUT_ANIM, "ori_idle.png"))
    save_strip(make_run(p), os.path.join(OUT_ANIM, "ori_run.png"))
    save_strip(make_jump(p), os.path.join(OUT_ANIM, "ori_jump.png"))
    save_strip(make_land(p), os.path.join(OUT_ANIM, "ori_land.png"))
    save_strip(make_dash(p), os.path.join(OUT_ANIM, "ori_dash.png"))
    for i in range(4):
        save_strip(make_attack(p, i),
                   os.path.join(OUT_ANIM, f"ori_atk{i + 1}.png"))
    for i in range(3):
        save_strip(make_heavy(p, i),
                   os.path.join(OUT_ANIM, f"ori_heavy{i + 1}.png"))
    # gain 单独（手部动作，无剑）
    save_strip(make_gain(p), os.path.join(OUT_ANIM, "ori_gain.png"))


if __name__ == "__main__":
    p = load_parts()
    save_all(p)
    print("done →", OUT_ANIM)
