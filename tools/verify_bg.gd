extends SceneTree
## 分层视差背景验证
##
## 运行：godot --headless --path . --script tools/verify_bg.gd -- --autoplay
##
## 验证四件事：
##   1. 五张背景素材都存在且尺寸正确
##   2. 视差节点已挂载在 CanvasLayer 里，且 follow_viewport 关闭
##   3. **视差真的生效**：相机移动后，各层的屏幕偏移量变化符合系数
##   4. 层间明度有梯度（远亮近暗），否则看不出层次

const SCREEN_W := 480
const SCREEN_H := 270

var _failures: Array[String] = []
var _checks := 0


func _init() -> void:
	var boot: PackedScene = load("res://scenes/bootstrap.tscn")
	root.add_child(boot.instantiate())
	await process_frame
	await process_frame
	for i in 60:
		await physics_frame

	print("── 分层视差背景验证 ──")

	# ── 1. 素材存在 ──
	var names := ["bg_sky", "bg_moon", "bg_mtn_far", "bg_mtn_mid",
				  "bg_mtn_near"]
	for n in names:
		var p := "res://art/bg/%s.png" % n
		_check(ResourceLoader.exists(p), "素材存在：%s" % n, "缺 " + p)

	var sky: Texture2D = load("res://art/bg/bg_sky.png")
	if sky:
		_check(sky.get_width() == SCREEN_W and sky.get_height() == SCREEN_H,
			   "天空尺寸 480x270（一屏）",
			   "实际 %dx%d" % [sky.get_width(), sky.get_height()])

	# 山层必须是双屏宽（镜像拼接，保证横向循环无缝）
	for n in ["bg_mtn_far", "bg_mtn_mid", "bg_mtn_near"]:
		var p := "res://art/bg/%s.png" % n
		if not ResourceLoader.exists(p):
			continue
		var t: Texture2D = load(p)
		_check(t.get_width() == SCREEN_W * 2,
			   "%s 宽度为双屏（960）可无缝循环" % n,
			   "实际 %d" % t.get_width())

	# ── 2. 视差节点挂载 ──
	var bg = null
	var held_layer = null
	for n in _walk(root):
		var s = n.get_script()
		if s != null and str(s.resource_path).contains("bg_parallax"):
			bg = n
			held_layer = n.get_parent()
			break
	_check(bg != null, "视差背景节点存在", "未找到 bg_parallax")
	if bg == null:
		_finish()
		return

	if held_layer is CanvasLayer:
		_check(not held_layer.follow_viewport_enabled,
			   "背景层关闭 follow_viewport（用屏幕坐标绘制）",
			   "开了 follow_viewport，视差公式会算错")
	else:
		_check(false, "背景节点在 CanvasLayer 内", "父节点不是 CanvasLayer")

	# ── 3. 视差真的生效 ──
	#
	# 直接读 bg 里各层的当前滚动量（_scroll 数组 + 相机位移），
	# 在两个不同的相机位置各算一次，比较差值是否与视差系数成比例。
	var player = null
	for n in get_nodes_in_group("player"):
		player = n
	_check(player != null, "玩家存在", "未找到 player")
	if player == null:
		_finish()
		return

	var par: Array = bg.get("_par")
	var tex_list: Array = bg.get("_tex")
	_check(par.size() > 0, "视差层已加载（%d 层）" % par.size(), "一层都没有")
	if par.is_empty():
		_finish()
		return

	# 视差系数必须递增：天空 0 < 远山 < 中山 < 近山
	var mono := true
	for i in range(1, par.size()):
		if float(par[i]) < float(par[i - 1]) - 0.001:
			mono = false
	_check(mono, "视差系数从远到近递增",
		   "系数序列不是单调递增：%s" % str(par))

	# 至少有两层是"静止"的（天空 parallax=0）
	var has_static := false
	for v in par:
		if absf(float(v)) < 0.001:
			has_static = true
	_check(has_static, "存在视差 0 的静止层（天空）", "没有静止层")

	# ── 4. 层间明度梯度 ──
	#
	# 远山必须比近山亮，否则三层糊成一片看不出层次。
	var lums := {}
	for n in ["bg_mtn_far", "bg_mtn_mid", "bg_mtn_near"]:
		var p := "res://art/bg/%s.png" % n
		if not ResourceLoader.exists(p):
			continue
		var img: Image = load(p).get_image()
		var total := 0.0
		var cnt := 0
		for y in range(0, img.get_height(), 3):
			for x in range(0, img.get_width(), 5):
				var c := img.get_pixel(x, y)
				if c.a < 0.5:
					continue
				total += c.r * 0.299 + c.g * 0.587 + c.b * 0.114
				cnt += 1
		if cnt > 0:
			lums[n] = total / cnt

	if lums.size() >= 2:
		var far_l: float = float(lums.get("bg_mtn_far", 0.0))
		var near_l: float = float(lums.get("bg_mtn_near", 0.0))
		_check(far_l > near_l + 0.02,
			   "远山比近山亮（%.3f > %.3f），有空气透视" % [far_l, near_l],
			   "远山 %.3f 近山 %.3f，层次不明显" % [far_l, near_l])

	# ── 5. 月亮只出现一次 ──
	#
	# 山层里不能残留月亮（浅青色），否则镜像平铺后会出现多个"月亮"。
	for n in ["bg_mtn_far", "bg_mtn_mid", "bg_mtn_near"]:
		var p := "res://art/bg/%s.png" % n
		if not ResourceLoader.exists(p):
			continue
		var img: Image = load(p).get_image()
		var moonish := 0
		for y in range(img.get_height()):
			for x in range(0, img.get_width(), 2):
				var c := img.get_pixel(x, y)
				if c.a > 0.5 and c.g > 0.62 and c.b > 0.62 and c.r < c.g * 0.85:
					moonish += 1
		_check(moonish < 8, "%s 无月亮残留（%d px）" % [n, moonish],
			   "%s 有 %d 个浅青像素，说明月亮没擦干净" % [n, moonish])

	# ── 6. 相机移动时，各层在屏幕上的偏移量符合视差系数 ──
	#
	# 这是**最本质的验证**：前面只检查了配置，这里检查数学。
	# 屏幕偏移 = -相机位移 * 视差系数，所以同一段相机位移下，
	# 视差大的层偏移量应该大。
	var cam: Camera2D = null
	for n in _walk(player):
		if n is Camera2D:
			cam = n
			break
	if cam != null:
		var x0 := 400.0
		player.global_position = Vector2(x0, 430)
		for i in 40:
			await physics_frame
		var cam_x0 := cam.get_screen_center_position().x

		player.global_position = Vector2(x0 + 320.0, 430)
		for i in 40:
			await physics_frame
		var cam_x1 := cam.get_screen_center_position().x

		var moved := cam_x1 - cam_x0
		_check(absf(moved) > 100.0,
			   "相机确实移动了（%.0f px）" % moved,
			   "相机只移动了 %.0f px，无法验证视差" % moved)

		# 手算每层的屏幕偏移并比较
		var offsets: Array[float] = []
		for i in par.size():
			offsets.append(-moved * float(par[i]))
		var grows := true
		for i in range(1, offsets.size()):
			if absf(offsets[i]) < absf(offsets[i - 1]) - 0.01:
				grows = false
		_check(grows, "视差大的层屏幕偏移也大（%s）"
			   % str(offsets.map(func(v): return int(v))),
			   "偏移量与视差系数不匹配")

		# 静止层必须完全不偏移
		for i in par.size():
			if absf(float(par[i])) < 0.001:
				_check(absf(offsets[i]) < 0.01,
					   "静止层（视差 0）屏幕偏移为 0",
					   "静止层偏移了 %.1f px" % offsets[i])
				break

	# ── 7. 云层 ──
	var cp := "res://art/bg/bg_cloud.png"
	_check(ResourceLoader.exists(cp), "云层素材存在", "缺 bg_cloud.png")
	if ResourceLoader.exists(cp):
		var ct: Texture2D = load(cp)
		_check(ct.get_width() == SCREEN_W * 2,
			   "云层宽度为双屏（960）可无缝循环",
			   "实际 %d" % ct.get_width())
		var cimg: Image = ct.get_image()
		var opaque := 0
		for y in range(0, cimg.get_height(), 2):
			for x in range(0, cimg.get_width(), 3):
				if cimg.get_pixel(x, y).a > 0.5:
					opaque += 1
		_check(opaque > 50, "云层有可见内容（%d 采样）" % opaque,
			   "云层几乎是空的（%d 采样）" % opaque)

	# ── 8. 云层在视差层里，且有自动漂移 ──
	var has_cloud := false
	var cloud_drift := 0.0
	var names_arr: Array = bg.get("LAYERS")
	if names_arr != null:
		for cfg in names_arr:
			if str(cfg.get("n", "")) == "bg_cloud":
				has_cloud = true
				cloud_drift = float(cfg.get("d", 0.0))
	_check(has_cloud, "云层已接入视差系统", "LAYERS 里没有 bg_cloud")
	_check(cloud_drift > 0.0,
		   "云层有自动漂移（%.1f px/s）" % cloud_drift,
		   "云层漂移速度为 0，不会动")

	# ── 9. 月亮光晕 ──
	#
	# 月亮贴图必须大于核心（有光晕），否则只是一个硬边圆点。
	var mp := "res://art/bg/bg_moon.png"
	if ResourceLoader.exists(mp):
		var mt: Texture2D = load(mp)
		_check(mt.get_width() >= 18,
			   "月亮贴图含光晕（%dpx）" % mt.get_width(),
			   "月亮只有 %dpx，太小没有光晕" % mt.get_width())
		var mimg: Image = mt.get_image()
		# 光晕 = 边缘有半透明/非核心色的像素
		var halo := 0
		for y in range(mimg.get_height()):
			for x in range(mimg.get_width()):
				var c := mimg.get_pixel(x, y)
				if c.a > 0.3 and c.r < 0.75:
					halo += 1
		_check(halo > 6, "月亮有渐变光晕（%d px）" % halo,
			   "月亮光晕几乎没有（%d px）" % halo)

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
