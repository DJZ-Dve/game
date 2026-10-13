extends Node3D
## 调试：在捏脸场景里试 TressFX 发丝（GDExtension，addons/tressfx；源码 github.com/ismailivanov/TressFX-Godot，MIT）。
## 把插件示例的马尾辫（AMD 的 Ruby 头，单位厘米，头比真人大三倍多）缩放后挂到船员的 Bip01 Head 上：
## 寸头那块层壳（Crew_Shell_buzz，贴着头皮）的包围盒对准马尾辫发根的包围盒——宽、深的比例取平均当缩放，
## 左右、前后对中，头顶对头顶；碰撞体照示例 ponytail.tscn 的四个（头、后脑、脖子、躯干）一起缩放。
## 只是对位用：发型是给 Ruby 的头梳的，套到别人头上难免有的地方离头皮远、有的地方扎进去。
## 捏脸场景加 --cc-tressfx 打开（character_creator.gd 把本节点挂到身体下面）；配 --cc-set=hair:1 换成寸头，免得原来的发片挡着。
##   --cc-tfx-fit=倍数,dx,dy,dz  手调：倍数乘在自动算的缩放上，dx dy dz 是世界坐标里再挪多少米
##   --cc-tfx-color=look|auburn|r,g,b  发色（默认捏脸的发色；auburn 是示例的红棕）
##   --cc-tfx-follow=N  每根主发丝再生成几根跟随的（马尾辫默认 3，和示例一样：4325 + 701 根主发丝 × 4 ≈ 2 万根；船员的发型见下）
##   --cc-tfx-shadow=off  头发不进阴影贴图（示例是开着的）
##   --cc-tfx-shader=plugin|路径  发丝的着色器：默认 assets/shaders/crew_hair_strand.gdshader（Marschner），
##       plugin 是插件自带的 tressfx_strand.gdshader（Kajiya-Kay，参数用 _material() 里调过的那套），也可以给别的 res:// 路径
##   --cc-tfx-sim=参数:值,...  改模拟参数（gravity、global_stiffness、global_range、damping……；
##       gravity:0,global_stiffness:1,global_range:1 就是不动的梳好的样子）
##   --cc-tfx-mat=参数:值,...  改发丝材质的参数（调光泽用：crew_hair_strand 的 roughness、specular、scatter……，
##       插件那份的 k_spec1、spec_exp1、k_diffuse……）
##   --cc-gpu --cc-tfx-ab[=shader]  量开销：同一个进程里轮流开关头发，或者轮流换着色器（见 _ab）
## 船员自己的发型（不用 Ruby 的马尾辫）：--cc-tfx-style=crop|slick|bob|back|long，读 tools/gen_tfx_hair.py 照发片长出来的整头发丝
## （.tmp/tfx/styles/<f|m>_<发型>.tfx，网格坐标，跟发片一样按头骨的绑定姿势挂到头上，不用缩放对位）。每根的粗细、深浅在
## 发丝 UV 里（着色器的 strand_attrs）。发丝细（半径 0.18 毫米，这个距离不到一个像素宽），每根再带 2 根跟随的（1.2 毫米以内，
## 三根一小撮），一共八万多根：粗而少的发丝像笔刷刷的一道道（--cc-tfx-follow=N、--cc-tfx-radius=米、--cc-tfx-mat=fiber_radius:米 改）。
## 原来的发片藏起来；这个发型的头皮层壳只留最里一层，换成 crew_scalp_tint.gdshader 把头皮染成发根色（发际线渐淡，没有
## 层壳那道硬边；--cc-tfx-shell=on 用原来的层壳，off 不要）。碰撞体：头用皮肤网格本身（--cc-tfx-headcol=hull 换成凸包），
## 脖子、肩、胸按骨骼摆胶囊

