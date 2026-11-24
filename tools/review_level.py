"""关卡设计 Review：调用 LLM 分析关卡质量。

## 为什么要这个脚本

靠人眼反复看 ASCII 图容易漏问题。这个脚本把**客观数据 + 地图本身**
喂给 LLM，让它按三个固定维度打分并给出具体修改建议：

  1. **视觉美观 / 是否有断层** —— 地形是否连续、有没有突兀的悬空块
  2. **高低落差是否合理** —— 爬坡之后是否立刻下坡（无效辛苦）
  3. **对照成熟类银河恶魔城** —— 引用 Hollow Knight / Ori / Metroid
     的具体设计手法作为参考答案

## 输入给 LLM 的东西

  · ASCII 地图原图（LLM 能直接"看懂"形状）
  · 客观统计（地形块数、高差分布、跳跃可达性）
  · 当前设计原则（让它按我们的标准评价，而不是泛泛而谈）

## 输出

  · 终端打印结构化建议
  · 写入 `docs/level-review.md`

## 用法

    python tools/review_level.py
    python tools/review_level.py --model glm-5.3
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LVL = os.path.join(ROOT, "levels", "tutorial.lvl")
JSON_PATH = os.path.join(ROOT, "levels", "tutorial.json")
OUT_MD = os.path.join(ROOT, "docs", "level-review.md")

# 跳跃极限（实测）。地形相邻可站表面高差超过它 = 跳不上去的死地形。
JUMP_HEIGHT = 58.0
CELL = 20

# 策划用模型：opus 位对应更强的推理模型
DEFAULT_MODEL = "deepseek-v4.1-flash"


def api_config():
    """从环境变量读网关配置。缺失时给出可操作的提示。"""
    base = os.environ.get("ANTHROPIC_BASE_URL", "").rstrip("/")
    token = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
    if not base or not token:
        print("缺少环境变量 ANTHROPIC_BASE_URL / ANTHROPIC_AUTH_TOKEN",
              file=sys.stderr)
        print("示例（PowerShell）：", file=sys.stderr)
        print('  $env:ANTHROPIC_AUTH_TOKEN="sk-..."', file=sys.stderr)
        print('  $env:ANTHROPIC_BASE_URL="http://127.0.0.1:3088/'
              'codebuddy/anthropic"', file=sys.stderr)
        sys.exit(2)
    # 结尾不能带 /v1，否则会拼成 /v1/v1/messages 报 404
    if base.endswith("/v1"):
        base = base[:-3]
    return base, token


# 多模型 fallback 链。
#
# 实测（2026-11-24，网关 3088）：同一份 prompt 在不同模型上的成功率差别很大，
# 而且**同一个模型重复调用也可能时而成功、时而返回空正文**
# （stop_reason=max_tokens 但 text 为空）。这不是我们的 bug，是上游的不稳定
# 行为，所以只能：依次试多个模型 + 每个重试几次。
FALLBACK_MODELS = ["kimi-k3-1", "glm-5.3", "glm-5.3-flash", "deepseek-v4-pro", "minimax-m3.1-flash", "hy4flash"]
MAX_RETRIES = 4



def _looks_complete(text):
    """检查回答是否包含三个部分，且提到了参考游戏。

    返回 False 表示这份回答不完整（被截断或没答全），应当重试。
    """
    # 三个部分：模型通常用「一/二/三」或「1./2./3.」分节
    import re
    parts = 0
    for pat in (r"一[、,，.]", r"二[、,，.]", r"三[、,，.]"):
        if re.search(pat, text):
            parts += 1
    if parts < 3:
        # 也接受 ## 一 / 1. 这类写法
        parts = sum(1 for p in (r"#+\s*一", r"#+\s*二", r"#+\s*三",
                                r"^\s*1[\.\、]", r"^\s*2[\.\、]",
                                r"^\s*3[\.\、]")
                    if re.search(p, text, re.M))
    if parts < 3:
        return False
    # 必须提到至少一个参考游戏（第三部分的实质内容）
    games = ["空洞骑士", "奥日", "银河战士", "死亡细胞", "渎神",
             "Hollow", "Ori", "Metroid", "Dead Cells", "Blasphemous"]
    return any(g in text for g in games)
def call_llm_with_fallback(base, token, prompt, preferred=None,
                           max_tokens=8000, images=None):
    """按 fallback 链尝试多个模型，返回 (text, model_used)。"""
    order = []
    if preferred:
        order.append(preferred)
    for m in FALLBACK_MODELS:
        if m not in order:
            order.append(m)

    for model in order:
        for attempt in range(MAX_RETRIES):
            text = call_llm(base, token, model, prompt, max_tokens,
                            images=images)
            # 质量门槛 + **完整性校验**。
            #
            # 只判长度不够：曾经有一份回答写到了 2000 多字符，
            # 但在"见第三部分银河…"处被截断，第三部分完全缺失，
            # 却因为长度达标被当成成功。
            # 所以额外要求：必须能匹配到三个部分的小标题，
            # 且必须提到至少一个参考游戏。
            if text and len(text.strip()) >= 200 and _looks_complete(text):
                return text, model
            if text:
                short = len(text.strip())
                print("  %s 第 %d 次只返回 %d 字符，视为退化，重试..."
                      % (model, attempt + 1, short))
            else:
                print("  %s 第 %d 次返回空，重试..." % (model, attempt + 1))
    return None, None


def _encode_image(path):
    """把图片编码成 Anthropic 的 base64 image block。"""
    import base64
    with open(path, "rb") as f:
        data = base64.b64encode(f.read()).decode("ascii")
    ext = os.path.splitext(path)[1].lower()
    media = {".png": "image/png", ".jpg": "image/jpeg",
             ".jpeg": "image/jpeg"}.get(ext, "image/png")
    return {"type": "image",
            "source": {"type": "base64", "media_type": media,
                       "data": data}}


def call_llm(base, token, model, prompt, max_tokens=8000, images=None):
    """调用 Anthropic Messages 协议。返回文本。

    images: 可选图片路径列表。**实测网关支持图片输入**，
    所以可以把参考地图真的传给模型看，而不是只给它文件名。
    """
    url = base + "/v1/messages"
    if images:
        content = [_encode_image(p) for p in images]
        content.append({"type": "text", "text": prompt})
    else:
        content = prompt
    body = json.dumps({
        "model": model,
        "max_tokens": max_tokens,
        "temperature": 0.3,
        "messages": [{"role": "user", "content": content}],
    }).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "x-api-key": token,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:500]
        print(f"HTTP {e.code}: {detail}", file=sys.stderr)
        return None
    except Exception as e:  # noqa: BLE001
        print(f"请求失败：{e}", file=sys.stderr)
        return None

    # 兼容两种返回结构
    # 兼容两种返回结构
    if "content" in data:
        parts = []
        for blk in data["content"]:
            if isinstance(blk, dict) and blk.get("type") == "text":
                parts.append(blk.get("text", ""))
        text = "".join(parts)
        # **必须检查截断**：stop_reason == "max_tokens" 表示回答没说完。
        # 之前完全没看这个字段，结果一份被截断在"见第三部分银河"的回答
        # 被当成成功写入文件 —— 第三部分（参考成熟游戏）根本不存在。
        if data.get("stop_reason") == "max_tokens":
            print("  [截断] 回答未完成（stop_reason=max_tokens），当作失败",
                  file=sys.stderr)
            return None
        return text
    return str(data)


def read_map():
    """从 .lvl 抽出地图行（只含地图字符的行）。"""
    rows = []
    section = None
    with open(LVL, encoding="utf-8") as f:
        for raw in f:
            s = raw.strip()
            if s.startswith("[") and s.endswith("]"):
                section = s[1:-1]
                continue
            if section != "map":
                continue
            if not s:
                continue
            if all(c in "#=.PBblsT" for c in s):
                rows.append(s)
    return rows


def analyze(rows):
    """算出客观指标，供 LLM 参考（也顺便打印给人看）。"""
    h = len(rows)
    w = len(rows[0]) if rows else 0
    solid = sum(r.count("#") for r in rows)
    oneway = sum(r.count("=") for r in rows)

    with open(JSON_PATH, encoding="utf-8") as f:
        data = json.load(f)
    solids = data.get("solids", [])

    # 可站表面（宽度够站人、不是天花板/边界）
    surfaces = []
    for s in solids:
        x, y, sw, sh = s
        if sw >= 40 and y > 20:
            surfaces.append((y, x, sw))
    surfaces.sort()

    # 相邻高差
    gaps = []
    for i in range(1, len(surfaces)):
        gaps.append(abs(surfaces[i][0] - surfaces[i - 1][0]))

    return {
        "width": w,
        "height": h,
        "cells": w * h,
        "solid_cells": solid,
        "oneway_cells": oneway,
        "solid_rects": len(solids),
        "surfaces": surfaces,
        "gaps": gaps,
        "max_gap": max(gaps) if gaps else 0,
        "jump_height": JUMP_HEIGHT,
    }


def build_prompt(rows, stats):
    """构造给 LLM 的 prompt。

    ## 为什么必须压得这么短

    实测（2026-11-24，网关 3088 多模型）：

      · 单行 120 字符的地图 → 模型退化，stop_reason=max_tokens 但正文为空
      · prompt 超过约 3000 字符 → 同上
      · markdown 标题/列表/反引号 → 更容易触发

    稳定配置（实测 3 次 2 次成功）：
      · 地图横向压缩到每行 60 字符
      · 整个 prompt 约 1700 字符
      · 纯自然语言，不用 markdown

    **改这里之前先看上面这些数字**，写长了会直接跑不出结果。
    """
    COMPRESS = 2
    # **压缩时必须保留实体位置**。
    #
    # 直接写 r[::2] 会丢掉所有奇数列 —— 实测 BOSS 出生点 B、
    # 两只石守 s 都落在奇数位，压缩后整个消失，LLM 看到的是
    # 一张没有 BOSS、没有石守的地图，分析结论自然偏掉。
    #
    # 做法：先把实体"吸附"到最近的偶数列，再做压缩。
    comp_rows = []
    for r in rows:
        chars = list(r)
        for i, ch in enumerate(chars):
            if ch in "PBlsTb" and i % COMPRESS != 0:
                # 往左吸一个（若左边是空气），否则往右
                if i - 1 >= 0 and chars[i - 1] == ".":
                    chars[i - 1] = ch
                    chars[i] = "."
                elif i + 1 < len(chars) and chars[i + 1] == ".":
                    chars[i + 1] = ch
                    chars[i] = "."
        comp_rows.append("".join(chars[::COMPRESS]))
    map_text = "\n".join(comp_rows).replace("#", "X")
    gaps_desc = "、".join(str(g) for g in stats["gaps"]) or "无"

    return f"""你是资深横版动作游戏关卡设计师。请审查我们的关卡图。

