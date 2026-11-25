extends SceneTree
func _init() -> void:
	DisplayServer.window_set_flag(DisplayServer.WINDOW_FLAG_ALWAYS_ON_TOP, false)
	DisplayServer.window_set_flag(DisplayServer.WINDOW_FLAG_BORDERLESS, true)
	DisplayServer.window_set_size(Vector2i(960, 540))
	var screen := DisplayServer.screen_get_usable_rect()
	DisplayServer.window_set_position(Vector2i(
		screen.position.x + screen.size.x - 960,
		screen.position.y + screen.size.y - 540))
	var boot: PackedScene = load("res://scenes/bootstrap.tscn")
	var b = boot.instantiate()
	root.add_child(b)
	await process_frame
	await process_frame
	for i in 50:
		await process_frame
	var player = null
	for n in get_nodes_in_group("player"): player = n
	for n in b.get_children():
		if n is CanvasLayer and n.layer >= 80: n.visible = false
	player.global_position = Vector2(400, 430)
	for i in 60:
		await process_frame
	await RenderingServer.frame_post_draw
	root.get_viewport().get_texture().get_image().save_png(
		ProjectSettings.globalize_path("res://art/screenshots/score_pass.png"))
	print("done")
	quit(0)
