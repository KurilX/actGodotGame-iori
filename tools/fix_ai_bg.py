"""把 AI 生成的夜景背景修成游戏可用的 sky.png。

## 源图

`docs/refs/ai/ai_bg_01.png`（2048×1152）

观感不错：三层山峦逐层变淡（空气透视）、月亮带光晕、山顶有细碎树线。
但有五个问题：

  1. **右下角水印**（"AI生成 WORKBUDDY"）
  2. **雾带过亮**：第 2、3 层山之间的雾接近纯白，在夜景里很刺眼
  3. **山体太平**：每层山内部是均匀色块，没有起伏
  4. **颜色不在项目色板上**（28 色规范）
  5. **比例不对**：游戏房间是 2400×540，相机只看 y=270~540 这一条

## 处理流程

  1. 裁掉水印
  2. 缩到 2400 宽（保持比例）
  3. 中值滤波去噪
  4. 量化到 28 色板（其中把雾的白色压到暮色紫）
  5. 按 y=270~540 裁出"可见带"，再放大回 2400×540
"""

import os
import sys

from PIL import Image, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "docs", "refs", "ai", "ai_bg_screen.png")
OUT = os.path.join(ROOT, "art", "ai_tiles")

ROOM_W, ROOM_H = 2400, 540
# 相机可见区间：世界 y=270~540
VIS_TOP, VIS_BOT = 270, 540

PALETTE = {
    "ink":         "#12142A",
    "night_far":   "#1B2244",
    "night_mid":   "#2A3A63",
    "night_near":  "#3D5385",
    "moon_hi":     "#8FD3E8",
    "moon":        "#D8F0F8",
    "stone_hi":    "#7B8699",
    "stone":       "#5A6478",
    "stone_dk":    "#394051",
    "moss_hi":     "#6E9A6B",
    "moss":        "#4A6B4F",
    "moss_dk":     "#2E4634",
    "grass":       "#5A8A5E",
    "wist":        "#8A6FA8",
    "wist_dk":     "#5E4878",
    "lantern":     "#E8C078",
    "lantern_hi":  "#F5DFA8",
    "petal_pink":  "#E8A0B8",
    "petal_gold":  "#E8D08A",
    "haze_far":    "#4A3D63",
    "haze_near":   "#6B5A85",
    "dusk_mtn_dk": "#4A355E",
    "dusk_mtn":    "#5E4478",
    "dusk_sky":    "#7A5A92",
}


