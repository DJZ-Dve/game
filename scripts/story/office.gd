extends StoryRoom
## 第一章「契」：东溟海洋工程的临时办事处（模型 blender/scripts/gen_office.py，台词 assets/story/office.dlg）。
## 推门进来，沈渡坐在写字台后面抬眼看你：「周先生，请坐。」坐到他对面开始谈；站起来能在屋里走动、看墙上的东西，
## 回来坐下接着谈。读合同 → 问几个问题 → 签：低头写生辰、写名字，拇指按进印泥、按在名字上——挂钟停了。
## 沈渡把平安符推过来。出门就是第二章。

const DLG := "res://assets/story/office.dlg"
const DOCS := "res://assets/story/docs/"
const NPC_MODEL := preload("res://assets/models/npc_shen.glb")
const SUB_MODEL := "res://assets/models/submarine_exterior.glb"
## 开场钟上的时间（下午三点零七分）；签字那一刻停在三点十四
const START_TIME := 15.0 * 3600.0 + 7.0 * 60.0 + 20.0

var shen: StoryNPC
var _clock_t := START_TIME
var _clock_running := true
var _hands := {}
var _pendulum: Node3D
var _pendulum_rest := Basis.IDENTITY
var _talisman: Node3D
var _pen: Node3D
var _leaving := false
var _in_talk := false
var _signed_marks := {}


func props() -> Dictionary:
	return {
		"Anchor_ShenChair": {"asset": "chinese_armchair", "scale": 0.78},
		"Anchor_Cabinet0": {"asset": "chinese_cabinet"},
		"Anchor_Cabinet1": {"asset": "chinese_cabinet"},
		"Anchor_Screen": {"asset": "chinese_screen_panels"},
		"Anchor_Altar": {"asset": "chinese_console_table"},
		"Anchor_Drawers8": {"asset": "vintage_wooden_drawer_01"},
		"Anchor_Drawers0": {"asset": "vintage_wooden_drawer_01"},
		"Anchor_Lifebuoy": {"asset": "lifebuoy"},
		"Anchor_TeaTable": {"asset": "chinese_tea_table"},
		"Anchor_Stool1": {"asset": "chinese_stool"},
		"Anchor_Stool2": {"asset": "chinese_stool"},
	}


func lights() -> Dictionary:
	return {
		# 两盏日光灯：一盏亮着（有点闪），一盏坏了不亮
		"Light_Tube_A": {"color": Color(0.82, 0.95, 0.9), "energy": 0.9, "range": 7.0, "atten": 1.2, "size": 0.03,
			"specular": 0.2, "fog": 0.2, "flicker": 0.08, "flicker_speed": 10.0},
		"Light_Tube_B": {"color": Color(0.82, 0.95, 0.9), "energy": 0.9, "range": 7.0, "atten": 1.2, "size": 0.03,
			"specular": 0.2},
		# 绿罩台灯：照着沈渡的手和桌上的合同，脸从下面打亮一点
		"Light_DeskLamp": {"spot": true, "color": Color(1.0, 0.82, 0.55), "energy": 3.0, "range": 1.8, "angle": 60.0,
			"atten": 1.0, "size": 0.05, "fog": 0.3},
		"Light_Incense": {"color": Color(1.0, 0.45, 0.15), "energy": 0.12, "range": 0.8, "shadow": false},
		"Light_Lighthouse": {"color": Color(1.0, 0.15, 0.08), "energy": 30.0, "range": 25.0, "shadow": false,
			"fog": 1.0},
		"Light_ShipMast": {"color": Color(1.0, 0.95, 0.85), "energy": 8.0, "range": 10.0, "shadow": false},
	}


