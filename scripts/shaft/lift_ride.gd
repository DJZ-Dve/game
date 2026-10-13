extends Node3D
## 开局后的下井（docs/design.md「八、开场 · 下井」）：电脑上匹配好、主机点了开始，四个人就坐在冰井升降机的轿厢里往下走——
## 这一段就是加载画面：后台加载下一个场景（现在是潜艇 scenes/deep_sea.tscn，以后是井底的前进基地），
## 所有人都加载好了、而且坐够 MIN_RIDE 秒，主机说“到了”（Net.ride_go），大家一起黑场进下一个场景。
## 不能走动、没有按钮：坐在两侧的折叠凳上，用鼠标转头看。朝井心那面是钢丝网，看得见整口井：一圈圈走台和灯从脚下涨上来、
## 从头顶滑走，冰壁上喷的深度标记一个比一个深；推拉门外面每 2.4 秒擦过一圈走台的断头。对面坐着队友（替身，
## 头跟着他们的鼠标转，Net.send_ride_look），座位按岗位分（驾驶、声呐在左边，轮机、潜水员在右边）。
##
## 井是“跑步机”：轿厢一直停在原点，冰井一圈圈往上滚，滚出视野的那一圈挪到最下面、换成新的圈号（ShaftKit 的网格反复用，
## 冰壁的网格 WALL_CYCLE 段一循环，花纹按真正的高度接着走）。每圈的灯怎么排、哪盏坏了按圈号定（同一圈每次都一样）。
## 灯：离镜头近的几圈挂真的灯（洗墙灯、往井里照的灯、缺口两边照走台的灯），再远只挂几盏洗墙灯，更远的光斑、
## 冰上的光圈在着色器里算；按离镜头的距离渐变，圈滚过来时不跳。
## 坐标：井轴是 Y 轴（和 ShaftKit 一样），轿厢挂在方位角 0 的导轨上，地板面在 y = 0。
##
## 调试：--scene=lift 直接从这里开始（单人）；--ride-hold 一直坐着不到站（截图、看效果）；--depth=米 从这个深度开始；
##       --ride-crew=N 单人时往空座位上放 N 个假队友（看满员的样子；到站不等他们；--ride-faces=a,b,c 他们用第几个捏脸预设）；--ride-still 轿厢停着不动（截图用，配 --depth 定在某个位置）；--seat=0~3 坐哪个座位；--ride-look=度,度 坐下以后视线往左右、上下偏多少；--ride-next=场景 到站以后进哪个场景

const SPEED := 5.0             # 往下走的速度（米/秒）：20 公里单程一个多小时
const START_DEPTH := 96.0      # 进来的时候轿厢已经下到多深了（刚过第 8 圈）
const MIN_RIDE := 12.0         # 至少坐这么久（加载再快也得看两眼井）
const FIRST_LOOK := 45.0       # 坐下时视线先往井心那边偏多少度（对着坐的是对面的门，井在侧面）
const RINGS_ABOVE := 9         # 头顶建几圈、脚下建几圈（再远的没进黑暗里了；顶板、地板挡着，看不到正上方、正下方）
const RINGS_BELOW := 12
const WALL_CYCLE := 8          # 冰壁的网格几段一循环（偶数：爬梯背后修平的那条冰跟着圈号单双交替）
const TEX_WRAP := 10           # 冰里的花纹按真正的高度接着走，每 WALL_CYCLE × TEX_WRAP 圈取一次模（float 的精度）
const NEAR := 30.0             # 离镜头这么近的圈挂真的灯
const MID := 110.0             # 再远到这里每圈只挂几盏洗墙灯
const SHADOW_NEAR := 15.0      # 缺口两边照走台的灯在这个距离以内投影（走台的栏杆、轿厢在格栅上拖影子）
const R := ShaftKit.R
const RING_STEP := ShaftKit.RING_STEP
const LAMPS := ShaftKit.LAMPS
const ARRIVE_TITLE := "一小时后"
const ARRIVE_SUB := "井底 · −20 000 m"
const CREW_BODY := preload("res://scripts/crew_body.gd")
const FONT := "res://assets/fonts/NotoSerifSC-VF.ttf"

## 轿厢地板面离井口多深（米）
var depth := START_DEPTH
var t := 0.0

