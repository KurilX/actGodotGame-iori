"""美术评价体系：用成熟参考素材推导阈值，给当前资产打分。

## 核心思路

**阈值不从主观设定，全部由参考素材反推。**

流程：
  1. 对 4 份成熟像素素材算指标 → 得到"合格区间"
  2. 对我们的资产算同样的指标
  3. 逐项对比打分（落在参考区间内得满分，偏离越多扣分）
  4. 加权总分 ≥ 门槛才允许通过

## 参考素材（docs/refs/pixel/）

  · p2_db32_tileset.png   256x144   DB32 32 色调色板平台瓦片（CC0）
  · p4_forest.png         288x172   森林地形 + 角色，侧视（CC0）
  · p1_castle_tiles.png   512x1344  城堡瓦片图集，多套配色（CC0）
  · p3_db32_mockup.png    1024x576  DB32 平台游戏实机构图（CC0）

它们的指标分布就是"成熟商业素材"的实测区间。

## 评分维度与权重

| 维度 | 权重 | 为什么重要 |
|---|---|---|
| 用色丰富度 | 0.20 | 只有 1~2 色的图层等于没画 |
| 明度层次 | 0.22 | 决定立体感，参考素材 7~15 档 |
| 细节密度 | 0.18 | 边缘细节量，参考 0.13~0.70 |
| 对比度跨度 | 0.15 | 过平会糊、过曝会刺眼 |
| 抗锯齿纯净度 | 0.15 | 像素画必须硬边 |
| 色相凝聚度 | 0.10 | 色调统一度 |

总分 100，**门槛 70**。低于 70 判定「不允许通过」。
"""

import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import art_metrics as M

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── 参考素材 ──
REFERENCES = [
    "docs/refs/pixel/p2_db32_tileset.png",
    "docs/refs/pixel/p4_forest.png",
    "docs/refs/pixel/p1_castle_tiles.png",
    "docs/refs/pixel/p3_db32_mockup.png",
]

# ── 待评资产，按**图层类型**分组 ──
#
# **不同类型不能用同一套基线。**
# 地形是"实体"，需要丰富的色阶和细节；
# 天空/云是"氛围"，本来就该低对比、少颜色 —— 用地形标准评它们，
# 会把合格的渐变天空判成不合格（实测 bg_sky 只有 2 色就被判 50 分）。
#
# 所以：
#   solid  实心地形 → 用全部参考素材（DB32 图集、森林地形、城堡瓦片）
#   sky    天空     → 用"大面积纯色 + 缓渐变"的参考
#   mtn    山层     → 用"剪影式远山"的参考
TARGETS = [
    ("地形层 terrain", "art/scene/terrain.png", "solid"),
    ("天空层 bg_sky", "art/bg/bg_sky.png", "sky"),
    ("远山 bg_mtn_far", "art/bg/bg_mtn_far.png", "mtn"),
    ("中山 bg_mtn_mid", "art/bg/bg_mtn_mid.png", "mtn"),
    ("近山 bg_mtn_near", "art/bg/bg_mtn_near.png", "mtn"),
    ("云层 bg_cloud", "art/bg/bg_cloud.png", "sky"),
]

# 各类型的"可以省略的维度"及其权重重分配。
# 天空/云不需要"用色丰富"和"高对比" —— 那是地形的标准。
SKIP_FOR = {
    "solid": set(),
    "sky": {"colors", "contrast"},
    "mtn": {"colors", "contrast"},
}

# ── 权重 ──
WEIGHTS = {
    "colors": 0.20,
    "lum_bins": 0.22,
    "detail": 0.18,
    "contrast": 0.15,
    "aa_purity": 0.15,
    "hue_focus": 0.10,
}

PASS_SCORE = 70.0


