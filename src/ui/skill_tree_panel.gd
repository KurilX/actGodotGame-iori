extends Control
## 技能树面板：按 Tab 打开/关闭。
##
## ## 布局
##
## 节点位置由 skill_tree.gd 的 `pos` 字段给出（归一化坐标），
## UI 只负责映射到屏幕。这样加新技能不用改这里。
##
## ## 三种节点状态
##
##   已解锁   实心圆 + 亮边，图标正常显示
##   可解锁   虚线圆 + 暗边，显示"?"，并列出触发条件
##   未满足   灰色圆 + 极暗，显示锁形
##
## ## 为什么用"圆 + 连线"而不是列表
##
## 列表看不出"前后依赖"。连线的意义是告诉玩家"你还差哪个前置"。

const SkillTree := preload("res://src/skills/skill_tree.gd")

const BG_ALPHA := 0.88
# 节点半径。**不能太大**：节点间距约 90px（见 skill_tree.gd 的 pos），
# 半径 24 + 名字偏移 16 会占到 64px，和下一个节点重叠，
# 导致名字被盖住（实测解锁节点的名字完全看不见）。
const NODE_R := 19.0

const C_BG := Color(0.04, 0.05, 0.11, BG_ALPHA)
const C_GRID := Color(0.14, 0.17, 0.28, 0.55)
const C_LINE_ON := Color(0.73, 0.95, 1.0, 0.75)
const C_LINE_OFF := Color(0.24, 0.28, 0.42, 0.55)
const C_NODE_ON := Color(0.25, 0.55, 0.48, 1.0)
const C_NODE_ON_EDGE := Color("#B9F2FF")
const C_NODE_READY := Color(0.18, 0.22, 0.36, 1.0)
const C_NODE_READY_EDGE := Color("#FFC46B")
const C_NODE_LOCK := Color(0.11, 0.13, 0.21, 1.0)
const C_NODE_LOCK_EDGE := Color(0.26, 0.30, 0.44, 1.0)
const C_TEXT := Color("#E8F0F2")
const C_SUB := Color("#8FD3E8")
const C_ACCENT := Color("#FFC46B")

var _tree: Node = null
var _open := false
var _t := 0.0
var _hover: String = ""
var _flash: Dictionary = {}      # skill_id -> 剩余闪烁时间


func _ready() -> void:
	set_anchors_preset(Control.PRESET_FULL_RECT)
	offset_left = 0
	offset_top = 0
	offset_right = 0
	offset_bottom = 0
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	visible = false
	set_process(false)


func bind(tree: Node) -> void:
	_tree = tree
	if _tree and _tree.has_signal("skill_unlocked"):
		_tree.skill_unlocked.connect(_on_unlocked)
	queue_redraw()


func _on_unlocked(skill_id: String) -> void:
	# 解锁时闪一下，即使面板没开着也记录（下次打开能看到高亮）
	_flash[skill_id] = 1.6


func toggle() -> void:
	_open = not _open
	visible = _open
	set_process(_open)
	if _open:
		_t = 0.0
		# 立刻给一个非零的 _t，避免首帧完全透明（慢帧/headless 下
		# _t 累积很慢，首帧 a≈0 会让面板看起来"没打开"）
		_t = 0.10
	queue_redraw()


func is_open() -> bool:
	return _open


func _process(delta: float) -> void:
	_t += delta
	for k in _flash.keys():
		_flash[k] -= delta
		if _flash[k] <= 0.0:
			_flash.erase(k)
	# **每次都要重绘**。
	# 之前只在 _flash 非空时 queue_redraw，导致：
	#   打开面板 → _draw 执行一次（此时 _t≈0，淡入透明度接近 0）
	#   → 之后再也没有重绘 → 面板永远是透明的
	# 表现为"面板打开了但屏幕上看不到"。
	queue_redraw()


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo:
		# **浏览器里 Tab 会被用来切焦点**，Web 导出时按下 Tab
		# 可能根本不进游戏（或者切走焦点）。所以主键用 F1，
		# Tab 作为桌面端的备选。
		if event.keycode == KEY_F1 or event.keycode == KEY_TAB:
			toggle()
			get_viewport().set_input_as_handled()


func _node_pos(skill_id: String, vs: Vector2) -> Vector2:
	var sk: Dictionary = _tree.get_skill(skill_id) if _tree else {}
	var p: Vector2 = sk.get("pos", Vector2(0.5, 0.5))
	# 留出边距，避免节点贴边
	var margin := 60.0
	return Vector2(
		margin + (vs.x - margin * 2) * p.x,
		margin + (vs.y - margin * 2) * p.y,
	)


