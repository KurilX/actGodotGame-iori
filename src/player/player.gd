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
# **hit_on 从 0.06 缩到 0.02**：弹反要靠"在弹幕到达前一刻挥剑"，
# 起手 0.06 秒（120Hz 下 7 帧）太晚 —— 实测弹幕 2 帧就能撞上玩家，
# 判定框还没开就已经吃伤害了，弹反根本来不及。改成 0.02（2.4 帧）。
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

# ── 重攻击三连（v0.6） ──
# 与轻攻击的区别（这是设计上的三条硬线，不只是数值放大）：
#   1. **时间更长**：每段 0.55~0.85s（轻攻击 0.22~0.36s），有明确的蓄力前摇
#   2. **幅度更大**：前冲距离翻倍以上，判定框更大，第2段还能打到上方
#   3. **反馈更重**：顿帧更久、震屏更狠，命中时停顿感明显
#
# 连段规则也与轻攻击不同：重攻击几乎不能取消（HEAVY_CANCEL_AFTER = 0.92），
# 必须等这一段走完，否则「重」就没有代价。
const HEAVY_COMBO := [
	# 第1段：蓄力横扫 —— 前摇长，横向大范围
	{"dur": 0.55, "hit_on": 0.20, "hit_off": 0.34, "dmg": 5, "lunge": 22.0,
	 "box": Vector4(34, 30, 20, -26), "hitstop": 0.08, "shake": 2.5},
	# 第2段：上挑重斩 —— 打高，判定框向右上延伸
	{"dur": 0.62, "hit_on": 0.22, "hit_off": 0.38, "dmg": 7, "lunge": 14.0,
	 "box": Vector4(30, 42, 18, -34), "hitstop": 0.09, "shake": 3.0},
	# 第3段：泰山压顶 —— 跃起下砸，最大伤害与最强反馈
	{"dur": 0.85, "hit_on": 0.34, "hit_off": 0.52, "dmg": 12, "lunge": 30.0,
	 "box": Vector4(40, 36, 22, -22), "hitstop": 0.14, "shake": 5.0},
]
const HEAVY_MAX := 3
const HEAVY_INPUT_WINDOW := 0.35   # 比轻攻击更短：重攻击接段要更精确
const HEAVY_CANCEL_AFTER := 0.92   # 几乎不能取消，必须打完

# 顿帧（hitstop）：命中瞬间把时间流速压到很低，制造打击感
const HITSTOP_SCALE := 0.05

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

# ── 连段状态：**统一由一条链表达** ──
#
# 历史：原来轻重各有一套游标（_combo_index/_heavy_index 等 8 个变量），
# 每一处判断都要 `if is_heavy_attack: ... else: ...` 分支一次，
# 而技能树的连招判定又维护了第三份状态（_sequence）。
# 三者本质是同一个事实的三种投影。
#
# 现在全部由 ComboChain 承载：
#   · 段号        → chain.current_index("light"/"heavy")
#   · 连招        → chain.matches(pattern)
#   · 接段窗口    → chain 内部按时间戳清理
#
# 下面这些变量保留为**只读映射**，避免改动 70 处调用点；
# 写入统一走 _chain_push()。
var _chain = null                       # ComboChain 实例（见 src/player/combo_chain.gd）
var _combo_index := 0                   # 由链同步：轻攻击当前段
var _heavy_index := 0                   # 由链同步：重攻击当前段
var _combo_timer := 0.0                 # 当前段已进行时间（仍是本地计时，与链无关）
var _heavy_timer := 0.0
var _combo_idle := 0.0                  # 距上一段结束（保留给外部测试读）
var _heavy_idle := 0.0
var _combo_buffer := false              # 是否缓存了攻击输入
var _heavy_buffer := false
var is_heavy_attack := false            # 当前 ATTACK 状态属于重攻击
var _hit_this_swing := false            # 本次挥击是否已命中（避免一次判多下）
var _hit_targets: Array = []            # 本次挥击已命中的目标
var _chain_time := 0.0                  # 链的单调时钟（秒）

# 获得道具动画：独立的计时器，不占用 State
const GAIN_ANIM_DUR := 0.72
# 弹反窗口：攻击起手后的这段时间内，判定框对弹幕生效（早于伤害窗口）
const PARRY_WINDOW := 0.10
const ComboChain := preload("res://src/player/combo_chain.gd")
var _gain_anim_timer := 0.0
var _parry_window := 0.0



