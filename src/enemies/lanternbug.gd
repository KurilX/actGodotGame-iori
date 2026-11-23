extends "res://src/enemies/enemy_base.gd"
## 灯笼虫（lanternbug）：飞行单位
##
## 定位：迫使玩家抬头/跳跃对付它。血少但会保持距离，不主动贴身。
## 行为：悬浮 → 在玩家上方左右游走 → 靠近后俯冲攻击 → 退回。
##
## 与地面敌人的关键区别：不受重力，且攻击后有后撤，
## 所以玩家不能靠"站着等它撞过来"，得主动追。

var _hover_base_y := 0.0
var _hover_phase := 0.0
var _retreat := 0.0


func _ready() -> void:
	max_hp = 9                  # 血最薄
	move_speed = 46.0           # 但最灵活
	detect_range = 280.0
	attack_range = 34.0
	attack_cooldown = 1.6
	windup_time = 0.38
	attack_time = 0.22
	recover_time = 0.45         # 收招长，攻击后有明显空隙
	damage = 1
	knockback_resist = 0.6      # 最容易被击飞
	can_fly = true

	# ── 远程：甩光球 ──
	# 定位：**空中骚扰**。它在天上，玩家够不到，只能用弹反处理。
	# 弹速最快（180）、弹体最小（3.5），但伤害低（1），
	# 冷却也较长（2.8s），因为它是唯一"打不到本体"的敌人，
	# 远程如果太频繁会让玩家很烦。
	ranged_enabled = true
	ranged_cooldown = 2.8
	ranged_speed = 180.0
	ranged_damage = 1
	ranged_radius = 3.5
	ranged_windup = 0.40
	ranged_min_dist = 100.0
	ranged_max_dist = 280.0
	attack_box = Vector4(24, 20, 14, -18)
	sprite_name = "lanternbug"
	super._ready()
	_hover_base_y = global_position.y
	_hover_phase = randf() * TAU


func _physics_process(delta: float) -> void:
	# 悬停：在基准高度上下浮动，攻击/受击时不浮动
	if state in [State.IDLE, State.CHASE] and not is_dead():
		_hover_phase += delta * 3.0
		var target_y := _hover_base_y + sin(_hover_phase) * 3.0
		global_position.y = move_toward(global_position.y, target_y, 60.0 * delta)
	super._physics_process(delta)


func _do_attack(delta: float) -> void:
	# 灯笼虫的攻击是俯冲：带明显的向下位移
	velocity = Vector2(facing * 20.0, 40.0)
	if _anim and _anim.sprite_frames.has_animation("attack"):
		var total := windup_time + attack_time + recover_time
		var p := 1.0 - (_timer / total)
		_anim.frame = clampi(int(p * 8.0), 3, 6)
	if _timer <= 0.0:
		_set_attack_box(false)
		state = State.CHASE
		_cooldown = attack_cooldown
		_timer = recover_time
		# 攻击后后撤，拉开距离
		_retreat = 0.35
		velocity.y = -60.0


func _do_chase(delta: float) -> void:
	if _retreat > 0.0:
		_retreat -= delta
		velocity.x = -facing * move_speed * 0.8
		return
	super._do_chase(delta)
