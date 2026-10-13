extends Node3D
## 捏脸（大厅里点「捏脸」进来，scenes/character_creator.tscn）：左边性别、预设、随机；右边分页的滑杆
## （脸型、眼睛、鼻子、嘴、头、肤色、眉眼、妆容）；中间是自己的船员，拖动转身、滚轮拉近拉远，下面切正脸 / 侧脸 / 全身。
## 保存写进 settings.cfg（Net.set_local_look），在房间里的话主机那边跟着变；样子的数据见 crew_look.gd。
## 灯是柔光棚：左前上方暖色主光（软阴影）、右前方冷色补光、身后右上方轮廓光，背景深灰。
## 调试：--cc-preset=N 开场用第几个预设，--cc-view=face|side|body|back|eye，--cc-yaw=度（人转多少），--cc-ui=off 截图不要界面，
##       --cc-shots=0,1,2|all 批量拍预设（见 _shots），--cc-set=形态:值,形态:值 再改几个形态 / 参数（调预设用），--cc-hide=材质名,… 把这几个材质的面藏起来（查眼睛）
##       --cc-tressfx 试 TressFX 发丝（见 scripts/tools/tressfx_try.gd），--cc-gpu 打印渲染时间（见 _measure_gpu）

const CREW_BODY := preload("res://scripts/crew_body.gd")
const TFX_TRY := preload("res://scripts/tools/tressfx_try.gd")
const LOBBY := "res://scenes/lobby.tscn"
const SERIF := "res://assets/fonts/NotoSerifSC-VF.ttf"
const INK := Color(0.9, 0.86, 0.78)
const DIM := Color(0.62, 0.58, 0.5)
const ACCENT := Color(0.78, 0.36, 0.26)
## 机位：[看向哪（脸在 (0, 1.6, 0)，朝 +Z）, 距离, 竖直视角, 绕着转的角度]
const VIEWS := {
	"face": [Vector3(0.0, 1.585, 0.0), 0.62, 26.0, 0.0],
	"side": [Vector3(0.0, 1.585, -0.02), 0.62, 26.0, 38.0],
	"body": [Vector3(0.0, 0.98, 0.0), 3.3, 32.0, 0.0],
	"back": [Vector3(0.0, 1.6, -0.05), 0.7, 26.0, 160.0],
	"eye": [Vector3(0.032, 1.618, 0.0), 0.16, 26.0, 12.0],
}
## 分页：[名字, 滑杆的分组（crew_look.gd 的 SLIDERS 第一项）或者特殊页]
const TABS := [["脸型", "脸型"], ["眼睛", "眼睛"], ["鼻子", "鼻子"], ["嘴", "嘴"], ["头", "头"], ["肤色", "#skin"],
	["发型眉眼", "#brow"], ["妆容", "#makeup"]]

var look := {}
var _body: Node3D
var _stand: Stand
var _cam: Camera3D
var _view := "face"
var _orbit := 0.0
var _dist := 0.62
var _target := Vector3.ZERO
var _fov := 26.0
var _drag := false
var _rng := RandomNumberGenerator.new()
var _font: FontVariation
var _ui: Control
var _rows := {}           # 滑杆的键 → HSlider（换预设时刷新）
var _swatches := {}       # 色块那几项的键 → 按钮数组
var _sex_buttons := {}
var _beard_row: Control


func _ready() -> void:
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	if DebugArgs.has("cc-nolod"):
		get_viewport().mesh_lod_threshold = 0.0
	_rng.randomize()
	look = CrewLook.sanitize(Net.local_look)
	if DebugArgs.has("cc-preset"):
		look = CrewLook.preset(int(DebugArgs.get_arg("cc-preset")))
	if DebugArgs.has("cc-set"):
		for kv: String in DebugArgs.get_arg("cc-set").split(","):
			var p := kv.split(":")
			if p.size() == 2:
				if CrewLook.PARAMS.has(p[0]) or CrewLook.INDICES.has(p[0]):
					look[p[0]] = float(p[1]) if CrewLook.PARAMS.has(p[0]) else int(p[1])
				else:
					look.shape[p[0]] = float(p[1])
		look = CrewLook.sanitize(look)
	_build_stage()
	_spawn_body()
	_build_ui()
	_set_view(DebugArgs.get_arg("cc-view", "face"))
	if DebugArgs.has("cc-yaw"):
		_stand.turn = deg_to_rad(float(DebugArgs.get_arg("cc-yaw")))
	if DebugArgs.get_arg("cc-ui", "on") == "off":
		_ui.visible = false
	if DebugArgs.has("cc-shots"):
		_shots.call_deferred()
	if DebugArgs.has("cc-gpu"):
		_measure_gpu.call_deferred()


