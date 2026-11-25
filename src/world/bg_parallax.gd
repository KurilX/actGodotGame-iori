"""分层视差背景：多层独立滚动，支持云层漂移。

## 坐标系：**屏幕空间**

这个节点必须放在一个 `CanvasLayer`（`follow_viewport_enabled = false`）里，
这样 `_draw()` 收到的是**屏幕坐标（0..480, 0..270）**，不是世界坐标。

## 为什么不用世界坐标

如果按世界坐标画，每层的 x 就得写 `cam_pos.x * parallax` —— 但那样
图层会**跟着相机一起走**，视差系数 0 的层反而会跑出屏幕。

屏幕空间里公式干净得多：

    层的横向滚动量 = -相机位移 * (1 - 视差系数) - 自动漂移

  · 视差 0（天空/月亮）→ 滚动量 = -相机位移，但**不画偏移**
    天空是纯色，月亮单独定位，都不需要滚动
  · 视差 0.1（远山）→ 只滚 90%，看起来"慢"
  · 视差 0.9 → 几乎跟世界同速

## 横向循环

每层贴图宽 W。绘制时从 `-fposmod(scroll, W)` 开始，
每隔 W 画一份，直到铺满 480。生成时已做镜像拼接，接缝连续。
"""

extends Node2D

const VIEW_W := 480
const VIEW_H := 270

# (资源名, 视差系数, 漂移px/s, 屏幕y, 特殊)
# **y 要让山只占画面下 40%**。
#
# 第一版远山放在 y=88，而它高 113px，等于占到 y=201（画面的 74%），
# 天空被压得只剩一条 —— 实测山脊顶到画面 60% 高度，很压抑。
# 现在三层整体下移并拉开，让山脊落在画面的 45%~70% 区间。
const LAYERS := [
	{"n": "bg_sky",       "p": 0.0,  "d": 0.0, "y": 0},
	{"n": "bg_mtn_far",   "p": 0.10, "d": 1.5, "y": 122},
	{"n": "bg_mtn_mid",   "p": 0.22, "d": 3.0, "y": 152},
	{"n": "bg_mtn_near",  "p": 0.38, "d": 0.0, "y": 182},
]

# 月亮单独处理：固定屏幕位置，不参与滚动
const MOON_PATH := "res://art/bg/bg_moon.png"
const MOON_X_FRAC := 0.60
const MOON_Y := 34

var _tex: Array[Texture2D] = []
var _par: Array[float] = []
var _drift: Array[float] = []
var _y: Array[float] = []
var _w: Array[int] = []
var _scroll: Array[float] = []
var _moon: Texture2D = null
var _cam: Camera2D = null


func setup(camera: Camera2D) -> void:
	_cam = camera
	for cfg in LAYERS:
		var path := "res://art/bg/%s.png" % cfg["n"]
		if not ResourceLoader.exists(path):
			printerr("背景层缺失：" + path)
			continue
		var t: Texture2D = load(path)
		_tex.append(t)
		_par.append(float(cfg["p"]))
		_drift.append(float(cfg["d"]))
		_y.append(float(cfg["y"]))
		_w.append(t.get_width())
		_scroll.append(0.0)
	if ResourceLoader.exists(MOON_PATH):
		_moon = load(MOON_PATH)


func _process(delta: float) -> void:
	for i in _drift.size():
		if _drift[i] != 0.0:
			_scroll[i] += _drift[i] * delta
	queue_redraw()


func _draw() -> void:
	if _cam == null:
		return
	var cam_x: float = _cam.get_screen_center_position().x - VIEW_W * 0.5

	for i in _tex.size():
		var t: Texture2D = _tex[i]
		var w: int = _w[i]
		if w <= 0:
			continue
		# 屏幕空间的横向偏移：视差越小，滚动越慢
		var shift := -cam_x * _par[i] - _scroll[i]
		var start := fposmod(shift, float(w))
		# 从 start - w 开始画，保证左边缘也铺到
		var x := start - float(w)
		while x < VIEW_W:
			draw_texture(t, Vector2(x, _y[i]))
			x += float(w)

	if _moon:
		draw_texture(_moon, Vector2(VIEW_W * MOON_X_FRAC, MOON_Y))
