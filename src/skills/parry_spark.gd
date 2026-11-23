"""弹反成功的爆闪特效。

## 为什么单独一个类

原本想在 bootstrap 里用 lambda + `draw.connect` 凑合，但那样
**无法可靠触发 queue_redraw**（Godot 的 `draw` 信号只负责"画什么"，
不负责"什么时候画"）。结果就是特效出不来或者只画一帧。

独立成 Node2D 子类，用 `_process` 每帧 `queue_redraw()` 才是可靠做法。

## 视觉

两圈硬边环从中心向外扩散 + 中心亮核收缩消失，总时长 0.26s。
**不用半透明渐变**：像素风里模糊会糊成一片，硬边环才读得出来。
"""

extends Node2D

const DURATION := 0.26

const C_RING := Color(1.0, 0.98, 0.7)    # 暖白（和弹反的金色弹幕呼应）
const C_CORE := Color(1.0, 1.0, 1.0)

var _t := 0.0


func _ready() -> void:
	set_process(true)


func _process(delta: float) -> void:
	_t += delta
	if _t >= DURATION:
		queue_free()
		return
	queue_redraw()


func _draw() -> void:
	var k := clampf(_t / DURATION, 0.0, 1.0)
	var fade := 1.0 - k

	# 两圈扩散的环
	for i in 2:
		var r: float = 6.0 + i * 5.0 + k * (26.0 + i * 10.0)
		var a: float = 0.85 * fade * (1.0 - i * 0.3)
		draw_arc(Vector2.ZERO, r, 0.0, TAU, 24,
				 Color(C_RING.r, C_RING.g, C_RING.b, a), 1.5)

	# 中心亮核：快速收缩
	if k < 0.5:
		var cr := 4.0 * (1.0 - k * 2.0)
		draw_circle(Vector2.ZERO, cr, Color(C_CORE.r, C_CORE.g, C_CORE.b,
											0.95 * fade))