## 调试：--cc-gpu 打印第 150~230 帧平均的 GPU、CPU 渲染时间（比较加不加 TressFX 发丝；截图配 --wait=240，
## 不然第 150 帧就截完退出了）
func _measure_gpu() -> void:
	var vp := get_viewport().get_viewport_rid()
	RenderingServer.viewport_set_measure_render_time(vp, true)
	for _f in 150:
		await get_tree().process_frame
	var gpu := 0.0
	var cpu := 0.0
	var t0 := Time.get_ticks_usec()
	for _f in 80:
		await get_tree().process_frame
		gpu += RenderingServer.viewport_get_measured_render_time_gpu(vp)
		cpu += RenderingServer.viewport_get_measured_render_time_cpu(vp)
	var size := get_viewport().get_visible_rect().size
	print("CC 渲染时间（%d×%d）：GPU %.2f ms，CPU %.2f ms，一帧 %.2f ms" % [size.x, size.y, gpu / 80.0, cpu / 80.0,
		(Time.get_ticks_usec() - t0) / 1000.0 / 80.0])


## 调试：--cc-shots=0,1,2（或 all）挨个用这几个预设，每个拍正脸、侧脸两张，存到 --cc-out 目录（默认 .tmp/faces），拍完退出。
## 配 tools/face_sheet.py 拼成一张对比图
func _shots() -> void:
	_ui.visible = false
	var arg := DebugArgs.get_arg("cc-shots")
	var ids := []
	if arg == "all":
		ids = range(CrewLook.PRESETS.size())
	else:
		for x in arg.split(","):
			ids.append(int(x))
	var dir := DebugArgs.get_arg("cc-out", ProjectSettings.globalize_path("res://.tmp/faces"))
	DirAccess.make_dir_recursive_absolute(dir)
	for i: int in ids:
		var sex: String = look.sex
		look = CrewLook.preset(i)
		if look.sex != sex:
			_spawn_body()
		else:
			_apply()
		for v in ["face", "side"]:
			_view = v
			_dist = VIEWS[v][1]
			_target = VIEWS[v][0]
			_fov = VIEWS[v][2]
			_orbit = deg_to_rad(VIEWS[v][3])
			for _f in 30:
				await get_tree().process_frame
			var img := get_viewport().get_texture().get_image()
			img.save_png("%s/%02d_%s.png" % [dir, i, v])
		print("shot preset ", i, " ", CrewLook.PRESETS[i].name)
	get_tree().quit()


