"""生成刀光贴图序列（这是第 4 次实现，方案改为贴图驱动）。

为什么放弃 Node2D._draw：
  实测 _draw 里的 draw_rect / draw_polyline 在 root viewport +
  canvas_items stretch 下画不出来（节点状态、位置、z_index、visible 全对，
  但最终画面里没有内容）。连续试了 4 个版本都没解决，
  所以改用像素游戏最常规的做法：预先画好贴图，用 Sprite2D 播放。

输出：art/fx/slash/seg{1..4}_{0..2}.png，每帧 48x48，锚点在帧中心
      4 段分别对应轻攻击四连，各 3 帧（起 → 盛 → 衰）
"""

import math
import os

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "art", "fx", "slash")

SIZE = 64
# 弧心位置（贴图像素坐标）。
# 贴图以**中心**为锚点贴在角色原点偏上处，所以：
#   CX=24 表示弧心正对角色身上（水平居中）
#   CY=24 表示弧心在贴图垂直中心
# 弧线在角色「身前」展开，靠的是角度范围（围绕 0°/正右），而不是把弧心挪前面。
CX, CY = 32.0, 26.0

# 色板（与 art/palette.gpl 一致）
ARC_LIGHT = (0xB9, 0xF2, 0xFF)   # 丝线光
ARC_HOT = (0xFF, 0x7A, 0x9C)     # 危险/弹幕
ARC_CORE = (0xFF, 0xFF, 0xFF)    # 内芯高光

# 每段：(半径, 起始角, 终止角, 粗细, 颜色)
# 角度基准 0°=正右，-90°=正上，90°=正下（y 向下）
# 与 player.gd 的 SLASH_FX 保持一致，四段轨迹各不相同：
SEGMENTS = [
    (20.0, 80.0, -100.0, 2.6, ARC_LIGHT),    # 第1段 上挑（竖直上撩）
    (22.0, -30.0, 35.0, 2.8, ARC_LIGHT),    # 第2段 横斩（窄而平）
    (24.0, -6.0, 6.0, 3.0, ARC_LIGHT),      # 第3段 突刺（近直线）
    (26.0, -95.0, 100.0, 3.6, ARC_HOT),    # 第4段 跳劈（头顶→身前下方）
]

# 每段的 3 帧：(扫过的角度比例上限, 整体亮度)
FRAMES = [
    (0.55, 1.00),    # 起：只扫出一半
    (1.00, 0.95),    # 盛：全弧
    (1.00, 0.55),    # 衰：全弧但变暗（收势残影）
]


def draw_slash(radius, a0, a1, thick, color, cover, bright):
    """画一帧刀光。

    用「按像素求极坐标」的方式填像素，而不是画线：
    对每个像素算它到弧心的距离与角度，落在环带内就填色。
    这样弧线边缘天然对齐像素网格，不会出现半像素毛边。
    """
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    px = img.load()

    span = (a1 - a0) * cover
    for y in range(SIZE):
        for x in range(SIZE):
            dx = x + 0.5 - CX
            dy = y + 0.5 - CY
            dist = math.hypot(dx, dy)

            # 环带判定
            if abs(dist - radius) > thick * 0.5:
                continue

            ang = math.degrees(math.atan2(dy, dx))

            # 归一到 a0..a0+span 区间（处理跨 ±180 的情况）
            rel = ang - a0
            while rel > 180.0:
                rel -= 360.0
            while rel < -180.0:
                rel += 360.0

            direction = 1.0 if span >= 0 else -1.0
            progress = rel / span if span != 0 else 0.0
            if direction > 0:
                inside = 0.0 <= rel <= span
            else:
                inside = span <= rel <= 0.0
            if not inside:
                continue

            # 亮度渐变方向：**终点最亮（刀锋当前所在处），起点最淡（尾迹）**。
            # 早期写成 `fade = 1 - abs(progress)*0.55`，t=0 在起点，
            # 结果亮部留在起始角度上 —— 跳劈（-115°→95°）的亮部就跑去头顶，
            # 看起来像「从下往上撩」，方向整个反了。
            # 正确做法：朝扫过的方向越走越亮。
            head = abs(progress)          # 0 = 起点，1 = 终点
            fade = 0.35 + head * 0.65
            # 环带中心最亮（内芯），边缘稍暗
            band = 1.0 - abs(dist - radius) / (thick * 0.5)
            core = band > 0.55

            a = int(255 * bright * fade * min(1.0, 0.55 + band * 0.45))
            if a <= 12:
                continue
            c = ARC_CORE if (core and color is not ARC_HOT) else color
            px[x, y] = (c[0], c[1], c[2], a)

    return img


def main():
    os.makedirs(OUT, exist_ok=True)
    total = 0
    for si, (radius, a0, a1, thick, color) in enumerate(SEGMENTS, start=1):
        for fi, (cover, bright) in enumerate(FRAMES):
            img = draw_slash(radius, a0, a1, thick, color, cover, bright)
            path = os.path.join(OUT, f"seg{si}_{fi}.png")
            img.save(path)
            total += 1
        print(f"第 {si} 段: 3 帧 (r={radius}, {a0}°→{a1}°)")
    print(f"共 {total} 张刀光贴图 -> art/fx/slash/")


if __name__ == "__main__":
    main()
