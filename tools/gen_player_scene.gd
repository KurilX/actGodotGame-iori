extends SceneTree
## 生成 player.tscn：45 帧 + AttackHitbox 子节点
##
## 为什么用脚本生成而不是手写 tscn：
## 帧数多，手写容易漏 ext_resource 或写错 id，脚本生成可复现且不会错。

const OUT := "res://scenes/player/player.tscn"


func _init() -> void:
	var anims := [
		{"name": "idle", "prefix": "ori_idle", "count": 4, "loop": true, "fps": 6.0},
		{"name": "run", "prefix": "ori_run", "count": 6, "loop": true, "fps": 12.0},
		{"name": "jump", "prefix": "ori_jump", "count": 3, "loop": false, "fps": 8.0},
		{"name": "land", "prefix": "ori_land", "count": 2, "loop": false, "fps": 12.0},
		{"name": "atk1", "prefix": "ori_atk1", "count": 3, "loop": false, "fps": 0.0},
		{"name": "atk2", "prefix": "ori_atk2", "count": 3, "loop": false, "fps": 0.0},
		{"name": "atk3", "prefix": "ori_atk3", "count": 3, "loop": false, "fps": 0.0},
		{"name": "atk4", "prefix": "ori_atk4", "count": 3, "loop": false, "fps": 0.0},
		{"name": "dash", "prefix": "ori_dash", "count": 3, "loop": false, "fps": 0.0},
	]

	# 收集所有帧，生成 ext_resource 与 SpriteFrames
	var lines: Array[String] = []
	var ext: Array[String] = []
	var frame_map := {}
	var eid := 2

	for a in anims:
		var frames: Array[String] = []
		for i in a["count"]:
			var path := "res://art/characters/ori/frames/%s_%d.png" % [a["prefix"], i]
			if not ResourceLoader.exists(path):
				printerr("缺少帧文件: " + path)
				quit(1)
				return
			var id := "t%d" % eid
			ext.append(
				'[ext_resource type="Texture2D" path="%s" id="%s"]' % [path, id])
			frames.append(id)
			eid += 1
		frame_map[a["name"]] = frames

	# 计算 load_steps = ext 数 + 2 个 sub_resource + 1
	var load_steps := eid + 3

	lines.append('[gd_scene load_steps=%d format=3 uid="uid://bqorip1ayer00"]' % load_steps)
	lines.append("")
	lines.append('[ext_resource type="Script" path="res://src/player/player.gd" id="1_player"]')
	lines.append('[ext_resource type="Script" path="res://src/player/shadow.gd" id="17_shadow"]')
	lines.append('[ext_resource type="Script" path="res://src/player/attack_hitbox.gd" id="18_hitbox"]')
	for e in ext:
		lines.append(e)
	lines.append("")

	# sub_resource: 碰撞盒
	lines.append('[sub_resource type="RectangleShape2D" id="RectangleShape2D_body"]')
	lines.append("size = Vector2(24, 40)")
	lines.append("")

	# sub_resource: 攻击判定框
	lines.append('[sub_resource type="RectangleShape2D" id="RectangleShape2D_hit"]')
	lines.append("size = Vector2(22, 18)")
	lines.append("")

	# sub_resource: SpriteFrames
	lines.append('[sub_resource type="SpriteFrames" id="SpriteFrames_ori"]')
	lines.append("animations = [")
	var anim_blocks: Array[String] = []
	for a in anims:
		var frames: Array[String] = frame_map[a["name"]]
		var fb: Array[String] = []
		for fid in frames:
			fb.append('{\n"duration": 1.0,\n"texture": ExtResource("%s")\n}' % fid)
		anim_blocks.append(
			'{\n"frames": [%s],\n"loop": %s,\n"name": &"%s",\n"speed": %.1f\n}'
			% [", ".join(fb), "true" if a["loop"] else "false",
			   a["name"], 1.0 if a["fps"] == 0.0 else a["fps"]])
	lines.append(", ".join(anim_blocks))
	lines.append("]")
	lines.append("")

	# 节点
	lines.append('[node name="Player" type="CharacterBody2D"]')
	lines.append("collision_layer = 2")
	lines.append("collision_mask = 1")
	lines.append('script = ExtResource("1_player")')
	lines.append("")
	lines.append('[node name="Visual" type="Node2D" parent="."]')
	lines.append("")
	lines.append('[node name="AnimatedSprite2D" type="AnimatedSprite2D" parent="Visual"]')
	lines.append("texture_filter = 1")
	lines.append("position = Vector2(0, -24)")
	lines.append('sprite_frames = SubResource("SpriteFrames_ori")')
	lines.append('animation = &"idle"')
	lines.append('autoplay = "idle"')
	lines.append("")
	lines.append('[node name="CollisionShape2D" type="CollisionShape2D" parent="."]')
	lines.append("position = Vector2(0, -20)")
	lines.append('shape = SubResource("RectangleShape2D_body")')
	lines.append("")
	lines.append('[node name="AttackHitbox" type="Area2D" parent="."]')
	lines.append("collision_layer = 0")
	lines.append("collision_mask = 8")
	lines.append("monitoring = false")
	lines.append("monitorable = false")
	lines.append('script = ExtResource("18_hitbox")')
	lines.append("")
	lines.append('[node name="CollisionShape2D" type="CollisionShape2D" parent="AttackHitbox"]')
	lines.append("disabled = true")
	lines.append('shape = SubResource("RectangleShape2D_hit")')
	lines.append("")
	lines.append('[node name="Shadow" type="Node2D" parent="."]')
	lines.append('script = ExtResource("17_shadow")')
	lines.append("")

	var f := FileAccess.open(OUT, FileAccess.WRITE)
	if f == null:
		printerr("无法写入 " + OUT)
		quit(1)
		return
	f.store_string("\n".join(lines))
	f.close()
	print("wrote %s (%d 帧, load_steps=%d)" % [OUT, eid - 2, load_steps])
	quit(0)
