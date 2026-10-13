class_name CrewLook
extends RefCounted
## 船员的样子（捏脸）：性别、脸型（Vitruvian 的捏脸形态）、肤色、眉毛、瞳色、睫毛、化妆、胡茬……
## 存成一个 Dictionary：本机的存在 settings.cfg（Net.local_look），联机时跟名字、岗位一起放在名单里广播。
## apply() 把它套到船员身体的模型上（assets/models/crew_body_m.glb / crew_body_f.glb，见 blender/scripts/gen_crew.py）：
## 设头和口腔的形态键（ID_xxx）、换脸 / 眼睛 / 睫毛 / 身体的材质参数（手的颜色跟着脸的肤色走）。
## 模型和贴图见 blender/scripts/gen_head_vitruvian.py。

const TEX := "res://assets/textures/crew/"
const BODY_SCENES := {"m": "res://assets/models/crew_body_m.glb", "f": "res://assets/models/crew_body_f.glb"}
const SKIN_SHADER := preload("res://assets/shaders/crew_skin.gdshader")
const EYE_SHADER := preload("res://assets/shaders/crew_sclera.gdshader")
const TEARLINE_SHADER := preload("res://assets/shaders/crew_tearline.gdshader")
const HAIR_SHADER := preload("res://assets/shaders/crew_hair.gdshader")
const SHELL_SHADER := preload("res://assets/shaders/crew_hair_shell.gdshader")
const LASH_SHADER := preload("res://assets/shaders/crew_lash.gdshader")
const OCCLUSION_SHADER := preload("res://assets/shaders/crew_eye_occlusion.gdshader")
const BODY_SHADER := preload("res://assets/shaders/crew_body.gdshader")
## 眉毛那一片 UV（Blender 的 UV，gen_head_vitruvian.py 打印的「brows: UV」）
const BROW_RECT := Vector4(0.328, 0.597, 0.672, 0.669)
const BROW_STYLES := 14
## 浅、深肤色贴图两颊的平均色（线性），身体贴图里手的平均色（线性）：手按这两个对色
const SKIN_LIGHT := Vector3(0.4703, 0.2369, 0.2077)
const SKIN_DARK := Vector3(0.0761, 0.0442, 0.0359)
const HAND := {"m": Vector3(0.5159, 0.2676, 0.1882), "f": Vector3(0.4176, 0.3276, 0.1897)}

