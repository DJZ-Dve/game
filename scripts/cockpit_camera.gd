extends Camera3D
## 舱内第一人称：坐在驾驶椅上开船，或者起身在舱里走动；走到舷窗边按住右键贴近舷窗。
## 相机挂在 Body 下面，跟着艇身一起晃；走动用的是舱内局部坐标，不走物理引擎（舱里只有一条过道）。

signal seated_changed(seated: bool)

enum Mode { SEATED, WALKING }

@export var sensitivity := 0.0022
@export var walk_speed := 1.3
@export var walk_accel := 7.0
@export var eye_height := 1.62
@export var body_radius := 0.2
@export var normal_fov := 70.0
@export var lean_fov := 58.0
@export var seated_yaw_limit := 110.0

## 能站的地方（舱内局部坐标 x、z 范围，和 blender/scripts/cockpit.py 的布局对应）：
## 两排工作台之间的过道 + 后部通往水密门的一小块（直梯后面过不去）
const WALK_AREAS := [
	Rect2(-0.56, -1.2, 1.12, 3.15),
	Rect2(-0.7, 1.76, 0.28, 0.62),
]
const DECK_Y := -0.9
const SEAT_POS := Vector2(0.0, -1.48)  # 驾驶椅（x, z）
const SIT_RANGE := 0.8
const LEAN_RANGE := 0.95

var mode := Mode.SEATED
var yaw := 0.0
var pitch := 0.0
var lean := 0.0
## 给 HUD 显示的操作提示
var prompt := ""

var _body: Node3D
var _seat_eye := Transform3D.IDENTITY
var _stand := Transform3D.IDENTITY
var _leans: Array[Transform3D] = []
var _lean_target := -1
var _pos := Vector2.ZERO  # 走动时脚下的位置（x, z）
var _vel := Vector2.ZERO
var _bob := 0.0
var _blend := 1.0  # 0→1：从切换前的位置过渡到当前模式
var _from := Transform3D.IDENTITY
var _shake := 0.0
var _noise := FastNoiseLite.new()


func configure(body: Node3D) -> void:
	_body = body
	var inv := body.global_transform.affine_inverse()
	var eye := body.find_child("Anchor_Eye", true, false) as Node3D
	if eye:
		_seat_eye = inv * eye.global_transform
	var stand := body.find_child("Anchor_Stand", true, false) as Node3D
	if stand:
		_stand = inv * stand.global_transform
	for n in ["Anchor_Lean_L", "Anchor_Lean_R"]:
		var a := body.find_child(n, true, false) as Node3D
		if a:
			_leans.append(inv * a.global_transform)
	_pos = Vector2(_stand.origin.x, _stand.origin.z)
	_apply_debug_args()


func _apply_debug_args() -> void:
	if DebugArgs.has("at"):
		var p := DebugArgs.get_arg("at").split(",")
		_pos = Vector2(float(p[0]), float(p[1]))
		mode = Mode.WALKING
	if DebugArgs.has("yaw"):
		yaw = deg_to_rad(float(DebugArgs.get_arg("yaw")))
	if DebugArgs.has("pitch"):
		pitch = deg_to_rad(float(DebugArgs.get_arg("pitch")))
	if DebugArgs.has("lean"):
		_lean_target = int(DebugArgs.get_arg("lean"))
		lean = 1.0


func _ready() -> void:
	_noise.frequency = 2.0
	add_to_group("crew")
	if not DebugArgs.has("capture"):
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED


func is_seated() -> bool:
	return mode == Mode.SEATED


func add_shake(strength: float) -> void:
	_shake = clampf(_shake + strength * 0.6, 0.0, 1.0)


func _unhandled_input(event: InputEvent) -> void:
	if not current:
		return
	if event is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		yaw -= event.relative.x * sensitivity
		pitch = clampf(pitch - event.relative.y * sensitivity, deg_to_rad(-80.0), deg_to_rad(80.0))
		if mode == Mode.SEATED:
			yaw = clampf(yaw, -deg_to_rad(seated_yaw_limit), deg_to_rad(seated_yaw_limit))
	elif event.is_action_pressed("interact"):
		_interact()
	elif event.is_action_pressed("release_mouse"):
		Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	elif event is InputEventMouseButton and event.pressed and Input.mouse_mode != Input.MOUSE_MODE_CAPTURED:
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED


func _interact() -> void:
	if mode == Mode.SEATED:
		_switch(Mode.WALKING)
		_pos = Vector2(_stand.origin.x, _stand.origin.z)
		_vel = Vector2.ZERO
		yaw = 0.0
	elif _near_seat():
		_switch(Mode.SEATED)
		yaw = 0.0
		pitch = 0.0


