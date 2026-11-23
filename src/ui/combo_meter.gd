extends Control

const GameFont := preload("res://src/ui/game_font.gd")
## 连击条：右侧竖条，按连击段数累加，满了升级评级（F → SS）。
##
## ## 评分规则
##
##   每命中一次敌人 +1 段（轻攻击一段算 1，重攻击一段算 2 —— 重击更值钱）
##   段数累积到阈值就升级：F → E → D → C → B → A → S → SS
##   **受击清零**（被打断就没了，这是压力来源）
##   **6 秒不出手自动衰减**（不能靠站着攒）
##
## ## 为什么用「段数」而不是「伤害」
##
## 伤害会让重攻击变成唯一解（一次 12 点，等于轻攻击打 12 下）。
## 用段数则鼓励**连续、准确**地打，轻重各有位置：
## 轻攻击接得更快（段数涨得快），重攻击单次值更多（+2）。
##
## ## 视觉
##
## 右侧竖条 + 等级字母。条的快慢用颜色区分：
##   F~D 冷色（青），C~A 暖色（金），S~SS 危险色（红）。
## 等级变化时有一次放大脉冲，让玩家明确感知到"升级了"。

signal rank_changed(old_rank: int, new_rank: int)

# 评级：F 最低，SS 最高
const RANKS := ["F", "E", "D", "C", "B", "A", "S", "SS"]

# 达到各评级所需的累计段数
# 递增幅度刻意做成"前期快、后期慢"，让玩家很快看到 F→D，
# 但 A→SS 需要真正的连续压制
const RANK_THRESHOLDS := [0, 3, 6, 10, 15, 21, 28, 36]

const DECAY_TIME := 6.0        # 多久不出手开始衰减
const DECAY_RATE := 6.0        # 每秒掉多少段
const BAR_W := 8.0
const BAR_H := 120.0
const MARGIN_R := 34.0      # 右边距。太小会把 SS 字样挤出屏幕（实测 18 时被裁切）

var _segments := 0             # 当前累计段数
var _rank := 0                 # 当前评级下标（0=F）
var _idle := 0.0               # 距上次命中的时间
var _pulse := 0.0              # 升级脉冲（1→0）
var _bar_fill := 0.0           # 进度条平滑值（0..1）
var _decay_acc := 0.0           # 衰减累加器（浮点，攒够 1 才扣 1 段）
var _last_reported := 0        # 上次上报的段数（避免重复发信号）

# 颜色（取自项目调色板）
const C_LOW := Color("#B9F2FF")     # 冷色：F~D
const C_MID := Color("#FFC46B")     # 暖色：C~A
const C_HIGH := Color("#FF5A6E")    # 危险：S~SS
const C_BG := Color(0.07, 0.08, 0.16, 0.72)
const C_EDGE := Color(0.75, 0.91, 0.78, 0.28)
const C_TEXT := Color("#D8F0F8")


func _ready() -> void:
	set_anchors_preset(Control.PRESET_FULL_RECT)
	# 只设锚点不够：offset 会保留原值，Control 尺寸可能变成 (0,0)，
	# 导致 draw_* 被裁剪。必须显式清零。
	offset_left = 0
	offset_top = 0
	offset_right = 0
	offset_bottom = 0
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	# 初始隐藏：没有连击时不占用屏幕
	visible = false


# ─────────────────── 对外接口 ───────────────────

func register_hit(weight: int = 1) -> void:
	"""命中敌人时调用。weight：轻攻击 1，重攻击 2。"""
	_segments += maxi(1, weight)
	_idle = 0.0
	visible = true

	var new_rank := _rank_for(_segments)
	if new_rank != _rank:
		var old := _rank
		_rank = new_rank
		_pulse = 1.0
		rank_changed.emit(old, new_rank)
	queue_redraw()


func register_whiff(heavy: bool = false) -> void:
	"""空挥扣段：挥空一次扣 1 段（重攻击挥空扣 2 段）。

	为什么要扣：没有惩罚的话，玩家可以对着空气连按攒满 SS，
	评级就成了"按得久"而不是"打得准"。
	重攻击代价更大（前摇长、收招长），挥空的惩罚也应该更重。
	"""
	if _segments <= 0:
		return
	var penalty := 2 if heavy else 1
	_segments = maxi(0, _segments - penalty)
	_idle = 0.0          # 挥空也算"出手"，重置超时计时
	var nr := _rank_for(_segments)
	if nr != _rank:
		var old := _rank
		_rank = nr
		rank_changed.emit(old, nr)
	if _segments == 0:
		reset_combo()
	else:
		queue_redraw()


func register_perfect_dodge() -> void:
	"""完美闪避加成：给一次段数奖励，奖励高风险操作。

	现在完美闪避只触发子弹时间，没有任何直接收益，
	玩家没有动力去练。给 +2 段，让它成为攒评级的高效手段。
	"""
	_segments += 2
	_idle = 0.0
	visible = true
	var nr := _rank_for(_segments)
	if nr != _rank:
		var old := _rank
		_rank = nr
		_pulse = 1.0
		rank_changed.emit(old, nr)
	queue_redraw()


func reset_combo() -> void:
	"""重置连击（受击 / 手动清空）。"""
	if _segments == 0 and _rank == 0:
		return
	var old := _rank
	_segments = 0
	_rank = 0
	_idle = 0.0
	_pulse = 0.0
	_bar_fill = 0.0
	_decay_acc = 0.0
	_last_reported = 0
	visible = false
	if old != 0:
		rank_changed.emit(old, 0)
	queue_redraw()


func get_segments() -> int:
	return _segments


