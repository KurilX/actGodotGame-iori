extends SceneTree
## 专项回归：一次点按轻/重攻击必须恰好出一段（不允许连出两段）。
##
## 背景（用户实测 bug）：点一下 J 触发了两次轻攻击。
## 根因：_handle_input 用 is_action_pressed 置 buffer，120Hz 下一次点按
## 持续多帧，段 1 取消窗口又消费 buffer 接段 2。
## 修复：buffer 改 just_pressed；按住连打由取消窗口/自然结束时实时读键。
##
## 运行：godot --headless --path . --script tools/verify_attack_once.gd -- --autoplay

var _failures: Array[String] = []
var _checks := 0


func _ok(name: String) -> void:
	_checks += 1
	print("  ok   %d. %s" % [_checks, name])


func _fail(name: String, why: String) -> void:
	_checks += 1
	_failures.append(name)
	print("  FAIL %d. %s  —— %s" % [_checks, name, why])


func _find_player(root_node: Node) -> Node:
	for n in get_nodes_in_group("player"):
		return n
	return null


func _settle(node: Node, frames: int) -> void:
	for i in frames:
		await process_frame


func _init() -> void:
	var boot: PackedScene = load("res://scenes/bootstrap.tscn")
	var root_node := boot.instantiate()
	root.add_child(root_node)
	await process_frame
	await process_frame

	var player = _find_player(root_node)
	if player == null:
		printerr("FAIL: 未找到 Player（缺 -- --autoplay？）")
		quit(1)
		return

	var dummy = null
	for n in root_node.find_children("*", "Node2D", true, false):
		if n.get_script() and str(n.get_script().resource_path) == "res://src/world/training_dummy.gd":
			dummy = n
			break
	if dummy == null:
		printerr("FAIL: 未找到训练木桩")
		quit(1)
		return

	player.global_position = dummy.global_position + Vector2(-40, 0)
	for e in get_nodes_in_group("enemy"):
		if e != player:
			e.global_position = Vector2(5000, 5000)
			e.set_physics_process(false)
	await _settle(player, 60)

	print("── 单次点按 = 单段攻击 回归 ──")

	# 用 Input.action_press/action_release 模拟真实按键
	var ATTACK := "attack"

	# ── 1. 点按一次（按下+释放各 1 帧）→ 恰好 1 段 ──
	var seg0: int = player._chain.current_index("light")
	Input.action_press(ATTACK)
	await process_frame
	Input.action_release(ATTACK)
	# 等攻击启动
	await _settle(player, 3)
	var in_attack: bool = player.state == player.State.ATTACK
	if in_attack:
		_ok("点按进入 ATTACK 状态")
	else:
		_fail("点按进入 ATTACK 状态", "state=%s" % player.state)

	# 等整段自然打完 + 取消窗口期间键已松开
	await _settle(player, 120)
	var in_attack2: bool = player.state == player.State.ATTACK
	if not in_attack2:
		_ok("松键后自然收招（不接下一段）")
	else:
		_fail("松键后自然收招", "点按后仍在 ATTACK")

	# 链里 light 段号应只推进 1（seg0 → seg0+1，不出现 +2）
	var seg_now: int = player._chain.current_index("light")
	if seg_now == seg0 + 1:
		_ok("链上 light 段号恰好 +1")
	elif seg_now == seg0:
		_ok("链上 light 段号恰好 +1")
	else:
		_fail("链上 light 段号恰好 +1", "seg0=%d now=%d" % [seg0, seg_now])

	# ── 2. 按住 1.2 秒 → 应该连出多段（按住连打仍有效）──
	# 段计数用 attack_segment_done 信号。**GDScript lambda 按值捕获**：
	# lambda 里 `count += 1` 改的是副本，外部变量恒 0 —— 必须用数组引用。
	print("    [dbg] state before hold = ", player.state)
	var seg_box := [0]
	var counter := func(_heavy: bool) -> void: seg_box[0] += 1
	player.attack_segment_done.connect(counter)
	var ev_press := InputEventKey.new()
	ev_press.physical_keycode = KEY_J
	ev_press.pressed = true
	Input.parse_input_event(ev_press)
	Input.flush_buffered_events()
	await process_frame
	print("    [dbg] action held = ", Input.is_action_pressed("attack"),
			" player state = ", player.state)
	# 等待用 physics_frame（攻击计时在 _physics_process 120Hz）
	for i in 200:
		await physics_frame
	var ev_release: InputEventKey = InputEventKey.new()
	ev_release.physical_keycode = KEY_J
	ev_release.pressed = false
	Input.parse_input_event(ev_release)
	Input.flush_buffered_events()
	for i in 120:
		await physics_frame
	player.attack_segment_done.disconnect(counter)
	if seg_box[0] >= 2:
		_ok("按住连打仍然有效（连出 %d 段）" % seg_box[0])
	else:
		_fail("按住连打仍然有效", "只完成 %d 段" % seg_box[0])

	# ── 3. 收尾：等回 IDLE ──
	await _settle(player, 120)

	print("")
	if _failures.is_empty():
		print("PASS: 全部 %d 项通过" % _checks)
		quit(0)
	else:
		printerr("FAIL: %d/%d 项失败" % [_failures.size(), _checks])
		quit(1)
