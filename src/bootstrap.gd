extends Node
## 启动场景：直接进灰盒测试房，跳过菜单
##
## W1 阶段只关心手感，不做菜单。之后接主菜单时改 run/main_scene 即可。

func _ready() -> void:
	var room: PackedScene = load("res://scenes/rooms/room_greybox.tscn")
	add_child(room.instantiate())
