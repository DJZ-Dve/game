extends Node3D
## 中间隔壁上的快速水密门：开门先转手轮——经过减速箱带动曲柄盘，六根连杆同时把门扇四周的压紧把手拨离楔块——
## 再把门扇推开；关门反过来，门扇甩回去撞上门框，再拧紧手轮把把手压回楔块上。
## 门扇（Door_Leaf_*）、手轮（Door_Wheel_*）、曲柄盘（Door_Crank_*）、把手（Door_Dog{k}_*）、连杆（Door_Rod_k）
## 在舱内模型里都是单独的网格，这里把它们挂到各自的转轴（Door_Hinge、Door_WheelAxis、Door_CrankAxis、
## Door_DogAxis_k）上转。门往控制舱一侧开，门轴在左舷。
##
## 动作按一扇八九十公斤的钢门来做，不用匀速插值：
## - 手轮是两只手倒着把一把一把拧的：每一把转一百来度、中间换手停一下；把手压在楔块上时越拧越沉，
##   每把转得更少更慢，换手时手轮被楔块顶回来一点；开门第一下要先使劲掰（把手在楔块上咬死了），掰动了才猛地一松
## - 门扇：开门时胶条先“啵”地松开一条缝，再推开，起步慢、越荡越快、快到头时被手拦住，略微过头再回来；
##   关门是先使劲拉、再靠惯性甩过去，越来越快地撞上门框，弹回来一点又被拉回去贴上，把手被震得晃几下

signal state_changed(open: bool)
## 给音效的节点（sub_audio.gd）。strength 0~1 是这一下的轻重：
##   strain   开门第一下掰手轮（把手还咬在楔块上）
##   unlatch  掰动了，六个把手一起从楔块上蹦开
##   seal     胶条松开、两舱压差“噗”地泄掉
##   air      门扇快关上时挤出来的风
##   slam     门扇撞上门框
##   knock    弹回来再贴上门框的那一下
##   latched  手轮拧到底，把手全部压死在楔块上（上锁）
signal sound(event: StringName, strength: float)

const OPEN_DEG := 110.0
const WHEEL_TURNS := 1.25
## 手轮转 WHEEL_TURNS 圈，曲柄盘转这么多度
const CRANK_DEG := 50.0
## 把手骑上楔块的那一段（unlatch 低于这个值时越拧越沉，把手在楔块上刮）
const WEDGE_ZONE := 0.3
## 拧紧时胶条被压进去，门扇往门框里多转这么一点
const SEAT_DEG := 0.3

var is_open := false
var busy := false
## 0 = 关紧，1 = 全开（走动范围按它决定门洞能不能过）
var openness := 0.0
## 0 = 把手压紧，1 = 把手全部拨开；跟着手轮一起变
var unlatch := 0.0:
	set(v):
		unlatch = v
		_update_linkage()

## 人的双手（crew_body.gd 按它摆 IK）：hands 想不想握着手轮；grip 是这一把开始时手轮的角度——
## 握住以后手跟着手轮转过 (手轮角度 - grip)，换手时 grip 跟上，手滑回原来的位置重新握
var hands := false
var grip := 0.0

var _hinge: Node3D
var _wheel: Node3D
var _crank: Node3D
## 门扇撞门框时把手、手轮被震得晃（加在连杆解算的角度上，慢慢衰减）
var _rattle := 0.0
var _rattling := false
# 连杆机构：门扇平面里的二维坐标（门轴转轴的局部坐标系，门扇平面是它的 XY 平面）
var _dogs: Array[Node3D] = []
var _rods: Array[Node3D] = []
var _c := Vector2.ZERO        # 曲柄盘中心
var _a0: Array[Vector2] = []  # 曲柄盘上的连杆销（关门时）
var _s: Array[Vector2] = []   # 把手转轴
var _b0: Array[Vector2] = []  # 把手曲臂上的连杆销（关门时）
var _b: Array[Vector2] = []   # 上一帧的曲臂销（两个解里挑离它近的那个）
var _len: Array[float] = []
var _rod_z: Array[float] = []


