extends SceneTree
## 关卡系统验证：ASCII 关卡生成 + JSON 加载 + 地形可达性
##
## 运行：godot --headless --path . --script tools/verify_level.gd -- --autoplay
##
## 背景：关卡从「硬编码坐标」改成「ASCII 字符画 + 生成器」，
## 这里验证整条链路：.lvl → .json → 游戏内碰撞体。

var _failures: Array[String] = []
var _checks := 0


func _init() -> void:
	var boot: PackedScene = load("res://scenes/bootstrap.tscn")
	root.add_child(boot.instantiate())
	await process_frame
	await process_frame
	for i in 60:
		await physics_frame

	print("── 关卡系统验证 ──")

	# ── 1. 源文件与编译产物都在 ──
	var lvl_path := "res://levels/tutorial.lvl"
	var json_path := "res://levels/tutorial.json"
	_check(FileAccess.file_exists(lvl_path),
		   "1. ASCII 关卡源文件存在（tutorial.lvl）", "缺 .lvl")
	_check(FileAccess.file_exists(json_path),
		   "2. 编译产物存在（tutorial.json）",
		   "缺 .json，跑 python tools/build_level.py")

	# ── 2. JSON 结构完整 ──
	var f := FileAccess.open(json_path, FileAccess.READ)
	var data = JSON.parse_string(f.get_as_text()) if f else null
	f.close() if f else null
	_check(data is Dictionary, "3. JSON 可解析", "解析失败")
	if not (data is Dictionary):
		_finish()
		return

	_check(data.has("solids") and data.has("one_way")
		   and data.has("entities"), "4. JSON 含地形/平台/实体三段",
		   "字段缺失")
	var solids: Array = data.get("solids", [])
	_check(solids.size() > 0, "5. 实心地形非空（%d 块）" % solids.size(),
		   "没有地形，玩家会掉下去")

	# ── 3. 地图尺寸与房间一致 ──
	var w: int = int(data.get("width", 0))
	var h: int = int(data.get("height", 0))
	_check(w == 2400, "6. 关卡宽度 2400", "实际 %d" % w)
	_check(h == 540, "7. 关卡高度 540", "实际 %d" % h)

	# ── 4. 必须有玩家出生点 ──
	var spawn_found := false
	var spawn_pos := Vector2.ZERO
	var boss_found := false
	for ent in data.get("entities", []):
		var kind := str(ent.get("kind", ""))
		if kind == "spawn_player":
			spawn_found = true
			spawn_pos = Vector2(float(ent["x"]), float(ent["y"]))
		elif kind == "spawn_boss":
			boss_found = true
	_check(spawn_found, "8. 有玩家出生点", "地图里没有 P")
	_check(boss_found, "9. 有 BOSS 出生点", "地图里没有 B")

	# ── 5. 游戏内实际加载的数据与 JSON 一致 ──
	var room = null
	for n in _walk(root):
		var s = n.get_script()
		if s != null and str(s.resource_path).contains("room_greybox"):
			room = n
			break
	_check(room != null, "10. 房间节点存在", "未找到")
	if room != null:
		var in_game: Array = room.SOLIDS
		_check(in_game.size() == solids.size(),
			   "11. 游戏内地形块数与 JSON 一致（%d）" % in_game.size(),
			   "JSON 有 %d，游戏内 %d" % [solids.size(), in_game.size()])
		_check(int(room.ROOM_W) == w, "12. 游戏内房间宽度与 JSON 一致",
			   "游戏 %d / JSON %d" % [room.ROOM_W, w])

	# ── 6. 玩家出生后不会掉出地图 ──
	var player = null
	for n in get_nodes_in_group("player"):
		player = n
	_check(player != null, "13. 玩家已生成", "未找到")
	if player != null:
		# 让物理跑一会儿，确认站在地面上
		for i in 90:
			await physics_frame
		_check(player.is_on_floor(), "14. 玩家出生后站在地面上",
			   "没落地，y=%.0f" % player.global_position.y)
		_check(player.global_position.y < float(h) + 20.0,
			   "15. 玩家没有掉出地图底部",
			   "y=%.0f 超出地图高 %d" % [player.global_position.y, h])
		# 出生点附近不该是墙（生成器已经保证离墙 2 格）
		_check(player.global_position.x > 20.0,
			   "16. 出生点离左墙有距离",
			   "x=%.0f 贴墙了" % player.global_position.x)

	# ── 7. 地形可达性：台阶高差不超过跳跃极限 ──
	#
	# 玩家跳跃极限实测约 58px。地形的"上表面"如果相邻两块高差
	# 超过这个值，就是跳不上去的死地形。
	var tops: Array[float] = []
	for s in solids:
		var rr: Array = s
		# 只统计能站人的（宽度 ≥ 40px，排除左右墙）
		if int(rr[2]) >= 40 and int(rr[1]) > 20:
			tops.append(float(rr[1]))
	tops.sort()
	var too_high := 0
	for i in range(1, tops.size()):
		var gap: float = absf(tops[i] - tops[i - 1])
		if gap > 60.0:
			too_high += 1
	_check(too_high == 0, "17. 地形层高差都在跳跃极限内",
		   "有 %d 处高差 > 60px" % too_high)

	# ── 8. 单向平台必须可达 ──
	#
	# **这条是为一个真实 bug 补的**：单向平台曾经放在高差 80px 的位置，
	# 而玩家跳跃只有 58px —— 那块板子在视觉上很显眼，
	# 但玩家永远跳不上去，等于画了个假目标。
	#
	# 判据：每段单向平台下方最近的实心顶面，高差必须 ≤ 跳跃极限。
	var ow: Array = data.get("one_way", [])
	print("  info 单向平台 %d 段" % ow.size())
	var jump := 58.0
	for plat in ow:
		var px: float = float(plat[0])
		var py: float = float(plat[1])
		var pw: float = float(plat[2])
		var below := -1.0
		for s in solids:
			var sx: float = float(s[0])
			var sy: float = float(s[1])
			var sw: float = float(s[2])
			# 水平有交集，且在地形下方
			if sx < px + pw and sx + sw > px and sy > py + 10.0:
				if below < 0.0 or sy < below:
					below = sy
		if below < 0.0:
			continue
		var gap := below - py
		_check(gap <= jump,
			   "单向平台 y=%.0f 可达（高差 %.0f ≤ %.0f）" % [py, gap, jump],
			   "高差 %.0f > 跳跃极限 %.0f，玩家跳不上去" % [gap, jump])

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
