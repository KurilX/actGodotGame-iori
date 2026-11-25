"""美术评分报告页：单 HTML，内嵌图片与全部指标。

## 为什么单独做报告而不是复用 gallery

gallery 是"看素材"，报告是"看结论"：
  · 每项资产一行，列出 6 个维度的得分
  · 参考素材的实测区间作为对照轴
  · 总分与门槛线直接标出来
  · 不通过的项红色高亮

## 数据来源

`tools/art_review.py` 生成 `art/art_score.json`。
本脚本读它，并把资产图片 base64 内嵌，输出 `art/art_report.html`。
"""

import base64
import json
import os
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCORE = os.path.join(ROOT, "art", "art_score.json")
OUT = os.path.join(ROOT, "art", "art_report.html")

# 维度中文名与说明
DIMENSION_INFO = {
    "colors": ("用色丰富度", "独立颜色数量。太少等于没画"),
    "lum_bins": ("明度层次", "亮度的非空分档数，决定立体感"),
    "detail": ("细节密度", "边缘像素占比，反映质感"),
    "contrast": ("对比度跨度", "最亮与最暗的差，过平会糊"),
    "aa_purity": ("抗锯齿纯净度", "有没有糊边，像素画必须硬边"),
    "hue_focus": ("色相凝聚度", "色调是否统一"),
}


def data_uri(path):
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    mime = "image/jpeg" if ext in ("jpg", "jpeg") else "image/png"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def bar(score, passed):
    """分数条。颜色按是否达标区分。"""
    color = "#6fcf6f" if passed else "#e06c6c"
    w = max(0.0, min(100.0, score))
    return (f'<div class="bar"><div class="fill" '
            f'style="width:{w:.1f}%;background:{color}"></div></div>')


