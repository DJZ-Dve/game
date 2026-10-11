extends Control
## 大厅（主场景）：起名字 → 建房 / 加入 / 单人下潜 → 房间里挑岗位、主机开局。
## 以后大厅会搬进办事处（docs/design.md 第三节），现在先用一个界面顶着。
## 联机方式：局域网 / 直连 IP 能用；Steam、归墟服务器是占位（按钮灰着，见 net_backend.gd）。

const SERIF := "res://assets/fonts/NotoSerifSC-VF.ttf"
const PHOTO := "res://assets/textures/story/desk_photo.png"
const INK := Color(0.9, 0.86, 0.78)
const DIM := Color(0.62, 0.58, 0.5)
const ACCENT := Color(0.78, 0.36, 0.26)

var _font: FontVariation
var _font_bold: FontVariation
var _main: VBoxContainer
var _room: VBoxContainer
var _name_edit: LineEdit
var _addr_edit: LineEdit
var _status: Label
var _slots: VBoxContainer
var _roles: HBoxContainer
var _role_hint: Label
var _start: Button
var _room_info: Label


func _ready() -> void:
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	var base: Font = load(SERIF)
	_font = FontVariation.new()
	_font.base_font = base
	_font.variation_opentype = {"wght": 500}
	_font_bold = FontVariation.new()
	_font_bold.base_font = base
	_font_bold.variation_opentype = {"wght": 700}
	set_anchors_preset(Control.PRESET_FULL_RECT)
	theme = _make_theme()
	_build_background()
	var col := VBoxContainer.new()
	col.set_anchors_and_offsets_preset(Control.PRESET_LEFT_WIDE)
	col.offset_left = 120
	col.offset_right = 640
	col.alignment = BoxContainer.ALIGNMENT_CENTER
	col.add_theme_constant_override("separation", 10)
	add_child(col)
	col.add_child(_label("归 墟", 84, INK, true))
	col.add_child(_label("一九九八 · 白沙门 · 四人深海打捞", 20, DIM))
	col.add_child(_spacer(28))
	_main = _build_main()
	col.add_child(_main)
	_room = _build_room()
	col.add_child(_room)
	col.add_child(_spacer(12))
	_status = _label("", 17, ACCENT)
	_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_status.custom_minimum_size.x = 480
	col.add_child(_status)
	Net.roster_changed.connect(_refresh)
	Net.status.connect(func(t: String) -> void: _status.text = t)
	_status.text = Net.last_message
	Net.last_message = ""
	_refresh()


func _build_background() -> void:
	var bg := ColorRect.new()
	bg.color = Color(0.035, 0.034, 0.03)
	bg.set_anchors_preset(Control.PRESET_FULL_RECT)
	add_child(bg)
	if ResourceLoader.exists(PHOTO):
		var photo := TextureRect.new()
		photo.texture = load(PHOTO)
		photo.set_anchors_preset(Control.PRESET_FULL_RECT)
		photo.anchor_left = 0.38
		photo.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		photo.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
		photo.modulate = Color(0.55, 0.52, 0.46)
		add_child(photo)
	# 照片左边压暗，文字压在暗处
	var grad := Gradient.new()
	grad.set_color(0, Color(0.035, 0.034, 0.03, 1.0))
	grad.set_color(1, Color(0.035, 0.034, 0.03, 0.0))
	var tex := GradientTexture2D.new()
	tex.gradient = grad
	tex.fill_from = Vector2(0.0, 0.5)
	tex.fill_to = Vector2(1.0, 0.5)
	var shade := TextureRect.new()
	shade.texture = tex
	shade.set_anchors_preset(Control.PRESET_FULL_RECT)
	shade.anchor_left = 0.38
	shade.anchor_right = 0.75
	shade.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	shade.stretch_mode = TextureRect.STRETCH_SCALE
	add_child(shade)


