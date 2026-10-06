extends GPUParticles3D
## 海雪：跟着潜艇走（粒子本身留在世界坐标里），把驾驶舱位置告诉着色器以便在舱内隐藏。

@export var cabin_path: NodePath

var _cabin: Node3D
var _mat: ShaderMaterial


func _ready() -> void:
	_cabin = get_node_or_null(cabin_path)
	var mesh := draw_pass_1
	if mesh and mesh.surface_get_material(0) is ShaderMaterial:
		_mat = mesh.surface_get_material(0)


func _process(_delta: float) -> void:
	if _mat and _cabin:
		_mat.set_shader_parameter("cabin_center", _cabin.global_position)
