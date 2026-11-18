"""生成角色动画（v2）：四段攻击各有独立动作。

## 为什么要重写

v1 的四个连段只是「身体倾斜角度略微不同」，观感完全一样。根因有两个：

1. **剑没有被画出来**。v1 把整个下半身（含垂在身侧的剑）当成「腿部」段
   来摆位，剑被埋在腿里、随腿一起动，等于消失了。没有武器就没有挥砍感。
2. 四段共用同一套 compose 参数，只有 ±1px 的位移差别。

## v2 的做法

把部件拆成：头+躯干 / 左腿 / 右腿 / **剑（可任意旋转）**。
四段按真实动作设计：

  第1段 上挑   —— 剑从下往上撩，身体后仰，收势时前压
  第2段 横斩   —— 剑水平横扫，身体扭转，重心前移
  第3段 突刺   —— 剑直刺前方，身体极度前倾，后腿蹬直
  第4段 下劈   —— 剑从头顶劈落，身体下压，双膝微屈

每段 4 帧：预备 → 加速 → 命中(剑最伸展) → 收势。

## 输入 / 输出

输入 art/characters/ori/parts/ 下的部件（由 tools/split_parts.py 生成）
输出 art/characters/ori/ori_*.png 横排图集，每帧 48x48，锚点帧底中心
"""

import math
import os

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARTS = os.path.join(ROOT, "art", "characters", "ori", "parts")
OUT_DIR = os.path.join(ROOT, "art", "characters", "ori")

FRAME_W = 48
FRAME_H = 48

# 部件在源图中的水平基准（28 宽居中）
SRC_W = 28


def load_parts():
    def op(name):
        p = os.path.join(PARTS, name)
        if not os.path.exists(p):
            raise FileNotFoundError(
                f"缺部件 {p}，先跑 tools/split_parts.py")
        return Image.open(p).convert("RGBA")

    return {
        "upper": op("upper.png"),
        "leg_l": op("leg_l.png"),
        "leg_r": op("leg_r.png"),
        "sword": op("sword.png"),
    }


def rtrim(img):
    """裁掉右侧透明列（骨架姿势差异时用）。"""
    bbox = img.getbbox()
    return img if bbox is None else img.crop(bbox)


def place(frame, part, x, y):
    if part is None or part.width == 0 or part.height == 0:
        return
    frame.alpha_composite(part, (int(x), int(y)))


def rotate_sword(sword, angle_deg, facing):
    """把剑旋转到指定角度，返回 (图像, 握把在图像内的坐标)。

    angle_deg：0 = 剑尖朝右（正前方），-90 = 朝上，90 = 朝下。
    facing=-1 时水平镜像。

    **关键**：不裁掉旋转后的透明边。
    若裁到紧包围盒，就再也无法知道「剑柄端」落在图里哪个像素，
    剑会浮在手的旁边（v2 前两版正是这个毛病）。
    这里保留完整方形画布，并用数学算回握把坐标。
    """
    from math import cos, radians, sin

    # 画布边长取对角线，保证任意角度都不切掉剑尖
    diag = int(math.ceil(math.hypot(sword.width, sword.height))) + 4
    canvas = Image.new("RGBA", (diag, diag), (0, 0, 0, 0))

    # 把剑的**中心**对齐到画布中心（PIL rotate 以画布中心为轴）。
    # 用 (diag - w)//2 会让中心偏移半个像素，旋转后握把坐标随之漂移，
    # 表现为剑柄和手之间有空隙。
    cx = diag * 0.5
    cy = diag * 0.5
    ox = cx - sword.width * 0.5
    oy = cy - sword.height * 0.5
    canvas.alpha_composite(sword, (int(round(ox)), int(round(oy))))

    # 握把在未旋转画布中的精确位置（剑的左端中点）
    grip_x = ox
    grip_y = oy + sword.height * 0.5

    # PIL rotate 逆时针为正；屏幕 y 向下，所以传 -angle
    rot = canvas.rotate(-angle_deg, resample=Image.NEAREST, expand=False)

    # 算回握把旋转后的坐标（绕画布中心旋转）
    rad = radians(angle_deg)
    dx = grip_x - cx
    dy = grip_y - cy
    # 屏幕坐标下顺时针旋转 angle
    nx = cx + dx * cos(rad) - dy * sin(rad)
    ny = cy + dx * sin(rad) + dy * cos(rad)

    if facing < 0:
        rot = rot.transpose(Image.FLIP_LEFT_RIGHT)
        nx = diag - nx

    return rot, (nx, ny)