func _ready() -> void:
	var sub := owner
	var hinge := sub.find_child("Door_Hinge", true, false) as Node3D
	var axis := sub.find_child("Door_WheelAxis", true, false) as Node3D
	if hinge == null or axis == null:
		push_warning("舱内模型里没有水密门（Door_Hinge / Door_WheelAxis）")
		return
	_hinge = _pivot("DoorPivot", hinge)
	_wheel = _pivot("DoorWheelPivot", axis)
	for n in sub.find_children("Door_Leaf_*", "Node3D", true, false):
		n.reparent(_hinge, true)
	for n in sub.find_children("Door_Wheel_*", "Node3D", true, false):
		n.reparent(_wheel, true)
	_wheel.reparent(_hinge, true)
	_setup_linkage(sub)
	set_process(false)
	if DebugArgs.get_arg("door") == "open":
		is_open = true
		openness = 1.0
		_hinge.rotation.y = deg_to_rad(OPEN_DEG)
		_wheel.rotation.z = TAU * WHEEL_TURNS
		unlatch = 1.0
	else:
		_hinge.rotation.y = -deg_to_rad(SEAT_DEG)


## 在挂点同一位置建一个空节点当转轴
func _pivot(nm: String, anchor: Node3D) -> Node3D:
	var p := Node3D.new()
	p.name = nm
	anchor.get_parent().add_child(p)
	p.transform = anchor.transform
	return p


func _setup_linkage(sub: Node) -> void:
	var crank_axis := sub.find_child("Door_CrankAxis", true, false) as Node3D
	if crank_axis == null:
		return
	_crank = _pivot("DoorCrankPivot", crank_axis)
	for n in sub.find_children("Door_Crank_*", "Node3D", true, false):
		n.reparent(_crank, true)
	_crank.reparent(_hinge, true)
	_c = _flat(_crank.position)
	var k := 0
	while true:
		var dog_axis := sub.find_child("Door_DogAxis_%d" % k, true, false) as Node3D
		var pin := sub.find_child("Door_DogPin_%d" % k, true, false) as Node3D
		var rod := sub.find_child("Door_Rod_%d" % k, true, false) as Node3D
		if dog_axis == null or pin == null or rod == null:
			break
		var dog := _pivot("DoorDogPivot%d" % k, dog_axis)
		for n in sub.find_children("Door_Dog%d_*" % k, "Node3D", true, false):
			n.reparent(dog, true)
		dog.reparent(_hinge, true)
		rod.reparent(_hinge, true)
		_dogs.append(dog)
		_rods.append(rod)
		_s.append(_flat(dog.position))
		_a0.append(_flat(rod.position))
		var b := _flat(_hinge.to_local(pin.global_position))
		_b0.append(b)
		_b.append(b)
		_len.append(b.distance_to(_flat(rod.position)))
		_rod_z.append(rod.position.z)
		k += 1


func _flat(v: Vector3) -> Vector2:
	return Vector2(v.x, v.y)


## 曲柄盘转到 unlatch 对应的角度，解出每个把手的转角（四连杆：曲柄销绕曲柄盘转，曲臂销绕把手轴转，中间连杆长度不变）
func _update_linkage() -> void:
	if _crank == null:
		return
	var ang := deg_to_rad(CRANK_DEG) * (unlatch + _rattle)
	_crank.rotation.z = ang
	for k in _dogs.size():
		var a := _c + (_a0[k] - _c).rotated(ang)
		var b := _circle_hit(_s[k], _s[k].distance_to(_b0[k]), a, _len[k], _b[k])
		_b[k] = b
		_dogs[k].rotation.z = angle_difference((_b0[k] - _s[k]).angle(), (b - _s[k]).angle())
		var d := (b - a).normalized()
		var x := Vector3(d.x, d.y, 0.0)
		var z := Vector3(0, 0, 1)
		_rods[k].transform = Transform3D(Basis(x, z.cross(x), z), Vector3(a.x, a.y, _rod_z[k]))


## 两个圆的交点里离 near 近的那个（不相交时取最近点）
func _circle_hit(c1: Vector2, r1: float, c2: Vector2, r2: float, near: Vector2) -> Vector2:
	var d := c2 - c1
	var dist := maxf(d.length(), 1e-6)
	var a := (r1 * r1 - r2 * r2 + dist * dist) / (2.0 * dist)
	var h := sqrt(maxf(r1 * r1 - a * a, 0.0))
	var m := c1 + d * (a / dist)
	var perp := Vector2(-d.y, d.x) / dist * h
	var p1 := m + perp
	var p2 := m - perp
	return p1 if p1.distance_squared_to(near) < p2.distance_squared_to(near) else p2


