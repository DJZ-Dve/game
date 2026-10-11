class_name CrewPuppet
extends Node3D
## 别的玩家在本机的替身：从网络收到他的第一人称状态（眼睛位置、视线、步伐、坐没坐、开没开门），
## 装成 cockpit_camera.gd 的样子给 crew_body.gd 读，身体、动画、开门的手 IK 就和本机的一模一样地动起来。
## 挂在潜艇的 Body 下面，坐标是舱内局部坐标（和 cockpit_camera 一样）。
##
## 收到的状态带着对方的时间戳，按对方的时间往后推 DELAY 秒播放，在前后两帧之间插值——网络抖一下也不会一顿一顿的。

## 走动时每落一步（和 cockpit_camera.gd 的 stepped 一样，给 sub_audio.gd 放脚步声）
signal stepped(foot: Vector3, strength: float, kind: StringName)

## 比收到的最新状态晚多少秒播放（状态每秒发 20 次，留两三帧的余量）
const DELAY := 0.12
const KEEP := 1.0

# crew_body.gd 读的这些，名字和 cockpit_camera.gd 一样
var yaw := 0.0
var pitch := 0.0
var gait_steps := 0.0
var gait_speed := 0.0
var gait_run := 0.0
var door_op := false
var door_aft := false
var door_lean := 0.0
var door_yaw := 0.0
## 水密门（crew_body.gd 用 _cam.get("_door") 拿，按它摆握手轮的手）
var _door: Node

var peer_id := 0
var _sit := 0.0
var _feet := Vector2.ZERO
var _snaps: Array = []   # [对方的时间, 状态]，按时间排
var _clock := -1.0       # 正在播放的时刻（对方的时间）
var _got := false
var _label: Label3D


func setup(id: int, display_name: String, door: Node) -> void:
	peer_id = id
	_door = door
	name = "Puppet_%d" % id
	_label = Label3D.new()
	_label.text = display_name
	_label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	_label.pixel_size = 0.0011
	_label.font_size = 40
	_label.outline_size = 10
	_label.modulate = Color(0.92, 0.86, 0.72, 0.85)
	_label.outline_modulate = Color(0, 0, 0, 0.6)
	_label.position = Vector3(0, 0.2, 0)
	_label.font = load("res://assets/fonts/NotoSerifSC-VF.ttf")
	add_child(_label)
	visible = false


## 第一次收到状态之前不显示（不然会在舱中间站一个摆着默认姿势的人）
func has_state() -> bool:
	return _got


func sit_amount() -> float:
	return _sit


func feet() -> Vector2:
	return _feet


func push(t: float, s: Dictionary) -> void:
	if not _snaps.is_empty() and t <= _snaps[-1][0]:
		return
	_snaps.append([t, s])
	if not _got:
		Net.log_event("puppet %d first state" % peer_id)
		_got = true
		visible = true
		_clock = t
		_apply(s, s, 0.0)
		gait_steps = s.gs


func _process(delta: float) -> void:
	if _snaps.is_empty():
		return
	var latest: float = _snaps[-1][0]
	_clock += delta
	# 时钟跑到最新状态前面（对方卡了）就停在那儿；落后太多（这边卡了）就跳回去
	if _clock > latest:
		_clock = latest
	elif _clock < latest - DELAY * 3.0:
		_clock = latest - DELAY
	var t := _clock - DELAY
	while _snaps.size() > 2 and _snaps[1][0] <= t:
		_snaps.pop_front()
	while _snaps.size() > 1 and float(_snaps[0][0]) < latest - KEEP:
		_snaps.pop_front()
	var a: Array = _snaps[0]
	var b: Array = _snaps[1] if _snaps.size() > 1 else a
	var span: float = b[0] - a[0]
	var k := clampf((t - a[0]) / span, 0.0, 1.0) if span > 0.0 else 1.0
	var before := gait_steps
	_apply(a[1], b[1], k)
	_emit_steps(before)
	if _label:
		# 坐在驾驶椅上时名字别挡在仪表前面
		_label.visible = _sit < 0.5


func _apply(a: Dictionary, b: Dictionary, k: float) -> void:
	position = (a.eye as Vector3).lerp(b.eye, k)
	_feet = (a.feet as Vector2).lerp(b.feet, k)
	yaw = lerp_angle(a.yaw, b.yaw, k)
	pitch = lerpf(a.pitch, b.pitch, k)
	gait_steps = lerpf(a.gs, b.gs, k)
	gait_speed = lerpf(a.gv, b.gv, k)
	gait_run = lerpf(a.gr, b.gr, k)
	_sit = lerpf(a.sit, b.sit, k)
	door_lean = lerpf(a.dl, b.dl, k)
	door_yaw = lerp_angle(a.dy, b.dy, k)
	var s: Dictionary = b if k > 0.5 else a
	door_op = s.dop
	door_aft = s.daft


## 步伐相位每过一个整数就是落了一步（偶数左脚、奇数右脚），和 cockpit_camera.gd 的 _step 一样
func _emit_steps(before: float) -> void:
	if gait_steps <= before or gait_steps - before > 3.0:
		return
	var k := floorf(gait_steps)
	if k <= floorf(before):
		return
	var side := -0.11 if int(k) % 2 == 0 else 0.11
	var foot := Vector3(_feet.x, -0.9, _feet.y) + Vector3(side, 0, 0).rotated(Vector3.UP, yaw)
	stepped.emit(foot, clampf(gait_speed / 1.25, 0.0, 1.0), &"run" if gait_run > 0.5 else &"walk")
