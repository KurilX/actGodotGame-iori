extends Control

const GameFont := preload("res://src/ui/game_font.gd")
## 主菜单：开始游戏 / 继续游戏 / 设置，外加存档槽导出。
##
## ## 布局
##
##   ┌─────────────────────────────┐
##   │          《缀》              │
##   │        （标题 + 副标题）       │
##   │                             │
##   │   ▸ 开始游戏                 │
##   │   ▸ 继续游戏   <存档摘要>     │
##   │   ▸ 设置                    │
##   │                             │
##   │   存档槽：[导出] [清除]        │
##   └─────────────────────────────┘
##
## ## 键盘与鼠标/touch 双支持
##
## Web 端触屏用户没有键盘，所以按钮必须可点。
## 同时支持上下键 + Enter，方便桌面。

signal start_new_game
signal continue_game
signal open_settings
signal copy_code          # 复制存档码到剪贴板
signal import_code(text: String)   # 从输入框的存档码导入
signal clear_save

const C_BG := Color(0.03, 0.04, 0.09, 1.0)
const C_TITLE := Color("#A8E8C6")
const C_SUB := Color("#5FA882")
const C_TEXT := Color("#E8F0F2")
const C_DIM := Color(0.45, 0.50, 0.62)
const C_ACCENT := Color("#FFC46B")
const C_EDGE := Color("#B9F2FF")

const BTN_W := 220.0
const BTN_H := 34.0
const BTN_GAP := 10.0

var _save: Node = null
var _selected := 0
var _items: Array[Dictionary] = []
var _t := 0.0
var _hover: int = -1
var _flash := {}          # 按钮 key -> 剩余闪烁


func _ready() -> void:
	set_anchors_preset(Control.PRESET_FULL_RECT)
	offset_left = 0
	offset_top = 0
	offset_right = 0
	offset_bottom = 0
	mouse_filter = Control.MOUSE_FILTER_PASS
	set_process(true)
	_build_import_box()
	_rebuild()


# ─────────────── 导入输入框 ───────────────
#
# 用 LineEdit 而不是自绘：存档码要能选中、粘贴、Ctrl+V，
# 自绘输入框要自己实现光标/选区/剪贴板，不值得。

var _import_box: LineEdit
var _import_open := false
var _import_msg := ""
var _import_msg_t := 0.0
var _import_ok := false


func _build_import_box() -> void:
	_import_box = LineEdit.new()
	_import_box.name = "ImportBox"
	_import_box.placeholder_text = "粘贴存档码（AG1.xxxxx）"
	_import_box.visible = false
	_import_box.max_length = 4096
	_import_box.text_submitted.connect(func(_t: String) -> void:
		_submit_import())
	add_child(_import_box)


func _toggle_import_box() -> void:
	_import_open = not _import_open
	_import_box.visible = _import_open
	if _import_open:
		# **必须在这里定位**，不能只在 _draw 里设。
		# _draw 的调用时机不可靠（控件第一次显示时可能还没画），
		# 结果输入框停在 (0,0) 跑到屏幕左上角（实测如此）。
		_layout_import_box()
		_import_box.grab_focus()
		_import_box.text = ""
		_import_msg = ""
	else:
		_import_box.release_focus()
	queue_redraw()


func _layout_import_box() -> void:
	if _import_box == null:
		return
	var vs := get_viewport_rect().size
	var rs := _secondary_rects(vs)
	var bw: float = rs["copy"].size.x * 3.0 + 16.0
	var bx := (vs.x - bw) * 0.5
	# 放在**标题和按钮组之间**的空档里。
	# 曾经试过"存档槽上方"，但那里正好是「设置」按钮的位置，
	# 会把它压住（实测）。标题在 y≈0.17H、按钮组从 y≈0.36H 开始，
	# 中间那段是空的。
	# 按钮组下移了 26px，所以这里放在原按钮组顶部再往上一点
	var total_h: float = 3.0 * (34.0 + 10.0) - 10.0
	var by: float = vs.y * 0.50 - total_h * 0.5 - 16.0
	_import_box.position = Vector2(bx, by)
	_import_box.size = Vector2(bw, 24.0)


func _submit_import() -> void:
	var txt := _import_box.text.strip_edges()
	if txt.is_empty():
		_set_import_msg("存档码为空", false)
		return
	import_code.emit(txt)


func set_import_result(ok: bool, msg: String) -> void:
	_set_import_msg(msg, ok)
	if ok:
		_toggle_import_box()