def compose(parts, *,
            body_dy=0,      # 整体上下偏移
            upper_dx=0,     # 头+躯干水平偏移
            upper_dy=0,     # 头+躯干额外上下
            ll_dx=0, ll_dy=0,
            rl_dx=0, rl_dy=0,
            sword_angle=-40.0,     # 剑的角度（0=前方，-90=上，90=下）
            sword_hand=(14, -20),  # 握剑点（相对帧底中心，y 向上为负）
            facing=1):
    """按参数合成一帧。锚点：帧底中心。

    绘制顺序：腿 → 头+躯干 → 剑。
    剑最后画，保证始终压在身体之上、不被头发/衣服遮住
    （v2 早期版本剑被画在躯干之前，举过头顶时被头发挡掉了）。
    """
    frame = Image.new("RGBA", (FRAME_W, FRAME_H), (0, 0, 0, 0))
    base_x = (FRAME_W - SRC_W) // 2

    # 腿：底边贴帧底。
    # body_dy 必须同时作用于腿，否则「整体上下偏移」只有上半身在动，
    # 头和腿之间会裂开一道缝（v2 早期版本正是这个 bug：
    # 第 1 段命中帧用了 body_dy=2，结果上身上抬、腿不动，断成两截）。
    leg_l, leg_r = parts["leg_l"], parts["leg_r"]
    place(frame, leg_l, base_x + 5 + ll_dx,
          FRAME_H - leg_l.height + ll_dy + body_dy)
    place(frame, leg_r, base_x + 14 + rl_dx,
          FRAME_H - leg_r.height + rl_dy + body_dy)

    # 头+躯干
    upper = parts["upper"]
    place(frame, upper, base_x + upper_dx,
          FRAME_H - 10 - upper.height + body_dy + upper_dy)

    # 剑：以握剑点为轴心。
    # rotate_sword 返回握把在旋转后图像内的精确坐标，
    # 把那个坐标对齐到握剑点即可，不再靠包围盒猜（猜会导致剑浮在手的旁边）。
    sw, (gx, gy) = rotate_sword(parts["sword"], sword_angle, facing)
    hx = base_x + SRC_W * 0.5 + sword_hand[0] * facing
    hy = FRAME_H + sword_hand[1] + body_dy
    place(frame, sw, hx - gx, hy - gy)

    return frame


# ─────────────────────────── 基础动作 ───────────────────────────

def make_idle(parts):
    frames = []
    for dy, dx in [(0, 0), (-1, 1), (0, 0), (-1, -1)]:
        frames.append(compose(parts, body_dy=dy, upper_dx=dx,
                              sword_angle=75.0, sword_hand=(6, -18)))
    return frames


def make_run(parts):
    specs = [
        (-1, 1, (4, -1), (-3, 0)),
        (0, 1, (2, 0), (-1, 0)),
        (0, 0, (0, 0), (0, 0)),
        (-1, -1, (-3, 0), (4, -1)),
        (0, -1, (-1, 0), (2, 0)),
        (0, 0, (0, 0), (0, 0)),
    ]
    return [compose(parts, body_dy=d[0], upper_dx=d[1],
                    ll_dx=d[2][0], ll_dy=d[2][1],
                    rl_dx=d[3][0], rl_dy=d[3][1],
                    sword_angle=70.0, sword_hand=(6, -18))
            for d in specs]


def make_jump(parts):
    specs = [
        dict(body_dy=-1, ll_dy=-2, rl_dy=-2, sword_angle=40.0),
        dict(body_dy=0, ll_dx=-3, rl_dx=3, sword_angle=20.0),
        dict(body_dy=0, ll_dx=-1, rl_dx=2, sword_angle=60.0),
    ]
    return [compose(parts, sword_hand=(6, -20), **s) for s in specs]