func _draw() -> void:
	if not _open or _tree == null:
		return

	var vs := get_viewport_rect().size
	# 打开时有个淡入。用 0.10 秒（而不是 0.18）—— 实测 headless/慢帧下
	# _t 累积很慢，0.18 会让面板长时间几乎透明，截图看起来像"没显示"。
	var a := minf(1.0, _t / 0.10)

	# ── 背景 ──
	draw_rect(Rect2(Vector2.ZERO, vs),
			  Color(C_BG.r, C_BG.g, C_BG.b, C_BG.a * a))

	# ── 背景网格（暗示这是"技术面板"）──
	var gs := 24.0
	for x in range(0, int(vs.x), int(gs)):
		draw_line(Vector2(x, 0), Vector2(x, vs.y),
				  Color(C_GRID.r, C_GRID.g, C_GRID.b, C_GRID.a * a), 1.0)
	for y in range(0, int(vs.y), int(gs)):
		draw_line(Vector2(0, y), Vector2(vs.x, y),
				  Color(C_GRID.r, C_GRID.g, C_GRID.b, C_GRID.a * a), 1.0)

	var font := ThemeDB.fallback_font

	# ── 标题 ──
	var title := "技能树"
	var tw := font.get_string_size(title, HORIZONTAL_ALIGNMENT_LEFT, -1, 16).x
	draw_string(font, Vector2((vs.x - tw) * 0.5, 30), title,
				HORIZONTAL_ALIGNMENT_LEFT, -1, 16,
				Color(C_TEXT.r, C_TEXT.g, C_TEXT.b, a))

	var cnt := "%d / %d 已解锁" % [_tree.get_unlocked_count(),
								_tree.all_skills().size()]
	var cw := font.get_string_size(cnt, HORIZONTAL_ALIGNMENT_LEFT, -1, 10).x
	draw_string(font, Vector2((vs.x - cw) * 0.5, 46), cnt,
				HORIZONTAL_ALIGNMENT_LEFT, -1, 10,
				Color(C_SUB.r, C_SUB.g, C_SUB.b, a * 0.9))

	# ── 连线（先画，压在节点下面）──
	for id in _tree.all_skills():
		var sk: Dictionary = _tree.get_skill(id)
		var to := _node_pos(id, vs)
		for req in sk.get("requires", []):
			var from := _node_pos(req, vs)
			var on: bool = _tree.is_unlocked(req)
			var col := C_LINE_ON if on else C_LINE_OFF
			# 已解锁的连线画实线 + 流动光点
			draw_line(from, to, Color(col.r, col.g, col.b, col.a * a), 2.0)
			if on:
				# 沿线流动的光点，暗示"已打通"
				var ph := fmod(_t * 0.8 + float(hash(id) % 100) / 100.0, 1.0)
				var p := from.lerp(to, ph)
				draw_circle(p, 2.0,
							Color(C_LINE_ON.r, C_LINE_ON.g, C_LINE_ON.b,
								  0.9 * a))

	# ── 节点 ──
	for id in _tree.all_skills():
		var sk: Dictionary = _tree.get_skill(id)
		var pos := _node_pos(id, vs)
		var unlocked: bool = _tree.is_unlocked(id)
		var pre_ok := true
		for req in sk.get("requires", []):
			if not _tree.is_unlocked(req):
				pre_ok = false
				break
		_draw_node(font, id, sk, pos, unlocked, pre_ok, a)

	# ── 底部提示 ──
	var hint := "F1 / Tab 关闭"
	var hw := font.get_string_size(hint, HORIZONTAL_ALIGNMENT_LEFT, -1, 9).x
	draw_string(font, Vector2((vs.x - hw) * 0.5, vs.y - 12), hint,
				HORIZONTAL_ALIGNMENT_LEFT, -1, 9,
				Color(C_SUB.r, C_SUB.g, C_SUB.b, a * 0.7))


