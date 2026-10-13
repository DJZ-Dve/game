class_name Giant
extends Node3D
## 第一个巨物（暂名「闷雷」）：四十来米长，背上一层叠一层的甲片，肚子底下垂着一片长须，没有眼睛，靠听声音找东西。
## 参考潜渊症里 Moloch 那一类：打不了，只能躲——关掉主动声呐、停车、别撞东西，等它游过去。
##
## 它听的是潜艇的噪音（Submarine.noise_level / make_noise）：主动声呐一声 ping 方圆四百米都听得见，
## 满速的螺旋桨一百多米，停车漂着几乎听不见。听到一次「兴趣」涨一点，不出声慢慢消下去：
##   游荡 → 听到了：过去看看（往听到的地方游，离得越远听得越不准）
##        → 离得近、还在响、兴趣够高：冲过来撞（冲之前吼一声）；半路没声了就扑空，在附近兜圈子找
##        → 撞上了：艇壳掉一截、艇被撞得打转，它冲过头游开，过一会儿再回来听
##   不冲的时候它会从艇上方游过去（长须从艇身边扫过），艇壳跟着水压吱嘎作响。
##
## 联机：主机算行为，每秒广播 10 次位置、朝向、速度、状态，别人那边插值跟着；吼叫、撞艇是事件，大家同一时刻听到。
## 物理层在第 5 层：潜艇不和它碰（撞艇由脚本判定），声呐的射线照样打得到（屏上一大团硬回波）。
## 模型是 assets/models/giant.glb（blender/scripts/gen_giant.py，规格见 blender/scripts/giant/spec.py）：
## 第二版照格陵兰睡鲨做的深海鲨鱼，嘴照尖牙鱼，只在舱外视角看得见（舷窗封着）。动作全是程序化驱动骨骼（scripts/giant_motion.gd）：
##   游动：鲨鱼的游法，前三分之二几乎不动、头很稳，后段和尾巴摆；巡航又慢又小，冲刺时大力甩尾，尾鳍晚半拍甩出去；
##         转弯整条身子顺着弯，上浮下潜也弯一点。
##   呼吸：嘴先微微张开、接着鳃裂后缘的皮瓣往外翻开，平时五到七秒一口；冲刺、吼叫、撞上以后喘得急、鳃开得大。
##   嘴：平时闭着，跟着呼吸开合几度，隔一阵再张合一下；吼的时候张到 30～40° 几秒；冲刺时离艇越近张得越大，
##       最后十几米张满 70°、上头往上抬（张嘴加抬头不超过 80°）；撞上那一下猛地合上（弹回来一点），头甩几下；扑空了也咬一口空的。
##   联机：张嘴按广播来的状态 + 本机算的到艇距离 + 吼叫 / 撞艇事件各算各的，差不多一致。
##   胸鳍：平时轻轻起伏；转弯时内侧下压、外侧上抬（打舵），上浮下潜两片一起调攻角，冲刺时往后收贴到身上；腹鳍跟着轻轻动。
##   寄生虫卵带：眼睛上挂的两条有惯性地拖在水里，游得快往后拉直，停下来慢慢垂下，偶尔被乱流扰一下。
##   碰撞：沿脊椎的胶囊跟着骨骼走（层 5、sonar_hard），声呐照样打得到。
##
## 调试：--giant=off 不放；--giant-at=dx,dy,dz 开场放在潜艇的这个偏移处（默认 160 米外）；
##      --giant-still 定住不动（截图看模型）；--giant-log 打印状态变化（GIANT 帧号 ...）
##      --giant-yaw=度 开场朝向（世界坐标，0 头朝 -Z、90 头朝 -X；默认头朝着潜艇），配合 --giant-still 摆侧面
##      --giant-jaw=度 嘴一直张这么大（0～70）
##      --giant-pose=idle|cruise|charge|moan|ram[:帧]|turn_left|turn_right|rise|dive|gasp  只改动作、不改行为（配合 --giant-still 截图）：
##          cruise 按巡航速度摆尾；charge 按冲刺速度甩尾、嘴张满、上头抬起、胸鳍收起；moan 开场吼一下的张嘴（不出声）；
##          ram 先是 charge，到第几帧（默认 240）猛地合上、头甩；
##          turn_left / turn_right 巡航速度、按 9°/秒 转弯（身子弯、胸鳍打舵）；rise / dive 巡航速度、抬头 / 低头 14°（胸鳍调攻角）；
##          gasp 原地喘得最急（呼吸快、鳃开得大）
##      --giant-breath=倍数 呼吸快慢（2 = 快一倍）；--giant-gill=度 鳃皮瓣一直翻开这么多（看鳃）
##      --giant-shots=帧,帧,...:路径前缀  到这几帧各存一张截图（<前缀>_<帧>.png，连拍看摆动；配合 capture.py 的 --wait 设成最后一帧之后）
##      --giant-bones 把骨骼画成线（不挡，脊椎白、尾鳍蓝、下颌青、鳍黄、鳃红、卵带绿），灰模上没刷权重的骨头也看得见在动
##      --giant-turn=度每秒 动作按这个转弯角速度弯身子（正的往左转）
##      --giant-anim-log 每秒打印一行动作（GIANT_ANIM 帧号 jaw= lift= amp= freq= head= tail= gill= exert= pec= para=）
##      --giant-light 两侧挂两盏大灯照着它（深海里本来几乎看不见，看模型、看动作用）

