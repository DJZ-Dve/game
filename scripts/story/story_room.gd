class_name StoryRoom
extends Node3D
## 岸上的房间场景（宿舍、办事处）的公共部分。房间模型（gen_dorm.py / gen_office.py 导出的 glb）里预留了挂点，这里照着摆：
##   Walk_* / WalkDoor_*   能站的矩形（缩放就是长宽）；WalkDoor_* 只在门开着时能走
##   Spawn                 开场站哪、朝哪
##   Seat_* / SeatStand_*  坐的地方（眼睛的位置、朝向）/ 站起来站哪；自动在椅子上放一个「坐下」的交互
##   Use_*                 能按 E 的东西，参数见子类的 uses()
##   Anchor_*              摆 Poly Haven 道具，见 props()
##   Light_*               灯，见 lights()
##   Decal_*               贴花，见 DECALS（和艇里的共用一批贴图）
##   Paper_*               纸（换成 PaperDoc 的贴图），见 papers()
##   Spin_*                转的东西（吊扇）
##   Tube_*                日光灯管（亮度跟着灯走）
##   Door_Leaf / Door_Leaf_*  门扇和门上的零件（零件挂到门扇下面一起转）
##   Mirror_Glass          镜子（mirror.gd）
## 子类覆盖 props() / lights() / uses() / papers()，再写剧情。

const MODEL := "res://assets/third_party/polyhaven/models/%s/%s_2k.gltf"
const DECAL_DIR := "res://assets/textures/decals/"
const FLICKER := preload("res://scripts/flicker_light.gd")
const BODY := preload("res://scripts/crew_body.gd")
const MIRROR := preload("res://scripts/story/mirror.gd")
const RAIN := preload("res://assets/shaders/rain_streaks.gdshader")
const FILM := preload("res://assets/shaders/film_post.gdshader")

## 贴花：种类 -> 贴图、有没有 ORM、浓淡、albedo_mix（同 cockpit_props.gd，多了几种岸上用的）
const DECALS := {
	"Ring": {"tex": "ring", "alpha": 0.8},
	"Burn": {"tex": "burn"},
	"Grime": {"tex": "grease", "orm": true, "alpha": 0.7},
	"Scuff": {"tex": "scuff", "alpha": 0.7},
	"BootL": {"tex": "boot_l", "orm": true, "alpha": 0.8},
	"BootR": {"tex": "boot_r", "orm": true, "alpha": 0.8},
	"Puddle": {"tex": "puddle", "orm": true},
	"Rust": {"tex": "rust", "alpha": 0.85},
	"Streak": {"tex": "streak", "orm": true, "alpha": 0.9},
	"FloorWear": {"tex": "floor_wear", "orm": true, "alpha": 0.85},
	"FloorDull": {"tex": "floor_dull", "orm": true, "alpha": 1.0},
	"Damp": {"tex": "damp", "orm": true, "alpha": 0.8},
	"CeilStain": {"tex": "ceil_stain", "alpha": 0.85},
	"Mold": {"tex": "mold", "alpha": 0.8},
	"Hand": {"tex": "hand", "orm": true, "alpha": 0.85},
}

## 闪电（窗外）：strength 0~1。声音、灯闪跟着它
signal lightning(strength: float)

@export var room_name := "room"
## 烘焙好的 VoxelGI 数据（没有就开场现烘，要卡几秒）。--bake-gi 重新烘焙后退出
@export var gi_path := ""
## 层高（米）：墙上的流痕从这里往下垂
@export var ceiling_height := 3.0
## 房间的地面范围（房间局部坐标 x、z）：墙角积灰用
@export var floor_rect := Rect2(-2.0, -2.0, 4.0, 4.0)


func room_box() -> AABB:
	return AABB(Vector3(floor_rect.position.x, 0.0, floor_rect.position.y),
		Vector3(floor_rect.size.x, ceiling_height, floor_rect.size.y))

var walker: RoomWalker
var body: Node3D
var model: Node3D
var uses := {}          # 名字 -> Interactable
var seats := {}         # 名字 -> Seat 节点
var papers := {}        # 名字 -> PaperDoc
var lights_by_name := {}
var door_leaf: Node3D
var door_open := 0.0    # 0 关 → 1 开（门扇转过的比例）
var mirror: Node3D
var audio: RoomAudio

var _walk: Array[Rect2] = []
var _walk_door: Array[Rect2] = []
var _spins: Array[Node3D] = []
var _tubes := {}        # 灯光名 -> 灯管 MeshInstance3D
var _lightning: DirectionalLight3D
var _flash := 0.0
var _next_flash := 8.0
var _door_rest_y := 0.0
var lightmap := RoomLightmap.new(self)


func _ready() -> void:
	model = find_child("Model", false, false) as Node3D
	_collect_anchors()
	_add_props()
	_add_lights()
	_add_decals()
	_add_papers()
	_add_uses()
	_setup_shell()
	_add_rain()
	_add_player()
	_setup_lens()
	audio = RoomAudio.new()
	audio.name = "Audio"
	add_child(audio)
	setup_audio(audio)
	Story.ui.reader_opened.connect(func() -> void: audio.play("paper"))
	walker.seated_changed.connect(func(on: bool) -> void:
		if on:
			audio.play("chair_creak"))
	_setup_mirror()
	if DebugArgs.capturing():
		_setup_capture()
	_bake_gi.call_deferred()
	if DebugArgs.has("read"):
		# 调试：开场直接把这张纸拿起来看（检查排版）
		await get_tree().create_timer(0.3).timeout
		Story.ui.read([papers[DebugArgs.get_arg("read")].get_texture()])


# ----------------------------------------------------------------------------- 子类覆盖
func props() -> Dictionary:
	return {}


func lights() -> Dictionary:
	return {}


func use_config() -> Dictionary:
	return {}


