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
	detect_range = 140.0
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
