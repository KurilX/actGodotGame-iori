extends Control
## 子弹时间特效：完美闪避触发时的全屏视觉反馈。
##
## ## 为什么需要这个
##
## 完美闪避原本只 emit 一个 `perfect_dodge` 信号，**没有任何代码连接它** ——
## 也就是说玩家做出完美闪避后，屏幕上什么也不会发生。
## 时间流速变了，但没有视觉线索，玩家根本不知道自己成功了。
## 动作游戏里「奖励要有明确反馈」是硬要求，否则玩家不会去练。
##
## ## 三层表现
##
##   1. **画面染色**：全屏叠一层冷蓝，暗示"时间被冻结"
##   2. **放射线**：从角色位置向外放射的白色细线，速度感
##   3. **边缘暗角**：四周压暗，把注意力收拢到中心
##
## 另外会临时降低 Engine.time_scale（子弹时间本体），并在结束时恢复。
## 注意 time_scale 会影响**所有** _process/_physics_process 的 delta，
## 包括这个特效自己 —— 所以计时必须用**真实时间**（Time.get_ticks_msec）。

signal finished

const DURATION_MS := 600        # 真实时长（毫秒），不受 time_scale 影响
const TIME_SCALE := 0.35        # 子弹时间倍率
const RAY_COUNT := 24

const C_TINT := Color(0.35, 0.72, 0.95, 0.16)
const C_RAY := Color(0.76, 0.95, 1.0, 0.55)

var _active := false
var _start_ms := 0
var _origin := Vector2.ZERO      # 角色屏幕位置（放射线中心）
var _prev_scale := 1.0


func _ready() -> void:
	set_anchors_preset(Control.PRESET_FULL_RECT)
	# 只设锚点不够：offset 会保留原值，Control 尺寸可能变成 (0,0)，
	# 导致 draw_* 被裁剪。必须显式清零。
	offset_left = 0
	offset_top = 0
	offset_right = 0
	offset_bottom = 0
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	visible = false
	set_process(false)


func trigger(world_pos: Vector2, camera: Camera2D = null) -> void:
	"""触发子弹时间。world_pos 用来定位放射线中心。"""
	if _active:
		# 已经在播放就重新计时，避免叠多层
		_start_ms = Time.get_ticks_msec()
		return

	_active = true
	_start_ms = Time.get_ticks_msec()
	visible = true
	set_process(true)

	# 换算到屏幕坐标：用相机的屏幕中心 + 世界坐标差
	if camera != null:
		var screen_c := camera.get_screen_center_position()
		var vs := get_viewport_rect().size
		_origin = world_pos - screen_c + vs * 0.5
	else:
		_origin = get_viewport_rect().size * 0.5

	# 子弹时间
	_prev_scale = Engine.time_scale
	Engine.time_scale = TIME_SCALE
	queue_redraw()


func _process(_delta: float) -> void:
	if not _active:
		return

	# 必须用真实时间判断进度：_delta 已被 time_scale 缩放，
	# 用它来计时会让 0.6 秒的子弹时间变成 1.7 秒。
	var elapsed := Time.get_ticks_msec() - _start_ms
	var t := clampf(float(elapsed) / float(DURATION_MS), 0.0, 1.0)

	# 放射线随时间向外扩散
	_ray_progress = t
	queue_redraw()

	if t >= 1.0:
		_stop()


func _stop() -> void:
	_active = false
	visible = false
	set_process(false)
	Engine.time_scale = _prev_scale
	finished.emit()
	queue_redraw()


var _ray_progress := 0.0


func _draw() -> void:
	if not _active:
		return

	var vs := get_viewport_rect().size
	var t := _ray_progress

	# ── 1. 全屏冷色染色（前段强、后段淡出）──
	var tint_a := C_TINT.a * (1.0 - t * t)
	draw_rect(Rect2(Vector2.ZERO, vs), Color(C_TINT.r, C_TINT.g, C_TINT.b, tint_a))

	# ── 2. 放射线 ──
	# 从中心向外放射的细线，长度随进度增长、透明度衰减
	var ray_len_base := maxf(vs.x, vs.y) * 0.55
	var ray_a := C_RAY.a * (1.0 - t) ** 1.5
	if ray_a > 0.01:
		for i in RAY_COUNT:
			var ang := TAU * float(i) / float(RAY_COUNT)
			# 加一点不规则，避免像车轮辐条
			ang += sin(float(i) * 2.7) * 0.06
			var dir := Vector2(cos(ang), sin(ang))
			# 起始半径随时间外推，留出中心区域
			var r0 := 26.0 + t * 120.0
			var r1 := r0 + ray_len_base * (0.25 + t * 0.55)
			var p0 := _origin + dir * r0
			var p1 := _origin + dir * r1
			draw_line(p0, p1, Color(C_RAY.r, C_RAY.g, C_RAY.b, ray_a), 1.5)

	# ── 3. 边缘暗角 ──
	# 用四条渐变边模拟（像素风格不做平滑 radial gradient，
	# 用若干层不同透明度的矩形叠出层次）
	var vig_a := 0.42 * (1.0 - t)
	if vig_a > 0.01:
		var band := 8
		for i in band:
			var k := float(i) / float(band)
			var a := vig_a * k * 0.5
			var w := vs.x * 0.06 * (1.0 - k)
			var col := Color(0.03, 0.04, 0.09, a)
			# 左右
			draw_rect(Rect2(0, 0, w * 2, vs.y), col)
			draw_rect(Rect2(vs.x - w * 2, 0, w * 2, vs.y), col)
			# 上下
			draw_rect(Rect2(0, 0, vs.x, w * 1.4), col)
			draw_rect(Rect2(0, vs.y - w * 1.4, vs.x, w * 1.4), col)
