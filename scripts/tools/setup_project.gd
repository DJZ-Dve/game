extends SceneTree
## 一次性/可重复运行的项目配置脚本（无界面运行）：
##   Godot --headless --path . --script res://scripts/tools/setup_project.gd
## 1. 写入输入映射（在编辑器「项目设置 → 输入映射」里可见、可改）
## 2. 生成 assets/materials/ 下的材质（文件名 = Blender 里的材质名）

const PH := "res://assets/third_party/polyhaven/textures/"
const ACG := "res://assets/third_party/ambientcg/"
const MAT_DIR := "res://assets/materials/"
const WORN := preload("res://assets/shaders/worn_surface.gdshader")
const SEABED := preload("res://assets/shaders/seabed.gdshader")
const CRT := preload("res://assets/shaders/crt_sonar.gdshader")


func _init() -> void:
	_setup_input()
	_build_materials()
	print("setup done")
	quit()


# ----------------------------------------------------------------------------- 输入
func _key(code: Key) -> InputEventKey:
	var e := InputEventKey.new()
	e.device = -1  # 所有设备
	e.physical_keycode = code
	return e


func _mouse(button: MouseButton) -> InputEventMouseButton:
	var e := InputEventMouseButton.new()
	e.device = -1
	e.button_index = button
	return e


func _setup_input() -> void:
	var actions := {
		"move_forward": [_key(KEY_W), _key(KEY_UP)],
		"move_back": [_key(KEY_S), _key(KEY_DOWN)],
		"turn_left": [_key(KEY_A), _key(KEY_LEFT)],
		"turn_right": [_key(KEY_D), _key(KEY_RIGHT)],
		"ascend": [_key(KEY_SPACE), _key(KEY_R)],
		"descend": [_key(KEY_CTRL), _key(KEY_C)],
		"interact": [_key(KEY_E)],
		"toggle_lights": [_key(KEY_F)],
		"toggle_view": [_key(KEY_TAB)],
		"lean": [_mouse(MOUSE_BUTTON_RIGHT)],
		"toggle_help": [_key(KEY_F1)],
		"release_mouse": [_key(KEY_ESCAPE)],
	}
	for name: String in actions:
		ProjectSettings.set_setting("input/" + name, {"deadzone": 0.2, "events": actions[name]})
	ProjectSettings.save()


# ----------------------------------------------------------------------------- 材质
func _tex(asset: String, kind: String) -> Texture2D:
	return load(PH + "%s/%s_%s_2k.jpg" % [asset, asset, kind])


## ambientCG 贴图：kind = Color / NormalGL / Roughness / Metalness / AmbientOcclusion / Opacity
func _acg(id: String, kind: String) -> Texture2D:
	return load(ACG + "%s/%s_2K-JPG_%s.jpg" % [id, id, kind])


