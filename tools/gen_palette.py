import os

PALETTE = [
    ("01_ink",        "#12142A", "描边 / 深渊"),
    ("02_night_far",  "#1B2244", "夜色远景"),
    ("03_night_mid",  "#2A3A63", "夜色中景"),
    ("04_night_near", "#3D5385", "夜色近景"),
    ("05_moon_hi",    "#8FD3E8", "月光高光"),
    ("06_moon_white", "#D8F0F8", "月白"),
    ("07_stone",      "#5A6478", "石材中"),
    ("08_stone_dark", "#394051", "石材暗"),
    ("09_stone_lit",  "#7B8699", "石材亮"),
    ("10_moss",       "#4A6B4F", "苔中"),
    ("11_moss_dark",  "#2E4634", "苔暗"),
    ("12_moss_lit",   "#6E9A6B", "苔亮"),
    ("13_wisteria",   "#7A5FA8", "紫藤中"),
    ("14_wisteria_d", "#4F3D74", "紫藤暗"),
    ("15_wisteria_l", "#A98FD6", "紫藤亮"),
    ("16_lantern_hi", "#FFE9A8", "灯笼亮"),
    ("17_lantern",    "#FFC46B", "灯笼中"),
    ("18_lantern_d",  "#E0913F", "灯笼暗"),
    ("19_cape_lit",   "#F2F8EC", "主角披肩亮"),
    ("20_cape_dark",  "#C4D8C2", "主角披肩暗"),
    ("21_hair_lit",   "#A8E8C6", "发色亮"),
    ("22_hair_dark",  "#5FA882", "发色暗"),
    ("23_skin_lit",   "#FBE3D2", "肤色亮"),
    ("24_skin_dark",  "#E2B49B", "肤色暗"),
    ("25_danger",     "#FF7A9C", "危险 / 弹幕"),
    ("26_danger_d",   "#C2456A", "危险暗"),
    ("27_thread",     "#B9F2FF", "丝线光"),
    ("28_white",      "#FFFFFF", "纯白高光"),
]


def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def write_gpl(path):
    lines = [
        "GIMP Palette",
        "Name: Ori 28",
        "Columns: 8",
        "# 缀 / actGame 像素色板 28 色硬上限",
    ]
    for name, hexv, desc in PALETTE:
        r, g, b = hex_to_rgb(hexv)
        lines.append(f"{r:3d} {g:3d} {b:3d}\t{name}  {desc}")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")


def write_hex(path):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(f"{hexv}\t{name}\t{desc}"
                          for name, hexv, desc in PALETTE) + "\n")


def write_godot(path):
    entries = []
    for i, (name, hexv, desc) in enumerate(PALETTE):
        r, g, b = hex_to_rgb(hexv)
        entries.append(
            f'\t"{name}": Color({r / 255:.6f}, {g / 255:.6f}, {b / 255:.6f}, 1),'
        )
    body = "\n".join(entries)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(
            "# 缀 / actGame 28 色板 —— 由 tools/gen_palette.py 生成，勿手改\n"
            "# 用法：const P := preload(\"res://art/palette.gd\"); 然后 P.COLORS[\"01_ink\"]\n"
            "const COLORS := {\n" + body + "\n}\n"
        )


if __name__ == "__main__":
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    art = os.path.join(base, "art")
    os.makedirs(art, exist_ok=True)
    write_gpl(os.path.join(art, "palette.gpl"))
    write_hex(os.path.join(art, "palette.hex.txt"))
    write_godot(os.path.join(art, "palette.gd"))
    print(f"wrote {len(PALETTE)} colors")