# ---------------------------------------------------------------------------- 舞台
func _build_stage() -> void:
	var env := Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color(0.045, 0.045, 0.05)
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color(0.32, 0.33, 0.36)
	env.ambient_light_energy = 0.35 if not DebugArgs.has("cc-noamb") else 0.0
	env.reflected_light_source = Environment.REFLECTION_SOURCE_BG
	env.tonemap_mode = Environment.TONE_MAPPER_AGX
	env.tonemap_exposure = 1.0
	env.ssao_enabled = true
	env.ssao_radius = 0.25
	env.ssao_intensity = 1.2
	# 不开辉光：眼神光（角膜上的高光）亮度峰值很高，辉光一晕开整只眼睛蒙一层白雾
	env.glow_enabled = false
	var we := WorldEnvironment.new()
	we.environment = env
	add_child(we)
	# 背景：人身后两米一块很大的深灰板，中间稍亮（布光的背景光）
	var bg := MeshInstance3D.new()
	var quad := QuadMesh.new()
	quad.size = Vector2(12, 8)
	bg.mesh = quad
	bg.position = Vector3(0, 1.5, -2.2)
	var bgm := StandardMaterial3D.new()
	bgm.albedo_color = Color(0.11, 0.11, 0.115)
	bgm.roughness = 1.0
	bg.material_override = bgm
	add_child(bg)
	var floor_mi := MeshInstance3D.new()
	var plane := PlaneMesh.new()
	plane.size = Vector2(12, 12)
	floor_mi.mesh = plane
	var fm := StandardMaterial3D.new()
	fm.albedo_color = Color(0.08, 0.08, 0.085)
	fm.roughness = 0.9
	floor_mi.material_override = fm
	add_child(floor_mi)
	# 主光：左前上方，暖白，软阴影
	var key := SpotLight3D.new()
	key.light_color = Color(1.0, 0.94, 0.86)
	key.light_energy = 7.0
	key.spot_range = 6.0
	key.spot_angle = 32.0
	key.spot_angle_attenuation = 0.6
	key.light_size = 0.35
	key.shadow_enabled = true
	key.shadow_blur = 1.5
	_aim(key, Vector3(1.3, 2.55, 1.25), Vector3(0, 1.5, 0))
	add_child(key)
	# 补光：右前方，冷一点，没有影子
	var fill := OmniLight3D.new()
	fill.light_color = Color(0.82, 0.88, 1.0)
	fill.light_energy = 0.55
	fill.omni_range = 6.0
	fill.position = Vector3(-1.6, 1.7, 1.6)
	add_child(fill)
	# 轮廓光：身后右上方
	var rim := SpotLight3D.new()
	rim.light_color = Color(0.95, 0.97, 1.0)
	rim.light_energy = 5.0
	rim.spot_range = 6.0
	rim.spot_angle = 30.0
	rim.light_size = 0.2
	_aim(rim, Vector3(-1.2, 2.4, -1.6), Vector3(0, 1.55, 0))
	add_child(rim)
	# 背景光：照在背景板上一团
	var bgl := SpotLight3D.new()
	bgl.light_energy = 2.5
	bgl.spot_range = 5.0
	bgl.spot_angle = 40.0
	bgl.light_color = Color(0.6, 0.66, 0.75)
	_aim(bgl, Vector3(0.0, 0.6, -0.6), Vector3(0, 1.6, -2.2))
	add_child(bgl)
	_cam = Camera3D.new()
	_cam.near = 0.02
	add_child(_cam)
	_cam.make_current()


func _aim(n: Node3D, from: Vector3, to: Vector3) -> void:
	n.position = from
	n.look_at_from_position(from, to, Vector3.UP)


func _spawn_body() -> void:
	if _body:
		_body.queue_free()
	if _stand == null:
		_stand = Stand.new()
		_stand.position = Vector3(0, 1.62, 0)
		add_child(_stand)
	_body = CREW_BODY.new()
	_body.first_person = false
	_body.look = look
	_body.camera_path = _stand.get_path()
	add_child(_body)
	if DebugArgs.has("cc-tressfx"):
		# 调试：试 TressFX 发丝（见 scripts/tools/tressfx_try.gd）
		var tfx: Node3D = TFX_TRY.new()
		tfx.body = _body
		tfx.look = look
		_body.add_child(tfx)
	if DebugArgs.has("cc-dump"):
		await get_tree().process_frame
		for mi in CrewLook.head_meshes(_body):
			var names := []
			for i in mi.get_blend_shape_count():
				var nm: String = mi.mesh.get("blend_shape/names")[i] if false else str(mi.find_blend_shape_by_name(&"ID_Jaw_Width"))
				break
			print("CC ", mi.name, " blend shapes ", mi.get_blend_shape_count(), " ID_Jaw_Width idx ",
				mi.find_blend_shape_by_name(&"ID_Jaw_Width"), " value ",
				mi.get_blend_shape_value(maxi(mi.find_blend_shape_by_name(&"ID_Jaw_Width"), 0)) if mi.get_blend_shape_count() else 0.0,
				" mesh blend shapes ", (mi.mesh as ArrayMesh).get_blend_shape_count() if mi.mesh is ArrayMesh else -1,
				" first ", (mi.mesh as ArrayMesh).get_blend_shape_name(0) if mi.mesh is ArrayMesh and (mi.mesh as ArrayMesh).get_blend_shape_count() else "")
		for mi in CrewLook.head_meshes(_body):
			for i in mi.mesh.get_surface_count():
				var m := mi.mesh.surface_get_material(i)
				var o := mi.get_surface_override_material(i)
				print("CC ", mi.name, " ", i, " ", m.resource_name if m else "-", " -> ", o.get_class() if o else "-",
					" ", (o as ShaderMaterial).shader.resource_path if o is ShaderMaterial else "")
	if DebugArgs.has("cc-hide"):
		# 调试：把这几个材质的面藏起来（查眼睛哪一层出问题）
		var hide := DebugArgs.get_arg("cc-hide").split(",")
		var none := StandardMaterial3D.new()
		none.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		none.albedo_color = Color(0, 0, 0, 0)
		for mi in CrewLook.head_meshes(_body):
			for i in mi.mesh.get_surface_count():
				var m := mi.mesh.surface_get_material(i)
				if m and m.resource_name in hide:
					mi.set_surface_override_material(i, none)