const DIR := "res://addons/tressfx/demo/ponytail/"
const SHADER := "res://assets/shaders/crew_hair_strand.gdshader"
const PLUGIN_SHADER := "res://addons/tressfx/shaders/tressfx_strand.gdshader"
## 马尾辫发根的包围盒，米（文件里是厘米，乘 import_scale 0.01 以后）
const ROOT_MIN := Vector3(-0.2583, 0.6236, -0.3700)
const ROOT_MAX := Vector3(0.2565, 1.1996, 0.2632)
## 示例的碰撞体（同一个坐标系）：[半径, 胶囊高（0 是球）, 位置, 横着放, 距离场格数]
const COLLIDERS := [
	[0.26, 0.62, Vector3(0, 0.9, -0.02), false, 48],    # 头
	[0.22, 0.0, Vector3(0, 0.83, -0.14), false, 40],    # 后脑
	[0.17, 0.6, Vector3(0, 0.42, 0), false, 32],        # 脖子
	[0.44, 1.7, Vector3(0, -0.15, 0), true, 48],        # 躯干
]
## 示例两块头发的模拟参数（ponytail.tscn）
const SIM := {
	"head": {"vsp_coeff": 0.758, "local_stiffness": 0.4, "global_stiffness": 0.3, "global_range": 0.4,
		"length_iterations": 3, "damping": 0.2, "gravity": 1.0},
	"tail": {"vsp_coeff": 0.25, "local_stiffness": 0.35, "global_stiffness": 0.06, "global_range": 0.2,
		"length_iterations": 3, "damping": 0.1, "gravity": 1.5},
}

## 船员自己的发型的模拟参数。捏脸时人基本不动，要的是梳好的样子立得住：短发几乎整根拉回原形，长发只拉住前半截、让发梢自己垂
const STYLES := {
	"crop": {"global_stiffness": 0.9, "global_range": 1.0, "local_stiffness": 0.9, "damping": 0.3},
	"slick": {"global_stiffness": 0.8, "global_range": 1.0, "local_stiffness": 0.9, "damping": 0.3},
	"bob": {"global_stiffness": 0.6, "global_range": 0.8, "local_stiffness": 0.9, "damping": 0.2},
	"back": {"global_stiffness": 0.5, "global_range": 0.7, "local_stiffness": 0.9, "damping": 0.2},
	"long": {"global_stiffness": 0.35, "global_range": 0.5, "local_stiffness": 0.9, "damping": 0.15},
}
## 发际线：头皮染色从发量多少染到多少（crew_scalp_tint.gdshader 的 coverage）、发根淡入多长（crew_hair_strand 的 root_fade）。
## 分缝的发型要染得满、发根不淡入（不然分缝成了一道亮缝）；梳到后面的发际线全露着，要染得收、发根淡入（不然一排刺、一道染色带）
const HAIRLINE := {
	"back": [Vector2(0.55, 0.95), 0.04],
	"slick": [Vector2(0.55, 0.95), 0.04],
}
const HAIRLINE_DEFAULT := [Vector2(0.3, 0.9), 0.0]
const STYLE_DIR := "res://.tmp/tfx/styles/"
## 身体的碰撞胶囊：[挂在哪根骨头上, 从哪根骨头, 到哪根骨头, 半径]（长头发垂到肩上、背上时别穿进身体）
const BODY_CAPSULES := [
	["Bip01 Neck", "Bip01 Neck", "Bip01 Head", 0.05],
	["Bip01 Spine2", "Bip01 L UpperArm", "Bip01 R UpperArm", 0.065],
	["Bip01 Spine2", "Bip01 Spine2", "Bip01 Neck", 0.11],
]

## 船员的身体（crew_body.gd），本节点挂在它下面
var body: Node3D
var look := {}
## 发丝材质的粗细、头发团的中心（头发节点坐标系），_material 用
var _fiber := 0.0
var _center := Vector3.ZERO
## crew_hair_strand 才有的参数（插件那份没有），_material 用
var _extra := {}


