extends Node2D
## 训练木桩：用来验证攻击连段与命中判定
##
## 属于「可受击目标」组，受击后闪白 + 后退 + 顶部飘伤害数字。
## 血量归零后延迟复活，方便反复测试。

signal died

const GROUP_HURTABLE := "hurtable"

@export var max_hp := 30
@export var respawn_delay := 1.2

var hp := 30
var _flash := 0.0
var _knock := Vector2.ZERO
var _dead_timer := 0.0

var _body_rect := Rect2(-7, -30, 14, 30)   # 木桩本体（相对节点原点，原点在脚底）


func _ready() -> void:
	add_to_group(GROUP_HURTABLE)
	hp = max_hp
	# 碰撞体：木桩本体用 Area2D，放在第 4 层（bit3），
	# 玩家的 AttackHitbox 的 mask 也是 bit3，两者才能互相检测
	var area := Area2D.new()
	area.collision_layer = 1 << 3
	area.collision_mask = 0
	var cs := CollisionShape2D.new()
	var rect := RectangleShape2D.new()
	rect.size = _body_rect.size
	cs.shape = rect
	cs.position = Vector2(_body_rect.position.x + _body_rect.size.x * 0.5,
	                      _body_rect.position.y + _body_rect.size.y * 0.5)
	area.add_child(cs)
	area.add_to_group(GROUP_HURTABLE)
	add_child(area)
	queue_redraw()


func take_hit(damage: int, from_x: float) -> void:
	if hp <= 0:
		return
	hp -= damage
	_flash = 0.12
	# 击退方向：从攻击者指向自己
	var dir := signf(global_position.x - from_x)
	if dir == 0.0:
		dir = 1.0
	_knock = Vector2(dir * 6.0, 0.0)
	if hp <= 0:
		hp = 0
		_dead_timer = respawn_delay
		died.emit()
	queue_redraw()


func get_hp() -> int:
	return hp


func is_alive() -> bool:
	return hp > 0


func _process(delta: float) -> void:
	if _flash > 0.0:
		_flash -= delta
		queue_redraw()
	if _knock.length() > 0.01:
		position += _knock * delta * 8.0
		_knock = _knock.move_toward(Vector2.ZERO, delta * 40.0)

	if _dead_timer > 0.0:
		_dead_timer -= delta
		if _dead_timer <= 0.0:
			hp = max_hp
			queue_redraw()


func _draw() -> void:
	if hp <= 0:
		# 倒下：一截残桩 + 石座上的碎木
		draw_rect(Rect2(-7, -6, 14, 6), Color("#394051"))
		draw_rect(Rect2(-9, -2, 18, 4), Color("#45283C"))
		return

	var base := Color("#5A6478")
	var lit := Color("#7B8699")
	var ink := Color("#12142A")
	var wood := Color("#7A6A58")        # 木身（palette.e 的土亮档）
	var wood_dk := Color("#5A4C40")     # 木暗（缠绳/阴影）
	var rope := Color("#E0913F")        # 绑绳（灯笼暗档，暖色点缀）

	if _flash > 0.0:
		base = Color("#FFFFFF")
		lit = Color("#FFFFFF")
		wood = Color("#FFFFFF")

	# ── 石座（和地形同材质的 stone 档，1px 描边）──
	# 之前木桩直接插在草地上，"孤立悬贴"的观感一半来自没有承重结构。
	draw_rect(Rect2(-11, -8, 22, 8), base)
	draw_rect(Rect2(-11, -8, 22, 2), lit)          # 座顶受光
	draw_rect(Rect2(-11, -8, 22, 8), ink, false, 1.0)
	draw_rect(Rect2(-11, -1, 22, 1), ink)          # 座底落地阴影

	# ── 木桩身（木纹竖条 + 缠绳）──
	draw_rect(Rect2(-7, -34, 14, 26), wood)
	draw_rect(Rect2(-7, -34, 3, 26), lit)          # 左上高光（光源锁死左上）
	# 木纹：两根竖暗线
	draw_rect(Rect2(-2, -34, 1, 26), wood_dk)
	draw_rect(Rect2(3, -34, 1, 26), wood_dk)
	# 缠绳：上下两圈（草垫的绑法）
	draw_rect(Rect2(-7, -32, 14, 2), rope)
	draw_rect(Rect2(-7, -14, 14, 2), rope)
	# 顶盖：石帽压住木桩
	draw_rect(Rect2(-9, -38, 18, 4), base)
	draw_rect(Rect2(-9, -38, 18, 1), lit)
	# 描边
	draw_rect(Rect2(-7, -34, 14, 26), ink, false, 1.0)
	draw_rect(Rect2(-9, -38, 18, 4), ink, false, 1.0)

	# 血量条（顶部 2px）
	var w := 18.0
	var ratio := float(hp) / float(max_hp)
	draw_rect(Rect2(-9, -43, w, 2), Color("#12142A"))
	draw_rect(Rect2(-9, -43, w * ratio, 2), Color("#FF7A9C") if ratio < 0.4 else Color("#FFE9A8"))
