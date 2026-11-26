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
	# 云：视差极小（几乎不动）+ 自动漂移，是"飘在天上"的关键
	{"n": "bg_cloud",     "p": 0.04, "d": 6.0, "y": 52},
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
		var mx := VIEW_W * MOON_X_FRAC
		draw_texture(_moon, Vector2(mx, MOON_Y))

		# ── 月光：halo + 云缘受光（屏幕空间），亮斑在场景层（room）──
		#
		# ## 为什么要重做（用户反馈）
		#
		# 旧版"竖直月光柱"三个问题：
		#   1. 光柱是屏幕空间固定的，云在飘、山在滚，光柱纹丝不动
		#      → 看起来像钉在屏幕上的路灯；
		#   2. 月亮在画面右上，光却垂直向下打在云层上——光没有落到
		#      任何实体表面，"光照"没有对象；
		#   3. 探照灯式的光束不是月光的视觉语言。
		#
		# ## 现在的光影模型（三层，各自属于正确的空间）
		#
		#   A. **月亮 halo + 星芒**（这里，屏幕空间）：月亮是极远的
		#      天体，跟屏幕走是对的；halo 用抖动点阵，4 向十字星芒
		#      是像素画月光的经典画法；
		#   B. **云缘受光**（这里，跟着云层滚动偏移画）：月亮在云层
		#      后上方，靠近月亮的云块下缘加一行 moon_hi 亮边——
		#      "月光从云后面透出来"，且亮边跟着云一起飘；
		#   C. **地面月光斑**（room 层按世界坐标画，见 room_greybox）：
		#      月亮正下方的地面顶面加一条 1px moon_hi 亮带渐隐——
		#      光落在实体上，且随相机按视差移动，和场景同步。
		#
		# 全部用抖动点阵，不用 alpha 混合（像素画规则）。

		# ── A. halo：月亮柔光晕 —— 抖动填充圆盘，不是同心环 ──
		#
		# 第一版画 2 圈椭圆环，环太完整 → 像"靶环/雷达"。
		# 柔光的正确画法：从月亮边缘向外**密度递减的抖动点云**，
		# 点位置带噪声（半径抖动），没有可辨认的几何形状。
		var halo := Color(0.55, 0.70, 0.86)
		var cx := mx + 11.0          # 月亮贴图 22x22，中心
		var cy := MOON_Y + 11.0
		var halo_r := 26.0
		var steps := 140
		for i in steps:
			var a := TAU * float(i) / float(steps) * 7.13   # 黄金角散布
			var rnd := float(((i * 1103515245) ^ (i * 7)) % 1000) / 1000.0
			var rr := 13.0 + rnd * rnd * halo_r             # 密集在内圈
			# 椭圆（横向略宽）
			var hx0 := cx + cos(a) * rr * 1.2
			var hy0 := cy + sin(a) * rr * 0.85
			var th := float(((i * 7) % 16)) / 16.0
			# 密度随半径衰减 + 轻噪声
			var dens := 0.62 * (1.0 - rr / (halo_r + 13.0)) + 0.05
			if th < dens:
				draw_rect(Rect2(floorf(hx0), floorf(hy0),
								2.0 if i % 3 == 0 else 1.0, 1.0),
						  halo, true)
		# 十字星芒：保留但更细（1px、渐减密度）——像素月光的点缀
		for dir in 4:
			var dx: float = [0.0, 0.0, -1.0, 1.0][dir]
			var dy: float = [-1.0, 1.0, 0.0, 0.0][dir]
			for k in range(1, 6):
				var dist := 20.0 + k * 5.0
				var th2 := float(((k * 11 + dir * 7) % 16)) / 16.0
				if th2 < 0.6 - k * 0.12:
					draw_rect(Rect2(floorf(cx + dx * dist),
									floorf(cy + dy * dist),
									1.0, 1.0), halo, true)

		# ── B. 云缘受光：**已删除** ──
		#
		# 两版尝试都失败：亮线 y 固定不跟云形状（虚线横杠感），
		# 即使加 y 波动也和云的轮廓无关 —— 视觉上是负资产。
		# 要正确做"云受月照"必须读取云贴图逐列的实际 alpha 下缘，
		# 成本高收益低；地面月光斑（moon_patch）才是"光落在实体上"
		# 的正解，云层保持纯剪影。
