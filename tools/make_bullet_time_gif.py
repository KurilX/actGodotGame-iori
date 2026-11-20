"""录制游戏内实拍 GIF：完美闪避的子弹时间 → 空挥扣段 → 连击条变化。

## 怎么录的

不是逐帧摆姿势（那是"渲染"不是"录制"），而是：
  1. 真的让游戏跑起来
  2. 用 Input.action_press 模拟真实按键
  3. 每个渲染帧抓一张图（用 RenderingServer.frame_post_draw）
  4. 按真实时间戳算每帧的 GIF 停留时长

这样录出来的是真实游戏节奏，包括子弹时间的时间变慢。

## 关键坑

子弹时间会把 Engine.time_scale 压到 0.35，
如果用 delta 估算帧时长，整段录像会变成慢动作的慢动作。
必须用 **Time.get_ticks_msec()** 记录每帧的真实时间戳。

输出：docs/gifs/07_bullet_time.gif
"""

import os
import sys

# Godot 脚本在这里没法直接 import Python，所以录帧由 GDScript 完成，
# 本文件只负责把导出的 PNG 序列合成 GIF。

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEQ_DIR = os.path.join(ROOT, "art", "recordings", "bullet_time")
OUT = os.path.join(ROOT, "docs", "gifs", "07_bullet_time.gif")

# 输出尺寸：原帧 960x540，GIF 用 480x270（接近游戏原生分辨率 480x270）。
# 2x 会到 1920x1080、体积 2.5MB，网页上加载太慢；1x 又太小看不清特效。
SCALE_W = 480


def main():
    from PIL import Image

    if not os.path.isdir(SEQ_DIR):
        print(f"缺帧目录 {SEQ_DIR}，先跑 tools/record_bullet_time.gd")
        return 1

    files = sorted(f for f in os.listdir(SEQ_DIR) if f.endswith(".png"))
    if not files:
        print("没有帧")
        return 1

    # 每帧的时间戳写在 meta.txt 里（GDScript 导出）
    meta_path = os.path.join(SEQ_DIR, "meta.txt")
    stamps = []
    if os.path.exists(meta_path):
        with open(meta_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    stamps.append(int(line))

    imgs = []
    durs = []
    for i, fn in enumerate(files):
        im = Image.open(os.path.join(SEQ_DIR, fn)).convert("RGB")
        h = round(im.height * SCALE_W / im.width)
        im = im.resize((SCALE_W, h), Image.LANCZOS)
        # 量化到 64 色：像素画色数本来就少，64 色足够且体积小很多
        im = im.quantize(colors=64, method=Image.MEDIANCUT).convert("P")
        imgs.append(im)
        # 按真实时间戳算停留时长
        if i + 1 < len(stamps):
            d = stamps[i + 1] - stamps[i]
        else:
            d = 50
        durs.append(max(20, min(500, d)))

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    imgs[0].save(OUT, save_all=True, append_images=imgs[1:],
                 duration=durs, loop=0, optimize=False, disposal=2)

    total = sum(durs)
    print(f"{os.path.basename(OUT)}  {len(imgs)} 帧  {total}ms  "
          f"({imgs[0].width}x{imgs[0].height})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
