class_name SubSession
extends Node
## 舱内联机同步。深海场景（deep_sea.gd）开局挂一个，节点名固定叫 Session——各家的节点路径一样，RPC 才找得到。
## - 船员：每个人把自己的第一人称状态（眼睛、视线、步伐、坐没坐、开没开门）每秒发 20 次给别人，
##   别人那边用替身（crew_puppet.gd）带着一个 crew_body.gd 的身体演出来，脸看得见，脚步声也有
## - 潜艇：主机算物理，每秒广播 20 次位置、速度和正在用的操纵输入；别人那边用同样的输入跟着算（不卡），
##   再慢慢往主机的位置上拉。坐在驾驶椅上的人把自己的输入发给主机（自己这边直接用，不等主机）
## - 驾驶椅谁坐、探照灯、声呐主动 / 被动、水密门：先问主机，主机定了再告诉所有人（同时有两个人抢，主机说了算）
## - 艇壳耐久：主机算（巨物撞的，见 giant.gd），跟着潜艇状态广播；破了就全员出局回大厅
## 单人（没联网）时自己就是主机，走的是同一条路，只是没有别人可发。

const CREW_RATE := 20.0
const SUB_RATE := 20.0
const INPUT_RATE := 30.0
## 和主机的潜艇位置差多少米就直接跳过去（卡得太久、刚连上）
const SNAP_DIST := 4.0
## 艇壳破了以后过多久回大厅
const WRECK_DELAY := 7.0
## 门的开关和主机对不上多久就按主机的摆过去（各家演门的动作有随机的快慢，演完前后差个零点几秒是正常的）
const DOOR_GRACE := 2.0
## 开局站在哪（舱内局部 x、z）、朝哪：驾驶的人坐驾驶椅，其余按岗位站到各自的工作台跟前
## （左舷导航、水声通信；右舷配电、生命支持；潜水员在后面水密门跟前，见 README 的舱内布局）
const STATIONS := {
	Net.Role.SONAR: [Vector2(-0.3, -0.5), PI * 0.5],
	Net.Role.ENGINEER: [Vector2(0.3, -0.75), -PI * 0.5],
	Net.Role.DIVER: [Vector2(0.05, 1.65), PI],
}
const CREW_BODY := preload("res://scripts/crew_body.gd")
const FONT := "res://assets/fonts/NotoSerifSC-VF.ttf"

## 驾驶椅上坐着谁（peer id，0 = 空着）
var seat_owner := 0

var sub: Submarine
var _cam: Node   # cockpit_camera.gd
var _door: Node  # watertight_door.gd
var _audio: Node
var _puppets := {}  # peer id → CrewPuppet
var _bodies := {}   # peer id → crew_body
var _crew_t := 0.0
var _sub_t := 0.0
var _input_t := 0.0
## 主机上：坐驾驶椅的人发来的输入
var _pilot_input := Vector3.ZERO
## 别人那边：主机最近一次广播的潜艇状态
var _auth := {}
var _auth_at := 0.0
var _door_mismatch := 0.0
## 别人那边：主机的场景还没加载好时想坐驾驶椅，等主机好了再问（-1 没有要问的，0 站起来，1 坐下）
var _seat_wish := -1
var _hud: CanvasLayer
var _roster: Label
var _menu: Control
var _wreck: Label
var _wreck_t := -1.0


func _init() -> void:
	name = "Session"


func setup(p_sub: Submarine) -> void:
	sub = p_sub
	_cam = sub.get_node("%CockpitCamera")
	_door = sub.find_child("Door", true, false)
	_audio = sub.find_child("Audio", true, false)
	sub.session = self
	if _door:
		_door.session = self