enum State { WANDER, INVESTIGATE, SEARCH, CHARGE, RETREAT }
const STATE_NAMES := ["wander", "investigate", "search", "charge", "retreat"]

const LAYER := 16
const LENGTH := 42.0

## 各状态的速度（米/秒）、最大转向（度/秒）、自己发出的声音（被动声呐上多亮）
const SPEED := [2.0, 3.4, 2.2, 7.0, 4.2]
const TURN := [6.0, 9.0, 8.0, 15.0, 9.0]
const RADIATED := [0.35, 0.5, 0.4, 1.0, 0.65]

const LISTEN_EVERY := 0.25
## 离海底至少这么高（身体半径加一点）
const MIN_ALTITUDE := 7.0
## 头离潜艇的中轴线这么近就算撞上
const CONTACT := 6.5
const SYNC_RATE := 10.0

const SFX := "res://assets/audio/%s.wav"
const VOL := {"giant_moan": 2.0, "giant_swim": -2.0, "giant_ram": 0.0}

## 噪音 1.0 在这么远能听见（噪音小一半，距离也近一半）
@export var hear_range := 400.0
@export var wander_radius := 170.0
@export var ram_damage := 0.34

var sub: Submarine
var state := State.WANDER
var speed := 0.0
var yaw := 0.0
var pitch := 0.0
## 对潜艇的兴趣：0 不在意，1 盯上了
var interest := 0.0
## 被动声呐上占多大一片方位（sonar_display.gd 读）
var half_length := LENGTH / 2.0

var _rng := RandomNumberGenerator.new()
var _home := Vector3.ZERO
var _target := Vector3.ZERO
var _heard_at := Vector3.ZERO
var _since_heard := INF
var _state_t := 0.0
var _listen_t := 0.0
var _floor_y := -INF
var _blocked := false
var _turn_rate := 0.0
var _search_ang := 0.0
var _moan_wait := 15.0
var _moan_boost := 0.0
var _still := false
var _log := false
var _log_t := 0.0
# 别人那边：主机最近一次广播的状态
var _auth := {}
var _auth_at := 0.0
var _sync_t := 0.0
# 身体、动作（动作用自己的随机数，不动行为那一串）
var _motion: GiantMotion
var _anim_rng := RandomNumberGenerator.new()
var _last_pitch := 0.0
var _anim_state := State.WANDER
var _moan_t := INF
var _moan_open := 35.0
var _gulp_wait := 8.0
var _gulp_t := INF
var _gulp_open := 6.0
var _pose := ""
var _pose_ram_at := 240
var _jaw_force := -1.0
var _turn_force := NAN
var _anim_log := false
var _anim_log_t := 0.0
var _shots := PackedInt32Array()
var _shot_prefix := ""
# 声音、贴着艇过去时的艇壳吱嘎
var _swim: AudioStreamPlayer3D
var _voice: AudioStreamPlayer3D
var _ram_sfx: AudioStreamPlayer
var _moans: Array[AudioStream] = []
var _rams: Array[AudioStream] = []
var _stress_t := 0.0
var _audio: Node
var _cam: Node


func _init() -> void:
	name = "Giant"


