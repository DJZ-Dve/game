extends Node3D
## 巨物「闷雷」看样场景（lookdev）：静止姿态的 giant.glb、深海环境（deep_sea_env.tres + 水体吸收 / 海雪，同 water_fx.gd）、
## 一盏像潜艇探照灯的聚光灯（暖白、体积雾里有光柱），很弱的环境光。材质改了不用重新导入 glb：
## 这里按材质名把 assets/materials/ 下的同名 .tres 直接套上去（所以改完 .tres / 着色器直接截图就是最新的）。
##
## 后台截图（不抢焦点、不出声）：
##   tools/capture.sh out.png --scene=res://scenes/dev/giant_lookdev.tscn --shot=maw --jaw=65 --light=side
## 参数（`--` 之后）：
##   --shot=名字      机位：side 全身侧面、q34 前上方 3/4、head 头、maw 正面看嘴（配 --jaw）、
##                    closeup_skin 体侧皮肤特写、closeup_teeth 牙特写（自动张嘴）、closeup_socket 上颚的獠牙牙槽（张嘴、从下往上看）、
##                    closeup_eye 眼睛和寄生虫、closeup_gill 鳃裂、tail 尾鳍、fin 胸鳍、belly 腹面、flank 体侧中景（看斑点、旧疤的分布）、
##                    perf 贴着体侧、皮铺满全屏（量性能用）、
##                    swatch 材质样件（五种材质，假的 mask 贴图把各通道都用上：疤、生肉、凹槽、凸棱、薄处、牙根牙尖、寄生虫），
##                    swatch_skin 皮的样件近看、swatch_mouth 嘴里和牙近看、swatch_eye 眼球和寄生虫近看、swatch_fin 鳍近看
##   --jaw=度         张嘴（绕 Jaw 骨的铰链往下转；最大 70）
##   --bend=度        脊椎左右弯（整条身子弯成一个弧，看蒙皮动起来纹理游不游）；--pose=raw 不动骨骼（导入时的样子）
##   --light=front|side|back|top|below  灯从哪边来（相对机位）：front 灯在相机旁边（潜艇里看出去的样子）、
##                    side 侧光、back 逆光（看透射）、top 顶光、below 从下往上
##   --fog=倍数       雾（距离雾 + 体积雾）的浓度，默认按机位（远景稀一些），1 = 深海场景原样
##   --energy=倍数    灯的亮度；--ambient=倍数 环境光；--water=off 关掉水体吸收（只看材质本身）；--snow=off 关海雪
##   --mat=M_GiantSkin  全身换成这个材质；--mat=_faces 查法线翻没翻（背面红）；--mat=_flat 纯色（量性能时当基准）
##   --param=名字:值;名字:值   临时改着色器参数（所有巨物材质和样件上有这个参数的都改；值是数字，或 r,g,b 颜色 / 向量），
##                    调参对比用，不写回 .tres。例 `--param=debug_view:4` 看区域图、`--param=spot_amount:0;mottle_amount:0`
##   --cam=x,y,z --target=x,y,z --fov=度   自定机位（覆盖 --shot）
##   --perf           第 100~400 帧量整帧时间，打印 `PERF gpu_ms=… frame_ms=…`。量材质开销：
##                    `--shot=perf --perf` 和 `--shot=perf --perf --mat=_flat` 比；Godot 参数加 --disable-vsync、--resolution 1920x1080，
##                    再加 `--scale3d=1.3333`（窗口大不过屏幕，2560x1440 的窗口会被压成屏幕大小；用 3D 缩放按 1440p 渲染）。
##                    别的 Godot / Blender 在跑时整帧时间抖得厉害，多跑几次取最小值
## 交互（直接在编辑器里跑这个场景）：右键拖动转、滚轮推拉、中键拖动平移，
##   1~9 切机位、L 换灯的方向、J 张嘴 / 闭嘴、W 水体吸收开关

const GIANT := preload("res://assets/models/giant.glb")
const ENV := preload("res://assets/environment/deep_sea_env.tres")
const WATER := preload("res://scripts/water_fx.gd")
const MAT_DIR := "res://assets/materials/"