func _ready() -> void:
	# 直接打开深海场景（--scene=deep_sea、F6）：没走大厅，当单人
	if Net.players.is_empty():
		Net.players = {Net.my_id(): {"name": Net.local_name, "role": Net.Role.PILOT}}
		Net.in_game = true
	_place_local()
	_cam.seated_changed.connect(func(s: bool) -> void: _ask_seat(s))
	Net.roster_changed.connect(_sync_puppets)
	Net.peer_left.connect(_on_peer_left)
	Net.peer_loaded.connect(_on_peer_loaded)
	_sync_puppets()
	_build_hud()
	Net.mark_loaded()
	if Net.is_host():
		# 比主机先加载好的人
		for id: int in Net.loaded_peers():
			_on_peer_loaded(id)
	if _cam.is_seated():
		_ask_seat(true)


## 按岗位摆好自己：驾驶坐驾驶椅（开局默认就坐着），其余站到工作台跟前。--at 调试摆位时不动
func _place_local() -> void:
	if DebugArgs.has("at"):
		return
	var role := Net.role_of(Net.my_id())
	if STATIONS.has(role):
		var st: Array = STATIONS[role]
		_cam.place_standing(st[0], st[1])


# ---------------------------------------------------------------------------- 每帧
func _process(delta: float) -> void:
	var me := Net.my_id()
	_cam.seat_taken = seat_owner != 0 and seat_owner != me
	var obstacles: Array[Vector2] = []
	for id: int in _puppets:
		var p: CrewPuppet = _puppets[id]
		var show := p.has_state()
		p.visible = show
		_bodies[id].visible = show
		if show and p.sit_amount() < 0.5:
			obstacles.append(p.feet())
	_cam.crew_obstacles = obstacles

	_crew_t += delta
	if _crew_t >= 1.0 / CREW_RATE:
		_crew_t = 0.0
		_send_crew()
	if Net.is_host():
		_sub_t += delta
		if _sub_t >= 1.0 / SUB_RATE:
			_sub_t = 0.0
			_send_sub()
	elif seat_owner == me and _cam.is_seated() and _host_ready():
		_input_t += delta
		if _input_t >= 1.0 / INPUT_RATE:
			_input_t = 0.0
			_pilot_input_msg.rpc_id(1, sub.steering())
	_update_menu()
	_update_wreck(delta)


func _physics_process(delta: float) -> void:
	var me := Net.my_id()
	if Net.is_host():
		# 主机：自己坐着就读键盘；别人坐着用他发来的输入；没人坐就不推（单人时舱外视角也能开，见 Submarine.steering）
		if not Net.is_online() or seat_owner == me:
			sub.use_remote_input = false
		else:
			sub.use_remote_input = true
			sub.remote_input = _pilot_input if seat_owner != 0 else Vector3.ZERO
		return
	# 别人那边：自己坐着就按自己的键盘先算（不等主机），否则用主机广播的输入；算完往主机的位置上拉
	var local_pilot: bool = seat_owner == me and _cam.is_seated()
	sub.use_remote_input = not local_pilot
	if _auth.is_empty():
		return
	if not local_pilot:
		sub.remote_input = _auth.input
	var age := Time.get_ticks_msec() / 1000.0 - _auth_at
	var target: Vector3 = _auth.pos + (_auth.vel as Vector3) * minf(age, 0.5)
	var err := target - sub.global_position
	var k := 1.0 - exp(-delta * 3.0)
	if err.length() > SNAP_DIST:
		sub.global_position = target
	elif err.length() > 0.002:
		sub.global_position += err * k
	var dyaw := angle_difference(sub.rotation.y, _auth.yaw)
	if absf(dyaw) > 0.0005:
		sub.rotation.y += dyaw * k
	sub.velocity = sub.velocity.lerp(_auth.vel, k)
	sub.yaw_speed = lerpf(sub.yaw_speed, _auth.yaw_speed, k)


func _send_crew() -> void:
	var peers := Net.loaded_peers()
	if peers.is_empty():
		return
	var c: Node = _cam
	var door_op: bool = c.door_op
	var pack := [Time.get_ticks_msec() / 1000.0, (c as Node3D).position, c.feet(), c.yaw, c.pitch,
		c.gait_steps, c.gait_speed, c.gait_run, c.sit_amount(), c.door_lean, c.door_yaw, door_op, c.door_aft]
	for id: int in peers:
		_crew_state.rpc_id(id, pack)