## 涂漆的设备/金属件：底色 + 细节贴图（ambientCG）+ 棱边磨损 + 指纹 + 积灰。
func _paint(name: String, paint: Color, o := {}) -> ShaderMaterial:
	var m := ShaderMaterial.new()
	m.shader = WORN
	m.resource_name = name
	var detail: String = o.get("detail", "PaintedMetal005")
	m.set_shader_parameter("paint_color", paint)
	m.set_shader_parameter("paint_roughness", o.get("rough", 0.5))
	m.set_shader_parameter("paint_metallic", o.get("metal", 0.15))
	m.set_shader_parameter("paint_variation", o.get("variation", 0.12))
	m.set_shader_parameter("rough_variation", o.get("rough_var", 0.15))
	m.set_shader_parameter("rust_amount", o.get("rust", 0.05))
	m.set_shader_parameter("edge_wear", o.get("edge", 0.8))
	m.set_shader_parameter("cavity_dirt", o.get("cavity", 1.0))
	m.set_shader_parameter("wear_color", o.get("wear", Color(0.55, 0.55, 0.53)))
	m.set_shader_parameter("tex_scale", o.get("scale", 3.0))
	m.set_shader_parameter("grime_albedo", _acg(o.get("albedo", "Metal016"), "Color"))
	m.set_shader_parameter("grime_normal", _acg(detail, "NormalGL"))
	m.set_shader_parameter("normal_strength", o.get("nstrength", 0.18))
	m.set_shader_parameter("grime_arm", _acg(detail, "Roughness"))
	m.set_shader_parameter("arm_packed", false)
	m.set_shader_parameter("smudge_tex", _acg("Fingerprints001", "Opacity"))
	m.set_shader_parameter("smudge_amount", o.get("smudge", 0.5))
	m.set_shader_parameter("smudge_scale", o.get("smudge_scale", 5.0))
	m.set_shader_parameter("dust_amount", o.get("dust", 0.3))
	m.set_shader_parameter("macro_amount", o.get("macro", 0.3))
	m.set_shader_parameter("floor_dirt", o.get("floor", 0.6))
	if o.has("streak"):
		m.set_shader_parameter("streak_tex", _acg("Leaking004", "Opacity"))
		m.set_shader_parameter("streak_amount", o.streak)
		m.set_shader_parameter("streak_scale", o.get("streak_scale", 1.2))
	if o.has("emission"):
		m.set_shader_parameter("emission_color", o.emission)
		m.set_shader_parameter("emission_energy", o.get("emission_energy", 1.0))
	return m


## 带贴图的标准材质（物体空间三平面映射，不需要 UV）。
func _tex_std(name: String, color: Color, id: String, o := {}) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.resource_name = name
	m.albedo_color = color
	if o.get("albedo_tex", false):
		m.albedo_texture = _acg(id, "Color")
	m.normal_enabled = true
	m.normal_texture = _acg(id, "NormalGL")
	m.normal_scale = o.get("nstrength", 1.0)
	if o.get("rough_tex", true):
		m.roughness_texture = _acg(id, "Roughness")
		m.roughness_texture_channel = BaseMaterial3D.TEXTURE_CHANNEL_GRAYSCALE
	m.roughness = o.get("rough", 1.0)
	m.metallic = o.get("metal", 0.0)
	if o.get("metal_tex", false):
		m.metallic_texture = _acg(id, "Metalness")
		m.metallic_texture_channel = BaseMaterial3D.TEXTURE_CHANNEL_GRAYSCALE
	m.uv1_triplanar = true
	m.uv1_world_triplanar = false
	var s: float = o.get("scale", 2.0)
	m.uv1_scale = Vector3(s, s, s)
	m.uv1_triplanar_sharpness = 4.0
	return m


func _worn(name: String, paint: Color, rough: float, metal: float, rust: float, edge: float,
		tex := "rusty_painted_metal", scale := 1.2, variation := 0.35, ntex := "rusty_metal_02",
		nstrength := 0.45) -> ShaderMaterial:
	var m := ShaderMaterial.new()
	m.shader = WORN
	m.resource_name = name
	m.set_shader_parameter("paint_color", paint)
	m.set_shader_parameter("paint_roughness", rough)
	m.set_shader_parameter("paint_metallic", metal)
	m.set_shader_parameter("paint_variation", variation)
	m.set_shader_parameter("rust_amount", rust)
	m.set_shader_parameter("edge_wear", edge)
	m.set_shader_parameter("tex_scale", scale)
	m.set_shader_parameter("grime_albedo", _tex(tex, "diff"))
	m.set_shader_parameter("grime_normal", _tex(ntex, "nor_gl"))
	m.set_shader_parameter("normal_strength", nstrength)
	m.set_shader_parameter("grime_arm", _tex(tex, "arm"))
	return m


func _std(name: String, color: Color, rough := 0.6, metal := 0.0, emission := Color.BLACK,
		energy := 0.0) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.resource_name = name
	m.albedo_color = color
	m.roughness = rough
	m.metallic = metal
	if energy > 0.0:
		m.emission_enabled = true
		m.emission = emission
		m.emission_energy_multiplier = energy
	return m