func get_rank() -> int:
	return _rank


func get_rank_label() -> String:
	return RANKS[_rank]


func _rank_for(segments: int) -> int:
	var r := 0
	for i in RANK_THRESHOLDS.size():
		if segments >= RANK_THRESHOLDS[i]:
			r = i
	return r


# ─────────────────── 每帧推进 ───────────────────

func _process(delta: float) -> void:
	if _segments > 0:
		_idle += delta
		# 超时衰减。
		# **坑**：早期写的是 `_segments -= int(DECAY_RATE * delta)`，
		# 但 delta 约 0.016s，6.0 * 0.016 = 0.096，int() 取整后是 0 ——
		# 段数永远减不下去，"衰减"形同虚设（测试第15项抓到）。
		# 改成用浮点累加器记录"该扣多少"，攒够 1 才真正扣。
		if _idle >= DECAY_TIME:
			_decay_acc += DECAY_RATE * delta
			while _decay_acc >= 1.0 and _segments > 0:
				_decay_acc -= 1.0
				_segments -= 1
			if _segments != _last_reported:
				_last_reported = _segments
				var nr := _rank_for(_segments)
				if nr != _rank:
					var old := _rank
					_rank = nr
					rank_changed.emit(old, nr)
				queue_redraw()
			if _segments == 0:
				reset_combo()

	if _pulse > 0.0:
		_pulse = maxf(_pulse - delta * 3.2, 0.0)
		queue_redraw()

	# 进度条平滑跟随
	var target := _fill_ratio()
	_bar_fill = lerpf(_bar_fill, target, 1.0 - pow(0.001, delta))


func _fill_ratio() -> float:
	"""当前评级内的完成度（0..1）。到 SS 后恒为 1。"""
	if _rank >= RANKS.size() - 1:
		return 1.0
	var lo: int = RANK_THRESHOLDS[_rank]
	var hi: int = RANK_THRESHOLDS[_rank + 1]
	if hi <= lo:
		return 1.0
	return clampf(float(_segments - lo) / float(hi - lo), 0.0, 1.0)


# ─────────────────── 绘制 ───────────────────

func _draw() -> void:
	if _segments <= 0:
		return

	var vs := get_viewport_rect().size
	# 右侧垂直居中
	var x := vs.x - MARGIN_R - BAR_W
	var y := (vs.y - BAR_H) * 0.5

	# 背板
	draw_rect(Rect2(x - 3, y - 3, BAR_W + 6, BAR_H + 6), C_BG)
	draw_rect(Rect2(x - 3, y - 3, BAR_W + 6, BAR_H + 6), C_EDGE, false, 1.0)

	# 填充：从下往上
	var col := _rank_color()
	var fh := BAR_H * _bar_fill
	draw_rect(Rect2(x, y + BAR_H - fh, BAR_W, fh), col)

	# 填充高光（左边缘 1px 亮线）
	if fh > 2:
		draw_rect(Rect2(x, y + BAR_H - fh, 2, fh),
				  Color(col.r + 0.25, col.g + 0.25, col.b + 0.25, 0.9))

	# 等级刻度：标出每级的分界
	for i in range(1, RANKS.size()):
		var t: float = float(RANK_THRESHOLDS[i]) / float(RANK_THRESHOLDS[-1])
		var ty := y + BAR_H * (1.0 - t)
		draw_line(Vector2(x - 2, ty), Vector2(x + BAR_W + 2, ty),
				  Color(1, 1, 1, 0.16), 1.0)

	# 等级字母：在条的上方
	var label: String = RANKS[_rank]
	# 等级越高字号越大，SS 用最大
	var scale_k := 1.0 + 0.22 * _rank
	if _pulse > 0.0:
		scale_k += _pulse * 0.55

	# 用 draw_string 需要字体，改用 draw_rect 拼字符太重；
	# 这里用 Godot 默认主题字体
	var font := GameFont.get_font()
	var fsize := int(13 * scale_k)
	var col_lbl := _rank_color()
	# 描边：先画深色偏移，再画本体（提升在夜景上的可读性）
	# 等级字母居中于条中心。
	# SS 是两个字符、宽度更大，需要夹在屏幕内，否则会被右边裁掉。
	var tw := font.get_string_size(label, HORIZONTAL_ALIGNMENT_LEFT, -1, fsize).x
	var tx := x + BAR_W * 0.5 - tw * 0.5
	var ty := y - 9
	tx = clampf(tx, 2.0, vs.x - tw - 2.0)
	for off in [Vector2(-1, 0), Vector2(1, 0), Vector2(0, -1), Vector2(0, 1)]:
		draw_string(font, Vector2(tx, ty) + off, label,
					HORIZONTAL_ALIGNMENT_LEFT, -1, fsize,
					Color(0.07, 0.08, 0.16, 0.95))
	draw_string(font, Vector2(tx, ty), label,
				HORIZONTAL_ALIGNMENT_LEFT, -1, fsize, col_lbl)

	# 段数：条的下方，小字
	var seg_txt := str(_segments)
	var ssize := 9
	var sw := font.get_string_size(seg_txt, HORIZONTAL_ALIGNMENT_LEFT, -1, ssize).x
	draw_string(font, Vector2(x + BAR_W * 0.5 - sw * 0.5, y + BAR_H + 12),
				seg_txt, HORIZONTAL_ALIGNMENT_LEFT, -1, ssize,
				Color(C_TEXT.r, C_TEXT.g, C_TEXT.b, 0.62))


func _rank_color() -> Color:
	if _rank <= 2:
		return C_LOW
	if _rank <= 5:
		return C_MID
	return C_HIGH