## 窗外的雨（rain_streaks.gdshader）：{"min": 盒子一角, "max": 另一角（房间局部坐标，放在窗外，别伸进屋里）,
## "count": 多少滴, "wind": Vector2(x, z) 水平风速, 其余键原样给着色器（fall_speed、ambient、brightness……）}。空的就不下
func rain_config() -> Dictionary:
	return {}


## 坐着时对焦在哪（世界坐标，比如对面人的脸）：远处跟着虚一点（景深）。null 不开景深。子类覆盖
func focus_target() -> Variant:
	return null


## 镜头（_setup_lens）：{"auto_exposure": 自动曝光的 scale（0 不开）, "ae_min" / "ae_max": 最低 / 最高感光度（ISO，
## 默认 AE_MIN_SENSITIVITY / AE_MAX_SENSITIVITY）}。调色 LUT 挂在房间的 Environment 上。子类覆盖
func lens_config() -> Dictionary:
	return {}


func paper_config() -> Dictionary:
	return {}


## 循环音、有位置的音效（RoomAudio.loop / sources），子类覆盖
func setup_audio(_a: RoomAudio) -> void:
	pass


## 场景脚本放一次性的声音
func play(sfx: String) -> void:
	audio.play(sfx)

# ----------------------------------------------------------------------------- 挂点
func _collect_anchors() -> void:
	for n in model.find_children("Walk*", "Node3D", true, false):
		var r := _rect_of(n)
		if String(n.name).begins_with("WalkDoor_"):
			_walk_door.append(r)
		else:
			_walk.append(r)
	for n in model.find_children("Spin_*", "Node3D", true, false):
		_spins.append(n)
	door_leaf = model.find_child("Door_Leaf", true, false) as Node3D
	if door_leaf:
		_door_rest_y = door_leaf.rotation.y
		for part in model.find_children("Door_Leaf_*", "Node3D", true, false):
			part.reparent(door_leaf, true)


## Walk_* 挂点：Blender 里缩放就是长宽，导出后 Godot 的缩放是 (宽, 1, 深)
func _rect_of(n: Node3D) -> Rect2:
	var p := to_local(n.global_position)
	var s := n.global_basis.get_scale()
	return Rect2(p.x - s.x / 2, p.z - s.z / 2, s.x, s.z)


func walk_areas(with_door: bool) -> Array[Rect2]:
	var out: Array[Rect2] = _walk.duplicate()
	if with_door:
		out.append_array(_walk_door)
	return out


## 挂点在房间局部坐标里的位置（给声音定位用）
func pos_of(anchor_name: String) -> Vector3:
	var n := model.find_child(anchor_name, true, false) as Node3D
	return to_local(n.global_position) if n else Vector3.ZERO


func _add_player() -> void:
	walker = RoomWalker.new()
	walker.name = "Walker"
	walker.walk_areas = walk_areas(false)
	walker.cull_mask = 0xFFFFF & ~(1 << (PlanarMirror.HEAD_LAYER - 1))
	var sp := model.find_child("Spawn", true, false) as Node3D
	if sp:
		var p := to_local(sp.global_position)
		var f := -sp.global_basis.z
		walker.start = Vector2(p.x, p.z)
		walker.start_yaw = rad_to_deg(atan2(-f.x, -f.z))
	add_child(walker)
	walker.current = true
	body = Node3D.new()
	body.name = "CrewBody"
	body.set_script(BODY)
	body.set("camera_path", NodePath("../Walker"))
	add_child(body)


# ----------------------------------------------------------------------------- 道具
func _add_props() -> void:
	var cfg := props()
	for anchor_name: String in cfg:
		var anchor := model.find_child(anchor_name, true, false) as Node3D
		if anchor == null:
			push_warning("缺少挂点 " + anchor_name)
			continue
		var p: Dictionary = cfg[anchor_name]
		var inst := load(MODEL % [p.asset, p.asset]).instantiate() as Node3D
		inst.scale = Vector3.ONE * p.get("scale", 1.0)
		inst.rotation_degrees.y = p.get("rot", 0.0)
		inst.position.y = p.get("lift", 0.0)
		if p.has("keep"):
			_keep_only(inst, p.keep, p.get("center", false))
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
		if p.has("tint"):
			_tint(inst, p.tint)
		anchor.add_child(inst)


## 只留下 keep 里的几块（Poly Haven 常把几个变体并排摆在一个文件里）；center：把留下的挪回原点
func _keep_only(root: Node, keep: Array, center: bool) -> void:
	var kept: Array[Node3D] = []
	for n in root.find_children("*", "MeshInstance3D", true, false):
		if String(n.name) in keep:
			kept.append(n)
		else:
			n.queue_free()
	if center and not kept.is_empty():
		var c := Vector3.ZERO
		for n in kept:
			c += n.position
		c /= kept.size()
		for n in kept:
			n.position -= Vector3(c.x, 0.0, c.z)


## 道具染色（Poly Haven 的颜色对不上年代的，压一压）
func _tint(root: Node, c: Color) -> void:
	for m in root.find_children("*", "MeshInstance3D", true, false):
		var mi := m as MeshInstance3D
		for i in mi.mesh.get_surface_count():
			var mat := mi.get_active_material(i) as StandardMaterial3D
			if mat:
				mat = mat.duplicate()
				mat.albedo_color = mat.albedo_color * c
				mi.set_surface_override_material(i, mat)


