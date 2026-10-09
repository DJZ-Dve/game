extends Camera3D
## 舱内第一人称：坐在驾驶椅上开船，或者起身在舱里走动；走到舷窗边按住右键贴近舷窗。
## 相机挂在 Body 下面，跟着艇身一起晃；走动用的是舱内局部坐标，不走物理引擎（舱里只有一条过道）。

signal seated_changed(seated: bool)
## 走动时每落一步（脚落地的位置，舱内局部坐标；strength 0~1 按步速）
signal stepped(foot: Vector3, strength: float)

enum Mode { SEATED, WALKING }

@export var sensitivity := 0.0022
@export var walk_speed := 1.3
@export var walk_accel := 7.0
@export var eye_height := 1.62
@export var body_radius := 0.2
@export var normal_fov := 70.0
@export var lean_fov := 58.0
@export var seated_yaw_limit := 110.0

## 能站的地方（舱内局部坐标 x、z 范围，和 blender/scripts/cockpit.py、quarters.py 的布局对应）。
## 控制舱：两排工作台之间的过道 + 后面水密门前的一块（门开着时门扇占掉左边一半）
const FRONT_AISLE := Rect2(-0.56, -1.2, 1.12, 3.15)
const FRONT_REAR := Rect2(-0.6, 1.76, 1.0, 0.44)
const FRONT_AISLE_DOOR_OPEN := Rect2(-0.56, -1.2, 1.12, 2.8)
const FRONT_REAR_DOOR_OPEN := Rect2(-0.3, 1.6, 0.7, 0.6)
## 门洞（只有门开着才能过）
const DOORWAY := Rect2(-0.12, 2.2, 0.24, 0.65)
## 生活舱：门后的过道（厨房和衣柜之间），直梯两边各一条窄道，铺位之间的过道一直到后隔壁
const AFT_AREAS := [
	Rect2(-0.5, 2.85, 1.0, 0.47),
	Rect2(-0.5, 3.3, 0.11, 0.56),
	Rect2(0.39, 3.3, 0.11, 0.56),
	Rect2(-0.4, 3.84, 0.8, 2.26),
]
const DECK_Y := -0.9
const SEAT_POS := Vector2(0.0, -1.48)  # 驾驶椅（x, z）
const SIT_RANGE := 0.8
const LEAN_RANGE := 0.95
const DOOR_POS := Vector2(0.0, 2.6)  # 水密门（x, z），和 cockpit.py 的 DOOR、Y_AFT 对应
const DOOR_RANGE := 1.1
## 过门时要低头（门洞上沿离地 1.63 米）
const DOOR_DUCK := 0.26

@export var door_path: NodePath

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
var _bob := 0.0  # 走路的相位：每 2π 一步，(_bob + π/2) 是 2π 的整数倍时脚落地
var _land := 0.0  # 落脚时身体被压下去的量（米，负的），弹簧阻尼弹回
var _land_v := 0.0
var _blend := 1.0  # 0→1：从切换前的位置过渡到当前模式
var _from := Transform3D.IDENTITY
var _shake := 0.0
var _noise := FastNoiseLite.new()
var _door: Node


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
	_door = get_node_or_null(door_path)
	if not DebugArgs.has("capture") and Engine.get_write_movie_path().is_empty():
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
	elif _facing_door():
		_door.toggle()


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


## 站在水密门跟前（门两边都行）、脸朝着门
func _facing_door() -> bool:
	if _door == null or _door.busy:
		return false
	var to: Vector2 = DOOR_POS - _pos
	var look := Vector2(-sin(yaw), -cos(yaw))
	return to.length() < DOOR_RANGE and look.dot(to.normalized()) > 0.4