# ---------------------------------------------------------------------------- 首页
func _build_main() -> VBoxContainer:
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 10)
	box.add_child(_label("你的名字", 16, DIM))
	_name_edit = LineEdit.new()
	_name_edit.text = Net.local_name
	_name_edit.max_length = 16
	_name_edit.custom_minimum_size = Vector2(360, 44)
	_name_edit.text_changed.connect(func(t: String) -> void: Net.set_local_name(t))
	box.add_child(_name_edit)
	box.add_child(_spacer(10))

	box.add_child(_label("局域网 / 直连 IP", 16, DIM))
	var host_row := HBoxContainer.new()
	host_row.add_theme_constant_override("separation", 10)
	host_row.add_child(_button("建房", func() -> void: Net.host_game("enet")))
	box.add_child(host_row)
	var join_row := HBoxContainer.new()
	join_row.add_theme_constant_override("separation", 10)
	_addr_edit = LineEdit.new()
	_addr_edit.placeholder_text = "主机的 IP（例如 192.168.1.23）"
	_addr_edit.text = "127.0.0.1"
	_addr_edit.custom_minimum_size = Vector2(360, 44)
	_addr_edit.text_submitted.connect(func(_t: String) -> void: _join())
	join_row.add_child(_addr_edit)
	join_row.add_child(_button("加入", _join))
	box.add_child(join_row)
	box.add_child(_spacer(6))

	for kind: String in ["steam", "server"]:
		var be: NetBackend = Net.backends[kind]
		var b := _button(be.title, func() -> void: pass)
		b.disabled = not be.available()
		b.tooltip_text = be.unavailable_reason()
		var row := HBoxContainer.new()
		row.add_theme_constant_override("separation", 12)
		row.add_child(b)
		row.add_child(_label(be.unavailable_reason(), 15, DIM.darkened(0.25)))
		box.add_child(row)
	box.add_child(_spacer(14))
	var solo_row := HBoxContainer.new()
	solo_row.add_theme_constant_override("separation", 10)
	solo_row.add_child(_button("单人下潜", func() -> void: Net.start_solo()))
	solo_row.add_child(_button("旧版剧情（单人）", func() -> void: Story.goto_scene("dorm")))
	solo_row.add_child(_button("退出", func() -> void: get_tree().quit()))
	box.add_child(solo_row)
	return box


func _join() -> void:
	Net.join_game("enet", _addr_edit.text)


# ---------------------------------------------------------------------------- 房间
func _build_room() -> VBoxContainer:
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 10)
	_room_info = _label("", 16, DIM)
	_room_info.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_room_info.custom_minimum_size.x = 480
	box.add_child(_room_info)
	box.add_child(_spacer(4))
	_slots = VBoxContainer.new()
	_slots.add_theme_constant_override("separation", 6)
	box.add_child(_slots)
	box.add_child(_spacer(10))
	box.add_child(_label("你的岗位（不锁死，谁都能操作任何位置）", 16, DIM))
	_roles = HBoxContainer.new()
	_roles.add_theme_constant_override("separation", 8)
	for r in Net.ROLE_NAMES.size():
		var b := _button(Net.ROLE_NAMES[r], func() -> void: Net.set_role(r))
		b.toggle_mode = true
		b.custom_minimum_size.x = 104
		_roles.add_child(b)
	box.add_child(_roles)
	_role_hint = _label("", 15, DIM)
	box.add_child(_role_hint)
	box.add_child(_spacer(14))
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 10)
	_start = _button("开始下潜", func() -> void: Net.start_game())
	row.add_child(_start)
	row.add_child(_button("离开房间", func() -> void: Net.leave()))
	box.add_child(row)
	return box