# ----------------------------------------------------------------------------- 灯
## lights() 每一项：名字 -> 参数。名字是模型里 Light_* 挂点的前缀（灯挂在挂点下面，朝挂点的 -Z）；
## 带 "pos"（房间局部坐标）或 "at"（另一个挂点名，加 "offset"）的是不挂在挂点上、直接放在房间里的灯，节点就叫这个名字。
##   种类：默认点光；"spot": true 聚光（"angle"、"soft"）；"area": Vector2(宽, 高) 面光（AreaLight3D，朝自己的 -Z 发光，
##         "normalize"：总亮度按面积摊开，默认 true）
##   朝向："aim" 对准房间里的一点；"facing" 朝房间里的一个方向（"up"：面光的高那条边朝哪，日光灯管沿哪个方向）
##   "offset"：在挂点位置上再挪一点（房间坐标）；"range"、"atten"、"energy"、"color"、"size"、"blur"、"nbias"、
##   "specular"、"fog"、"shadow"、"flicker"（"flicker_speed"）
##   "with": 灯名  跟着那盏灯一起开关（日光灯管往天花板上照的那点光）
##   "flash": 倍数  只在窗外打闪电时亮（亮度 = 闪电亮度 × 倍数），平时灭着
##   "bake": "off"  不进光照贴图（假的补光：代替反弹光的，再烘一遍就重复了）
func _add_lights() -> void:
	var cfg := lights()
	for anchor: Node3D in model.find_children("Light_*", "Node3D", true, false):
		var nm := String(anchor.name)
		var key := ""
		for k: String in cfg:
			if nm.begins_with(k) and k.length() > key.length() and not _free_light(cfg[k]):
				key = k
		if key.is_empty():
			continue
		var l := _make_light(cfg[key])
		l.name = "Light"
		anchor.add_child(l)
		_place_light(l, cfg[key])
		lights_by_name[nm] = l
		var tube_name := nm.replace("Light_Tube_", "Tube_")
		if tube_name != nm:
			var tube := model.find_child(tube_name, true, false) as MeshInstance3D
			if tube:
				_tubes[nm] = tube
	for k: String in cfg:
		var c: Dictionary = cfg[k]
		if not _free_light(c):
			continue
		var l := _make_light(c)
		l.name = k
		add_child(l)
		l.position = c.pos if c.has("pos") else pos_of(c.at)
		_place_light(l, c)
		lights_by_name[k] = l
		if c.has("flash"):
			_flash_lights[l] = float(c.flash)
			l.visible = false
	for k: String in cfg:
		if cfg[k].has("with") and lights_by_name.has(k):
			_followers[k] = cfg[k].with


func _free_light(c: Dictionary) -> bool:
	return c.has("pos") or c.has("at")


func _make_light(c: Dictionary) -> Light3D:
	var l: Light3D
	if c.has("area"):
		var a := AreaLight3D.new()
		a.area_size = c.area
		a.area_range = c.range
		a.area_attenuation = c.get("atten", 1.0)
		a.area_normalize_energy = c.get("normalize", true)
		l = a
	elif c.get("spot", false):
		var s := SpotLight3D.new()
		s.spot_range = c.range
		s.spot_attenuation = c.get("atten", 1.0)
		s.spot_angle = c.angle
		s.spot_angle_attenuation = c.get("soft", 0.8)
		l = s
	else:
		var o := OmniLight3D.new()
		o.omni_range = c.range
		o.omni_attenuation = c.get("atten", 1.0)
		l = o
	l.light_color = c.color
	l.light_energy = c.energy
	l.shadow_enabled = c.get("shadow", true)
	l.shadow_blur = c.get("blur", 1.5)
	l.shadow_bias = 0.08 if not c.has("area") else 0.04
	l.shadow_normal_bias = c.get("nbias", 1.2)
	l.light_size = c.get("size", 0.05)
	l.light_volumetric_fog_energy = c.get("fog", 0.5)
	l.light_specular = c.get("specular", 0.5)
	if c.get("bake", "") == "off" or c.has("flash"):
		l.light_bake_mode = Light3D.BAKE_DISABLED
	l.set_meta("base_energy", c.energy)
	if c.has("flicker"):
		l.set_script(FLICKER)
		l.set("amount", c.flicker)
		l.set("speed", c.get("flicker_speed", 14.0))
	return l


## 挪位置、定朝向（灯已经在场景树里）
func _place_light(l: Light3D, c: Dictionary) -> void:
	if c.has("offset"):
		l.global_position += global_basis * (c.offset as Vector3)
	var dir := Vector3.ZERO
	if c.has("aim"):
		dir = to_global(c.aim) - l.global_position
	elif c.has("facing"):
		dir = global_basis * (c.facing as Vector3)
	elif c.has("area"):
		dir = global_basis * Vector3.DOWN
	if dir == Vector3.ZERO:
		return
	var up: Vector3 = global_basis * (c.get("up", Vector3.UP) as Vector3)
	if absf(dir.normalized().dot(up.normalized())) > 0.95:
		up = global_basis * Vector3.FORWARD
	l.look_at(l.global_position + dir, up)


var _followers := {}     # 灯名 -> 跟着开关的那盏灯的名字
var _flash_lights := {}  # 闪电时才亮的灯 -> 倍数


## 开灯、关灯（日光灯管、灯泡的发光跟着变）；level：亮到正常亮度的几成（日光灯启辉时那几下暗闪）
func set_light(nm: String, on: bool, level := 1.0) -> void:
	var l: Light3D = lights_by_name.get(nm)
	if l == null:
		return
	l.visible = on
	var e := float(l.get_meta("base_energy", l.light_energy)) * level
	l.light_energy = e
	if l.get_script() == FLICKER:
		l.set("_base", e)
	if _tubes.has(nm):
		_tube_glow(_tubes[nm], level if on else 0.0)
	for f: String in _followers:
		if _followers[f] == nm:
			set_light(f, on, level)
	lightmap.pick_variant()


func _tube_glow(tube: MeshInstance3D, k: float) -> void:
	var mat := tube.get_surface_override_material(0) as StandardMaterial3D
	if mat == null:
		mat = (tube.get_active_material(0) as StandardMaterial3D).duplicate()
		tube.set_surface_override_material(0, mat)
	mat.emission_energy_multiplier = 3.0 * k
	mat.albedo_color = Color(0.95, 0.97, 0.95) * lerpf(0.55, 1.0, k)


