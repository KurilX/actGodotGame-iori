extends Node2D
## 前摇预警：在技能命中区域画出即将到来的攻击范围。
##
## ## 为什么必须做
##
## BOSS 的大招如果只有"前摇时间"而没有"范围指示"，玩家只能靠背板记忆，
## 那是很差的动作游戏设计。预警把"看不见的判定框"变成"看得见的几何形状"，
## 玩家才能做出反应。
##
## ## 三种形状
##
##   show_line   冲锋 —— 一条横向长条，标出冲锋路径
##   show_circle 砸地 —— 一个圆，标出冲击范围
##   show_fan    弹幕 —— 若干扇形射线，标出弹幕覆盖角度
##
## ## 动效
##
## 预警本身会**闪烁并逐渐变亮**，前摇结束时最亮，形成"倒计时"的暗示。

const C_WARN := Color("#FF7A9C")
const C_WARN_HOT := Color("#FFE9A8")

var _active := false
var _kind := "line"
var _t := 0.0
var _dur := 0.5
var _len := 100.0
var _radius := 60.0
var _fan_deg := 30.0
var _fan_count := 5
var _dir := 1


func _ready() -> void:
	visible = false
	set_process(false)
	z_index = 25


func show_line(pos_world: Vector2, facing: int, length: float, dur: float) -> void:
	_kind = "line"
	_len = length
	_dir = facing
	_begin(pos_world, dur)


func show_circle(pos_world: Vector2, radius: float, dur: float) -> void:
	_kind = "circle"
	_radius = radius
	_begin(pos_world, dur)


func show_fan(pos_world: Vector2, facing: int, fan_deg: float,
			  count: int, dur: float) -> void:
	_kind = "fan"
	_fan_deg = fan_deg
	_fan_count = count
	_dir = facing
	_begin(pos_world, dur)


func _begin(pos_world: Vector2, dur: float) -> void:
	var parent := get_parent()
	position = Vector2.ZERO
	if parent is Node2D:
		position = pos_world - parent.global_position
	_t = 0.0
	_dur = maxf(0.1, dur)
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


func stop() -> void:
	_active = false
	visible = false
	set_process(false)


func _draw() -> void:
	if not _active:
		return

	var k := clampf(_t / _dur, 0.0, 1.0)
	# 前摇开始时半透明，越接近结束越亮 —— 这就是"倒计时"
	var a := 0.20 + 0.55 * k
	# 闪烁：快速脉动，越接近结束越快
	var blink_hz := 6.0 + 10.0 * k
	var blink := 0.72 + 0.28 * sin(_t * TAU * blink_hz)
	a *= blink
	var col := C_WARN if k < 0.75 else C_WARN_HOT

	match _kind:
		"line":
			_draw_line(col, a, k)
		"circle":
			_draw_circle(col, a, k)
		"fan":
			_draw_fan(col, a, k)


func _draw_line(col: Color, a: float, k: float) -> void:
	# 冲锋路径：贴地的横向长条，随时间"填充"
	var y := -6.0
	var h := 22.0
	var w := _len * k
	var x0 := 0.0 if _dir > 0 else -w
	# 半透明填充
	draw_rect(Rect2(x0, y, w, h), Color(col.r, col.g, col.b, a * 0.28))
	# 边框
	draw_rect(Rect2(x0, y, w, h), Color(col.r, col.g, col.b, a), false, 1.5)
	# 中轴线（指向）
	var ly := y + h * 0.5
	draw_line(Vector2(x0, ly), Vector2(x0 + w, ly),
			  Color(col.r, col.g, col.b, a * 0.6), 1.0)


func _draw_circle(col: Color, a: float, k: float) -> void:
	# 砸地范围：同心圆，填充随进度扩大
	var r := _radius * k
	draw_circle(Vector2.ZERO, r, Color(col.r, col.g, col.b, a * 0.20))
	draw_arc(Vector2.ZERO, r, 0.0, TAU, 48,
			 Color(col.r, col.g, col.b, a), 2.0)
	# 内圈刻度，暗示"即将命中"
	draw_arc(Vector2.ZERO, _radius, 0.0, TAU, 48,
			 Color(col.r, col.g, col.b, a * 0.45), 1.0)


func _draw_fan(col: Color, a: float, k: float) -> void:
	# 弹幕扇形：画出每条弹道
	var spread := deg_to_rad(_fan_deg)
	var base := deg_to_rad(0.0 if _dir > 0 else 180.0)
	var length := 120.0 * k
	for i in _fan_count:
		var t := 0.0 if _fan_count <= 1 else (
			float(i) / float(_fan_count - 1)) - 0.5
		var ang := base + t * spread
		var dir := Vector2(cos(ang), sin(ang))
		var p0 := Vector2(0, -4)
		var p1 := p0 + dir * length
		draw_line(p0, p1, Color(col.r, col.g, col.b, a * 0.55), 1.0)
		# 末端一个点，表示弹幕将达到的位置
		draw_circle(p1, 2.0, Color(col.r, col.g, col.b, a))