func _build_materials() -> void:
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(MAT_DIR))
	var mats: Array[Material] = []
	# 外壳
	mats.append(_worn("M_HullRed", Color(0.62, 0.1, 0.055), 0.5, 0.1, 0.42, 0.9, "rusty_painted_metal", 0.6, 0.2))
	mats.append(_worn("M_HullWhite", Color(0.6, 0.58, 0.53), 0.55, 0.1, 0.38, 0.8, "rusty_painted_metal", 0.8))
	mats.append(_worn("M_SpherePaint", Color(0.12, 0.13, 0.13), 0.45, 0.4, 0.22, 0.9))
	mats.append(_worn("M_FrameSteel", Color(0.07, 0.07, 0.075), 0.5, 0.6, 0.45, 0.8, "rusty_metal_02"))
	mats.append(_worn("M_BareMetal", Color(0.5, 0.5, 0.52), 0.35, 0.9, 0.12, 0.2, "rusty_metal_02", 2.0, 0.2))
	mats.append(_worn("M_Iron", Color(0.22, 0.13, 0.08), 0.85, 0.5, 0.9, 0.3, "rusty_metal_02", 0.9))
	mats.append(_worn("M_PaintText", Color(0.82, 0.8, 0.7), 0.6, 0.0, 0.35, 0.6))
	mats.append(_std("M_Rubber", Color(0.025, 0.025, 0.025), 0.85))
	mats.append(_std("M_ClothRed", Color(0.42, 0.015, 0.015), 0.95))
	var lens := _std("M_LampLens", Color(1, 0.95, 0.85), 0.1, 0.0, Color(1, 0.92, 0.8), 6.0)
	mats.append(lens)
	var glass := _std("M_Glass", Color(0.6, 0.75, 0.72, 0.07), 0.03)
	glass.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	glass.metallic_specular = 0.7
	# 玻璃上有擦拭留下的污痕：粗糙度不均匀，反光才有层次
	glass.roughness = 0.35
	glass.roughness_texture = _acg("Smear004", "Roughness")
	glass.roughness_texture_channel = BaseMaterial3D.TEXTURE_CHANNEL_GRAYSCALE
	glass.uv1_triplanar = true
	glass.uv1_scale = Vector3(4, 4, 4)
	mats.append(glass)
	_interior_materials(mats)
	var crt := ShaderMaterial.new()
	crt.resource_name = "M_CRT"
	crt.shader = CRT
	crt.set_shader_parameter("screen_size", Vector2(0.2, 0.15))
	mats.append(crt)
	# 海床
	var sea := ShaderMaterial.new()
	sea.resource_name = "M_Seabed"
	sea.shader = SEABED
	sea.set_shader_parameter("sand_albedo", _tex("coast_sand_01", "diff"))
	sea.set_shader_parameter("sand_normal", _tex("coast_sand_01", "nor_gl"))
	sea.set_shader_parameter("sand_arm", _tex("coast_sand_01", "arm"))
	sea.set_shader_parameter("mud_albedo", _tex("brown_mud_02", "diff"))
	sea.set_shader_parameter("mud_normal", _tex("brown_mud_02", "nor_gl"))
	sea.set_shader_parameter("rock_albedo", _tex("dark_rock", "diff"))
	sea.set_shader_parameter("rock_normal", _tex("dark_rock", "nor_gl"))
	mats.append(sea)

	for m in mats:
		var err := ResourceSaver.save(m, MAT_DIR + m.resource_name + ".tres")
		if err != OK:
			push_error("save failed: %s (%d)" % [m.resource_name, err])


