extends Node2D
## 灰盒测试房：手动搭建静态碰撞体 + 单向平台
##
## 目的：W1 阶段排除 TileSet 配置的干扰，先把「跑跳砍」手感调出来。
## 场景里的地形全部由本脚本按数据生成，改数据即可改关卡。
## 尺寸按规范：单房间 960 x 540（2 屏宽 x 2 屏高，视口 480x270）

# BOSS 生成后发出，供 UI 层连接血条
signal boss_spawned(boss: Node2D)
# 玩家进入 BOSS 房、BOSS 苏醒时发出 —— UI 层据此显示血条
signal boss_awakened(boss: Node2D)

var boss: Node2D = null

# ── 房间尺寸 ──
#
# 整张地图是一条从左到右的横线，分两大段：
#   x    0 ~ 1560   教程关（5 个教学段，见 docs/04-教程关设计.md）
#   x 1560 ~ 2400   主关卡（BOSS 房）
#
# 为什么合成一个场景而不是两个：
#   1. 现在没有场景切换系统，拆开要额外写加载/过渡
#   2. 横版动作里"走过去"本身就有连续感
#   3. 存档只需记一个坐标，不用记"在哪个场景"
# 以后要拆时，把两段的 SOLIDS 各切一半、加个 transition 节点即可。
var ROOM_W := 2400
var ROOM_H := 540

# 地面顶部 y 坐标（与 SOLIDS 里地面矩形一致）。
# 植被都种在这条线上。
const GROUND_Y_FOR_DECO := 480.0

# 段边界（世界坐标 x）
var TUTORIAL_END := 1560.0
var BOSS_ZONE_START := 1560.0

# ── 关卡数据：从 levels/tutorial.json 读取 ──
#
# 原来 SOLIDS / ONE_WAY / 敌人位置全部硬编码在这个脚本里，
# 改一个台阶要在三处同步（房间脚本、美术脚本 solids、单向平台数组），
# 改完还看不出地形长什么样。
#
# 现在关卡是 `levels/tutorial.lvl`（一张字符画），
# 由 tools/build_level.py 编译成 tutorial.json，本脚本只负责读。
#
# 修改关卡的正确流程：
#   1. 编辑 levels/tutorial.lvl（字符画，形状即地形）
#   2. python tools/build_level.py       ← 编译 + 校验
#   3. python tools/make_scene_art.py    ← 重新生成地形贴图
#   4. godot --headless --path . --import
const LEVEL_PATH := "res://levels/tutorial.json"

# 下面这些在 _load_level() 里填充，保持和原来同名，
# 这样 _build_solids() 等函数不用改。
var SOLIDS: Array = []
# 关卡实体表（敌人/BOSS/木桩），由 _load_level 填充
var _level_entities: Array = []
var ONE_WAY: Array = []
var SPAWN := Vector2(80, 440)


func _load_level() -> bool:
	var f := FileAccess.open(LEVEL_PATH, FileAccess.READ)
	if f == null:
		printerr("关卡文件缺失：" + LEVEL_PATH +
				 "（先跑 python tools/build_level.py）")
		return false
	var txt := f.get_as_text()
	f.close()
	var data = JSON.parse_string(txt)
	if not (data is Dictionary):
		printerr("关卡 JSON 解析失败：" + LEVEL_PATH)
		return false

	# 转成 [x, y, w, h] 数组形式（和原来的常量格式一致）
	SOLIDS = []
	for r in data.get("solids", []):
		SOLIDS.append([int(r[0]), int(r[1]), int(r[2]), int(r[3])])
	ONE_WAY = []
	for r in data.get("one_way", []):
		ONE_WAY.append([int(r[0]), int(r[1]), int(r[2])])

	ROOM_W = int(data.get("width", 2400))
	ROOM_H = int(data.get("height", 540))
	TUTORIAL_END = float(data.get("tutorial_end_x", 1560))
	BOSS_ZONE_START = TUTORIAL_END

	# 实体表（敌人/BOSS/木桩），供 _spawn_from_level 使用
	_level_entities = data.get("entities", [])
	# SPAWN 从实体表里取
	for ent in data.get("entities", []):
		if str(ent.get("kind", "")) == "spawn_player":
			SPAWN = Vector2(float(ent["x"]), float(ent["y"]))

	return true




