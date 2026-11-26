"""Ark 图生图（带参考图）：以当前游戏 idle 帧为参考，保持比例与配色。

Seedream 的 image 参数：参考图数组，第一张当主参考（主体冲突以第一张为准）。
prompt 策略（用户指点）：
  · 明确「保持图中角色的比例、造型、配色不变」
  · 只做画面质量提升：更干净的像素块、更清晰的轮廓
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

# 参考图：当前游戏 idle 帧（38x48 精灵贴 80x80 帧）放大 4x，
# 让模型看清比例/配色/描边语言
ref_frame = Image_open = None
from PIL import Image  # noqa: E402
ref = Image.open(ROOT / "art/characters/ori/frames/ori_idle_0.png")
ref_big = ref.resize((ref.width * 6, ref.height * 6), Image.NEAREST)
buf = Path(ROOT / "tools" / "_ref_frame.png")
ref_big.save(buf)
b64 = base64.b64encode(buf.read_bytes()).decode()
data_uri = f"data:image/png;base64,{b64}"

PROMPT = (
    "以参考图中的像素风 Q 版少女角色为准：保持她的 2.5 头身比例、"
    "正面站姿、绿色短发发髻、深蓝斗篷、手持缝衣针的配色与造型完全不变，"
    "生成同一角色的同一站姿立绘。"
    "要求：角色比例与参考图相差不要太大（头身比一致、头部大小一致），"
    "纯黑色背景，全身居中，"
    "像素风格干净大色块，1px 细描边，硬边阴影无渐变，"
    "角色轮廓圆润，比例不要放大或缩小，与参考图保持同一视角与姿态"
)

body = {
    "model": MODEL,
    "prompt": PROMPT,
    "image": [data_uri],
    "response_format": "url",
    "size": "2K",
    "stream": False,
    "watermark": False,
    "seed": 20261126,
}
req = urllib.request.Request(
    API, data=json.dumps(body).encode(), method="POST",
    headers={"Content-Type": "application/json",
             "Authorization": "Bearer " + ARK_API_KEY})
try:
    with urllib.request.urlopen(req, timeout=180) as r:
        d = json.loads(r.read().decode())
except urllib.error.HTTPError as e:
    print("HTTP", e.code)
    print(e.read().decode("utf-8", "replace")[:400])
    sys.exit(1)

url = d["data"][0]["url"]
print("size:", d["data"][0].get("size"))
data = urllib.request.urlopen(urllib.request.Request(
    url, headers={"User-Agent": "Mozilla/5.0"}), timeout=120).read()
out = ROOT / "docs" / "refs" / "ai" / "ori_ark_i2i_raw.jpeg"
out.write_bytes(data)
print(f"saved {out} {len(data)//1024} KB")
