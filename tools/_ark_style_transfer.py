"""风格迁移路线：手绘帧逐批过 i2i，只换渲染风格，姿势零漂移。

每批 9 格：每格参考 = 该帧手绘原图（脚本画的结构，骨架/比例全对）。
prompt：完全保持每格的姿势/轮廓/比例，仅把渲染风格统一为第二张参考图
（CaChiu 风）的大色块像素风。
"""
import json
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
BRIDGE = ROOT / "tools" / "ark_skill_bridge.js"
NODE = r"D:\tools\nodejs\node-v24.19.0-win-x64\node.exe"
FRAMES = ROOT / "art/characters/ori/frames"
OUT = ROOT / "docs/refs/ai/style_transfer"
OUT.mkdir(exist_ok=True)

ANIMS = ["idle", "run", "jump", "atk1", "atk2", "atk3", "atk4",
         "dash", "heavy1", "heavy2", "heavy3", "gain", "land"]

# 手绘帧是 80x80；拼 3×3 网格每格 80x80 → 240x240 太小，
# 放大 3x → 720x720 每格 240x240，画布 720x720。再放大给模型细节。
SCALE = 3


def build_sheet(anim: str, idxs: list[int]) -> Path:
    """把某动画的最多 9 帧手绘帧拼成 3×3 网格（每帧 NEAREST 放大）。"""
    cell = 80 * SCALE
    sheet = Image.new("RGB", (cell * 3, cell * 3), (26, 28, 42))
    for i, idx in enumerate(idxs[:9]):
        p = FRAMES / f"ori_{anim}_{idx}.png"
        fr = Image.open(p).convert("RGBA")
        big = fr.resize((cell, cell), Image.NEAREST)
        # 白底合成（便于模型识别非透明区）
        white = Image.new("RGBA", big.size, (240, 240, 235, 255))
        white.alpha_composite(big)
        gx, gy = i % 3, i // 3
        sheet.paste(white.convert("RGB"), (gx * cell, gy * cell))
    p = OUT / f"sheet_{anim}.png"
    sheet.save(p)
    return p


from PIL import Image  # noqa: E402


def style_transfer(sheet_path: Path, tag: str) -> Path | None:
    """i2i：保持姿势结构，仅统一渲染风格。"""
    import os
    key = ""
    kf = ROOT / "tools" / "ark_key.txt"
    if kf.exists():
        key = kf.read_text(encoding="utf-8").strip()
    API = "https://ark.cn-beijing.volces.com/api/plan/v3/images/generations"
    style_b64 = base64.b64encode(
        (ROOT / "tools/_ref_small.jpg").read_bytes()).decode()
    sheet_b64 = base64.b64encode(sheet_path.read_bytes()).decode()

    body = {
        "model": "doubao-seedream-5-0-flash-260915",
        "prompt": (
            "参考图 1 是一个像素风 Q 版角色的 3×3 动作帧网格"
            "（白色底、每格一个姿势，从左到右从上到下依次排列）。"
            "参考图 2 是目标渲染风格示例。"
            "任务：**逐格重新绘制**参考图 1 中的九个姿势，"
            "每个格子的姿势、轮廓、身体比例、构图必须与原图完全一致"
            "（不要改变任何动作或比例），只把渲染风格统一成参考图 2 的"
            "大色块像素风（干净、少色数、黑方眼、无渐变）。"
            "输出也是 3×3 网格，顺序一致，每格背景纯黑"
        ),
        "image": [
            f"data:image/png;base64,{sheet_b64}",
            f"data:image/jpeg;base64,{style_b64}",
        ],
        "response_format": "url",
        "size": "2K",
        "stream": False,
        "watermark": False,
    }
    req = urllib.request.Request(
        API, data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + key})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            d = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        print(f"{tag}: HTTP {e.code} "
              + e.read().decode("utf-8", "replace")[:200])
        return None
    url = d["data"][0]["url"]
    data = urllib.request.urlopen(urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0"}), timeout=120).read()
    dst = OUT / f"{tag}_restyled.jpeg"
    dst.write_bytes(data)
    print(f"{tag}: {dst.stat().st_size//1024} KB")
    return dst


import base64  # noqa: E402
import urllib.error  # noqa: E402
import urllib.request  # noqa: E402

if __name__ == "__main__":
    only = sys.argv[1] if len(sys.argv) > 1 else None
    for anim in ANIMS:
        if only and anim != only:
            continue
        # 帧数 ≤9 的直接一批；atk 等多于 9 帧的动画按前 9 帧（atk 都是 6 帧 OK）
        idxs = sorted(int(p.name.split("_")[-1][:-4])
                      for p in FRAMES.glob(f"ori_{anim}_*.png"))
        sheet = build_sheet(anim, idxs)
        style_transfer(sheet, anim)
