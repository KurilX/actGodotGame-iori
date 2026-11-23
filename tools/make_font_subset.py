"""把中文字体子集化，只保留游戏里实际用到的字。

## 为什么必须做

Godot 的 `ThemeDB.fallback_font` 在 **Web 导出下不含 CJK 字形**，
所有中文都渲染成方块（tofu）。桌面端能看到是因为回落到系统字体，
但 Web 没有系统字体。

## 为什么要子集化

`simhei.ttf` 有 9.3MB，全量嵌进去会让 pck 暴涨。
而游戏实际只用到 600 多个汉字，子集后通常只有几百 KB。

## 不丢字

子集化会漏掉"以后新加的中文" —— 所以除源码里的字，
额外把**常用标点、数字、ASCII、以及 GB2312 一级字库**
（3755 字）一起打包。3755 字的子集也就 1~2MB，
比全量 9.3MB 小，又足够覆盖后续文案。

输出：assets/fonts/game_zh.ttf
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_FONT = r"C:\Windows\Fonts\simhei.ttf"
OUT_DIR = os.path.join(ROOT, "assets", "fonts")
OUT_FONT = os.path.join(OUT_DIR, "game_zh.ttf")

# 常用标点与符号
PUNCT = "　、。，．·；：！？…—～“”‘’（）【】《》〈〉「」『』〔〕％＋－×÷＝／＼"

# ASCII 全段
ASCII = "".join(chr(c) for c in range(0x20, 0x7F))

# GB2312 一级汉字区（0xB0A1..0xD7F9）—— 3755 个最常用汉字。
# 用它做兜底，保证以后加新文案也不会出现方块。
GB2312_LEVEL1_START = (0xB0, 0xA1)
GB2312_LEVEL1_END = (0xD7, 0xF9)


def gb2312_level1() -> str:
    out = []
    for hi in range(GB2312_LEVEL1_START[0], GB2312_LEVEL1_END[0] + 1):
        for lo in range(0xA1, 0xFF):
            try:
                ch = bytes([hi, lo]).decode("gb2312")
            except UnicodeDecodeError:
                continue
            out.append(ch)
    return "".join(out)


def collect_source_chars() -> str:
    """扫描 src/ 下所有 .gd 的双引号字符串，提取其中出现的字符。"""
    chars = set()
    src = os.path.join(ROOT, "src")
    for dirpath, _dirnames, filenames in os.walk(src):
        for fn in filenames:
            if not fn.endswith(".gd"):
                continue
            path = os.path.join(dirpath, fn)
            with open(path, encoding="utf-8") as f:
                text = f.read()
            for m in re.finditer(r'"([^"]*)"', text):
                for ch in m.group(1):
                    if ord(ch) > 0x7F:
                        chars.add(ch)
    return "".join(sorted(chars))


def main():
    if not os.path.exists(SRC_FONT):
        print(f"找不到源字体 {SRC_FONT}", file=sys.stderr)
        return 1

    os.makedirs(OUT_DIR, exist_ok=True)

    src_chars = collect_source_chars()
    print(f"源码里用到 {len(src_chars)} 个非 ASCII 字符")

    try:
        level1 = gb2312_level1()
    except Exception as e:  # noqa: BLE001
        print(f"GB2312 展开失败（{e}），只打包源码字符", file=sys.stderr)
        level1 = ""

    # 合集：ASCII + 标点 + 源码字符 + GB2312 一级
    charset = set(ASCII) | set(PUNCT) | set(src_chars) | set(level1)
    text = "".join(sorted(charset))
    print(f"子集目标：{len(text)} 个字符"
          f"（ASCII {len(ASCII)} + 源码 {len(src_chars)} + GB2312 一级 {len(level1)}）")

    from fontTools import subset

    options = subset.Options()
    options.set(layout_features="*")
    options.name_IDs = ["*"]
    options.notdef_outline = True
    options.recalc_bounds = True
    options.drop_tables = []

    font = subset.load_font(SRC_FONT, options)
    subsetter = subset.Subsetter(options=options)
    subsetter.populate(text=text)
    subsetter.subset(font)
    subset.save_font(font, OUT_FONT, options)
    font.close()

    sz = os.path.getsize(OUT_FONT)
    print(f"输出 {OUT_FONT}")
    print(f"  大小 {sz / 1024:.0f} KB（原字体 "
          f"{os.path.getsize(SRC_FONT) / 1024 / 1024:.1f} MB）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
