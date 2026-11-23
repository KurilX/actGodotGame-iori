extends SceneTree
## 新手教程关验证：关卡结构、怪物分布、教学提示、BOSS 房锁
##
## 运行：godot --headless --path . --script tools/verify_tutorial.gd -- --autoplay
##
## 这个测试对应的设计文档：docs/04-教程关设计.md
## 每条断言都对应设计里的一个明确决定，不是"能跑就算过"。

var _failures: Array[String] = []
var _checks := 0


func _init() -> void:
	var boot: PackedScene = load("res://scenes/bootstrap.tscn")
	root.add_child(boot.instantiate())
	await process_frame
	await process_frame
	for i in 40:
		await physics_frame

	print("── 新手教程关验证 ──")

	var room = _find_room(root)
	var player = _find_player(root)
	var hints = _find_script(root, "tutorial_hints")
	var bar = _find_script(root, "boss_healthbar")

	_check(room != null, "1. 房间节点存在", "未找到")
	_check(hints != null, "2. 教学提示 UI 存在", "未找到")
	if room == null:
		_finish()
		return

	# ── 关卡尺寸 ──
	var w: int = room.ROOM_W
	_check(w == 2400, "3. 关卡宽度 2400（教程 + 主关卡）", "实际 %d" % w)
	_check(float(room.TUTORIAL_END) == 1560.0,
	       "4. 教程关分界在 x=1560", str(room.TUTORIAL_END))

	# ── 怪物分布：按教学段 ──
	var minions := []
	for e in get_nodes_in_group("enemy"):
		if e.get("max_hp") != 120:
			minions.append(e)
	_check(minions.size() == 6, "5. 共 6 只杂兵", "实际 %d" % minions.size())

	# 按 x 分区间统计
	var counts := {"move": 0, "light": 0, "heavy": 0, "dash": 0, "mix": 0}
	for m in minions:
		var x: float = m.global_position.x
		if x < 480:
			counts["move"] += 1
		elif x < 880:
			counts["light"] += 1
		elif x < 1180:
			counts["heavy"] += 1
		elif x < 1400:
			counts["dash"] += 1
		else:
			counts["mix"] += 1

	# **核心设计断言**：移动段必须完全没有敌人
	_check(counts["move"] == 0, "6. ① 移动段没有敌人（第一个怪前必须有安全区）",
	       "实际 %d 只" % counts["move"])
	_check(counts["light"] == 1, "7. ② 轻攻击段 1 只（站着对打的靶子）",
	       "实际 %d 只" % counts["light"])
	_check(counts["heavy"] == 1, "8. ③ 重攻击段 1 只（石守，教破霸体）",
	       "实际 %d 只" % counts["heavy"])
	_check(counts["dash"] == 2, "9. ④ 闪避段 2 只（两侧夹击）",
	       "实际 %d 只" % counts["dash"])
	_check(counts["mix"] == 2, "10. ⑤ 综合段 2 只（三种威胁同场）",
	       "实际 %d 只" % counts["mix"])

	# 重攻击段必须是石守（有霸体，能教出轻/重区别）
	var heavy_kind := ""
	for m in minions:
		var x: float = m.global_position.x
		if x >= 880 and x < 1180:
			heavy_kind = str(m.name).to_lower()
	_check(heavy_kind.contains("stonepaw"),
	       "11. 重攻击段放的是石守（唯一能教出轻/重区别的敌人）",
	       "实际是 %s" % heavy_kind)

	# ── 教学提示 ──
	if hints != null:
		_check(hints.SEGMENTS.size() == 5, "12. 有 5 段教学提示",
		       "实际 %d" % hints.SEGMENTS.size())
		var ids := []
		for s in hints.SEGMENTS:
			ids.append(s["id"])
		_check(ids == ["move", "light", "heavy", "dash", "mix"],
		       "13. 教学段顺序正确", str(ids))
		# 每段都要有按键提示和非空目标
		var all_have_keys := true
		for s in hints.SEGMENTS:
			if (s["keys"] as Array).is_empty() or str(s["hint"]) == "":
				all_have_keys = false
		_check(all_have_keys, "14. 每段都有按键提示和目标", "有段缺内容")

	# 玩家在移动段 → 应显示 move 提示
	player.global_position = Vector2(200, 440)
	for i in 20:
		await physics_frame
	_check(hints.get_current_segment() == "move",
	       "15. 玩家在移动段时显示对应提示",
	       "实际 %s" % hints.get_current_segment())
	_check(hints.is_showing(), "16. 提示确实在显示", "没显示")

	# 走到轻攻击段
	player.global_position = Vector2(700, 440)
	for i in 20:
		await physics_frame
	_check(hints.get_current_segment() == "light",
	       "17. 走到轻攻击段切换提示",
	       "实际 %s" % hints.get_current_segment())

	# ── BOSS 房锁 ──
	var boss = _find_boss(root)
	_check(boss != null, "18. BOSS 已生成", "未找到")
	if boss != null:
		# 玩家还在教程关 → BOSS 应休眠
		player.global_position = Vector2(200, 440)
		for i in 20:
			await physics_frame
		_check(boss.is_dormant(), "19. 玩家在教程关时 BOSS 休眠",
		       "BOSS 醒了，会追到教程关")
		if bar != null:
			_check(not bar.visible, "20. 未进 BOSS 房时不显示血条",
			       "血条提前显示")

		# 走进 BOSS 房 → 应唤醒
		player.global_position = Vector2(1700, 440)
		for i in 40:
			await physics_frame
		_check(not boss.is_dormant(), "21. 玩家进入 BOSS 房后 BOSS 苏醒",
		       "仍休眠")
		if bar != null:
			_check(bar.visible, "22. 进入 BOSS 房后显示血条",
			       "血条没出现")

	# ── 地形与美术 ──
	var solids: Array = room.SOLIDS
	_check(solids.size() >= 12, "23. 地形块数量合理（%d 块）" % solids.size(),
	       "只有 %d 块" % solids.size())
	# 地面必须贯穿全图
	var ground_ok := false
	for s in solids:
		if int(s[0]) == 0 and int(s[2]) >= 2400:
			ground_ok = true
	_check(ground_ok, "24. 地面贯穿全图的 2400px", "地面没有铺满")

	_check(ResourceLoader.exists("res://art/scene/sky.png"),
	       "25. 场景美术 sky.png 存在", "缺文件")
	var sky = load("res://art/scene/sky.png")
	if sky is Texture2D:
		_check(sky.get_width() == 2400,
		       "26. 天空贴图宽度 2400（与关卡一致）",
		       "实际 %d" % sky.get_width())

	# 训练木桩（无条件练习目标）
	var dummy_found := false
	for n in _walk(root):
		if "dummy" in str(n.name).to_lower():
			dummy_found = true
	# 木桩可能没有名字，这条只做提示不算失败
	print("  info 训练木桩存在 = %s" % dummy_found)

	_finish()


func _finish() -> void:
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


func _walk(n):
	var o = [n]
	for c in n.get_children():
		o.append_array(_walk(c))
	return o


func _find_room(node: Node):
	var s = node.get_script()
	if s != null and str(s.resource_path).contains("room_greybox"):
		return node
	for c in node.get_children():
		var r = _find_room(c)
		if r:
			return r
	return null


func _find_player(node: Node):
	if node.is_in_group("player"):
		return node
	for c in node.get_children():
		var r = _find_player(c)
		if r:
			return r
	return null


func _find_boss(node: Node):
	if node is CharacterBody2D and node.get("max_hp") == 120:
		return node
	for c in node.get_children():
		var r = _find_boss(c)
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