func _ready() -> void:
	if not ClassDB.class_exists(&"TressFXHair"):
		push_error("TFX 没有 TressFX 插件（addons/tressfx 没放进来，或者 DLL 没加载上）")
		return
	# 等两帧：身体的动画把姿势摆好了再量头皮在哪
	await get_tree().process_frame
	await get_tree().process_frame
	_build()


func _build() -> void:
	var skel: Skeleton3D = body.find_children("*", "Skeleton3D", true, false)[0]
	var head := skel.find_bone("Bip01 Head")
	var shader_path := DebugArgs.get_arg("cc-tfx-shader", SHADER)
	if shader_path == "plugin":
		shader_path = PLUGIN_SHADER
	var style := DebugArgs.get_arg("cc-tfx-style")
	var built: Array = _build_style(skel, head, style, shader_path) if style != "" else _build_ponytail(skel, head, shader_path)
	if built.is_empty():
		return
	var root: Node3D = built[0]
	var hairs: Array = built[1]
	var mat: ShaderMaterial = built[2]
	print("TFX 着色器 ", shader_path)
	for h: Node3D in hairs:
		print("TFX %s：%d 根（主发丝 %d），每根 %d 个顶点" % [h.name, h.call("get_strand_count"),
			h.call("get_guide_strand_count"), h.call("get_vertices_per_strand")])

	if DebugArgs.has("cc-gpu"):
		# 视口的 GPU 计时不含插件在渲染线程上另外提交的计算着色器（模拟、距离场），用它自带的统计面板量，
		# 和 character_creator.gd 的 _measure_gpu 同一段（第 230 帧）打出来
		var layer := CanvasLayer.new()
		add_child(layer)
		var stats: Label = ClassDB.instantiate(&"TressFXStats")
		layer.add_child(stats)
		for _f in 228:
			await get_tree().process_frame
		print("TFX 统计：", stats.text.replace("\n", " | "))
		if DebugArgs.get_arg("cc-tfx-ab") == "shader":
			# 轮流换着色器（新的对插件的），比着色器本身的开销
			var other_path := PLUGIN_SHADER if shader_path != PLUGIN_SHADER else SHADER
			var other := _material(other_path)
			var swap := func(a: bool) -> void:
				for h: Node3D in hairs:
					h.set("material", mat if a else other)
			_ab(stats, swap, [shader_path.get_file(), other_path.get_file()])
		elif DebugArgs.has("cc-tfx-ab"):
			_ab(stats, func(a: bool) -> void: root.visible = a, ["有头发", "没头发"])


