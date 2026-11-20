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

# 统计「按钮描边色」的像素数。
#
# 注意：这个判据随场景美术变化会失效。加入夜景后，月亮 #D8F0F8、
# 苔藓/草丛的浅绿都落进了原来的阈值 (r>160,g>195,b>160)，默认隐藏状态下
# 统计值从 78 涨到 1037，误判成"按键显示了"。
#
# 按钮描边的实际颜色是 Color(0.75,0.91,0.78, alpha) 叠加在深色背景上，
# 展开后接近 (191,232,199)。收紧到这个窄区间，并要求 g-b 和 g-r 的差值
# 都落在按钮色的特征范围内，避开月亮（偏蓝，b 高）和苔藓（b 低但饱和高）。
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
            // 按钮描边（低透明度叠深底）：r 145~205, g 175~235, b 150~215
            // 月亮 b 更高（>230），苔藓 b 更低（<140），都能排除
            if (r > 145 && r < 205 && gg > 175 && gg < 235 &&
                bb > 150 && bb < 218 && gg > r && gg > bb) b++;
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
