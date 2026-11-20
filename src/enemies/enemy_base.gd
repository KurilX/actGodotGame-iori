extends CharacterBody2D
## 敌人基类：三个敌人共用的移动、受击、状态机、攻击判定
##
## 设计原则
## ────────
## 1. **敌人也要有「前摇」**：攻击前有明显准备动作，玩家能读出来并闪避。
##    没有前摇的敌人只能靠背板，那是很差的动作游戏设计。
## 2. **受击要能被打断**：轻攻击不打断，重攻击打断（这就是「重」的价值）。
## 3. 死亡后播放一次倒地，然后消失并通知房间。

signal died(enemy: Node)

const GROUP_HURTABLE := "hurtable"
const GROUP_ENEMY := "enemy"

enum State { IDLE, CHASE, WINDUP, ATTACK, HURT, DEAD }

# ── 子类需要覆盖的参数 ──
@export var max_hp := 10
@export var move_speed := 40.0
@export var detect_range := 120.0     # 发现玩家的距离
@export var attack_range := 26.0      # 进入攻击的距离
@export var attack_cooldown := 1.2
@export var windup_time := 0.35       # 攻击前摇
@export var attack_time := 0.30       # 挥出持续
@export var recover_time := 0.35      # 收招
@export var damage := 1
@export var knockback_resist := 1.0
@export var can_fly := false
@export var attack_box := Vector4(26, 22, 14, -20)   # w,h,offset_x,offset_y
@export var heavy_breaks := true      # 重攻击能否打断其动作
@export var sprite_name := ""         # art/enemies/frames/ 下的前缀

var hp := 10
var state: State = State.IDLE
var facing := -1

var _timer := 0.0
var _cooldown := 0.0
var _flash := 0.0
var _player: Node2D = null
var _anim: AnimatedSprite2D
var _hitbox_already_hit := false

# 索敌用的射线（避免穿墙追人）
var _ray := RayCast2D.new()


func _ready() -> void:
	add_to_group(GROUP_ENEMY)
	add_to_group(GROUP_HURTABLE)
	hp = max_hp
	collision_layer = 1 << 2       # 第3层：敌人本体
	collision_mask = 1             # 与地形碰撞
	_build_visual()
	_build_hitbox()
	queue_redraw()


# ─────────────── 子类可覆盖的钩子 ───────────────

func _build_visual() -> void:
	"""创建 AnimatedSprite2D 并加载该敌人的帧。"""
	_anim = AnimatedSprite2D.new()
	_anim.name = "Anim"
	_anim.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	_anim.position = Vector2(0, -24)     # 帧高 48、锚点帧底中心
	_anim.sprite_frames = _make_frames()
	_anim.play("idle")
	add_child(_anim)


func _make_frames() -> SpriteFrames:
	var sf := SpriteFrames.new()
	sf.remove_animation("default")
	var specs := [
		["idle", 4, 6.0],
		["run", 8, 10.0],
		["attack", 8, 10.0],
	]
	for spec in specs:
		var aname: String = spec[0]
		var count: int = spec[1]
		var fps: float = spec[2]
		sf.add_animation(aname)
		sf.set_animation_speed(aname, fps)
		sf.set_animation_loop(aname, aname != "attack")
		for i in count:
			var path := "res://art/enemies/frames/%s_%s_%d.png" % [sprite_name, aname, i]
			if ResourceLoader.exists(path):
				sf.add_frame(aname, load(path))
	return sf


func _build_hitbox() -> void:
	"""敌人自己的攻击判定框（打玩家用）。"""
	var area := Area2D.new()
	area.name = "AttackBox"
	area.collision_layer = 1 << 4     # 第5层：敌人攻击
	area.collision_mask = 1 << 1      # 检测玩家所在层（player collision_layer=2 → bit1）
	area.monitoring = false
	var cs := CollisionShape2D.new()
	# **必须显式命名**：不命名时 Godot 会给自动名（如 @CollisionShape2D@23），
	# 后续 get_node("CollisionShape2D") 就取不到，导致判定框永远打不中。
	cs.name = "CollisionShape2D"
	var rect := RectangleShape2D.new()
	rect.size = Vector2(attack_box.x, attack_box.y)
	cs.shape = rect
	cs.position = Vector2(attack_box.z, attack_box.w)
	cs.disabled = true
	area.add_child(cs)
	area.body_entered.connect(_on_attack_area_body_entered)
	add_child(area)


