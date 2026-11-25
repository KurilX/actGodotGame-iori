"""AI 视觉打分：把游戏截图与成熟参考素材一起给模型，做相对比较。

## 为什么需要这一步

数值指标（`art_metrics.py`）只能测**几何统计**：颜色数、边缘密度、
对比度……它测不出：

  · 东西是不是"漂浮"的（没有落地阴影）
  · 层与层之间有没有缝合感
  · 视觉重心是否失衡
  · 一眼看上去像不像成品

这些只有真正"看一眼"才能判断。

## 关键设计：让模型做**相对比较**，不是绝对打分

只给一张图问"打几分"，模型会给出随机的客气分数。
这里每次都**同时塞入 4 张成熟参考素材**，要求它在同一把尺子下比较。

## 抗噪：多次采样取中位数

单次打分方差大。默认跑 3 次，取各维度中位数。
模型也不稳定（网关有时返回空），所以带 fallback 链 + 完整性校验。

## 与数值指标的关系

两者**互补、都要过**：
  · 数值指标管"有没有画"（1 色 vs 15 色的客观差距）
  · AI 打分管"画得对不对"（构图、落地感、层次）

最终分 = 数值分 × 0.55 + AI 分 × 0.45，两项各自也有单独门槛。
"""

import base64
import json
import os
import statistics
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "art", "ai_score.json")

# 待评的游戏截图（实际渲染，不是素材）
TARGETS = [
    ("教程关起点", "art/screenshots/par_x400.png"),
    ("跳跃段台阶", "art/screenshots/par_x1200.png"),
    ("BOSS 房", "art/screenshots/par_x2000.png"),
]

# 参考素材：同一把尺子
REFERENCES = [
    "docs/refs/pixel/p2_db32_tileset.png",
    "docs/refs/pixel/p4_forest.png",
    "docs/refs/pixel/p3_db32_mockup.png",
]

# 模型 fallback 链（网关对这些模型的稳定性不同）
MODELS = ["glm-5.3", "kimi-k3-1", "deepseek-v4-pro"]
SAMPLES = 3               # 每个目标采样几次取中位数
MIN_PIXELS_OK = 800       # 图片太小说明截取失败

RUBRIC = """你在为像素风横版动作游戏做美术质量评审。

【评审对象】一张游戏实机截图。
【参考基准】同时给出的若干张成熟商业级像素素材（CC0 授权的平台游戏图集/实景）。
请**在参考素材的尺度下**判断截图质量，不要给客气的印象分。

【四个维度，各 0~25 分】

1. 层次与纵深（depth）
   近景/中景/远景是否分明？地形与背景是否有清晰的明暗分离？
   有没有"所有东西贴在同一平面"的扁平感？

2. 落地与实在感（grounding）
   角色、敌人、道具是否都有落脚点？悬空的东西看着像 bug 还是有意设计？
   地形边缘是否可信（不是悬浮的方块）？

3. 材质与细节（material）
   地形有石质/土质的质感吗？还是纯色块？
   与参考素材相比，细节密度差多少？

4. 整体完成度（polish）
   一眼看上去像可发布的游戏，还是像原型/灰盒？
   配色是否统一？有没有刺眼的突兀色块？

【输出格式】
只输出一行 JSON，不要任何其他文字：
{"depth":<0-25>,"grounding":<0-25>,"material":<0-25>,"polish":<0-25>,
 "top_issue":"<一句话，指出最明显的视觉问题>",
 "compare_note":"<一句话，描述与参考素材的主要差距>"}
"""


def api_config():
    base = os.environ.get("ANTHROPIC_BASE_URL", "").rstrip("/")
    token = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
    if not base or not token:
        print("缺少 ANTHROPIC_BASE_URL / ANTHROPIC_AUTH_TOKEN", file=sys.stderr)
        sys.exit(2)
    if base.endswith("/v1"):
        base = base[:-3]
    return base, token


def encode(path):
    ext = os.path.splitext(path)[1].lower()
    mime = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"
    with open(path, "rb") as f:
        data = base64.b64encode(f.read()).decode("ascii")
    return {"type": "image",
            "source": {"type": "base64", "media_type": mime, "data": data}}


def call(base, token, model, images, prompt, max_tokens=900):
    url = base + "/v1/messages"
    content = [encode(p) for p in images]
    content.append({"type": "text", "text": prompt})
    body = json.dumps({
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": content}],
    }).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "x-api-key": token,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=240) as r:
            d = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:200]}",
              file=sys.stderr)
        return None
    except Exception as e:  # noqa: BLE001
        print(f"  请求失败：{e}", file=sys.stderr)
        return None

    if d.get("stop_reason") == "max_tokens":
        print("  [截断] 回答未完成，当作失败", file=sys.stderr)
        return None
    text = "".join(b.get("text", "") for b in d.get("content", [])
                   if isinstance(b, dict) and b.get("type") == "text")
    return text.strip() if text.strip() else None