X是实心地形，等号是单向平台，点是空气，P是玩家出生点，
B是BOSS，b苔团，l灯笼虫，s石守，T木桩。
左边起点，右边BOSS房。已横向每2列取1列压缩，每行{stats['width'] // COMPRESS}字符。

{map_text}

玩家身高48像素，跳跃高度58像素。相邻可站表面高差依次是{gaps_desc}像素。

我们的原则：每个地形都要有存在的理由，爬上去要有回报。

【参考真实地图】
我们手上有空骑士（Hollow Knight）的官方地图剪影，文件在 docs/refs/：
  hk_white_palace_1.png  左侧长走廊 + 竖直塔 + 顶部独立房间
  hk_white_palace_3.png  垂直塔状结构 + 横向支路分叉
  hk_white_palace_5.png  多层横向平台 + 陡峭的锯齿边缘
  hk_godhome_1.png       最复杂：多层横向平台 + 多个竖直连接 + 独立岛房间
这些图的特点是**每个竖直攀爬的终点都是独立房间或有内容的平台**，
从来不是"爬上去看看然后跳回来"。

请回答三个问题，每个先给判断再列具体问题：
一，地形是否连续、有无突兀悬空块、画面是否显得乱。
二，高低落差是否合理，特别检查有没有爬坡之后立刻下坡的无效设计，
有的话指出在哪一列、该怎么改；并指出哪些高差跳上去没意义。
三，参考空洞骑士、奥日、银河战士、死亡细胞的具体手法说明怎么改。

建议要具体到列号，能直接改字符地图。最后给优先级最高的三个改动。
"""
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=os.environ.get(
        "ANTHROPIC_DEFAULT_OPUS_MODEL", DEFAULT_MODEL))
    ap.add_argument("--dry", action="store_true",
                    help="只打印统计和 prompt，不调 LLM")
    args = ap.parse_args()

    if not os.path.exists(LVL):
        print(f"找不到关卡文件 {LVL}", file=sys.stderr)
        return 1
    if not os.path.exists(JSON_PATH):
        print(f"找不到 {JSON_PATH}，先跑 python tools/build_level.py",
              file=sys.stderr)
        return 1

    rows = read_map()
    if not rows:
        print("地图为空", file=sys.stderr)
        return 1
    stats = analyze(rows)

    print("=== 关卡客观统计 ===")
    print(f"  网格 {stats['width']}x{stats['height']}")
    print(f"  实心矩形 {stats['solid_rects']} 块")
    print(f"  可站表面 {len(stats['surfaces'])} 处")
    print(f"  相邻高差 {stats['gaps']}")
    print(f"  最大高差 {stats['max_gap']}px / 跳跃极限 {JUMP_HEIGHT}px")

    prompt = build_prompt(rows, stats)

    if args.dry:
        print("\n=== PROMPT（dry run）===")
        print(prompt)
        return 0

    base, token = api_config()
    print(f"\n调用模型（首选 {args.model}，失败会自动换）...")
    # 收集参考图（docs/refs 下的空骑士地图剪影）
    refs = []
    ref_dir = os.path.join(ROOT, "docs", "refs")
    if os.path.isdir(ref_dir):
        for fn in sorted(os.listdir(ref_dir)):
            if fn.lower().endswith((".png", ".jpg", ".jpeg")):
                refs.append(os.path.join(ref_dir, fn))
    if refs:
        print(f"附带 {len(refs)} 张参考地图")
    else:
        print("没有参考图（docs/refs 为空），只做纯文本分析")

    text, used = call_llm_with_fallback(base, token, prompt,
                                        preferred=args.model,
                                        images=refs or None)
    if not text:
        print("所有模型都没返回内容。网关可能不稳定，稍后重试。",
              file=sys.stderr)
        return 1
    print(f"（实际使用 {used}）")
    args.model = used

    print("\n" + "=" * 60)
    print(text)
    print("=" * 60)

    os.makedirs(os.path.dirname(OUT_MD), exist_ok=True)
    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("# 关卡设计 Review\n\n")
        f.write(f"> 由 `tools/review_level.py` 调用 `{args.model}` 生成\n\n")
        f.write("## 客观统计\n\n")
        f.write(f"- 网格 {stats['width']}x{stats['height']}\n")
        f.write(f"- 实心矩形 {stats['solid_rects']} 块\n")
        f.write(f"- 相邻高差 {stats['gaps']}\n")
        f.write(f"- 最大高差 {stats['max_gap']}px"
                f"（跳跃极限 {JUMP_HEIGHT}px）\n\n")
        # 注意：**写入文件的 markdown 可以用代码围栏**（给人看），
        # 但送进 prompt 的不能带围栏 —— 实测会让模型输出空内容。
        f.write("## 地图\n\n```\n")
        f.write("\n".join(rows))
        f.write("\n```\n\n")
        f.write("## LLM 分析\n\n")
        f.write(text)
    print(f"\n已写入 {OUT_MD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
