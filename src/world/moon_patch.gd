extends Node2D
## 地面月光斑：月亮正下方的地表顶面加一条 moon_hi 亮带。
##
## ## 为什么存在
##
## 旧的"竖直月光柱"画在屏幕空间、垂直向下、不落在任何实体上——
## 用户反馈"像灯一样，光影很怪"。真正的月光光影要回答三个问题：
##   · 光从哪来？（月亮，屏幕右上固定）
##   · 照到哪？（月亮正下方的地表顶面）
##   · 光斑怎么动？（相机每移动 480px，月亮在世界里"移动"480px，
##     所以光斑的世界位置 = f(cam_x)，用屏幕月亮位置反推）
##
## ## 画什么
##
## 沿地表（surface_y_at 逐 x 查询，和植被同一套函数）在月亮下方
## ±70px 窗口内，把顶面第 0 行像素改成 moon_hi（月光高光档），
## 第 1 行按抖动改成 stone（受光过渡）——远看是"月光洒在地面上
## 的一条亮带"，边缘渐隐，不遮死原有纹理。
##
## 山层不在本节点处理（山是屏幕空间视差层，属于 bg_parallax 的
## 云缘受光那部分）。

const MOON_X_FRAC := 0.60      # 与 bg_parallax.gd 保持一致
const VIEW_W := 480.0
const PATCH_HALF := 90.0       # 光斑半宽（放大：中心到边缘渐变更明显）
const CENTER_ROW_HIT := 0.92   # 中心处顶行改色概率
const EDGE_ROW_HIT := 0.30     # 边缘处概率（渐隐）

var _cam: Camera2D = null
var _solids: Array = []


func setup(camera: Camera2D) -> void:
	_cam = camera
	# 从房间脚本拿 SOLIDS：父节点就是 room_greybox
	var room := get_parent()
	if room != null and "SOLIDS" in room:
		_solids = room.get("SOLIDS")
	set_process(true)


func _surface_y_at(x: float) -> float:
	## 与 room_greybox._surface_y_at 同款：该 x 处最高的可站表面
	var best := -1.0
	for r in _solids:
		var sx: float = float(r[0])
		var sy: float = float(r[1])
		var sw: float = float(r[2])
		if sw < 40.0:
			continue
		if x < sx or x >= sx + sw:
			continue
		if sy < 100.0:
			continue
		if best < 0.0 or sy < best:
			best = sy
	return best


func _process(_delta: float) -> void:
	queue_redraw()


func _draw() -> void:
	if _cam == null:
		return
	# 月亮的世界 x：屏幕固定位置 + 相机左缘
	var cam_left: float = _cam.get_screen_center_position().x - VIEW_W * 0.5
	var moon_world_x := cam_left + VIEW_W * MOON_X_FRAC + 11.0

	# 沿光斑窗口逐列查地表并画亮带
	var x0 := moon_world_x - PATCH_HALF
	var x1 := moon_world_x + PATCH_HALF
	var px_x := floorf(x0)
	while px_x <= x1:
		var sy := _surface_y_at(px_x)
		if sy > 0.0:
			# 距中心越远越稀（渐隐）
			var dd: float = absf(px_x - moon_world_x) / PATCH_HALF
			var hit := CENTER_ROW_HIT * (1.0 - dd * dd)
			var th := float(((int(px_x) * 7 + int(sy) * 13) % 16)) / 16.0
			if th < hit:
				# 顶面第 0 行 → 月光高光（moon_hi）
				draw_rect(Rect2(px_x, sy, 1.0, 1.0),
						  Color("#8FD3E8"), true)
			# 第 1 行：受光过渡（moon 白），更稀
			if th < hit * 0.45:
				draw_rect(Rect2(px_x, sy + 1.0, 1.0, 1.0),
						  Color("#D8F0F8"), true)
			# 第 2 行：stone 提亮一行（石面受光），偶尔出现
			if th < hit * 0.25:
				draw_rect(Rect2(px_x, sy + 2.0, 1.0, 1.0),
						  Color("#7B8699"), true)
		px_x += 1.0
