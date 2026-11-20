extends Node2D
## 灰盒测试房：手动搭建静态碰撞体 + 单向平台
##
## 目的：W1 阶段排除 TileSet 配置的干扰，先把「跑跳砍」手感调出来。
## 场景里的地形全部由本脚本按数据生成，改数据即可改关卡。
## 尺寸按规范：单房间 960 x 540（2 屏宽 x 2 屏高，视口 480x270）

const ROOM_W := 960
const ROOM_H := 540

# 实心地形矩形：[x, y, w, h]（游戏像素，y 向下）
const SOLIDS := [
	# 地面（整条）
	[0, 480, 960, 60],
	# 左侧台阶（练跳）
	[0, 420, 96, 60],
	[96, 372, 72, 48],
	[168, 324, 60, 48],
	# 中间高台
	[300, 340, 120, 24],
	# 右侧塔
	[720, 288, 48, 192],
	[768, 420, 192, 60],
	# 天花板
	[0, 0, 960, 12],
	# 左右墙
	[-12, 0, 12, 540],
	[960, 0, 12, 540],
	# 一层地板（把房间分成上下两块）
	[0, 250, 180, 20],
]

# 单向平台：[x, y, w] —— 可以从下方跳上去
const ONE_WAY := [
	[200, 300, 84],
	[420, 260, 72],
	[560, 320, 96],
	[300, 180, 120],
]

# 出生点（落在地面中央，避免一出生就站在台阶上）
const SPAWN := Vector2(240, 400)


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
	# 三张图都是 960x540 全屏尺寸，直接 Sprite2D 贴上，
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
	_spawn_dummy(Vector2(300, 480))

	# 三个实际敌人，分布在不同距离以展示不同的战斗节奏：
	#   苔团（近战教学）在较近处，一进场就能遇到
	#   灯笼虫（飞行）在中距离空中，需要主动追
	#   石守（重甲）在较远处，作为"关底"级别的对手
	_spawn_enemy("mossling", Vector2(400, 470))
	_spawn_enemy("lanternbug", Vector2(560, 430))
	_spawn_enemy("stonepaw", Vector2(720, 470))

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
