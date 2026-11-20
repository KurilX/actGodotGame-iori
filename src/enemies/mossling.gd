extends "res://src/enemies/enemy_base.gd"
## 苔团（mossling）：最基础的近战敌人
##
## 定位：教学敌人。血薄、移动慢、攻击前摇长，让玩家学会「看前摇 → 闪避/打断」。
## 行为：发现玩家 → 弹跳靠近 → 贴身冲撞。

func _ready() -> void:
	max_hp = 12
	move_speed = 34.0
	detect_range = 130.0
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
	super._ready()