# 顿帧：>0 时把时间流速压到 HITSTOP_SCALE，制造命中停顿
var _hitstop := 0.0

# 闪避状态
var _dash_timer := 0.0
var _dash_cd := 0.0
var _dash_invuln := 0.0

# 全局时间缩放（子弹时间由 main 控制，这里只发信号）
signal perfect_dodge
signal hit_landed(target: Node, damage: int)
# 弹反成功：UI 据此播特效/给连击加成
signal parried(projectile: Node)
# 玩家受伤：连击条据此清零
signal damaged(amount: int)
# 空挥：一段攻击打完但没有命中任何目标
signal whiffed(heavy: bool)
# 一段攻击打完（无论命中与否）：供技能树追踪连招序列
signal attack_segment_done(heavy: bool)
# 刀光请求：由世界层 SlashLayer 接收并绘制，player 自己不画特效
signal slash_requested(origin: Vector2, deg0: float, deg1: float,
					   radius: float, color: Color, thick: float,
					   duration: float, facing: int, heavy: bool)
# 震屏请求：重攻击命中时相机抖动
signal shake_requested(amount: float, duration: float)
# 顿帧请求：把全局时间流速压低一小段
signal hitstop_requested(duration: float)

@onready var _visual: Node2D = $Visual
@onready var _anim: AnimatedSprite2D = $Visual/AnimatedSprite2D
@onready var _hitbox: Area2D = $AttackHitbox

# 每段的刀光参数：(起始角, 终止角, 半径, 粗细)
# 角度基准 0°=正右，90°=下，-90°=上
# 与 v3 四段动作一一对应（v3 动作幅度加大，半径也相应加大）：
#   1 上挑：剑沿身体竖直上撩 → 弧线从 +80° 扫到 -100°
#   2 横斩：水平横扫       → 窄而平的横弧 -30° 到 +35°
#   3 突刺：水平直刺       → 近直线，-6° 到 +6°
#   4 跳劈：腾空后下砸     → 大半径竖弧 -115° 到 +95°
const SLASH_FX := [
	Vector4(80, -100, 20, 2.4),     # 第1段 上挑
	Vector4(-30, 35, 22, 2.6),      # 第2段 横斩
	Vector4(-6, 6, 24, 2.8),        # 第3段 突刺（近直线）
	Vector4(-95, 100, 26, 3.4),     # 第4段 跳劈（头顶→身前下方）
]

var _current_anim := ""


func _ready() -> void:
	# 角色物理体尺寸：48px 高、24px 宽（碰撞盒只用躯干+腿，不含头发）
	var shape := $CollisionShape2D.shape as RectangleShape2D
	if shape:
		shape.size = Vector2(24, 40)
	# 碰撞盒中心上移到腿部，让脚贴地面
	$CollisionShape2D.position = Vector2(0, -20)
	# 加入 player 组：敌人靠这个组找到玩家
	add_to_group("player")
	_hitbox.hit_landed.connect(_on_hit_landed)
	# 弹反信号转发到玩家层，供 UI 与连击条使用
	_hitbox.parried.connect(func(proj: Node) -> void:
		parried.emit(proj))

	# 初始化连段链：把各链的上限与接段窗口注入
	_chain = ComboChain.new()
	_chain.configure(COMBO_MAX, HEAVY_MAX, COMBO_INPUT_WINDOW,
					 HEAVY_INPUT_WINDOW)
	_chain_time = 0.0

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
	# 轻攻击输入：**按住也算**，不要求每一下都重新点。
	# 动作游戏的通行手感是按住攻击键持续连打；只认 just_pressed 会导致
	# 玩家必须疯狂点击才能接上连段，手感非常糟。
	if Input.is_action_pressed("attack"):
		_combo_buffer = true

	# 重攻击：同样支持按住连打，但用独立缓冲，不与轻攻击互相消耗
	if Input.is_action_pressed("heavy"):
		_heavy_buffer = true

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


# ────────────────────── 攻击连段（轻攻击 + 重攻击） ──────────────────────

func _current_seg() -> Dictionary:
	"""取当前段的参数表，轻/重共用同一套推进逻辑。"""
	return HEAVY_COMBO[_heavy_index] if is_heavy_attack else COMBO[_combo_index]


