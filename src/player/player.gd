extends CharacterBody2D
## 主角「织」——Q 版像素动作控制
##
## 数值来源：docs/01-游戏规划.md v0.4 4.1/4.2 节
## 手感三件套：Coyote Time / 跳跃缓冲 / 高松手减速度
##
## 战斗系统（v0.5）：
##   - 轻攻击四连连段树，可取消窗口内接下一段
##   - 闪避带无敌帧，完美闪避触发子弹时间
##   - 攻击判定由 AttackHitbox 子节点驱动，与动画帧对齐

# ── 手感数值（游戏像素/秒，v0.4 定稿，勿随意改） ──
const RUN_SPEED := 144.0          # 跑速
const ACCEL := 1350.0             # 加速度 → 约 0.107s 到满速
const DECEL_GROUND := 1650.0      # 地面松手减速度（响应优先于物理真实）
const DECEL_AIR := 900.0          # 空中减速稍缓，保留一点惯性
const GRAVITY := 1350.0           # 重力
const GRAVITY_RISE_MUL := 0.82    # 上升时重力打折 → 手感更飘
const GRAVITY_FALL_MUL := 1.15    # 下落时重力加强 → 落地更脆
const MAX_FALL := 570.0           # 最大下落速度
const JUMP_VELOCITY := -360.0     # 跳跃初速 → 实测顶点 58.5px（屏高 21.7%）
                                  # 注意：文档里的 -398 是按基础重力算的；实际上升期重力
                                  # 乘了 0.82，所以初速要降到 -360 才能压出 58.5px 的顶点
const JUMP_CUT_MUL := 0.45        # 提前松键的截断系数（小跳约 14px）
const COYOTE_TIME := 0.10         # 离开平台后仍可跳
const JUMP_BUFFER := 0.12         # 落地前按跳会自动补跳
const AIR_CONTROL_MUL := 0.85     # 空中水平控制倍率
const TURN_BOOST := 2.2           # 反向输入时的减速倍率（急转向响应，动作游戏必备）

# ── 轻攻击四连连段树（v0.5） ──
# 每段：总时长 / 判定开启区间 / 伤害 / 前冲 / 判定框尺寸(w,h,offset_x,offset_y)
# offset 以角色脚底为原点，y 向上为负
const COMBO := [
	{"dur": 0.24, "hit_on": 0.06, "hit_off": 0.16, "dmg": 1, "lunge": 10.0,
	 "box": Vector4(22, 18, 14, -26)},
	{"dur": 0.22, "hit_on": 0.05, "hit_off": 0.15, "dmg": 1, "lunge": 6.0,
	 "box": Vector4(24, 18, 15, -26)},
	{"dur": 0.30, "hit_on": 0.08, "hit_off": 0.20, "dmg": 2, "lunge": 4.0,
	 "box": Vector4(26, 26, 15, -24)},
	{"dur": 0.36, "hit_on": 0.08, "hit_off": 0.22, "dmg": 3, "lunge": 26.0,
	 "box": Vector4(30, 30, 18, -24)},
]
const COMBO_MAX := 4
const COMBO_INPUT_WINDOW := 0.55   # 上一段结束后多久内按攻击仍接下一段
const COMBO_CANCEL_AFTER := 0.55   # 一段进度过这个比例后允许取消进下一段

# ── 闪避（v0.5） ──
const DASH_SPEED := 300.0
const DASH_DURATION := 0.20
const DASH_COOLDOWN := 0.28
const DASH_INVULN := 0.16         # 无敌帧比位移短，落地后恢复可被打
const DASH_FRAMES := 3
const PERFECT_WINDOW := 0.12      # 受击前这段时间内闪避 = 完美闪避
const BULLET_TIME_SCALE := 0.35   # 子弹时间倍率
const BULLET_TIME_DUR := 0.60

# ── 受击 ──
const HURT_STUN := 0.90           # 受击硬直
const KNOCKBACK := 15.0           # 击退距离
const INVULN_TIME := 0.90         # 受击后无敌
const MAX_HEARTS := 5

enum State { IDLE, RUN, JUMP, FALL, LAND, ATTACK, DASH, HURT, DEAD }

