extends StoryRoom
## 序章「二〇七」：船厂单身宿舍（模型 blender/scripts/gen_dorm.py，台词 assets/story/dorm.dlg，剧情 docs/story.md）。
## 一九九八年八月二十八日夜，台风外围的暴雨。坐在床边醒过来 → 桌上的传呼机响 → 看看屋里的东西 →
## 有人敲门、脚步声走远、门缝底下塞进来一个湿信封 → 开门：楼道里一串湿脚印，只有来、没有回 → 出门，转到第一章。

const DLG := "res://assets/story/dorm.dlg"
const DOCS := "res://assets/story/docs/"
## 房间局部坐标（Godot：x 东、-z 北）。门洞在 z = 2.2，走廊在 z ∈ [2.44, 4.24]
const CORRIDOR_Z := 2.75

var _pager: Node3D
var _pager_beep := false
var _pager_t := 0.0
var _pager_base := Transform3D.IDENTITY
var _envelope: Node3D
var _radio_on := false
var _crane_lights: Array[Light3D] = []
var _leaving := false
var _knock_timer := -1.0
var _backdrop: ShaderMaterial

## 窗外 150 米以外和天空：Cycles 预渲染的全景条（blender/scripts/render_backdrop.py 渲，图在 BACKDROP_DIR），
## 贴在以窗户眼点为圆心、半径 BACKDROP_R 的一段圆柱面上。眼点、水平范围（正北左右各 BACKDROP_U 度）、
## 竖直范围（tan(仰角)，BACKDROP_V）和 render_backdrop.py 的 EYE、U_DEG、V_MIN/V_MAX 同步
const BACKDROP_DIR := "res://assets/textures/backdrop/"
const BACKDROP_EYE := Vector3(0.0, 1.62, -2.34)
const BACKDROP_U := 80.0
const BACKDROP_V := Vector2(-0.0874887, 0.8433315)
const BACKDROP_R := 600.0
## 远处那盏快坏的钠灯（render_backdrop.py 的 FLICKER_LAMP：方位角、水平距离、灯头比眼睛高多少，米）
const BACKDROP_FLICKER := Vector3(-36.0, 230.0, 7.03)
## 闪电最亮那一下体积雾往前散射的亮度（闪电的颜色）：圆柱不吃雾，自己补上，和圆柱外面的天、3D 近景前面那层雾对上
const BACKDROP_FLASH_FOG := Color(0.70, 0.765, 0.9)
## 闪电时远处的雨雾也被照亮：深度雾换成冷白（sRGB），亮度按闪电亮度往这边插。不然 150 米处 3D 地面的雾还是暗橙，
## 全景条已经亮了，地平线上一道明暗交界
const FLASH_FOG_COLOR := Color(0.62, 0.66, 0.74)
const FLASH_FOG_ENERGY := 0.5
var _fog_base := Color.BLACK
var _fog_base_energy := 0.0
var _fog_flashing := false


func props() -> Dictionary:
	return {
		"Anchor_Bed": {"asset": "old_bed_frame"},
		"Anchor_BoxBed1": {"asset": "cardboard_box_01"},
		"Anchor_BoxBed2": {"asset": "cardboard_box_01", "scale": 0.85},
		"Anchor_AlarmClock": {"asset": "alarm_clock_01"},
		"Anchor_Radio": {"asset": "cassette_player"},
		"Anchor_Pears": {"asset": "food_pears_asian_01"},
		"Anchor_Chair": {"asset": "painted_wooden_chair_02", "scale": 0.78},   # 座面 0.45 米（原大 0.58，坐下腿埋进椅面）
		"Anchor_Bucket": {"asset": "wooden_bucket_01"},
		"Anchor_Suitcase": {"asset": "cardboard_box_01", "scale": 0.9},
		"Anchor_Cabinet": {"asset": "painted_wooden_cabinet"},
		"Anchor_Pot": {"asset": "pot_enamel_01"},
		"Anchor_Boots": {"asset": "rubber_boots", "keep": ["rubber_boots_dirty_l", "rubber_boots_dirt_r"],
			"center": true},
		"Anchor_Trash": {"asset": "trashbag", "scale": 0.7},
		"Anchor_CorBulb": {"asset": "lightbulb_01"},
		"Anchor_CorBulbDead": {"asset": "lightbulb_01"},
	}