## 机位：相机位置、看的点、视野、聚光灯张角、雾的浓度倍数（远景机位把雾调稀，不然四五十米外整条只剩个剪影——游戏里本来就是这样）（Godot 坐标：-Z 朝前（头），+Y 朝上，+X 右，原点在身体中段中轴线上）
const SHOTS := {
	"side": {"cam": Vector3(-62, 4, 0), "target": Vector3(0, 0, 0), "fov": 46.0, "spot": 34.0, "fog": 0.08},
	"q34": {"cam": Vector3(-30, 14, -46), "target": Vector3(0, -1, -10), "fov": 50.0, "spot": 34.0, "fog": 0.12},
	"head": {"cam": Vector3(-24, 3, -26), "target": Vector3(0, -0.5, -14), "fov": 48.0, "spot": 32.0, "fog": 0.25},
	"maw": {"cam": Vector3(-7, -3, -44), "target": Vector3(0, -2.5, -16), "fov": 50.0, "spot": 30.0, "jaw": 65.0, "fog": 0.25},
	"closeup_skin": {"cam": Vector3(-7.6, 1.8, 4.5), "target": Vector3(-4.6, 0.4, -2.5), "fov": 50.0, "spot": 34.0},
	"closeup_teeth": {"cam": Vector3(-5.5, -1.0, -30.0), "target": Vector3(-2.2, -2.2, -21.0), "fov": 50.0, "spot": 28.0, "jaw": 60.0},
	"closeup_socket": {"cam": Vector3(-2.5, -7.0, -27.0), "target": Vector3(-1.4, -1.2, -19.6), "fov": 45.0, "spot": 26.0, "jaw": 65.0},
	"closeup_eye": {"cam": Vector3(-7.2, 2.6, -20.5), "target": Vector3(-3.6, 1.0, -17.6), "fov": 40.0, "spot": 28.0},
	"closeup_gill": {"cam": Vector3(-12.0, 1.0, -7.0), "target": Vector3(-4.9, -0.6, -10.1), "fov": 45.0, "spot": 30.0},
	"tail": {"cam": Vector3(-20, 3, 30), "target": Vector3(0, 1, 18), "fov": 50.0, "spot": 34.0, "fog": 0.5},
	"fin": {"cam": Vector3(-14, 2, -2), "target": Vector3(-7, -3, -8), "fov": 50.0, "spot": 34.0, "fog": 0.5},
	"belly": {"cam": Vector3(-14, -16, -4), "target": Vector3(0, -2, -6), "fov": 55.0, "spot": 36.0, "fog": 0.5},
	"flank": {"cam": Vector3(-17, 2, 6), "target": Vector3(-3, 0, 0), "fov": 50.0, "spot": 40.0, "fog": 0.3},
	"perf": {"cam": Vector3(-7.6, 0.4, 0.0), "target": Vector3(0, 0.4, 0.0), "fov": 50.0, "spot": 60.0},
	"swatch": {"cam": Vector3(101.0, 1.0, 11.5), "target": Vector3(101.0, -0.3, 0), "fov": 46.0, "spot": 50.0, "fog": 0.3},
	"swatch_skin": {"cam": Vector3(95.0, 0.6, 4.6), "target": Vector3(95.0, -0.1, 0), "fov": 40.0, "spot": 45.0, "fog": 0.3},
	"swatch_mouth": {"cam": Vector3(99.6, 0.0, 4.6), "target": Vector3(99.6, -0.5, 0), "fov": 40.0, "spot": 45.0, "fog": 0.3},
	"swatch_eye": {"cam": Vector3(103.5, 0.2, 2.6), "target": Vector3(103.5, -0.2, 0), "fov": 40.0, "spot": 45.0, "fog": 0.3},
	"swatch_fin": {"cam": Vector3(107.5, 0.0, 5.0), "target": Vector3(107.5, -0.2, 0), "fov": 40.0, "spot": 45.0, "fog": 0.3},
}
const SHOT_KEYS := ["side", "maw", "closeup_skin", "closeup_teeth", "closeup_eye", "closeup_gill", "closeup_socket", "tail", "swatch"]
const LIGHTS := ["front", "side", "back", "top", "below"]
## 样件放在离巨物远的地方（x = 100），各自的灯照不到巨物
const SWATCH_ORIGIN := Vector3(100, 0, 0)

var giant: Node3D
var skeleton: Skeleton3D
var cam: Camera3D
var spot: SpotLight3D
var water: Node3D
var env: Environment

var shot := "side"
var light_mode := "front"
var jaw := 0.0
var bend := 0.0
var _target := Vector3.ZERO
var _spot_angle := 30.0
var _energy := 1.0
var _fog := 1.0
var _orbit_drag := false
var _pan_drag := false


