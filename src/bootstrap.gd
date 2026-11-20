extends Node
## 启动场景：直接进灰盒测试房，跳过菜单
##
## 挂载三个 UI 层：
##   BulletTimeLayer  子弹时间特效（layer 80，在游戏画面之上）
##   ComboLayer       连击条（layer 90，右侧）
##   TouchLayer       触屏虚拟按键（layer 100，默认隐藏）

const TouchControls := preload("res://src/ui/touch_controls.gd")
const ComboMeter := preload("res://src/ui/combo_meter.gd")
const BulletTimeFx := preload("res://src/ui/bullet_time_fx.gd")


func _ready() -> void:
	var room_scene: PackedScene = load("res://scenes/rooms/room_greybox.tscn")
	var room := room_scene.instantiate()
	add_child(room)

	# ── 子弹时间特效：layer 80，盖在游戏画面之上、连击条之下 ──
	var bt_layer := CanvasLayer.new()
	bt_layer.name = "BulletTimeLayer"
	bt_layer.layer = 80
	add_child(bt_layer)

	var bt := Control.new()
	bt.name = "BulletTimeFx"
	bt.set_script(BulletTimeFx)
	bt_layer.add_child(bt)

	# ── 连击条：layer 90 ──
	var combo_layer := CanvasLayer.new()
	combo_layer.name = "ComboLayer"
	combo_layer.layer = 90
	add_child(combo_layer)

	var combo := Control.new()
	combo.name = "ComboMeter"
	combo.set_script(ComboMeter)
	combo_layer.add_child(combo)

	# ── 触屏按键：layer 100 ──
	var touch_layer := CanvasLayer.new()
	touch_layer.name = "TouchLayer"
	touch_layer.layer = 100
	add_child(touch_layer)

	var touch := Control.new()
	touch.name = "TouchControls"
	touch.set_script(TouchControls)
	touch_layer.add_child(touch)

	# ── 连接信号 ──
	await get_tree().process_frame
	_connect(room, combo, bt)


func _connect(room: Node, combo: Control, bt: Control) -> void:
	var player := _find_player(room)
	if player == null:
		printerr("UI：未找到玩家，信号未连接")
		return

	# 命中 → 累加段数。重攻击（伤害>=4）值 2 段。
	player.hit_landed.connect(func(_target: Node, damage: int) -> void:
		var weight := 2 if damage >= 4 else 1
		combo.register_hit(weight)
	)

	# 空挥 → 扣段
	player.whiffed.connect(func(heavy: bool) -> void:
		combo.register_whiff(heavy)
	)

	# 受伤 → 连击清零
	player.damaged.connect(func(_amount: int) -> void:
		combo.reset_combo()
	)

	# 完美闪避 → 子弹时间特效 + 连击加成
	var cam := _find_camera(player)
	player.perfect_dodge.connect(func() -> void:
		bt.trigger(player.global_position, cam)
		combo.register_perfect_dodge()
	)


func _find_player(node: Node) -> Node:
	if node.is_in_group("player"):
		return node
	for c in node.get_children():
		var r := _find_player(c)
		if r != null:
			return r
	return null


func _find_camera(node: Node) -> Camera2D:
	for c in node.get_children():
		if c is Camera2D:
			return c
		var r := _find_camera(c)
		if r != null:
			return r
	return null