var _kit: ShaftKit
var _cab: LiftCab
var _shaft: Node3D
var _slots: Array[Dictionary] = []   # 按圈号从小到大（从上往下）：见 _make_slot
var _walls_fine: Array = []          # 冰壁一段段的网格（WALL_CYCLE 段一循环）：近处 25 厘米一行、远处 1 米一行
var _walls_coarse: Array = []
var _vert: ArrayMesh                 # 一圈的竖着的东西（加热管、导轨、齿条、滑触线、桥架），每圈一样
var _shake := FastNoiseLite.new()
var _walker: RoomWalker
var _seat_yaw := 0.0                 # 自己座位的朝向（发给别人的视线是相对它的）
var _riders := {}                    # 别的玩家：peer id → Rider
var _next := ""
var _packed: PackedScene
var _ready_sent := false
var _arriving := false
var _hold := DebugArgs.has("ride-hold")
var _env: Environment
var _hint: Label
var _hum: AudioStreamPlayer
var _creak_t := 6.0
var _look_t := 0.0


func _ready() -> void:
	# 先把下一个场景丢给后台线程去加载，再搭冰井（搭的这一两秒也在加载）
	_next = DebugArgs.get_arg("ride-next", Net.GAME_SCENE)
	_next = Story.SCENES.get(_next, _next)
	ResourceLoader.load_threaded_request(_next)
	if Net.players.is_empty():
		# 直接打开这个场景（--scene=lift）：没走大厅，当单人；--ride-crew=N 再放几个假队友（只在本机的名单上）
		Net.players = {Net.my_id(): {"name": Net.local_name, "role": Net.Role.PILOT, "look": Net.local_look}}
		Net.in_game = true
		# 假队友按预设轮着换脸（--ride-faces=a,b,c 指定用第几个预设）
		var faces := DebugArgs.get_arg("ride-faces", "0,1,2").split(",")
		for i in clampi(int(DebugArgs.get_arg("ride-crew", "0")), 0, 3):
			Net.players[1000 + i] = {"name": ["老周", "阿兰", "米沙"][i], "role": i + 1,
				"look": CrewLook.preset(int(faces[i % faces.size()]))}
	if DebugArgs.has("depth"):
		depth = float(DebugArgs.get_arg("depth"))
	_shake.seed = 5
	_shake.frequency = 1.0
	# 冰的次表面散射：灯照到冰上光会渗开一圈（离开场景时调回默认值）
	RenderingServer.sub_surface_scattering_set_scale(0.06, 0.02)
	_build_environment()
	_kit = ShaftKit.new()
	_build_shaft()
	_cab = LiftCab.new()
	_cab.detail = 0
	_cab.transform = LiftCab.mount(R, 0.0, 0.0)
	add_child(_cab)
	_build_crew()
	_build_particles()
	_build_audio()
	_build_hint()
	Net.ride_look.connect(_on_look)
	Net.ride_arrive.connect(_arrive)
	Net.roster_changed.connect(_sync_riders)
	_update(0.0)


func _process(delta: float) -> void:
	t += delta
	if not DebugArgs.has("ride-still"):
		depth += SPEED * delta
	_update(delta)
	_poll_loading()
	# 主机：都加载好了、坐够了，就说到了
	if Net.is_host() and not _hold and not _arriving and t > MIN_RIDE and Net.ride_all_ready():
		Net.ride_go()
	# 自己的视线发给别人（每秒 10 次，丢了也不要紧）
	_look_t -= delta
	if _look_t <= 0.0 and _walker:
		_look_t = 0.1
		Net.send_ride_look(angle_difference(_seat_yaw, _walker.yaw), _walker.pitch)


func _exit_tree() -> void:
	RenderingServer.sub_surface_scattering_set_scale(0.05, 0.01)


# ---------------------------------------------------------------------------- 加载、到站
func _poll_loading() -> void:
	if _ready_sent:
		return
	var st := ResourceLoader.load_threaded_get_status(_next)
	if st == ResourceLoader.THREAD_LOAD_LOADED:
		_packed = ResourceLoader.load_threaded_get(_next) as PackedScene
	elif st == ResourceLoader.THREAD_LOAD_IN_PROGRESS:
		return
	else:
		push_error("下井：后台加载 %s 失败，到站时再同步加载" % _next)
	_ready_sent = true
	Net.ride_mark_ready()


func _arrive() -> void:
	if _arriving:
		return
	_arriving = true
	_play("relay_drop_0", -6.0, 0.8)
	await Story.goto_scene(_packed if _packed else _next, ARRIVE_TITLE, ARRIVE_SUB)


