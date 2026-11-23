"""为三个敌人程序化生成动画（待机 / 行走 / 攻击）。

三个敌人的战斗定位刻意不同，动画也要体现出来：

  苔团（mossling）  近战冲撞：矮胖，靠"弹跳"移动，攻击是整个人撞过来
  灯笼虫（lanternbug）飞行弹幕：悬浮，上下飘动，攻击是灯体鼓胀后喷火
  石守（stonepaw）   重甲近战：沉重，每一步都"顿"，攻击是大臂抡砸

做法与主角一致：把静态精灵拆成上下两段（身体 + 腿/悬挂物），
按帧给不同位移。**不做旋转**（像素图旋转会破坏网格）。

输出：art/enemies/frames/{name}_{anim}_{i}.png，每帧 48x48，锚点帧底中心
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clean_sprite_outline

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(ROOT, "art", "enemies", "src")
OUT_DIR = os.path.join(ROOT, "art", "enemies", "frames")

FRAME = 48
FEET_Y = 46          # 脚底位置（留 1px 余量避免贴边）


def load(name):
    p = os.path.join(SRC_DIR, f"{name}.png")
    if not os.path.exists(p):
        raise FileNotFoundError(f"缺 {p}，先跑 tools/split_enemies.py")
    return Image.open(p).convert("RGBA")


def compose(sprite, *, dx=0, dy=0, squash=0.0, stretch=0.0):
    """把精灵贴到 48x48 帧里。

    squash/stretch：用「底部固定、按比例压缩/拉伸」模拟弹跳，
    只能用整数像素行裁剪，不能用 resize（会破坏像素网格）。
    """
    dst = Image.new("RGBA", (FRAME, FRAME), (0, 0, 0, 0))
    w, h = sprite.size
    x = (FRAME - w) // 2 + dx
    y = FEET_Y - h + dy

    img = sprite
    if squash > 0:
        # 压扁：从顶部裁掉若干行，再整体下移
        cut = int(round(h * squash))
        if cut > 0 and cut < h:
            img = sprite.crop((0, cut, w, h))
            y += cut
    elif stretch > 0:
        # 拉伸：顶部补几行。
        # 注意**不能用最后一行**填充 —— 精灵最底部是地面阴影（浅灰），
        # 把它复制到顶部会变成一条灰色横条（实测就是这样翻车的）。
        # 正确做法：复制精灵**主体区的第一行**（跳过透明边缘），
        # 或者干脆留透明，让拉伸只表现为整体上移。
        extra = int(round(h * stretch))
        if extra > 0:
            img = Image.new("RGBA", (w, h + extra), (0, 0, 0, 0))
            img.paste(sprite, (0, extra))
            # 找第一个有实质不透明像素的行作为填充源
            sp = sprite.load()
            src_row = 0
            for yy in range(h):
                if any(sp[x, yy][3] > 200 for x in range(w)):
                    src_row = yy
                    break
            fill = sprite.crop((0, src_row, w, src_row + 1))
            for i in range(extra):
                img.paste(fill, (0, extra - 1 - i))
            y -= extra

    dst.alpha_composite(img, (x, y))
    return dst


# ─────────────────────── 苔团（近战冲撞） ───────────────────────

def mossling_anims():
    s = load("mossling")
    out = {}

    # 待机：**呼吸 + 咕涌**（6 帧）
    #
    # 原来只有 4 帧、压扁 0.03（约 1px）。在 30px 高的苔团身上，
    # 1px 几乎看不出来 —— 用户反馈"静止状态也要有待机动作"，
    # 说明原来的幅度等于没有。
    #
    # 现在做成两段呼吸循环：吸气鼓起（拉高）、呼气压扁，
    # 并在中间加一次轻微的左右咕涌，让它像一团活着的黏液。
    # **圆形身体只用 squash，不用 stretch**。
    # stretch 是"向上补像素"，用在球体上会变成椭球（像被拉长），
    # 而不是"吸气鼓起"。对一团黏液来说，鼓起来=横向变宽，
    # 也就是**压扁**（squash 让高度减少、宽度不变，视觉上更圆更扁）。
    idle = []
    specs = [
        # (squash, dy, dx)
        (0.00, 0, 0),      # 静
        (0.00, -1, 0),     # 微微上浮（呼吸的"吸"）
        (0.00, -1, 0),     # 顶上稍停，制造节奏
        (0.07, 1, 1),      # 呼气下沉 + 压扁 + 右咕涌
        (0.11, 2, 0),      # 压到最扁
        (0.04, 0, -1),     # 回弹 + 向左轻晃
    ]
    for sq, dy, dx in specs:
        idle.append(compose(s, squash=sq, dy=dy, dx=dx))
    out["idle"] = idle

    # 行走：弹跳移动（压扁 → 拉起 → 落下）
    # 苔团是靠身体弹跳前进的，所以用 squash/stretch 而不是腿位移
    run = []
    frames = [
        (0.0, 0.0, 0),      # 落地
        (0.10, 0.0, -1),    # 压扁蓄力
        (0.0, 0.12, -4),    # 弹起
        (0.0, 0.0, -2),     # 空中
        (0.0, 0.0, 0),      # 落地
        (0.06, 0.0, 0),     # 轻压
    ]
    for sq, st, dy in frames:
        run.append(compose(s, squash=sq, stretch=st, dy=dy))
    out["run"] = run

    # 攻击：向后缩 → 猛扑（整体前冲 + 拉伸）
    atk = []
    atk.append(compose(s, dx=-3, squash=0.08))      # 后缩蓄力
    atk.append(compose(s, dx=-4, squash=0.12))      # 压到最扁
    atk.append(compose(s, dx=4, stretch=0.15, dy=-2))   # 猛扑
    atk.append(compose(s, dx=7, stretch=0.08, dy=-1))   # 冲到头
    atk.append(compose(s, dx=5, dy=0))              # 收
    atk.append(compose(s, dx=2))                    # 回位
    out["attack"] = atk

    # 硬直：被击中瞬间向上弹起 + 压扁，然后回落
    # 三帧足够表达「被打飞→疼→站稳」，再多会拖慢战斗节奏
    hurt = []
    hurt.append(compose(s, dy=-3, squash=0.10, dx=-2))   # 被打飞，身体缩
    hurt.append(compose(s, dy=-1, squash=0.05, dx=-3))   # 回落
    hurt.append(compose(s, dy=0, squash=0.02, dx=-2))    # 站稳
    out["hurt"] = hurt

    return out


# ─────────────────────── 灯笼虫（飞行弹幕） ───────────────────────

def lanternbug_anims():
    s = load("lanternbug")
    out = {}

    # 待机：**悬浮 + 摇曳**（6 帧）
    #
    # 原来是 4 帧、上下 2px，看不出"飘"的感觉。
    # 灯笼是悬挂物，待机应该像被风轻轻推着：上下浮动 + 左右摆。
    idle = []
    specs2 = [
        # (dy, dx, squash)
        (0, 0, 0.00),
        (-2, 1, 0.00),     # 上浮 + 右摆
        (-4, 2, 0.00),     # 浮到最高
        (-3, 1, -0.03),    # 顶点稍停
        (-1, -1, 0.00),    # 下落 + 回摆
        (0, -1, 0.02),     # 落回最低，灯体微微一沉
    ]
    for dy, dx, sq in specs2:
        idle.append(compose(s, dy=dy, dx=dx, squash=sq))
    out["idle"] = idle

    # 行走（飞行）：水平飘 + 轻微上下
    run = []
    for dx, dy in [(0, 0), (1, -1), (2, -2), (1, -1),
                   (0, 0), (-1, -1), (-2, -2), (-1, -1)]:
        run.append(compose(s, dx=dx, dy=dy))
    out["run"] = run

    # 攻击：鼓胀蓄力 → 前倾喷火
    atk = []
    atk.append(compose(s, dy=-1, stretch=0.04))     # 微胀
    atk.append(compose(s, dy=-2, stretch=0.10))     # 鼓满
    atk.append(compose(s, dy=-2, stretch=0.12, dx=1))   # 顶点
    atk.append(compose(s, dy=0, squash=0.06, dx=2))     # 喷出
    atk.append(compose(s, dy=0, dx=1))              # 余韵
    atk.append(compose(s, dy=-1))                   # 回位
    out["attack"] = atk

    # 硬直：灯体被击退，往反方向荡开再回正（悬挂物会先晃）
    hurt = []
    hurt.append(compose(s, dx=-4, dy=-1, squash=0.06))   # 被击退
    hurt.append(compose(s, dx=-2, dy=0, stretch=0.04))   # 回摆
    hurt.append(compose(s, dx=0, dy=0))                  # 归位
    out["hurt"] = hurt

    return out


# ─────────────────────── 石守（重甲近战） ───────────────────────

def stonepaw_anims():
    s = load("stonepaw")
    out = {}

    # 待机：**沉重的呼吸**（8 帧，最慢）
    #
    # 原设计"几乎不动（石头感）"只有 4 帧、1px —— 意图是对的
    # （石守应该显得笨重），但幅度小到读不出来，看起来就是静止的贴图。
    #
    # 改成"慢而明显"：呼吸周期更长（8 帧），幅度 3px，
    # 加一点肩部起伏的拉伸。**重不是不动，是动得慢。**
    idle = []
    # 石守是块状身体，stretch 同样会破坏轮廓（变成细长条），
    # 用**轻微压扁 + 整体抬升**表达沉重呼吸。
    specs3 = [
        # (dy, dx, squash)
        (0, 0, 0.00),      # 静
        (0, 0, 0.00),      # 停顿（迟滞感）
        (-1, 0, 0.00),     # 开始吸气
        (-2, 0, 0.00),     # 吸到一半
        (-3, 0, 0.00),     # 吸满：整体抬升
        (-2, 0, 0.00),     # 呼气开始
        (-1, 0, 0.03),     # 下沉 + 微压
        (0, 0, 0.06),      # 落回，压得最扁
    ]
    for dy, dx, sq in specs3:
        idle.append(compose(s, dy=dy, dx=dx, squash=sq))
    out["idle"] = idle

    # 行走：沉重的步伐，每步都往下顿一下
    run = []
    for dx, dy, sq in [(0, 0, 0.0), (1, 1, 0.03), (2, 0, 0.0),
                       (1, 0, 0.0), (0, 0, 0.0), (-1, 1, 0.03),
                       (-2, 0, 0.0), (-1, 0, 0.0)]:
        run.append(compose(s, dx=dx, dy=dy, squash=sq))
    out["run"] = run

    # 攻击：抬身 → 抡砸（最重的一击，有明显的前摇与下砸）
    atk = []
    atk.append(compose(s, dx=-2, dy=-1))            # 后仰起手
    atk.append(compose(s, dx=-3, dy=-3, stretch=0.06))   # 抬到最高
    atk.append(compose(s, dx=-3, dy=-4, stretch=0.08))   # 顶点
    atk.append(compose(s, dx=3, dy=2, squash=0.10))      # 砸下
    atk.append(compose(s, dx=5, dy=3, squash=0.14))      # 砸到最低
    atk.append(compose(s, dx=4, dy=1, squash=0.06))      # 余震
    atk.append(compose(s, dx=2))                    # 回位
    out["attack"] = atk

    # 硬直：石守很重，被打时只是整体后错一格 + 轻微下沉，
    # 不做弹跳（那会显得太轻，与"重甲"设定冲突）
    hurt = []
    hurt.append(compose(s, dx=-4, dy=1, squash=0.04))    # 后错下沉
    hurt.append(compose(s, dx=-3, dy=0, squash=0.02))    # 稳住
    hurt.append(compose(s, dx=-2, dy=0))                 # 归位
    out["hurt"] = hurt

    return out


# ─────────────────────────── 输出 ───────────────────────────

BUILDERS = {
    "mossling": mossling_anims,
    "lanternbug": lanternbug_anims,
    "stonepaw": stonepaw_anims,
}


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    for name, fn in BUILDERS.items():
        anims = fn()
        for anim_name, frames in anims.items():
            for i, f in enumerate(frames):
                path = os.path.join(OUT_DIR, f"{name}_{anim_name}_{i}.png")
                f.save(path)
                # 输出后立即清白边 + 重描 2px 轮廓。
                # AI 素材抠图后在轮廓上残留亮像素（实测苔团 15%、石守 7%），
                # 在深色背景上很明显。放在这里保证每次重跑都生效。
                clean_sprite_outline.clean_one(path, outline_width=2)
            print(f"{name}/{anim_name}: {len(frames)} 帧")
    total = len([f for f in os.listdir(OUT_DIR) if f.endswith(".png")])
    print(f"共 {total} 帧 -> art/enemies/frames/")


if __name__ == "__main__":
    main()
