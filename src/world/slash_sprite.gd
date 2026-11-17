extends Sprite2D
## 刀光特效：用预生成贴图播放，不依赖 _draw
##
## 为什么换成贴图：实测 Node2D._draw 里的 draw_rect / draw_polyline
## 在 root viewport + canvas_items stretch 下画不出来（节点状态、位置、
## z_index、visible 全对，但最终画面没有内容），连续 4 版都没解决。
## 预生成贴图 + Sprite2D 是像素游戏的常规做法，稳定可控。
##
## 用法：spawn(world_pos, segment_idx, facing)

const FRAME_DUR := 0.045      # 每帧停留时间 → 3 帧约 0.135s
const SEGMENTS := 4
const FRAMES_PER_SEG := 3

var _timer := 0.0
var _frame := 0
var _seg := 1
var _active := false

var _textures := {}           # key: "seg_frame" → Texture2D


func _ready() -> void:
	z_index = 50              # 高于角色与地形
	texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	centered = true
	visible = false
	set_process(true)
	_preload()


func _preload() -> void:
	for si in range(1, SEGMENTS + 1):
		for fi in range(FRAMES_PER_SEG):
			var path := "res://art/fx/slash/seg%d_%d.png" % [si, fi]
			if ResourceLoader.exists(path):
				_textures["%d_%d" % [si, fi]] = load(path)
	if _textures.is_empty():
		printerr("刀光贴图缺失：art/fx/slash/ 下没有 png，先跑 tools/make_slash_fx.py")


func spawn(world_pos: Vector2, segment_idx: int, facing: int) -> void:
	# segment_idx 是 0..3（连段下标），贴图从 1 开始编号
	_seg = clampi(segment_idx + 1, 1, SEGMENTS)
	global_position = world_pos
	flip_h = facing < 0
	_frame = 0
	_timer = 0.0
	_active = true
	visible = true
	_apply(0)


func _apply(f: int) -> void:
	var key := "%d_%d" % [_seg, f]
	if not _textures.has(key):
		_active = false
		visible = false
		return
	texture = _textures[key]


func _process(delta: float) -> void:
	if not _active:
		return
	_timer += delta
	while _timer >= FRAME_DUR:
		_timer -= FRAME_DUR
		_frame += 1
		if _frame >= FRAMES_PER_SEG:
			_active = false
			visible = false
			return
		_apply(_frame)


func is_active() -> bool:
	return _active