func _send_sub() -> void:
	var peers := Net.loaded_peers()
	if peers.is_empty():
		return
	var pack := [sub.global_position, sub.rotation.y, sub.velocity, sub.yaw_speed,
		Vector3(sub.thrust_input, sub.lift_input, sub.steering().z if not sub.use_remote_input else sub.remote_input.z),
		_door.is_open if _door else false, sub.hull]
	for id: int in peers:
		_sub_state.rpc_id(id, pack)


## 主机：发给自己和所有已经加载好的人
func _to_all(method: StringName, args: Array = []) -> void:
	callv(method, args)
	for id: int in Net.loaded_peers():
		var call_args := [id, method]
		call_args.append_array(args)
		callv(&"rpc_id", call_args)


# ---------------------------------------------------------------------------- 替身
func _sync_puppets() -> void:
	var me := Net.my_id()
	for id: int in Net.players:
		if id != me and not _puppets.has(id):
			_spawn(id)
	for id: int in _puppets.keys():
		if not Net.players.has(id):
			_despawn(id)


func _spawn(id: int) -> void:
	var body := sub.body
	var p := CrewPuppet.new()
	body.add_child(p)
	p.setup(id, Net.player_name(id), _door)
	var cb: Node3D = CREW_BODY.new()
	cb.name = "Crew_%d" % id
	cb.first_person = false
	cb.camera_path = NodePath("../" + String(p.name))
	cb.visible = false
	body.add_child(cb)
	_puppets[id] = p
	_bodies[id] = cb
	if _audio and _audio.has_method("add_walker"):
		_audio.add_walker(p)


func _despawn(id: int) -> void:
	if _puppets.has(id):
		_puppets[id].queue_free()
		_bodies[id].queue_free()
		_puppets.erase(id)
		_bodies.erase(id)


func _on_peer_left(id: int) -> void:
	_despawn(id)
	if Net.is_host() and seat_owner == id:
		_to_all(&"_seat", [0])


## 主机：新加载好的人要知道现在谁坐着、灯开没开、门开没开。
## 别人那边：主机加载好了，之前想坐驾驶椅的话现在去问
func _on_peer_loaded(id: int) -> void:
	if Net.is_host() and id != Net.my_id():
		_init_state.rpc_id(id, seat_owner, sub.lights_on, _door.is_open if _door else false, sub.sonar_active)
	elif id == 1 and _seat_wish >= 0:
		_seat_req.rpc_id(1, _seat_wish == 1)
		_seat_wish = -1


## 主机的场景加载好了没有（没好的时候发过去的 RPC 主机那边找不到节点）
func _host_ready() -> bool:
	return Net.is_host() or 1 in Net.loaded_peers()


# ---------------------------------------------------------------------------- 请求（先问主机）
func _ask_seat(sit: bool) -> void:
	if Net.is_host():
		_seat_decide(Net.my_id(), sit)
	elif _host_ready():
		_seat_req.rpc_id(1, sit)
	else:
		_seat_wish = 1 if sit else 0


func request_lights(on: bool) -> void:
	if Net.is_host():
		_to_all(&"_lights", [on])
	elif _host_ready():
		_lights_req.rpc_id(1, on)


func request_sonar(active: bool) -> void:
	if Net.is_host():
		_to_all(&"_sonar", [active])
	elif _host_ready():
		_sonar_req.rpc_id(1, active)


func request_door() -> void:
	if Net.is_host():
		_door_decide(Net.my_id())
	elif _host_ready():
		_door_req.rpc_id(1)


func _seat_decide(id: int, sit: bool) -> void:
	if sit:
		if seat_owner != 0 and seat_owner != id:
			if id == Net.my_id():
				_seat_denied()
			else:
				_seat_denied.rpc_id(id)
			return
		_to_all(&"_seat", [id])
	elif seat_owner == id:
		_to_all(&"_seat", [0])


