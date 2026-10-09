extends Camera3D
## 舱外环绕视角（调试/欣赏艇身用）：按住左键拖动环绕，滚轮缩放。

@export var target_path: NodePath = ".."
@export var distance := 17.0
@export var min_distance := 6.0
@export var max_distance := 36.0
@export var yaw_deg := 145.0
@export var pitch_deg := -12.0

var _target: Node3D
var _dragging := false


var _fill: SpotLight3D


func _ready() -> void:
	top_level = true
	_target = get_node(target_path)
	# 舱外视角像一台跟拍的水下机器人，自带一盏补光灯：一束对着艇身的聚光，
	# 只照得到艇和艇底下一小片海床，再远就是黑水（以前用全向灯，整片海床被照得像舞台）
	_fill = SpotLight3D.new()
	_fill.light_color = Color(0.9, 0.95, 1.0)
	_fill.spot_attenuation = 1.0
	_fill.spot_angle_attenuation = 1.6
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
	# 环绕中心在艇身中部（围壳和尾舵之间）
	var center := _target.global_position + Vector3(0, 0.6, 3.6).rotated(Vector3.UP, _target.global_rotation.y)
	var rot := Basis.from_euler(Vector3(deg_to_rad(pitch_deg), deg_to_rad(yaw_deg) + _target.global_rotation.y, 0))
	global_transform = Transform3D(rot, center + rot * Vector3(0, 0, distance))
	# 灯在相机斜上方一点（避免正面平光）、对着艇身中部；光照按距离平方衰减，亮度跟着相机距离走，
	# 保证艇身始终看得清。光束宽度按艇身对着灯的张角，射程只比艇远一点
	_fill.spot_angle = clampf(rad_to_deg(atan(9.0 / distance)), 14.0, 55.0)
	_fill.spot_range = distance + 12.0
	_fill.light_energy = 0.3 * distance * distance
	# 灯本身变亮了，相机跟前那段水的散射也跟着变亮：按同样的比例压回去，光束的雾感不随距离变
	_fill.light_volumetric_fog_energy = minf(1.0, 150.0 / (distance * distance))
	if _fill.is_inside_tree():
		var lamp := global_position + rot.y * 2.0 + rot.x * 1.5
		_fill.global_transform = Transform3D(Basis.looking_at(center - lamp, Vector3.UP), lamp)
