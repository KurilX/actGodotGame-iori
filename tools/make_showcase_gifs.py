"""生成动画展示页用的 GIF。

## 为什么要还原「不均匀帧时长」

攻击动画在游戏里不是按固定 fps 播的，而是 player.gd 里按进度阈值手动设帧：

    progress >= 0.88 -> frame 5
    progress >= 0.72 -> frame 4
    progress >= 0.42 -> frame 3   ← 命中帧，停留最久
    progress >= 0.26 -> frame 2
    progress >= 0.12 -> frame 1
    else              -> frame 0

所以每帧的停留时间差很多（命中帧占 30% 时长，起手帧只占 12%）。
如果用固定 fps 导出 GIF，动作会变成匀速，打击感全没了。

这里按真实的进度阈值反算每帧时长，再交给 GIF 编码。

## 刀光

攻击的刀光由世界层单独绘制（slash_sprite.gd），不在角色帧里。
为了让展示更接近实际观感，这里在命中窗口把刀光贴图合成到角色帧上。
对齐方式：角色帧 80×80、脚底 y=79、中轴 x=40；刀光弧心在角色身前 4px、
躯干高度 -22px 处，所以弧心 = (44, 57)，贴图 64×64 居中 → 左上角 (12, 25)。

输出：docs/gifs/*.gif
"""

import os

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRAMES = os.path.join(ROOT, "art", "characters", "ori", "frames")
SLASH = os.path.join(ROOT, "art", "fx", "slash")
OUT = os.path.join(ROOT, "docs", "gifs")

FRAME = 80
SCALE = 3
BG = (18, 20, 42)              # 与游戏 default_clear_color 一致

# 攻击动画的进度阈值（与 player.gd 的 _animate_attack 完全一致）
ATTACK_THRESHOLDS = [0.88, 0.72, 0.42, 0.26, 0.12]
HEAVY_THRESHOLDS = [0.90, 0.78, 0.62, 0.40, 0.28, 0.18, 0.08]

# 攻击段时长（与 player.gd 的 COMBO / HEAVY_COMBO 一致）
LIGHT_DUR = [0.24, 0.22, 0.30, 0.36]
HEAVY_DUR = [0.55, 0.62, 0.85]

# 刀光弧心在 80x80 帧内的位置
SLASH_CX, SLASH_CY = 44, 57


def load(name, i):
    p = os.path.join(FRAMES, f"ori_{name}_{i}.png")
    if not os.path.exists(p):
        raise FileNotFoundError(p)
    return Image.open(p).convert("RGBA")


def load_slash(prefix, seg, i):
    p = os.path.join(SLASH, f"{prefix}{seg}_{i}.png")
    if not os.path.exists(p):
        return None
    return Image.open(p).convert("RGBA")


def flatten(img):
    """铺到不透明背景上（GIF 不支持 alpha 渐变）。"""
    bg = Image.new("RGBA", img.size, BG + (255,))
    bg.alpha_composite(img)
    return bg.convert("RGB")


def with_slash(frame, slash):
    """把刀光合成到帧上。"""
    if slash is None:
        return frame
    out = frame.copy()
    x = SLASH_CX - slash.width // 2
    y = SLASH_CY - slash.height // 2
    out.alpha_composite(slash, (x, y))
    return out


def durations_from_thresholds(thresholds, total_dur):
    """按进度阈值反算每帧时长（毫秒）。

    thresholds 是降序的百分比：progress >= t 时进入更高的帧号。
    例如 [0.88, 0.72, 0.42, 0.26, 0.12]：
      帧0 占 0    ~ 0.12  -> 12%
      帧1 占 0.12 ~ 0.26  -> 14%
      帧2 占 0.26 ~ 0.42  -> 16%
      帧3 占 0.42 ~ 0.72  -> 30%  ← 命中帧，最长
      帧4 占 0.72 ~ 0.88  -> 16%
      帧5 占 0.88 ~ 1.00  -> 12%
    """
    bounds = sorted(thresholds + [0.0, 1.0])
    ms = []
    for i in range(len(bounds) - 1):
        span = bounds[i + 1] - bounds[i]
        ms.append(max(20, int(round(span * total_dur * 1000))))
    return ms