func _door_decide(id: int) -> void:
	if _door == null or _door.busy:
		if id == Net.my_id():
			_door_nack()
		else:
			_door_nack.rpc_id(id)
		return
	_to_all(&"_door_go")


# ---------------------------------------------------------------------------- RPC
@rpc("any_peer", "unreliable_ordered")
func _crew_state(pack: Array) -> void:
	var id := multiplayer.get_remote_sender_id()
	if not _puppets.has(id):
		return
	_puppets[id].push(pack[0], {"eye": pack[1], "feet": pack[2], "yaw": pack[3], "pitch": pack[4],
		"gs": pack[5], "gv": pack[6], "gr": pack[7], "sit": pack[8], "dl": pack[9], "dy": pack[10],
		"dop": pack[11], "daft": pack[12]})


@rpc("authority", "unreliable_ordered")
func _sub_state(pack: Array) -> void:
	_auth = {"pos": pack[0], "yaw": pack[1], "vel": pack[2], "yaw_speed": pack[3], "input": pack[4]}
	_auth_at = Time.get_ticks_msec() / 1000.0
	sub.hull = pack[6]
	if _door == null:
		return
	var open: bool = pack[5]
	if _door.busy or _door.pending or _door.is_open == open:
		_door_mismatch = 0.0
	else:
		_door_mismatch += 1.0 / SUB_RATE
		if _door_mismatch > DOOR_GRACE:
			_door_mismatch = 0.0
			_door.set_open_now(open)


@rpc("any_peer", "unreliable_ordered")
func _pilot_input_msg(steer: Vector3) -> void:
	if Net.is_host() and multiplayer.get_remote_sender_id() == seat_owner:
		_pilot_input = steer.clamp(-Vector3.ONE, Vector3.ONE)


@rpc("authority", "reliable")
func _init_state(owner_id: int, lights: bool, door_open: bool, sonar_active: bool) -> void:
	seat_owner = owner_id
	sub.set_lights(lights)
	sub.set_sonar(sonar_active)
	if _door:
		_door.set_open_now(door_open)


@rpc("any_peer", "reliable")
func _seat_req(sit: bool) -> void:
	if Net.is_host():
		_seat_decide(multiplayer.get_remote_sender_id(), sit)


@rpc("authority", "reliable")
func _seat(owner_id: int) -> void:
	seat_owner = owner_id
	Net.log_event("seat %d" % owner_id)
	_pilot_input = Vector3.ZERO


## 两个人同时坐上去，主机判给了别人：站起来
@rpc("authority", "reliable")
func _seat_denied() -> void:
	_cam.stand_up()


@rpc("any_peer", "reliable")
func _lights_req(on: bool) -> void:
	if Net.is_host():
		_to_all(&"_lights", [on])


@rpc("authority", "reliable")
func _lights(on: bool) -> void:
	sub.switch_lights(on)
	Net.log_event("lights %s" % on)


@rpc("any_peer", "reliable")
func _sonar_req(active: bool) -> void:
	if Net.is_host():
		_to_all(&"_sonar", [active])


@rpc("authority", "reliable")
func _sonar(active: bool) -> void:
	sub.switch_sonar(active)
	Net.log_event("sonar %s" % ("active" if active else "passive"))


@rpc("any_peer", "reliable")
func _door_req() -> void:
	if Net.is_host():
		_door_decide(multiplayer.get_remote_sender_id())


@rpc("authority", "reliable")
func _door_go() -> void:
	Net.log_event("door toggle")
	if _door:
		_door.toggle()


@rpc("authority", "reliable")
func _door_nack() -> void:
	if _door:
		_door.pending = false


