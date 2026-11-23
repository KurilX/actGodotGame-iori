extends "res://src/enemies/enemy_base.gd"
## BOSS「瓷面的守夜人」—— 三阶段，五技能。
##
## ## 技能设计原则
##
## 每个技能都必须**逼玩家用不同的应对手段**，否则就是换个特效的同一个技能：
##
##   | 技能     | 玩家正确应对      | 为什么                     |
##   |----------|-------------------|----------------------------|
##   | 冲锋     | 跳跃 or 闪避      | 贴地冲刺，打不到高处         |
##   | 砸地     | 远离 or 闪避      | 大范围，但前摇极长           |
##   | 弹幕     | **弹反** or 闪避  | 唯一能把伤害打回去的机会     |
##   | 瞬移斩   | 听脚步/看残影     | 强制玩家保持注意力           |
##   | 狂暴连击 | 纯粹闪避          | 第三阶段的压力测试           |
##
## ## 三阶段
##
##   一阶段（100%~66%）：只用冲锋、砸地。教会玩家读前摇。
##   二阶段（66%~33%）：加入弹幕。**红弹（不可弹）混在青弹里**，逼玩家分辨。
##   三阶段（33%~0%）：加入瞬移斩 + 狂暴连击，前摇缩短 30%。
##
## 阶段转换时有一次全屏冲击 + 短暂无敌，给玩家喘息。

const Projectile := preload("res://src/enemies/projectile.gd")

enum Skill { CHARGE, SLAM, VOLLEY, BLINK, FRENZY }

signal phase_changed(new_phase: int)
signal skill_started(skill: int)
signal boss_died

# ── 阶段阈值 ──
const PHASE_HP := [1.0, 0.66, 0.33]     # 各阶段开始时的血量比例

# ── 技能参数（三阶段的差异通过 _phase_speed() 缩放）──
const SKILL_CHARGE := {
	"windup": 0.55, "active": 0.45, "recover": 0.50,
	"damage": 2, "speed": 340.0,
}
const SKILL_SLAM := {
	"windup": 0.75, "active": 0.18, "recover": 0.65,
	"damage": 3, "radius": 78.0,
}
const SKILL_VOLLEY := {
	"windup": 0.60, "active": 0.10, "recover": 0.55,
	"count": 5, "spread": 34.0, "speed": 150.0, "damage": 1,
}
const SKILL_BLINK := {
	"windup": 0.42, "active": 0.16, "recover": 0.45,
	"damage": 2,
}
const SKILL_FRENZY := {
	"windup": 0.35, "active": 1.10, "recover": 0.50,
	"damage": 2, "hits": 4,
}

var phase := 1
var _skill_timer := 0.0
var _skill_stage := 0        # 0=windup 1=active 2=recover
var _current_skill: int = Skill.CHARGE
var _skill_seq: Array[int] = []
var _frenzy_hits := 0
var _frenzy_next := 0.0
var _invuln := 0.0
var _phase_transition := false


## 玩家进入 BOSS 房之前保持休眠：不移动、不攻击、不检测。
## 由 room_greybox 在玩家跨过 BOSS_ZONE_START 时调用 wake()。
var _dormant := true


func wake() -> void:
	_dormant = false


func is_dormant() -> bool:
	return _dormant


func _ready() -> void:
	max_hp = 120
	move_speed = 42.0
	# **不能是 999**：关卡扩成 2400px 后，BOSS 会从教程关就开始锁定玩家、
	# 一路冲出 BOSS 房追到教学段（实测），玩家还没学会走路就撞上 BOSS。
	# 改成"进入 BOSS 房才激活"：由 room 在玩家跨过 BOSS_ZONE_START 时唤醒。
	detect_range = 380.0        # 略大于 BOSS 房宽度，房内全程锁定
	attack_range = 62.0
	attack_cooldown = 1.1
	windup_time = 0.55
	attack_time = 0.35
	recover_time = 0.55
	damage = 2
	knockback_resist = 8.0      # 几乎推不动
	can_fly = false
	attack_box = Vector4(46, 48, 24, -26)
	sprite_name = "warden"
	super._ready()

	# BOSS 用自定义动画集，覆盖基类生成的
	_anim.sprite_frames = _boss_frames()
	_anim.play("idle")
	# 帧是 144x144，锚点要相应调整（基类按 48x48 设的 -24）
	_anim.position = Vector2(0, -72)

	_build_shockwave()
	_build_warning()