func use_config() -> Dictionary:
	return {
		"Shen": {"prompt": "和沈先生说话", "size": 0.3, "reach": 2.2},
		"Contract": {"prompt": "看合同", "size": 0.03, "reach": 1.3},
		"InkPad": {"size": 0.04, "reach": 1.3, "lines": ["（印泥。红得发黑。）"]},
		"TeaMine": {"prompt": "喝茶", "size": 0.06, "reach": 1.3},
		"TeaShen": {"size": 0.06, "reach": 1.6},
		"DeskGlass": {"prompt": "看玻璃板底下", "size": 0.18, "reach": 1.4},
		"Phone": {"size": 0.08, "reach": 1.5},
		"Luopan": {"size": 0.1, "reach": 1.5},
		"Chart": {"prompt": "看海图", "size": 0.6, "reach": 2.2},
		"Rubbing": {"prompt": "看拓片", "size": 0.3, "reach": 1.8},
		"OldPhoto": {"prompt": "看照片", "size": 0.15, "reach": 1.6},
		"Screen": {"size": 0.5, "reach": 1.8},
		"Altar": {"size": 0.3, "reach": 1.6},
		"Scroll": {"size": 0.3, "reach": 2.2},
		"Clock": {"size": 0.2, "reach": 3.0},
		"Window": {"prompt": "看窗外", "size": 0.8, "reach": 2.5},
		"Safe": {"size": 0.3, "reach": 1.6},
		"Lifebuoy": {"size": 0.3, "reach": 1.8},
		"Umbrella": {"size": 0.2, "reach": 1.5},
		"Door": {"prompt": "出门", "size": 0.35, "reach": 1.5},
	}


func paper_config() -> Dictionary:
	var paper := Color(0.92, 0.9, 0.83)
	return {
		"Contract1": {"text_path": DOCS + "contract_1.txt", "tint": paper, "age": 0.1, "stains": 0.0,
			"paper_seed": 31.0, "line_spacing": 4, "margin": Vector2(120, 100)},
		"Contract2": {"text_path": DOCS + "contract_2.txt", "tint": paper, "age": 0.1, "stains": 0.0,
			"paper_seed": 32.0, "stamps": [[Vector2(780, 1290), 125, "东溟海洋工程有限公司", "合同专用章", -10.0]]},
		"Card": {"text_path": DOCS + "card.txt", "paper_size": Vector2i(900, 540), "margin": Vector2(40, 40),
			"tint": Color(0.94, 0.93, 0.9), "age": 0.05, "paper_seed": 33.0},
		"Chart": {"text_path": "", "paper_size": Vector2i(1500, 1000), "tint": Color(0.88, 0.85, 0.74), "age": 0.55,
			"stains": 0.4, "folds": Vector2(2, 1), "paper_seed": 34.0},
		"DeskChart": {"text_path": "", "paper_size": Vector2i(1200, 860), "tint": Color(0.88, 0.85, 0.74), "age": 0.4,
			"stains": 0.2, "folds": Vector2(1, 1), "paper_seed": 35.0},
		"Rubbing": {"text_path": "", "paper_size": Vector2i(700, 1050), "tint": Color(0.1, 0.1, 0.1), "age": 0.3,
			"stains": 0.0, "paper_seed": 36.0},
		"OldPhoto": {"text_path": "", "paper_size": Vector2i(800, 600), "tint": Color(0.72, 0.66, 0.55), "age": 0.7,
			"stains": 0.3, "paper_seed": 37.0},
		"DeskPhoto": {"text_path": "", "paper_size": Vector2i(800, 560), "tint": Color(0.72, 0.66, 0.55), "age": 0.7,
			"stains": 0.2, "paper_seed": 38.0},
	}


func _ready() -> void:
	room_name = "office"
	gi_path = "res://assets/gi/office_gi.res"
	super._ready()
	set_light("Light_Tube_B", false)
	setup_lightning(Vector3(-0.3, -0.6, 1.0))
	_dress_papers()
	_add_shen()
	_add_sub()
	_setup_clock()
	_add_steam()
	_talisman = model.find_child("Hide_Talisman", true, false) as Node3D
	if _talisman:
		_talisman.visible = false
	_connect_uses()
	walker.seated_changed.connect(_on_seated)
	if DebugArgs.has("capture") or DebugArgs.has("at") or DebugArgs.has("bake-gi"):
		return
	if not Story.is_target("office") and not Story.flag("chapter0_done"):
		return
	_intro()
	if DebugArgs.has("autoplay"):
		_autoplay()


