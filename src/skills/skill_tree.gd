"""技能树数据模型。

## 设计要点

1. **数据与表现分离** —— 技能树的结构（节点、前置关系、解锁条件）
   全部放在这个脚本里，UI 只负责画。这样加技能不用改 UI。

2. **解锁条件是"连招"而不是"等级"** —— 用户的原始需求是
   「轻攻击三连 + 一次重攻击」触发。所以条件是**动作序列**，
   不是数值门槛。这让技能有"练出来"的感觉。

3. **节点有前置依赖** —— 技能树不是平铺列表，解锁 A 才能解锁 B。
   这里用 `requires` 字段表达有向依赖。

## 当前技能

  根节点 `seam`（缝纫基础）永远解锁，是树的起点。
  唯一可解锁节点 `pierce_weave`（贯穿织）——BOSS 奖励，
  触发条件：轻攻击 1→2→3 段接一次重攻击。
"""

extends Node
## 技能树管理器。挂在 bootstrap 上，全局唯一。

signal skill_unlocked(skill_id: String)
signal unlock_failed(skill_id: String, reason: String)

# ── 技能定义 ──
# id:        唯一标识
# name:      显示名
# desc:      一句话说明
# requires:  前置技能 id 数组（空 = 无前置）
# always:    true 表示开局就解锁（树根）
# combo:     解锁所需的连招序列（空 = 不需要连招）
# cost:      保留字段（当前没有资源系统）
const SKILLS := {
	"seam": {
		"name": "缝",
		"desc": "织线的基础。以针为剑，以布为盾。",
		"requires": [],
		"always": true,
		"combo": [],
		"pos": Vector2(0.5, 0.14),      # UI 归一化坐标
	},
	"pierce_weave": {
		"name": "贯穿织",
		"desc": "把线收成一束贯穿出去。轻攻击三连后接重击即可发动。",
		"requires": ["seam"],
		"always": false,
		# 触发序列：轻 0 → 轻 1 → 轻 2 → 重。用字符串描述，
		# 这样一眼能读懂，也方便以后加新组合。
		"combo": ["light", "light", "light", "heavy"],
		# **必须由 BOSS 掉落获得**，不能靠连招自己解锁。
		# 否则"打 BOSS 给奖励"这件事就没有意义了 ——
		# 玩家在杂兵身上连招就能拿到技能。
		"from_boss": true,
		"pos": Vector2(0.5, 0.50),
	},
	"mend_veil": {
		"name": "补幕",
		"desc": "（未实装）把破口缝合成屏障。",
		"requires": ["pierce_weave"],
		"always": false,
		"combo": [],
		"pos": Vector2(0.5, 0.86),
	},
}

# 已解锁集合
var _unlocked: Dictionary = {}
# **连招判定直接复用玩家侧的连段链**（见 src/player/combo_chain.gd）
# 不再自己维护一份 _sequence —— 那会导致"两份状态可能不一致"。
# 由 bootstrap 在玩家就绪后注入。
var _chain = null


func bind_chain(chain) -> void:
	"""注入连段链。之后所有连招判定都读它。"""
	_chain = chain


func _ready() -> void:
	for id in SKILLS:
		if SKILLS[id]["always"]:
			_unlocked[id] = true


func is_unlocked(skill_id: String) -> bool:
	return _unlocked.get(skill_id, false)


func get_skill(skill_id: String) -> Dictionary:
	return SKILLS.get(skill_id, {})


func all_skills() -> Array:
	return SKILLS.keys()


func get_unlocked_count() -> int:
	var n := 0
	for id in _unlocked:
		if _unlocked[id]:
			n += 1
	return n


# ─────────────── 连招追踪 ───────────────

func push_action(kind: String) -> void:
	"""已废弃：连招序列现在由玩家的 ComboChain 统一维护。

	保留这个空壳是为了不动 bootstrap 的调用点（它还会调一次），
	真正的入链发生在 player 的 _chain_push 里。
	这里只负责"链变化后检查一次解锁"。
	"""
	_check_unlock()


func _check_unlock() -> void:
	for id in SKILLS:
		var sk: Dictionary = SKILLS[id]
		if sk["always"] or is_unlocked(id):
			continue
		# from_boss 的技能只能通过 try_unlock（掉落）获得，
		# 连招不能自己解锁它们
		if sk.get("from_boss", false):
			continue
		var combo: Array = sk["combo"]
		if combo.is_empty():
			continue
		# 前置是否满足
		var pre_ok := true
		for req in sk["requires"]:
			if not is_unlocked(req):
				pre_ok = false
				break
		if not pre_ok:
			continue
		if _chain != null and _chain.matches(combo):
			_unlock(id)


func _unlock(skill_id: String) -> void:
	if is_unlocked(skill_id):
		return
	_unlocked[skill_id] = true
	# 解锁后清空链，避免同一个连招连续触发多个技能
	if _chain != null:
		_chain.clear()
	skill_unlocked.emit(skill_id)


func try_unlock(skill_id: String) -> bool:
	"""外部（比如 BOSS 掉落）直接尝试解锁。返回是否成功。

	用途：BOSS 打死后如果玩家已经会用这个连招，直接给技能；
	如果还不会，先记下来（这里简化成直接解锁，因为技能是"奖励"）。
	"""
	var sk: Dictionary = SKILLS.get(skill_id, {})
	if sk.is_empty():
		unlock_failed.emit(skill_id, "技能不存在")
		return false
	var pre_ok := true
	for req in sk.get("requires", []):
		if not is_unlocked(req):
			pre_ok = false
			break
	if not pre_ok:
		unlock_failed.emit(skill_id, "前置技能未解锁")
		return false
	_unlock(skill_id)
	return true


func reset_sequence() -> void:
	"""清空连招记录。现在直接清玩家的链（唯一真相）。"""
	if _chain != null:
		_chain.clear()


func is_bound() -> bool:
	return _chain != null


func get_sequence() -> Array:
	return _chain.kinds() if _chain != null else []


func get_chain() -> Variant:
	return _chain
