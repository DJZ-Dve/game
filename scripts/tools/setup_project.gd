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
const NET := preload("res://assets/shaders/net_bag.gdshader")
const FABRIC := preload("res://assets/shaders/fabric.gdshader")
const RAIN_GLASS := preload("res://assets/shaders/rain_glass.gdshader")
const NET_SHADER := preload("res://assets/shaders/mosquito_net.gdshader")
const HARBOR := preload("res://assets/shaders/harbor_water.gdshader")


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
		"sprint": [_key(KEY_SHIFT)],
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
	m.set_shader_parameter("rough_variation", o.get("rough_var", 0.25))
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
		m.set_shader_parameter("streak_cover", o.get("streak_cover", 1.0))
	if o.has("emission"):
		m.set_shader_parameter("emission_color", o.emission)
		m.set_shader_parameter("emission_energy", o.get("emission_energy", 1.0))
	if o.has("cond"):
		m.set_shader_parameter("condensation", o.cond)
		m.set_shader_parameter("cond_height", o.get("cond_h", 0.2))
		m.set_shader_parameter("cond_patch_cover", o.get("cond_cover", 0.4))
	m.set_shader_parameter("wear_metallic", o.get("wear_metal", 0.85))
	# 厚漆钢件：分层掉漆（漆 → 红丹底漆 → 钢）、大面磕碰、漆层台阶、焊接变形的起伏
	if o.has("primer"):
		m.set_shader_parameter("primer_amount", o.primer)
		m.set_shader_parameter("primer_color", o.get("primer_color", Color(0.32, 0.11, 0.065)))
	if o.has("chip"):
		m.set_shader_parameter("chip_tex", _acg("PaintedMetal005", "Opacity"))
		m.set_shader_parameter("chip_amount", o.chip)
		m.set_shader_parameter("chip_scale", o.get("chip_scale", 2.0))
		m.set_shader_parameter("chip_cover", o.get("chip_cover", 0.5))
	m.set_shader_parameter("bare_rust", o.get("bare_rust", 0.0))
	m.set_shader_parameter("paint_depth", o.get("depth", 0.0))
	m.set_shader_parameter("warp_amount", o.get("warp", 0.0))
	m.set_shader_parameter("warp_scale", o.get("warp_scale", 2.5))
	if o.has("dust_color"):
		m.set_shader_parameter("dust_color", o.dust_color)
	if o.has("floor_h"):
		# 岸上的房间地面在 y = 0（舱里是 -0.9）
		m.set_shader_parameter("floor_height", o.floor_h)
		m.set_shader_parameter("floor_fade", o.get("floor_fade", 0.65))
	if o.has("floor_color"):
		m.set_shader_parameter("floor_color", o.floor_color)
	if o.has("wear_color2"):
		m.set_shader_parameter("streak_color", o.wear_color2)
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


