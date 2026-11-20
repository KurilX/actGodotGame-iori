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
const BossHealthBar := preload("res://src/ui/boss_healthbar.gd")


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

	# ── BOSS 血条：layer 85 ──
	var boss_layer := CanvasLayer.new()
	boss_layer.name = "BossBarLayer"
	boss_layer.layer = 85
	add_child(boss_layer)

	var bossbar := Control.new()
	bossbar.name = "BossHealthBar"
	bossbar.set_script(BossHealthBar)
	boss_layer.add_child(bossbar)

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
	_connect_boss(room, bossbar)
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


func _connect_boss(room: Node, bossbar: Control) -> void:
	"""连接 BOSS 血条。

	BOSS 是在 room 的 _ready 里异步 spawn 的，所以要等一下。
	"""
	var boss: Node = room.get("boss")
	if boss == null:
		# 再等一帧试试（room 可能在 _spawn_boss 前还没赋值）
		await get_tree().process_frame
		boss = room.get("boss")
	if boss == null:
		printerr("BOSS 血条：未找到 BOSS")
		return

	bossbar.show_boss("瓷面的守夜人")
	bossbar.set_hp(1.0)

	# 血量变化 → 更新血条
	# 用轮询而不是信号：hp 是普通变量，BOSS 内部改它时不发信号
	bossbar.set_process(true)
	var update := func() -> void:
		if boss == null or not is_instance_valid(boss):
			bossbar.hide_boss()
			return
		var ratio: float = float(boss.get("hp")) / float(boss.get("max_hp"))
		bossbar.set_hp(ratio)
		var ph: int = boss.get("phase")
		if ph != bossbar.get_phase():
			bossbar.set_phase(ph)
	# 每帧更新（开销极小，只有一个浮点除法）
	bossbar.set_meta("updater", update)

	# 用 _process 驱动
	var timer := Timer.new()
	timer.wait_time = 0.05
	timer.autostart = true
	timer.timeout.connect(update)
	bossbar.add_child(timer)


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
