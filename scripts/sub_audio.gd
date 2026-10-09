extends Node3D
## 潜艇上的声音：舱内环境声（艇体低鸣、头顶风口、配电柜嗡声、坏灯管的电流声、漏水滴答）、艇外的水声和推进器、
## 压载泵、随机的艇壳吱嘎、主动声呐的 ping、交互音（水密门、脚步、探照灯开关、撞礁）。
## 音效都由 tools/gen_sfx.py 合成（assets/audio/），这里只管摆位置、按游戏状态调音量音高。
##
## 总线（default_bus_layout.tres）：
##   Cabin     舱里的声音，带小钢舱的短混响；切到舱外视角时整个闷掉压低
##     CabinFwd / CabinAft  控制舱、生活舱各一条：水密门关着时，另一个舱的声音隔着门闷掉一大截
##   Sea       艇外的水声；在舱里听只剩隔着艇壳的低频，贴近舷窗时亮一点，切到舱外视角全开
## 这个节点挂在 Body 下面，坐标都是舱内局部坐标（x 右舷、y 上、-z 艏），和 cockpit_camera.gd 一致。

const SFX := "res://assets/audio/%s.wav"
const DoorScript := preload("res://scripts/watertight_door.gd")
const DOOR_Z := 2.6  # 中间隔壁（水密门）

## 舱内固定声源（对应 blender/scripts/cockpit.py 的布局）
const VENT_POS := Vector3(-0.3, 0.81, -1.46)   # 驾驶员头顶的球形风口
const POWER_POS := Vector3(1.05, 0.25, 1.4)    # 右舷配电柜 PD-4
const PUMP_POS := Vector3(0.0, -1.15, 0.6)     # 地板底下的压载泵
const SWITCH_POS := Vector3(0.3, -0.05, -2.0)  # 驾驶台上的探照灯开关
const COMPARTMENTS := [Vector2(-1.9, 2.5), Vector2(2.75, 6.3)]  # 控制舱、生活舱的 z 范围（吱嘎声随机落在里面）

## 音量（dB），都是相对生成时的归一化（循环音 RMS -20 dBFS、一次性峰值 -3 dBFS）
const VOL := {
	"hull_bed": -11.0, "sea_deep": -4.0, "vent": -24.0, "power_hum": -24.0, "fluoro_buzz": -27.0,
	"motor_hum": -12.0, "prop_wash": -4.0, "sea_flow": -3.0, "pump": -13.0,
	"door_grind": -14.0, "hinge_creak": -13.0, "door_wedge": -13.0, "gear_tick": -21.0, "door_strain": -8.0,
	"door_unlatch": -5.0, "door_seal": -12.0, "door_air": -17.0, "door_slam": -2.0, "door_knock": -9.0,
	"door_latch": -2.0, "creak": 0.0, "pop": -6.0, "sonar_ping": -12.0, "drip": -10.0,
	"footstep_plate": -3.0, "footstep_grate": -3.0, "footstep_sill": -4.0, "run_plate": -1.0, "run_grate": -1.0,
	"step_settle": -7.0, "switch": -8.0, "hull_impact": 0.0,
}

## 手轮每转过这么多度响一下齿轮
const TICK_DEG := 15.0

@onready var sub: Submarine = owner

## 调试：--only-sfx=a,b 只开这几种声音、--mute-sfx=a,b 关掉这几种（单独录某一路声音时用）
var _only := DebugArgs.get_arg("only-sfx").split(",", false)
var _mute := DebugArgs.get_arg("mute-sfx").split(",", false)

var _cam  # cockpit_camera.gd（没有 class_name）
var _door  # watertight_door.gd
var _buzz_light  # flicker_light.gd
var _sonar
var _external := false
var _view := 0.0  # 0 舱内 → 1 舱外，平滑过渡

