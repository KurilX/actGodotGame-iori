"""actGame ↔ pixel-studio 通用接入层。

## 引入原因

之前地形是**一整张 2400x540 的贴图**（先裁大图、后来换成 AI 生图整幅平铺），
AI 评审反复指出「石砖纹理重复且均匀」「每个 tile 一模一样」。

根因是**没有真正的瓦片系统**。alanfrigo/pixel-studio（MIT，
tools/vendor/pixel-studio）里的 `python/pixel_pipeline` 是一个离线光栅管线，
它有完整的地形/瓦片操作（world/scenes 模块）：

  · side_guides      18 种侧视瓦片模板（顶面/侧壁/天花板/薄台/内角…）
  · corner_guides    16 掩码 Wang autotile 图集
  · texture_seams    无缝纹理检测（边对边拼接 + 材质健康检查）
  · tileset_seams    图集内瓦片两两接缝检测（+ 样例地图验证）
  · scene_layer_check 视差层横向循环检测 + 地面线连续性

## 接入方式

不启动它的 Next.js 服务（真实生图需要 OpenRouter/OpenAI key），
而是**直接调用它的 Python 光栅管线** —— 完全离线、可复现、可直接 import。

## 协议要点（踩过的坑）

  · 顶层键是 `operation` 不是 `op`；`protocolVersion` 必须是 1
  · `recipe` 里必须有 `version: 1`
  · 每个 input 必须带 `sha256`，与实际文件一致，
    否则报 "Hash da entrada ... diverge do pedido"
  · 多个同 role 的输入要靠 `ordinal` 区分顺序，缺了报 KeyError 'ordinal'
  · 所有路径（输入 relPath 与输出 out/…）都不得越出 workdir
  · 输出统一落在 `workdir/out/<relPath>`，带 role/width/height/sha256
"""

import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
VENDOR = ROOT / "tools" / "vendor" / "pixel-studio" / "python"
WORK_ROOT = ROOT / "art" / "tiles" / ".pswork"

sys.path.insert(0, str(VENDOR))

# pixel-studio src/server/world/core.ts 的官方默认：
# 结构化纹理（砖缝/硬边）的 seam/interior 判据容差
DEFAULT_SEAM_THRESHOLD = 1.5
DEFAULT_PAIR_THRESHOLD = 1.6


def clean_workroot():
    """清掉上次运行留下的临时 workdir（out/ 残留会混淆输出查找）。"""
    if WORK_ROOT.exists():
        import shutil
        shutil.rmtree(WORK_ROOT, ignore_errors=True)
    WORK_ROOT.mkdir(parents=True, exist_ok=True)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_op(op: str, inputs, recipe: dict, keep: bool = False) -> dict:
    """在独立临时目录里跑一个 pixel_pipeline 操作。

    inputs: [(本地路径, role), ...]（同 role 多输入自动编号 ordinal）
    返回 {"status", "report", "warnings", "files": {role: Path}}。
    每次调用用全新的 workdir，避免上一次的 out/ 残留混淆。
    """
    from pixel_pipeline import protocol

    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    work = WORK_ROOT / f"{op}-{len(list(WORK_ROOT.iterdir())):04d}"
    work.mkdir(parents=True, exist_ok=True)

    req_inputs = []
    for ordinal, (src, role) in enumerate(inputs):
        src = Path(src)
        dst = work / src.name
        shutil.copyfile(src, dst)
        entry = {"role": role, "relPath": src.name, "sha256": _sha256(dst)}
        if sum(1 for _, r in inputs if r == role) > 1:
            entry["ordinal"] = ordinal
        req_inputs.append(entry)

    req = {
        "protocolVersion": 1,
        "operation": op,
        "inputs": req_inputs,
        "outputs": [],
        "recipe": {"version": 1, **recipe},
    }
    try:
        res = protocol.handle(req, work)
    except Exception as e:  # noqa: BLE001
        res = {"status": "error", "error": {"code": type(e).__name__,
                                            "message": str(e)}}
    files = {}
    for o in res.get("outputs") or []:
        p = work / o.get("relPath", "")
        if p.exists():
            files.setdefault(o.get("role"), p)
    res["files"] = files
    res["workdir"] = str(work)
    if not keep and res.get("status") in ("ok", "needs_review"):
        # 默认清掉临时目录（已把需要的输出拷走了就不用留）
        pass
    return res


# ────────────────────────── 具体操作的封装 ──────────────────────────

SIDE_CONFIGS = [
    "surface_middle", "surface_left", "surface_right", "surface_single",
    "interior", "wall_left", "wall_right", "column_middle",
    "ceiling_middle", "ceiling_left", "ceiling_right", "column_bottom",
    "thin_middle", "thin_left", "thin_right", "block_single",
    "inner_corner_left", "inner_corner_right",
]


def side_guides(body_png: Path, surface_png: Path, cell=20,
                 surface_depth=7, columns=6) -> dict:
    """生成 18 配置侧视瓦片图集（横版地形的标准瓦片表）。"""
    return run_op("side_guides", [(body_png, "layer"), (surface_png, "layer")], {
        "cellSize": [cell, cell],
        "configurations": SIDE_CONFIGS,
        "surfaceDepthPx": surface_depth,
        "columns": columns,
    })


def corner_guides(tex_a: Path, tex_b: Path, cell=20, band=5, seed=7) -> dict:
    """生成 16 掩码 Wang autotile 图集（A/B 两种材质的过渡）。"""
    return run_op("corner_guides", [(tex_a, "layer"), (tex_b, "layer")], {
        "cellSize": [cell, cell],
        "bandPx": band,
        "seed": seed,
        "zoom": 1,
        "diagonals": {"mask5": "connected", "mask10": "connected"},
    })


