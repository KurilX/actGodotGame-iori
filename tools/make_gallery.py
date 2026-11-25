"""生成美术总览页：把所有视觉素材内嵌进单个 HTML。

## 为什么要这个

美术迭代过程中会产生几十张截图（对比图、放大图、原型图、瓦片表）。
散落在 `art/screenshots/` 里，只能一张张点开看，很难整体判断。

这个脚本把**当期所有视觉素材**扫出来，按类别分组，
全部 base64 内嵌，生成一个自包含的 HTML：

    python tools/make_gallery.py

输出 `art/gallery.html`，双击即可打开，不需要服务器。

## 分类规则

按文件名前缀自动归类，加一张新图只要命名符合就能自动进对的分组。
"""

import base64
import os
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "art", "gallery.html")

# (分组名, 说明, [目录], [文件名关键字])
GROUPS = [
    ("当前游戏画面", "实际渲染的关卡截图", ["art/screenshots"],
     ["lv2_", "lvl_", "fix_", "veg_", "seam_view", "band_fix", "wave_preview"]),
    ("美术迭代对比", "改前/改后对照", ["art/screenshots"],
     ["compare", "proto_ingame", "wave_compare", "filter_"]),
    # 只收本次地形/植被迭代的放大图。
    # 之前用宽泛的 "zoom" 关键字，把旧战斗动作和树的放大图也扫进来了。
    ("细节放大", "4x~6x 放大看像素", ["art/screenshots"],
     ["seam_zoom", "veg_zoom", "wave_zoom", "proto_zoom", "tiles_zoom",
      "tiles_mock2x"]),
    ("瓦片研发", "手绘瓦片与拼接试验", ["art/tiles", "art/screenshots"],
     ["tileset", "tiles_mock", "tiles_zoom"]),
    ("参考素材（真实）", "从 opengameart 采集的 CC0 像素地形",
     ["docs/refs/pixel", "docs/refs/candidates"],
     ["p1_", "p2_", "p3_", "p4_", "p5_", "c1_", "c2_", "c3_"]),
    ("参考地图（HK）", "空洞骑士官方区域地图剪影", ["docs/refs"],
     ["hk_"]),
    ("AI 地形链路", "AI 生成 → 28 色量化 → 缩像素 → 可平铺",
     ["docs/refs/ai", "art/ai_tiles", "art/screenshots"],
     ["ai_terrain_01", "ai_terrain_quantized", "ai_terrain_pixel",
      "ai_terrain_tileable", "ai_pixel_zoom", "ai_compare", "ai_zoom"]),
    ("AI 背景素材尝试", "早期三轮尝试（含失败版）",
     ["docs/refs/ai", "art/ai_tiles", "art/screenshots"],
     ["ai_bg_01", "ai_bg_screen", "ai_bg_wide", "ai_bg_sky",
      "bg_ai_compare"]),
    ("分层视差背景", "最终方案：六层独立平铺，随相机视差滚动",
     ["art/bg", "art/screenshots"],
     ["bg_sky", "bg_moon", "bg_mtn_", "bg_layers", "par_x"]),
    ("原型与纹理", "程序化生成的贴图", ["art/scene"],
     ["proto_terrain", "terrain", "deco", "sky"]),
]


def collect():
    """扫描所有目录，按分组关键字归类。返回 [(组名, 说明, [(路径, 说明)])]。"""
    found = []
    for name, desc, dirs, keys in GROUPS:
        items = []
        for d in dirs:
            full = os.path.join(ROOT, d)
            if not os.path.isdir(full):
                continue
            for fn in sorted(os.listdir(full)):
                if not fn.lower().endswith((".png", ".jpg", ".jpeg")):
                    continue
                if not any(k in fn for k in keys):
                    continue
                items.append(os.path.join(full, fn))
        # 去掉已经出现在前面分组的图（避免重复展示）
        items = [p for p in items if p not in found]
        if items:
            found.extend(items)
            found_paths = items
            yield name, desc, [(p, os.path.basename(p)) for p in found_paths]


def data_uri(path):
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    mime = "image/jpeg" if ext in ("jpg", "jpeg") else "image/png"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def size_of(path):
    from PIL import Image
    try:
        with Image.open(path) as im:
            return im.size
    except Exception:
        return (0, 0)


def build():
    sections = list(collect())
    total = sum(len(items) for _, _, items in sections)

    parts = ["""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>actGame 美术总览</title>
<style>
  :root {
    --bg: #14141f;
    --panel: #1d1d2b;
    --line: #2f2f45;
    --text: #e6e8f0;
    --dim: #8a8da3;
    --accent: #9ed47e;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 28px 32px 64px;
    background: var(--bg); color: var(--text);
    font: 14px/1.6 -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif;
  }
  h1 { font-size: 22px; margin: 0 0 6px; font-weight: 600; }
  .sub { color: var(--dim); font-size: 13px; margin-bottom: 28px; }
  h2 {
    font-size: 15px; margin: 36px 0 4px; font-weight: 600;
    padding-bottom: 8px; border-bottom: 1px solid var(--line);
  }
  h2 .count { color: var(--dim); font-weight: 400; font-size: 13px; }
  .desc { color: var(--dim); font-size: 12px; margin: 6px 0 14px; }
  .grid {
    display: grid; gap: 16px;
    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  }
  figure {
    margin: 0; background: var(--panel);
    border: 1px solid var(--line); border-radius: 6px;
    overflow: hidden;
  }
  figure img {
    display: block; width: 100%; height: auto;
    background: #0e0e16;
  }
  figcaption {
    padding: 8px 10px; font-size: 12px; color: var(--dim);
    border-top: 1px solid var(--line);
    word-break: break-all;
  }
  .px img { image-rendering: pixelated; }
  .empty { color: var(--dim); font-style: italic; padding: 12px 0; }
</style>
</head>
<body>
"""]

    parts.append(f"<h1>actGame《缀》美术总览</h1>\n")
    parts.append(
        f'<div class="sub">共 {total} 张 · 生成于 '
        f'{datetime.now().strftime("%Y-%m-%d %H:%M")} · '
        f'图片已内嵌，可直接分享</div>\n')

    if not sections:
        parts.append('<div class="empty">没有找到图片</div>\n')

    for name, desc, items in sections:
        parts.append(
            f'<h2>{name} <span class="count">({len(items)})</span></h2>\n')
        parts.append(f'<div class="desc">{desc}</div>\n')
        parts.append('<div class="grid">\n')
        for path, label in items:
            w, h = size_of(path)
            # 像素图用 pixelated 渲染，避免浏览器插值糊掉
            cls = "px" if "scene" not in path and "refs/pixel" not in path \
                else "px"
            parts.append(
                f'<figure class="{cls}">'
                f'<img src="{data_uri(path)}" alt="{label}" loading="lazy">'
                f'<figcaption>{label} · {w}×{h}</figcaption>'
                f'</figure>\n')
        parts.append('</div>\n')

    parts.append("</body>\n</html>\n")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("".join(parts))
    print(f"总览页: {OUT}")
    print(f"  共 {total} 张，分 {len(sections)} 组")
    for name, _, items in sections:
        print(f"    {name}: {len(items)}")
    return 0


if __name__ == "__main__":
    sys.exit(build())
