extends Control
## 触屏虚拟按键：仅在触摸设备上显示
##
## 设计要点
## ─────────
## 1. **不改 InputMap 语义**：虚拟按键直接 press/release 已有的 action，
##    所以 player.gd 的手感代码一行都不用改，桌面/手机跑同一套逻辑。
## 2. **视口只有 480x270**，按钮必须够大才好点（拇指约需 40px 直径），
##    同时半透明，避免挡住角色和敌人。
## 3. **左摇杆区 + 右侧功能键**：左侧是方向（左右两个大按钮，不需要摇杆精度），
##    右侧三键扇形排布（跳跃/攻击/闪避），攻击键最大且最好按。
## 4. **多点触控**：必须支持同时按住「左」和「攻击」，所以每个按钮
##    独立追踪 touch index，不能用单个 index。

const ACTION_LEFT := "move_left"
const ACTION_RIGHT := "move_right"
const ACTION_JUMP := "jump"
const ACTION_ATTACK := "attack"
const ACTION_DASH := "dash"

# 按钮视觉参数
# 透明度压得比较低：按键是辅助层，不该盖住场景和敌人
const BTN_ALPHA := 0.22
const BTN_ALPHA_ACTIVE := 0.48
const BTN_EDGE := Color(0.75, 0.91, 0.78, 0.42)
const ICON_ALPHA := 0.72

# 桌面调试时是否强制显示（--touch 命令行参数）
var _force_show := false

var _buttons: Array[Dictionary] = []
var _touch_map := {}          # touch_index -> button id


func _ready() -> void:
	# 判断是否为触摸设备；桌面默认隐藏
	_force_show = "--touch" in OS.get_cmdline_user_args()
	var is_touch := DisplayServer.is_touchscreen_available()
	visible = is_touch or _force_show

	# 铺满整个视口，保证在任意分辨率下坐标都对
	set_anchors_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_IGNORE

	_build_buttons()
	if visible:
		print("触屏按键已启用（touchscreen=%s, forced=%s）" % [is_touch, _force_show])


func _build_buttons() -> void:
	# 坐标是相对 480x270 视口的比例值。
	#
	# 布局经过实际间隙计算（不是凭感觉摆的）：
	#   左下角：左右移动，拇指自然位置
	#   右侧三角：闪避(左上) / 跳跃(右下) / 攻击(右上)
	#
	# 为什么是三角：视口只有 480x270，半径 30 的按钮直径 60px 就占屏宽 1/8。
	# 若三键排成一条斜线，jump 与 attack 的中心距只有 48px，
	# 而命中半径之和要 88px，必然重叠（第一版就是这么翻车的）。
	# 三角排布把三组间距都拉到 75px 以上，同时保证不越界。
	_add("left", ACTION_LEFT, Vector2(0.0875, 0.8000), 25.0)
	_add("right", ACTION_RIGHT, Vector2(0.2333, 0.8000), 25.0)
	_add("dash", ACTION_DASH, Vector2(0.7333, 0.5481), 23.0)
	_add("jump", ACTION_JUMP, Vector2(0.8292, 0.7630), 25.0)
	_add("attack", ACTION_ATTACK, Vector2(0.9375, 0.6222), 25.0)


func _add(id: String, action: String, anchor: Vector2, radius: float) -> void:
	_buttons.append({
		"id": id,
		"action": action,
		"anchor": anchor,     # 相对视口的比例坐标
		"r": radius,          # 半径（视口像素）
		"pressed": false,
	})


func _viewport_size() -> Vector2:
	# 用项目的基准视口尺寸做坐标基准，这样在任意窗口尺寸下比例一致
	return get_viewport_rect().size


func _button_center(b: Dictionary) -> Vector2:
	var vs := _viewport_size()
	var a: Vector2 = b["anchor"]
	return Vector2(vs.x * a.x, vs.y * a.y)


func _hit_test(pos: Vector2) -> Dictionary:
	# 从后往前测，后加的（攻击键）优先
	for i in range(_buttons.size() - 1, -1, -1):
		var b: Dictionary = _buttons[i]
		var c := _button_center(b)
		var r: float = b["r"] * (_viewport_size().y / 270.0)
		# 命中区比视觉半径大 15%，拇指点偏一点也能触发
		if pos.distance_to(c) <= r * 1.15:
			return b
	return {}


# ───────────────────────── 触摸事件 ─────────────────────────

