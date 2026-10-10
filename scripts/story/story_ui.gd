class_name StoryUI
extends CanvasLayer
## 剧情的界面：黑场转场、章节字幕、对白字幕（说话人 + 逐字出现）、心声、选项、纸面阅读、交互提示和准星点。
## 由 Story（自动加载）创建，跨场景一直在。字体是思源宋体（Noto Serif SC，SIL OFL）。

signal advanced
signal chosen(index: int)
signal reader_closed
signal reader_opened

const SERIF := "res://assets/fonts/NotoSerifSC-VF.ttf"
const INK := Color(0.9, 0.86, 0.78)
const NAME_COLOR := Color(0.72, 0.62, 0.48)
const THOUGHT := Color(0.66, 0.66, 0.64)
## 字幕逐字出现的速度（字/秒）；读完以后停多久自动翻下一句（还要加上按字数算的时间）
const TYPE_SPEED := 22.0
const HOLD := 1.1
const HOLD_PER_CHAR := 0.11

var _font: FontVariation
var _font_bold: FontVariation
var _fade: ColorRect
var _card: VBoxContainer
var _card_title: Label
var _card_sub: Label
var _line_box: VBoxContainer
var _name: Label
var _text: RichTextLabel
var _choice_box: VBoxContainer
var _choices: Array = []
var _choice_sel := 0
var _prompt: Label
var _dot: ColorRect
var _reader: Control
var _reader_tex: TextureRect
var _reader_hint: Label
var _reader_pages: Array = []
var _reader_page := 0

var _typing := 0.0      # 已经显示出来的字数（逐字）
var _line_len := 0
var _hold := 0.0        # 显示完以后还要停多久
var _waiting := false   # 正在等玩家看完这一句
var _choosing := false
var _reading := false


func _ready() -> void:
	layer = 50
	process_mode = Node.PROCESS_MODE_ALWAYS
	var base: Font = load(SERIF) if ResourceLoader.exists(SERIF) else SystemFont.new()
	_font = FontVariation.new()
	_font.base_font = base
	_font.variation_opentype = {"wght": 500}
	_font_bold = FontVariation.new()
	_font_bold.base_font = base
	_font_bold.variation_opentype = {"wght": 700}

	var root := Control.new()
	root.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(root)

	# 准星点：很小、很淡，对着能交互的东西时亮一点
	_dot = ColorRect.new()
	_dot.color = Color(1, 1, 1, 0.18)
	_dot.size = Vector2(4, 4)
	_dot.set_anchors_preset(Control.PRESET_CENTER)
	_dot.position = -_dot.size / 2
	_dot.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_dot.visible = false
	root.add_child(_dot)

	_prompt = _label(20, INK)
	_prompt.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_prompt.set_anchors_and_offsets_preset(Control.PRESET_CENTER_BOTTOM)
	_prompt.offset_left = -400
	_prompt.offset_right = 400
	_prompt.offset_top = -120
	_prompt.offset_bottom = -88
	root.add_child(_prompt)

	# 对白：屏幕下方居中，说话人一行、台词一行（可以折两行）
	_line_box = VBoxContainer.new()
	_line_box.set_anchors_and_offsets_preset(Control.PRESET_CENTER_BOTTOM)
	_line_box.offset_left = -620
	_line_box.offset_right = 620
	_line_box.offset_top = -250
	_line_box.offset_bottom = -90
	_line_box.alignment = BoxContainer.ALIGNMENT_END
	_line_box.add_theme_constant_override("separation", 6)
	_line_box.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root.add_child(_line_box)
	_choice_box = VBoxContainer.new()
	_choice_box.add_theme_constant_override("separation", 4)
	_choice_box.alignment = BoxContainer.ALIGNMENT_END
	_line_box.add_child(_choice_box)
	_name = _label(20, NAME_COLOR)
	_name.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_line_box.add_child(_name)
	_text = RichTextLabel.new()
	_text.bbcode_enabled = true
	_text.fit_content = true
	_text.scroll_active = false
	_text.autowrap_mode = TextServer.AUTOWRAP_ARBITRARY
	_text.add_theme_font_override("normal_font", _font)
	_text.add_theme_font_override("bold_font", _font_bold)
	_text.add_theme_font_size_override("normal_font_size", 27)
	_text.add_theme_font_size_override("bold_font_size", 27)
	_text.add_theme_color_override("default_color", INK)
	_text.add_theme_color_override("font_shadow_color", Color(0, 0, 0, 0.85))
	_text.add_theme_constant_override("shadow_offset_x", 0)
	_text.add_theme_constant_override("shadow_offset_y", 2)
	_text.add_theme_constant_override("shadow_outline_size", 6)
	_text.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_line_box.add_child(_text)
	_line_box.visible = false

	# 纸面阅读：压暗背景，纸放在中间
	_reader = Control.new()
	_reader.set_anchors_preset(Control.PRESET_FULL_RECT)
	_reader.visible = false
	root.add_child(_reader)
	var dim := ColorRect.new()
	dim.color = Color(0, 0, 0, 0.72)
	dim.set_anchors_preset(Control.PRESET_FULL_RECT)
	_reader.add_child(dim)
	_reader_tex = TextureRect.new()
	_reader_tex.set_anchors_preset(Control.PRESET_FULL_RECT)
	_reader_tex.offset_top = 40
	_reader_tex.offset_bottom = -70
	_reader_tex.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	_reader_tex.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	_reader.add_child(_reader_tex)
	_reader_hint = _label(18, Color(0.75, 0.72, 0.66))
	_reader_hint.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_reader_hint.set_anchors_and_offsets_preset(Control.PRESET_CENTER_BOTTOM)
	_reader_hint.offset_left = -400
	_reader_hint.offset_right = 400
	_reader_hint.offset_top = -56
	_reader_hint.offset_bottom = -24
	_reader.add_child(_reader_hint)

	# 章节字幕（黑场上）
	_card = VBoxContainer.new()
	_card.set_anchors_preset(Control.PRESET_FULL_RECT)
	_card.alignment = BoxContainer.ALIGNMENT_CENTER
	_card.add_theme_constant_override("separation", 18)
	_card.modulate.a = 0.0
	_card_title = _label(46, Color(0.86, 0.82, 0.74), _font_bold)
	_card_title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_card_sub = _label(22, Color(0.6, 0.57, 0.52))
	_card_sub.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_card.add_child(_card_title)
	_card.add_child(_card_sub)

	_fade = ColorRect.new()
	_fade.color = Color(0, 0, 0, 0)
	_fade.set_anchors_preset(Control.PRESET_FULL_RECT)
	_fade.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root.add_child(_fade)
	root.add_child(_card)
	if DebugArgs.has("no-hud") or DebugArgs.has("capture"):
		_prompt.visible = false
		_dot.modulate.a = 0.0


