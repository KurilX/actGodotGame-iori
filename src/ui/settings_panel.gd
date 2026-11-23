extends Control

const GameFont := preload("res://src/ui/game_font.gd")
## 设置面板：音量、画面、存档管理、返回菜单。
##
## ## 为什么设置里也要有存档操作
##
## 玩家想"重新开始"时最自然的动作是来设置里找，
## 而不是回主菜单（那里可能已经被继续游戏占满）。
## 所以设置里也放一份"清除存档/导出"。

signal closed
signal volume_changed(value: float)
signal export_save
signal clear_save
signal back_to_menu

const C_BG := Color(0.03, 0.04, 0.09, 0.97)
const C_TEXT := Color("#E8F0F2")
const C_DIM := Color(0.45, 0.50, 0.62)
const C_ACCENT := Color("#FFC46B")
const C_EDGE := Color("#B9F2FF")

const PANEL_W := 260.0
const ROW_H := 26.0
const ROW_GAP := 8.0

var _volume := 0.8
var _rows: Array[Dictionary] = []
var _selected := 0
var _hover := -1
var _t := 0.0
var _msg := ""
var _msg_timer := 0.0


func _ready() -> void:
	set_anchors_preset(Control.PRESET_FULL_RECT)
	offset_left = 0
	offset_top = 0
	offset_right = 0
	offset_bottom = 0
	mouse_filter = Control.MOUSE_FILTER_PASS
	visible = false
	set_process(false)
	_build_rows()


func _build_rows() -> void:
	_rows = [
		{"key": "volume", "label": "音量", "kind": "slider"},
		{"key": "export", "label": "导出存档", "kind": "button"},
		{"key": "clear", "label": "清除存档", "kind": "button"},
		{"key": "menu", "label": "返回主菜单", "kind": "button"},
		{"key": "close", "label": "关闭", "kind": "button"},
	]


func open() -> void:
	visible = true
	set_process(true)
	_t = 0.0
	_selected = 0
	_msg = ""
	queue_redraw()


func close() -> void:
	visible = false
	set_process(false)
	closed.emit()


func set_message(text: String) -> void:
	_msg = text
	_msg_timer = 2.2


func get_volume() -> float:
	return _volume


func _process(delta: float) -> void:
	_t += delta
	if _msg_timer > 0.0:
		_msg_timer = maxf(_msg_timer - delta, 0.0)
		if _msg_timer <= 0.0:
			_msg = ""
	queue_redraw()


func _unhandled_input(event: InputEvent) -> void:
	if not visible:
		return

	if event is InputEventKey and event.pressed and not event.echo:
		match event.keycode:
			KEY_UP, KEY_W:
				_selected = (_selected - 1 + _rows.size()) % _rows.size()
				queue_redraw()
				get_viewport().set_input_as_handled()
			KEY_DOWN, KEY_S:
				_selected = (_selected + 1) % _rows.size()
				queue_redraw()
				get_viewport().set_input_as_handled()
			KEY_LEFT, KEY_A:
				if _rows[_selected]["kind"] == "slider":
					_volume = clampf(_volume - 0.1, 0.0, 1.0)
					volume_changed.emit(_volume)
					queue_redraw()
				get_viewport().set_input_as_handled()
			KEY_RIGHT, KEY_D:
				if _rows[_selected]["kind"] == "slider":
					_volume = clampf(_volume + 0.1, 0.0, 1.0)
					volume_changed.emit(_volume)
					queue_redraw()
				get_viewport().set_input_as_handled()
			KEY_ENTER, KEY_KP_ENTER, KEY_SPACE:
				_activate(_selected)
				get_viewport().set_input_as_handled()
			KEY_ESCAPE:
				close()
				get_viewport().set_input_as_handled()

	elif event is InputEventMouseMotion:
		_hover = _hit(event.position)
		queue_redraw()

	elif event is InputEventMouseButton and event.pressed \
			and event.button_index == MOUSE_BUTTON_LEFT:
		var idx := _hit(event.position)
		if idx >= 0:
			_selected = idx
			if _rows[idx]["kind"] == "slider":
				# 点滑块直接按位置设值
				var r := _row_rect(idx, get_viewport_rect().size)
				var track_x0 := r.position.x + 92.0
				var track_w := r.size.x - 100.0
				_volume = clampf((event.position.x - track_x0) / track_w, 0.0, 1.0)
				volume_changed.emit(_volume)
				queue_redraw()
			else:
				_activate(idx)
			get_viewport().set_input_as_handled()

	elif event is InputEventScreenTouch and event.pressed:
		var idx2 := _hit(event.position)
		if idx2 >= 0:
			_selected = idx2
			_activate(idx2)
			get_viewport().set_input_as_handled()