# ─────────────── 主循环 ───────────────

func _physics_process(delta: float) -> void:
	_tick(delta)
	if state == State.DEAD:
		return

	_player = _find_player()

	match state:
		State.IDLE:
			_do_idle(delta)
		State.CHASE:
			_do_chase(delta)
		State.WINDUP:
			_do_windup(delta)
		State.ATTACK:
			_do_attack(delta)
		State.HURT:
			_do_hurt(delta)

	_apply_gravity(delta)
	move_and_slide()
	_sync_anim()


func _tick(delta: float) -> void:
	_cooldown = maxf(_cooldown - delta, 0.0)
	_flash = maxf(_flash - delta, 0.0)
	if _timer > 0.0:
		_timer -= delta


func _apply_gravity(delta: float) -> void:
	if can_fly:
		# 飞行单位：保持高度，不做重力（高度由子类的悬停逻辑控制）
		velocity.y = move_toward(velocity.y, 0.0, 600.0 * delta)
	else:
		if not is_on_floor():
			velocity.y = minf(velocity.y + 1200.0 * delta, 600.0)


func _do_idle(delta: float) -> void:
	velocity.x = move_toward(velocity.x, 0.0, 400.0 * delta)
	if _player and _distance_to_player() < detect_range:
		state = State.CHASE


func _do_chase(delta: float) -> void:
	if _player == null:
		state = State.IDLE
		return

	var d := _distance_to_player()
	if d > detect_range * 1.4:
		state = State.IDLE
		return

	if d <= attack_range and _cooldown <= 0.0:
		_enter_windup()
		return

	# 朝玩家移动
	var dir := signf(_player.global_position.x - global_position.x)
	if dir != 0.0:
		facing = 1 if dir > 0.0 else -1
		velocity.x = move_toward(velocity.x, dir * move_speed, 600.0 * delta)
	else:
		velocity.x = move_toward(velocity.x, 0.0, 400.0 * delta)


func _enter_windup() -> void:
	state = State.WINDUP
	_timer = windup_time
	velocity.x = 0.0
	if _anim and _anim.sprite_frames.has_animation("attack"):
		_anim.play("attack")
		_anim.frame = 0
		_anim.pause()


func _do_windup(delta: float) -> void:
	velocity.x = move_toward(velocity.x, 0.0, 800.0 * delta)
	# 前摇期间显示攻击动画的前段（看得见的蓄力）
	if _anim and _anim.sprite_frames.has_animation("attack"):
		var total := windup_time + attack_time + recover_time
		var p := 1.0 - (_timer / total)
		_anim.frame = clampi(int(p * 8.0), 0, 3)
	if _timer <= 0.0:
		state = State.ATTACK
		_timer = attack_time
		_hitbox_already_hit = false
		_set_attack_box(true)


func _do_attack(delta: float) -> void:
	# 攻击期间带一点前冲
	velocity.x = facing * 30.0 * delta * 20.0
	if _anim and _anim.sprite_frames.has_animation("attack"):
		var total := windup_time + attack_time + recover_time
		var p := 1.0 - (_timer / total)
		_anim.frame = clampi(int(p * 8.0), 3, 6)
	if _timer <= 0.0:
		_set_attack_box(false)
		state = State.CHASE
		_cooldown = attack_cooldown
		_timer = recover_time


func _do_hurt(delta: float) -> void:
	velocity.x = move_toward(velocity.x, 0.0, 500.0 * delta)
	if _timer <= 0.0:
		state = State.CHASE


