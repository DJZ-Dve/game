class_name Submarine
extends CharacterBody3D
## 潜艇本体：带惯性的推进/转向/升降、碰撞反馈、探照灯、舱内/舱外视角切换。

signal bumped(strength: float)

@export_group("航行")
@export var max_speed := 2.6
@export var thrust_accel := 0.9
@export var vertical_max := 1.0
@export var vertical_accel := 0.7
@export var turn_max_deg := 24.0
@export var turn_accel_deg := 30.0
@export var water_drag := 0.45

@export_group("深度")
## 世界坐标 y = 0 处对应的水深（米）
@export var depth_at_origin := 1850.0

@export_group("探照灯")
@export var light_energy := 22.0
@export var light_range := 60.0
@export var light_angle := 28.0
@export var light_color := Color(1.0, 0.93, 0.82)

var lights_on := true
## 有人坐在驾驶椅上才响应操纵（起身走动时艇只靠惯性漂）
var piloting := true
var thrust_input := 0.0
var lift_input := 0.0
var yaw_speed := 0.0
var external_view := false

var _floodlights: Array[SpotLight3D] = []
var _lens: MeshInstance3D
var _lens_material: StandardMaterial3D
var _sway := Vector3.ZERO

@onready var body: Node3D = $Body
@onready var cockpit_camera: Camera3D = %CockpitCamera
@onready var external_camera: Camera3D = %ExternalCamera


func _ready() -> void:
	_build_floodlights()
	cockpit_camera.configure(body)
	cockpit_camera.make_current()
	piloting = cockpit_camera.is_seated()
	cockpit_camera.seated_changed.connect(func(s: bool) -> void: piloting = s)
	bumped.connect(cockpit_camera.add_shake)
	if DebugArgs.has("view"):
		set_external_view(DebugArgs.get_arg("view") == "external")
	if DebugArgs.get_arg("lights", "on") == "off":
		set_lights(false)


func depth() -> float:
	return depth_at_origin - global_position.y


func heading_deg() -> float:
	return fposmod(-rad_to_deg(global_rotation.y), 360.0)


func speed() -> float:
	return velocity.length()


func _build_floodlights() -> void:
	for anchor in find_children("Light_*", "Node3D", true, false):
		var l := SpotLight3D.new()
		l.name = "Spot"
		l.light_color = light_color
		l.light_energy = light_energy * (0.5 if anchor.name.begins_with("Light_S") else 1.0)
		l.spot_range = light_range
		l.spot_angle = light_angle
		l.spot_angle_attenuation = 0.9
		l.spot_attenuation = 1.2
		l.shadow_enabled = true
		l.shadow_blur = 1.5
		l.light_volumetric_fog_energy = 1.6
		l.light_size = 0.12
		anchor.add_child(l)
		_floodlights.append(l)
	_lens = find_child("Lens_Floodlights", true, false) as MeshInstance3D
	if _lens:
		var m := _lens.get_active_material(0)
		if m is StandardMaterial3D:
			_lens_material = m.duplicate()
			_lens.set_surface_override_material(0, _lens_material)


func set_lights(on: bool) -> void:
	lights_on = on
	for l in _floodlights:
		l.visible = on
	if _lens_material:
		_lens_material.emission_energy_multiplier = 6.0 if on else 0.0


func set_external_view(on: bool) -> void:
	external_view = on
	if on:
		external_camera.make_current()
	else:
		cockpit_camera.make_current()


func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("toggle_lights"):
		set_lights(not lights_on)
	elif event.is_action_pressed("toggle_view"):
		set_external_view(not external_view)


func _physics_process(delta: float) -> void:
	var drive := piloting or external_view
	thrust_input = Input.get_axis("move_back", "move_forward") if drive else 0.0
	lift_input = Input.get_axis("descend", "ascend") if drive else 0.0
	var turn := Input.get_axis("turn_right", "turn_left") if drive else 0.0

	var forward := -global_basis.z
	var hv := Vector3(velocity.x, 0.0, velocity.z)
	hv += forward * thrust_input * thrust_accel * delta
	hv -= hv * water_drag * delta
	hv = hv.limit_length(max_speed)
	var vv := velocity.y + lift_input * vertical_accel * delta
	vv -= vv * water_drag * 1.5 * delta
	vv = clampf(vv, -vertical_max, vertical_max)
	velocity = Vector3(hv.x, vv, hv.z)

	yaw_speed = move_toward(yaw_speed, turn * deg_to_rad(turn_max_deg), deg_to_rad(turn_accel_deg) * delta)
	rotate_y(yaw_speed * delta)

	var before := velocity
	move_and_slide()
	if get_slide_collision_count() > 0:
		var impact := (before - velocity).length()
		if impact > 0.2:
			bumped.emit(impact)

	_update_sway(delta)


## 艇身随推进、转向轻微俯仰和侧倾，再叠一点水流造成的晃动。
func _update_sway(delta: float) -> void:
	var t := Time.get_ticks_msec() / 1000.0
	var target := Vector3(
		-thrust_input * 0.03 + lift_input * 0.02 + sin(t * 0.7) * 0.006,
		0.0,
		-yaw_speed * 0.22 + sin(t * 0.53 + 1.3) * 0.008)
	_sway = _sway.lerp(target, 1.0 - exp(-delta * 1.4))
	body.rotation = _sway