# ---------------------------------------------------------------------------- 环境
func _build_environment() -> void:
	var env := Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color(0, 0, 0)
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	# 冰里透出来的散射光是蓝的：一层很淡的蓝色环境光
	env.ambient_light_color = Color(0.3, 0.55, 0.75)
	env.ambient_light_energy = 0.03
	env.tonemap_mode = Environment.TONE_MAPPER_AGX
	env.tonemap_exposure = 1.05
	env.ssao_enabled = true
	env.ssao_radius = 0.6
	env.ssao_intensity = 1.6
	env.ssr_enabled = false
	env.glow_enabled = true
	env.glow_intensity = 0.7
	env.glow_strength = 1.0
	env.glow_bloom = 0.03
	env.glow_blend_mode = Environment.GLOW_BLEND_MODE_SCREEN
	env.glow_hdr_threshold = 1.6
	# 远处没进黑暗里（井只建了头顶、脚下这么多圈）
	env.fog_enabled = true
	env.fog_mode = Environment.FOG_MODE_DEPTH
	env.fog_light_color = Color(0, 0, 0)
	env.fog_depth_begin = 40.0
	env.fog_depth_end = RINGS_BELOW * RING_STEP - 4.0
	env.fog_depth_curve = 1.4
	env.volumetric_fog_enabled = true
	env.volumetric_fog_density = 0.014
	env.volumetric_fog_albedo = Color(0.86, 0.9, 0.95)
	env.volumetric_fog_anisotropy = 0.62
	env.volumetric_fog_length = 90.0
	env.volumetric_fog_detail_spread = 1.6
	env.volumetric_fog_ambient_inject = 0.0
	env.volumetric_fog_temporal_reprojection_enabled = true
	env.adjustment_enabled = true
	env.adjustment_contrast = 1.06
	env.adjustment_saturation = 0.94
	_env = env
	var we := WorldEnvironment.new()
	we.environment = env
	add_child(we)


# ---------------------------------------------------------------------------- 冰井（跑步机）
func _build_shaft() -> void:
	_shaft = Node3D.new()
	_shaft.name = "Shaft"
	add_child(_shaft)
	# 冰壁：第 0~WALL_CYCLE-1 圈那一截（假的高度，首尾接成周期），近、远两档行距；切口都在两圈正中间，两档接得上
	var span := WALL_CYCLE * RING_STEP
	for step: float in [0.25, 1.0]:
		var ys: Array[float] = []
		var y := RING_STEP * 0.5
		while y > RING_STEP * 0.5 - span + 0.001:
			ys.append(y)
			y -= step
		ys.append(RING_STEP * 0.5 - span)
		var chunks := _kit.wall_chunks(ys, Vector2i(-1000000, 1000000), span)
		(_walls_fine if step < 0.5 else _walls_coarse).append_array(chunks.map(func(c: Dictionary) -> Mesh: return c.mesh))
	# 竖着的东西：一圈的那一截（上下各 6 米），合成一个多面的网格
	_vert = ArrayMesh.new()
	for m in _kit.verticals(RING_STEP * 0.5, -RING_STEP * 0.5):
		var src: ArrayMesh = m[0]
		_vert.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, src.surface_get_arrays(0))
		_vert.surface_set_material(_vert.get_surface_count() - 1, m[1])
	var g0 := ceili((depth - (RINGS_ABOVE * RING_STEP + RING_STEP * 0.5)) / RING_STEP)
	for i in RINGS_ABOVE + RINGS_BELOW + 1:
		var slot := _make_slot()
		_assign(slot, g0 + i)
		_slots.append(slot)