## 示例的马尾辫，按头皮缩放对位（见文件头）。返回 [对位节点, 头发节点们, 材质]，找不到头皮返回空
func _build_ponytail(skel: Skeleton3D, head: int, shader_path: String) -> Array:
	var head_world := skel.global_transform * skel.get_bone_global_pose(head)
	# 头皮：层壳的顶点用绑定姿势换到头骨坐标（头皮整块蒙在头骨上），再按当前姿势放到世界里
	var lo := Vector3.INF
	var hi := -Vector3.INF
	for mi: MeshInstance3D in body.find_children("Crew_Shell_buzz", "MeshInstance3D", true, false):
		var bind := _bind_pose(mi.skin, head)
		for v: Vector3 in mi.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]:
			var w := head_world * (bind * v)
			lo = lo.min(w)
			hi = hi.max(w)
	if lo == Vector3.INF:
		push_error("TFX 找不到头皮（Crew_Shell_buzz）")
		return []
	var size_s := hi - lo
	var size_r := ROOT_MAX - ROOT_MIN
	var s := 0.5 * (size_s.x / size_r.x + size_s.z / size_r.z)
	var off := Vector3.ZERO
	var fit := DebugArgs.get_arg("cc-tfx-fit").split(",")
	if fit.size() == 4:
		s *= float(fit[0])
		off = Vector3(float(fit[1]), float(fit[2]), float(fit[3]))
	var c_r := (ROOT_MIN + ROOT_MAX) * 0.5
	var c_s := (lo + hi) * 0.5
	var origin := Vector3(c_s.x - s * c_r.x, hi.y - s * ROOT_MAX.y, c_s.z - s * c_r.z) + off
	print("TFX 头皮 %s ~ %s，尺寸 %s；宽 %.3f 深 %.3f 高 %.3f → 缩放 %.3f，原点 %s" % [lo, hi, size_s,
		size_s.x / size_r.x, size_s.z / size_r.z, size_s.y / size_r.y, s, origin])

	# 挂在头骨上的对位节点：世界里不带缩放、不带旋转（马尾辫的文件 y 朝上、+z 朝前，和捏脸场景里的人一样）
	var att := BoneAttachment3D.new()
	att.bone_name = "Bip01 Head"
	skel.add_child(att)
	var root := Node3D.new()
	root.name = "TressFX"
	att.add_child(root)
	root.transform = head_world.affine_inverse() * Transform3D(Basis(), origin)

	var cols := []
	for c: Array in COLLIDERS:
		var col: Node3D = ClassDB.instantiate(&"TressFXCollisionMesh")
		var m: PrimitiveMesh
		if c[1] > 0.0:
			m = CapsuleMesh.new()
			(m as CapsuleMesh).radius = c[0] * s
			(m as CapsuleMesh).height = c[1] * s
		else:
			m = SphereMesh.new()
			(m as SphereMesh).radius = c[0] * s
			(m as SphereMesh).height = c[0] * 2.0 * s
		col.set("mesh", m)
		col.set("num_cells_x", c[4])
		col.position = c[2] * s
		if c[3]:
			col.rotation = Vector3(0.0, 0.0, PI / 2.0)
		root.add_child(col)
		cols.append(col)

	# 头发团的中心：示例里头那个碰撞体的位置（头骨中心），和碰撞体一样缩放；
	# 头发节点挂在 root 下面、不带变换，所以就是头发节点坐标系里的位置
	_fiber = 0.0012 * s
	_center = COLLIDERS[0][2] * s
	var mat := _material(shader_path)

	var hairs: Array[Node3D] = []
	for part: String in SIM:
		var h: Node3D = ClassDB.instantiate(&"TressFXHair")
		h.name = "Hair_" + part
		root.add_child(h)
		h.set("num_follow_hairs", int(DebugArgs.get_arg("cc-tfx-follow", "3")))
		h.set("tip_separation", 1.0)
		h.set("import_scale", 0.01 * s)
		h.set("material", mat)
		h.set("cast_hair_shadows", DebugArgs.get_arg("cc-tfx-shadow", "on") != "off")
		h.set("collision_meshes", cols)
		for k: String in SIM[part]:
			h.set(k, SIM[part][k])
		h.set("tfx_path", DIR + "ponytail_hair_%s.tfx" % part)   # 最后设：前面几项改了都会重新加载
		hairs.append(h)
	return [root, hairs, mat]


