extends "res://src/enemies/enemy_base.gd"
## 苔团（mossling）：最基础的近战敌人
##
## 定位：教学敌人。血薄、移动慢、攻击前摇长，让玩家学会「看前摇 → 闪避/打断」。
## 行为：发现玩家 → 弹跳靠近 → 贴身冲撞。

func _ready() -> void:
	max_hp = 12
	move_speed = 34.0
	detect_range = 280.0
	attack_range = 30.0
	attack_cooldown = 1.35
	windup_time = 0.42          # 前摇很长，新手也能反应
	attack_time = 0.26
	recover_time = 0.30
	damage = 1
	knockback_resist = 0.8      # 很轻，容易被打飞
	can_fly = false
	attack_box = Vector4(26, 20, 16, -14)
	sprite_name = "mossling"

	# ── 远程：吐毒弹 ──
	# 定位：**全场第一个教弹反的对象**。
	# 慢速（95）让玩家有充裕时间反应，前摇 0.5s 也够长。
	# 冷却最短（2.4s），因为它血薄、打得快，需要频繁给可弹反的机会。
	ranged_enabled = true
	ranged_cooldown = 2.4
	ranged_speed = 95.0
	ranged_damage = 1
	ranged_radius = 4.0
	ranged_windup = 0.50
	ranged_min_dist = 80.0
	ranged_max_dist = 240.0

	super._ready()
