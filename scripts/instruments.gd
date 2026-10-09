extends Node
## 驾驶舱仪表：指针（带弹簧阻尼和抖动）、数码管、指示灯、报警灯牌、氧气流量计浮子；声呐屏见 sonar_display.gd。
## 指针对象由 Blender 生成：原点在转轴上，静止时指在刻度起点，绕局部 Y 轴顺时针转 sweep 度到满量程。

## 指针名 -> 满量程转过的角度
const GAUGES := {
	"Depth": 270.0, "Pressure": 270.0, "Heading": 360.0,
	"Volt": 90.0, "Amp": 90.0, "ThrL": 90.0, "ThrR": 90.0,
	"Ballast": 270.0, "Trim": 270.0, "Temp": 270.0, "Hum": 270.0,
	"O2": 90.0, "CO2": 90.0, "Hyd": 270.0, "Comp": 270.0, "O2Tank": 270.0,
	"BatV": 90.0, "BatA": 90.0, "Heading2": 360.0, "Speed": 270.0, "Ballast2": 270.0, "Signal": 90.0,
}
const SEG_FONT := preload("res://assets/fonts/DSEG7Classic-Bold.ttf")

## 报警灯牌（和 Blender 里 annunciator 的顺序一致）
enum Warn { O2_LOW, CO2_HIGH, LEAK, BATTERY, INSULATION, TOO_DEEP, HYDRAULIC, COMMS }

@onready var sub: Submarine = owner

var _needles := {}  # 名字 -> {node, basis, sweep, value, vel}
var _displays := {}  # 名字 -> Label3D
var _lamps: Array[StandardMaterial3D] = []
var _warns: Array[StandardMaterial3D] = []
var _warn_state: Array[int] = []  # 0 灭 1 亮 2 闪
var _floats := {}  # 名字 -> {node, base}
var _battery := 4.6
var _co2 := 0.55
var _dive_time := 0.0
var _log_km := 0.0


func _ready() -> void:
	for n in sub.find_children("Needle_*", "Node3D", true, false):
		var key := String(n.name).trim_prefix("Needle_")
		if GAUGES.has(key):
			_needles[key] = {"node": n, "basis": n.transform.basis, "sweep": GAUGES[key], "value": 0.0, "vel": 0.0}
	for name in ["Depth", "Alt", "Clock", "Log"]:
		_setup_display(name)
	for i in 8:
		var m := _own_material("Lamp_%d" % i)
		if m:
			_lamps.append(m)
	for i in 8:
		var m := _own_material("Warn_%d" % i)
		if m:
			_warns.append(m)
			_warn_state.append(0)
	for n in sub.find_children("Float_*", "Node3D", true, false):
		_floats[String(n.name)] = {"node": n, "base": n.position}
	var screen := sub.find_child("Screen_Sonar", true, false) as MeshInstance3D
	if screen:
		var sonar := SonarDisplay.new()
		sonar.name = "Sonar"
		sonar.setup(sub, screen, sub.find_child("Lamp_SonarTx", true, false) as MeshInstance3D)
		add_child(sonar)
	# 演示用：通信中断灯一直闪（以后由事件系统控制）
	set_warning(Warn.COMMS, 2)


## 打开/关闭某个报警灯：0 灭 1 常亮 2 闪烁
func set_warning(i: int, state: int) -> void:
	if i < _warn_state.size():
		_warn_state[i] = state


## 每个运行时要改的网格都复制一份自己的材质，免得互相影响。
func _own_material(node_name: String) -> StandardMaterial3D:
	var mi := sub.find_child(node_name, true, false) as MeshInstance3D
	if mi == null:
		return null
	var m := mi.get_active_material(0)
	if m is StandardMaterial3D:
		var d: StandardMaterial3D = m.duplicate()
		mi.set_surface_override_material(0, d)
		return d
	return null


## 数码管：DSEG 七段字体，后面垫一层暗暗的「8888」当没点亮的段，真数码管就是这样。
func _setup_display(name: String) -> void:
	var anchor := sub.find_child("Display_" + name, true, false) as Node3D
	if anchor == null:
		return
	var ghost := _seg_label(Color(0.35, 0.02, 0.01, 0.35))
	ghost.text = "8888.8" if name != "Clock" else "88:88:88"
	ghost.position.z = -0.0003
	anchor.add_child(ghost)
	var l := _seg_label(Color(3.2, 0.22, 0.1))
	anchor.add_child(l)
	_displays[name] = l


func _seg_label(c: Color) -> Label3D:
	var l := Label3D.new()
	l.font = SEG_FONT
	l.font_size = 64
	l.pixel_size = 0.00028
	l.modulate = c
	l.outline_size = 0
	l.shaded = false
	l.double_sided = false
	l.alpha_cut = Label3D.ALPHA_CUT_DISABLED
	l.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS
	return l