func toggle() -> void:
	if busy or _hinge == null:
		return
	busy = true
	if is_open:
		_close_sequence()
	else:
		_open_sequence()


# ---------------------------------------------------------------------------- 开门
func _open_sequence() -> void:
	hands = true
	grip = _wheel.rotation.z
	# 先使劲掰：手轮只挪动几度（把手咬在楔块上），掰动的一瞬间猛地一松，把手全部蹦开
	sound.emit(&"strain", 1.0)
	await _turn(deg_to_rad(randf_range(3.5, 5.0)), 0.32, 2.2)
	await _wait(0.05)
	sound.emit(&"unlatch", 1.0)
	_shake(0.12)
	await _turn(deg_to_rad(randf_range(55.0, 65.0)), 0.16, 0.6)
	grip = _wheel.rotation.z
	# 接着一把一把拧开
	await _crank_to(TAU * WHEEL_TURNS, false)
	await _wait(randf_range(0.18, 0.26))
	# 胶条粘在刀口上：门扇先“啵”地松开一条缝，再推开
	sound.emit(&"seal", 1.0)
	await _swing_to(deg_to_rad(1.8), 0.12)
	await _wait(0.1)
	await _swing_open()
	_finish()


## 推开门扇：被手一推起步慢慢加速，快到头时被手拦住，略微过头一点再回来（欠阻尼的弹簧）
func _swing_open() -> void:
	var target := deg_to_rad(OPEN_DEG)
	var w := 2.8
	var zeta := 0.8
	var th := _hinge.rotation.y
	var v := 0.0
	var t := 0.0
	while t < 3.0:
		var dt := get_process_delta_time()
		t += dt
		for i in 4:
			var h := dt / 4.0
			v += (w * w * (target - th) - 2.0 * zeta * w * v) * h
			th += v * h
		_hinge.rotation.y = th
		openness = clampf(th / target / 0.6, 0.0, 1.0)
		if th > deg_to_rad(25.0):
			hands = false   # 推（拉）开二十几度就够不着了，松手
		if t > 0.8 and absf(target - th) < deg_to_rad(0.3) and absf(v) < 0.03:
			break
		await get_tree().process_frame
	_hinge.rotation.y = target
	openness = 1.0


# ---------------------------------------------------------------------------- 关门
func _close_sequence() -> void:
	# 门洞马上就不让过了；手一直想去够手轮（够得着才握得上，见 crew_body.gd）
	openness = 0.0
	hands = true
	grip = _wheel.rotation.z
	await _swing_shut()
	await _wait(randf_range(0.3, 0.4))
	while _rattling:
		await get_tree().process_frame
	# 拧紧：越往后把手骑上楔块越沉；最后一把咬死，手轮被楔块顶回来一点
	await _crank_to(0.0, true)
	_finish()


## 拉上门扇：先使劲拉一把，之后手扶着跟着走、靠惯性甩过去，撞上门框弹回来一点，又被拉回去贴上
func _swing_shut() -> void:
	var th := _hinge.rotation.y
	var v := 0.0
	var t := 0.0
	var pull := deg_to_rad(randf_range(140.0, 160.0))
	var pull_time := randf_range(0.5, 0.6)
	var hold := deg_to_rad(150.0)  # 撞上以后人还拉着门把手
	var air_done := false
	var hits := 0
	while hits < 3:
		var dt := get_process_delta_time()
		t += dt
		for i in 4:
			var h := dt / 4.0
			var a := -pull if t < pull_time else -deg_to_rad(40.0)
			if hits > 0:
				a = -hold
			a -= 0.35 * v
			v += a * h
			th += v * h
			if th <= 0.0 and v < 0.0:
				var speed := -v
				hits += 1
				if hits == 1:
					var s := clampf(rad_to_deg(speed) / 90.0, 0.3, 1.2)
					sound.emit(&"slam", s)
					_shake(0.45 * s)
					_start_rattle(s)
				elif rad_to_deg(speed) > 3.0:
					sound.emit(&"knock", clampf(rad_to_deg(speed) / 30.0, 0.1, 1.0))
					_shake(0.06)
				th = 0.0
				v = speed * 0.17
				if rad_to_deg(v) < 2.0:
					hits = 3
					v = 0.0
					break
		if not air_done and th < deg_to_rad(14.0) and hits == 0:
			air_done = true
			sound.emit(&"air", clampf(rad_to_deg(-v) / 90.0, 0.3, 1.0))
		_hinge.rotation.y = maxf(th, 0.0)
		await get_tree().process_frame
	_hinge.rotation.y = 0.0


