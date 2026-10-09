extends Camera3D
## 舱内第一人称：坐在驾驶椅上开船，或者起身在舱里走动；走到舷窗边按住右键贴近舷窗。
## 相机挂在 Body 下面，跟着艇身一起晃；走动用的是舱内局部坐标，不走物理引擎（舱里只有一条过道）。

signal seated_changed(seated: bool)
## 走动时每落一步：脚落地的位置（舱内局部坐标）、strength 0~1 按步速、kind 是 walk / run / settle（停下收脚）
signal stepped(foot: Vector3, strength: float, kind: StringName)

enum Mode { SEATED, WALKING }

@export var sensitivity := 0.0022
@export var walk_speed := 1.25
@export var run_speed := 2.5
@export var walk_accel := 7.0
@export var run_accel := 5.0
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
## 过门时要低头（门洞上沿离地 1.65 米）
const DOOR_DUCK := 0.26
## 开关门时站的地方：控制舱这边拧手轮站在门正前方；门扇往控制舱这边开、扫过门前，所以开门拉门时往右后方让开，
## 关门时也先站在右后方伸手去够；生活舱那边门往外推开、往里拉上，一直站在门前
## 手轮在腰那么高，拧的时候低着头、上身往前探（door_lean，crew_body.gd 跟着弯腰）
const DOOR_STAND_FRONT := Vector2(0.0, 2.0)
const DOOR_STAND_SIDE := Vector2(0.4, 1.85)   # 离门轴 1 米多，门扇（半径 0.82 米）扫不到
const DOOR_STAND_AFT := Vector2(0.0, 3.0)
const DOOR_LOOK_PITCH := -0.95
const DOOR_LEAN := Vector2(0.14, 0.07)  # 探身时眼睛往前、往下挪多少

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
## 步伐：走过的步数，整数时脚落地（偶数左脚、奇数右脚）。步频按实际速度算，crew_body.gd 按它对齐走路、跑步动画
var gait_steps := 0.0
## 实际移动的速度（米/秒，平滑过）；跑的程度 0 走 → 1 跑（按速度算）
var gait_speed := 0.0
var gait_run := 0.0
var _stepping := false
var _sprint := 0.0
var _land := 0.0  # 落脚时身体被压下去的量（米，负的），弹簧阻尼弹回
var _land_v := 0.0
var _blend := 1.0  # 0→1：从切换前的位置过渡到当前模式
var _from := Transform3D.IDENTITY
var _shake := 0.0
var _noise := FastNoiseLite.new()
var _door: Node
## 正在开关门（走过去、动手、让开），这期间不听走动按键；door_aft 是人在生活舱那边
var door_op := false
var door_aft := false
var door_yaw := 0.0
## 拧手轮时上身往前探的程度 0~1
var door_lean := 0.0
var _door_toggled := false
var _door_t := 0.0
var _auto_pos := Vector2.ZERO
var _auto_aim := false


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


## 给 crew_body.gd：脚下的位置（舱内局部 x、z）
func feet() -> Vector2:
	return _pos


## 坐着的程度：0 站着走动 → 1 坐在驾驶椅上，起身、坐下时跟着视角一起平滑过渡
func sit_amount() -> float:
	var k := smoothstep(0.0, 1.0, _blend)
	return k if mode == Mode.SEATED else 1.0 - k


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
	if door_op:
		return
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
		_start_door()


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


## 开关门：先走到手轮跟前站好、看着手轮，再动手；门扇甩过来时让开，关上以后再上前拧紧（_door_choreo）
func _start_door() -> void:
	door_op = true
	door_aft = _pos.y > DOOR_POS.y
	_door_toggled = false
	_door_t = 0.0
	if door_aft:
		_go(DOOR_STAND_AFT, 0.0)
	elif _door.is_open:
		_go(DOOR_STAND_SIDE, PI - 0.35)
	else:
		_go(DOOR_STAND_FRONT, PI)


func _go(p: Vector2, face: float) -> void:
	_auto_pos = p
	door_yaw = face
	_auto_aim = true