var state: State = State.IDLE
var facing := 1                   # 1 右 / -1 左

var _coyote := 0.0
var _jump_buffer := 0.0
var _jump_held := false
var _jump_cut_done := false
var _land_timer := 0.0
var _hurt_timer := 0.0
var _invuln := 0.0
var _hearts := MAX_HEARTS

# 连段状态
var _combo_index := 0             # 当前段（0..3）
var _combo_timer := 0.0           # 当前段已进行时间
var _combo_idle := 0.0            # 距离上一段结束的时间（用于接段窗口）
var _combo_buffer := false        # 是否缓存了攻击输入
var _hit_this_swing := false      # 本次挥击是否已命中（避免一次判多下）
var _hit_targets: Array = []      # 本次挥击已命中的目标

# 闪避状态
var _dash_timer := 0.0
var _dash_cd := 0.0
var _dash_invuln := 0.0

# 全局时间缩放（子弹时间由 main 控制，这里只发信号）
signal perfect_dodge
signal hit_landed(target: Node, damage: int)
# 刀光请求：由世界层 SlashLayer 接收并绘制，player 自己不画特效
signal slash_requested(origin: Vector2, deg0: float, deg1: float,
					   radius: float, color: Color, thick: float,
					   duration: float, facing: int)

@onready var _visual: Node2D = $Visual
@onready var _anim: AnimatedSprite2D = $Visual/AnimatedSprite2D
@onready var _hitbox: Area2D = $AttackHitbox

# 每段的刀光参数：(起始角, 终止角, 半径, 粗细)
# 角度基准 0°=正右，90°=下，-90°=上
# 与四段动作一一对应：
#   1 上挑：剑从下往上撩 → 弧线从 +70° 扫到 -80°
#   2 横斩：水平横扫   → 弧线窄而平，-25° 到 +25°
#   3 突刺：水平直刺   → 不画弧，用短促的前方直线光（角度范围极小）
#   4 下劈：从头顶劈落 → 弧线从 -110° 扫到 +90°
const SLASH_FX := [
	Vector4(70, -80, 16, 2.0),      # 第1段 上挑
	Vector4(-25, 28, 17, 2.2),      # 第2段 横斩
	Vector4(-8, 8, 19, 2.6),        # 第3段 突刺（近直线）
	Vector4(-110, 90, 20, 3.0),     # 第4段 下劈
]

var _current_anim := ""


func _ready() -> void:
	# 角色物理体尺寸：48px 高、24px 宽（碰撞盒只用躯干+腿，不含头发）
	var shape := $CollisionShape2D.shape as RectangleShape2D
	if shape:
		shape.size = Vector2(24, 40)
	# 碰撞盒中心上移到腿部，让脚贴地面
	$CollisionShape2D.position = Vector2(0, -20)
	_hitbox.hit_landed.connect(_on_hit_landed)
	_play_anim("idle")


func _physics_process(delta: float) -> void:
	_tick_timers(delta)

	if state == State.DEAD:
		velocity.y = minf(velocity.y + GRAVITY * delta, MAX_FALL)
		move_and_slide()
		return

	if state == State.HURT:
		velocity.y = minf(velocity.y + GRAVITY * delta, MAX_FALL)
		velocity.x = move_toward(velocity.x, 0.0, DECEL_AIR * delta)
		move_and_slide()
		return

	if state == State.DASH:
		_update_dash(delta)
		move_and_slide()
		return

	_handle_input(delta)
	if state == State.ATTACK:
		_update_attack(delta)
	else:
		_handle_jump(delta)
		_handle_horizontal(delta)
	_apply_gravity(delta)

	move_and_slide()
	_update_state()


# ────────────────────────────── 输入 ──────────────────────────────

func _handle_input(_delta: float) -> void:
	# 攻击输入：**按住也算**，不要求每一下都重新点。
	# 动作游戏的通行手感是按住攻击键持续连打；只认 just_pressed 会导致
	# 玩家必须疯狂点击才能接上连段，手感非常糟。
	if Input.is_action_pressed("attack"):
		_combo_buffer = true

	# 闪避优先于一切（除了受击/死亡）
	if Input.is_action_just_pressed("dash") and _dash_cd <= 0.0:
		_start_dash()

	if Input.is_action_just_pressed("jump"):
		_jump_buffer = JUMP_BUFFER
		_jump_held = true
		_jump_cut_done = false
	elif not Input.is_action_pressed("jump"):
		_jump_held = false