func _boss_frames() -> SpriteFrames:
	var sf := SpriteFrames.new()
	sf.remove_animation("default")
	var specs := [
		["idle", 8, 8.0],
		["walk", 8, 10.0],
		["charge", 6, 12.0],
		["slam", 7, 10.0],
		["cast", 7, 9.0],
		["hurt", 4, 14.0],
		["dead", 6, 8.0],
	]
	for spec in specs:
		var aname: String = spec[0]
		var count: int = spec[1]
		var fps: float = spec[2]
		sf.add_animation(aname)
		sf.set_animation_speed(aname, fps)
		sf.set_animation_loop(aname, aname in ["idle", "walk"])
		for i in count:
			var p := "res://art/boss/frames/warden_%s_%d.png" % [aname, i]
			if ResourceLoader.exists(p):
				sf.add_frame(aname, load(p))
	return sf


# ─────────────── 技能触发范围视觉 ───────────────

var _shockwave: Node2D

func _build_shockwave() -> void:
	_shockwave = Node2D.new()
	_shockwave.name = "Shockwave"
	_shockwave.z_index = 30
	_shockwave.visible = false
	_shockwave.set_script(preload("res://src/enemies/shockwave_fx.gd"))
	add_child(_shockwave)


var _warning: Node2D

func _build_warning() -> void:
	"""前摇预警：地面上画一条/一圈，告诉玩家"要来了"。

	这是 BOSS 战最重要的可读性设计 —— 没有预警的大招只能靠背板。
	"""
	_warning = Node2D.new()
	_warning.name = "Warning"
	_warning.z_index = 25
	_warning.visible = false
	_warning.set_script(preload("res://src/enemies/warning_fx.gd"))
	add_child(_warning)


# ─────────────── 主循环 ───────────────

func _physics_process(delta: float) -> void:
	# ── 休眠：玩家还没进 BOSS 房 ──
	# **必须在 super 之前拦住**，否则父类的 _physics_process 会做
	# 寻敌和状态推进，BOSS 会自己走向玩家（实测会一路走到教学段）。
	if _dormant:
		velocity.x = 0.0
		if _anim != null and _anim.animation != "idle":
			_anim.play("idle")
		move_and_slide()
		return

	super._physics_process(delta)

	if state == State.DEAD or _phase_transition:
		return

	_invuln = maxf(_invuln - delta, 0.0)
	_tick_skill(delta)
	_check_phase()


func _check_phase() -> void:
	var ratio := float(hp) / float(max_hp)
	var target := 1
	for i in PHASE_HP.size():
		if ratio <= PHASE_HP[i]:
			target = i + 1
	if target > phase:
		_enter_phase(target)


func _enter_phase(p: int) -> void:
	phase = p
	_phase_transition = true
	_invuln = 1.0
	velocity = Vector2.ZERO
	_set_attack_box(false)
	_warning.visible = false

	# 阶段转换：全屏冲击 + 短暂停顿
	_shockwave.play_burst(global_position, 140.0, 0.55)
	phase_changed.emit(p)
	skill_started.emit(-1)

	# 转换期间不做任何动作
	await get_tree().create_timer(0.9).timeout
	_phase_transition = false
	_skill_timer = 0.0
	_skill_stage = 0
	state = State.CHASE


# ─────────────── 技能调度 ───────────────

func _tick_skill(delta: float) -> void:
	if state == State.HURT:
		return

	_skill_timer -= delta

	if _skill_stage == 0:       # windup
		if _skill_timer <= 0.0:
			_skill_activate()
	elif _skill_stage == 1:     # active
		_skill_update(delta)
		if _skill_timer <= 0.0:
			_skill_recover()
	elif _skill_stage == 2:     # recover
		if _skill_timer <= 0.0:
			_skill_end()