def make_land(parts):
    return [
        compose(parts, body_dy=2, ll_dx=-1, rl_dx=1,
                sword_angle=80.0, sword_hand=(6, -16)),
        compose(parts, body_dy=0, ll_dx=0, rl_dx=0,
                sword_angle=75.0, sword_hand=(6, -18)),
    ]


def make_dash(parts):
    return [
        compose(parts, body_dy=1, upper_dx=-2, ll_dx=-3, rl_dx=2,
                sword_angle=-10.0, sword_hand=(5, -22)),
        compose(parts, body_dy=-1, upper_dx=3, ll_dx=-5, rl_dy=-1,
                rl_dx=5, sword_angle=0.0, sword_hand=(12, -24)),
        compose(parts, body_dy=0, upper_dx=1, ll_dx=-2, rl_dx=3,
                sword_angle=20.0, sword_hand=(6, -22)),
    ]


# ─────────────────────── 四段攻击（核心） ───────────────────────

def make_attack(parts, idx):
    """四段攻击，每段 4 帧，动作设计完全不同。

    帧序列：预备 → 加速 → 命中(剑最伸展) → 收势
    """
    if idx == 0:
        return _attack_uppercut(parts)
    if idx == 1:
        return _attack_sideslash(parts)
    if idx == 2:
        return _attack_thrust(parts)
    return _attack_overhead(parts)


def _attack_uppercut(parts):
    """第1段 上挑：剑从下往上撩起，身体先沉后仰。

    剑角度：90(朝下) → 40 → -50(朝上) → -20
    身体：先下沉蓄力，命中瞬间整体上抬、后仰。
    """
    frames = []
    # 帧0 预备：重心下沉，剑垂在下方
    frames.append(compose(parts, body_dy=2, upper_dx=-2,
                          ll_dx=-2, rl_dx=2,
                          sword_angle=95.0, sword_hand=(7, -14)))
    # 帧1 加速：开始上撩，剑到身前
    frames.append(compose(parts, body_dy=1, upper_dx=-1,
                          ll_dx=-2, rl_dx=2,
                          sword_angle=45.0, sword_hand=(12, -18)))
    # 帧2 命中：剑挥到头顶上方，身体上抬后仰
    frames.append(compose(parts, body_dy=0, upper_dx=1, upper_dy=-2,
                          ll_dx=-1, rl_dx=1,
                          sword_angle=-55.0, sword_hand=(8, -24)))
    # 帧3 收势：剑落回身前
    frames.append(compose(parts, body_dy=0, upper_dx=1,
                          ll_dx=-1, rl_dx=1,
                          sword_angle=-15.0, sword_hand=(7, -21)))
    return frames


def _attack_sideslash(parts):
    """第2段 横斩：剑水平横扫，身体扭转，重心前移。

    剑角度：-15(略上) → 0(水平) → 10 → 25
    身体：上身明显前倾，前后腿张开（弓步）。
    """
    frames = []
    # 帧0 预备：扭腰蓄力，剑收在身后
    frames.append(compose(parts, body_dy=1, upper_dx=-3,
                          ll_dx=-3, rl_dx=3,
                          sword_angle=-20.0, sword_hand=(6, -20)))
    # 帧1 加速：剑开始扫出
    frames.append(compose(parts, body_dy=0, upper_dx=-1,
                          ll_dx=-3, rl_dx=3,
                          sword_angle=-5.0, sword_hand=(6, -20)))
    # 帧2 命中：剑完全水平伸展，身体前压到最大
    frames.append(compose(parts, body_dy=1, upper_dx=3,
                          ll_dx=-4, rl_dx=4,
                          sword_angle=5.0, sword_hand=(14, -20)))
    # 帧3 收势：剑略下垂，身体回正
    frames.append(compose(parts, body_dy=0, upper_dx=2,
                          ll_dx=-2, rl_dx=2,
                          sword_angle=30.0, sword_hand=(8, -18)))
    return frames