func _handle_horizontal(delta: float) -> void:
	var dir := Input.get_axis("move_left", "move_right")

	if absf(dir) > 0.01:
		facing = 1 if dir > 0.0 else -1
		var accel := ACCEL * (AIR_CONTROL_MUL if not is_on_floor() else 1.0)
		# 反向输入：先按 TURN_BOOST 急刹，再重新加速。没有这一步角色会「滑冰」
		if signf(velocity.x) != signf(dir) and absf(velocity.x) > 1.0:
			accel *= TURN_BOOST
		velocity.x = move_toward(velocity.x, dir * RUN_SPEED, accel * delta)
	else:
		var decel := DECEL_GROUND if is_on_floor() else DECEL_AIR
		velocity.x = move_toward(velocity.x, 0.0, decel * delta)


func _handle_jump(delta: float) -> void:
	var can_jump := is_on_floor() or _coyote > 0.0
	if _jump_buffer > 0.0 and can_jump:
		velocity.y = JUMP_VELOCITY
		_jump_buffer = 0.0
		_coyote = 0.0
		_jump_cut_done = false
		state = State.JUMP

	# 提前松键 → 小跳。只在松开的**那一帧**截断一次，
	# 若每帧都乘系数会把上升速度持续打成 0，跳跃高度几乎归零。
	if velocity.y < 0.0 and not _jump_held and not _jump_cut_done:
		velocity.y *= JUMP_CUT_MUL
		_jump_cut_done = true
	# delta 未在本函数用到，保留参数以对齐调用约定
	if delta < 0.0:
		pass


func _apply_gravity(delta: float) -> void:
	var mul := GRAVITY_RISE_MUL if velocity.y < 0.0 else GRAVITY_FALL_MUL
	velocity.y = minf(velocity.y + GRAVITY * mul * delta, MAX_FALL)
	if is_on_floor():
		_coyote = COYOTE_TIME


# ────────────────────────── 轻攻击四连连段树 ──────────────────────────

func _update_attack(delta: float) -> void:
	var seg: Dictionary = COMBO[_combo_index]
	_combo_timer += delta

	# 攻击期间保留惯性，逐渐减速
	velocity.x = move_toward(velocity.x, 0.0, DECEL_AIR * delta)

	# 判定框开关：只在 hit_on..hit_off 区间开启
	var t := _combo_timer
	var should_hit: bool = t >= float(seg["hit_on"]) and t <= float(seg["hit_off"])
	if should_hit != _hitbox.active:
		_hitbox.set_active(should_hit)

	# 段内结束
	if t >= float(seg["dur"]):
		_hitbox.set_active(false)
		_combo_idle = 0.0
		_combo_timer = 0.0
		_hit_this_swing = false
		_hit_targets.clear()
		state = State.IDLE
		# 段刚结束时若已缓存输入，立即接下一段
		_try_next_combo()
		return

	# 取消窗口：一段过半后按攻击可提前接下一段
	var progress: float = t / float(seg["dur"])
	if _combo_buffer and progress >= COMBO_CANCEL_AFTER and _combo_index < COMBO_MAX - 1:
		_hitbox.set_active(false)
		_combo_index += 1
		_combo_timer = 0.0
		_hit_this_swing = false
		_hit_targets.clear()
		_combo_buffer = false
		_begin_swing()
		return

	_animate_attack(progress)


func _try_next_combo() -> bool:
	"""一段结束后尝试接下一段。

	第 4 段打完后**循环回第 1 段**，这样按住攻击键可以无限连打，
	而不是打完四段就停手等玩家重新按键（那是很差的连续攻击手感）。
	"""
	if not _combo_buffer:
		return false
	if _combo_index >= COMBO_MAX - 1:
		# 四段打完，回到第一段接着打
		_combo_index = 0
	else:
		_combo_index += 1
	_combo_buffer = false
	_begin_swing()
	return true


