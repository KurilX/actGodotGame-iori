extends Control

const GameFont := preload("res://src/ui/game_font.gd")
## BOSS 血条：屏幕顶部横条，分三段显示阶段。
##
## ## 为什么分段画
##
## 单条血条只能告诉玩家"还剩多少"，分段则额外传达"还有几个阶段"。
## 玩家看到第三段亮起，就知道要进入最难的阶段了 —— 这是预期管理。
##
## ## 视觉
##
##   · 三段之间留 4px 间隙，每段对应一个阶段
##   · 当前阶段段位用暖色填充，已过的阶段变暗，未来的阶段只是轮廓
##   · 顶部有 BOSS 名字（用默认字体，带深色描边保证可读性）
##   · 受伤时血条有一次白色闪烁（受击反馈要在 UI 上也体现）

const SEGMENTS := 3
const BAR_H := 10.0
const BAR_W := 300.0
const SEG_GAP := 5.0
const MARGIN_TOP := 14.0

const C_FILL := Color("#FF5A6E")
const C_FILL_HOT := Color("#FFE9A8")
const C_EMPTY := Color(0.10, 0.12, 0.22, 0.85)
const C_EDGE := Color("#12142A")
const C_TEXT := Color("#E8F0F2")

var _hp := 1.0                 # 0..1
var _hp_shown := 1.0           # 平滑追赶值
var _flash := 0.0
var _phase := 1
var _name := "瓷面的守夜人"
var _active := false


func _ready() -> void:
	# **关键**：只调 set_anchors_preset 不够 —— 它保留了原有的 offset，
	# 结果 Control 的实际尺寸是 (0,0)（实测 offset_right = -480），
	# draw_* 画在尺寸为 0 的节点上会被裁剪，导致血条整体偏到左上角。
	# 必须显式把四个 offset 清零，才能得到真正的全屏矩形。
	set_anchors_preset(Control.PRESET_FULL_RECT)
	offset_left = 0
	offset_top = 0
	offset_right = 0
	offset_bottom = 0
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	visible = false


func show_boss(name_text: String) -> void:
	_name = name_text
	_active = true
	visible = true
	_hp = 1.0
	_hp_shown = 1.0
	_phase = 1
	_flash = 0.0
	queue_redraw()


func hide_boss() -> void:
	_active = false
	visible = false


func set_hp(ratio: float) -> void:
	ratio = clampf(ratio, 0.0, 1.0)
	if ratio < _hp:
		_flash = 1.0
	_hp = ratio
	queue_redraw()


func set_phase(p: int) -> void:
	_phase = clampi(p, 1, SEGMENTS)
	_flash = 1.0
	queue_redraw()


func _process(delta: float) -> void:
	if not _active:
		return
	# 平滑追赶（受伤后血条缓慢降到实际值，更有打击感）
	_hp_shown = lerpf(_hp_shown, _hp, 1.0 - pow(0.0005, delta))
	if absf(_hp_shown - _hp) < 0.001:
		_hp_shown = _hp
	if _flash > 0.0:
		_flash = maxf(_flash - delta * 3.0, 0.0)
	queue_redraw()


func _draw() -> void:
	if not _active:
		return

	var vs := get_viewport_rect().size
	var total_w := BAR_W
	var x0 := (vs.x - total_w) * 0.5
	var y0 := MARGIN_TOP

	# ── 名字 ──
	var font := GameFont.get_font()
	var fsize := 11
	var tw := font.get_string_size(_name, HORIZONTAL_ALIGNMENT_LEFT,
								  -1, fsize).x
	var tx := (vs.x - tw) * 0.5
	for off in [Vector2(-1, 0), Vector2(1, 0), Vector2(0, -1), Vector2(0, 1)]:
		draw_string(font, Vector2(tx, y0 - 4) + off, _name,
					HORIZONTAL_ALIGNMENT_LEFT, -1, fsize,
					Color(0.04, 0.05, 0.10, 0.95))
	draw_string(font, Vector2(tx, y0 - 4), _name,
				HORIZONTAL_ALIGNMENT_LEFT, -1, fsize, C_TEXT)

	# ── 三段血条 ──
	var seg_w := (total_w - SEG_GAP * (SEGMENTS - 1)) / SEGMENTS
	for i in SEGMENTS:
		var sx := x0 + i * (seg_w + SEG_GAP)
		# 这一段覆盖的血量区间（从右往左：段 0 是最后 1/3）
		var seg_lo := 1.0 - float(i + 1) / SEGMENTS
		var seg_hi := 1.0 - float(i) / SEGMENTS

		var fill := 0.0
		if _hp_shown >= seg_hi:
			fill = 1.0
		elif _hp_shown > seg_lo:
			fill = (_hp_shown - seg_lo) / (seg_hi - seg_lo)
		fill = clampf(fill, 0.0, 1.0)

		# 底
		draw_rect(Rect2(sx, y0, seg_w, BAR_H), C_EMPTY)
		# 填充
		if fill > 0.0:
			var fw := seg_w * fill
			var col := C_FILL
			# 已过的阶段（fill 已满且不是当前段）变暗
			var seg_phase := SEGMENTS - i
			if seg_phase < _phase:
				col = Color(C_FILL.r * 0.45, C_FILL.g * 0.45, C_FILL.b * 0.45)
			draw_rect(Rect2(sx, y0, fw, BAR_H), col)
			# 顶部高光条
			if fw > 1:
				draw_rect(Rect2(sx, y0, fw, 2),
						  Color(1, 1, 1, 0.22))
		# 边框
		draw_rect(Rect2(sx, y0, seg_w, BAR_H), C_EDGE, false, 1.0)

	# ── 受伤白闪：整条叠一层 ──
	if _flash > 0.0:
		var a := 0.30 * _flash
		draw_rect(Rect2(x0, y0, total_w, BAR_H), Color(1, 1, 1, a))

	# ── 当前阶段标记：在对应段下方画一个小三角 ──
	var seg_idx := SEGMENTS - _phase
	var sx2 := x0 + seg_idx * (seg_w + SEG_GAP) + seg_w * 0.5
	var ty := y0 + BAR_H + 3
	draw_colored_polygon(PackedVector2Array([
		Vector2(sx2 - 3, ty), Vector2(sx2 + 3, ty), Vector2(sx2, ty + 4),
	]), Color(C_FILL_HOT.r, C_FILL_HOT.g, C_FILL_HOT.b, 0.9))


func get_hp_ratio() -> float:
	return _hp


func get_phase() -> int:
	return _phase
