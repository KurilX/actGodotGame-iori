"""野花：一根随风的茎 + 十字形花冠。

## 为什么要单独一个类

花和草的区别：草是"整根弯"，花是"**茎弯、花冠保持形状**"——
花朵自己会有一点跟不上茎的滞后感（就像真花那样）。

用同一个 WindSprite 画不了：它把所有点一起弯。这里分成两段：
茎用 WindSprite 的弯曲算法，花冠单独按滞后相位偏移。
"""

extends Node2D

@export var petal_color := Color("#FFB8D0")
@export var stem_x := 0.0
@export var stem_h := 12.0
@export var sway_amp := 3.6
@export var sway_freq := 1.15
# 描边：和角色/敌人/草丛同一个墨色
@export var outline := true

const INK := Color("#12142A")

var _t := 0.0
var _phase := 0.0


func _ready() -> void:
	set_process(true)
	_phase = stem_x * 0.012 + 0.9


func _process(delta: float) -> void:
	_t += delta
	queue_redraw()


func _bend(lag: float) -> float:
	""""计算弯曲量。lag 让花冠比茎慢一拍（真实感）。"""
	var a := sin(_t * sway_freq - lag + _phase) * sway_amp
	var b := sin(_t * sway_freq * 0.57 - lag * 0.5 + _phase * 1.4) * sway_amp * 0.4
	return a + b


func _draw() -> void:
	# ── 茎 ──
	var bend := _bend(0.0)
	var top := Vector2(roundf(bend * 0.8), roundf(-stem_h))
	var mid := Vector2(roundf(bend * 0.35), roundf(-stem_h * 0.5))

	# 茎的描边：先画 3px 宽的深色底线，再叠 1px 本色。
	# 茎只有 1px，四周描边会变粗管子，所以用"左右各 1px"的底线方案
	# （和 wind_sprite.gd 里草叶的处理一致）。
	if outline:
		draw_line(Vector2(-1, 0), mid + Vector2(-1, 0), INK, 1.0)
		draw_line(Vector2(1, 0), mid + Vector2(1, 0), INK, 1.0)
		draw_line(mid + Vector2(-1, 0), top + Vector2(-1, 0), INK, 1.0)
		draw_line(mid + Vector2(1, 0), top + Vector2(1, 0), INK, 1.0)
	draw_line(Vector2.ZERO, mid, Color("#4A6B4F"), 1.0)
	draw_line(mid, top, Color("#5A8A5E"), 1.0)

	# ── 花冠 ──
	# 比茎慢 0.35 相位，画成十字 + 中心亮点
	var cbend := _bend(0.35)
	var cx := roundf(cbend)
	var cy := roundf(-stem_h - 1.0)

	var petals := [
		Rect2(cx - 1, cy - 2, 3, 2),
		Rect2(cx - 1, cy + 1, 3, 2),
		Rect2(cx - 2, cy - 1, 2, 3),
		Rect2(cx + 1, cy - 1, 2, 3),
	]

	# 描边：把整个花冠的包围盒外扩 1px 先填深色。
	# 花冠是多块矩形拼的十字，逐个描边会在中间留缝，
	# 整体填一个外扩矩形更干净（中间重叠部分被本体盖住）。
	if outline:
		draw_rect(Rect2(cx - 3, cy - 3, 7, 7), INK)

	for r in petals:
		draw_rect(r, petal_color)
	# 花心
	draw_rect(Rect2(cx, cy, 1, 1), Color("#FFE9A8"))