## 捏脸滑杆：[分组, 形态（Vitruvian 的 L2 形态名，模型里是 ID_ 加这个名字）, 名字, 最小, 最大]
const SLIDERS := [
	["脸型", "Macro_FaceWidth", "脸宽", -1.0, 1.0],
	["脸型", "Macro_VLine", "V 脸", -1.0, 1.0],
	["脸型", "Macro_CheekSlim", "瘦脸颊", -1.0, 1.0],
	["脸型", "Macro_ChinLength", "下巴长", -1.0, 1.0],
	["脸型", "Macro_MidfaceShort", "中庭短", -1.0, 1.0],
	["脸型", "Fat_Face", "脸部胖瘦", 0.0, 1.0],
	["脸型", "Cheeks_BuccalFat", "脸颊饱满", -1.0, 1.0],
	["脸型", "Face_Zygomatic_Bone", "颧骨宽窄", -1.0, 1.0],
	["脸型", "Cheeks_CheeksBonePositionZ", "颧骨高低", -1.0, 1.0],
	["脸型", "Cheeks_UpperCheek_Bone", "苹果肌", -1.0, 1.0],
	["脸型", "Jaw_Width", "下颌宽窄", -1.0, 1.0],
	["脸型", "Jaw_Mandible_GonialAngle", "下颌角", -1.0, 1.0],
	["脸型", "Jaw_Definition", "下颌线", -1.0, 1.0],
	["脸型", "Chin_Height", "下巴长短", -1.0, 1.0],
	["脸型", "Chin_Width", "下巴宽窄", -1.0, 1.0],
	["脸型", "Chin_SecondaryWidth", "下巴尖圆", -1.0, 1.0],
	["脸型", "Chin_Portrusion", "下巴前后", -1.0, 1.0],
	["脸型", "Face_FrontalBone", "额头", -1.0, 1.0],
	["脸型", "Face_FrontalBone_BrowRidge", "眉骨", -1.0, 1.0],
	["脸型", "Face_Puffy", "浮肿", 0.0, 1.0],
	["眼睛", "Macro_EyeScale", "眼睛大小", -1.0, 1.0],
	["眼睛", "Macro_EyeTilt", "眼角上挑", -1.0, 1.0],
	["眼睛", "Eyes_Size", "眼球大小", -1.0, 1.0],
	["眼睛", "Eyes_Distance", "眼距", -1.0, 1.0],
	["眼睛", "Eyes_VerticalShift", "高低", -1.0, 1.0],
	["眼睛", "Eyes_EyelidsAngle", "眼角上扬", -1.0, 1.0],
	["眼睛", "Eyes_EyelidsAngle2", "眼尾", 0.0, 1.0],
	["眼睛", "Eyes_Eyelid_Monolid", "单眼皮", 0.0, 1.0],
	["眼睛", "Eyes_Eyelid_Hooded", "内双", 0.0, 1.0],
	["眼睛", "Eyes_EyelidsCrease", "双眼皮", -1.0, 1.0],
	["眼睛", "Eyes_UpperLidOpenness", "睁眼", 0.0, 1.0],
	["眼睛", "Eyes_LowerLidOpenness", "下眼睑", -1.0, 1.0],
	["眼睛", "Eyes_EyeBagsSize", "卧蚕眼袋", -1.0, 1.0],
	["眼睛", "Face_EyeSocket_Protrusion", "眼窝", -1.0, 1.0],
	["眼睛", "Eyes_EyebrowsAngle", "眉形角度", -1.0, 1.0],
	["眼睛", "Eyes_EyebrowsDroop", "眉尾", -1.0, 1.0],
	["鼻子", "Macro_NoseSlim", "鼻子窄", -1.0, 1.0],
	["鼻子", "Macro_NoseShort", "鼻子短", -1.0, 1.0],
	["鼻子", "Nose_BridgeProminence", "鼻梁高低", -1.0, 1.0],
	["鼻子", "Nose_NasalBone", "鼻骨", -1.0, 1.0],
	["鼻子", "Nose_Width", "鼻翼宽窄", -1.0, 1.0],
	["鼻子", "Nose_NostrilSize", "鼻孔", -1.0, 1.0],
	["鼻子", "Nose_NoseHeight", "鼻子长短", -1.0, 1.0],
	["鼻子", "Nose_Protrusion", "挺拔", -1.0, 1.0],
	["鼻子", "Nose_NasalAngle", "鼻头上翘", -1.0, 1.0],
	["鼻子", "Nose_Tip_Protrusion", "鼻尖", -1.0, 1.0],
	["鼻子", "Nose_Tip_Z", "鼻头高低", -1.0, 1.0],
	["鼻子", "Nose_Flatness", "扁平", 0.0, 1.0],
	["嘴", "Macro_LipFull", "嘴唇饱满", -1.0, 1.0],
	["嘴", "Macro_MouthSmall", "嘴小", -1.0, 1.0],
	["嘴", "Mouth_Lips_Height", "唇厚", -1.0, 1.0],
	["嘴", "Mouth_Lips_Length", "嘴宽", -1.0, 1.0],
	["嘴", "Mouth_Lips_UpperLipArch", "唇峰", 0.0, 1.0],
	["嘴", "Mouth_Lips_UpperLipDepth", "上唇", -1.0, 1.0],
	["嘴", "Mouth_Lips_BottomLipDepth", "下唇", -1.0, 1.0],
	["嘴", "Mouth_Lips_UpperAngle", "上唇弧度", -1.0, 1.0],
	["嘴", "Mouth_Lips_LowerAngle", "嘴角", -1.0, 1.0],
	["嘴", "Mouth_PhiltrumHeight", "人中", -1.0, 1.0],
	["头", "Ears_Height", "耳朵大小", -1.0, 1.0],
	["头", "Ears_Protrusion", "招风耳", -1.0, 1.0],
	["头", "Ears_Lobe", "耳垂", -1.0, 1.0],
	["头", "Head_TopScalpPotrusion", "头顶", -1.0, 1.0],
	["头", "Head_BackScalp_Protrusion", "后脑", -1.0, 1.0],
	["头", "Head_SideScalp_Protrusion", "头宽", -1.0, 1.0],
	["头", "Neck_AdamsApple", "喉结", 0.0, 1.0],
	["头", "Age_Old", "年纪", 0.0, 1.0],
	["头", "Generic_Assymetry", "不对称", -1.0, 1.0],
]
## 瞳色：[名字, 内圈, 外圈]
const IRIS_COLORS := [
	["深棕", Color(0.24, 0.13, 0.065), Color(0.075, 0.045, 0.03)],
	["棕", Color(0.42, 0.25, 0.1), Color(0.16, 0.095, 0.05)],
	["琥珀", Color(0.62, 0.4, 0.13), Color(0.3, 0.18, 0.06)],
	["榛", Color(0.48, 0.36, 0.15), Color(0.2, 0.26, 0.15)],
	["绿", Color(0.36, 0.47, 0.22), Color(0.12, 0.22, 0.12)],
	["灰蓝", Color(0.47, 0.54, 0.6), Color(0.2, 0.26, 0.32)],
	["蓝", Color(0.36, 0.52, 0.72), Color(0.12, 0.2, 0.36)],
]
## 发型：[模型里的名字, 名字]。每个发型一块层壳 Crew_Shell_xxx（头皮往外复制几层撒发丝：寸头全靠它，别的拿它打底），
## 除了寸头都有发片 Crew_Hair_xxx；光头都没有
const HAIR_STYLES := [["none", "光头"], ["buzz", "寸头"], ["crop", "碎短发"], ["slick", "短发后梳"],
	["bob", "波波头"], ["back", "长发后梳"], ["long", "长直发"]]
