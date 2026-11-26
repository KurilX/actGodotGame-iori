"""生成 pixel-studio 瓦片化地形迭代的单文件 HTML 总览页。

所有图片内嵌 base64 data URI，双击即看，不需要服务器。
内容：前后对比（旧整幅贴图 vs 新瓦片砌图）、三张实机截图、
评分轨迹、图集与样例地图、结论与下一步。
"""
import base64
import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = ROOT / "art" / "tilegen_report.html"

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def b64(rel: str) -> str:
    p = ROOT / rel
    if not p.exists():
        return ""
    return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode()


def img(rel: str, caption: str, max_w=960) -> str:
    src = b64(rel)
    if not src:
        return f"<div class='miss'>缺图 {rel}</div>"
    return (f"<figure><img src='{src}' style='max-width:{max_w}px'>"
            f"<figcaption>{caption}</figcaption></figure>")


report = json.load(open(ROOT / "art" / "tiles" / "tilegen_report.json",
                        encoding="utf-8"))
try:
    final = json.load(open(ROOT / "art" / "final_score.json", encoding="utf-8"))
except Exception:  # noqa: BLE001
    final = {}

SCORE_ROWS = [
    ("R0 基线（旧整幅 AI 贴图）", "53 / 69 / 68", "63.3", "53.0",
     "大面积灰蓝纯色块、像未完成的灰盒"),
    ("R1 瓦片化 v1（18 配置 × 2 变体）", "77 / 91 / 67", "78.3", "67.0",
     "砖块结构出现；跳跃段冲到 91"),
    ("R4 瓦片 v0/v1 mix（3 采样中位）", "77 / 76 / 69", "74.0", "69.0",
     "最低分抬到 69，方差收窄"),
    ("R5 场景道具（残柱/石堆/木桶/吊灯）", "78 / 85 / 77", "78.0", "77.0",
     "BOSS 房从 69 → 77；木桩换成石座木桩"),
    ("R8 色板修复 + 预警圈隐藏", "82 / 72 / 77", "77.0", "72.0",
     "背景/天空全落 28 色板，教程起点首破 80"),
    ("S1 v3 风化砖（12% 混入）", "68 / 77 / 73", "72.7", "68.0",
     "✗ 蓝灰砖与背景明度粘连，回退（教训：地形必须亮过背景一档）"),
    ("S2 回退 + 云层微调", "76 / 73 / 80", "76.3", "73.0",
     "BOSS 房首破 80"),
    ("S3 矮墙 + 清弹幕（5 采样）", "84 / 81 / 69", "78.0", "69.0",
     "教程/跳跃新高；BOSS 拖底 → 确认需要大件"),
    ("S4 BOSS 大件：断墙/门框（7 采样）", "75 / 79 / 79", "77.7", "75.0",
     "三张全部 ≥75；BOSS 大件是真实提升"),
    ("S5 接地阴影（7 采样）", "76 / 79 / 80", "78.3", "76.0",
     "最低分 76 创新高；合并分 74.1"),
]

rows_html = "".join(
    f"<tr><td>{a}</td><td>{b}</td><td class='num'>{c}</td><td class='num'>{d}</td>"
    f"<td>{e}</td></tr>" for a, b, c, d, e in SCORE_ROWS)