## 一圈：冰壁一段、竖着的一截、走台（格栅、钢结构、扶手）、下到下一圈的爬梯、灯具和灯罩、灯光
func _make_slot() -> Dictionary:
	var node := Node3D.new()
	_shaft.add_child(node)
	var mk := func(mat: Material) -> MeshInstance3D:
		var mi := MeshInstance3D.new()
		mi.material_override = mat
		node.add_child(mi)
		return mi
	var wall: MeshInstance3D = mk.call(_kit.ice_mat)
	wall.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	var vert: MeshInstance3D = mk.call(null)
	vert.mesh = _vert
	var slot := {"node": node, "wall": wall, "g": -1, "lod": -1,
		"grating": mk.call(_kit.grate_mat), "steel": mk.call(_kit.mat_steel), "rail": mk.call(_kit.mat_rail),
		"ladder": mk.call(null)}
	var mms := []
	for i in 3:
		var mm := MultiMesh.new()
		mm.transform_format = MultiMesh.TRANSFORM_3D
		mm.use_custom_data = i == 2
		mm.instance_count = LAMPS / 2 if i == 1 else LAMPS
		var mmi := MultiMeshInstance3D.new()
		mmi.multimesh = mm
		mmi.material_override = _kit.lens_mat if i == 2 else _kit.mat_lamp
		if i != 1:
			mmi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		node.add_child(mmi)
		mms.append(mm)
	slot.fixtures = mms[0]
	slot.washes = mms[1]
	slot.globes = mms[2]
	(mms[1] as MultiMesh).mesh = _kit.wash
	# 灯光（一套建好，按离镜头的距离开关、调亮度）：每隔一盏一个洗墙灯、每四盏一个往井里照的、缺口两边四盏照走台的
	var lights: Array = []
	for j in LAMPS:
		if j % 2 == 0:
			var wl := SpotLight3D.new()
			wl.spot_range = 15.0
			wl.spot_angle = 58.0
			wl.spot_attenuation = 1.2
			wl.spot_angle_attenuation = 0.55
			wl.light_size = 0.15
			wl.light_volumetric_fog_energy = 0.8
			node.add_child(wl)
			lights.append({"light": wl, "j": j, "kind": "wash"})
		if j % 4 == 1:
			var vl := SpotLight3D.new()
			vl.spot_range = 13.0
			vl.spot_angle = 70.0
			vl.spot_attenuation = 1.4
			vl.spot_angle_attenuation = 0.7
			vl.light_size = 0.09
			vl.light_volumetric_fog_energy = 1.6
			node.add_child(vl)
			lights.append({"light": vl, "j": j, "kind": "beam"})
		if j in [0, 1, LAMPS - 2, LAMPS - 1]:
			var sl := SpotLight3D.new()
			sl.spot_range = 3.2
			sl.spot_angle = 80.0
			sl.spot_attenuation = 1.6
			sl.spot_angle_attenuation = 0.7
			sl.light_size = 0.12
			sl.shadow_blur = 1.5
			sl.light_volumetric_fog_energy = 1.4
			node.add_child(sl)
			lights.append({"light": sl, "j": j, "kind": "deck"})
	slot.lights = lights
	return slot