# 持续的循环音
var _motor: AudioStreamPlayer
var _flow: AudioStreamPlayer
var _prop: AudioStreamPlayer3D
var _pump: AudioStreamPlayer3D
var _grind: AudioStreamPlayer3D
var _hinge: AudioStreamPlayer3D
var _wedge: AudioStreamPlayer3D
var _buzz: AudioStreamPlayer3D
var _pump_level := 0.0
# 一次性的声音（每种一个播放器，AudioStreamRandomizer 在变体里随机挑、随机微调音高）
var _shots := {}
var _impact: AudioStreamPlayer

var _wheel_last := 0.0
var _hinge_last := 0.0
var _unlatch_last := 0.0
var _tick_acc := 0.0
var _creak_wait := 6.0

var _bus_cabin := 0
var _bus_fwd := 0
var _bus_aft := 0
var _bus_sea := 0


func _ready() -> void:
	_bus_cabin = AudioServer.get_bus_index(&"Cabin")
	_bus_fwd = AudioServer.get_bus_index(&"CabinFwd")
	_bus_aft = AudioServer.get_bus_index(&"CabinAft")
	_bus_sea = AudioServer.get_bus_index(&"Sea")
	_cam = sub.get_node("%CockpitCamera")  # sub 的 @onready 要等子节点都 ready 之后才赋值
	_door = sub.find_child("Door", true, false)

	# 一直在响的底子
	_loop2d("hull_bed", &"Cabin").play()
	_loop2d("sea_deep", &"Sea").play()
	_loop3d("vent", VENT_POS, 1.0).play()
	_loop3d("power_hum", POWER_POS, 1.2).play()
	# 跟着状态走的
	_motor = _loop2d("motor_hum", &"Cabin")
	_flow = _loop2d("sea_flow", &"Sea")
	_prop = _loop3d("prop_wash", _local_of("Prop_Axis", Vector3(0, 0, 6.8)), 8.0, &"Sea")
	_pump = _loop3d("pump", PUMP_POS, 1.5)
	var strip := sub.find_child("CabinLight_Strip_R2", true, false) as Node3D
	if strip:
		_buzz_light = strip.get_node_or_null("Light")
		_buzz = _loop3d("fluoro_buzz", to_local(strip.global_position), 0.8)
		_buzz.play()

	_shot("creak", 5, 2.0, 1.08)
	_shot("pop", 3, 2.0, 1.1)
	_shot("drip", 6, 1.5, 1.06)
	for sfx: String in ["footstep_plate", "footstep_grate", "run_plate", "run_grate"]:
		_shot(sfx, 10 if sfx.begins_with("footstep") else 8, 1.2, 1.07, 3.0)
	_shot("footstep_sill", 4, 1.2, 1.05, 2.0)
	_shot("step_settle", 4, 1.0, 1.06, 3.0)
	_shot("gear_tick", 5, 1.0, 1.12, 2.0, 8)
	for sfx: String in ["door_strain", "door_unlatch", "door_seal", "door_air", "door_knock", "door_latch"]:
		_shot(sfx, 2, 1.5, 1.03)
	_shot("door_slam", 2, 2.0, 1.03)
	_shot("switch", 3, 0.8, 1.05)
	_shot("sonar_ping", 1, 4.0, 1.0)
	_impact = AudioStreamPlayer.new()
	_impact.stream = _randomizer("hull_impact", 3, 1.06, 0.0)
	_impact.bus = &"Cabin"
	_impact.max_polyphony = 2
	add_child(_impact)

	if _door:
		_grind = _loop3d("door_grind", Vector3(0, 0, DOOR_Z), 1.2, &"Cabin")
		_hinge = _loop3d("hinge_creak", Vector3(-0.43, 0, DOOR_Z - 0.13), 1.2, &"Cabin")
		_wedge = _loop3d("door_wedge", Vector3(0, 0, DOOR_Z), 1.2, &"Cabin")
		_door.sound.connect(_on_door)
		_wheel_last = _door.wheel_angle()
		_hinge_last = _door.hinge_angle()
		_unlatch_last = _door.unlatch
	_cam.stepped.connect(_on_step)
	sub.bumped.connect(_on_bump)
	sub.lights_switched.connect(func(_on: bool) -> void: _play("switch", SWITCH_POS))
	var props := sub.find_child("Props", true, false)
	if props and props.has_signal("drip_landed"):
		props.drip_landed.connect(func(p: Vector3) -> void: _play("drip", p))
	_connect_sonar.call_deferred()


