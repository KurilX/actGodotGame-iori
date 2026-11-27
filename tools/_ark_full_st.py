"""全量风格迁移：动作类动画（run/atk1-4/dash/heavy1-3/gain）逐动画跑
姿势网格 + 侧视基底 + 风格图 三参考重绘，然后切格修帧替换游戏帧。

idle / land 保留原帧（微动作会被抹平）。
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
FRAMES = ROOT / "art/characters/ori/frames"
BAK = ROOT / "art/characters/ori/backup_pre_ark_v2"
OUT = ROOT / "docs/refs/ai/style_transfer"
NEW = ROOT / "art/characters/ori/frames_side_st"
NEW.mkdir(exist_ok=True)
GRID = 18

sys.path.insert(0, str(ROOT / "artqa"))
from artqa.palette import load_palette  # noqa: E402
from artqa.config import repo_path  # noqa: E402

PAL = load_palette(repo_path("art/palette.gpl"), repo_path("art/palette.hex.txt"))
pal_colors = [tuple(int(v) for v in c) for c in PAL.colors]
INK = (18, 20, 42)

ANIMS = ["run", "atk1", "atk2", "atk3", "atk4", "dash",
         "heavy1", "heavy2", "heavy3", "gain"]


def du_small(p, maxpx=200):
    im = Image.open(p).convert("RGB")
    im.thumbnail((maxpx, maxpx), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=82)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def build_sheet(anim, idxs):
    cell = 240
    sheet = Image.new("RGB", (cell * 3, cell * 3), (26, 28, 42))
    for i, idx in enumerate(idxs[:9]):
        fr = Image.open(BAK / f"ori_{anim}_{idx}.png").convert("RGBA")
        big = fr.resize((cell, cell), Image.NEAREST)
        white = Image.new("RGBA", big.size, (240, 240, 235, 255))
        white.alpha_composite(big)
        gx, gy = i % 3, i // 3
        sheet.paste(white.convert("RGB"), (gx * cell, gy * cell))
    p = OUT / f"sheet_{anim}.png"
    sheet.save(p)
    return p


def restyle(sheet_path, anim, idxs):
    body = {
        "model": "doubao-seedream-5-0-flash-260915",
        "prompt": (
            "参考图 1 是一个像素风 Q 版角色的 3×3 动作帧网格"
            "（白底，每格一个姿势，从左到右从上到下排列），"
            "姿势结构与轮廓是权威基准。"
            "参考图 2 是该角色的标准侧视立绘（长相、发色、服装以此为准）。"
            "参考图 3 是像素画风示例。"
            "任务：逐格重绘参考图 1 的九个姿势，每格的姿势、轮廓、身体比例、"
            "构图与原图完全一致（不要改变动作），渲染统一为参考图 2 的长相配色、"
            "参考图 3 的大色块像素风（干净少色，黑方眼，无渐变）。"
            "输出 3×3 网格，顺序一致，每格背景纯黑"),
        "image": [du_small(sheet_path),
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
        print(f"{anim}: HTTP {e.code} "
              + e.read().decode("utf-8", "replace")[:200])
        return None
    url = d["data"][0]["url"]
    data = urllib.request.urlopen(urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0"}), timeout=120).read()
    dst = OUT / f"{anim}_restyled.jpeg"
    dst.write_bytes(data)
    print(f"{anim}: {dst.stat().st_size//1024} KB")
    return dst


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
    only = sys.argv[1] if len(sys.argv) > 1 else None
    for anim in ANIMS:
        if only and anim != only:
            continue
        idxs = sorted(int(p.name.split("_")[-1][:-4])
                      for p in BAK.glob(f"ori_{anim}_*.png"))
        sheet = build_sheet(anim, idxs)
        restyled = OUT / f"{anim}_restyled.jpeg"
        if not restyled.exists():
            restyled = restyle(sheet, anim, idxs)
        if not restyled:
            continue
        # 对齐 + 切格 + 修帧 + 替换
        im = Image.open(restyled).convert("RGB")
        w, h = im.size
        w2, h2 = (w // GRID) * GRID, (h // GRID) * GRID
        x0, y0 = (w - w2) // 2, (h - h2) // 2
        cropped = im.crop((x0, y0, x0 + w2, y0 + h2))
        small = cropped.resize((w2 // GRID, h2 // GRID), Image.NEAREST)
        aligned = small.resize((w2, h2), Image.NEAREST)
        cw, ch = aligned.width // 3, aligned.height // 3
        ok = 0
        for gi, idx in enumerate(idxs[:9]):
            gx, gy = gi % 3, gi // 3
            cell = aligned.crop((gx * cw, gy * ch,
                                 (gx + 1) * cw, (gy + 1) * ch))
            fr = cell_to_frame(cell)
            if fr is None:
                print(f"  {anim}_{idx}: empty cell, keep original")
                continue
            fr.save(NEW / f"ori_{anim}_{idx}.png")
            bk = BAK / f"ori_{anim}_{idx}.png"
            if not bk.exists():
                shutil.copy(FRAMES / f"ori_{anim}_{idx}.png", bk)
            shutil.copy(NEW / f"ori_{anim}_{idx}.png",
                        FRAMES / f"ori_{anim}_{idx}.png")
            ok += 1
        print(f"  {anim}: {ok}/{len(idxs[:9])} frames replaced")


if __name__ == "__main__":
    main()