# ----------------------------------------------------------------------------- 贴花
func _add_decals() -> void:
	var cache := {}
	for a: Node3D in model.find_children("Decal_*", "Node3D", true, false):
		var kind := String(a.name).split("_")[1]
		if not DECALS.has(kind):
			push_warning("未知贴花 " + a.name)
			continue
		var c: Dictionary = DECALS[kind]
		var path: String = DECAL_DIR + c.tex + ".png"
		if not ResourceLoader.exists(path):
			continue
		var d := Decal.new()
		d.size = Vector3.ONE
		if not cache.has(c.tex):
			cache[c.tex] = load(path)
		d.texture_albedo = cache[c.tex]
		if c.get("orm", false) and ResourceLoader.exists(DECAL_DIR + c.tex + "_orm.png"):
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
		d.distance_fade_begin = 12.0
		d.distance_fade_length = 3.0
		a.add_child(d)


# ----------------------------------------------------------------------------- 纸
func _add_papers() -> void:
	var cfg := paper_config()
	for nm: String in cfg:
		var doc := make_doc(cfg[nm])
		papers[nm] = doc
		var mesh := model.find_child("Paper_" + nm, true, false) as MeshInstance3D
		if mesh:
			var mat := StandardMaterial3D.new()
			mat.albedo_texture = doc.display_texture()
			mat.roughness = 0.85
			mat.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC
			if doc.style == "lcd":
				mat.emission_enabled = true
				mat.emission_texture = doc.display_texture()
				mat.emission_energy_multiplier = 0.0
			else:
				# 纸透一点光（灯在纸背后时）
				mat.backlight_enabled = true
				mat.backlight = Color(0.25, 0.24, 0.2)
			doc.display_changed.connect(func() -> void:
				mat.albedo_texture = doc.display_texture()
				if doc.style == "lcd":
					mat.emission_texture = doc.display_texture())
			mesh.material_override = mat


func make_doc(c: Dictionary) -> PaperDoc:
	var doc := PaperDoc.new()
	for k: String in c:
		if k in ["stamps", "writing", "thumb", "circles"]:
			continue
		doc.set(k, c[k])
	add_child(doc)
	for s: Array in c.get("stamps", []):
		doc.add_stamp(s[0], s[1], s[2], s[3] if s.size() > 3 else "", s[4] if s.size() > 4 else 0.0)
	for w: Array in c.get("writing", []):
		doc.add_writing(w[0], w[1], w[2], w[3] if w.size() > 3 else "hand",
			w[4] if w.size() > 4 else Color(0.06, 0.07, 0.12), w[5] if w.size() > 5 else 0.0)
	for k: Array in c.get("circles", []):
		doc.add_circle(k[0], k[1], k[2] if k.size() > 2 else Color(0.72, 0.08, 0.07))
	return doc


# ----------------------------------------------------------------------------- 交互
func _add_uses() -> void:
	var cfg := use_config()
	for a: Node3D in model.find_children("Use_*", "Node3D", true, false):
		var nm := String(a.name).substr(4)
		var c: Dictionary = cfg.get(nm, {})
		if c.is_empty():
			continue
		var it := Interactable.new()
		it.name = "Use_" + nm
		it.prompt = c.get("prompt", "查看")
		it.reach = c.get("reach", 1.6)
		it.size = c.get("size", 0.12)
		it.lines = PackedStringArray(c.get("lines", []))
		it.lines_again = PackedStringArray(c.get("again", []))
		it.enabled = c.get("enabled", true)
		add_child(it)
		it.global_position = a.global_position
		uses[nm] = it
	# 椅子：坐的地方自动放一个「坐下」
	for a: Node3D in model.find_children("Seat_*", "Node3D", true, false):
		var nm := String(a.name).substr(5)
		var seat := Marker3D.new()
		seat.name = "Seat_" + nm
		add_child(seat)
		seat.global_transform = a.global_transform
		var st := model.find_child("SeatStand_" + nm, true, false) as Node3D
		if st:
			var m := Marker3D.new()
			m.name = "Stand"
			seat.add_child(m)
			m.global_position = st.global_position
		seats[nm] = seat
		if not uses.has("Sit" + nm):
			var it := Interactable.new()
			it.name = "Use_Sit" + nm
			it.prompt = "坐下"
			it.reach = 1.3
			it.size = 0.25
			add_child(it)
			it.global_position = seat.global_position - Vector3(0, 0.6, 0) - seat.global_basis.z * -0.05
			it.used.connect(func(_i: Interactable) -> void: walker.sit_at(seat))
			uses["Sit" + nm] = it


# ----------------------------------------------------------------------------- 壳子、门、镜子
func _setup_shell() -> void:
	# 墙是单面的：灯在墙外（路灯、闪电）时阴影要双面画，不然光从墙背后漏进来
	for m in model.find_children("Body_*", "GeometryInstance3D", true, false):
		(m as GeometryInstance3D).cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_DOUBLE_SIDED
	for n in ["Body_MosquitoNet", "Body_WindowGlass", "GaugeGlass"]:
		var g := model.find_child(n, true, false) as GeometryInstance3D
		if g:
			g.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	for g in model.find_children("Glass_*", "GeometryInstance3D", true, false):
		(g as GeometryInstance3D).cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	# 白灰墙上的水渍流痕从天花板往下垂（worn_surface 的 streak_down），两个房间层高不一样
	var plaster := model.find_child("Body_Plaster", true, false) as GeometryInstance3D
	if plaster:
		plaster.set_instance_shader_parameter("streak_top", ceiling_height)
	# 墙角、顶角、墙根积灰（worn_surface 的 corner_dirt）要知道房间的范围
	var box := room_box()
	for nm in ["Body_Plaster", "Body_Ceiling", "Body_FloorPaint", "Body_Terrazzo", "Body_DadoGreen", "Body_Wainscot"]:
		var g := model.find_child(nm, true, false) as GeometryInstance3D
		if g:
			g.set_instance_shader_parameter("room_min", box.position)
			g.set_instance_shader_parameter("room_max", box.end)