def make_gif(frames, durations, path, loop_hold=0):
    """写 GIF。loop_hold>0 时在末尾加若干帧停留，让循环有呼吸感。"""
    if not frames:
        return
    imgs = [flatten(f).resize((FRAME * SCALE, FRAME * SCALE), Image.NEAREST)
            for f in frames]
    durs = list(durations)
    if loop_hold:
        imgs.append(imgs[-1])
        durs.append(loop_hold)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    imgs[0].save(path, save_all=True, append_images=imgs[1:],
                 duration=durs, loop=0, optimize=False, disposal=2)
    print(f"  {os.path.basename(path)}  {len(frames)} 帧  "
          f"{sum(durations)}ms")


# ─────────────────────── 各动画段的产出 ───────────────────────

def seq_simple(name, count, fps, loop_hold=0):
    frames = [load(name, i) for i in range(count)]
    ms = int(1000 / fps)
    return frames, [ms] * count, loop_hold


def seq_attack(kind, seg_index, prefix, thresholds, dur):
    """一段攻击。kind: 'atk' 或 'heavy'。"""
    name = f"{kind}{seg_index + 1}"
    count = len(thresholds) + 1
    frames = []
    for i in range(count):
        f = load(name, i)
        # 命中窗口（大约第 3、4 帧）叠刀光
        if i in (2, 3):
            slash = load_slash(prefix, seg_index + 1, min(i - 2, 2))
            f = with_slash(f, slash)
        frames.append(f)
    ms = durations_from_thresholds(thresholds, dur)
    return frames, ms, 0


def seq_combo(kind, prefix, thresholds, durs, seg_count):
    """连续多段攻击，拼成一条 GIF 展示连段推进。"""
    frames, ms = [], []
    for s in range(seg_count):
        f, m, _ = seq_attack(kind, s, prefix, thresholds, durs[s])
        frames.extend(f)
        ms.extend(m)
    return frames, ms, 600        # 连段打完停 0.6s 再循环


def seq_jump_land():
    """跳跃 → 落地 的完整流程。

    jump 是上升段的 3 帧；land 是触地后的 6 帧屈膝缓冲。
    中间那个"最高点"用 jump 的最后一帧多停一会来体现滞空。
    """
    frames, ms = [], []
    for i in range(3):
        frames.append(load("jump", i))
        ms.append(140 if i < 2 else 220)      # 到顶点后滞空久一点
    for i in range(6):
        frames.append(load("land", i))
        # 落地前两帧压得最深，停留稍长才有"砸下去"的重量
        ms.append(90 if i < 2 else 70)
    return frames, ms, 400


def main():
    os.makedirs(OUT, exist_ok=True)
    print("生成 GIF：")

    # 待机与移动
    f, m, h = seq_simple("idle", 8, 8.0)
    make_gif(f, m, os.path.join(OUT, "01_idle.gif"), h)
    f, m, h = seq_simple("run", 8, 12.0)
    make_gif(f, m, os.path.join(OUT, "02_run.gif"), h)

    # 跳跃落地流程
    f, m, h = seq_jump_land()
    make_gif(f, m, os.path.join(OUT, "03_jump_land.gif"), h)

    # 闪避
    f, m, h = seq_simple("dash", 3, 15.0)
    make_gif(f, m, os.path.join(OUT, "04_dash.gif"), h)

    # 轻攻击四连（单段 + 完整连段）
    for s in range(4):
        f, m, h = seq_attack("atk", s, "seg", ATTACK_THRESHOLDS, LIGHT_DUR[s])
        make_gif(f, m, os.path.join(OUT, f"05_light_{s + 1}.gif"), 350)
    f, m, h = seq_combo("atk", "seg", ATTACK_THRESHOLDS, LIGHT_DUR, 4)
    make_gif(f, m, os.path.join(OUT, "05_light_combo.gif"), h)

    # 重攻击三连（单段 + 完整连段）
    for s in range(3):
        f, m, h = seq_attack("heavy", s, "heavy", HEAVY_THRESHOLDS, HEAVY_DUR[s])
        make_gif(f, m, os.path.join(OUT, f"06_heavy_{s + 1}.gif"), 400)
    f, m, h = seq_combo("heavy", "heavy", HEAVY_THRESHOLDS, HEAVY_DUR, 3)
    make_gif(f, m, os.path.join(OUT, "06_heavy_combo.gif"), h)

    print(f"\n输出目录：{OUT}")


if __name__ == "__main__":
    main()
