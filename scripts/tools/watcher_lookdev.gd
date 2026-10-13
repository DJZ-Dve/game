extends Node3D
## 巨物「大眼」看样场景（lookdev）：静止姿态的 watcher.glb、深海环境（deep_sea_env.tres + 水体吸收 / 海雪，同 water_fx.gd）、
## 一盏像潜艇探照灯的聚光灯，很弱的环境光。按材质名把 assets/materials/ 下的同名 .tres 直接套上去
## （改完 .tres / 着色器直接截图就是最新的，不用重新导入 glb）。结构照 giant_lookdev.gd，精简版。
##
## 后台截图（不抢焦点、不出声）：
##   python tools/capture.py out.png --scene=res://scenes/dev/watcher_lookdev.tscn --shot=q34 --light=front
## 参数（`--` 之后）：
##   --shot=名字      机位：front 正面、q34 前上方 3/4、side 侧面、below 前下方、back 后上方、
##                    eye 眼睛近景、lid 眼睑和眼窝（斜上方）、shell 背甲近景、spikes 背刺、
##                    paddle 右侧的桨（从前下方）、paddle_tip 叶片近景、siphon 腹面虹吸口
##   --light=front|side|back|top|below  灯从哪边来（相对机位；back 逆光看桨的透光）
##   --lid=0~1        眼睑闭合（1 全闭）；--gaze=左右度,上下度 转眼（--look 被 debug_args 占用）；--pupil=0~1 瞳孔张开；--glow=0~1 虹膜发光
##   --stroke=度      桨根绕竖直轴往前（正）/ 往后划多少度（看关节和根部肉褶的蒙皮）；--pose=raw 不动骨骼
##   --fog=倍数 --energy=倍数 --ambient=倍数 --water=off --snow=off   同 giant_lookdev
##   --mat=M_WatcherShell 全身换成这个材质；--mat=_faces 查法线翻没翻（背面红）
##   --param=名字:值;名字:值   临时改着色器参数（例 `--param=debug_view:4` 看区域图）
##   --cam=x,y,z --target=x,y,z --fov=度   自定机位（覆盖 --shot）
## 交互（编辑器里直接跑这个场景）：右键拖动转、滚轮推拉、中键拖动平移，1~9 换机位，L 换灯。
##
## 坐标：Blender (x, y, z) → Godot (x, z, -y)：眼睛朝 -Z，+X 右，原点在身体中心。

const WATCHER := preload("res://assets/models/watcher.glb")
const ENV := preload("res://assets/environment/deep_sea_env.tres")
const WATER := preload("res://scripts/water_fx.gd")
const MAT_DIR := "res://assets/materials/"
const LID_CLOSE := 75.0

const SHOTS := {
	"front": {"cam": Vector3(5, 2, -44), "target": Vector3(0, 0, 0), "fov": 46.0, "spot": 34.0, "fog": 0.15},
	"q34": {"cam": Vector3(30, 13, -32), "target": Vector3(0, -1, 0), "fov": 48.0, "spot": 36.0, "fog": 0.15},
	"side": {"cam": Vector3(46, 3, 2), "target": Vector3(0, -1.5, 1), "fov": 48.0, "spot": 36.0, "fog": 0.15},
	"below": {"cam": Vector3(22, -28, -20), "target": Vector3(0, -2, 0), "fov": 50.0, "spot": 38.0, "fog": 0.15},
	"back": {"cam": Vector3(-14, 12, 40), "target": Vector3(0, 0, 0), "fov": 48.0, "spot": 36.0, "fog": 0.15},
	"eye": {"cam": Vector3(3.5, 2.5, -24), "target": Vector3(0, 0.3, -6), "fov": 42.0, "spot": 28.0, "fog": 0.3},
	"lid": {"cam": Vector3(9, 9, -15), "target": Vector3(1.5, 2.5, -7), "fov": 42.0, "spot": 28.0, "fog": 0.3},
	"shell": {"cam": Vector3(7, 13, 2), "target": Vector3(3, 7, -1), "fov": 45.0, "spot": 30.0, "fog": 0.3},
	"spikes": {"cam": Vector3(14, 14, 10), "target": Vector3(0, 8, 2), "fov": 45.0, "spot": 32.0, "fog": 0.3},
	"paddle": {"cam": Vector3(20, -12, -8), "target": Vector3(11, -4.5, 3), "fov": 48.0, "spot": 32.0, "fog": 0.3},
	"paddle_tip": {"cam": Vector3(18, -9, 0), "target": Vector3(14, -6, 5), "fov": 42.0, "spot": 28.0, "fog": 0.4},
	"siphon": {"cam": Vector3(3, -13, -4), "target": Vector3(0, -7, -1.5), "fov": 42.0, "spot": 28.0, "fog": 0.4},
}
const SHOT_KEYS := ["front", "q34", "side", "below", "eye", "lid", "shell", "paddle", "siphon"]
const LIGHTS := ["front", "side", "back", "top", "below"]