var rain: MeshInstance3D


## 远处的灯（灯塔、吊车顶上的障碍灯、路灯）的光晕：一块朝着镜头的加法混合圆斑。远处的灯在体积雾的范围外，
## 光本身照不到什么，只靠这团光晕看得出它亮着。挂在灯的挂点上，跟着灯 visible
func add_glow(light_name: String, color: Color, size: float, energy := 2.0) -> MeshInstance3D:
	var l: Light3D = lights_by_name.get(light_name)
	if l == null:
		return null
	var g := Gradient.new()
	g.set_color(0, Color(1, 1, 1, 1))
	g.add_point(0.25, Color(1, 1, 1, 0.35))
	g.set_color(g.get_point_count() - 1, Color(1, 1, 1, 0))
	var tex := GradientTexture2D.new()
	tex.gradient = g
	tex.fill = GradientTexture2D.FILL_RADIAL
	tex.fill_from = Vector2(0.5, 0.5)
	tex.fill_to = Vector2(1.0, 0.5)
	var m := StandardMaterial3D.new()
	m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	m.billboard_mode = BaseMaterial3D.BILLBOARD_ENABLED
	m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	m.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
	m.no_depth_test = false
	m.albedo_texture = tex
	m.albedo_color = Color(color.r * energy, color.g * energy, color.b * energy, 1.0)
	var q := QuadMesh.new()
	q.size = Vector2(size, size)
	var mi := MeshInstance3D.new()
	mi.name = "Glow"
	mi.mesh = q
	mi.material_override = m
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	mi.gi_mode = GeometryInstance3D.GI_MODE_DISABLED
	l.add_child(mi)
	return mi
var _cam_attr: CameraAttributesPractical
var _dof := 0.0
var _ae_hold := 0.0

## 自动曝光（房间的 lens_config() 开，宿舍开、办事处不开）：眼睛跟着明暗慢慢调。曝光 = scale / 测到的场景平均亮度，
## 亮度先夹在最低 / 最高感光度换算出来的范围里（ISO 100 ≈ 亮度 0.125）：夹得窄，曝光就只在很小的范围里变——
## 暗处不会被提成白天，亮处不会被压平。speed 0.5：开灯后三四秒落稳；闪电那一下（零点几秒）来不及压暗
const AE_MIN_SENSITIVITY := 100.0
const AE_MAX_SENSITIVITY := 800.0
const AE_SPEED := 0.5
## 截图（--capture、--shots）时自动曝光一下子收敛到位：同一个机位每次拍出来一样，和前一个机位、等了多久无关
const AE_SPEED_SHOT := 12.0


## 镜头：抗锯齿（MSAA 2x 管不到着色器、贴图里的锯齿，加一道 SMAA；FSR2/TAA 时不用）、自动曝光、
## 坐着时的景深、调色 LUT（--lut 换掉，对比用）、颗粒和暗角
func _setup_lens() -> void:
	update_aa()
	_cam_attr = CameraAttributesPractical.new()
	_cam_attr.dof_blur_far_enabled = false
	_cam_attr.dof_blur_far_transition = 1.6
	_cam_attr.dof_blur_amount = 0.0
	var lc := lens_config()
	var ae := [float(lc.get("auto_exposure", 0.0)), float(lc.get("ae_min", AE_MIN_SENSITIVITY)),
		float(lc.get("ae_max", AE_MAX_SENSITIVITY))]
	match DebugArgs.get_arg("exposure"):
		"", "auto":
			pass
		"off":
			ae[0] = 0.0
		var v:
			# --exposure=scale[:min_sensitivity[:max_sensitivity]]（调参用）
			var p := String(v).split(":")
			for i in mini(p.size(), 3):
				ae[i] = float(p[i])
	_cam_attr.auto_exposure_enabled = ae[0] > 0.0
	_cam_attr.auto_exposure_scale = ae[0]
	_cam_attr.auto_exposure_min_sensitivity = ae[1]
	_cam_attr.auto_exposure_max_sensitivity = ae[2]
	_cam_attr.auto_exposure_speed = AE_SPEED_SHOT if DebugArgs.capturing() else AE_SPEED
	# 截图拍闪电（shot_flash）那一下按游戏里的速度适应，别被快速收敛压暗
	lightning.connect(func(_s: float) -> void: _ae_hold = 0.5)
	walker.attributes = _cam_attr
	if DebugArgs.has("lut"):
		var we := find_child("WorldEnvironment", false, false) as WorldEnvironment
		var lut := DebugArgs.get_arg("lut")
		if we:
			we.environment.adjustment_color_correction = null if lut == "off" else load(lut)
	var layer := CanvasLayer.new()
	layer.name = "Film"
	layer.layer = 40     # 在剧情界面（50）下面：字幕不吃颗粒
	var rect := ColorRect.new()
	rect.set_anchors_preset(Control.PRESET_FULL_RECT)
	rect.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var mat := ShaderMaterial.new()
	mat.shader = FILM
	if DebugArgs.capturing():
		mat.set_shader_parameter("time_seed", 3.0)   # 截图前后对比时颗粒不变
	rect.material = mat
	layer.add_child(rect)
	add_child(layer)


func _exit_lens() -> void:
	if is_inside_tree():
		get_viewport().screen_space_aa = Viewport.SCREEN_SPACE_AA_DISABLED


## SMAA 只在没有时域抗锯齿时叠：FSR2、TAA 自己就把高光、贴图、软阴影的噪点收了，再叠一道只会更糊。
## --aa 换抗锯齿（debug_args.gd）后也调这里；--smaa=on|off 强行开关
func update_aa() -> void:
	var vp := get_viewport()
	var temporal := vp.use_taa or vp.scaling_3d_mode == Viewport.SCALING_3D_MODE_FSR2
	var smaa := DebugArgs.get_arg("smaa", "off" if temporal else "on") == "on"
	vp.screen_space_aa = Viewport.SCREEN_SPACE_AA_SMAA if smaa else Viewport.SCREEN_SPACE_AA_DISABLED