const HAIR_COLORS := [
	["黑", Color(0.03, 0.026, 0.024)],
	["深棕", Color(0.085, 0.058, 0.044)],
	["棕", Color(0.2, 0.12, 0.07)],
	["栗色", Color(0.3, 0.14, 0.07)],
	["浅棕", Color(0.42, 0.3, 0.18)],
	["金", Color(0.75, 0.6, 0.38)],
	["红棕", Color(0.45, 0.15, 0.06)],
	["灰白", Color(0.55, 0.53, 0.5)],
]
const LIP_COLORS := [
	["豆沙", Color(0.62, 0.33, 0.33)],
	["裸粉", Color(0.76, 0.46, 0.43)],
	["正红", Color(0.6, 0.08, 0.1)],
	["珊瑚", Color(0.85, 0.38, 0.3)],
	["梅子", Color(0.42, 0.12, 0.2)],
]
const SHADOW_COLORS := [
	["大地", Color(0.55, 0.4, 0.32)],
	["烟灰", Color(0.36, 0.34, 0.34)],
	["玫瑰", Color(0.66, 0.4, 0.4)],
	["暖橘", Color(0.72, 0.46, 0.3)],
]
## 外观里除了形态以外的项：[键, 最小, 最大, 默认]（整数项最小最大是下标范围）
const PARAMS := {
	"gender": [0.0, 1.0, 1.0],
	"skin": [0.0, 1.0, 0.2],
	"warm": [-1.0, 1.0, 0.1],
	"flush": [0.0, 1.0, 0.3],
	"beard": [0.0, 1.0, 0.0],
	"brow_dens": [0.0, 1.5, 1.0],
	"lash": [0.3, 1.5, 1.0],
	"liner": [0.0, 1.0, 0.0],
	"shadow": [0.0, 1.0, 0.0],
	"blush": [0.0, 1.0, 0.0],
	"lip": [0.0, 1.0, 0.0],
}
const INDICES := {"brow": BROW_STYLES, "eye": 7, "hair": 7, "hair_col": 8, "lip_col": 5, "shadow_col": 4}