var watcher: Node3D
var skeleton: Skeleton3D
var cam: Camera3D
var spot: SpotLight3D
var env: Environment

var shot := "q34"
var light_mode := "front"
var _target := Vector3.ZERO
var _spot_angle := 30.0
var _energy := 1.0
var _orbit_drag := false
var _pan_drag := false


func _ready() -> void:
	env = ENV.duplicate()
	env.ambient_light_energy *= float(DebugArgs.get_arg("ambient", "1"))
	var we := WorldEnvironment.new()
	we.environment = env
	add_child(we)

	watcher = WATCHER.instantiate()
	add_child(watcher)
	skeleton = _find(watcher, "Skeleton3D") as Skeleton3D
	_apply_materials(watcher, DebugArgs.get_arg("mat"))
	for mi in _meshes(watcher):
		mi.set_instance_shader_parameter("pupil", float(DebugArgs.get_arg("pupil", "0.15")))
		mi.set_instance_shader_parameter("glow", float(DebugArgs.get_arg("glow", "0")))

	cam = Camera3D.new()
	cam.near = 0.1
	cam.far = 400.0
	add_child(cam)
	cam.make_current()

	spot = SpotLight3D.new()
	spot.light_color = Color(1.0, 0.93, 0.82)
	spot.spot_attenuation = 1.2
	spot.spot_angle_attenuation = 0.9
	spot.shadow_enabled = true
	spot.shadow_blur = 1.5
	spot.light_size = 0.12
	spot.light_volumetric_fog_energy = 4.0
	add_child(spot)

	if DebugArgs.get_arg("water", "on") != "off":
		var water := Node3D.new()
		water.set_script(WATER)
		var far := Node3D.new()
		far.name = "FarCabin"
		far.position = Vector3(0, -5000, 0)
		water.add_child(far)
		water.set("cabin_path", NodePath("FarCabin"))
		add_child(water)
		if DebugArgs.get_arg("snow", "on") == "off":
			for c in water.get_children():
				if c is MeshInstance3D and c.name != "Underwater":
					c.visible = false

	_energy = float(DebugArgs.get_arg("energy", "1"))
	light_mode = DebugArgs.get_arg("light", "front")
	_set_shot(DebugArgs.get_arg("shot", "q34"))
	if DebugArgs.has("cam"):
		cam.position = _vec(DebugArgs.get_arg("cam"))
		_target = _vec(DebugArgs.get_arg("target", "0,0,0"))
	if DebugArgs.has("fov"):
		cam.fov = float(DebugArgs.get_arg("fov"))
	_apply_pose()
	_update_view()


func _find(n: Node, cls: String) -> Node:
	if n.is_class(cls):
		return n
	for c in n.get_children():
		var r := _find(c, cls)
		if r:
			return r
	return null


func _meshes(n: Node, out: Array[MeshInstance3D] = []) -> Array[MeshInstance3D]:
	if n is MeshInstance3D:
		out.append(n)
	for c in n.get_children():
		_meshes(c, out)
	return out