func _set_attack_timer(t: float) -> void:
	if is_heavy_attack:
		_heavy_timer = t
	else:
		_combo_timer = t


func _get_attack_timer() -> float:
	return _heavy_timer if is_heavy_attack else _combo_timer


func _update_attack(delta: float) -> void:
	var seg: Dictionary = _current_seg()
	_set_attack_timer(_get_attack_timer() + delta)

	# 攻击期间保留惯性，逐渐减速
	velocity.x = move_toward(velocity.x, 0.0, DECEL_AIR * delta)

	# 判定框开关。
	#
	# 有两个窗口：
	#   · 弹反窗口 _parry_window：起手就开，专用于打回弹幕
	#   · 伤害窗口 hit_on..hit_off：正常命中敌人
	# 取并集，任一有效就开判定框。
	var t := _get_attack_timer()
	var should_hit: bool = t >= float(seg["hit_on"]) and t <= float(seg["hit_off"])
	var in_parry: bool = _parry_window > 0.0
	if should_hit or in_parry:
		if not _hitbox.active:
			_hitbox.set_active(true)
	elif _hitbox.active:
		_hitbox.set_active(false)

	# 段内结束
	if t >= float(seg["dur"]):
		_hitbox.set_active(false)
		_set_attack_timer(0.0)
		# 空挥判定：这一段打完了但一个目标都没碰到。
		# 必须在这里判断（段结束时 _hit_targets 还没清空），
		# 清空之后就再也拿不到"是否命中过"的信息了。
		if _hit_targets.is_empty():
			whiffed.emit(is_heavy_attack)
		# 通知技能树：这一段打完了。放在这里是因为无论命中与否
		# 都算"完成了一个动作"，连招判定看的是动作序列而非命中。
		attack_segment_done.emit(is_heavy_attack)
		_hit_this_swing = false
		_hit_targets.clear()
		state = State.IDLE
		if is_heavy_attack:
			_heavy_idle = 0.0
			is_heavy_attack = false
			_try_next_heavy()
		else:
			_combo_idle = 0.0
			_try_next_combo()
		return

	var progress: float = t / float(seg["dur"])

	# 取消窗口：轻攻击过半可取消；重攻击几乎不能（HEAVY_CANCEL_AFTER=0.92）
	var cancel_after := HEAVY_CANCEL_AFTER if is_heavy_attack else COMBO_CANCEL_AFTER
	var buf := _heavy_buffer if is_heavy_attack else _combo_buffer
	var max_n := HEAVY_MAX if is_heavy_attack else COMBO_MAX
	var idx := _heavy_index if is_heavy_attack else _combo_index

	if buf and progress >= cancel_after and idx < max_n - 1:
		_hitbox.set_active(false)
		# 取消进下一段：同样走链，保证链与段号一致
		if is_heavy_attack:
			_heavy_timer = 0.0
			_heavy_buffer = false
			_heavy_index = _chain_push(ComboChain.KIND_HEAVY)
		else:
			_combo_timer = 0.0
			_combo_buffer = false
			_combo_index = _chain_push(ComboChain.KIND_LIGHT)
		_hit_this_swing = false
		_hit_targets.clear()
		_begin_swing()
		return

	_animate_attack(progress)


func _sync_from_chain() -> void:
	"""把链里的段号同步到兼容变量。

	兼容层存在的唯一原因：文件里还有 70 处引用 _combo_index/_heavy_index。
	统一在这里写回，保证读到的永远是链的当前真相。
	"""
	_combo_index = _chain.current_index(ComboChain.KIND_LIGHT)
	_heavy_index = _chain.current_index(ComboChain.KIND_HEAVY)


func _chain_push(kind: String) -> int:
	"""把一次动作推进链，返回段号。"""
	var idx: int = _chain.push(kind, _chain_time)
	_sync_from_chain()
	return idx


func _try_next_combo() -> bool:
	"""轻攻击一段结束后尝试接下一段。

	第 4 段打完后**循环回第 1 段**（链满整体清空），
	这样按住攻击键可以无限连打。
	"""
	if not _combo_buffer:
		return false
	_combo_buffer = false
	is_heavy_attack = false
	var idx := _chain_push(ComboChain.KIND_LIGHT)
	# 链已经在回环时清空过，idx 就是正确的段号
	_combo_index = idx
	_begin_swing()
	return true