## 预设：只写和默认值不一样的（性别、形态、参数）。船员来自好几个国家（docs/design.md「中文元素」）
const PRESETS := [
	{"name": "清和", "sex": "f", "shape": {"Eyes_Size": 0.35, "Eyes_Eyelid_Hooded": 0.25, "Eyes_EyelidsCrease": 0.2,
		"Eyes_EyelidsAngle": 0.15, "Eyes_EyeBagsSize": 0.3, "Nose_Width": -0.5, "Nose_BridgeProminence": 0.25,
		"Nose_NasalAngle": 0.25, "Nose_Tip_Protrusion": 0.1, "Nose_NostrilSize": -0.3, "Nose_NoseHeight": -0.1,
		"Jaw_Width": -0.5, "Jaw_Mandible_GonialAngle": -0.2, "Chin_Width": -0.4, "Chin_Height": 0.12,
		"Chin_SecondaryWidth": -0.3, "Cheeks_BuccalFat": -0.1, "Face_Zygomatic_Bone": -0.3, "Cheeks_UpperCheek_Bone": 0.2,
		"Face_FrontalBone": 0.15, "Mouth_Lips_Height": 0.25, "Mouth_Lips_Length": -0.15, "Mouth_Lips_UpperLipArch": 0.5,
		"Mouth_Lips_LowerAngle": 0.15, "Mouth_PhiltrumHeight": -0.2}, "skin": 0.12, "warm": 0.15, "flush": 0.35,
		"brow": 2, "eye": 0, "hair": 6, "liner": 0.35, "shadow": 0.25, "blush": 0.3, "lip": 0.5, "lip_col": 0},
	{"name": "若兰", "sex": "f", "shape": {"Eyes_Size": 0.3, "Eyes_EyelidsCrease": 0.45, "Eyes_EyelidsAngle": 0.3,
		"Eyes_EyelidsAngle2": 0.3, "Nose_Width": -0.4, "Nose_BridgeProminence": 0.35, "Nose_Tip_Protrusion": 0.15,
		"Nose_NostrilSize": -0.25, "Jaw_Width": -0.4, "Chin_Width": -0.3, "Chin_Height": 0.05, "Cheeks_BuccalFat": 0.05,
		"Cheeks_UpperCheek_Bone": 0.3, "Mouth_Lips_Height": 0.35, "Mouth_Lips_UpperLipArch": 0.6,
		"Mouth_Lips_LowerAngle": 0.1}, "skin": 0.1, "warm": 0.1, "flush": 0.4, "brow": 4, "eye": 1, "hair": 4,
		"hair_col": 1, "liner": 0.5, "shadow": 0.35, "shadow_col": 2, "blush": 0.35, "lip": 0.6, "lip_col": 2},
	{"name": "远山", "sex": "m", "shape": {"Jaw_Definition": 0.5, "Jaw_Width": 0.1, "Chin_Height": 0.1, "Chin_Width": 0.1,
		"Nose_BridgeProminence": 0.35, "Nose_Width": -0.2, "Eyes_Eyelid_Hooded": 0.4, "Eyes_EyelidsAngle": 0.1,
		"Face_FrontalBone_BrowRidge": 0.25, "Cheeks_BuccalFat": -0.35, "Mouth_Lips_Height": -0.1}, "skin": 0.22,
		"warm": 0.25, "flush": 0.15, "beard": 0.15, "brow": 6, "eye": 0, "hair": 3},
	{"name": "青川", "sex": "m", "shape": {"Eyes_Size": 0.15, "Eyes_EyelidsCrease": 0.25, "Jaw_Width": -0.15,
		"Jaw_Definition": 0.3, "Chin_Width": -0.1, "Nose_BridgeProminence": 0.25, "Nose_Width": -0.3,
		"Cheeks_BuccalFat": -0.2, "Mouth_Lips_Height": 0.05, "Face_FrontalBone": 0.1}, "skin": 0.17, "warm": 0.2,
		"flush": 0.25, "beard": 0.05, "brow": 11, "eye": 0, "hair": 2},
	{"name": "伊琳娜", "sex": "f", "shape": {"Eyes_Size": 0.2, "Eyes_EyelidsCrease": 0.4, "Nose_BridgeProminence": 0.4,
		"Nose_Width": -0.3, "Nose_Tip_Protrusion": 0.2, "Jaw_Width": -0.3, "Chin_Height": 0.15, "Cheeks_UpperCheek_Bone": 0.3,
		"Face_Zygomatic_Bone": 0.2, "Mouth_Lips_Height": 0.3, "Mouth_Lips_UpperLipArch": 0.5}, "skin": 0.02,
		"warm": -0.2, "flush": 0.4, "brow": 9, "eye": 5, "hair": 5, "hair_col": 4, "liner": 0.2, "shadow": 0.2,
		"shadow_col": 1, "blush": 0.2, "lip": 0.3, "lip_col": 1},
	{"name": "马库斯", "sex": "m", "shape": {"Jaw_Width": 0.35, "Jaw_Definition": 0.5, "Chin_Width": 0.2,
		"Face_FrontalBone_BrowRidge": 0.4, "Nose_BridgeProminence": 0.35, "Nose_Protrusion": 0.2,
		"Eyes_EyelidsCrease": 0.3, "Cheeks_BuccalFat": -0.4}, "skin": 0.05, "warm": 0.0, "flush": 0.3,
		"beard": 0.45, "brow": 12, "eye": 3, "hair": 2, "hair_col": 2},
	{"name": "阿玛拉", "sex": "f", "shape": {"Eyes_Size": 0.25, "Nose_Width": 0.1, "Nose_NasalAngle": 0.2,
		"Mouth_Lips_Height": 0.55, "Mouth_Lips_Length": 0.1, "Jaw_Width": -0.3, "Chin_Width": -0.2,
		"Cheeks_UpperCheek_Bone": 0.35}, "skin": 0.8, "warm": 0.1, "flush": 0.2, "brow": 1, "eye": 0, "hair": 4,
		"liner": 0.4, "shadow": 0.2, "shadow_col": 3, "lip": 0.3, "lip_col": 4},
	{"name": "拉吉夫", "sex": "m", "shape": {"Eyes_Size": 0.15, "Eyes_EyelidsCrease": 0.3, "Nose_BridgeProminence": 0.3,
		"Nose_Tip_Protrusion": 0.2, "Jaw_Definition": 0.3, "Face_FrontalBone_BrowRidge": 0.25,
		"Mouth_Lips_Height": 0.15}, "skin": 0.5, "warm": 0.25, "flush": 0.1, "beard": 0.55, "brow": 13, "eye": 0,
		"hair": 1},
]