## 台风前夜十点五十：主光是台灯的一圈暖光；窗外的钠灯透过防盗窗把栅格投进屋里（西墙、床、蚊帐上）；
## 夜空的余光只够看清窗边的轮廓；门缝底下漏进来一线楼道的暖光。屋里大部分是暗的——开场要压抑
const TUBE_COLOR := Color(0.84, 0.95, 0.9)
const SODIUM := Color(1.0, 0.55, 0.22)


func lights() -> Dictionary:
	return {
		# 日光灯：一长条面光（1.2 m × 5 cm，沿东西），偏冷偏绿，软阴影；屋里有点潮气，光里看得见浮尘
		"Light_Tube": {"area": Vector2(0.05, 1.2), "up": Vector3.RIGHT, "offset": Vector3(0, -0.01, 0),
			"color": TUBE_COLOR, "energy": 0.6, "range": 6.0, "nbias": 1.5, "specular": 0.25, "fog": 0.2,
			"flicker": 0.05, "flicker_speed": 9.0},
		# 灯管往上照亮一圈天花板（面光只朝下），跟着日光灯开关
		"TubeUp": {"at": "Light_Tube_Main", "offset": Vector3(0, 0.05, 0), "with": "Light_Tube_Main",
			"color": TUBE_COLOR, "energy": 0.08, "range": 1.4, "atten": 1.5, "shadow": false, "specular": 0.0, "fog": 0.0},
		# 台灯：暖黄，照亮桌面一圈，影子软一点
		"Light_DeskLamp": {"spot": true, "color": Color(1.0, 0.74, 0.46), "energy": 2.4, "range": 2.6, "angle": 52.0,
			"soft": 1.2, "atten": 1.2, "size": 0.05, "fog": 0.15, "specular": 0.3},
		# 灯罩往后、往上漏的一点光（照窗框、窗帘、墙）
		"LampSpill": {"at": "Light_DeskLamp", "offset": Vector3(-0.03, 0.05, 0), "color": Color(1.0, 0.72, 0.45),
			"energy": 0.06, "range": 1.4, "atten": 1.4, "shadow": false, "specular": 0.0, "fog": 0.0},
		# 窗外路灯（钠灯，橙色），往下照着院子；雨丝在光里看得见
		"Light_Street": {"spot": true, "color": Color(1.0, 0.5, 0.18), "energy": 16.0, "range": 24.0, "angle": 62.0,
			"atten": 1.3, "size": 0.2, "fog": 0.6},
		# 同一盏路灯照进屋的那一束：灯头位置一盏 9° 的窄聚光只罩住窗洞，投影——防盗窗、窗框的栅格印在西墙、床和蚊帐上
		"StreetProj": {"spot": true, "pos": Vector3(3.3, 3.0, -9.5), "aim": Vector3(0.0, 1.5, -2.2), "color": SODIUM,
			"energy": 9.0, "range": 18.0, "angle": 9.0, "soft": 0.4, "size": 0.2, "blur": 1.0, "specular": 0.3,
			"fog": 0.5},
		# 夜空的余光：窗洞里一块很暗的灰色面光（不投影，只给窗边的轮廓）
		"NightSky": {"area": Vector2(1.5, 1.45), "pos": Vector3(0.0, 1.62, -2.28), "facing": Vector3.BACK,
			"color": Color(0.55, 0.55, 0.6), "energy": 0.05, "range": 6.0, "shadow": false, "specular": 0.2, "fog": 0.0},
		# 门缝底下：楼道的灯从门下面漏进来一线（薄薄一条面光贴着地面朝屋里）
		"DoorGap": {"area": Vector2(0.86, 0.02), "pos": Vector3(1.0, 0.03, 2.16), "facing": Vector3(0, -0.6, -1),
			"color": Color(1.0, 0.66, 0.36), "energy": 3.0, "range": 1.6, "shadow": false, "specular": 0.0, "fog": 0.0},
		# 闪电：窗口一整块冷白面光（投影：防盗窗的硬影子一下子打满屋），只在闪的那一下亮
		"FlashWin": {"area": Vector2(1.5, 1.45), "pos": Vector3(0.0, 1.62, -2.3), "facing": Vector3(0, -0.25, 1),
			"color": Color(0.78, 0.85, 1.0), "energy": 0.0, "flash": 0.25, "range": 8.0, "specular": 0.6, "fog": 0.4},
		"Light_Corridor": {"color": Color(1.0, 0.68, 0.38), "energy": 0.9, "range": 5.0, "atten": 1.4, "size": 0.03,
			"fog": 0.6, "flicker": 0.4, "flicker_speed": 6.0},
		"Light_CorWindow": {"spot": true, "color": Color(1.0, 0.5, 0.2), "energy": 0.6, "range": 4.0, "angle": 40.0,
			"shadow": false},
		"Light_CraneRed": {"color": Color(1.0, 0.08, 0.05), "energy": 6.0, "range": 8.0, "shadow": false, "fog": 2.0},
		# 船台的高杆灯：远远照着船壳、吊车腿，雨在光里成一片雾
		"Light_Yard": {"spot": true, "color": Color(1.0, 0.55, 0.22), "energy": 60.0, "range": 60.0, "angle": 50.0,
			"atten": 1.0, "shadow": false, "fog": 1.5},
	}