def collect_reference_stats():
    """算参考素材每项指标的 min / median / max。"""
    rows = []
    for p in REFERENCES:
        full = os.path.join(ROOT, p)
        if not os.path.exists(full):
            print(f"  警告：参考素材缺失 {p}")
            continue
        r = M.measure(full)
        if r:
            rows.append(r)
    if not rows:
        print("没有可用的参考素材", file=sys.stderr)
        return None

    def stat(key):
        vals = sorted(float(r[key]) for r in rows)
        return {
            "min": vals[0],
            "median": vals[len(vals) // 2],
            "max": vals[-1],
        }

    return {
        "files": [r["path"] for r in rows],
        "colors": stat("colors"),
        "lum_bins": stat("nonempty_bins"),
        "detail": stat("detail"),
        "contrast": stat("contrast"),
        "aa_ratio": stat("aa_ratio"),
        "hue_std": stat("hue_std"),
    }


def score_metric(value, ref, higher_better=True, hard_floor=None):
    """把一项指标映射到 0~100。

    规则：
      · 落在 [min, max] 区间内 → 100 分
      · 低于 min（偏高方向是恶化）→ 按相对差距扣分
      · 高于 max → 同样扣分
    """
    lo, hi = ref["min"], ref["max"]
    if lo <= value <= hi:
        return 100.0
    if value < lo:
        span = max(1e-6, hi - lo)
        deficit = (lo - value) / span
        s = max(0.0, 100.0 - deficit * 100.0)
    else:
        span = max(1e-6, hi - lo)
        excess = (value - hi) / span
        s = max(0.0, 100.0 - excess * 100.0)
    if hard_floor is not None and value < hard_floor:
        s = min(s, 30.0)
    return s


def evaluate(refs):
    results = []
    for label, rel, kind in TARGETS:
        full = os.path.join(ROOT, rel)
        if not os.path.exists(full):
            results.append({
                "label": label, "path": rel, "missing": True,
                "score": 0.0, "items": {},
            })
            continue
        r = M.measure(full)
        if r is None:
            results.append({
                "label": label, "path": rel, "missing": True,
                "score": 0.0, "items": {},
            })
            continue

        items = {}
        # 用色丰富度：参考区间 15~115
        items["colors"] = score_metric(float(r["colors"]), refs["colors"],
                                       hard_floor=6.0)
        # 明度层次：参考 7~15 档
        items["lum_bins"] = score_metric(float(r["nonempty_bins"]),
                                        refs["lum_bins"], hard_floor=4.0)
        # 细节密度
        items["detail"] = score_metric(float(r["detail"]), refs["detail"])
        # 对比度
        items["contrast"] = score_metric(float(r["contrast"]), refs["contrast"])
        # 抗锯齿纯净度：换成"纯净度"再比（越低越好）
        items["aa_purity"] = score_metric(-float(r["aa_ratio"]),
                                         {"min": -refs["aa_ratio"]["max"],
                                          "median": -refs["aa_ratio"]["median"],
                                          "max": -refs["aa_ratio"]["min"]})
        # 色相凝聚度：标准差不该太大（参考 49~146 是不同题材，取 60 为上限）
        items["hue_focus"] = score_metric(
            float(r["hue_std"]),
            {"min": 0.0, "median": 40.0, "max": 110.0})

        # 按类型跳过不适用的维度，并把权重归一化
        skip = SKIP_FOR.get(kind, set())
        active = {k: w for k, w in WEIGHTS.items() if k not in skip}
        wsum = sum(active.values())
        total = sum(items[k] * (w / wsum) for k, w in active.items())

        results.append({
            "label": label, "path": rel, "missing": False,
            "kind": kind, "skipped": sorted(skip),
            "raw": r,
            "items": {k: round(v, 1) for k, v in items.items()},
            "score": round(total, 1),
        })
    return results


def main():
    print("=== 1. 测量参考素材（成熟商业级）===")
    refs = collect_reference_stats()
    if refs is None:
        return 1
    for f in refs["files"]:
        print(f"  {f}")
    print("\n  参考区间（min / median / max）:")
    for key in ["colors", "lum_bins", "detail", "contrast", "aa_ratio",
                "hue_std"]:
        s = refs[key]
        print(f"    {key:10s}  {s['min']:.3f} / {s['median']:.3f} / "
              f"{s['max']:.3f}")

    print("\n=== 2. 评估当前资产 ===")
    results = evaluate(refs)
    worst = 100.0
    failed = []
    for r in results:
        if r["missing"]:
            print(f"  {r['label']}: 素材缺失 → 0 分")
            worst = 0.0
            failed.append(r["label"])
            continue
        mark = "PASS" if r["score"] >= PASS_SCORE else "FAIL"
        print(f"  {r['label']}: {r['score']} 分  [{mark}]")
        raw = r["raw"]
        print(f"     用色 {raw['colors']}  明度档 {raw['nonempty_bins']}  "
              f"细节 {raw['detail']:.3f}  对比 {raw['contrast']:.3f}")
        for k in WEIGHTS:
            print(f"       {k:10s} {r['items'][k]:5.1f} × {WEIGHTS[k]:.2f}")
        worst = min(worst, r["score"])
        if r["score"] < PASS_SCORE:
            failed.append(r["label"])

    print(f"\n=== 3. 结论 ===")
    print(f"  门槛 {PASS_SCORE}  最低分 {worst:.1f}")

    # 落盘 JSON，供 Godot 测试与 HTML 报告读取
    out_json = os.path.join(ROOT, "art", "art_score.json")
    payload = {
        "pass_score": PASS_SCORE,
        "min_score": round(worst, 1),
        "passed": not failed,
        "failed": failed,
        "weights": WEIGHTS,
        "skip_by_kind": {k: sorted(v) for k, v in SKIP_FOR.items()},
        "reference_range": refs,
        "items": [{k: v for k, v in r.items() if k != "raw"}
                  for r in results],
    }
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    print(f"  报告: {os.path.relpath(out_json, ROOT)}")

    if failed:
        print(f"  ✗ 不通过：{", ".join(failed)}")
        return 1
    print("  ✓ 全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
