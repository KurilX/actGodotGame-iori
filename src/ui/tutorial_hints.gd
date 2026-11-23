extends Control

const GameFont := preload("res://src/ui/game_font.gd")
## 教程提示：玩家走到教学段时在屏幕下方弹出按键提示。
##
## ## 设计
##
## 提示由**世界坐标触发**：玩家 x 落在某段区间就显示对应提示，
## 离开就收起。不用"一次性弹窗 + 确认"，因为玩家可能回头重看。
##
## ## 为什么放屏幕下方而不是世界内
##
## 设计文档里原本想用"牌坊"（世界内 Sprite）。实现时改成屏幕下方 UI：
##   1. 牌坊要单独画一套像素美术，成本高于收益
##   2. 屏幕下方的提示在任何分辨率下都清晰可读
##   3. 牌坊会被地形/敌人遮挡
## 世界内仍然可以加"路标"，但提示文字走 UI 更稳。
##
## ## 只教一次
##
## 每段提示首次进入时停留较久（6s），之后回头只短暂提示（2.5s）。
## 反复弹同样的字会烦人。

const SEGMENTS := [
	{
		"id": "move",
		"x0": 0.0, "x1": 480.0,
		"title": "移动与跳跃",
		"keys": ["A / D  移动", "空格  跳跃（按住跳更高）"],
		"hint": "跑到最右边继续",
		"hold_first": 6.0, "hold_again": 2.5,
	},
	{
		"id": "light",
		"x0": 480.0, "x1": 880.0,
		"title": "轻攻击",
		"keys": ["J  连点：四段轻击", "连段要接得上才有伤害"],
		"hint": "打掉那只苔团",
		"hold_first": 6.0, "hold_again": 2.5,
	},
	{
		"id": "heavy",
		"x0": 880.0, "x1": 1180.0,
		"title": "重攻击 · 破霸体",
		"keys": ["L  重攻击（前摇长、伤害高）", "石守有霸体：轻击打不断，必须用重击"],
		"hint": "用重击打断它抡砸",
		"hold_first": 8.0, "hold_again": 3.0,
	},
	{
		"id": "dash",
		"x0": 1180.0, "x1": 1400.0,
		"title": "闪避 · 无敌帧",
		"keys": ["K  闪避（冲刺瞬间无敌）", "完美闪避会触发子弹时间"],
		"hint": "从两只苔团之间穿过去",
		"hold_first": 7.0, "hold_again": 2.5,
	},
	{
		# **教学段到 BOSS 房分界（x=1560）为止**：
		# 玩家跨过 1560 就不再显示教学提示 —— 那里已经是战斗。
		# 综合段覆盖 1980~2400 是错的原设计，实际综合段的敌人分布在
		# x 2100~2260，但那些在 BOSS 房里；所以综合段改为
		# "进入 BOSS 房前的最后提示"，区间 1880~2000。
		"id": "mix",
		"x0": 1400.0, "x1": 1560.0,
		"title": "综合考验",
		"keys": ["三种敌人同场", "用上你学到的全部"],
		"hint": "右边是守夜人",
		"hold_first": 6.0, "hold_again": 2.5,
	},
]

const C_BG := Color(0.03, 0.04, 0.09, 0.88)
const C_EDGE := Color("#B9F2FF")
const C_TITLE := Color("#FFC46B")
const C_KEY := Color("#E8F0F2")
const C_HINT := Color("#8FD3E8")

var _player: Node2D = null
var _current := ""          # 当前显示的段 id
var _timer := 0.0
var _alpha := 0.0
var _seen := {}             # 已看过的段（决定停留时长）
var _enabled := true
var _t := 0.0


func _ready() -> void:
	set_anchors_preset(Control.PRESET_FULL_RECT)
	offset_left = 0
	offset_top = 0
	offset_right = 0
	offset_bottom = 0
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	set_process(true)


func bind_player(p: Node2D) -> void:
	_player = p


