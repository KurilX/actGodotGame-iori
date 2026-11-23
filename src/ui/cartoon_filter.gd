"""卡通滤镜层：全屏着色器后处理。

## 为什么需要一层 BackBufferCopy

项目用 `gl_compatibility` 渲染器（Web 兼容性优先），
它不支持 Forward+ 的屏幕后处理。要在"游戏画面上再叠一层效果"，
唯一可靠的做法是：

    BackBufferCopy（把当前画面复制到可读缓冲）
      + ColorRect（全屏着色器，从 SCREEN_TEXTURE 读）

## 层的位置很重要

放在 **CanvasLayer.layer = 50**：
  · 高于世界（游戏内容，默认 layer 0）
  · 低于所有 UI（菜单 10、子弹时间 80、血条 85、连击条 90 …）

这样滤镜只作用在**游戏画面**上，不会把 UI 的字也调色 —— 否则
菜单文字会跟着变暖、血条颜色会偏离设计值。

**例外**：主菜单/设置（layer 10/12）也低于 50，但它们在进游戏时
是隐藏的，所以不冲突。
"""

extends ColorRect

const SHADER_PATH := "res://shaders/cartoon_filter.gdshader"

# 滤镜强度的默认值。写在代码里而不是只放 shader 里，
# 是因为设置面板要读写它，需要一个单一来源。
const DEFAULT_AMOUNT := 1.0

var _mat: ShaderMaterial = null
var _enabled := true


func _ready() -> void:
	set_anchors_preset(Control.PRESET_FULL_RECT)
	offset_left = 0
	offset_top = 0
	offset_right = 0
	offset_bottom = 0
	mouse_filter = Control.MOUSE_FILTER_IGNORE

	if not ResourceLoader.exists(SHADER_PATH):
		printerr("卡通滤镜着色器缺失：" + SHADER_PATH)
		return

	var sh: Shader = load(SHADER_PATH)
	_mat = ShaderMaterial.new()
	_mat.shader = sh
	material = _mat

	# **必须加 BackBufferCopy**：没有它，SCREEN_TEXTURE 读到的是空的，
	# 画面会变成全黑（实测）。这是 gl_compatibility 下的硬性要求。
	var bb := BackBufferCopy.new()
	bb.copy_mode = BackBufferCopy.COPY_MODE_VIEWPORT
	add_child(bb)

	set_amount(DEFAULT_AMOUNT)


func set_amount(a: float) -> void:
	if _mat == null:
		return
	_mat.set_shader_parameter("mix_amount", clampf(a, 0.0, 1.0))
	_enabled = a > 0.001
	# 完全关闭时隐藏节点，省掉整屏一次采样
	visible = _enabled


func get_amount() -> float:
	if _mat == null:
		return 0.0
	return float(_mat.get_shader_parameter("mix_amount"))


func is_enabled() -> bool:
	return _enabled and visible


# ── 单项参数调音（方便调试与以后做画质档位）──

func set_param(name: String, value: Variant) -> void:
	if _mat != null:
		_mat.set_shader_parameter(name, value)


func get_param(name: String) -> Variant:
	return _mat.get_shader_parameter(name) if _mat != null else null