func _input(event: InputEvent) -> void:
	if not visible:
		return

	if event is InputEventScreenTouch:
		var e := event as InputEventScreenTouch
		var b := _hit_test(e.position)
		if e.pressed:
			if b.is_empty():
				return
			_set_pressed(b, true)
			_touch_map[e.index] = b["id"]
		else:
			# 释放：找到这个 touch 绑定的按钮
			var id = _touch_map.get(e.index, "")
			if id == "":
				return
			for btn in _buttons:
				if btn["id"] == id:
					_set_pressed(btn, false)
					break
			_touch_map.erase(e.index)
		get_viewport().set_input_as_handled()

	elif event is InputEventScreenDrag:
		# 拖动：滑出按钮范围就松开，滑入就按下（手指滚动式操作更跟手）
		var d := event as InputEventScreenDrag
		var id = _touch_map.get(d.index, "")
		var b := _hit_test(d.position)
		var hit_id: String = b["id"] if not b.is_empty() else ""

		if id != "" and id != hit_id:
			for btn in _buttons:
				if btn["id"] == id:
					_set_pressed(btn, false)
					break
			_touch_map.erase(d.index)

		if hit_id != "" and not _touch_map.has(d.index):
			_set_pressed(b, true)
			_touch_map[d.index] = hit_id


func _set_pressed(b: Dictionary, on: bool) -> void:
	if b["pressed"] == on:
		return
	b["pressed"] = on
	var action: String = b["action"]
	if on:
		Input.action_press(action)
	else:
		Input.action_release(action)
	queue_redraw()


# ───────────────────────── 绘制 ─────────────────────────

func _draw() -> void:
	if not visible:
		return

	var scale_k := _viewport_size().y / 270.0
	for b in _buttons:
		var c := _button_center(b)
		var r: float = b["r"] * scale_k
		var pressed: bool = b["pressed"]

		# 底色圆
		var col := Color(0.07, 0.08, 0.16, BTN_ALPHA_ACTIVE if pressed else BTN_ALPHA)
		draw_circle(c, r, col)

		# 描边
		draw_arc(c, r, 0.0, TAU, 24, BTN_EDGE, 1.5 * scale_k)

		# 图标
		var icon_col := Color(0.75, 0.91, 0.78, ICON_ALPHA)
		match b["id"]:
			"left":
				_draw_arrow(c, r, -1.0, icon_col, scale_k)
			"right":
				_draw_arrow(c, r, 1.0, icon_col, scale_k)
			"jump":
				# 上箭头
				var s := r * 0.42
				draw_line(c + Vector2(0, s), c + Vector2(0, -s),
						  icon_col, 2.0 * scale_k)
				draw_line(c + Vector2(0, -s), c + Vector2(-s * 0.7, -s * 0.1),
						  icon_col, 2.0 * scale_k)
				draw_line(c + Vector2(0, -s), c + Vector2(s * 0.7, -s * 0.1),
						  icon_col, 2.0 * scale_k)
			"attack":
				# 剑形：一条斜线 + 短护手
				var s2 := r * 0.5
				draw_line(c + Vector2(-s2, s2), c + Vector2(s2, -s2),
						  icon_col, 2.5 * scale_k)
				draw_line(c + Vector2(-s2 * 0.5, s2 * 0.5),
						  c + Vector2(s2 * 0.2, s2 * 0.9),
						  icon_col, 2.0 * scale_k)
			"dash":
				# 双横线表示冲刺
				for i in 2:
					var yy := r * (-0.15 + 0.3 * i)
					draw_line(c + Vector2(-r * 0.4, yy), c + Vector2(r * 0.4, yy),
							  icon_col, 2.0 * scale_k)


func _draw_arrow(c: Vector2, r: float, dir: float, col: Color, k: float) -> void:
	var s := r * 0.38
	draw_line(c + Vector2(-s * dir, 0), c + Vector2(s * dir, 0), col, 2.5 * k)
	draw_line(c + Vector2(s * dir, 0), c + Vector2(s * dir * 0.25, -s * 0.75),
			  col, 2.5 * k)
	draw_line(c + Vector2(s * dir, 0), c + Vector2(s * dir * 0.25, s * 0.75),
			  col, 2.5 * k)


# 窗口尺寸变化时重算布局
func _notification(what: int) -> void:
	if what == NOTIFICATION_RESIZED or what == NOTIFICATION_WM_SIZE_CHANGED:
		queue_redraw()