## 台风外围的暴雨：窗外院子上空，风从东北往西南斜着吹；夜里只有被路灯、高杆灯照到的那几片看得见
func rain_config() -> Dictionary:
	return {"min": Vector3(-14.0, -3.65, -30.0), "max": Vector3(14.0, 12.0, -2.75), "count": 36000,
		"wind": Vector2(-3.0, 2.5), "gust": 0.45, "fall_speed": 8.5, "brightness": 1.2}


## 自动曝光（见 story_room.gd 的 _setup_lens）：开灯转身看屋里那一下亮，三四秒里慢慢落回来（落到不开时的 0.8 倍）；
## 关灯以后先黑一下再稍稍看清（暗着时只比不开亮 0.15 档左右，开场还是那么暗）。
## 曝光只在 0.7~1.1 倍之间变：最低 / 最高感光度把测到的场景亮度夹在 0.09~0.14，曝光 = scale / 亮度。
## 台灯下看纸、贴着白墙最多压暗半档；闪电只有零点几秒，来不及压（录像实测）。想让暗处「慢慢看清」更明显就把 ae_min 往下调
func lens_config() -> Dictionary:
	return {"auto_exposure": 0.1, "ae_min": 73.0, "ae_max": 114.0}


## 光照贴图：日光灯关着（开场）、开着各烘一份，开关灯时换（见 room_lightmap.gd）
func lightmap_variants() -> Dictionary:
	return {"tube": "Light_Tube_Main"}


## 龙门吊顶上的红色障碍灯一闪一闪的，不烘进光照贴图
func lightmap_skip_lights() -> Array:
	return ["Light_CraneRed"]


func use_config() -> Dictionary:
	return {
		"Pager": {"prompt": "看传呼", "size": 0.06, "reach": 1.4},
		"Bill": {"prompt": "看催款单", "size": 0.1},
		"Bankbook": {"prompt": "看存折", "size": 0.06},
		"Discharge": {"prompt": "看退伍证", "size": 0.06},
		"Calendar": {"prompt": "看挂历", "size": 0.22},
		"Photo": {"prompt": "看照片", "size": 0.08},
		"Radio": {"prompt": "开收音机", "size": 0.08},
		"Mirror": {"prompt": "照镜子", "size": 0.16, "reach": 1.3},
		"Window": {"prompt": "看窗外", "size": 0.5, "reach": 1.6},
		"Award": {"prompt": "看奖状", "size": 0.2, "reach": 2.0},
		"Switch": {"prompt": "开灯", "size": 0.06, "reach": 1.3},
		"Door": {"prompt": "开门", "size": 0.35, "reach": 1.5},
		"Envelope": {"prompt": "捡起信封", "size": 0.12, "reach": 1.9, "enabled": false},
		"Thermos": {"size": 0.07, "lines": ["（空的。）"]},
		"Noodles": {"size": 0.07, "lines": ["（晚饭。）"]},
		"Clock": {"size": 0.06, "lines": ["（十点五十。）"]},
		"Sweater": {"size": 0.15, "lines": ["（妈织的毛衣。三伏天，用不上。）",
			"（她住院前织到一半，剩下几针是隔壁床的阿姨帮着收的。）"], "again": ["（……）"]},
		"Bed": {"prompt": "坐在床边", "size": 0.3},
		"Wardrobe": {"size": 0.3, "lines": ["（几件换洗衣服。军装压在最底下。）"]},
		"Stove": {"size": 0.1, "lines": ["（电炉丝断过一回，拿铁丝绞上的。）"]},
	}