func _ready() -> void:
	env = ENV.duplicate()
	env.ambient_light_energy *= float(DebugArgs.get_arg("ambient", "1"))
	var we := WorldEnvironment.new()
	we.environment = env
	add_child(we)

	giant = GIANT.instantiate()
	add_child(giant)
	skeleton = _find_skeleton(giant)
	_apply_materials(giant, DebugArgs.get_arg("mat"))

	_build_swatches()

	cam = Camera3D.new()
	cam.near = 0.1
	cam.far = 400.0
	add_child(cam)
	cam.make_current()

	spot = SpotLight3D.new()
	spot.light_color = Color(1.0, 0.93, 0.82)
	spot.spot_attenuation = 1.2
	spot.spot_angle_attenuation = 0.9
	spot.shadow_enabled = true
	spot.shadow_blur = 1.5
	spot.light_size = 0.12
	spot.light_volumetric_fog_energy = 4.0
	add_child(spot)

	# 水体吸收 + 海雪（和深海场景同一个脚本）；耐压舱的胶囊放到远处，免得在巨物身上挖出一块不衰减的地方
	water = Node3D.new()
	water.set_script(WATER)
	var far := Node3D.new()
	far.name = "FarCabin"
	far.position = Vector3(0, -5000, 0)
	water.add_child(far)
	water.set("cabin_path", NodePath("FarCabin"))
	add_child(water)
	if DebugArgs.get_arg("snow", "on") == "off":
		for c in water.get_children():
			if c is MeshInstance3D and c.name != "Underwater":
				c.visible = false

	_energy = float(DebugArgs.get_arg("energy", "1"))
	light_mode = DebugArgs.get_arg("light", "front")
	bend = float(DebugArgs.get_arg("bend", "0"))
	_set_shot(DebugArgs.get_arg("shot", "side"))
	if DebugArgs.has("jaw"):
		jaw = float(DebugArgs.get_arg("jaw"))
	if DebugArgs.has("cam"):
		cam.position = _vec(DebugArgs.get_arg("cam"))
		_target = _vec(DebugArgs.get_arg("target", "0,0,0"))
	if DebugArgs.has("fov"):
		cam.fov = float(DebugArgs.get_arg("fov"))
	_apply_pose()
	_update_view()
	if DebugArgs.has("perf"):
		RenderingServer.viewport_set_measure_render_time(get_viewport().get_viewport_rid(), true)
	# --scale3d=倍数：3D 按窗口的这么多倍渲染（窗口大不过屏幕：1920x1080 的窗口配 1.3333 就是按 2560x1440 渲染）
	if DebugArgs.has("scale3d"):
		get_viewport().scaling_3d_mode = Viewport.SCALING_3D_MODE_BILINEAR
		get_viewport().scaling_3d_scale = float(DebugArgs.get_arg("scale3d"))
	set_process(DebugArgs.has("perf"))


var _perf_sum := 0.0
var _perf_n := 0
var _perf_t0 := 0


func _process(_delta: float) -> void:
	var f := Engine.get_process_frames()
	if f == 100:
		_perf_t0 = Time.get_ticks_usec()
	if f >= 100 and f < 400:
		_perf_sum += RenderingServer.viewport_get_measured_render_time_gpu(get_viewport().get_viewport_rid())
		_perf_n += 1
	elif f == 400:
		# Mac（Metal）上量不到 GPU 时间（是 0），那就看整帧时间（配 --disable-vsync、大分辨率，让 GPU 成为瓶颈）
		print("PERF gpu_ms=%.2f frame_ms=%.3f" % [_perf_sum / maxi(_perf_n, 1), (Time.get_ticks_usec() - _perf_t0) / 300000.0])
		set_process(false)


func _find_skeleton(n: Node) -> Skeleton3D:
	if n is Skeleton3D:
		return n
	for c in n.get_children():
		var s := _find_skeleton(c)
		if s:
			return s
	return null


## --mat=_faces：查法线 / 绕序翻没翻——正面灰、背面红（双面渲染）
const FACES_SHADER := "shader_type spatial;\nrender_mode cull_disabled;\nvoid fragment() {\n\tALBEDO = FRONT_FACING ? vec3(0.5) : vec3(0.8, 0.03, 0.03);\n\tROUGHNESS = 0.6;\n}\n"
## --mat=_flat：纯色（量性能的基准：同样的光照、没有贴图）
const FLAT_SHADER := "shader_type spatial;\nrender_mode cull_back, diffuse_burley, specular_schlick_ggx;\nvoid fragment() {\n\tALBEDO = vec3(0.05, 0.045, 0.04);\n\tROUGHNESS = 0.6;\n}\n"


## 按材质名套 assets/materials/ 下的同名 .tres（override 给了就全身都用它）
func _apply_materials(n: Node, override: String) -> void:
	if n is MeshInstance3D and n.mesh:
		var mi := n as MeshInstance3D
		if override == "_faces" or override == "_flat":
			var sh := Shader.new()
			sh.code = FACES_SHADER if override == "_faces" else FLAT_SHADER
			var fm := ShaderMaterial.new()
			fm.shader = sh
			mi.material_override = fm
			return
		for i in mi.mesh.get_surface_count():
			var m := mi.mesh.surface_get_material(i)
			var nm := override if not override.is_empty() else (m.resource_name if m else "")
			var path := MAT_DIR + nm + ".tres"
			if not nm.is_empty() and ResourceLoader.exists(path):
				mi.set_surface_override_material(i, _tweak(load(path)))
	for c in n.get_children():
		_apply_materials(c, override)


var _tweaked := {}


## --param：复制一份材质改参数（同一个材质只复制一次，各处共用）
func _tweak(m: Material) -> Material:
	if not DebugArgs.has("param") or not m is ShaderMaterial:
		return m
	if _tweaked.has(m):
		return _tweaked[m]
	var sm := (m as ShaderMaterial).duplicate() as ShaderMaterial
	var names := {}
	for u in sm.shader.get_shader_uniform_list(true):
		names[u.name] = u.type
	for item in DebugArgs.get_arg("param").split(";", false):
		var kv := item.split(":")
		if kv.size() < 2 or not names.has(kv[0]):
			continue
		var parts := kv[1].split(",")
		var v: Variant = float(kv[1])
		if parts.size() == 2:
			v = Vector2(float(parts[0]), float(parts[1]))
		elif parts.size() >= 3:
			v = Color(float(parts[0]), float(parts[1]), float(parts[2]))
			if names[kv[0]] == TYPE_VECTOR3:
				v = Vector3(float(parts[0]), float(parts[1]), float(parts[2]))
		elif names[kv[0]] == TYPE_INT:
			v = int(kv[1])
		sm.set_shader_parameter(kv[0], v)
	_tweaked[m] = sm
	return sm