def parse_scores(text):
    """从模型输出里抠出 JSON。模型偶尔会包 ```json 或加解释。"""
    if not text:
        return None
    s = text.strip()
    # 去掉代码围栏
    if "```" in s:
        parts = s.split("```")
        for p in parts:
            p = p.strip()
            if p.startswith("json"):
                p = p[4:].strip()
            if p.startswith("{"):
                s = p
                break
    i, j = s.find("{"), s.rfind("}")
    if i < 0 or j <= i:
        return None
    try:
        d = json.loads(s[i:j + 1])
    except json.JSONDecodeError:
        return None
    for k in ("depth", "grounding", "material", "polish"):
        if k not in d:
            return None
        try:
            d[k] = max(0.0, min(25.0, float(d[k])))
        except (TypeError, ValueError):
            return None
    return d


def score_one(base, token, label, img_path, refs):
    """对一个目标采样多次，取各维度中位数。"""
    images = [img_path] + refs
    prompt = RUBRIC + f"\n\n本次评审对象是「{label}」。"
    samples = []
    for attempt in range(SAMPLES * len(MODELS)):
        model = MODELS[attempt % len(MODELS)]
        raw = call(base, token, model, images, prompt)
        d = parse_scores(raw)
        if d:
            samples.append(d)
            print(f"  {label} 采样 {len(samples)}/{SAMPLES}（{model}）"
                  f" {d['depth']:.0f}/{d['grounding']:.0f}/"
                  f"{d['material']:.0f}/{d['polish']:.0f}")
        if len(samples) >= SAMPLES:
            break
    if not samples:
        return None

    med = {}
    for k in ("depth", "grounding", "material", "polish"):
        med[k] = statistics.median(s[k] for s in samples)
    med["total"] = round(sum(med[k] for k in
                             ("depth", "grounding", "material", "polish")), 1)
    med["samples"] = len(samples)
    # 取出现最多的 top_issue（去重后取第一条）
    issues = [s.get("top_issue", "") for s in samples if s.get("top_issue")]
    med["top_issue"] = issues[0] if issues else ""
    notes = [s.get("compare_note", "") for s in samples
             if s.get("compare_note")]
    med["compare_note"] = notes[0] if notes else ""
    return med


def main():
    base, token = api_config()
    targets = []
    refs = []
    for p in REFERENCES:
        full = os.path.join(ROOT, p)
        if os.path.exists(full):
            refs.append(full)
        else:
            print(f"  警告：参考素材缺失 {p}", file=sys.stderr)
    if len(refs) < 2:
        print("参考素材不足 2 份，无法做相对比较", file=sys.stderr)
        return 1

    print(f"参考素材 {len(refs)} 份（同一把尺子）")
    for label, rel in TARGETS:
        full = os.path.join(ROOT, rel)
        if not os.path.exists(full):
            print(f"  {label}: 截图缺失 {rel}", file=sys.stderr)
            continue
        print(f"\n评审 {label}")
        r = score_one(base, token, label, full, refs)
        if r is None:
            print(f"  {label}: 全部采样失败")
            targets.append({"label": label, "path": rel, "failed": True,
                            "total": 0.0})
            continue
        targets.append({
            "label": label, "path": rel, "failed": False,
            "depth": round(r["depth"], 1),
            "grounding": round(r["grounding"], 1),
            "material": round(r["material"], 1),
            "polish": round(r["polish"], 1),
            "total": r["total"],
            "samples": r["samples"],
            "top_issue": r["top_issue"],
            "compare_note": r["compare_note"],
        })

    if not targets:
        print("没有任何目标被评分", file=sys.stderr)
        return 1

    valid = [t for t in targets if not t["failed"]]
    avg = (round(sum(t["total"] for t in valid) / len(valid), 1)
           if valid else 0.0)
    worst = min((t["total"] for t in valid), default=0.0)

    payload = {
        "scale": 100,
        "avg_score": avg,
        "min_score": worst,
        "targets": targets,
        "references": [os.path.relpath(p, ROOT) for p in refs],
        "samples_per_target": SAMPLES,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    print(f"\n=== AI 打分结果 ===")
    for t in targets:
        if t["failed"]:
            print(f"  {t['label']}: 失败")
        else:
            print(f"  {t['label']}: {t['total']:.0f}/100")
            print(f"      层次 {t['depth']:.0f} 落地 {t['grounding']:.0f} "
                  f"材质 {t['material']:.0f} 完成度 {t['polish']:.0f}")
            if t.get("top_issue"):
                print(f"      主要问题：{t['top_issue']}")
    print(f"\n  平均 {avg}  最低 {worst}")
    print(f"  输出 {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