def _attack_thrust(parts):
    """第3段 突刺：剑直刺正前方，身体极度前倾，后腿蹬直。

    剑角度：-25 → -8 → 0（完全水平前指）→ -15
    与其他三段的区别靠三件事叠出来：
      1. 上身水平前移最多（upper_dx 0→8）
      2. 双腿前后张到最大（-6 / +6），形成弓步
      3. 握剑点前伸到 19px，剑身几乎完全伸出体侧
    """
    frames = []
    # 帧0 预备：重心后坐，剑收到身侧
    frames.append(compose(parts, body_dy=1, upper_dx=-5,
                          ll_dx=-3, rl_dx=3,
                          sword_angle=-25.0, sword_hand=(3, -19)))
    # 帧1 加速：身体开始前送
    frames.append(compose(parts, body_dy=0, upper_dx=1,
                          ll_dx=-4, rl_dx=4,
                          sword_angle=-8.0, sword_hand=(11, -19)))
    # 帧2 命中：弓步张到最大 + 剑水平直刺
    # 说明：48px 帧宽、角色占 28px，剑长 20px —— 直刺时不可能整把伸出体侧，
    # 最多露出约 14px。这是分辨率决定的物理上限，靠刀光补足「刺出去」的观感。
    frames.append(compose(parts, body_dy=0, upper_dx=4, upper_dy=2,
                          ll_dx=-6, rl_dx=6,
                          sword_angle=0.0, sword_hand=(6, -19)))
    # 帧3 收势：身体回撤
    frames.append(compose(parts, body_dy=0, upper_dx=3,
                          ll_dx=-4, rl_dx=4,
                          sword_angle=-15.0, sword_hand=(7, -19)))
    return frames


def _attack_overhead(parts):
    """第4段 下劈：剑从头顶劈落，身体下压、双膝微屈。

    剑角度：-110(举过头顶) → -70 → 80(劈到地面方向) → 100
    身体：先上举蓄力，命中瞬间整体下压 3px。
    """
    frames = []
    # 帧0 预备：举剑过头，身体微微上抬
    frames.append(compose(parts, body_dy=-1, upper_dx=-1,
                          ll_dx=-2, rl_dx=2,
                          sword_angle=-105.0, sword_hand=(13, -26)))
    # 帧1 加速：剑开始下落
    frames.append(compose(parts, body_dy=-1, upper_dx=0,
                          ll_dx=-2, rl_dx=2,
                          sword_angle=-60.0, sword_hand=(12, -25)))
    # 帧2 命中：剑劈到身前下方，身体下压
    frames.append(compose(parts, body_dy=3, upper_dx=2,
                          ll_dx=-3, rl_dx=3,
                          sword_angle=75.0, sword_hand=(8, -17)))
    # 帧3 收势：剑低垂，身体略起
    frames.append(compose(parts, body_dy=2, upper_dx=1,
                          ll_dx=-2, rl_dx=2,
                          sword_angle=95.0, sword_hand=(7, -15)))
    return frames


# ─────────────────────────── 输出 ───────────────────────────

def save_strip(frames, path):
    strip = Image.new("RGBA", (FRAME_W * len(frames), FRAME_H), (0, 0, 0, 0))
    for i, f in enumerate(frames):
        strip.alpha_composite(f, (i * FRAME_W, 0))
    strip.save(path)
    print(f"wrote {os.path.basename(path)} "
          f"({strip.width}x{strip.height}, {len(frames)} frames)")


def main():
    parts = load_parts()
    print("parts: " + ", ".join(f"{k}={v.size}" for k, v in parts.items()))

    save_strip(make_idle(parts), os.path.join(OUT_DIR, "ori_idle.png"))
    save_strip(make_run(parts), os.path.join(OUT_DIR, "ori_run.png"))
    save_strip(make_jump(parts), os.path.join(OUT_DIR, "ori_jump.png"))
    save_strip(make_land(parts), os.path.join(OUT_DIR, "ori_land.png"))
    save_strip(make_dash(parts), os.path.join(OUT_DIR, "ori_dash.png"))

    for i in range(4):
        save_strip(make_attack(parts, i),
                   os.path.join(OUT_DIR, f"ori_atk{i + 1}.png"))


if __name__ == "__main__":
    main()
