"""存档系统：localStorage 持久化 + 快照 + 导出/导入。

## 设计

**单槽位、快照式**：不设存档点实体，玩家随时退出都能接着玩。
每次关键事件（受伤、解锁技能、打赢 BOSS、场景切换）自动存一次。

## 存储格式

localStorage 的键：`actgame.save.v1`
值是 JSON 字符串：

    {
      "version": 1,
      "saved_at": 1795401015,          # Unix 秒，用于"继续游戏"显示时间
      "play_time": 623.5,               # 累计游玩秒数
      "hearts": 4,
      "max_hearts": 5,
      "skills": ["seam", "pierce_weave"],
      "boss_defeated": true,
      "phase": 1,                       # 预留：以后有多场景时用
      "player_pos": [240.0, 400.0],
      "checksum": "8f3a..."             # 简单校验，防手改坏档
    }

## 为什么带 version 和 checksum

- `version`：以后改存档结构时能识别旧档，做迁移或丢弃，而不是崩溃
- `checksum`：玩家可能手动改 localStorage 或导入别人的档，
  校验能挡住明显的损坏（**不是防作弊**，只是防手滑）

## 导出/导入

导出成 `.json` 文件（用浏览器 download）。导入时校验 version 与 checksum，
失败给明确原因而不是静默丢弃。

## Web 与非 Web

Godot 的 `JavaScriptBridge` 只在 Web 导出下存在。
桌面运行时退回 `user://save.json`，这样本地调试也能用。
"""

extends Node
## 存档管理器。挂在 bootstrap 上，全局唯一。
##
## 导出格式：**加密存档码**（一串可复制粘贴的文本，见 save_codec.gd），
## 不再是 .json 文件 —— 移动端复制粘贴比下载文件顺手得多。

signal saved
signal loaded(success: bool, reason: String)
signal save_cleared
# 存档内容变化（写入/清除/导入）：菜单据此刷新"继续游戏"的可用状态
signal changed

const KEY := "actgame.save.v1"
const SAVE_VERSION := 1
const DESKTOP_PATH := "user://actgame_save.json"
const SaveCodec := preload("res://src/systems/save_codec.gd")

# 当前内存中的存档数据
var _data: Dictionary = {}
var _has_save := false
var _save_time := 0.0
var _dirty := false


func _ready() -> void:
	_refresh_state()


func _process(delta: float) -> void:
	_save_time += delta
	# 每秒检查一次"脏了没"，攒够 2 秒自动落盘，避免频繁写 localStorage
	if _dirty and _save_time >= 2.0:
		_save_time = 0.0
		flush()


# ─────────────── Web / 桌面 适配 ───────────────

func _is_web() -> bool:
	return OS.has_feature("web")


func _js_call(code: String) -> String:
	"""执行一段 JS 并返回字符串结果。非 Web 返回空串。"""
	if not _is_web():
		return ""
	# JavaScriptBridge.eval 返回 Variant，统一转成字符串
	var r = JavaScriptBridge.eval(code, true)
	return "" if r == null else str(r)


func _storage_get() -> String:
	if _is_web():
		# 用 try 包住：隐私模式下 localStorage 访问会抛异常
		return _js_call(
			"(function(){try{var v=localStorage.getItem('%s');" % KEY +
			"return v===null?'':v;}catch(e){return '';}})()")
	# 桌面：读 user:// 文件
	if not FileAccess.file_exists(DESKTOP_PATH):
		return ""
	var f := FileAccess.open(DESKTOP_PATH, FileAccess.READ)
	if f == null:
		return ""
	var s := f.get_as_text()
	f.close()
	return s


func _storage_set(payload: String) -> void:
	if _is_web():
		# 用 JSON.stringify 再包一层，避免内容里的引号破坏 JS 字符串字面量
		_js_call(
			"(function(){try{localStorage.setItem('%s', %s);return '1';}" % [KEY, JSON.stringify(payload)] +
			"}catch(e){return '0';}})()")
		return
	var f := FileAccess.open(DESKTOP_PATH, FileAccess.WRITE)
	if f == null:
		printerr("存档写入失败：", DESKTOP_PATH)
		return
	f.store_string(payload)
	f.close()


func _storage_remove() -> void:
	if _is_web():
		_js_call("(function(){try{localStorage.removeItem('%s');}catch(e){}})()" % KEY)
		return
	if FileAccess.file_exists(DESKTOP_PATH):
		DirAccess.remove_absolute(ProjectSettings.globalize_path(DESKTOP_PATH))


# ─────────────── 校验 ───────────────

func _checksum(d: Dictionary) -> String:
	"""对关键字段算一个轻量校验和。

	**只取整数字段和字符串数组**，不碰浮点。
	踩过的坑：最初还想把 player_pos（浮点）算进去，
	但 JSON 往返一次浮点可能从 240.0 变成 240，str() 出来的字面量不同，
	校验和就对不上，导致"导出的档导不回去"。
	浮点本来也不该参与完整性校验。
	"""
	var parts := PackedStringArray()
	parts.append(str(int(d.get("version", 0))))
	parts.append(str(int(d.get("hearts", 0))))
	parts.append(str(int(d.get("max_hearts", 0))))
	parts.append("1" if d.get("boss_defeated", false) else "0")
	var sk: Array = d.get("skills", [])
	var sorted: Array = []
	for s in sk:
		sorted.append(str(s))
	sorted.sort()
	parts.append(",".join(sorted))
	var raw := "|".join(parts)
	# 简易 FNV-1a 32 位
	var h := 2166136261
	for i in raw.length():
		h = h ^ raw.unicode_at(i)
		h = (h * 16777619) & 0xFFFFFFFF
	return "%08x" % h