func _set_shot(nm: String) -> void:
	if not SHOTS.has(nm):
		push_warning("giant_lookdev: 没有机位 %s，用 side" % nm)
		nm = "side"
	shot = nm
	var s: Dictionary = SHOTS[nm]
	cam.position = s.cam
	_target = s.target
	cam.fov = s.fov
	_spot_angle = s.spot
	jaw = s.get("jaw", 0.0)
	_fog = float(DebugArgs.get_arg("fog", str(s.get("fog", 1.0))))
	env.fog_density = ENV.fog_density * _fog
	env.volumetric_fog_density = ENV.volumetric_fog_density * _fog


func _update_view() -> void:
	cam.look_at(_target, Vector3.UP)
	var view := _target - cam.position
	var dist := view.length()
	var fwd := view / dist
	var right := fwd.cross(Vector3.UP).normalized()
	var ld := maxf(dist * 0.85, 8.0)
	var pos: Vector3
	match light_mode:
		"side":
			pos = _target - fwd * ld * 0.6 + right * ld * 0.8 + Vector3.UP * ld * 0.3
		"back":
			pos = _target + fwd * ld * 0.9 + right * ld * 0.35 + Vector3.UP * ld * 0.35
		"top":
			pos = _target - fwd * ld * 0.25 + Vector3.UP * ld
		"below":
			pos = _target - fwd * ld * 0.4 - Vector3.UP * ld * 0.9 + right * ld * 0.2
		_:
			# 探照灯在相机旁边偏右上（潜艇的灯在艇首两侧）
			pos = cam.position + right * minf(2.5, dist * 0.12) + Vector3.UP * minf(1.5, dist * 0.08)
	spot.position = pos
	spot.look_at(_target, Vector3.UP if absf((_target - pos).normalized().y) < 0.95 else Vector3.FORWARD)
	var d := pos.distance_to(_target)
	spot.spot_range = d * 2.0 + 30.0
	spot.spot_angle = _spot_angle
	# 衰减指数 1.2：离得远要更亮，保持被照的地方和潜艇灯在 12 米处差不多亮
	spot.light_energy = 22.0 * pow(maxf(d, 6.0) / 12.0, 1.2) * _energy


## 静止姿态 + 张嘴 + 弯身子（绕世界轴转，换算到每根骨头自己的坐标系里）
func _apply_pose() -> void:
	if not skeleton or DebugArgs.get_arg("pose") == "raw":
		return
	var to_skel := skeleton.global_transform.basis.inverse()
	for i in skeleton.get_bone_count():
		var bn := skeleton.get_bone_name(i)
		var rest := skeleton.get_bone_rest(i)
		var q := rest.basis.get_rotation_quaternion()
		var grest := skeleton.get_bone_global_rest(i).basis.orthonormalized()
		if bn == "Jaw" and absf(jaw) > 0.01:
			var axis := (grest.inverse() * (to_skel * Vector3.RIGHT)).normalized()
			q = q * Quaternion(axis, -deg_to_rad(jaw))
		elif bn.begins_with("Spine_") and absf(bend) > 0.01:
			var axis := (grest.inverse() * (to_skel * Vector3.UP)).normalized()
			q = q * Quaternion(axis, deg_to_rad(bend) / 16.0)
		skeleton.set_bone_pose_rotation(i, q)
		skeleton.set_bone_pose_position(i, rest.origin)


func _vec(s: String) -> Vector3:
	var p := s.split(",")
	return Vector3(float(p[0]), float(p[1]), float(p[2])) if p.size() >= 3 else Vector3.ZERO


# ---------------------------------------------------------------------------- 交互

