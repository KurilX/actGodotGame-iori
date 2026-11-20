extends SceneTree
func _init() -> void:
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path("res://art/screenshots"))
	DisplayServer.window_set_flag(DisplayServer.WINDOW_FLAG_ALWAYS_ON_TOP, false)
	DisplayServer.window_set_flag(DisplayServer.WINDOW_FLAG_BORDERLESS, true)
	DisplayServer.window_set_size(Vector2i(1280, 720))
	var screen := DisplayServer.screen_get_usable_rect()
	DisplayServer.window_set_position(Vector2i(
		screen.position.x + screen.size.x - 1280,
		screen.position.y + screen.size.y - 720))

	var boot: PackedScene = load("res://scenes/bootstrap.tscn")
	root.add_child(boot.instantiate())
	await process_frame
	await process_frame
	for i in 60:
		await process_frame

	# 把玩家挪到能同时看到三个敌人的位置
	var player = null
	for n in get_nodes_in_group("player"): player = n
	player.global_position = Vector2(430, 470)
	for i in 40:
		await process_frame
	await _shoot("enemies_01_scene")

	# 朝最近敌人走，抓战斗画面
	Input.action_press("move_right")
	for i in 90:
		await process_frame
	Input.action_release("move_right")
	for i in 30:
		await process_frame
	await _shoot("enemies_02_approach")

	# 攻击
	Input.action_press("heavy")
	for i in 10:
		await process_frame
	await _shoot("enemies_03_heavy")
	Input.action_release("heavy")
	for i in 40:
		await process_frame
	await _shoot("enemies_04_after")

	print("done")
	quit(0)

func _shoot(tag: String) -> void:
	for i in 3:
		await process_frame
	await RenderingServer.frame_post_draw
	var img := root.get_viewport().get_texture().get_image()
	img.save_png(ProjectSettings.globalize_path("res://art/screenshots/%s.png" % tag))
	print("  saved ", tag)