## 进了场景树以后调（要摆位置）
func setup(p_sub: Submarine) -> void:
	sub = p_sub
	_audio = sub.find_child("Audio", true, false)
	_cam = sub.get_node("%CockpitCamera")
	_home = sub.global_position
	_still = DebugArgs.has("giant-still")
	_log = DebugArgs.has("giant-log")
	var off := Vector3.ZERO
	if DebugArgs.has("giant-at"):
		var p := DebugArgs.get_arg("giant-at").split(",")
		off = Vector3(float(p[0]), float(p[1]) if p.size() > 1 else 0.0, float(p[2]) if p.size() > 2 else 0.0)
	else:
		var a := _rng.randf() * TAU
		off = Vector3(cos(a), 0.0, sin(a)) * 160.0 + Vector3.UP * 6.0
	global_position = _home + off
	yaw = atan2(off.x, off.z)  # 头朝着潜艇这边
	if DebugArgs.has("giant-yaw"):
		yaw = deg_to_rad(float(DebugArgs.get_arg("giant-yaw")))
	rotation = Vector3(0.0, yaw, 0.0)
	_pick_wander()


func _ready() -> void:
	add_to_group("noise_source")
	_build_body()
	_build_audio()
	if _pose == "moan":
		_moan_t = 0.0


## 被动声呐听到它多响（游得越急越响，吼的时候最响）
func radiated_noise() -> float:
	return clampf(RADIATED[state] * (0.5 + 0.5 * clampf(speed / 3.0, 0.0, 1.5)) + _moan_boost, 0.0, 1.5)


func head() -> Vector3:
	return global_transform * Vector3(0.0, 0.0, -half_length * 0.95)


func forward() -> Vector3:
	return Vector3(-sin(yaw) * cos(pitch), sin(pitch), -cos(yaw) * cos(pitch))


# ---------------------------------------------------------------------------- 每帧
func _physics_process(delta: float) -> void:
	if sub == null:
		return
	if Net.is_host():
		if not _still:
			_think(delta)
			_move(delta)
		_sync(delta)
	else:
		_follow(delta)


func _process(delta: float) -> void:
	if sub == null:
		return
	_moan_boost = maxf(_moan_boost - delta / 6.0, 0.0)
	_animate(delta)
	if not _shots.is_empty() and Engine.get_process_frames() >= _shots[0]:
		_shoot(_shots[0])
		_shots.remove_at(0)
	_near_effects(delta)
	if _swim:
		_swim.volume_db = VOL.giant_swim + linear_to_db(clampf(speed / 4.0, 0.12, 1.3))
		_swim.pitch_scale = 0.85 + clampf(speed, 0.0, 8.0) * 0.04


# ---------------------------------------------------------------------------- 行为（主机）
func _think(delta: float) -> void:
	_state_t += delta
	_since_heard += delta
	interest = maxf(interest - delta * 0.025, 0.0)
	_listen_t += delta
	if _listen_t >= LISTEN_EVERY:
		_listen_t = 0.0
		_listen()
		_probe()
	_moan_wait -= delta
	if _moan_wait <= 0.0:
		_moan()

	var h := head()
	var to_sub := _sub_distance(h)
	match state:
		State.WANDER:
			if h.distance_to(_target) < 25.0 or _state_t > 90.0:
				_pick_wander()
			if interest > 0.15:
				_set_state(State.INVESTIGATE)
		State.INVESTIGATE:
			_target = _heard_at
			if interest > 0.55 and _since_heard < 1.5 and to_sub < 70.0 and _state_t > 2.0:
				_set_state(State.CHARGE)
				_moan()
			elif (h.distance_to(_heard_at) < 18.0 and _since_heard > 6.0) or interest < 0.03:
				_set_state(State.SEARCH)
		State.SEARCH:
			# 在最后听到的地方附近兜圈子
			_search_ang += delta * 0.09
			_target = _heard_at + Vector3(cos(_search_ang), 0.0, sin(_search_ang)) * 28.0 + Vector3.UP * 4.0
			# 扑空以后先掉个头（几秒内不再冲）
			if _since_heard < LISTEN_EVERY * 1.5 and interest > 0.15 and _state_t > 5.0:
				_set_state(State.INVESTIGATE)
			elif _state_t > 35.0:
				_set_state(State.WANDER)
				_pick_wander()
		State.CHARGE:
			_target = _heard_at
			if to_sub < CONTACT:
				_ram()
			elif h.distance_to(_heard_at) < 6.0 or (h.distance_to(_heard_at) < 20.0 and forward().dot(_heard_at - h) < 0.0):
				_set_state(State.SEARCH)   # 扑空：艇不出声挪开了
			elif _state_t > 25.0:
				_set_state(State.SEARCH)
		State.RETREAT:
			if _state_t > 12.0:
				_set_state(State.INVESTIGATE if interest > 0.3 else State.SEARCH)

	if _log:
		_log_t += delta
		if _log_t > 2.0:
			_log_t = 0.0
			_say("d=%.0f interest=%.2f speed=%.1f" % [to_sub, interest, speed])


