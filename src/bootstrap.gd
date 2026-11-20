extends Node
## 启动场景：直接进灰盒测试房，跳过菜单
##
## 同时挂载触屏虚拟按键层。按键层是 canvas 层，独立于游戏世界，
## 所以不会跟着相机移动。

const TouchControls := preload("res://src/ui/touch_controls.gd")

func _ready() -> void:
	var room: PackedScene = load("res://scenes/rooms/room_greybox.tscn")
	add_child(room.instantiate())

	# 触屏按键：放在 CanvasLayer 里，保证不受相机与世界坐标影响
	var layer := CanvasLayer.new()
	layer.name = "TouchLayer"
	# 高 layer 值确保盖在游戏画面之上
	layer.layer = 100
	add_child(layer)

	var touch := Control.new()
	touch.name = "TouchControls"
	touch.set_script(TouchControls)
	layer.add_child(touch)