## 墙上、桌上的纸：海图、拓片、老照片（不是文字的那几张）
func _dress_papers() -> void:
	papers.Chart.add_chart(Rect2(Vector2(30, 30), Vector2(1440, 940)), 7)
	papers.DeskChart.add_chart(Rect2(Vector2(20, 20), Vector2(1160, 820)), 7, 1.6)
	papers.Rubbing.add_vertical(Rect2(Vector2(40, 30), Vector2(620, 990)), PackedStringArray([
		"□光绪四年□次戊寅七月望□沈□□□□",
		"□□东□□□□□□□白沙门□□□□",
		"□□□□□□□□□□□□",
		"□□□□□□□□□□□□□□",
		"□□□□□□契□□□□□□□镇□□",
		"□海不扬波□□□□□□□□□□□□□□",
		"□□□□□□□□□□□□□□",
	]), 52, Color(0.78, 0.75, 0.68))
	for nm in ["OldPhoto", "DeskPhoto"]:
		var path := "res://assets/textures/story/%s.png" % nm.to_snake_case()
		if ResourceLoader.exists(path):
			papers[nm].add_image(load(path), Rect2(Vector2(36, 36), Vector2(papers[nm].paper_size) - Vector2(72, 72)))


func _add_shen() -> void:
	var a := model.find_child("Anchor_Shen", true, false) as Node3D
	shen = StoryNPC.new()
	shen.name = "Shen"
	shen.model = NPC_MODEL
	shen.base_anim = "sit"
	shen.talk_gestures = ["sit_think", "sit_shrug", "sit_touch_face"]
	a.add_child(shen)
	# 挂点的 +Z 朝南（面朝来客），角色模型面朝 -Z：转过来
	shen.rotation_degrees.y = 180.0


func _add_sub() -> void:
	var a := model.find_child("Anchor_Sub", true, false) as Node3D
	if a == null or not ResourceLoader.exists(SUB_MODEL):
		return
	var sub := (load(SUB_MODEL) as PackedScene).instantiate() as Node3D
	a.add_child(sub)


func _connect_uses() -> void:
	uses.Shen.used.connect(func(_i: Interactable) -> void:
		await Story.run(DLG, "shen_after" if Story.flag("signed") else "shen_standing", self))
	uses.Contract.used.connect(func(_i: Interactable) -> void: await _read("contract"))
	uses.TeaMine.used.connect(func(_i: Interactable) -> void: await Story.run(DLG, "tea_mine", self))
	uses.TeaShen.used.connect(func(_i: Interactable) -> void: await Story.run(DLG, "tea_shen", self))
	uses.DeskGlass.used.connect(func(_i: Interactable) -> void: await Story.run(DLG, "desk_glass", self))
	uses.Door.used.connect(func(_i: Interactable) -> void: _on_door())
	for nm in ["Chart", "Rubbing", "Screen", "Altar", "Scroll", "Clock", "Luopan", "Phone", "Window", "Safe",
			"Lifebuoy", "Umbrella"]:
		var lbl: String = nm.to_snake_case()
		uses[nm].used.connect(func(_i: Interactable) -> void: await Story.run(DLG, lbl, self))
	uses.OldPhoto.used.connect(func(_i: Interactable) -> void: await Story.run(DLG, "old_photo", self))
	# 坐下就是开谈（来客椅自动生成的「坐下」）
	uses.SitVisitor.prompt = "坐下"


func _intro() -> void:
	if not Story.flag("chapter0_done"):
		# 直接从这一章开始（调试）：自己放章节字幕
		Story.ui.set_black(true)
		await Story.ui.show_card("第一章　契", "一九九八年八月二十九日　下午三点　渔业公司老楼")
		Story.ui.fade_in(2.0)
	await get_tree().create_timer(1.6).timeout
	if not walker.is_seated():
		await Story.run(DLG, "arrive", self)


func _on_seated(seated: bool) -> void:
	if not seated or _in_talk:
		return
	_in_talk = true
	await get_tree().create_timer(0.8).timeout
	var lbl := "start"
	if Story.flag("signed"):
		lbl = "shen_after"
	elif Story.flag("read_contract"):
		lbl = "contract_menu"
	elif Story.visited(DLG, "start"):
		lbl = "menu"
	await Story.run(DLG, lbl, self)
	_in_talk = false