func _set_import_msg(msg: String, ok: bool) -> void:
	_import_msg = msg
	_import_ok = ok
	_import_msg_t = 3.0
	queue_redraw()


func _input(event: InputEvent) -> void:
	# Esc 关掉导入框（免得焦点困在里面）
	if _import_open and event is InputEventKey and event.pressed \
			and event.keycode == KEY_ESCAPE:
		_toggle_import_box()
		get_viewport().set_input_as_handled()


func bind_save(save: Node) -> void:
	_save = save
	_rebuild()


func _rebuild() -> void:
	_items = [
		{"key": "new", "label": "开始游戏", "sub": ""},
		{"key": "continue", "label": "继续游戏", "sub": ""},
		{"key": "settings", "label": "设置", "sub": ""},
	]
	# 继续游戏的副标题显示存档摘要；无存档则置灰
	if _save != null and _save.has_save():
		_items[1]["sub"] = _save.summary()
		_items[1]["enabled"] = true
	else:
		_items[1]["sub"] = "（无存档）"
		_items[1]["enabled"] = false
	# 保证选中项不是禁用的
	if _selected == 1 and not _items[1].get("enabled", true):
		_selected = 0
	queue_redraw()


func refresh() -> void:
	_rebuild()


func _notification(what: int) -> void:
	# 窗口尺寸变了要重排输入框，否则它会停在旧位置
	if what == NOTIFICATION_RESIZED and _import_open:
		_layout_import_box()


# ─────────────── 输入 ───────────────

func _process(delta: float) -> void:
	_t += delta
	for k in _flash.keys():
		_flash[k] -= delta
		if _flash[k] <= 0.0:
			_flash.erase(k)
	if _import_msg_t > 0.0:
		_import_msg_t = maxf(_import_msg_t - delta, 0.0)
		if _import_msg_t <= 0.0:
			_import_msg = ""
	queue_redraw()


func _unhandled_input(event: InputEvent) -> void:
	if not visible:
		return

	if event is InputEventKey and event.pressed and not event.echo:
		match event.keycode:
			KEY_UP, KEY_W:
				_move(-1)
				get_viewport().set_input_as_handled()
			KEY_DOWN, KEY_S:
				_move(1)
				get_viewport().set_input_as_handled()
			KEY_ENTER, KEY_KP_ENTER, KEY_SPACE:
				_activate(_selected)
				get_viewport().set_input_as_handled()
			KEY_E:
				copy_code.emit()
				get_viewport().set_input_as_handled()
			KEY_I:
				_toggle_import_box()
				get_viewport().set_input_as_handled()

	elif event is InputEventMouseMotion:
		_hover = _hit_button(event.position)
		queue_redraw()

	elif event is InputEventMouseButton and event.pressed:
		if event.button_index == MOUSE_BUTTON_LEFT:
			var idx := _hit_button(event.position)
			if idx >= 0:
				_activate(idx)
				get_viewport().set_input_as_handled()
			# 导出/清除按钮
			var hb := _hit_secondary(event.position)
			if hb == "copy":
				copy_code.emit()
				get_viewport().set_input_as_handled()
			elif hb == "import":
				_toggle_import_box()
				get_viewport().set_input_as_handled()
			elif hb == "clear":
				clear_save.emit()
				get_viewport().set_input_as_handled()

	# 触屏：移动端的 tap 会转成 mouse 事件，上面已经覆盖；
	# 但某些浏览器只发 touch，这里兜底
	elif event is InputEventScreenTouch and event.pressed:
		var idx2 := _hit_button(event.position)
		if idx2 >= 0:
			_activate(idx2)
			get_viewport().set_input_as_handled()


func _move(dir: int) -> void:
	var n := _items.size()
	for i in n:
		_selected = (_selected + dir + n) % n
		if _items[_selected].get("enabled", true):
			break


func _activate(idx: int) -> void:
	if idx < 0 or idx >= _items.size():
		return
	if not _items[idx].get("enabled", true):
		return
	_flash[_items[idx]["key"]] = 0.35
	match _items[idx]["key"]:
		"new":
			start_new_game.emit()
		"continue":
			continue_game.emit()
		"settings":
			open_settings.emit()


# ─────────────── 布局与命中 ───────────────

func _btn_rect(i: int, vs: Vector2) -> Rect2:
	var total := _items.size() * (BTN_H + BTN_GAP) - BTN_GAP
	# 导入框打开时整体下移，给它腾出空间 —— 菜单本身很紧凑，
	# 没有天然的空档可以放输入框（试过几个位置都会压住按钮）。
	var shift: float = 26.0 if _import_open else 0.0
	var y0 := vs.y * 0.50 - total * 0.5 + shift
	var x := (vs.x - BTN_W) * 0.5
	return Rect2(x, y0 + i * (BTN_H + BTN_GAP), BTN_W, BTN_H)


