extends SceneTree
## 敌人系统验证：三个敌人的存在、追击、攻击、受击、死亡、打断规则
##
## 运行：godot --headless --path . --script tools/verify_enemies.gd

var _failures: Array[String] = []
var _checks := 0


func _init() -> void:
	var boot: PackedScene = load("res://scenes/bootstrap.tscn")
	root.add_child(boot.instantiate())
	await process_frame
	await process_frame
	await physics_frame

	var player = _find_player(root)
	var enemies = _find_all_by_base(root)
	if player == null:
		printerr("FAIL: 未找到玩家")
		quit(1)
		return

	print("── 敌人系统验证 ──")
	print("")

	# 排除 BOSS（BOSS 有独立的 verify_boss.gd 覆盖），这里只测三种杂兵
	var minions := []
	for e in enemies:
		if e.get("max_hp") != 120:
			minions.append(e)
	# 关卡扩成 2400px 后，杂兵按教学段分布（见 docs/04-教程关设计.md）：
	# ② 轻攻击 1 只、③ 重攻击 1 只、④ 闪避 2 只、⑤ 综合 2 只 = 6 只
	_check(minions.size() == 6, "1. 房间里有 6 只杂兵（按教学段分布）",
	       "实际 %d 个" % minions.size())
	enemies = minions

	# 按名字归类
	var by_name := {}
	for e in enemies:
		by_name[str(e.name).to_lower()] = e
	print("  敌人: %s" % str(by_name.keys()))

	var moss = by_name.get("mossling")
	var lantern = by_name.get("lanternbug")
	var stone = by_name.get("stonepaw")
	_check(moss != null and lantern != null and stone != null,
	       "2. 三个敌人类型齐全", "缺少: %s" % str(by_name.keys()))

	# ── 3. 血量差异（体现不同的耐久定位）──
	_check(moss.hp == 12 and lantern.hp == 9 and stone.hp == 26,
	       "3. 三者血量符合定位（苔团12/灯笼虫9/石守26）",
	       "实测 %d/%d/%d" % [moss.hp, lantern.hp, stone.hp])
	# ── 3b. 待机动作：**必须看得出来在动** ──
	#
	# 用户明确要求"怪物静止状态也要有待机动作"。
	# 原来三个敌人都只有 4 帧、幅度 1~2px —— 在 30px 体型上等于静止。
	# 这里直接量像素包围盒的变化，不是看"动画在播"就算了。
	for e in [moss, lantern, stone]:
		var anim = null
		for n in _walk(e):
			if n is AnimatedSprite2D:
				anim = n
				break
		if anim == null:
			continue
		var frames: int = anim.sprite_frames.get_frame_count("idle")
		_check(frames >= 6, "%s 待机帧数 ≥ 6（实际 %d）" % [e.name, frames],
			   "只有 %d 帧，动作会显得僵硬" % frames)
		# 量所有待机帧的包围盒，看顶部位移
		var tops: Array[float] = []
		var hs: Array[float] = []
		for f in frames:
			var tex: Texture2D = anim.sprite_frames.get_frame_texture("idle", f)
			if tex == null:
				continue
			var img: Image = tex.get_image()
			var used := img.get_used_rect()
			tops.append(float(used.position.y))
			hs.append(float(used.size.y))
		if tops.size() >= 2:
			var top_span: float = tops.max() - tops.min()
			var h_span: float = hs.max() - hs.min()
			var amp: float = maxf(top_span, h_span)
			# 幅度至少 3px 才看得见（1~2px 在 30px 体型上是噪音）
			_check(amp >= 3.0,
				   "%s 待机幅度 ≥ 3px（位移 %.0f / 高度 %.0f）" % [
					   e.name, top_span, h_span],
				   "幅度只有 %.1fpx，肉眼几乎看不出在动" % amp)


	# ── 4. 飞行单位不受重力 ──
	await _wait(40)
	var lantern_y_before = lantern.global_position.y
	await _wait(60)
	var lantern_drift = absf(lantern.global_position.y - lantern_y_before)
	_check(lantern_drift < 12.0,
	       "4. 灯笼虫能悬停（不会掉下去）",
	       "y 漂移了 %.1f px" % lantern_drift)

	# ── 5. 玩家靠近后敌人进入追击 ──
	player.global_position = moss.global_position + Vector2(-40, 0)
	await _wait(30)
	_check(moss.state != 0, "5. 玩家靠近后苔团开始行动",
	       "state 仍为 IDLE(0)")

	# ── 6. 敌人能打到玩家（掉血）──
	var hp_before: int = player.get_hearts()
	# 贴着敌人站，等它攻击
	player.global_position = moss.global_position + Vector2(-20, 0)
	var damaged := false
	for i in 200:
		await physics_frame
		player.global_position = moss.global_position + Vector2(-20, 0)
		if player.get_hearts() < hp_before:
			damaged = true
			break
	_check(damaged, "6. 敌人攻击能对玩家造成伤害",
	       "等 200 帧玩家血量仍是 %d" % player.get_hearts())

	# ── 7. 玩家能打到敌人 ──
	await _wait(120)      # 等玩家无敌结束
	var moss_hp_before: int = moss.hp
	moss.take_hit(1, player.global_position.x)
	_check(moss.hp < moss_hp_before, "7. 玩家攻击能扣除敌人血量",
	       "hp %d -> %d" % [moss_hp_before, moss.hp])

	# ── 8. 轻攻击不打断石守，重攻击打断 ──
	stone.state = 2       # WINDUP（枚举：0 IDLE / 1 CHASE / 2 WINDUP / 3 ATTACK / 4 HURT / 5 DEAD）
	stone._timer = 0.5
	var stone_hp0: int = stone.hp
	stone.take_hit(2, player.global_position.x)    # 轻攻击
	_check(stone.state == 2,
	       "8. 轻攻击打不断石守的动作（霸体）",
	       "state 变成 %d" % stone.state)
	stone.take_hit(5, player.global_position.x)    # 重攻击
	_check(stone.state == 4,
	       "9. 重攻击能打断石守（进入 HURT）",
	       "state 变成 %d（期望 4=HURT）" % stone.state)

	# ── 10. 血量归零后死亡并移出组 ──
	var lantern_hp: int = lantern.hp
	lantern.take_hit(lantern_hp + 10, 0.0)
	_check(lantern.is_dead(), "10. 血量归零后进入死亡状态",
	       "state 不是 DEAD")
	_check(not lantern.is_in_group("enemy"),
	       "11. 死亡后移出 enemy 组", "仍在 enemy 组")

	# ── 12. 死亡后不再造成伤害 ──
	var hp_now: int = player.get_hearts()
	await _wait(30)
	_check(player.get_hearts() == hp_now,
	       "12. 死亡敌人不再攻击玩家",
	       "血量仍从 %d 变成 %d" % [hp_now, player.get_hearts()])

	print("")
	if _failures.is_empty():
		print("PASS: 全部 %d 项通过" % _checks)
		quit(0)
	else:
		print("FAIL: %d 项失败" % _failures.size())
		for f in _failures:
			printerr("  - " + f)
		quit(1)


func _wait(frames: int) -> void:
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
	if node is CharacterBody2D and node.is_in_group("player"):
		return node
	for c in node.get_children():
		var r = _find_player(c)
		if r:
			return r
	return null


func _find_all_by_base(node: Node) -> Array:
	var out := []
	if node.is_in_group("enemy"):
		out.append(node)
	for c in node.get_children():
		out.append_array(_find_all_by_base(c))
	return out


func _walk(n):
	var o = [n]
	for c in n.get_children():
		o.append_array(_walk(c))
	return o