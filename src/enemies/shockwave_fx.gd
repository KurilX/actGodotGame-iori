extends Node2D
## 冲击波：从一点向外的扩散环，用于砸地、阶段转换、瞬移。
##
## 像素风格的做法：**用整数半径 + 硬边圆**，不做平滑渐变。
## 平滑渐变的环形在低分辨率下会糊成一片灰雾。
## 这里用 2~3 圈不同透明度的硬边圆叠加，模拟"能量环"。

const C_CORE := Color("#FFE9A8")
const C_MID := Color("#FFC46B")
const C_OUT := Color("#FF7A9C")

var _active := false
var _t := 0.0
var _dur := 0.4
var _max_r := 60.0
var _center := Vector2.ZERO


func _ready() -> void:
	visible = false
	set_process(false)
	z_index = 30


func play_burst(world_pos: Vector2, max_radius: float, duration: float) -> void:
	# 位置是相对 BOSS 的：换算成局部坐标
	var parent := get_parent()
	if parent is Node2D:
		_center = world_pos - parent.global_position
	else:
		_center = world_pos
	_max_r = max_radius
	_dur = maxf(0.08, duration)
	_t = 0.0
	_active = true
	visible = true
	set_process(true)
	queue_redraw()


func _process(delta: float) -> void:
	if not _active:
		return
	_t += delta
	if _t >= _dur:
		_active = false
		visible = false
		set_process(false)
		queue_redraw()
		return
	queue_redraw()


func _draw() -> void:
	if not _active:
		return

	var k := clampf(_t / _dur, 0.0, 1.0)
	# 半径用整数，避免半像素毛边
	var r := int(round(_max_r * k))
	var alpha := 1.0 - k

	# 三圈同心环：外粉、中金、内白
	if r > 2:
		draw_arc(_center, float(r), 0.0, TAU, 40,
				 Color(C_OUT.r, C_OUT.g, C_OUT.b, 0.55 * alpha), 2.0)
	if r > 6:
		draw_arc(_center, float(r) * 0.78, 0.0, TAU, 36,
				 Color(C_MID.r, C_MID.g, C_MID.b, 0.70 * alpha), 2.0)
	if r > 10:
		draw_arc(_center, float(r) * 0.52, 0.0, TAU, 32,
				 Color(C_CORE.r, C_CORE.g, C_CORE.b, 0.9 * alpha), 1.5)

	# 中心闪白（只在最开始的 25% 内）
	if k < 0.25:
		var ia := (1.0 - k / 0.25)
		draw_circle(_center, 8.0, Color(1, 1, 1, 0.5 * ia))


func is_active() -> bool:
	return _active
