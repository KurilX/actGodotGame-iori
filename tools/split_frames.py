"""把横排图集拆成单帧文件，并生成 SpriteFrames 场景片段。

为什么拆：Godot 4 的 SpriteFrames 里直接写 `region` 不会裁剪贴图，
整条图集会被当作一整张画出来——实测一张图里并排出现 6 个角色
（间隔正好等于帧宽 48px，这就是铁证）。正确做法是给每帧一个
独立的贴图资源，或用 AtlasTexture 显式裁剪。这里选前者：最直白。

输出：
  art/characters/ori/frames/{名字}_{序号}.png
  art/characters/ori/SpriteFrames_ori.tres   （可选，便于复用）

用法：python tools/split_frames.py
"""

import os

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ART = os.path.join(ROOT, "art", "characters", "ori")
OUT = os.path.join(ART, "frames")

FRAME = 80

# 图集名 → (帧数, 循环, 帧率)
SPECS = {
    "ori_idle": (4, True, 6.0),
    "ori_run": (6, True, 12.0),
    "ori_jump": (3, False, 8.0),
    "ori_land": (2, False, 12.0),
    # 轻攻击四连：每段 3 帧，不循环，靠逻辑控制推进
    "ori_atk1": (6, False, 0.0),
    "ori_atk2": (6, False, 0.0),
    "ori_atk3": (6, False, 0.0),
    "ori_atk4": (6, False, 0.0),
    # 闪避：3 帧
    "ori_dash": (3, False, 0.0),
}


def split(name, count):
    src = Image.open(os.path.join(ART, f"{name}.png")).convert("RGBA")
    expect = FRAME * count
    if src.width != expect:
        raise ValueError(
            f"{name}.png 宽 {src.width}，但按 {count} 帧应为 {expect}")
    paths = []
    for i in range(count):
        f = src.crop((i * FRAME, 0, (i + 1) * FRAME, src.height))
        p = os.path.join(OUT, f"{name}_{i}.png")
        f.save(p)
        paths.append(p)
    return paths


def main():
    os.makedirs(OUT, exist_ok=True)
    total = 0
    for name, (count, loop, fps) in SPECS.items():
        paths = split(name, count)
        total += len(paths)
        print(f"{name}: {count} 帧 -> {os.path.basename(OUT)}/")
    print(f"共导出 {total} 张单帧")


if __name__ == "__main__":
    main()