html = f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<title>pixel-studio 瓦片化地形 · 迭代总览</title>
<style>
body {{ font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif; background:#14152b;
       color:#dcdff0; margin:0; padding:32px; line-height:1.6; }}
h1 {{ color:#a7f070; font-size:26px; }} h2 {{ color:#ffcd75; margin-top:44px; }}
figure {{ margin:14px 0; text-align:center; }}
img {{ border:1px solid #394051; border-radius:6px; image-rendering:pixelated; }}
figcaption {{ font-size:13px; color:#8f97b8; margin-top:6px; }}
table {{ border-collapse:collapse; width:100%; margin:16px 0; }}
th, td {{ border:1px solid #394051; padding:8px 12px; font-size:14px; text-align:left; }}
th {{ background:#22243f; color:#a7f070; }}
tr:nth-child(even) {{ background:#1a1c30; }}
.num {{ text-align:center; font-variant-numeric:tabular-nums; }}
.good {{ color:#a7f070; }} .bad {{ color:#ff8f8f; }} .warn {{ color:#ffcd75; }}
.miss {{ color:#ff8f8f; padding:12px; border:1px dashed #59405a; }}
.kv {{ background:#1a1c30; border:1px solid #394051; border-radius:6px;
       padding:14px 18px; margin:12px 0; font-size:14px; }}
code {{ background:#22243f; padding:1px 6px; border-radius:4px; }}
.cols {{ display:flex; gap:18px; flex-wrap:wrap; }}
.cols > div {{ flex:1 1 400px; }}
</style></head><body>

<h1>pixel-studio 瓦片化地形 · 迭代总览</h1>
<p>生成日期 {datetime.now().strftime('%Y-%m-%d %H:%M')} ·
生成端 <code>tools/make_terrain_tiles.py</code> ·
接入层 <code>tools/pixel_studio_bridge.py</code> ·
上游 <code>tools/vendor/pixel-studio</code>（alanfrigo/pixel-studio, MIT, cd5a9ca）</p>

<h2>1. 一句话结论</h2>
<div class="kv">
地形层从「一整张 2400×540 贴图」换成 <b>pixel-studio side_guides 的 18 配置瓦片图集
（× 2 个 body 变体）</b>，按关卡 solids 逐格砌出。<b>细节密度 0.154 → 0.777（×5）</b>。
扩展迭代（场景排布 + 大件装饰 + 接地阴影）后 AI 平均分 <b>63.3 → 78.3</b>，
最低单图 <b>53 → 76</b>（创新高），合并分 59.0 → 74.1。<br><br>
<b>本轮（S1~S5）关键结论</b>：
① 蓝灰风化砖让地形与背景明度粘连（S1 -14），回退——<b>地形必须亮过背景一档</b>；
② BOSS 房需要<b>大件</b>（断墙/门框）而非小石堆，S3→S4 BOSS 69→79→80；
③ 所有评分噪声 ±4~15，单轮结论必须 5+ 采样才可信；
④ 截图脚本清弹幕/预警圈——战斗实体不进美术评分帧。
</div>

<h2>2. 前后对比（同一关卡位置）</h2>
<div class="cols">
<div>{img('art/screenshots/_old_x400.png', '旧：整幅 AI 贴图平铺（R0 基线 · 教程起点）')}
     {img('art/screenshots/par_x400.png', '新：pixel-studio 瓦片砌图（R4 · 教程起点）')}</div>
<div>{img('art/screenshots/_old_x1200.png', '旧：跳跃段台阶（R0）')}
     {img('art/screenshots/par_x1200.png', '新：跳跃段台阶（R4）')}</div>
</div>

<h2>3. 瓦片系统本体</h2>
{img('art/tiles/tiles_mock_v2.png', 'pixel-studio 官方 12×5 样例地图，用本项目图集渲染（surface / wall / thin / 内角）', 560)}
{img('art/tiles/tiles_tileset_a.png', 'side_guides 图集 A：18 配置 × 20px（顶面/侧壁/天花板/薄台/内角），放大 4×', 560)}
{img('art/tiles/tiles_body_a.png', 'body 源材质 a：20×20 严格纵向循环石砖（texture_seams Y 轴通过）', 160)}

<h2>4. 评分轨迹（glm-5.3 主评，同尺度参考素材）</h2>
<table><tr><th>轮次</th><th>三张截图分</th><th>平均</th><th>最低</th><th>备注</th></tr>
{rows_html}</table>
<div class="kv">
数值指标（art_review.py）：地形细节密度 <b class="good">0.154 → 0.777</b>，
terrain 数值分 84.6 → 76.3（该指标奖励色数多，砖缝确定性结构色数略少；
它测不出「像不像成品」，AI 分才是主裁判 —— 详见 final_score 权重 AI 0.65）。
R2 破损变体与 R3 单变体对照用来<b>控制变量</b>：破损裂缝在小分辨率下变噪点（回退），
双变体 mix 贡献约 +5。
</div>

<h2>5. 管线与验收</h2>
<div class="kv">
<b>生成链</b>：<code>make_terrain_tiles.py</code> 生成 body a/b/c + surface →
pixel-studio <code>side_guides</code> 出 3×18 配置图集 →
<code>texture_seams</code>（body 纵向循环 ✓）→
<code>tileset_seams</code>（官方样例地图 advisory，gaps=0 ✓）→
按 tutorial.json 砌 2400×540 → 28 色板量化 →
<code>make_scene_art.py</code> 优先采用 <code>terrain_from_tiles.png</code> →
Godot 导入 → <code>cap_par.gd</code> 实机抓图 → AI 评审。<br><br>
<b>瓦片使用统计</b>：{json.dumps(report['configs_used'], ensure_ascii=False)}<br>
<b>最终用色</b>：{report['colors_final']} / 28（硬上限内）
</div>

<h2>6. 遗留问题（下一杠杆）</h2>
<div class="kv">
<ul>
<li>跳跃段（79）：砖块重复感仍是最高频 top_issue——变体明度路线已证伪
    （S1），可行方向是<b>缝级变化</b>（部分砖缝断开 1px、缝里长草籽）。</li>
<li>BOSS 房（80）：纹理重复；大件已足量，下一杠杆是柱身<b>裂缝贴花</b>。</li>
<li>数值分最低 70.6（bg_sky/cloud 氛围层用色少被数值口径压分）——
    可考虑按类别分权重，与 AI 分解耦。</li>
<li>合并分 74.1 / 门槛 80：S1~S5 五轮累计 min 72→76（+4），噪声大，
    继续迭代优先级 &gt; 继续抠单轮分数。</li>
</ul>
</div>

<h2>7. 复现</h2>
<div class="kv">
<pre style="margin:0;white-space:pre-wrap">python tools/make_terrain_tiles.py   # 瓦片图集 + 砌地形（离线，秒级）
python tools/make_scene_art.py       # 场景三层合成（优先用瓦片层）
godot --headless --path . --import   # Godot 重导入
godot --path . --script tools/cap_par.gd -- --autoplay   # 实机抓图
# AI 评分需 ANTHROPIC_BASE_URL / ANTHROPIC_AUTH_TOKEN（codebuddy 网关）</pre>
</div>

</body></html>"""

OUT.write_text(html, encoding="utf-8")
print(f"written {OUT} ({OUT.stat().st_size // 1024} KB)")
sys.exit(0)