func _label(size: int, color: Color, font: Font = null) -> Label:
	var l := Label.new()
	l.add_theme_font_override("font", font if font else _font)
	l.add_theme_font_size_override("font_size", size)
	l.add_theme_color_override("font_color", color)
	l.add_theme_color_override("font_shadow_color", Color(0, 0, 0, 0.85))
	l.add_theme_constant_override("shadow_offset_y", 2)
	l.add_theme_constant_override("shadow_outline_size", 6)
	l.mouse_filter = Control.MOUSE_FILTER_IGNORE
	return l


# ----------------------------------------------------------------------------- 黑场、章节字幕
func fade_out(t := 1.0) -> void:
	var tw := create_tween()
	tw.tween_property(_fade, "color:a", 1.0, t)
	await tw.finished


func fade_in(t := 1.0) -> void:
	var tw := create_tween()
	tw.tween_property(_fade, "color:a", 0.0, t)
	await tw.finished


func set_black(on: bool) -> void:
	_fade.color.a = 1.0 if on else 0.0


func show_card(title: String, sub: String, hold := 2.6) -> void:
	_card_title.text = title
	_card_sub.text = sub
	var tw := create_tween()
	tw.tween_property(_card, "modulate:a", 1.0, 1.2)
	tw.tween_interval(hold)
	tw.tween_property(_card, "modulate:a", 0.0, 1.0)
	await tw.finished


# ----------------------------------------------------------------------------- 提示
func set_prompt(text: String, focused: bool, show_dot: bool) -> void:
	_prompt.text = text
	_dot.visible = show_dot and not _reading
	_dot.color.a = 0.55 if focused else 0.16


# ----------------------------------------------------------------------------- 对白
## 显示一句，等玩家看完（自动翻页或按 E / 空格 / 左键）
func show_line(who: String, text: String, thought: bool) -> void:
	_line_box.visible = true
	_choice_box.visible = false
	_name.text = who
	_name.visible = not who.is_empty()
	if thought:
		_text.text = "[center][color=#%s]%s[/color][/center]" % [THOUGHT.to_html(false), text]
	else:
		_text.text = "[center]%s[/center]" % text
	_line_len = text.length()
	_typing = 0.0
	_text.visible_characters = 0
	_hold = HOLD + HOLD_PER_CHAR * _line_len
	_waiting = true
	await advanced


func clear_line() -> void:
	_line_box.visible = false
	_waiting = false


## 列出选项，返回选中的下标
func choose(items: PackedStringArray) -> int:
	_line_box.visible = true
	_choice_box.visible = true
	for c in _choice_box.get_children():
		c.queue_free()
	_choices.clear()
	for i in items.size():
		var l := _label(24, INK)
		l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		l.text = "%d. %s" % [i + 1, items[i]]
		_choice_box.add_child(l)
		_choices.append(l)
	_choice_sel = 0
	_highlight()
	_choosing = true
	var idx: int = await chosen
	_choosing = false
	_choice_box.visible = false
	return idx


