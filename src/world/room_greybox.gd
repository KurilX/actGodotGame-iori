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
const ROOM_W := 2400
const ROOM_H := 540

# 段边界（世界坐标 x）
const TUTORIAL_END := 1560.0
const BOSS_ZONE_START := 1560.0

# 实心地形矩形：[x, y, w, h]（游戏像素，y 向下）
const SOLIDS := [
	# ═══════════ 地面（整条，贯穿全图）═══════════
	[0, 480, 2400, 60],

	# ═══════════ ① 移动教学（x 0~500）═══════════
	# 三级台阶：高 40px、间隔 100px。这个间距略小于跳跃极限，
	# 新手一次就能上去（跳跃高度约 58px，实测）。
	[120, 440, 72, 40],
	[220, 400, 72, 40],
	[320, 360, 72, 40],
	# 一层地板（教"上跳穿单向平台"）
	[0, 250, 150, 20],

	# ═══════════ ② 轻攻击教学（x 500~900）═══════════
	# 平地，只放一块单向平台做可选练习

	# ═══════════ ③ 重攻击教学（x 900~1400）═══════════
	# 石守站的高台（60px 高 = 玩家身高 48 + 一点余量，跳上去正好能打）
	[1120, 420, 130, 60],

	# ═══════════ ④ 闪避教学（x 1400~1900）═══════════
	# 刻意留空：这段是开阔地，两只苔团从两侧夹击

	# ═══════════ ⑤ 综合（x 1900~2400）═══════════
	# 一小段抬高的地形，制造高低差让三种敌人各显其能
	[1900, 440, 90, 40],

	# ═══════════ 主关卡：BOSS 房（x 1560~2400）═══════════
	# 左侧塔（和原来一样，作为视觉锚点）
	[2160, 288, 48, 192],
	[2208, 420, 192, 60],
	# BOSS 房的天花板压低一点，形成压迫感
	[1560, 0, 840, 12],

	# ═══════════ 边界 ═══════════
	[0, 0, 2400, 12],          # 天花板（全图）
	[-12, 0, 12, 540],         # 左墙
	[2400, 0, 12, 540],        # 右墙
]

# 单向平台：[x, y, w] —— 可以从下方跳上去
const ONE_WAY := [
	# ① 移动教学
	[200, 300, 84],
	# ② 轻攻击教学（可选上去）
	[600, 320, 96],
	[560, 200, 100],
	# ③ 重攻击教学（高台上方，跳上去打完可以站这）
	[980, 260, 80],
	# ⑤ 综合段
	[2020, 260, 120],
]

# 出生点：教程关起点，地板上方一点（落地有个轻微下坠，手感更自然）
const SPAWN := Vector2(80, 440)


func _ready() -> void:
	_build_visuals()
	_build_solids()
	_build_one_way()
	_spawn_player()


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
	# ① 移动段（x 0~500）**不放假人**：第一个怪之前必须有安全区，
	#    否则新手一进场就被打，学不会任何东西。

	# ② 轻攻击段：1 只苔团。它前摇最长（0.42s）、血最薄（12），
	#    是唯一适合"站着对打"的敌人。
	_spawn_enemy("mossling", Vector2(700, 470))

	# ③ 重攻击段：1 只石守站在高台上。
	#    它有霸体 —— 轻攻击打不断它抡砸，**必须用重击**才能打断。
	#    这是"轻 vs 重"区别唯一能被玩家亲手发现的机会。
	_spawn_enemy("stonepaw", Vector2(1150, 415))

	# ④ 闪避段（x 1200~1400）：2 只苔团从两侧夹击，逼玩家用无敌帧穿过去。
	# 位置避开石守高台（1120~1250），否则会卡在台边。
	_spawn_enemy("mossling", Vector2(1258, 470))
	_spawn_enemy("mossling", Vector2(1380, 470))

	# ⑤ 综合段（x 1400~1560）：BOSS 房入口前的最后考验。
	# 两种互补威胁：灯笼虫在空中逼玩家上跳，石守在地面逼玩家用重击。
	_spawn_enemy("lanternbug", Vector2(1450, 400))
	_spawn_enemy("stonepaw", Vector2(1520, 470))

	# BOSS「瓷面的守夜人」：BOSS 房中央
	_spawn_boss(Vector2(2000, 468))

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