func _hit_button(pos: Vector2) -> int:
	var vs := get_viewport_rect().size
	for i in _items.size():
		if _btn_rect(i, vs).has_point(pos):
			return i
	return -1


func _secondary_rects(vs: Vector2) -> Dictionary:
	var w := 62.0
	var h := 20.0
	var gap := 8.0
	var total := w * 3 + gap * 2
	var x0 := (vs.x - total) * 0.5
	var y := vs.y - 54.0
	return {
		"copy": Rect2(x0, y, w, h),
		"import": Rect2(x0 + w + gap, y, w, h),
		"clear": Rect2(x0 + (w + gap) * 2, y, w, h),
	}


func _hit_secondary(pos: Vector2) -> String:
	var rs := _secondary_rects(get_viewport_rect().size)
	for k in rs:
		if rs[k].has_point(pos):
			return k
	return ""


# ─────────────── 绘制 ───────────────

func _draw() -> void:
	var vs := get_viewport_rect().size

	# 背景
	draw_rect(Rect2(Vector2.ZERO, vs), C_BG)

	# 背景网格（和技能树同一套视觉语言）
	var gs := 24.0
	var grid := Color(0.10, 0.13, 0.22, 0.45)
	for x in range(0, int(vs.x), int(gs)):
		draw_line(Vector2(x, 0), Vector2(x, vs.y), grid, 1.0)
	for y in range(0, int(vs.y), int(gs)):
		draw_line(Vector2(0, y), Vector2(vs.x, y), grid, 1.0)

	var font := GameFont.get_font()

	# ── 标题 ──
	var title := "缀"
	var tsz := 42
	var tw := font.get_string_size(title, HORIZONTAL_ALIGNMENT_LEFT, -1, tsz).x
	var tx := (vs.x - tw) * 0.5
	var ty := vs.y * (0.12 if _import_open else 0.17)
	# 标题光晕：几圈同色描边
	for off in [Vector2(-2, 0), Vector2(2, 0), Vector2(0, -2), Vector2(0, 2),
				Vector2(-2, -2), Vector2(2, 2), Vector2(-2, 2), Vector2(2, -2)]:
		draw_string(font, Vector2(tx, ty) + off, title,
					HORIZONTAL_ALIGNMENT_LEFT, -1, tsz,
					Color(C_SUB.r, C_SUB.g, C_SUB.b, 0.45))
	draw_string(font, Vector2(tx, ty), title,
				HORIZONTAL_ALIGNMENT_LEFT, -1, tsz, C_TITLE)

	# 副标题。导入框打开时不画 —— 垂直空间不够，它会和输入框重叠。
	if not _import_open:
		var sub := "ORI  ·  瓷面守夜人"
		var ssz := 10
		var sw := font.get_string_size(sub, HORIZONTAL_ALIGNMENT_LEFT, -1, ssz).x
		draw_string(font, Vector2((vs.x - sw) * 0.5, ty + 16), sub,
					HORIZONTAL_ALIGNMENT_LEFT, -1, ssz,
					Color(C_SUB.r, C_SUB.g, C_SUB.b, 0.85))

	# ── 按钮 ──
	for i in _items.size():
		_draw_button(font, i, vs)

	# ── 存档槽操作 ──
	_draw_secondary(font, vs)

	# ── 底部提示 ──
	var hint := "↑↓ 选择   Enter 确认   E 复制存档码   I 导入"
	var hw := font.get_string_size(hint, HORIZONTAL_ALIGNMENT_LEFT, -1, 9).x
	draw_string(font, Vector2((vs.x - hw) * 0.5, vs.y - 12), hint,
				HORIZONTAL_ALIGNMENT_LEFT, -1, 9,
				Color(C_DIM.r, C_DIM.g, C_DIM.b, 0.75))


