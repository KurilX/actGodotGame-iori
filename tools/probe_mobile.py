"""用 Playwright 模拟手机触摸设备，探测线上/本地 Web 版的实际表现。

目的：在动手写触屏控制之前，先确认三件事：
  1. 手机视口下 canvas 实际尺寸是多少（是否被裁切）
  2. 触摸事件能否到达页面
  3. Godot 是否识别为触摸设备（ProjectSettings "input_devices/pointing" 相关）

用法：
  python tools/probe_mobile.py https://kurilx.github.io/actGodotGame-iori/
"""

import sys

from playwright.sync_api import sync_playwright

# iPhone 13 的常见视口（横屏，因为游戏是横版）
MOBILE = {
    "viewport": {"width": 844, "height": 390},
    "device_scale_factor": 3,
    "is_mobile": True,
    "has_touch": True,
}


def main():
    url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765/"
    print(f"target = {url}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(**MOBILE,
                                  user_agent=("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 "
                                              "like Mac OS X) AppleWebKit/605.1.15 "
                                              "(KHTML, like Gecko) Version/17.0 Mobile/15E148 "
                                              "Safari/604.1"))
        page = ctx.new_page()

        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))

        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(15000)

        info = page.evaluate("""() => {
            const c = document.getElementById('canvas');
            const r = c ? c.getBoundingClientRect() : null;
            return {
                innerW: window.innerWidth,
                innerH: window.innerHeight,
                dpr: window.devicePixelRatio,
                hasTouch: 'ontouchstart' in window || navigator.maxTouchPoints > 0,
                maxTouchPoints: navigator.maxTouchPoints,
                canvasAttr: c ? {w: c.width, h: c.height} : null,
                canvasRect: r ? {x: r.x, y: r.y, w: r.width, h: r.height} : null,
                // 是否被裁切（画布超出视口）
                clipped: r ? (r.width > window.innerWidth + 1 ||
                              r.height > window.innerHeight + 1) : null,
            };
        }""")

        print()
        print("=== 手机视口下的实际状态 ===")
        for k, v in info.items():
            print(f"  {k}: {v}")

        print()
        print("=== JS 错误 ===")
        print("  " + ("无" if not errors else "\n  ".join(errors[:5])))

        page.screenshot(path="art/screenshots/mobile_before.png")

        # 尝试模拟一次触摸，看是否有反应
        rect = info.get("canvasRect")
        if rect:
            cx = rect["x"] + rect["w"] * 0.25
            cy = rect["y"] + rect["h"] * 0.5
            page.touchscreen.tap(cx, cy)
            page.wait_for_timeout(500)
            print()
            print(f"=== 已模拟在 ({cx:.0f},{cy:.0f}) 点击 ===")

        page.wait_for_timeout(1000)
        page.screenshot(path="art/screenshots/mobile_after_tap.png")

        browser.close()
        print()
        print("截图: art/screenshots/mobile_before.png / mobile_after_tap.png")


if __name__ == "__main__":
    main()