func _ready() -> void:
	# **必须先加载关卡**：后面的美术尺寸、碰撞体、植被分布、
	# 出生点都依赖 _load_level() 填好的数据。
	if not _load_level():
		printerr("关卡加载失败，使用空地图（玩家会掉下去）")

	_build_visuals()
	_build_solids()
	_build_wind_life()
	_build_one_way()
	_spawn_player()


const WindSprite := preload("res://src/world/wind_sprite.gd")
const WindPetals := preload("res://src/world/wind_petals.gd")



func _surface_y_at(x: float) -> float:
	"""查询世界坐标 x 处"可站表面"的 y。找不到返回 -1。

	## 为什么需要这个

	植被原来固定种在 `GROUND_Y_FOR_DECO`（480，地面顶那一条线）。
	但关卡里有台阶和高台，它们的顶面在 440 / 400 / 360 等位置 ——
	植被种在 480 就全部跑到石头里去了（用户反馈"花草怎么都到石头里了"），
	而台阶顶上光秃秃的。

	这里返回该 x 处**最高的实心地形顶面**，植被就种在真正的地表上。
	"""
	var best := -1.0
	for r in SOLIDS:
		var sx: float = float(r[0])
		var sy: float = float(r[1])
		var sw: float = float(r[2])
		# 只考虑宽度够站人的地形（排除边界墙/天花板）
		if sw < 40.0:
			continue
		if x < sx or x >= sx + sw:
			continue
		# 天花板类是 y 很小、且不是可站表面，跳过
		if sy < 100.0:
			continue
		if best < 0.0 or sy < best:
			best = sy
	return best