func _draw_button(font: Font, i: int, vs: Vector2) -> void:
	var r := _btn_rect(i, vs)
	var item: Dictionary = _items[i]
	var enabled: bool = item.get("enabled", true)
	var is_sel: bool = (i == _selected)
	var is_hov: bool = (i == _hover)

	var bg := Color(0.10, 0.13, 0.22, 0.9)
	var edge := C_DIM
	var txt := C_DIM

	if not enabled:
		bg = Color(0.07, 0.08, 0.14, 0.9)
		edge = Color(0.22, 0.25, 0.34, 0.7)
		txt = Color(0.35, 0.39, 0.50)
	elif is_sel or is_hov:
		bg = Color(0.16, 0.26, 0.32, 0.95)
		edge = C_EDGE
		txt = C_TEXT

	# 选中时左右各一道竖线（像素风不用发光模糊）
	draw_rect(r, bg)
	draw_rect(r, edge, false, 1.5)

	if is_sel and enabled:
		# 左侧指示三角
		var cx := r.position.x - 12
		var cy := r.position.y + r.size.y * 0.5
		draw_colored_polygon(PackedVector2Array([
			Vector2(cx, cy - 5), Vector2(cx + 7, cy), Vector2(cx, cy + 5),
		]), C_ACCENT)
		# 顶部一条高光线
		draw_rect(Rect2(r.position.x, r.position.y, r.size.x, 1.5),
				  Color(C_EDGE.r, C_EDGE.g, C_EDGE.b, 0.75))

	# 点击闪烁
	var fl: float = _flash.get(item["key"], 0.0)
	if fl > 0.0:
		draw_rect(r, Color(1, 1, 1, 0.22 * (fl / 0.35)))

	# 主文字
	var label: String = item["label"]
	var lsz := 13
	var lw := font.get_string_size(label, HORIZONTAL_ALIGNMENT_LEFT, -1, lsz).x
	draw_string(font, Vector2(r.position.x + (r.size.x - lw) * 0.5,
							  r.position.y + 15), label,
				HORIZONTAL_ALIGNMENT_LEFT, -1, lsz, txt)

	# 副文字（存档摘要）
	var sub: String = item.get("sub", "")
	if sub != "":
		var ssz2 := 8
		var sw2 := font.get_string_size(sub, HORIZONTAL_ALIGNMENT_LEFT, -1, ssz2).x
		var scol := Color(C_SUB.r, C_SUB.g, C_SUB.b, 0.85) if enabled \
			else Color(0.32, 0.36, 0.46)
		draw_string(font, Vector2(r.position.x + (r.size.x - sw2) * 0.5,
								  r.position.y + 27), sub,
					HORIZONTAL_ALIGNMENT_LEFT, -1, ssz2, scol)


func _draw_secondary(font: Font, vs: Vector2) -> void:
	var rs := _secondary_rects(vs)
	var has: bool = _save != null and _save.has_save()

	# 标题
	var lbl := "存档槽"
	var lw := font.get_string_size(lbl, HORIZONTAL_ALIGNMENT_LEFT, -1, 8).x
	draw_string(font, Vector2((vs.x - lw) * 0.5, rs["export"].position.y - 5),
				lbl, HORIZONTAL_ALIGNMENT_LEFT, -1, 8,
				Color(C_DIM.r, C_DIM.g, C_DIM.b, 0.8))

	# 三个按钮：复制存档码 / 导入 / 清除
	# "导入"始终可用（没档的人也可能想导入别人的档）
	var labels := {"copy": "复制存档码", "import": "导入", "clear": "清除"}
	for k in ["copy", "import", "clear"]:
		var r: Rect2 = rs[k]
		var enabled := has if k != "import" else true
		var edge := Color(0.28, 0.34, 0.46) if enabled else Color(0.18, 0.21, 0.28)
		var txt := Color(C_TEXT.r, C_TEXT.g, C_TEXT.b, 0.85) if enabled \
			else Color(0.30, 0.34, 0.44)
		draw_rect(r, Color(0.09, 0.11, 0.18, 0.9))
		draw_rect(r, edge, false, 1.0)
		var t: String = labels[k]
		var tw := font.get_string_size(t, HORIZONTAL_ALIGNMENT_LEFT, -1, 9).x
		draw_string(font, Vector2(r.position.x + (r.size.x - tw) * 0.5,
								  r.position.y + 14), t,
					HORIZONTAL_ALIGNMENT_LEFT, -1, 9, txt)

	# 导入框 + 结果消息
	if _import_open:
		_layout_import_box()

	if _import_msg != "":
		var mc := C_ACCENT if _import_ok else Color("#FF7A9C")
		var mw := font.get_string_size(_import_msg, HORIZONTAL_ALIGNMENT_LEFT,
									   -1, 9).x
		var my: float = rs["copy"].position.y - (32.0 if _import_open else 6.0)
		draw_string(font, Vector2((vs.x - mw) * 0.5, my), _import_msg,
					HORIZONTAL_ALIGNMENT_LEFT, -1, 9, mc)