## 坐着看对面的人：0.6 秒里把远处慢慢虚掉，焦点在他脸上
func _update_dof(delta: float) -> void:
	if _cam_attr == null:
		return
	# 截图时自动曝光平时一下子收敛；刚打过闪电的半秒按游戏里的速度
	if DebugArgs.capturing() and _cam_attr.auto_exposure_enabled:
		_ae_hold = maxf(_ae_hold - delta, 0.0)
		_cam_attr.auto_exposure_speed = AE_SPEED if _ae_hold > 0.0 else AE_SPEED_SHOT
	var tgt: Variant = focus_target() if walker.is_seated() else null
	_dof = move_toward(_dof, 0.04 if tgt != null else 0.0, delta * 0.04 / 0.6)
	_cam_attr.dof_blur_far_enabled = _dof > 0.0005
	_cam_attr.dof_blur_amount = _dof
	if tgt != null:
		_cam_attr.dof_blur_far_distance = walker.global_position.distance_to(tgt) + 0.6


func _add_rain() -> void:
	var c := rain_config()
	if c.is_empty():
		return
	var mat := ShaderMaterial.new()
	mat.shader = RAIN
	mat.set_shader_parameter("box_min", c["min"])
	mat.set_shader_parameter("box_max", c["max"])
	for k: String in c:
		if not k in ["min", "max", "count"]:
			mat.set_shader_parameter(k, c[k])
	rain = MeshInstance3D.new()
	rain.name = "Rain"
	rain.mesh = _drop_field(int(c.get("count", 20000)))
	rain.material_override = mat
	rain.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	rain.gi_mode = GeometryInstance3D.GI_MODE_DISABLED
	rain.custom_aabb = AABB(c["min"], c["max"] - c["min"]).grow(1.0)
	add_child(rain)


## n 个四边形，每个的四个顶点带同一个随机种子（COLOR），UV 是四个角；位置在着色器里算
func _drop_field(n: int) -> ArrayMesh:
	var rng := RandomNumberGenerator.new()
	rng.seed = 7
	var verts := PackedVector3Array()
	var uvs := PackedVector2Array()
	var cols := PackedColorArray()
	var idx := PackedInt32Array()
	verts.resize(n * 4)
	uvs.resize(n * 4)
	cols.resize(n * 4)
	idx.resize(n * 6)
	var corners := [Vector2(0, 0), Vector2(1, 0), Vector2(1, 1), Vector2(0, 1)]
	var tri := [0, 1, 2, 0, 2, 3]
	for i in n:
		var col := Color(rng.randf(), rng.randf(), rng.randf(), rng.randf())
		for k in 4:
			uvs[i * 4 + k] = corners[k]
			cols[i * 4 + k] = col
		for k in 6:
			idx[i * 6 + k] = i * 4 + tri[k]
	var arr := []
	arr.resize(Mesh.ARRAY_MAX)
	arr[Mesh.ARRAY_VERTEX] = verts
	arr[Mesh.ARRAY_TEX_UV] = uvs
	arr[Mesh.ARRAY_COLOR] = cols
	arr[Mesh.ARRAY_INDEX] = idx
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arr)
	return mesh


func _setup_mirror() -> void:
	var glass := model.find_child("Mirror_Glass", true, false) as MeshInstance3D
	if glass == null:
		return
	mirror = MIRROR.new()
	mirror.name = "Mirror"
	glass.add_child(mirror)


## 开门 / 关门（门扇绕门轴转 deg 度，正的往屋里开）
func swing_door(to: float, secs := 1.2) -> void:
	if door_leaf == null:
		return
	var tw := create_tween()
	tw.tween_property(self, "door_open", to, secs).set_trans(Tween.TRANS_SINE).set_ease(Tween.EASE_OUT)
	await tw.finished


func _process(delta: float) -> void:
	for s in _spins:
		s.rotate_object_local(Vector3.UP, delta * spin_speed(String(s.name)))
	if door_leaf:
		door_leaf.rotation.y = _door_rest_y + deg_to_rad(door_angle()) * door_open
		walker.walk_areas = walk_areas(door_open > 0.6)
	_update_lightning(delta)
	_update_dof(delta)


## 门开到底是多少度（子类改；正负决定往哪边开）
func door_angle() -> float:
	return 100.0


## Spin_<名字> 每秒转多少弧度
func spin_speed(_nm: String) -> float:
	return 6.0


# ----------------------------------------------------------------------------- 闪电（窗外）
## 闪电平行光的亮度（× 闪电强度 0~1）；闪电时夜空背景加亮多少（0 不变）
var lightning_energy := 2.2
var flash_sky := 0.0
var _sky_base := -1.0


func setup_lightning(dir: Vector3) -> void:
	_lightning = DirectionalLight3D.new()
	_lightning.name = "Lightning"
	_lightning.light_color = Color(0.75, 0.82, 1.0)
	_lightning.light_energy = 0.0
	_lightning.shadow_enabled = true
	_lightning.light_volumetric_fog_energy = 0.2
	add_child(_lightning)
	_lightning.look_at_from_position(Vector3.ZERO, dir, Vector3.UP)
	if DebugArgs.capturing() and DebugArgs.get_arg("lightning") != "on":
		_next_flash = INF   # 截图时不打闪电（保证可复现），--lightning=on 照常


