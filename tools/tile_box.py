"""通用瓦片砌块器：用 pixel-studio side_guides 图集砌任意矩形实体。

## 为什么

此前断墙/门框/矮墙/残柱都是"interior 单格采样 + 手绘描边/受光/压暗"
—— 每个装饰函数自己重复实现一遍边缘语义，而且手绘的受光边只有 1px
stone_hi，和地形层（side_guides 出的 surface/wall 瓦片自带 2px 渐变
受光边）放在一起时材质语言不一致。

## side_guides 18 配置的曝光语义（pixel-studio SIDE_EXPOSURE）

每个配置的瓦片**自带**对应曝光面的受光/压暗/圆角：

  T=顶面受光  L=左壁压暗  R=右壁压暗  B=底面压暗
  i/j=内角（紧邻 solids 时顶面延伸进来的受光折角）

  surface_*   T（+L/R/…）：地面块 —— 顶面 7px 草皮+受光
  interior    ""：内部填充
  wall_left/right  L/R：侧壁
  column_middle    LR：两侧都暴露（薄柱）
  ceiling_*   B：天花板
  thin_*      TB：薄台（顶受光+底压暗，单向平台）
  block_single TBLR：孤立块（四面临空）
  inner_corner_*   i/j：内角

## 本模块提供

  load_atlas()          读 art/tiles/tiles_tileset_a.png + 配置→rect 表
  draw_box(px, x, y, w, h, grid)  按 0/1 网格语义从图集取瓦片砌矩形
  wall_grid(w, h, jag)  生成断墙网格（顶部锯齿+可选悬挑断砖）
  gate_grid(inner_w, h) 生成门框网格（两柱+顶梁，洞口 0）
"""

import json
import os
from pathlib import Path

from PIL import Image

ROOT = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ATLAS = ROOT / "art" / "tiles" / "tiles_tileset_a.png"

# 配置 → 图集 rect（side_guides 输出的固定布局，columns=6）
RECTS = {
    "surface_middle": (0, 0, 20, 20),
    "surface_left": (20, 0, 20, 20),
    "surface_right": (40, 0, 20, 20),
    "surface_single": (60, 0, 20, 20),
    "interior": (80, 0, 20, 20),
    "wall_left": (100, 0, 20, 20),
    "wall_right": (0, 20, 20, 20),
    "column_middle": (20, 20, 20, 20),
    "ceiling_middle": (40, 20, 20, 20),
    "ceiling_left": (60, 20, 20, 20),
    "ceiling_right": (80, 20, 20, 20),
    "column_bottom": (100, 20, 20, 20),
    "thin_middle": (0, 40, 20, 20),
    "thin_left": (20, 40, 20, 20),
    "thin_right": (40, 40, 20, 20),
    "block_single": (60, 40, 20, 20),
    "inner_corner_left": (80, 40, 20, 20),
    "inner_corner_right": (100, 40, 20, 20),
}


def load_atlas(path=None):
    p = Path(path) if path else ATLAS
    if not p.exists():
        return None, {}
    im = Image.open(p).convert("RGBA")
    return im, dict(RECTS)


def tile_for(grid, gx, gy):
    """0/1 网格 → 该格应取的配置名（外圈按实心处理的 side 规则）。"""
    rows, cols = len(grid), len(grid[0])

    def at(cx, cy, outside):
        if cx < 0 or cy < 0 or cx >= cols or cy >= rows:
            return outside
        return grid[cy][cx]

    if not at(gx, gy, 0):
        return None
    top = not at(gx, gy - 1, 0)
    left = not at(gx - 1, gy, 1)
    right = not at(gx + 1, gy, 1)
    bottom = not at(gx, gy + 1, 1)
    key = f"{'T' if top else ''}{'B' if bottom else ''}{'L' if left else ''}{'R' if right else ''}"
    cfg = {
        "T": "surface_middle", "TL": "surface_left", "TR": "surface_right",
        "TLR": "surface_single", "": "interior", "L": "wall_left",
        "R": "wall_right", "LR": "column_middle", "B": "ceiling_middle",
        "BL": "ceiling_left", "BR": "ceiling_right", "BLR": "column_bottom",
        "TB": "thin_middle", "TBL": "thin_left", "TBR": "thin_right",
        "TBLR": "block_single",
    }[key]
    if cfg == "interior":
        if not at(gx - 1, gy - 1, 0):
            return "inner_corner_left"
        if not at(gx + 1, gy - 1, 0):
            return "inner_corner_right"
    return cfg


def draw_box(px, x, y, grid, atlas=None, rects=None, alt_atlas=None):
    """把 0/1 网格砌到像素画布上。x/y 为网格原点像素坐标。

    alt_atlas：第二个图集（如 body_b），按格哈希混合，破坏平铺节奏。
    """
    if atlas is None:
        atlas, rects = load_atlas()
    if rects is None:
        rects = RECTS
    cell = 20
    for gy in range(len(grid)):
        for gx in range(len(grid[0])):
            cfg = tile_for(grid, gx, gy)
            if cfg is None or cfg not in rects:
                continue
            rx, ry, rw, rh = rects[cfg]
            # 变体选择：确定性哈希，85% a / 15% b
            v = 0
            if alt_atlas is not None:
                h = ((gx * 73856093) ^ (gy * 19349663)) & 0xFFFF
                v = 1 if (h / 65535.0) < 0.15 else 0
            src = alt_atlas if v == 1 else atlas
            tile = src.crop((rx, ry, rx + rw, ry + rh))
            ox, oy = x + gx * cell, y + gy * cell
            for ty in range(cell):
                for tx in range(cell):
                    c = tile.getpixel((tx, ty))
                    xx, yy = ox + tx, oy + ty
                    # 画布越界保护由调用方保证，这里只画不透明像素
                    if c[3] > 128:
                        px[xx, yy] = c


def wall_grid(w, h, jag_fn, overhang=None):
    """断墙网格：w×h 格，顶部 jag_fn(col) 行锯齿，可带悬挑断砖列。"""
    grid = [[1] * w for _ in range(h)]
    for gx in range(w):
        j = jag_fn(gx)          # 0..4 px → 0/0.2 格，四舍五入到格
        rows = max(1, round(j / 20 * 1.0))  # 锯齿最多削 1 格
        for gy in range(rows):
            grid[gy][gx] = 0
    if overhang is not None:
        ox = overhang
        for gy in range(1):
            if ox < w and grid[0][ox] == 0:
                grid[0][ox] = 1
            if ox + 1 < w:
                grid[0][ox + 1] = 1
    return grid


def gate_grid(inner_w, h, beam=1):
    """门框网格：两柱(1格宽) + 顶梁 beam 格，洞口 inner_w 格宽 0。"""
    w = 2 + inner_w
    grid = [[0] * w for _ in range(h)]
    for gy in range(h):
        grid[gy][0] = 1
        grid[gy][w - 1] = 1
    for gx in range(w):
        for gy in range(beam):
            grid[gy][gx] = 1
    return grid


def low_wall_grid(w, h, jag_fn):
    """矮墙网格：h 通常 1~2 格。"""
    grid = [[1] * w for _ in range(h)]
    for gx in range(w):
        j = jag_fn(gx)
        if j >= 1:
            grid[0][gx] = 0
    return grid
