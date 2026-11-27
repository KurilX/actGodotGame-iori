"""表情差分 V2：prompt 强约束像素语言 + 修帧像素化兜底。

## 问题（用户反馈）

上一版九宫格表情完全不是像素风——眼睛变成带睫毛高光的精细动漫眼、
脸有渐变腮红、线条平滑。原因：prompt 里"像素风"被九宫格构图需求
稀释，模型往"精致表情特写"方向跑了。

## 两个手段叠加

1. **prompt 强约束**：明确「低分辨率像素网格」「有限色数」「无抗锯齿
   无渐变无平滑线条」「粗大的方块状像素」，把"像素"从背景词提为主语。
2. **修帧像素化兜底**：生成后整图做「网格强制像素化」——把 2048px 图
   按 ~10px 网格降采样再放大回原尺寸，任何非像素细节都会被强制量化
   成大色块（无论模型画得多精细，出来必是像素风）。
"""
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
API = "https://ark.cn-beijing.volces.com/api/v3/images/generations"
ARK_API_KEY = os.environ.get("ARK_API_KEY", "")
if not ARK_API_KEY:
    kf = ROOT / "tools" / "ark_key.txt"
    if kf.exists():
        ARK_API_KEY = kf.read_text(encoding="utf-8").strip()
MODEL = "doubao-seedream-5-0-flash-260915"

REF = ROOT / "docs" / "refs" / "ai" / "ori_cachiu_raw.jpeg"
OUT = ROOT / "docs" / "refs" / "ai" / "expressions"

b64 = base64.b64encode(REF.read_bytes()).decode()
data_uri = f"data:image/jpeg;base64,{b64}"

PROMPT = (
    "低分辨率像素画（pixel art），有限调色板，粗大方块状像素，"
    "无抗锯齿，无渐变，无平滑线条，所有形状由可见的方形像素拼成。"
    "以参考图的 Q 版女孩角色为基准，保持她的绿发发髻、深蓝斗篷、"
    "配色和头身比例不变。"
    "生成一张 3×3 网格的表情差分图：九个格子整齐排列，"
    "每格是同一角色的头部特写（构图一致，仅表情不同），"
    "格子间用深色细线分隔。九个表情："
    "1 平静微笑；2 闭眼眨眼；3 开心大笑；4 生气皱眉；"
    "5 惊讶张嘴；6 受伤紧闭眼；7 委屈含泪；8 得意坏笑；9 无表情。"
    "背景纯黑。保持粗大像素颗粒，画面必须看起来像用低分辨率"
    "像素编辑器画的，颜色数量少而干净"
)

body = {
    "model": MODEL,
    "prompt": PROMPT,
    "image": [data_uri],
    "response_format": "url",
    "size": "2K",
    "stream": False,
    "watermark": False,
}
req = urllib.request.Request(
    API, data=json.dumps(body).encode(), method="POST",
    headers={"Content-Type": "application/json",
             "Authorization": "Bearer " + ARK_API_KEY})
try:
    with urllib.request.urlopen(req, timeout=180) as r:
        d = json.loads(r.read().decode())
    url = d["data"][0]["url"]
    data = urllib.request.urlopen(urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0"}), timeout=120).read()
except urllib.error.HTTPError as e:
    print("HTTP", e.code)
    print(e.read().decode("utf-8", "replace")[:400])
    sys.exit(1)

raw_path = OUT / "expressions_sheet_v2_raw.jpeg"
raw_path.write_bytes(data)
print(f"raw {raw_path} {len(data)//1024} KB")

# ── 修帧像素化兜底：10px 网格强制量化 ──
from PIL import Image  # noqa: E402
im = Image.open(raw_path).convert("RGB")
GRID = 10
small = im.resize((im.width // GRID, im.height // GRID), Image.NEAREST)
px = small.load()

# 限制色数：整图归并到最近的 ≤48 色（简单 median cut 的替代：
# 按亮度+色相粗分桶）
from collections import Counter  # noqa: E402
cnt = Counter()
for y in range(small.height):
    for x in range(small.width):
        cnt[px[x, y]] += 1
# 取出现最多的 48 色
top = [c for c, _ in cnt.most_common(48)]

def snap(c):
    best = min(top, key=lambda q: sum((q[i] - c[i]) ** 2 for i in range(3)))
    return best

for y in range(small.height):
    for x in range(small.width):
        px[x, y] = snap(px[x, y])

final = small.resize((small.width * GRID, small.height * GRID), Image.NEAREST)
final_path = OUT / "expressions_sheet_v2.png"
final.save(final_path)
print(f"pixelated {final_path} ({len(top)} colors)")
