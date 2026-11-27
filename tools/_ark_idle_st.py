"""idle 帧也走风格迁移：姿势网格保留原帧微动作，但 prompt 明确
「保持每格姿势差异（呼吸起伏/眨眼）」+ 低温度约束，避免抹平。

上次问题：idle 帧间微动作（呼吸/眨眼）被抹平成同姿势。
对策：prompt 逐格点名动作（格子1=低头，格子2=站立呼吸…），
并在输出网格间加分隔线让模型严格按格复刻。
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
API = "https://ark.cn-beijing.volces.com/api/plan/v3/images/generations"
BAK = ROOT / "art/characters/ori/backup_pre_ark_v2"
FRAMES = ROOT / "art/characters/ori/frames"
NEW = ROOT / "art/characters/ori/frames_side_st"
NEW.mkdir(exist_ok=True)
GRID = 18

sys.path.insert(0, str(ROOT / "artqa"))
from artqa.palette import load_palette  # noqa: E402
from artqa.config import repo_path  # noqa: E402

PAL = load_palette(repo_path("art/palette.gpl"), repo_path("art/palette.hex.txt"))
pal_colors = [tuple(int(v) for v in c) for c in PAL.colors]
INK = (18, 20, 42)


def du_small(p, maxpx=240):
    im = Image.open(p).convert("RGB")
    im.thumbnail((maxpx, maxpx), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


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


def main():
    idxs = list(range(8))
    # 拼网格（白底、加格线）
    cell = 240
    sheet = Image.new("RGB", (cell * 3, cell * 3), (26, 28, 42))
    for i, idx in enumerate(idxs):
        fr = Image.open(BAK / f"ori_idle_{idx}.png").convert("RGBA")
        big = fr.resize((cell, cell), Image.NEAREST)
        white = Image.new("RGBA", big.size, (240, 240, 235, 255))
        white.alpha_composite(big)
        gx, gy = i % 3, i // 3
        sheet.paste(white.convert("RGB"), (gx * cell, gy * cell))
    sp = OUT_DIR = ROOT / "docs/refs/ai/style_transfer/idle_sheet_v2.png"
    sheet.save(sp)

    ACTIONS = [
        "低头（头微微向下，看地面）", "抬头回正（标准站姿）",
        "站立呼吸（身体微起伏）", "眨眼瞬间（眼睛闭合成细线）",
        "站立呼吸（头发轻飘）", "站立（标准）",
        "眨眼（另一帧）", "站立（头微微偏右看）",
    ]
    prompt = (
        "参考图 1 是像素风 Q 版角色的 3×3 动作帧网格（白底，每格一个姿势，"
        "从左到右从上到下排列），姿势是权威基准。"
        "参考图 2 是该角色标准侧视立绘（长相、发色、服装以此为准）。"
        "参考图 3 是像素画风示例。"
        "任务：逐格重绘参考图 1 的八个姿势，每格姿势必须与原图格子的姿势"
        "**完全一致**——包括头部的低垂角度、眨眼状态、身体起伏幅度，"
        "这些帧间差异是待机动画的关键，绝对不要抹平。"
        "格子顺序的动作分别是：" + "；".join(ACTIONS) + "。"
        "渲染统一为参考图 2 的长相配色 + 参考图 3 的大色块像素风。"
        "输出 3×3 网格（8 个有内容 + 右下空格纯黑），顺序一致，"
        "格子间用细深色分隔线")
    body = {
        "model": "doubao-seedream-5-0-flash-260915",
        "prompt": prompt,
        "image": [du_small(sp),
                  du_small(ROOT / "docs/refs/ai/ori_side_raw.jpeg"),
                  du_small(ROOT / "docs/refs/ai/参考风格.png")],
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
        print("HTTP", e.code, e.read().decode("utf-8", "replace")[:300])
        return
    url = d["data"][0]["url"]
    data = urllib.request.urlopen(urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0"}), timeout=120).read()
    raw = OUT_DIR if isinstance(OUT_DIR, Path) else None
    dst = ROOT / "docs/refs/ai/style_transfer/idle_v2_restyled.jpeg"
    dst.write_bytes(data)
    print(f"restyled {dst} {len(data)//1024} KB")

    # 对齐切格修帧替换
    im = Image.open(dst).convert("RGB")
    w, h = im.size
    w2, h2 = (w // GRID) * GRID, (h // GRID) * GRID
    x0, y0 = (w - w2) // 2, (h - h2) // 2
    cropped = im.crop((x0, y0, x0 + w2, y0 + h2))
    small = cropped.resize((w2 // GRID, h2 // GRID), Image.NEAREST)
    aligned = small.resize((w2, h2), Image.NEAREST)
    cw, ch = aligned.width // 3, aligned.height // 3
    ok = 0
    for gi, idx in enumerate(idxs):
        gx, gy = gi % 3, gi // 3
        cell_img = aligned.crop((gx * cw, gy * ch,
                                 (gx + 1) * cw, (gy + 1) * ch))
        fr = cell_to_frame(cell_img)
        if fr is None:
            print(f"  idle_{idx}: empty, keep")
            continue
        fr.save(NEW / f"ori_idle_{idx}.png")
        shutil.copy(NEW / f"ori_idle_{idx}.png",
                    FRAMES / f"ori_idle_{idx}.png")
        ok += 1
    print(f"idle {ok}/8 replaced")
    # 条带
    strip = Image.new("RGBA", (80 * 8 + 70, 90), (26, 28, 42, 255))
    for i in range(8):
        f = Image.open(FRAMES / f"ori_idle_{i}.png")
        strip.alpha_composite(f, (10 + i * 90, 5))
    strip = strip.resize((int(strip.width * 1.5), int(strip.height * 1.5)),
                         Image.NEAREST)
    strip.save(ROOT / "art/screenshots/_idle_strip_v2.png")
    print("strip saved")


if __name__ == "__main__":
    main()
