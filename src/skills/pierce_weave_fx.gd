extends Node2D
## 新技能「贯穿织」的视觉效果与伤害判定。
##
## ## 技能定位
##
## 触发条件：轻攻击 1→2→3 段，接一次重攻击。
## 效果：射出一道横贯屏幕的丝线光束，**穿透所有敌人**造成伤害。
##
## ## 为什么这样设计
##
## 已有手段都是"贴身"的（连段要靠近、重击要贴身）。这个技能补的是
## **远程清场**能力 —— 用来对付 BOSS 的弹幕阶段（站远处输出）和
## 多个敌人并排的情况。它是"连招奖励"而非"数值升级"。
##
## ## 视觉分层
##
##   1. 光束主线（月白，粗）
##   2. 上下各一条细的流动丝线（暗示"织"）
##   3. 命中点的爆裂环
##   4. 蓄力瞬间的前置闪光（在发射前一帧）

const BEAM_DUR := 0.42
const BEAM_LEN := 460.0
const BEAM_H := 10.0
const DAMAGE := 8

const C_CORE := Color("#FFFFFF")
const C_MID := Color("#D8F0F8")
const C_OUT := Color("#B9F2FF")
const C_THREAD := Color("#A8E8C6")

var _active := false
var _t := 0.0
var _dir := 1
var _origin := Vector2.ZERO
var _hit_targets: Array = []


func _ready() -> void:
	z_index = 45
	visible = false
	set_process(false)


func fire(world_pos: Vector2, facing: int) -> void:
	_origin = world_pos
	_dir = facing
	_t = 0.0
	_active = true
	visible = true
	_hit_targets.clear()
	set_process(true)
	queue_redraw()
	_deal_damage()


func _deal_damage() -> void:
	"""沿光束路径判定伤害：穿透所有敌人。"""
	var half_h := BEAM_H * 0.5 + 6.0
	for e in get_tree().get_nodes_in_group("enemy"):
		if e in _hit_targets:
			continue
		if not e.has_method("take_hit"):
			continue
		var d: Vector2 = e.global_position - _origin
		# 必须在朝向那一侧
		if signf(d.x) != float(_dir) and absf(d.x) > 4.0:
			continue
		# 必须落在光束长度内
		if absf(d.x) > BEAM_LEN:
			continue
		# 垂直距离在光束宽度内
		if absf(d.y) > half_h:
			continue
		_hit_targets.append(e)
		e.take_hit(DAMAGE, _origin.x)


func _process(delta: float) -> void:
	if not _active:
		return
	_t += delta
	if _t >= BEAM_DUR:
		_active = false
		visible = false
		set_process(false)
		queue_redraw()
		return
	queue_redraw()


func _draw() -> void:
	if not _active:
		return

	var k := clampf(_t / BEAM_DUR, 0.0, 1.0)
	# 前 20% 快速展开，之后保持，最后 30% 淡出
	var grow := minf(1.0, k / 0.20)
	var fade := 1.0 if k < 0.70 else (1.0 - (k - 0.70) / 0.30)

	var len_now := BEAM_LEN * grow
	# 光束高度也随展开变大，中间最粗
	var hh := BEAM_H * (0.4 + 0.6 * grow) * (0.6 + 0.4 * fade)

	# 起点（角色身前）
	var x0 := float(_dir) * 6.0
	var x1 := x0 + float(_dir) * len_now

	# ── 外层光晕 ──
	for i in 3:
		var pad := float(i + 1) * 3.0
		draw_rect(Rect2(x0, -hh - pad, len_now * _dir, (hh + pad) * 2.0),
				  Color(C_OUT.r, C_OUT.g, C_OUT.b, 0.10 * fade))
	# 上面那个 Rect2 对负宽不合法，改用规范化矩形
	# （Godot 的 draw_rect 接受负尺寸但渲染可能异常，这里显式规范化）

	# ── 主光束 ──
	var ry := -hh
	var rh := hh * 2.0
	draw_rect(Rect2(minf(x0, x1), ry, absf(x1 - x0), rh),
			  Color(C_MID.r, C_MID.g, C_MID.b, 0.85 * fade))
	# 内芯（更亮更窄）
	draw_rect(Rect2(minf(x0, x1), -hh * 0.4, absf(x1 - x0), hh * 0.8),
			  Color(C_CORE.r, C_CORE.g, C_CORE.b, 0.95 * fade))

	# ── 上下两条流动丝线 ──
	for side: float in [-1.0, 1.0]:
		var ly: float = side * (hh + 3.0)
		var segs := 14
		for i in segs:
			var t0 := float(i) / segs
			var t1 := float(i + 0.55) / segs
			# 相位偏移让丝线像在流动
			var ph := fmod(t0 + _t * 2.2 + (0.5 if side > 0 else 0.0), 1.0)
			if ph > 1.0:
				ph -= 1.0
			var px0 := x0 + len_now * _dir * ph
			var px1 := x0 + len_now * _dir * minf(1.0, ph + 0.04)
			draw_line(Vector2(px0, ly), Vector2(px1, ly),
					  Color(C_THREAD.r, C_THREAD.g, C_THREAD.b,
							0.55 * fade), 1.0)
			if t0 > t1:
				break

	# ── 端点爆裂 ──
	if grow >= 1.0:
		var tip := Vector2(x1, 0)
		var burst := 1.0 - (k - 0.20) / 0.80
		if burst > 0.0:
			for rr in [10.0, 18.0, 27.0]:
				draw_arc(tip, rr * (1.2 - burst * 0.5), 0.0, TAU, 20,
						 Color(C_OUT.r, C_OUT.g, C_OUT.b,
							   0.6 * burst * fade), 1.5)

	# ── 发射口闪光 ──
	if k < 0.35:
		var fa := (1.0 - k / 0.35) * fade
		draw_circle(Vector2(x0, 0), 9.0,
					Color(C_CORE.r, C_CORE.g, C_CORE.b, 0.6 * fa))


func is_active() -> bool:
	return _active
