extends Node3D
## 中间隔壁上的快速水密门：开门先转手轮——经过减速箱带动曲柄盘，六根连杆同时把门扇四周的压紧把手拨离楔块——
## 再把门扇推开；关门反过来，最后哐的一声，拧紧手轮把把手压回楔块上。
## 门扇（Door_Leaf_*）、手轮（Door_Wheel_*）、曲柄盘（Door_Crank_*）、把手（Door_Dog{k}_*）、连杆（Door_Rod_k）
## 在舱内模型里都是单独的网格，这里把它们挂到各自的转轴（Door_Hinge、Door_WheelAxis、Door_CrankAxis、
## Door_DogAxis_k）上转。门往控制舱一侧开，门轴在左舷。

signal state_changed(open: bool)
## 给音效的节点：unlatch（开门时把手离开楔块）、slam（关门时门扇撞上门框）、latched（关门最后拧紧）
signal sound(event: StringName)

const OPEN_DEG := 110.0
const WHEEL_TURNS := 1.25
const WHEEL_TIME := 0.9
const SWING_TIME := 1.7
## 手轮转 WHEEL_TURNS 圈，曲柄盘转这么多度
const CRANK_DEG := 50.0

var is_open := false
var busy := false
## 0 = 关紧，1 = 全开（走动范围按它决定门洞能不能过）
var openness := 0.0
## 0 = 把手压紧，1 = 把手全部拨开；跟着手轮一起变
var unlatch := 0.0:
	set(v):
		unlatch = v
		_update_linkage()

var _hinge: Node3D
var _wheel: Node3D
var _crank: Node3D
var _tween: Tween
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
	if DebugArgs.get_arg("door") == "open":
		is_open = true
		openness = 1.0
		_hinge.rotation.y = deg_to_rad(OPEN_DEG)
		_wheel.rotation.z = TAU * WHEEL_TURNS
		unlatch = 1.0


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
	var ang := deg_to_rad(CRANK_DEG) * unlatch
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
	if _tween:
		_tween.kill()
	_tween = create_tween()
	if not is_open:
		sound.emit(&"unlatch")
		# 手轮逆时针转一圈多，压紧把手松开；门扇慢慢荡开
		_tween.tween_property(_wheel, "rotation:z", TAU * WHEEL_TURNS, WHEEL_TIME) \
			.set_trans(Tween.TRANS_SINE).set_ease(Tween.EASE_IN_OUT)
		_tween.parallel().tween_property(self, "unlatch", 1.0, WHEEL_TIME) \
			.set_trans(Tween.TRANS_SINE).set_ease(Tween.EASE_IN_OUT)
		_tween.tween_callback(_shake.bind(0.08))
		_tween.tween_property(_hinge, "rotation:y", deg_to_rad(OPEN_DEG), SWING_TIME) \
			.set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
		_tween.parallel().tween_property(self, "openness", 1.0, SWING_TIME * 0.6)
	else:
		# 关门：门洞马上就不让过了，门扇甩回去哐地撞上门框，再把手轮拧紧
		openness = 0.0
		_tween.tween_property(_hinge, "rotation:y", 0.0, SWING_TIME * 0.8) \
			.set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_IN)
		_tween.tween_callback(_shake.bind(0.35))
		_tween.tween_callback(sound.emit.bind(&"slam"))
		_tween.tween_property(_wheel, "rotation:z", 0.0, WHEEL_TIME) \
			.set_trans(Tween.TRANS_SINE).set_ease(Tween.EASE_IN_OUT)
		_tween.parallel().tween_property(self, "unlatch", 0.0, WHEEL_TIME) \
			.set_trans(Tween.TRANS_SINE).set_ease(Tween.EASE_IN_OUT)
	_tween.tween_callback(_finish)


func _finish() -> void:
	busy = false
	is_open = not is_open
	if not is_open:
		sound.emit(&"latched")
	state_changed.emit(is_open)


## 手轮转过的角度（弧度）、门扇开的角度（弧度），音效按它们的变化快慢出声
func wheel_angle() -> float:
	return _wheel.rotation.z if _wheel else 0.0


func hinge_angle() -> float:
	return _hinge.rotation.y if _hinge else 0.0


## 手轮中心（世界坐标），门的声音从这里出来
func wheel_position() -> Vector3:
	return _wheel.global_position if _wheel else global_position


func _shake(strength: float) -> void:
	var crew := get_tree().get_first_node_in_group("crew")
	if crew and crew.has_method("add_shake"):
		crew.add_shake(strength)
