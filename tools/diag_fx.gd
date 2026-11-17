extends SceneTree
func _init() -> void:
	var boot: PackedScene = load("res://scenes/bootstrap.tscn")
	root.add_child(boot.instantiate())
	await process_frame
	await process_frame
	for i in 60:
		await physics_frame

	var p = _find(root)
	var fx = p.get_node("SlashFX")
	# 用 set_meta 观察 _draw 是否执行：脚本里没这个逻辑，所以改为
	# 直接检查 fx 的 draw 调用次数——通过覆盖一个脚本内部计数器不可行，
	# 改为读取 script 的静态状态。
	p.start_attack()
	for i in 3:
		await process_frame
	print("visible=", fx.visible, " life=", fx._life, " life_max=", fx._life_max)
	print("is_inside_tree=", fx.is_inside_tree(), " is_visible_in_tree=", fx.is_visible_in_tree())
	print("canvas_item_visible=", fx.visible)
	print("modulate.a=", fx.modulate.a, " self_modulate.a=", fx.self_modulate.a)
	# 检查父节点 Visible 链
	var n = fx
	while n:
		print("  ", n.name, " visible=", n.visible)
		n = n.get_parent()
	quit(0)

func _find(n):
	if n is CharacterBody2D: return n
	for c in n.get_children():
		var r = _find(c)
		if r: return r
	return null
