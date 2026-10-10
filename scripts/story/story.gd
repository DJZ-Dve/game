extends Node
## 剧情：剧情标记、转场（黑场 + 章节字幕）、播放对白文件。自动加载为 Story。
## 剧情设计见 docs/story.md；对白在 assets/story/*.dlg。
##
## 调试参数（`--` 之后）：
##   --scene=dorm|office|deep_sea   直接从这个场景开始（也可以给 res:// 路径）
##   --flags=a,b,c                  开场先设好这些剧情标记（跳过前面的流程）
##   --autoplay                     自动过剧情（录演示、查流程）：场景脚本自己走位，纸看一会儿就放下，
##                                  选项按 auto_choices 里的字挑（挑不到就选第一个）

## 说话：说话人、台词、大概要说多久（秒）。NPC 听这个对口型
signal line_started(who: String, text: String, duration: float)
signal line_finished(who: String)

const SCENES := {
	"dorm": "res://scenes/dorm.tscn",
	"office": "res://scenes/office.tscn",
	"deep_sea": "res://scenes/deep_sea.tscn",
}
## 普通话大约一秒四五个字
const SPEECH_RATE := 4.6

var flags := {}
var ui: StoryUI
## 对白、过场进行中（走动、交互都停下）
var busy := false

var _scripts := {}
## 自动演示时要选的选项（选项文字里含这几个字就选它，按顺序用掉）
var auto_choices: PackedStringArray = []
var _auto_t := 0.0


func _ready() -> void:
	ui = StoryUI.new()
	add_child(ui)
	for f in DebugArgs.get_arg("flags").split(",", false):
		flags[f] = true
	var start := DebugArgs.get_arg("scene")
	var path: String = SCENES.get(start, start)
	var main: String = ProjectSettings.get_setting("application/run/main_scene")
	if (SCENES.has(start) or start.begins_with("res://")) and path != main:
		get_tree().change_scene_to_file.call_deferred(path)


## 调试参数 --scene 要的是不是这个场景（没给 --scene 就是主场景，也算）。
## 主场景是宿舍：--scene 指向别的场景时，宿舍会先加载一下再被换掉，这期间别做开场演出、别烘焙
func is_target(key: String) -> bool:
	var s := DebugArgs.get_arg("scene")
	return s.is_empty() or s == key or SCENES.get(s, s) == SCENES.get(key, key)


func _process(delta: float) -> void:
	if not DebugArgs.has("autoplay"):
		return
	if ui.is_reading():
		_auto_t += delta
		if _auto_t > 2.8:
			_auto_t = 0.0
			ui.reader_closed.emit()
	elif ui.is_choosing():
		_auto_t += delta
		if _auto_t > 1.4:
			_auto_t = 0.0
			var texts := ui.choice_texts()
			var pick := 0
			if not auto_choices.is_empty():
				for i in texts.size():
					if texts[i].contains(auto_choices[0]):
						pick = i
						auto_choices.remove_at(0)
						break
			ui.pick(pick)
	else:
		_auto_t = 0.0


func flag(name: String) -> bool:
	return flags.get(name, false)


func set_flag(name: String, value := true) -> void:
	flags[name] = value


## 转场：黑场 →（章节字幕）→ 换场景 → 亮起来
func goto_scene(key: String, title := "", sub := "") -> void:
	busy = true
	await ui.fade_out(1.4)
	if not title.is_empty():
		await ui.show_card(title, sub)
	get_tree().change_scene_to_file(SCENES.get(key, key))
	ui.set_prompt("", false, false)
	ui.clear_line()
	for i in 3:
		await get_tree().process_frame
	busy = false
	await ui.fade_in(1.6)


## 几句心声（简单的查看用，不用写对白文件）
func monologue(lines: PackedStringArray) -> void:
	busy = true
	for s in lines:
		await say("", s)
	ui.clear_line()
	busy = false


func say(who: String, text: String) -> void:
	var thought := who.is_empty()
	var plain := text
	if not thought:
		line_started.emit(who, plain, maxf(0.8, plain.length() / SPEECH_RATE))
	await ui.show_line(who, text, thought)
	if not thought:
		line_finished.emit(who)


## 播放对白文件里的一段。handler 是场景脚本：`@命令` 交给它的 on_cmd(name, args)（可以是协程）
func run(path: String, label: String, handler: Object = null) -> void:
	var d := _load(path)
	var key := path.get_file().get_basename()
	var lbl := label
	var i := 0
	busy = true
	while d.sections.has(lbl):
		var sec: Array = d.sections[lbl]
		flags["dlg:%s:%s" % [key, lbl]] = true
		if i >= sec.size():
			break
		var e: Dictionary = sec[i]
		i += 1
		match e.t:
			"say":
				await say(e.who, e.text)
			"think":
				await say("", e.text)
			"choice":
				var items: Array = e.items.filter(func(c: Dictionary) -> bool:
					return c.keep or not flags.get("dlg:%s:%s" % [key, c.to], false))
				if items.is_empty():
					continue
				var texts := PackedStringArray(items.map(func(c: Dictionary) -> String: return c.text))
				var k := await ui.choose(texts)
				lbl = items[k].to
				i = 0
			"goto":
				lbl = e.to
				i = 0
			"if":
				if flag(e.flag) != e.neg:
					lbl = e.to
					i = 0
			"cmd":
				if e.name == "end":
					break
				elif e.name == "flag":
					for f in e.args:
						set_flag(f)
				elif handler and handler.has_method("on_cmd"):
					await handler.on_cmd(e.name, e.args)
	if not d.sections.has(lbl):
		push_error("%s 里没有标签 %s" % [path, lbl])
	ui.clear_line()
	busy = false


func visited(path: String, label: String) -> bool:
	return flags.get("dlg:%s:%s" % [path.get_file().get_basename(), label], false)


func _load(path: String) -> DialogueScript:
	if not _scripts.has(path):
		_scripts[path] = DialogueScript.load_file(path)
	return _scripts[path]