## 这一格换成第 g 圈：灯怎么排、哪盏坏了按圈号定（同一圈每次都一样）
func _assign(slot: Dictionary, g: int) -> void:
	slot.g = g
	var rng := RandomNumberGenerator.new()
	rng.seed = hash(g * 7919 + 1998)
	var hatch := ShaftKit.ladder_a(g)
	slot.hatch = hatch
	var ring_off := rng.randf()
	slot.phase = ring_off
	var a0 := ShaftKit.lamp_a0()
	var spacing := ShaftKit.lamp_spacing()
	var lamps: Array = []
	var fix: MultiMesh = slot.fixtures
	var wash: MultiMesh = slot.washes
	var globes: MultiMesh = slot.globes
	for j in LAMPS:
		var la := a0 + spacing * (j + ring_off + rng.randf_range(-0.12, 0.12))
		var dead := rng.randf() < 0.05
		var faulty := not dead and rng.randf() < 0.04
		var tint := 1.0 if rng.randf() < 0.12 else maxf(rng.randf_range(-0.15, 0.15), 0.0)
		var p := MeshKit.pol(ShaftKit.LAMP_R, la, ShaftKit.LAMP_H)
		fix.set_instance_transform(j, Transform3D(Basis(Vector3.UP, -la), Vector3.ZERO))
		if j % 2 == 0:
			wash.set_instance_transform(j / 2, Transform3D(Basis(Vector3.UP, -ShaftKit.wash_a(la, hatch)), Vector3.ZERO))
		globes.set_instance_transform(j, Transform3D(Basis(), p) if not dead
			else Transform3D(Basis().scaled(Vector3(1.05, 0.2, 1.05)), p + Vector3(0, 0.072, 0)))
		globes.set_instance_custom_data(j, Color(0 if dead else 1, 0, tint, 0))
		lamps.append({"a": la, "pos": p, "dead": dead, "faulty": faulty, "tint": tint, "idx": g * LAMPS + j})
	slot.lamps = lamps
	# 灯光挂到各自的灯上
	for l in slot.lights:
		var lamp: Dictionary = lamps[l.j]
		var light: SpotLight3D = l.light
		var col := ShaftKit.LAMP_COLOR.lerp(ShaftKit.LAMP_COOL, lamp.tint)
		light.light_color = col
		var la: float = lamp.a
		var radial := Vector3(cos(la), 0, sin(la))
		match l.kind:
			"wash":
				# 洗墙灯：朝下、略往井壁偏，挂在两根斜撑正中间，光贴着冰面扫下去
				var wa := ShaftKit.wash_a(la, hatch)
				var wr := Vector3(cos(wa), 0, sin(wa))
				var wdir := (wr * (0.22 + 0.06 * ShaftKit.hash3(g, l.j, 1)) + Vector3.DOWN).normalized()
				light.transform = Transform3D(Basis.looking_at(wdir, wr), MeshKit.pol(R - 0.55, wa, -0.58))
				l.base = 7.0 * (0.8 + 0.35 * ShaftKit.hash3(g, l.j, 2))
				# 隔一盏的那几盏在远处代表这一片（每四盏一个，亮度顶上其余几盏）
				l.mid = l.j % 4 == 2
			"beam":
				var vdir := (-radial + Vector3(0, -0.45, 0)).normalized()
				light.transform = Transform3D(Basis.looking_at(vdir, Vector3.UP), lamp.pos)
				l.base = 2.0
				l.mid = false
			"deck":
				var dir := (Vector3.DOWN - radial * 0.35).normalized()
				light.transform = Transform3D(Basis.looking_at(dir, radial), lamp.pos)
				l.base = ShaftKit.DECK_LIGHT
				l.mid = false
	(slot.grating as GeometryInstance3D).set_instance_shader_parameter("hatch_a", hatch)
	(slot.grating as GeometryInstance3D).set_instance_shader_parameter("ring_phase", ring_off)
	(slot.ladder as MeshInstance3D).transform = Transform3D(Basis(Vector3.UP, -hatch), Vector3.ZERO)
	# 冰壁：第 g 圈用第 m 段网格（假的高度 -12m），挪回第 g 圈；花纹按真正的高度接着走（tex_y，取过模），标记写真正的圈号
	var m := posmod(g, WALL_CYCLE)
	var tex_y := -RING_STEP * WALL_CYCLE * posmod(floori(float(g) / WALL_CYCLE), TEX_WRAP)
	var wall: MeshInstance3D = slot.wall
	wall.position = Vector3(0, RING_STEP * m, 0)
	wall.set_instance_shader_parameter("tex_y", tex_y)
	wall.set_instance_shader_parameter("ring_y", -RING_STEP * m + tex_y)
	wall.set_instance_shader_parameter("ring_base", float(g - m - WALL_CYCLE * posmod(floori(float(g) / WALL_CYCLE), TEX_WRAP)))
	wall.set_instance_shader_parameter("ring_phase", ring_off)
	slot.lod = -1


## 按离镜头的距离换档（网格、灯具的细节）
func _set_lod(slot: Dictionary, lod: int) -> void:
	if slot.lod == lod:
		return
	slot.lod = lod
	(slot.grating as MeshInstance3D).mesh = _kit.grates[lod][0]
	(slot.rail as MeshInstance3D).mesh = _kit.grates[lod][1]
	(slot.steel as MeshInstance3D).mesh = _kit.steel(lod, slot.hatch)
	(slot.ladder as MeshInstance3D).mesh = _kit.ladders[lod]
	(slot.fixtures as MultiMesh).mesh = _kit.fixtures[0 if lod == 0 else 1]
	(slot.globes as MultiMesh).mesh = _kit.globes[0 if lod == 0 else 1]
	(slot.wall as MeshInstance3D).mesh = (_walls_fine if lod == 0 else _walls_coarse)[posmod(slot.g, WALL_CYCLE)]


## 第 g 圈第 j 盏灯此刻的亮度（接触不良的一直在跳）
func _lamp_power(lamp: Dictionary) -> float:
	if lamp.dead:
		return 0.0
	if lamp.faulty:
		var nz := _shake.get_noise_2d(t * 3.5, float(lamp.idx) * 1.7)
		if nz < -0.18:
			return 0.04 if fposmod(t * 17.0 + float(lamp.idx), 1.0) < 0.6 else 0.6
	return 1.0


