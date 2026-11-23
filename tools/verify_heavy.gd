extends SceneTree
## 重攻击三连验证：连段推进、时长/伤害比轻攻击更大、不能无限循环、顿帧与震屏
##
## 运行：godot --headless --path . --script tools/verify_heavy.gd

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
	player.global_position = dummy.global_position + Vector2(-20, 0)
	player.facing = 1
	for i in 20:
		await physics_frame

	print("── 重攻击三连验证 ──")

	# ── 1. 三连能依次推进 0→1→2 ──
	# **用真实按键驱动**：按住重击键，记录段号轨迹。
	# 早期用手动 start_heavy_attack() 反复调，会和"段结束自动接段"打架
	# （buffer 已被消费、state 还在 ATTACK），测不出真实行为。
	var seen: Array[int] = []
	Input.action_press("heavy")
	for i in 420:
		await physics_frame
		if player.is_heavy() or player.get_heavy_index() > 0:
			var idx: int = player.get_heavy_index()
			if seen.is_empty() or seen[seen.size() - 1] != idx:
				# 回到 0 说明新起一套，第一轮记录到此为止
				if idx == 0 and seen.size() >= 3:
					break
				seen.append(idx)
		if seen.size() >= 3 and player.get_heavy_index() == 2:
			break
	Input.action_release("heavy")

	_check(seen == [0, 1, 2], "1. 重攻击连段按 0→1→2 推进",
	       "实际 %s" % str(seen))

	# ── 2. 第 3 段打完不回到第 1 段（不循环）──
	player._heavy_idle = 0.0
	player._heavy_buffer = true
	var looped: bool = player._try_next_heavy()
	_check(not looped, "2. 第3段打完不循环回第1段",
	       "三段后仍能接段，重攻击会变成无脑连按")
	_check(player.get_heavy_index() == 0, "3. 收招后索引归零",
	       "索引 = %d" % player.get_heavy_index())

	# ── 3. 重攻击比轻攻击慢、伤害更高 ──
	var light_total := 0.0
	for s in player.COMBO:
		light_total += float(s["dur"])
	var heavy_total := 0.0
	var light_dmg := 0
	var heavy_dmg := 0
	for s in player.COMBO:
		light_dmg += int(s["dmg"])
	for s in player.HEAVY_COMBO:
		heavy_total += float(s["dur"])
		heavy_dmg += int(s["dmg"])

	_check(heavy_total > light_total * 1.5,
	       "4. 重攻击总时长远超轻攻击",
	       "重 %.2fs vs 轻 %.2fs" % [heavy_total, light_total])
	_check(heavy_dmg > light_dmg * 2,
	       "5. 重攻击总伤害远超轻攻击",
	       "重 %d vs 轻 %d" % [heavy_dmg, light_dmg])

	# 每一段单独看也要更慢
	var all_slower := true
	var detail := ""
	for i in 3:
		var hd := float(player.HEAVY_COMBO[i]["dur"])
		var ld := float(player.COMBO[i]["dur"])
		if hd <= ld:
			all_slower = false
			detail = "第%d段 重 %.2f <= 轻 %.2f" % [i + 1, hd, ld]
			break
	_check(all_slower, "6. 每一段单独都比对应轻攻击段慢", detail)

	# ── 4. 重攻击判定框比轻攻击大 ──
	var bigger := true
	var bd := ""
	for i in 3:
		var hb: Vector4 = player.HEAVY_COMBO[i]["box"]
		var lb: Vector4 = player.COMBO[i]["box"]
		if hb.x <= lb.x or hb.y <= lb.y:
			bigger = false
			bd = "第%d段 重框 %.0fx%.0f vs 轻框 %.0fx%.0f" % [
				i + 1, hb.x, hb.y, lb.x, lb.y]
			break
	_check(bigger, "7. 每段判定框都比轻攻击大", bd)

	# ── 5. 重攻击几乎不能取消（必须打完）──
	_check(player.HEAVY_CANCEL_AFTER > 0.85,
	       "8. 重攻击取消窗口极靠后（不能提前取消）",
	       "HEAVY_CANCEL_AFTER = %.2f" % player.HEAVY_CANCEL_AFTER)

	# ── 6. 命中触发顿帧与震屏 ──
	var got_hitstop := [false]
	var got_shake := [false]
	player.hitstop_requested.connect(func(_d): got_hitstop[0] = true)
	player.shake_requested.connect(func(_a, _d): got_shake[0] = true)

	player._heavy_index = 2
	player.is_heavy_attack = true
	player._begin_swing()
	for i in 60:
		await physics_frame
	_check(got_hitstop[0], "9. 重攻击命中有顿帧请求", "未收到 hitstop_requested")
	_check(got_shake[0], "10. 重攻击命中有震屏请求", "未收到 shake_requested")

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
