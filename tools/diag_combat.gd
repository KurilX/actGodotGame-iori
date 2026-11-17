extends SceneTree
func _init() -> void:
	var boot: PackedScene = load("res://scenes/bootstrap.tscn")
	root.add_child(boot.instantiate())
	await process_frame
	await process_frame
	for i in 60:
		await physics_frame

	var p = _find(root)
	var dummy = _find_script(root, "training_dummy")
	p.global_position = dummy.global_position + Vector2(-18, 0)
	for i in 20:
		await physics_frame

	var hb = p.get_node("AttackHitbox")
	hb.set_active(true)
	await physics_frame
	await physics_frame
	var areas = hb.get_overlapping_areas()
	print("overlap area instance = ", areas[0].get_instance_id())
	print("dummy instance = ", dummy.get_instance_id())
	print("area is dummy? ", areas[0] == dummy)
	print("area parent = ", areas[0].get_parent())
	print("area parent is dummy? ", areas[0].get_parent() == dummy)
	print("")
	print("area has take_hit = ", areas[0].has_method("take_hit"))
	print("area script = ", areas[0].get_script())
	quit(0)

func _find(n):
	if n is CharacterBody2D: return n
	for c in n.get_children():
		var r = _find(c)
		if r: return r
	return null

func _find_script(n, s):
	var sc = n.get_script()
	if sc != null and str(sc.resource_path).contains(s): return n
	for c in n.get_children():
		var r = _find_script(c, s)
		if r: return r
	return null