func _build_wind_life() -> void:
	"""动态植被：会随风摇摆的草、花、芦苇 + 飘落的花瓣。

	## 为什么用代码画而不是贴图

	一棵会动的草如果逐帧画，12 帧 × 几十棵 = 帧数爆炸，而且每棵的
	摆动相位还必须一致（否则像各摆各的）。用自绘 + 正弦相位：
	  · 一棵草只有几个控制点，绘制开销可忽略
	  · 相位由 x 坐标决定，天然形成"风从右往左推"的波浪
	  · 想加就加，不受美术资源限制

	## 分层

	  z=-4  背景草丛（远、矮、暗，不遮挡）
	  z=-1  前景草丛（近、高、亮，从画面前景探出）
	  z=-3  飘落花瓣（在草丛之上、角色之下）
	"""
	var rng := RandomNumberGenerator.new()
	rng.seed = 20261124

	# ── 背景草丛：沿地面稀疏分布 ──
	var bg := Node2D.new()
	bg.name = "WindGrassBack"
	bg.z_index = -4
	add_child(bg)

	var x := 20.0
	while x < ROOM_W - 20:
		var w: Node2D = WindSprite.new()
		w.wind_freq = rng.randf_range(0.85, 1.25)
		w.wind_amp = rng.randf_range(2.2, 3.4)
		w.wind_speed = rng.randf_range(28.0, 40.0)
		var sy_back := _surface_y_at(x)
		if sy_back < 0.0:
			x += 20.0
			continue
		w.position = Vector2(x, sy_back)
		var n: int = rng.randi_range(3, 6)
		for i in n:
			var h: float = rng.randf_range(9.0, 18.0)
			var dx: float = rng.randf_range(-4.0, 4.0)
			var col_kind: int = rng.randi_range(0, 2)
			var col: Color
			match col_kind:
				0:
					col = Color("#4A6B4F")      # moss
				1:
					col = Color("#2E4634")      # moss_dk
				_:
					col = Color("#5A8A5E")      # grass
			w.add_blade(dx, h, 1.6, col)
		bg.add_child(w)
		x += rng.randf_range(14.0, 34.0)

	# ── 前景草丛：更少但更高，从画面下沿探出 ──
	var fg := Node2D.new()
	fg.name = "WindGrassFront"
	fg.z_index = -1
	add_child(fg)

	x = 40.0
	while x < ROOM_W - 40:
		var w2: Node2D = WindSprite.new()
		w2.wind_freq = rng.randf_range(0.9, 1.3)
		w2.wind_amp = rng.randf_range(3.4, 5.2)   # 前景摆幅更大
		var sy_front := _surface_y_at(x)
		if sy_front < 0.0:
			x += 60.0
			continue
		w2.position = Vector2(x, sy_front + 4.0)
		for i in rng.randi_range(4, 7):
			var h2: float = rng.randf_range(14.0, 26.0)
			w2.add_blade(rng.randf_range(-6.0, 6.0), h2, 1.4,
						 Color("#5A8A5E") if rng.randf() < 0.6
						 else Color("#6E9A6B"))
		fg.add_child(w2)
		x += rng.randf_range(55.0, 110.0)

	# ── 小野花：点缀在草丛之间 ──
	var flowers := Node2D.new()
	flowers.name = "WindFlowers"
	flowers.z_index = -3
	add_child(flowers)
	x = 60.0
	while x < ROOM_W - 60:
		var fw: Node2D = WindSprite.new()
		fw.wind_freq = rng.randf_range(1.0, 1.4)
		fw.wind_amp = rng.randf_range(2.8, 4.0)
		var sy_flow := _surface_y_at(x)
		if sy_flow < 0.0:
			x += 90.0
			continue
		fw.position = Vector2(x, sy_flow)
		# 花茎
		fw.add_blade(0.0, rng.randf_range(9.0, 15.0), 1.0,
					 Color("#4A6B4F"))
		flowers.add_child(fw)
		# 花冠：用自绘节点画一个小十字花
		var petal: Node2D = Node2D.new()
		petal.position = Vector2(x, sy_flow - 12.0)
		petal.z_index = -3
		petal.set_script(preload("res://src/world/wind_flower.gd"))
		petal.set("petal_color", Color("#FFB8D0") if rng.randf() < 0.7
				  else Color("#FFE9A8"))
		petal.set("stem_x", x)
		add_child(petal)
		x += rng.randf_range(70.0, 150.0)

	# ── 飘落花瓣 ──
	var petals := WindPetals.new()
	petals.name = "WindPetals"
	add_child(petals)


func _build_solids() -> void:
	for r in SOLIDS:
		var body := StaticBody2D.new()
		body.collision_layer = 1
		body.collision_mask = 0
		body.position = Vector2(r[0] + r[2] * 0.5, r[1] + r[3] * 0.5)

		var shape := CollisionShape2D.new()
		var rect := RectangleShape2D.new()
		rect.size = Vector2(r[2], r[3])
		shape.shape = rect
		body.add_child(shape)
		add_child(body)


func _build_one_way() -> void:
	for r in ONE_WAY:
		var body := StaticBody2D.new()
		body.collision_layer = 1
		body.collision_mask = 0
		body.position = Vector2(r[0] + r[2] * 0.5, r[1] + 3)

		var shape := CollisionShape2D.new()
		var rect := RectangleShape2D.new()
		rect.size = Vector2(r[2], 6)
		shape.shape = rect
		# 单向平台：只能从上方落下时挡住
		shape.one_way_collision = true
		body.add_child(shape)
		add_child(body)


