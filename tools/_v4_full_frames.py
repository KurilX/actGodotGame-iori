"""V4 AI 直出全帧：以 ori_v4_base.jpeg 为角色锚，10 批九宫格出 82 帧。

批分配（82 帧）：
  b1 idle 8 + land 0-4（5）= 9... 实际按 9 格/批排：
  b1: idle 0-7 + land_0        (9)
  b2: land_1-5 + run_0-3       (9)
  b3: run_4-7 + jump_0-2 + dash_0-2 (9)
  b4: atk1_0-5 + atk2_0-2      (9)
  b5: atk2_3-5 + atk3_0-5      (9)
  b6: atk4_0-5 + dash_1-2      (9)
  b7: heavy1_0-7               (8)
  b8: heavy2_0-7               (8)
  b9: heavy3_0-7               (8)
  b10: gain_0-5 + land 重试    (6+)
"""
import base64
import io
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
KEY = (ROOT / "tools/ark_key.txt").read_text(encoding="utf-8").strip()
API = "https://ark.cn-beijing.volces.com/api/plan/v3/images/generations"
MODEL = "doubao-seedream-5-5-flash"
ANCHOR = ROOT / "docs/refs/ai/ori_v4_base.jpeg"
OUT = ROOT / "docs/refs/ai/v4_frames"
NEW = ROOT / "art/characters/ori/frames_v4"
FRAMES = ROOT / "art/characters/ori/frames"
BAK = ROOT / "art/characters/ori/backup_pre_v4"
OUT.mkdir(exist_ok=True)
NEW.mkdir(exist_ok=True)
GRID = 18

sys.path.insert(0, str(ROOT / "artqa"))
from artqa.palette import load_palette  # noqa: E402
from artqa.config import repo_path  # noqa: E402

PAL = load_palette(repo_path("art/palette.gpl"), repo_path("art/palette.hex.txt"))
pal_colors = [tuple(int(v) for v in c) for c in PAL.colors]
INK = (18, 20, 42)


def du(p, maxpx=280):
    im = Image.open(p).convert("RGB")
    im.thumbnail((maxpx, maxpx), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=86)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


BATCHES = [
    ("b1", ["站立（标准）", "站立呼吸（身体微起伏）", "站立眨眼",
            "站立（头微偏）", "站立呼吸（另一帧）", "站立（微笑）",
            "站立（头发轻飘）", "站立呼吸（另一帧）",
            "落地缓冲（屈膝）"]),
    ("b2", ["落地缓冲（屈膝）", "落地起身", "落地站稳", "落地缓冲（深蹲）",
            "落地收势", "站稳", "跑步（迈左腿）", "跑步（腾空）",
            "跑步（迈右腿）"]),
    ("b3", ["跑步（后蹬）", "跑步（迈左腿另一帧）", "跑步（腾空另一帧）",
            "跑步（迈右腿另一帧）", "跳跃起跳", "跳跃腾空",
            "闪避滑步（低身）", "闪避翻滚", "闪避起身"]),
    ("b4", ["轻斩起手", "轻斩上撩", "轻斩横扫", "轻斩命中",
            "轻斩跟随", "轻斩收势", "二连斩起手", "二连斩横扫",
            "二连斩收"]),
    ("b5", ["二连斩（续）", "三连突刺起手", "三连突刺", "三连突刺收",
            "三连收剑", "轻斩重置", "回剑", "拔剑", "警戒"]),
    ("b6", ["四段回旋斩起手", "四段回旋斩", "四段回旋斩收", "四段结束",
            "四段收剑", "四段重置", "闪避滑步", "闪避起身"]),
    ("b7", ["重击蓄力（举剑过肩）", "重击蓄力（蓄深）", "重击蓄力（绷紧）",
            "重击下劈", "重击命中", "重击跟随", "重击收势（喘息）",
            "重击收势（直起）"]),
    ("b8", ["二段重击起手（举剑反手）", "二段重击蓄力", "二段重击上撩",
            "二段重击腾空", "二段重击收", "二段重击重置", "二段喘息",
            "持剑站立"]),
    ("b9", ["三段重击（泰山压顶起跳）", "三段重击（空中）", "三段重击（下砸）",
            "三段重击（震地）", "三段重击（扬尘）", "三段重击（起身）",
            "三段重击（收剑）", "三段重击（重置）"]),
    ("b10", ["双手接住道具", "举高道具", "抱住道具开心", "收起道具",
             "拍拍手", "行礼"]),
]