func _door_open() -> bool:
	return _door != null and _door.openness > 0.75


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
		elif _facing_door():
			prompt = "E 关门" if _door.is_open else "E 开门"
		else:
			prompt = ""
		# 走路的起伏按「倒摆」来：脚踩在身体正下方时头最高，两脚交替落地的瞬间最低（是个尖角，不是正弦波）；
		# 每两步左右晃一次，重心移到撑地的那只脚上，头也往那边歪一点；落脚时再被压一下、点一下头（_land）
		var sp := clampf(_vel.length() / walk_speed, 0.0, 1.0)
		var steps := (_bob + PI / 2.0) / TAU          # 走过的步数，整数时脚落地
		var arc := sin(PI * fposmod(steps, 1.0)) - 0.64  # 0.64 是弧线的平均值，平均高度不变
		var side := sin(PI * fposmod(steps, 2.0))       # 正：右脚撑地，负：左脚撑地
		var duck := 0.0
		if _door:
			duck = DOOR_DUCK * (1.0 - smoothstep(0.12, 0.5, absf(_pos.y - DOOR_POS.y)))
		base = Transform3D(Basis(Vector3.UP, yaw) * Basis(Vector3.RIGHT, pitch + _land * 1.2)
			* Basis(Vector3.BACK, -side * deg_to_rad(0.5) * sp),
			Vector3(_pos.x, DECK_Y + eye_height - duck + arc * 0.028 * sp + _land, _pos.y))
		base.origin += Vector3(side * 0.014 * sp, 0, 0).rotated(Vector3.UP, yaw)
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
	var scripted := DebugArgs.has("actions")  # 录音测试时由脚本按键，鼠标没被捕获
	if current and (Input.mouse_mode == Input.MOUSE_MODE_CAPTURED or scripted) and lean < 0.1:
		input = Input.get_vector("turn_left", "turn_right", "move_forward", "move_back")
	var wish := input.rotated(-yaw) * walk_speed
	_vel = _vel.move_toward(wish, walk_accel * delta)
	# 门洞只有 24 厘米宽：开着门朝门洞走时，把人往门洞中线上带，别卡在门框上
	if _door_open() and absf(_pos.y - DOOR_POS.y) < 0.6 and _vel.y * signf(DOOR_POS.y - _pos.y) > 0.05:
		_pos.x = move_toward(_pos.x, DOOR_POS.x, absf(_vel.y) * delta * 1.2)
	var before := _pos
	_pos = _clamp_to_walkable(_pos + _vel * delta)
	var bob0 := _bob
	# 步伐按实际挪动的距离算：顶着墙走时人没动，不该原地踏步
	_bob += _pos.distance_to(before) * 8.9  # 全速 1.3 m/s 时每秒 1.85 步（舱里过道窄，步子小）
	_land_v += (-_land * 400.0 - _land_v * 28.0) * delta
	_land += _land_v * delta
	# 两脚交替落地：步数跨过整数的那一帧
	var k := floorf((_bob + PI / 2.0) / TAU)
	if k > floorf((bob0 + PI / 2.0) / TAU):
		var side := 0.11 if int(k) % 2 == 0 else -0.11
		var foot := Vector3(_pos.x, DECK_Y, _pos.y) + Vector3(side, 0, 0).rotated(Vector3.UP, yaw)
		var strength := clampf(_vel.length() / walk_speed, 0.0, 1.0)
		_land_v -= 0.13 * strength
		stepped.emit(foot, strength)


func _walk_areas() -> Array:
	var open := _door_open()
	var leaf_out: bool = _door != null and (_door.openness > 0.05 or _door.busy)  # 门扇甩进控制舱，占掉左后角
	var areas := [FRONT_AISLE_DOOR_OPEN, FRONT_REAR_DOOR_OPEN] if leaf_out else [FRONT_AISLE, FRONT_REAR]
	if open:
		areas.append(DOORWAY)
	areas.append_array(AFT_AREAS)
	return areas


## 把脚下位置限制在能站的区域里（几块矩形的并集，取最近的那块）。
## 门关着时前后两舱互不相通：只在当前所在的那个舱里找（关门时站在门洞里的人被推回原来那边）。
func _clamp_to_walkable(p: Vector2) -> Vector2:
	var best := p
	var best_d := INF
	var areas := _walk_areas()
	if not _door_open() and _door:
		var aft := _pos.y > DOOR_POS.y
		areas = areas.filter(func(r: Rect2) -> bool: return (r.position.y > DOOR_POS.y) == aft)
	for r: Rect2 in areas:
		var q := p.clamp(r.position, r.end)
		var d := q.distance_squared_to(p)
		if d < best_d:
			best_d = d
			best = q
	return best