func set_enabled(on: bool) -> void:
	_enabled = on
	if not on:
		_current = ""
		_alpha = 0.0
		queue_redraw()


func _process(delta: float) -> void:
	_t += delta
	if not _enabled or _player == null or not is_instance_valid(_player):
		return

	var seg := _segment_at(_player.global_position.x)
	var seg_id: String = seg.get("id", "") if not seg.is_empty() else ""

	if seg_id != _current:
		_current = seg_id
		if seg_id == "":
			_timer = 0.0
		else:
			var first: bool = not _seen.has(seg_id)
			_seen[seg_id] = true
			_timer = float(seg["hold_first"]) if first \
				else float(seg["hold_again"])

	if _timer > 0.0:
		_timer -= delta
		_alpha = minf(1.0, _alpha + delta * 4.0)
	else:
		_alpha = maxf(0.0, _alpha - delta * 3.0)

	queue_redraw()


func _segment_at(x: float) -> Dictionary:
	for s in SEGMENTS:
		if x >= float(s["x0"]) and x < float(s["x1"]):
			return s
	return {}


func _draw() -> void:
	if _alpha <= 0.01 or _current == "":
		return
	var seg := {}
	for s in SEGMENTS:
		if s["id"] == _current:
			seg = s
			break
	if seg.is_empty():
		return

	var vs := get_viewport_rect().size
	var a := _alpha
	var font := GameFont.get_font()

	# ── 面板尺寸按内容算 ──
	var keys: Array = seg["keys"]
	var h := 20.0 + keys.size() * 13.0 + 14.0
	var w := 300.0
	var x0 := (vs.x - w) * 0.5
	var y0 := vs.y - h - 22.0

	# 背景
	draw_rect(Rect2(x0, y0, w, h),
			  Color(C_BG.r, C_BG.g, C_BG.b, C_BG.a * a))
	# 顶部亮线
	draw_rect(Rect2(x0, y0, w, 1.5),
			  Color(C_EDGE.r, C_EDGE.g, C_EDGE.b, 0.8 * a))

	# 标题
	var title: String = seg["title"]
	var tw := font.get_string_size(title, HORIZONTAL_ALIGNMENT_LEFT, -1, 12).x
	for off in [Vector2(-1, 0), Vector2(1, 0), Vector2(0, -1), Vector2(0, 1)]:
		draw_string(font, Vector2((vs.x - tw) * 0.5, y0 + 15) + off, title,
					HORIZONTAL_ALIGNMENT_LEFT, -1, 12,
					Color(0.03, 0.04, 0.09, a))
	draw_string(font, Vector2((vs.x - tw) * 0.5, y0 + 15), title,
				HORIZONTAL_ALIGNMENT_LEFT, -1, 12,
				Color(C_TITLE.r, C_TITLE.g, C_TITLE.b, a))

	# 按键行
	var yy := y0 + 30.0
	for line in keys:
		var lw := font.get_string_size(str(line), HORIZONTAL_ALIGNMENT_LEFT,
									   -1, 10).x
		draw_string(font, Vector2((vs.x - lw) * 0.5, yy), str(line),
					HORIZONTAL_ALIGNMENT_LEFT, -1, 10,
					Color(C_KEY.r, C_KEY.g, C_KEY.b, a * 0.92))
		yy += 13.0

	# 底部提示（目标）
	var hint: String = seg["hint"]
	var hw := font.get_string_size(hint, HORIZONTAL_ALIGNMENT_LEFT, -1, 9).x
	draw_string(font, Vector2((vs.x - hw) * 0.5, y0 + h - 6), hint,
				HORIZONTAL_ALIGNMENT_LEFT, -1, 9,
				Color(C_HINT.r, C_HINT.g, C_HINT.b, a * 0.85))


func get_current_segment() -> String:
	return _current


func is_showing() -> bool:
	return _alpha > 0.01 and _current != ""