## 船员自己的发型（--cc-tfx-style，见文件头）。返回 [对位节点, 头发节点们, 材质]，缺文件返回空
func _build_style(skel: Skeleton3D, head: int, style: String, shader_path: String) -> Array:
	var sex: String = look.get("sex", "f")
	var tfx := STYLE_DIR + "%s_%s.tfx" % [sex, style]
	var info_path := STYLE_DIR + "%s_head.json" % sex
	if not STYLES.has(style) or not FileAccess.file_exists(tfx) or not FileAccess.file_exists(info_path):
		push_error("TFX 没有发型 %s（先跑 python tools/gen_tfx_hair.py）" % tfx)
		return []
	var info: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(info_path))
	# 原来的发片藏起来；层壳见文件头
	for mi: MeshInstance3D in body.find_children("Crew_Hair_*", "MeshInstance3D", true, false):
		mi.visible = false
	var shell_mode := DebugArgs.get_arg("cc-tfx-shell", "tint")
	if shell_mode != "on":
		var tint := ShaderMaterial.new()
		tint.shader = load("res://assets/shaders/crew_scalp_tint.gdshader")
		tint.set_shader_parameter("hair_color", _color())
		tint.set_shader_parameter("coverage", HAIRLINE.get(style, HAIRLINE_DEFAULT)[0])
		for mi: MeshInstance3D in body.find_children("Crew_Shell_*", "MeshInstance3D", true, false):
			mi.visible = shell_mode == "tint" and mi.name == "Crew_Shell_" + style
			mi.material_override = tint
	var head_mi: MeshInstance3D = body.find_children("Crew_Head", "MeshInstance3D", true, false)[0]
	# 对位节点挂在头骨上，变换就是头骨的绑定姿势（网格坐标 → 头骨坐标）：发丝、头的碰撞体都是网格坐标，
	# 这样放上去和蒙皮到头骨上的发片、皮肤分毫不差
	var att := BoneAttachment3D.new()
	att.bone_name = "Bip01 Head"
	skel.add_child(att)
	var root := Node3D.new()
	root.name = "TressFX"
	att.add_child(root)
	root.transform = _bind_pose(head_mi.skin, head)
	print("TFX 发型 %s（%s），头骨绑定姿势的缩放 %s" % [style, sex, root.transform.basis.get_scale()])

	var cols := []
	var col: Node3D = ClassDB.instantiate(&"TressFXCollisionMesh")
	col.set("mesh", _head_collider(head_mi, info))
	col.set("num_cells_x", 64)   # 发丝离头皮只有 1.5 毫米起，格子细一点（头 20 厘米见方，一格 3 毫米）
	root.add_child(col)
	cols.append(col)
	cols.append_array(_body_colliders(skel))

	var cfg: Dictionary = STYLES[style]
	_fiber = 0.00018
	var c: Array = info.volume_center
	_center = Vector3(c[0], c[1], c[2])
	# 每根的粗细倍数、深浅在发丝 UV 里；头发层约 1.5 厘米厚（gen_tfx_hair.py 的 lift + 发片原本离头皮的那点）。
	# 粗糙一点、里层压暗少一点、背光那半边多漏一点光：默认那套（Ruby 的马尾辫调的）在这里像湿头发，暗处一团死黑；
	# 发根淡入见 HAIRLINE
	_extra = {"strand_attrs": true, "volume_thickness": 0.015, "roughness": 0.5, "volume_occlusion": 0.45, "volume_wrap": 0.7,
		"root_fade": HAIRLINE.get(style, HAIRLINE_DEFAULT)[1]}
	var mat := _material(shader_path)
	var h: Node3D = ClassDB.instantiate(&"TressFXHair")
	h.name = "Hair_" + style
	root.add_child(h)
	h.set("num_follow_hairs", int(DebugArgs.get_arg("cc-tfx-follow", "2")))
	h.set("follow_radius", float(DebugArgs.get_arg("cc-tfx-radius", "0.0012")))
	h.set("tip_separation", 0.4)
	h.set("material", mat)
	h.set("cast_hair_shadows", DebugArgs.get_arg("cc-tfx-shadow", "on") != "off")
	h.set("collision_meshes", cols)
	for k: String in cfg:
		h.set(k, cfg[k])
	for kv: String in DebugArgs.get_arg("cc-tfx-sim").split(",", false):
		var p := kv.split(":")
		h.set(p[0], float(p[1]))
	h.set("tfx_path", ProjectSettings.globalize_path(tfx))   # 最后设：前面几项改了都会重新加载
	return [root, [h], mat]


