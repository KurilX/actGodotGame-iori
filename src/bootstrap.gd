extends Node
## 启动场景：主菜单优先，选择后才进游戏。
##
## ## 状态流
##
##   MENU  ──开始/继续──▶  GAME  ──返回菜单──▶  MENU
##    ↑                                          │
##    └──────────── 设置面板（叠在 MENU 上）──────┘
##
## ## 层分配（layer 从低到高）
##
##   10  MenuLayer       主菜单
##   12  SettingsLayer   设置面板
##   80  BulletTimeLayer 子弹时间特效
##   85  BossBarLayer    BOSS 血条
##   88  ItemBannerLayer 获得道具横幅
##   90  ComboLayer      连击条
##   92  SkillTreeLayer  技能树面板（F1/Tab）
##   100 TouchLayer      触屏虚拟按键
##
## ## 为什么游戏内容延迟创建
##
## 原来是 _ready 里就 instantiate 房间。现在如果玩家停在菜单，
## 房间里的 BOSS/杂兵会在后台一直跑（耗 CPU、也可能触发逻辑）。
## 所以房间改为"开始游戏时才创建"，退出时 queue_free。

enum Mode { MENU, GAME }

const TouchControls := preload("res://src/ui/touch_controls.gd")
const ComboMeter := preload("res://src/ui/combo_meter.gd")
const BulletTimeFx := preload("res://src/ui/bullet_time_fx.gd")
const BossHealthBar := preload("res://src/ui/boss_healthbar.gd")
const ItemGainBanner := preload("res://src/ui/item_gain_banner.gd")
const SkillTreePanel := preload("res://src/ui/skill_tree_panel.gd")
const SkillTree := preload("res://src/skills/skill_tree.gd")
const PierceWeaveFx := preload("res://src/skills/pierce_weave_fx.gd")
const SaveSystem := preload("res://src/systems/save_system.gd")
const MainMenu := preload("res://src/ui/main_menu.gd")
const SettingsPanel := preload("res://src/ui/settings_panel.gd")
const TutorialHints := preload("res://src/ui/tutorial_hints.gd")
const ParrySpark := preload("res://src/skills/parry_spark.gd")
const CartoonFilter := preload("res://src/ui/cartoon_filter.gd")

var skill_tree: Node
var save: Node
var _mode: Mode = Mode.MENU
var _room: Node = null
var _player: Node = null
var _pierce_fx: Node2D = null

# UI 引用
var _menu: Control
var _settings: Control
var _combo: Control
var _bt: Control
var _bossbar: Control
var _banner: Control
var _panel: Control
var _tutorial: Control
var _touch: Control
var _filter: Control

# 需要随游戏创建/销毁的层（菜单常驻的不动）
var _game_layers: Array[CanvasLayer] = []