func _process(delta: float) -> void:
	var k := 1.0 - exp(-delta * 6.0)
	var want: Array = VIEWS[_view]
	_target = _target.lerp(want[0], k)
	_fov = lerpf(_fov, want[2], k)
	_orbit = lerp_angle(_orbit, deg_to_rad(want[3]), k)
	var dir := Vector3(sin(_orbit), 0.06, cos(_orbit)).normalized()
	_cam.position = _target + dir * _dist
	_cam.look_at(_target, Vector3.UP)
	_cam.fov = _fov


func _set_view(v: String) -> void:
	if not VIEWS.has(v):
		v = "face"
	_view = v
	_dist = VIEWS[v][1]
	if _target == Vector3.ZERO:
		_target = VIEWS[v][0]
		_fov = VIEWS[v][2]
		_orbit = deg_to_rad(VIEWS[v][3])


func _unhandled_input(e: InputEvent) -> void:
	if e is InputEventMouseButton:
		var mb := e as InputEventMouseButton
		if mb.button_index == MOUSE_BUTTON_LEFT:
			_drag = mb.pressed
		elif mb.pressed and mb.button_index == MOUSE_BUTTON_WHEEL_UP:
			_dist = maxf(_dist * 0.9, 0.35)
		elif mb.pressed and mb.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			_dist = minf(_dist * 1.1, 4.5)
	elif e is InputEventMouseMotion and _drag:
		_stand.turn += (e as InputEventMouseMotion).relative.x * 0.01
	elif e.is_action_pressed("ui_cancel"):
		_leave(false)


# ---------------------------------------------------------------------------- 改样子
func _apply() -> void:
	look = CrewLook.sanitize(look)
	if _body:
		_body.set_look(look)


func _set_sex(sex: String) -> void:
	if look.sex == sex:
		return
	# 换性别：换成那个性别第一个预设的样子（男女的脸型差得多，沿用滑杆的值不好看）
	for i in CrewLook.PRESETS.size():
		if CrewLook.PRESETS[i].sex == sex:
			look = CrewLook.preset(i)
			break
	_spawn_body()
	_refresh()


func _use_preset(i: int) -> void:
	var sex: String = look.sex
	look = CrewLook.preset(i)
	if look.sex != sex:
		_spawn_body()
	else:
		_apply()
	_refresh()


func _randomize() -> void:
	look = CrewLook.random_look(look.sex, _rng)
	_apply()
	_refresh()


func _leave(save: bool) -> void:
	if save:
		Net.set_local_look(look)
	get_tree().change_scene_to_file(LOBBY)