## 头的碰撞体（网格坐标）：皮肤网格本身（Crew_Skin 那一面；脖子底下、眼眶、嘴是开口的，离头发远，距离场的正负号错不到头发上），
## 或者 gen_tfx_hair.py 算的凸包（--cc-tfx-headcol=hull；封闭，但耳后、脖子两边凹进去的地方被填平，长发贴着垂下来会被推开）。
## 插件按顶点法线定里外，法线一定要带上
func _head_collider(head_mi: MeshInstance3D, info: Dictionary) -> ArrayMesh:
	var arr := []
	arr.resize(Mesh.ARRAY_MAX)
	if DebugArgs.get_arg("cc-tfx-headcol", "mesh") == "hull":
		var c: Array = info.volume_center
		var center := Vector3(c[0], c[1], c[2])
		var v := PackedVector3Array()
		var n := PackedVector3Array()
		for p: Array in info.verts:
			v.append(Vector3(p[0], p[1], p[2]))
			n.append((v[-1] - center).normalized())
		var idx := PackedInt32Array()
		for t: Array in info.tris:
			idx.append_array([int(t[0]), int(t[1]), int(t[2])])
		arr[Mesh.ARRAY_VERTEX] = v
		arr[Mesh.ARRAY_NORMAL] = n
		arr[Mesh.ARRAY_INDEX] = idx
	else:
		for i in head_mi.mesh.get_surface_count():
			var m := head_mi.mesh.surface_get_material(i)
			if m and m.resource_name == "Crew_Skin":
				var a := head_mi.mesh.surface_get_arrays(i)
				arr[Mesh.ARRAY_VERTEX] = a[Mesh.ARRAY_VERTEX]
				arr[Mesh.ARRAY_NORMAL] = a[Mesh.ARRAY_NORMAL]
				arr[Mesh.ARRAY_INDEX] = a[Mesh.ARRAY_INDEX]
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arr)
	return mesh


## 脖子、肩、胸的碰撞胶囊（BODY_CAPSULES）：按骨骼现在的姿势摆好，挂在对应的骨头上跟着动
func _body_colliders(skel: Skeleton3D) -> Array:
	var out := []
	for c: Array in BODY_CAPSULES:
		var on := skel.find_bone(c[0])
		var a := skel.find_bone(c[1])
		var b := skel.find_bone(c[2])
		if on < 0 or a < 0 or b < 0:
			push_warning("TFX 找不到骨头 %s / %s / %s，少一个碰撞胶囊" % c.slice(0, 3))
			continue
		var pa := (skel.global_transform * skel.get_bone_global_pose(a)).origin
		var pb := (skel.global_transform * skel.get_bone_global_pose(b)).origin
		var cap := CapsuleMesh.new()
		cap.radius = c[3]
		cap.height = pa.distance_to(pb) + 2.0 * c[3]
		var col: Node3D = ClassDB.instantiate(&"TressFXCollisionMesh")
		col.set("mesh", cap)
		col.set("num_cells_x", 32)
		var att := BoneAttachment3D.new()
		att.bone_name = c[0]
		skel.add_child(att)
		att.add_child(col)
		var bone_world := skel.global_transform * skel.get_bone_global_pose(on)
		col.transform = bone_world.affine_inverse() * Transform3D(Basis(Quaternion(Vector3.UP, (pb - pa).normalized())), (pa + pb) * 0.5)
		out.append(col)
	return out


