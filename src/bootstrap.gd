extends Node
## 启动场景：直接进房间，跳过菜单。
##
## 挂载的层（layer 从低到高）：
##   80  BulletTimeLayer   子弹时间特效
##   85  BossBarLayer      BOSS 血条
##   88  ItemBannerLayer   获得道具横幅
##   90  ComboLayer        连击条
##   92  SkillTreeLayer    技能树面板（Tab 开关）
##   100 TouchLayer        触屏虚拟按键
##
## 另外承载 SkillTree 单例逻辑（挂在 bootstrap 上，全局可访问）。

const TouchControls := preload("res://src/ui/touch_controls.gd")
const ComboMeter := preload("res://src/ui/combo_meter.gd")
const BulletTimeFx := preload("res://src/ui/bullet_time_fx.gd")
const BossHealthBar := preload("res://src/ui/boss_healthbar.gd")
const ItemGainBanner := preload("res://src/ui/item_gain_banner.gd")
const SkillTreePanel := preload("res://src/ui/skill_tree_panel.gd")
const SkillTree := preload("res://src/skills/skill_tree.gd")
const PierceWeaveFx := preload("res://src/skills/pierce_weave_fx.gd")

var skill_tree: Node
var _pierce_fx: Node2D
var _player: Node = null


func _ready() -> void:
	var room_scene: PackedScene = load("res://scenes/rooms/room_greybox.tscn")
	var room := room_scene.instantiate()
	add_child(room)

	# ── 技能树（逻辑单例）──
	skill_tree = Node.new()
	skill_tree.name = "SkillTree"
	skill_tree.set_script(SkillTree)
	add_child(skill_tree)

	# ── 各个 UI 层 ──
	var bt := _make_layer("BulletTimeLayer", 80, BulletTimeFx, "BulletTimeFx")
	var bossbar := _make_layer("BossBarLayer", 85, BossHealthBar,
							   "BossHealthBar")
	var banner := _make_layer("ItemBannerLayer", 88, ItemGainBanner,
							  "ItemGainBanner")
	var combo := _make_layer("ComboLayer", 90, ComboMeter, "ComboMeter")
	var panel := _make_layer("SkillTreeLayer", 92, SkillTreePanel,
							 "SkillTreePanel")
	_make_layer("TouchLayer", 100, TouchControls, "TouchControls")

	panel.bind(skill_tree)

	# 技能特效挂在房间里（要跟随世界坐标）
	_pierce_fx = Node2D.new()
	_pierce_fx.name = "PierceWeaveFx"
	_pierce_fx.set_script(PierceWeaveFx)
	room.add_child(_pierce_fx)

	await get_tree().process_frame
	_connect_player(room, combo, bt)
	_connect_boss(room, bossbar, banner)


func _make_layer(layer_name: String, layer_idx: int, script: Script,
				 node_name: String) -> Control:
	var cl := CanvasLayer.new()
	cl.name = layer_name
	cl.layer = layer_idx
	add_child(cl)
	var c := Control.new()
	c.name = node_name
	c.set_script(script)
	cl.add_child(c)
	return c


func _connect_player(room: Node, combo: Control, bt: Control) -> void:
	_player = _find_player(room)
	if _player == null:
		printerr("UI：未找到玩家")
		return

	_player.hit_landed.connect(func(_t: Node, damage: int) -> void:
		combo.register_hit(2 if damage >= 4 else 1))

	_player.whiffed.connect(func(heavy: bool) -> void:
		combo.register_whiff(heavy))

	_player.damaged.connect(func(_a: int) -> void:
		combo.reset_combo()
		if skill_tree:
			skill_tree.reset_sequence())

	# 每段攻击结束 → 记录到连招序列，并检查是否触发技能
	_player.attack_segment_done.connect(_on_segment_done)

	var cam := _find_camera(_player)
	_player.perfect_dodge.connect(func() -> void:
		bt.trigger(_player.global_position, cam)
		combo.register_perfect_dodge())

	if skill_tree:
		skill_tree.skill_unlocked.connect(func(skill_id: String) -> void:
			# 解锁时给个视觉提示（横幅由 BOSS 掉落那边负责，
			# 这里只管技能本体可用）
			pass)


func _on_segment_done(heavy: bool) -> void:
	if skill_tree == null:
		return
	skill_tree.push_action("heavy" if heavy else "light")
	# push_action 内部会在序列匹配时解锁技能并 emit。
	# 但"解锁"和"释放"是两件事：
	#   · BOSS 掉落 → 解锁（之后可以用）
	#   · 已经解锁 + 凑成连招 → 立即释放
	# 所以这里检查"已解锁 + 序列匹配"，匹配就放技能。
	_check_cast()


func _check_cast() -> void:
	if skill_tree == null or _pierce_fx == null or _player == null:
		return
	if not skill_tree.is_unlocked("pierce_weave"):
		return
	var seq: Array = skill_tree.get_sequence()
	var n := PIERCE_COMBO.size()
	if seq.size() < n:
		return
	var off := seq.size() - n
	for i in n:
		if seq[off + i] != PIERCE_COMBO[i]:
			return
	# 匹配上了：释放并清空序列，避免连续触发
	skill_tree.reset_sequence()
	var facing: int = _player.get("facing")
	var origin: Vector2 = _player.global_position + Vector2(0, -20)
	_pierce_fx.fire(origin, facing)


const PIERCE_COMBO := ["light", "light", "light", "heavy"]


func _connect_boss(room: Node, bossbar: Control, banner: Control) -> void:
	var boss: Node = room.get("boss")
	if boss == null:
		await get_tree().process_frame
		boss = room.get("boss")
	if boss == null:
		return

	bossbar.show_boss("瓷面的守夜人")
	bossbar.set_hp(1.0)

	var timer := Timer.new()
	timer.wait_time = 0.05
	timer.autostart = true
	timer.timeout.connect(func() -> void:
		if boss == null or not is_instance_valid(boss):
			bossbar.hide_boss()
			return
		var ratio: float = float(boss.get("hp")) / float(boss.get("max_hp"))
		bossbar.set_hp(ratio)
		var ph: int = boss.get("phase")
		if ph != bossbar.get_phase():
			bossbar.set_phase(ph))
	bossbar.add_child(timer)

	boss.boss_died.connect(func() -> void:
		bossbar.hide_boss()
		_grant_reward(banner))


func _grant_reward(banner: Control) -> void:
	"""BOSS 奖励：显示获得横幅 → 解锁技能。

	注意解锁的是"能不能用"，不是"立刻放一次"。
	玩家拿到技能后要靠自己打出连招才触发 —— 这才是"学会"。
	"""
	if skill_tree == null:
		return
	var sk: Dictionary = skill_tree.get_skill("pierce_weave")
	if sk.is_empty():
		return
	banner.show_item(sk["name"], sk["desc"], "res://art/items/spool_48.png")
	# 人物抬手接住的动作
	if _player != null and _player.has_method("play_gain_anim"):
		_player.play_gain_anim()
	skill_tree.try_unlock("pierce_weave")


func _find_player(node: Node) -> Node:
	if node.is_in_group("player"):
		return node
	for c in node.get_children():
		var r := _find_player(c)
		if r != null:
			return r
	return null


func _find_camera(node: Node) -> Camera2D:
	for c in node.get_children():
		if c is Camera2D:
			return c
		var r := _find_camera(c)
		if r != null:
			return r
	return null