## 门扇撞上门框：把手和手轮跟着晃几下（齿轮、销子都有间隙），一边晃一边衰减
func _start_rattle(strength: float) -> void:
	_rattling = true
	var t := 0.0
	while t < 0.5:
		t += get_process_delta_time()
		var env := exp(-t / 0.12) * strength
		_rattle = 0.03 * env * sin(TAU * 11.0 * t)
		_update_linkage()
		_wheel.rotation.z = TAU * WHEEL_TURNS + deg_to_rad(2.5) * env * sin(TAU * 7.0 * t + 0.6)
		await get_tree().process_frame
	_rattle = 0.0
	_update_linkage()
	_wheel.rotation.z = TAU * WHEEL_TURNS
	_rattling = false


# ---------------------------------------------------------------------------- 手轮
## 两只手倒着一把一把拧到 target。closing 时最后几把把手骑在楔块上：
## 每把转得少、转得慢，换手时手轮被顶回来一点；拧到底咬死（latched）
func _crank_to(target: float, closing: bool) -> void:
	var full := TAU * WHEEL_TURNS
	var dir := signf(target - _wheel.rotation.z)
	while absf(target - _wheel.rotation.z) > 1e-4:
		var effort := _load()
		var remain := absf(target - _wheel.rotation.z)
		var stroke := deg_to_rad(lerpf(randf_range(105.0, 125.0), randf_range(55.0, 65.0), effort))
		var dur := lerpf(randf_range(0.29, 0.33), randf_range(0.5, 0.6), effort)
		var last := remain <= stroke * 1.25
		if last:
			stroke = remain
			dur *= clampf(remain / deg_to_rad(110.0), 0.45, 1.0)
		grip = _wheel.rotation.z
		if closing and last:
			# 最后一把：越拧越吃力、越拧越慢，快到头时再使一把劲，带着速度“咔”地压死在楔块上，手轮被弹回来一点
			await _turn_seat(dir * stroke, dur * 1.35)
			_wheel.rotation.z = target
			unlatch = 0.0
			sound.emit(&"latched", 1.0)
			_shake(0.18)
			await _settle_wheel(target, -dir * deg_to_rad(5.0))
			return
		await _turn(dir * stroke, dur, 1.0)
		if absf(target - _wheel.rotation.z) <= 1e-4:
			break
		# 换手：停一下；把手压着楔块时手轮被顶回来一点，下一把先把它拧回去
		grip = _wheel.rotation.z
		var back := deg_to_rad(2.5) * _load() * (1.0 if closing else 0.4)
		await _turn(-dir * back, randf_range(0.07, 0.1) + 0.06 * _load(), 1.0)
		await _wait(randf_range(0.03, 0.06))
	_wheel.rotation.z = target
	unlatch = clampf(target / full, 0.0, 1.0)


## 手轮转过 delta：shape > 1 时起步慢后段快（越拧越顺），< 1 时起步猛后段收（掰开一松）
func _turn(delta: float, dur: float, shape: float) -> void:
	var start := _wheel.rotation.z
	var full := TAU * WHEEL_TURNS
	var t := 0.0
	while t < dur:
		t = minf(t + get_process_delta_time(), dur)
		var u := t / dur
		var p := smoothstep(0.0, 1.0, pow(u, shape)) if shape >= 1.0 else 1.0 - pow(1.0 - smoothstep(0.0, 1.0, u), 1.0 / shape)
		_wheel.rotation.z = start + delta * p
		unlatch = clampf(_wheel.rotation.z / full, 0.0, 1.0)
		await get_tree().process_frame