func _set_state(s: State) -> void:
	if s == state:
		return
	_say("-> " + STATE_NAMES[s])
	state = s
	_state_t = 0.0
	if s == State.SEARCH:
		var off := global_position - _heard_at
		_search_ang = atan2(off.z, off.x)


## 听一下潜艇：这段时间里最响的一下够不够传到这里
func _listen() -> void:
	var n := sub.take_noise()
	var h := head()
	var d := h.distance_to(sub.global_position)
	var reach := n * hear_range
	if d > reach:
		return
	var k := 1.0 - d / reach
	interest = minf(interest + k * (0.4 if n >= 0.8 else 0.04), 1.0)
	# 离得越远、声音越小，听得越不准
	var err := d * 0.15 * (1.0 - k)
	_heard_at = sub.global_position + Vector3(_rng.randfn() * err, _rng.randfn() * err * 0.3, _rng.randfn() * err)
	_since_heard = 0.0


## 探一下海底、前方：别钻进泥里、别撞崖
func _probe() -> void:
	var space := get_world_3d().direct_space_state
	var h := head()
	var q := PhysicsRayQueryParameters3D.create(h + Vector3.UP * 5.0, h + Vector3.DOWN * 120.0, 1)
	var hit := space.intersect_ray(q)
	_floor_y = (hit.position as Vector3).y if not hit.is_empty() else -INF
	var f := forward()
	f.y = 0.0
	q = PhysicsRayQueryParameters3D.create(h, h + f.normalized() * 35.0, 1)
	_blocked = not space.intersect_ray(q).is_empty()


func _pick_wander() -> void:
	var a := _rng.randf() * TAU
	var r := sqrt(_rng.randf()) * wander_radius
	_target = _home + Vector3(cos(a) * r, _rng.randf_range(2.0, 22.0), sin(a) * r)
	_state_t = 0.0


func _move(delta: float) -> void:
	var tgt := _target
	if state != State.CHARGE:
		tgt = _pass_over(tgt)
	if _blocked:
		tgt.y = maxf(tgt.y, global_position.y + 25.0)
	var to := tgt - global_position
	var want_yaw := atan2(-to.x, -to.z)
	var dyaw := angle_difference(yaw, want_yaw)
	var max_turn := deg_to_rad(TURN[state])
	_turn_rate = move_toward(_turn_rate, clampf(dyaw * 0.8, -max_turn, max_turn), max_turn * delta)
	yaw = wrapf(yaw + _turn_rate * delta, -PI, PI)
	var horiz := Vector2(to.x, to.z).length()
	var want_pitch := clampf(atan2(to.y, maxf(horiz, 1.0)), -0.35, 0.35)
	pitch = lerp_angle(pitch, want_pitch, 1.0 - exp(-delta * 0.6))
	var want_speed: float = SPEED[state] * (0.5 if absf(dyaw) > 1.2 and state != State.CHARGE else 1.0)
	speed = move_toward(speed, want_speed, (1.8 if state == State.CHARGE else 0.5) * delta)
	global_position += forward() * speed * delta
	if global_position.y < _floor_y + MIN_ALTITUDE:
		global_position.y = move_toward(global_position.y, _floor_y + MIN_ALTITUDE, 3.0 * delta)
	rotation = Vector3(pitch, yaw, 0.0)


## 不冲的时候不往艇身上钻：要从艇旁边过，就从它头顶上过去
func _pass_over(tgt: Vector3) -> Vector3:
	var h := head()
	var p := sub.global_position
	var seg := tgt - h
	var len2 := seg.length_squared()
	if len2 < 1.0:
		return tgt
	var t := clampf((p - h).dot(seg) / len2, 0.0, 1.0)
	var closest := h + seg * t
	if closest.distance_to(p) < 14.0 and h.distance_to(p) < 60.0:
		tgt.y = maxf(tgt.y, p.y + 15.0)
	return tgt