func _build_visuals() -> void:
	# ── 三层场景美术（art/scene/ 下由 tools/make_scene_art.py 生成）──
	#
	# z_index 分层：
	#   sky     -20  夜空 + 远山 + 月亮
	#   terrain -10  石台（有顶面明暗、砖缝、苔藓）
	#   deco     -2  草丛 / 紫藤 / 灯笼（在地形之上、角色之下）
	#
	# 三张图都是 ROOM_W x ROOM_H（2400x540）全尺寸，直接 Sprite2D 贴上，
	# 位置放在房间原点、centered=false。
	#
	# 为什么要换成贴图而不是继续用 Polygon2D：
	# 灰盒的纯色块拼不出石块纹理、苔藓边缘、月光光晕这些细节，
	# 而程序化生成贴图可以精确控制到像素，且能复用同一套调色板。
	var layers := [
		["sky", -20],
		["terrain", -10],
		["deco", -2],
	]
	for entry in layers:
		var lname: String = entry[0]
		var z: int = entry[1]
		var path := "res://art/scene/%s.png" % lname
		if not ResourceLoader.exists(path):
			# 缺素材时退回纯色底，避免房间一片黑
			printerr("场景素材缺失: %s（先跑 tools/make_scene_art.py）" % path)
			if lname == "sky":
				var bg := ColorRect.new()
				bg.color = Color("#1B2244")
				bg.position = Vector2.ZERO
				bg.size = Vector2(ROOM_W, ROOM_H)
				bg.z_index = z
				bg.mouse_filter = Control.MOUSE_FILTER_IGNORE
				add_child(bg)
			continue

		var spr := Sprite2D.new()
		spr.name = "Scene_" + lname
		spr.texture = load(path)
		spr.centered = false          # 左上角对齐房间原点
		spr.position = Vector2.ZERO
		spr.z_index = z
		spr.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
		add_child(spr)

func _spawn_dummy(pos: Vector2) -> void:
	var script: GDScript = load("res://src/world/training_dummy.gd")
	var node := Node2D.new()
	node.set_script(script)
	node.position = pos
	add_child(node)


func _spawn_enemy(kind: String, pos: Vector2) -> void:
	"""生成敌人。用 CharacterBody2D + 对应脚本动态创建，
	这样不用为每个敌人都做一个 .tscn 场景文件。"""
	var script_path := "res://src/enemies/%s.gd" % kind
	if not ResourceLoader.exists(script_path):
		printerr("敌人脚本不存在: " + script_path)
		return
	var body := CharacterBody2D.new()
	body.set_script(load(script_path))
	body.position = pos
	body.name = kind.capitalize()

	# 碰撞体（敌人本体，用于与地形阻挡）
	var cs := CollisionShape2D.new()
	var rect := RectangleShape2D.new()
	rect.size = Vector2(18, 20)
	cs.shape = rect
	cs.position = Vector2(0, -10)
	body.add_child(cs)

	add_child(body)


func _spawn_boss(pos: Vector2) -> void:
	"""生成 BOSS。

	BOSS 的碰撞体是矩形（不是和杂兵一样的 18x20），
	因为它的体型是杂兵的 3 倍。碰撞体尺寸影响玩家能不能跳过它。
	"""
	var script_path := "res://src/enemies/boss_warden.gd"
	if not ResourceLoader.exists(script_path):
		printerr("BOSS 脚本不存在: " + script_path)
		return
	var body := CharacterBody2D.new()
	body.set_script(load(script_path))
	body.position = pos
	body.name = "BossWarden"

	var cs := CollisionShape2D.new()
	var rect := RectangleShape2D.new()
	rect.size = Vector2(40, 88)        # 覆盖身体 + 头，玩家跳不过去
	cs.shape = rect
	cs.position = Vector2(0, -44)
	body.add_child(cs)

	add_child(body)
	boss = body