func _update_lightning(delta: float) -> void:
	if _lightning == null:
		return
	_next_flash -= delta
	if _next_flash <= 0.0:
		_next_flash = randf_range(14.0, 34.0)
		_flash_once(randf_range(0.6, 1.0))
	_flash = maxf(_flash - delta * 6.0, 0.0)
	_lightning.light_energy = _flash * lightning_energy
	_lightning.visible = _flash > 0.001
	for l: Light3D in _flash_lights:
		l.light_energy = _flash * _flash_lights[l]
		l.visible = _lightning.visible
	if flash_sky > 0.0:
		# 闪电那一下夜空跟着亮（窗外的吊车、楼变成剪影）
		var env := (find_child("WorldEnvironment", false, false) as WorldEnvironment).environment
		if _sky_base < 0.0:
			_sky_base = env.background_energy_multiplier
		env.background_energy_multiplier = _sky_base + _flash * flash_sky
	var fill := lightmap.lightning_fill
	if fill:
		fill.light_energy = _flash * RoomLightmap.LIGHTNING_FILL
		fill.visible = _lightning.visible and not fill.get_meta("off", false)


## 现在闪电有多亮（0~1，闪完往下掉）：窗外的远景（dorm.gd 的全景条）跟着它换闪电版
func flash_level() -> float:
	return _flash


func _flash_once(strength: float) -> void:
	lightning.emit(strength)
	for k in randi_range(1, 3):
		if not is_inside_tree():
			return
		_flash = strength * randf_range(0.6, 1.0)
		await get_tree().create_timer(randf_range(0.06, 0.16)).timeout


# ----------------------------------------------------------------------------- 截图（--capture、--shots，见 debug_args.gd）
## 按墙上的时间闪的灯（宿舍窗外吊车顶上的航空障碍灯，dorm.gd 一秒半闪一下）：截图时灭着，免得前后两次一张亮一张灭
const SHOT_DARK := ["Light_CraneRed"]

var _shot_fov := -1.0


## 截图模式：同样的机位每次拍出来要一样，改画面前后才好比。闪电不打（setup_lightning）；闪的灯停在基础亮度
## （--flicker=on 照常闪）；障碍灯灭着；坐着不晃、镜子里不眨眼。--sit 坐到椅子上；--shots 向 DebugArgs 报到
func _setup_capture() -> void:
	walker.still = true
	body.set("_blink_wait", INF)
	for nm: String in lights_by_name:
		var l: Light3D = lights_by_name[nm]
		if l.get_script() == FLICKER and DebugArgs.get_arg("flicker") != "on":
			l.set_process(false)
		for k: String in SHOT_DARK:
			if nm.begins_with(k):
				l.light_energy = 0.0
	if not Story.is_target(room_name):
		return
	if DebugArgs.has("sit"):
		shot_pose({"sit": DebugArgs.get_arg("sit"), "yaw": float(DebugArgs.get_arg("yaw", "0")),
			"pitch": float(DebugArgs.get_arg("pitch", "0")), "tube": DebugArgs.get_arg("tube") == "on"})
	if DebugArgs.has("shots"):
		DebugArgs.room = self


## 摆一个机位（--shots 的一项，字段见 debug_args.gd）：站哪 / 坐哪张椅子、看哪、视野、宿舍日光灯、门开多少
func shot_pose(s: Dictionary) -> void:
	if _shot_fov < 0.0:
		_shot_fov = walker.normal_fov
	walker.normal_fov = float(s.get("fov", _shot_fov))
	if s.has("gi"):
		set_gi(String(s.gi))
	# 查问题用："set": {"节点路径:属性": 值}（路径相对房间），比如临时调一盏灯的亮度
	var sets: Dictionary = s.get("set", {})
	for k: String in sets:
		var parts := k.split(":")
		var n := get_node_or_null(NodePath(parts[0]))
		if n:
			n.set(parts[1], sets[k])
	set_light("Light_Tube_Main", bool(s.get("tube", DebugArgs.get_arg("tube") == "on")))
	door_open = clampf(float(s.get("door", 0.0)), 0.0, 1.0)
	walker.walk_areas = walk_areas(door_open > 0.6)
	var seat: Node3D = null
	if s.has("sit"):
		seat = seats.get(String(s.sit))
		if seat == null:
			push_error("没有座位 Seat_%s（有：%s）" % [s.sit, ", ".join(seats.keys())])
	# 没给 at 就站在开场的位置、朝开场的方向
	var at: Array = s.get("at", [walker.start.x, walker.start.y])
	var yaw_deg := float(s.get("yaw", 0.0 if s.has("at") or seat != null else walker.start_yaw))
	walker.place_for_shot(Vector2(at[0], at[1]), yaw_deg, float(s.get("pitch", 0.0)), seat, bool(s.get("free", false)))
	body.set("_blink_wait", INF)


## 窗外打一道闪电，亮度在 strength 上停 frames 帧（体积雾跟上一点），截图拍最亮的那一下
func shot_flash(strength: float, frames := 6) -> void:
	if _lightning == null:
		return
	lightning.emit(strength)
	for i in frames:
		_flash = strength
		await get_tree().process_frame


