"""用 seedream 5.5（AgentPlan 新模型 ID）重做侧视基底立绘。

用户要求：基底模型用 seedream 5.5 重新生成，同时发送参考风格.png。
先探测 5.5 的模型 ID（可能为 doubao-seedream-5-5-flash / 5-5-pro 等）。
"""
import base64
import io
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
KEY = (ROOT / "tools/ark_key.txt").read_text(encoding="utf-8").strip()
API = "https://ark.cn-beijing.volces.com/api/plan/v3/images/generations"


def du(p, maxpx=200):
    im = Image.open(p).convert("RGB")
    im.thumbnail((maxpx, maxpx), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=82)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


from PIL import Image  # noqa: E402

STYLE = ROOT / "docs/refs/ai/参考风格.png"

CANDIDATES = [
    "doubao-seedream-5-5-flash",
    "doubao-seedream-5.5-flash",
    "doubao-seedream-5-5-flash-260915",
    "doubao-seedream-5-5-pro",
]

PROMPT = (
    "以参考图的像素画风格与可爱程度为基准：完全保留它的大色块画法、"
    "简约五官（黑方眼、小嘴）、头身比例、像素颗粒密度和干净程度。"
    "生成同一风格的 Q 版女孩角色全身立绘：绿色短发头顶丸子发髻，"
    "深蓝色小斗篷加白色内衬，深色短靴。"
    "朝向为右侧四分之三侧视（面朝画面右侧，身体微微右转，能看出鼻子侧影），"
    "这是横版动作游戏的角色朝向。"
    "正面稍侧站姿，纯黑背景，像素风，无渐变无抗锯齿，"
    "保持参考图的干净程度与可爱精致"
)

for model in CANDIDATES:
    body = {
        "model": model,
        "prompt": PROMPT,
        "image": [du(STYLE)],
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
        url = d["data"][0]["url"]
        data = urllib.request.urlopen(urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0"}), timeout=120).read()
        out = ROOT / "docs/refs/ai/ori_side_v3_raw.jpeg"
        out.write_bytes(data)
        print(f"OK {model}: saved {out} {len(data)//1024} KB")
        break
    except urllib.error.HTTPError as e:
        msg = e.read().decode("utf-8", "replace")[:150]
        print(f"{model}: HTTP {e.code} {msg}")