func _pick_skill() -> int:
	"""按阶段挑选技能。用「轮转队列」而不是纯随机 ——

	纯随机会出现连续三次冲锋，观感很差。轮转保证每阶段都能
	把所有技能都演一遍。
	"""
	if _skill_seq.is_empty():
		var pool: Array[int] = [Skill.CHARGE, Skill.SLAM]
		if phase >= 2:
			pool.append(Skill.VOLLEY)
		if phase >= 3:
			pool.append(Skill.BLINK)
			pool.append(Skill.FRENZY)
		# 打乱后作为本轮序列
		_skill_seq = pool.duplicate()
		_skill_seq.shuffle()
	return _skill_seq.pop_front() if not _skill_seq.is_empty() else Skill.CHARGE


func _skill_speed() -> float:
	"""三阶段前摇缩短，压力递增。"""
	if phase >= 3:
		return 0.70
	if phase >= 2:
		return 0.85
	return 1.0


func _start_skill(skill: int) -> void:
	_current_skill = skill
	_skill_stage = 0
	_frenzy_hits = 0

	var cfg: Dictionary = _skill_cfg(skill)
	_skill_timer = float(cfg["windup"]) * _skill_speed()
	velocity = Vector2.ZERO

	# 动画与前摇预警
	match skill:
		Skill.CHARGE:
			_play("charge")
			_warning.show_line(global_position, facing, 220.0, _skill_timer)
		Skill.SLAM:
			_play("slam")
			_warning.show_circle(global_position, 78.0, _skill_timer)
		Skill.VOLLEY:
			_play("cast")
			_warning.show_fan(global_position, facing, 34.0,
							  int(SKILL_VOLLEY["count"]), _skill_timer)
		Skill.BLINK:
			_play("cast")
			_warning.show_circle(global_position, 50.0, _skill_timer)
		Skill.FRENZY:
			_play("charge")
			_warning.show_line(global_position, facing, 120.0, _skill_timer)

	skill_started.emit(skill)


func _skill_cfg(skill: int) -> Dictionary:
	match skill:
		Skill.CHARGE: return SKILL_CHARGE
		Skill.SLAM: return SKILL_SLAM
		Skill.VOLLEY: return SKILL_VOLLEY
		Skill.BLINK: return SKILL_BLINK
		Skill.FRENZY: return SKILL_FRENZY
	return SKILL_CHARGE


func _skill_activate() -> void:
	_skill_stage = 1
	_warning.visible = false
	var cfg: Dictionary = _skill_cfg(_current_skill)
	_skill_timer = float(cfg["active"])

	match _current_skill:
		Skill.CHARGE:
			velocity.x = facing * float(SKILL_CHARGE["speed"])
			_set_attack_box(true)
		Skill.SLAM:
			_shockwave.play_burst(global_position + Vector2(0, -4),
								  float(SKILL_SLAM["radius"]), 0.42)
			_set_attack_box(true)
		Skill.VOLLEY:
			_fire_volley()
		Skill.BLINK:
			_do_blink()
		Skill.FRENZY:
			_frenzy_next = 0.0
			_set_attack_box(true)


func _skill_update(delta: float) -> void:
	match _current_skill:
		Skill.CHARGE:
			# 冲锋期间保持速度（撞到墙也无所谓，由物理解决）
			velocity.x = facing * float(SKILL_CHARGE["speed"])
		Skill.FRENZY:
			_frenzy_next -= delta
			if _frenzy_next <= 0.0 and _frenzy_hits < int(SKILL_FRENZY["hits"]):
				_frenzy_hits += 1
				_frenzy_next = 0.24
				# 每次连击都向前小突进
				velocity.x = facing * 180.0
				# 换个方向，逼玩家不能一直站一边
				if _frenzy_hits % 2 == 0:
					facing = -facing
				_shockwave.play_burst(
					global_position + Vector2(facing * 30, -10), 46.0, 0.22)


func _skill_recover() -> void:
	_skill_stage = 2
	_set_attack_box(false)
	var cfg: Dictionary = _skill_cfg(_current_skill)
	_skill_timer = float(cfg["recover"])
	velocity = Vector2.ZERO
	if _current_skill == Skill.SLAM:
		_play("slam")


func _skill_end() -> void:
	_skill_stage = -1
	_skill_timer = 0.0
	_current_skill = _pick_skill()
	_start_skill(_current_skill)


# ─────────────── 各技能实现 ───────────────

