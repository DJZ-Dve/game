class_name Submarine
extends CharacterBody3D
## 潜艇本体：带惯性的推进/转向/升降、碰撞反馈、探照灯、舱内/舱外视角切换。

signal bumped(strength: float)
## 驾驶员按了探照灯开关（给音效用；调试参数开场关灯不算）
signal lights_switched(on: bool)

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
# 艉部的动件：螺旋桨、方向舵、升降舵（外壳模型里单独的网格，挂到各自的转轴上）
var _prop: Node3D
var _rudder: Node3D
var _planes: Node3D
var _prop_speed := 0.0
var _lift_smooth := 0.0

@onready var body: Node3D = $Body
@onready var cockpit_camera: Camera3D = %CockpitCamera
@onready var external_camera: Camera3D = %ExternalCamera


## 舱外的网格放在第 2 个可见层：舱内的反射探针只作用于第 1 层（见 submarine.tscn 的 reflection_mask），
## 否则紧贴着耐压舱的艇身外表面会映出舱里亮着的灯，整条艇泛银白
const EXTERIOR_LAYER := 2
## 舱内、海底的网格在第 1 层之外再各挂一层，只用来分投影：舱内灯只让舱内的东西投影（艇身外壳、海底在耐压壳外面，
## 影子永远落不进舱里），探照灯和舱外补光只让艇身外壳、海底投影（舱内的东西被外壳包着，影子也出不去）。
## 舱内网格是按材质合并的大网格，包围盒盖住整条艇，不分开的话每盏灯都要把全艇和海底画一遍阴影图
const CABIN_LAYER := 4
const SEABED_LAYER := 8
const CABIN_SHADOW_CASTERS := CABIN_LAYER
const OUTSIDE_SHADOW_CASTERS := EXTERIOR_LAYER | SEABED_LAYER


## 给 root 下面所有网格加上一个可见层（保留原来的层）
static func add_layer(root: Node, layer: int) -> void:
	for g in root.find_children("*", "GeometryInstance3D", true, false):
		(g as GeometryInstance3D).layers |= layer


## 一直在动的小东西（仪表指针、浮子、平安符）不投影：灯照得到的范围里只要有投影的东西动了，
## 那盏灯的阴影图就得每帧重画；它们的影子小到看不出来
static func stop_casting(root: Node) -> void:
	var nodes: Array = root.find_children("*", "GeometryInstance3D", true, false)
	nodes.append(root)
	for g in nodes:
		if g is GeometryInstance3D:
			(g as GeometryInstance3D).cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF


func _ready() -> void:
	_build_floodlights()
	_setup_stern()
	for g in $Body/Exterior.find_children("*", "GeometryInstance3D", true, false):
		if not String(g.name).begins_with("Viewport_Glass"):  # 舷窗玻璃主要是从舱里看
			(g as GeometryInstance3D).layers = EXTERIOR_LAYER
	for n in body.get_children():
		if n.name != "Exterior":
			add_layer(n, CABIN_LAYER)
	cockpit_camera.configure(body)
	cockpit_camera.make_current()
	piloting = cockpit_camera.is_seated()
	cockpit_camera.seated_changed.connect(func(s: bool) -> void: piloting = s)
	bumped.connect(cockpit_camera.add_shake)
	if DebugArgs.has("view"):
		set_external_view(DebugArgs.get_arg("view") == "external")
	if DebugArgs.get_arg("lights", "on") == "off":
		set_lights(false)
	if DebugArgs.has("sub-yaw"):
		rotate_y(deg_to_rad(float(DebugArgs.get_arg("sub-yaw"))))


func depth() -> float:
	return depth_at_origin - global_position.y


func heading_deg() -> float:
	return fposmod(-rad_to_deg(global_rotation.y), 360.0)


func speed() -> float:
	return velocity.length()


## 螺旋桨转速（任意单位，满速前进约 9）
func prop_speed() -> float:
	return _prop_speed


func _build_floodlights() -> void:
	for anchor in find_children("Light_*", "Node3D", true, false):
		var l := SpotLight3D.new()
		l.name = "Spot"
		l.light_color = light_color
		l.light_energy = light_energy * (0.8 if anchor.name.begins_with("Light_S") else 1.0)
		l.spot_range = light_range
		l.spot_angle = light_angle
		l.spot_angle_attenuation = 0.9
		l.spot_attenuation = 1.2
		l.shadow_enabled = true
		l.shadow_blur = 1.5
		l.light_volumetric_fog_energy = 4.0
		l.light_size = 0.12
		l.shadow_caster_mask = OUTSIDE_SHADOW_CASTERS
		# 不参与舱内 VoxelGI（灯在艇外，算进去会从壳体漏光进来）
		l.light_bake_mode = Light3D.BAKE_DISABLED
		anchor.add_child(l)
		_floodlights.append(l)
	_lens = find_child("Lens_Floodlights", true, false) as MeshInstance3D
	if _lens:
		var m := _lens.get_active_material(0)
		if m is StandardMaterial3D:
			_lens_material = m.duplicate()
			_lens.set_surface_override_material(0, _lens_material)


