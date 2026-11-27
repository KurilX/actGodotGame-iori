"""以用户提供的 CaChiu 参考图为 i2i 参考重新生成玩家立绘。

关键：这次把**参考图本身**（不是手绘临摹）喂给 Seedream，prompt 让它
保留参考图的可爱度/干净度/比例语言，只替换发色与服装为主题角色。
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

REF = ROOT / "docs" / "refs" / "ai" / "参考风格.png"
b64 = base64.b64encode(REF.read_bytes()).decode()
data_uri = f"data:image/png;base64,{b64}"

PROMPT = (
    "以这张像素画的角色风格为准：完全保留它的可爱程度、干净的大色块、"
    "简约五官（小方眼、小嘴）、头身比例和像素颗粒密度。"
    "只做以下替换：把角色的蓝紫发改成绿色短发发髻，"
    "把服装改成深蓝色小斗篷，保持同样的极简色块画法。"
    "背景改成纯黑色。角色为正面全身站姿立绘，"
    "输出为同一像素风格，不要增加任何细节或渐变"
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
except urllib.error.HTTPError as e:
    print("HTTP", e.code)
    print(e.read().decode("utf-8", "replace")[:400])
    sys.exit(1)

url = d["data"][0]["url"]
print("size:", d["data"][0].get("size"))
data = urllib.request.urlopen(urllib.request.Request(
    url, headers={"User-Agent": "Mozilla/5.0"}), timeout=120).read()
out = ROOT / "docs" / "refs" / "ai" / "ori_cachiu_raw.jpeg"
out.write_bytes(data)
print(f"saved {out} {len(data)//1024} KB")