func _try_next_heavy() -> bool:
	"""重攻击一段结束后尝试接下一段。

	与轻攻击的差别：**第 3 段打完不回第 1 段**，而是收招结束。
	重攻击是「一套打完」的爆发，循环回去会变成无脑连按。
	"""
	if not _heavy_buffer:
		return false
	_heavy_buffer = false
	# 已经是第 3 段（index 达到上限）→ 收招，不再接
	var cur: int = _chain.current_index(ComboChain.KIND_HEAVY)
	if cur >= HEAVY_MAX - 1:
		_heavy_index = 0
		_heavy_idle = 999.0
		return false
	is_heavy_attack = true
	var idx := _chain_push(ComboChain.KIND_HEAVY)
	_heavy_index = idx
	_begin_swing()
	return true


func _begin_swing() -> void:
	var seg: Dictionary = _current_seg()
	state = State.ATTACK
	_set_attack_timer(0.0)
	_combo_idle = 0.0
	_heavy_idle = 0.0
	_hit_this_swing = false
	_hit_targets.clear()
	_hitbox.damage = int(seg["dmg"])

	var box: Vector4 = seg["box"]
	_hitbox.set_reach(box.x, box.y, box.z * facing, box.w)

	# 前冲。重攻击冲得更远，但重攻击的 lunge 值本身已经更大，
	# 这里用不同的系数保持手感区分：
	#   轻攻击 ×6（起步快、位移短）
	#   重攻击 ×4（起步稍慢、但基数大，整体位移更远）
	var mul := 4.0 if is_heavy_attack else 6.0
	velocity.x = facing * float(seg["lunge"]) * mul

	# ── 弹反窗口 ──
	# 攻击起手瞬间就开启判定框，持续 PARry_WINDOW 秒，之后再交给
	# 正常的 hit_on/hit_off 窗口。
	#
	# **为什么需要单独的弹反窗口**：实测弹幕从进入身体范围到消失只要
	# 2 帧，而正常攻击判定要 0.06s（7 帧）后才开 —— 弹反根本来不及。
	# 动作游戏里"格挡/弹反"本来就应该比"出伤害"更早生效。
	_parry_window = PARRY_WINDOW

	_play_attack_anim()
	_fire_slash_fx()


# 重攻击三连的刀光参数：(起始角, 终止角, 半径, 粗细)
# 比轻攻击明显更"重"：半径更大（覆盖更广）、更粗、颜色更暖
const HEAVY_SLASH_FX := [
	Vector4(-70, 75, 32, 5.0),      # 第1段 蓄力横扫：大横弧
	Vector4(85, -105, 30, 5.5),     # 第2段 上挑重斩：从下扫到头顶
	Vector4(-115, 100, 36, 7.0),    # 第3段 泰山压顶：最大竖弧
]


func _fire_slash_fx() -> void:
	# 刀光由世界层的 SlashLayer 绘制（见 src/world/slash_sprite.gd）。
	# 不画进角色帧、也不做 Player 子节点：前者会覆盖角色像素，
	# 后者受 flip_h 和父变换影响，位置会错乱。
	var fx: Vector4
	var color: Color
	var duration: float

	if is_heavy_attack:
		fx = HEAVY_SLASH_FX[_heavy_index]
		# 重攻击用更暖的橙金色，第3段用高饱和红强调终结感
		color = Color("#FFB04A") if _heavy_index < HEAVY_MAX - 1 else Color("#FF5A6E")
		duration = 0.30          # 比轻攻击（0.16）挂得更久，视觉更有分量
	else:
		fx = SLASH_FX[_combo_index]
		color = Color("#B9F2FF")
		if _combo_index == COMBO_MAX - 1:
			color = Color("#FF7A9C")
		duration = 0.16

	# 弧心：角色身前、躯干中部高度。
	var origin := global_position + Vector2(4.0 * facing, -22.0)
	slash_requested.emit(origin, fx.x, fx.y, fx.z, color, fx.w, duration, facing, is_heavy_attack)

	# 重攻击额外叠一层「残影」：同一道弧、更大的半径、更低的透明度，
	# 在视觉上做出双层刀光，比单纯加粗更有层次。
	if is_heavy_attack:
		var ghost_origin := origin + Vector2(-6.0 * facing, -2.0)
		slash_requested.emit(ghost_origin, fx.x * 0.85, fx.y * 0.85,
							 fx.z * 1.22, Color(color.r, color.g, color.b, 0.45),
							 fx.w * 0.7, duration * 1.35, facing, true)


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

	# 接段条件：距上一段结束不超过窗口，且还没打满
	var can_chain: bool = _combo_idle <= COMBO_INPUT_WINDOW \
		and _combo_index < COMBO_MAX - 1 \
		and _combo_idle < 900.0
	if can_chain:
		var idx := _chain_push(ComboChain.KIND_LIGHT)
		_combo_index = idx
	else:
		# 不能再接：从第 1 段重新开始。
		# 段号来自链，所以必须让链也"重开"（push 出新的一段 index=0），
		# 否则 _next_index() 会接着旧记录累加。
		_combo_buffer = false
		is_heavy_attack = false
		_combo_index = _chain_push(ComboChain.KIND_LIGHT)
		_begin_swing()
		return
	_begin_swing()