## 铺位上的布料（模型带 UV，单位米）：面料贴图染成 tint，见 fabric.gdshader
func _fabric(name: String, tint: Color, id: String, o := {}) -> ShaderMaterial:
	var m := ShaderMaterial.new()
	m.shader = FABRIC
	m.resource_name = name
	m.set_shader_parameter("tint", tint)
	m.set_shader_parameter("albedo_tex", _acg(id, "Color"))
	m.set_shader_parameter("normal_tex", _acg(id, "NormalGL"))
	m.set_shader_parameter("rough_tex", _acg(id, "Roughness"))
	for k: String in o:
		m.set_shader_parameter(k, o[k])
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
	# 艇身：水线以上黑漆（老化发灰、锈水往下淌），以下红色防污漆；甲板是防滑涂层
	mats.append(_worn("M_HullBlack", Color(0.04, 0.042, 0.045), 0.6, 0.1, 0.28, 0.25, "rusty_painted_metal", 0.5,
		0.25))
	mats.append(_worn("M_Antifoul", Color(0.3, 0.075, 0.05), 0.75, 0.05, 0.28, 0.25, "rusty_painted_metal", 0.6, 0.3))
	mats.append(_worn("M_DeckNonSkid", Color(0.07, 0.07, 0.07), 0.9, 0.1, 0.35, 0.4, "rusty_metal_02", 1.5, 0.3))
	mats.append(_worn("M_FrameSteel", Color(0.07, 0.07, 0.075), 0.5, 0.6, 0.45, 0.8, "rusty_metal_02"))
	mats.append(_worn("M_BareMetal", Color(0.5, 0.5, 0.52), 0.35, 0.9, 0.12, 0.2, "rusty_metal_02", 2.0, 0.2))
	# 螺旋桨：铝青铜，发暗、长了一层铜绿
	mats.append(_worn("M_Bronze", Color(0.5, 0.35, 0.18), 0.42, 0.95, 0.3, 0.2, "rusty_metal_02", 1.5, 0.3))
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
	_room_materials(mats)
	var crt := ShaderMaterial.new()
	crt.resource_name = "M_CRT"
	crt.shader = CRT
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
		"macro": 0.5, "floor": 0.9, "nstrength": 0.3, "cond": 0.75, "cond_cover": 0.42, "streak_cover": 0.45}))
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
	# ---- 管路（按介质刷色；冷却水管最凉，结露最多）
	mats.append(_paint("M_PipeRed", Color(0.42, 0.05, 0.035), {"rough": 0.55, "edge": 0.9, "rust": 0.25,
		"dust": 0.5, "floor": 0.0, "cond": 0.35, "cond_h": -0.5}))
	mats.append(_paint("M_PipeBlue", Color(0.12, 0.2, 0.32), {"rough": 0.55, "edge": 0.9, "rust": 0.2,
		"dust": 0.5, "floor": 0.0, "cond": 1.0, "cond_h": -1.5}))
	mats.append(_paint("M_PipeGray", Color(0.3, 0.31, 0.3), {"rough": 0.6, "edge": 0.9, "rust": 0.25,
		"dust": 0.6, "floor": 0.0, "streak": 0.5, "cond": 0.4, "cond_h": -0.5}))
	# 通风管外面包的帆布保温层：发黄、积灰、有水渍
	mats.append(_paint("M_Lagging", Color(0.48, 0.45, 0.37), {"rough": 0.92, "metal": 0.0, "edge": 0.0,
		"rust": 0.0, "detail": "Fabric045", "albedo": "Fabric045", "nstrength": 0.9, "scale": 5.0,
		"variation": 0.5, "dust": 0.55, "smudge": 0.0, "streak": 0.7, "streak_scale": 2.0, "macro": 0.8,
		"floor": 0.0, "cavity": 0.6}))
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
	# ---- 水密门：一层层刷上去的厚瓷漆（哑光、不带金属光泽），磕掉的地方先露红丹底漆再露钢；
	# 门扇下半截被脚踢、上面被手推，大面上也有成片的磕痕划痕，门板焊过有点起伏。
	# 锻钢件发黑、带氧化皮，只有把手尖、楔块顶面、铰链这些常磨的地方是亮的
	mats.append(_paint("M_DoorPaint", Color(0.17, 0.2, 0.185), {"rough": 0.6, "metal": 0.0, "edge": 1.6,
		"rust": 0.24, "smudge": 0.9, "dust": 0.25, "streak": 0.55, "streak_cover": 0.5, "macro": 0.9,
		"floor": 0.8, "nstrength": 0.45, "variation": 0.25, "rough_var": 0.4, "wear": Color(0.5, 0.49, 0.47),
		"primer": 0.6, "chip": 0.6, "chip_scale": 1.6, "chip_cover": 0.35, "bare_rust": 0.8, "depth": 0.0012,
		"warp": 1.0, "warp_scale": 2.2}))
	# 门框、补强板：和隔壁同一种舱漆，但门边常被磕碰、踩，掉漆更多
	mats.append(_paint("M_DoorFrame", Color(0.34, 0.38, 0.34), {"rough": 0.58, "metal": 0.0, "rust": 0.24,
		"edge": 1.4, "scale": 1.2, "smudge": 0.6, "dust": 0.35, "streak": 0.7, "variation": 0.25,
		"macro": 0.6, "floor": 0.9, "nstrength": 0.35, "rough_var": 0.35, "streak_cover": 0.5,
		"wear": Color(0.5, 0.49, 0.47), "primer": 0.6, "chip": 0.6, "chip_scale": 2.2, "chip_cover": 0.4,
		"bare_rust": 0.8, "depth": 0.0012, "warp": 0.6, "warp_scale": 3.0}))
	mats.append(_paint("M_Forged", Color(0.085, 0.082, 0.078), {"rough": 0.62, "metal": 0.7, "edge": 1.1,
		"wear": Color(0.5, 0.49, 0.46), "wear_metal": 1.0, "rust": 0.2, "detail": "Metal016", "smudge": 0.7,
		"dust": 0.12, "variation": 0.35, "rough_var": 0.5, "nstrength": 0.55, "floor": 0.3, "macro": 0.6,
		"warp": 0.8, "warp_scale": 9.0}))
	mats.append(_paint("M_WheelRed", Color(0.3, 0.03, 0.018), {"rough": 0.58, "metal": 0.0, "edge": 1.2,
		"wear": Color(0.42, 0.41, 0.39), "rust": 0.12, "smudge": 1.0, "smudge_scale": 7.0, "dust": 0.08,
		"macro": 0.6, "floor": 0.0, "nstrength": 0.35, "rough_var": 0.35, "chip": 0.55, "chip_scale": 4.0,
		"chip_cover": 0.55, "bare_rust": 0.5, "depth": 0.0008, "primer": 0.3,
		"primer_color": Color(0.12, 0.11, 0.1)}))
	var grease := _std("M_Grease", Color(0.035, 0.028, 0.014), 0.12)
	grease.metallic_specular = 0.6
	mats.append(grease)
	mats.append(_paint("M_Copper", Color(0.62, 0.32, 0.2), {"rough": 0.35, "metal": 1.0, "rust": 0.1,
		"edge": 0.0, "detail": "Metal016", "smudge": 0.4, "cond": 0.6, "cond_h": -0.5}))
	mats.append(_tex_std("M_Bakelite", Color(0.03, 0.025, 0.022), "Plastic012B",
		{"rough": 0.8, "scale": 6.0, "nstrength": 0.3}))
	mats.append(_tex_std("M_Knob", Color(0.02, 0.02, 0.02), "Plastic012B", {"rough": 0.7, "scale": 8.0,
		"nstrength": 0.4}))
	# 镀铬件：发乌、有指纹和细划痕，高光不会一整片炸白
	mats.append(_paint("M_Chrome", Color(0.78, 0.78, 0.77), {"rough": 0.2, "metal": 1.0, "rust": 0.04,
		"edge": 0.0, "detail": "Metal016", "smudge": 0.7, "smudge_scale": 9.0, "rough_var": 0.35, "dust": 0.15,
		"variation": 0.15, "nstrength": 0.12, "scale": 6.0, "floor": 0.0}))
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
	# 人造革：皮纹 + 坐久了磨亮的光泽
	mats.append(_tex_std("M_Vinyl", Color(0.42, 0.33, 0.29), "Leather033A", {"albedo_tex": true,
		"scale": 4.0, "rough": 0.62, "nstrength": 1.2}))
	mats.append(_tex_std("M_Cloth", Color(0.55, 0.6, 0.42), "Fabric045", {"albedo_tex": true,
		"scale": 6.0, "nstrength": 0.8}))
	mats.append(_tex_std("M_MaskTape", Color(0.8, 0.74, 0.58), "Fabric045", {"rough": 0.9, "scale": 14.0,
		"nstrength": 0.25}))
	mats.append(_std("M_Marker", Color(0.03, 0.03, 0.06), 0.5))
	mats.append(_std("M_NoteYellow", Color(0.93, 0.8, 0.32), 0.8))
	# 花纹钢地板刷了一层灰绿甲板漆（凸起的花纹上磨得发亮）。纯金属的话贴花（脚印、斑马线）的颜色显不出来
	mats.append(_paint("M_Deck", Color(0.3, 0.32, 0.29), {"rough": 0.55, "metal": 0.2, "detail": "DiamondPlate008A",
		"albedo": "DiamondPlate008A", "nstrength": 1.0, "scale": 1.6, "edge": 0.0, "rust": 0.15, "variation": 0.45,
		"rough_var": 0.5, "dust": 0.12, "smudge": 0.0, "macro": 0.6, "floor": 0.0}))
	mats.append(_paint("M_O2Blue", Color(0.3, 0.52, 0.68), {"rough": 0.45, "rust": 0.1, "edge": 0.9,
		"dust": 0.35}))
	mats.append(_paint("M_Brass", Color(0.62, 0.45, 0.18), {"rough": 0.35, "metal": 1.0, "rust": 0.08,
		"edge": 0.0, "detail": "Metal016", "smudge": 0.6}))
	# ---- 神龛（漆面棱边磨出底下的木胎，常年烟熏，落着香灰）
	mats.append(_paint("M_RedLacquer", Color(0.3, 0.022, 0.014), {"rough": 0.28, "metal": 0.0, "rust": 0.0,
		"edge": 1.2, "wear": Color(0.16, 0.08, 0.04), "wear_metal": 0.0, "detail": "Plastic012B",
		"smudge": 0.5, "dust": 0.45, "dust_color": Color(0.33, 0.31, 0.29), "macro": 0.6, "floor": 0.0,
		"nstrength": 0.15}))
	mats.append(_paint("M_Gold", Color(0.8, 0.58, 0.22), {"rough": 0.32, "metal": 1.0, "rust": 0.0,
		"edge": 0.9, "wear": Color(0.28, 0.04, 0.02), "wear_metal": 0.0, "detail": "Metal016", "smudge": 0.4,
		"dust": 0.5, "dust_color": Color(0.33, 0.31, 0.29), "macro": 0.7, "rough_var": 0.4, "floor": 0.0}))
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
	# ---- 生活痕迹
	mats.append(_tex_std("M_Towel", Color(0.78, 0.74, 0.62), "Fabric045", {"albedo_tex": true, "scale": 9.0,
		"nstrength": 1.4, "rough": 1.0}))
	mats.append(_tex_std("M_Jacket", Color(0.16, 0.22, 0.34), "Fabric045", {"albedo_tex": true, "scale": 7.0,
		"nstrength": 1.0, "rough": 1.0}))
	var net := ShaderMaterial.new()
	net.resource_name = "M_Net"
	net.shader = NET
	mats.append(net)
	mats.append(_tex_std("M_Orange", Color(0.9, 0.36, 0.04), "Leather033A", {"scale": 45.0, "nstrength": 0.6,
		"rough": 0.45, "rough_tex": false}))
	var bottle := _std("M_Bottle", Color(0.5, 0.62, 0.66), 0.18)
	bottle.metallic_specular = 0.7
	mats.append(bottle)
	mats.append(_paint("M_Can", Color(0.62, 0.62, 0.6), {"rough": 0.3, "metal": 0.9, "rust": 0.3,
		"edge": 0.0, "detail": "Metal016", "dust": 0.35, "smudge": 0.3, "floor": 0.0}))
	mats.append(_paint("M_CanLabel", Color(0.5, 0.1, 0.04), {"rough": 0.55, "metal": 0.0, "rust": 0.05,
		"edge": 0.5, "wear": Color(0.6, 0.6, 0.58), "detail": "Plastic012B", "dust": 0.3, "floor": 0.0}))
	# 茶缸子里的茶（几乎是镜面的深褐色液面）和内壁的茶垢
	var tea := _std("M_Tea", Color(0.07, 0.03, 0.01), 0.04)
	tea.metallic_specular = 0.6
	mats.append(tea)
	mats.append(_std("M_TeaStain", Color(0.36, 0.2, 0.08), 0.75))
	mats.append(_tex_std("M_Cardboard", Color(0.52, 0.38, 0.22), "Fabric045", {"scale": 4.0, "nstrength": 0.25,
		"rough": 0.95}))
	# ---- 生活舱：军毯、布帘、镜子
	# 军毯：粗毛毡，橄榄绿，绒面有一层光泽
	mats.append(_fabric("M_Blanket", Color(0.2, 0.22, 0.13), "Fabric034", {"tex_scale": 2.0, "tex_mean": 0.36,
		"tex_contrast": 1.3, "normal_strength": 1.1, "sheen": 0.4, "sheen_tint": 0.7, "stain_amount": 0.25,
		"stain_color": Color(0.7, 0.62, 0.45), "binding_width": 0.014, "binding_color": Color(0.62, 0.62, 0.58)}))
	# 枕套：洗旧了的白棉布，中间一大块汗渍发黄
	mats.append(_fabric("M_Pillow", Color(0.66, 0.63, 0.55), "Fabric001", {"tex_scale": 1.6, "tex_mean": 0.55,
		"tex_contrast": 3.0, "normal_strength": 0.5, "sheen": 0.25, "stain_amount": 0.55, "stain_scale": 4.0,
		"stain_color": Color(0.82, 0.66, 0.4)}))
	# 床单：发灰的白棉布，睡出来的黄印子
	mats.append(_fabric("M_Sheet", Color(0.6, 0.61, 0.58), "Fabric001", {"tex_scale": 1.3, "tex_mean": 0.55,
		"tex_contrast": 2.5, "normal_strength": 0.35, "sheen": 0.2, "stain_amount": 0.4, "stain_scale": 2.5,
		"stain_color": Color(0.85, 0.72, 0.5)}))
	# 床垫：蓝白条纹的床垫布，发黄、到处是水渍
	mats.append(_fabric("M_Mattress", Color(0.8, 0.76, 0.64), "Fabric071", {"tex_scale": 3.5, "albedo_mix": 0.35,
		"tex_mean": 0.33, "tex_contrast": 0.8, "normal_strength": 1.0, "sheen": 0.2, "stain_amount": 0.6, "stain_scale": 2.5,
		"stain_color": Color(0.72, 0.56, 0.34), "cavity_dirt": 0.8}))
	# 布帘：灰绿细帆布，后面亮着床头灯时透出一点暖光
	mats.append(_fabric("M_Curtain", Color(0.26, 0.29, 0.22), "Fabric036", {"tex_scale": 2.0, "tex_mean": 0.49,
		"tex_contrast": 1.2, "normal_strength": 0.9, "sheen": 0.3, "stain_amount": 0.2,
		"backlight": Color(0.32, 0.26, 0.16)}))
	# 镜子：水银发乌、有擦拭的污痕
	var mirror := _std("M_Mirror", Color(0.62, 0.63, 0.6), 0.25, 1.0)
	mirror.roughness_texture = _acg("Smear004", "Roughness")
	mirror.roughness_texture_channel = BaseMaterial3D.TEXTURE_CHANNEL_GRAYSCALE
	mirror.uv1_triplanar = true
	mirror.uv1_scale = Vector3(3, 3, 3)
	mats.append(mirror)

