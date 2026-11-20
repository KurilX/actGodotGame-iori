extends Node
## 启动场景：直接进灰盒测试房，跳过菜单
##
## 挂载两个 UI 层：
##   TouchLayer  触屏虚拟按键（默认隐藏）
##   ComboLayer  连击条（右侧，默认隐藏，有连击时出现）

const TouchControls := preload("res://src/ui/touch_controls.gd")
const ComboMeter := preload("res://src/ui/combo_meter.gd")


func _ready() -> void:
	var room_scene: PackedScene = load("res://scenes/rooms/room_greybox.tscn")
	var room := room_scene.instantiate()
	add_child(room)

	# ── 连击条：layer 90，在触屏按键（100）之下 ──
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

	# ── 连接连击信号 ──
	# 房间是异步建好玩家再 spawn 的，等一帧确保 player 已存在
	await get_tree().process_frame
	_connect_combo(room, combo)


func _connect_combo(room: Node, combo: Control) -> void:
	var player := _find_player(room)
	if player == null:
		printerr("连击条：未找到玩家，信号未连接")
		return

	# 命中敌人 → 累加段数。重攻击一段值 2 段。
	player.hit_landed.connect(func(_target: Node, damage: int) -> void:
		# damage 是本次命中的伤害值。轻攻击 1~3，重攻击 5~12。
		# 用伤害值当权重的简化版：>=4 视为重击（+2 段），否则 +1。
		var weight := 2 if damage >= 4 else 1
		combo.register_hit(weight)
	)

	# 玩家受伤 → 连击清零
	player.damaged.connect(func(_amount: int) -> void:
		combo.reset_combo()
	)


func _find_player(node: Node) -> Node:
	if node.is_in_group("player"):
		return node
	for c in node.get_children():
		var r := _find_player(c)
		if r != null:
			return r
	return null
