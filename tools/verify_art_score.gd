extends SceneTree
## 美术评分门禁：读 art/art_score.json，确认全部资产过线
##
## 运行：godot --headless --path . --script tools/verify_art_score.gd
##
## ## 为什么这是一道"门"
##
## 这份测试不测代码逻辑，测的是**美术是否达标**。
## 流程是：
##   1. python tools/art_review.py     ← 用成熟参考素材的指标区间打分
##   2. 本脚本读它输出的 JSON，确认 passed == true
##
## 任何一次提交如果让美术退步到门槛以下，这条测试就会红。

var _failures: Array[String] = []
var _checks := 0

const SCORE_PATH := "res://art/art_score.json"


func _init() -> void:
	print("── 美术评分门禁 ──")

	if not FileAccess.file_exists(SCORE_PATH):
		_check(false, "美术评分报告存在", "缺 art/art_score.json，先跑 "
			   + "python tools/art_review.py")
		_finish()
		return
	_check(true, "美术评分报告存在", "")

	var f := FileAccess.open(SCORE_PATH, FileAccess.READ)
	var data = JSON.parse_string(f.get_as_text()) if f else null
	if f:
		f.close()
	_check(data is Dictionary, "评分报告可解析", "JSON 解析失败")
	if not (data is Dictionary):
		_finish()
		return

	var threshold := float(data.get("pass_score", 70.0))
	var min_score := float(data.get("min_score", 0.0))
	var passed := bool(data.get("passed", false))
	var items: Array = data.get("items", [])

	_check(items.size() >= 5, "评分覆盖至少 5 项资产（%d 项）" % items.size(),
		   "只有 %d 项，覆盖不足" % items.size())

	# ── 核心断言：全部门槛 ──
	_check(passed,
		   "全部资产过线（最低 %.1f ≥ %.0f）" % [min_score, threshold],
		   "未通过：%s" % str(data.get("failed", [])))

	# ── 逐项列出，便于定位是哪个资产拖后腿 ──
	for it in items:
		var label := str(it.get("label", "?"))
		var score := float(it.get("score", 0.0))
		_check(score >= threshold,
			   "  %s：%.1f 分" % [label, score],
			   "%s 只有 %.1f 分，低于门槛 %.0f" % [label, score, threshold])

	# ── 参考基准必须来自真实素材 ──
	#
	# 阈值必须由参考素材反推，不能是拍脑袋的数字。
	# 这里检查 JSON 里确实带了参考区间，且区间有效（min < max）。
	var refs = data.get("reference_range", null)
	_check(refs is Dictionary, "携带参考素材基准", "reference_range 缺失")
	if refs is Dictionary:
		var files: Array = refs.get("files", [])
		_check(files.size() >= 3,
			   "参考素材至少 3 份（%d 份）" % files.size(),
			   "只有 %d 份，基准不可信" % files.size())
		var colors_ref = refs.get("colors", {})
		if colors_ref is Dictionary:
			var cmin := float(colors_ref.get("min", 0))
			var cmax := float(colors_ref.get("max", 0))
			_check(cmax > cmin,
				   "参考区间有效（用色 %.0f~%.0f）" % [cmin, cmax],
				   "参考区间无效：%.0f~%.0f" % [cmin, cmax])

	# ── 权重和必须为 1 ──
	var weights = data.get("weights", {})
	if weights is Dictionary:
		var wsum := 0.0
		for k in weights:
			wsum += float(weights[k])
		_check(absf(wsum - 1.0) < 0.01,
			   "各维度权重和为 1（%.2f）" % wsum,
			   "权重和为 %.2f，总分会失真" % wsum)

	_finish()


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
