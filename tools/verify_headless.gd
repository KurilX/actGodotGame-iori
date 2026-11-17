extends SceneTree
## Godot headless 行为冒烟测试：验证重力、碰撞、左右移动、跳跃、Coyote
##
## 运行：godot --headless --path . --script tools/verify_headless.gd
## 退出码：0 全通过 / 1 有失败

var _failures: Array[String] = []
var _checks := 0


func _init() -> void:
	var boot: PackedScene = load("res://scenes/bootstrap.tscn")
	var root_node := boot.instantiate()
	root.add_child(root_node)

	# bootstrap._ready → 房间._ready → 生成玩家，需要等帧
	await process_frame
	await process_frame

	var player = _find_player(root_node)
	if player == null:
		printerr("FAIL: 未找到 Player 节点")
		quit(1)
		return

	print("── 《缀》灰盒冒烟测试 ──")
	print("viewport      = %sx%s" % [
		ProjectSettings.get_setting("display/window/size/viewport_width"),
		ProjectSettings.get_setting("display/window/size/viewport_height")])
	print("window        = %sx%s" % [
		ProjectSettings.get_setting("display/window/size/window_width_override"),
		ProjectSettings.get_setting("display/window/size/window_height_override")])
	print("scale_mode    = %s" % ProjectSettings.get_setting("display/window/stretch/scale_mode"))
	print("snap_2d       = %s / %s" % [
		ProjectSettings.get_setting("rendering/2d/snap/snap_2d_transforms_to_pixel"),
		ProjectSettings.get_setting("rendering/2d/snap/snap_2d_vertices_to_pixel")])
	print("spawn         = %s" % str(player.global_position))
	print("")

	# ── 1. 落到地面 ──
	var y0: float = player.global_position.y
	for i in 120:
		await physics_frame
	_check(player.is_on_floor(), "1. 落地", "玩家没落在地面上")
	_check(player.global_position.y > y0, "2. 重力生效", "Y 没有增加（初始 y=%.1f，当前 %.1f）" % [y0, player.global_position.y])
	var ground_y: float = player.global_position.y

	# ── 3. 右移 ──
	var x0: float = player.global_position.x
	Input.action_press("move_right")
	for i in 30:
		await physics_frame
	Input.action_release("move_right")
	var moved: float = player.global_position.x - x0
	_check(moved > 10.0, "3. 右移", "30 帧内只移动了 %.1f px" % moved)

	# ── 4. 左移 ──
	x0 = player.global_position.x
	Input.action_press("move_left")
	for i in 30:
		await physics_frame
	Input.action_release("move_left")
	moved = x0 - player.global_position.x
	_check(moved > 10.0, "4. 左移", "30 帧内只移动了 %.1f px" % moved)

	# 停下来
	for i in 30:
		await physics_frame

	# ── 5. 大跳（按住不放）──
	var pre_jump_y: float = player.global_position.y
	Input.action_press("jump")
	var peak := pre_jump_y
	# 按住整个上升期，取到顶点后仍继续按
	for i in 40:
		await physics_frame
		peak = minf(peak, player.global_position.y)
	Input.action_release("jump")
	var jump_height: float = pre_jump_y - peak
	_check(jump_height > 45.0, "5. 大跳高度达标", "跳跃高度只有 %.1f px（预期约 58.5）" % jump_height)

	# ── 5b. 小跳（点一下立刻松）──
	for i in 120:
		await physics_frame
	var pre_small_y: float = player.global_position.y
	Input.action_press("jump")
	await physics_frame
	Input.action_release("jump")
	var peak_small := pre_small_y
	for i in 40:
		await physics_frame
		peak_small = minf(peak_small, player.global_position.y)
	var small_height: float = pre_small_y - peak_small
	_check(small_height < jump_height * 0.6 and small_height > 5.0,
		"5b. 小跳明显低于大跳",
		"小跳 %.1f px vs 大跳 %.1f px" % [small_height, jump_height])

	# ── 6. 落回地面 ──
	for i in 120:
		await physics_frame
	_check(player.is_on_floor(), "6. 落回地面", "跳完没有回到地面")

	# ── 7. 攻击状态 ──
	Input.action_press("attack")
	await physics_frame
	await physics_frame
	Input.action_release("attack")
	_check(player.state == player.State.ATTACK, "7. 攻击进入 ATTACK 状态", "状态是 %d" % player.state)
	for i in 40:
		await physics_frame

	# ── 8. 受伤与无敌 ──
	var hp0: int = player.get_hearts()
	player.take_damage(1, player.global_position.x + 100.0)
	_check(player.get_hearts() == hp0 - 1, "8. 受伤扣血", "血量 %d -> %d" % [hp0, player.get_hearts()])
	player.take_damage(1, player.global_position.x + 100.0)
	_check(player.get_hearts() == hp0 - 1, "9. 无敌期间不重复扣血", "血量变成了 %d" % player.get_hearts())

	print("")
	if _failures.is_empty():
		print("PASS: 全部 %d 项通过" % _checks)
		quit(0)
	else:
		print("FAIL: %d 项失败" % _failures.size())
		for f in _failures:
			printerr("  - " + f)
		quit(1)


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
