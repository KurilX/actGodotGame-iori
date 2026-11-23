"""统一字体入口。

## 为什么需要这个

Godot 的 `ThemeDB.fallback_font` 在 **Web 导出下不含 CJK 字形**，
所有中文渲染成方块（tofu）。桌面端能看是因为回落到系统字体，
浏览器里没有系统字体可回落。

## 用法

    const F := preload("res://src/ui/game_font.gd")
    var font: Font = F.get_font()

`get_font()` 永远是同一个实例，首次调用时加载。
"""

extends RefCounted

const FONT_PATH := "res://assets/fonts/game_zh.ttf"

static var _cached: Font = null


static func get_font() -> Font:
	if _cached != null:
		return _cached
	if ResourceLoader.exists(FONT_PATH):
		var f = load(FONT_PATH)
		if f is Font:
			_cached = f
			return _cached
	# 兜底：字体缺失时退回默认字体（中文会显示方块，但不至于崩溃）
	# 这种情况会打日志，提醒跑 tools/make_font_subset.py
	if _cached == null:
		printerr("字体缺失：" + FONT_PATH +
				 "，中文会显示为方块。先跑 tools/make_font_subset.py")
		_cached = ThemeDB.fallback_font
	return _cached
