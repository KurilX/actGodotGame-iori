extends "res://src/enemies/enemy_base.gd"
## 石守（stonepaw）：精英级重甲敌人
##
## 定位：教玩家「用重攻击破霸体」。血厚、抗击退、攻击前摇长但伤害高。
## 行为：缓慢逼近 → 抡砸 → 长硬直（这是玩家的输出窗口）。
##
## 关键设计：它的重击前摇 0.6s 很长，但攻击范围大、伤害 2。
## 玩家硬拼会吃亏，正确做法是闪避后趁硬直打重攻击。

var _armor_timer := 0.0


func _ready() -> void:
	max_hp = 26                 # 血最厚
	move_speed = 26.0           # 最慢
	detect_range = 280.0
	attack_range = 38.0         # 攻击范围大
	attack_cooldown = 2.2
	windup_time = 0.60          # 最长的前摇，明确可读
	attack_time = 0.34
	recover_time = 0.70         # 最长的收招窗口
	damage = 2                  # 伤害最高
	knockback_resist = 3.0      # 抗击退，轻攻击几乎打不动
	can_fly = false
	attack_box = Vector4(34, 30, 18, -20)
	sprite_name = "stonepaw"

	# ── 远程：掷石块 ──
	# 定位：**重甲远程**。它近战要贴身、远程也打得远，
	# 逼玩家在"贴近吃抡砸"和"拉远吃石头"之间选。
	# 石块比毒弹快（150）、更大（radius 6），但冷却长（3.4s），
	# 因为石守血厚、站桩时间长，不需要频繁远程。
	ranged_enabled = true
	ranged_cooldown = 3.4
	ranged_speed = 150.0
	ranged_damage = 2
	ranged_radius = 6.0
	ranged_windup = 0.62        # 最长前摇：它动作慢，可读性强
	ranged_min_dist = 90.0
	ranged_max_dist = 300.0
	super._ready()


func take_hit(amount: int, from_x: float) -> void:
	# 石守的「霸体」：只有重攻击（伤害>=4）才能打断它的动作。
	# 轻攻击打上去只掉血、不打断 —— 这就是设计上要求玩家用重攻击的原因。
	if amount < 4 and state in [State.WINDUP, State.ATTACK]:
		hp -= amount
		_flash = 0.14
		queue_redraw()
		if hp <= 0:
			hp = 0
			_die()
		return          # 不进入 HURT，动作继续
	super.take_hit(amount, from_x)
