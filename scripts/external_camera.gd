extends Camera3D
## 舱外环绕视角（调试/欣赏艇身用）：按住左键拖动环绕，滚轮缩放。

@export var target_path: NodePath = ".."
@export var distance := 14.0
@export var min_distance := 6.0
@export var max_distance := 30.0
@export var yaw_deg := 145.0
@export var pitch_deg := -12.0

var _target: Node3D
var _dragging := false


var _fill: OmniLight3D


func _ready() -> void:
	top_level = true
	_target = get_node(target_path)
	# 舱外视角像一台跟拍的水下机器人，自带一盏补光灯
	_fill = OmniLight3D.new()
	_fill.light_color = Color(0.9, 0.95, 1.0)
	_fill.omni_range = 30.0
	_fill.omni_attenuation = 1.0
	_fill.light_volumetric_fog_energy = 0.12
	_fill.shadow_enabled = true
	_fill.top_level = true
	_target.add_child.call_deferred(_fill)
	if DebugArgs.has("orbit"):
		yaw_deg = float(DebugArgs.get_arg("orbit"))
	if DebugArgs.has("orbit_pitch"):
		pitch_deg = float(DebugArgs.get_arg("orbit_pitch"))
	if DebugArgs.has("orbit_dist"):
		distance = float(DebugArgs.get_arg("orbit_dist"))


func _unhandled_input(event: InputEvent) -> void:
	if not current:
		return
	if event is InputEventMouseButton:
		if event.button_index == MOUSE_BUTTON_LEFT:
			_dragging = event.pressed
		elif event.button_index == MOUSE_BUTTON_WHEEL_UP:
			distance = maxf(min_distance, distance * 0.9)
		elif event.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			distance = minf(max_distance, distance * 1.1)
	elif event is InputEventMouseMotion and (_dragging or Input.mouse_mode == Input.MOUSE_MODE_CAPTURED):
		yaw_deg -= event.relative.x * 0.25
		pitch_deg = clampf(pitch_deg - event.relative.y * 0.25, -80.0, 60.0)


func _process(_delta: float) -> void:
	_fill.visible = current
	var center := _target.global_position + Vector3(0, 0.3, 2.0).rotated(Vector3.UP, _target.global_rotation.y)
	var rot := Basis.from_euler(Vector3(deg_to_rad(pitch_deg), deg_to_rad(yaw_deg) + _target.global_rotation.y, 0))
	global_transform = Transform3D(rot, center + rot * Vector3(0, 0, distance))
	# 光照按距离平方衰减：补光亮度跟着相机距离走，保证艇身始终看得清
	_fill.light_energy = 0.12 * distance * distance
	if _fill.is_inside_tree():
		# 补光放在相机斜上方一点，避免正面平光
		_fill.global_position = global_position + global_basis.y * 2.0 + global_basis.x * 1.5