static var _tex := {}


## 某个性别的默认样子（性别特征拉满，其余都在中间）
static func default_look(sex := "m") -> Dictionary:
	var l := {"sex": sex, "shape": {}, "brow": 10 if sex == "m" else 2, "eye": 0, "hair": 2 if sex == "m" else 4,
		"hair_col": 0, "lip_col": 0, "shadow_col": 0}
	for k: String in PARAMS:
		l[k] = PARAMS[k][2]
	if sex == "m":
		l.beard = 0.15
	return l


## 预设 i（PRESETS 里只写了和默认不一样的）
static func preset(i: int) -> Dictionary:
	var p: Dictionary = PRESETS[clampi(i, 0, PRESETS.size() - 1)]
	var l := default_look(p.sex)
	for k: String in p:
		if k == "shape":
			l.shape = (p.shape as Dictionary).duplicate()
		elif k != "name":
			l[k] = p[k]
	return l


## 联机收到的、存档里读出来的样子：缺的补上默认，超出范围的夹回去，不认识的丢掉
static func sanitize(v: Variant) -> Dictionary:
	var src: Dictionary = v if v is Dictionary else {}
	var sex: String = "f" if String(src.get("sex", "m")) == "f" else "m"
	var l := default_look(sex)
	for k: String in PARAMS:
		if src.has(k):
			l[k] = clampf(float(src[k]), PARAMS[k][0], PARAMS[k][1])
	for k: String in INDICES:
		if src.has(k):
			l[k] = clampi(int(src[k]), 0, INDICES[k] - 1)
	var shape: Dictionary = src.get("shape", {}) if src.get("shape") is Dictionary else {}
	for s: Array in SLIDERS:
		if shape.has(s[1]):
			var x := clampf(float(shape[s[1]]), s[3], s[4])
			if absf(x) > 0.001:
				l.shape[s[1]] = x
	return l


## 随机一个样子：从某个同性别的预设出发，每个形态随机挪一点
static func random_look(sex: String, rng: RandomNumberGenerator) -> Dictionary:
	var pool := []
	for i in PRESETS.size():
		if PRESETS[i].sex == sex:
			pool.append(i)
	var l := preset(pool[rng.randi() % pool.size()])
	for s: Array in SLIDERS:
		var x: float = l.shape.get(s[1], 0.0) + rng.randfn(0.0, 0.18)
		l.shape[s[1]] = clampf(x, s[3], s[4])
	l.shape["Age_Old"] = clampf(rng.randfn(0.0, 0.15), 0.0, 1.0)
	l.skin = clampf(l.skin + rng.randfn(0.0, 0.05), 0.0, 1.0)
	l.brow = rng.randi() % BROW_STYLES
	return sanitize(l)


static func body_scene(look: Dictionary) -> PackedScene:
	return load(BODY_SCENES["f" if look.get("sex", "m") == "f" else "m"]) as PackedScene


