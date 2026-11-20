extends SceneTree
## 录制实拍序列帧：完美闪避子弹时间 → 连击 + 空挥扣段
##
## 运行：godot --path . --script tools/record_bullet_time.gd
## 输出：art/recordings/bullet_time/0000.png ... + meta.txt（每帧真实时间戳）
##
## 之后用 tools/make_bullet_time_gif.py 合成 GIF。
##
## 关键：子弹时间会改 Engine.time_scale，所以时间戳必须用
## Time.get_ticks_msec()（真实时间），不能用 delta 累加。

const OUT_DIR := "res://art/recordings/bullet_time"

var _frame_idx := 0
var _stamps: Array[int] = []
var _recording := false


func _init() -> void:
	# 清理旧帧
	var abs_dir := ProjectSettings.globalize_path(OUT_DIR)
	if DirAccess.dir_exists_absolute(abs_dir):
		for f in DirAccess.get_files_at(abs_dir):
			DirAccess.remove_absolute(os_path_join(abs_dir, f))
	DirAccess.make_dir_recursive_absolute(abs_dir)

	# 窗口：小窗、无边框、不置顶（不抢焦点）
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

	var player = _find_player(root)
	var combo = _find_script(root, "combo_meter")
	var bt = _find_script(root, "bullet_time_fx")
	if player == null or combo == null:
		printerr("缺 player 或 combo_meter")
		quit(1)
		return

	print("开始录制…")
	_recording = true
	_recording_loop()          # 后台持续抓帧

	# ── 编排一段有代表性的操作 ──
	# 1) 先打两下，建立连击
	combo.register_hit(1)
	combo.register_hit(1)
	await _wait_ms(500)

	# 2) 空挥一次，看扣段
	combo.register_whiff(false)
	await _wait_ms(700)

	# 3) 再打两下，回到有连击的状态
	combo.register_hit(1)
	combo.register_hit(1)
	await _wait_ms(500)

	# 4) 完美闪避 → 子弹时间
	bt.trigger(player.global_position, _find_camera(player))
	await _wait_ms(1400)       # 覆盖 600ms 的子弹时间 + 恢复

	# 5) 子弹时间结束后的余韵
	combo.register_hit(2)
	await _wait_ms(900)

	_recording = false
	await process_frame

	# 写时间戳
	var meta := PackedStringArray()
	for t in _stamps:
		meta.append(str(t))
	var f := FileAccess.open(os_path_join(
		ProjectSettings.globalize_path(OUT_DIR), "meta.txt"), FileAccess.WRITE)
	if f:
		f.store_string("\n".join(meta))
		f.close()

	print("录完 %d 帧" % _frame_idx)
	quit(0)


func os_path_join(a: String, b: String) -> String:
	return a.rstrip("/").rstrip("\\") + "/" + b


func _recording_loop() -> void:
	"""每个渲染帧抓一张图。用递归 await 而不是 while，
	避免阻塞主循环。"""
	while _recording:
		await RenderingServer.frame_post_draw
		if not _recording:
			break
		var img := root.get_viewport().get_texture().get_image()
		if img == null:
			continue
		var path := os_path_join(ProjectSettings.globalize_path(OUT_DIR),
								 "%04d.png" % _frame_idx)
		img.save_png(path)
		_stamps.append(Time.get_ticks_msec())
		_frame_idx += 1


func _wait_ms(ms: int) -> void:
	# 用真实时间等待，不受 time_scale 影响
	var t0 := Time.get_ticks_msec()
	while Time.get_ticks_msec() - t0 < ms:
		await process_frame


func _find_player(node: Node):
	if node.is_in_group("player"):
		return node
	for c in node.get_children():
		var r = _find_player(c)
		if r:
			return r
	return null


func _find_camera(node: Node):
	for c in node.get_children():
		if c is Camera2D:
			return c
		var r = _find_camera(c)
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
