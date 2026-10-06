extends Node3D
## 把 Poly Haven 的道具摆到驾驶舱模型里预留的挂点（Anchor_*）上，并在 CabinLight_* 处加舱内灯光。
## 道具都按真实尺寸摆放（scale 1），只有神龛里的油灯缩小了。

const MODEL := "res://assets/third_party/polyhaven/models/%s/%s_2k.gltf"
const FLICKER := preload("res://scripts/flicker_light.gd")

var _charm: Node3D
var _swing := Vector2.ZERO  # 绕 X、绕 Z 的摆角
var _swing_v := Vector2.ZERO
var _last_vel := Vector3.ZERO

## 挂点 -> 素材、缩放、绕 Y 旋转（度）、只保留哪些节点（并把它们移到原点）、子节点额外旋转
const PROPS := {
	"Anchor_ShrineLamp": {"asset": "brass_diya_lantern", "scale": 0.45,
		"keep": ["brass_diya_lantern"], "lift": 0.027},
	"Anchor_Radio": {"asset": "vintage_radio_transceiver",
		"drop": ["vintage_radio_transceiver_antenna", "vintage_radio_transceiver_antenna_plug_a",
			"vintage_radio_transceiver_antenna_plug_b"]},
	"Anchor_PowerBox": {"asset": "power_box_01", "node_rot": {"power_box_01_door": Vector3(0, -112, 0)}},
	"Anchor_Scope": {"asset": "vintage_spacecraft_instrument", "lift": 0.135},
	"Anchor_GasMask": {"asset": "old_gas_mask"},
	"Anchor_Extinguisher": {"asset": "korean_fire_extinguisher_01", "scale": 0.85},
	"Anchor_Thermos": {"asset": "plastic_thermos"},
	"Anchor_Clipboard": {"asset": "clipboard"},
	"Anchor_Checklist": {"asset": "clipboard", "tilt": 90.0},
	"Anchor_Logbook": {"asset": "binder_notebook", "keep": ["binder_notebook_closed"]},
	"Anchor_Flashlight": {"asset": "signal_flashlight", "lay": true, "lift": 0.022},
	"Anchor_Multimeter": {"asset": "retro_multimeter"},
	"Anchor_Medical": {"asset": "medical_box"},
	"Anchor_Walkman": {"asset": "portable_cassette_player", "lay": true, "lift": 0.017},
	"Anchor_Spectacles": {"asset": "round_spectacles"},
	"Anchor_Watch": {"asset": "digital_wrist_watch"},
	"Anchor_Screwdriver": {"asset": "screwdriver", "lay": true, "lift": 0.0135},
	"Anchor_Pliers": {"asset": "pliers", "lay": true, "lift": 0.009},
	"Anchor_Tape": {"asset": "medical_tape"},
}

## 舱内灯光：挂点名前缀 -> 参数（挂点名以这个前缀开头的都用这套参数）
const LIGHTS := {
	# 顶灯：笼罩里的白炽灯泡，暖白，带阴影——舱里主要的光，故意只有三盏，中间留出暗区
	"CabinLight_Dome": {"color": Color(1.0, 0.8, 0.58), "energy": 1.5, "range": 3.4, "atten": 1.6,
		"shadow": true},
	# 后隔壁上的灯
	"CabinLight_Aft": {"color": Color(1.0, 0.8, 0.58), "energy": 0.9, "range": 2.8, "atten": 1.6,
		"shadow": true},
	# 工作台灯罩下的日光灯管：偏冷，只照亮下面那块仪表板
	"CabinLight_Strip": {"spot": true, "color": Color(0.82, 0.95, 0.88), "energy": 0.7, "range": 1.3,
		"atten": 1.4, "angle": 62.0, "shadow": true},
	# 红色夜灯
	"CabinLight_Night": {"color": Color(1.0, 0.12, 0.06), "energy": 0.3, "range": 2.2, "atten": 1.1,
		"shadow": false},
	# 主控台蛇管台灯：聚光，照亮面板
	"CabinSpot_Console": {"spot": true, "color": Color(1.0, 0.86, 0.66), "energy": 1.0, "range": 1.5,
		"atten": 1.0, "angle": 50.0, "shadow": true},
}
## 个别灯的额外设定：日光灯管老化，一根一直在闪
const LIGHT_OVERRIDES := {
	"CabinLight_Strip_R2": {"flicker": 0.6},
}