func _refresh() -> void:
	var in_room := Net.is_online() or Net.connecting
	_main.visible = not in_room
	_room.visible = in_room
	if not in_room:
		return
	for c in _slots.get_children():
		c.queue_free()
	var ids := Net.players.keys()
	ids.sort()
	for i in Net.MAX_PLAYERS:
		var text := "—— 空位 ——"
		var color := DIM.darkened(0.35)
		if i < ids.size():
			var id: int = ids[i]
			text = "%s　%s%s%s" % [Net.ROLE_NAMES[Net.role_of(id)], Net.player_name(id),
				"　（主机）" if id == 1 else "", "　← 你" if id == Net.my_id() else ""]
			color = INK
		_slots.add_child(_label(text, 20, color))
	var my_role := Net.role_of(Net.my_id()) if Net.players.has(Net.my_id()) else -1
	for r in _roles.get_child_count():
		(_roles.get_child(r) as Button).set_pressed_no_signal(r == my_role)
		(_roles.get_child(r) as Button).disabled = Net.connecting
	_role_hint.text = Net.ROLE_HINTS[my_role] if my_role >= 0 else ""
	_start.visible = Net.is_host()
	if Net.connecting:
		_room_info.text = "正在连接……"
	elif Net.is_host():
		var addrs := NetBackend.ENetBackend.lan_addresses()
		_room_info.text = "房间开好了。让同一个局域网里的人在“加入”里填：%s（端口 %d）" % [
			"、".join(addrs) if not addrs.is_empty() else "本机 IP", NetBackend.ENetBackend.DEFAULT_PORT]
	else:
		_room_info.text = "等主机开局"


# ---------------------------------------------------------------------------- 小零件
func _label(text: String, size: int, color: Color, bold := false) -> Label:
	var l := Label.new()
	l.text = text
	l.add_theme_font_override("font", _font_bold if bold else _font)
	l.add_theme_font_size_override("font_size", size)
	l.add_theme_color_override("font_color", color)
	return l


func _button(text: String, cb: Callable) -> Button:
	var b := Button.new()
	b.text = text
	b.custom_minimum_size = Vector2(120, 44)
	b.pressed.connect(cb)
	return b


func _spacer(h: float) -> Control:
	var c := Control.new()
	c.custom_minimum_size.y = h
	return c


func _make_theme() -> Theme:
	var t := Theme.new()
	t.default_font = _font
	t.default_font_size = 18
	var normal := StyleBoxFlat.new()
	normal.bg_color = Color(0.09, 0.085, 0.075, 0.9)
	normal.border_color = Color(0.45, 0.38, 0.28, 0.7)
	normal.set_border_width_all(1)
	normal.set_content_margin_all(10)
	var hover := normal.duplicate() as StyleBoxFlat
	hover.bg_color = Color(0.16, 0.14, 0.11, 0.95)
	hover.border_color = Color(0.75, 0.62, 0.42)
	var pressed := normal.duplicate() as StyleBoxFlat
	pressed.bg_color = Color(0.32, 0.14, 0.1, 0.95)
	pressed.border_color = ACCENT
	var disabled := normal.duplicate() as StyleBoxFlat
	disabled.bg_color = Color(0.06, 0.06, 0.055, 0.7)
	disabled.border_color = Color(0.25, 0.23, 0.2, 0.6)
	for k in ["normal", "focus"]:
		t.set_stylebox(k, "Button", normal)
	t.set_stylebox("hover", "Button", hover)
	t.set_stylebox("pressed", "Button", pressed)
	t.set_stylebox("hover_pressed", "Button", pressed)
	t.set_stylebox("disabled", "Button", disabled)
	t.set_color("font_color", "Button", INK)
	t.set_color("font_hover_color", "Button", Color(1, 0.95, 0.85))
	t.set_color("font_pressed_color", "Button", Color(1, 0.92, 0.85))
	t.set_color("font_hover_pressed_color", "Button", Color(1, 0.92, 0.85))
	t.set_color("font_disabled_color", "Button", Color(0.42, 0.4, 0.36))
	var edit := normal.duplicate() as StyleBoxFlat
	edit.bg_color = Color(0.05, 0.05, 0.045, 0.95)
	t.set_stylebox("normal", "LineEdit", edit)
	t.set_stylebox("focus", "LineEdit", hover)
	t.set_color("font_color", "LineEdit", INK)
	t.set_color("font_placeholder_color", "LineEdit", Color(0.45, 0.42, 0.37))
	t.set_color("caret_color", "LineEdit", INK)
	return t
