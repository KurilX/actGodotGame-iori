extends Control
## 道具获得演出：横幅 + 图标 + 技能名，附带一次全屏光效。
##
## ## 时序
##
##   0.0s  横幅从上方滑入，道具图标在中心放大出现
##   0.3s  图标开始旋转发光
##   1.6s  横幅保持（给玩家读技能描述的时间）
##   2.8s  淡出
##
## ## 为什么需要这个
##
## BOSS 死后如果只是"血条没了"，玩家不知道发生了什么。
## 必须有一个明确的"你获得了 X"的时刻，否则奖励感为零。

signal finished

const BANNER_H := 54.0
const ICON_SIZE := 48.0

const C_BG := Color(0.03, 0.04, 0.09, 0.92)
const C_EDGE := Color("#B9F2FF")
const C_TEXT := Color("#E8F0F2")
const C_SUB := Color("#8FD3E8")
const C_ACCENT := Color("#FFC46B")

var _t := 0.0
var _active := false
var _icon: Texture2D = null
var _title := ""
var _desc := ""

# 阶段：0=滑入 1=保持 2=淡出
const T_IN := 0.32
const T_HOLD := 2.45
const T_OUT := 0.55
const T_TOTAL := T_IN + T_HOLD + T_OUT


func _ready() -> void:
	set_anchors_preset(Control.PRESET_FULL_RECT)
	offset_left = 0
	offset_top = 0
	offset_right = 0
	offset_bottom = 0
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	visible = false
	set_process(false)


func show_item(title: String, desc: String, icon_path: String) -> void:
	_title = title
	_desc = desc
	_icon = null
	if ResourceLoader.exists(icon_path):
		_icon = load(icon_path)
	_t = 0.0
	_active = true
	visible = true
	set_process(true)
	queue_redraw()


func _process(delta: float) -> void:
	if not _active:
		return
	_t += delta
	if _t >= T_TOTAL:
		_active = false
		visible = false
		set_process(false)
		finished.emit()
		queue_redraw()
		return
	queue_redraw()


func _alpha() -> float:
	if _t < T_IN:
		return _t / T_IN
	if _t < T_IN + T_HOLD:
		return 1.0
	return maxf(0.0, 1.0 - (_t - T_IN - T_HOLD) / T_OUT)


func _slide() -> float:
	"""横幅滑入进度 0→1。"""
	if _t >= T_IN:
		return 1.0
	var k := _t / T_IN
	# 缓出，落位时有个轻微过冲
	return 1.0 - pow(1.0 - k, 3)


func _draw() -> void:
	if not _active:
		return

	var vs := get_viewport_rect().size
	var a := _alpha()
	var slide := _slide()

	# ── 全屏压暗（轻微）──
	draw_rect(Rect2(Vector2.ZERO, vs), Color(0.02, 0.03, 0.07, 0.35 * a))

	# ── 横幅：从上方滑入 ──
	var bh := BANNER_H
	var by := -bh + (vs.y * 0.28 + bh) * slide
	var bw := vs.x * 0.86
	var bx := (vs.x - bw) * 0.5

	draw_rect(Rect2(bx, by, bw, bh), Color(C_BG.r, C_BG.g, C_BG.b, C_BG.a * a))
	# 上下边缘亮线
	draw_rect(Rect2(bx, by, bw, 1.5),
			  Color(C_EDGE.r, C_EDGE.g, C_EDGE.b, 0.85 * a))
	draw_rect(Rect2(bx, by + bh - 1.5, bw, 1.5),
			  Color(C_EDGE.r, C_EDGE.g, C_EDGE.b, 0.45 * a))

	# ── 图标：在横幅左侧，带脉动缩放和旋转光晕 ──
	if _icon != null:
		var pulse := 1.0 + 0.06 * sin(_t * 7.0)
		var sz := ICON_SIZE * pulse
		var ix := bx + 14.0 + (ICON_SIZE - sz) * 0.5
		var iy := by + (bh - sz) * 0.5

		# 光晕：几圈同心硬边圆（像素风不用平滑渐变）
		var glow_a := a * (0.20 + 0.10 * sin(_t * 5.0))
		var cx := ix + sz * 0.5
		var cy := iy + sz * 0.5
		for r in [sz * 0.95, sz * 0.72, sz * 0.55]:
			draw_arc(Vector2(cx, cy), r, 0.0, TAU, 28,
					 Color(C_EDGE.r, C_EDGE.g, C_EDGE.b, glow_a), 1.5)

		draw_texture_rect(_icon, Rect2(ix, iy, sz, sz), false,
						  Color(1, 1, 1, a))

	# ── 文字 ──
	var font := ThemeDB.fallback_font
	var tx := bx + 14.0 + (ICON_SIZE if _icon != null else 0.0) + 14.0
	var ty := by + 22.0

	# 标题：加粗感靠描边
	for off in [Vector2(-1, 0), Vector2(1, 0), Vector2(0, -1), Vector2(0, 1)]:
		draw_string(font, Vector2(tx, ty) + off, _title,
					HORIZONTAL_ALIGNMENT_LEFT, -1, 15,
					Color(0.03, 0.04, 0.09, a))
	draw_string(font, Vector2(tx, ty), _title,
				HORIZONTAL_ALIGNMENT_LEFT, -1, 15,
				Color(C_ACCENT.r, C_ACCENT.g, C_ACCENT.b, a))

	# 描述：小字
	if _desc != "":
		draw_string(font, Vector2(tx, ty + 17), _desc,
					HORIZONTAL_ALIGNMENT_LEFT, -1, 10,
					Color(C_SUB.r, C_SUB.g, C_SUB.b, a * 0.95))

	# ── 顶部"获得"标签（小字，横幅上方）──
	if slide > 0.9:
		var la := a * (slide - 0.9) / 0.1
		var lw := font.get_string_size("获得道具", HORIZONTAL_ALIGNMENT_LEFT,
									   -1, 9).x
		draw_string(font, Vector2((vs.x - lw) * 0.5, by - 6), "获得道具",
					HORIZONTAL_ALIGNMENT_LEFT, -1, 9,
					Color(C_EDGE.r, C_EDGE.g, C_EDGE.b, la * 0.8))


func is_active() -> bool:
	return _active