## 头（或身体上 at 那一点）离潜艇中轴线多远
func _sub_distance(at: Vector3) -> float:
	var a := sub.global_transform * Vector3(0.0, 0.0, -6.0)
	var b := sub.global_transform * Vector3(0.0, 0.0, 7.0)
	return at.distance_to(Geometry3D.get_closest_point_to_segment(at, a, b))


func _moan() -> void:
	_moan_wait = _rng.randf_range(10.0, 20.0) if state >= State.INVESTIGATE else _rng.randf_range(25.0, 60.0)
	_to_all(&"_moan_go", [_rng.randi() % maxi(_moans.size(), 1)])


func _ram() -> void:
	var push := forward()
	push.y = maxf(push.y, 0.1)
	sub.damage(ram_damage)
	_to_all(&"_ram_go", [push.normalized()])
	_set_state(State.RETREAT)
	# 冲过头：从艇上方继续往前游一段
	_target = head() + forward() * 60.0 + Vector3.UP * 12.0
	_say("RAM hull=%.2f" % sub.hull)


func _say(msg: String) -> void:
	if _log:
		print("GIANT %d %s %s" % [Engine.get_physics_frames(), STATE_NAMES[state], msg])


# ---------------------------------------------------------------------------- 联机
func _to_all(method: StringName, args: Array) -> void:
	callv(method, args)
	for id: int in Net.loaded_peers():
		var call_args := [id, method]
		call_args.append_array(args)
		callv(&"rpc_id", call_args)


func _sync(delta: float) -> void:
	_sync_t += delta
	if _sync_t < 1.0 / SYNC_RATE:
		return
	_sync_t = 0.0
	var pack := [global_position, yaw, pitch, speed, int(state)]
	for id: int in Net.loaded_peers():
		_state_msg.rpc_id(id, pack)


func _follow(delta: float) -> void:
	if _auth.is_empty():
		return
	var age := Time.get_ticks_msec() / 1000.0 - _auth_at
	speed = _auth.speed
	state = _auth.state
	var y0 := yaw
	var k := 1.0 - exp(-delta * 4.0)
	yaw = lerp_angle(yaw, _auth.yaw, k)
	pitch = lerp_angle(pitch, _auth.pitch, k)
	_turn_rate = angle_difference(y0, yaw) / maxf(delta, 1e-4)
	var target: Vector3 = _auth.pos + forward() * speed * minf(age, 0.5)
	if global_position.distance_to(target) > 30.0:
		global_position = target
	else:
		global_position = global_position.lerp(target, k)
	rotation = Vector3(pitch, yaw, 0.0)


@rpc("authority", "unreliable_ordered")
func _state_msg(pack: Array) -> void:
	_auth = {"pos": pack[0], "yaw": pack[1], "pitch": pack[2], "speed": pack[3], "state": pack[4]}
	_auth_at = Time.get_ticks_msec() / 1000.0


@rpc("authority", "reliable")
func _moan_go(variant: int) -> void:
	_moan_boost = 1.0
	_moan_t = 0.0
	_moan_open = _anim_rng.randf_range(30.0, 40.0)
	if _motion:
		_motion.exert(0.6)  # 吼完喘得急一点
	if _voice and not _moans.is_empty():
		_voice.stream = _moans[variant % _moans.size()]
		_voice.pitch_scale = 1.0 if state != State.CHARGE else 1.12
		_voice.play()
		DebugArgs.log_sfx("giant_moan")


@rpc("authority", "reliable")
func _ram_go(push: Vector3) -> void:
	# 主机算的物理会广播过来，这里各家先自己推一把，不等
	if _motion:
		_motion.snap()
		_moan_t = INF  # 咬下去以后不再接着吼的张嘴
	sub.velocity += push * 3.5
	sub.yaw_speed += _rng.randf_range(-0.35, 0.35)
	sub.bumped.emit(3.0)
	if _ram_sfx and not _rams.is_empty():
		_ram_sfx.stream = _rams[_rng.randi() % _rams.size()]
		_ram_sfx.play()
		DebugArgs.log_sfx("giant_ram")