func paper_config() -> Dictionary:
	return {
		"Bill": {"text_path": DOCS + "bill.txt", "age": 0.25, "stains": 0.35, "folds": Vector2(1, 2), "paper_seed": 3.0,
			"tint": Color(0.9, 0.88, 0.8),
			"stamps": [[Vector2(930, 1440), 120, "白沙门县人民医院", "财务专用章", 12.0]],
			"writing": [[Vector2(140, 1610), "480×12＝5760　　差 32656", 40, "hand", Color(0.25, 0.25, 0.28, 0.85), -2.0]]},
		"Calendar": {"text_path": DOCS + "calendar.txt", "paper_size": Vector2i(760, 1100), "margin": Vector2(40, 30), "line_spacing": 0,
			"age": 0.2, "stains": 0.1, "paper_seed": 5.0, "tint": Color(0.94, 0.92, 0.86),
			"circles": [[Vector2(83, 940), 40.0]],
			"writing": [[Vector2(120, 1010), "海生生日", 34, "hand", Color(0.7, 0.08, 0.07, 0.9), -6.0]]},
		"Award": {"text_path": DOCS + "award.txt", "paper_size": Vector2i(1500, 1060), "margin": Vector2(150, 110),
			"age": 0.45, "stains": 0.2, "paper_seed": 8.0, "border": 46.0, "tint": Color(0.93, 0.88, 0.76),
			"stamps": [[Vector2(1180, 860), 115, "国营白沙门船厂", "", -6.0]]},
		"Newspaper": {"text_path": DOCS + "newspaper.txt", "paper_size": Vector2i(900, 1260), "margin": Vector2(50, 40),
			"age": 0.75, "stains": 0.5, "wet": 0.35, "paper_seed": 11.0, "tint": Color(0.76, 0.73, 0.64)},
		"Pager": {"text_path": DOCS + "pager.txt", "style": "lcd", "paper_size": Vector2i(480, 300),
			"margin": Vector2(26, 18), "font": "bold"},
		"Photo": {"text_path": "", "paper_size": Vector2i(600, 440), "tint": Color(0.86, 0.84, 0.78), "age": 0.6,
			"stains": 0.0, "paper_seed": 12.0},
	}


func _ready() -> void:
	room_name = "dorm"
	gi_path = "res://assets/gi/dorm_gi.res"
	floor_rect = Rect2(-1.65, -2.2, 3.3, 4.4)
	ceiling_height = 2.9
	super._ready()
	setup_lightning(Vector3(0.2, -0.5, 1.0))   # 从北边窗外劈过来
	lightning_light().light_angular_distance = 0.3
	lightning_energy = 4.4
	flash_sky = 16.0   # 闪的那一下夜空亮起来，窗外的吊车、楼成了剪影
	_pager = model.find_child("Hide_Pager", true, false) as Node3D
	if _pager:
		var scr := model.find_child("Paper_Pager", true, false)
		if scr:
			scr.reparent(_pager, true)
		_pager_base = _pager.transform
	_envelope = _make_envelope()
	if not (DebugArgs.has("bake-gi") or DebugArgs.has("lm-export")):
		_add_backdrop()
	for k in ["Light_CraneRed", "Light_CraneRed2"]:
		if lights_by_name.has(k):
			_crane_lights.append(lights_by_name[k])
	if ResourceLoader.exists("res://assets/textures/story/crew_photo.png"):
		papers.Photo.add_image(load("res://assets/textures/story/crew_photo.png"), Rect2(Vector2(24, 24), Vector2(552, 392)))
	_connect_uses()
	for k in ["Light_CraneRed", "Light_CraneRed2"]:
		add_glow(k, Color(1.0, 0.1, 0.06), 3.0, 3.0)
	add_glow("Light_Street", Color(1.0, 0.55, 0.22), 1.2, 1.5)
	# 开场日光灯是关着的，只有台灯和窗外的路灯；门边的开关能开
	set_light("Light_Tube_Main", DebugArgs.get_arg("tube") == "on")
	if DebugArgs.has("capture") or DebugArgs.has("at") or DebugArgs.has("bake-gi") or DebugArgs.has("lm-export") \
			or not Story.is_target("dorm"):
		return
	_intro()
	if DebugArgs.has("autoplay"):
		_autoplay()


