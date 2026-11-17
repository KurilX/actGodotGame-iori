extends Node2D
## 落地阴影：贴在角色脚下的椭圆，随离地高度淡出并收缩
##
## 为什么需要：像素角色仅靠"脚底与地面边缘对齐"眼睛判不出接触，
## 会看成悬浮。阴影提供接触点，是最便宜有效的解法。
##
## 用法：作为 Player 的子节点，脚本自己在 _physics_process 里
##       向下做射线检测地面，据此调整位置、缩放与透明度。

const MAX_DIST := 56.0        # 超过这个离地高度完全不可见
const MIN_SCALE := 0.45       # 最高处缩到原尺寸的比例
const MIN_ALPHA := 0.0
const BASE_ALPHA := 0.34      # 贴地时的不透明度（太高会糊住地面）

@export var radius_scale := 1.0

var _base_w := 14.0           # 略窄于角色（角色宽 20px），避免溢出到草皮外
var _base_h := 4.0

var _owner_body: CharacterBody2D


func _ready() -> void:
	_owner_body = get_parent() as CharacterBody2D
	# 层级：背景 -10 / 远景 -5 / 地形 -1 / 草皮顶 0 / 阴影 1 / 角色 2
	# 阴影必须在草皮顶(0)之上，否则被地形挡住看不见
	z_index = 1
	texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	queue_redraw()


func _physics_process(_delta: float) -> void:
	if _owner_body == null:
		return
	_update_shadow()


func _update_shadow() -> void:
	var space := get_world_2d().direct_space_state
	var from := _owner_body.global_position
	var to := from + Vector2(0, MAX_DIST)

	var q := PhysicsRayQueryParameters2D.create(from, to, 1)
	var hit := space.intersect_ray(q)

	if hit.is_empty():
		visible = false
		return

	visible = true
	var ground_y: float = hit.position.y
	var dist: float = maxf(ground_y - from.y, 0.0)

	# 阴影落在地面顶部
	global_position = Vector2(from.x, ground_y)

	var t := clampf(dist / MAX_DIST, 0.0, 1.0)
	var s := lerpf(1.0, MIN_SCALE, t)
	scale = Vector2(s * radius_scale, 1.0)
	modulate.a = lerpf(BASE_ALPHA, MIN_ALPHA, t)


func _draw() -> void:
	# 扁椭圆：半透明深色，贴地一圈
	# 色板 #12142A，用 modulate.a 控制强度
	var w := _base_w
	var h := _base_h
	var pts := PackedVector2Array()
	var n := 16
	for i in n:
		var a := TAU * float(i) / float(n)
		pts.append(Vector2(cos(a) * w * 0.5, sin(a) * h * 0.5))
	draw_colored_polygon(pts, Color("#12142A"))
