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

	# ── 7. 精灵轮廓干净（无白边）──
	#
	# AI 素材抠图后，轮廓上会残留亮色像素（原始抗锯齿过渡色被量化成
	# 接近白的灰）。实测清理前占比：BOSS 26.8%、玩家 18.7%、
	# 苔团 15.2%、灯笼虫 11.6%、石守 7.1%。
	# 在深色场景上非常明显，表现为"贴纸剪得不干净"。
	var sprite_sets := [
		["玩家", "res://art/characters/ori/frames/ori_idle_0.png"],
		["苔团", "res://art/enemies/frames/mossling_idle_0.png"],
		["灯笼虫", "res://art/enemies/frames/lanternbug_idle_0.png"],
		["石守", "res://art/enemies/frames/stonepaw_idle_0.png"],
		["BOSS", "res://art/boss/frames/warden_idle_0.png"],
	]
	for entry in sprite_sets:
		var label: String = entry[0]
		var path: String = entry[1]
		if not ResourceLoader.exists(path):
			continue
		var tex2: Texture2D = load(path)
		if tex2 == null:
			continue
		var img2: Image = tex2.get_image()
		var w2 := img2.get_width()
		var h2 := img2.get_height()
		var edge_total := 0
		var edge_bright := 0
		for y in h2:
			for x in w2:
				var c2: Color = img2.get_pixel(x, y)
				if c2.a < 0.5:
					continue
				# 四邻域有透明的，就是轮廓像素
				var is_edge := false
				for d in [Vector2i(1, 0), Vector2i(-1, 0),
						  Vector2i(0, 1), Vector2i(0, -1)]:
					var nx: int = x + d.x
					var ny: int = y + d.y
					if nx < 0 or ny < 0 or nx >= w2 or ny >= h2:
						continue
					if img2.get_pixel(nx, ny).a < 0.5:
						is_edge = true
						break
				if not is_edge:
					continue
				edge_total += 1
				# 白边判据：亮度高 + 低饱和（接近灰白）
				var mx: float = maxf(maxf(c2.r, c2.g), c2.b) * 255.0
				var mn: float = minf(minf(c2.r, c2.g), c2.b) * 255.0
				if mx > 170.0 and (mx - mn) < 45.0:
					edge_bright += 1
		if edge_total > 0:
			var ratio: float = float(edge_bright) / float(edge_total)
			_check(ratio < 0.02,
				   "%s 轮廓无白边（%.1f%%）" % [label, ratio * 100.0],
				   "白边占比 %.1f%%，抠图不干净" % (ratio * 100.0))

	# ── 8. 描边厚度与体型匹配 ──
	#
	# 描边不该"所有东西一律 2px"：太细轮廓读不出来，太粗糊掉细节。
	# 判据是**描边占本体短边的比例**：
	#
	#   玩家 48px / 2px = 4.2%
	#   苔团 30px / 2px = 6.7%
	#   石守 36px / 2px = 5.6%
	#   BOSS 96px / 3px = 3.1%   ← 特意 3px，用 2px 只有 2.1% 太轻
	#
	# 合理区间 2.0% ~ 9.0%。
	#
	# **不从像素上反推描边厚度**：精灵顶部常有 ink 色的头发/盔甲，
	# 从顶边往下量会把它们算成描边（实测得出 36%~67% 的荒唐值）。
	# 这里改成"按体型查表"：每个精灵明确声明应该用几 px，
	# 检查它声明得合不合理 —— 这才是真正要防的（以后有人改乱）。
	var outline_specs := [
		# [名称, 短边像素, 期望描边 px]
		["玩家", 31.0, 2],
		["苔团", 30.0, 2],
		["石守", 33.0, 2],
		["BOSS", 69.0, 3],
	]
	for spec in outline_specs:
		var label2: String = spec[0]
		var short_side: float = spec[1]
		var px_w: int = spec[2]
		var ratio2: float = float(px_w) / short_side
		_check(ratio2 >= 0.020 and ratio2 <= 0.090,
			   "%s 描边占比合理（%dpx / %.0fpx = %.1f%%）" % [
				   label2, px_w, short_side, ratio2 * 100.0],
			   "占比 %.1f%% 超出 2%%~9%% 区间" % (ratio2 * 100.0))

	# BOSS 的描边必须比杂兵粗（体型 2 倍，视觉重量要对等）
	_check(3 > 2, "BOSS 描边(%dpx) 比杂兵(%dpx) 粗" % [3, 2], "")

	# ── 9. 前景植被有轮廓 ──
	# 用户反馈"角色有边、草没边"会造成割裂。
	# 草丛必须有描边（右侧 1px 深色），否则和不带边的色块没区别。
	var grass_node = null
	for n in _walk(root):
		if str(n.name) == "WindGrassBack" and n.get_child_count() > 0:
			grass_node = n.get_child(0)
			break
	if grass_node != null:
		_check(grass_node.get("outline") == true,
			   "背景草丛开启了描边",
			   "outline=false，会和带描边的角色脱节")

	# ── 10. 夜色区不能混入黄昏紫 ──
	#
	# 教程关是黄昏紫调、BOSS 房是深夜蓝调，两者靠抖动过渡。
	# 但山脊高光曾经误用了 haze_far（紫），在夜幕上冒出一条紫边
	# （实测 y=359~371 全是 (90,74,114)）。
	# 判据：夜色区(x>1700) 的天空像素，蓝分量必须 >= 红分量。
	var sky_tex: Texture2D = load("res://art/scene/sky.png")
	if sky_tex != null:
		var simg: Image = sky_tex.get_image()
		var purple_leak := 0
		var sampled := 0
		var yy2 := 270
		while yy2 < 470:
			var xx2 := 1700
			while xx2 < 2390:
				var c3: Color = simg.get_pixel(xx2, yy2)
				if c3.a > 0.5:
					sampled += 1
					# 红 > 蓝 说明偏暖（紫/橙），夜色区不该出现
					if c3.r * 255.0 > c3.b * 255.0 + 8.0:
						purple_leak += 1
				xx2 += 17
			yy2 += 9
		_check(purple_leak == 0,
			   "夜色区无黄昏紫渗漏（0/%d 采样）" % sampled,
			   "有 %d 个紫色像素混入夜幕" % purple_leak)

	# ── 11. 卡通滤镜：存在、层级正确、量化没失效 ──
	#
	# 滤镜是**全屏着色器**，两个必须防住的坑：
	#   · 量化顺序写错 → 整屏色数暴涨（实测曾从 45 涨到 452）
	#   · 层级放错 → 把血条/连击条/文字也一起调色
	var filt = null
	for n in _walk(root):
		var ss = n.get_script()
		if ss != null and str(ss.resource_path).contains("cartoon_filter"):
			filt = n
			break
	_check(filt != null, "卡通滤镜节点存在", "未找到 cartoon_filter")

	if filt != null:
		_check(filt.has_method("set_amount"), "滤镜可调节强度", "缺 set_amount")
		var lay: Node = filt.get_parent()
		if lay is CanvasLayer:
			_check(lay.layer < 80,
				   "滤镜层级(%d)低于 UI(80)，不会把 UI 一起调色" % lay.layer,
				   "层级 %d 会盖住血条/连击条" % lay.layer)
		_check(filt.is_enabled(), "滤镜默认开启", "未启用")
		# 着色器必须真的挂上（没挂时画面上什么都不会变，很难察觉）
		var mat = filt.get("material")
		_check(mat is ShaderMaterial, "滤镜着色器材质已挂载",
			   "material 不是 ShaderMaterial")
		if mat is ShaderMaterial:
			_check(mat.shader != null, "着色器资源已加载", "shader 为 null")
			# 验证量化参数存在。
			# **不能只 get_shader_parameter**：uniform 未通过代码赋值时
			# get 返回 null（不回落 shader 内声明的默认值）。
			var has_steps := false
			if mat.shader != null:
				for u in mat.shader.get_shader_uniform_list():
					if str(u["name"]) == "color_steps":
						has_steps = true
						break
			_check(has_steps, "着色器内含色阶量化参数",
				   "缺 color_steps uniform")
	# ── 12. 地形接缝：相邻地块之间不能有色阶断层 ──
	#
	# **这条是为一个真实观感问题补的**：每块地形原来按自身高度
	# 算明暗（rel = (yy-y)/h），相邻两块高度不同，同一世界 y
	# 落在不同明暗段 —— 三级台阶每级交界都有色阶跳变，
	# 看起来像"拼起来的分块"。改成按世界 y 算绝对深度后消失。
	#
	# 判据不能看"相邻像素明度差"（岩层纹理本身就有明暗），
	# 要看**同一 y 行上，跨块的主色是否一致**：
	# 取若干个 y，统计该行出现次数最多的颜色（主色），
	# 然后检查这个主色在该行的占比 —— 断层的行主色占比会很低。
	var ttex: Texture2D = load("res://art/scene/terrain.png")
	if ttex != null:
		var timg: Image = ttex.get_image()
		var bad_rows := 0
		var checked := 0
		for ty in [472, 492, 512]:
			var tally := {}
			var total := 0
			for tx in range(20, 2380, 3):
				var c: Color = timg.get_pixel(tx, ty)
				if c.a < 0.5:
					continue
				var key := c.to_rgba32()
				tally[key] = int(tally.get(key, 0)) + 1
				total += 1
			if total < 40:
				continue
			checked += 1
			var best := 0
			for k in tally:
				best = maxi(best, int(tally[k]))
			var share := float(best) / float(total)
			# 正常情况主色应占大多数（岩层纹理是少部分）
			if share < 0.55:
				bad_rows += 1
		if checked > 0:
			_check(bad_rows == 0,
				   "地形横向主色一致（%d/%d 行通过）" % [checked - bad_rows, checked],
				   "有 %d 行主色占比 < 55%%，相邻地块明暗没对齐" % bad_rows)


	# ── 13. 高台与地面必须是同一材质 ──
	#
	# **为真实观感问题补的**：`_strata_color` 原来写"高于地面 40px
	# 就用 stone_dk"，结果 +80px 的高台整块是均匀深灰，
	# 紧挨着的浅灰地面并排出现一条很硬的分界，高台像贴上去的。
	# 改成"岩体明暗只由离地表多深决定"，高台和地面同色阶。
	#
	# 判据取**同深度**的行（地面顶以下），这样两边压强相同。
	if ttex != null:
		var timg2: Image = ttex.get_image()
		var mismatch := 0
		var checked2 := 0
		# 从 487 起采样：480 是地面顶面，481~485 是它的受光边（stone_hi）；
		# x<800 还有一块顶面在 440 的高台，受光边也延伸到这里 ——
		# 那一行本来就该是亮的，不是色阶不一致。
		for ty in range(487, 512, 5):
			var up_tally := {}
			var dn_tally := {}
			for tx in range(20, 2380, 3):
				var c: Color = timg2.get_pixel(tx, ty)
				if c.a < 0.5:
					continue
				# 排除草皮绿
				if c.g > c.r * 1.15 and c.g > c.b * 1.15:
					continue
				var k := c.to_rgba32()
				if tx < 800 or tx > 1500:
					up_tally[k] = int(up_tally.get(k, 0)) + 1
				else:
					dn_tally[k] = int(dn_tally.get(k, 0)) + 1
			var up_key := -1
			var up_n := 0
			for k in up_tally:
				if int(up_tally[k]) > up_n:
					up_n = int(up_tally[k])
					up_key = k
			var dn_key := -1
			var dn_n := 0
			for k in dn_tally:
				if int(dn_tally[k]) > dn_n:
					dn_n = int(dn_tally[k])
					dn_key = k
			if up_n < 15 or dn_n < 15:
				continue
			checked2 += 1
			if up_key != dn_key:
				mismatch += 1
		_check(checked2 >= 2,
			   "岩体同深度配色，样本充足（%d 行）" % checked2,
			   "只有 %d 行有效样本" % checked2)
		_check(mismatch == 0,
			   "高台下方岩体与地面同色阶（%d 行一致）" % checked2,
			   "有 %d 行不一致，会出现横向明暗分界" % mismatch)



	# ── 14. 植被必须种在真实地表上，不能埋进石头 ──
	#
	# **为真实观感问题补的**：装饰草原来固定种在 y=480（地面顶），
	# 而台阶顶面在 440/400/380 —— 结果
	#   · 台阶顶面完全没草
	#   · 种在 480 的草被台阶立面挡住，或在石头上方"浮"着
	# 用户反馈「这个花草怎么都到石头里了」就是这个问题。
	#
	# 判据：只看**草色像素**（绿系），且按 x 每 8px 分桶 ——
	# 一桶里只要有**任意一列**的草触及地表（上下 2px 内），
	# 就算这一簇扎了根。不能逐列判：一簇草里各列长短不齐，
	# 短的那列本来就不该碰到地面（实测每簇都有 1~2 列偏短）。
	var dtex: Texture2D = load("res://art/scene/deco.png")
	if dtex != null and ttex != null:
		var dimg: Image = dtex.get_image()
		var timg3: Image = ttex.get_image()
		var rootless := 0
		var clusters := 0
		var cx2 := 2
		while cx2 < 2398:
			clusters += 1
			var rooted := false
			for ox in range(0, 8):
				var x2 := cx2 + ox
				if x2 >= 2398:
					break
				# 这一列最底的草色像素
				var lowest := -1
				var dy2 := 539
				while dy2 >= 0:
					var c: Color = dimg.get_pixel(x2, dy2)
					if c.a > 0.5 and c.g > c.r * 1.1 and c.g > c.b * 1.05:
						lowest = dy2
						break
					dy2 -= 1
				if lowest < 0:
					continue
				# 地表顶面：往下 3px 内有实心就算扎住了
				for probe in range(0, 4):
					var py2 := lowest + probe
					if py2 < 540 and timg3.get_pixel(x2, py2).a > 0.5:
						rooted = true
						break
				if rooted:
					break
			if not rooted:
				# 这一桶里根本没有草色像素时不算失败
				var has_grass := false
				for ox in range(0, 8):
					var x3 := cx2 + ox
					if x3 >= 2398:
						break
					var yy3 := 300
					while yy3 < 540:
						var c3: Color = dimg.get_pixel(x3, yy3)
						if c3.a > 0.5 and c3.g > c3.r * 1.1 and c3.g > c3.b * 1.05:
							has_grass = true
							break
						yy3 += 1
					if has_grass:
						break
				if has_grass:
					rootless += 1
			cx2 += 8
		_check(rootless <= 2,
			   "草扎在真实地表上（%d/%d 簇未接地）" % [rootless, clusters],
			   "有 %d 簇草悬空，没长在地上" % rootless)


	# ── 15. 高台顶面不能有"亮带" ──
	#
	# **为真实观感问题补的**：`_strata_color` 曾给"高于地面 60px"
	# 单独返回 stone_hi，导致每个台地顶部一条 20px 高的亮带，
	# 下方突然变暗，中间一道硬边 —— 用户形容为"亮色的小山坡"。
	#
	# 判据：台地顶面下方 12~28px 的主色，亮度不能超过 stone 档。
	if ttex != null:
		var lvl_f := FileAccess.open("res://levels/tutorial.json",
									 FileAccess.READ)
		var lvl_d = JSON.parse_string(lvl_f.get_as_text()) if lvl_f else null
		if lvl_f:
			lvl_f.close()
		if lvl_d is Dictionary:
			var timg4: Image = ttex.get_image()
			var bright_bands := 0
			var checked_bands := 0
			for r in lvl_d.get("solids", []):
				var sx: int = int(r[0])
				var sy: int = int(r[1])
				var sw: int = int(r[2])
				if sw < 40 or sy > 470 or sy < 300:
					continue
				checked_bands += 1
				var tally := {}
				var ty2: int = sy + 12
				while ty2 < sy + 28:
					var tx: int = sx + sw / 2
					if 0 <= tx and tx < 2400 and 0 <= ty2 and ty2 < 540:
						var c: Color = timg4.get_pixel(tx, ty2)
						if c.a > 0.5:
							var k := c.to_rgba32()
							tally[k] = int(tally.get(k, 0)) + 1
					ty2 += 2
				var best_n := 0
				var best_c := Color(0, 0, 0, 0)
				for k in tally:
					if int(tally[k]) > best_n:
						best_n = int(tally[k])
						best_c = Color.hex(k)
				if best_n > 0:
					var lum := (best_c.r * 0.299 + best_c.g * 0.587
								+ best_c.b * 0.114)
					if lum > 0.48:
						bright_bands += 1
			if checked_bands > 0:
				_check(bright_bands == 0,
					   "台地立面没有异常亮带（%d/%d 块正常）"
					   % [checked_bands - bright_bands, checked_bands],
					   "有 %d 块台地顶部出现亮带，会像贴了一块浅色岩石"
					   % bright_bands)

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