func _unhandled_input(e: InputEvent) -> void:
	if e is InputEventMouseButton:
		var mb := e as InputEventMouseButton
		if mb.button_index == MOUSE_BUTTON_RIGHT:
			_orbit_drag = mb.pressed
		elif mb.button_index == MOUSE_BUTTON_MIDDLE:
			_pan_drag = mb.pressed
		elif mb.pressed and mb.button_index in [MOUSE_BUTTON_WHEEL_UP, MOUSE_BUTTON_WHEEL_DOWN]:
			var k := 0.9 if mb.button_index == MOUSE_BUTTON_WHEEL_UP else 1.0 / 0.9
			cam.position = _target + (cam.position - _target) * k
			_update_view()
	elif e is InputEventMouseMotion:
		var mm := e as InputEventMouseMotion
		if _orbit_drag:
			var off := cam.position - _target
			off = off.rotated(Vector3.UP, -mm.relative.x * 0.006)
			var right := off.cross(Vector3.UP).normalized()
			var off2 := off.rotated(right, -mm.relative.y * 0.006)
			if absf(off2.normalized().y) < 0.97:
				off = off2
			cam.position = _target + off
			_update_view()
		elif _pan_drag:
			var d := cam.position.distance_to(_target) * 0.0015
			var delta := cam.global_basis.x * -mm.relative.x * d + cam.global_basis.y * mm.relative.y * d
			cam.position += delta
			_target += delta
			_update_view()
	elif e is InputEventKey and e.pressed and not e.echo:
		var k := (e as InputEventKey).keycode
		if k >= KEY_1 and k <= KEY_9:
			_set_shot(SHOT_KEYS[k - KEY_1])
			_apply_pose()
			_update_view()
		elif k == KEY_L:
			light_mode = LIGHTS[(LIGHTS.find(light_mode) + 1) % LIGHTS.size()]
			_update_view()
		elif k == KEY_J:
			jaw = 0.0 if jaw > 1.0 else 65.0
			_apply_pose()
		elif k == KEY_W:
			var post := water.get_node_or_null("Underwater")
			if post:
				post.visible = not post.visible


# ---------------------------------------------------------------------------- 材质样件
# 灰模（块面占位）的烘焙贴图里还没有疤、生肉、薄处、牙根、寄生虫这些区域，样件用这里现算的「假」烘焙贴图
# （同样的格式：法线 OpenGL Y+；mask R AO、G 凹槽、B 凸棱、A 区域图），把着色器的每个通道都用上。
# 每个样件复制一份正式材质，只换 normal_tex / mask_tex / atlas_meters，其余参数和正式的一样。
# UV0 = 0～1（1 个单位 = atlas_meters 米），UV2 = BodyST（s, 1 - θ/π），顶点色 R 棱边 G 凹槽 B 随机。

func _build_swatches() -> void:
	var root := Node3D.new()
	root.name = "Swatches"
	root.position = SWATCH_ORIGIN
	add_child(root)
	# 皮：一个大球（上半背、下半腹），正面有一道长旧疤、一个愈合的达摩鲨咬坑、一处新伤、三道鳃裂似的沟、一片壶腹孔
	var r := 1.3
	_swatch(root, _sphere(r, 0.45), "M_GiantSkin", _fake("skin", 512), TAU * r, Vector3(-5.0, 0.0, 0.0))
	# 嘴里：上颚的横褶、一个牙槽（周围一圈牙床）；旁边一排牙（牙根 AO 低、纵纹）
	r = 1.0
	_swatch(root, _sphere(r, 0.1), "M_GiantMouth", _fake("mouth", 256), TAU * r, Vector3(-1.6, -0.3, 0.0))
	var tooth_tex := _fake("tooth", 256)
	for k in 5:
		var length := 0.9 + 0.3 * k
		_swatch(root, _tooth(length, 0.1 + 0.025 * k, 0.2 * k), "M_GiantTooth", tooth_tex, 1.0,
				Vector3(0.2 + 0.45 * k, -1.3, 0.2 * (k % 2)), Vector3(0, 0.4 * k, 0))
	# 眼球（左半张图，A = 0）+ 一截寄生虫（右半张图，A = 1）
	var eye_tex := _fake("eye", 256)
	_swatch(root, _eyeball(0.38), "M_GiantEye", eye_tex, 2.0, Vector3(3.2, 0.0, 0.0))
	var par := _swatch(root, _parasite(0.12, 1.4), "M_GiantEye", eye_tex, 2.0, Vector3(3.85, -0.9, 0.1))
	par.rotation_degrees = Vector3(0, 0, -12)
	# 鳍：一块有厚度的板，上边是鳍缘（薄、透光），鳍条往鳍根走
	_swatch(root, _fin(3.2, 2.4), "M_GiantFin", _fake("fin", 256), 3.2, Vector3(7.5, -1.4, -0.3), Vector3(0, deg_to_rad(-20), 0))


func _swatch(root: Node3D, mesh: Mesh, mat: String, tex: Array, meters: float, pos: Vector3, rot := Vector3.ZERO) -> MeshInstance3D:
	var mi := MeshInstance3D.new()
	mi.mesh = mesh
	mi.position = pos
	mi.rotation = rot
	var m := (load(MAT_DIR + mat + ".tres") as ShaderMaterial).duplicate() as ShaderMaterial
	m.set_shader_parameter("normal_tex", tex[0])
	m.set_shader_parameter("mask_tex", tex[1])
	m.set_shader_parameter("atlas_meters", meters)
	mi.material_override = _tweak(m)
	root.add_child(mi)
	return mi