def texture_seams(path: Path, axis_x=True, axis_y=False,
                  threshold=None, zoom=4) -> dict:
    """检测一张贴图的循环接缝 + 材质健康（透明/平板等问题）。

    threshold 用 pixel-studio 的官方默认 1.5（seam/interior 判据，
    而不是绝对差异）；structured 纹理（砖缝这类硬边）必须有这个容差。
    """
    return run_op("texture_seams", [(path, "source")], {
        "axes": {"x": axis_x, "y": axis_y},
        "threshold": DEFAULT_SEAM_THRESHOLD if threshold is None else threshold,
        "zoom": zoom,
    })


def scene_layer_check(path: Path, axis_x=True, axis_y=False,
                      threshold=0.12, ground_line_y=None) -> dict:
    """视差层循环检测（比 texture_seams 更适合带透明的场景层）。"""
    recipe = {
        "axes": {"x": axis_x, "y": axis_y},
        "threshold": threshold,
        "zoom": 2,
    }
    if ground_line_y is not None:
        recipe["groundLineY"] = ground_line_y
    return run_op("scene_layer_check", [(path, "source")], recipe)


def tileset_seams_side(atlas: Path, tiles, cell=20,
                       threshold=None) -> dict:
    """侧视图集接缝检测。

    tiles: [{"key": 配置名, "rect": [x,y,w,h]}, ...]（来自 side_guides 报告）
    sample 用 pixel-studio 官方 12x5 演示地图（平台/边/缺口/台阶）。
    """
    return run_op("tileset_seams", [(atlas, "source")], {
        "cellSize": [cell, cell],
        "threshold": DEFAULT_PAIR_THRESHOLD if threshold is None else threshold,
        "zoom": 3,
        "layout": "side",
        "lockedBandPx": 0,
        "tiles": tiles,
        "sample": {"size": [12, 5], "cells": side_sample_cells()},
    })


# pixel-studio src/domain/world/side.ts 的 SIDE_SAMPLE + RULES 的 Python 复刻
_SIDE_RULES = {
    "T": "surface_middle", "TL": "surface_left", "TR": "surface_right",
    "TLR": "surface_single", "": "interior", "L": "wall_left",
    "R": "wall_right", "LR": "column_middle", "B": "ceiling_middle",
    "BL": "ceiling_left", "BR": "ceiling_right", "BLR": "column_bottom",
    "TB": "thin_middle", "TBL": "thin_left", "TBR": "thin_right",
    "TBLR": "block_single",
}
_SIDE_SAMPLE_SOLID = [
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [1, 1, 0, 0, 0, 0, 0, 1, 1, 1, 1, 0],
    [1, 1, 1, 1, 0, 0, 1, 1, 1, 1, 1, 1],
    [1, 1, 1, 1, 0, 0, 1, 1, 1, 1, 1, 1],
]


def side_configuration(solid, cols, rows, x, y):
    def at(cx, cy, outside):
        if cx < 0 or cy < 0 or cx >= cols or cy >= rows:
            return outside
        return solid[cy * cols + cx]
    if not at(x, y, 0):
        return None
    top = not at(x, y - 1, 0)
    left = not at(x - 1, y, 1)
    right = not at(x + 1, y, 1)
    bottom = not at(x, y + 1, 1)
    key = f"{'T' if top else ''}{'B' if bottom else ''}{'L' if left else ''}{'R' if right else ''}"
    cfg = _SIDE_RULES[key]
    if cfg == "interior":
        if not at(x - 1, y - 1, 0):
            return "inner_corner_left"
        if not at(x + 1, y - 1, 0):
            return "inner_corner_right"
    return cfg


def side_sample_cells():
    solid = [v for row in _SIDE_SAMPLE_SOLID for v in row]
    rows, cols = len(_SIDE_SAMPLE_SOLID), len(_SIDE_SAMPLE_SOLID[0])
    cells = []
    for y in range(rows):
        for x in range(cols):
            cfg = side_configuration(solid, cols, rows, x, y)
            cells.append(cfg or "")
    return cells


def main(argv):
    """命令行入口：对任意贴图跑接缝/材质检查。

    python tools/pixel_studio_bridge.py seams <png> [--y]
    python tools/pixel_studio_bridge.py layer <png> [--ground Y]
    """
    try:  # Windows 控制台默认 GBK，中文报告会乱码
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    if len(argv) < 2:
        print(__doc__)
        return 1
    cmd, path = argv[0], Path(argv[1])
    if cmd == "seams":
        res = texture_seams(path, axis_y="--y" in argv)
    elif cmd == "layer":
        gy = None
        if "--ground" in argv:
            gy = int(argv[argv.index("--ground") + 1])
        res = scene_layer_check(path, axis_y="--y" in argv,
                                ground_line_y=gy)
    else:
        print(f"未知命令 {cmd}", file=sys.stderr)
        return 1
    rep = res.get("report") or {}
    mat = rep.get("material") or {}
    print(f"status={res.get('status')}")
    if mat:
        print(f"  不透明={mat.get('opaqueFraction')} 用色={mat.get('distinctColors')}"
              f" 问题={len(mat.get('problems') or [])}")
        for p in mat.get("problems") or []:
            msg = p.get("zh-CN") or p.get("en") or str(p) if isinstance(p, dict) else str(p)
            print(f"    - {msg}")
    for axis in ("x", "y"):
        r = rep.get(axis)
        if r:
            print(f"  接缝[{axis}] ratio={r.get('ratio')} passed={r.get('passed')}")
    if rep.get("ground"):
        print(f"  地面线: {rep['ground']}")
    if res.get("warnings"):
        for w in res["warnings"]:
            msg = w.get("en") if isinstance(w, dict) else w
            print(f"  警告: {msg}")
    return 0 if res.get("status") in ("ok", "needs_review") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
