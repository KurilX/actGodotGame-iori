"""背景分层生成：把 AI 背景拆成可独立平铺、可独立运动的图层。

## 为什么分层

单张 2400x540 的贴图无法做视差 —— 相机移动时背景整体跟着走，
远山近山同速，看起来就是一张贴在后面的画。

拆层之后每层可以有独立的：
  · 视差系数（远山 0.1，中山 0.3，近山 0.6，云 0.05）
  · 平铺周期（每层宽 480px 的一屏，横向循环）
  · 动画（云层横向漂移、月亮静止）

## 六层（从远到近）

  1. sky      纯垂直渐变，无平铺，视差 0（永远不动）
  2. moon     月亮，只画一次，固定于天空，视差 0
  3. cloud    AI 图的云/雾带，横向漂移，视差 0.05
  4. mtn_far  最远的山，视差 0.15
  5. mtn_mid  中山，视差 0.32
  6. mtn_near 近山，视差 0.55

## 从 AI 图拆解

源图 `docs/refs/ai/ai_bg_screen.png`（2048x1152，16:9，含三层山 + 月亮）。

按 y 坐标切出三个山层，各自：
  · 抠出山体（山脊以上透明）
  · 缩到一屏宽 480
  · 换掉源图的配色 → 项目 28 色板的紫色阶
  · 横向镜像拼接成双屏宽，保证无缝循环

月亮单独从源图抠出来（浅青色区域），做成独立小贴图。
"""

import json
import os
import sys

from PIL import Image, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "docs", "refs", "ai", "ai_bg_screen.png")
OUT = os.path.join(ROOT, "art", "bg")

# 一屏尺寸；每层横向平铺 2 次做循环
SCREEN_W, SCREEN_H = 480, 270

# 项目 28 色板里的紫色阶（从暗到亮）
# **全部统一在紫色系**。
#
# 第一版的低端是 #1B2244 / #2A3A63（蓝调），结果近山是一堵**蓝墙**，
# 和紫调的远山、中山脱节（实测近山主色 #2A3A63 明显偏蓝）。
# 现在把低端也改成紫调，整组形成从深紫到浅紫的连续过渡。
PURPLE_RAMP = [
    "#1A1030",   # 最深（近山底部）
    "#251844",
    "#332057",
    "#452A6E",   # 中段
    "#553580",
    "#6B4A96",
    "#7F5FAE",
    "#9678C4",   # 最亮（远山顶部）
]

MOON_COLORS = ("#8FD3E8", "#D8F0F8")


def hex_rgb(h):
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def load_source():
    im = Image.open(SRC).convert("RGBA")
    # 裁掉右下角水印
    w, h = im.size
    im = im.crop((0, 0, w - 200, h))
    return im


