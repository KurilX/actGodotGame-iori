"""验证 ?touch=1 能打开虚拟按键，以及默认状态下不显示。

用法：
  python tools/verify_touch_toggle.py http://127.0.0.1:8765/
"""

import sys

from playwright.sync_api import sync_playwright

DESKTOP = {
    "viewport": {"width": 1280, "height": 800},
    "device_scale_factor": 1,
    "is_mobile": False,
    "has_touch": False,
}

MOBILE = {
    "viewport": {"width": 844, "height": 390},
    "device_scale_factor": 2,
    "is_mobile": True,
    "has_touch": True,
}


def count_button_edges(page):
    """统计按钮描边的近白绿像素。

    注意：地形草皮 #6E9A6B 也是浅绿，用低阈值会把草皮算进来
    （早期用 gg>90 判断时，隐藏状态也报 336，完全误判）。
    这里要求 r>160 且 g>195，只有按钮描边这种近白绿才满足。
    实测：隐藏 ≈64（角色/木桩自身高光），显示 ≈123。
    """
    return page.evaluate("""() => {
        const src = document.getElementById('canvas');
        const W = src.width, H = src.height;
        const tmp = document.createElement('canvas');
        tmp.width = W; tmp.height = H;
        const g = tmp.getContext('2d');
        g.drawImage(src, 0, 0);
        const d = g.getImageData(0, 0, W, H).data;
        let bright = 0;
        for (let y = 0; y < H; y += 2) {
            for (let x = 0; x < W; x += 2) {
                const i = (y * W + x) * 4;
                const r = d[i], gg = d[i+1], b = d[i+2];
                if (r > 160 && gg > 195 && b > 160 && gg > r) bright++;
            }
        }
        return bright;
    }""")


def main():
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765/"
    if not base.endswith("/"):
        base += "/"
    failures = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        print("=== 场景 1：桌面浏览器，无参数（应隐藏）===")
        ctx = browser.new_context(**DESKTOP)
        page = ctx.new_page()
        page.goto(base, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(16000)
        n1 = count_button_edges(page)
        print(f"  描边像素 = {n1}")
        page.screenshot(path="art/screenshots/toggle_01_desktop_default.png")
        if n1 < 100:
            print("  ok   桌面默认不显示按键")
        else:
            failures.append(f"桌面默认仍显示按键（{n1}）")
            print("  FAIL 桌面默认仍显示按键")
        ctx.close()

        print()
        print("=== 场景 2：桌面浏览器 + ?touch=1（应显示）===")
        ctx = browser.new_context(**DESKTOP)
        page = ctx.new_page()
        page.goto(base + "?touch=1", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(16000)
        n2 = count_button_edges(page)
        print(f"  描边像素 = {n2}")
        page.screenshot(path="art/screenshots/toggle_02_desktop_forced.png")
        if n2 > 100:
            print("  ok   ?touch=1 能打开按键")
        else:
            failures.append(f"?touch=1 没打开按键（{n2}）")
            print("  FAIL ?touch=1 没打开按键")
        ctx.close()

        print()
        print("=== 场景 3：手机，无参数（默认也隐藏，需显式开启）===")
        ctx = browser.new_context(**MOBILE)
        page = ctx.new_page()
        page.goto(base, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(16000)
        n3 = count_button_edges(page)
        print(f"  描边像素 = {n3}")
        page.screenshot(path="art/screenshots/toggle_03_mobile_default.png")
        if n3 < 100:
            print("  ok   手机默认也不显示（与桌面行为一致）")
        else:
            failures.append(f"手机默认显示了按键（{n3}）")
            print("  FAIL 手机默认显示了按键")
        ctx.close()

        print()
        print("=== 场景 4：手机 + ?touch=1（应显示，且可操作）===")
        ctx = browser.new_context(**MOBILE)
        page = ctx.new_page()
        page.goto(base + "?touch=1", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(16000)
        n4 = count_button_edges(page)
        print(f"  描边像素 = {n4}")
        page.screenshot(path="art/screenshots/toggle_04_mobile_forced.png")
        if n4 > 100:
            print("  ok   手机 + ?touch=1 显示按键")
        else:
            failures.append(f"手机 + ?touch=1 没显示按键（{n4}）")
            print("  FAIL 手机 + ?touch=1 没显示按键")
        ctx.close()

        browser.close()

    print()
    if failures:
        print(f"FAIL: {len(failures)} 项失败")
        for f in failures:
            print("  - " + f)
        return 1
    print("PASS: 默认隐藏 + ?touch=1 开启，行为全部正确")
    return 0


if __name__ == "__main__":
    sys.exit(main())