# 格子 → (anim, idx)
MAPPING = {
    "b1": [("idle", 0), ("idle", 1), ("idle", 2), ("idle", 3), ("idle", 4),
           ("idle", 5), ("idle", 6), ("idle", 7), ("land", 0)],
    "b2": [("land", 1), ("land", 2), ("land", 3), ("land", 4), ("land", 5),
           ("land", 2), ("run", 0), ("run", 1), ("run", 2)],
    "b3": [("run", 3), ("run", 4), ("run", 5), ("run", 6), ("run", 7),
           ("jump", 0), ("jump", 1), ("dash", 0), ("dash", 1)],
    "b4": [("atk1", 0), ("atk1", 1), ("atk1", 2), ("atk1", 3), ("atk1", 4),
           ("atk1", 5), ("atk2", 0), ("atk2", 1), ("atk2", 2)],
    "b5": [("atk2", 3), ("atk2", 4), ("atk2", 5), ("atk3", 0), ("atk3", 1),
           ("atk3", 2), ("atk3", 3), ("atk3", 4), ("atk3", 5)],
    "b6": [("atk4", 0), ("atk4", 1), ("atk4", 2), ("atk4", 3), ("atk4", 4),
           ("atk4", 5), ("dash", 1), ("dash", 2)],
    "b7": [("heavy1", 0), ("heavy1", 1), ("heavy1", 2), ("heavy1", 3),
           ("heavy1", 4), ("heavy1", 5), ("heavy1", 6), ("heavy1", 7)],
    "b8": [("heavy2", 0), ("heavy2", 1), ("heavy2", 2), ("heavy2", 3),
           ("heavy2", 4), ("heavy2", 5), ("heavy2", 6), ("heavy2", 7)],
    "b9": [("heavy3", 0), ("heavy3", 1), ("heavy3", 2), ("heavy3", 3),
           ("heavy3", 4), ("heavy3", 5), ("heavy3", 6), ("heavy3", 7)],
    "b10": [("gain", 0), ("gain", 1), ("gain", 2), ("gain", 3),
            ("gain", 4), ("gain", 5)],
}


def nearest(c):
    return min(pal_colors, key=lambda q: sum((q[i] - c[i]) ** 2 for i in range(3)))


def cell_to_frame(cell_rgb):
    rgba = cell_rgb.convert("RGBA")
    a = np.array(rgba)
    bg = (a[..., 0] < 45) & (a[..., 1] < 45) & (a[..., 2] < 55)
    a[bg] = (0, 0, 0, 0)
    cim = Image.fromarray(a)
    aa = np.array(cim)
    vis = aa[..., 3] > 127
    if not vis.any():
        return None
    ys, xs = np.where(vis)
    crop = cim.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
    mid = crop.resize((max(1, crop.width // 8), max(1, crop.height // 8)),
                      Image.NEAREST)
    tw = max(1, round(mid.width * 48 / mid.height))
    small = mid.resize((tw, 48), Image.NEAREST)
    sa = np.array(small).copy()
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
    return fr


def gen_batch(name, actions):
    prompt = (
        "严格复刻第一张参考图中像素角色的全部风格语言：超大头 Q 版比例"
        "（头身比 1:1.2）、大色块极简配色（每区域 2~4 色阶，全图不超过 12 色）、"
        "黑方眼浅紫瞳、蓝紫发双马尾丸子、红发卡方格、深蓝斗篷红领结白衬衫"
        "黑短裙深色靴、方形像素构成、无渐变无抗锯齿。"
        "这是同一个角色的动作帧网格。生成 3×3 格子图：九个格子整齐排列，"
        "每格是同一角色的全身动作，角色大小与参考图一致（放大到格子填满），"
        "像素颗粒密度与参考图一致。"
        "动作从左到右、从上到下依次是：" + "；".join(actions) + "。"
        "纯黑背景，格子之间用细的深色分隔线")
    body = {
        "model": MODEL,
        "prompt": prompt,
        "image": [du(ANCHOR)],
        "response_format": "url",
        "size": "2K",
        "stream": False,
        "watermark": False,
    }
    req = urllib.request.Request(
        API, data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + KEY})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            d = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        print(f"{name}: HTTP {e.code} "
              + e.read().decode("utf-8", "replace")[:200])
        return None
    url = d["data"][0]["url"]
    data = urllib.request.urlopen(urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0"}), timeout=120).read()
    dst = OUT / f"{name}_raw.jpeg"
    dst.write_bytes(data)
    print(f"{name}: {dst.stat().st_size//1024} KB")
    return dst


def swap_batch(name):
    mapping = MAPPING[name]
    raw = OUT / f"{name}_raw.jpeg"
    if not raw.exists():
        return 0
    im = Image.open(raw).convert("RGB")
    w, h = im.size
    w2, h2 = (w // GRID) * GRID, (h // GRID) * GRID
    x0, y0 = (w - w2) // 2, (h - h2) // 2
    cropped = im.crop((x0, y0, x0 + w2, y0 + h2))
    small = cropped.resize((w2 // GRID, h2 // GRID), Image.NEAREST)
    aligned = small.resize((w2, h2), Image.NEAREST)
    cw, ch = aligned.width // 3, aligned.height // 3
    ok = 0
    for gi, (anim, idx) in enumerate(mapping):
        gx, gy = gi % 3, gi // 3
        cell = aligned.crop((gx * cw, gy * ch, (gx + 1) * cw, (gy + 1) * ch))
        fr = cell_to_frame(cell)
        if fr is None:
            print(f"  {anim}_{idx}: empty, keep")
            continue
        fr.save(NEW / f"ori_{anim}_{idx}.png")
        bk = BAK / f"ori_{anim}_{idx}.png"
        bk.parent.mkdir(exist_ok=True)
        if not bk.exists():
            shutil_copy(FRAMES / f"ori_{anim}_{idx}.png", bk)
        shutil_copy(NEW / f"ori_{anim}_{idx}.png",
                    FRAMES / f"ori_{anim}_{idx}.png")
        ok += 1
    return ok


def shutil_copy(src, dst):
    import shutil
    shutil.copy(src, dst)


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    total = 0
    for name, actions in BATCHES:
        if only and name != only:
            continue
        raw = OUT / f"{name}_raw.jpeg"
        if not raw.exists():
            raw = gen_batch(name, actions)
        if raw:
            total += swap_batch(name)
    print(f"total swapped: {total}")


if __name__ == "__main__":
    main()