# ---------------------------------------------------------------------------- 界面：右上角船员名单，Esc 放出鼠标时的菜单
func _build_hud() -> void:
	_hud = CanvasLayer.new()
	_hud.layer = 5
	add_child(_hud)
	if DebugArgs.capturing() or DebugArgs.has("no-hud"):
		_hud.visible = false
	var font: Font = load(FONT)
	_roster = Label.new()
	_roster.anchor_left = 1.0
	_roster.anchor_right = 1.0
	_roster.offset_left = -360
	_roster.offset_right = -24
	_roster.offset_top = 20
	_roster.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	_roster.add_theme_font_override("font", font)
	_roster.add_theme_font_size_override("font_size", 17)
	_roster.add_theme_color_override("font_color", Color(0.85, 0.78, 0.65, 0.85))
	_roster.add_theme_color_override("font_shadow_color", Color(0, 0, 0, 0.8))
	_hud.add_child(_roster)

	_menu = PanelContainer.new()
	_menu.set_anchors_and_offsets_preset(Control.PRESET_CENTER)
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.05, 0.05, 0.045, 0.88)
	sb.border_color = Color(0.55, 0.45, 0.3, 0.6)
	sb.set_border_width_all(1)
	sb.set_content_margin_all(24)
	_menu.add_theme_stylebox_override("panel", sb)
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 12)
	_menu.add_child(box)
	for spec: Array in [["继续", _resume], ["离开下潜，回大厅", func() -> void: Net.leave()]]:
		var b := Button.new()
		b.text = spec[0]
		b.custom_minimum_size = Vector2(260, 44)
		b.add_theme_font_override("font", font)
		b.add_theme_font_size_override("font_size", 19)
		b.pressed.connect(spec[1])
		box.add_child(b)
	_menu.visible = false
	_hud.add_child(_menu)

	_wreck = Label.new()
	_wreck.set_anchors_and_offsets_preset(Control.PRESET_CENTER)
	_wreck.grow_horizontal = Control.GROW_DIRECTION_BOTH
	_wreck.grow_vertical = Control.GROW_DIRECTION_BOTH
	_wreck.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_wreck.add_theme_font_override("font", font)
	_wreck.add_theme_font_size_override("font_size", 30)
	_wreck.add_theme_color_override("font_color", Color(0.85, 0.78, 0.65))
	_wreck.add_theme_color_override("font_shadow_color", Color(0, 0, 0, 0.9))
	_wreck.text = "艇壳裂了。\n镇海号沉进了归墟。"
	_wreck.modulate.a = 0.0
	_hud.add_child(_wreck)
	Net.roster_changed.connect(_update_roster)
	_update_roster()


## 艇壳破了：字慢慢浮出来，过几秒回大厅（--no-wreck 调试时不回）
func _update_wreck(delta: float) -> void:
	if _wreck == null:
		return
	if _wreck_t < 0.0:
		if sub.hull <= 0.0:
			_wreck_t = 0.0
			Net.log_event("wrecked")
		return
	_wreck_t += delta
	_wreck.modulate.a = clampf((_wreck_t - 1.0) / 2.0, 0.0, 1.0)
	if _wreck_t > WRECK_DELAY and not DebugArgs.has("no-wreck"):
		_wreck_t = -INF
		Net.leave("镇海号失事")


func _resume() -> void:
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED


func _update_menu() -> void:
	if _menu:
		_menu.visible = Input.mouse_mode == Input.MOUSE_MODE_VISIBLE and not DebugArgs.has("actions")
	if Engine.get_process_frames() % 15 == 0:
		_update_roster()


func _update_roster() -> void:
	if _roster == null:
		return
	if not Net.is_online():
		_roster.text = ""
		return
	var lines := PackedStringArray()
	var ids := Net.players.keys()
	ids.sort()
	for id: int in ids:
		var tag := "（你）" if id == Net.my_id() else ""
		var seat := "  · 驾驶椅" if id == seat_owner else ""
		lines.append("%s%s  %s%s" % [Net.player_name(id), tag, Net.ROLE_NAMES[Net.role_of(id)], seat])
	_roster.text = "\n".join(lines)