func _draw_node(font: Font, id: String, sk: Dictionary, pos: Vector2,
				unlocked: bool, pre_ok: bool, a: float) -> void:
	var r := NODE_R
	var body := C_NODE_LOCK
	var edge := C_NODE_LOCK_EDGE
	var label_col := Color(0.45, 0.50, 0.62, a)

	if unlocked:
		body = C_NODE_ON
		edge = C_NODE_ON_EDGE
		label_col = Color(C_TEXT.r, C_TEXT.g, C_TEXT.b, a)
	elif pre_ok:
		body = C_NODE_READY
		edge = C_NODE_READY_EDGE
		label_col = Color(C_ACCENT.r, C_ACCENT.g, C_ACCENT.b, a)

	# 解锁时的脉冲光晕
	var fl: float = _flash.get(id, 0.0)
	if fl > 0.0:
		var k := fl / 1.6
		# 光晕只画两圈、半径收小，避免盖住下方节点名称
		for rr in [r + 6.0, r + 12.0]:
			draw_arc(pos, rr * (1.0 + (1.0 - k) * 0.45), 0.0, TAU, 32,
					 Color(edge.r, edge.g, edge.b, 0.45 * k * a), 1.5)

	# 主体
	draw_circle(pos, r, Color(body.r, body.g, body.b, body.a * a))
	draw_arc(pos, r, 0.0, TAU, 32,
			 Color(edge.r, edge.g, edge.b, a), 2.0)

	# 图标 / 问号 / 锁
	if unlocked:
		# 已解锁：画一个内圈亮点表示"激活"
		draw_circle(pos, r * 0.35,
					Color(C_NODE_ON_EDGE.r, C_NODE_ON_EDGE.g,
						  C_NODE_ON_EDGE.b, 0.9 * a))
	elif pre_ok:
		# 可解锁：问号
		var q := "?"
		var qw := font.get_string_size(q, HORIZONTAL_ALIGNMENT_LEFT,
									   -1, 18).x
		draw_string(font, pos + Vector2(-qw * 0.5, 7), q,
					HORIZONTAL_ALIGNMENT_LEFT, -1, 18,
					Color(C_ACCENT.r, C_ACCENT.g, C_ACCENT.b, a))
	else:
		# 未满足：锁形（用两个矩形拼）
		draw_rect(Rect2(pos.x - 5, pos.y - 1, 10, 8),
				  Color(0.35, 0.40, 0.52, a))
		draw_arc(pos + Vector2(0, -2), 4.0, PI, TAU, 12,
				 Color(0.35, 0.40, 0.52, a), 1.5)

	# 名字（节点下方）。加一圈深色描边 —— 节点光晕和连线是浅色，
	# 文字直接叠上去会看不清（实测解锁后名字被光晕盖住）。
	var nm: String = sk.get("name", id)
	var nw := font.get_string_size(nm, HORIZONTAL_ALIGNMENT_LEFT, -1, 10).x
	var npos := pos + Vector2(-nw * 0.5, r + 16)
	for off in [Vector2(-1, 0), Vector2(1, 0), Vector2(0, -1), Vector2(0, 1)]:
		draw_string(font, npos + off, nm,
					HORIZONTAL_ALIGNMENT_LEFT, -1, 10,
					Color(0.03, 0.04, 0.09, 0.9 * a))
	draw_string(font, npos, nm, HORIZONTAL_ALIGNMENT_LEFT, -1, 10, label_col)

	# 未解锁时，把触发条件显示在下面 —— 这是"怎么解锁"的提示
	if not unlocked:
		var combo: Array = sk.get("combo", [])
		if not combo.is_empty():
			var txt := " + ".join(combo.map(func(c):
				return "轻" if c == "light" else "重"))
			var cw := font.get_string_size(txt, HORIZONTAL_ALIGNMENT_LEFT,
										   -1, 8).x
			var cp := pos + Vector2(-cw * 0.5, r + 28)
			for off in [Vector2(-1, 0), Vector2(1, 0)]:
				draw_string(font, cp + off, txt,
							HORIZONTAL_ALIGNMENT_LEFT, -1, 8,
							Color(0.03, 0.04, 0.09, 0.85 * a))
			draw_string(font, cp, txt,
						HORIZONTAL_ALIGNMENT_LEFT, -1, 8,
						Color(C_SUB.r, C_SUB.g, C_SUB.b, a * 0.9))
		elif not pre_ok:
			var txt2 := "需先解锁前置"
			var cw2 := font.get_string_size(txt2, HORIZONTAL_ALIGNMENT_LEFT,
											-1, 8).x
			draw_string(font, pos + Vector2(-cw2 * 0.5, r + 25), txt2,
						HORIZONTAL_ALIGNMENT_LEFT, -1, 8,
						Color(0.45, 0.50, 0.62, a * 0.75))
