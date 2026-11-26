extends SceneTree
## 抓取三张实机截图（视差背景 + 地形 + 角色 + 敌人）。
##
## 运行：godot --path . --script tools/cap_par.gd -- --autoplay
##
## 供 tools/ai_art_score.py 在评分前调用，确保 AI 评的是**当前**画面，
## 而不是若干小时前的缓存图。
##
## 三个位置覆盖关卡三段：教程起点 / 跳跃台阶 / BOSS 房。

const SHOTS := [
	[400.0, "par_x400"],
	[1200.0, "par_x1200"],
	[2000.0, "par_x2000"],
]


func _init() -> void:
	# 窗口缩到 960x540，放右下角，不抢焦点
	DisplayServer.window_set_flag(
		DisplayServer.WINDOW_FLAG_ALWAYS_ON_TOP, false)
	DisplayServer.window_set_flag(DisplayServer.WINDOW_FLAG_BORDERLESS, true)
	DisplayServer.window_set_size(Vector2i(960, 540))
	var screen := DisplayServer.screen_get_usable_rect()
	DisplayServer.window_set_position(Vector2i(
		screen.position.x + screen.size.x - 960,
		screen.position.y + screen.size.y - 540))

	var boot: PackedScene = load("res://scenes/bootstrap.tscn")
	if boot == null:
		printerr("找不到 bootstrap.tscn")
		quit(1)
		return
	var b = boot.instantiate()
	root.add_child(b)
	await process_frame
	await process_frame
	# 等关卡与背景初始化
	for i in 50:
		await process_frame

	var player = null
	for n in get_nodes_in_group("player"):
		player = n
	if player == null:
		printerr("找不到玩家")
		quit(1)
		return

	# 隐藏 UI/触屏层，只留游戏画面（评分只看美术）
	for n in b.get_children():
		if n is CanvasLayer and n.layer >= 80:
			n.visible = false

	# 隐藏前摇预警 FX：那是"战斗反馈"不是"美术"，
	# 截图瞬间恰好抓到 BOSS 蓄力的话，画面上会有一圈半透明粉色圆，
	# AI 会判成"未清理的占位/特效框"（实测 R5 BOSS 房 77 分被它拖累）
	for n in get_nodes_in_group("warning_fx"):
		n.visible = false

	for shot in SHOTS:
		player.global_position = Vector2(shot[0], 430)
		# 等相机平滑跟上
		for i in 60:
			await process_frame
		await RenderingServer.frame_post_draw
		var img := root.get_viewport().get_texture().get_image()
		var path := "res://art/screenshots/%s.png" % shot[1]
		img.save_png(ProjectSettings.globalize_path(path))
		print("  抓取 " + shot[1])

	quit(0)
