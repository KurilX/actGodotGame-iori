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
	# 背景
	var bg := ColorRect.new()
	bg.color = Color("#1B2244")
	bg.position = Vector2(0, 0)
	bg.size = Vector2(ROOM_W, ROOM_H)
	bg.z_index = -10
	bg.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(bg)

	# 远景剪影
	var far := Polygon2D.new()
	far.polygon = PackedVector2Array([
		Vector2(0, 400), Vector2(120, 300), Vector2(240, 380),
		Vector2(360, 260), Vector2(520, 360), Vector2(680, 280),
		Vector2(820, 370), Vector2(960, 320), Vector2(960, 540), Vector2(0, 540),
	])
	far.color = Color("#232E52")
	far.z_index = -5
	add_child(far)

	# 实心地形：暗色块 + 顶部草皮亮边
	for r in SOLIDS:
		var poly := Polygon2D.new()
		poly.polygon = PackedVector2Array([
			Vector2(r[0], r[1]),
			Vector2(r[0] + r[2], r[1]),
			Vector2(r[0] + r[2], r[1] + r[3]),
			Vector2(r[0], r[1] + r[3]),
		])
		poly.color = Color("#5A6478")
		poly.z_index = -1
		add_child(poly)

		var top := Polygon2D.new()
		top.polygon = PackedVector2Array([
			Vector2(r[0], r[1]),
			Vector2(r[0] + r[2], r[1]),
			Vector2(r[0] + r[2], r[1] + 3),
			Vector2(r[0], r[1] + 3),
		])
		top.color = Color("#6E9A6B")
		top.z_index = 0
		add_child(top)

	# 单向平台：薄板
	for r in ONE_WAY:
		var poly := Polygon2D.new()
		poly.polygon = PackedVector2Array([
			Vector2(r[0], r[1]),
			Vector2(r[0] + r[2], r[1]),
			Vector2(r[0] + r[2], r[1] + 6),
			Vector2(r[0], r[1] + 6),
		])
		poly.color = Color("#7B8699")
		poly.z_index = 0
		add_child(poly)


func _spawn_dummy(pos: Vector2) -> void:
	var script: GDScript = load("res://src/world/training_dummy.gd")
	var node := Node2D.new()
	node.set_script(script)
	node.position = pos
	add_child(node)


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

	# 训练木桩：放在出生点右侧，验证攻击连段
	_spawn_dummy(Vector2(320, 480))
	_spawn_dummy(Vector2(430, 480))

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