## 把样子套到身体模型（crew_body_*.glb 实例化出来的）上：形态键、材质参数
static func apply(model: Node3D, look: Dictionary) -> void:
	var l := sanitize(look)
	var vals := {}
	for s: Array in SLIDERS:
		vals[s[1]] = float(l.shape.get(s[1], 0.0))
	vals["Gender_FemaleHeadOnly"] = l.gender if l.sex == "f" else 0.0
	vals["Gender_MaleHeadOnly"] = l.gender if l.sex == "m" else 0.0
	for mi in head_meshes(model):
		for k: String in vals:
			var i := mi.find_blend_shape_by_name("ID_" + k)
			if i >= 0:
				mi.set_blend_shape_value(i, vals[k])
	_apply_materials(model, l)


## 头上的几块网格（脸、口腔、头发）
static func head_meshes(model: Node) -> Array[MeshInstance3D]:
	var out: Array[MeshInstance3D] = []
	for n in model.find_children("Crew_*", "MeshInstance3D", true, false):
		if String(n.name) != "Crew_Body":
			out.append(n as MeshInstance3D)
	return out


static func _t(name: String) -> Texture:
	if not _tex.has(name):
		_tex[name] = load(TEX + name + ".png")
	return _tex[name]


## 每个模型一套材质（第一次套的时候建，存在 meta 里），之后只改参数
static func _apply_materials(model: Node3D, l: Dictionary) -> void:
	var mats: Dictionary = model.get_meta("crew_mats", {})
	if mats.is_empty():
		mats = _build_materials(model)
		model.set_meta("crew_mats", mats)
	var hair: Color = HAIR_COLORS[l.hair_col][1]
	var style: String = HAIR_STYLES[l.hair][0]
	for mi in head_meshes(model):
		var nm := String(mi.name)
		if nm.begins_with("Crew_Hair_") or nm.begins_with("Crew_Shell_"):
			mi.visible = nm == "Crew_Hair_" + style or nm == "Crew_Shell_" + style
	(mats.hair as ShaderMaterial).set_shader_parameter("hair_color", hair)
	var shell: ShaderMaterial = mats.shell
	shell.set_shader_parameter("hair_color", hair)
	# 层壳发丝一段多长：短发竖着的短，顺下来、梳过去的长
	shell.set_shader_parameter("segment", {"buzz": 2.0, "crop": 3.0, "slick": 16.0}.get(style, 12.0))
	shell.set_shader_parameter("base_layer", 0.0 if style == "buzz" else 1.0)
	shell.set_shader_parameter("cover", 0.45 if style == "buzz" else 1.0)
	var skin: ShaderMaterial = mats.skin
	# 头皮：寸头是头皮上一层发茬；别的发型压暗一点（层壳的发根盖住大半，这里接上发际线外那圈、管发片之间的缝），发际线下压暗
	skin.set_shader_parameter("scalp_hair", 0.0 if style == "none" else (1.0 if style == "buzz" else 0.6))
	skin.set_shader_parameter("hairline_ao", 0.0 if style in ["none", "buzz"] else 1.0)
	skin.set_shader_parameter("melanin", l.skin)
	skin.set_shader_parameter("warmth", l.warm)
	skin.set_shader_parameter("flush", l.flush)
	skin.set_shader_parameter("beard", l.beard if l.sex == "m" else 0.0)
	skin.set_shader_parameter("hair_color", hair)
	skin.set_shader_parameter("brow_color", hair.darkened(0.1))
	skin.set_shader_parameter("brow_style", float(l.brow))
	skin.set_shader_parameter("brow_density", l.brow_dens)
	skin.set_shader_parameter("age_detail", float(l.shape.get("Age_Old", 0.0)))
	skin.set_shader_parameter("liner", l.liner)
	skin.set_shader_parameter("shadow", l.shadow)
	skin.set_shader_parameter("shadow_color", SHADOW_COLORS[l.shadow_col][1])
	skin.set_shader_parameter("blush", l.blush)
	skin.set_shader_parameter("lip", l.lip)
	skin.set_shader_parameter("lip_color", LIP_COLORS[l.lip_col][1])
	skin.set_shader_parameter("roughness_mul", 0.95 if l.sex == "f" else 1.05)
	var eye: ShaderMaterial = mats.eye
	eye.set_shader_parameter("iris_inner", IRIS_COLORS[l.eye][1])
	eye.set_shader_parameter("iris_outer", IRIS_COLORS[l.eye][2])
	(mats.lash as ShaderMaterial).set_shader_parameter("density", l.lash)
	(mats.lash as ShaderMaterial).set_shader_parameter("lash_color", hair.darkened(0.3))
	# 手：身体贴图里手的平均色对到脸颊的平均色（线性，冷暖跟着脸）
	var face := SKIN_LIGHT.lerp(SKIN_DARK, l.skin)
	if l.warm > 0.0:
		face *= Vector3.ONE.lerp(Vector3(1.03, 1.0, 0.86), l.warm)
	else:
		face *= Vector3.ONE.lerp(Vector3(1.04, 0.95, 1.0), -l.warm)
	var hand: Vector3 = HAND[l.sex]
	if mats.has("body"):
		(mats.body as ShaderMaterial).set_shader_parameter("skin_tint", face / hand)