# ----------------------------------------------------------------------------- GI
## 间接光两套：
##   LightmapGI（光照贴图）：有 assets/gi/<房间>.lmbake 就用它（tools/bake_lightmap.sh 烘）。只烘间接光——灯的 bake_mode
##     是 Dynamic，直接光和阴影照旧实时算；会动的东西（门扇、吊扇、钟、人）不进贴图，由烘出来的探针照亮
##   VoxelGI（场景里的 RoomGI）：没有光照贴图时用；--gi=voxel 强制用它（对比），--gi=both 两个都开
## --shots 截图时两套都准备好，机位里写 "gi": "voxel" / "lightmap" 就地切换（同一个进程里轮流量帧率，比两次启动公平）
func _bake_gi() -> void:
	if not Story.is_target(room_name):
		return
	if DebugArgs.has("lm-export"):
		lightmap.export()
		return
	var gi := find_child("RoomGI", false, false) as VoxelGI
	var mode := DebugArgs.get_arg("gi", "lightmap")
	# 光照贴图和模型对不上（模型改了没重烘）时 load_data 返回 false，退回 VoxelGI
	if mode != "voxel" and not DebugArgs.has("bake-gi") and ResourceLoader.exists(lightmap_path()) \
			and lightmap.load_data():
		if gi and mode != "both":
			if not DebugArgs.has("shots"):
				gi.queue_free()
				return
			gi.visible = false
	if gi == null:
		return
	var baking := DebugArgs.has("bake-gi")
	if not baking and not gi_path.is_empty() and ResourceLoader.exists(gi_path):
		gi.data = load(gi_path)
		return
	await get_tree().process_frame
	var t0 := Time.get_ticks_msec()
	gi.bake(model)
	if gi.data:
		gi.data.interior = true
		gi.data.energy = 1.0
		gi.data.propagation = 0.7
		gi.data.normal_bias = 0.2
		print("VoxelGI %s baked in %d ms" % [room_name, Time.get_ticks_msec() - t0])
		if baking and not gi_path.is_empty():
			DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(gi_path.get_base_dir()))
			print("saved ", gi_path, " err=", ResourceSaver.save(gi.data, gi_path))
	if baking:
		get_tree().quit()


# ----------------------------------------------------------------------------- 光照贴图（LightmapGI，见 room_lightmap.gd）
## 光照贴图存哪；variant 是变体名（"" 是默认那份）。--lm-dir=res://lmexp/试验/ 换个目录（试参数：导出、烘焙、截图都带上它，
## 不动 assets/gi/ 里正式的那份；目录名不能以点开头，编辑器不导入隐藏目录里烘出来的贴图）
func lightmap_path(variant := "") -> String:
	return DebugArgs.get_arg("lm-dir", "res://assets/gi/").path_join(
		"%s%s.lmbake" % [room_name, "_" + variant if variant else ""])


## 光照贴图的变体：变体名 -> 灯名。这盏灯开着（亮到它正常亮度的一半以上）时换成这份贴图，
## 烘焙时每个变体把这盏灯打开各烘一份（宿舍的日光灯：关着、开着各一份）。子类覆盖
func lightmap_variants() -> Dictionary:
	return {}


## 不烘进光照贴图的灯（名字前缀）：一闪一闪的（宿舍窗外龙门吊的障碍灯）。子类覆盖
func lightmap_skip_lights() -> Array:
	return []


## 烘焙时窗外的天（只给光照贴图用，运行时看得见的背景不变）；null 就用房间环境里的。--lm-sky-energy=倍数 试亮度。子类覆盖
func lightmap_sky() -> Sky:
	return null


## 只在烘焙时才有的灯（烘成 Static：直接光、间接光都进贴图，探针也记下它，会动的东西由探针照亮；运行时没有这盏灯，不花一点开销）。
## 位置相对房间。用来做窗口的「天光面光源」：窗洞里放一块朝屋里发光的面光源，代替窗外的天往屋里透的光，
## 窗外的东西（防盗窗、外墙）不会跟着被照亮。子类覆盖
func lightmap_bake_lights() -> Array[Light3D]:
	return []


## 只在烘焙时改的灯光属性：名字前缀 -> {属性: 值}（light_indirect_energy：这盏灯的间接光烘多亮，不影响实时的直接光）。子类覆盖
func lightmap_bake_overrides() -> Dictionary:
	return {}


## 连直接光一起烘进光照贴图的灯（bake_mode 改成 Static）：名字前缀 -> 烘焙和运行时都要改的属性（light_size、亮度……）。
## 用在从窗外照进来、自己不动也不变的光上（宿舍的路灯光 StreetGlow）：防盗窗的影子按灯的大小软软地烘在床上、地上；
## 运行时 Godot 对有光照贴图的东西跳过 Static 的灯（不会照两遍），只实时照会动的（人、吊扇、开着的门扇……）。子类覆盖
func lightmap_static_lights() -> Dictionary:
	return {}


## LightmapGI 的烘焙参数（属性名 → 值，子类可以改）。--lm-<属性名>=值 临时覆盖（tools/bake_lightmap.sh 里试参数用）。
## 另外 "sky_energy"：烘焙时窗外的天（环境背景）亮几倍（运行时看得见的背景不变），--lm-sky-energy=倍数 再乘上去。
## texel_scale 乘在导入时的 lightmap_texel_size（.import 里 0.03 米）上：1.0 就是 3 厘米一个像素
func lightmap_config() -> Dictionary:
	return {
		"quality": LightmapGI.BAKE_QUALITY_HIGH,
		"bounces": 4,
		"bounce_indirect_energy": 1.0,
		"directional": true,          # 方向性光照贴图：间接光也带方向，法线贴图在背光处不会糊成一片
		"texel_scale": 1.0,
		# 超采样（2 倍）：分辨率不变（显存不变），烘焙时间约 3 倍；不开的话窗框、窗帘投在墙上的软影子被糊成一团
		# （tools/bake_lightmap.sh 试过：ULTRA 质量和 HIGH 看不出差别，贴图密度翻倍和超采样效果差不多但显存 4 倍）
		"supersampling": true,
		"supersampling_factor": 2.0,
		"use_denoiser": true,
		"denoiser_strength": 0.1,
		"generate_probes_subdiv": LightmapGI.GENERATE_PROBES_SUBDIV_16,
		"environment_mode": LightmapGI.ENVIRONMENT_MODE_SCENE,   # 窗外的天光（WorldEnvironment 的天空）
	}


## 截图对比：就地在光照贴图（"lightmap"）和 VoxelGI（"voxel"）之间切换，"off" 都关（--shots 机位的 "gi" 字段）
func set_gi(mode: String) -> void:
	lightmap.set_mode(mode)


## 窗外的闪电（setup_lightning 建的平行光，没有就是 null）
func lightning_light() -> DirectionalLight3D:
	return _lightning


func _exit_tree() -> void:
	lightmap.release()
	_exit_lens()
