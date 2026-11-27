"""表情差分：**一张图装下全部表情**（用户要求省 token，后期再裁剪）。

用 Ark i2i，参考图 = 已确认风格的绿发立绘。
prompt 要求画 3x3 表情格子（九宫格），每个格子同一角色不同表情。
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
OUT.mkdir(exist_ok=True)

b64 = base64.b64encode(REF.read_bytes()).decode()
data_uri = f"data:image/jpeg;base64,{b64}"

PROMPT = (
    "以参考图的像素风 Q 版少女角色为基准，完全保留她的绿发发髻、"
    "深蓝斗篷、大色块像素风格、干净的程度和头身比例。"
    "生成一张 3×3 的表情差分格子图：九个格子整齐排列，"
    "每个格子里是**同一个角色的头部与肩部特写**（构图一致，只有表情不同），"
    "格子之间用细的深色分隔线。九个表情分别是："
    "1 平静微笑；2 闭眼眨眼；3 开心大笑（眼睛弯成月牙、脸颊粉点）；"
    "4 生气皱眉；5 惊讶瞪圆眼张嘴；6 受伤痛苦紧闭眼；"
    "7 委屈快哭；8 得意坏笑；9 平静无表情。"
    "所有格子背景纯黑，角色像素风格与参考图完全一致，"
    "不增加任何细节或渐变，同一角色同一画法"
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
out = OUT / "expressions_sheet.jpeg"
out.write_bytes(data)
print(f"saved {out} {len(data)//1024} KB")