const FACES_SHADER := "shader_type spatial;\nrender_mode cull_disabled;\nvoid fragment() {\n\tALBEDO = FRONT_FACING ? vec3(0.5) : vec3(0.8, 0.03, 0.03);\n\tROUGHNESS = 0.6;\n}\n"


func _apply_materials(n: Node, override: String) -> void:
	if n is MeshInstance3D and n.mesh:
		var mi := n as MeshInstance3D
		if override == "_faces":
			var sh := Shader.new()
			sh.code = FACES_SHADER
			var fm := ShaderMaterial.new()
			fm.shader = sh
			mi.material_override = fm
			return
		for i in mi.mesh.get_surface_count():
			var m := mi.mesh.surface_get_material(i)
			var nm := m.resource_name if m else ""
			if not override.is_empty() and nm != "M_WatcherCornea":
				nm = override
			var path := MAT_DIR + nm + ".tres"
			if not nm.is_empty() and ResourceLoader.exists(path):
				mi.set_surface_override_material(i, _tweak(load(path)))
	for c in n.get_children():
		_apply_materials(c, override)


var _tweaked := {}


func _tweak(m: Material) -> Material:
	if not DebugArgs.has("param") or not m is ShaderMaterial:
		return m
	if _tweaked.has(m):
		return _tweaked[m]
	var sm := (m as ShaderMaterial).duplicate() as ShaderMaterial
	var names := {}
	for u in sm.shader.get_shader_uniform_list(true):
		names[u.name] = u.type
	for item in DebugArgs.get_arg("param").split(";", false):
		var kv := item.split(":")
		if kv.size() < 2 or not names.has(kv[0]):
			continue
		var parts := kv[1].split(",")
		var v: Variant = float(kv[1])
		if parts.size() == 2:
			v = Vector2(float(parts[0]), float(parts[1]))
		elif parts.size() >= 3:
			v = Color(float(parts[0]), float(parts[1]), float(parts[2]))
		elif names[kv[0]] == TYPE_INT:
			v = int(kv[1])
		sm.set_shader_parameter(kv[0], v)
	_tweaked[m] = sm
	return sm


func _set_shot(nm: String) -> void:
	if not SHOTS.has(nm):
		push_warning("watcher_lookdev: 没有机位 %s，用 q34" % nm)
		nm = "q34"
	shot = nm
	var s: Dictionary = SHOTS[nm]
	cam.position = s.cam
	_target = s.target
	cam.fov = s.fov
	_spot_angle = s.spot
	var fog := float(DebugArgs.get_arg("fog", str(s.get("fog", 1.0))))
	env.fog_density = ENV.fog_density * fog
	env.volumetric_fog_density = ENV.volumetric_fog_density * fog


func _update_view() -> void:
	cam.look_at(_target, Vector3.UP)
	var view := _target - cam.position
	var dist := view.length()
	var fwd := view / dist
	var right := fwd.cross(Vector3.UP).normalized()
	var ld := maxf(dist * 0.85, 8.0)
	var pos: Vector3
	match light_mode:
		"side":
			pos = _target - fwd * ld * 0.6 + right * ld * 0.8 + Vector3.UP * ld * 0.3
		"back":
			pos = _target + fwd * ld * 0.9 + right * ld * 0.35 + Vector3.UP * ld * 0.35
		"top":
			pos = _target - fwd * ld * 0.25 + Vector3.UP * ld
		"below":
			pos = _target - fwd * ld * 0.4 - Vector3.UP * ld * 0.9 + right * ld * 0.2
		_:
			pos = cam.position + right * minf(2.5, dist * 0.12) + Vector3.UP * minf(1.5, dist * 0.08)
	spot.position = pos
	spot.look_at(_target, Vector3.UP if absf((_target - pos).normalized().y) < 0.95 else Vector3.FORWARD)
	var d := pos.distance_to(_target)
	spot.spot_range = d * 2.0 + 40.0
	spot.spot_angle = _spot_angle
	spot.light_energy = 22.0 * pow(maxf(d, 6.0) / 12.0, 1.2) * _energy


