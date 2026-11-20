"""验证动画展示页：所有 GIF 是否真的加载成功、布局是否正常。

不只看 HTTP 200，要确认浏览器里每个 <img> 的 naturalWidth > 0
（即 GIF 真的被解码，不是破图）。

用法：python tools/verify_showcase.py http://127.0.0.1:8899/animations.html
"""

import sys

from playwright.sync_api import sync_playwright

DESKTOP = {"viewport": {"width": 1440, "height": 1000}, "device_scale_factor": 1}


def main():
    url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8899/animations.html"
    print(f"target = {url}")

    failures = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(**DESKTOP)
        page = ctx.new_page()

        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("requestfailed",
                lambda r: errors.append(f"请求失败 {r.url}"))

        page.goto(url, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(2500)

        # 检查所有 img
        imgs = page.evaluate("""() => {
            return Array.from(document.images).map(im => ({
                src: im.getAttribute('src'),
                loaded: im.complete && im.naturalWidth > 0,
                w: im.naturalWidth,
                h: im.naturalHeight,
                alt: im.alt || '',
            }));
        }""")

        print()
        print(f"=== 图片检查（{len(imgs)} 个）===")
        bad = []
        for im in imgs:
            mark = "OK  " if im["loaded"] else "FAIL"
            print(f"  {mark} {im['src']:<28} {im['w']}x{im['h']}  {im['alt']}")
            if not im["loaded"]:
                bad.append(im["src"])

        if bad:
            failures.append(f"{len(bad)} 张图没加载: {bad}")

        # 分区标题
        heads = page.evaluate("""() => Array.from(
            document.querySelectorAll('.sec-head h2')).map(h => h.textContent.trim())""")
        print()
        print(f"=== 分区（{len(heads)} 个）===")
        for h in heads:
            print(f"  · {h}")

        # 卡片数
        cards = page.eval_on_selector_all(".card", "els => els.length")
        print()
        print(f"=== 卡片数: {cards} ===")

        # 检查是否有横向溢出
        overflow = page.evaluate("""() => {
            return document.documentElement.scrollWidth >
                   document.documentElement.clientWidth + 2;
        }""")
        print(f"=== 横向溢出: {overflow} ===")
        if overflow:
            failures.append("页面存在横向溢出")

        page.screenshot(path="art/screenshots/showcase_top.png")
        # 整页截图
        page.screenshot(path="art/screenshots/showcase_full.png", full_page=True)

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
    print("PASS: 所有 GIF 加载成功，布局正常")
    return 0


if __name__ == "__main__":
    sys.exit(main())
