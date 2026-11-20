"""在桌面浏览器里检查触摸能力，确认按键为什么会误显示。

用法：
  python tools/probe_desktop_touch.py http://127.0.0.1:8765/
"""

import sys

from playwright.sync_api import sync_playwright

# 桌面环境：明确不带 has_touch
DESKTOP = {
    "viewport": {"width": 1280, "height": 800},
    "device_scale_factor": 1,
    "is_mobile": False,
    "has_touch": False,
}


def main():
    url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765/"
    print(f"target = {url}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(**DESKTOP)
        page = ctx.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(16000)

        info = page.evaluate("""() => ({
            ontouchstart: 'ontouchstart' in window,
            maxTouchPoints: navigator.maxTouchPoints,
            pointerCoarse: window.matchMedia('(pointer: coarse)').matches,
            pointerFine: window.matchMedia('(pointer: fine)').matches,
            anyPointerCoarse: window.matchMedia('(any-pointer: coarse)').matches,
            hoverNone: window.matchMedia('(hover: none)').matches,
        })""")

        print()
        print("=== 桌面环境下的触摸能力（关键判断依据）===")
        for k, v in info.items():
            print(f"  {k}: {v}")

        # 检测按键是否显示。
        # 注意：不能用「浅绿像素数」判断 —— 地形草皮 #6E9A6B 本身就是浅绿，
        # 会把草皮算成按钮（第一版就是这么误判的，明明是隐藏状态却报 336）。
        # 正确做法：按键的**描边**是近乎白的高亮线（#BFF0C7 系），
        # 亮度明显高于草皮，只在按钮的圆弧边缘出现。
        has_buttons = page.evaluate("""() => {
            const src = document.getElementById('canvas');
            const W = src.width, H = src.height;
            const tmp = document.createElement('canvas');
            tmp.width = W; tmp.height = H;
            const g = tmp.getContext('2d');
            g.drawImage(src, 0, 0);
            const d = g.getImageData(0, 0, W, H).data;
            let bright = 0;
            // 扫全屏：按钮描边是 r>160 且 g>200 的近白绿
            for (let y = 0; y < H; y += 2) {
                for (let x = 0; x < W; x += 2) {
                    const i = (y * W + x) * 4;
                    const r = d[i], gg = d[i+1], b = d[i+2];
                    if (r > 160 && gg > 195 && b > 160 && gg > r) bright++;
                }
            }
            return {nearWhiteGreen: bright};
        }""")

        print()
        print(f"=== 近白绿像素数（按钮描边）= {has_buttons['nearWhiteGreen']} ===")
        print("（>100 说明按键被画出来了；隐藏时应接近 0）")

        page.screenshot(path="art/screenshots/desktop_probe.png")
        browser.close()
        print()
        print("截图: art/screenshots/desktop_probe.png")


if __name__ == "__main__":
    main()