func _ready() -> void:
	var sub := owner
	for anchor_name: String in PROPS:
		var anchor := sub.find_child(anchor_name, true, false) as Node3D
		if anchor == null:
			push_warning("缺少挂点 " + anchor_name)
			continue
		var p: Dictionary = PROPS[anchor_name]
		var scene := load(MODEL % [p.asset, p.asset]) as PackedScene
		if scene == null:
			continue
		var inst := scene.instantiate() as Node3D
		inst.scale = Vector3.ONE * p.get("scale", 1.0)
		inst.rotation_degrees.y = p.get("rot", 0.0)
		inst.position.y = p.get("lift", 0.0)
		if p.get("lay", false):
			# 躺在地上：模型本来是立着的，绕 X 转 90°
			inst.rotation_degrees.x = -90.0
		if p.has("tilt"):
			inst.rotation_degrees.x = p.tilt
		if p.has("keep"):
			_keep_only(inst, p.keep)
		if p.has("drop"):
			for n: String in p.drop:
				var d := inst.find_child(n, true, false)
				if d:
					d.queue_free()
		if p.has("node_rot"):
			for n: String in p.node_rot:
				var c := inst.find_child(n, true, false) as Node3D
				if c:
					c.rotation_degrees += p.node_rot[n]
		if p.get("no_shadow", false):
			# 灯具自己不投影，否则灯罩里的光源整个被挡住
			for g in inst.find_children("*", "GeometryInstance3D", true, false):
				(g as GeometryInstance3D).cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		anchor.add_child(inst)

	_add_lights(sub)
	_setup_charm(sub)


## 只保留名字在 keep 里的网格节点，并把它们挪到原点（Poly Haven 把几个变体并排摆在一个文件里）。
func _keep_only(root: Node, keep: Array) -> void:
	for n in root.find_children("*", "Node3D", true, false):
		if n == root:
			continue
		var nm := String(n.name)
		var kept := false
		for k: String in keep:
			if nm == k:
				kept = true
		if kept:
			(n as Node3D).position = Vector3.ZERO
		elif n is MeshInstance3D:
			# 不是要保留的：如果它也不是要保留节点的子孙，就删掉
			var anc := n.get_parent()
			var under_kept := false
			while anc and anc != root:
				if String(anc.name) in keep:
					under_kept = true
				anc = anc.get_parent()
			if not under_kept:
				n.queue_free()


func _add_lights(sub: Node) -> void:
	for anchor: Node3D in sub.find_children("Cabin*", "Node3D", true, false):
		var key := ""
		for k: String in LIGHTS:
			if String(anchor.name).begins_with(k):
				key = k
		if key.is_empty():
			continue
		var c: Dictionary = LIGHTS[key].merged(LIGHT_OVERRIDES.get(String(anchor.name), {}), true)
		var l: Light3D
		if c.get("spot", false):
			var s := SpotLight3D.new()
			s.spot_range = c.range
			s.spot_attenuation = c.atten
			s.spot_angle = c.angle
			s.spot_angle_attenuation = 0.6
			l = s
		else:
			var o := OmniLight3D.new()
			o.omni_range = c.range
			o.omni_attenuation = c.atten
			l = o
		l.name = "Light"
		l.light_color = c.color
		l.light_energy = c.energy
		l.shadow_enabled = c.shadow
		l.shadow_blur = 1.5
		l.light_volumetric_fog_energy = 0.0
		l.light_size = 0.03
		if c.has("flicker"):
			l.set_script(FLICKER)
			l.set("amount", c.flicker)
			l.set("speed", 14.0)
		anchor.add_child(l)

	# 本命灯：神龛里的油灯火光
	var lamp_anchor := sub.find_child("Anchor_ShrineLamp", true, false) as Node3D
	if lamp_anchor:
		var l := OmniLight3D.new()
		l.set_script(FLICKER)
		l.light_color = Color(1.0, 0.55, 0.22)
		l.light_energy = 0.45
		l.omni_range = 1.2
		l.omni_attenuation = 1.4
		l.shadow_enabled = true
		l.position = Vector3(0, 0.05, 0)
		l.light_volumetric_fog_energy = 0.0
		lamp_anchor.add_child(l)


## 舷窗上方的平安符：符袋、玉扣、穗子挂成一串，当钟摆处理。
func _setup_charm(sub: Node) -> void:
	_charm = sub.find_child("Sway_Charm", true, false) as Node3D
	if _charm == null:
		return
	for n in ["Sway_Charm_Jade", "Sway_Charm_Tassel"]:
		var c := sub.find_child(n, true, false) as Node3D
		if c:
			c.reparent(_charm, true)


func _physics_process(delta: float) -> void:
	if _charm == null:
		return
	var sub := owner as CharacterBody3D
	var acc := (sub.velocity - _last_vel) / maxf(delta, 1e-4)
	_last_vel = sub.velocity
	var parent := _charm.get_parent() as Node3D
	var inv := parent.global_basis.inverse()
	# 平衡位置：绳子顺着真实的重力方向（舱体晃的时候符不跟着歪）
	var g := (inv * Vector3.DOWN).normalized()
	var eq := Vector2(asin(clampf(-g.z, -1, 1)), asin(clampf(g.x, -1, 1)))
	# 潜艇加速时往反方向甩
	var la := inv * acc
	var push := Vector2(la.z, -la.x) * 0.05
	_swing_v += ((eq - _swing) * 30.0 - _swing_v * 0.9) * delta + push * delta * 30.0
	_swing_v += Vector2(randf() - 0.5, randf() - 0.5) * delta * 0.15
	_swing += _swing_v * delta
	_charm.basis = Basis.from_euler(Vector3(_swing.x, 0.0, _swing.y))