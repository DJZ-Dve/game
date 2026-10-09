extends Node3D
## 舱外的水：水体吸收后处理（underwater.gdshader）+ 三层绕相机的颗粒场
## （海雪、细悬浮物、生物发光，见 marine_snow.gdshader / bioluminescence.gdshader）。
## 颗粒钉在世界坐标里、跟着洋流漂，相机走到哪周围都有；耐压舱里的位置每帧告诉着色器，舱内不显示也不衰减。

const UNDERWATER := preload("res://assets/shaders/underwater.gdshader")
const SNOW := preload("res://assets/shaders/marine_snow.gdshader")
const GLOW := preload("res://assets/shaders/bioluminescence.gdshader")
## 后处理面片单独放一层：舱内反射探针不渲染这一层（submarine.tscn 里探针的 cull_mask）
const POST_LAYER := 1 << 19

@export var cabin_path: NodePath
## 耐压舱轴线两端在舱内局部坐标里的位置：艏部半球顶、生活舱后隔壁（见 blender/scripts/cockpit.py）
@export var cabin_front := Vector3(0, 0, -1.6 - 1.35)
@export var cabin_back := Vector3(0, 0, 6.4)
@export var cabin_radius := 1.38
## 耐压舱内壁半径 1.35、外表面 1.41（blender/scripts/gen_submarine.py 的 R_OUT），取中间：外表面算水里
## 每米光程的衰减（RGB），所有着色器共用
@export var absorption := Vector3(0.09, 0.032, 0.026)

var _cabin: Node3D
var _mats: Array[ShaderMaterial] = []
var _cam: Camera3D
var _cam_pos := Vector3.ZERO
var _cam_vel := Vector3.ZERO


func _ready() -> void:
	_cabin = get_node_or_null(cabin_path)

	var quad := QuadMesh.new()
	quad.size = Vector2(1, 1)
	var post := _add("Underwater", quad, UNDERWATER, {}, -128)
	post.layers = POST_LAYER
	post.visible = DebugArgs.get_arg("water", "on") != "off"

	# 海雪：毫米到两厘米的絮状颗粒，被灯照到的一片
	_add("MarineSnow", _field(14000, 1), SNOW, {
		"box": Vector3(24, 16, 24), "size_range": Vector2(0.003, 0.022), "size_bias": 3.0,
		"brightness": 0.9,
	})
	# 细悬浮物：密得多、小得多，只在近处，让光柱里的水看着"浑"
	_add("Silt", _field(24000, 2), SNOW, {
		"box": Vector3(8, 6, 8), "size_range": Vector2(0.0006, 0.0018), "size_bias": 1.0,
		"brightness": 0.5, "current": Vector3(0.03, -0.004, 0.015), "wobble": 0.05,
		"color": Color(0.8, 0.86, 0.84, 1.0),
	})
	_add("Bioluminescence", _field(300, 3), GLOW, {})


func _add(nm: String, mesh: Mesh, shader: Shader, params: Dictionary, priority := 0) -> MeshInstance3D:
	var mat := ShaderMaterial.new()
	mat.shader = shader
	mat.render_priority = priority
	for k in params:
		mat.set_shader_parameter(k, params[k])
	mat.set_shader_parameter("absorption", absorption)
	mat.set_shader_parameter("cabin_radius", cabin_radius)
	var mi := MeshInstance3D.new()
	mi.name = nm
	mi.mesh = mesh
	mi.material_override = mat
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	mi.gi_mode = GeometryInstance3D.GI_MODE_DISABLED
	# 位置都在着色器里算，包围盒给大，永远不被剔除
	mi.custom_aabb = AABB(Vector3.ONE * -5000.0, Vector3.ONE * 10000.0)
	add_child(mi)
	_mats.append(mat)
	return mi


## n 个四边形，每个的四个顶点带同一个随机种子（COLOR），UV 是四个角
func _field(n: int, seed_: int) -> ArrayMesh:
	var rng := RandomNumberGenerator.new()
	rng.seed = seed_
	var verts := PackedVector3Array()
	var uvs := PackedVector2Array()
	var cols := PackedColorArray()
	var idx := PackedInt32Array()
	verts.resize(n * 4)
	uvs.resize(n * 4)
	cols.resize(n * 4)
	idx.resize(n * 6)
	var corners := [Vector2(0, 0), Vector2(1, 0), Vector2(1, 1), Vector2(0, 1)]
	for i in n:
		var c := Color(rng.randf(), rng.randf(), rng.randf(), rng.randf())
		for k in 4:
			uvs[i * 4 + k] = corners[k]
			cols[i * 4 + k] = c
		for k in 6:
			idx[i * 6 + k] = i * 4 + [0, 1, 2, 0, 2, 3][k]
	var arr := []
	arr.resize(Mesh.ARRAY_MAX)
	arr[Mesh.ARRAY_VERTEX] = verts
	arr[Mesh.ARRAY_TEX_UV] = uvs
	arr[Mesh.ARRAY_COLOR] = cols
	arr[Mesh.ARRAY_INDEX] = idx
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arr)
	return mesh


func _process(delta: float) -> void:
	# 相机速度（拖影用）；换了相机就从零开始，免得一帧跳几十米拉出满屏长线
	var cam := get_viewport().get_camera_3d()
	if cam:
		var p := cam.global_position
		if cam != _cam:
			_cam = cam
			_cam_vel = Vector3.ZERO
		elif delta > 0.0:
			_cam_vel = _cam_vel.lerp(((p - _cam_pos) / delta).limit_length(6.0), 1.0 - exp(-delta * 12.0))
		_cam_pos = p
	var a := Vector3.ZERO
	var b := Vector3.FORWARD
	if _cabin:
		# 胶囊两端各往里收一个半径，球冠正好盖住艏部半球和后隔壁
		a = _cabin.global_transform * (cabin_front + Vector3(0, 0, cabin_radius))
		b = _cabin.global_transform * (cabin_back - Vector3(0, 0, cabin_radius * 0.5))
	for m in _mats:
		m.set_shader_parameter("cabin_a", a)
		m.set_shader_parameter("cabin_b", b)
		m.set_shader_parameter("cam_velocity", _cam_vel)
