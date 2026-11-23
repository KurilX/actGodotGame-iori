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

# ── 远程招式（可选）──
#
# **为什么杂兵也要有远程**：弹反是玩家常驻技能，但原来全游戏只有 BOSS
# 发射弹幕，导致玩家在 1560px 的教程关和所有杂兵战里根本见不到可弹的东西，
# 弹反实际变成了"BOSS 二阶段专属机制"。给杂兵加远程后，弹反贯穿全程。
#
# 每个敌人用数据配置自己的远程：
#   ranged_enabled   是否启用
#   ranged_cooldown  远程冷却（比近战长，避免刷屏）
#   ranged_speed     弹速
#   ranged_damage    伤害
#   ranged_radius    弹体大小
#   ranged_color     颜色（用可弹反的青色系）
@export var ranged_enabled := false
@export var ranged_cooldown := 2.6
@export var ranged_speed := 110.0
@export var ranged_damage := 1
@export var ranged_radius := 4.0
@export var ranged_windup := 0.45     # 远程前摇（比近战长，给玩家反应时间）
@export var ranged_min_dist := 70.0   # 就近战太近时改用近战
@export var ranged_max_dist := 260.0  # 超出这个距离不发射

const ProjectileR := preload("res://src/enemies/projectile.gd")

var _ranged_cd := 0.0                 # 远程冷却计时
var _ranged_windup_left := 0.0        # 远程前摇剩余
var _ranged_pending := false          # 前摇结束要发射

signal ranged_fired

var hp := 10
var state: State = State.IDLE
var facing := -1

var _timer := 0.0
var _cooldown := 0.0
const FLASH_DURATION := 0.14   # 受击染色持续时间

var _flash := 0.0
var _hurt_duration := 0.12     # 本次硬直的初始时长（用于把 hurt 动画映射到硬直时间段）
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
		["hurt", 3, 12.0],
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
	_tick_ranged(delta)
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
	_sync_hit_tint()


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


# ─────────────── 远程招式 ───────────────

func _tick_ranged(delta: float) -> void:
	if not ranged_enabled:
		return
	_ranged_cd = maxf(_ranged_cd - delta, 0.0)

	# 前摇中：到点就发射
	if _ranged_pending:
		_ranged_windup_left -= delta
		if _ranged_windup_left <= 0.0:
			_ranged_pending = false
			_fire_projectile()
		return

	# **不受 state 限制**：远程的作用就是"在近战够不到的地方施加压力"。
	# 之前只在 CHASE 里触发，结果敌人 detect_range(120) 小于射程(240)，
	# 玩家站在 140 距离时敌人既不动也不开枪 —— 远程形同虚设（实测）。
	# 现在只要不在受击/死亡/前摇中就允许开火。
	if state == State.HURT or state == State.DEAD:
		return
	if state == State.WINDUP or state == State.ATTACK:
		return
	if _ranged_cd > 0.0:
		return
	var player := _find_player()
	if player == null:
		return
	var d := _distance_to_player()
	if d < ranged_min_dist or d > ranged_max_dist:
		return
	# 进入前摇：站住蓄力，给玩家反应时间
	_begin_ranged_windup()


func _begin_ranged_windup() -> void:
	_ranged_pending = true
	_ranged_windup_left = ranged_windup
	velocity.x = 0.0
	if _anim and _anim.sprite_frames.has_animation("attack"):
		_anim.play("attack")
		_anim.frame = 0
		_anim.pause()


func _fire_projectile() -> void:
	var player := _find_player()
	if player == null:
		_cancel_ranged()
		return
	# 瞄准玩家躯干中心。
	# 玩家 global_position 是脚底，躯干大约在 -30 处（身高 48，碰撞盒中心 -20）。
	# 之前瞄 -14 太靠脚，弹幕会从判定框下方擦过去（实测打不中）。
	var origin := global_position + Vector2(0, -18)
	var aim := player.global_position + Vector2(0, -30)
	var dir := (aim - origin).normalized()

	var p := Area2D.new()
	p.set_script(ProjectileR)
	get_parent().add_child(p)
	p.spawn(origin, dir, {
		"speed": ranged_speed,
		"damage": ranged_damage,
		"radius": ranged_radius,
		"reflectable": true,
		"lifetime": 3.2,
	})
	_ranged_cd = ranged_cooldown
	# 发射时面向玩家
	if player.global_position.x != global_position.x:
		facing = 1 if player.global_position.x > global_position.x else -1
	ranged_fired.emit()


func _cancel_ranged() -> void:
	_ranged_pending = false
	_ranged_windup_left = 0.0


func is_ranged_winding() -> bool:
	return _ranged_pending


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
		# 退出硬直时恢复播放，否则会停在被 pause 的 hurt 最后一帧
		if _anim:
			_anim.play("idle")


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
	_flash = FLASH_DURATION

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
			_hurt_duration = 0.25 if heavy else 0.12
			_timer = _hurt_duration
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

	# 硬直：播 hurt 动画并按剩余时间推进帧。
	# 早期版本没处理 HURT，受击时敌人还在播 idle/run，
	# 看起来像「没被打到」——这是打击感缺失的主因之一。
	if state == State.HURT:
		if _anim.sprite_frames.has_animation("hurt"):
			if _anim.animation != "hurt":
				_anim.play("hurt")
				_anim.frame = 0
			# 3 帧按剩余硬直时间映射，保证硬直结束时刚好播完
			var dur := _hurt_duration
			var p := 1.0 - clampf(_timer / maxf(dur, 0.01), 0.0, 1.0)
			_anim.frame = clampi(int(p * 3.0), 0, 2)
			_anim.pause()
		return

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


func _sync_hit_tint() -> void:
	"""受击染色：把整个精灵染红，而不是在旁边画一个矩形。

	为什么不用 draw_rect：
	  早期是在身体位置画半透明白矩形，问题有两个 ——
	  ① 矩形是方的，会盖住比身形更大的区域（尤其飞行单位）；
	  ② 白色闪一下在夜景里辨识度低，看着像"亮了一下"而不是"被打中"。

	改用 modulate 乘算：红色 (2.2, 0.45, 0.45) 乘上原色，
	整体偏红且压暗，像素轮廓完全保留（不改变形状，只改颜色），
	是像素游戏表现受击的通行做法。
	"""
	if _anim == null:
		return
	if _flash > 0.0:
		var t := _flash / FLASH_DURATION          # 1.0 → 0.0
		# 起始最红，随后快速回落。
		#
		# **踩过的坑**：一开始用 R 增益（>1.0）+ G/B 压暗的乘算，
		# 绿色敌人被乘成了黄褐色（绿 × 红 = 黄），看着像中毒不像受击。
		# 乘算没法把色相真正推向红色，只能调整亮度比。
		#
		# 正确做法：用「自照明」思路 —— 让精灵本身发出的光偏红。
		# 在 CanvasItem 上开自调制（self_modulate 之外）不改变原色相，
		# 而是叠加一个红色发光层：把 modulate 的 R 保持高水平、
		# G/B 压到接近 0，同时**大幅提高亮度**，让暗部也被红光照亮。
		# 这样原本的绿色只剩极弱的痕迹，整体读起来是"红了的敌人"。
		var k := t ** 0.7
		_anim.modulate = Color(
			1.0 + 2.6 * k,      # R 强增益：让红色占绝对主导
			1.0 - 0.94 * k,     # G 几乎归零：抹掉绿色
			1.0 - 0.90 * k      # B 几乎归零
		)
	else:
		_anim.modulate = Color(1, 1, 1, 1)