# ---------------------------------------------------------------------------- 贴着艇过去
func _near_effects(delta: float) -> void:
	var a := global_transform * Vector3(0.0, 0.0, -half_length)
	var b := global_transform * Vector3(0.0, 0.0, half_length)
	var p := sub.global_position
	var d := p.distance_to(Geometry3D.get_closest_point_to_segment(p, a, b))
	if d > 30.0 or speed < 0.8:
		return
	var k := 1.0 - d / 30.0
	_stress_t -= delta * (0.5 + 1.5 * k)
	if _stress_t > 0.0:
		return
	_stress_t = _rng.randf_range(1.5, 3.5)
	if _audio and _audio.has_method("hull_stress"):
		_audio.hull_stress(k)
	if _cam:
		_cam.add_shake(0.25 * k * k)


# ---------------------------------------------------------------------------- 声音
func _build_audio() -> void:
	_swim = AudioStreamPlayer3D.new()
	_swim.stream = load(SFX % "giant_swim")
	_swim.bus = &"Sea"
	_swim.unit_size = 30.0
	_swim.max_distance = 500.0
	_swim.max_db = 4.0
	_swim.volume_db = VOL.giant_swim
	_swim.autoplay = true
	add_child(_swim)
	for k in 4:
		_moans.append(load(SFX % ("giant_moan_%d" % k)))
	for k in 2:
		_rams.append(load(SFX % ("giant_ram_%d" % k)))
	_voice = AudioStreamPlayer3D.new()
	_voice.bus = &"Sea"
	_voice.unit_size = 60.0
	_voice.max_distance = 1000.0
	_voice.max_db = 6.0
	_voice.volume_db = VOL.giant_moan
	_voice.position = Vector3(0.0, 0.0, -half_length * 0.8)
	add_child(_voice)
	_ram_sfx = AudioStreamPlayer.new()
	_ram_sfx.bus = &"Cabin"
	_ram_sfx.volume_db = VOL.giant_ram
	add_child(_ram_sfx)
	var only := DebugArgs.get_arg("only-sfx").split(",", false)
	var mute := DebugArgs.get_arg("mute-sfx").split(",", false)
	for pl: Node in [_swim, _voice, _ram_sfx]:
		var sfx := "giant_swim" if pl == _swim else ("giant_moan" if pl == _voice else "giant_ram")
		if sfx in mute or (not only.is_empty() and sfx not in only):
			pl.set("volume_db", -80.0)




# ---------------------------------------------------------------------------- 身体、动作
func _build_body() -> void:
	_anim_rng.randomize()
	_anim_log = DebugArgs.has("giant-anim-log")
	if DebugArgs.has("giant-jaw"):
		_jaw_force = clampf(float(DebugArgs.get_arg("giant-jaw")), 0.0, GiantMotion.JAW_OPEN_MAX)
	if DebugArgs.has("giant-turn"):
		_turn_force = deg_to_rad(float(DebugArgs.get_arg("giant-turn")))
	var pose := DebugArgs.get_arg("giant-pose").split(":")
	_pose = pose[0]
	if pose.size() > 1:
		_pose_ram_at = int(pose[1])
	_motion = GiantMotion.new(self, LAYER)
	if DebugArgs.has("giant-breath"):
		_motion.breath_rate = float(DebugArgs.get_arg("giant-breath"))
	if DebugArgs.has("giant-gill"):
		_motion.gill_force = float(DebugArgs.get_arg("giant-gill"))
	if _pose == "gasp":
		_motion.exert_force = 1.0
	if DebugArgs.has("giant-shots"):
		var a := DebugArgs.get_arg("giant-shots").split(":")
		for f in a[0].split(",", false):
			_shots.append(int(f))
		_shots.sort()
		_shot_prefix = a[1] if a.size() > 1 else "user://giant"
	if DebugArgs.has("giant-bones"):
		_motion.show_bones()
	Submarine.add_layer(self, Submarine.SEABED_LAYER)
	if DebugArgs.has("giant-light"):
		# 看模型、看动作用：两侧上方各一盏大灯跟着它走
		for side in [-1.0, 1.0]:
			var lamp := OmniLight3D.new()
			lamp.position = Vector3(side * 28.0, 16.0, side * 6.0)
			lamp.omni_range = 75.0
			lamp.light_energy = 6.0 if side > 0.0 else 2.5
			lamp.omni_attenuation = 0.6
			add_child(lamp)