func _on_door() -> void:
	if not Story.flag("signed"):
		await Story.run(DLG, "door_before", self)
		return
	if _leaving:
		return
	_leaving = true
	play("door_open")
	swing_door(1.0, 1.4)
	await Story.run(DLG, "leave", self)


func door_angle() -> float:
	return 95.0


# ----------------------------------------------------------------------------- 对白里的命令
func on_cmd(cmd: String, args: Array) -> void:
	match cmd:
		"anim":
			shen.gesture(args[0])
		"smile":
			shen.grin(0.7 if args.size() > 0 and args[0] == "big" else 0.4, 2.5)
		"look":
			if args[0] == "window":
				walker.look_toward(to_global(Vector3(3.0, 0.5, -25.0)), 2.2)
				await get_tree().create_timer(2.5).timeout
			else:
				walker.look_toward(null)
				walker.look_toward(shen.global_position + Vector3(0, 1.25, 0), 3.0)
				await get_tree().create_timer(1.2).timeout
				walker.look_toward(null)
		"wait":
			await get_tree().create_timer(float(args[0])).timeout
		"read":
			await _read(args[0])
		"sign":
			# 签字、按手印到挂钟停摆这一段不让汽笛插进来（会盖住钟停的那一下）
			_horn_wait = maxf(_horn_wait, 30.0)
			await _sign(args[0])
		"clock":
			_clock_running = false
			play("clock_stop")
		"give":
			await _give_talisman()
		"stand":
			walker.stand_up()
		"leave":
			Story.set_flag("chapter1_done")
			Story.goto_scene("deep_sea", "第二章　下潜", "一九九八年九月四日　农历七月十四　亥时")


func _read(doc: String) -> void:
	var pages: Array = []
	match doc:
		"contract":
			pages = [papers.Contract1.get_texture(), papers.Contract2.get_texture()]
		"chart":
			pages = [papers.Chart.get_texture()]
		"desk_chart":
			pages = [papers.DeskChart.get_texture(), papers.Card.get_texture()]
		"rubbing":
			pages = [papers.Rubbing.get_texture()]
		"old_photo":
			pages = [papers.OldPhoto.get_texture()]
	if not pages.is_empty():
		await Story.ui.read(pages)


# ----------------------------------------------------------------------------- 签字
## 纸上一点（PaperDoc 的像素坐标）在 3D 里的位置：纸面网格四个角的 UV 是 (0,0)…(1,1)，双线性插值
func paper_point(nm: String, px: Vector2) -> Vector3:
	var mi := model.find_child("Paper_" + nm, true, false) as MeshInstance3D
	var doc: PaperDoc = papers[nm]
	var uv := px / Vector2(doc.paper_size)
	var arr := mi.mesh.surface_get_arrays(0)
	var verts: PackedVector3Array = arr[Mesh.ARRAY_VERTEX]
	var uvs: PackedVector2Array = arr[Mesh.ARRAY_TEX_UV]
	var corner := {}
	for i in uvs.size():
		var key := Vector2i(roundi(uvs[i].x), roundi(uvs[i].y))
		if absf(uvs[i].x - key.x) < 0.01 and absf(uvs[i].y - key.y) < 0.01:
			corner[key] = verts[i]
	var top: Vector3 = (corner[Vector2i(0, 0)] as Vector3).lerp(corner[Vector2i(1, 0)], uv.x)
	var bot: Vector3 = (corner[Vector2i(0, 1)] as Vector3).lerp(corner[Vector2i(1, 1)], uv.x)
	return mi.global_transform * top.lerp(bot, uv.y)


