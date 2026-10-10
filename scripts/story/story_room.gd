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


func _ready() -> void:
	model = find_child("Model", false, false) as Node3D
	_collect_anchors()
	_add_props()
	_add_lights()
	_add_decals()
	_add_papers()
	_add_uses()
	_setup_shell()
	_add_player()
	audio = RoomAudio.new()
	audio.name = "Audio"
	add_child(audio)
	setup_audio(audio)
	Story.ui.reader_opened.connect(func() -> void: audio.play("paper"))
	walker.seated_changed.connect(func(on: bool) -> void:
		if on:
			audio.play("chair_creak"))
	_setup_mirror()
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
func _add_lights() -> void:
	var cfg := lights()
	for anchor: Node3D in model.find_children("Light_*", "Node3D", true, false):
		var nm := String(anchor.name)
		var key := ""
		for k: String in cfg:
			if nm.begins_with(k) and k.length() > key.length():
				key = k
		if key.is_empty():
			continue
		var c: Dictionary = cfg[key]
		var l: Light3D
		if c.get("spot", false):
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
		l.name = "Light"
		l.light_color = c.color
		l.light_energy = c.energy
		l.shadow_enabled = c.get("shadow", true)
		l.shadow_blur = c.get("blur", 1.5)
		l.shadow_bias = 0.08
		l.shadow_normal_bias = 1.2
		l.light_size = c.get("size", 0.05)
		l.light_volumetric_fog_energy = c.get("fog", 0.5)
		l.light_specular = c.get("specular", 0.5)
		if c.has("flicker"):
			l.set_script(FLICKER)
			l.set("amount", c.flicker)
			l.set("speed", c.get("flicker_speed", 14.0))
		anchor.add_child(l)
		lights_by_name[nm] = l
		var tube_name := nm.replace("Light_Tube_", "Tube_")
		if tube_name != nm:
			var tube := model.find_child(tube_name, true, false) as MeshInstance3D
			if tube:
				_tubes[nm] = tube


## 开灯、关灯（日光灯管、灯泡的发光跟着变）
func set_light(nm: String, on: bool, energy := -1.0) -> void:
	var l: Light3D = lights_by_name.get(nm)
	if l == null:
		return
	l.visible = on
	if energy >= 0.0:
		l.light_energy = energy
	if _tubes.has(nm):
		_tube_glow(_tubes[nm], 1.0 if on else 0.0)


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
			mat.albedo_texture = doc.get_texture()
			mat.roughness = 0.85
			mat.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC
			if doc.style == "lcd":
				mat.emission_enabled = true
				mat.emission_texture = doc.get_texture()
				mat.emission_energy_multiplier = 0.0
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


## 门开到底是多少度（子类改；正负决定往哪边开）
func door_angle() -> float:
	return 100.0


## Spin_<名字> 每秒转多少弧度
func spin_speed(_nm: String) -> float:
	return 6.0


# ----------------------------------------------------------------------------- 闪电（窗外）
func setup_lightning(dir: Vector3) -> void:
	_lightning = DirectionalLight3D.new()
	_lightning.name = "Lightning"
	_lightning.light_color = Color(0.75, 0.82, 1.0)
	_lightning.light_energy = 0.0
	_lightning.shadow_enabled = true
	_lightning.light_volumetric_fog_energy = 0.2
	add_child(_lightning)
	_lightning.look_at_from_position(Vector3.ZERO, dir, Vector3.UP)


func _update_lightning(delta: float) -> void:
	if _lightning == null:
		return
	_next_flash -= delta
	if _next_flash <= 0.0:
		_next_flash = randf_range(14.0, 34.0)
		_flash_once(randf_range(0.6, 1.0))
	_flash = maxf(_flash - delta * 6.0, 0.0)
	_lightning.light_energy = _flash * 2.2
	_lightning.visible = _flash > 0.001


func _flash_once(strength: float) -> void:
	lightning.emit(strength)
	for k in randi_range(1, 3):
		if not is_inside_tree():
			return
		_flash = strength * randf_range(0.6, 1.0)
		await get_tree().create_timer(randf_range(0.06, 0.16)).timeout


# ----------------------------------------------------------------------------- GI
func _bake_gi() -> void:
	var gi := find_child("RoomGI", false, false) as VoxelGI
	if gi == null:
		return
	if not Story.is_target(room_name):
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
