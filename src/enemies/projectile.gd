"""弹幕：BOSS 发射的投射物，可被玩家弹反打回去。

## 设计要点

1. **可弹反标记** —— 不是所有弹幕都能弹（有些是"红弹"必须闪避）。
   这里用两种颜色区分：
     · 青色弹（可弹反）：玩家挥剑能打回去，打回去的弹幕对 BOSS 造成伤害
     · 红色弹（不可弹）：只能闪避
   BOSS 第二阶段起会混着放，逼玩家分辨。

2. **打回去的弹幕要能伤到 BOSS** —— 这是弹反的价值所在。
   实现上用 `reflected` 标志切换 collision_mask。

3. **像素风格** —— 不用圆形渐变，用硬边圆 + 1px 描边 + 核心亮点。
"""

extends Area2D
## 弹幕。由 BOSS/敌人 spawn，飞向玩家。

signal hit_player
signal hit_boss(damage: int)

const GROUP_PROJECTILE := "projectile"

# 视觉
const R_OUTER := Color("#12142A")     # 描边
const R_CORE := Color("#B9F2FF")      # 可弹反弹的芯（青）
const R_EDGE := Color("#8FD3E8")
const RED_CORE := Color("#FF5A6E")    # 不可弹弹的芯（红）
const RED_EDGE := Color("#C2456A")

@export var speed := 130.0
@export var damage := 1
@export var reflectable := true        # 玩家能否弹反
@export var radius := 5.0
@export var lifetime := 4.0

var direction := Vector2.RIGHT
var _reflected := false                # 已被弹反
var _reflected_damage := 0
var _age := 0.0
var _trail: Array[Vector2] = []        # 拖尾位置（世界坐标）
var _pulse := 0.0

var _shape: CollisionShape2D
var _sprite: Node2D = null


func _ready() -> void:
	add_to_group(GROUP_PROJECTILE)
	collision_layer = 1 << 6            # 第7层：弹幕
	# 未弹反时检测玩家（第2层）；弹反后切到检测敌人（第3层）
	collision_mask = (1 << 1) if not _reflected else (1 << 2)

	_shape = CollisionShape2D.new()
	var circle := CircleShape2D.new()
	circle.radius = radius
	_shape.shape = circle
	add_child(_shape)

	# 碰撞检测用 area（不参与物理推挤）
	var body := Area2D.new()
	body.name = "HitArea"
	body.collision_layer = collision_layer
	body.collision_mask = collision_mask
	var cs := CollisionShape2D.new()
	var c2 := CircleShape2D.new()
	c2.radius = radius
	cs.shape = c2
	body.add_child(cs)
	body.area_entered.connect(_on_area_entered)
	body.body_entered.connect(_on_body_entered)
	add_child(body)

	z_index = 40
	set_process(true)


func spawn(pos: Vector2, dir: Vector2, opts: Dictionary = {}) -> void:
	global_position = pos
	direction = dir.normalized()
	for k in opts:
		set(k, opts[k])
	# 按参数调整视觉/碰撞
	collision_mask = (1 << 1) if not _reflected else (1 << 2)
	queue_redraw()
	# **主动扫一次**：如果出生点已经和目标重叠，
	# body_entered/area_entered 不会补发（Godot 只在"进入"瞬间发信号）。
	# 这和 AttackHitbox 踩的是同一个坑。
	_scan_initial_overlap()


func _scan_initial_overlap() -> void:
	await get_tree().physics_frame
	if not is_inside_tree():
		return
	var body := get_node_or_null("HitArea")
	if body == null:
		return
	for b in body.get_overlapping_bodies():
		_handle_hit(b)
		if not is_inside_tree():
			return
	for a in body.get_overlapping_areas():
		_handle_hit(a)
		if not is_inside_tree():
			return


func reflect() -> void:
	"""被玩家弹反：反向飞行，改为伤害敌人。"""
	if _reflected or not reflectable:
		return
	_reflected = true
	direction = -direction
	_reflected_damage = damage * 2          # 弹反双倍伤害（原设计如此）
	speed *= 1.6                            # 反弹回去更快
	_clear_trail()
	# 切换检测目标：从现在只认敌人
	collision_mask = 1 << 2
	var body := get_node_or_null("HitArea")
	if body:
		body.collision_mask = collision_mask
	queue_redraw()


func is_reflected() -> bool:
	return _reflected


func _process(delta: float) -> void:
	_age += delta
	if _age > lifetime:
		queue_free()
		return

	# 拖尾采样
	_trail.append(global_position)
	if _trail.size() > 6:
		_trail.pop_front()

	global_position += direction * speed * delta
	_pulse += delta * 12.0
	queue_redraw()


func _on_area_entered(area: Area2D) -> void:
	_handle_hit(area)


func _on_body_entered(body: Node2D) -> void:
	_handle_hit(body)


func _handle_hit(target: Node) -> void:
	if _reflected:
		# 弹反后只伤敌人
		if target.is_in_group("enemy") and target.has_method("take_hit"):
			target.take_hit(_reflected_damage, global_position.x)
			hit_boss.emit(_reflected_damage)
			queue_free()
		return

	# 未弹反：只伤玩家
	if target.has_method("take_damage"):
		# **可弹反的弹幕在击中前先问一次玩家要不要弹反**。
		#
		# 为什么需要这一步：弹幕的 HitArea 和玩家的攻击判定框都是 Area2D，
		# 谁先响应取决于物理帧处理顺序 —— 实测弹幕总是先撞上玩家身体
		# 然后 queue_free()，玩家的判定框根本没机会碰到它，
		# 弹反永远失败。这里在真正结算伤害前主动给玩家一次机会。
		if reflectable and not _reflected:
			var player := _find_player()
			if player != null and player.has_method("try_parry_incoming"):
				if player.call("try_parry_incoming", self):
					return          # 已被弹反，弹幕不再消失
		target.take_damage(damage, global_position.x)
		hit_player.emit()
		queue_free()


func _find_player() -> Node:
	for p in get_tree().get_nodes_in_group("player"):
		return p
	return null


func _clear_trail() -> void:
	_trail.clear()


func _draw() -> void:
	# 拖尾：逐渐变淡的小点（像素风用方块而不是圆）
	var n := _trail.size()
	for i in n:
		var t := float(i) / maxf(1.0, float(n))
		var p := _trail[i] - global_position
		var a := int(90 * t)
		if a <= 4:
			continue
		var col := (R_CORE if reflectable else RED_CORE)
		draw_rect(Rect2(p.x - 1, p.y - 1, 2, 2),
				  Color(col.r, col.g, col.b, a / 255.0))

	# 本体：硬边圆 + 描边
	var r := radius + (1.0 if sin(_pulse) > 0.6 else 0.0)
	var core := R_CORE if reflectable else RED_CORE
	var edge := R_EDGE if reflectable else RED_EDGE
	if _reflected:
		# 弹反后变金色，和敌弹明显区分
		core = Color("#FFE9A8")
		edge = Color("#FFC46B")

	draw_circle(Vector2.ZERO, r + 1.0, R_OUTER)
	draw_circle(Vector2.ZERO, r, edge)
	draw_circle(Vector2.ZERO, maxf(1.0, r - 2.0), core)