## 签字的三步：生辰、名字、手印。右手（握着笔）在纸上从左往右移，字跟着一笔一笔出来
func _sign(step: String) -> void:
	var doc: PaperDoc = papers.Contract2
	var fields := {
		"birth": [Vector2(322, 268), "一九六六年七月十五日子时", 46],
		"name": [Vector2(420, 1395), "周海生", 64],
	}
	walker.locked = true
	walker.door_lean = 0.6
	if step == "thumb":
		await _thumb(doc)
		return
	var f: Array = fields[step]
	var w := doc.add_writing(f[0], f[1], f[2])
	w.reveal = 0.0
	_signed_marks[step] = w
	var text_w: float = (w.font as Font).get_string_size(f[1], HORIZONTAL_ALIGNMENT_LEFT, -1, f[2]).x
	var a := paper_point("Contract2", f[0] + Vector2(0, -f[2] * 0.3))
	var b := paper_point("Contract2", f[0] + Vector2(text_w, -f[2] * 0.3))
	walker.look_toward(a.lerp(b, 0.5), 3.0)
	_show_pen(true)
	doc.begin_live()
	play("pen_write")
	var dur := 0.35 * (f[1] as String).length() + 0.6
	var t := 0.0
	while t < dur:
		var k := t / dur
		w.reveal = k
		# 手腕在笔尖后上方；写字时一上一下地点
		var tip := a.lerp(b, k) + Vector3(0, 0.004 + 0.003 * absf(sin(t * 18.0)), 0)
		_hand_at(tip + Vector3(0.0, 0.06, 0.07), 0.75)
		await get_tree().process_frame
		t += get_process_delta_time()
	w.reveal = 1.0
	doc.end_live()
	_show_pen(false)
	walker.set_hand(1, {})
	walker.look_toward(null)
	walker.door_lean = 0.0
	walker.locked = false


func _thumb(doc: PaperDoc) -> void:
	var pad := (uses.InkPad as Node3D).global_position
	var spot := paper_point("Contract2", Vector2(590, 1372))
	walker.look_toward(pad, 3.0)
	for i in 30:
		_hand_at(pad + Vector3(0, 0.07 - 0.04 * i / 30.0, 0.04), 0.9)
		await get_tree().process_frame
	play("ink_press")
	await get_tree().create_timer(0.4).timeout
	walker.look_toward(spot, 3.0)
	for i in 40:
		_hand_at(pad.lerp(spot, i / 40.0) + Vector3(0, 0.08 - 0.02 * sin(PI * i / 40.0), 0.04), 0.9)
		await get_tree().process_frame
	var tp := doc.add_thumb(Vector2(590, 1372), 90, 8)
	doc.begin_live()
	play("thumb_press")
	for i in 30:
		tp.amount = i / 29.0
		_hand_at(spot + Vector3(0, 0.07 - 0.03 * i / 29.0, 0.04), 0.9)
		await get_tree().process_frame
	await get_tree().create_timer(0.5).timeout
	doc.end_live()
	walker.set_hand(1, {})
	walker.look_toward(null)
	walker.door_lean = 0.0
	walker.locked = false


## 右手到某处（世界坐标 → 房间局部坐标给 RoomWalker）：手指朝前、掌心朝下
func _hand_at(world: Vector3, grasp: float) -> void:
	var p := to_local(world)
	var fwd := Vector3(-sin(walker.yaw), 0, -cos(walker.yaw))
	walker.set_hand(1, {"pos": p, "fingers": (fwd + Vector3(-0.3, -0.3, 0)).normalized(), "palm": Vector3.DOWN,
		"weight": 1.0, "grasp": grasp})


## 签字时右手里拿一支钢笔（挂在手骨上，顺着手指的方向）
func _show_pen(on: bool) -> void:
	if _pen == null:
		var sk := body.find_children("*", "Skeleton3D", true, false)
		if sk.is_empty():
			return
		var skel := sk[0] as Skeleton3D
		var att := BoneAttachment3D.new()
		att.bone_name = "Bip01 R Hand"
		skel.add_child(att)
		var hand := skel.find_bone("Bip01 R Hand")
		var finger := skel.find_bone("Bip01 R Finger1")
		var rest_h := skel.get_bone_global_rest(hand)
		var dir := (rest_h.basis.inverse() * (skel.get_bone_global_rest(finger).origin - rest_h.origin)).normalized()
		var pen := MeshInstance3D.new()
		var cm := CylinderMesh.new()
		cm.top_radius = 0.005
		cm.bottom_radius = 0.004
		cm.height = 0.13
		pen.mesh = cm
		var mat := StandardMaterial3D.new()
		mat.albedo_color = Color(0.03, 0.03, 0.03)
		mat.roughness = 0.3
		pen.material_override = mat
		# 笔顺着手指往前、斜着往下伸出去；中段握在拇指和食指之间
		pen.basis = Basis(Quaternion(Vector3.UP, (dir + Vector3(0, -0.5, 0)).normalized()))
		pen.position = dir * 0.07 / skel.global_basis.get_scale().x
		pen.scale = Vector3.ONE / skel.global_basis.get_scale().x
		att.add_child(pen)
		_pen = att
	_pen.visible = on