func _set_attack_box(on: bool) -> void:
	var area := get_node_or_null("AttackBox")
	if area == null:
		return
	area.monitoring = on
	var cs := area.get_node_or_null("CollisionShape2D")
	if cs:
		cs.disabled = not on
		# **判定框必须跟着 facing 翻转**。
		# 早期写死 offset 正数，敌人朝左攻击时判定框仍然伸向右侧，
		# 结果永远打不中玩家（实测 overlaps 恒为 0）。
		cs.position = Vector2(attack_box.z * facing, attack_box.w)
	if on:
		# 立即扫一次重叠（与玩家 AttackHitbox 同样的坑：
		# 开启瞬间就重叠时 area_entered 不会补发）
		_scan_attack_overlaps(area)


func _scan_attack_overlaps(area: Area2D) -> void:
	await get_tree().physics_frame
	if not area.monitoring:
		return
	for b in area.get_overlapping_bodies():
		_damage_player(b)


func _on_attack_area_body_entered(body: Node2D) -> void:
	_damage_player(body)


func _damage_player(body: Node) -> void:
	if _hitbox_already_hit:
		return
	if not body.has_method("take_damage"):
		return
	# 玩家闪避无敌由 player.take_damage 内部判断，这里不做额外检查
	body.take_damage(damage, global_position.x)
	_hitbox_already_hit = true


# ─────────────── 受击 ───────────────

func take_hit(amount: int, from_x: float) -> void:
	if state == State.DEAD:
		return
	hp -= amount
	_flash = 0.14

	# 被击退
	var dir := signf(global_position.x - from_x)
	if dir == 0.0:
		dir = 1.0
	velocity.x = dir * 90.0 / maxf(knockback_resist, 0.1)

	# 受击打断：重攻击（伤害 >= 4）可以打断敌人的前摇与攻击
	var heavy := amount >= 4
	if heavy or state in [State.IDLE, State.CHASE]:
		if state != State.DEAD:
			state = State.HURT
			_timer = 0.25 if heavy else 0.12
			_set_attack_box(false)

	if hp <= 0:
		hp = 0
		_die()
	queue_redraw()


func _die() -> void:
	state = State.DEAD
	_set_attack_box(false)
	velocity = Vector2.ZERO
	if _anim:
		_anim.pause()
		_anim.modulate = Color(1, 1, 1, 1)
	remove_from_group(GROUP_HURTABLE)
	remove_from_group(GROUP_ENEMY)
	# 淡出后移除
	var tw := create_tween()
	tw.tween_property(self, "modulate:a", 0.0, 0.35)
	tw.tween_callback(func():
		died.emit(self)
		queue_free())


# ─────────────── 工具 ───────────────

func _find_player() -> Node2D:
	var ps := get_tree().get_nodes_in_group("player")
	return ps[0] if ps.size() > 0 else null


func _distance_to_player() -> float:
	if _player == null:
		return INF
	return global_position.distance_to(_player.global_position)


func _sync_anim() -> void:
	if _anim == null:
		return
	_anim.flip_h = facing > 0     # 素材朝向默认朝左

	if state == State.WINDUP or state == State.ATTACK:
		return          # 由 _do_windup/_do_attack 控制帧

	var aname := "idle"
	if state == State.CHASE and absf(velocity.x) > 4.0:
		aname = "run"
	if _anim.sprite_frames.has_animation(aname):
		if not _anim.is_playing() or _anim.animation != aname:
			_anim.play(aname)


func is_dead() -> bool:
	return state == State.DEAD


func get_hp() -> int:
	return hp


func _draw() -> void:
	# 受击闪白：在身体位置画一个半透明白色矩形
	if _flash > 0.0:
		var w := 20.0
		var h := 30.0
		draw_rect(Rect2(-w * 0.5, -h, w, h),
				  Color(1, 1, 1, 0.35 * (_flash / 0.14)))
		queue_redraw()