func _update(_delta: float) -> void:
	# 滚出头顶的那圈挪到最下面
	while depth - RING_STEP * float(_slots[0].g) > RINGS_ABOVE * RING_STEP + RING_STEP * 0.5:
		var top: Dictionary = _slots.pop_front()
		_assign(top, int(_slots[-1].g) + 1)
		_slots.append(top)
	var eye_y := 1.25
	for slot in _slots:
		var y: float = depth - RING_STEP * float(slot.g)
		(slot.node as Node3D).position = Vector3(0, y, 0)
		var d := absf(y + 0.5 - eye_y)
		_set_lod(slot, 0 if d < 34.0 else (1 if d < 120.0 else 2))
		# 灯：近处真的灯，远一点只剩几盏洗墙灯（顶上其余几盏的亮度），再远交给着色器
		var near := 1.0 - smoothstep(NEAR - 10.0, NEAR, d)
		var mid := (1.0 - near) * (1.0 - smoothstep(MID - 20.0, MID, d))
		var lamps: Array = slot.lamps
		var avg := 0.0
		var pw: Array[float] = []
		for j in LAMPS:
			var lamp: Dictionary = lamps[j]
			var p := _lamp_power(lamp)
			pw.append(p)
			avg += p
			if lamp.faulty:
				(slot.globes as MultiMesh).set_instance_custom_data(j, Color(p, 0, lamp.tint, 0))
		avg /= LAMPS
		for l in slot.lights:
			var light: SpotLight3D = l.light
			var k: float = near if not l.mid else near + mid * 3.3
			light.light_energy = l.base * pw[l.j] * k
			light.visible = light.light_energy > 0.002
			if l.kind == "deck" and light.shadow_enabled != (d < SHADOW_NEAR):
				light.shadow_enabled = d < SHADOW_NEAR
		(slot.wall as GeometryInstance3D).set_instance_shader_parameter("ring_power", avg * ShaftKit.WALL_GLOW)
		(slot.grating as GeometryInstance3D).set_instance_shader_parameter("pool_power",
			avg * ShaftKit.DECK_LIGHT * 0.5 * exp(-maxf(d / RING_STEP - 6.0, 0.0) / 9.0))
	# 轿厢：操纵箱上的深度；顺着导轨走，轻轻地抖（导靴滚过导轨的接头）
	_cab.depth_m = depth
	var buzz := _shake.get_noise_2d(t * 14.0, 3.0) * 0.0012 + _shake.get_noise_2d(t * 2.3, 9.0) * 0.002
	_cab.transform = LiftCab.mount(R, 0.0, 0.0)
	_cab.position += _cab.transform.basis.x * buzz
	# 灯的嗡声：一圈灯从身边擦过的时候大一点
	if _hum:
		var near_ring := 1e9
		for slot in _slots:
			near_ring = minf(near_ring, absf(depth - RING_STEP * float(slot.g) + 0.5 - eye_y))
		_hum.volume_db = -20.0 + 8.0 * exp(-near_ring * near_ring / 18.0)


# ---------------------------------------------------------------------------- 空气里的冰晶
func _build_particles() -> void:
	# 井里的空气不动，轿厢往下走：冰晶一粒粒从脚下往上飘过去（看得出在动、有多快）
	var motes := GPUParticles3D.new()
	motes.amount = 2600
	motes.lifetime = 9.0
	motes.preprocess = 9.0
	motes.visibility_aabb = AABB(Vector3(-R, -25, -R), Vector3(2 * R, 50, 2 * R))
	var pm := ParticleProcessMaterial.new()
	pm.emission_shape = ParticleProcessMaterial.EMISSION_SHAPE_BOX
	pm.emission_box_extents = Vector3(R * 0.8, 1.0, R * 0.8)
	pm.direction = Vector3.UP
	pm.spread = 3.0
	pm.initial_velocity_min = SPEED * 0.97
	pm.initial_velocity_max = SPEED * 1.03
	pm.gravity = Vector3.ZERO
	pm.turbulence_enabled = true
	pm.turbulence_noise_strength = 0.3
	pm.turbulence_noise_scale = 2.5
	pm.turbulence_influence_min = 0.01
	pm.turbulence_influence_max = 0.03
	pm.scale_min = 0.4
	pm.scale_max = 1.3
	motes.process_material = pm
	var q := QuadMesh.new()
	q.size = Vector2(0.008, 0.008)
	var m := StandardMaterial3D.new()
	m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	m.billboard_mode = BaseMaterial3D.BILLBOARD_PARTICLES
	m.albedo_color = Color(0.95, 0.97, 1.0, 0.55)
	m.roughness = 0.3
	var g := Gradient.new()
	g.set_color(0, Color(1, 1, 1, 1))
	g.set_color(1, Color(1, 1, 1, 0))
	var gt := GradientTexture2D.new()
	gt.gradient = g
	gt.fill = GradientTexture2D.FILL_RADIAL
	gt.fill_from = Vector2(0.5, 0.5)
	gt.fill_to = Vector2(0.5, 0.0)
	gt.width = 32
	gt.height = 32
	m.albedo_texture = gt
	q.material = m
	motes.draw_pass_1 = q
	motes.position = Vector3(0, -22, 0)
	motes.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(motes)