## 沈渡把平安符推过来，玩家拿起来（藏掉）
func _give_talisman() -> void:
	if _talisman == null:
		return
	_talisman.visible = true
	var start := _talisman.position
	var tw := create_tween()
	tw.tween_property(_talisman, "position", start + Vector3(0, 0, 0.35), 1.2).set_trans(Tween.TRANS_SINE)
	await tw.finished
	play("cloth")
	await get_tree().create_timer(0.8).timeout
	_talisman.visible = false
	Story.set_flag("has_talisman")


# ----------------------------------------------------------------------------- 钟
func _setup_clock() -> void:
	for nm in ["Hour", "Minute", "Second"]:
		var n := model.find_child("Spin_Clock" + nm, true, false) as Node3D
		if n:
			_hands[nm] = [n, n.basis]
	_pendulum = model.find_child("Spin_Pendulum", true, false) as Node3D
	if _pendulum:
		_pendulum_rest = _pendulum.basis
	_update_clock(0.0)


func spin_speed(nm: String) -> float:
	return 2.2 if nm == "Spin_Fan" else 0.0


func _update_clock(delta: float) -> void:
	if _clock_running:
		_clock_t += delta
	var sec := floorf(fmod(_clock_t, 60.0))   # 秒针一跳一跳的
	var mins := fmod(_clock_t / 60.0, 60.0)
	var hours := fmod(_clock_t / 3600.0, 12.0)
	for nm: String in _hands:
		var v: float = {"Hour": hours / 12.0, "Minute": mins / 60.0, "Second": sec / 60.0}[nm]
		var n: Node3D = _hands[nm][0]
		n.basis = (_hands[nm][1] as Basis) * Basis(Vector3.UP, -TAU * v)
	if _pendulum:
		var a := 0.12 * sin(_clock_t * PI) if _clock_running else 0.0
		_pendulum.basis = _pendulum_rest * Basis(Vector3.UP, a)


var _last_tick := 0


func _process(delta: float) -> void:
	super._process(delta)
	_update_clock(delta)
	if _clock_running and int(_clock_t) != _last_tick:
		_last_tick = int(_clock_t)
		audio.tick()


