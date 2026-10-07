extends Node3D
## 中间隔壁上的水密门：开门先转手轮（松开压紧把手），再把门扇推开；关门反过来，最后哐的一声压紧。
## 门扇（Door_Leaf_*）和手轮（Door_Wheel_*）在舱内模型里是单独的网格，这里把它们挂到
## 门轴（Door_Hinge）、手轮轴（Door_WheelAxis）上转。门往控制舱一侧开，门轴在左舷。

signal state_changed(open: bool)

const OPEN_DEG := 110.0
const WHEEL_TURNS := 1.25
const WHEEL_TIME := 0.9
const SWING_TIME := 1.7

var is_open := false
var busy := false
## 0 = 关紧，1 = 全开（走动范围按它决定门洞能不能过）
var openness := 0.0

var _hinge: Node3D
var _wheel: Node3D
var _tween: Tween


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
	if DebugArgs.get_arg("door") == "open":
		is_open = true
		openness = 1.0
		_hinge.rotation.y = deg_to_rad(OPEN_DEG)
		_wheel.rotation.z = TAU * WHEEL_TURNS


## 在挂点同一位置建一个空节点当转轴
func _pivot(nm: String, anchor: Node3D) -> Node3D:
	var p := Node3D.new()
	p.name = nm
	anchor.get_parent().add_child(p)
	p.transform = anchor.transform
	return p


func toggle() -> void:
	if busy or _hinge == null:
		return
	busy = true
	if _tween:
		_tween.kill()
	_tween = create_tween()
	if not is_open:
		# 手轮逆时针转一圈多，压紧把手松开；门扇慢慢荡开
		_tween.tween_property(_wheel, "rotation:z", TAU * WHEEL_TURNS, WHEEL_TIME) \
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
		_tween.tween_property(_wheel, "rotation:z", 0.0, WHEEL_TIME) \
			.set_trans(Tween.TRANS_SINE).set_ease(Tween.EASE_IN_OUT)
	_tween.tween_callback(_finish)


func _finish() -> void:
	busy = false
	is_open = not is_open
	state_changed.emit(is_open)


func _shake(strength: float) -> void:
	var crew := get_tree().get_first_node_in_group("crew")
	if crew and crew.has_method("add_shake"):
		crew.add_shake(strength)
