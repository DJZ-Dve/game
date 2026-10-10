class_name RoomAudio
extends Node3D
## 岸上房间的声音（音效都由 tools/gen_sfx.py 合成，assets/audio/）：
## - 循环：窗外的雨（挂在窗户上）、吊扇、日光灯的电流声（灯亮着才响）、收音机的沙沙声、港湾的水声
## - 一次性：脚步（按房间的地面挑：水泥 / 水磨石）、传呼机、敲门、门、纸、钢笔、钟……场景脚本 play(名字) 就响；
##   有位置的声音放在 SOURCES 里登记的挂点上，没登记的在玩家头上（2D）
## - 打雷：房间的 lightning 信号来了，按远近隔一两秒再响
## 总线（default_bus_layout.tres）：Room 屋里的声音（小房间混响），Outdoor 窗外的雨、水、雷。
## 坐标是房间局部坐标，和 RoomWalker 一样。

const SFX := "res://assets/audio/%s.wav"

## 音量（dB），相对生成时的归一化（循环音 RMS -20 dBFS、一次性峰值 -3 dBFS）
const VOL := {
	"rain_window": -13.0, "rain_steel": -11.0, "fan_whir": -19.0, "fluoro_buzz": -27.0, "radio_static": -12.0,
	"harbor": -18.0, "pager_beep": -6.0, "knock": 3.0, "steps_away": 4.0, "envelope": 0.0, "door_open": -2.0,
	"door_close": 0.0, "tube_start": -8.0, "paper": -3.0, "pen_write": -6.0, "ink_press": -6.0,
	"thumb_press": -4.0, "clock_tick": -16.0, "clock_tock": -16.0, "clock_stop": -6.0, "thunder": -2.0,
	"chair_creak": -8.0, "wall_switch": -4.0, "switch": -4.0, "ship_horn": -10.0, "cloth": -8.0,
	"step_concrete": 0.0, "run_concrete": 1.0, "settle_concrete": -4.0, "step_terrazzo": 0.0,
	"run_terrazzo": 1.0,
}
## 变体个数（gen_sfx.py 的 SOUNDS）
const VARIANTS := {
	"knock": 2, "door_open": 2, "door_close": 2, "paper": 4, "clock_tick": 2, "clock_tock": 2, "thunder": 3,
	"chair_creak": 3, "wall_switch": 2, "step_concrete": 8, "run_concrete": 6, "settle_concrete": 4,
	"step_terrazzo": 8, "run_terrazzo": 6,
}
## 场景脚本叫的名字 -> 实际的音效（有的共用一个）
const ALIAS := {"switch": "wall_switch", "cloth": "paper"}

## 地面：concrete（宿舍、走廊）/ terrazzo（办事处）
var floor_kind := "concrete"
## 有位置的一次性声音：名字 -> 房间局部坐标
var sources := {}

var _shots := {}
var _loops := {}
var _walker: RoomWalker
var _radio: AudioStreamPlayer3D
var _tick := false
var _only := DebugArgs.get_arg("only-sfx").split(",", false)
var _mute := DebugArgs.get_arg("mute-sfx").split(",", false)


func _ready() -> void:
	var room := get_parent() as StoryRoom
	_walker = room.walker
	_walker.stepped.connect(_on_step)
	room.lightning.connect(_on_lightning)


## 一直在响的声音：sfx 名字、位置（null 就是 2D）、总线、多大范围内听得清（unit_size）
func loop(sfx: String, pos: Variant, bus := &"Room", unit := 2.0) -> Node:
	var p: Node
	if pos == null:
		var a := AudioStreamPlayer.new()
		a.bus = bus
		p = a
	else:
		var a := AudioStreamPlayer3D.new()
		a.bus = bus
		a.unit_size = unit
		a.position = pos
		a.attenuation_model = AudioStreamPlayer3D.ATTENUATION_INVERSE_DISTANCE
		p = a
	p.set("stream", load(SFX % sfx))
	p.set("volume_db", _vol(sfx))
	add_child(p)
	if _allowed(sfx):
		p.call("play", randf() * 3.0)
	_loops[sfx] = p
	DebugArgs.log_loop(sfx, true)
	return p


