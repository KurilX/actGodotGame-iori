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
	p.facing = 1
	for i in 20:
		await physics_frame

	var anim = p.get_node("Visual/AnimatedSprite2D")
	print("=== 攻击动画帧追踪 ===")
	p.start_attack()
	for i in 16:
		await process_frame
		print("f%2d state=%d anim=%s frame=%d playing=%s paused=%s" % [
			i, p.state, anim.animation, anim.frame, anim.is_playing(), anim.is_playing() == false])
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