## 假的烘焙贴图：按 kind 现算高度场和 mask，返回 [法线, mask]（ImageTexture，带 mip）
func _fake(kind: String, size: int) -> Array:
	var h := PackedFloat32Array()
	h.resize(size * size)
	var mask := Image.create(size, size, false, Image.FORMAT_RGBA8)
	for y in size:
		var v := (y + 0.5) / size
		for x in size:
			var u := (x + 0.5) / size
			var o: Array = _fake_px(kind, u, v)   # [高度, AO, 凹槽, 凸棱, 区域]
			h[y * size + x] = o[0]
			mask.set_pixel(x, y, Color(o[1], o[2], o[3], o[4]))
	var nimg := Image.create(size, size, false, Image.FORMAT_RGBA8)
	# 高度是「米」，一个像素 = atlas_meters / size 米；这里把坡度放大到看得清（样件的贴图比正式的粗）
	var k := 0.06 * size
	for y in size:
		for x in size:
			var dx := h[y * size + (x + 1) % size] - h[y * size + (x + size - 1) % size]
			var dy := h[((y + 1) % size) * size + x] - h[((y + size - 1) % size) * size + x]
			# OpenGL 约定：Y+ 朝图像上方（v 减小）
			var n := Vector3(-dx * k, dy * k, 1.0).normalized()
			nimg.set_pixel(x, y, Color(n.x * 0.5 + 0.5, n.y * 0.5 + 0.5, n.z * 0.5 + 0.5))
	nimg.generate_mipmaps()
	mask.generate_mipmaps()
	return [ImageTexture.create_from_image(nimg), ImageTexture.create_from_image(mask)]


func _sm(a: float, b: float, x: float) -> float:
	return smoothstep(a, b, x)


## 点到线段的距离
func _seg(p: Vector2, a: Vector2, b: Vector2) -> float:
	var ab := b - a
	var t := clampf((p - a).dot(ab) / ab.length_squared(), 0.0, 1.0)
	return p.distance_to(a + ab * t)


