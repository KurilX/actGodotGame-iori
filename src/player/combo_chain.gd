"""连段链：用一条「打过的动作序列」同时表达段号、连招、时间窗口。

## 为什么这么做

原来是两套东西各存一份状态：
  · `player.gd` 的 `_combo_index/_heavy_index`  —— 当前打到第几段
  · `skill_tree.gd` 的 `_sequence`              —— 最近打了什么动作

这两者本质是**同一个事实的两种投影**：打过的动作序列必然确定了段号。
用户指出这一点是对的，之前我担心的三个反例（回环、轻重独立、时间窗口）
其实都能在**一条链里**用更简单的规则表达：

  · 回环        → 链满就整体清空，而不是把游标归零
  · 轻重独立    → 链元素带类型，轻/重各自算自己的段号
  · 时间窗口    → 每个元素带时间戳，超窗的自动丢弃

## 链元素结构

    {"kind": "light"|"heavy", "index": 段号, "t": 时间戳}

`index` 在入链时就固定下来（那一刻段号就是链里同类元素的个数），
所以后面读段号不需要重新推算，也不会受"清空重开"影响。

## 段号怎么算

    func current_index(kind) -> int:
        # 清空后链为空 → 0；否则是链里最后一个同类元素的 index
        for i in range(chain.size() - 1, -1, -1):
            if chain[i].kind == kind: return chain[i].index
        return 0

回环处理：链里同类元素达到上限时，**整体清空**再追加新的。
这样"第 5 次轻攻击"的链是 `[{light,0}]`，段号自然是 0，
而不是靠 "_combo_index 取模" 这种隐含规则。
"""

const KIND_LIGHT := "light"
const KIND_HEAVY := "heavy"

# 链最多保留多少个元素（跨轻重合计）
const MAX_ENTRIES := 12


class Entry:
	var kind: String
	var index: int          # 段号（同类元素在这一串里的序号）
	var t: float            # 打出时的时间戳（秒）

	func _init(k: String, i: int, time: float) -> void:
		kind = k
		index = i
		t = time

	func to_dict() -> Dictionary:
		return {"kind": kind, "index": index, "t": t}


var _chain: Array = []
var _start_time := 0.0

# 每类链的最大段数（由玩家侧注入，避免这里硬编码）
var _max_of := {KIND_LIGHT: 4, KIND_HEAVY: 3}
# 接段窗口（秒）：同类动作间隔超过这个值就视为新的一套
var _window_of := {KIND_LIGHT: 0.55, KIND_HEAVY: 0.35}


func configure(max_light: int, max_heavy: int,
			   window_light: float, window_heavy: float) -> void:
	_max_of[KIND_LIGHT] = max_light
	_max_of[KIND_HEAVY] = max_heavy
	_window_of[KIND_LIGHT] = window_light
	_window_of[KIND_HEAVY] = window_heavy


func set_start_time(seconds: float) -> void:
	_start_time = seconds


func now(seconds: float) -> void:
	"""由外部每帧喂当前时间，链内部用它做过期清理。"""
	_prune(seconds)


func _prune(t: float) -> void:
	"""丢掉超过窗口的元素。

	窗口按类型分别算：轻攻击 0.55s、重攻击 0.35s。
	用「最近一个同类元素」的时间判断，而不是每个元素各自比 ——
	因为连招的语义是"连续接上"，中间夹一个超时的就算断了。
	"""
	var last_t := {KIND_LIGHT: -INF, KIND_HEAVY: -INF}
	# 从后往前找每个类型的最后时间
	for i in range(_chain.size() - 1, -1, -1):
		var e = _chain[i]
		if last_t[e.kind] == -INF:
			last_t[e.kind] = e.t
	# 再过一遍，删掉超窗的
	var kept: Array = []
	for e in _chain:
		var lt: float = last_t[e.kind]
		if lt - e.t <= _window_of[e.kind] + 0.0001:
			kept.append(e)
	_chain = kept
	# 超过总容量就从最老的丢
	while _chain.size() > MAX_ENTRIES:
		_chain.pop_front()


func push(kind: String, t: float) -> int:
	"""追加一次动作。**返回本次的段号**。

	注意返回类型必须是 int —— 曾经误写成 `-> void`，
	调用方拿到的值是 null，导致段号永远是 0，回环逻辑完全失效。
	"""
	_prune(t)
	var idx := _next_index(kind)
	# 回环：同类段数达到上限 → 整体清空重开，新段号从 0 开始。
	# 用"清空"而不是"游标归零"，这样链内容与段号天然一致。
	if idx >= _max_of[kind]:
		_chain.clear()
		idx = 0
	_chain.append(Entry.new(kind, idx, t))
	while _chain.size() > MAX_ENTRIES:
		_chain.pop_front()
	return idx


func _next_index(kind: String) -> int:
	"""下一次该是第几段 = 链里同类元素的最后一个 index + 1。"""
	for i in range(_chain.size() - 1, -1, -1):
		if _chain[i].kind == kind:
			return _chain[i].index + 1
	return 0


func current_index(kind: String) -> int:
	"""当前（最后一次）是第几段。没有记录则为 0。"""
	for i in range(_chain.size() - 1, -1, -1):
		if _chain[i].kind == kind:
			return _chain[i].index
	return 0


func last_kind() -> String:
	return _chain[-1].kind if not _chain.is_empty() else ""


func size() -> int:
	return _chain.size()


func clear() -> void:
	_chain.clear()


# ─────────────── 连招匹配 ───────────────

func matches(pattern: Array) -> bool:
	"""链的**末尾**是否匹配给定的动作序列。

	pattern 元素可以是：
	  · 字符串 "light"/"heavy"        —— 只匹配动作类型
	  · Dictionary {"kind": ..., "index": n} —— 同时匹配段号

	后者用来表达"必须是第 3 段接重击"这类更严格的条件。
	"""
	var n := pattern.size()
	if _chain.size() < n:
		return false
	var off := _chain.size() - n
	for i in n:
		var e = _chain[off + i]
		var pat = pattern[i]
		if pat is String:
			if e.kind != pat:
				return false
		elif pat is Dictionary:
			if e.kind != pat.get("kind", e.kind):
				return false
			if pat.has("index") and e.index != int(pat["index"]):
				return false
		else:
			return false
	return true


func kinds() -> Array:
	var out: Array = []
	for e in _chain:
		out.append(e.kind)
	return out


func dump() -> Array:
	var out: Array = []
	for e in _chain:
		out.append(e.to_dict())
	return out