# ---------------------------------------------------------------------------- 界面
func _build_ui() -> void:
	var layer := CanvasLayer.new()
	add_child(layer)
	_font = FontVariation.new()
	_font.base_font = load(SERIF)
	_font.variation_opentype = {"wght": 500}
	_ui = Control.new()
	_ui.set_anchors_preset(Control.PRESET_FULL_RECT)
	_ui.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_ui.theme = _make_theme()
	layer.add_child(_ui)

	# 左边：标题、性别、预设、随机
	var left := _panel(Vector2(60, 70), Vector2(300, 0))
	left.anchor_bottom = 1.0
	left.offset_bottom = -70
	var lbox := VBoxContainer.new()
	lbox.add_theme_constant_override("separation", 10)
	left.add_child(lbox)
	lbox.add_child(_label("捏 脸", 40, INK))
	lbox.add_child(_label("船员档案 · 外貌", 16, DIM))
	lbox.add_child(_spacer(8))
	var sex_row := HBoxContainer.new()
	sex_row.add_theme_constant_override("separation", 8)
	for s: Array in [["m", "男"], ["f", "女"]]:
		var b := _button(s[1], func() -> void: _set_sex(s[0]))
		b.toggle_mode = true
		b.custom_minimum_size.x = 100
		_sex_buttons[s[0]] = b
		sex_row.add_child(b)
	lbox.add_child(sex_row)
	lbox.add_child(_spacer(6))
	lbox.add_child(_label("预设", 16, DIM))
	var grid := GridContainer.new()
	grid.columns = 2
	grid.add_theme_constant_override("h_separation", 8)
	grid.add_theme_constant_override("v_separation", 8)
	for i in CrewLook.PRESETS.size():
		var p: Dictionary = CrewLook.PRESETS[i]
		var b := _button("%s（%s）" % [p.name, "男" if p.sex == "m" else "女"], func() -> void: _use_preset(i))
		b.custom_minimum_size.x = 136
		grid.add_child(b)
	lbox.add_child(grid)
	lbox.add_child(_spacer(6))
	lbox.add_child(_button("随机一张脸", _randomize))

	# 右边：分页滑杆
	var right := _panel(Vector2(-500, 70), Vector2(440, 0))
	right.anchor_left = 1.0
	right.anchor_right = 1.0
	right.anchor_bottom = 1.0
	right.offset_bottom = -150
	var tabs := TabContainer.new()
	tabs.add_theme_font_size_override("font_size", 17)
	right.add_child(tabs)
	for t: Array in TABS:
		var scroll := ScrollContainer.new()
		scroll.name = t[0]
		scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
		var box := VBoxContainer.new()
		box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		box.add_theme_constant_override("separation", 6)
		scroll.add_child(box)
		tabs.add_child(scroll)
		match t[1]:
			"#skin":
				_skin_page(box)
			"#brow":
				_brow_page(box)
			"#makeup":
				_makeup_page(box)
			_:
				for s: Array in CrewLook.SLIDERS:
					if s[0] == t[1]:
						box.add_child(_slider_row(s[1], s[2], s[3], s[4], true))

	# 下面：机位、保存、返回
	var bottom := HBoxContainer.new()
	bottom.add_theme_constant_override("separation", 10)
	bottom.anchor_left = 0.5
	bottom.anchor_right = 0.5
	bottom.anchor_top = 1.0
	bottom.anchor_bottom = 1.0
	bottom.offset_left = -330
	bottom.offset_top = -100
	_ui.add_child(bottom)
	for v: Array in [["face", "正脸"], ["side", "侧脸"], ["body", "全身"]]:
		bottom.add_child(_button(v[1], func() -> void: _set_view(v[0])))
	bottom.add_child(_spacer_h(30))
	bottom.add_child(_button("保存", func() -> void: _leave(true)))
	bottom.add_child(_button("返回", func() -> void: _leave(false)))
	var hint := _label("拖动转身，滚轮拉近拉远", 15, DIM.darkened(0.2))
	hint.anchor_left = 0.5
	hint.anchor_top = 1.0
	hint.anchor_bottom = 1.0
	hint.offset_left = -330
	hint.offset_top = -134
	_ui.add_child(hint)
	_refresh()


func _skin_page(box: VBoxContainer) -> void:
	box.add_child(_slider_row("skin", "肤色深浅", 0.0, 1.0, false))
	box.add_child(_slider_row("warm", "冷暖", -1.0, 1.0, false))
	box.add_child(_slider_row("flush", "红润", 0.0, 1.0, false))
	box.add_child(_slider_row("gender", "性别特征", 0.0, 1.0, false))
	_beard_row = _slider_row("beard", "胡茬", 0.0, 1.0, false)
	box.add_child(_beard_row)


func _brow_page(box: VBoxContainer) -> void:
	box.add_child(_label("眉毛款式", 16, DIM))
	var grid := GridContainer.new()
	grid.columns = 7
	grid.add_theme_constant_override("h_separation", 6)
	grid.add_theme_constant_override("v_separation", 6)
	var btns := []
	for i in CrewLook.BROW_STYLES:
		var b := _button(str(i + 1), func() -> void:
			look.brow = i
			_apply()
			_refresh())
		b.toggle_mode = true
		b.custom_minimum_size = Vector2(52, 40)
		btns.append(b)
		grid.add_child(b)
	_swatches["brow"] = btns
	box.add_child(grid)
	box.add_child(_slider_row("brow_dens", "眉毛浓淡", 0.0, 1.5, false))
	box.add_child(_slider_row("lash", "睫毛", 0.3, 1.5, false))
	box.add_child(_spacer(6))
	box.add_child(_label("瞳色", 16, DIM))
	box.add_child(_swatch_row("eye", CrewLook.IRIS_COLORS))
	box.add_child(_label("发型", 16, DIM))
	var hg := GridContainer.new()
	hg.columns = 3
	hg.add_theme_constant_override("h_separation", 6)
	hg.add_theme_constant_override("v_separation", 6)
	var hb := []
	for i in CrewLook.HAIR_STYLES.size():
		var b := _button(CrewLook.HAIR_STYLES[i][1], func() -> void:
			look.hair = i
			_apply()
			_refresh())
		b.toggle_mode = true
		b.custom_minimum_size = Vector2(118, 40)
		hb.append(b)
		hg.add_child(b)
	_swatches["hair"] = hb
	box.add_child(hg)
	box.add_child(_label("发色（眉毛、睫毛跟着变）", 16, DIM))
	box.add_child(_swatch_row("hair_col", CrewLook.HAIR_COLORS))


