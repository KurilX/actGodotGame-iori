extends Area2D
## 攻击判定框：挂在玩家身上，随攻击帧启停
##
## 设计要点（和《結ノ町》踩过的坑对齐）：
##   预警范围必须与判定范围严格一致，否则会出现「特效糊脸却没伤害」。
##   所以判定框用可见的 CollisionShape2D，调试时能画出来看。

signal hit_landed(target: Node, damage: int, from_x: float)

const GROUP_HURTABLE := "hurtable"

var damage := 1
var active := false

@onready var _shape: CollisionShape2D = $CollisionShape2D


func _ready() -> void:
	# 只在攻击帧启用，平时完全关闭
	monitoring = false
	monitorable = false
	collision_layer = 0
	collision_mask = 1 << 3        # 只检测第 4 层（敌人/木桩）
	area_entered.connect(_on_area_entered)
	body_entered.connect(_on_body_entered)


func set_active(on: bool) -> void:
	var was := active
	active = on
	monitoring = on
	$CollisionShape2D.disabled = not on
	# 开启的瞬间就与目标重叠时，area_entered 不会补发（Godot 只在实际「进入」时发信号）。
	# 所以开启后主动扫一次已重叠目标，否则贴身攻击会完全打空。
	if on and not was:
		_scan_overlaps()


func _scan_overlaps() -> void:
	# 延迟一帧，等物理引擎刷新重叠列表
	await get_tree().physics_frame
	if not active:
		return
	for a in get_overlapping_areas():
		if a.is_in_group(GROUP_HURTABLE):
			_emit(a)
	for b in get_overlapping_bodies():
		if b.is_in_group(GROUP_HURTABLE):
			_emit(b)


func set_reach(width: float, height: float, offset_x: float, offset_y: float) -> void:
	var rect := _shape.shape as RectangleShape2D
	if rect == null:
		rect = RectangleShape2D.new()
		_shape.shape = rect
	rect.size = Vector2(width, height)
	_shape.position = Vector2(offset_x, offset_y)


func _on_area_entered(area: Area2D) -> void:
	if not active:
		return
	if area.is_in_group(GROUP_HURTABLE):
		_emit(area)


func _on_body_entered(body: Node2D) -> void:
	if not active:
		return
	if body.is_in_group(GROUP_HURTABLE):
		_emit(body)


func _emit(target: Node) -> void:
	# 命中的可能不是「可受击实体」本身，而是它的碰撞子节点
	# （比如木桩把 Area2D 作为子节点挂在自己身上）。
	# 所以要向上找到真正带受击方法的节点，否则信号发出去了也会被静默丢弃。
	var real := _resolve_hurtable(target)
	if real == null:
		return
	hit_landed.emit(real, damage, global_position.x)


func _resolve_hurtable(node: Node) -> Node:
	var cur := node
	while cur != null:
		if cur.has_method("take_hit") or cur.has_method("take_damage"):
			return cur
		cur = cur.get_parent()
	return null