def erase_moon_from_source(im):
    """**在拆层之前把月亮（含光晕）从源图里擦掉。**

    ## 为什么必须在这里擦

    月亮及其光晕是画面里唯一的浅青色区域，亮度极高（~170）。
    拆山层时按亮度抠取，月亮的光晕会被当成"最亮的山"抠进去，
    再经过镜像拼接就变成**左右各一个圆环**（实测三层山每层都有两个环）。

    正确做法：拆层前就擦掉它，用周围的天空/山色填充。
    """
    px = im.load()
    W, H = im.size

    # 找月亮：浅青（G、B 都远高于 R）
    pts = []
    for y in range(0, H, 2):
        for x in range(0, W, 2):
            c = px[x, y]
            if c[3] > 0 and c[1] > 140 and c[2] > 140 and c[0] < c[1] * 0.85:
                pts.append((x, y))
    if not pts:
        print("  警告：源图里没找到月亮")
        return im

    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    cx = (min(xs) + max(xs)) // 2
    cy = (min(ys) + max(ys)) // 2
    r = max(max(xs) - min(xs), max(ys) - min(ys)) // 2 + 18   # 含光晕余量
    print(f"  擦除源图月亮：中心 ({cx},{cy}) 半径 {r}")

    # 用**同 y 行、圈外左右两侧**的颜色填充（天空在该行是横向均匀的）
    for y in range(max(0, cy - r), min(H, cy + r + 1)):
        dy2 = (y - cy) ** 2
        left_c = None
        for dx in range(r + 2, r + 220):
            xl = cx - dx
            if 0 <= xl < W:
                c = px[xl, y]
                if c[3] > 0:
                    left_c = c
                    break
        right_c = None
        for dx in range(r + 2, r + 220):
            xr = cx + dx
            if 0 <= xr < W:
                c = px[xr, y]
                if c[3] > 0:
                    right_c = c
                    break
        # **填充色必须与该行原有的天空完全一致，不能插值。**
        #
        # 第一版用左右两侧线性插值，但月亮所在的 y 行左右颜色本来就不同
        #（天空有横向渐变），插值后在原月亮位置留下**一圈色差圆环**，
        # 拆山层时被当成"亮度异常区"抠进中山和近山。
        #
        # 正确做法：取该行**紧邻圆外侧的 3 个采样点**，用它们的**中位数**
        # 作为填充色 —— 中位数对局部色差鲁棒，且不会引入渐变。
        cand = []
        for dx in (r + 3, r + 8, r + 16):
            for xl in (cx - dx, cx + dx):
                if 0 <= xl < W:
                    c = px[xl, y]
                    if c[3] > 0:
                        cand.append((c[0], c[1], c[2]))
        if cand:
            cand.sort(key=lambda t: t[0] + t[1] + t[2])
            col = cand[len(cand) // 2]
        else:
            col = (30, 26, 44)
        for x in range(max(0, cx - r), min(W, cx + r + 1)):
            if (x - cx) ** 2 + dy2 <= r * r:
                px[x, y] = (*col, 255)
    return im


def is_moonish(c):
    return c[1] > 140 and c[2] > 140 and c[0] < c[1] * 0.85


def extract_moon(im):
    """从源图抠出月亮：返回 (rgba 小图, (cx, cy)) 或 (None, None)。"""
    px = im.load()
    W, H = im.size
    pts = [(x, y) for y in range(0, H, 2) for x in range(0, W, 2)
           if px[x, y][3] > 0 and is_moonish(px[x, y])]
    if not pts:
        return None, None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    x0, x1 = min(xs) - 6, max(xs) + 7
    y0, y1 = min(ys) - 6, max(ys) + 7
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(W, x1), min(H, y1)

    # 缩到 1/8 做成像素月亮
    crop = im.crop((x0, y0, x1, y1))
    # 月亮直径约屏幕高的 1/10（270/10≈27），取 14px
    tw = th = 14
    small = crop.resize((tw, th), Image.LANCZOS)

    # 只保留月亮本体（浅青）+ 光晕（稍暗一圈），其余透明
    out = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    sp = small.load()
    op = out.load()
    cx, cy = tw / 2.0, th / 2.0
    r = min(tw, th) / 2.0
    core = hex_rgb(MOON_COLORS[1])
    halo = hex_rgb(MOON_COLORS[0])
    # **月亮只画"核心 + 一圈光晕"两层，其余全透明。**
    #
    # 第一版把整个裁剪框都填了色，导致画面里出现"一个青色点 +
    # 一个紫色球"两个月亮的错觉 —— 那个紫球其实是光晕被错误填充了。
    #
    # 月球半径 r 是根据裁剪框算的，但裁剪框含了 6px 边距，
    # 所以真正的月球半径应取 min(tw,th)//2 - 3。
    for y in range(th):
        for x in range(tw):
            d = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
            if d <= r * 0.55:
                op[x, y] = (*core, 255)
            elif d <= r * 0.78:
                op[x, y] = (*halo, 255)
            # 其余保持透明，不再填充
    return out, (cx, cy)


def quantize_ramp(img, ramp):
    """把一个图层量化到给定的紫色阶（保留 alpha）。"""
    pal = [hex_rgb(h) for h in ramp]
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ip = img.load()
    op = out.load()
    W, H = img.size
    for y in range(H):
        for x in range(W):
            c = ip[x, y]
            if c[3] < 40:
                continue
            # 按亮度映射到色阶
            lum = c[0] * 0.299 + c[1] * 0.587 + c[2] * 0.114
            idx = int(lum / 255.0 * (len(pal) - 1) + 0.5)
            idx = max(0, min(len(pal) - 1, idx))
            op[x, y] = (*pal[idx], 255)
    return out


def extract_layer(im, ridge_frac, ramp):
    """按**山脊高度**提取一层完整山体，整块填纯色。

    ## 为什么不能按亮度取

    第一版按亮度区间（如 58~68）取像，但源图山体**内部亮度有起伏**
    （同一块山既有 55 也有 65），结果取出来是**紫色和蓝色交错的碎斑**，
    像等高线地图，完全不是岩石剪影（实测）。

    ## 正确做法

    山是**实心的块**，语义是"从山脊线以下全是山"。所以：
      1. 对每一列，从下往上找**天空与山的边界**（亮度突变点）= 山脊高度
      2. 山脊以下整列填同一个颜色
      3. 每一层用不同的"山脊高度偏移 + 色阶"区分远近
    """
    W, H = im.size
    hill_only = im.crop((0, int(H * 0.62), W, H))
    W, H = hill_only.size
    ratio = SCREEN_W / W
    small = hill_only.resize((SCREEN_W, int(H * ratio)), Image.LANCZOS)
    sw, sh = small.size
    sp = small.load()

    pal = [hex_rgb(h) for h in ramp]
    body = pal[len(pal) // 2]        # 山体主色
    edge = pal[min(len(pal) - 1, len(pal) // 2 + 1)]   # 山脊高光

    out = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
    op = out.load()

    # **阈值必须从源图实际亮度分布推出来，不能拍脑袋。**
    #
    # 第一版写 thresh = sum(body)/3 + 6，其中 body 是**色板**里的紫色
    # （亮度 ~90），而源图山体亮度只有 50~80 —— 阈值永远够不到，
    # 每列 ridge 都等于 sh，整层画成空的（实测非透明像素 0）。
    #
    # 正确做法：统计这张缩略图的亮度分布，取**中位数**作为"山/天空"分界。
    lums = []
    for y in range(sh):
        for x in range(0, sw, 3):
            c = sp[x, y]
            lums.append(c[0] * 0.299 + c[1] * 0.587 + c[2] * 0.114)
    lums.sort()
    thresh = lums[int(len(lums) * 0.62)] if lums else 60

    ridge = []
    for x in range(sw):
        r = None
        for y in range(sh):
            c = sp[x, y]
            lum = c[0] * 0.299 + c[1] * 0.587 + c[2] * 0.114
            if lum > thresh:
                r = y
                break
        ridge.append(r if r is not None else sh)

    # ridge_frac 控制山脊**往下偏移多少**：
    #   0.0 = 山脊保持在原位（露出最多）→ 远山
    #   0.6 = 山脊下移（露出最少，被前面的山挡住）→ 近山
    #
    # **第一版写成了 base = sh * (1 - ridge_frac)**，ridge_frac=0 时
    # base 等于整个高度，top 全部越界 → **整层是空的**（实测画面只剩天空）。
    base = int(sh * ridge_frac * 0.8)
    for x in range(sw):
        r = ridge[x]
        top = max(0, min(sh, r + base))
        for y in range(top, sh):
            op[x, y] = (*body, 255)
        if 0 <= top < sh:
            op[x, top] = (*edge, 255)    # 山脊高光 1px
    return out


def build_sky(im):
    """天空：只取源图上部的主色，做垂直渐变。"""
    W, H = im.size
    top_part = im.crop((0, 0, W, int(H * 0.45)))
    from collections import Counter
    tp = top_part.load()
    cnt = Counter()
    for y in range(0, top_part.height, 6):
        for x in range(0, W, 12):
            c = tp[x, y]
            if c[3] > 0:
                cnt[(c[0], c[1], c[2])] += 1
    darkest = min(cnt, key=lambda c: c[0] + c[1] + c[2])
    lightest = max(cnt, key=lambda c: c[0] + c[1] + c[2])

    out = Image.new("RGBA", (SCREEN_W, SCREEN_H), (0, 0, 0, 255))
    op = out.load()
    # **渐变方向：上方暗（深空）→ 下方亮（靠近地平线）。**
    # 第一版写反了（顶部用最亮的色），结果天空上亮下暗，
    # 像白天而不是夜晚。
    for y in range(SCREEN_H):
        t = y / max(1, SCREEN_H - 1)
        c = tuple(int(darkest[i] * (1 - t) + lightest[i] * t)
                  for i in range(3))
        for x in range(SCREEN_W):
            op[x, y] = (*c, 255)
    # 量化到色板（用 8 级紫阶做渐变，配合抖动）
    pal = [hex_rgb(h) for h in PURPLE_RAMP]
    # **不做抖动，直接分档硬切。**
    #
    # 抖动（Bayer 网点）在 480x270 这种小分辨率下颗粒感极强，
    # 实测整片天空像印刷网点纸，完全不是像素画该有的样子。
    # 而且本项目规范里抖动只允许用于"大面积远景渐变"，
    # 但这里天空已经是纯色分档，根本不需要抖。
    #
    # 8 级紫阶直接按亮度分档，每档是纯色横带，边界清晰 ——
    # 这才是像素夜空的常见做法。
    for y in range(SCREEN_H):
        for x in range(SCREEN_W):
            c = op[x, y]
            lum = c[0] * 0.299 + c[1] * 0.587 + c[2] * 0.114
            f = lum / 255.0 * (len(pal) - 1)
            idx = int(f + 0.5)
            idx = max(0, min(len(pal) - 1, idx))
            op[x, y] = (*pal[idx], 255)
    return out


def mirror_tile(img):
    """水平镜像拼成双倍宽，保证横向循环无缝。"""
    w, h = img.size
    out = Image.new("RGBA", (w * 2, h), (0, 0, 0, 0))
    out.alpha_composite(img, (0, 0))
    out.alpha_composite(img.transpose(Image.FLIP_LEFT_RIGHT), (w, 0))
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    im = load_source()
    W, H = im.size
    print(f"源图 {W}x{H}")

    # **顺序很重要**：先抠月亮（需要原图），再擦擦除（为了拆山层干净）。
    moon, mc = extract_moon(im)
    im = erase_moon_from_source(im)

    # ── 天空 ──
    sky = build_sky(im)
    sky.save(os.path.join(OUT, "bg_sky.png"))
    print(f"  bg_sky.png       {sky.size}")

    # ── 月亮 ──
    if moon:
        moon.save(os.path.join(OUT, "bg_moon.png"))
        print(f"  bg_moon.png      {moon.size}")
    else:
        print("  警告：未找到月亮")

    # ── 三层山（按 y 比例切）──
    # 按亮度区间抠三层山（远亮近暗，符合空气透视）
    # 亮度区间按"只含山体"重新标定（实测 53~80）。
    # 远山最亮、近山最暗，符合空气透视。
    # 色阶区间整体压暗一档：远山用 [3:6] 而不是 [5:8]。
    # 第一版远山用了最亮的 [5:8]（#7F5FAE~#9678C4），在深紫夜空下
    # 显得发白刺眼，像被打了灯的塑料板。
    # **三层之间必须拉开明显的明度差**，否则看不出层次。
    # 第一版远 [3:6] / 中 [1:4] / 近 [0:3] 跨度太小（相差一档），
    # 实测三层糊成一片，只有山脊线能勉强分辨。
    # 这里让每层相差两档以上。
    layers = [
        ("bg_mtn_far", 0.00, PURPLE_RAMP[4:7]),    # 远：偏亮
        ("bg_mtn_mid", 0.34, PURPLE_RAMP[2:5]),    # 中
        ("bg_mtn_near", 0.60, PURPLE_RAMP[0:2]),   # 近：很暗
    ]
    for name, rf, ramp in layers:
        lay = extract_layer(im, rf, ramp)
        tiled = mirror_tile(lay)
        tiled.save(os.path.join(OUT, f"{name}.png"))
        print(f"  {name}.png  {lay.size} -> {tiled.size} (镜像)")

if __name__ == "__main__":
    sys.exit(main())