func _ready() -> void:
	# ── 逻辑单例 ──
	save = Node.new()
	save.name = "SaveSystem"
	save.set_script(SaveSystem)
	add_child(save)

	skill_tree = Node.new()
	skill_tree.name = "SkillTree"
	skill_tree.set_script(SkillTree)
	add_child(skill_tree)

	# ── 常驻 UI：主菜单 + 设置 ──
	_menu = _make_layer("MenuLayer", 10, MainMenu, "MainMenu")
	_settings = _make_layer("SettingsLayer", 12, SettingsPanel, "SettingsPanel")

	_menu.bind_save(save)
	# 存档一变就刷新菜单，否则"继续游戏"的可用状态不会更新
	save.changed.connect(func() -> void: _menu.refresh())
	_menu.start_new_game.connect(_on_start_new)
	_menu.continue_game.connect(_on_continue)
	_menu.open_settings.connect(_on_open_settings)
	_menu.copy_code.connect(_on_copy_code)
	_menu.import_code.connect(_on_import_code)
	_menu.clear_save.connect(_on_clear)

	_settings.copy_code.connect(_on_copy_code)
	_settings.clear_save.connect(_on_clear)
	_settings.back_to_menu.connect(func() -> void:
		if _mode == Mode.GAME:
			_return_to_menu())
	_settings.volume_changed.connect(_on_volume)

	# ── 卡通滤镜（layer 50）──
	#
	# 放在**世界之上、所有 UI 之下**：
	#   · 高于世界（layer 0）→ 能对整个游戏画面调色
	#   · 低于 UI（80/85/88/90/92/100）→ 不会把血条、连击条、
	#     菜单文字也一起调暖调色，否则颜色会偏离设计值
	# **注意**：滤镜脚本 extends ColorRect，不能用 _make_layer
	# （它创建的是 Control，set_script 会报
	#  "Script inherits from native type 'ColorRect'" 而静默失败）。
	# 这里手动建 CanvasLayer + ColorRect。
	_filter = _make_filter_layer("CartoonFilterLayer", 50)

	# ── 游戏 UI 层：先建好但隐藏，进游戏才显示 ──
	_bt = _make_game_layer("BulletTimeLayer", 80, BulletTimeFx, "BulletTimeFx")
	_bossbar = _make_game_layer("BossBarLayer", 85, BossHealthBar,
								"BossHealthBar")
	_banner = _make_game_layer("ItemBannerLayer", 88, ItemGainBanner,
							   "ItemGainBanner")
	_combo = _make_game_layer("ComboLayer", 90, ComboMeter, "ComboMeter")
	_panel = _make_game_layer("SkillTreeLayer", 92, SkillTreePanel,
							  "SkillTreePanel")
	# 教程提示放在连击条下层，避免遮挡战斗信息
	_tutorial = _make_game_layer("TutorialLayer", 86, TutorialHints,
								 "TutorialHints")
	_touch = _make_game_layer("TouchLayer", 100, TouchControls, "TouchControls")
	_panel.bind(skill_tree)

	# 进菜单，或按参数直接进游戏。
	#
	# `--autoplay` 命令行参数：跳过菜单直接开始一局。
	# 用途是让 140+ 项自动化测试不必每次模拟"点开始游戏"；
	# 正常启动仍然停在菜单。
	#
	# 另外 URL 参数 ?autoplay=1 也给 Web 端留了口子（方便手动测某个状态）。
	if "--autoplay" in OS.get_cmdline_user_args() or _url_has_autoplay():
		_enter_game(false)
	else:
		_enter_menu()


func _url_has_autoplay() -> bool:
	if not OS.has_feature("web"):
		return false
	var q := str(JavaScriptBridge.eval(
		"(function(){var m=location.search.match(/[?&]autoplay=([^&]*)/);"
		+ "return m?m[1]:'';})()", true))
	return q == "1" or q.to_lower() == "true"


# ─────────────── 状态切换 ───────────────

func _enter_menu() -> void:
	_mode = Mode.MENU
	_menu.visible = true
	_menu.refresh()
	_settings.visible = false
	_set_game_ui_visible(false)
	if _room != null and is_instance_valid(_room):
		_room.queue_free()
		_room = null
		_player = null
		_pierce_fx = null


func _enter_game(from_save: bool) -> void:
	_mode = Mode.GAME
	_menu.visible = false
	_settings.visible = false
	_set_game_ui_visible(true)

	# 建房间（延迟到此刻）
	var room_scene: PackedScene = load("res://scenes/rooms/room_greybox.tscn")
	_room = room_scene.instantiate()
	add_child(_room)

	# 技能特效挂在房间里
	_pierce_fx = Node2D.new()
	_pierce_fx.name = "PierceWeaveFx"
	_pierce_fx.set_script(PierceWeaveFx)
	_room.add_child(_pierce_fx)

	await get_tree().process_frame

	_player = _find_player(_room)
	if _player != null and skill_tree.has_method("bind_chain"):
		skill_tree.bind_chain(_player.get_chain())

	if _tutorial != null and _player != null:
		_tutorial.bind_player(_player)
	_connect_player(_room)
	_connect_boss(_room)

	# 读档：把状态应用到刚建好的角色与技能树
	if from_save and save.has_save():
		_apply_save(save.get_data())


func _return_to_menu() -> void:
	# 退出游戏前先存一次，保证"随时退出都能继续"
	if _mode == Mode.GAME:
		_write_save()
	_enter_menu()


func _set_game_ui_visible(on: bool) -> void:
	for cl in _game_layers:
		cl.visible = on
	# 触屏按键自己有显隐规则（默认隐藏 + ?touch=1/F2），不要强行打开
	if _touch != null and not on:
		_touch.visible = false


# ─────────────── 存档 ───────────────

func _write_save() -> void:
	if _player == null or not is_instance_valid(_player):
		return
	var d: Dictionary = _player.to_save_dict()
	d["skills"] = skill_tree.to_save_array()
	d["boss_defeated"] = _boss_defeated
	d["phase"] = 1
	save.write_snapshot(d)