func set_loop(sfx: String, on: bool) -> void:
	var p: Node = _loops.get(sfx)
	if p == null:
		return
	if on and not p.get("playing") and _allowed(sfx):
		p.call("play")
	elif not on:
		p.call("stop")
	DebugArgs.log_loop(sfx, on)


func play(sfx: String) -> void:
	var real: String = ALIAS.get(sfx, sfx)
	if not _allowed(real):
		return
	var p := _shot(real)
	if p == null:
		return
	if p is AudioStreamPlayer3D:
		(p as AudioStreamPlayer3D).position = sources.get(sfx, _walker.position + Vector3(0, -0.2, 0))
	p.call("play")
	DebugArgs.log_sfx(real)


## 收音机：on（先沙沙一下）/ static（只剩沙沙）/ off
func set_radio(state: String) -> void:
	if _radio == null:
		_radio = loop("radio_static", sources.get("radio", Vector3.ZERO), &"Room", 1.0)
	set_loop("radio_static", state != "off")
	_radio.volume_db = _vol("radio_static") + (0.0 if state == "static" else -8.0)


## 摆钟走一下（嘀、嗒轮着来）
func tick() -> void:
	_tick = not _tick
	play("clock_tick" if _tick else "clock_tock")


func _shot(sfx: String) -> Node:
	if _shots.has(sfx):
		return _shots[sfx]
	var n: int = VARIANTS.get(sfx, 1)
	var stream: AudioStream
	if n == 1:
		if not ResourceLoader.exists(SFX % sfx):
			return null
		stream = load(SFX % sfx)
	else:
		var r := AudioStreamRandomizer.new()
		for i in n:
			r.add_stream(-1, load(SFX % ("%s_%d" % [sfx, i])))
		r.random_pitch = 1.05
		r.random_volume_offset_db = 1.5
		stream = r
	var p: Node
	if sources.has(sfx) or sfx.begins_with("step_") or sfx.begins_with("run_") or sfx.begins_with("settle_"):
		var a := AudioStreamPlayer3D.new()
		a.unit_size = 2.0
		a.max_polyphony = 3
		p = a
	else:
		var a := AudioStreamPlayer.new()
		a.max_polyphony = 2
		p = a
	p.set("stream", stream)
	p.set("bus", &"Outdoor" if sfx in ["thunder", "ship_horn"] else &"Room")
	p.set("volume_db", _vol(sfx))
	add_child(p)
	_shots[sfx] = p
	return p


func _vol(sfx: String) -> float:
	return VOL.get(sfx, -10.0)


func _allowed(sfx: String) -> bool:
	for m in _mute:
		if sfx.begins_with(m):
			return false
	if _only.is_empty():
		return true
	for o in _only:
		if sfx.begins_with(o):
			return true
	return false


func _on_step(foot: Vector3, strength: float, kind: StringName) -> void:
	var sfx: String = {&"run": "run_", &"settle": "settle_"}.get(kind, "step_") + floor_kind
	if not ResourceLoader.exists(SFX % (sfx + "_0")):
		sfx = "step_" + floor_kind
	var p := _shot(sfx) as AudioStreamPlayer3D
	if p == null or not _allowed(sfx):
		return
	p.position = foot
	p.volume_db = _vol(sfx) + linear_to_db(clampf(strength, 0.2, 1.0))
	p.play()
	DebugArgs.log_sfx(sfx)


func _on_lightning(strength: float) -> void:
	# 雷声跟在闪电后面：近的一秒不到，远的三四秒
	await get_tree().create_timer(lerpf(3.5, 0.6, strength)).timeout
	var p := _shot("thunder")
	if p and _allowed("thunder"):
		p.set("volume_db", _vol("thunder") + lerpf(-8.0, 0.0, strength))
		p.call("play")
		DebugArgs.log_sfx("thunder")