func _door_choreo(delta: float) -> void:
	_door_t += delta
	var arrived := _pos.distance_to(_auto_pos) < 0.04 and gait_speed < 0.2
	if arrived:
		_auto_aim = false
	if not _door_toggled:
		if arrived or _door_t > 1.6:
			_door_toggled = true
			_door.toggle()
		return
	if not door_aft:
		var h: float = _door.hinge_angle()
		if _door.is_open and h < deg_to_rad(0.5) and _auto_pos != DOOR_STAND_FRONT:
			_go(DOOR_STAND_FRONT, PI)       # 关上了：上前一步拧紧
		elif not _door.is_open and h > deg_to_rad(3.0) and _auto_pos != DOOR_STAND_SIDE:
			_go(DOOR_STAND_SIDE, PI - 0.35)  # 门扇朝人甩过来：往右后方让开
	if not _door.busy:
		door_op = false
		_auto_aim = false


## 站在水密门跟前（门两边都行）、脸朝着门
func _facing_door() -> bool:
	if _door == null or _door.busy or door_op:
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
		if door_op:
			_door_choreo(delta)
		var hands_on: bool = door_op and _door.hands and _pos.distance_to(_auto_pos) < 0.1
		door_lean = move_toward(door_lean, 1.0 if hands_on else 0.0, delta * 2.5)
		_walk(delta)
		var vp := _facing_viewport()
		if not DebugArgs.has("lean"):
			_lean_target = vp if (vp >= 0 and current and Input.is_action_pressed("lean")) else _lean_target
			var want := 1.0 if (_lean_target >= 0 and current and Input.is_action_pressed("lean")) else 0.0
			lean = move_toward(lean, want, delta * 2.5)
			if lean == 0.0:
				_lean_target = -1
		if door_op:
			prompt = ""
		elif _near_seat():
			prompt = "E 坐下驾驶"
		elif vp >= 0 and lean < 0.5:
			prompt = "按住右键 贴近舷窗"
		elif _facing_door():
			prompt = "E 关门" if _door.is_open else "E 开门"
		else:
			prompt = ""
		# 走路的起伏按「倒摆」来：脚踩在身体正下方时头最高，两脚交替落地的瞬间最低（是个尖角，不是正弦波）；
		# 每两步左右晃一次，重心移到撑地的那只脚上，头也往那边歪一点；落脚时再被压一下、点一下头（_land）
		# 跑起来起伏更大、更尖，左右晃得少一点，落脚压得更狠，视野略微拉宽
		var sp := clampf(gait_speed / walk_speed, 0.0, 1.0)
		var steps := gait_steps
		var arc := sin(PI * fposmod(steps, 1.0)) - 0.64  # 0.64 是弧线的平均值，平均高度不变
		var side := -sin(PI * fposmod(steps, 2.0))      # 负：左脚撑地（刚落的是左脚），正：右脚撑地
		var amp := lerpf(0.028, 0.048, gait_run)
		var duck := 0.0
		if _door:
			duck = DOOR_DUCK * (1.0 - smoothstep(0.12, 0.5, absf(_pos.y - DOOR_POS.y)))
			if door_op:
				duck = 0.0  # 开关门时站在门前，不是在钻门
		base = Transform3D(Basis(Vector3.UP, yaw) * Basis(Vector3.RIGHT, pitch + _land * 1.2)
			* Basis(Vector3.BACK, -side * deg_to_rad(0.5) * sp),
			Vector3(_pos.x, DECK_Y + eye_height - duck + arc * amp * sp + _land, _pos.y))
		base.origin += Vector3(side * lerpf(0.014, 0.01, gait_run) * sp, 0, 0).rotated(Vector3.UP, yaw)
		var lk := smoothstep(0.0, 1.0, door_lean)
		base.origin += Vector3(-sin(door_yaw), 0, -cos(door_yaw)) * DOOR_LEAN.x * lk + Vector3.DOWN * DOOR_LEAN.y * lk
		if lean > 0.0 and _lean_target >= 0:
			var k := smoothstep(0.0, 1.0, lean)
			var tgt := _leans[_lean_target]
			base = Transform3D(base.basis.slerp(tgt.basis * Basis.from_euler(Vector3(pitch * 0.3, 0, 0)), k),
				base.origin.lerp(tgt.origin, k))
		fov = lerpf(normal_fov + 4.0 * gait_run, lean_fov, smoothstep(0.0, 1.0, lean))

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
	if current and (Input.mouse_mode == Input.MOUSE_MODE_CAPTURED or scripted) and lean < 0.1 and not door_op:
		input = Input.get_vector("turn_left", "turn_right", "move_forward", "move_back")
	# 按住 Shift 往前跑（往后退、横着走不跑）；门洞跟前要低头钻门，跑不起来
	var near_door := absf(_pos.y - DOOR_POS.y) < 0.7
	var want_run := current and Input.is_action_pressed("sprint") and input.y < -0.3 and not near_door
	_sprint = move_toward(_sprint, 1.0 if want_run else 0.0, delta * 3.0)
	var top := lerpf(walk_speed, run_speed, _sprint)
	if near_door:
		top = minf(top, walk_speed * 0.8)
	var wish := input.rotated(-yaw) * top
	if door_op:
		# 开关门时自己走到位、转过去看着手轮（走的时候才强行转视角，站定了鼠标照样能看）
		var to := _auto_pos - _pos
		wish = to.normalized() * minf(walk_speed * 0.7, to.length() * 4.0) if to.length() > 0.01 else Vector2.ZERO
		if _auto_aim:
			var k := 1.0 - exp(-delta * 6.0)
			yaw = lerp_angle(yaw, door_yaw, k)
			pitch = lerpf(pitch, DOOR_LOOK_PITCH, k)
	_vel = _vel.move_toward(wish, lerpf(walk_accel, run_accel, _sprint) * delta)
	# 门洞只有 24 厘米宽：开着门朝门洞走时，把人往门洞中线上带，别卡在门框上
	if _door_open() and absf(_pos.y - DOOR_POS.y) < 0.6 and _vel.y * signf(DOOR_POS.y - _pos.y) > 0.05:
		_pos.x = move_toward(_pos.x, DOOR_POS.x, absf(_vel.y) * delta * 1.2)
	var before := _pos
	_pos = _clamp_to_walkable(_pos + _vel * delta)
	# 步伐按实际挪动的距离算：顶着墙走时人没动，不该原地踏步
	var v := _pos.distance_to(before) / maxf(delta, 1e-4)
	gait_speed = lerpf(gait_speed, v, 1.0 - exp(-delta * 12.0))
	gait_run = smoothstep(walk_speed * 1.1, run_speed * 0.95, gait_speed)
	_land_v += (-_land * 400.0 - _land_v * 28.0) * delta
	_land += _land_v * delta
	var s0 := gait_steps
	if gait_speed > 0.12:
		if not _stepping:
			# 起步：抬脚迈出去半步就落地，不用先走一整步才响
			_stepping = true
			gait_steps = floorf(gait_steps) + 0.5
			s0 = gait_steps
		# 步频（每秒几步）：走路随速度加快（1.25 米/秒约 1.7 步），跑起来 2.6 步上下，和动作捕捉的动画一致
		var cadence := lerpf(0.95 + 0.6 * gait_speed, 2.25 + 0.15 * gait_speed, gait_run)
		gait_steps += cadence * delta
		var k := floorf(gait_steps)
		if k > floorf(s0):
			_step(int(k), clampf(gait_speed / walk_speed, 0.0, 1.0), &"run" if gait_run > 0.5 else &"walk")
	elif _stepping:
		# 停下：一步迈到一半以上的，把后脚收过来落一下；刚落地的就不用了
		_stepping = false
		if fposmod(gait_steps, 1.0) > 0.3:
			gait_steps = ceilf(gait_steps)
			_step(int(gait_steps), 0.35, &"settle")


## 落一步：偶数左脚、奇数右脚
func _step(k: int, strength: float, kind: StringName) -> void:
	var side := -0.11 if k % 2 == 0 else 0.11
	var foot := Vector3(_pos.x, DECK_Y, _pos.y) + Vector3(side, 0, 0).rotated(Vector3.UP, yaw)
	_land_v -= lerpf(0.13, 0.3, gait_run) * strength
	stepped.emit(foot, strength, kind)


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