func _connect_uses() -> void:
	uses.Pager.used.connect(func(_i: Interactable) -> void: _on_pager())
	uses.Door.used.connect(func(_i: Interactable) -> void: _on_door())
	uses.Envelope.used.connect(func(_i: Interactable) -> void: _on_envelope())
	uses.Radio.used.connect(func(_i: Interactable) -> void: _on_radio())
	uses.Bed.used.connect(func(_i: Interactable) -> void: walker.sit_at(seats.Bed))
	uses.Switch.used.connect(func(_i: Interactable) -> void: _toggle_tube())
	for nm in ["Bill", "Bankbook", "Discharge", "Calendar", "Photo", "Window", "Award"]:
		var lbl: String = nm.to_lower()
		uses[nm].used.connect(func(_i: Interactable) -> void: Story.run(DLG, lbl, self))
	uses.Mirror.used.connect(func(it: Interactable) -> void:
		if not _tube_on:
			it.times -= 1
			Story.run(DLG, "mirror_dark", self)
		else:
			Story.run(DLG, "mirror" if it.times <= 1 else "mirror_again", self))


func _intro() -> void:
	walker.sit_at(seats.Bed, true)
	Story.ui.set_black(true)
	await get_tree().create_timer(0.6).timeout
	await Story.ui.show_card("序章　二〇七", "一九九八年八月二十八日　农历七月初七　夜")
	Story.ui.fade_in(2.5)
	await get_tree().create_timer(1.5).timeout
	await Story.run(DLG, "intro", self)
	await get_tree().create_timer(2.0).timeout
	_pager_beep = true


# ----------------------------------------------------------------------------- 对白里的命令
func on_cmd(cmd: String, args: Array) -> void:
	match cmd:
		"read":
			await _read(args[0])
		"wait":
			await get_tree().create_timer(float(args[0])).timeout
		"knock":
			play("knock")
			await get_tree().create_timer(1.6).timeout
		"steps":
			play("steps_away")
			await get_tree().create_timer(1.5).timeout
		"envelope":
			await _slide_envelope()
		"radio":
			_radio(args[0])
		"leave":
			_leaving = true
			Story.set_flag("chapter0_done")
			Story.goto_scene("office", "第一章　契", "一九九八年八月二十九日　下午三点　渔业公司老楼")


func _read(doc: String) -> void:
	var p: PaperDoc
	match doc:
		"bill":
			p = papers.Bill
		"photo":
			p = papers.Photo
		"calendar":
			p = papers.Calendar
		_:
			p = _loose_doc(doc)
	await Story.ui.read([p.get_texture()])


var _loose := {}


## 不贴在模型上的纸（退伍证、存折、信），读的时候才排版
func _loose_doc(doc: String) -> PaperDoc:
	if _loose.has(doc):
		return _loose[doc]
	var c: Dictionary
	match doc:
		"discharge":
			c = {"text_path": DOCS + "discharge.txt", "paper_size": Vector2i(980, 1360), "margin": Vector2(110, 120),
				"tint": Color(0.92, 0.89, 0.8), "age": 0.35, "folds": Vector2(1, 0), "paper_seed": 21.0,
				"stamps": [[Vector2(700, 1170), 110, "海军某部政治部", "", 8.0]]}
		"bankbook":
			c = {"text_path": DOCS + "bankbook.txt", "paper_size": Vector2i(1240, 900), "margin": Vector2(70, 60),
				"tint": Color(0.86, 0.9, 0.84), "age": 0.3, "folds": Vector2(1, 0), "paper_seed": 22.0}
		"letter":
			c = {"text_path": DOCS + "letter.txt", "font": "brush", "paper_size": Vector2i(1100, 1500),
				"margin": Vector2(110, 120), "tint": Color(0.93, 0.9, 0.82), "age": 0.15, "wet": 0.55,
				"folds": Vector2(0, 2), "paper_seed": 23.0, "line_spacing": 18}
	_loose[doc] = make_doc(c)
	return _loose[doc]


# ----------------------------------------------------------------------------- 传呼机
func _on_pager() -> void:
	if not Story.flag("pager_read"):
		_pager_beep = false
		await Story.ui.read([papers.Pager.get_texture()])
		await Story.run(DLG, "pager", self)
		_knock_timer = 9.0
	else:
		await Story.ui.read([papers.Pager.get_texture()])
		await Story.run(DLG, "pager_again", self)