# ---------------------------------------------------------------------------- 人：自己坐在座位上（第一人称），别人是替身
func _build_crew() -> void:
	var me := Net.my_id()
	_walker = RoomWalker.new()
	_walker.name = "Walker"
	_walker.deck_y = 0.0
	_walker.normal_fov = 64.0
	_walker.seated_fov = 64.0
	_walker.seated_yaw_limit = 110.0
	_walker.locked = true
	add_child(_walker)
	_walker.make_current()
	var seat := _seat_of(me)
	if DebugArgs.has("seat"):
		seat = clampi(int(DebugArgs.get_arg("seat")), 0, 3)
	_walker.sit_at(_cab.seats[seat], true)
	var f := -(_cab.seats[seat] as Node3D).global_basis.z
	_seat_yaw = atan2(-f.x, -f.z)
	# 左边的座位往左转是井心，右边的往右转
	_walker.yaw += deg_to_rad(FIRST_LOOK) * (1.0 if seat < 2 else -1.0)
	if DebugArgs.has("ride-look"):
		# 截图：相对座位的朝向（左边的座位 +度是往井心转）
		var lk := DebugArgs.get_arg("ride-look").split(",")
		_walker.yaw = _seat_yaw + deg_to_rad(float(lk[0]))
		if lk.size() > 1:
			_walker.pitch = deg_to_rad(float(lk[1]))
	var body := CREW_BODY.new()
	body.camera_path = _walker.get_path()
	add_child(body)
	_sync_riders()


## 座位按岗位分：0 驾驶、1 声呐在左边（前、后），2 轮机、3 潜水员在右边；岗位撞了就找空着的
func _seat_of(id: int) -> int:
	var taken := {}
	var ids := Net.players.keys()
	ids.sort()
	for other: int in ids:
		var want := clampi(Net.role_of(other), 0, 3)
		while taken.has(want):
			want = (want + 1) % 4
		taken[want] = other
		if other == id:
			return want
	return 0


func _sync_riders() -> void:
	for id: int in _riders.keys():
		if not Net.players.has(id):
			(_riders[id] as Node).queue_free()
			_riders.erase(id)
	for id: int in Net.players:
		if id == Net.my_id() or _riders.has(id):
			continue
		var r := Rider.new()
		r.setup(Net.player_name(id), _cab.seats[_seat_of(id)])
		add_child(r)
		var body := CREW_BODY.new()
		body.first_person = false
		body.look = Net.look_of(id)
		body.camera_path = r.get_path()
		add_child(body)
		r.body = body
		_riders[id] = r


func _on_look(id: int, yaw_off: float, pitch: float) -> void:
	if _riders.has(id):
		(_riders[id] as Rider).look(yaw_off, pitch)


