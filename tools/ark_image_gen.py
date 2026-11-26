"""接入层正式化：tools/ark_image_gen.py（可复用的 Ark 生图客户端）。"""
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = "https://ark.cn-beijing.volces.com/api/v3/images/generations"
# 火山方舟 API key：**不要写进代码**（GitHub push protection 会拦截）。
# 读取顺序：环境变量 ARK_API_KEY → tools/ark_key.txt（gitignore）→ 报错。
ARK_API_KEY = os.environ.get("ARK_API_KEY", "")
if not ARK_API_KEY:
    _key_file = ROOT / "tools" / "ark_key.txt"
    if _key_file.exists():
        ARK_API_KEY = _key_file.read_text(encoding="utf-8").strip()
if not ARK_API_KEY:
    raise RuntimeError("缺 Ark API key：设 ARK_API_KEY 环境变量，"
                       "或写入 tools/ark_key.txt（已在 .gitignore）")
MODEL = "doubao-seedream-5-0-flash-260915"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass


def generate(prompt: str, size: str = "2K", watermark: bool = False,
             out_path: str | None = None) -> list[dict]:
    """生成图像，返回 [{"url", "size"}]。out_path 给定则下载第一个到本地。"""
    body = {
        "model": MODEL,
        "prompt": prompt,
        "response_format": "url",
        "size": size,
        "stream": False,
        "watermark": watermark,
    }
    req = urllib.request.Request(
        API, data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + ARK_API_KEY})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            d = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Ark HTTP {e.code}: "
                           + e.read().decode("utf-8", "replace")[:300]) from e
    items = d.get("data") or []
    if out_path and items:
        url = items[0].get("url")
        data = urllib.request.urlopen(urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0"}), timeout=120).read()
        Path(out_path).write_bytes(data)
    return items


if __name__ == "__main__":
    prompt = sys.argv[1] if len(sys.argv) > 1 else "test"
    out = sys.argv[2] if len(sys.argv) > 2 else None
    for item in generate(prompt, out_path=out):
        print(item.get("size"), item.get("url"))
    if out:
        print("saved:", out)
