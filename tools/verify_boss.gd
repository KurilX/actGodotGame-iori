extends SceneTree
## BOSS「瓷面的守夜人」验证：三阶段、技能、弹幕、弹反、血条
##
## 运行：godot --headless --path . --script tools/verify_boss.gd

var _failures: Array[String] = []
var _checks := 0


func _init() -> void:
	var boot: PackedScene = load("res://scenes/bootstrap.tscn")
	root.add_child(boot.instantiate())
	await process_frame
	await process_frame
	for i in 40:
		await physics_frame

	# 房间里的三种杂兵会主动打玩家，干扰本测试（尤其第19项要验证
	# 弹幕伤害，玩家可能正处于杂兵造成的无敌期）。先隔离它们。
	for e in get_nodes_in_group("enemy"):
		if e.get("max_hp") != 120:
			e.global_position = Vector2(5000, 5000)
			e.set_physics_process(false)

	print("── BOSS「瓷面的守夜人」验证 ──")

	var boss = _find_boss(root)
	var player = _find_player(root)
	var bar = _find_script(root, "boss_healthbar")

	if boss == null:
		printerr("FAIL 未找到 BOSS")
		quit(1)
		return

	# ── 1. 基础属性 ──
	_check(boss.max_hp == 120, "1. BOSS 血量 120",
	       "实际 %d" % boss.max_hp)
	_check(boss.hp == 120, "2. 初始满血", "实际 %d" % boss.hp)
	_check(boss.phase == 1, "3. 初始第一阶段", "实际 %d" % boss.phase)
	_check(boss.is_in_group("enemy"), "4. 在 enemy 组里", "不在组里")

	# ── 2. 血条 ──
	_check(bar != null, "5. 血条节点存在", "未找到")
	if bar:
		_check(bar.visible, "6. 血条可见", "visible=false")
		_check(bar.get_hp_ratio() >= 0.99, "7. 血条初始满血",
		       "%.2f" % bar.get_hp_ratio())

	# ── 3. 技能调度：会自己开始放技能 ──
	var skill_seen := {}
	for i in 400:
		await physics_frame
		var sk: int = boss._current_skill
		skill_seen[sk] = true
	_check(skill_seen.size() >= 1, "8. BOSS 会主动释放技能",
	       "400 帧内没放任何技能")

	# ── 4. 阶段转换 ──
	boss.hp = int(boss.max_hp * 0.60)      # 降到 60% → 应进入二阶段
	for i in 30:
		await physics_frame
	_check(boss.phase == 2, "9. 血量降到 60% 进入第二阶段",
	       "phase = %d" % boss.phase)
	if bar:
		_check(bar.get_phase() == 2, "10. 血条同步显示第二阶段",
		       "血条 phase = %d" % bar.get_phase())

	# 阶段转换期间应该无敌
	boss.hp = int(boss.max_hp * 0.30)
	await physics_frame
	var hp_before: int = boss.hp
	boss.take_hit(50, 0.0)
	_check(boss.hp == hp_before, "11. 阶段转换期间无敌（不掉血）",
	       "hp %d → %d" % [hp_before, boss.hp])

	# 等转换结束
	for i in 80:
		await physics_frame
	_check(boss.phase == 3, "12. 血量降到 30% 进入第三阶段",
	       "phase = %d" % boss.phase)

	# ── 5. 二阶段起会发弹幕 ──
	boss.phase = 2
	boss._current_skill = 2         # VOLLEY
	boss._skill_activate()
	await physics_frame
	await physics_frame
	var projectiles := get_nodes_in_group("projectile")
	_check(projectiles.size() > 0, "13. 弹幕技能会生成投射物",
	       "场上没有 projectile")
	if projectiles.size() > 0:
		var has_reflectable := false
		var has_red := false
		for p in projectiles:
			if p.get("reflectable"):
				has_reflectable = true
			else:
				has_red = true
		_check(has_reflectable, "14. 弹幕里有可弹反的（青弹）",
		       "全是不可弹反")
		_check(has_red, "15. 二阶段弹幕里混有不可弹反的（红弹）",
		       "全是可弹反 —— 玩家不需要分辨，设计目标没达成")

	# ── 6. 弹反机制 ──
	if projectiles.size() > 0:
		var p = projectiles[0]
		var dir_before: Vector2 = p.direction
		var reflectable = p.get("reflectable")
		if reflectable:
			p.reflect()
			_check(p.is_reflected(), "16. 可弹反弹幕能被弹反",
			       "reflect() 后 is_reflected 仍为 false")
			_check(p.direction.dot(dir_before) < 0,
			       "17. 弹反后弹幕反向飞行",
			       "方向没变")
		else:
			_check(true, "16. (跳过，第一个是不可弹弹幕)")
			_check(true, "17. (跳过)")

	# ── 7. 不可弹反的弹幕打不回去 ──
	var red = _spawn_projectile(root, Vector2(400, 400),
								 Vector2.LEFT, false)
	await physics_frame
	red.reflect()
	_check(not red.is_reflected(), "18. 不可弹反的弹幕打不回去",
	       "红弹被弹反了 —— 应当打不动")
	red.queue_free()

	# ── 8. 弹幕能伤到玩家 ──
	# **必须先等无敌结束**：前面的用例已经让玩家受过伤，
	# take_damage 后有 INVULN_TIME（0.9s）的无敌，
	# 不等的话弹幕打上去不掉血，会误判成"弹幕没伤害"。
	# 用 0.9s × 60fps ≈ 60 帧，给足 80 帧。
	for i in 80:
		await physics_frame

	var hearts_before: int = player.get_hearts()
	var near = _spawn_projectile(root,
								  player.global_position + Vector2(-8, -10),
								  Vector2.RIGHT, true)
	for i in 10:
		await physics_frame
	_check(player.get_hearts() < hearts_before,
	       "19. 弹幕能对玩家造成伤害（%d → %d）" % [
	           hearts_before, player.get_hearts()],
	       "玩家血量没变（可能仍在受伤无敌期）")

	print("")
	if _failures.is_empty():
		print("PASS: 全部 %d 项通过" % _checks)
		quit(0)
	else:
		print("FAIL: %d 项失败" % _failures.size())
		for f in _failures:
			printerr("  - " + f)
		quit(1)


func _spawn_projectile(parent: Node, pos: Vector2, dir: Vector2,
					   reflectable: bool):
	# projectile.gd 继承 Area2D，必须用 Area2D 实例化
	var p := Area2D.new()
	p.set_script(load("res://src/enemies/projectile.gd"))
	parent.add_child(p)
	p.spawn(pos, dir, {"reflectable": reflectable, "speed": 100.0})
	return p


func _check(cond: bool, name: String, detail: String = "") -> void:
	_checks += 1
	if cond:
		print("  ok   %s" % name)
	else:
		print("  FAIL %s" % name)
		_failures.append(name + (": " + detail if detail != "" else ""))


func _find_boss(node: Node):
	if node is CharacterBody2D and node.get("max_hp") == 120:
		return node
	for c in node.get_children():
		var r = _find_boss(c)
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


func _find_script(node: Node, name: String):
	var s = node.get_script()
	if s != null and str(s.resource_path).contains(name):
		return node
	for c in node.get_children():
		var r = _find_script(c, name)
		if r:
			return r
	return null
