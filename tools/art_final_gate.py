"""美术终审：合并数值分与 AI 分，做最终放行判定。

## 为什么要两个都过

数值指标和 AI 打分测的是**不同的东西**，缺一不可：

  · 数值指标测「有没有画」
    实测：我们的山层只有 1~2 种颜色，参考素材 15~115 种。
    这种差距机器能精确量化，AI 反而会说"风格化"。

  · AI 视觉测「画得对不对」
    实测：数值分全部 70+ 通过，但 AI 只给 53~69 分，指出
    「地形是大面积灰蓝纯色块」「像未完成的灰盒块」「悬空物件」
    —— 这些是统计数据看不出来的。

**所以两项各自有门槛，合并分再有一道门槛。**

## 合并公式

    final = 数值分 × 0.55 + AI 分 × 0.45

数值分更客观（可复现），权重略高；AI 分带主观判断但能抓住观感问题。

## 三道门

  1. 数值分 ≥ NUMERIC_MIN（每项资产都要过）
  2. AI 分 ≥ AI_MIN（每张截图都要过）
  3. 合并分 ≥ FINAL_MIN

任何一道不过，整体判定 REJECTED。
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NUMERIC_JSON = os.path.join(ROOT, "art", "art_score.json")
AI_JSON = os.path.join(ROOT, "art", "ai_score.json")
OUT = os.path.join(ROOT, "art", "final_score.json")

# 三道门
NUMERIC_MIN = 70.0
AI_MIN = 55.0
FINAL_MIN = 68.0

# 合并权重
W_NUMERIC = 0.55
W_AI = 0.45


def load(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    numeric = load(NUMERIC_JSON)
    ai = load(AI_JSON)

    problems = []
    if numeric is None:
        problems.append("缺 art/art_score.json（先跑 art_review.py）")
    if ai is None:
        problems.append("缺 art/ai_score.json（先跑 ai_art_score.py）")
    if problems:
        for p in problems:
            print("  ✗ " + p, file=sys.stderr)
        return 1

    num_min = float(numeric.get("min_score", 0.0))
    num_ok = num_min >= NUMERIC_MIN

    # AI：每张截图都要过 AI_MIN，取最低
    ai_targets = ai.get("targets", [])
    valid_ai = [t for t in ai_targets if not t.get("failed")]
    ai_min = min((float(t["total"]) for t in valid_ai), default=0.0)
    ai_avg = (round(sum(float(t["total"]) for t in valid_ai) / len(valid_ai), 1)
              if valid_ai else 0.0)
    ai_ok = ai_min >= AI_MIN and len(valid_ai) == len(ai_targets)

    # 用数值"最低分"与 AI"最低分"配对，而不是平均对平均 ——
    # 避免某一项很差但被其他项的成绩拉平。
    final = round(num_min * W_NUMERIC + ai_min * W_AI, 1)
    final_ok = final >= FINAL_MIN

    passed = num_ok and ai_ok and final_ok

    print("=== 美术终审 ===")
    print(f"  数值分最低 {num_min:.1f}  （门槛 {NUMERIC_MIN:.0f}）"
          f"  {'PASS' if num_ok else 'FAIL'}")
    print(f"  AI 分最低  {ai_min:.1f}  （门槛 {AI_MIN:.0f}）"
          f"  {'PASS' if ai_ok else 'FAIL'}")
    print(f"  合并分     {final:.1f}  （门槛 {FINAL_MIN:.0f}）"
          f"  {'PASS' if final_ok else 'FAIL'}")
    print(f"    公式：{num_min:.1f}×{W_NUMERIC} + {ai_min:.1f}×{W_AI}")

    # 列出 AI 指出的具体问题，这是最有行动价值的部分
    if valid_ai:
        print("\n  AI 指出的具体问题：")
        for t in valid_ai:
            issue = t.get("top_issue", "").strip()
            if issue:
                flag = "!" if float(t["total"]) < AI_MIN else " "
                print(f"   {flag} [{t['total']:.0f}] {t['label']}：{issue}")

    payload = {
        "passed": passed,
        "numeric_min": num_min,
        "numeric_threshold": NUMERIC_MIN,
        "ai_min": ai_min,
        "ai_avg": ai_avg,
        "ai_threshold": AI_MIN,
        "final": final,
        "final_threshold": FINAL_MIN,
        "weights": {"numeric": W_NUMERIC, "ai": W_AI},
        "gates": {
            "numeric": num_ok,
            "ai": ai_ok,
            "final": final_ok,
        },
        "ai_targets": valid_ai,
        "numeric_items": numeric.get("items", []),
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    print(f"\n  输出 {OUT}")
    print(f"\n  {'✓ 通过' if passed else '✗ 不通过'}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