## 来传呼：哔哔三声一组，机子在桌上震着挪；屏幕亮绿灯
func _update_pager(delta: float) -> void:
	if _pager == null:
		return
	var lcd := model.find_child("Paper_Pager", true, false) as MeshInstance3D
	var lit := _pager_beep or Story.ui.is_reading()
	if lcd and lcd.material_override:
		(lcd.material_override as StandardMaterial3D).emission_energy_multiplier = 0.6 if lit else 0.0
	if not _pager_beep:
		return
	_pager_t += delta
	var phase := fmod(_pager_t, 3.0)
	var buzz := phase < 1.2 and fmod(phase, 0.4) < 0.22
	if buzz:
		var j := Vector3(randf_range(-1, 1), 0, randf_range(-1, 1)) * 0.0006
		_pager.transform = _pager.transform.translated(j)
		_pager.rotate_y(randf_range(-0.004, 0.004))
	if phase < delta + 0.001:
		play("pager_beep")


# ----------------------------------------------------------------------------- 门、信
func _on_door() -> void:
	if not Story.flag("knocked"):
		await Story.run(DLG, "door_late", self)
		return
	if door_open < 0.5:
		uses.Door.prompt = "关门"
		play("door_open")
		swing_door(1.0, 1.6)
		if not Story.flag("saw_prints"):
			await get_tree().create_timer(1.0).timeout
			walker.look_toward(to_global(Vector3(0.6, 0.0, 3.4)), 2.0)
			await Story.run(DLG, "door_open", self)
			walker.look_toward(null)
	else:
		uses.Door.prompt = "开门"
		play("door_close")
		swing_door(0.0, 0.9)


## 门往屋里开（门轴在东边）
func door_angle() -> float:
	return -100.0


func _make_envelope() -> Node3D:
	var a := model.find_child("Anchor_Envelope", true, false) as Node3D
	if a == null:
		return null
	var mi := MeshInstance3D.new()
	var bm := BoxMesh.new()
	bm.size = Vector3(0.22, 0.004, 0.11)
	mi.mesh = bm
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color(0.62, 0.58, 0.48)
	mat.roughness = 0.35   # 湿的
	mi.material_override = mat
	mi.position = Vector3(0, 0.002, 0)
	a.add_child(mi)
	a.visible = false
	return a


## 信从门缝底下塞进来
func _slide_envelope() -> void:
	if _envelope == null:
		return
	var end := _envelope.position
	_envelope.position = end + _envelope.global_basis.inverse() * Vector3(0, 0, 0.45)
	_envelope.visible = true
	play("envelope")
	var tw := create_tween()
	tw.tween_property(_envelope, "position", end, 0.9).set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_OUT)
	await tw.finished
	uses.Envelope.enabled = true


func _on_envelope() -> void:
	uses.Envelope.enabled = false
	_envelope.visible = false
	await Story.run(DLG, "envelope", self)


# ----------------------------------------------------------------------------- 日光灯
var _tube_on := false


## 开日光灯：启辉器「嗒、嗒」几下，灯管两头先发红、中间闪几下才亮稳
func _toggle_tube() -> void:
	play("switch")
	_tube_on = not _tube_on
	uses.Switch.prompt = "关灯" if _tube_on else "开灯"
	if not _tube_on:
		set_light("Light_Tube_Main", false)
		audio.set_loop("fluoro_buzz", false)
		return
	play("tube_start")
	for k in [0.15, 0.08, 0.3, 0.06, 0.12]:
		set_light("Light_Tube_Main", true, 0.3)
		await get_tree().create_timer(k * 0.6).timeout
		set_light("Light_Tube_Main", false)
		await get_tree().create_timer(k).timeout
		if not _tube_on:
			return
	set_light("Light_Tube_Main", true)
	audio.set_loop("fluoro_buzz", true)


# ----------------------------------------------------------------------------- 收音机
func _on_radio() -> void:
	if _radio_on:
		await Story.run(DLG, "radio_off", self)
	else:
		await Story.run(DLG, "radio_on", self)


func _radio(state: String) -> void:
	_radio_on = state != "off"
	uses.Radio.prompt = "关收音机" if _radio_on else "开收音机"
	play("switch")
	audio.set_radio(state)


