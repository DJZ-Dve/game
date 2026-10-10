class_name DialogueScript
extends RefCounted
## 对白文件（assets/story/*.dlg）解析成一段段的条目。格式（详见 docs/story.md 末尾）：
##   # 标签                一段的开始
##   沈渡：台词            某人说话（全角或半角冒号）
##   （心声）              主角心里话
##   * 选项 -> 标签        一次性选项（选过就不再出现）；连着几行是一组
##   + 选项 -> 标签        常驻选项（一直在）
##   -> 标签               跳到另一段
##   ?标记 -> 标签         剧情标记已设置时跳转；?!标记 -> 标签 是没设置时跳转
##   @命令 参数 ...        交给场景脚本（@end、@flag 由 Story 自己处理）
##   // 注释
## 条目是字典：{t = "say"/"think"/"choice"/"goto"/"if"/"cmd", ...}

## 名字最多几个字（冒号前面太长的就不当说话人，免得把带冒号的句子拆错）
const MAX_NAME := 6

var path := ""
var sections := {}  # 标签 -> Array[Dictionary]
var order: PackedStringArray = []


static func load_file(p: String) -> DialogueScript:
	var d := DialogueScript.new()
	d.path = p
	var f := FileAccess.open(p, FileAccess.READ)
	if f == null:
		push_error("对白文件打不开: " + p)
		return d
	d._parse(f.get_as_text())
	return d


func _parse(text: String) -> void:
	var cur: Array = []
	var label := ""
	var n := 0
	for raw in text.split("\n"):
		n += 1
		var s := raw.strip_edges()
		if s.is_empty() or s.begins_with("//"):
			continue
		if s.begins_with("#"):
			label = s.substr(1).strip_edges()
			cur = []
			sections[label] = cur
			order.append(label)
			continue
		if label.is_empty():
			push_warning("%s:%d 在第一个标签之前，忽略" % [path, n])
			continue
		var e := _entry(s)
		if e.is_empty():
			push_warning("%s:%d 看不懂：%s" % [path, n, s])
			continue
		# 连着的选项并成一组
		if e.t == "choice" and not cur.is_empty() and cur[-1].t == "choice":
			cur[-1].items.append_array(e.items)
		else:
			cur.append(e)


func _entry(s: String) -> Dictionary:
	if s.begins_with("*") or s.begins_with("+"):
		var parts := s.substr(1).split("->", true, 1)
		if parts.size() < 2:
			return {}
		return {t = "choice", items = [{text = parts[0].strip_edges(), to = parts[1].strip_edges(),
			keep = s.begins_with("+")}]}
	if s.begins_with("->"):
		return {t = "goto", to = s.substr(2).strip_edges()}
	if s.begins_with("?"):
		var parts := s.substr(1).split("->", true, 1)
		if parts.size() < 2:
			return {}
		var fl := parts[0].strip_edges()
		var neg := fl.begins_with("!")
		return {t = "if", flag = fl.trim_prefix("!"), neg = neg, to = parts[1].strip_edges()}
	if s.begins_with("@"):
		var words := s.substr(1).split(" ", false)
		return {t = "cmd", name = words[0], args = words.slice(1)}
	if s.begins_with("（") or s.begins_with("("):
		return {t = "think", text = s}
	for sep in ["：", ":"]:
		var i := s.find(sep)
		if i > 0 and i <= MAX_NAME:
			return {t = "say", who = s.substr(0, i).strip_edges(), text = s.substr(i + 1).strip_edges()}
	# 没有说话人的就当旁白（和心声一样显示）
	return {t = "think", text = s}