func _fake_px(kind: String, u: float, v: float) -> Array:
	if kind == "skin" or kind == "mouth":
		u = fposmod(u - 0.5, 1.0)   # 球的正面在 UV.x = 0.75，挪到 0.25
	var p := Vector2(u, v)
	var hgt := 0.0
	var ao := 1.0
	var cav := 0.0
	var ridge := 0.0
	var area := 0.0
	match kind:
		"skin":
			# 球的 UV：u 绕一圈，v 从顶上 0 到底下 0.5；正对相机的是 u ≈ 0.25
			# 一道长旧疤（隆起、发白）
			var d := _seg(p, Vector2(0.08, 0.17), Vector2(0.42, 0.31)) + sin(u * 70.0) * 0.002
			var sc := 1.0 - _sm(0.004, 0.012, d)
			hgt += sc * 0.6
			ridge = maxf(ridge, (1.0 - _sm(0.0, 0.006, d)) * 0.8)
			area = maxf(area, sc * 0.5)
			# 愈合的达摩鲨咬坑：圆坑、边缘一圈旧疤
			var dc := p.distance_to(Vector2(0.17, 0.36))
			var pit := 1.0 - _sm(0.022, 0.034, dc)
			hgt -= pit * 0.5
			area = maxf(area, (1.0 - _sm(0.03, 0.04, dc)) * 0.5)
			cav = maxf(cav, pit * 0.5 * _sm(0.015, 0.03, dc))
			ao -= pit * 0.25
			# 新伤：椭圆的生肉（凹下去）
			var dw := Vector2((u - 0.33) / 0.045, (v - 0.23) / 0.028).length()
			var w := 1.0 - _sm(0.75, 1.0, dw)
			hgt -= w * 0.8 + sin(u * 300.0) * sin(v * 260.0) * 0.08 * w
			area = maxf(area, w)
			cav = maxf(cav, w * (1.0 - _sm(0.3, 0.9, dw)) * 0.6)
			ao -= w * 0.3
			# 三道往后斜的沟（像鳃裂）
			for i in 3:
				var x0 := 0.06 + 0.025 * i
				var dg := _seg(p, Vector2(x0, 0.24), Vector2(x0 + 0.012, 0.31))
				var g := 1.0 - _sm(0.0015, 0.005, dg)
				hgt -= g * 0.9
				cav = maxf(cav, g)
				ao -= (1.0 - _sm(0.0, 0.012, dg)) * 0.35
				ridge = maxf(ridge, (1.0 - _sm(0.0, 0.003, absf(dg - 0.006))) * 0.6)
			# 壶腹孔：一片深色小孔
			var q := Vector2(u * 260.0, v * 260.0)
			var cell := Vector2(floor(q.x), floor(q.y))
			var jit := Vector2(fposmod(sin(cell.dot(Vector2(12.9, 78.2))) * 43758.5, 1.0), fposmod(sin(cell.dot(Vector2(39.3, 11.1))) * 24634.6, 1.0))
			var dp := (q - cell - Vector2(0.25, 0.25) - jit * 0.5).length()
			var region := 1.0 - _sm(0.03, 0.06, p.distance_to(Vector2(0.4, 0.4)))
			var pore := (1.0 - _sm(0.12, 0.2, dp)) * region
			hgt -= pore * 0.3
			cav = maxf(cav, pore)
			# 大的起伏
			hgt += sin(u * 40.0 + sin(v * 30.0) * 2.0) * 0.08
		"mouth":
			# 上颚的横褶（rugae）
			var ph := v * TAU * 16.0 + sin(u * TAU * 3.0) * 2.0
			var wv := sin(ph)
			hgt += wv * 0.25
			ridge = _sm(0.5, 0.95, wv)
			cav = _sm(0.5, 0.95, -wv) * 0.7
			ao -= _sm(0.3, 1.0, -wv) * 0.25
			# 牙槽：深坑，周围一圈牙床（A 渐变）
			var ds := Vector2((u - 0.25) / 0.035, (v - 0.3) / 0.05).length()
			var sock := 1.0 - _sm(0.6, 1.0, ds)
			hgt -= sock * 2.0
			cav = maxf(cav, sock)
			ao -= sock * 0.8
			area = (1.0 - _sm(1.0, 1.8, ds)) * 0.6 * (1.0 - sock)
		"tooth":
			# 牙：u 绕一圈，along = 1 - v（0 牙根 → 1 牙尖）
			var along := 1.0 - v
			ao = lerpf(0.15, 1.0, _sm(0.0, 0.3, along))
			var stri := sin(u * TAU * 22.0 + sin(along * 9.0) * 0.6)
			hgt += stri * 0.03 * (1.0 - along * 0.5)
			cav = _sm(0.8, 1.0, stri) * 0.4
			# 一道裂纹
			var dk := absf(u - 0.3 - sin(along * 7.0) * 0.02)
			var crack := (1.0 - _sm(0.002, 0.008, dk)) * _sm(0.1, 0.25, along) * (1.0 - _sm(0.55, 0.7, along))
			hgt -= crack * 0.15
			cav = maxf(cav, crack)
			area = 1.0
		"eye":
			if u < 0.5:
				# 眼球：几道浅划痕
				var dsr := absf(sin(u * 37.0 + v * 21.0) * 0.5 + sin(u * 11.0 - v * 43.0) * 0.5)
				var sr := 1.0 - _sm(0.0, 0.03, dsr)
				hgt -= sr * 0.01
				cav = sr * 0.3
				area = 0.0
			else:
				# 寄生虫：一节一节的（沿 v），节缝是凹槽
				var seg := absf(sin(v * TAU * 10.0))
				hgt -= (1.0 - _sm(0.0, 0.35, seg)) * 0.4
				cav = (1.0 - _sm(0.0, 0.2, seg)) * 0.8
				ao -= (1.0 - _sm(0.0, 0.3, seg)) * 0.3
				area = 1.0
		"fin":
			# 鳍：v = 0 是鳍缘（上边），往下是鳍根；鳍条沿 v 走
			var rays := sin(u * TAU * 14.0 + sin(v * 4.0) * 0.8)
			hgt += rays * 0.12 * (1.0 - v * 0.3)
			ridge = _sm(0.6, 1.0, rays) * 0.6
			cav = _sm(0.6, 1.0, -rays) * 0.35
			# 鳍缘的撕口
			var notch := 1.0 - _sm(0.0, 0.05, Vector2((u - 0.6) * 1.2, v).length())
			cav = maxf(cav, notch * 0.5)
			area = 1.0 - _sm(0.05, 0.55, v)
			ao = lerpf(1.0, 0.55, _sm(0.6, 1.0, v))
	return [hgt * 0.02, clampf(ao, 0.0, 1.0), clampf(cav, 0.0, 1.0), clampf(ridge, 0.0, 1.0), clampf(area, 0.0, 1.0)]


## 球：UV0 = (经度 / 2π, 纬度弧长 / 周长)（等密度，1 个单位 = 周长），UV2：s 固定，θ 从顶上的背中线（0）到底下的腹中线（1）
func _sphere(r: float, s: float) -> ArrayMesh:
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var nu := 96
	var nv := 48
	for j in nv + 1:
		var v := float(j) / nv
		var lat := PI * v
		for i in nu + 1:
			var u := float(i) / nu
			var lon := TAU * u
			var n := Vector3(sin(lat) * cos(lon), cos(lat), sin(lat) * sin(lon))
			st.set_normal(n)
			st.set_uv(Vector2(1.0 - u, v * 0.5))
			st.set_uv2(Vector2(s + (u - 0.5) * TAU * r / 42.0, 1.0 - v))   # s 跟着经度变（不然斑驳只沿一个方向变，成横条）
			st.set_color(Color(0.0, 0.0, 0.37, 1.0))
			st.add_vertex(n * r)
	_grid_indices(st, nu, nv, false)
	st.generate_tangents()
	return st.commit()


func _grid_indices(st: SurfaceTool, nu: int, nv: int, flip: bool) -> void:
	for j in nv:
		for i in nu:
			var a := j * (nu + 1) + i
			var b := a + nu + 1
			if flip:
				st.add_index(a); st.add_index(a + 1); st.add_index(b)
				st.add_index(a + 1); st.add_index(b + 1); st.add_index(b)
			else:
				st.add_index(a); st.add_index(b); st.add_index(a + 1)
				st.add_index(a + 1); st.add_index(b); st.add_index(b + 1)