func _apply_save(d: Dictionary) -> void:
	if _player != null:
		_player.from_save_dict(d)
		var pos: Array = d.get("player_pos", [])
		if pos.size() == 2:
			_player.global_position = Vector2(float(pos[0]), float(pos[1]))
	if skill_tree.has_method("from_save_array"):
		skill_tree.from_save_array(d.get("skills", []))
	_boss_defeated = bool(d.get("boss_defeated", false))
	# 技能树状态变了，面板要刷新
	_menu.refresh()


var _boss_defeated := false


# ─────────────── 事件 ───────────────

func _on_start_new() -> void:
	save.clear()
	_boss_defeated = false
	_enter_game(false)


func _on_continue() -> void:
	if not save.has_save():
		return
	_enter_game(true)


func _on_open_settings() -> void:
	_settings.open()


func _on_copy_code() -> void:
	"""把加密存档码复制到剪贴板。"""
	var code: String = save.export_payload()
	if code == "":
		_settings.set_message("没有可导出的存档")
		if _menu != null and _menu.has_method("set_import_result"):
			_menu.set_import_result(false, "没有可导出的存档")
		return

	var ok := _copy_to_clipboard(code)
	var msg := ("存档码已复制（%d 字符），可粘贴保存" % code.length()) if ok \
		else "复制失败，请手动保存"
	_settings.set_message(msg)
	if _menu != null and _menu.has_method("set_import_result"):
		_menu.set_import_result(ok, msg)


func _copy_to_clipboard(text: String) -> bool:
	"""跨平台复制到剪贴板。"""
	if OS.has_feature("web"):
		# navigator.clipboard 需要安全上下文（https 或 localhost），
		# 失败时退回 execCommand（老浏览器/非安全上下文）。
		var js := JSON.stringify(text)
		var r := str(JavaScriptBridge.eval(
			"(function(){var t=%s;" % js +
			"try{if(navigator.clipboard&&navigator.clipboard.writeText){" +
			"navigator.clipboard.writeText(t);return '1';}}catch(e){}" +
			"try{var a=document.createElement('textarea');a.value=t;" +
			"a.style.position='fixed';a.style.opacity='0';" +
			"document.body.appendChild(a);a.select();" +
			"var ok=document.execCommand('copy');a.remove();" +
			"return ok?'1':'0';}catch(e){return '0';}})()", true))
		return r == "1"
	DisplayServer.clipboard_set(text)
	return true


func _on_import_code(text: String) -> void:
	"""导入存档码：解码 → 校验 → 写入 → 刷新菜单。

	`import_payload` 是同步返回结果的，所以这里直接拿返回值判断，
	不需要再去监听 loaded 信号（那样反而会重复提示）。
	"""
	var ok: bool = save.import_payload(text)
	if ok:
		_menu.refresh()
		if _menu.has_method("set_import_result"):
			_menu.set_import_result(true, "导入成功")
	else:
		# 具体原因由 save 内部 emit loaded(false, reason)，
		# 这里只给一个简短的提示（详细原因写在 save 的日志里）
		if _menu.has_method("set_import_result"):
			_menu.set_import_result(false, "导入失败：存档码无效或已损坏")


func _on_clear() -> void:
	save.clear()
	_boss_defeated = false
	_menu.refresh()
	_settings.set_message("存档已清除")


func _on_volume(v: float) -> void:
	AudioServer.set_bus_volume_db(0, linear_to_db(maxf(v, 0.0001)))


# ─────────────── 层构造 ───────────────

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


func _make_filter_layer(layer_name: String, layer_idx: int) -> Control:
	"""构造卡通滤镜层。

	单独一个函数的原因：滤镜节点必须是 **ColorRect**（要全屏着色器），
	而 `_make_layer` 固定创建 Control —— 两者类型不兼容，
	`set_script` 会失败且只打一条 ERROR，节点变成空 Control。
	"""
	var cl := CanvasLayer.new()
	cl.name = layer_name
	cl.layer = layer_idx
	add_child(cl)

	var rect := ColorRect.new()
	rect.name = "CartoonFilter"
	rect.set_script(CartoonFilter)
	cl.add_child(rect)
	_game_layers.append(cl)
	return rect


func _make_game_layer(layer_name: String, layer_idx: int, script: Script,
					  node_name: String) -> Control:
	var c := _make_layer(layer_name, layer_idx, script, node_name)
	_game_layers.append(c.get_parent() as CanvasLayer)
	return c


# ─────────────── 游戏内信号连接 ───────────────