func _fire_volley() -> void:
	"""弹幕：扇形发射。**二阶段起混入不可弹反的红弹**。"""
	var count := int(SKILL_VOLLEY["count"])
	if phase >= 3:
		count += 2
	var spread := deg_to_rad(float(SKILL_VOLLEY["spread"]))
	var base_dir := Vector2(facing, -0.12).normalized()
	var origin := global_position + Vector2(facing * 28, -54)

	for i in count:
		var t := 0.0 if count <= 1 else (float(i) / float(count - 1)) - 0.5
		var ang := t * spread
		var dir := base_dir.rotated(ang)
		# **必须用 Area2D 实例化**：projectile.gd 继承 Area2D，
		# 用 Node2D.new() 会报 "Script inherits from native type 'Area2D',
		# so it can't be assigned to an object of type 'Node2D'"，
		# 对象创建失败后后续调用全部异常，表现为测试永久卡死。
		var p := Area2D.new()
		p.set_script(Projectile)
		get_parent().add_child(p)

		# 二阶段起：中间那一发是红弹（不可弹反），两侧是青弹
		# 玩家必须分辨：青弹可以打回去，红弹只能闪
		var is_red := false
		if phase >= 2 and count >= 3:
			is_red = (i == count / 2)
		p.spawn(origin, dir, {
			"damage": int(SKILL_VOLLEY["damage"]),
			"speed": float(SKILL_VOLLEY["speed"]),
			"reflectable": not is_red,
		})


func _do_blink() -> void:
	"""瞬移斩：瞬间出现在玩家身后并斩击。"""
	var player := _find_player()
	if player == null:
		return
	var behind := player.global_position + Vector2(-40 * signf(
		player.global_position.x - global_position.x), 0)
	# 残影：起点和终点各放一次冲击
	_shockwave.play_burst(global_position, 40.0, 0.3)
	global_position = behind
	facing = 1 if player.global_position.x > global_position.x else -1
	_shockwave.play_burst(global_position, 50.0, 0.34)
	_set_attack_box(true)
	# 立刻结算一次近身伤害
	await get_tree().physics_frame
	_scan_attack_overlaps(get_node("AttackBox"))


# ─────────────── 覆写基类 ───────────────

func _do_chase(delta: float) -> void:
	# BOSS 不走路追人：它靠技能压迫。
	# 只在技能间隔朝玩家缓慢移动，避免原地不动。
	if _skill_stage < 0:
		_skill_timer -= delta
		if _skill_timer <= 0.0:
			_start_skill(_pick_skill())
		return

	var player := _find_player()
	if player:
		var dir := signf(player.global_position.x - global_position.x)
		if dir != 0.0:
			facing = 1 if dir > 0.0 else -1
		velocity.x = move_toward(velocity.x, dir * move_speed, 300.0 * delta)
		if absf(velocity.x) > 4.0:
			_play("walk")
		else:
			_play("idle")


func _enter_windup() -> void:
	# BOSS 不用基类的前摇逻辑，改由 _start_skill 统一调度
	_start_skill(_pick_skill())


func _do_windup(_delta: float) -> void:
	pass


func _do_attack(_delta: float) -> void:
	pass


func take_hit(amount: int, from_x: float) -> void:
	# 阶段转换期间无敌
	if _invuln > 0.0 or _phase_transition:
		return
	super.take_hit(amount, from_x)
	# BOSS 只在受击很重时进入硬直，平时不打断动作
	if amount >= 8 and state != State.DEAD:
		_play("hurt")


func _die() -> void:
	_phase_transition = false
	_warning.visible = false
	_shockwave.play_burst(global_position, 120.0, 0.8)
	_play("dead")
	state = State.DEAD
	_set_attack_box(false)
	remove_from_group(GROUP_HURTABLE)
	remove_from_group(GROUP_ENEMY)
	boss_died.emit()
	died.emit(self)
	# BOSS 不淡出消失，保留尸体
	var tw := create_tween()
	tw.tween_interval(2.5)
	tw.tween_property(self, "modulate:a", 0.35, 0.6)


func _play(anim: String) -> void:
	if _anim == null:
		return
	if not _anim.sprite_frames.has_animation(anim):
		return
	if _anim.animation != anim or not _anim.is_playing():
		_anim.play(anim)
