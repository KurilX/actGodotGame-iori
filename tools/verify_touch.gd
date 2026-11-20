extends SceneTree
## 触屏按键验证：强制显示按键层，截图并模拟触摸事件
##
## 运行：godot --path . --script tools/verify_touch.gd
## 输出：art/screenshots/touch_*.png

const SHOT_DIR := "res://art/screenshots"

var _failures: Array[String] = []

# headless（无渲染）下不能截图：frame_post_draw 不触发会永久挂起。
# 用 --headless 运行时只跑逻辑断言。
var _no_render := DisplayServer.get_name() == "headless"
var _checks := 0


func _init() -> void:
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(SHOT_DIR))
	if not _no_render:
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

	var touch = _find_script(root, "touch_controls")
	var player = _find_player(root)

	print("── 触屏按键验证 ──")
	if touch == null:
		printerr("FAIL: 未找到触屏按键节点")
		quit(1)
		return

	# 按键现在**默认隐藏**（仅 URL ?touch=1 / 命令行 --touch / F2 打开）。
	# 这里先断言默认确实是关的，再手动打开验证布局与命中逻辑。
	_check(not touch.visible, "0. 默认不显示按键",
	       "刚进游戏时 visible=true，电脑上会显得冗余")

	touch.visible = true
	touch.queue_redraw()
	await process_frame
	await process_frame
	await _shoot("01_按键布局")

	# 检查按钮数量与位置
	var buttons: Array = touch._buttons
	_check(buttons.size() == 6, "1. 构造了 6 个按钮（含重击）",
	       "实际 %d 个" % buttons.size())

	# 逐个验证命中测试：按钮中心必须能命中自己
	var all_hit := true
	var bad := ""
	for b in buttons:
		var c: Vector2 = touch._button_center(b)
		var got: Dictionary = touch._hit_test(c)
		if got.is_empty() or got["id"] != b["id"]:
			all_hit = false
			bad = "%s 中心命中了 %s" % [b["id"], got.get("id", "空")]
			break
	_check(all_hit, "2. 每个按钮中心都能命中自己", bad)

	# 按钮之间不能重叠
	var overlap := false
	var ov := ""
	for i in buttons.size():
		for j in range(i + 1, buttons.size()):
			var a: Dictionary = buttons[i]
			var b: Dictionary = buttons[j]
			var dist: float = touch._button_center(a).distance_to(touch._button_center(b))
			var need: float = (a["r"] + b["r"]) * 1.15
			if dist < need:
				overlap = true
				ov = "%s 与 %s 距离 %.0f < %.0f" % [a["id"], b["id"], dist, need]
	_check(not overlap, "3. 按钮之间不重叠", ov)

	# 模拟按下「攻击」按钮，验证 InputMap 被触发
	var attack_btn: Dictionary = {}
	for b in buttons:
		if b["id"] == "attack":
			attack_btn = b
			break
	if not attack_btn.is_empty():
		var c: Vector2 = touch._button_center(attack_btn)
		var ev := InputEventScreenTouch.new()
		ev.index = 0
		ev.position = c
		ev.pressed = true
		touch._input(ev)
		await process_frame
		_check(Input.is_action_pressed("attack"),
		       "4. 触摸攻击键触发了 attack action",
		       "Input.is_action_pressed('attack') = false")
		await _shoot("02_攻击键按下")

		# 多点触控：再按左移，两个都要保持
		var left_btn: Dictionary = {}
		for b in buttons:
			if b["id"] == "left":
				left_btn = b
				break
		var ev2 := InputEventScreenTouch.new()
		ev2.index = 1
		ev2.position = touch._button_center(left_btn)
		ev2.pressed = true
		touch._input(ev2)
		await process_frame
		_check(Input.is_action_pressed("attack") and Input.is_action_pressed("move_left"),
		       "5. 多点触控同时生效（攻击+左移）",
		       "attack=%s left=%s" % [Input.is_action_pressed("attack"),
		                             Input.is_action_pressed("move_left")])
		await _shoot("03_多键同时按下")

		# 释放
		ev.pressed = false
		touch._input(ev)
		ev2.pressed = false
		touch._input(ev2)
		await process_frame
		_check(not Input.is_action_pressed("attack"),
		       "6. 松开后 action 被释放", "attack 仍按住")

	# ── 7/8. toggle 开关 + 关闭时必须释放按键 ──
	# 场景：按住攻击键的同时把按键层关掉，若不释放 action，
	# 角色会一直处于攻击状态（这是很隐蔽的卡手感 bug）
	var atk2: Dictionary = {}
	for b in buttons:
		if b["id"] == "attack":
			atk2 = b
			break
	var ev3 := InputEventScreenTouch.new()
	ev3.index = 5
	ev3.position = touch._button_center(atk2)
	ev3.pressed = true
	touch._input(ev3)
	await process_frame
	var held := Input.is_action_pressed("attack")

	touch.toggle()          # 关闭
	await process_frame
	_check(not touch.visible, "7. toggle 能关闭按键层", "visible 仍为 true")
	_check(not Input.is_action_pressed("attack"),
	       "8. 关闭时释放了按住的 action",
	       "按住状态下关闭，attack 仍为 pressed（会导致角色卡在攻击）")

	touch.toggle()          # 再打开，验证可逆
	await process_frame
	_check(touch.visible, "9. toggle 能再次打开", "visible 仍为 false")
	touch.visible = false
	touch._release_all()

	print("")
	if _failures.is_empty():
		print("PASS: 全部 %d 项通过" % _checks)
		quit(0)
	else:
		print("FAIL: %d 项失败" % _failures.size())
		for f in _failures:
			printerr("  - " + f)
		quit(1)


func _shoot(tag: String) -> void:
	if _no_render:
		return
	for i in 2:
		await process_frame
	await RenderingServer.frame_post_draw
	var img := root.get_viewport().get_texture().get_image()
	img.save_png(ProjectSettings.globalize_path("%s/touch_%s.png" % [SHOT_DIR, tag]))
	print("  saved touch_%s.png (%dx%d)" % [tag, img.get_width(), img.get_height()])


func _check(cond: bool, name: String, detail: String = "") -> void:
	_checks += 1
	if cond:
		print("  ok   %s" % name)
	else:
		print("  FAIL %s" % name)
		_failures.append(name + (": " + detail if detail != "" else ""))


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