func play_gain_anim() -> void:
	"""播放"获得道具"动画（抬手接住）。

	用独立的状态位而不是 State 枚举：这只是一个**表现层动画**，
	不应该阻塞移动/攻击逻辑。如果塞进状态机，玩家在原地看动画时
	会有"输入没反应"的卡顿感。
	"""
	if _anim == null or not _anim.sprite_frames.has_animation("gain"):
		return
	_gain_anim_timer = GAIN_ANIM_DUR
	_anim.play("gain")
	_anim.frame = 0


# ─────────────── 存档接口 ───────────────

func to_save_dict() -> Dictionary:
	"""导出可存档的状态。"""
	return {
		"hearts": _hearts,
		"max_hearts": MAX_HEARTS,
		"player_pos": [global_position.x, global_position.y],
	}


func from_save_dict(d: Dictionary) -> void:
	"""从存档恢复状态。缺字段就用默认值，不报错。"""
	_hearts = clampi(int(d.get("hearts", MAX_HEARTS)), 1, MAX_HEARTS)
	_invuln = 0.0
	_hurt_timer = 0.0
	state = State.IDLE
	velocity = Vector2.ZERO
	# 位置由调用方设置（它可能还要处理相机跟随）
	queue_redraw()


func try_parry_incoming(proj: Node) -> bool:
	"""弹幕击中玩家前的最后一刻询问：现在能不能弹反？

	返回 true 表示已弹反（弹幕应继续飞行，不结算伤害）。

	**为什么由弹幕来问**：见 projectile.gd 里 _handle_hit 的注释 ——
	Area2D 之间的信号顺序不可靠，弹幕往往先撞到玩家就自毁了。
	把判断权放在弹幕结算前，才能保证弹反一定有机会触发。
	"""
	if _parry_window <= 0.0:
		return false
	var hb = _hitbox
	if hb == null or not hb.has_method("_try_parry"):
		return false
	return bool(hb._try_parry(proj))


func get_chain():
	"""暴露连段链给技能树读 —— 保证"连段推进"和"连招判定"是同一份状态。"""
	return _chain


func get_combo_index() -> int:
	return _combo_index


func get_heavy_index() -> int:
	return _heavy_index


func start_heavy_attack() -> void:
	"""供外部/测试调用：发起重攻击。

	连段规则与轻攻击一致（窗口内可接段），但第 3 段打完不回第 1 段。
	"""
	if state == State.ATTACK or state == State.DASH:
		return
	if state == State.HURT or state == State.DEAD:
		return

	var can_chain: bool = _heavy_idle <= HEAVY_INPUT_WINDOW \
		and _heavy_index < HEAVY_MAX - 1 \
		and _heavy_idle < 900.0
	if can_chain:
		_heavy_index = _chain_push(ComboChain.KIND_HEAVY)
	else:
		# 同 light：必须让链也重开，段号以链为准
		_heavy_index = _chain_push(ComboChain.KIND_HEAVY)
	_heavy_buffer = false
	is_heavy_attack = true
	_begin_swing()


