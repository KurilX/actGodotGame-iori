"""手绘地形瓦片 v2：按真实像素素材的结构重画。

## 参考素材实测（docs/refs/pixel/p1_castle_tiles.png）

用程序测量了一块砖墙的精确结构：

    每个砖块 8px 高，四行一个循环
    y+0   #331C18   缝隙（最深）
    y+1   #7C5E4B   顶面高光（最亮）
    y+2~6 #5A4028   砖面主体（5px）
    y+7   #482B1E   底部暗边

**四档明暗，不是两档。** 每一档只占 1px，但正是这 1px 让砖块"有厚度"。

## 另外两份素材的规律

  · p4_forest：岩体大面积纯色，细节全部堆在顶部 3~4px 的一圈
    （碎土、草芽），草是**竖着的尖刺**而不是平铺色带
  · p3_db32：土是密集碎石纹理、石墙是错缝砖块 ——
    关键是**有明确重复单元**，不是无规律横纹

## 这版的做法

砖块**错缝排列**（奇数行偏移半个砖宽），
每块砖有 亮顶 / 中面 / 暗底 / 缝 四层。
草皮按 p4 的做法：顶部一圈碎土 + 竖着的草芽。
"""

import os
import sys

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_TILES = os.path.join(ROOT, "art", "tiles")
OUT_SHOTS = os.path.join(ROOT, "art", "screenshots")

TS = 20

# **四档之间必须有明显跨度。**
#
# 参考素材 db32 的石墙四档是：
#   #45283C（深紫缝）→ #696A6A（中）→ #847E87 → #9BADB7（亮）
# 相邻两档的亮度差约 15~20，跨度很大。
#
# 我第一版四档挤在一起（#3F4258 / #4E5169 / #6A6E85 / #8E93A8），
# 相邻差只有 10 左右，砖块就没有厚度感，看着像一块平灰。
PAL = {
    ".": None,
    "i": "#12142A",   # 描边（最深）
    "1": "#2A2C42",   # 石缝（压很深）
    "2": "#9DA3BE",   # 砖块高光（提很亮）
    "3": "#6E7392",   # 砖面主色
    "4": "#3E4159",   # 砖块暗底
    "a": "#9ED47E",   # 草尖（最亮）
    "b": "#6FB558",   # 草主体
    "c": "#4E8A45",   # 草根
    "d": "#356138",   # 草影
    "e": "#7A6A58",   # 土亮
    "f": "#5A4C40",   # 土中
}


def color_of(ch):
    h = PAL[ch]
    if h is None:
        return (0, 0, 0, 0)
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 255)


def _h(x, y, salt=0):
    """确定性哈希，给砖块内噪点用（不含随机，保证可复现）。"""
    v = ((x * 73856093) ^ (y * 19349663) ^ (salt * 83492791)) & 0xFFFF
    return v / 65535.0


