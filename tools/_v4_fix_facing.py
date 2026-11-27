"""修复 V4 全帧的帧间朝向不一致 + 补 jump_2。

1. 基准：V4 基底立绘面朝画面右侧，发卡（红）在角色可见侧（右半）。
   → 统一标准：所有帧的发卡必须在**画面右半**（与基底一致）。
2. 对发卡在左半的帧：水平镜像翻转（角色朝向翻转为面朝右）。
3. jump_2 补一张单独请求（跳跃下落瞬间）。
"""
import base64
import io
import json
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
KEY = (ROOT / "tools/ark_key.txt").read_text(encoding="utf-8").strip()
FRAMES = ROOT / "art/characters/ori/frames"
NEW = ROOT / "art/characters/ori/frames_v4"
BAK = ROOT / "art/characters/ori/backup_pre_v4"


def hair_card_side(p):
    a = np.array(Image.open(p).convert("RGBA"))
    vis = a[..., 3] > 127
    red = (a[..., 0] > 150) & (a[..., 1] < 110) & (a[..., 2] < 130) & vis
    if red.sum() < 5:
        return None
    xs = np.where(red.any(axis=0))[0]
    # 主体中心
    allxs = np.where(vis.any(axis=0))[0]
    mid = (allxs.min() + allxs.max()) / 2
    return "right" if xs.mean() >= mid else "left"


def main():
    fixed = []
    for p in sorted(FRAMES.glob("ori_*.png")):
        side = hair_card_side(p)
        if side is None:
            continue
        if side == "left":
            im = Image.open(p).convert("RGBA")
            im = im.transpose(Image.FLIP_LEFT_RIGHT)
            im.save(p)
            fixed.append(p.name)
    print(f"mirrored {len(fixed)} frames to face right:")
    for f in fixed:
        print("  ", f)

    # jump_2 补图
    ANCHOR = ROOT / "docs/refs/ai/ori_v4_base.jpeg"
    b64 = base64.b64encode(ANCHOR.read_bytes()).decode()
    body = {
        "model": "doubao-seedream-5-5-flash",
        "prompt": (
            "严格复刻第一张参考图中像素角色的全部风格语言：超大头 Q 版比例、"
            "大色块极简配色、黑方眼浅紫瞳、蓝紫发双马尾丸子、红发卡方格、"
            "深蓝斗篷红领结白衬衫黑短裙深色靴、方形像素构成、无渐变无抗锯齿。"
            "同一角色单一姿势：跳跃后下落瞬间（身体在空中，双膝微收，"
            "斗篷向上飘），面朝画面右侧，发卡在画面右侧。"
            "纯黑背景，全身居中"),
        "image": ["data:image/jpeg;base64," + base64.b64encode(
            io.BytesIO() and b"") .decode()] if False else [  # noqa
            "data:image/jpeg;base64," + b64],
        "response_format": "url",
        "size": "2K",
        "stream": False,
        "watermark": False,
    }
    req = urllib.request.Request(
        "https://ark.cn-beijing.volces.com/api/plan/v3/images/generations",
        data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + KEY})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            d = json.loads(r.read().decode())
        url = d["data"][0]["url"]
        data = urllib.request.urlopen(urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0"}), timeout=120).read()
        raw = NEW / "jump2_raw.jpeg"
        raw.write_bytes(data)
        print(f"jump2 generated {len(data)//1024} KB")
    except urllib.error.HTTPError as e:
        print("jump2 HTTP", e.code, e.read().decode("utf-8", "replace")[:200])
        return

    # 修帧
    im = Image.open(raw).convert("RGB")
    w, h = im.size
    w2, h2 = (w // 18) * 18, (h // 18) * 18
    cropped = im.crop(((w - w2) // 2, (h - h2) // 2,
                       (w - w2) // 2 + w2, (h - h2) // 2 + h2))
    small = cropped.resize((w2 // 18, h2 // 18), Image.NEAREST)
    aligned = small.resize((w2, h2), Image.NEAREST)

    sys.path.insert(0, str(ROOT / "artqa"))
    from artqa.palette import load_palette
    from artqa.config import repo_path
    PAL = load_palette(repo_path("art/palette.gpl"),
                       repo_path("art/palette.hex.txt"))
    pal_colors = [tuple(int(v) for v in c) for c in PAL.colors]
    INK = (18, 20, 42)

    def nearest(c):
        return min(pal_colors, key=lambda q: sum(
            (q[i] - c[i]) ** 2 for i in range(3)))

    rgba = aligned.convert("RGBA")
    a = np.array(rgba)
    bg = (a[..., 0] < 45) & (a[..., 1] < 45) & (a[..., 2] < 55)
    a[bg] = (0, 0, 0, 0)
    cim = Image.fromarray(a)
    aa = np.array(cim)
    vis = aa[..., 3] > 127
    ys, xs = np.where(vis)
    crop = cim.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
    mid = crop.resize((max(1, crop.width // 8), max(1, crop.height // 8)),
                      Image.NEAREST)
    tw = max(1, round(mid.width * 48 / mid.height))
    sm = mid.resize((tw, 48), Image.NEAREST)
    sa = np.array(sm).copy()
    for yy in range(sa.shape[0]):
        for xx in range(sa.shape[1]):
            r, g, b, al = sa[yy, xx]
            if al < 128:
                sa[yy, xx] = (0, 0, 0, 0)
                continue
            if r < 40 and g < 40 and b < 40:
                sa[yy, xx] = (*INK, 255)
                continue
            sa[yy, xx] = (*nearest((int(r), int(g), int(b))), 255)
    spr = Image.fromarray(sa)
    fr = Image.new("RGBA", (80, 80), (0, 0, 0, 0))
    fr.alpha_composite(spr, ((80 - spr.width) // 2, 78 - spr.height + 1))
    fr.save(FRAMES / "ori_jump_2.png")
    fr.save(NEW / "ori_jump_2.png")
    print("jump_2 replaced")


if __name__ == "__main__":
    main()
