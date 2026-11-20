extends SceneTree
## 连击条验证：段数累加、评级升级、受击清零、超时衰减
##
## 运行：godot --headless --path . --script tools/verify_combo_meter.gd

var _failures: Array[String] = []
var _checks := 0


func _init() -> void:
	var boot: PackedScene = load("res://scenes/bootstrap.tscn")
	root.add_child(boot.instantiate())
	await process_frame
	await process_frame
	for i in 30:
		await physics_frame

	print("── 连击条验证 ──")

	var combo = _find_script(root, "combo_meter")
	var player = _find_player(root)

	if combo == null:
		printerr("FAIL: 未找到 combo_meter 节点")
		quit(1)
		return
	if player == null:
		printerr("FAIL: 未找到玩家")
		quit(1)
		return

	# ── 1. 初始状态：隐藏、0 段、F 级 ──
	_check(combo.get_segments() == 0, "1. 初始 0 段",
	       "实际 %d" % combo.get_segments())
	_check(combo.get_rank_label() == "F", "2. 初始评级是 F",
	       "实际 %s" % combo.get_rank_label())
	_check(not combo.visible, "3. 无连击时不显示",
	       "visible = true")

	# ── 2. 累加段数 ──
	combo.register_hit(1)
	_check(combo.get_segments() == 1, "4. 命中1次后 1 段",
	       "%d" % combo.get_segments())
	_check(combo.visible, "5. 有连击后显示出来", "visible = false")

	# ── 3. 评级升级（阈值 3 → E）──
	combo.reset_combo()
	for i in 3:
		combo.register_hit(1)
	_check(combo.get_segments() == 3, "6. 累计 3 段",
	       "%d" % combo.get_segments())
	_check(combo.get_rank_label() == "E", "7. 3 段升到 E 级",
	       "实际 %s" % combo.get_rank_label())

	# ── 4. 重击权重 2 ──
	combo.reset_combo()
	combo.register_hit(2)
	_check(combo.get_segments() == 2, "8. 重击（权重2）一次加 2 段",
	       "%d" % combo.get_segments())

	# ── 5. 一路升到 SS ──
	combo.reset_combo()
	var ranks_seen: Array[String] = []
	var prev: String = ""
	for i in 40:
		combo.register_hit(1)
		var r: String = combo.get_rank_label()
		if r != prev:
			ranks_seen.append(r)
			prev = r
	_check(combo.get_rank_label() == "SS", "9. 40 段达到最高 SS",
	       "实际 %s（%d 段）" % [combo.get_rank_label(), combo.get_segments()])
	_check(ranks_seen.size() >= 7, "10. 过程中经过 7 个以上等级",
	       "只经过 %s" % str(ranks_seen))

	# ── 6. SS 封顶，不会超出 ──
	var ss_seg: int = combo.get_segments()
	combo.register_hit(1)
	_check(combo.get_rank_label() == "SS", "11. SS 是上限，不会溢出",
	       "%s" % combo.get_rank_label())

	# ── 7. 受击清零 ──
	combo.register_hit(1)
	combo.register_hit(1)
	var before: int = combo.get_segments()
	player.damaged.emit(1)          # 模拟玩家受伤
	await process_frame
	_check(combo.get_segments() == 0,
	       "12. 玩家受伤后连击清零（受伤前 %d 段）" % before,
	       "仍有 %d 段" % combo.get_segments())
	_check(combo.get_rank_label() == "F", "13. 清零后评级回到 F",
	       "%s" % combo.get_rank_label())
	_check(not combo.visible, "14. 清零后隐藏", "visible = true")

	# ── 8. 超时衰减 ──
	combo.reset_combo()
	for i in 4:
		combo.register_hit(1)
	var seg_before: int = combo.get_segments()
	# 直接推进内部计时器，避免跑 6 秒真实时间
	combo._idle = combo.DECAY_TIME + 0.1
	for i in 30:
		await process_frame
	_check(combo.get_segments() < seg_before,
	       "15. 长时间不出手会衰减（%d → %d 段）" % [seg_before, combo.get_segments()],
	       "段数没有减少")

	# ── 9. 继续命中会刷新计时器 ──
	combo.reset_combo()
	combo.register_hit(1)
	combo._idle = combo.DECAY_TIME - 0.5      # 快超时
	combo.register_hit(1)                      # 又打了一下
	_check(combo._idle < 0.1, "16. 新的命中会重置超时计时",
	       "_idle = %.2f" % combo._idle)

	# ── 10. 评级颜色分段 ──
	combo.reset_combo()
	for i in 3:
		combo.register_hit(1)
	var low_col: Color = combo._rank_color()
	for i in 20:
		combo.register_hit(1)
	var high_col: Color = combo._rank_color()
	_check(low_col != high_col, "17. 低段位与高段位颜色不同",
	       "都是 %s" % str(low_col))

	# ── 11. 空挥扣段 ──
	combo.reset_combo()
	for i in 5:
		combo.register_hit(1)
	var before_whiff: int = combo.get_segments()
	combo.register_whiff(false)          # 轻攻击挥空 -1
	_check(combo.get_segments() == before_whiff - 1,
	       "18. 空挥（轻）扣 1 段（%d → %d）" % [before_whiff, combo.get_segments()],
	       "实际 %d" % combo.get_segments())

	var before_heavy: int = combo.get_segments()
	combo.register_whiff(true)           # 重攻击挥空 -2
	_check(combo.get_segments() == before_heavy - 2,
	       "19. 空挥（重）扣 2 段（%d → %d）" % [before_heavy, combo.get_segments()],
	       "实际 %d" % combo.get_segments())

	# 空挥不会扣成负数
	combo.reset_combo()
	combo.register_hit(1)
	combo.register_whiff(true)
	combo.register_whiff(true)
	_check(combo.get_segments() == 0, "20. 空挥不会扣成负数",
	       "实际 %d" % combo.get_segments())

	# 空挥可能导致降级
	combo.reset_combo()
	for i in 3:
		combo.register_hit(1)            # 3 段 = E 级
	var rank_before: String = combo.get_rank_label()
	combo.register_whiff(false)          # 扣到 2 段
	_check(combo.get_rank_label() != rank_before,
	       "21. 空挥可以降级（%s → %s）" % [rank_before, combo.get_rank_label()],
	       "评级没有变化")

	# ── 12. 完美闪避加成 ──
	combo.reset_combo()
	combo.register_hit(1)
	var before_pd: int = combo.get_segments()
	combo.register_perfect_dodge()
	_check(combo.get_segments() == before_pd + 2,
	       "22. 完美闪避加 2 段（%d → %d）" % [before_pd, combo.get_segments()],
	       "实际 %d" % combo.get_segments())

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
	if node.is_in_group("player"):
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
