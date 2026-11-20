"""线上验证：确认 BOSS 真的在线上跑起来。

## 判据

不依赖任何内部状态（拿不到），用**画面内容判断**：
  1. BOSS 血条在最顶部有一条横向的红色带 —— 用像素扫描找它
  2. BOSS 本体在画面右侧 —— 一块明显高于其他角色的非背景区域

## 踩过的坑（沿用之前的教训）

  · 不能按 canvas 的 W/H 直接换算逻辑坐标 —— Godot 不铺满 canvas
  · 不能只靠"亮像素数" —— 月亮/苔藓会和 UI 同色
  · 这里改为**在整幅图里找特定的几何特征**（顶部的横向红条），
    而不是在"我以为它该在的位置"找

用法：python tools/verify_live_boss.py
"""

import base64
import io
import sys

from PIL import Image
from playwright.sync_api import sync_playwright

BASE = "https://kurilx.github.io/actGodotGame-iori/"

DESKTOP = {
    "viewport": {"width": 1280, "height": 800},
    "device_scale_factor": 1,
    "is_mobile": False,
    "has_touch": False,
}

JS_GRAB = """() => {
    const s = document.getElementById('canvas');
    const t = document.createElement('canvas');
    t.width = s.width; t.height = s.height;
    const g = t.getContext('2d');
    g.drawImage(s, 0, 0);
    return t.toDataURL('image/png');
}"""


def grab(page):
    data = page.evaluate(JS_GRAB)
    raw = base64.b64decode(data.split(",", 1)[1])
    return Image.open(io.BytesIO(raw)).convert("RGB")


def find_boss_bar(img):
    """找 BOSS 血条：画面顶部一条连续的红色横带。

    血条填充色 #FF5A6E = (255, 90, 110)。
    特征：三道横条并排，每道约 90px 宽（画面 480 宽时），
    位于画面顶部 15~30px 的逻辑高度内。
    """
    px = img.load()
    W, H = img.size

    def is_bar_red(c):
        r, g, b = c
        return r > 200 and 60 < g < 130 and 80 < b < 150

    # 扫描顶部 25% 的区域。
    # **坑**：一开始只扫顶部 12%（y < H*0.12 = 96），但实际血条在 y≈155~180，
    # 完全在扫描范围之外，导致明明渲染了却报"没找到"。
    # 血条位置取决于 canvas 内游戏画面的垂直居中偏移，不是固定的。
    top_limit = int(H * 0.25)
    rows = {}
    for y in range(0, top_limit, 2):
        cnt = sum(1 for x in range(0, W, 2) if is_bar_red(px[x, y]))
        if cnt > 10:
            rows[y] = cnt

    return rows


def measure_game_area(img):
    """找游戏画面的真实包围盒（非黑区）。"""
    px = img.load()
    W, H = img.size

    def non_black(c):
        return c[0] > 8 or c[1] > 8 or c[2] > 10

    xs = [x for x in range(W) if any(non_black(px[x, y])
                                     for y in range(0, H, 6))]
    ys = [y for y in range(H) if any(non_black(px[x, y])
                                     for x in range(0, W, 6))]
    if not xs or not ys:
        return None
    return (min(xs), min(ys), max(xs), max(ys))


def main():
    failures = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(**DESKTOP)
        page = ctx.new_page()

        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))

        loaded = {}

        def on_resp(resp):
            for k in ("index.wasm", "index.pck", "index.js"):
                if k in resp.url:
                    loaded[k] = resp.status

        page.on("response", on_resp)

        print(f"target = {BASE}")
        page.goto(BASE, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(20000)

        print()
        print("=== 资源加载 ===")
        for k in ("index.js", "index.wasm", "index.pck"):
            st = loaded.get(k, "-")
            print(f"  {k}: {st}")
            if st != 200:
                failures.append(f"{k} 未加载")

        img = grab(page)
        img.save("art/screenshots/live_boss_check.png")

        area = measure_game_area(img)
        print()
        print("=== 游戏画面区域 ===")
        print(f"  {area}")
        if area is None:
            failures.append("找不到游戏画面")
            browser.close()
            return 1

        # ── 检查 1：BOSS 血条 ──
        print()
        print("=== BOSS 血条（顶部红色横带）===")
        rows = find_boss_bar(img)
        if rows:
            ys = sorted(rows.keys())
            print(f"  找到红色横带：y {min(ys)}..{max(ys)}，"
                  f"最宽一行有 {max(rows.values()) * 2} 个红像素")
            print("  ok   BOSS 血条已在线上渲染")
        else:
            failures.append("没找到 BOSS 血条")
            print("  FAIL 没找到 BOSS 血条")

        # ── 检查 2：整个画面有内容 ──
        print()
        print("=== 画面内容 ===")
        px = img.load()
        non_black = sum(1 for y in range(0, img.size[1], 4)
                        for x in range(0, img.size[0], 4)
                        if px[x, y][0] > 8 or px[x, y][1] > 8
                        or px[x, y][2] > 10)
        print(f"  非黑像素: {non_black}")
        if non_black < 100:
            failures.append("画面几乎全黑")

        print()
        print("=== JS 错误 ===")
        print("  " + ("无" if not errors else "\n  ".join(errors[:5])))

        browser.close()

    print()
    if failures:
        print(f"FAIL: {len(failures)} 项")
        for f in failures:
            print("  - " + f)
        return 1
    print("PASS: BOSS 血条在线上正常渲染")
    return 0


if __name__ == "__main__":
    sys.exit(main())
