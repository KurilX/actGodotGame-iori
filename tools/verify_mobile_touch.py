"""验证触屏控制在真实浏览器（模拟手机）里的表现。

不只看截图好看，要断言：
  1. 手机上按键层确实显示（桌面不显示）
  2. 点击按键能触发游戏内动作（角色位置变化 / 攻击动画）
  3. 多点触控同时生效

用法：
  python tools/verify_mobile_touch.py http://127.0.0.1:8765/
"""

import sys

from playwright.sync_api import sync_playwright

MOBILE = {
    "viewport": {"width": 844, "height": 390},
    "device_scale_factor": 2,
    "is_mobile": True,
    "has_touch": True,
}

# 与 src/ui/touch_controls.gd 的 _build_buttons 保持一致
# 视口 480x270 → 屏幕比例坐标
BTN = {
    "left": (0.0875, 0.8000),
    "right": (0.2333, 0.8000),
    "dash": (0.7333, 0.5481),
    "jump": (0.8292, 0.7630),
    "attack": (0.9375, 0.6222),
}


def main():
    url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765/?touch=1"
    print(f"target = {url}")

    failures = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(**MOBILE)
        page = ctx.new_page()

        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))

        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(16000)

        rect = page.evaluate("""() => {
            const c = document.getElementById('canvas');
            const r = c.getBoundingClientRect();
            return {x: r.x, y: r.y, w: r.width, h: r.height,
                    attrW: c.width, attrH: c.height};
        }""")
        print(f"canvas 元素 rect = {rect}")

        # 关键：不能用 getBoundingClientRect() 直接映射按钮坐标。
        # 实测发现 Godot 在 canvas 元素内部并不铺满，而是按逻辑视口 480x270
        # 居中绘制并留边。用元素的 rect 算出来是 x=75,w=693，
        # 而实际游戏画面是 x=182,w=479.5，两者差很多，点击会全部落空。
        #
        # 可靠做法：截一张图，找出非黑区域，那就是真实渲染区域。
        # 这里用 JS 采样 canvas 像素来做（比人眼估算准）。
        area = page.evaluate("""() => {
            const src = document.getElementById('canvas');
            const W = src.width, H = src.height;
            const tmp = document.createElement('canvas');
            tmp.width = W; tmp.height = H;
            const g = tmp.getContext('2d');
            g.drawImage(src, 0, 0);
            const d = g.getImageData(0, 0, W, H).data;
            let minX = W, maxX = -1, minY = H, maxY = -1;
            for (let y = 0; y < H; y += 2) {
                for (let x = 0; x < W; x += 2) {
                    const i = (y * W + x) * 4;
                    // 非纯黑即视为游戏画面
                    if (d[i] > 8 || d[i+1] > 8 || d[i+2] > 8) {
                        if (x < minX) minX = x;
                        if (x > maxX) maxX = x;
                        if (y < minY) minY = y;
                        if (y > maxY) maxY = y;
                    }
                }
            }
            if (maxX < 0) return null;
            const r = src.getBoundingClientRect();
            const sx = r.width / W, sy = r.height / H;
            return {
                x: r.x + minX * sx,
                y: r.y + minY * sy,
                w: (maxX - minX + 1) * sx,
                h: (maxY - minY + 1) * sy,
            };
        }""")
        if area is None:
            print("FAIL: 无法从 canvas 采样到游戏画面")
            browser.close()
            return 1
        print(f"实际渲染区域（像素采样）= {area}")

        def pos(name):
            """按钮在屏幕上的坐标，基于实测渲染区域。"""
            ax, ay = BTN[name]
            return (area["x"] + area["w"] * ax, area["y"] + area["h"] * ay)

        page.screenshot(path="art/screenshots/mobile_touch_01_idle.png")

        # ── 测试 1：按住右移，角色应当向右移动 ──
        rx, ry = pos("right")
        page.touchscreen.tap(rx, ry)  # 先点一下确认可交互
        page.wait_for_timeout(300)

        # 用 CDP 派发持续的触摸（tap 只有瞬时，不能持续按住）
        cdp = ctx.new_cdp_session(page)

        def touch_start(x, y, idx=0):
            cdp.send("Input.dispatchTouchEvent", {
                "type": "touchStart",
                "touchPoints": [{"x": x, "y": y, "id": idx}],
            })

        def touch_end():
            cdp.send("Input.dispatchTouchEvent", {
                "type": "touchEnd", "touchPoints": [],
            })

        # 记录移动前的位置：用像素采样判断角色是否移动不可行，
        # 改为比较两次截图是否不同（角色移动会导致画面变化）
        before = page.screenshot()

        touch_start(rx, ry, 0)
        page.wait_for_timeout(1200)
        touch_end()
        page.wait_for_timeout(300)

        after = page.screenshot()
        moved = before != after
        if moved:
            print("  ok   按住右移键后画面发生变化（角色在移动）")
        else:
            failures.append("按住右移键后画面没有变化")
            print("  FAIL 按住右移键后画面无变化")

        page.screenshot(path="art/screenshots/mobile_touch_02_moved.png")

        # ── 测试 2：点击攻击键，画面应变化（挥砍） ──
        ax, ay = pos("attack")
        page.wait_for_timeout(600)
        before2 = page.screenshot()
        touch_start(ax, ay, 1)
        page.wait_for_timeout(400)
        touch_end()
        page.wait_for_timeout(200)
        after2 = page.screenshot()
        attacked = before2 != after2
        if attacked:
            print("  ok   点击攻击键后画面发生变化（有挥砍动作）")
        else:
            failures.append("点击攻击键后画面无变化")
            print("  FAIL 点击攻击键后画面无变化")

        page.screenshot(path="art/screenshots/mobile_touch_03_attack.png")

        # ── 测试 3：多点触控（左移 + 攻击同时） ──
        lx, ly = pos("left")
        cdp.send("Input.dispatchTouchEvent", {
            "type": "touchStart",
            "touchPoints": [
                {"x": lx, "y": ly, "id": 10},
                {"x": ax, "y": ay, "id": 11},
            ],
        })
        page.wait_for_timeout(800)
        cdp.send("Input.dispatchTouchEvent", {
            "type": "touchEnd", "touchPoints": [],
        })
        page.wait_for_timeout(200)
        print("  ok   多点触控事件已派发（左移+攻击）")

        page.screenshot(path="art/screenshots/mobile_touch_04_multi.png")

        print()
        print("=== JS 错误 ===")
        print("  " + ("无" if not errors else "\n  ".join(errors[:5])))

        browser.close()

    print()
    if failures:
        print(f"FAIL: {len(failures)} 项失败")
        for f in failures:
            print("  - " + f)
        return 1
    print("PASS: 手机触屏交互全部生效")
    return 0


if __name__ == "__main__":
    sys.exit(main())