## 拧紧的最后一把：起手快，把手骑上楔块越来越慢（只剩三成速度），最后再使一把劲，带着速度撞到底（不减速）。
## 速度曲线积分成进度，查表
func _turn_seat(delta: float, dur: float) -> void:
	const N := 64
	var cum: Array[float] = [0.0]
	for i in N:
		var u := (i + 0.5) / N
		var v := smoothstep(0.0, 0.15, u) * (1.0 - 0.7 * smoothstep(0.15, 0.75, u) + 0.9 * smoothstep(0.75, 1.0, u))
		cum.append(cum[-1] + v)
	var start := _wheel.rotation.z
	var full := TAU * WHEEL_TURNS
	var t := 0.0
	while t < dur:
		t = minf(t + get_process_delta_time(), dur)
		var x := t / dur * N
		var i := mini(int(x), N - 1)
		var p := lerpf(cum[i], cum[i + 1], x - i) / cum[N]
		_wheel.rotation.z = start + delta * p
		unlatch = clampf(_wheel.rotation.z / full, 0.0, 1.0)
		await get_tree().process_frame


## 咬死以后手轮被弹回来一点又停住
func _settle_wheel(rest: float, kick: float) -> void:
	var t := 0.0
	while t < 0.35:
		t += get_process_delta_time()
		_wheel.rotation.z = rest + kick * exp(-t / 0.06) * sin(minf(t / 0.05, 1.0) * PI * 0.5)
		_hinge.rotation.y = -deg_to_rad(SEAT_DEG) * smoothstep(0.0, 0.2, t)
		await get_tree().process_frame
	_wheel.rotation.z = rest
	_hinge.rotation.y = -deg_to_rad(SEAT_DEG)


## 把手骑在楔块上有多吃劲（0 = 离开楔块，1 = 压死）
func _load() -> float:
	return smoothstep(WEDGE_ZONE, 0.0, unlatch)


func _swing_to(target: float, dur: float) -> void:
	var start := _hinge.rotation.y
	var t := 0.0
	while t < dur:
		t = minf(t + get_process_delta_time(), dur)
		_hinge.rotation.y = lerpf(start, target, 1.0 - pow(1.0 - t / dur, 3.0))
		await get_tree().process_frame


func _wait(secs: float) -> void:
	await get_tree().create_timer(secs, false).timeout


func _finish() -> void:
	busy = false
	hands = false
	is_open = not is_open
	state_changed.emit(is_open)


## 手轮转过的角度（弧度）、门扇开的角度（弧度），音效按它们的变化快慢出声
func wheel_angle() -> float:
	return _wheel.rotation.z if _wheel else 0.0


func hinge_angle() -> float:
	return _hinge.rotation.y if _hinge else 0.0


## 把手骑在楔块上的吃劲程度（音效：把手在楔块上刮）
func wedge_load() -> float:
	return _load()


## 手握手轮的地方（世界坐标）：hand 0 左手、1 右手；aft = 人站在生活舱那边，握门扇背面的手轮。
## 人面对手轮时左手在 10 点钟、右手在 2 点钟，握住以后跟着手轮转过 held（弧度，一般就是 手轮角度 - grip）。
## 返回 [握点, 半径方向（朝外）, 手轮面朝人的方向]
func grip_point(hand: int, aft: bool, held: float) -> Array:
	var r := 0.12 if aft else 0.15
	var z := 0.126 if aft else -0.094          # 轮缘所在的平面（转轴局部 z，-z 朝控制舱）
	# 从控制舱这面看过去转轴局部 +X 在人的左手边，从生活舱那面看在右手边
	var base := deg_to_rad(30.0 if (hand == 0) != aft else 150.0)
	var a := base + held
	var frame := _hinge.global_transform * Transform3D(Basis.from_euler(Vector3(_wheel.rotation.x, _wheel.rotation.y, 0.0)),
		_wheel.position)
	var radial := Vector3(cos(a), sin(a), 0.0)
	return [frame * (radial * r + Vector3(0, 0, z)), (frame.basis * radial).normalized(),
		(frame.basis * Vector3(0, 0, 1.0 if aft else -1.0)).normalized()]


## 手轮中心（世界坐标），门的声音从这里出来
func wheel_position() -> Vector3:
	return _wheel.global_position if _wheel else global_position


func _shake(strength: float) -> void:
	var crew := get_tree().get_first_node_in_group("crew")
	if crew and crew.has_method("add_shake"):
		crew.add_shake(strength)
