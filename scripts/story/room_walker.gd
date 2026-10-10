class_name RoomWalker
extends Camera3D
## 岸上场景（宿舍、办事处）的第一人称：走动、跑、看东西、按 E 交互、坐到椅子上。
## 和 cockpit_camera.gd 一样不走物理引擎：能站的地方是几块矩形（walk_areas，房间局部坐标 x、z）。
## 步伐（倒摆式的起伏、按实际挪动的距离走相位、起步半步、停下收脚）照搬 cockpit_camera.gd，
## crew_body.gd 读这里的步伐相位、坐姿、手的目标，身体和动画跟在艇里一样。
## 挂在房间根节点下面，坐标就是房间局部坐标（x 右、y 上、-z 前）。

signal stepped(foot: Vector3, strength: float, kind: StringName)
signal seated_changed(seated: bool)

@export var sensitivity := 0.0022
@export var walk_speed := 1.15
@export var run_speed := 2.3
@export var walk_accel := 7.0
@export var run_accel := 5.0
@export var eye_height := 1.62
@export var deck_y := 0.0
@export var normal_fov := 68.0
## 能站的地方：房间局部坐标（x, z）的几块矩形，取并集
@export var walk_areas: Array[Rect2] = []
## 开场站在哪、朝哪（度，0 = 朝 -Z）
@export var start := Vector2.ZERO
@export var start_yaw := 0.0
## 坐着时左右最多转多少度
@export var seated_yaw_limit := 100.0

var yaw := 0.0
var pitch := 0.0
## 给界面显示的操作提示
var prompt := ""
var focus: Interactable
## 剧情锁：不能走、不能交互（还能转头看）。Story.busy 时也一样
var locked := false
## 步伐：走过的步数，整数时脚落地（偶数左脚、奇数右脚）；实际移动的速度；跑的程度 0~1
var gait_steps := 0.0
var gait_speed := 0.0
var gait_run := 0.0
## crew_body.gd 要读的（水密门那一套，岸上用不到）
var door_op := false
var door_aft := false
var door_yaw := 0.0
var door_lean := 0.0
var _door = null

var _pos := Vector2.ZERO
var _vel := Vector2.ZERO
var _stepping := false
var _sprint := 0.0
var _land := 0.0
var _land_v := 0.0
var _seat: Node3D            # 正坐着的椅子：Seat 挂点（位置 = 坐着时的眼睛，-Z = 面朝的方向）
var _sit := 0.0              # 0 站 → 1 坐（平滑）
var _seat_yaw := 0.0
var _blend := 1.0
var _from := Transform3D.IDENTITY
var _look_at: Variant = null # 过场时把视线拉过去（房间局部坐标）
var _look_speed := 3.0
var _hand := [{}, {}]        # 两只手的目标（签字、按手印），crew_body.gd 读
var _goal: Variant = null    # 自动走到这里（自动演示用），Vector2


func _ready() -> void:
	add_to_group("crew")
	add_to_group("walker")
	_pos = start
	yaw = deg_to_rad(start_yaw)
	if DebugArgs.has("at"):
		var p := DebugArgs.get_arg("at").split(",")
		_pos = Vector2(float(p[0]), float(p[1]))
	if DebugArgs.has("yaw"):
		yaw = deg_to_rad(float(DebugArgs.get_arg("yaw")))
	if DebugArgs.has("pitch"):
		pitch = deg_to_rad(float(DebugArgs.get_arg("pitch")))
	fov = normal_fov
	if not DebugArgs.has("capture") and Engine.get_write_movie_path().is_empty():
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
	_process(0.0)


func is_seated() -> bool:
	return _seat != null


## 坐着的程度：0 站着 → 1 坐好了（crew_body.gd 按它在站、坐动画之间混合）
func sit_amount() -> float:
	return smoothstep(0.0, 1.0, _sit)


## 身体朝向：走动时跟着视线，坐着时朝椅子的方向
func body_yaw() -> float:
	return lerp_angle(yaw, _seat_yaw, sit_amount())


func feet() -> Vector2:
	return _pos


## 手的目标（房间局部坐标 → 世界坐标由 crew_body.gd 换算）：pos 手腕、fingers 手指方向、palm 掌心朝向、
## weight 0~1、grasp 手指弯多少。i：0 左手、1 右手；给空字典就是放下
func set_hand(i: int, goal: Dictionary) -> void:
	_hand[i] = goal


func hand_goal(i: int) -> Dictionary:
	return _hand[i]


