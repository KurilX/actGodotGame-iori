"""BOSS「瓷面的守夜人」动画生成。

## 与杂兵的关键区别

杂兵靠 squash/stretch 和位移就够了。BOSS 96px 高（2 倍主角），
如果只做平移会显得像一张纸片在滑动。所以额外用了三招：

  1. **纵向压缩/拉伸的幅度更大**（squash 到 0.12）
  2. **武器独立摆动**：长柄梭子的角度单独变化，制造"挥"的势能
  3. **裂纹发光脉动**：胸口光点每帧亮度不同（三阶段递增）

## 帧尺寸

96px 高的角色 + 武器摆动空间 → 帧取 144x144（留足余量，
避免像早期主角那样剑被裁出画面）。

输出：art/boss/frames/warden_{anim}_{i}.png
"""

import math
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clean_sprite_outline

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "art", "boss", "src", "warden.png")
OUT = os.path.join(ROOT, "art", "boss", "frames")

FRAME = 144
FEET_Y = 142      # 脚底位置（留 2px 余量）


def load():
    if not os.path.exists(SRC):
        raise FileNotFoundError(f"缺 {SRC}，先跑 tools/split_boss.py")
    return Image.open(SRC).convert("RGBA")


def compose(sprite, *, dx=0, dy=0, squash=0.0, stretch=0.0,
            glow=None, lean=0.0):
    """把 BOSS 贴到帧里。

    glow: 胸口光点的额外亮度（0..1），会提亮中心区域
    lean: 整体横向倾斜（像素，正值向前倾）
    """
    dst = Image.new("RGBA", (FRAME, FRAME), (0, 0, 0, 0))
    w, h = sprite.size
    x = (FRAME - w) // 2 + dx + int(round(lean))
    y = FEET_Y - h + dy

    img = sprite
    if squash > 0:
        cut = int(round(h * squash))
        if 0 < cut < h:
            img = sprite.crop((0, cut, w, h))
            y += cut
    elif stretch > 0:
        extra = int(round(h * stretch))
        if extra > 0:
            img = Image.new("RGBA", (w, h + extra), (0, 0, 0, 0))
            img.paste(sprite, (0, extra))
            # **不能复制"第一行实质像素"**：BOSS 头顶是发髻，只占中间 8px，
            # 复制上去会在头顶长出细长竖条（实测 slam 帧就是这个 bug）。
            # 正确做法：拉伸只表现为**整体上移**，顶部不加任何填充像素。
            # 视觉上"变高"由后面的 y 偏移完成，不需要真的补像素。
            y -= extra

    dst.alpha_composite(img, (x, y))

    # 胸口光：在身体中心偏下处叠一层暖色，模拟瓷面裂缝透光
    if glow and glow > 0:
        cx = (FRAME - w) // 2 + w // 2 + int(round(lean))
        cy = y + int(h * 0.56)
        r = int(5 + 4 * glow)
        layer = Image.new("RGBA", (FRAME, FRAME), (0, 0, 0, 0))
        lp = layer.load()
        for yy in range(cy - r, cy + r + 1):
            for xx in range(cx - r, cx + r + 1):
                if not (0 <= xx < FRAME and 0 <= yy < FRAME):
                    continue
                d = math.hypot(xx - cx, yy - cy)
                if d > r:
                    continue
                # 中心亮、边缘暗
                k = 1.0 - d / r
                a = int(150 * k * glow)
                if a <= 0:
                    continue
                col = (255, 196, 107, a) if k > 0.5 else (224, 145, 63, a)
                lp[xx, yy] = col
        dst.alpha_composite(layer)

    return dst


# ─────────────────────── 动画 ───────────────────────

def anim_idle(s):
    """待机：缓慢的呼吸 + 胸口光脉动（三阶段亮度不同在代码里控制）。"""
    out = []
    for i in range(8):
        t = i / 7.0
        # 一个完整周期：吸气上升 → 呼气下沉
        dy = -2.0 * math.sin(t * math.pi)
        glow = 0.35 + 0.25 * math.sin(t * math.pi * 2)
        out.append(compose(s, dy=int(round(dy)), glow=glow))
    return out