# ----------------------------------------------------------------------------- 窗外远景
func _add_backdrop() -> void:
	var night := load(BACKDROP_DIR + "dorm_night.exr") as Texture2D
	if night == null:
		return
	# 圆柱面：水平每 2° 一段（600 米远，弦和弧差不到一个像素），竖直一段（中心圆柱投影在高度上本来就是线性的）
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var n := int(BACKDROP_U)
	for i in n + 1:
		var u := float(i) / n
		var a := deg_to_rad(lerpf(-BACKDROP_U, BACKDROP_U, u))
		var d := Vector3(sin(a), 0.0, -cos(a)) * BACKDROP_R
		st.set_uv(Vector2(u, 1.0))
		st.add_vertex(d + Vector3.UP * BACKDROP_R * BACKDROP_V.x)
		st.set_uv(Vector2(u, 0.0))
		st.add_vertex(d + Vector3.UP * BACKDROP_R * BACKDROP_V.y)
	for i in n:
		for k in [0, 1, 2, 1, 3, 2]:
			st.add_index(i * 2 + k)
	_backdrop = ShaderMaterial.new()
	_backdrop.shader = preload("res://assets/shaders/backdrop.gdshader")
	_backdrop.set_shader_parameter("night_tex", night)
	_backdrop.set_shader_parameter("flash_tex", load(BACKDROP_DIR + "dorm_flash.exr"))
	_backdrop.set_shader_parameter("glow_tex", load(BACKDROP_DIR + "dorm_glow.png"))
	_backdrop.set_shader_parameter("tan_range", BACKDROP_V)
	_backdrop.set_shader_parameter("sky_fade", Vector2(tan(deg_to_rad(10.0)), BACKDROP_V.y))
	var ff := BACKDROP_FLASH_FOG
	_backdrop.set_shader_parameter("flash_fog", Vector3(ff.r, ff.g, ff.b))
	if lightning_light():
		_backdrop.set_shader_parameter("flash_dir", lightning_light().global_basis.z)
	var fl := BACKDROP_FLICKER
	_backdrop.set_shader_parameter("flicker_uv", Vector2((fl.x + BACKDROP_U) / (2.0 * BACKDROP_U),
		1.0 - (fl.z / fl.y - BACKDROP_V.x) / (BACKDROP_V.y - BACKDROP_V.x)))
	# 截图时窗户不灭、灯不闪（--flicker=on 照常）
	_backdrop.set_shader_parameter("animate", 0.0 if DebugArgs.capturing() and DebugArgs.get_arg("flicker") != "on" else 1.0)
	var mi := MeshInstance3D.new()
	mi.name = "Backdrop"
	mi.mesh = st.commit()
	mi.material_override = _backdrop
	mi.position = BACKDROP_EYE
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	mi.gi_mode = GeometryInstance3D.GI_MODE_DISABLED
	add_child(mi)


## 每帧：闪电那一下全景条换成闪电版、远处的深度雾跟着亮；圆柱往上淡到的夜空颜色跟着环境背景（闪电时 story_room 把它调亮）
func _update_backdrop() -> void:
	if _backdrop == null:
		return
	var env := ($WorldEnvironment as WorldEnvironment).environment
	var c := env.background_color.srgb_to_linear() * env.background_energy_multiplier
	var f := clampf(flash_level(), 0.0, 1.0)
	_backdrop.set_shader_parameter("sky_top", Vector3(c.r, c.g, c.b))
	_backdrop.set_shader_parameter("flash_amt", f)
	# 深度雾只在闪的时候动（闪之前记下原来的颜色、亮度，闪完放回去），平时不碰
	if f > 0.0 and not _fog_flashing:
		_fog_base = env.fog_light_color
		_fog_base_energy = env.fog_light_energy
	if f > 0.0 or _fog_flashing:
		env.fog_light_color = _fog_base.lerp(FLASH_FOG_COLOR, f)
		env.fog_light_energy = lerpf(_fog_base_energy, FLASH_FOG_ENERGY, f)
	_fog_flashing = f > 0.0


# ----------------------------------------------------------------------------- 每帧
func _process(delta: float) -> void:
	super._process(delta)
	_update_backdrop()
	_update_pager(delta)
	if _knock_timer > 0.0 and not Story.busy:
		_knock_timer -= delta
		if _knock_timer <= 0.0:
			Story.run(DLG, "knock", self)
	# 红色航空障碍灯：一秒闪一下
	var on := fmod(Time.get_ticks_msec() / 1000.0, 1.5) < 0.2
	for l in _crane_lights:
		l.visible = on
	_update_street(delta)
	# 走到走廊里：信看过了就出门（转到第一章），没看过就被拦回来
	if not _leaving and not Story.busy and walker.feet().y > CORRIDOR_Z:
		if Story.flag("letter_read"):
			Story.run(DLG, "leave", self)
		else:
			walker.teleport(Vector2(walker.feet().x, 2.0), rad_to_deg(walker.yaw))
			Story.run(DLG, "leave_no_letter", self)