func is_heavy() -> bool:
	return state == State.ATTACK and is_heavy_attack


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
	"""命中反馈：顿帧 + 震屏。

	轻攻击给短顿帧、轻震屏；重攻击用段参数里配的 hitstop/shake，
	数值明显更大 —— 这是「重」最重要的手感来源，比伤害数字有用得多。
	"""
	if is_heavy_attack:
		var seg: Dictionary = HEAVY_COMBO[_heavy_index]
		var stop: float = float(seg.get("hitstop", 0.08))
		var shake: float = float(seg.get("shake", 2.5))
		_hitstop = maxf(_hitstop, stop)
		hitstop_requested.emit(stop)
		shake_requested.emit(shake, 0.18)
	else:
		# 轻攻击：极短的顿帧，只够"顿一下"
		_hitstop = maxf(_hitstop, 0.04)
		hitstop_requested.emit(0.04)
		shake_requested.emit(1.2, 0.10)


func get_hitstop() -> float:
	return _hitstop


func _tick_hitstop(delta: float) -> void:
	_hitstop = maxf(_hitstop - delta, 0.0)


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
	# 链的单调时钟：用于按时间戳清理超窗元素
	_chain_time += delta
	# 获得道具动画：独立推进，优先级高于常规动画
	if _gain_anim_timer > 0.0:
		_gain_anim_timer = maxf(_gain_anim_timer - delta, 0.0)
		if _anim and _anim.sprite_frames.has_animation("gain"):
			var p := 1.0 - _gain_anim_timer / GAIN_ANIM_DUR
			_anim.pause()
			_anim.frame = clampi(int(p * 6.0), 0, 5)
			if _gain_anim_timer <= 0.0:
				# 结束后恢复常规范式
				_anim.play("idle")

	_parry_window = maxf(_parry_window - delta, 0.0)

	_coyote = maxf(_coyote - delta, 0.0)
	_jump_buffer = maxf(_jump_buffer - delta, 0.0)
	_invuln = maxf(_invuln - delta, 0.0)
	_dash_cd = maxf(_dash_cd - delta, 0.0)
	_dash_invuln = maxf(_dash_invuln - delta, 0.0)
	if state != State.ATTACK:
		_combo_idle += delta
		_heavy_idle += delta
	# 顿帧倒计时（无论什么状态都要推进，否则会卡住）
	_tick_hitstop(delta)
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

	# 非攻击状态时，缓存的攻击输入在这里消费。
	# **重攻击优先**：玩家同时按住轻重时，「更重的那一下」是更明确的意图，
	# 而且重攻击打不出来会让玩家觉得按键没响应。
	if _heavy_buffer:
		_heavy_buffer = false
		start_heavy_attack()
		return

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
	# 获得道具动画期间不覆盖它的帧
	if _gain_anim_timer > 0.0:
		return
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
	var anim_name: String
	if is_heavy_attack:
		anim_name = "heavy%d" % (_heavy_index + 1)
	else:
		anim_name = "atk%d" % (_combo_index + 1)
	_current_anim = anim_name
	if _anim.sprite_frames.has_animation(anim_name):
		_anim.play(anim_name)
		_anim.pause()
		_anim.frame = 0


func _animate_attack(progress: float) -> void:
	if is_heavy_attack:
		_animate_heavy(progress)
		return
	# 轻攻击 6 帧：0 蓄势 / 1 起手 / 2 加速 / 3 命中 / 4 收势 / 5 回位
	# 命中帧（3）要落在 COMBO 的 hit_on..hit_off 窗口内，
	# 否则会出现「动画已经打完了判定才开」的错位感。
	var f := 0
	if progress >= 0.88:
		f = 5
	elif progress >= 0.72:
		f = 4
	elif progress >= 0.42:
		f = 3
	elif progress >= 0.26:
		f = 2
	elif progress >= 0.12:
		f = 1
	_anim.pause()
	_anim.frame = f


func _animate_heavy(progress: float) -> void:
	"""重攻击 8 帧：0 起势 / 1-2 长蓄力 / 3 加速 / 4 命中 / 5 余震 / 6 收势 / 7 回位。

	与轻攻击相比，蓄力占的比例明显更大（0~0.40 都还在准备），
	这是「重」的时间感来源；命中帧落在 hit_on（0.20~0.34）之后，
	保证「看到蓄力 → 打出去」的因果清晰。
	"""
	var f := 0
	if progress >= 0.90:
		f = 7
	elif progress >= 0.78:
		f = 6
	elif progress >= 0.62:
		f = 5
	elif progress >= 0.40:
		f = 4
	elif progress >= 0.28:
		f = 3
	elif progress >= 0.18:
		f = 2
	elif progress >= 0.08:
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
	damaged.emit(amount)
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
