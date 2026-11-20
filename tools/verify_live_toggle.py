"""线上验证：默认隐藏、?touch=1 显示。

用法：python tools/verify_live_toggle.py
"""

from playwright.sync_api import sync_playwright

DESKTOP = {
    "viewport": {"width": 1280, "height": 800},
    "device_scale_factor": 1,
    "is_mobile": False,
    "has_touch": False,
}

BASE = "https://kurilx.github.io/actGodotGame-iori/"

JS_COUNT = """() => {
    const s = document.getElementById('canvas');
    const W = s.width, H = s.height;
    const t = document.createElement('canvas');
    t.width = W; t.height = H;
    const g = t.getContext('2d');
    g.drawImage(s, 0, 0);
    const d = g.getImageData(0, 0, W, H).data;
    let b = 0;
    for (let y = 0; y < H; y += 2) {
        for (let x = 0; x < W; x += 2) {
            const i = (y * W + x) * 4;
            const r = d[i], gg = d[i+1], bb = d[i+2];
            if (r > 160 && gg > 195 && bb > 160 && gg > r) b++;
        }
    }
    return b;
}"""


def main():
    failures = []
    with sync_playwright() as p:
        br = p.chromium.launch(headless=True)

        cases = [
            ("默认（无参数）", BASE, True),
            ("?touch=1", BASE + "?touch=1", False),
        ]

        for label, url, expect_hidden in cases:
            ctx = br.new_context(**DESKTOP)
            page = ctx.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(16000)
            n = page.evaluate(JS_COUNT)
            hidden = n < 100
            ok = hidden == expect_hidden
            tag = "OK" if ok else "FAIL"
            print(f"  {label:<14} 描边像素={n:<4} 期望{'隐藏' if expect_hidden else '显示'}  [{tag}]")
            if not ok:
                failures.append(f"{label}: 像素数 {n}，期望{'隐藏' if expect_hidden else '显示'}")
            fname = "live_default.png" if expect_hidden else "live_touch1.png"
            page.screenshot(path="art/screenshots/" + fname)
            ctx.close()

        br.close()

    print()
    if failures:
        print(f"FAIL: {len(failures)} 项")
        for f in failures:
            print("  - " + f)
        return 1
    print("PASS: 线上默认隐藏，?touch=1 可开启")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