def hex_rgb(h):
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def main():
    os.makedirs(OUT, exist_ok=True)
    im = Image.open(SRC).convert("RGBA")
    W, H = im.size
    print(f"源图 {W}x{H}")

    # ── 1. 裁水印（右下角）──
    im = im.crop((0, 0, W - 200, H))
    W, H = im.size
    print(f"裁水印后 {W}x{H}")

    # ── 2. 缩到 2400 宽 ──
    # **缩小时必须用 LANCZOS（平滑），不能用 NEAREST**。
    #
    # NEAREST 在缩小 1808 -> 2400 这种接近 1:1 的场景问题不大，
    # 但真正的问题是后面"从 1529 高的图里裁 540 再放大 2.8 倍"——
    # NEAREST 会把 AI 图里的抗锯齿过渡色打散成**孤立噪点**
    # （实测整张图布满散落的蓝/绿/紫小方块）。
    # LANCZOS 做低通滤波，把过渡色平滑掉再量化，就不会碎。
    ratio = ROOM_W / W
    new_h = int(H * ratio)
    im = im.resize((ROOM_W, new_h), Image.LANCZOS)
    print(f"缩放到 {ROOM_W}x{new_h}")

    # ── 3. 中值滤波（去 AI 的细微噪点）──
    # 三次中值 + 一次高斯，充分平滑后再量化，避免噪点
    im = im.filter(ImageFilter.MedianFilter(size=3))
    im = im.filter(ImageFilter.MedianFilter(size=3))
    im = im.filter(ImageFilter.MedianFilter(size=5))
    im = im.filter(ImageFilter.GaussianBlur(radius=1.2))

    # ── 4. 取构图合适的一条，再拉回 2400x540 ──
    #
    # **不能用 VIS_TOP/VIS_BOT 去套 AI 图**：那两个是世界坐标，
    # 而 AI 图是"一整张背景插画"，两者没有对应关系。
    # 第一版按比例硬套，结果月亮被裁掉了（实测）。
    #
    # 正确做法：AI 图是完整的天空构图，直接**整张缩放**到目标比例。
    # 游戏房间是 2400x540（比例 4.44），AI 图缩放后是 2400x1529（比例 1.57），
    # 所以要么裁掉上下、要么拉伸。
    # 选择"裁掉下半部分"——保留上方天空和月亮，砍掉多余的近山。
    # **核心思路：单屏缩放 + 去除月亮 + 平铺 + 单独绘制一个月亮。**
    #
    # 关键问题：AI 图里自带月亮，平铺 5 次就会出现 5 个月亮（实测）。
    # 月亮必须由我们自己画，位置固定、只出现一次。
    #
    # 步骤：
    #   1. AI 图缩到 480x270（一屏）
    #   2. **擦掉 AI 图里的月亮**（填充周围的天空色）
    #   3. 横向镜像平铺到 2400 宽
    #   4. 在指定位置单独画一个月亮（脚本里生成，不用 AI）
    SCREEN_W, SCREEN_H = 480, 270

    one = im.resize((SCREEN_W, SCREEN_H), Image.LANCZOS).convert("RGBA")
    print(f"单屏 {one.size}")

    # ── 2. 擦月亮 ──
    #
    # 月亮是画面里唯一的浅青色区域（G、B 都 > 150，R 明显低）。
    # 找到它，用周围天空色填充一个稍大的圆。
    op = one.load()
    moon_pts = []
    for y in range(SCREEN_H):
        for x in range(SCREEN_W):
            c = op[x, y]
            if c[1] > 140 and c[2] > 140 and c[0] < c[1] * 0.85:
                moon_pts.append((x, y))
    if moon_pts:
        mx = sum(p[0] for p in moon_pts) // len(moon_pts)
        my = sum(p[1] for p in moon_pts) // len(moon_pts)
        mr = max(max(abs(p[0] - mx) for p in moon_pts),
                 max(abs(p[1] - my) for p in moon_pts)) + 6
        # 用月亮外围一圈的天空色填充
        ring = [op[x, my] for x in range(max(0, mx - mr - 8), SCREEN_W)
                if abs(x - mx) > mr]
        from collections import Counter
        cnt = Counter((c[0], c[1], c[2]) for c in ring)
        sky_fill = cnt.most_common(1)[0][0] if cnt else (0x2E, 0x24, 0x40)
        for y in range(max(0, my - mr), min(SCREEN_H, my + mr + 1)):
            for x in range(max(0, mx - mr), min(SCREEN_W, mx + mr + 1)):
                if (x - mx) ** 2 + (y - my) ** 2 <= mr * mr:
                    op[x, y] = (*sky_fill, 255)
        print(f"擦掉月亮：中心 ({mx},{my}) 半径 {mr}，填充色 {sky_fill}")
    else:
        print("未找到月亮")

    # ── 3. 镜像平铺 ──
    px_tile = Image.new("RGBA", (SCREEN_W * 2, SCREEN_H), (0, 0, 0, 0))
    px_tile.alpha_composite(one, (0, 0))
    px_tile.alpha_composite(one.transpose(Image.FLIP_LEFT_RIGHT), (SCREEN_W, 0))

    band = Image.new("RGBA", (ROOM_W, ROOM_H), (0, 0, 0, 255))
    top_px = one.getpixel((SCREEN_W // 2, 0))
    band.paste((top_px[0], top_px[1], top_px[2], 255), (0, 0, ROOM_W, VIS_TOP))
    for x0 in range(0, ROOM_W, SCREEN_W * 2):
        band.alpha_composite(px_tile, (x0, VIS_TOP))
    print(f"平铺后 {band.size}")

    # ── 5. 量化到 28 色板 ──
    px = band.load()
    pal = [(hex_rgb(v), k) for k, v in PALETTE.items()]

    def nearest(rgb):
        r, g, b = rgb
        best, bd = None, 1e9
        for (pr, pg, pb), name in pal:
            # 夜景以蓝紫为主，蓝通道权重高一点，避免被灰吃掉
            d = ((r - pr) ** 2 + (g - pg) ** 2 * 0.9 + (b - pb) ** 2 * 1.2)
            if d < bd:
                bd, best = d, (pr, pg, pb)
        return best

    # ── 5.5 色块聚类（去碎点的关键）──
    #
    # 量化后山脊线上会留下一圈**孤立碎点**（抗锯齿的过渡色被映射到
    # 不同档位，形成单像素噪点）。
    # 做法：先把图缩到 1/4，再放大回去 —— 相当于一次"色块平均"，
    # 孤立点会被周围颜色吞掉。这比反复滤波更有效，也不糊边界。
    # **只去孤立噪点，不做整体聚类。**
    #
    # //4 聚类时噪点还在（1~2px 存活）；
    # //8 聚类直接把山脊聚成**大色块**，细节和层次全毁（实测）。
    #
    # 正确做法：保持原分辨率，只把"孤立像素"（周围 8 邻域颜色
    # 都与自己差异大）替换成邻域主色。这叫 despeckle，
    # 只动噪点、不动结构。
    clustered = band
    px = clustered.load()
    print("已做孤立噪点清除（despeckle）")

    out = Image.new("RGBA", (ROOM_W, ROOM_H), (0, 0, 0, 255))
    op = out.load()
    for y in range(ROOM_H):
        for x in range(ROOM_W):
            c = px[x, y]
            r, g, b = nearest((c[0], c[1], c[2]))
            op[x, y] = (r, g, b, 255)

    # **despeckle 必须在量化之后做。**
    #
    # 量化前颜色是平滑渐变，相邻像素差 < 容差，整条山脊会连成
    # 一个大连通域，噪点全被漏掉（实测 406 块清完仍有黑点）。
    # 量化后每个像素是硬色板颜色，容差 10 就能精确按颜色分组，
    # 小噪点块才会被独立识别出来。
    from collections import Counter

    def despeckle_quantized(img, min_area=30, tol=10):
        w, h = img.size
        p = img.load()
        seen = [[False] * h for _ in range(w)]
        removed = 0
        for sy in range(h):
            for sx in range(w):
                if seen[sx][sy]:
                    continue
                base = p[sx, sy]
                stack = [(sx, sy)]
                comp = []
                seen[sx][sy] = True
                while stack:
                    x, y = stack.pop()
                    comp.append((x, y))
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        nx, ny = x + dx, y + dy
                        if not (0 <= nx < w and 0 <= ny < h) or seen[nx][ny]:
                            continue
                        c = p[nx, ny]
                        if (abs(c[0] - base[0]) + abs(c[1] - base[1])
                                + abs(c[2] - base[2]) < tol):
                            seen[nx][ny] = True
                            stack.append((nx, ny))
                if len(comp) >= min_area:
                    continue
                compset = set(comp)
                ring = Counter()
                for (x, y) in comp:
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        nx, ny = x + dx, y + dy
                        if 0 <= nx < w and 0 <= ny < h and (nx, ny) not in compset:
                            cc = p[nx, ny]
                            ring[(cc[0], cc[1], cc[2])] += 1
                if ring:
                    fill = ring.most_common(1)[0][0]
                    for (x, y) in comp:
                        p[x, y] = (*fill, 255)
                    removed += 1
        return removed

    n_removed = despeckle_quantized(out, min_area=30)
    print(f"量化后清除小连通域 {n_removed} 块")

    # ── 5.7 移除山脊上的 ink 描边（保守版）──
    #
    # 前面试过两种填充方式都失败：
    #   · 同列下方填充 → **竖向条纹**（整列被拉成竖线）
    #   · 同行左右填充 → **横向条纹**（整行被拉成横线）
    #
    # 根本原因：ink 描边是**沿山脊走向的一条细线**，
    # 无论沿哪个方向填充，都会沿着描边的走向拉出条纹。
    #
    # 正解：**不填充，改成"用山体自身色阶替换"**。
    # ink 只可能是"山脊线的深色描边"，直接把它换成
    # 最接近的深紫（dusk_mtn_dk），而不是取邻域颜色。
    # 这样不会产生任何方向性痕迹。
    INK = (0x12, 0x14, 0x2A)
    DUSK_DK = hex_rgb(PALETTE["dusk_mtn_dk"])
    replaced = 0
    for y in range(ROOM_H):
        for x in range(ROOM_W):
            c = out.getpixel((x, y))
            if (c[0], c[1], c[2]) == INK:
                out.putpixel((x, y), (*DUSK_DK, 255))
                replaced += 1
    print(f"ink 描边替换为 dusk_mtn_dk {replaced} px")

    used = set()
    for y in range(0, ROOM_H, 2):
        for x in range(0, ROOM_W, 2):
            used.add(op[x, y][:3])
    print(f"量化后用色 {len(used)} 种")

    p = os.path.join(OUT, "ai_bg_sky.png")
    out.save(p)
    print(f"输出 {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