func _activate(idx: int) -> void:
	if idx < 0 or idx >= _rows.size():
		return
	match _rows[idx]["key"]:
		"export":
			export_save.emit()
			set_message("已导出")
		"clear":
			clear_save.emit()
			set_message("存档已清除")
		"menu":
			back_to_menu.emit()
			close()
		"close":
			close()


# ─────────────── 布局 ───────────────

func _row_rect(i: int, vs: Vector2) -> Rect2:
	var h := ROW_H
	var total := _rows.size() * (h + ROW_GAP) - ROW_GAP
	var x := (vs.x - PANEL_W) * 0.5
	var y0 := (vs.y - total) * 0.5
	return Rect2(x, y0 + i * (h + ROW_GAP), PANEL_W, h)


func _hit(pos: Vector2) -> int:
	var vs := get_viewport_rect().size
	for i in _rows.size():
		if _row_rect(i, vs).has_point(pos):
			return i
	return -1


# ─────────────── 绘制 ───────────────

func _draw() -> void:
	if not visible:
		return
	var vs := get_viewport_rect().size
	var font := GameFont.get_font()

	draw_rect(Rect2(Vector2.ZERO, vs), C_BG)
	# 网格底纹
	var gs := 24.0
	var grid := Color(0.10, 0.13, 0.22, 0.40)
	for x in range(0, int(vs.x), int(gs)):
		draw_line(Vector2(x, 0), Vector2(x, vs.y), grid, 1.0)
	for y in range(0, int(vs.y), int(gs)):
		draw_line(Vector2(0, y), Vector2(vs.x, y), grid, 1.0)

	# 标题
	var title := "设置"
	var tw := font.get_string_size(title, HORIZONTAL_ALIGNMENT_LEFT, -1, 18).x
	var ty := _row_rect(0, vs).position.y - 26
	draw_string(font, Vector2((vs.x - tw) * 0.5, ty), title,
				HORIZONTAL_ALIGNMENT_LEFT, -1, 18, C_TEXT)

	for i in _rows.size():
		_draw_row(font, i, vs)

	# 提示消息
	if _msg != "":
		var mw := font.get_string_size(_msg, HORIZONTAL_ALIGNMENT_LEFT, -1, 10).x
		draw_string(font, Vector2((vs.x - mw) * 0.5, vs.y - 30), _msg,
					HORIZONTAL_ALIGNMENT_LEFT, -1, 10, C_ACCENT)

	# 底部提示
	var hint := "↑↓ 选择   ←→ 调音量   Esc 返回"
	var hw := font.get_string_size(hint, HORIZONTAL_ALIGNMENT_LEFT, -1, 9).x
	draw_string(font, Vector2((vs.x - hw) * 0.5, vs.y - 14), hint,
				HORIZONTAL_ALIGNMENT_LEFT, -1, 9,
				Color(C_DIM.r, C_DIM.g, C_DIM.b, 0.75))


func _draw_row(font: Font, i: int, vs: Vector2) -> void:
	var r := _row_rect(i, vs)
	var row: Dictionary = _rows[i]
	var sel := (i == _selected) or (i == _hover)

	var bg := Color(0.10, 0.13, 0.22, 0.9) if sel else Color(0.07, 0.09, 0.15, 0.9)
	var edge := C_EDGE if sel else Color(0.24, 0.28, 0.38)
	draw_rect(r, bg)
	draw_rect(r, edge, false, 1.5)

	var label: String = row["label"]
	draw_string(font, Vector2(r.position.x + 12, r.position.y + 17), label,
				HORIZONTAL_ALIGNMENT_LEFT, -1, 11,
				C_TEXT if sel else Color(0.72, 0.78, 0.88))

	if row["kind"] == "slider":
		# 滑块：轨道 + 填充 + 手柄
		var x0 := r.position.x + 92.0
		var w := r.size.x - 100.0
		var cy := r.position.y + r.size.y * 0.5
		draw_rect(Rect2(x0, cy - 2, w, 4), Color(0.16, 0.19, 0.28))
		draw_rect(Rect2(x0, cy - 2, w * _volume, 4), C_EDGE)
		var hx := x0 + w * _volume
		draw_rect(Rect2(hx - 3, cy - 6, 6, 12), C_ACCENT)
		# 百分比
		var pct := "%d%%" % int(round(_volume * 100))
		var pw := font.get_string_size(pct, HORIZONTAL_ALIGNMENT_LEFT, -1, 9).x
		draw_string(font, Vector2(r.position.x + r.size.x - pw - 8, cy + 4),
					pct, HORIZONTAL_ALIGNMENT_LEFT, -1, 9,
					Color(C_DIM.r, C_DIM.g, C_DIM.b))
