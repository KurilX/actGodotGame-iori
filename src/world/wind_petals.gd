"""飘落的花瓣：被风吹过场景的粒子。

## 为什么需要这个

静止的草丛只能表达"草在动"，但**风的实感主要来自"有东西被吹走"**。
花瓣/落叶从右往左飘过，玩家立刻能感到有风。

## 实现要点

1. **不用 GPUParticles2D** —— 它的半透明淡入淡出在像素风里会糊成光斑。
   这里用自绘，每个花瓣是 2~4 个硬边像素点。

2. **循环而不是一次性** —— 花瓣在右边界生成、飘出左边界后回收，
   水平和垂直范围都远大于视口，玩家走到哪都有花瓣。

3. **跟随相机** —— 花瓣位置是**世界坐标**，铺满整张地图（0~2400），
   而不是只围着相机。这样玩家移动时花瓣自然地从身边飘过。

## 三种形态

  · 花瓣（粉色小方块，旋转）
  · 落叶（较大的斜四边形，翻转）
  · 尘絮（1px 亮点，飘得最慢）
"""

extends Node2D

@export var count := 46
@export var area_left := -200.0
@export var area_right := 2600.0
@export var area_top := 180.0
@export var area_bottom := 500.0
# 是否画描边（花瓣/落叶画，尘絮不画）
@export var outline := true

const WIND_X := -26.0         # 风速（向左）
const SWAY := 9.0             # 横向摇摆幅度

# 描边：和角色/敌人/草丛同一个墨色
const INK := Color("#12142A")

const C_PETAL := Color("#FFB8D0")
const C_PETAL_DK := Color("#D98BA8")
const C_LEAF := Color("#A8E8C6")
const C_LEAF_DK := Color("#5FA882")
const C_DUST := Color("#E8F0F2")

var _items: Array = []
var _t := 0.0


func _ready() -> void:
	z_index = -3
	set_process(true)
	_seed_items()


func _seed_items() -> void:
	var rng := RandomNumberGenerator.new()
	rng.seed = 20261123
	_items.clear()
	for i in count:
		_items.append(_new_item(rng, true))


func _new_item(rng: RandomNumberGenerator, initial: bool) -> Dictionary:
	var kind := rng.randi_range(0, 9)
	var k: String = "petal" if kind < 5 else ("leaf" if kind < 8 else "dust")
	return {
		"x": rng.randf_range(area_left, area_right),
		"y": rng.randf_range(area_top, area_bottom),
		"vx": WIND_X * rng.randf_range(0.7, 1.5),
		"vy": rng.randf_range(4.0, 14.0),
		"sway_ph": rng.randf_range(0.0, TAU),
		"sway_f": rng.randf_range(0.8, 1.8),
		"k": k,
		"size": rng.randi_range(1, 2),
		"life": rng.randf_range(0.0, 6.0),
	}


func _process(delta: float) -> void:
	_t += delta
	for it in _items:
		it["x"] += it["vx"] * delta
		it["y"] += it["vy"] * delta
		it["life"] += delta
		# 超出边界回收（从右侧重新进入）
		if it["x"] < area_left:
			it["x"] = area_right
			it["y"] = randf_range(area_top, area_bottom)
		if it["y"] > area_bottom:
			it["y"] = area_top
			it["x"] = randf_range(area_left, area_right)
	queue_redraw()


func _draw() -> void:
	for it in _items:
		var sway: float = sin(_t * it["sway_f"] * 2.0 + it["sway_ph"]) * SWAY
		var x := roundf(it["x"] + sway)
		var y := roundf(it["y"])
		var sz: int = it["size"]

		match str(it["k"]):
			"petal":
				# 花瓣：2~3 px 的小点，偶尔变暗模拟翻转
				var flip: bool = int(_t * 3.0 + it["sway_ph"]) % 2 == 0
				var c := C_PETAL if flip else C_PETAL_DK
				var w2: float = float(sz)
				var h2: float = float(maxi(1, sz - 1))
				# **不描边**：花瓣只有 2~3px，外扩 1px 深色会让
				# 描边面积超过本体 —— 实测看起来是一个个黑色小方块，
				# 完全不像花瓣。这种尺寸靠自身明度区分就够了。
				draw_rect(Rect2(x, y, w2, h2), c)
			"leaf":
				# 落叶：斜线状。同样不描边（只有 1~2px 宽）
				var flip2: bool = int(_t * 2.2 + it["sway_ph"]) % 2 == 0
				var c2 := C_LEAF if flip2 else C_LEAF_DK
				if flip2:
					draw_rect(Rect2(x, y, sz + 1, 1), c2)
					draw_rect(Rect2(x + 1, y + 1, sz, 1), c2)
				else:
					draw_rect(Rect2(x, y, 1, sz + 1), c2)
			"dust":
				# 尘絮：1px 亮点的呼吸
				var a := 0.45 + 0.35 * sin(_t * 2.4 + it["sway_ph"])
				draw_rect(Rect2(x, y, 1, 1),
						  Color(C_DUST.r, C_DUST.g, C_DUST.b, a))


func item_count() -> int:
	return _items.size()


## 供测试：验证花瓣真的在动
func sample_positions() -> Array:
	var out: Array = []
	for it in _items:
		out.append(Vector2(it["x"], it["y"]))
	return out