## 每帧摆骨骼：游动跟着速度、转弯角速度、俯仰变化；嘴和上头按状态（冲刺时按到艇的距离）、吼叫、撞艇来
func _animate(delta: float) -> void:
	if delta <= 0.0:
		return
	var pitch_rate := angle_difference(_last_pitch, pitch) / delta
	_last_pitch = pitch
	var spd := speed
	var turn := _turn_rate
	var pitch_now := pitch
	var cur := state
	# 冲刺扑空（没撞上就转去找）：咬一口空的
	if _anim_state == State.CHARGE and cur == State.SEARCH:
		_motion.snap(false)
		_moan_t = INF
	_anim_state = cur
	var charge_d := INF
	if cur == State.CHARGE:
		charge_d = _sub_distance(head())
	match _pose:
		"cruise":
			spd = SPEED[State.WANDER]
		"charge", "ram":
			spd = SPEED[State.CHARGE]
			charge_d = 0.0
			if _pose == "ram" and Engine.get_process_frames() >= _pose_ram_at:
				_pose = "rammed"
				_motion.snap()
				_moan_t = INF
				_anim_say("snap")
		"rammed":
			spd = SPEED[State.RETREAT]
		"idle", "gasp":
			spd = 0.0
		"turn_left", "turn_right":
			spd = SPEED[State.WANDER]
			turn = deg_to_rad(9.0) * (1.0 if _pose == "turn_left" else -1.0)
		"rise", "dive":
			spd = SPEED[State.WANDER]
			pitch_now = deg_to_rad(14.0) * (1.0 if _pose == "rise" else -1.0)
			pitch_rate = 0.0
	if not is_nan(_turn_force):
		turn = _turn_force
	var target := _jaw_idle(delta, cur)
	var lift_target := 0.0
	if charge_d < INF:
		# 冲过来：离得越近张得越大，最后十几米张满，上头往上抬
		target = maxf(target, lerpf(14.0, GiantMotion.JAW_OPEN_MAX, smoothstep(60.0, 14.0, charge_d)))
		lift_target = 8.0 * smoothstep(45.0, 14.0, charge_d)
	# 吼：张到 30～40° 停几秒再慢慢合上
	_moan_t += delta
	if _moan_t < 7.0:
		var k := smoothstep(0.0, 1.2, _moan_t) * (1.0 - smoothstep(4.5, 7.0, _moan_t))
		target = maxf(target, _moan_open * k)
	_motion.still_flow = _still  # setup() 在 _ready 之后才定 _still，每帧跟一下
	_motion.update(delta, spd, turn, pitch_rate, target, lift_target, _jaw_force, pitch_now)
	if _anim_log:
		_anim_log_t += delta
		if _anim_log_t >= 1.0:
			_anim_log_t = 0.0
			_anim_say("d=%.0f" % charge_d if charge_d < INF else "")


## 不冲的时候：差不多闭着（呼吸那几度 giant_motion.gd 自己加），隔一阵再张合一下（过水）；找东西的时候嘴半开着一点
func _jaw_idle(delta: float, cur: State) -> float:
	var open := 0.0
	if cur == State.INVESTIGATE or cur == State.SEARCH:
		open += 2.5
	_gulp_wait -= delta
	if _gulp_wait <= 0.0:
		_gulp_wait = _anim_rng.randf_range(14.0, 30.0)
		_gulp_t = 0.0
		_gulp_open = _anim_rng.randf_range(4.0, 8.0)
	_gulp_t += delta
	if _gulp_t < 4.0:
		open += _gulp_open * sin(PI * _gulp_t / 4.0)
	return open


## --giant-shots：这一帧画完存一张截图（连拍看摆动用）
func _shoot(frame: int) -> void:
	await RenderingServer.frame_post_draw
	get_viewport().get_texture().get_image().save_png("%s_%d.png" % [_shot_prefix, frame])
	print("GIANT_SHOT %s_%d.png" % [_shot_prefix, frame])


func _anim_say(msg: String) -> void:
	if _anim_log:
		print("GIANT_ANIM %d %s jaw=%.1f lift=%.1f amp=%.2f freq=%.3f head=%.2f tail=%.2f speed=%.1f gill=%.1f,%.1f exert=%.2f pec=%.1f,%.1f sweep=%.0f att=%.1f para=%.2f %s" % [
			Engine.get_physics_frames(), STATE_NAMES[state], _motion.jaw, _motion.lift, _motion.amp, _motion.freq,
			_motion.head_yaw, _motion.tail_x, speed, _motion.gill.x, _motion.gill.y, _motion.exertion,
			_motion.pec_el.x, _motion.pec_el.y, _motion.pec_sweep, _motion.pec_attack, _motion.para_back, msg])