## 牙：弯的圆锥，UV0 = (绕一圈 0～1, 1 - 牙根到牙尖 0～1)，顶点色 R 在牙尖（模拟低模曲率），牙根埋进一点点
func _tooth(length: float, radius: float, rnd: float) -> ArrayMesh:
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var nu := 24
	var nv := 32
	for j in nv + 1:
		var v := float(j) / nv
		var y := v * length
		var rr := radius * (1.0 - pow(v, 1.3)) + 0.004
		var bendx := pow(v, 2.0) * length * 0.18
		for i in nu + 1:
			var u := float(i) / nu
			var a := TAU * u
			var p := Vector3(cos(a) * rr * 0.8 + bendx, y, sin(a) * rr)
			st.set_uv(Vector2(1.0 - u, 1.0 - v))
			st.set_uv2(Vector2(0.03, 0.4))
			st.set_color(Color(smoothstep(0.75, 1.0, v), 0.0, fmod(rnd + 0.37, 1.0), 1.0))
			st.add_vertex(p)
	_grid_indices(st, nu, nv, false)
	st.generate_normals()
	st.generate_tangents()
	return st.commit()


## 眼球：正面（+Z）对着相机；UV0 在图的左半边；UV2 按 BodyST 摆，让着色器算出来的眼睛中心正好在正面
func _eyeball(r: float) -> ArrayMesh:
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var nu := 64
	var nv := 32
	var hp := lerpf(5.02, 12.13, 0.75)   # s = 0.075 处的半周长（同着色器的 G_HALF_PERIM）
	for j in nv + 1:
		var v := float(j) / nv
		var lat := PI * v
		for i in nu + 1:
			var u := float(i) / nu
			var lon := TAU * u
			var n := Vector3(sin(lat) * cos(lon), cos(lat), sin(lat) * sin(lon))
			st.set_normal(n)
			st.set_uv(Vector2((1.0 - u) * 0.5, v * 0.5))
			# 正面的切平面上离中心多少米 → BodyST
			var s := 0.075 + n.x * r / 42.0
			var th := 0.3556 - n.y * r / hp
			if n.z < 0.0:
				s = 0.075 + signf(n.x) * r / 42.0
			st.set_uv2(Vector2(s, 1.0 - th))
			st.set_color(Color(0.0, 0.0, 0.5, 1.0))
			st.add_vertex(n * r)
	_grid_indices(st, nu, nv, false)
	st.generate_tangents()
	return st.commit()


## 寄生虫的一截：两头收尖的管，UV0 在图的右半边（v 沿长度）
func _parasite(radius: float, length: float) -> ArrayMesh:
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var nu := 24
	var nv := 40
	for j in nv + 1:
		var v := float(j) / nv
		var y := v * length
		var rr := radius * pow(sin(PI * clampf(v * 1.1, 0.0, 1.0)), 0.5) * (1.0 - 0.4 * v) + 0.005
		var sway := sin(v * 5.0) * 0.06
		for i in nu + 1:
			var u := float(i) / nu
			var a := TAU * u
			st.set_uv(Vector2(0.5 + (1.0 - u) * 0.5, v))
			st.set_uv2(Vector2(0.08, 0.6))
			st.set_color(Color(0.0, 0.0, 0.6, 1.0))
			st.add_vertex(Vector3(cos(a) * rr + sway, -y, sin(a) * rr))
	_grid_indices(st, nu, nv, true)
	st.generate_normals()
	st.generate_tangents()
	return st.commit()


## 鳍：有厚度的板（前后两面），UV0：u 横跨（0～1 = w 米），v = 离鳍缘（上边）的距离 / w
func _fin(w: float, h: float) -> ArrayMesh:
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var nu := 40
	var nv := 30
	for side in 2:
		var base := side * (nu + 1) * (nv + 1)
		for j in nv + 1:
			var v := float(j) / nv
			for i in nu + 1:
				var u := float(i) / nu
				var x := (u - 0.5) * w
				var y := (1.0 - v) * h
				var th := 0.02 + 0.1 * v
				var z := sin(u * 18.0) * 0.04 * (1.0 - v) + (th if side == 0 else -th)
				st.set_uv(Vector2(u if side == 0 else 1.0 - u, v * h / w))
				st.set_uv2(Vector2(0.3, 0.6))
				st.set_color(Color(0.0, 0.0, 0.6, 1.0))
				st.add_vertex(Vector3(x, y, z))
		for j in nv:
			for i in nu:
				var a := base + j * (nu + 1) + i
				var b := a + nu + 1
				if side == 0:
					st.add_index(a); st.add_index(a + 1); st.add_index(b)
					st.add_index(a + 1); st.add_index(b + 1); st.add_index(b)
				else:
					st.add_index(a); st.add_index(b); st.add_index(a + 1)
					st.add_index(a + 1); st.add_index(b); st.add_index(b + 1)
	st.generate_normals()
	st.generate_tangents()
	return st.commit()