func _highlight() -> void:
	for i in _choices.size():
		var l: Label = _choices[i]
		l.add_theme_color_override("font_color", Color(1.0, 0.93, 0.78) if i == _choice_sel else Color(0.62, 0.6, 0.56))


# ----------------------------------------------------------------------------- 纸面
## pages：每页一张贴图（PaperDoc 的 SubViewport 贴图）。A / D 翻页，E / Esc 放下
func read(pages: Array, hint := "") -> void:
	_reader_pages = pages
	_reader_page = 0
	reader_opened.emit()
	_reader.visible = true
	_reading = true
	_dot.visible = false
	_show_page(hint)
	await reader_closed
	_reader.visible = false
	_reading = false


func _show_page(hint := "") -> void:
	var tex: Texture2D = _reader_pages[_reader_page]
	_reader_tex.texture = tex
	# 小纸片（传呼机的屏、名片）最多放大到原尺寸的 1.3 倍，不然一张名片铺满整个屏幕
	var vp := get_viewport().get_visible_rect().size
	var full := Vector2(vp.x, vp.y - 110.0)
	var want := Vector2(tex.get_size()) * 1.3
	var fit := minf(minf(full.x / want.x, full.y / want.y), 1.0)
	var sz := want * fit
	_reader_tex.set_anchors_preset(Control.PRESET_CENTER)
	_reader_tex.size = sz
	_reader_tex.position = Vector2((vp.x - sz.x) / 2.0, 40.0 + (full.y - sz.y) / 2.0)
	var n := _reader_pages.size()
	var h := "E 放下" if n == 1 else "A / D 翻页　第 %d / %d 页　E 放下" % [_reader_page + 1, n]
	_reader_hint.text = (hint + "　" if hint else "") + h


func is_reading() -> bool:
	return _reading


func is_choosing() -> bool:
	return _choosing


func choice_texts() -> PackedStringArray:
	var out := PackedStringArray()
	for l in _choices:
		out.append((l as Label).text)
	return out


## 替玩家选（自动演示用）
func pick(i: int) -> void:
	_choice_sel = i
	_highlight()
	chosen.emit(i)


# ----------------------------------------------------------------------------- 输入
func _process(delta: float) -> void:
	if not _waiting:
		return
	if _typing < _line_len:
		_typing = minf(_typing + delta * TYPE_SPEED, _line_len)
		_text.visible_characters = int(_typing)
		return
	_hold -= delta
	if _hold <= 0.0:
		_finish_line()


func _finish_line() -> void:
	_waiting = false
	advanced.emit()


func _input(event: InputEvent) -> void:
	if _reading:
		if event.is_action_pressed("interact") or event.is_action_pressed("release_mouse"):
			get_viewport().set_input_as_handled()
			reader_closed.emit()
		elif event.is_action_pressed("turn_left") and _reader_page > 0:
			_reader_page -= 1
			_show_page()
			reader_opened.emit()
		elif event.is_action_pressed("turn_right") and _reader_page < _reader_pages.size() - 1:
			_reader_page += 1
			_show_page()
			reader_opened.emit()
		return
	if _choosing:
		var pick := -1
		if event is InputEventKey and event.pressed and not event.echo:
			var k: int = event.physical_keycode
			if k >= KEY_1 and k <= KEY_9 and k - KEY_1 < _choices.size():
				pick = k - KEY_1
		if event.is_action_pressed("move_forward"):
			_choice_sel = posmod(_choice_sel - 1, _choices.size())
			_highlight()
		elif event.is_action_pressed("move_back"):
			_choice_sel = posmod(_choice_sel + 1, _choices.size())
			_highlight()
		elif event.is_action_pressed("interact") or (event is InputEventKey and event.pressed
				and event.physical_keycode in [KEY_ENTER, KEY_KP_ENTER, KEY_SPACE]):
			pick = _choice_sel
		if pick >= 0:
			get_viewport().set_input_as_handled()
			_choice_sel = pick
			_highlight()
			chosen.emit(pick)
		return
	if _waiting:
		var skip: bool = event.is_action_pressed("interact") or (event is InputEventKey and event.pressed
			and event.physical_keycode == KEY_SPACE) or (event is InputEventMouseButton and event.pressed
			and event.button_index == MOUSE_BUTTON_LEFT)
		if skip:
			get_viewport().set_input_as_handled()
			if _typing < _line_len:
				_typing = _line_len   # 先把这一句全显示出来
				_text.visible_characters = -1
				_hold = minf(_hold, 0.6 + 0.03 * _line_len)
			else:
				_finish_line()
