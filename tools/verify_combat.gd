extends SceneTree
## 战斗系统冒烟测试：连段树 / 攻击判定 / 闪避无敌 / 完美闪避
##
## 运行：godot --headless --path . --script tools/verify_combat.gd
## 退出码：0 全通过 / 1 有失败

var _failures: Array[String] = []
var _checks := 0


func _init() -> void:
	var boot: PackedScene = load("res://scenes/bootstrap.tscn")
	root.add_child(boot.instantiate())
	await process_frame
	await process_frame

	var player = _find_player(root)
	if player == null:
		printerr("FAIL: 未找到 Player")
		quit(1)
		return

	var dummy = _find_by_script(root, "training_dummy")
	if dummy == null:
		printerr("FAIL: 未找到训练木桩")
		quit(1)
		return

	# 房间里在加入敌人后，测试闪避/完美闪避期间会被敌人打断。
	# 这里把敌人移开（不是关掉，只是挪出交互范围），
	# 让本测试专注于玩家自身的战斗逻辑。
	var enemies := get_nodes_in_group("enemy")
	for e in enemies:
		e.global_position = Vector2(2000, 2000)
		e.set_physics_process(false)

	await _settle(player, 90)

	print("── 战斗系统冒烟测试 ──")
	print("")

	# ── 1. 连段树：连续四段分别命中 ──
	# 把玩家挪到木桩左侧，且距离要落在判定框覆盖范围内。
	# 判定框 offset_x 约 +14~18，半宽 11~15，所以水平间距 12~28px 都能覆盖。
	player.global_position = dummy.global_position + Vector2(-18, 0)
	player.facing = 1
	for i in 30:
		await physics_frame

	var seen_segments: Array[int] = []
	var hp_before: int = dummy.get_hp()

	for seg in 4:
		# 直接调 start_attack 驱动连段，绕开输入时序的不可控
		player.start_attack()
		seen_segments.append(player.get_combo_index())
		# 每段最长 0.36s；physics 60Hz 下需 ~22 帧。
		# 多等几帧，确保段落真正结束（否则下一轮 start_attack 会被状态挡掉）。
		for i in 40:
			await physics_frame
		# 段间保持极短间隔，落在连段窗口内
		for i in 2:
			await physics_frame

	var hp_after: int = dummy.get_hp()
	_check(seen_segments == [0, 1, 2, 3],
	       "1. 连段树按 0→1→2→3 推进", "实际 %s" % str(seen_segments))
	_check(hp_after < hp_before,
	       "2. 攻击命中扣血", "血量 %d -> %d" % [hp_before, hp_after])

	# ── 3. 一次挥击对同一目标只结算一次 ──
	# 等到木桩复活（或直接重置血量）
	for i in 120:
		await physics_frame
	if not dummy.is_alive():
		for i in 120:
			await physics_frame

	player.global_position = dummy.global_position + Vector2(-26, 0)
	for i in 20:
		await physics_frame
	var hp0: int = dummy.get_hp()
	player.start_attack()
	# 跑满整段，判定窗口内会反复触发 area_entered
	for i in 30:
		await physics_frame
	var hp1: int = dummy.get_hp()
	var dealt: int = hp0 - hp1
	_check(dealt <= 1, "3. 单次挥击只结算一次伤害",
	       "扣了 %d 点（应等于第一段伤害 1）" % dealt)

	# ── 4. 闪避进入 DASH 状态 ──
	await _settle(player, 40)
	player.start_dash()
	_check(player.is_dashing(), "4. 闪避进入 DASH 状态", "状态 = %d" % player.state)

	# ── 5. 闪避期间无敌 ──
	var hearts0: int = player.get_hearts()
	player.take_damage(1, player.global_position.x + 100.0)
	_check(player.get_hearts() == hearts0, "5. 闪避无敌帧免疫伤害",
	       "血量 %d -> %d" % [hearts0, player.get_hearts()])

	# ── 6. 无敌窗口结束后恢复可受击 ──
	for i in 40:
		await physics_frame
	_check(not player.is_dashing(), "6. 闪避按时结束", "仍在闪避")
	_check(not player.is_invulnerable(), "7. 闪避结束不再无敌", "仍无敌")

	var hearts1: int = player.get_hearts()
	player.take_damage(1, player.global_position.x + 100.0)
	_check(player.get_hearts() == hearts1 - 1,
	       "8. 无敌结束后正常受伤",
	       "血量 %d -> %d" % [hearts1, player.get_hearts()])

	# ── 9. 完美闪避信号 ──
	var got_perfect := [false]
	player.perfect_dodge.connect(func(): got_perfect[0] = true)
	await _settle(player, 120)      # 等受击无敌和硬直都结束
	player.start_dash()
	# 闪避中调用 try_perfect_dodge 应返回 true 并触发信号
	var ok: bool = player.try_perfect_dodge()
	_check(ok and got_perfect[0], "9. 完美闪避判定与信号",
	       "返回 %s，信号 %s" % [ok, got_perfect[0]])

	print("")
	if _failures.is_empty():
		print("PASS: 全部 %d 项通过" % _checks)
		quit(0)
	else:
		print("FAIL: %d 项失败" % _failures.size())
		for f in _failures:
			printerr("  - " + f)
		quit(1)


func _settle(node, frames: int) -> void:
	for i in frames:
		await physics_frame


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


func _find_by_script(node: Node, script_name: String):
	var s = node.get_script()
	if s != null and str(s.resource_path).contains(script_name):
		return node
	for c in node.get_children():
		var r = _find_by_script(c, script_name)
		if r:
			return r
	return null
