class_name PlanarMirror
extends Node3D
## 真的镜子：挂在镜面网格（Mirror_Glass，一个带 0~1 UV 的四边形）下面。
## 反射相机放在主相机关于镜面的对称点上，看向镜面；用斜视锥（frustum + offset）让近平面正好贴着镜面、
## 画面正好框住镜子，画到一张 SubViewport 里，镜面材质再把它左右翻过来贴上（assets/shaders/mirror.gdshader）。
## 第一人称的头平时不画（相机在头里面），只有镜子看得见：头在 HEAD_LAYER 层，主相机不画这一层、反射相机画。
## 只在镜子在视野里、离得不远时才渲染。

const HEAD_LAYER := 20
const SHADER := preload("res://assets/shaders/mirror.gdshader")
## 反射画面的分辨率（长边）
@export var resolution := 640
@export var max_distance := 5.0

var _mesh: MeshInstance3D
var _vp: SubViewport
var _cam: Camera3D
var _half := Vector2.ONE
var _vis: VisibleOnScreenNotifier3D


func _ready() -> void:
	add_to_group("mirror")
	_mesh = get_parent() as MeshInstance3D
	var aabb := _mesh.get_aabb()
	# 镜面在网格局部坐标里的大小（四边形，法线方向那一维是 0）
	var s := aabb.size
	var dims := [s.x, s.y, s.z]
	dims.sort()
	_half = Vector2(dims[2], dims[1]) * 0.5
	_vp = SubViewport.new()
	var aspect := _half.x / _half.y
	_vp.size = Vector2i(resolution, int(resolution / aspect)) if aspect >= 1.0 else Vector2i(int(resolution * aspect), resolution)
	_vp.render_target_update_mode = SubViewport.UPDATE_WHEN_PARENT_VISIBLE
	_vp.msaa_3d = Viewport.MSAA_2X
	add_child(_vp)
	_cam = Camera3D.new()
	_cam.projection = Camera3D.PROJECTION_FRUSTUM
	_cam.keep_aspect = Camera3D.KEEP_HEIGHT
	_cam.cull_mask = 0xFFFFF
	_vp.add_child(_cam)
	var mat := ShaderMaterial.new()
	mat.shader = SHADER
	mat.set_shader_parameter("reflection", _vp.get_texture())
	mat.set_shader_parameter("smear", load("res://assets/third_party/ambientcg/Smear004/Smear004_2K-JPG_Roughness.jpg"))
	_mesh.material_override = mat
	_vis = VisibleOnScreenNotifier3D.new()
	_vis.aabb = aabb
	_mesh.add_child(_vis)


## 镜面的中心、法线（朝屋里）、右、上（世界坐标）
func _plane() -> Array:
	var t := _mesh.global_transform
	var aabb := _mesh.get_aabb()
	var c := t * aabb.get_center()
	# 网格局部坐标里最薄的那一维就是法线方向
	var s := aabb.size
	var nl := Vector3.UP
	if s.x <= s.y and s.x <= s.z:
		nl = Vector3.RIGHT
	elif s.z <= s.x and s.z <= s.y:
		nl = Vector3.BACK
	var n := (t.basis * nl).normalized()
	var cam := get_viewport().get_camera_3d()
	if cam and n.dot(cam.global_position - c) < 0.0:
		n = -n
	var up := Vector3.UP
	up = (up - n * up.dot(n)).normalized()
	var right := up.cross(n).normalized()
	return [c, n, right, up]


func _process(_delta: float) -> void:
	var main := get_viewport().get_camera_3d()
	if main == null or main == _cam:
		return
	var pl := _plane()
	var c: Vector3 = pl[0]
	var n: Vector3 = pl[1]
	var r: Vector3 = pl[2]
	var u: Vector3 = pl[3]
	var eye := main.global_position
	var d := n.dot(eye - c)
	var on := _vis.is_on_screen() and d > 0.02 and eye.distance_to(c) < max_distance
	_vp.render_target_update_mode = SubViewport.UPDATE_ALWAYS if on else SubViewport.UPDATE_DISABLED
	if not on:
		return
	# 对称点在镜子后面，看向屋里（-Z = n）；它的右手是 -r，所以画面天然是左右反的
	var e := eye - 2.0 * d * n
	_cam.global_transform = Transform3D(Basis(-r, u, -n), e)
	var local := _cam.global_transform.affine_inverse() * c
	_cam.near = maxf(d - 0.002, 0.01)
	_cam.far = 40.0
	_cam.size = _half.y * 2.0
	_cam.frustum_offset = Vector2(local.x, local.y)
	_cam.environment = main.environment if main.environment else null