## instant：直接坐好（开场就坐着），不从站着的样子过渡过去
func sit_at(seat: Node3D, instant := false) -> void:
	_from = transform
	_blend = 1.0 if instant else 0.0
	if instant:
		_sit = 1.0
	_seat = seat
	var f := -seat.global_basis.z
	_seat_yaw = atan2(-f.x, -f.z)
	yaw = _seat_yaw
	pitch = 0.0
	_vel = Vector2.ZERO
	seated_changed.emit(true)


func stand_up() -> void:
	if _seat == null:
		return
	var stand := _seat.get_node_or_null("Stand") as Node3D
	var p := (stand if stand else _seat).global_position
	_pos = Vector2(p.x, p.z)
	_from = transform
	_blend = 0.0
	_seat = null
	seated_changed.emit(false)


## 过场：把视线拉到某一点（世界坐标）；null 放开
func look_toward(p: Variant, speed := 3.0) -> void:
	_look_at = p
	_look_speed = speed


## 自己走过去（自动演示用）：朝着目标走，到了就停
func move_to(p: Vector2) -> void:
	_goal = p


func arrived() -> bool:
	return _goal == null


func teleport(p: Vector2, yaw_deg: float) -> void:
	_pos = p
	yaw = deg_to_rad(yaw_deg)
	_vel = Vector2.ZERO


func _unhandled_input(event: InputEvent) -> void:
	if not current:
		return
	if event is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		yaw -= event.relative.x * sensitivity
		pitch = clampf(pitch - event.relative.y * sensitivity, deg_to_rad(-80.0), deg_to_rad(75.0))
		if _seat:
			var d := clampf(angle_difference(_seat_yaw, yaw), -deg_to_rad(seated_yaw_limit), deg_to_rad(seated_yaw_limit))
			yaw = _seat_yaw + d
	elif event.is_action_pressed("interact"):
		if _busy():
			return
		if focus:
			get_viewport().set_input_as_handled()
			focus.activate()
		elif _seat and not locked:
			stand_up()
	elif event.is_action_pressed("release_mouse"):
		Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	elif event is InputEventMouseButton and event.pressed and Input.mouse_mode != Input.MOUSE_MODE_CAPTURED \
			and not Story.ui.is_reading():
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED


func _busy() -> bool:
	return locked or Story.busy or Story.ui.is_reading()


func _process(delta: float) -> void:
	if _look_at != null:
		var to: Vector3 = _look_at - global_position
		var want_yaw := atan2(-to.x, -to.z)
		var want_pitch := atan2(to.y, Vector2(to.x, to.z).length())
		var k := 1.0 - exp(-delta * _look_speed)
		yaw = lerp_angle(yaw, want_yaw, k)
		pitch = lerpf(pitch, want_pitch, k)
	_sit = move_toward(_sit, 1.0 if _seat else 0.0, delta * 1.6)
	if _seat:
		_walk_stop(delta)
	else:
		_walk(delta)
	_update_focus()

	var base: Transform3D
	var look := Basis.from_euler(Vector3(pitch, yaw, 0.0))
	var t := Time.get_ticks_msec() / 1000.0
	if _seat:
		var p := get_parent_node_3d().global_transform.affine_inverse() * _seat.global_position
		base = Transform3D(look, p + Vector3(sin(t * 0.9) * 0.004, sin(t * 1.7) * 0.003, 0.0))
	else:
		# 走路的起伏（同 cockpit_camera.gd）：脚踩在身体正下方时头最高，两脚交替落地的瞬间最低；
		# 每两步左右晃一次；落脚时被压一下、点一下头
		var sp := clampf(gait_speed / walk_speed, 0.0, 1.0)
		var arc := sin(PI * fposmod(gait_steps, 1.0)) - 0.64
		var side := -sin(PI * fposmod(gait_steps, 2.0))
		var amp := lerpf(0.026, 0.046, gait_run)
		base = Transform3D(Basis(Vector3.UP, yaw) * Basis(Vector3.RIGHT, pitch + _land * 1.2)
			* Basis(Vector3.BACK, -side * deg_to_rad(0.5) * sp),
			Vector3(_pos.x, deck_y + eye_height + arc * amp * sp + _land, _pos.y))
		base.origin += Vector3(side * lerpf(0.014, 0.01, gait_run) * sp, 0, 0).rotated(Vector3.UP, yaw)
	fov = normal_fov + 4.0 * gait_run
	if _blend < 1.0:
		_blend = minf(_blend + delta * 1.4, 1.0)
		var k := smoothstep(0.0, 1.0, _blend)
		base = Transform3D(_from.basis.slerp(base.basis.orthonormalized(), k), _from.origin.lerp(base.origin, k))
	transform = base

	if current:
		prompt = ""
		if not _busy():
			if focus:
				prompt = "E " + focus.prompt
			elif _seat and not locked:
				prompt = "E 站起来"
		Story.ui.set_prompt(prompt, focus != null, not Story.busy)


