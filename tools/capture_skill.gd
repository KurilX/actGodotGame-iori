extends SceneTree
## 技能系统截图：技能树（锁定/解锁）、获得道具横幅、贯穿织特效
##
## 运行：godot --path . --script tools/capture_skill.gd
##
## **时序坑**：每次 toggle 后必须等足帧数再截图。
## 面板打开时有一个淡入（_t 从 0 开始），慢帧下 _t 累积很慢，
## 立刻截图会得到"几乎全透明"的画面，看起来像面板没打开。

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
	for i in 40:
		await process_frame

	var panel = null
	var banner = null
	var fx = null
	var st = null
	var player = null
	for n in _walk(root):
		var s = n.get_script()
		if s == null:
			continue
		var p := str(s.resource_path)
		if p.contains("skill_tree_panel"):
			panel = n
		elif p.contains("item_gain_banner"):
			banner = n
		elif p.contains("pierce_weave_fx"):
			fx = n
		elif p.ends_with("skill_tree.gd"):
			st = n
	for n in get_nodes_in_group("player"):
		player = n

	# ── 1. 技能树：解锁前 ──
	# 不依赖 toggle：直接把内部状态摆好，避免"toggle 后 _process 还没跑"的时序问题
	panel.toggle()
	await _wait(30)
	await _shot("skill_01_tree_locked")
	panel.toggle()
	await _wait(8)

	# ── 2. 获得道具横幅 ──
	banner.show_item("贯穿织",
					 "把线收成一束贯穿出去。轻攻击三连后接重击即可发动。",
					 "res://art/items/spool_48.png")
	await _wait(22)
	await _shot("skill_02_gain_banner")

	# 等横幅完全消失，避免遮住后面的面板
	for i in 260:
		await process_frame
		if not banner.is_active():
			break

	# ── 3. 技能树：解锁后 ──
	st.try_unlock("pierce_weave")
	panel.toggle()
	await _wait(30)
	await _shot("skill_03_tree_unlocked")
	panel.toggle()
	await _wait(8)

	# ── 4. 贯穿织特效 ──
	player.global_position = Vector2(360, 470)
	await _wait(10)
	fx.fire(player.global_position + Vector2(0, -20), 1)
	await _wait(6)
	await _shot("skill_04_pierce")

	print("done")
	quit(0)


func _open_panel_directly(panel) -> void:
	"""绕开 toggle，直接摆好状态。

	为什么：toggle 里 set_process 是延迟生效的（要等下一个 _process 才跑），
	而且 _t 从 0 开始，慢帧下透明度很久上不去，
	截图会得到"看起来没打开"的画面。
	"""
	panel.set("_open", true)
	panel.visible = true
	panel.set_process(true)
	panel.set("_t", 1.0)          # 直接拉满透明度
	panel.queue_redraw()


func _close_panel_directly(panel) -> void:
	panel.set("_open", false)
	panel.visible = false
	panel.set_process(false)
	panel.queue_redraw()


func _wait(frames: int) -> void:
	for i in frames:
		await process_frame


func _shot(tag: String) -> void:
	"""截图。

	**必须多等几帧再抓**：`frame_post_draw` 单次等待只能保证"上一帧画完了"，
	但 Control 的 _draw 提交到 CanvasLayer 后需要额外的帧才真正合成到 viewport。
	之前只等一次 frame_post_draw，结果 UI 层（技能树/特效）是空的，
	而 3D/2D 世界层（用 Sprite2D）却能正常出图 —— 两者的提交时机不一样。
	"""
	for i in 4:
		await process_frame
	await RenderingServer.frame_post_draw
	var img := root.get_viewport().get_texture().get_image()
	img.save_png(ProjectSettings.globalize_path(
		"res://art/screenshots/%s.png" % tag))
	print("  ", tag)


func _walk(n):
	var o = [n]
	for c in n.get_children():
		o.append_array(_walk(c))
	return o