func _makeup_page(box: VBoxContainer) -> void:
	box.add_child(_slider_row("liner", "眼线", 0.0, 1.0, false))
	box.add_child(_slider_row("shadow", "眼影", 0.0, 1.0, false))
	box.add_child(_swatch_row("shadow_col", CrewLook.SHADOW_COLORS))
	box.add_child(_slider_row("blush", "腮红", 0.0, 1.0, false))
	box.add_child(_slider_row("lip", "口红", 0.0, 1.0, false))
	box.add_child(_swatch_row("lip_col", CrewLook.LIP_COLORS))


## 一行滑杆：shape 为真时改 look.shape[key]，否则改 look[key]
func _slider_row(key: String, text: String, lo: float, hi: float, shape: bool) -> Control:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 10)
	var l := _label(text, 16, INK)
	l.custom_minimum_size.x = 96
	row.add_child(l)
	var s := HSlider.new()
	s.min_value = lo
	s.max_value = hi
	s.step = 0.01
	s.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	s.custom_minimum_size = Vector2(200, 30)
	s.value_changed.connect(func(v: float) -> void:
		if shape:
			look.shape[key] = v
		else:
			look[key] = v
		_apply())
	row.add_child(s)
	_rows[("shape:" if shape else "") + key] = s
	return row


## 一排色块（瞳色、发色、口红色……），点了改 look[key]（下标）
func _swatch_row(key: String, colors: Array) -> Control:
	var row := HFlowContainer.new()
	row.add_theme_constant_override("h_separation", 6)
	row.add_theme_constant_override("v_separation", 6)
	var btns := []
	for i in colors.size():
		var b := Button.new()
		b.toggle_mode = true
		b.tooltip_text = colors[i][0]
		b.custom_minimum_size = Vector2(44, 34)
		var sb := StyleBoxFlat.new()
		sb.bg_color = colors[i][1]
		sb.set_border_width_all(2)
		sb.border_color = Color(0.2, 0.18, 0.15)
		var on := sb.duplicate() as StyleBoxFlat
		on.border_color = ACCENT.lightened(0.3)
		on.set_border_width_all(3)
		for k in ["normal", "hover", "focus"]:
			b.add_theme_stylebox_override(k, sb)
		for k in ["pressed", "hover_pressed"]:
			b.add_theme_stylebox_override(k, on)
		b.pressed.connect(func() -> void:
			look[key] = i
			_apply()
			_refresh())
		btns.append(b)
		row.add_child(b)
	_swatches[key] = btns
	return row


## 按当前的 look 刷新界面上所有控件（不触发改动）
func _refresh() -> void:
	for k: String in _rows:
		var s: HSlider = _rows[k]
		var v: float = look.shape.get(k.trim_prefix("shape:"), 0.0) if k.begins_with("shape:") else look.get(k, 0.0)
		s.set_value_no_signal(v)
	for k: String in _swatches:
		for i in _swatches[k].size():
			(_swatches[k][i] as Button).set_pressed_no_signal(i == int(look.get(k, 0)))
	for s: String in _sex_buttons:
		(_sex_buttons[s] as Button).set_pressed_no_signal(look.sex == s)
	if _beard_row:
		_beard_row.visible = look.sex == "m"


func _panel(pos: Vector2, size: Vector2) -> PanelContainer:
	var p := PanelContainer.new()
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.05, 0.048, 0.044, 0.82)
	sb.border_color = Color(0.45, 0.38, 0.28, 0.45)
	sb.set_border_width_all(1)
	sb.set_content_margin_all(18)
	p.add_theme_stylebox_override("panel", sb)
	p.position = pos
	p.offset_left = pos.x
	p.offset_top = pos.y
	p.offset_right = pos.x + size.x
	p.custom_minimum_size = size
	_ui.add_child(p)
	return p


