extends SceneTree
## 截取重攻击三连的每一帧（游戏内实际渲染）
##
## 运行：godot --path . --script tools/capture_heavy.gd

const SHOT_DIR := "res://art/screenshots"


func _init() -> void:
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(SHOT_DIR))
	DisplayServer.window_set_flag(DisplayServer.WINDOW_FLAG_ALWAYS_ON_TOP, false)
	DisplayServer.window_set_flag(DisplayServer.WINDOW_FLAG_BORDERLESS, true)
	DisplayServer.window_set_size(Vector2i(960, 540))
	var screen := DisplayServer.screen_get_usable_rect()
	DisplayServer.window_set_position(Vector2i(
		screen.position.x + screen.size.x - 960,
		screen.position.y + screen.size.y - 540))

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

	player.global_position = dummy.global_position + Vector2(-24, 0)
	player.facing = 1
	for i in 20:
		await process_frame

	var anim: AnimatedSprite2D = player.get_node("Visual/AnimatedSprite2D")
	var slash = _find_script(root, "slash_sprite")

	# 三段各截 8 帧；命中帧（4）额外叠刀光
	for seg in 3:
		for f in 8:
			anim.play("heavy%d" % (seg + 1))
			anim.pause()
			anim.frame = f

			# 命中帧显示刀光，其余帧不显示，便于单独看姿态
			if slash:
				slash.visible = (f == 4)
				if f == 4:
					slash.spawn(player.global_position + Vector2(4, -22),
								seg, 1, "heavy", 0.075)
					slash.visible = true
			for i in 3:
				await process_frame
			await _shoot("h%d_f%d" % [seg + 1, f])
			if slash:
				slash.visible = false

	print("重攻击截图完成")
	quit(0)


func _shoot(tag: String) -> void:
	for i in 2:
		await process_frame
	await RenderingServer.frame_post_draw
	var img := root.get_viewport().get_texture().get_image()
	img.save_png(ProjectSettings.globalize_path("%s/heavy_%s.png" % [SHOT_DIR, tag]))
	print("  saved heavy_%s.png" % tag)


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