func _spawn_player() -> void:
	var player_scene: PackedScene = load("res://scenes/player/player.tscn")
	var player := player_scene.instantiate()
	player.position = SPAWN
	add_child(player)

	# 刀光层：预生成贴图 + Sprite2D 播放。
	# 早期试过 Node2D._draw 画弧线，在 root viewport 下画不出来，
	# 换成贴图方案后稳定可见（见 src/world/slash_sprite.gd）。
	var slash_script: GDScript = load("res://src/world/slash_sprite.gd")
	var slash := Sprite2D.new()
	slash.set_script(slash_script)
	slash.name = "SlashLayer"
	add_child(slash)
	# 重攻击用不同的贴图前缀（heavy）和更慢的帧速（更"重"的观感）
	player.slash_requested.connect(
		func(origin, _d0, _d1, _r, _c, _th, dur, facing, heavy: bool):
			if heavy:
				slash.spawn(origin, player.get_heavy_index(), facing, "heavy", 0.075)
			else:
				slash.spawn(origin, player.get_combo_index(), facing))

	# 训练木桩保留一个（用来试连段手感，不会还手）
	# 训练木桩放在轻攻击教学段旁边，玩家想练连段随时可以过来
	_spawn_dummy(Vector2(560, 480))

	# ── 敌人分布：严格按教学段设计（见 docs/04-教程关设计.md）──
	#
	# 段落区间：move 0-400 / light 400-760 / heavy 760-1080 /
	#           parry 1080-1320 / dash 1320-1440 / mix 1440-1560
	# ── 敌人与 BOSS：**从关卡 JSON 的 entities 表生成** ──
	#
	# 原来是硬编码坐标，和新关卡完全脱节 —— 改关卡后敌人还站在旧位置，
	# 有的浮空、有的卡在台阶里。现在统一由 .lvl 字符画决定。
	#
	# 实体锚点在格子底部中心（角色按脚底对齐），
	# 再上抬 2px 让碰撞体落到地面而不是半嵌进去。
	var spawned_any := false
	for ent in _level_entities:
		var kind := str(ent.get("kind", ""))
		var pos := Vector2(float(ent["x"]), float(ent["y"])) - Vector2(0, 2)
		match kind:
			"enemy_mossling":
				_spawn_enemy("mossling", pos)
				spawned_any = true
			"enemy_lanternbug":
				_spawn_enemy("lanternbug", pos)
				spawned_any = true
			"enemy_stonepaw":
				_spawn_enemy("stonepaw", pos)
				spawned_any = true
			"spawn_boss":
				_spawn_boss(pos)
				spawned_any = true
			"dummy":
				_spawn_dummy(pos)
				spawned_any = true
	if not spawned_any:
		printerr("关卡里没有任何实体，检查 .lvl 的 [map] 段")

	# 摄像机跟随玩家，限制在房间内
	var cam := Camera2D.new()
	cam.limit_left = 0
	cam.limit_top = 0
	cam.limit_right = ROOM_W
	cam.limit_bottom = ROOM_H
	cam.position_smoothing_enabled = true
	cam.position_smoothing_speed = 12.0
	player.add_child(cam)
	cam.make_current()

	# ── BOSS 房锁：玩家越过分界线才唤醒 BOSS ──
	# 用轮询而不是 Area2D：这里只是每帧比较一个 x 值，
	# 加物理体反而要处理层/遮罩，得不偿失。
	_boss_lock_timer = Timer.new()
	_boss_lock_timer.wait_time = 0.1
	_boss_lock_timer.autostart = true
	_boss_lock_timer.timeout.connect(_check_boss_lock)
	add_child(_boss_lock_timer)


var _boss_lock_timer: Timer = null
var _boss_awake := false


func _check_boss_lock() -> void:
	if _boss_awake or boss == null or not is_instance_valid(boss):
		return
	var player := _find_player()
	if player == null:
		return
	if player.global_position.x >= BOSS_ZONE_START:
		_boss_awake = true
		if boss.has_method("wake"):
			boss.wake()
		boss_awakened.emit(boss)
		if _boss_lock_timer != null:
			_boss_lock_timer.stop()


func _find_player() -> Node2D:
	for p in get_tree().get_nodes_in_group("player"):
		return p
	return null