# ----------------------------------------------------------------------------- 茶的热气
func _add_steam() -> void:
	var a := model.find_child("Light_Steam", true, false) as Node3D
	if a == null:
		return
	var g := Gradient.new()
	g.set_color(0, Color(1, 1, 1, 1))
	g.set_color(1, Color(1, 1, 1, 0))
	var dot := GradientTexture2D.new()
	dot.gradient = g
	dot.fill = GradientTexture2D.FILL_RADIAL
	dot.fill_from = Vector2(0.5, 0.5)
	dot.fill_to = Vector2(1.0, 0.5)
	var m := StandardMaterial3D.new()
	m.billboard_mode = BaseMaterial3D.BILLBOARD_PARTICLES
	m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	m.albedo_texture = dot
	m.albedo_color = Color(0.9, 0.9, 0.88, 0.06)
	m.vertex_color_use_as_albedo = true
	m.specular_mode = BaseMaterial3D.SPECULAR_DISABLED
	var mesh := QuadMesh.new()
	mesh.size = Vector2(0.025, 0.025)
	mesh.material = m
	var p := GPUParticles3D.new()
	p.amount = 30
	p.lifetime = 2.4
	p.preprocess = 3.0
	p.local_coords = false
	p.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	var pm := ParticleProcessMaterial.new()
	pm.emission_shape = ParticleProcessMaterial.EMISSION_SHAPE_SPHERE
	pm.emission_sphere_radius = 0.02
	pm.direction = Vector3.UP
	pm.spread = 12.0
	pm.initial_velocity_min = 0.03
	pm.initial_velocity_max = 0.05
	pm.gravity = Vector3(0, 0.02, 0)
	pm.turbulence_enabled = true
	pm.turbulence_noise_scale = 0.6
	pm.turbulence_influence_min = 0.04
	pm.turbulence_influence_max = 0.08
	var curve := Curve.new()
	curve.add_point(Vector2(0, 0.4))
	curve.add_point(Vector2(1, 2.4))
	var ct := CurveTexture.new()
	ct.curve = curve
	pm.scale_curve = ct
	var ramp := Gradient.new()
	ramp.set_color(0, Color(1, 1, 1, 0))
	ramp.set_color(1, Color(1, 1, 1, 0))
	ramp.add_point(0.2, Color(1, 1, 1, 1))
	var rt := GradientTexture1D.new()
	rt.gradient = ramp
	pm.color_ramp = rt
	p.process_material = pm
	p.draw_pass_1 = mesh
	a.add_child(p)


func setup_audio(a: RoomAudio) -> void:
	a.floor_kind = "terrazzo"
	a.loop("rain_steel", Vector3(0.0, 1.85, -3.1), &"Outdoor", 3.0)
	a.loop("harbor", null, &"Outdoor")
	a.loop("fan_whir", pos_of("Spin_Fan"), &"Room", 1.5)
	a.loop("fluoro_buzz", pos_of("Tube_A"), &"Room", 0.8)
	var desk := pos_of("Use_Contract")
	var clock := pos_of("Use_Clock")
	a.sources = {
		"clock_tick": clock, "clock_tock": clock, "clock_stop": clock, "door_open": pos_of("Use_Door"),
		"pen_write": desk, "ink_press": pos_of("Use_InkPad"), "thumb_press": desk, "cloth": desk,
	}


var _horn_wait := 25.0


func _physics_process(delta: float) -> void:
	# 港里隔一阵有船拉一声汽笛
	_horn_wait -= delta
	if _horn_wait <= 0.0:
		_horn_wait = randf_range(50.0, 95.0)
		play("ship_horn")


# ----------------------------------------------------------------------------- 自动演示（--autoplay）
## 自己把第一章走一遍：进门 → 坐下 → 一路问到签字 → 站起来看钟（停了）→ 出门
func _autoplay() -> void:
	Story.auto_choices = ["怎么找到", "什么东西", "多深", "多少钱", "查我", "合同", "八字", "之前", "归位", "签"]
	await _pause(4.0)
	while Story.busy:
		await get_tree().process_frame
	await _walk_path([Vector2(-1.0, 1.6), Vector2(-0.15, 0.1)])
	uses.SitVisitor.activate()
	while not Story.flag("signed"):
		await get_tree().process_frame
	while Story.busy:
		await get_tree().process_frame
	await _pause(1.5)
	walker.stand_up()
	await _pause(1.5)
	await _walk_path([Vector2(1.1, 0.3), Vector2(1.6, -1.6)])
	await _use("Clock", true)
	await _walk_path([Vector2(1.5, -0.4), Vector2(-0.6, 1.4), Vector2(-1.5, 2.45)])
	await _use("Door", true)


func _pause(t: float) -> void:
	await get_tree().create_timer(t).timeout


func _walk_path(points: Array) -> void:
	for p: Vector2 in points:
		walker.move_to(p)
		while not walker.arrived():
			await get_tree().process_frame


func _use(nm: String, wait: bool) -> void:
	var it: Interactable = uses[nm]
	walker.look_toward(it.global_position, 3.0)
	await _pause(1.0)
	walker.look_toward(null)
	it.activate()
	await get_tree().process_frame
	if wait:
		while Story.busy or Story.ui.is_reading():
			await get_tree().process_frame
		await _pause(0.6)
