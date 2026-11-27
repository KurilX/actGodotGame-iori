"""全量铺帧：为 82 个游戏帧生成 9 批锚定九宫格请求。

批分配（每批 9 格，动作词组内连贯）：
  batch_idle  : idle 0-7 + land_5        （待机 8 + 收招 1）
  batch_run   : run 0-7 + jump_1          （跑步 8 + 空中过渡 1）
  batch_atk1  : atk1 0-5 + atk2 0-2       （轻1 全 6 + 轻2 前 3）
  batch_atk2  : atk2 3-5 + atk3 0-5       （轻2 后 3 + 轻3 全 6）
  batch_atk4  : atk4 0-5 + dash 0-2       （轻4 全 6 + 闪避前 3）
  batch_heavy : heavy1 0-5                （重1 前 6）
  batch_heavy2: heavy1 6-7 + heavy2 0-6   （重1 尾 2 + 重2 前 7）
  batch_heavy3: heavy2 7 + heavy3 0-7     （重2 尾 1 + 重3 全 8）
  batch_misc  : gain 0-5 + land 0-4      （拾取 6 + 落地前 5）
  batch_jump  : jump 0-2 + land 0-5 重生成备用

简化：每批 prompt 列 9 个动作短语，动作词用"描述性短语"（如
'站立呼吸（身体微微起伏）'），让 AI 自行发挥。
"""

import json
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
BRIDGE = ROOT / "tools" / "ark_skill_bridge.js"
NODE = r"D:\tools\nodejs\node-v24.19.0-win-x64\node.exe"
OUT = ROOT / "docs/refs/ai/poses_full"
OUT.mkdir(exist_ok=True)

BATCHES = [
    ("b1_idle", [
        "站立呼吸（身体微微起伏）", "站立呼吸（另一帧）", "站立眨眼",
        "站立微笑", "站立呼吸（头发轻飘）", "站立呼吸（另一帧）",
        "站立眨眼（另一帧）", "站立收势", "轻轻弯腰行礼"]),
    ("b2_run", [
        "跑步（迈左腿）", "跑步（腾空）", "跑步（迈右腿）", "跑步（后蹬）",
        "跑步（迈左腿另一帧）", "跑步（腾空另一帧）", "跑步（迈右腿另一帧）",
        "跑步（后蹬另一帧）", "小跳"]),
    ("b3_atk12", [
        "轻挥剑起手", "轻挥剑上撩", "轻挥剑横斩", "轻挥剑收势",
        "轻挥剑（另一角度）", "轻挥剑结束", "第二段连斩起手",
        "第二段连斩横扫", "第二段连斩收"]),
    ("b4_atk23", [
        "第二段连斩（续）", "第三段突刺起手", "第三段突刺", "第三段突刺收",
        "第三段收剑", "轻挥剑重置", "回剑入鞘", "拔剑", "警戒姿势"]),
    ("b5_atk4dash", [
        "第四段回旋斩起手", "第四段回旋斩", "第四段回旋斩收", "第四段结束",
        "第四段收剑", "第四段重置", "闪避翻滚（团身）", "闪避滑步", "闪避起身"]),
    ("b6_heavy1", [
        "重击蓄力（举剑过肩）", "重击蓄力（蓄力加深）", "重击蓄力（蓄满绷紧）",
        "重击挥砍（下劈）", "重击挥砍（命中）", "重击挥砍（跟随）",
        "重击收势（喘息）", "重击收势（直起）", "重击重置"]),
    ("b7_heavy2", [
        "重击收势（另两帧）", "二段重击起手（举剑反手）", "二段重击蓄力",
        "二段重击上撩", "二段重击腾空", "二段重击收", "二段重击重置",
        "二段重击喘息", "持剑站立"]),
    ("b8_heavy3", [
        "三段重击（泰山压顶起跳）", "三段重击（空中）", "三段重击（下砸）",
        "三段重击（落地震地）", "三段重击（扬尘）", "三段重击（起身）",
        "三段重击（收剑）", "三段重击（重置）", "疲惫站立"]),
    ("b9_misc", [
        "双手接住道具", "举高道具", "抱住道具开心", "收起道具",
        "拍拍手", "行礼结束", "落地缓冲（屈膝）", "落地起身",
        "站稳"]),
]

REFS = (str(ROOT / "tools/_anchor_head_small.jpg") + "|" +
        str(ROOT / "tools/_ref_base_small.jpg") + "|" +
        str(ROOT / "tools/_ref_small.jpg"))

HEAD = ("像素风格。第一张参考图是角色头部特写（发型轮廓、五官位置必须与它完全一致，"
        "一个像素都不要改），第二张是角色全身标准立绘（身体与服装以此为准），"
        "第三张是像素画风示例。"
        "生成 3×3 动作格子图：九个格子整齐排列，每格是同一个角色"
        "（绿发丸子头、深蓝斗篷的女孩）的全身动作，"
        "角色头部大小与第一张参考图一致（放大到格子填满），"
        "像素颗粒密度与参考图完全一致（粗大的方块状像素，不要画细）。"
        "动作从左到右、从上到下依次是：")

TAIL = ("纯黑背景，格子之间用细的深色分隔线，无渐变无抗锯齿。"
        "所有格子里的角色都是同一个人，只有动作不同")


def run_batch(name: str, actions: list[str]) -> Path | None:
    prompt = HEAD + "；".join(actions) + "。" + TAIL
    pf = ROOT / "tools" / f"_prompt_{name}.txt"
    pf.write_text(prompt, encoding="utf-8")
    cmd = [NODE, str(BRIDGE), str(pf), REFS, str(OUT), "false"]
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=300)
    out = (r.stdout or "") + (r.stderr or "")
    for line in out.splitlines():
        if line.startswith("SAVED "):
            src = Path(line.split(" ", 1)[1].split(" ")[0].strip('"'))
            if not src.exists():
                # bridge 的保存路径可能带工作目录歧义 → 扫 Desktop Seedream 目录
                desk = Path(r"C:\Users\zepeng.huang\Desktop\Seedream-Images")
                cands = sorted(desk.rglob("seedream_*.jpg"),
                               key=lambda p: p.stat().st_mtime)
                if cands:
                    src = cands[-1]
            dst = OUT / f"{name}_raw.jpeg"
            dst.write_bytes(src.read_bytes())
            print(f"{name}: {dst.stat().st_size//1024} KB")
            return dst
    print(f"{name}: FAILED")
    print(out[-400:])
    return None


if __name__ == "__main__":
    only = sys.argv[1] if len(sys.argv) > 1 else None
    for name, actions in BATCHES:
        if only and name != only:
            continue
        raw = OUT / f"{name}_raw.jpeg"
        if raw.exists():
            print(f"{name}: skip (exists)")
            continue
        run_batch(name, actions)