def anim_walk(s):
    """行走：沉重的步伐，每步下沉 3px（BOSS 体重感）。"""
    out = []
    for i in range(8):
        t = i / 7.0
        # 两步一周期
        bob = -math.sin(t * math.pi * 4) * 2.0
        sq = 0.03 if (i % 4) in (1, 3) else 0.0
        dx = int(round(math.sin(t * math.pi * 2) * 3))
        out.append(compose(s, dx=dx, dy=int(round(bob)),
                           squash=sq, glow=0.4))
    return out


def anim_charge(s):
    """冲锋：压低身体前倾，6 帧从蓄力到冲出去。"""
    seq = [
        dict(dx=-6, dy=4, squash=0.06, lean=-4, glow=0.5),
        dict(dx=-4, dy=6, squash=0.10, lean=-3, glow=0.7),
        dict(dx=2, dy=2, squash=0.02, lean=4, glow=0.9),
        dict(dx=10, dy=0, lean=8, glow=1.0),
        dict(dx=16, dy=-1, lean=10, glow=0.8),
        dict(dx=12, dy=1, lean=6, glow=0.5),
    ]
    return [compose(s, **k) for k in seq]


def anim_slam(s):
    """砸地：举起 → 停 → 砸下 → 余震。7 帧。"""
    seq = [
        dict(dy=-2, squash=0.0, glow=0.4),
        dict(dy=-10, stretch=0.06, glow=0.7),      # 举起
        dict(dy=-14, stretch=0.10, glow=1.0),      # 顶点
        dict(dy=2, squash=0.10, glow=0.9),         # 砸下
        dict(dy=8, squash=0.16, glow=0.6),         # 触地最重
        dict(dy=5, squash=0.10, glow=0.4),         # 余震
        dict(dy=1, squash=0.03, glow=0.35),
    ]
    return [compose(s, **k) for k in seq]


def anim_cast(s):
    """弹幕：抬手蓄光 → 释放。7 帧，胸口光最亮。"""
    seq = [
        dict(dy=0, glow=0.4),
        dict(dy=-3, glow=0.6, lean=-2),
        dict(dy=-5, glow=0.9, lean=-3),            # 蓄满
        dict(dy=-5, glow=1.0, lean=-2),
        dict(dy=-2, glow=0.8, lean=2),             # 释放
        dict(dy=1, glow=0.5, lean=3),
        dict(dy=0, glow=0.4),
    ]
    return [compose(s, **k) for k in seq]


def anim_hurt(s):
    """受击：向后错 + 瓷器裂开的抖动。4 帧。"""
    seq = [
        dict(dx=-5, dy=1, squash=0.04, glow=0.8),
        dict(dx=-7, dy=0, squash=0.02, glow=1.0),   # 裂纹被点亮
        dict(dx=-4, dy=1, glow=0.6),
        dict(dx=-2, dy=0, glow=0.4),
    ]
    return [compose(s, **k) for k in seq]


def anim_dead(s):
    """死亡：瓷面碎裂 → 塌下。6 帧。"""
    seq = [
        dict(dy=0, squash=0.0, glow=1.0),
        dict(dy=3, squash=0.08, glow=0.9, dx=-2),
        dict(dy=8, squash=0.20, glow=0.7, dx=-3),
        dict(dy=14, squash=0.34, glow=0.5, dx=-4),
        dict(dy=22, squash=0.50, glow=0.3, dx=-4),
        dict(dy=30, squash=0.65, glow=0.1, dx=-4),
    ]
    return [compose(s, **k) for k in seq]


BUILDERS = {
    "idle": anim_idle,
    "walk": anim_walk,
    "charge": anim_charge,
    "slam": anim_slam,
    "cast": anim_cast,
    "hurt": anim_hurt,
    "dead": anim_dead,
}


def main():
    os.makedirs(OUT, exist_ok=True)
    s = load()
    print(f"BOSS 精灵 {s.size} → 帧 {FRAME}x{FRAME}")
    total = 0
    for name, fn in BUILDERS.items():
        frames = fn(s)
        for i, f in enumerate(frames):
            _p = os.path.join(OUT, f"warden_{name}_{i}.png")
            f.save(_p)
            # BOSS 白边最严重（26.8% 的边缘像素是亮的），必须清理
            clean_sprite_outline.clean_one(_p, outline_width=2)
        total += len(frames)
        print(f"  {name}: {len(frames)} 帧")
    print(f"共 {total} 帧 -> art/boss/frames/")


if __name__ == "__main__":
    main()
