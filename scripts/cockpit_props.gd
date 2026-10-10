extends Node3D
## 把 Poly Haven 的道具摆到驾驶舱模型里预留的挂点（Anchor_*）上，并在 CabinLight_* 处加舱内灯光。
## 道具都按真实尺寸摆放（scale 1），只有神龛里的油灯缩小了。

const MODEL := "res://assets/third_party/polyhaven/models/%s/%s_2k.gltf"
const FLICKER := preload("res://scripts/flicker_light.gd")
const DECAL_DIR := "res://assets/textures/decals/"

## 贴花：挂点名 Decal_<种类>_NN（尺寸就是挂点的缩放，见 cockpit.py 的 decal()）-> 贴图、
## 有没有 ORM 图（改粗糙度：湿的、油的、磨亮的）、浓淡、albedo_mix（0 = 只改粗糙度不改颜色）
const DECALS := {
	"Ring": {"tex": "ring", "alpha": 0.8},
	"Burn": {"tex": "burn"},
	"Tape": {"tex": "tape", "alpha": 0.85},
	"Polish": {"tex": "polish", "orm": true, "mix": 0.0},
	"Grease": {"tex": "grease", "orm": true, "alpha": 0.8},
	"Scuff": {"tex": "scuff", "alpha": 0.8},
	"BootL": {"tex": "boot_l", "orm": true, "alpha": 0.75},
	"BootR": {"tex": "boot_r", "orm": true, "alpha": 0.75},
	"Puddle": {"tex": "puddle", "orm": true},
	"Hazard": {"tex": "hazard", "orm": true},
	"Rust": {"tex": "rust", "alpha": 0.85},
	"Streak": {"tex": "streak", "orm": true},
	"Hand": {"tex": "hand", "orm": true, "alpha": 0.85},
	"TextC03": {"tex": "text_c03"},
	"TextFire": {"tex": "text_fire"},
	"TextCool": {"tex": "text_cool"},
	"TextFireWater": {"tex": "text_firewater"},
	"TextReturn": {"tex": "text_return"},
	"TextAir": {"tex": "text_air", "alpha": 0.8},
}

## 漏水的水珠落到地板上（落点，舱内局部坐标），给音效用
signal drip_landed(pos: Vector3)

var _charm: Node3D
var _porthole_lights: Array[OmniLight3D] = []
var _caustic := FastNoiseLite.new()
var _swing := Vector2.ZERO  # 绕 X、绕 Z 的摆角
var _swing_v := Vector2.ZERO
var _last_vel := Vector3.ZERO
# 漏水：滴的节奏在这边掐（粒子只管画），这样落地的声音能和水花对上
var _drip: GPUParticles3D
var _drip_spot := Vector3.ZERO  # 落点
var _drip_fall := 0.6           # 从法兰底下落到地板要多久
var _drip_wait := 1.5           # 离下一滴还有多久
var _drip_land := -1.0          # 这一滴还有多久落地

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
	# 生活舱
	"Anchor_GalleyThermos": {"asset": "modified_thermos"},
	"Anchor_Notepads": {"asset": "office_notepads", "keep": ["office_notepads_yellow_pad"]},
	"Anchor_PocketWatch": {"asset": "pocket_watch"},
	"Anchor_BunkBook": {"asset": "binder_notebook", "keep": ["binder_notebook_closed"]},
	"Anchor_BunkSpectacles": {"asset": "round_spectacles"},
	"Anchor_Wrench": {"asset": "adjustable_wrench"},
	"Anchor_Compass": {"asset": "seadogs_compass"},
}

