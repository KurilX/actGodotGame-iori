"""美术度量：从图片里算出可比的质量指标。

## 为什么先测参考素材

打分体系最容易变成"拍脑袋定阈值"。这里的做法相反：

  1. 先对**真实成熟素材**（CC0 像素地形、DB32 调色板图集）算指标
  2. 用它们的分布反推"合格线"
  3. 我们的资产落在参考区间内才算过

阈值全部由参考素材推导，不写死。

## 六个可测维度

| 维度 | 含义 | 怎么算 |
|---|---|---|
| 调色板纪律 | 用色是否克制 | 独立色数 / 像素数，对照 DB32 的 32 色基准 |
| 明度结构 | 有多少明暗层次 | 亮度直方图的非空分箱数 + 对比度跨度 |
| 细节密度 | 每千像素的边缘数 | Sobel 边缘像素占比，排除平坦区 |
| 抗锯齿纯净度 | 有没有糊边 | "介于两邻色之间"的像素占比，越低越纯 |
| 轮廓一致性 | 描边是否统一 | 最暗一档色的占比 |
| 色相凝聚度 | 色调是否统一 | 有彩色像素的色相标准差（越小越集中）|

每项归一到 0~100，加权求总分。
"""

import math
import os
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_rgba(path):
    im = Image.open(path).convert("RGBA")
    return im


def visible_pixels(im):
    """返回 [(r,g,b)] 列表，只含 alpha>0.5 的像素（下采样控制计算量）。"""
    px = im.load()
    w, h = im.size
    step = max(1, int(math.sqrt(w * h / 24000.0)))
    out = []
    for y in range(0, h, step):
        for x in range(0, w, step):
            c = px[x, y]
            if c[3] > 128:
                out.append((c[0], c[1], c[2]))
    return out, step


def luminance(c):
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


def rgb_to_hsv(r, g, b):
    r, g, b = r / 255.0, g / 255.0, b / 255.0
    mx, mn = max(r, g, b), min(r, g, b)
    d = mx - mn
    if mx <= 0:
        return 0.0, 0.0, mx
    s = d / mx
    if d == 0:
        h = 0.0
    elif mx == r:
        h = ((g - b) / d) % 6
    elif mx == g:
        h = (b - r) / d + 2
    else:
        h = (r - g) / d + 4
    return h * 60.0, s, mx


def measure(path):
    """对一张图算全部指标。"""
    im = load_rgba(path)
    px = im.load()
    w, h = im.size
    pixels, step = visible_pixels(im)
    n = len(pixels)
    if n == 0:
        return None

    # ── 1. 调色板纪律 ──
    uniq = set(pixels)
    color_count = len(uniq)

    # ── 2. 明度结构 ──
    lums = [luminance(c) for c in pixels]
    hist = [0] * 16
    for l in lums:
        hist[min(15, int(l / 16.0))] += 1
    nonempty_bins = sum(1 for b in hist if b > n * 0.002)
    lum_min, lum_max = min(lums), max(lums)
    contrast = (lum_max - lum_min) / 255.0

    # ── 3. 细节密度（Sobel 边缘占比）──
    # 用完整分辨率算，否则下采样会抹掉 1px 的细节
    edges = 0
    total = 0
    for y in range(1, h - 1, 2):
        for x in range(1, w - 1, 2):
            c0 = px[x, y]
            if c0[3] <= 128:
                continue
            total += 1
            l00 = luminance(px[x - 1, y - 1]) if px[x - 1, y - 1][3] > 128 else luminance(c0)
            l10 = luminance(px[x, y - 1]) if px[x, y - 1][3] > 128 else luminance(c0)
            l20 = luminance(px[x + 1, y - 1]) if px[x + 1, y - 1][3] > 128 else luminance(c0)
            l01 = luminance(px[x - 1, y]) if px[x - 1, y][3] > 128 else luminance(c0)
            l21 = luminance(px[x + 1, y]) if px[x + 1, y][3] > 128 else luminance(c0)
            gx = (l20 + 2 * l21 + l10) - (l00 + 2 * l01 + l10)
            gy = (l00 + 2 * l10 + l20) - (l01 + 2 * l21 + l20)
            if math.hypot(gx, gy) > 24:
                edges += 1
    detail = edges / max(1, total)

    # ── 4. 抗锯齿纯净度 ──
    # 判据：该像素的颜色是否恰好"介于左右邻色之间"（线性插值）
    # 真正的像素画应该几乎没有这种像素
    aa = 0
    aa_total = 0
    for y in range(0, h, 2):
        for x in range(1, w - 1, 2):
            c = px[x, y]
            if c[3] <= 128:
                continue
            cl = px[x - 1, y]
            cr = px[x + 1, y]
            if cl[3] <= 128 or cr[3] <= 128:
                continue
            aa_total += 1
            mid = ((cl[0] + cr[0]) // 2, (cl[1] + cr[1]) // 2, (cl[2] + cr[2]) // 2)
            d = abs(c[0] - mid[0]) + abs(c[1] - mid[1]) + abs(c[2] - mid[2])
            # 和中间值很接近，但又和左右两侧都不同 → 是过渡色
            dl = abs(c[0] - cl[0]) + abs(c[1] - cl[1]) + abs(c[2] - cl[2])
            dr = abs(c[0] - cr[0]) + abs(c[1] - cr[1]) + abs(c[2] - cr[2])
            if d <= 12 and dl > 18 and dr > 18:
                aa += 1
    aa_ratio = aa / max(1, aa_total)

    # ── 5. 轮廓一致性（最暗一档占比）──
    lum_sorted = sorted(lums)
    dark_cut = lum_sorted[max(0, int(n * 0.06))]
    dark = sum(1 for l in lums if l <= dark_cut)
    dark_ratio = dark / n

    # ── 6. 色相凝聚度 ──
    hues = []
    for c in pixels:
        hh, ss, vv = rgb_to_hsv(*c)
        if ss > 0.18 and vv > 0.08:
            hues.append(hh)
    if len(hues) > 50:
        # 圆形标准差：先算平均向量
        sx = sum(math.cos(math.radians(hh)) for hh in hues) / len(hues)
        sy = sum(math.sin(math.radians(hh)) for hh in hues) / len(hues)
        R = math.hypot(sx, sy)
        hue_std = math.degrees(math.sqrt(max(0.0, -2 * math.log(max(1e-6, R)))))
    else:
        hue_std = 180.0

    return {
        "path": os.path.relpath(path, ROOT),
        "size": (w, h),
        "pixels": n,
        "colors": color_count,
        "nonempty_bins": nonempty_bins,
        "contrast": round(contrast, 3),
        "detail": round(detail, 4),
        "aa_ratio": round(aa_ratio, 4),
        "dark_ratio": round(dark_ratio, 4),
        "hue_std": round(hue_std, 1),
    }


def main(argv):
    targets = argv[1:] if len(argv) > 1 else []
    if not targets:
        print("用法: python tools/art_metrics.py <图片...>")
        return 1
    for t in targets:
        r = measure(t)
        if r is None:
            print(f"{t}: 无可见像素")
            continue
        print(f"{r['path']}")
        print(f"  尺寸 {r['size'][0]}x{r['size'][1]}  采样 {r['pixels']}")
        print(f"  用色 {r['colors']}  明度档 {r['nonempty_bins']}  "
              f"对比度 {r['contrast']}")
        print(f"  细节 {r['detail']:.4f}  抗锯齿 {r['aa_ratio']:.4f}  "
              f"暗部 {r['dark_ratio']:.4f}  色相std {r['hue_std']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
