extends SceneTree
## AI 美术门禁：验证「数值 + AI」双轨评分机制本身正确
##
## 运行：godot --headless --path . --script tools/verify_ai_gate.gd
##
## ## 这条测试测什么、不测什么
##
## 它**不**断言"美术必须通过"——因为美术是否达标是内容问题，
## 不是代码问题。如果把它写成"必须通过"，美术一退步整条 CI 就红，
## 反而会逼着人去放宽阈值。
##
## 它断言的是**机制正确**：
##   · 两份评分 JSON 都存在且可解析
##   · 三道门都有明确的布尔结果
##   · 合并公式算得对（防止权重写错导致误放行）
##   · AI 确实指出了具体问题（不是空泛的"不错"）
##
## 真正的放行判定由 `python tools/art_final_gate.py` 负责，
## 它以退出码 1 阻断发布。

var _failures: Array[String] = []
var _checks := 0

const FINAL_PATH := "res://art/final_score.json"
const AI_PATH := "res://art/ai_score.json"
const NUM_PATH := "res://art/art_score.json"


func _init() -> void:
	print("── AI 美术门禁机制验证 ──")

	for p in [NUM_PATH, AI_PATH, FINAL_PATH]:
		var exists := FileAccess.file_exists(p)
		_check(exists, "存在 %s" % p.get_file(),
			   "缺文件，先跑对应的 python 脚本")

	if not FileAccess.file_exists(FINAL_PATH):
		_finish()
		return

	var d = _read_json(FINAL_PATH)
	if not (d is Dictionary):
		_check(false, "终审 JSON 可解析", "解析失败")
		_finish()
		return
	_check(true, "终审 JSON 可解析", "")

	# ── 三道门都要有明确结果 ──
	var gates = d.get("gates", {})
	_check(gates is Dictionary, "含三道门结果", "gates 缺失")
	if gates is Dictionary:
		for key in ["numeric", "ai", "final"]:
			_check(gates.has(key), "门「%s」有布尔结果" % key,
				   "缺 " + key)
		# 整体通过 = 三道门全过，不能有例外
		var all_gates: bool = bool(gates.get("numeric", false)) \
			and bool(gates.get("ai", false)) \
			and bool(gates.get("final", false))
		_check(bool(d.get("passed", false)) == all_gates,
			   "总判定与三道门一致（%s）" % str(all_gates),
			   "总判定 %s 与门结果 %s 不一致"
			   % [str(d.get("passed")), str(all_gates)])

	# ── 合并公式必须算得对 ──
	#
	# 这是最关键的一条：权重写错会导致**该拦的没拦住**。
	var num_min := float(d.get("numeric_min", 0.0))
	var ai_min := float(d.get("ai_min", 0.0))
	var weights = d.get("weights", {})
	if weights is Dictionary:
		var wn := float(weights.get("numeric", 0.0))
		var wa := float(weights.get("ai", 0.0))
		_check(absf(wn + wa - 1.0) < 0.01,
			   "数值/AI 权重和为 1（%.2f）" % (wn + wa),
			   "权重和 %.2f，合并分会失真" % (wn + wa))
		var expect := num_min * wn + ai_min * wa
		var actual := float(d.get("final", 0.0))
		_check(absf(expect - actual) < 0.15,
			   "合并分按公式算对（%.1f ≈ %.1f）" % [actual, expect],
			   "合并分 %.1f 与公式 %.1f 不符" % [actual, expect])
		# 合并分不能高于两者的最大值（否则说明算错了）
		_check(actual <= maxf(num_min, ai_min) + 0.15,
			   "合并分未超出两个输入的最大值",
			   "合并分 %.1f 高于 max(%.1f, %.1f)，公式有问题"
			   % [actual, num_min, ai_min])

	# ── 阈值必须是合理的正数 ──
	for key in ["numeric_threshold", "ai_threshold", "final_threshold"]:
		var v := float(d.get(key, -1.0))
		_check(v > 0.0 and v <= 100.0,
			   "%s 合理（%.0f）" % [key, v],
			   "%s = %.0f，超出 0~100" % [key, v])

	# ── AI 必须给出具体问题，不能空泛 ──
	var targets: Array = d.get("ai_targets", [])
	_check(targets.size() >= 2, "AI 评审了至少 2 张截图（%d 张）"
		   % targets.size(), "只有 %d 张" % targets.size())
	var with_issue := 0
	for t in targets:
		var issue := str(t.get("top_issue", "")).strip_edges()
		if issue.length() >= 10:
			with_issue += 1
	_check(with_issue == targets.size() and targets.size() > 0,
		   "每张截图都给出具体问题（%d/%d）" % [with_issue, targets.size()],
		   "有 %d 张没给出具体问题，AI 打分可能空泛"
		   % (targets.size() - with_issue))
	# 分数必须在合法范围
	for t in targets:
		var tot := float(t.get("total", -1.0))
		_check(tot >= 0.0 and tot <= 100.0,
			   "  %s 分数合法（%.0f）" % [t.get("label", "?"), tot],
			   "分数 %.0f 超出 0~100" % tot)

	_finish()


func _read_json(path: String):
	var f := FileAccess.open(path, FileAccess.READ)
	if f == null:
		return null
	var txt := f.get_as_text()
	f.close()
	return JSON.parse_string(txt)


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