## 准星对着、够得着的那个可交互物（离视线中心角度最小的）
func _update_focus() -> void:
	focus = null
	if _busy() or _blend < 0.9:
		return
	var eye := global_position
	var fwd := -global_basis.z
	var best := 1.0
	for n in get_tree().get_nodes_in_group("interactable"):
		var it := n as Interactable
		if it == null or not it.enabled or not it.is_visible_in_tree():
			continue
		var d := it.global_position - eye
		var dist := d.length()
		if dist > it.reach or dist < 1e-3:
			continue
		var ang := acos(clampf(fwd.dot(d / dist), -1.0, 1.0))
		var allow := atan(it.size / dist) + deg_to_rad(3.0)
		var score := ang / allow
		if score < best:
			best = score
			focus = it


func _walk(delta: float) -> void:
	var input := Vector2.ZERO
	var scripted := DebugArgs.has("actions")
	if current and (Input.mouse_mode == Input.MOUSE_MODE_CAPTURED or scripted) and not _busy():
		input = Input.get_vector("turn_left", "turn_right", "move_forward", "move_back")
	var want_run := current and Input.is_action_pressed("sprint") and input.y < -0.3 and not _busy()
	_sprint = move_toward(_sprint, 1.0 if want_run else 0.0, delta * 3.0)
	var top := lerpf(walk_speed, run_speed, _sprint)
	var wish := input.rotated(-yaw) * top
	if _goal != null and not _busy():
		var to: Vector2 = _goal - _pos
		if to.length() < 0.06:
			_goal = null
		else:
			wish = to.normalized() * minf(walk_speed * 0.85, to.length() * 3.0)
			if _look_at == null:
				yaw = lerp_angle(yaw, atan2(-to.x, -to.y), 1.0 - exp(-delta * 4.0))
				pitch = lerpf(pitch, -0.15, 1.0 - exp(-delta * 3.0))
	_vel = _vel.move_toward(wish, lerpf(walk_accel, run_accel, _sprint) * delta)
	var before := _pos
	_pos = _clamp_to_walkable(_pos + _vel * delta)
	_gait(delta, _pos.distance_to(before) / maxf(delta, 1e-4))


func _walk_stop(delta: float) -> void:
	_vel = Vector2.ZERO
	_gait(delta, 0.0)


## 步伐（同 cockpit_camera.gd）：步频随速度变，起步迈半步就落脚，停下时一步迈到一半以上的把后脚收过来
func _gait(delta: float, v: float) -> void:
	gait_speed = lerpf(gait_speed, v, 1.0 - exp(-delta * 12.0))
	gait_run = smoothstep(walk_speed * 1.1, run_speed * 0.95, gait_speed)
	_land_v += (-_land * 400.0 - _land_v * 28.0) * delta
	_land += _land_v * delta
	var s0 := gait_steps
	if gait_speed > 0.12:
		if not _stepping:
			_stepping = true
			gait_steps = floorf(gait_steps) + 0.5
			s0 = gait_steps
		var cadence := lerpf(0.95 + 0.6 * gait_speed, 2.25 + 0.15 * gait_speed, gait_run)
		gait_steps += cadence * delta
		if floorf(gait_steps) > floorf(s0):
			_step(int(floorf(gait_steps)), clampf(gait_speed / walk_speed, 0.0, 1.0),
				&"run" if gait_run > 0.5 else &"walk")
	elif _stepping:
		_stepping = false
		if fposmod(gait_steps, 1.0) > 0.3:
			gait_steps = ceilf(gait_steps)
			_step(int(gait_steps), 0.35, &"settle")


func _step(k: int, strength: float, kind: StringName) -> void:
	var side := -0.11 if k % 2 == 0 else 0.11
	var foot := Vector3(_pos.x, deck_y, _pos.y) + Vector3(side, 0, 0).rotated(Vector3.UP, yaw)
	_land_v -= lerpf(0.13, 0.3, gait_run) * strength
	stepped.emit(foot, strength, kind)


func _clamp_to_walkable(p: Vector2) -> Vector2:
	if walk_areas.is_empty():
		return p
	var best := p
	var best_d := INF
	for r: Rect2 in walk_areas:
		var q := p.clamp(r.position, r.end)
		var d := q.distance_squared_to(p)
		if d < best_d:
			best_d = d
			best = q
	return best