## 声呐是仪表脚本在 _ready 里现建的，等一帧再找
func _connect_sonar() -> void:
	_sonar = sub.find_child("Sonar", true, false)
	if _sonar:
		_sonar.pinged.connect(func() -> void: _play("sonar_ping", SonarDisplay.SONAR_HEAD, true))


func _local_of(node_name: String, fallback: Vector3) -> Vector3:
	var n := sub.find_child(node_name, true, false) as Node3D
	return to_local(n.global_position) if n else fallback


# ---------------------------------------------------------------------------- 播放器
func _loop2d(sfx: String, bus: StringName) -> AudioStreamPlayer:
	var p := AudioStreamPlayer.new()
	p.name = sfx
	p.stream = load(SFX % sfx)
	p.bus = bus
	p.volume_db = _vol(sfx)
	add_child(p)
	return p


func _loop3d(sfx: String, pos: Vector3, unit: float, bus := StringName()) -> AudioStreamPlayer3D:
	var p := _player3d(sfx, unit)
	p.stream = load(SFX % sfx)
	p.position = pos
	p.bus = bus if bus else _bus_at(pos.z)
	add_child(p)
	return p


func _player3d(sfx: String, unit: float) -> AudioStreamPlayer3D:
	var p := AudioStreamPlayer3D.new()
	p.name = sfx
	p.volume_db = _vol(sfx)
	p.unit_size = unit
	p.max_db = 3.0
	p.max_distance = 40.0
	# 舱里就几米远，距离带来的高频衰减不要太狠（默认 -24 dB，隔两三米就像闷在被子里）
	p.attenuation_filter_db = -6.0
	return p


func _randomizer(sfx: String, count: int, pitch: float, vol_rand: float) -> AudioStream:
	if count == 1:
		return load(SFX % sfx)
	var r := AudioStreamRandomizer.new()
	r.playback_mode = AudioStreamRandomizer.PLAYBACK_RANDOM_NO_REPEATS
	r.random_pitch = pitch
	r.random_volume_offset_db = vol_rand
	for k in count:
		r.add_stream(k, load(SFX % ("%s_%d" % [sfx, k])))
	return r


func _shot(sfx: String, count: int, unit: float, pitch: float, vol_rand := 1.5, poly := 3) -> void:
	var p := _player3d(sfx, unit)
	p.stream = _randomizer(sfx, count, pitch, vol_rand)
	p.max_polyphony = poly
	add_child(p)
	_shots[sfx] = p


## 在舱内局部坐标 pos 处响一下。hull = true 的是艇壳传声（声呐、撞击）：在舱外视角走 Sea 总线
func _play(sfx: String, pos: Vector3, hull := false, gain_db := 0.0) -> void:
	var p: AudioStreamPlayer3D = _shots[sfx]
	p.position = pos
	p.bus = &"Sea" if (hull and _external) else _bus_at(pos.z)
	p.volume_db = _vol(sfx) + gain_db
	p.play()
	DebugArgs.log_sfx(sfx)


func _vol(sfx: String) -> float:
	if sfx in _mute or (not _only.is_empty() and sfx not in _only):
		return -80.0
	return VOL[sfx]


func _bus_at(z: float) -> StringName:
	return &"CabinAft" if z > DOOR_Z else &"CabinFwd"


# ---------------------------------------------------------------------------- 事件
## 门的事件名直接对应音效 door_<事件>（latched → door_latch）；strength 是这一下的轻重
func _on_door(event: StringName, strength: float) -> void:
	var sfx := "door_latch" if event == &"latched" else "door_" + event
	if not _shots.has(sfx):
		return
	_play(sfx, to_local(_door.wheel_position()), false, linear_to_db(clampf(strength, 0.05, 1.3)))