func _setup_stern() -> void:
	var axis := find_child("Prop_Axis", true, false) as Node3D
	var prop := find_child("Prop_Main", true, false) as Node3D
	if axis and prop:
		_prop = _pivot("PropPivot", axis, [prop])
	var stern := find_child("Pivot_Stern", true, false) as Node3D
	if stern:
		_rudder = _pivot("RudderPivot", stern, [find_child("Fin_RudderU", true, false),
			find_child("Fin_RudderD", true, false)])
		_planes = _pivot("PlanesPivot", stern, [find_child("Fin_PlaneL", true, false),
			find_child("Fin_PlaneR", true, false)])


## 在挂点处建一个转轴节点，把 parts 挂上去（保持原位）
func _pivot(nm: String, anchor: Node3D, parts: Array) -> Node3D:
	var p := Node3D.new()
	p.name = nm
	anchor.get_parent().add_child(p)
	p.transform = anchor.transform
	for n in parts:
		if n:
			(n as Node3D).reparent(p, true)
	return p


## 螺旋桨跟着推进转；方向舵跟着转向、升降舵跟着上浮下潜偏转
func _update_stern(delta: float) -> void:
	if _prop:
		var want := thrust_input * 7.0 + velocity.dot(-global_basis.z) * 0.8
		_prop_speed = move_toward(_prop_speed, want, delta * 3.0)
		if absf(_prop_speed) > 0.01:
			_prop.rotate_object_local(Vector3.BACK, _prop_speed * delta)
	# 停下来以后不再写变换：动件一动，照得到它的探照灯就得每帧重画阴影图
	if _rudder:
		var r := -clampf(yaw_speed / deg_to_rad(turn_max_deg), -1.0, 1.0) * deg_to_rad(28.0)
		if _rudder.rotation.y != r:
			_rudder.rotation.y = _approach(_rudder.rotation.y, r, 1.0 - exp(-delta * 3.0))
	if _planes:
		_lift_smooth = _approach(_lift_smooth, lift_input, 1.0 - exp(-delta * 2.0))
		var p := _lift_smooth * deg_to_rad(20.0)
		if _planes.rotation.x != p:
			_planes.rotation.x = p


## 指数逼近，离目标足够近时直接落到目标上（不然永远差一点点，每帧都在改）
static func _approach(from: float, to: float, k: float) -> float:
	var v := lerpf(from, to, k)
	return to if absf(v - to) < 1e-4 else v


func set_lights(on: bool) -> void:
	lights_on = on
	for l in _floodlights:
		l.visible = on
	if _lens_material:
		_lens_material.emission_energy_multiplier = 6.0 if on else 0.0


func set_external_view(on: bool) -> void:
	external_view = on
	# 舱内的 VoxelGI 会渗到紧贴着耐压舱的艇身外表面上（黑漆被照成灰白），在舱外看时关掉；
	# 在舱里时艇身外表面又看不见，正好互不干扰
	for gi in body.find_children("CabinGI*", "VoxelGI", false, false):
		(gi as VoxelGI).visible = not on
	if on:
		external_camera.make_current()
	else:
		cockpit_camera.make_current()


func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("toggle_lights"):
		set_lights(not lights_on)
		lights_switched.emit(lights_on)
	elif event.is_action_pressed("toggle_view"):
		set_external_view(not external_view)


func _physics_process(delta: float) -> void:
	var drive := piloting or external_view
	thrust_input = Input.get_axis("move_back", "move_forward") if drive else 0.0
	lift_input = Input.get_axis("descend", "ascend") if drive else 0.0
	var turn := Input.get_axis("turn_right", "turn_left") if drive else 0.0
	if DebugArgs.has("cruise"):
		thrust_input = float(DebugArgs.get_arg("cruise"))

	var forward := -global_basis.z
	var hv := Vector3(velocity.x, 0.0, velocity.z)
	hv += forward * thrust_input * thrust_accel * delta
	hv -= hv * water_drag * delta
	hv = hv.limit_length(max_speed)
	var vv := velocity.y + lift_input * vertical_accel * delta
	vv -= vv * water_drag * 1.5 * delta
	vv = clampf(vv, -vertical_max, vertical_max)
	velocity = Vector3(hv.x, vv, hv.z)

	# 漂到几乎停住就停死：艇停着的时候不再每帧写变换，舱里的灯才能复用上一帧的阴影图
	if velocity.length_squared() < 1e-6 and thrust_input == 0.0 and lift_input == 0.0:
		velocity = Vector3.ZERO

	yaw_speed = move_toward(yaw_speed, turn * deg_to_rad(turn_max_deg), deg_to_rad(turn_accel_deg) * delta)
	if yaw_speed != 0.0:
		rotate_y(yaw_speed * delta)

	if velocity != Vector3.ZERO:
		var before := velocity
		move_and_slide()
		if get_slide_collision_count() > 0:
			var impact := (before - velocity).length()
			if impact > 0.2:
				bumped.emit(impact)

	_update_sway(delta)
	_update_stern(delta)


## 艇身随推进、转向轻微俯仰和侧倾。
## 停着的时候不晃：一千多米深的地方没有浪；而且艇身一动，舱里所有投影灯每帧都得重画阴影图
## （舱里站着时的晃动感由相机自己的呼吸起伏给，见 cockpit_camera.gd）。
func _update_sway(delta: float) -> void:
	var target := Vector3(-thrust_input * 0.03 + lift_input * 0.02, 0.0, -yaw_speed * 0.22)
	if _sway == target:
		return
	_sway = _sway.lerp(target, 1.0 - exp(-delta * 1.4))
	if _sway.distance_to(target) < 1e-4:
		_sway = target
	body.rotation = _sway