func _connect_player(room: Node) -> void:
	if _player == null:
		return

	_player.hit_landed.connect(func(_t: Node, damage: int) -> void:
		_combo.register_hit(2 if damage >= 4 else 1))

	_player.whiffed.connect(func(heavy: bool) -> void:
		_combo.register_whiff(heavy))

	_player.damaged.connect(func(_a: int) -> void:
		_combo.reset_combo()
		skill_tree.reset_sequence()
		# 受伤立刻存档，避免"掉了血退出后血又满了"
		_write_save())

	_player.attack_segment_done.connect(_on_segment_done)

	var cam := _find_camera(_player)
	_player.perfect_dodge.connect(func() -> void:
		_bt.trigger(_player.global_position, cam)
		_combo.register_perfect_dodge())

	# ── 弹反成功反馈 ──
	# 弹反是常驻技能，每次成功都必须有明确反馈，否则玩家不知道自己成功了。
	# 三层：震屏（力度感）+ 连击加成（正反馈）+ 弹幕变金色飞回去（因果可见）。
	_player.parried.connect(func(proj: Node) -> void:
		var cam2 := _find_camera(_player)
		if cam2 != null:
			cam2.shake(5.0, 0.18)
		_combo.register_perfect_dodge()
		# 弹反点爆闪：用一个短命的自绘节点，比开新场景/粒子省事
		_spawn_parry_spark(proj.global_position if is_instance_valid(proj)
						   else _player.global_position))


func _spawn_parry_spark(pos: Vector2) -> void:
	"""弹反成功的爆闪：几圈快速扩散的硬边环 + 中心亮核。

	不用粒子系统：像素风不能有平滑模糊，粒子的半透明缩放会糊。
	用 Tween 驱动一个自绘节点，0.25s 结束。
	"""
	var node := ParrySpark.new()
	node.z_index = 46
	_room.add_child(node)
	node.global_position = pos

func _on_segment_done(_heavy: bool) -> void:
	skill_tree.push_action("")
	_check_cast()


func _check_cast() -> void:
	if _pierce_fx == null or _player == null:
		return
	if not skill_tree.is_unlocked("pierce_weave"):
		return
	var chain = skill_tree.get_chain()
	if chain == null:
		return
	if not chain.matches(PIERCE_COMBO):
		return
	chain.clear()
	var facing: int = _player.get("facing")
	var origin: Vector2 = _player.global_position + Vector2(0, -20)
	_pierce_fx.fire(origin, facing)
	# 释放技能也算一次进度，存一下
	_write_save()


const PIERCE_COMBO := ["light", "light", "light", "heavy"]


func _connect_boss(room: Node) -> void:
	var boss: Node = room.get("boss")
	if boss == null:
		await get_tree().process_frame
		boss = room.get("boss")
	if boss == null:
		return

	# **血条默认不显示**：玩家还在教程关时不该看到 BOSS 血条。
	# 等 room 的 boss_awakened 信号（玩家跨过 BOSS 房分界线）再显示。
	_bossbar.hide_boss()

	if room.has_signal("boss_awakened"):
		room.boss_awakened.connect(func(_b: Node) -> void:
			_bossbar.set_hp(1.0)
			_bossbar.show_boss("瓷面的守夜人"))

	var timer := Timer.new()
	timer.wait_time = 0.05
	timer.autostart = true
	timer.timeout.connect(func() -> void:
		if boss == null or not is_instance_valid(boss):
			_bossbar.hide_boss()
			return
		var ratio: float = float(boss.get("hp")) / float(boss.get("max_hp"))
		_bossbar.set_hp(ratio)
		var ph: int = boss.get("phase")
		if ph != _bossbar.get_phase():
			_bossbar.set_phase(ph))
	_bossbar.add_child(timer)

	boss.boss_died.connect(func() -> void:
		_bossbar.hide_boss()
		_boss_defeated = true
		_grant_reward())


func _grant_reward() -> void:
	var sk: Dictionary = skill_tree.get_skill("pierce_weave")
	if sk.is_empty():
		return
	_banner.show_item(sk["name"], sk["desc"], "res://art/items/spool_48.png")
	if _player != null and _player.has_method("play_gain_anim"):
		_player.play_gain_anim()
	skill_tree.try_unlock("pierce_weave")
	# 解锁后立刻存档 —— 这是最关键的进度，不能丢
	_write_save()
	_menu.refresh()


# ─────────────── 工具 ───────────────

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