## 闭眼、转眼、划桨：绕世界轴转，换算到每根骨头自己的坐标系里
func _apply_pose() -> void:
	if not skeleton or DebugArgs.get_arg("pose") == "raw":
		return
	var lid := float(DebugArgs.get_arg("lid", "0"))
	var look := _vec(DebugArgs.get_arg("gaze", "0,0") + ",0")
	var stroke := float(DebugArgs.get_arg("stroke", "0"))
	var to_skel := skeleton.global_transform.basis.inverse()
	for i in skeleton.get_bone_count():
		var bn := skeleton.get_bone_name(i)
		var rest := skeleton.get_bone_rest(i)
		var q := rest.basis.get_rotation_quaternion()
		var grest := skeleton.get_bone_global_rest(i).basis.orthonormalized()
		var rot := Quaternion.IDENTITY
		if bn == "LidUp" or bn == "LidLo":
			var sg := -1.0 if bn == "LidUp" else 1.0
			rot = Quaternion(Vector3.RIGHT, sg * deg_to_rad(LID_CLOSE) * lid)
		elif bn == "Eye":
			rot = Quaternion(Vector3.UP, -deg_to_rad(look.x)) * Quaternion(Vector3.RIGHT, deg_to_rad(look.y))
		elif bn.begins_with("Paddle") and bn.ends_with("_0"):
			var side := 1.0 if bn.begins_with("PaddleR") else -1.0
			rot = Quaternion(Vector3.UP, side * deg_to_rad(stroke))
		if rot != Quaternion.IDENTITY:
			var w := to_skel * Basis(rot) * to_skel.inverse()
			var local := Quaternion((grest.inverse() * w * grest).orthonormalized())
			q = q * local
		skeleton.set_bone_pose_rotation(i, q)
		skeleton.set_bone_pose_position(i, rest.origin)


func _vec(s: String) -> Vector3:
	var p := s.split(",")
	if p.size() < 3:
		return Vector3.ZERO
	return Vector3(float(p[0]), float(p[1]), float(p[2]))


func _unhandled_input(e: InputEvent) -> void:
	if e is InputEventMouseButton:
		var mb := e as InputEventMouseButton
		if mb.button_index == MOUSE_BUTTON_RIGHT:
			_orbit_drag = mb.pressed
		elif mb.button_index == MOUSE_BUTTON_MIDDLE:
			_pan_drag = mb.pressed
		elif mb.pressed and (mb.button_index == MOUSE_BUTTON_WHEEL_UP or mb.button_index == MOUSE_BUTTON_WHEEL_DOWN):
			var k := 0.9 if mb.button_index == MOUSE_BUTTON_WHEEL_UP else 1.1
			cam.position = _target + (cam.position - _target) * k
			_update_view()
	elif e is InputEventMouseMotion and (_orbit_drag or _pan_drag):
		var mm := e as InputEventMouseMotion
		if _orbit_drag:
			var off := cam.position - _target
			off = off.rotated(Vector3.UP, -mm.relative.x * 0.01)
			var right := off.cross(Vector3.UP).normalized()
			off = off.rotated(right, -mm.relative.y * 0.01)
			cam.position = _target + off
		else:
			var dist := cam.position.distance_to(_target)
			var delta := (-cam.global_basis.x * mm.relative.x + cam.global_basis.y * mm.relative.y) * dist * 0.0015
			cam.position += delta
			_target += delta
		_update_view()
	elif e is InputEventKey and e.pressed and not e.echo:
		var k := (e as InputEventKey).keycode
		if k >= KEY_1 and k <= KEY_9 and k - KEY_1 < SHOT_KEYS.size():
			_set_shot(SHOT_KEYS[k - KEY_1])
			_update_view()
		elif k == KEY_L:
			light_mode = LIGHTS[(LIGHTS.find(light_mode) + 1) % LIGHTS.size()]
			_update_view()