## 路灯（钠灯）快坏了：每隔半分钟到一分钟抽一阵，两秒里忽明忽暗、发红，屋里防盗窗的影子跟着一闪一闪。截图时不抽
var _street_t := 25.0
var _street_k := 1.0


func _update_street(delta: float) -> void:
	if DebugArgs.capturing():
		return
	_street_t -= delta
	var k := 1.0
	if _street_t < 0.0:
		var t := -_street_t
		k = 0.3 + 0.7 * absf(sin(t * 17.0) * sin(t * 5.3))
		if t > 2.0:
			_street_t = randf_range(30.0, 60.0)
	_street_k = lerpf(_street_k, k, 1.0 - exp(-delta * 30.0))
	for nm in ["Light_Street", "StreetProj"]:
		var l: Light3D = lights_by_name.get(nm)
		if l:
			l.light_energy = float(l.get_meta("base_energy")) * _street_k
			l.light_color = SODIUM.lerp(Color(1.0, 0.3, 0.1), 1.0 - _street_k)


func setup_audio(a: RoomAudio) -> void:
	a.floor_kind = "concrete"
	a.loop("rain_window", Vector3(0.0, 1.6, -2.3), &"Outdoor", 2.5)
	a.loop("fan_whir", pos_of("Spin_Fan"), &"Room", 1.5)
	a.loop("fluoro_buzz", pos_of("Tube_Main"), &"Room", 0.8)
	a.set_loop("fluoro_buzz", false)
	var door := pos_of("Use_Door")
	a.sources = {
		"radio": pos_of("Use_Radio"), "radio_static": pos_of("Use_Radio"), "pager_beep": pos_of("Use_Pager"),
		"knock": door, "door_open": door, "door_close": door, "envelope": door + Vector3(0, -1.0, -0.1),
		"steps_away": door + Vector3(-1.5, 0.0, 1.3), "switch": pos_of("Use_Switch"), "tube_start": pos_of("Tube_Main"),
	}


# ----------------------------------------------------------------------------- 自动演示（--autoplay）
## 自己把序章走一遍：起身 → 看传呼 → 照镜子 → 看催款单、挂历 → 等敲门 → 捡信 → 开门 → 出门
func _autoplay() -> void:
	while not _pager_beep:
		await get_tree().process_frame
	await _pause(2.0)
	walker.stand_up()
	await _pause(1.5)
	await _walk_path([Vector2(-0.2, -0.5), Vector2(0.45, -1.15)])
	await _use("Pager", true)
	await _walk_path([Vector2(0.95, -1.05)])
	await _use("Mirror", true)
	await _walk_path([Vector2(0.6, 0.2), Vector2(0.9, 1.75)])
	await _use("Switch", false)
	await _pause(4.0)
	await _walk_path([Vector2(0.6, 0.2), Vector2(0.95, -1.05)])
	await _use("Mirror", true)
	await _walk_path([Vector2(0.5, -1.25)])
	await _use("Bill", true)
	await _walk_path([Vector2(0.95, -1.4)])
	await _use("Calendar", true)
	while not Story.flag("knocked"):
		await get_tree().process_frame
	await _pause(1.0)
	await _walk_path([Vector2(0.6, -0.4), Vector2(0.75, 1.2), Vector2(0.85, 1.85)])
	await _use("Envelope", true)
	await _walk_path([Vector2(1.0, 1.6)])
	await _use("Door", true)
	await _pause(1.0)
	walker.walk_areas = walk_areas(true)
	await _walk_path([Vector2(1.0, 2.3), Vector2(1.0, 3.1)])


func _pause(t: float) -> void:
	await get_tree().create_timer(t).timeout


func _walk_path(points: Array) -> void:
	for p: Vector2 in points:
		walker.move_to(p)
		while not walker.arrived():
			await get_tree().process_frame


## 转过去看着它、等一下、按 E；wait：等对白、纸都放下了再往下走
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