## 舱内材质（名字和 blender/scripts/cockpit.py 里的 materials() 对应）
func _interior_materials(mats: Array[Material]) -> void:
	# ---- 耐压壳内壁、肋骨、隔壁（同一种舱漆：灰绿，冷凝水流痕，越往下越脏）
	mats.append(_paint("M_HullInner", Color(0.36, 0.4, 0.36), {"rough": 0.42, "metal": 0.25, "rust": 0.2,
		"edge": 1.0, "scale": 1.2, "smudge": 0.15, "dust": 0.35, "streak": 0.85, "variation": 0.25,
		"macro": 0.5, "floor": 0.9, "nstrength": 0.3}))
	mats.append(_paint("M_Rail", Color(0.52, 0.53, 0.52), {"rough": 0.4, "metal": 0.75, "rust": 0.18,
		"edge": 0.3, "detail": "Metal016", "smudge": 0.2}))
	# ---- 工作台台体（深蓝灰，倒角上磨出钢底，桌沿和把手附近满是手印）
	mats.append(_paint("M_Console", Color(0.15, 0.18, 0.2), {"rough": 0.4, "metal": 0.3, "edge": 1.3,
		"smudge": 0.8, "dust": 0.2, "rust": 0.1, "wear": Color(0.6, 0.6, 0.58), "macro": 0.7, "floor": 1.0,
		"nstrength": 0.25}))
	mats.append(_paint("M_DeskTop", Color(0.07, 0.085, 0.075), {"rough": 0.55, "metal": 0.0, "edge": 0.0,
		"smudge": 1.0, "smudge_scale": 3.0, "dust": 0.04, "rust": 0.0, "macro": 1.0, "floor": 0.0,
		"detail": "Plastic012B", "nstrength": 0.35}))
	mats.append(_paint("M_Grating", Color(0.22, 0.22, 0.21), {"rough": 0.45, "metal": 0.8, "edge": 1.5,
		"rust": 0.35, "detail": "Metal016", "smudge": 0.3, "dust": 0.5, "floor": 0.0}))
	var bilge := _std("M_Bilge", Color(0.015, 0.02, 0.016), 0.04)
	bilge.metallic_specular = 0.8
	mats.append(bilge)
	# ---- 管路（按介质刷色）
	mats.append(_paint("M_PipeRed", Color(0.42, 0.05, 0.035), {"rough": 0.45, "edge": 0.9, "rust": 0.25,
		"dust": 0.5, "floor": 0.0}))
	mats.append(_paint("M_PipeBlue", Color(0.12, 0.2, 0.32), {"rough": 0.45, "edge": 0.9, "rust": 0.2,
		"dust": 0.5, "floor": 0.0}))
	mats.append(_paint("M_PipeGray", Color(0.3, 0.31, 0.3), {"rough": 0.5, "edge": 0.9, "rust": 0.25,
		"dust": 0.6, "floor": 0.0, "streak": 0.5}))
	mats.append(_std("M_LampGlass", Color(1.0, 0.92, 0.8), 0.3, 0.0, Color(1.0, 0.86, 0.66), 4.0))
	# ---- 设备箱和面板（几种不同年代、不同厂家的漆色）
	mats.append(_paint("M_EquipGreen", Color(0.27, 0.33, 0.29), {"rough": 0.48, "dust": 0.4}))
	mats.append(_paint("M_EquipGray", Color(0.42, 0.43, 0.41), {"rough": 0.5, "dust": 0.22}))
	mats.append(_paint("M_EquipBeige", Color(0.5, 0.46, 0.37), {"rough": 0.5, "dust": 0.45}))
	mats.append(_paint("M_EquipBlue", Color(0.17, 0.23, 0.28), {"rough": 0.45, "dust": 0.3}))
	mats.append(_paint("M_PanelDark", Color(0.045, 0.045, 0.045), {"rough": 0.55, "metal": 0.1, "edge": 0.9,
		"smudge": 0.8, "dust": 0.25, "wear": Color(0.5, 0.5, 0.5), "nstrength": 0.45}))
	mats.append(_paint("M_PanelGray", Color(0.22, 0.23, 0.23), {"rough": 0.52, "edge": 0.8, "smudge": 0.7}))
	mats.append(_paint("M_Steel", Color(0.55, 0.55, 0.55), {"rough": 0.36, "metal": 0.95, "rust": 0.15,
		"edge": 0.0, "detail": "Metal016", "smudge": 0.5, "dust": 0.1}))
	mats.append(_paint("M_Copper", Color(0.62, 0.32, 0.2), {"rough": 0.35, "metal": 1.0, "rust": 0.1,
		"edge": 0.0, "detail": "Metal016", "smudge": 0.4}))
	mats.append(_tex_std("M_Bakelite", Color(0.03, 0.025, 0.022), "Plastic012B",
		{"rough": 0.8, "scale": 6.0, "nstrength": 0.3}))
	mats.append(_tex_std("M_Knob", Color(0.02, 0.02, 0.02), "Plastic012B", {"rough": 0.7, "scale": 8.0,
		"nstrength": 0.4}))
	mats.append(_std("M_Chrome", Color(0.85, 0.85, 0.85), 0.14, 1.0))
	mats.append(_tex_std("M_Alu", Color(0.78, 0.78, 0.77), "Metal016", {"rough": 0.75, "metal": 1.0,
		"scale": 3.0, "nstrength": 0.25}))
	mats.append(_std("M_Dark", Color(0.008, 0.008, 0.008), 0.95))
	mats.append(_std("M_Silk", Color(0.8, 0.79, 0.72), 0.7))
	mats.append(_std("M_GaugeInk", Color(0.02, 0.02, 0.02), 0.5))
	mats.append(_std("M_InkRed", Color(0.6, 0.04, 0.03), 0.5))
	var plate := _std("M_LabelPlate", Color(0.02, 0.02, 0.02), 0.25)
	plate.clearcoat_enabled = true
	mats.append(plate)
	mats.append(_std("M_LabelRed", Color(0.42, 0.025, 0.02), 0.3))
	# ---- 表盘、指针、指示灯（表盘有一点点背光）
	mats.append(_std("M_MeterFace", Color(0.86, 0.84, 0.76), 0.5, 0.0, Color(1, 0.86, 0.62), 0.05))
	mats.append(_std("M_GaugeFace", Color(0.86, 0.82, 0.7), 0.5, 0.0, Color(1, 0.72, 0.42), 0.08))
	mats.append(_std("M_Needle", Color(0.85, 0.1, 0.05), 0.4, 0.0, Color(1, 0.15, 0.05), 0.4))
	mats.append(_std("M_NeedleBlack", Color(0.02, 0.02, 0.02), 0.4))
	var tube := _std("M_GlassTube", Color(0.8, 0.88, 0.88, 0.14), 0.05)
	tube.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	tube.metallic_specular = 0.8
	mats.append(tube)
	mats.append(_std("M_FloatRed", Color(0.75, 0.05, 0.03), 0.35))
	mats.append(_std("M_IndicatorRed", Color(0.9, 0.05, 0.02), 0.3, 0.0, Color(1, 0.05, 0.02), 3.0))
	mats.append(_std("M_IndicatorAmber", Color(0.9, 0.5, 0.02), 0.3, 0.0, Color(1, 0.5, 0.02), 2.5))
	mats.append(_std("M_IndicatorGreen", Color(0.1, 0.9, 0.2), 0.3, 0.0, Color(0.1, 1, 0.2), 2.0))
	mats.append(_std("M_IndicatorWhite", Color(0.9, 0.88, 0.8), 0.3, 0.0, Color(1, 0.92, 0.75), 1.5))
	mats.append(_std("M_Warn", Color(0.5, 0.32, 0.06), 0.3, 0.0, Color(1, 0.55, 0.12), 0.02))
	var led := _std("M_LedWindow", Color(0.05, 0.0, 0.0), 0.06)
	led.metallic_specular = 0.7
	mats.append(led)
	mats.append(_std("M_BtnRed", Color(0.55, 0.035, 0.02), 0.35))
	mats.append(_std("M_BtnGreen", Color(0.04, 0.3, 0.08), 0.35))
	mats.append(_std("M_BtnYellow", Color(0.75, 0.55, 0.05), 0.4))
	mats.append(_paint("M_Olive", Color(0.19, 0.21, 0.12), {"rough": 0.5, "metal": 0.3, "edge": 1.0,
		"smudge": 0.4}))
	# ---- 线缆、扎带
	for c in [["M_CableBlack", Color(0.03, 0.03, 0.03)], ["M_CableGray", Color(0.28, 0.29, 0.28)],
			["M_CableOrange", Color(0.65, 0.22, 0.04)], ["M_CableYellow", Color(0.65, 0.55, 0.08)],
			["M_CableBlue", Color(0.08, 0.17, 0.4)], ["M_CableWhite", Color(0.7, 0.7, 0.67)]]:
		mats.append(_tex_std(c[0], c[1], "Rubber004", {"rough": 0.75, "scale": 12.0, "nstrength": 0.35}))
	mats.append(_std("M_ZipWhite", Color(0.82, 0.8, 0.74), 0.45))
	mats.append(_std("M_ZipBlack", Color(0.03, 0.03, 0.03), 0.45))
	# ---- 软的东西、纸
	mats.append(_tex_std("M_Vinyl", Color(0.32, 0.25, 0.22), "Leather033A", {"albedo_tex": true,
		"scale": 4.0, "rough": 0.9}))
	mats.append(_tex_std("M_Cloth", Color(0.55, 0.6, 0.42), "Fabric045", {"albedo_tex": true,
		"scale": 6.0, "nstrength": 0.8}))
	mats.append(_tex_std("M_MaskTape", Color(0.8, 0.74, 0.58), "Fabric045", {"rough": 0.9, "scale": 14.0,
		"nstrength": 0.25}))
	mats.append(_std("M_Marker", Color(0.03, 0.03, 0.06), 0.5))
	mats.append(_std("M_NoteYellow", Color(0.93, 0.8, 0.32), 0.8))
	mats.append(_tex_std("M_Deck", Color(0.55, 0.55, 0.53), "DiamondPlate008A", {"albedo_tex": true,
		"metal_tex": true, "metal": 1.0, "scale": 1.6}))
	mats.append(_paint("M_O2Blue", Color(0.3, 0.52, 0.68), {"rough": 0.45, "rust": 0.1, "edge": 0.9,
		"dust": 0.35}))
	mats.append(_paint("M_Brass", Color(0.62, 0.45, 0.18), {"rough": 0.35, "metal": 1.0, "rust": 0.08,
		"edge": 0.0, "detail": "Metal016", "smudge": 0.6}))
	# ---- 神龛
	var lacquer := _std("M_RedLacquer", Color(0.3, 0.022, 0.014), 0.3)
	lacquer.clearcoat_enabled = true
	lacquer.clearcoat = 0.6
	mats.append(lacquer)
	mats.append(_std("M_Gold", Color(0.8, 0.58, 0.22), 0.3, 1.0))
	mats.append(_std("M_StatueGilt", Color(0.55, 0.38, 0.13), 0.5, 0.8))
	mats.append(_tex_std("M_Paper", Color(0.82, 0.64, 0.24), "Fabric045", {"rough": 0.95, "scale": 10.0,
		"nstrength": 0.2}))
	mats.append(_std("M_BrushRed", Color(0.5, 0.02, 0.01), 0.7))
	mats.append(_std("M_Incense", Color(0.28, 0.09, 0.04), 0.85))
	mats.append(_std("M_Ember", Color(1, 0.3, 0.05), 0.5, 0.0, Color(1, 0.3, 0.05), 4.0))
	mats.append(_std("M_Ash", Color(0.3, 0.29, 0.27), 0.95))
	var jade := _std("M_Jade", Color(0.32, 0.55, 0.42), 0.18)
	jade.clearcoat_enabled = true
	jade.subsurf_scatter_enabled = true
	jade.subsurf_scatter_strength = 0.6
	mats.append(jade)