"""下载生成的立绘并放大预览。"""
import json
import sys
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(r"D:\Program Files\Projects\personal\actGame")
d = json.load(open(ROOT / "tools" / "_last_gen.json", encoding="utf-8"))
url = d["data"][0]["url"]
out = ROOT / "docs" / "refs" / "ai" / "ori_ark_raw.jpeg"
data = urllib.request.urlopen(urllib.request.Request(
    url, headers={"User-Agent": "Mozilla/5.0"}), timeout=120).read()
out.write_bytes(data)
print(f"raw {out} {len(data)//1024} KB")

from PIL import Image  # noqa: E402
im = Image.open(out)
print("size:", im.size)
# 立绘主体大约在中心，裁出并放大预览
im.thumbnail((512, 512), Image.NEAREST)
im.save(ROOT / "docs" / "refs" / "ai" / "ori_ark_preview.png")
print("preview saved")