# ─────────────── 读写 ───────────────

func has_save() -> bool:
	return _has_save


func get_data() -> Dictionary:
	return _data.duplicate(true)


func _refresh_state() -> void:
	var raw := _storage_get()
	if raw.strip_edges() == "":
		_has_save = false
		_data = {}
		return
	var parsed = JSON.parse_string(raw)
	if not (parsed is Dictionary):
		printerr("存档解析失败，视为无存档")
		_has_save = false
		_data = {}
		return
	# 版本检查
	if int(parsed.get("version", 0)) != SAVE_VERSION:
		printerr("存档版本不匹配（%s），视为无存档" % parsed.get("version", "?"))
		_has_save = false
		_data = {}
		return
	# 校验和
	var expect: String = _checksum(parsed)
	if parsed.get("checksum", "") != expect:
		printerr("存档校验失败，视为无存档")
		_has_save = false
		_data = {}
		return
	_data = parsed
	_has_save = true


func write_snapshot(state: Dictionary) -> void:
	"""写入一份快照。state 由调用方提供（player/skill_tree 汇总）。"""
	var d := state.duplicate(true)
	d["version"] = SAVE_VERSION
	d["saved_at"] = int(Time.get_unix_time_from_system())
	d["checksum"] = _checksum(d)
	_data = d
	_has_save = true
	_dirty = true
	# 立即写一次，保证"退出"这种极端情况也不丢
	flush()


func flush() -> void:
	if not _has_save:
		return
	_storage_set(JSON.stringify(_data))
	_dirty = false
	saved.emit()
	changed.emit()


func clear() -> void:
	_storage_remove()
	_data = {}
	_has_save = false
	_dirty = false
	save_cleared.emit()
	changed.emit()


# ─────────────── 导出 / 导入 ───────────────

func export_payload() -> String:
	"""导出成**加密存档码**（一串可直接复制粘贴的文本）。

	格式 `AG1.<base64>`，AES-256-CBC 加密 + SHA-256 完整性校验。
	同样的串粘回去就能还原原始存档。
	"""
	if not _has_save:
		return ""
	# 先序列化成紧凑 JSON（不要缩进 —— 缩进会让密文变长且没必要）
	var json := JSON.stringify(_data)
	return SaveCodec.encode(json)


func export_filename() -> String:
	var t := int(_data.get("saved_at", 0))
	if t <= 0:
		return "actgame_save.txt"
	var dt := Time.get_datetime_dict_from_unix_time(t)
	return "actgame_save_%04d%02d%02d_%02d%02d.txt" % [
		dt["year"], dt["month"], dt["day"], dt["hour"], dt["minute"]]


func import_payload(text: String) -> bool:
	"""导入存档码。

	流程：解码 → 解出 JSON → 校验 version/checksum → 写入。
	任何一步失败都会 emit loaded(false, reason)，并给出**人话的原因**
	（不要只说"失败"，玩家不知道是复制漏了还是码本身坏了）。
	"""
	var stripped := text.strip_edges()
	# 兼容纯 JSON（旧格式 / 开发者手动贴）—— 但主路径是加密码
	var json_text := stripped
	if stripped.begins_with(SaveCodec.MAGIC) or not stripped.begins_with("{"):
		var r: Dictionary = SaveCodec.decode(stripped)
		if not r.get("ok", false):
			loaded.emit(false, str(r.get("error", "存档码无法解码")))
			return false
		json_text = str(r.get("text", ""))

	var parsed = JSON.parse_string(json_text)
	if not (parsed is Dictionary):
		loaded.emit(false, "存档内容不是有效的 JSON 对象")
		return false
	if int(parsed.get("version", 0)) != SAVE_VERSION:
		loaded.emit(false, "存档版本不匹配（需要 v%d）" % SAVE_VERSION)
		return false
	var expect: String = _checksum(parsed)
	if parsed.get("checksum", "") != expect:
		loaded.emit(false, "存档校验失败，文件可能已损坏")
		return false
	_data = parsed
	_has_save = true
	flush()
	loaded.emit(true, "导入成功")
	return true


# ─────────────── 摘要（给菜单显示） ───────────────

func summary() -> String:
	"""给"继续游戏"按钮显示的一行摘要。"""
	if not _has_save:
		return "无存档"
	var hearts := int(_data.get("hearts", 0))
	var mx := int(_data.get("max_hearts", 5))
	var nskills: int = (_data.get("skills", []) as Array).size()
	var boss := "已击败守夜人" if _data.get("boss_defeated", false) else "未击败守夜人"
	return "❤ %d/%d   ·   技能 %d   ·   %s" % [hearts, mx, nskills, boss]
