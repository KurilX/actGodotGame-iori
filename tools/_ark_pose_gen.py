"""动作差分：3×3 姿态格子（V4 配方复用），并切出接入帧。

姿态词极简（表情 V3 的教训）：站立、走路、跳跃、下落、挥砍、
重击、受伤、闪避、胜利。
密度锁定 + 18px 网格对齐同 V4。
"""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "refs" / "ai" / "poses"

PROMPT = (
    "像素风格。第一张参考图是角色的标准立绘，第二张参考图是像素画风示例。"
    "生成 3×3 动作差分格子图：九个格子整齐排列，每格是同一个角色"
    "（绿发丸子头、深蓝斗篷的女孩）的全身动作，"
    "角色头部大小与第一张参考图立绘中的头部一样大，"
    "像素颗粒密度与参考图完全一致（粗大的方块状像素，不要画细）。"
    "动作从左到右、从上到下：站立、走路、跳跃、下落、挥剑、"
    "重击蓄力、受伤后仰、闪避滑步、胜利举手。"
    "纯黑背景，格子之间用细的深色分隔线，无渐变无抗锯齿"
)

with open(ROOT / "tools" / "_prompt_pose.txt", "w", encoding="utf-8") as f:
    f.write(PROMPT)
print("prompt written")