func _process(delta: float) -> void:
	var t := Time.get_ticks_msec() / 1000.0
	_dive_time += delta
	var depth := sub.depth()
	var thrust := absf(sub.thrust_input) + absf(sub.lift_input) * 0.6
	_battery = maxf(3.2, _battery - delta * (0.0004 + thrust * 0.002))
	_co2 = minf(3.0, _co2 + delta * 0.0008)

	_set_gauge("Depth", depth / 10000.0, delta)
	_set_gauge("Heading", sub.heading_deg() / 360.0, delta)
	_set_gauge("Pressure", (1.03 + sin(t * 0.1) * 0.01) / 2.0, delta)
	_set_gauge("Volt", (_battery * 25.0 - thrust * 6.0) / 150.0, delta)
	_set_gauge("Amp", (12.0 + thrust * 55.0) / 100.0, delta)
	var turn := sub.yaw_speed / sub.turn_max_deg
	_set_gauge("ThrL", absf(sub.thrust_input) * 0.8 + maxf(0.0, -turn) * 0.3, delta)
	_set_gauge("ThrR", absf(sub.thrust_input) * 0.8 + maxf(0.0, turn) * 0.3, delta)
	_set_gauge("Ballast", 0.62, delta)
	_set_gauge("Trim", 0.5 + sin(t * 0.21) * 0.02, delta)
	_set_gauge("Temp", 11.0 / 50.0, delta)
	_set_gauge("Hum", (82.0 + sin(t * 0.05) * 2.0) / 100.0, delta)
	_set_gauge("O2", (20.6 + sin(t * 0.37) * 0.15) / 25.0, delta)
	_set_gauge("CO2", _co2 / 5.0, delta)
	_set_gauge("Hyd", 17.5 / 25.0 + thrust * 0.02, delta)
	_set_gauge("Comp", 0.55, delta)
	_set_gauge("O2Tank", 13.8 / 25.0, delta)
	_set_gauge("BatV", (_battery * 25.0 - thrust * 6.0) / 150.0, delta)
	_set_gauge("BatA", (18.0 + thrust * 95.0) / 200.0, delta)
	_set_gauge("Heading2", sub.heading_deg() / 360.0, delta)
	_set_gauge("Speed", sub.speed() / 2.06, delta)  # 满量程 4 节
	_set_gauge("Ballast2", 0.41, delta)
	_set_gauge("Signal", 0.15 + absf(sin(t * 0.13)) * 0.1 + randf() * 0.05, delta)
	_log_km += sub.speed() * delta / 1000.0

	if _displays.has("Depth"):
		_displays.Depth.text = "%6.1f" % depth
	if _displays.has("Alt"):
		var alt := _altitude()
		_displays.Alt.text = "%5.1f" % alt if alt >= 0.0 else "  ---"
	if _displays.has("Log"):
		_displays.Log.text = "%6.2f" % (_log_km + 12.4)
	if _displays.has("Clock"):
		var s := int(_dive_time)
		_displays.Clock.text = "%02d:%02d:%02d" % [s / 3600, (s / 60) % 60, s % 60]

	# 指示灯：0 号红灯慢闪，6 号偶尔跳一下，其余常亮
	for i in _lamps.size():
		var on := true
		if i == 0:
			on = fmod(t, 1.6) < 0.8
		elif i == 6:
			on = fmod(t * 0.37 + 0.3, 1.0) > 0.15
		_lamps[i].emission_energy_multiplier = 3.0 if on else 0.05

	for i in _warns.size():
		var lit := _warn_state[i] == 1 or (_warn_state[i] == 2 and fmod(t, 1.0) < 0.55)
		_warns[i].emission_energy_multiplier = 2.2 if lit else 0.02

	# 流量计浮子：在刻度 4 附近轻轻上下抖
	for k: String in _floats:
		var f: Dictionary = _floats[k]
		var n: Node3D = f.node
		var h := 0.044 + sin(t * 2.3 + k.length()) * 0.0015 + (randf() - 0.5) * 0.0006
		n.position = f.base + n.basis.y.normalized() * h



func _set_gauge(key: String, target: float, delta: float) -> void:
	if not _needles.has(key):
		return
	var g: Dictionary = _needles[key]
	target = clampf(target, 0.0, 1.0)
	var jitter := (randf() - 0.5) * 0.004
	# 弹簧阻尼，让指针有一点惯性
	var acc: float = (target + jitter - g.value) * 40.0 - g.vel * 9.0
	g.vel += acc * delta
	g.value += g.vel * delta
	var node: Node3D = g.node
	node.transform.basis = g.basis * Basis(Vector3.UP, deg_to_rad(-g.sweep * g.value))


## 离底高度：往正下方打一条射线。
func _altitude() -> float:
	var space := sub.get_world_3d().direct_space_state
	var origin := sub.global_position + Vector3(0, -1.2, 0)
	var q := PhysicsRayQueryParameters3D.create(origin, origin + Vector3.DOWN * 99.0)
	q.exclude = [sub.get_rid()]
	var hit := space.intersect_ray(q)
	return origin.distance_to(hit.position) if hit else -1.0
