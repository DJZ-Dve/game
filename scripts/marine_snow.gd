extends GPUParticles3D
## 海雪：跟着潜艇走（粒子本身留在世界坐标里），把耐压舱的位置告诉着色器以便在舱内隐藏。

@export var cabin_path: NodePath
## 耐压舱轴线两端在舱内局部坐标里的位置：艏部半球顶、生活舱后隔壁（见 blender/scripts/cockpit.py）
@export var cabin_front := Vector3(0, 0, -1.6 - 1.35)
@export var cabin_back := Vector3(0, 0, 6.4)

var _cabin: Node3D
var _mat: ShaderMaterial


func _ready() -> void:
	_cabin = get_node_or_null(cabin_path)
	var mesh := draw_pass_1
	if mesh and mesh.surface_get_material(0) is ShaderMaterial:
		_mat = mesh.surface_get_material(0)


func _process(_delta: float) -> void:
	if _mat and _cabin:
		# 胶囊两端各往里收一个半径，球冠正好盖住艏部半球和后隔壁
		var r := 1.42  # 和 marine_snow.gdshader 的 cabin_radius 一致
		_mat.set_shader_parameter("cabin_a", _cabin.global_transform * (cabin_front + Vector3(0, 0, r)))
		_mat.set_shader_parameter("cabin_b", _cabin.global_transform * (cabin_back - Vector3(0, 0, r * 0.5)))
