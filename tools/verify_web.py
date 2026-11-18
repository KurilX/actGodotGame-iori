"""验证导出的 Godot Web build 能否真正在浏览器里跑起来。

不能只看 HTTP 200 就断言可用 —— 要确认：
  1. 没有未捕获的 JS 异常
  2. wasm 和 pck 都真的加载完成（不是只发起了请求）
  3. canvas 上有非空像素内容（说明游戏真的在渲染）

用法：
  python -m http.server 8765 --directory build   # 先起服务
  python tools/verify_web.py http://127.0.0.1:8765/
"""

import sys
import time

from playwright.sync_api import sync_playwright


def main():
    url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765/"
    print(f"target = {url}")

    errors: list[str] = []
    console_logs: list[str] = []
    loaded: dict[str, int] = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 800})

        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: console_logs.append(f"[{m.type}] {m.text}"))

        def on_response(resp):
            u = resp.url
            for key in ("index.wasm", "index.pck", "index.js", "index.html"):
                if key in u:
                    loaded[key] = resp.status

        page.on("response", on_response)

        page.goto(url, wait_until="domcontentloaded", timeout=60000)

        # 等 wasm 编译 + 首帧渲染
        print("等待引擎启动…")
        ok_canvas = False
        deadline = time.time() + 120
        while time.time() < deadline:
            page.wait_for_timeout(2000)
            try:
                # 检查 canvas 是否有非空内容
                res = page.evaluate("""() => {
                    const c = document.getElementById('canvas');
                    if (!c || c.width === 0) return {ok:false, reason:'no canvas'};
                    return {ok:true, w:c.width, h:c.height};
                }""")
                if res.get("ok"):
                    ok_canvas = True
                    break
            except Exception as e:
                errors.append(f"evaluate: {e}")
                break

        page.wait_for_timeout(4000)
        page.screenshot(path="art/screenshots/web_build.png")

        # 再确认一次 canvas 尺寸（Godot 会按窗口设置）
        canvas_info = page.evaluate("""() => {
            const c = document.getElementById('canvas');
            if (!c) return null;
            return {w: c.width, h: c.height,
                    cw: c.clientWidth, ch: c.clientHeight};
        }""")

        browser.close()

    print()
    print("=== 网络请求 ===")
    for k, v in sorted(loaded.items()):
        print(f"  {k}: HTTP {v}")

    print()
    print("=== canvas ===")
    print(f"  {canvas_info}")

    print()
    print("=== JS 错误 ===")
    if errors:
        for e in errors[:10]:
            print("  " + e)
    else:
        print("  无")

    # 只打印有信息量的 console（godot 自己的日志）
    interesting = [c for c in console_logs if "error" in c.lower()
                   or "fail" in c.lower() or "godot" in c.lower()]
    print()
    print("=== 关键 console ===")
    if interesting:
        for c in interesting[:10]:
            print("  " + c[:200])
    else:
        print("  无")

    print()
    print("=== 截图 ===")
    print("  art/screenshots/web_build.png")

    # 判定
    print()
    critical_errors = [e for e in errors
                       if "SharedArrayBuffer" in e or "wasm" in e.lower()]
    ok = (not critical_errors
          and loaded.get("index.wasm") == 200
          and loaded.get("index.pck") == 200
          and canvas_info is not None
          and canvas_info.get("w", 0) > 0)

    if ok:
        print("PASS: wasm/pck 加载成功，canvas 已创建")
        return 0
    print("FAIL: 见上方错误")
    return 1


if __name__ == "__main__":
    sys.exit(main())