## 舱内灯光：挂点名前缀 -> 参数（挂点名以这个前缀开头的都用这套参数）
const LIGHTS := {
	# 顶灯：笼罩里的白炽灯泡，暖白，带阴影——舱里主要的光，故意只有三盏，中间留出暗区。
	# 舱里有一层薄薄的水汽，顶灯下面能看到光锥
	"CabinLight_Dome": {"color": Color(1.0, 0.8, 0.58), "energy": 1.5, "range": 3.4, "atten": 1.6,
		"shadow": true, "fog": 1.2},
	# 后隔壁上的灯
	"CabinLight_Aft": {"color": Color(1.0, 0.8, 0.58), "energy": 0.9, "range": 2.8, "atten": 1.6,
		"shadow": true, "fog": 0.8},
	# 工作台灯罩下的日光灯管：偏冷，照亮仪表板和桌面。灯管是一条线，用投影贴图把光斑拉成长条
	"CabinLight_Strip": {"spot": true, "color": Color(0.82, 0.95, 0.88), "energy": 0.9, "range": 1.7,
		"atten": 1.1, "angle": 70.0, "shadow": true, "strip": true},
	# 舱底的防水灯：昏黄，从格栅缝里往上漏，把格栅的影子投到柜门和天花板上
	"CabinLight_Bilge": {"color": Color(1.0, 0.48, 0.16), "energy": 0.3, "range": 1.9, "atten": 1.3,
		"shadow": true},
	# 红色夜灯
	"CabinLight_Night": {"color": Color(1.0, 0.12, 0.06), "energy": 0.3, "range": 2.2, "atten": 1.1,
		"shadow": false},
	# 主控台蛇管台灯：聚光，照亮面板
	"CabinSpot_Console": {"spot": true, "color": Color(1.0, 0.86, 0.66), "energy": 1.0, "range": 1.5,
		"atten": 1.0, "angle": 50.0, "shadow": true},
	# 生活舱：床头小灯（暖黄，只照亮铺位里那一小块）、厨房吊柜下的灯管
	"CabinLight_Bunk": {"color": Color(1.0, 0.7, 0.42), "energy": 0.45, "range": 1.3, "atten": 1.5,
		"shadow": true},
	"CabinLight_Galley": {"spot": true, "color": Color(0.85, 0.95, 0.88), "energy": 0.8, "range": 1.4,
		"atten": 1.1, "angle": 65.0, "shadow": true, "strip": true},
}
## 个别灯的额外设定：日光灯管老化，一根一直在闪；生活舱铺位上方那盏顶灯坏了，只剩一点点光
const LIGHT_OVERRIDES := {
	"CabinLight_Strip_R2": {"flicker": 0.6},
	"CabinLight_Dome_5": {"energy": 0.35, "flicker": 0.8},
	"CabinLight_Bunk_L0": {"energy": 0.3, "flicker": 0.15},
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
	_add_porthole_lights(sub)
	_add_decals(sub)
	_add_drip(sub)
	_add_steam(sub)
	_add_dust()
	_setup_net(sub)
	_setup_charm(sub)
	_bake_gi.call_deferred(sub)


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
		# 舱里二十几盏投影灯挤在一张阴影图集里，每盏分到的分辨率不高：偏移小了，曲面上全是规则的网点（阴影痤疮），
		# 被照亮的面大半被自己的阴影吃掉。图集的分格见 project.godot 的 atlas_quadrant_*_subdiv
		l.shadow_bias = 0.3
		l.shadow_normal_bias = 2.0
		l.light_volumetric_fog_energy = c.get("fog", 0.0)
		l.light_size = 0.03
		l.shadow_caster_mask = Submarine.CABIN_SHADOW_CASTERS
		if c.get("strip", false):
			l.light_projector = _strip_projector()
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
		l.shadow_bias = 0.3
		l.shadow_normal_bias = 2.0
		l.shadow_caster_mask = Submarine.CABIN_SHADOW_CASTERS
		l.position = Vector3(0, 0.05, 0)
		l.light_volumetric_fog_energy = 0.0
		lamp_anchor.add_child(l)


## 日光灯管的投影贴图：沿灯管方向（灯的局部 Y）是一长条均匀的光，两头稍微补亮（抵消点光源的距离衰减），
## 横向慢慢暗下去。所有灯管共用一张。
var _strip_tex: ImageTexture


func _strip_projector() -> ImageTexture:
	if _strip_tex:
		return _strip_tex
	var w := 64
	var h := 128
	var img := Image.create(w, h, false, Image.FORMAT_RGBA8)
	for y in h:
		for x in w:
			var u := (float(x) / (w - 1)) * 2.0 - 1.0  # 横向
			var v := (float(y) / (h - 1)) * 2.0 - 1.0  # 沿灯管
			var along := (1.0 - smoothstep(0.55, 0.95, absf(v))) * (1.0 + 0.6 * v * v)
			var across := 1.0 - smoothstep(0.2, 1.0, absf(u))
			var k := clampf(along * across, 0.0, 1.0)
			img.set_pixel(x, y, Color(k, k, k, 1.0))
	img.generate_mipmaps()
	_strip_tex = ImageTexture.create_from_image(img)
	return _strip_tex


## 舷窗透进来的冷光：探照灯打在外面的水里，散射回来一点青色的光，随水波慢慢起伏。探照灯关了就只剩一点点。
func _add_porthole_lights(sub: Node) -> void:
	_caustic.frequency = 0.6
	for n in ["Anchor_Lean_L", "Anchor_Lean_R"]:
		var a := sub.find_child(n, true, false) as Node3D
		if a == null:
			continue
		var l := OmniLight3D.new()
		l.name = "SeaGlow"
		l.position = Vector3(0, 0, 0.12)
		l.light_color = Color(0.3, 0.62, 0.72)
		l.omni_range = 1.7
		l.omni_attenuation = 1.4
		l.light_volumetric_fog_energy = 0.6
		l.shadow_enabled = false
		a.add_child(l)
		_porthole_lights.append(l)


func _process(delta: float) -> void:
	_update_drip(delta)
	if _porthole_lights.is_empty():
		return
	var lit: bool = owner.get("lights_on")
	var t := Time.get_ticks_msec() / 1000.0
	for i in _porthole_lights.size():
		var base := 0.22 if lit else 0.04
		_porthole_lights[i].light_energy = base * (1.0 + 0.3 * _caustic.get_noise_2d(t * 0.8, i * 50.0))


## 每隔两三秒滴一滴，算好落地的时刻
func _update_drip(delta: float) -> void:
	if _drip == null:
		return
	_drip_wait -= delta
	if _drip_wait <= 0.0:
		_drip_wait = randf_range(2.0, 3.6)
		_drip.restart()
		_drip_land = _drip_fall
	if _drip_land >= 0.0:
		_drip_land -= delta
		if _drip_land < 0.0:
			drip_landed.emit(_drip_spot)


func _add_decals(sub: Node) -> void:
	var cache := {}
	for a: Node3D in sub.find_children("Decal_*", "Node3D", true, false):
		var kind := String(a.name).split("_")[1]
		if not DECALS.has(kind):
			push_warning("未知贴花 " + a.name)
			continue
		var c: Dictionary = DECALS[kind]
		var d := Decal.new()
		d.size = Vector3.ONE  # 尺寸由挂点的缩放决定
		if not cache.has(c.tex):
			cache[c.tex] = load(DECAL_DIR + c.tex + ".png")
		d.texture_albedo = cache[c.tex]
		if c.get("orm", false):
			var orm: String = c.tex + "_orm"
			if not cache.has(orm):
				cache[orm] = load(DECAL_DIR + orm + ".png")
			d.texture_orm = cache[orm]
		d.albedo_mix = c.get("mix", 1.0)
		d.modulate = Color(1, 1, 1, c.get("alpha", 1.0))
		d.upper_fade = 0.15
		d.lower_fade = 0.15
		d.normal_fade = 0.35
		d.distance_fade_enabled = true
		d.distance_fade_begin = 8.0
		d.distance_fade_length = 2.0
		a.add_child(d)


## 冷却水管法兰漏水：每隔两三秒滴一滴，落到地上溅开。
func _add_drip(sub: Node) -> void:
	var a := sub.find_child("Anchor_Drip", true, false) as Node3D
	if a == null:
		return
	var water := StandardMaterial3D.new()
	water.albedo_color = Color(0.02, 0.025, 0.025)
	water.roughness = 0.02
	water.metallic_specular = 0.9

	var drop_mesh := SphereMesh.new()
	drop_mesh.radius = 0.0032
	drop_mesh.height = 0.011
	drop_mesh.radial_segments = 8
	drop_mesh.rings = 4
	drop_mesh.material = water

	var splash := GPUParticles3D.new()
	splash.name = "Splash"
	splash.amount = 24
	splash.lifetime = 0.35
	splash.emitting = false
	splash.local_coords = true
	var spm := ParticleProcessMaterial.new()
	spm.direction = Vector3.UP
	spm.spread = 55.0
	spm.initial_velocity_min = 0.35
	spm.initial_velocity_max = 0.8
	spm.gravity = Vector3(0, -9.8, 0)
	spm.scale_min = 0.3
	spm.scale_max = 0.6
	splash.process_material = spm
	splash.draw_pass_1 = drop_mesh

	var drip := GPUParticles3D.new()
	drip.name = "Drip"
	drip.amount = 1
	drip.lifetime = 2.0
	drip.one_shot = true
	drip.emitting = false
	drip.local_coords = true
	drip.collision_base_size = 0.004
	var pm := ParticleProcessMaterial.new()
	pm.gravity = Vector3(0, -9.8, 0)
	pm.initial_velocity_min = 0.0
	pm.initial_velocity_max = 0.0
	pm.collision_mode = ParticleProcessMaterial.COLLISION_HIDE_ON_CONTACT
	pm.sub_emitter_mode = ParticleProcessMaterial.SUB_EMITTER_AT_COLLISION
	pm.sub_emitter_amount_at_collision = 6
	drip.process_material = pm
	drip.draw_pass_1 = drop_mesh
	drip.visibility_aabb = AABB(Vector3(-0.3, -2.2, -0.3), Vector3(0.6, 2.4, 0.6))
	a.add_child(drip)
	_drip = drip
	var p := to_local(a.global_position)  # Props 就在 Body 的原点上
	_drip_spot = Vector3(p.x, -0.9, p.z)
	_drip_fall = sqrt(2.0 * (p.y + 0.9) / 9.8)
	drip.add_child(splash)
	drip.sub_emitter = drip.get_path_to(splash)
	splash.visibility_aabb = AABB(Vector3(-0.5, -2.2, -0.5), Vector3(1.0, 2.6, 1.0))

	# 地板：粒子碰到就消失（溅起的水花从这里冒出来）
	var floor_box := GPUParticlesCollisionBox3D.new()
	floor_box.name = "DeckCollision"
	floor_box.size = Vector3(2.4, 0.2, 6.0)
	floor_box.position = Vector3(0, -0.9 - 0.1, 0)
	add_child(floor_box)  # Props 就在 Body 的原点上


## 圆形软边的小贴图（浮尘、热气共用），粒子用广告牌画
func _soft_dot() -> GradientTexture2D:
	var g := Gradient.new()
	g.set_color(0, Color(1, 1, 1, 1))
	g.set_color(1, Color(1, 1, 1, 0))
	var t := GradientTexture2D.new()
	t.gradient = g
	t.fill = GradientTexture2D.FILL_RADIAL
	t.fill_from = Vector2(0.5, 0.5)
	t.fill_to = Vector2(1.0, 0.5)
	t.width = 64
	t.height = 64
	return t


## 受光的粒子材质：只有被灯照到的地方才看得见（暗处的浮尘、热气本来就看不见）
func _lit_particle_material(alpha_tex: Texture2D, color: Color) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.billboard_mode = BaseMaterial3D.BILLBOARD_PARTICLES
	m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	m.albedo_texture = alpha_tex
	m.albedo_color = color
	m.vertex_color_use_as_albedo = true
	m.roughness = 1.0
	m.specular_mode = BaseMaterial3D.SPECULAR_DISABLED
	m.cull_mode = BaseMaterial3D.CULL_DISABLED
	return m


## 舱里的浮尘：控制舱、生活舱各一团，慢慢飘。只在顶灯、台灯的光里看得见，暗处就没有
func _add_dust() -> void:
	var dot := _soft_dot()
	var mesh := QuadMesh.new()
	mesh.size = Vector2(0.0035, 0.0035)
	mesh.material = _lit_particle_material(dot, Color(0.95, 0.9, 0.82, 0.55))
	# 舱内局部坐标（Godot）：-Z 朝艏。控制舱 z∈[-1.9, 2.6]，生活舱 z∈[2.6, 6.4]，地板 y=-0.9
	for part in [[Vector3(0, 0.2, 0.35), Vector3(0.95, 0.95, 2.25)], [Vector3(0, 0.2, 4.5), Vector3(0.95, 0.95, 1.9)]]:
		var p := GPUParticles3D.new()
		p.name = "Dust"
		p.amount = 500
		p.lifetime = 14.0
		p.preprocess = 14.0
		p.randomness = 0.5
		p.local_coords = true
		p.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		p.position = part[0]
		p.visibility_aabb = AABB(-part[1] - Vector3.ONE * 0.2, part[1] * 2.0 + Vector3.ONE * 0.4)
		var pm := ParticleProcessMaterial.new()
		pm.emission_shape = ParticleProcessMaterial.EMISSION_SHAPE_BOX
		pm.emission_box_extents = part[1]
		pm.gravity = Vector3(0, -0.003, 0)
		pm.initial_velocity_min = 0.0
		pm.initial_velocity_max = 0.01
		pm.spread = 180.0
		pm.turbulence_enabled = true
		pm.turbulence_noise_scale = 1.5
		pm.turbulence_noise_speed_random = 0.3
		pm.turbulence_influence_min = 0.01
		pm.turbulence_influence_max = 0.03
		pm.scale_min = 0.5
		pm.scale_max = 1.5
		# 淡入淡出，免得粒子凭空出现、消失
		var ramp := Gradient.new()
		ramp.set_color(0, Color(1, 1, 1, 0))
		ramp.set_color(1, Color(1, 1, 1, 0))
		ramp.add_point(0.15, Color(1, 1, 1, 1))
		ramp.add_point(0.85, Color(1, 1, 1, 1))
		var rt := GradientTexture1D.new()
		rt.gradient = ramp
		pm.color_ramp = rt
		p.process_material = pm
		p.draw_pass_1 = mesh
		add_child(p)


## 驾驶台上那缸热茶冒的热气：一缕一缕往上飘，散开，被台灯照着才看得见
func _add_steam(sub: Node) -> void:
	var a := sub.find_child("Anchor_Steam", true, false) as Node3D
	if a == null:
		return
	var mesh := QuadMesh.new()
	mesh.size = Vector2(0.03, 0.03)
	mesh.material = _lit_particle_material(_soft_dot(), Color(0.9, 0.9, 0.88, 0.07))
	var p := GPUParticles3D.new()
	p.name = "Steam"
	p.amount = 40
	p.lifetime = 2.6
	p.preprocess = 3.0
	p.randomness = 0.4
	p.local_coords = true
	p.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	p.visibility_aabb = AABB(Vector3(-0.25, -0.05, -0.25), Vector3(0.5, 0.6, 0.5))
	var pm := ParticleProcessMaterial.new()
	pm.emission_shape = ParticleProcessMaterial.EMISSION_SHAPE_SPHERE
	pm.emission_sphere_radius = 0.022
	pm.direction = Vector3.UP
	pm.spread = 12.0
	pm.initial_velocity_min = 0.03
	pm.initial_velocity_max = 0.06
	pm.gravity = Vector3(0, 0.025, 0)
	pm.damping_min = 0.01
	pm.damping_max = 0.03
	pm.turbulence_enabled = true
	pm.turbulence_noise_scale = 0.6
	pm.turbulence_noise_strength = 1.2
	pm.turbulence_influence_min = 0.04
	pm.turbulence_influence_max = 0.09
	pm.angle_min = -180.0
	pm.angle_max = 180.0
	var grow := Curve.new()
	grow.add_point(Vector2(0.0, 0.35))
	grow.add_point(Vector2(1.0, 2.6))
	var gt := CurveTexture.new()
	gt.curve = grow
	pm.scale_curve = gt
	var ramp := Gradient.new()
	ramp.set_color(0, Color(1, 1, 1, 0))
	ramp.set_color(1, Color(1, 1, 1, 0))
	ramp.add_point(0.2, Color(1, 1, 1, 1))
	ramp.add_point(0.6, Color(1, 1, 1, 0.5))
	var rt := GradientTexture1D.new()
	rt.gradient = ramp
	pm.color_ramp = rt
	p.process_material = pm
	p.draw_pass_1 = mesh
	a.add_child(p)


## 网兜的镂空图案要知道网兜中心在哪
func _setup_net(sub: Node) -> void:
	var c := sub.find_child("Net_Center", true, false) as Node3D
	var mesh := sub.find_child("Body_Net", true, false) as MeshInstance3D
	if c == null or mesh == null:
		return
	var m := mesh.get_active_material(0) as ShaderMaterial
	if m:
		m.set_shader_parameter("center", mesh.global_transform.affine_inverse() * c.global_position)


## 舱内的 VoxelGI（控制舱、生活舱各一个）：烘焙的只是体素化的几何体，灯光反弹是实时算的
## （闪烁的灯、开关灯都会跟着变）。艇的外部探照灯不参与（见 submarine.gd）。烘焙时水密门是关着的。
## 平时直接读烘焙文件；改了舱内模型要重新烘焙：Godot --path . -- --bake-gi（rebuild_models.sh 会自动做）。
## 没有烘焙文件时退回到开场现烘（要卡几秒）。
const GI_VOLUMES := {
	"CabinGI": "res://assets/gi/cabin_gi.res",
	"CabinGI_Aft": "res://assets/gi/cabin_gi_aft.res",
}


func _bake_gi(sub: Node) -> void:
	if not Story.is_target("deep_sea"):
		return
	var baking := DebugArgs.has("bake-gi")
	for nm: String in GI_VOLUMES:
		var gi := sub.find_child(nm, true, false) as VoxelGI
		var path: String = GI_VOLUMES[nm]
		if gi == null:
			continue
		if not baking and ResourceLoader.exists(path):
			gi.data = load(path)
			continue
		await get_tree().process_frame
		var t0 := Time.get_ticks_msec()
		gi.bake(sub.get_node("Body"))
		if gi.data == null:
			continue
		gi.data.interior = true
		gi.data.energy = 1.0
		gi.data.propagation = 0.75
		gi.data.normal_bias = 0.2
		print("VoxelGI %s baked in %d ms" % [nm, Time.get_ticks_msec() - t0])
		if baking:
			DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(path.get_base_dir()))
			var err := ResourceSaver.save(gi.data, path)
			print("saved ", path, " err=", err)
	if baking:
		get_tree().quit()


## 舷窗上方的平安符：符袋、玉扣、穗子挂成一串，当钟摆处理。
func _setup_charm(sub: Node) -> void:
	_charm = sub.find_child("Sway_Charm", true, false) as Node3D
	if _charm == null:
		return
	for n in ["Sway_Charm_Jade", "Sway_Charm_Tassel"]:
		var c := sub.find_child(n, true, false) as Node3D
		if c:
			c.reparent(_charm, true)
	Submarine.stop_casting(_charm)


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