## 脚步按落脚的地面挑：过道中间一条格栅、两边花纹钢板、门洞里的钢门槛（布局见 cockpit.py、quarters.py 的 deck）
func _on_step(foot: Vector3, strength: float, kind: StringName) -> void:
	var surface := _floor_at(foot)
	var sfx := "step_settle" if kind == &"settle" else ("run_" if kind == &"run" else "footstep_") + surface
	if surface == "sill" and kind != &"settle":
		sfx = "footstep_sill"
	_play(sfx, foot, false, linear_to_db(lerpf(0.4, 1.0, strength)))


func _floor_at(p: Vector3) -> String:
	if absf(p.z - DOOR_Z) < 0.08:
		return "sill"
	var on_grate := absf(p.x) < 0.3 and ((p.z > -1.55 and p.z < 2.35) or (p.z > 2.73 and p.z < 6.3))
	return "grate" if on_grate else "plate"


func _on_bump(strength: float) -> void:
	_impact.bus = &"Sea" if _external else &"Cabin"
	_impact.volume_db = _vol("hull_impact") + linear_to_db(clampf(strength / 1.5, 0.15, 1.0))
	_impact.play()
	DebugArgs.log_sfx("hull_impact")


# ---------------------------------------------------------------------------- 每帧
func _process(delta: float) -> void:
	_external = sub.external_view
	_view = move_toward(_view, 1.0 if _external else 0.0, delta * 3.0)
	_update_buses()
	_update_drive(delta)
	_update_door(delta)
	_update_creaks(delta)
	if _buzz and _buzz_light:
		var lv: float = clampf(_buzz_light.level(), 0.0, 1.3)
		_buzz.volume_db = _vol("fluoro_buzz") + linear_to_db(maxf(lv * lv, 0.001))


## 视角、隔舱、贴舷窗对总线的影响
func _update_buses() -> void:
	# 舱外视角：舱里的声音隔着艇壳只剩低沉的一点；艇外的水声全开
	_set_lowpass(_bus_cabin, _lerp_log(20000.0, 250.0, _view))
	AudioServer.set_bus_volume_db(_bus_cabin, lerpf(0.0, -24.0, _view))
	var lean: float = _cam.get("lean")
	var inside := _lerp_log(380.0, 650.0, lean)
	_set_lowpass(_bus_sea, _lerp_log(inside, 9000.0, _view))
	# 隔舱：门关着时，听者不在的那个舱闷掉；门开一条缝声音就过来不少
	var aft: bool = _cam.position.z > DOOR_Z
	var opening := 1.0
	if _door:
		opening = smoothstep(0.0, 0.35, _door.hinge_angle() / deg_to_rad(DoorScript.OPEN_DEG))
	var occ := 1.0 - opening
	var far := _bus_fwd if aft else _bus_aft
	var near := _bus_aft if aft else _bus_fwd
	_set_lowpass(far, _lerp_log(20000.0, 450.0, occ))
	AudioServer.set_bus_volume_db(far, -14.0 * occ)
	_set_lowpass(near, 20000.0)
	AudioServer.set_bus_volume_db(near, 0.0)


func _set_lowpass(bus: int, hz: float) -> void:
	var fx := AudioServer.get_bus_effect(bus, AudioServer.get_bus_effect_count(bus) - 1) as AudioEffectLowPassFilter
	if fx and absf(fx.cutoff_hz - hz) > 1.0:
		fx.cutoff_hz = hz


static func _lerp_log(a: float, b: float, t: float) -> float:
	return exp(lerpf(log(a), log(b), clampf(t, 0.0, 1.0)))


