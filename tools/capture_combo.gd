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
	root.add_child(boot.instantiate())
	await process_frame
	await process_frame
	for i in 60:
		await process_frame

	var combo = _find_script(root, "combo_meter")
	var player = _find_player(root)
	var moss = null
	for e in get_nodes_in_group("enemy"):
		if "mossling" in str(e.name).to_lower(): moss = e

	# 站到苔团旁边
	player.global_position = moss.global_position + Vector2(-44, 0)
	for i in 20:
		await process_frame

	# 1) 无连击
	await _shot("combo_00_empty")

	# 2) 打出连击到 F
	for i in 2:
		combo.register_hit(1)
	for i in 10:
		await process_frame
	await _shot("combo_01_F")

	# 3) 连击到 C 级（10段）
	while combo.get_segments() < 10:
		combo.register_hit(1)
	for i in 10:
		await process_frame
	await _shot("combo_02_C")

	# 4) 连击到 SS
	while combo.get_rank_label() != "SS":
		combo.register_hit(1)
	for i in 10:
		await process_frame
	await _shot("combo_03_SS")

	# 5) 受击染色
	# 注意：不能"设好 _flash 再 await 几帧"——物理帧会递减 _flash，
	# 等截到图时染色已经衰减回白色了（第一版就是这样，两张图看起来一样）。
	# 正确做法：先清理渲染，再立刻设染色并截当前帧，中间不 await physics。
	moss._flash = moss.FLASH_DURATION
	moss._sync_hit_tint()
	await _shot_now("combo_04_hitflash")

	print("done")
	quit(0)

func _shot_now(tag: String) -> void:
	"""立刻截当前帧，不等物理帧（用于抓瞬时状态如受击染色）。"""
	await RenderingServer.frame_post_draw
	var img := root.get_viewport().get_texture().get_image()
	img.save_png(ProjectSettings.globalize_path("res://art/screenshots/%s.png" % tag))
	print("  ", tag)


func _shot(tag: String) -> void:
	for i in 3:
		await process_frame
	await RenderingServer.frame_post_draw
	var img := root.get_viewport().get_texture().get_image()
	img.save_png(ProjectSettings.globalize_path("res://art/screenshots/%s.png" % tag))
	print("  ", tag)

func _find_player(node):
	if node.is_in_group("player"): return node
	for c in node.get_children():
		var r = _find_player(c)
		if r: return r
	return null

func _find_script(node, name):
	var s = node.get_script()
	if s != null and str(s.resource_path).contains(name): return node
	for c in node.get_children():
		var r = _find_script(c, name)
		if r: return r
	return null