def main():
    if not os.path.exists(SCORE):
        print("缺 art/art_score.json，先跑 python tools/art_review.py",
              file=sys.stderr)
        return 1
    with open(SCORE, encoding="utf-8") as f:
        d = json.load(f)

    # 终审数据（数值 + AI + 合并）。缺失时报告仍能生成，只是没有 AI 段。
    final = None
    fp = os.path.join(ROOT, "art", "final_score.json")
    if os.path.exists(fp):
        with open(fp, encoding="utf-8") as f:
            final = json.load(f)

    threshold = float(d["pass_score"])
    passed = bool(d["passed"])
    items = d.get("items", [])
    refs = d.get("reference_range", {})
    weights = d.get("weights", {})

    parts = ["""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>actGame 美术评分报告</title>
<style>
  :root { --bg:#14141f; --panel:#1d1d2b; --line:#2f2f45;
          --text:#e6e8f0; --dim:#8a8da3; --accent:#9ed47e;
          --bad:#e06c6c; --good:#6fcf6f; }
  * { box-sizing: border-box; }
  body { margin:0; padding:28px 32px 64px; background:var(--bg);
         color:var(--text); font:14px/1.6 -apple-system,"Segoe UI",
         "Microsoft YaHei",sans-serif; }
  h1 { font-size:22px; margin:0 0 4px; font-weight:600; }
  .sub { color:var(--dim); font-size:13px; margin-bottom:24px; }
  .verdict { padding:16px 20px; border-radius:8px; margin-bottom:28px;
             font-size:15px; font-weight:600; }
  .verdict.ok { background:#1e3a22; border:1px solid #2f6b38;
                color:var(--good); }
  .verdict.bad { background:#3a1e1e; border:1px solid #6b2f2f;
                 color:var(--bad); }
  h2 { font-size:15px; margin:28px 0 10px; padding-bottom:8px;
       border-bottom:1px solid var(--line); font-weight:600; }
  table { width:100%; border-collapse:collapse; font-size:13px; }
  th, td { text-align:left; padding:8px 10px;
           border-bottom:1px solid var(--line); vertical-align:middle; }
  th { color:var(--dim); font-weight:500; font-size:12px; }
  .score-cell { font-variant-numeric:tabular-nums; font-weight:600;
                width:70px; }
  .bad-score { color:var(--bad); }
  .good-score { color:var(--good); }
  .bar { position:relative; height:6px; background:#26263a;
         border-radius:3px; overflow:hidden; width:110px; }
  .bar .fill { height:100%; border-radius:3px; }
  .asset { display:flex; gap:14px; align-items:flex-start; padding:14px 0;
           border-bottom:1px solid var(--line); }
  .asset img { width:230px; height:auto; image-rendering:pixelated;
               border:1px solid var(--line); border-radius:4px;
               background:#0e0e16; flex-shrink:0; }
  .asset .meta { flex:1; min-width:0; }
  .asset h3 { font-size:14px; margin:0 0 4px; font-weight:600; }
  .path { color:var(--dim); font-size:12px; margin-bottom:8px;
          word-break:break-all; }
  .dims { display:grid; grid-template-columns:repeat(3,1fr); gap:6px 18px;
          font-size:12px; }
  .dim { display:flex; justify-content:space-between; gap:8px;
         color:var(--dim); }
  .dim b { color:var(--text); font-weight:500;
           font-variant-numeric:tabular-nums; }
  .skip { color:#666a80; font-style:italic; }
  .note { color:var(--dim); font-size:12px; margin:8px 0 0; }
</style>
</head>
<body>
"""]

    parts.append("<h1>actGame《缀》美术评分报告</h1>\n")
    parts.append(
        f'<div class="sub">门槛 {threshold:.0f} 分 · '
        f'最低 {d["min_score"]:.1f} 分 · '
        f'{datetime.now().strftime("%Y-%m-%d %H:%M")}</div>\n')

    if final is not None:
        ok = bool(final.get("passed"))
        gates = final.get("gates", {})
        rows = []
        for key, cn in (("numeric", "数值指标"), ("ai", "AI 视觉"),
                        ("final", "合并总分")):
            g = gates.get(key, False)
            mark = "✓" if g else "✗"
            rows.append(f"{mark} {cn}")
        head = "全部通过" if ok else "不通过"
        cls = "ok" if ok else "bad"
        parts.append(
            f'<div class="verdict {cls}">{"✓" if ok else "✗"} {head}'
            f'<span style="float:right;font-weight:400;font-size:13px">'
            f'{" · ".join(rows)}</span></div>\n')
    elif passed:
        parts.append(
            f'<div class="verdict ok">✓ 全部通过 —— '
            f'最低 {d["min_score"]:.1f} 分 ≥ 门槛 {threshold:.0f} 分</div>\n')
    else:
        parts.append(
            f'<div class="verdict bad">✗ 不通过 —— '
            f'{"、".join(d.get("failed", []))}</div>\n')

    # ── 参考区间 ──
    parts.append("<h2>参考基准（来自成熟商业素材的实测）</h2>\n")
    parts.append('<p class="note">阈值不是主观设定的，而是从以下公开素材的指标分布反推：'
                 + "、".join(os.path.basename(p) for p in refs.get("files", []))
                 + "</p>\n")
    parts.append("<table><tr><th>维度</th><th>最小值</th><th>中位数</th>"
                 "<th>最大值</th><th>权重</th></tr>\n")
    for key, (cn, _) in DIMENSION_INFO.items():
        r = refs.get(key)
        if not r:
            continue
        w = weights.get(key, 0)
        parts.append(
            f"<tr><td>{cn}</td><td>{r['min']:.3f}</td>"
            f"<td>{r['median']:.3f}</td><td>{r['max']:.3f}</td>"
            f"<td>{w:.2f}</td></tr>\n")
    parts.append("</table>\n")

    # ── AI 视觉打分 ──
    if final is not None:
        parts.append("<h2>AI 视觉评审（与成熟素材同尺度比较）</h2>\n")
        parts.append(
            '<p class="note">把游戏实机截图与多张成熟商业素材一起给模型，'
            '要求在同一把尺子下比较。每个目标采样 3 次取中位数。'
            '四个维度各 25 分。</p>\n')
        parts.append("<table><tr><th>截图</th><th>层次</th><th>落地</th>"
                     "<th>材质</th><th>完成度</th><th>总分</th></tr>\n")
        for t in final.get("ai_targets", []):
            tot = float(t.get("total", 0))
            cls = "good-score" if tot >= float(
                final.get("ai_threshold", 0)) else "bad-score"
            parts.append(
                f"<tr><td>{t.get('label','?')}</td>"
                f"<td>{t.get('depth',0):.0f}</td>"
                f"<td>{t.get('grounding',0):.0f}</td>"
                f"<td>{t.get('material',0):.0f}</td>"
                f"<td>{t.get('polish',0):.0f}</td>"
                f'<td class="{cls}"><b>{tot:.0f}</b></td></tr>\n')
        parts.append("</table>\n")

        parts.append("<h3 style=\"font-size:13px;margin:16px 0 8px\">"
                     "AI 指出的具体问题</h3>\n<ul style=\"margin:0;"
                     "padding-left:20px;font-size:13px\">\n")
        for t in final.get("ai_targets", []):
            issue = (t.get("top_issue") or "").strip()
            if issue:
                parts.append(f"<li><b>{t.get('label','?')}</b>：{issue}</li>\n")
        parts.append("</ul>\n")

    # ── 逐项资产 ──
    parts.append("<h2>数值指标评分</h2>\n")
    for it in items:
        label = it.get("label", "?")
        path = it.get("path", "")
        score = float(it.get("score", 0))
        ok = score >= threshold
        cls = "good-score" if ok else "bad-score"

        full = os.path.join(ROOT, path)
        img_tag = ""
        if os.path.exists(full):
            img_tag = (f'<img src="{data_uri(full)}" alt="{label}">')

        dims_html = []
        skipped = set(it.get("skipped", []))
        for key, (cn, desc) in DIMENSION_INFO.items():
            val = it.get("items", {}).get(key)
            if key in skipped:
                dims_html.append(
                    f'<div class="dim"><span>{cn}</span>'
                    f'<span class="skip">不适用</span></div>')
                continue
            if val is None:
                continue
            dims_html.append(
                f'<div class="dim"><span>{cn}</span>'
                f'<b>{float(val):.1f}</b></div>')

        parts.append(f'<div class="asset">{img_tag}'
                     f'<div class="meta">'
                     f'<h3>{label} '
                     f'<span class="{cls}">— {score:.1f} 分</span></h3>'
                     f'<div class="path">{path}</div>'
                     f'{bar(score, ok)}'
                     f'<div class="dims">{"".join(dims_html)}</div>'
                     f'</div></div>\n')

    # ── 维度说明 ──
    parts.append("<h2>维度说明</h2>\n<table>\n")
    parts.append("<tr><th>维度</th><th>含义</th><th>权重</th></tr>\n")
    for key, (cn, desc) in DIMENSION_INFO.items():
        parts.append(f"<tr><td>{cn}</td><td>{desc}</td>"
                     f"<td>{weights.get(key, 0):.2f}</td></tr>\n")
    parts.append("</table>\n")

    parts.append("</body>\n</html>\n")

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("".join(parts))
    print(f"报告: {OUT}")
    print(f"  {len(items)} 项资产，"
          f"{'通过' if passed else '不通过'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
