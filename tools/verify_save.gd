extends SceneTree
## 存档系统 + 主菜单 验证
##
## 运行：godot --headless --path . --script tools/verify_save.gd
##
## 注意：这些测试**不需要 autoplay**（要测菜单本身），
## 所以验证菜单/存档的部分走正常启动路径。

var _failures: Array[String] = []
var _checks := 0


func _init() -> void:
	# 干净起点：删掉可能存在的存档
	_clear_storage()

	var boot: PackedScene = load("res://scenes/bootstrap.tscn")
	root.add_child(boot.instantiate())
	await process_frame
	await process_frame
	for i in 20:
		await physics_frame

	print("── 存档系统与主菜单验证 ──")

	var save = _find_script(root, "save_system")
	var menu = _find_script(root, "main_menu")
	var settings = _find_script(root, "settings_panel")

	_check(save != null, "1. 存档系统节点存在", "未找到")
	_check(menu != null, "2. 主菜单节点存在", "未找到")
	_check(settings != null, "3. 设置面板节点存在", "未找到")
	if save == null:
		_finish()
		return

	# ── 初始状态 ──
	_check(not save.has_save(), "4. 无存档时 has_save 为 false",
	       "有存档")
	_check(save.summary() == "无存档", "5. 无存档时摘要正确",
	       save.summary())
	if menu:
		_check(menu.visible, "6. 启动停在主菜单", "菜单不可见")

	# ── 写入快照 ──
	save.write_snapshot({
		"hearts": 3, "max_hearts": 5,
		"skills": ["seam", "pierce_weave"],
		"boss_defeated": true,
		"phase": 1,
		"player_pos": [240.0, 400.0],
	})
	_check(save.has_save(), "7. 写入后 has_save 为 true", "未写入")
	var d: Dictionary = save.get_data()
	_check(int(d.get("hearts", 0)) == 3, "8. 写入的心心数正确",
	       str(d.get("hearts")))
	_check(d.has("checksum"), "9. 写入时附带 checksum", "缺 checksum")
	_check(int(d.get("version", 0)) == 1, "10. 写入时附带 version",
	       str(d.get("version")))

	# ── 摘要 ──
	var sm: String = save.summary()
	_check(sm.contains("3/5"), "11. 摘要显示心心数", sm)
	_check(sm.contains("技能 2"), "12. 摘要显示技能数", sm)
	_check(sm.contains("已击败"), "13. 摘要显示 BOSS 状态", sm)

	# ── 导出 → 导入往返 ──
	var exported: String = save.export_payload()
	_check(exported.length() > 50, "14. 导出内容非空", "导出为空")
	save.clear()
	_check(not save.has_save(), "15. 清除后无存档", "仍有存档")
	var ok: bool = save.import_payload(exported)
	_check(ok, "16. 导出的存档能原样导入", "导入失败")
	_check(save.has_save(), "17. 导入后有存档", "无存档")
	var d2: Dictionary = save.get_data()
	_check(int(d2.get("hearts", 0)) == 3, "18. 导入后数据一致",
	       str(d2.get("hearts")))

	# ── 坏档必须被拒 ──
	# 现在导出的是**加密存档码**，明文替换无效。
	# 改为篡改密文中间一个字符（长度不变），验证 SHA-256 校验能拦住。
	save.clear()
	var tampered: String = exported
	if tampered.length() > 20:
		var mid: int = tampered.length() / 2
		var ch: String = tampered[mid]
		var repl: String = "B" if ch != "B" else "C"
		tampered = tampered.substr(0, mid) + repl + tampered.substr(mid + 1)
	var bad: bool = save.import_payload(tampered)
	_check(not bad, "19. 篡改过的存档码被拒绝", "竟然导入成功")
	_check(not save.has_save(), "20. 拒绝后不产生存档", "出现了存档")

	# 明显不是存档码的输入
	var bad2: bool = save.import_payload("这不是存档码")
	_check(not bad2, "21. 乱码输入被拒绝", "竟然接受")

	# 合法明文 JSON 但版本号不对（走纯 JSON 兼容路径）
	save.clear()
	var wrong_ver: String = '{"version":99,"hearts":3,"max_hearts":5,"skills":["seam"],"boss_defeated":false,"player_pos":[0,0],"checksum":"x"}'
	_check(not save.import_payload(wrong_ver),
	       "22. 版本号不匹配被拒绝", "竟然接受")

	# 漏掉 AG1. 前缀也应能导入（宽松处理复制残留）
	save.clear()
	var no_prefix: String = exported
	if no_prefix.begins_with("AG1."):
		no_prefix = no_prefix.substr(4)
	_check(save.import_payload(no_prefix),
	       "22b. 漏掉 AG1. 前缀也能导入", "失败了")

	# ── 持久化：重新读取（模拟刷新页面）──
	save.write_snapshot({
		"hearts": 4, "max_hearts": 5, "skills": ["seam"],
		"boss_defeated": false, "phase": 1, "player_pos": [100.0, 400.0],
	})
	save.flush()
	save._refresh_state()
	_check(save.has_save(), "23. 落盘后重新读取仍有存档", "丢失")
	var d3: Dictionary = save.get_data()
	_check(int(d3.get("hearts", 0)) == 4, "24. 重新读取的数据正确",
	       str(d3.get("hearts")))

	# ── 导出文件名 ──
	var fn: String = save.export_filename()
	# 存档码是纯文本，文件名用 .txt（不再是 .json）
	_check(fn.ends_with(".txt"), "25. 导出文件名是 .txt", fn)
	_check(fn.contains("actgame_save"), "26. 导出文件名有前缀", fn)

	# ── 设置面板 ──
	if settings:
		_check(not settings.visible, "27. 设置面板默认关闭", "开着")
		settings.open()
		_check(settings.visible, "28. open() 打开设置面板", "没开")
		settings.close()
		_check(not settings.visible, "29. close() 关闭设置面板", "没关")

	# ── 主菜单的三项 ──
	if menu:
		_check(menu._items.size() == 3, "30. 主菜单有三个入口",
		       "实际 %d" % menu._items.size())
		var labels := []
		for it in menu._items:
			labels.append(it["label"])
		_check(labels == ["开始游戏", "继续游戏", "设置"],
		       "31. 三个入口标签正确", str(labels))

	_clear_storage()
	_finish()


func _clear_storage() -> void:
	# 测试在桌面环境跑，清 user:// 文件即可
	var p := "user://actgame_save.json"
	if FileAccess.file_exists(p):
		DirAccess.remove_absolute(ProjectSettings.globalize_path(p))


func _finish() -> void:
	print("")
	if _failures.is_empty():
		print("PASS: 全部 %d 项通过" % _checks)
		quit(0)
	else:
		print("FAIL: %d 项失败" % _failures.size())
		for f in _failures:
			printerr("  - " + f)
		quit(1)


func _check(cond: bool, name: String, detail: String = "") -> void:
	_checks += 1
	if cond:
		print("  ok   %s" % name)
	else:
		print("  FAIL %s" % name)
		_failures.append(name + (": " + detail if detail != "" else ""))


func _find_script(node: Node, name: String):
	var s = node.get_script()
	if s != null and str(s.resource_path).contains(name):
		return node
	for c in node.get_children():
		var r = _find_script(c, name)
		if r:
			return r
	return null
