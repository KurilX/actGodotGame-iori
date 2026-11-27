"""表情差分 V4：prompt 锁密度 + 修帧网格对齐（叠加方案）。

1. prompt：明确「每个格子里的角色头部大小与第一张参考图立绘一致」
   「像素颗粒密度与参考图完全一致（一个逻辑像素约 18 个实际像素）」
2. 修帧：出图后按基底立绘的逻辑像素网格（~18px）做对齐重采样，
   只对齐网格不并色（保留色彩层次）。
"""
import json
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
BRIDGE = ROOT / "tools" / "ark_skill_bridge.js"
OUT = ROOT / "docs" / "refs" / "ai" / "expressions"

# ── 1. prompt（锁密度版）──
PROMPT = (
    "像素风格。第一张参考图是角色的标准立绘，第二张参考图是像素画风示例。"
    "生成 3×3 表情差分格子图：九个格子整齐排列，每格是同一个角色"
    "（绿发丸子头、深蓝斗篷的女孩）的头部与肩部特写。"
    "关键要求：每个格子里的角色头部大小必须与第一张参考图立绘中的头部"
    "一样大（放大到格子填满），像素颗粒密度与参考图完全一致"
    "（粗大的方块状像素，不要画细）。"
    "表情从左到右、从上到下：生气、开心、闭眼、哭哭、惊讶、"
    "得意、平静、害羞、呆滞。"
    "纯黑背景，格子之间用细的深色分隔线，无渐变无抗锯齿"
)

with open(ROOT / "tools" / "_prompt_expr_v4.txt", "w", encoding="utf-8") as f:
    f.write(PROMPT)

# ── 2. 生成 ──
node = r"D:\tools\nodejs\node-v24.19.0-win-x64\node.exe"
cmd = [
    node, str(BRIDGE),
    str(ROOT / "tools" / "_prompt_expr_v4.txt"),
    str(ROOT / "tools" / "_ref_base_small.jpg") + "|" + str(ROOT / "tools" / "_ref_small.jpg"),
    str(OUT),
    "false",
]
r = subprocess.run(cmd, capture_output=True, text=True,
                   encoding="utf-8", errors="replace", timeout=300)
out = (r.stdout or "") + (r.stderr or "")
saved = None
for line in out.splitlines():
    if line.startswith("SAVED "):
        saved = Path(line.split(" ", 1)[1].split(" ")[0])
if saved:
    raw = OUT / "expressions_v4_raw.jpeg"
    saved.rename(raw)
    print(f"raw {raw} {raw.stat().st_size//1024} KB")
else:
    print("FAILED")
    print(out[-600:])
    sys.exit(1)

# ── 3. 网格对齐（18px 逻辑像素，只对齐不并色）──
from PIL import Image  # noqa: E402
import numpy as np  # noqa: E402

GRID = 18
im = Image.open(raw).convert("RGB")
w, h = im.size
# 中心对齐裁到网格倍数
w2, h2 = (w // GRID) * GRID, (h // GRID) * GRID
x0, y0 = (w - w2) // 2, (h - h2) // 2
cropped = im.crop((x0, y0, x0 + w2, y0 + h2))
small = cropped.resize((w2 // GRID, h2 // GRID), Image.NEAREST)
aligned = small.resize((w2, h2), Image.NEAREST)
final = OUT / "expressions_v4_aligned.png"
aligned.save(final)
print(f"aligned {final} ({len(set(small.getdata()))} colors)")
