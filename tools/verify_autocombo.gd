extends SceneTree
## 验证「按住攻击键持续连打」以及四段动作是否真的不同
##
## 运行：godot --headless --path . --script tools/verify_autocombo.gd

var _failures: Array[String] = []
var _checks := 0


func _init() -> void:
	var boot: PackedScene = load("res://scenes/bootstrap.tscn")
	root.add_child(boot.instantiate())
	await process_frame
	await process_frame

	var player = _find_player(root)
	var dummy = _find_script(root, "training_dummy")
	if player == null or dummy == null:
		printerr("未找到 player 或 dummy")
		quit(1)
		return

	for i in 60:
		await physics_frame

	player.global_position = dummy.global_position + Vector2(-18, 0)
	player.facing = 1
	for i in 20:
		await physics_frame

	print("── 按住连打测试 ──")

	# 按住攻击键不放（模拟玩家按住鼠标/按键）
	Input.action_press("attack")

	var segments: Array[int] = []
	var hp0: int = dummy.get_hp()
	# 跑 3 秒，够打好几轮四连
	for i in 360:
		await physics_frame
		var idx: int = player.get_combo_index()
		if segments.is_empty() or segments[-1] != idx:
			segments.append(idx)

	Input.action_release("attack")
	var hp1: int = dummy.get_hp()

	print("  段号序列: ", segments)
	print("  木桩血量: %d -> %d" % [hp0, hp1])
	print("")

	# 断言
	_check(segments.size() >= 8,
	       "1. 按住能持续推进连段（>=8 次段切换）",
	       "实际只有 %d 次切换：%s" % [segments.size(), str(segments)])
	_check(hp1 < hp0, "2. 连打期间持续造成伤害",
	       "血量 %d -> %d" % [hp0, hp1])

	# 检查是否出现了循环（4 段打完回到 0）
	var saw_cycle := false
	for i in range(1, segments.size()):
		if segments[i - 1] == 3 and segments[i] == 0:
			saw_cycle = true
			break
	_check(saw_cycle, "3. 四段打完后循环回第 1 段",
	       "序列里没有 3→0 的循环：%s" % str(segments))

	# 检查四段都出现过
	var seen := {}
	for s in segments:
		seen[s] = true
	_check(seen.size() == 4, "4. 四段都出现过",
	       "只出现了 %s" % str(seen.keys()))

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


func _find_script(node: Node, name: String):
	var s = node.get_script()
	if s != null and str(s.resource_path).contains(name):
		return node
	for c in node.get_children():
		var r = _find_script(c, name)
		if r:
			return r
	return null