static func _build_materials(model: Node3D) -> Dictionary:
	var mats := {}
	var skin := ShaderMaterial.new()
	skin.shader = SKIN_SHADER
	for k in ["skin_light", "skin_dark", "skin_crc", "skin_normal", "skin_mask", "skin_makeup"]:
		skin.set_shader_parameter(k, _t(k))
	skin.set_shader_parameter("pore_normal", _t("skin_pores"))
	skin.set_shader_parameter("brows", _t("brows"))
	skin.set_shader_parameter("brow_rect", BROW_RECT)
	mats.skin = skin
	# 眼球：眼白、虹膜、角膜都在眼白那块网格上画（crew_sclera.gdshader）；原来的虹膜、瞳孔网格藏在角膜后面，
	# 给个黑的就行；角膜外面那层泪膜不画
	var eye := ShaderMaterial.new()
	eye.shader = EYE_SHADER
	eye.set_shader_parameter("sclera_tex", _t("sclera"))
	eye.set_shader_parameter("sclera_rough", _t("sclera_rough"))
	eye.set_shader_parameter("iris_tex", _t("iris"))
	mats.eye = eye
	var dark := StandardMaterial3D.new()
	dark.albedo_color = Color(0.01, 0.008, 0.008)
	var hidden := StandardMaterial3D.new()
	hidden.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	hidden.albedo_color = Color(0, 0, 0, 0)
	var tear := ShaderMaterial.new()
	tear.shader = TEARLINE_SHADER
	tear.render_priority = 2
	var hair := ShaderMaterial.new()
	hair.shader = HAIR_SHADER
	hair.set_shader_parameter("hair_tex", _t("hair"))
	mats.hair = hair
	var shell := ShaderMaterial.new()
	shell.shader = SHELL_SHADER
	mats.shell = shell
	var lash := ShaderMaterial.new()
	lash.shader = LASH_SHADER
	mats.lash = lash
	var occ := ShaderMaterial.new()
	occ.shader = OCCLUSION_SHADER
	occ.render_priority = 1
	var mouth := StandardMaterial3D.new()
	mouth.albedo_texture = _t("mouth")
	mouth.roughness_texture = _t("mouth_rough")
	mouth.roughness_texture_channel = BaseMaterial3D.TEXTURE_CHANNEL_RED
	mouth.subsurf_scatter_enabled = true
	mouth.subsurf_scatter_strength = 0.3
	var by_name := {"Crew_Skin": skin, "Crew_Sclera": eye, "Crew_Iris": dark, "Crew_Pupil": dark,
		"Crew_Lashes": lash, "Crew_EyeOcclusion": occ, "Crew_Tearline": tear, "Crew_Aqueous": hidden,
		"Crew_Mouth": mouth, "Crew_Hair": hair, "Crew_Shell": shell}
	for mi in head_meshes(model):
		for i in mi.mesh.get_surface_count():
			var m := mi.mesh.surface_get_material(i)
			if m and by_name.has(m.resource_name):
				mi.set_surface_override_material(i, by_name[m.resource_name])
	# 身体：贴图从导入的材质里拿，换成能调手的肤色的着色器
	var body := model.find_child("Crew_Body", true, false) as MeshInstance3D
	if body:
		var old := body.mesh.surface_get_material(0) as BaseMaterial3D
		var bm := ShaderMaterial.new()
		bm.shader = BODY_SHADER
		if old:
			bm.set_shader_parameter("albedo_tex", old.albedo_texture)
			bm.set_shader_parameter("normal_tex", old.normal_texture)
		body.set_surface_override_material(0, bm)
		mats.body = bm
	return mats