## 岸上场景（宿舍、办事处）的材质（名字和 blender/scripts/room_kit.py、gen_dorm.py、gen_office.py 里的对应）。
## 房间的地面在 y = 0（floor_h）。
func _room_materials(mats: Array[Material]) -> void:
	# ---- 墙、顶：白灰墙（刷过好几遍的石灰，发黄、一块块深浅不一，起皮的地方露出底下的灰），窗下雨水渗出来的流痕
	mats.append(_paint("M_Plaster", Color(0.74, 0.72, 0.66), {"rough": 0.92, "metal": 0.0, "edge": 0.4,
		"rust": 0.0, "detail": "Plaster003", "albedo": "Plaster003", "nstrength": 0.25, "scale": 0.6,
		"variation": 0.14, "macro": 0.9, "smudge": 0.0, "dust": 0.0, "floor": 0.0,
		"streak": 0.45, "streak_cover": 0.35, "streak_scale": 0.8, "wear": Color(0.55, 0.54, 0.5),
		"wear_metal": 0.0, "primer": 0.5, "primer_color": Color(0.5, 0.49, 0.45), "chip": 0.2,
		"chip_scale": 0.6, "chip_cover": 0.08, "depth": 0.0015, "warp": 0.35, "warp_scale": 1.2,
		"floor_h": 0.0, "cavity": 0.4}))
	mats.append(_paint("M_Ceiling", Color(0.76, 0.75, 0.7), {"rough": 0.95, "metal": 0.0, "edge": 0.0,
		"rust": 0.0, "detail": "Plaster003", "albedo": "Plaster003", "nstrength": 0.2, "scale": 0.6,
		"variation": 0.12, "macro": 0.8, "smudge": 0.0, "dust": 0.0, "floor": 0.0, "floor_h": 0.0}))
	mats.append(_paint("M_Facade", Color(0.5, 0.5, 0.47), {"rough": 0.9, "metal": 0.0, "edge": 0.3, "rust": 0.0,
		"detail": "Concrete046", "albedo": "Concrete046", "nstrength": 0.6, "scale": 0.8, "variation": 0.4,
		"macro": 1.0, "streak": 0.9, "streak_cover": 0.7, "streak_scale": 0.5, "floor_h": -3.6, "floor": 0.5}))
	# 绿漆墙裙：油漆有光，磕掉的地方露出白灰，靠地面那截被拖把、鞋蹭得发黑
	mats.append(_paint("M_DadoGreen", Color(0.26, 0.4, 0.33), {"rough": 0.38, "metal": 0.0, "edge": 1.2,
		"rust": 0.0, "detail": "Plaster003", "albedo": "Plaster003", "nstrength": 0.35, "scale": 1.0,
		"variation": 0.18, "rough_var": 0.3, "macro": 0.6, "smudge": 0.5, "smudge_scale": 2.0, "dust": 0.0,
		"floor": 0.7, "floor_h": 0.0, "floor_fade": 0.35, "wear": Color(0.7, 0.69, 0.64), "wear_metal": 0.0,
		"primer": 0.4, "primer_color": Color(0.72, 0.71, 0.66), "chip": 0.55, "chip_scale": 1.6,
		"chip_cover": 0.3, "depth": 0.001, "warp": 0.4, "warp_scale": 1.5}))
	mats.append(_paint("M_DadoLine", Color(0.1, 0.17, 0.13), {"rough": 0.35, "metal": 0.0, "edge": 1.0, "rust": 0.0,
		"detail": "Plaster003", "nstrength": 0.3, "wear": Color(0.6, 0.6, 0.56), "wear_metal": 0.0, "smudge": 0.3,
		"floor_h": 0.0}))
	mats.append(_paint("M_Skirt", Color(0.4, 0.4, 0.38), {"rough": 0.85, "metal": 0.0, "edge": 1.0, "rust": 0.0,
		"detail": "Concrete046", "albedo": "Concrete046", "nstrength": 0.7, "scale": 1.5, "variation": 0.5,
		"macro": 0.8, "wear": Color(0.5, 0.5, 0.48), "wear_metal": 0.0, "floor": 0.8, "floor_h": 0.0,
		"floor_fade": 0.1}))
	# 水泥地刷紫红地板漆：漆面有光，磨掉的地方露出灰水泥
	mats.append(_paint("M_FloorPaint", Color(0.3, 0.1, 0.075), {"rough": 0.42, "metal": 0.0, "edge": 0.0,
		"rust": 0.0, "detail": "Concrete046", "albedo": "Concrete046", "nstrength": 0.5, "scale": 1.0,
		"variation": 0.3, "rough_var": 0.4, "macro": 0.8, "macro_scale": 0.4, "smudge": 0.0, "dust": 0.12,
		"dust_color": Color(0.4, 0.37, 0.33), "floor": 0.0, "primer": 0.7, "primer_color": Color(0.42, 0.41, 0.39),
		"chip": 0.7, "chip_scale": 1.3, "chip_cover": 0.4, "depth": 0.0008, "floor_h": -10.0}))
	mats.append(_tex_std("M_Concrete", Color(0.55, 0.55, 0.52), "Concrete046", {"albedo_tex": true, "scale": 0.7,
		"rough": 0.9, "nstrength": 0.8}))
	# 水磨石：灰底子里嵌着细石子（贴图的明暗压一压，不然像花岗岩），磨得发亮，照得出窗户；靠墙根积灰
	mats.append(_paint("M_Terrazzo", Color(0.5, 0.5, 0.47), {"rough": 0.3, "metal": 0.0, "edge": 0.0, "rust": 0.0,
		"detail": "Terrazzo005", "albedo": "Terrazzo005", "nstrength": 0.15, "scale": 3.0, "variation": 0.42,
		"rough_var": 0.5, "macro": 0.7, "smudge": 0.0, "dust": 0.06, "floor": 0.0, "cavity": 0.0,
		"floor_h": -10.0}))
	# ---- 木头
	mats.append(_tex_std("M_Wainscot", Color(0.5, 0.36, 0.28), "Wood051", {"albedo_tex": true, "scale": 1.2,
		"rough": 0.55, "nstrength": 0.5}))
	mats.append(_tex_std("M_WoodDark", Color(0.62, 0.45, 0.36), "Wood051", {"albedo_tex": true, "scale": 1.5,
		"rough": 0.5, "nstrength": 0.5}))
	mats.append(_tex_std("M_WoodLight", Color(1.0, 0.86, 0.62), "Wood049", {"albedo_tex": true, "scale": 1.5,
		"rough": 0.45, "nstrength": 0.5}))
	mats.append(_tex_std("M_WoodRaw", Color(0.9, 0.82, 0.68), "Wood049", {"albedo_tex": true, "scale": 2.0,
		"rough": 0.85, "nstrength": 0.8}))
	mats.append(_tex_std("M_WoodRed", Color(0.75, 0.42, 0.32), "Wood026", {"albedo_tex": true, "scale": 1.4,
		"rough": 0.32, "nstrength": 0.4}))
	# 门、窗框：刷了好几层的油漆木头（底下透出以前的颜色）
	mats.append(_paint("M_DoorBlue", Color(0.42, 0.56, 0.54), {"rough": 0.45, "metal": 0.0, "edge": 1.4, "rust": 0.0,
		"detail": "PaintedWood009C", "albedo": "PaintedWood009C", "nstrength": 0.7, "scale": 1.5,
		"variation": 0.3, "macro": 0.5, "smudge": 0.9, "smudge_scale": 2.5, "dust": 0.1, "floor": 0.5,
		"floor_h": 0.0, "floor_fade": 0.4, "wear": Color(0.45, 0.33, 0.22), "wear_metal": 0.0, "primer": 0.5,
		"primer_color": Color(0.55, 0.53, 0.45), "chip": 0.25, "chip_scale": 2.5, "chip_cover": 0.18,
		"depth": 0.0012}))
	mats.append(_paint("M_WindowWood", Color(0.62, 0.66, 0.6), {"rough": 0.5, "metal": 0.0, "edge": 1.5, "rust": 0.0,
		"detail": "PaintedWood009C", "albedo": "PaintedWood009C", "nstrength": 0.8, "scale": 2.0,
		"variation": 0.35, "macro": 0.5, "smudge": 0.4, "dust": 0.3, "wear": Color(0.4, 0.3, 0.2),
		"wear_metal": 0.0, "primer": 0.5, "primer_color": Color(0.35, 0.4, 0.42), "chip": 0.7, "chip_scale": 3.0,
		"chip_cover": 0.5, "depth": 0.001, "streak": 0.6, "floor_h": -10.0}))
	mats.append(_paint("M_WindowSteel", Color(0.3, 0.36, 0.33), {"rough": 0.5, "metal": 0.1, "edge": 1.4, "rust": 0.35,
		"smudge": 0.4, "dust": 0.3, "wear": Color(0.35, 0.22, 0.14), "wear_metal": 0.3, "primer": 0.5,
		"chip": 0.5, "chip_scale": 3.0, "chip_cover": 0.4, "bare_rust": 1.0, "streak": 0.5, "floor_h": -10.0}))
	mats.append(_paint("M_IronBar", Color(0.08, 0.075, 0.07), {"rough": 0.7, "metal": 0.2, "edge": 1.2, "rust": 0.62,
		"wear": Color(0.32, 0.17, 0.09), "wear_metal": 0.2, "streak": 0.6, "dust": 0.0, "floor_h": -10.0}))
	mats.append(_tex_std("M_Bamboo", Color(0.78, 0.66, 0.42), "Wood049", {"albedo_tex": true, "scale": 4.0,
		"rough": 0.5, "nstrength": 0.4}))
	# ---- 瓷、搪瓷、胶木、灯具
	var porcelain := _std("M_Porcelain", Color(0.86, 0.85, 0.8), 0.12)
	porcelain.clearcoat_enabled = true
	mats.append(porcelain)
	var enamel := _std("M_Enamel", Color(0.84, 0.84, 0.8), 0.15)
	enamel.clearcoat_enabled = true
	mats.append(enamel)
	mats.append(_tex_std("M_BakeliteBrown", Color(0.12, 0.05, 0.025), "Plastic012B", {"rough": 0.45, "scale": 6.0,
		"nstrength": 0.3}))
	mats.append(_paint("M_FixtureWhite", Color(0.72, 0.72, 0.68), {"rough": 0.45, "metal": 0.1, "edge": 1.2,
		"rust": 0.15, "smudge": 0.4, "dust": 0.6, "dust_color": Color(0.36, 0.34, 0.3), "wear": Color(0.3, 0.2, 0.15),
		"wear_metal": 0.4, "floor_h": -10.0}))
	mats.append(_paint("M_FanCream", Color(0.6, 0.56, 0.44), {"rough": 0.62, "metal": 0.0, "edge": 1.0, "rust": 0.1,
		"smudge": 0.3, "dust": 0.85, "dust_color": Color(0.3, 0.28, 0.25), "wear": Color(0.35, 0.3, 0.25),
		"floor_h": -10.0}))
	var tube := _std("M_Tube", Color(0.95, 0.97, 0.95), 0.25, 0.0, Color(0.92, 1.0, 0.96), 3.0)
	mats.append(tube)
	mats.append(_tex_std("M_Wire", Color(0.5, 0.42, 0.3), "Fabric045", {"albedo_tex": true, "scale": 30.0,
		"rough": 0.9, "nstrength": 0.8}))
	# ---- 玻璃：窗玻璃上挂着雨
	var rain := ShaderMaterial.new()
	rain.resource_name = "M_WindowGlass"
	rain.shader = RAIN_GLASS
	mats.append(rain)
	# ---- 纸、布、杂物
	mats.append(_tex_std("M_PaperWhite", Color(0.82, 0.79, 0.7), "Fabric045", {"rough": 0.95, "scale": 10.0,
		"nstrength": 0.15}))
	mats.append(_tex_std("M_Newspaper", Color(0.62, 0.6, 0.52), "Fabric045", {"rough": 0.95, "scale": 10.0,
		"nstrength": 0.15}))
	mats.append(_paint("M_ThermosRed", Color(0.45, 0.05, 0.035), {"rough": 0.4, "metal": 0.1, "edge": 1.3,
		"rust": 0.12, "smudge": 0.7, "dust": 0.2, "wear": Color(0.4, 0.38, 0.35), "wear_metal": 0.8,
		"floor_h": -10.0}))
	mats.append(_std("M_Cork", Color(0.42, 0.3, 0.18), 0.9))
	mats.append(_tex_std("M_Rope", Color(0.55, 0.5, 0.4), "Fabric045", {"albedo_tex": true, "scale": 40.0,
		"rough": 0.95}))
	mats.append(_std("M_Candle", Color(0.55, 0.04, 0.03), 0.45))
	mats.append(_paint("M_Pewter", Color(0.45, 0.45, 0.43), {"rough": 0.5, "metal": 0.85, "edge": 0.0, "rust": 0.1,
		"detail": "Metal016", "smudge": 0.5, "dust": 0.4, "floor_h": -10.0}))
	mats.append(_fabric("M_StrawMat", Color(0.62, 0.52, 0.3), "Fabric045", {"tex_scale": 1.2, "tex_mean": 0.4,
		"tex_contrast": 2.2, "normal_strength": 1.6, "sheen": 0.15, "roughness": 0.7, "stain_amount": 0.35,
		"stain_color": Color(0.7, 0.55, 0.35)}))
	mats.append(_fabric("M_TowelBlanket", Color(0.56, 0.4, 0.44), "Fabric045", {"tex_scale": 6.0, "tex_mean": 0.36,
		"tex_contrast": 1.4, "normal_strength": 1.4, "sheen": 0.5, "stain_amount": 0.2}))
	var net := ShaderMaterial.new()
	net.resource_name = "M_MosquitoNet"
	net.shader = NET_SHADER
	mats.append(net)
	mats.append(_fabric("M_Canvas", Color(0.3, 0.37, 0.4), "Fabric036", {"tex_scale": 2.5, "tex_mean": 0.49,
		"tex_contrast": 1.2, "normal_strength": 1.0, "sheen": 0.2, "stain_amount": 0.3}))
	mats.append(_fabric("M_CurtainCheck", Color(0.74, 0.74, 0.7), "Fabric001", {"tex_scale": 1.6, "tex_mean": 0.55,
		"tex_contrast": 2.0, "normal_strength": 0.6, "sheen": 0.25, "check_size": 0.022,
		"check_color": Color(0.32, 0.45, 0.68), "stain_amount": 0.3, "backlight": Color(0.3, 0.3, 0.3)}))
	mats.append(_fabric("M_Undershirt", Color(0.78, 0.77, 0.72), "Fabric001", {"tex_scale": 2.0, "tex_mean": 0.55,
		"tex_contrast": 2.5, "normal_strength": 0.5, "sheen": 0.25, "stain_amount": 0.35,
		"backlight": Color(0.35, 0.34, 0.3)}))
	mats.append(_fabric("M_Sock", Color(0.2, 0.2, 0.22), "Fabric034", {"tex_scale": 6.0, "tex_mean": 0.36,
		"normal_strength": 1.0, "sheen": 0.4}))
	mats.append(_fabric("M_Sweater", Color(0.38, 0.08, 0.07), "Fabric034", {"tex_scale": 5.0, "tex_mean": 0.36,
		"tex_contrast": 1.5, "normal_strength": 1.6, "sheen": 0.5}))
	mats.append(_std("M_PlasticRed", Color(0.52, 0.06, 0.04), 0.35))
	mats.append(_std("M_PlasticWhite", Color(0.8, 0.79, 0.74), 0.35))
	mats.append(_tex_std("M_BookletRed", Color(0.42, 0.05, 0.035), "Leather033A", {"scale": 12.0, "rough": 0.55,
		"nstrength": 0.6}))
	mats.append(_tex_std("M_BookletGreen", Color(0.13, 0.24, 0.17), "Leather033A", {"scale": 12.0, "rough": 0.55,
		"nstrength": 0.6}))
	mats.append(_std("M_Briquette", Color(0.045, 0.045, 0.045), 0.95))
	var ground := _std("M_WetGround", Color(0.05, 0.05, 0.05), 0.12)
	ground.metallic_specular = 0.7
	mats.append(ground)
	mats.append(_std("M_Brick", Color(0.22, 0.12, 0.09), 0.85))
	mats.append(_std("M_CraneRust", Color(0.12, 0.07, 0.05), 0.75, 0.3))
	mats.append(_std("M_ShipHull", Color(0.08, 0.08, 0.085), 0.6, 0.2))
	mats.append(_std("M_StreetLampGlass", Color(1.0, 0.6, 0.3), 0.3, 0.0, Color(1.0, 0.55, 0.2), 2.5))
	mats.append(_std("M_NeighborWindow", Color(0.6, 0.45, 0.25), 0.5, 0.0, Color(1.0, 0.62, 0.3), 1.4))
	mats.append(_std("M_Coil", Color(0.45, 0.4, 0.36), 0.5, 0.7))
	mats.append(_std("M_Noodle", Color(0.8, 0.7, 0.45), 0.6))
	mats.append(_std("M_Cigarette", Color(0.82, 0.78, 0.7), 0.85))
	mats.append(_std("M_CigFilter", Color(0.7, 0.45, 0.22), 0.85))
	mats.append(_std("M_PagerLcd", Color(0.45, 0.5, 0.4), 0.3))
	# ---- 办事处
	var lamp_green := _std("M_LampGreen", Color(0.03, 0.2, 0.08), 0.1)
	lamp_green.emission_enabled = true
	lamp_green.emission = Color(0.1, 0.5, 0.2)
	lamp_green.emission_energy_multiplier = 0.3
	lamp_green.clearcoat_enabled = true
	mats.append(lamp_green)
	mats.append(_paint("M_SafeGreen", Color(0.13, 0.2, 0.15), {"rough": 0.4, "metal": 0.2, "edge": 1.2, "rust": 0.1,
		"smudge": 0.8, "dust": 0.3, "wear": Color(0.4, 0.4, 0.38), "floor_h": 0.0, "floor": 0.4}))
	mats.append(_std("M_InkPaste", Color(0.48, 0.025, 0.02), 0.75))
	var water := ShaderMaterial.new()
	water.resource_name = "M_HarborWater"
	water.shader = HARBOR
	mats.append(water)
	mats.append(_std("M_ShipWhite", Color(0.55, 0.55, 0.52), 0.7, 0.1))
	mats.append(_std("M_Hill", Color(0.09, 0.11, 0.1), 0.95))
	mats.append(_fabric("M_Tarp", Color(0.14, 0.2, 0.17), "Fabric036", {"tex_scale": 0.8, "tex_mean": 0.49,
		"normal_strength": 1.2, "sheen": 0.1, "roughness": 0.55, "stain_amount": 0.4}))
	mats.append(_std("M_NavLight", Color(1.0, 0.2, 0.1), 0.3, 0.0, Color(1.0, 0.15, 0.08), 6.0))
	mats.append(_tex_std("M_ScrollPaper", Color(0.86, 0.82, 0.7), "Fabric045", {"rough": 0.95, "scale": 8.0,
		"nstrength": 0.2}))
	mats.append(_std("M_RottenFruit", Color(0.22, 0.13, 0.05), 0.55))