## --cc-tfx-ab：同一个进程里每 50 帧轮流显示 / 藏起头发，各轮四遍，比视口的 GPU 时间和一帧的时间。
## 这个场景很轻，显卡跑不满、频率一直在变，分两次启动量出来的差别比头发本身还大；轮流量，频率的漂移两边一样。
## 藏起来的头发不模拟、碰撞体也不重建（插件的 simulate_offscreen 默认关），所以差值就是头发的全部开销
## （模拟、距离场的计算着色器不在视口计时里，看统计面板那一行）。截图配 --wait=900。
## --cc-tfx-ab=shader：头发一直显示，轮流换 --cc-tfx-shader 给的着色器和另一个（新的 / 插件的），比两个着色器差多少；
## 显卡跑不满时差别淹在频率漂移里，配大一点的分辨率（--resolution 3840x2160）让显卡忙起来再比。
## toggle(true / false) 切到前 / 后一种，names 是两种的名字
func _ab(stats: Label, toggle: Callable, names: Array) -> void:
	var vp := get_viewport().get_viewport_rid()
	var gpu := [0.0, 0.0]
	var frame := [0.0, 0.0]
	var n := [0, 0]
	for round in 8:
		var on := round % 2 == 0
		toggle.call(on)
		var k := 0 if on else 1
		for _f in 15:   # 换了以后先等几帧（模拟醒过来、管线稳住）
			await get_tree().process_frame
		var t0 := Time.get_ticks_usec()
		for _f in 50:
			await get_tree().process_frame
			gpu[k] += RenderingServer.viewport_get_measured_render_time_gpu(vp)
		frame[k] += (Time.get_ticks_usec() - t0) / 1000.0
		n[k] += 50
		if on and round == 6:
			print("TFX 统计（轮流量时）：", stats.text.replace("\n", " | "))
	toggle.call(true)
	print("TFX 轮流量：%s GPU %.2f ms、一帧 %.2f ms；%s GPU %.2f ms、一帧 %.2f ms；差 GPU %.2f ms、一帧 %.2f ms" % [
		names[0], gpu[0] / n[0], frame[0] / n[0], names[1], gpu[1] / n[1], frame[1] / n[1],
		gpu[0] / n[0] - gpu[1] / n[1], frame[0] / n[0] - frame[1] / n[1]])


## 发丝材质：两个着色器共用的参数（发色、粗细 _fiber、发根压暗……），再加各自的（_extra 只给 crew_hair_strand），--cc-tfx-mat 最后改
func _material(shader_path: String) -> ShaderMaterial:
	var mat := ShaderMaterial.new()
	mat.shader = load(shader_path)
	var color := _color()
	mat.set_shader_parameter("base_color", color)
	mat.set_shader_parameter("tip_color", color.lightened(0.25) if DebugArgs.get_arg("cc-tfx-color", "look") == "auburn" else color)
	mat.set_shader_parameter("tip_percentage", 0.3)
	mat.set_shader_parameter("fiber_radius", _fiber)
	mat.set_shader_parameter("fiber_ratio", 0.3)
	if shader_path == PLUGIN_SHADER:
		mat.set_shader_parameter("k_diffuse", 0.35)
		mat.set_shader_parameter("k_spec1", 0.06)
		mat.set_shader_parameter("spec_exp1", 40.0)
		mat.set_shader_parameter("k_spec2", 0.25)
		mat.set_shader_parameter("spec_exp2", 14.0)
	else:
		# 头发团的中心（头发节点坐标系），挡掉穿过脑袋照过来的光，见 crew_hair_strand.gdshader
		mat.set_shader_parameter("volume_center", _center)
	mat.set_shader_parameter("root_shadow", 0.3)
	mat.set_shader_parameter("color_variation", 0.3)
	mat.set_shader_parameter("tip_fade", 0.25)
	if shader_path != PLUGIN_SHADER:
		for k: String in _extra:
			mat.set_shader_parameter(k, _extra[k])
	for kv: String in DebugArgs.get_arg("cc-tfx-mat").split(",", false):
		var p := kv.split(":")
		mat.set_shader_parameter(p[0], float(p[1]))
	return mat


## 蒙皮里头骨那一项的绑定姿势（网格坐标 → 头骨坐标）
func _bind_pose(skin: Skin, bone: int) -> Transform3D:
	for i in skin.get_bind_count():
		if skin.get_bind_bone(i) == bone or skin.get_bind_name(i) == &"Bip01 Head":
			return skin.get_bind_pose(i)
	push_error("TFX 层壳的蒙皮里没有 Bip01 Head")
	return Transform3D.IDENTITY


func _color() -> Color:
	var arg := DebugArgs.get_arg("cc-tfx-color", "look")
	if arg == "auburn":
		return Color(0.36, 0.11, 0.04)
	var p := arg.split(",")
	if p.size() == 3:
		return Color(float(p[0]), float(p[1]), float(p[2]))
	return CrewLook.HAIR_COLORS[look.get("hair_col", 0)][1]
