extends SceneTree
## 场景美术规范验证：调色板约束、动态植被、风吹动画
##
## 运行：godot --headless --path . --script tools/verify_art.gd -- --autoplay
##
## 这些断言对应 docs/02-像素美术规范.md 的硬性要求，
## 以及用户明确提出的"要有会动的体现被风吹的装饰物"。

var _failures: Array[String] = []
var _checks := 0

# 28 色硬上限（docs/02-像素美术规范.md）
const MAX_COLORS := 28


func _init() -> void:
	var boot: PackedScene = load("res://scenes/bootstrap.tscn")
	root.add_child(boot.instantiate())
	await process_frame
	await process_frame
	for i in 40:
		await physics_frame

	print("── 场景美术验证 ──")

	# ── 1. 三层贴图存在且尺寸与关卡一致 ──
	var layers := ["sky", "terrain", "deco"]
	for name in layers:
		var path := "res://art/scene/%s.png" % name
		_check(ResourceLoader.exists(path), "%s.png 存在" % name, "缺文件")
		var tex: Texture2D = load(path)
		if tex is Texture2D:
			_check(tex.get_width() == 2400,
				   "%s.png 宽度 2400（与关卡一致）" % name,
				   "实际 %d" % tex.get_width())

	# ── 2. 用色不超 28 ──
	var all_colors := {}
	for name in layers:
		var tex: Texture2D = load("res://art/scene/%s.png" % name)
		if not (tex is Texture2D):
			continue
		var img: Image = tex.get_image()
		for y in range(0, img.get_height(), 3):
			for x in range(0, img.get_width(), 3):
				var c: Color = img.get_pixel(x, y)
				if c.a > 0.1:
					all_colors[c.to_rgba32()] = true
	_check(all_colors.size() <= MAX_COLORS,
		   "三层贴图合计用色 ≤ %d（实际 %d）" % [MAX_COLORS,
											 all_colors.size()],
		   "超出调色板，违反了 28 色硬上限")

	# ── 3. 动态植被存在 ──
	var found := {"grass_back": -1, "grass_front": -1,
				  "flowers": -1, "petals": -1}
	for n in _walk(root):
		var nm := str(n.name)
		if nm == "WindGrassBack":
			found["grass_back"] = n.get_child_count()
		elif nm == "WindGrassFront":
			found["grass_front"] = n.get_child_count()
		elif nm == "WindFlowers":
			found["flowers"] = n.get_child_count()
		elif nm == "WindPetals":
			found["petals"] = n.item_count() if n.has_method("item_count") \
				else -1

	_check(found["grass_back"] > 20,
		   "背景草丛存在（%d 丛）" % found["grass_back"],
		   "只有 %d 丛，太少" % found["grass_back"])
	_check(found["grass_front"] > 5,
		   "前景草丛存在（%d 丛）" % found["grass_front"],
		   "只有 %d 丛" % found["grass_front"])
	_check(found["flowers"] > 3,
		   "野花存在（%d 朵）" % found["flowers"],
		   "只有 %d 朵" % found["flowers"])
	_check(found["petals"] > 10,
		   "飘落花瓣存在（%d 个）" % found["petals"],
		   "只有 %d 个" % found["petals"])

	# ── 4. **植被真的会动**（用户明确要求"体现被风吹"）──
	var grass = null
	for n in _walk(root):
		if str(n.name) == "WindGrassBack" and n.get_child_count() > 0:
			grass = n.get_child(0)
			break
	_check(grass != null, "取到一棵草做动画验证", "没找到")
	if grass != null:
		var b1: float = grass.current_bend()
		for i in 25:
			await physics_frame
		var b2: float = grass.current_bend()
		_check(absf(b1 - b2) > 0.05,
			   "草会随风弯曲（%.2f → %.2f）" % [b1, b2],
			   "两次采样相同，草是静止的")

	# ── 5. 花瓣在移动 ──
	var petals = null
	for n in _walk(root):
		if str(n.name) == "WindPetals":
			petals = n
			break
	if petals != null and petals.has_method("sample_positions"):
		var p1: Array = petals.sample_positions()
		for i in 20:
			await physics_frame
		var p2: Array = petals.sample_positions()
		var moved := 0
		for i in mini(p1.size(), p2.size()):
			if p1[i].distance_to(p2[i]) > 0.5:
				moved += 1
		_check(moved > p1.size() / 2,
			   "花瓣在飘动（%d/%d 移动）" % [moved, p1.size()],
			   "大部分花瓣没动")

	# ── 6. 地形与实际碰撞一致（防止贴图和碰撞体错位）──
	var room = null
	for n in _walk(root):
		var s = n.get_script()
		if s != null and str(s.resource_path).contains("room_greybox"):
			room = n
			break
	_check(room != null, "房间节点存在", "没找到")
	if room != null:
		var solids: Array = room.SOLIDS
		# 地面必须贯穿全图
		var ground_ok := false
		for s in solids:
			if int(s[0]) == 0 and int(s[2]) >= 2400:
				ground_ok = true
		_check(ground_ok, "地面贯穿全图（贴图与碰撞一致的前提）",
			   "地面没有铺满")

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