func _label(text: String, size: int, color: Color) -> Label:
	var l := Label.new()
	l.text = text
	l.add_theme_font_override("font", _font)
	l.add_theme_font_size_override("font_size", size)
	l.add_theme_color_override("font_color", color)
	return l


func _button(text: String, cb: Callable) -> Button:
	var b := Button.new()
	b.text = text
	b.custom_minimum_size = Vector2(110, 42)
	b.pressed.connect(cb)
	return b


func _spacer(h: float) -> Control:
	var c := Control.new()
	c.custom_minimum_size.y = h
	return c


func _spacer_h(w: float) -> Control:
	var c := Control.new()
	c.custom_minimum_size.x = w
	return c


func _make_theme() -> Theme:
	var t := Theme.new()
	t.default_font = _font
	t.default_font_size = 17
	var normal := StyleBoxFlat.new()
	normal.bg_color = Color(0.09, 0.085, 0.075, 0.9)
	normal.border_color = Color(0.45, 0.38, 0.28, 0.7)
	normal.set_border_width_all(1)
	normal.set_content_margin_all(8)
	var hover := normal.duplicate() as StyleBoxFlat
	hover.bg_color = Color(0.16, 0.14, 0.11, 0.95)
	hover.border_color = Color(0.75, 0.62, 0.42)
	var pressed := normal.duplicate() as StyleBoxFlat
	pressed.bg_color = Color(0.32, 0.14, 0.1, 0.95)
	pressed.border_color = ACCENT
	for k in ["normal", "focus"]:
		t.set_stylebox(k, "Button", normal)
	t.set_stylebox("hover", "Button", hover)
	t.set_stylebox("pressed", "Button", pressed)
	t.set_stylebox("hover_pressed", "Button", pressed)
	t.set_color("font_color", "Button", INK)
	t.set_color("font_hover_color", "Button", Color(1, 0.95, 0.85))
	t.set_color("font_pressed_color", "Button", Color(1, 0.92, 0.85))
	t.set_color("font_hover_pressed_color", "Button", Color(1, 0.92, 0.85))
	# 滑杆：细槽、暖色的已拖过那段
	var track := StyleBoxFlat.new()
	track.bg_color = Color(0.2, 0.19, 0.17)
	track.content_margin_top = 3
	track.content_margin_bottom = 3
	var fill := track.duplicate() as StyleBoxFlat
	fill.bg_color = Color(0.62, 0.42, 0.3)
	t.set_stylebox("slider", "HSlider", track)
	t.set_stylebox("grabber_area", "HSlider", fill)
	t.set_stylebox("grabber_area_highlight", "HSlider", fill)
	var tab := normal.duplicate() as StyleBoxFlat
	tab.set_content_margin_all(6)
	var tab_on := pressed.duplicate() as StyleBoxFlat
	tab_on.set_content_margin_all(6)
	t.set_stylebox("tab_unselected", "TabContainer", tab)
	t.set_stylebox("tab_hovered", "TabContainer", hover)
	t.set_stylebox("tab_selected", "TabContainer", tab_on)
	var page := StyleBoxFlat.new()
	page.bg_color = Color(0, 0, 0, 0)
	page.set_content_margin_all(10)
	t.set_stylebox("panel", "TabContainer", page)
	t.set_color("font_selected_color", "TabContainer", Color(1, 0.95, 0.85))
	t.set_color("font_unselected_color", "TabContainer", DIM)
	t.set_color("font_hovered_color", "TabContainer", INK)
	return t


## 站着的人（装成第一人称相机的样子给 crew_body.gd 读）：眼睛在 position，turn 是人转了多少（0 面朝镜头）
class Stand extends Node3D:
	var yaw := PI
	var pitch := 0.0
	var turn := 0.0
	var gait_steps := 0.0
	var gait_speed := 0.0
	var gait_run := 0.0
	var door_op := false
	var door_aft := false
	var door_lean := 0.0
	var door_yaw := 0.0
	var deck_y := 0.0
	var _door = null

	func sit_amount() -> float:
		return 0.0

	func body_yaw() -> float:
		return PI + turn

	func feet() -> Vector2:
		return Vector2(position.x, position.z)

	func _process(_delta: float) -> void:
		yaw = PI + turn