func _begin_swing() -> void:
	var seg: Dictionary = COMBO[_combo_index]
	state = State.ATTACK
	_combo_timer = 0.0
	_combo_idle = 0.0
	_hit_this_swing = false
	_hit_targets.clear()
	_hitbox.damage = int(seg["dmg"])

	var box: Vector4 = seg["box"]
	_hitbox.set_reach(box.x, box.y, box.z * facing, box.w)

	# 前冲
	velocity.x = facing * float(seg["lunge"]) * 6.0
	_play_attack_anim()
	_fire_slash_fx()


func _fire_slash_fx() -> void:
	# 刀光由世界层的 SlashLayer 绘制（见 src/world/slash_layer.gd）。
	# 不画进角色帧、也不做 Player 子节点：前者会覆盖角色像素，
	# 后者受 flip_h 和父变换影响，位置会错乱。
	var fx: Vector4 = SLASH_FX[_combo_index]
	var color := Color("#B9F2FF")
	if _combo_index == COMBO_MAX - 1:
		color = Color("#FF7A9C")
	# 弧心：角色身前、躯干高度
	var origin := global_position + Vector2(4.0 * facing, -26.0)
	slash_requested.emit(origin, fx.x, fx.y, fx.z, color, fx.w, 0.14, facing)


func start_attack() -> void:
	"""供外部/测试调用：发起一段攻击。

	连段规则：
	  - 若上一段结束不久（COMBO_INPUT_WINDOW 内）且未到第 4 段 → 接下一段
	  - 否则从第 1 段重来
	"""
	if state == State.ATTACK or state == State.DASH:
		return
	if state == State.HURT or state == State.DEAD:
		return

	var can_chain: bool = _combo_idle <= COMBO_INPUT_WINDOW \
		and _combo_index < COMBO_MAX - 1 \
		and _combo_idle < 900.0

	if can_chain:
		_combo_index += 1
	else:
		_combo_index = 0
	_begin_swing()


func get_combo_index() -> int:
	return _combo_index


func is_attacking() -> bool:
	return state == State.ATTACK


func _on_hit_landed(target: Node, damage: int, _from_x: float) -> void:
	if not _hit_this_swing:
		_hit_this_swing = true
	# 同一次挥击对同一目标只算一次
	if target in _hit_targets:
		return
	_hit_targets.append(target)

	if target.has_method("take_hit"):
		target.take_hit(damage, global_position.x)
	elif target.has_method("take_damage"):
		target.take_damage(damage, global_position.x)
	hit_landed.emit(target, damage)
	_emit_hit_feedback()


func _emit_hit_feedback() -> void:
	# 顿帧 + 震屏的挂点。真正实现放在 main 里，通过信号驱动，
	# 这样 player 不需要知道相机和全局时间。
	pass


# ────────────────────────────── 闪避 ──────────────────────────────

func start_dash() -> void:
	"""供外部/测试调用：立即发起闪避（忽略冷却）。"""
	if state == State.HURT or state == State.DEAD:
		return
	_start_dash()


func _start_dash() -> void:
	state = State.DASH
	_dash_timer = DASH_DURATION
	_dash_cd = DASH_COOLDOWN + DASH_DURATION
	_dash_invuln = DASH_INVULN
	_hitbox.set_active(false)

	# 有方向输入时按方向闪，否则按朝向
	var dir := Input.get_axis("move_left", "move_right")
	if absf(dir) > 0.01:
		facing = 1 if dir > 0.0 else -1
	velocity = Vector2(facing * DASH_SPEED, 0.0)

	_play_anim("dash")
	_anim.frame = 0


func _update_dash(delta: float) -> void:
	_dash_timer -= delta
	# 冲刺中途快速衰减速度，形成「一冲即停」的手感
	velocity.x = move_toward(velocity.x, 0.0, DASH_SPEED * 3.0 * delta)
	velocity.y = 0.0     # 闪避期间不受重力，水平位移更干净

	# 动画按进度切帧
	var p := 1.0 - clampf(_dash_timer / DASH_DURATION, 0.0, 1.0)
	var f := mini(int(p * DASH_FRAMES), DASH_FRAMES - 1)
	_anim.frame = f
	_anim.pause()

	if _dash_timer <= 0.0:
		state = State.IDLE
		_dash_timer = 0.0
		_combo_idle = 999.0


