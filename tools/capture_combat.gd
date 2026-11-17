extends SceneTree
## 抓取战斗画面：四连攻击 + 闪避
##
## 运行：godot --path . --script tools/capture_combat.gd
## 输出：art/screenshots/combat_*.png

const SHOT_DIR := "res://art/screenshots"


func _init() -> void:
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(SHOT_DIR))
	DisplayServer.window_set_flag(DisplayServer.WINDOW_FLAG_ALWAYS_ON_TOP, false)
	DisplayServer.window_set_flag(DisplayServer.WINDOW_FLAG_BORDERLESS, true)
	DisplayServer.window_set_size(Vector2i(480, 270))
	var screen := DisplayServer.screen_get_usable_rect()
	DisplayServer.window_set_position(Vector2i(
		screen.position.x + screen.size.x - 480,
		screen.position.y + screen.size.y - 270))

	var boot: PackedScene = load("res://scenes/bootstrap.tscn")
	root.add_child(boot.instantiate())
	await process_frame
	await process_frame

	var player = _find_player(root)
	var dummy = _find_script(root, "training_dummy")
	if player == null or dummy == null:
		printerr("未找到 player 或 dummy")
		quit(1)
		return

	for i in 90:
		await process_frame

	# 站到木桩左侧近处
	player.global_position = dummy.global_position + Vector2(-18, 0)
	player.facing = 1
	for i in 20:
		await process_frame
	await _shoot("01_待机面对木桩")

	# 四连连段：在刀光出现的那一帧抓图（刀光生命周期约 0.135s）
	for seg in 4:
		player.start_attack()
		# 等刀光节点真正激活
		var waited := 0
		while waited < 30:
			await process_frame
			waited += 1
			if _slash_active(root):
				break
		await process_frame
		await _shoot("02_第%d段" % (seg + 1))
		for i in 30:
			await process_frame

	# 等木桩复活
	for i in 90:
		await process_frame

	# 闪避
	player.global_position = dummy.global_position + Vector2(-50, 0)
	for i in 20:
		await process_frame
	Input.action_press("dash")
	await process_frame
	Input.action_release("dash")
	for i in 4:
		await process_frame
	await _shoot("03_闪避冲刺")

	print("战斗截图完成")
	quit(0)


func _shoot(tag: String) -> void:
	for i in 2:
		await process_frame
	await RenderingServer.frame_post_draw
	var img := root.get_viewport().get_texture().get_image()
	img.save_png(ProjectSettings.globalize_path("%s/combat_%s.png" % [SHOT_DIR, tag]))
	print("  saved combat_%s.png (%dx%d)" % [tag, img.get_width(), img.get_height()])


func _slash_active(node: Node) -> bool:
	# 找到 SlashLayer 并读它的激活状态
	if node is Sprite2D and node.name == "SlashLayer":
		return node.visible
	for c in node.get_children():
		if _slash_active(c):
			return true
	return false


func _find_player(node: Node):
	if node is CharacterBody2D:
		return node
	for c in node.get_children():
		var r = _find_player(c)
		if r:
			return r
	return null


func _find_script(node: Node, name: String):
	var s = node.get_script()
	if s != null and str(s.resource_path).contains(name):
		return node
	for c in node.get_children():
		var r = _find_script(c, name)
		if r:
			return r
	return null
