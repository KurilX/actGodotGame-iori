extends SceneTree
## 技能树 + 连招触发 + 道具解锁 验证
##
## 运行：godot --headless --path . --script tools/verify_skill_tree.gd

var _failures: Array[String] = []
var _checks := 0


func _init() -> void:
	var boot: PackedScene = load("res://scenes/bootstrap.tscn")
	root.add_child(boot.instantiate())
	await process_frame
	await process_frame
	for i in 20:
		await physics_frame

	print("── 技能树系统验证 ──")

	var st = _find_skill_tree(root)
	var player = _find_player(root)
	var panel = _find_script(root, "skill_tree_panel")
	var banner = _find_script(root, "item_gain_banner")
	var boss = _find_boss(root)

	if st == null:
		printerr("FAIL 未找到 skill_tree")
		quit(1)
		return

	# ── 1. 初始状态 ──
	_check(st.all_skills().size() == 3, "1. 技能树有 3 个节点",
	       "实际 %d" % st.all_skills().size())
	_check(st.is_unlocked("seam"), "2. 根节点 seam 开局解锁",
	       "未解锁")
	_check(not st.is_unlocked("pierce_weave"),
	       "3. 贯穿织开局未解锁", "已解锁")

	# ── 2. 连招不能自己解锁（必须靠 BOSS 掉落）──
	st.push_action("light")
	st.push_action("light")
	st.push_action("light")
	_check(not st.is_unlocked("pierce_weave"),
	       "4. 轻攻击三连不解锁（需先获得道具）", "已解锁")
	st.push_action("heavy")
	_check(not st.is_unlocked("pierce_weave"),
	       "5. 三连+重击也不能凭空解锁", "已解锁")

	# ── 3. 掉落解锁 ──
	var ok: bool = st.try_unlock("pierce_weave")
	_check(ok, "6. try_unlock 能解锁贯穿织", "返回 false")
	_check(st.is_unlocked("pierce_weave"), "7. 解锁状态正确", "未解锁")

	# ── 4. 前置依赖 ──
	var ok2: bool = st.try_unlock("mend_veil")
	_check(ok2, "8. 前置满足时可解锁 mend_veil", "返回 false")

	# ── 5. 序列追踪 ──
	st.reset_sequence()
	_check(st.get_sequence().size() == 0, "9. reset_sequence 清空序列",
	       "还有 %d 个" % st.get_sequence().size())
	st.push_action("light")
	st.push_action("light")
	st.push_action("light")
	st.push_action("heavy")
	var seq: Array = st.get_sequence()
	_check(seq.size() == 4, "10. 序列记录 4 个动作",
	       "实际 %d 个" % seq.size())
	_check(seq == ["light", "light", "light", "heavy"],
	       "11. 序列内容正确", str(seq))

	# 序列不会无限增长
	for i in 20:
		st.push_action("light")
	_check(st.get_sequence().size() <= 8, "12. 序列长度有上限",
	       "实际 %d" % st.get_sequence().size())

	# 受伤清空序列
	st.reset_sequence()
	st.push_action("light")
	player.damaged.emit(1)
	await process_frame
	_check(st.get_sequence().size() == 0, "13. 玩家受伤会清空连招序列",
	       "还有 %d 个" % st.get_sequence().size())

	# ── 6. UI 节点存在 ──
	_check(panel != null, "14. 技能树面板存在", "未找到")
	_check(banner != null, "15. 道具横幅存在", "未找到")
	if panel:
		_check(not panel.is_open(), "16. 技能树面板默认关闭",
		       "打开了")
		panel.toggle()
		_check(panel.is_open(), "17. toggle 能打开面板", "未打开")
		panel.toggle()
		_check(not panel.is_open(), "18. toggle 能关闭面板", "未关闭")

	# ── 7. 道具图标资源 ──
	_check(ResourceLoader.exists("res://art/items/spool_32.png"),
	       "19. 道具图标 spool_32.png 存在", "缺文件")
	_check(ResourceLoader.exists("res://art/items/spool_48.png"),
	       "20. 道具图标 spool_48.png 存在", "缺文件")

	# ── 8. 获得道具动画 ──
	if player:
		var anim = player.get_node_or_null("Visual/AnimatedSprite2D")
		_check(anim != null and anim.sprite_frames.has_animation("gain"),
		       "21. 玩家有 gain 动画", "缺 gain")
		player.play_gain_anim()
		await physics_frame
		await physics_frame
		_check(anim.animation == "gain", "22. play_gain_anim 切到 gain",
		       "当前动画 %s" % anim.animation)

	# ── 9. BOSS 死亡 → 掉落 ──
	if boss:
		boss.hp = 1
		boss.take_hit(999, 0.0)
		await physics_frame
		for i in 10:
			await physics_frame
		_check(boss.is_dead(), "23. BOSS 能被击杀", "还活着")
		# 掉落流程会把横幅打开
		if banner:
			_check(banner.is_active(), "24. BOSS 死亡触发获得道具横幅",
			       "横幅没出现")

	# ── 10. 技能特效节点 ──
	var fx = _find_script(root, "pierce_weave_fx")
	_check(fx != null, "25. 贯穿织特效节点存在", "未找到")
	if fx:
		fx.fire(Vector2(400, 400), 1)
		await physics_frame
		_check(fx.is_active(), "26. fire() 能激活特效", "未激活")

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


func _find_skill_tree(node: Node):
	var s = node.get_script()
	if s != null and str(s.resource_path).ends_with("skill_tree.gd"):
		return node
	for c in node.get_children():
		var r = _find_skill_tree(c)
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