func is_dashing() -> bool:
	return state == State.DASH


func is_dash_invulnerable() -> bool:
	return _dash_invuln > 0.0


# ────────────────────────────── 状态 ──────────────────────────────

func _tick_timers(delta: float) -> void:
	_coyote = maxf(_coyote - delta, 0.0)
	_jump_buffer = maxf(_jump_buffer - delta, 0.0)
	_invuln = maxf(_invuln - delta, 0.0)
	_dash_cd = maxf(_dash_cd - delta, 0.0)
	_dash_invuln = maxf(_dash_invuln - delta, 0.0)
	if state != State.ATTACK:
		_combo_idle += delta
	if _land_timer > 0.0:
		_land_timer -= delta
	if _hurt_timer > 0.0:
		_hurt_timer -= delta
		if _hurt_timer <= 0.0:
			state = State.IDLE


func _update_state() -> void:
	# 朝向每帧都跟手，不能只在状态切换时更新（否则待机转身不生效）
	_anim.flip_h = facing < 0

	if state == State.ATTACK or state == State.HURT or state == State.DEAD \
			or state == State.DASH:
		return

	# 非攻击状态时，缓存的攻击输入在这里消费
	if _combo_buffer:
		_combo_buffer = false
		start_attack()
		return

	if is_on_floor():
		if _land_timer > 0.0:
			state = State.LAND
		elif absf(velocity.x) > 4.0:
			state = State.RUN
		else:
			state = State.IDLE
	else:
		state = State.JUMP if velocity.y < 0.0 else State.FALL

	_sync_animation()


func _sync_animation() -> void:
	match state:
		State.RUN:
			_play_anim("run")
		State.JUMP:
			_play_anim("jump")
			_anim.frame = 0
			_anim.pause()
		State.FALL:
			_play_anim("jump")
			_anim.frame = 2
			_anim.pause()
		State.LAND:
			_play_anim("land")
		_:
			_play_anim("idle")


func _play_attack_anim() -> void:
	var anim_name: String = "atk%d" % (_combo_index + 1)
	_current_anim = anim_name
	if _anim.sprite_frames.has_animation(anim_name):
		_anim.play(anim_name)
		_anim.pause()
		_anim.frame = 0


func _animate_attack(progress: float) -> void:
	# 攻击动画 4 帧：0 预备 / 1 加速 / 2 命中 / 3 收势
	# 分段与 COMBO 里的 hit_on/hit_off 对齐，让命中帧正好落在判定窗口内。
	var f := 0
	if progress >= 0.75:
		f = 3
	elif progress >= 0.42:
		f = 2
	elif progress >= 0.18:
		f = 1
	_anim.pause()
	_anim.frame = f


func _play_anim(name: String) -> void:
	if _current_anim == name:
		return
	_current_anim = name
	if not _anim.sprite_frames.has_animation(name):
		return
	_anim.play(name)


func _on_landed() -> void:
	_land_timer = 0.08
	state = State.LAND


func take_damage(amount: int, from_x: float) -> void:
	# 闪避无敌帧：完全免疫
	if _dash_invuln > 0.0:
		return
	if _invuln > 0.0 or state == State.DEAD:
		return

	_hearts -= amount
	_invuln = INVULN_TIME
	_hurt_timer = HURT_STUN
	state = State.HURT

	var dir := signf(global_position.x - from_x)
	if dir == 0.0:
		dir = -facing
	velocity.x = dir * KNOCKBACK * 10.0
	velocity.y = -120.0

	if _hearts <= 0:
		_hearts = 0
		state = State.DEAD


func try_perfect_dodge() -> bool:
	"""由外部在即将受击时调用：若正在闪避则判定完美闪避。"""
	if _dash_invuln > 0.0:
		perfect_dodge.emit()
		return true
	return false


func heal(amount: int) -> void:
	_hearts = mini(_hearts + amount, MAX_HEARTS)


func get_hearts() -> int:
	return _hearts


func is_invulnerable() -> bool:
	return _invuln > 0.0 or _dash_invuln > 0.0