def brick_rows(offset=0, variant=0):
    """20x20 砖墙块。砖块 8px 高、16px 宽，奇数行错开 8px。

    variant 决定砖块内的噪点分布 —— 参考素材里每块砖都不是纯色，
    有 1~2 个暗点/亮点，这是"石头"和"积木"的关键差别。
    """
    rows = []
    for y in range(TS):
        yy = (y + offset) % 8
        shift = 8 if ((y + offset) // 8) % 2 else 0
        line = ""
        for x in range(TS):
            if yy == 0:
                ch = "1"
            elif yy == 1:
                ch = "2"
            elif yy <= 6:
                ch = "3"
            else:
                ch = "4"
            bx = (x + shift) % 16
            if bx == 0:
                ch = "1"
            elif bx == 1 and yy in (1, 2, 3):
                ch = "2"
            # ── 砖块内噪点 ──
            # 只在砖面主体（yy 2~5）里撒，且概率低，否则会变花
            if ch == "3" and 2 <= yy <= 5 and bx >= 3:
                h = _h(x + bx * 7, y + variant * 13, variant)
                if h < 0.10:
                    ch = "4"      # 暗点
                elif h > 0.94:
                    ch = "2"      # 亮点
            line += ch
        rows.append(line)
    return rows


def dirt_rows(offset=0, variant=0):
    """泥土块：密集碎石点阵（参考 p2 左半边的做法）。"""
    rows = []
    for y in range(TS):
        line = ""
        for x in range(TS):
            h = _h(x + variant * 31, y + offset * 17, 5)
            if h < 0.22:
                ch = "f"      # 土中
            elif h < 0.34:
                ch = "e"      # 土亮
            elif h < 0.40:
                ch = "1"      # 缝（暗点）
            else:
                ch = "3"      # 石色打底
            line += ch
        rows.append(line)
    return rows


# 草要**密**：几乎每一列都有草，只是高度在 1~4 之间起伏。
# 参考 p4 的草是连续的尖刺带，不是零星几点。
PROF_A = [3, 2, 4, 3, 2, 3, 4, 3, 2, 3, 2, 3, 4, 3, 2, 3, 4, 3, 2, 3]
PROF_B = [2, 3, 4, 3, 3, 2, 4, 3, 2, 3, 4, 3, 3, 2, 3, 4, 3, 2, 3, 4]
PROF_EDGE = [2, 3, 4, 3, 2, 3, 4, 3, 2, 3, 2, 3, 4, 3, 2, 3, 4, 3, 2, 3]


def grass_strip(profile):
    """顶部 5 行：草芽 + 碎土。参考 p4 的做法。"""
    soil = "".join("e" if (i * 7) % 3 == 0 else "f" for i in range(TS))
    r0 = "".join("a" if profile[i] >= 4 else "." for i in range(TS))
    r1 = "".join("a" if profile[i] >= 3 else "b" for i in range(TS))
    r2 = "".join("b" if profile[i] >= 2 else "c" for i in range(TS))
    r3 = "".join("c" if profile[i] >= 1 else s for i, s in enumerate(soil))
    return [r0, r1, r2, r3, soil]


def build_tiles():
    tiles = {}

    for i, (prof, off) in enumerate([(PROF_A, 0), (PROF_B, 4),
                                     (PROF_A, 2)], start=1):
        tiles[f"top_mid_{i}"] = grass_strip(prof) + brick_rows(offset=off)[5:]

    body = grass_strip(PROF_EDGE) + brick_rows(offset=1)[5:]

    tiles["top_left"] = [".." + row[2:] if i < 5 else "i" + row[1:]
                         for i, row in enumerate(body)]
    tiles["top_right"] = [row[:-1] + "i" for row in body]

    b = brick_rows(offset=3)
    out = []
    for i in range(TS):
        if i < 8:
            out.append("." * TS)
        elif i == 8:
            out.append("." * 8 + "2" * 12)
        elif i == 9:
            out.append("." * 8 + "3" * 12)
        else:
            out.append("." * 8 + b[i][8:])
    tiles["corner_in"] = out

    body2 = grass_strip(PROF_EDGE) + brick_rows(offset=3)[5:]
    tiles["corner_out"] = [row[:12] + "." * 8 for row in body2]

    tiles["side_left"] = ["i" + r[1:] for r in brick_rows(offset=0)]
    tiles["side_right"] = [r[:-1] + "i" for r in brick_rows(offset=5)]
    # **多种内部填充**：不能整片都是砖，否则像人工墙。
    # 参考 p2 的做法是"砖墙"和"碎石土"两种材质交替。
    tiles["fill"] = brick_rows(offset=6)
    tiles["fill_dirt"] = dirt_rows(offset=2, variant=1)
    tiles["fill_dark"] = brick_rows(offset=3, variant=2)

    b = brick_rows(offset=2)
    out = []
    for i in range(TS):
        if i < 16:
            out.append(b[i])
        elif i == 16:
            out.append("i" * TS)
        else:
            out.append("." * TS)
    tiles["bottom"] = out

    tiles["plat_mid"] = (
        ["." * TS] * 7
        + ["2" * TS, "3" * TS, "3" * TS, "4" * TS, "i" * TS]
        + ["." * TS] * 8
    )
    tiles["plat_left"] = (
        ["." * TS] * 7
        + ["i" + "2" * 19, "i" + "3" * 19, "i" + "3" * 19,
           "i" + "4" * 19, "i" * TS]
        + ["." * TS] * 8
    )
    return tiles


def render_tile(rows):
    assert len(rows) == TS, f"需要 {TS} 行，实际 {len(rows)}"
    im = Image.new("RGBA", (TS, TS), (0, 0, 0, 0))
    px = im.load()
    for y, row in enumerate(rows):
        assert len(row) == TS, f"行 {y} 需要 {TS} 列，实际 {len(row)}"
        for x, ch in enumerate(row):
            px[x, y] = color_of(ch)
    return im


def main():
    os.makedirs(OUT_TILES, exist_ok=True)
    os.makedirs(OUT_SHOTS, exist_ok=True)
    tiles = build_tiles()
    names = list(tiles.keys())

    cols, gap, lab, S = 4, 8, 14, 6
    TW = TS * S
    rows_n = (len(names) + cols - 1) // cols
    W = cols * (TW + gap) + gap
    H = rows_n * (TW + lab + gap) + gap
    sheet = Image.new("RGB", (W, H), (26, 28, 42))
    d = ImageDraw.Draw(sheet)
    for i, n in enumerate(names):
        t = render_tile(tiles[n]).resize((TW, TW), Image.NEAREST)
        cx = gap + (i % cols) * (TW + gap)
        cy = gap + (i // cols) * (TW + lab + gap) + lab
        bg = Image.new("RGBA", (TW, TW), (46, 38, 62, 255))
        bg.alpha_composite(t)
        sheet.paste(bg.convert("RGB"), (cx, cy))
        d.text((cx, cy - lab), n, fill=(230, 235, 250))
    sheet.save(os.path.join(OUT_TILES, "tileset_zoom.png"))

    MW, MH = 16, 10
    mock = Image.new("RGBA", (MW * TS, MH * TS), (0x2E, 0x24, 0x40, 255))
    gnd = 6
    mock.alpha_composite(render_tile(tiles["top_left"]), (0, gnd * TS))
    keys = ["top_mid_1", "top_mid_2", "top_mid_3"]
    for i in range(1, MW - 1):
        mock.alpha_composite(render_tile(tiles[keys[i % 3]]), (i * TS, gnd * TS))
    mock.alpha_composite(render_tile(tiles["top_right"]),
                         ((MW - 1) * TS, gnd * TS))
    mock.alpha_composite(render_tile(tiles["corner_out"]), (3 * TS, (gnd - 1) * TS))
    mock.alpha_composite(render_tile(tiles["top_mid_2"]), (4 * TS, (gnd - 1) * TS))
    mock.alpha_composite(render_tile(tiles["top_mid_3"]), (5 * TS, (gnd - 1) * TS))
    mock.alpha_composite(render_tile(tiles["corner_in"]), (6 * TS, (gnd - 1) * TS))
    # 填充交替：砖 / 土 / 暗砖，按 (x+y) 哈希选
    fills = ["fill", "fill_dirt", "fill_dark"]
    for r in range(gnd + 1, MH):
        for i in range(MW):
            k = fills[(i * 3 + r * 5) % 3]
            mock.alpha_composite(render_tile(tiles[k]), (i * TS, r * TS))
    mock.resize((mock.width * 2, mock.height * 2), Image.NEAREST).save(
        os.path.join(OUT_SHOTS, "tiles_mock.png"))

    print(f"瓦片表: {OUT_TILES}/tileset_zoom.png ({len(names)} 块)")
    print(f"拼接示意: {OUT_SHOTS}/tiles_mock.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