## 推进电机、螺旋桨、水流、压载泵
func _update_drive(delta: float) -> void:
	var rpm := clampf(absf(sub.prop_speed()) / 9.0, 0.0, 1.0)
	var pitch := lerpf(0.45, 1.0, rpm)
	_drive(_motor, rpm ** 0.8, "motor_hum", pitch)
	_drive(_prop, rpm ** 1.2, "prop_wash", pitch)
	var v := clampf(sub.speed() / sub.max_speed, 0.0, 1.0)
	_drive(_flow, v ** 1.2, "sea_flow", lerpf(0.8, 1.15, v))
	# 压载泵：按住上浮/下潜就转，起停有个转速爬升
	var want := 1.0 if sub.lift_input != 0.0 else 0.0
	_pump_level = move_toward(_pump_level, want, delta * (2.0 if want > 0.0 else 1.2))
	_drive(_pump, smoothstep(0.0, 1.0, _pump_level), "pump", lerpf(0.4, 1.0, _pump_level))


## 循环音按 level（0~1 线性幅度）开关、调音量音高；没声了就停掉，省得白混
func _drive(p: Node, level: float, sfx: String, pitch := 1.0) -> void:
	if level < 0.002:
		if p.playing:
			p.stop()
			DebugArgs.log_loop(sfx, false)
		return
	p.set("volume_db", _vol(sfx) + linear_to_db(level))
	p.set("pitch_scale", pitch)
	if not p.playing:
		p.play(randf() * p.stream.get_length())
		DebugArgs.log_loop(sfx, true)


## 水密门：手轮的齿轮咔哒、减速箱摩擦、铰链吱嘎、把手在楔块上刮都按实际转动的快慢出声
func _update_door(delta: float) -> void:
	if _door == null or delta <= 0.0:
		return
	var w: float = _door.wheel_angle()
	var dw := absf(w - _wheel_last)
	_wheel_last = w
	var h: float = _door.hinge_angle()
	var dh := absf(h - _hinge_last)
	_hinge_last = h
	var at := to_local(_door.wheel_position())
	_tick_acc += rad_to_deg(dw)
	if _tick_acc >= TICK_DEG:
		_tick_acc = fmod(_tick_acc, TICK_DEG)
		_play("gear_tick", at)
	_grind.position = at
	var ws := clampf(rad_to_deg(dw / delta) / 500.0, 0.0, 1.0)
	_drive(_grind, ws ** 0.7, "door_grind", lerpf(0.75, 1.05, ws))
	var hs := clampf((rad_to_deg(dh / delta) - 4.0) / 120.0, 0.0, 1.0)  # 拧紧时胶条压进去那一点点不算
	_drive(_hinge, hs ** 0.6, "hinge_creak", lerpf(0.75, 1.05, hs))
	# 把手在楔块上刮：吃劲程度 × 把手转动的快慢；越吃劲音高越低越沉
	var u: float = _door.unlatch
	var us := clampf(absf(u - _unlatch_last) / delta / 0.35, 0.0, 1.0)
	_unlatch_last = u
	var grip: float = _door.wedge_load()
	_wedge.position = at
	_drive(_wedge, (grip * us) ** 0.7, "door_wedge", lerpf(1.05, 0.85, grip))


## 艇壳受压的吱嘎、嘣：隔一阵来一下，升降、转向的时候更勤
func _update_creaks(delta: float) -> void:
	var stress := absf(sub.velocity.y) / sub.vertical_max + absf(sub.yaw_speed) / deg_to_rad(sub.turn_max_deg) * 0.5
	_creak_wait -= delta * (1.0 + 3.0 * clampf(stress, 0.0, 1.0))
	if _creak_wait > 0.0:
		return
	_creak_wait = randf_range(9.0, 26.0)
	# 落在听者所在的那个舱的艇壳上（舱外视角时随便挑一个）
	var comp: Vector2 = COMPARTMENTS[1 if _cam.position.z > DOOR_Z else 0]
	var a := randf_range(-PI, PI)
	var pos := Vector3(sin(a) * 1.3, cos(a) * 1.3 * 0.9, randf_range(comp.x, comp.y))
	_play("pop" if randf() < 0.3 else "creak", pos, true)