func _switch(m: Mode) -> void:
	_from = transform
	_blend = 0.0
	mode = m
	lean = 0.0
	seated_changed.emit(m == Mode.SEATED)


func _near_seat() -> bool:
	return _pos.distance_to(SEAT_POS) < SIT_RANGE


## 站在舷窗附近、脸朝着它：返回舷窗编号，否则 -1。
func _facing_viewport() -> int:
	var look := Vector2(-sin(yaw), -cos(yaw))
	for i in _leans.size():
		var o := _leans[i].origin
		var to := Vector2(o.x, o.z) - _pos
		if to.length() < LEAN_RANGE and look.dot(to.normalized()) > 0.5:
			return i
	return -1


func _process(delta: float) -> void:
	var t := Time.get_ticks_msec() / 1000.0
	var base: Transform3D
	var look := Basis.from_euler(Vector3(pitch, yaw, 0.0))

	if mode == Mode.SEATED:
		prompt = "E 起身" if current else ""
		base = Transform3D(_seat_eye.basis * look, _seat_eye.origin)
		base.origin += Vector3(sin(t * 0.9) * 0.004, sin(t * 1.7) * 0.003, 0.0)  # 呼吸
	else:
		_walk(delta)
		var vp := _facing_viewport()
		if not DebugArgs.has("lean"):
			_lean_target = vp if (vp >= 0 and current and Input.is_action_pressed("lean")) else _lean_target
			var want := 1.0 if (_lean_target >= 0 and current and Input.is_action_pressed("lean")) else 0.0
			lean = move_toward(lean, want, delta * 2.5)
			if lean == 0.0:
				_lean_target = -1
		if _near_seat():
			prompt = "E 坐下驾驶"
		elif vp >= 0 and lean < 0.5:
			prompt = "按住右键 贴近舷窗"
		else:
			prompt = ""
		var step := sin(_bob) * 0.025 * clampf(_vel.length() / walk_speed, 0.0, 1.0)
		base = Transform3D(Basis(Vector3.UP, yaw) * Basis(Vector3.RIGHT, pitch),
			Vector3(_pos.x, DECK_Y + eye_height + step, _pos.y))
		base.origin += Vector3(cos(_bob * 0.5) * 0.012, 0, 0).rotated(Vector3.UP, yaw) * clampf(
			_vel.length() / walk_speed, 0.0, 1.0)
		if lean > 0.0 and _lean_target >= 0:
			var k := smoothstep(0.0, 1.0, lean)
			var tgt := _leans[_lean_target]
			base = Transform3D(base.basis.slerp(tgt.basis * Basis.from_euler(Vector3(pitch * 0.3, 0, 0)), k),
				base.origin.lerp(tgt.origin, k))
		fov = lerpf(normal_fov, lean_fov, smoothstep(0.0, 1.0, lean))

	# 模式切换时平滑过渡
	if _blend < 1.0:
		_blend = minf(_blend + delta * 2.2, 1.0)
		var k := smoothstep(0.0, 1.0, _blend)
		base = Transform3D(_from.basis.slerp(base.basis.orthonormalized(), k), _from.origin.lerp(base.origin, k))

	_shake = maxf(_shake - delta * 1.5, 0.0)
	if _shake > 0.0:
		var s := _shake * _shake
		base.origin += Vector3(_noise.get_noise_2d(t * 40.0, 0.0), _noise.get_noise_2d(0.0, t * 40.0), 0.0) * 0.03 * s
		base.basis = base.basis * Basis.from_euler(Vector3(_noise.get_noise_2d(t * 30.0, 5.0) * 0.05 * s, 0.0,
			_noise.get_noise_2d(7.0, t * 30.0) * 0.08 * s))
	transform = base


func _walk(delta: float) -> void:
	var input := Vector2.ZERO
	if current and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED and lean < 0.1:
		input = Input.get_vector("turn_left", "turn_right", "move_forward", "move_back")
	var wish := input.rotated(-yaw) * walk_speed
	_vel = _vel.move_toward(wish, walk_accel * delta)
	_pos = _clamp_to_walkable(_pos + _vel * delta)
	_bob += _vel.length() * delta * 7.0


## 把脚下位置限制在能站的区域里（几块矩形的并集，取最近的那块）。
func _clamp_to_walkable(p: Vector2) -> Vector2:
	var best := p
	var best_d := INF
	for r: Rect2 in WALK_AREAS:
		var q := p.clamp(r.position, r.end)
		var d := q.distance_squared_to(p)
		if d < best_d:
			best_d = d
			best = q
	return best
