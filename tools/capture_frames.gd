extends SceneTree
## 逐帧截图：绕过攻击时序，直接把角色摆到指定动画帧再截。
##
## 为什么要这样：用 start_attack() 驱动时，截图需要 await 若干帧，
## 而攻击逻辑每帧都在改 _anim.frame，抓到的常常不是目标帧。
## 直接 set_anim(animation, frame) 并暂停，能得到确定的画面。
##
## 运行：godot --path . --script tools/capture_frames.gd

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

	# 站到木桩左侧
	player.global_position = dummy.global_position + Vector2(-20, 0)
	player.facing = 1
	for i in 20:
		await process_frame

	var anim: AnimatedSprite2D = player.get_node("Visual/AnimatedSprite2D")
	var slash = _find_script(root, "slash_sprite")

	# 四段 × 6 帧，全部截一遍；重点看命中帧（index 3）
	var clips := [
		["atk1", "01_上挑"],
		["atk2", "02_横斩"],
		["atk3", "03_突刺"],
		["atk4", "04_跳劈"],
	]

	for clip in clips:
		var aname: String = clip[0]
		var label: String = clip[1]
		for f in 6:
			anim.play(aname)
			anim.pause()
			anim.frame = f
			# 命中帧（3）显示刀光，其余帧不显示，方便单独看姿态
			if slash:
				slash.visible = (f == 3)
				if f == 3:
					slash.spawn(player.global_position + Vector2(4, -22),
								clips.find(clip), 1)
					slash.visible = true
			for i in 3:
				await process_frame
			await _shoot("%s_f%d" % [label, f])
			if slash:
				slash.visible = false

	print("逐帧截图完成")
	quit(0)


func _shoot(tag: String) -> void:
	for i in 2:
		await process_frame
	await RenderingServer.frame_post_draw
	var img := root.get_viewport().get_texture().get_image()
	img.save_png(ProjectSettings.globalize_path("%s/frame_%s.png" % [SHOT_DIR, tag]))
	print("  saved frame_%s.png" % tag)


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
