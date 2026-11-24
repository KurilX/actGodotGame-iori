extends SceneTree
## 敌人硬直动画验证
##
## 检查三件事：
##   1. 受击后进入 HURT 并切到 hurt 动画（不是还在播 idle/run）
##   2. hurt 动画帧随硬直时间推进
##   3. 硬直结束后动画恢复播放（不会卡在 hurt 最后一帧）
##
## 运行：godot --headless --path . --script tools/verify_hurt_anim.gd

var _failures: Array[String] = []
var _checks := 0


func _init() -> void:
	var boot: PackedScene = load("res://scenes/bootstrap.tscn")
	root.add_child(boot.instantiate())
	await process_frame
	await process_frame
	for i in 30:
		await physics_frame

	print("── 敌人硬直动画验证 ──")

	# 排除 BOSS（它有自己的受伤表现，且有独立的 verify_boss.gd）
	var enemies := []
	for e in get_nodes_in_group("enemy"):
		if e.get("max_hp") != 120:
			enemies.append(e)
	_check(enemies.size() == 7, "0. 找到 7 个杂兵（按教学段分布）",
	       "实际 %d 个" % enemies.size())

	# 三个敌人都要有 hurt 动画资源
	var all_have := true
	var missing := ""
	for e in enemies:
		var anim = e.get_node_or_null("Anim")
		if anim == null:
			all_have = false
			missing = str(e.name) + " 没有 Anim 节点"
			break
		if not anim.sprite_frames.has_animation("hurt"):
			all_have = false
			missing = str(e.name) + " 缺 hurt 动画"
			break
		if anim.sprite_frames.get_frame_count("hurt") < 3:
			all_have = false
			missing = "%s hurt 只有 %d 帧" % [
				e.name, anim.sprite_frames.get_frame_count("hurt")]
			break
	_check(all_have, "1. 三个敌人都配了至少 3 帧 hurt 动画", missing)

	# 逐个验证：受击 → 播 hurt → 结束恢复
	for e in enemies:
		var anim = e.get_node_or_null("Anim")
		e.state = 1                     # CHASE，确保不是 IDLE
		await physics_frame
		var before_anim: String = anim.animation

		e.take_hit(2, e.global_position.x + 50.0)   # 轻攻击，一定被打断
		await physics_frame
		await physics_frame

		_check(e.state == 4, "%s：受击后进入 HURT" % e.name,
		       "state = %d" % e.state)
		_check(anim.animation == "hurt",
		       "%s：切到 hurt 动画（受击前是 %s）" % [e.name, before_anim],
		       "实际动画 = %s" % anim.animation)

		# 观察帧推进
		var frames_seen := {}
		for i in 20:
			await physics_frame
			if e.state == 4:
				frames_seen[anim.frame] = true
		_check(frames_seen.size() >= 2,
		       "%s：hurt 动画帧会推进" % e.name,
		       "只看到帧 %s" % str(frames_seen.keys()))

		# 硬直结束
		for i in 40:
			await physics_frame
		_check(e.state != 4, "%s：硬直会结束" % e.name,
		       "state 仍为 HURT")
		_check(anim.animation != "hurt" or anim.is_playing(),
		       "%s：硬直结束后动画恢复播放" % e.name,
		       "仍停在 hurt 且未播放")

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
