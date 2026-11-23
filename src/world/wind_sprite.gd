"""风吹植被：会随风摇摆的草、花、芦苇、树。

## 为什么不用 SpriteFrames 逐帧画

一棵会动的芦苇如果逐帧画，12 帧 × N 棵 = 帧数爆炸。
而"风"的本质是**同一个形变参数随时间变化**，用代码逐帧变形更省也更自然：
每棵草只需要几个控制点，按风相位弯曲就行。

## 实现方式

`WindSprite` 是一个自绘 Node2D：持有若干"草叶"（从根部到尖端的折线），
每帧按风相位把顶端偏移出去，画出硬边像素线。

**像素风关键**：顶点必须取整到整数像素，否则线条会糊成抗锯齿效果。

## 风场

不是所有草同步摆动 —— 那样像机械。用 `sin(t * freq + x * k)` 让
不同 x 位置的草相位错开，形成"波浪"从右往左推过去的观感。
"""

extends Node2D

# ── 风参数 ──
@export var wind_freq := 1.1          # 主摆动频率
@export var wind_amp := 3.2           # 顶端最大偏移（像素）
@export var wind_speed := 34.0        # 风向传播速度（越大波越快）
@export var bend_bias := 0.55         # 恒定弯曲（风一直往一边吹）

# 草叶定义：每项 [x偏移, 高度, 颜色, 粗细]
var blades: Array = []
var base_color := Color("#2E4634")
var tip_color := Color("#6E9A6B")

var _t := 0.0
var _phase := 0.0


func _ready() -> void:
	set_process(true)
	# 用自身 x 坐标做相位种子，让同一屏内的草错开
	_phase = global_position.x * 0.012


func add_blade(x: float, h: float, width: float = 1.0,
			   col: Color = Color.WHITE) -> void:
	blades.append({"x": x, "h": h, "w": width, "c": col})


func _process(delta: float) -> void:
	_t += delta
	queue_redraw()


func _draw() -> void:
	# 风向传播：x 越大相位越超前，形成从左到右的波浪
	var wave := sin(_t * wind_freq + _phase) * wind_amp
	var wave2 := sin(_t * wind_freq * 0.63 + _phase * 1.7) * wind_amp * 0.45
	var bend := wave + wave2 + bend_bias * wind_amp

	for b in blades:
		_draw_blade(b["x"], b["h"], b["w"], b["c"], bend)


func _draw_blade(x: float, h: float, w: float, col: Color, bend: float) -> void:
	"""画一根草叶：从根部竖直向上，顶端按 bend 弯曲。

	分 3 段折线，弯曲量按高度平方分布（根部不动、越往尖越弯），
	这样看起来才像"整根被压弯"而不是"顶端平移"。
	"""
	var segs := 3
	var prev := Vector2(x, 0)

	for i in range(1, segs + 1):
		var t := float(i) / segs
		# 高度平方：根部几乎不动，尖端弯得最多
		var offset: float = bend * t * t
		# 取整到像素，保持硬边
		var px := roundf(x + offset)
		var py := roundf(-h * t)
		var p := Vector2(px, py)

		# 粗细：用**矩形**画，而不是叠多条线。
		# 叠线会有 1px 缝隙（硬边像素风里很显眼），矩形是实心的。
		var thick: int = maxi(1, int(round(w * (1.0 - t * 0.45))))
		var left := roundf(minf(prev.x, p.x)) if false else roundf(p.x)
		draw_rect(Rect2(roundf(p.x), roundf(minf(prev.y, p.y)),
						thick, roundf(absf(p.y - prev.y)) + 1.0),
				  col)
		prev = p


func _bend_at(t: float) -> float:
	var base := sin(_t * wind_freq + _phase) * wind_amp
	var base2 := sin(_t * wind_freq * 0.63 + _phase * 1.7) * wind_amp * 0.45
	return (base + base2 + bend_bias * wind_amp) * t * t


## 供测试读取：当前顶端偏移量
func current_bend() -> float:
	return _bend_at(1.0)
