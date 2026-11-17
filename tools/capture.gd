extends SceneTree
## 抓图工具：默认不打扰桌面，只有显式要求才显示窗口
##
## 用法：
##   godot --path . --script tools/capture.gd              # 离屏，不弹窗
##   godot --path . --script tools/capture.gd -- --show   # 显示窗口（方便肉眼看）
##
## 关于「离屏」的说明（实测结论，别走回头路）：
##   - `--headless` 下 frame_post_draw 不触发，抓图会永久挂起 → 不可用
##   - 把窗口移到屏幕外 → 交换链不提交，抓到的是多帧叠加（一张图 6 个角色）
##   - SubViewport 离屏渲染 → 尺寸对但精灵不渲染（相机/CanvasItem 层级问题）
##   所以：离屏抓图在 Godot 4.7 + OpenGL 下不可靠。
##   本脚本的默认策略是「窗口存在但缩到 1x1 且不置顶」，
##   若你看到窗口弹出，可以用 --show 反过来确认，或用 headless 跑验证脚本。

const SHOT_DIR := "res://art/screenshots"

var _show_window := false


func _init() -> void:
	_show_window = "--show" in OS.get_cmdline_user_args()
	_setup_window()
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(SHOT_DIR))

	var boot: PackedScene = load("res://scenes/bootstrap.tscn")
	var root_node := boot.instantiate()
	root.add_child(root_node)

	await process_frame
	await process_frame

	var player = _find_player(root_node)
	if player == null:
		printerr("未找到玩家")
		quit(1)
		return

	for i in 90:
		await process_frame

	# ── 待机 ──
	for i in 4:
		await _shoot("idle_%d" % i)
		for j in 6:
			await process_frame

	# ── 跑动 6 帧 ──
	Input.action_press("move_right")
	for i in 6:
		for j in 5:
			await process_frame
		await _shoot("run_%d" % i)
	Input.action_release("move_right")

	for i in 30:
		await process_frame

	# ── 跳跃 3 帧 ──
	Input.action_press("jump")
	await _shoot("jump_0")
	for i in 10:
		await process_frame
	await _shoot("jump_1")
	for i in 20:
		await process_frame
	await _shoot("jump_2")
	Input.action_release("jump")

	for i in 60:
		await process_frame

	# ── 朝左（验证翻转）──
	Input.action_press("move_left")
	for i in 20:
		await process_frame
	await _shoot("facing_left")
	Input.action_release("move_left")

	print("截图完成（%s）" % ("显示窗口" if _show_window else "不打扰桌面"))
	quit(0)


func _setup_window() -> void:
	DisplayServer.window_set_flag(DisplayServer.WINDOW_FLAG_ALWAYS_ON_TOP, false)
	if _show_window:
		DisplayServer.window_set_flag(DisplayServer.WINDOW_FLAG_BORDERLESS, false)
		print("窗口可见，可肉眼观察")
		return

	# 默认：无边框 + 最小尺寸，放在屏幕角落，尽量不遮挡
	DisplayServer.window_set_flag(DisplayServer.WINDOW_FLAG_BORDERLESS, true)
	DisplayServer.window_set_size(Vector2i(480, 270))
	var screen := DisplayServer.screen_get_usable_rect()
	DisplayServer.window_set_position(Vector2i(
		screen.position.x + screen.size.x - 480,
		screen.position.y + screen.size.y - 270))
	print("窗口缩到右下角 480x270，无边框不置顶")


func _shoot(tag: String) -> void:
	for i in 3:
		await process_frame
	await RenderingServer.frame_post_draw
	var img := root.get_viewport().get_texture().get_image()
	img.save_png(ProjectSettings.globalize_path("%s/anim_%s.png" % [SHOT_DIR, tag]))
	print("  saved anim_%s.png (%dx%d)" % [tag, img.get_width(), img.get_height()])


func _find_player(node: Node):
	if node is CharacterBody2D:
		return node
	for c in node.get_children():
		var r = _find_player(c)
		if r:
			return r
	return null