## 别的玩家在本机的替身：装成 RoomWalker 的样子给 crew_body.gd 读（坐着、视线跟着他的鼠标）
class Rider extends Node3D:
	var yaw := 0.0
	var pitch := 0.0
	var gait_steps := 0.0
	var gait_speed := 0.0
	var gait_run := 0.0
	var door_op := false
	var door_aft := false
	var door_lean := 0.0
	var door_yaw := 0.0
	var deck_y := 0.0
	var _door = null
	var body: Node3D
	var _seat_yaw := 0.0
	var _want := Vector2.ZERO
	var _label: Label3D

	func setup(display_name: String, seat: Node3D) -> void:
		position = seat.global_position
		var f := -seat.global_basis.z
		_seat_yaw = atan2(-f.x, -f.z)
		yaw = _seat_yaw
		_label = Label3D.new()
		_label.text = display_name
		_label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
		_label.pixel_size = 0.0011
		_label.font_size = 40
		_label.outline_size = 14
		_label.modulate = Color(0.95, 0.9, 0.78, 0.9)
		_label.outline_modulate = Color(0, 0, 0, 0.75)
		_label.position = Vector3(0, 0.26, 0)
		_label.font = load("res://assets/fonts/NotoSerifSC-VF.ttf")
		add_child(_label)

	func look(yaw_off: float, p: float) -> void:
		_want = Vector2(yaw_off, p)

	func sit_amount() -> float:
		return 1.0

	func body_yaw() -> float:
		return _seat_yaw

	func feet() -> Vector2:
		return Vector2(position.x, position.z)

	func _process(delta: float) -> void:
		var k := 1.0 - exp(-delta * 8.0)
		yaw = lerp_angle(yaw, _seat_yaw + _want.x, k)
		pitch = lerpf(pitch, _want.y, k)

	func _exit_tree() -> void:
		if body:
			body.queue_free()


# ---------------------------------------------------------------------------- 声音、提示
func _build_audio() -> void:
	# 井里的空气、顶上驱动电机的嗡声（3D，在轿厢顶上）、日光灯的嗡嗡声、灯从身边擦过时的灯嗡声；时不时轿厢吱嘎一声
	var air := AudioStreamPlayer.new()
	air.stream = load("res://assets/audio/shaft_air.wav")
	air.volume_db = -14.0
	add_child(air)
	air.play()
	_hum = AudioStreamPlayer.new()
	_hum.stream = load("res://assets/audio/shaft_hum.wav")
	_hum.volume_db = -20.0
	add_child(_hum)
	_hum.play()
	for s: Array in [["motor_hum", Vector3(0.2, LiftCab.ROOF + 0.6, LiftCab.OUT_Z - 0.4), -10.0, 1.25],
			["fluoro_buzz", Vector3(0.0, LiftCab.H - 0.1, 0.0), -24.0, 1.0]]:
		var p := AudioStreamPlayer3D.new()
		p.stream = load("res://assets/audio/%s.wav" % s[0])
		p.position = s[1]
		p.volume_db = s[2]
		p.pitch_scale = s[3]
		p.unit_size = 3.0
		_cab.add_child(p)
		p.play()


func _play(sfx: String, vol_db: float, pitch: float) -> void:
	var p := AudioStreamPlayer.new()
	p.stream = load("res://assets/audio/%s.wav" % sfx)
	p.volume_db = vol_db
	p.pitch_scale = pitch
	add_child(p)
	p.play()
	p.finished.connect(p.queue_free)
	DebugArgs.log_sfx(sfx)


## 屏幕下方一行小字：下井中（加载中）/ 等队友
func _build_hint() -> void:
	var layer := CanvasLayer.new()
	add_child(layer)
	_hint = Label.new()
	var f := FontVariation.new()
	f.base_font = load(FONT)
	f.variation_opentype = {"wght": 500}
	_hint.add_theme_font_override("font", f)
	_hint.add_theme_font_size_override("font_size", 18)
	_hint.add_theme_color_override("font_color", Color(0.85, 0.82, 0.74, 0.55))
	_hint.anchor_left = 0.0
	_hint.anchor_right = 1.0
	_hint.anchor_top = 1.0
	_hint.anchor_bottom = 1.0
	_hint.offset_top = -64.0
	_hint.offset_bottom = -36.0
	_hint.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_hint.mouse_filter = Control.MOUSE_FILTER_IGNORE
	layer.add_child(_hint)


func _physics_process(delta: float) -> void:
	if _hint and not _arriving:
		var dots := ".".repeat(1 + int(t * 1.5) % 3)
		# 自己加载好了、别人还没好：等队友；否则就是在下井（单人坐够 MIN_RIDE 秒）
		var waiting := _ready_sent and Net.is_online() and not Net.ride_all_ready()
		_hint.text = ("等队友" if waiting else "下井中") + dots if not _hold else ""
		_creak_t -= delta
		if _creak_t <= 0.0:
			_creak_t = randf_range(7.0, 16.0)
			_play("creak_%d" % randi_range(0, 4), -22.0, randf_range(0.7, 0.9))
