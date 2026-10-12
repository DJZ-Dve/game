class_name LiftCab
extends Node3D
## 冰井的升降机轿厢（齿轮齿条自爬式，像施工升降机）。docs/design.md「八、开场 · 下井」：四个菜鸟坐它下到井底的前进基地。
## 20 公里没法用钢丝绳吊（现实里一段提升最多三四公里）：轿厢挂在井壁方位角 0 的两根 T 形导轨上，背后驱动架上两台电机
## 经减速箱带小齿轮咬着导轨中间的齿条往下爬，电从井壁上的滑触线取——没有长度限制，单程一个多小时。
## 用在两个地方：开场镜头里它在镜头下方往下走（scripts/intro/shaft_blackout.gd，detail = 1），
## 开局后的下井（加载画面，scripts/shaft/lift_ride.gd，detail = 0）：四个人坐在里面，看得见整口井。
##
## 局部坐标：x 沿井壁切向、y 朝上、z 径向朝外（朝井壁）；原点在轿厢地板面正中。坐在里面面朝井心（-z）时 +x 在右手边。
## 净空 2.4 × 2.0 × 2.3 米。朝井心那面是钢丝网（三块网片、两根竖撑、腰上一道横撑），左右两侧前半截是网片、后半截是
## 黄色的推拉门（停在某圈走台时对着走台的断头；门往前推开，挂在门顶的轨道上），背后是实心钢板墙（操纵箱、电气柜、
## 灭火器、电铃），顶上是钢板顶（井里会掉冰块），顶上一圈护栏、一盏旋转警示灯，背后的驱动架伸出顶板 1.4 米，
## 两台电机横着朝井心；底下一盏往下照的灯（看下面的导轨）。两侧前半截各一条折叠长凳，一边两个座位。
## 漆：褪了色的信号橙，掉漆露出红丹、再露出钢，顶上、横撑朝上的面结霜（worn_surface 的 primer/chip/warp，不要干净金属）。

const W := 1.2           # 净空半宽（x）
const D := 1.0           # 净空半深（z）
const H := 2.3           # 净空高
const OUT_X := 1.28      # 立柱外沿
const OUT_Z := 1.08
const ROOF := 2.42       # 顶板面
const KICK := 0.25       # 网片下面的实心踢脚板
const MID_Y := 1.05      # 网墙腰上的横撑
const DOOR_Z0 := -0.04   # 两侧推拉门的门洞（z）
const DOOR_Z1 := 0.94
const DOOR_TOP := 2.12
const DOOR_X := 1.3      # 门扇（在墙外侧，顺着门顶的轨道往前推开）
const MAX_X := 1.35      # 最宽的地方（门轨），冰井走台的缺口要让出这么宽再加余量
const DRIVE_TOP := 3.82  # 背后驱动架的顶
const GUIDE_X := 0.54    # 两根 T 形导轨的腹板（井壁方位角 ±0.05）
const BACK_GAP := 0.33   # 轿厢背板离井壁多远（导轨、齿条、滑触线都在这道缝里）
const SEAT_Y := 0.46
const SEAT_DEPTH := 0.4
const SEAT_ZS := [-0.75, -0.32]   # 每条长凳两个座位的中心（z）
const TUBE_COLOR := Color(0.86, 1.0, 0.93)    # 日光灯管（偏一点绿）
const BEACON_COLOR := Color(1.0, 0.48, 0.06)
const HEAD_COLOR := Color(1.0, 0.93, 0.82)

## 0：近看（下井时坐在里面）；1：远看（开场镜头里在几十米外）——灯少、不投影、圆的东西段数少
@export var detail := 0
## 轿厢里的电（1 = 正常；跟着井里的电压沉、闪，0 = 断电）：灯管、灯光、警示灯、下照灯、显示屏都跟着
var power := 1.0
## 操纵箱上显示的深度（米，正数）
var depth_m := 0.0
## 四个座位的挂点（RoomWalker.sit_at 用：位置 = 坐着时的眼睛，-Z = 面朝的方向）；左边两个、右边两个
var seats: Array[Node3D] = []

var _sts := {}
var _mats := {}
var _lights: Array[Light3D] = []
var _light_base: Array[float] = []
var _emissive: Array = []          # [材质, 正常时的发光强度]
var _beacon: Node3D
var _beacon_spin := 0.0
var _display: Label3D
var _shown_depth := -1


## 挂在井壁方位角 a 上、地板面在 y 的变换（井的半径 r）：-z 朝井心，右手系（不能用 MeshKit.radial_basis，那个是镜像的）
static func mount(r: float, a: float, y: float) -> Transform3D:
	var radial := Vector3(cos(a), 0.0, sin(a))
	var b := Basis(Vector3.UP.cross(radial), Vector3.UP, radial)
	return Transform3D(b, radial * (r - BACK_GAP - OUT_Z) + Vector3(0, y, 0))


func _ready() -> void:
	_build_materials()
	_build_floor_roof()
	_build_walls()
	_build_doors()
	_build_drive()
	_build_roof_gear()
	if detail == 0:
		_build_interior()
	_build_seats()
	_build_lamps()
	for key: String in _sts:
		var mi := MeshInstance3D.new()
		mi.name = key.capitalize().replace(" ", "")
		mi.mesh = (_sts[key] as SurfaceTool).commit()
		mi.material_override = _mats[key]
		if key in ["tube", "glow", "rubber"]:
			mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		add_child(mi)
	_sts.clear()
	set_power(power)


func _process(delta: float) -> void:
	# 警示灯一秒转一圈多；没电了停在那儿
	if _beacon and power > 0.3:
		_beacon_spin = fposmod(_beacon_spin + delta * TAU * 1.3, TAU)
		_beacon.rotation.y = _beacon_spin
	if _display:
		var d := roundi(depth_m)
		if d != _shown_depth:
			_shown_depth = d
			# DSEG7 里空格比数字窄，补位用“!”（和数字一样宽的空白）
			_display.text = ("%5d" % clampi(d, 0, 99999)).replace(" ", "!")


## 灯、警示灯、下照灯、显示屏的亮度跟着电走
func set_power(p: float) -> void:
	power = p
	for i in _lights.size():
		_lights[i].light_energy = _light_base[i] * p
		_lights[i].visible = p > 0.002
	for e in _emissive:
		(e[0] as StandardMaterial3D).emission_energy_multiplier = float(e[1]) * p
	if _display:
		_display.modulate = Color(2.4, 0.32, 0.08) * clampf(p, 0.0, 1.2)
		_display.visible = p > 0.05


# ---------------------------------------------------------------------------- 材质
func _build_materials() -> void:
	var chip: Texture2D = load("res://assets/third_party/ambientcg/PaintedMetal005/PaintedMetal005_2K-JPG_Opacity.jpg")
	var frost := Color(0.72, 0.78, 0.82)
	# 车身：褪了色的信号橙
	var body: ShaderMaterial = load("res://assets/materials/M_SteelOld.tres").duplicate()
	body.set_shader_parameter("paint_color", Color(0.62, 0.21, 0.04))
	body.set_shader_parameter("paint_metallic", 0.0)
	body.set_shader_parameter("paint_roughness", 0.6)
	body.set_shader_parameter("paint_variation", 0.25)
	body.set_shader_parameter("rust_amount", 0.12)
	body.set_shader_parameter("primer_amount", 0.25)
	body.set_shader_parameter("chip_tex", chip)
	body.set_shader_parameter("chip_amount", 0.3)
	body.set_shader_parameter("chip_scale", 3.0)
	body.set_shader_parameter("chip_cover", 0.2)
	body.set_shader_parameter("bare_rust", 0.5)
	body.set_shader_parameter("dust_color", frost)
	body.set_shader_parameter("dust_amount", 0.25)
	body.set_shader_parameter("floor_dirt", 0.0)
	body.set_shader_parameter("warp_amount", 0.6)
	_mats["body"] = body
	# 里面的衬板、操纵箱、电气柜：浅灰绿，下沿脏
	var inner: ShaderMaterial = body.duplicate()
	inner.set_shader_parameter("paint_color", Color(0.5, 0.55, 0.51))
	inner.set_shader_parameter("rust_amount", 0.05)
	inner.set_shader_parameter("chip_amount", 0.12)
	inner.set_shader_parameter("chip_cover", 0.12)
	inner.set_shader_parameter("primer_amount", 0.1)
	inner.set_shader_parameter("bare_rust", 0.2)
	inner.set_shader_parameter("dust_amount", 0.05)
	inner.set_shader_parameter("floor_dirt", 0.5)
	inner.set_shader_parameter("floor_height", 0.3)
	inner.set_shader_parameter("smudge_amount", 0.4)
	_mats["inner"] = inner
	# 驱动架、电机、减速箱、导靴：深灰
	var dark: ShaderMaterial = body.duplicate()
	dark.set_shader_parameter("paint_color", Color(0.17, 0.19, 0.19))
	dark.set_shader_parameter("chip_amount", 0.25)
	dark.set_shader_parameter("rust_amount", 0.25)
	_mats["dark"] = dark
	# 门框、护栏、扶手：安全黄（和走台扶手一样）
	var yellow: ShaderMaterial = load("res://assets/materials/M_Rail.tres").duplicate()
	yellow.set_shader_parameter("paint_color", Color(0.72, 0.52, 0.08))
	yellow.set_shader_parameter("paint_metallic", 0.0)
	yellow.set_shader_parameter("paint_roughness", 0.55)
	yellow.set_shader_parameter("paint_variation", 0.25)
	yellow.set_shader_parameter("edge_wear", 1.0)
	yellow.set_shader_parameter("primer_amount", 0.3)
	yellow.set_shader_parameter("chip_tex", chip)
	yellow.set_shader_parameter("chip_amount", 0.35)
	yellow.set_shader_parameter("chip_scale", 4.0)
	yellow.set_shader_parameter("chip_cover", 0.3)
	yellow.set_shader_parameter("bare_rust", 0.6)
	yellow.set_shader_parameter("bare_roughness", 0.3)
	yellow.set_shader_parameter("dust_color", frost)
	yellow.set_shader_parameter("dust_amount", 0.2)
	yellow.set_shader_parameter("floor_dirt", 0.0)
	_mats["yellow"] = yellow
	# 地板：花纹钢板，中间被踩亮
	var floor_mat: ShaderMaterial = load("res://assets/materials/M_Deck.tres").duplicate()
	floor_mat.set_shader_parameter("paint_color", Color(0.3, 0.31, 0.3))
	floor_mat.set_shader_parameter("dust_color", frost)
	floor_mat.set_shader_parameter("dust_amount", 0.15)
	_mats["floor"] = floor_mat
	var mesh := ShaderMaterial.new()
	mesh.shader = preload("res://assets/shaders/wire_mesh.gdshader")
	_mats["mesh"] = mesh
	_mats["rubber"] = load("res://assets/materials/M_Rubber.tres")
	var seat := StandardMaterial3D.new()
	seat.albedo_color = Color(0.13, 0.12, 0.11)
	seat.roughness = 0.55
	_mats["seat"] = seat
	_mats["red"] = load("res://assets/materials/M_PlasticRed.tres")
	_mats["black"] = load("res://assets/materials/M_PanelBlack.tres")
	_mats["green"] = load("res://assets/materials/M_BtnGreen.tres")
	_mats["btn_red"] = load("res://assets/materials/M_BtnRed.tres")
	_mats["btn_yellow"] = load("res://assets/materials/M_BtnYellow.tres")
	var plate := StandardMaterial3D.new()
	plate.albedo_color = Color(0.78, 0.78, 0.74)
	plate.roughness = 0.45
	_mats["plate"] = plate
	# 发光的：灯管、警示灯罩、下照灯玻璃（亮度跟着电走，见 set_power）
	_mats["tube"] = _glow_mat(TUBE_COLOR, 1.4, Color(0.9, 0.95, 0.93))
	_mats["glow"] = _glow_mat(BEACON_COLOR, 6.0 if detail == 0 else 14.0, Color(0.6, 0.3, 0.05), 0.55)
	_mats["lens"] = _glow_mat(HEAD_COLOR, 5.0, Color(0.8, 0.8, 0.78))


func _glow_mat(col: Color, energy: float, albedo: Color, alpha := 1.0) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.albedo_color = Color(albedo.r, albedo.g, albedo.b, alpha)
	if alpha < 1.0:
		m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	m.roughness = 0.3
	m.emission_enabled = true
	m.emission = col
	m.emission_energy_multiplier = energy
	_emissive.append([m, energy])
	return m


# ---------------------------------------------------------------------------- 搭模型的小工具
func _st(key: String) -> SurfaceTool:
	if not _sts.has(key):
		var st := SurfaceTool.new()
		st.begin(Mesh.PRIMITIVE_TRIANGLES)
		st.set_color(Color(0.3, 0.25, 0, 1))
		_sts[key] = st
	return _sts[key]


## 按最小、最大角点给的盒子
func _bx(key: String, x0: float, x1: float, y0: float, y1: float, z0: float, z1: float) -> void:
	MeshKit.box(_st(key), Transform3D(Basis(), Vector3((x0 + x1) * 0.5, (y0 + y1) * 0.5, (z0 + z1) * 0.5)),
		Vector3(absf(x1 - x0), absf(y1 - y0), absf(z1 - z0)))


func _cy(key: String, a: Vector3, b: Vector3, r: float, sides: int, caps := true) -> void:
	MeshKit.cyl(_st(key), a, b, r, maxi(4, sides if detail == 0 else sides / 2), caps)


## 一块平的网片（两面都画）：法线沿 x 或 z
func _mesh_panel(a: Vector3, b: Vector3, c: Vector3, d: Vector3, n: Vector3) -> void:
	MeshKit.quad(_st("mesh"), a, b, c, d, n)


## 两侧各算一遍（s = -1 左、+1 右）
func _sides(fn: Callable) -> void:
	for s: float in [-1.0, 1.0]:
		fn.call(s)


# ---------------------------------------------------------------------------- 底盘、顶板、立柱
func _build_floor_roof() -> void:
	# 地板：花纹钢板铺在一圈槽钢底框上，底下三根横梁
	_bx("floor", -W, W, -0.008, 0.0, -D, D)
	_bx("body", -OUT_X, OUT_X, -0.2, 0.0, -OUT_Z, -D)
	_bx("body", -OUT_X, OUT_X, -0.2, 0.0, D, OUT_Z)
	_sides(func(s: float) -> void: _bx("body", s * W, s * OUT_X, -0.2, 0.0, -D, D))
	for z: float in [-0.5, 0.0, 0.5]:
		_bx("body", -W, W, -0.2, -0.008, z - 0.04, z + 0.04)
	# 四角立柱（80 方管）
	for sx: float in [-1.0, 1.0]:
		for sz: float in [-1.0, 1.0]:
			_bx("body", sx * W, sx * OUT_X, -0.2, ROOF, sz * D, sz * OUT_Z)
	# 顶上一圈围板（墙顶到顶板）、顶板、里面的顶棚衬板
	_bx("body", -OUT_X, OUT_X, H, ROOF, -OUT_Z, -D)
	_bx("body", -OUT_X, OUT_X, H, ROOF, D, OUT_Z)
	_sides(func(s: float) -> void: _bx("body", s * W, s * OUT_X, H, ROOF, -D, D))
	_bx("body", -OUT_X, OUT_X, ROOF - 0.008, ROOF, -OUT_Z, OUT_Z)
	_bx("inner", -W, W, H, H + 0.01, -D, D)
	# 顶棚上的检修口（里面看是一圈口框，外面是盖板）
	var hx := -0.55   # 在两盏灯中间
	var hz := 0.0
	for s: float in [-1.0, 1.0]:
		_bx("inner", hx - 0.3, hx + 0.3, H - 0.02, H, hz + s * 0.27, hz + s * 0.3)
		_bx("inner", hx + s * 0.27, hx + s * 0.3, H - 0.02, H, hz - 0.3, hz + 0.3)
	_bx("body", hx - 0.32, hx + 0.32, ROOF, ROOF + 0.05, hz - 0.32, hz + 0.32)
	_bx("body", hx - 0.34, hx + 0.34, ROOF + 0.05, ROOF + 0.06, hz - 0.34, hz + 0.34)
	_bx("dark", hx - 0.1, hx + 0.1, ROOF + 0.06, ROOF + 0.09, hz - 0.26, hz - 0.22)   # 拉手
	for s: float in [-1.0, 1.0]:
		_cy("dark", Vector3(hx - 0.34, ROOF + 0.07, hz + s * 0.2 - 0.06), Vector3(hx - 0.34, ROOF + 0.07, hz + s * 0.2 + 0.06), 0.018, 8)


# ---------------------------------------------------------------------------- 墙：前面的网墙、两侧前半截、背后的钢板墙
func _build_walls() -> void:
	var fz := -(D + 0.04)   # 前墙所在的平面（立柱中线）
	_bx("body", -W, W, 0.0, KICK, fz - 0.01, fz + 0.01)
	_bx("body", -W, W, MID_Y - 0.03, MID_Y + 0.03, fz - 0.03, fz + 0.03)
	for x: float in [-0.4, 0.4]:
		_bx("body", x - 0.025, x + 0.025, KICK, H, fz - 0.025, fz + 0.025)
	for span in [[-W, -0.425], [-0.375, 0.375], [0.425, W]]:
		var x0: float = span[0]
		var x1: float = span[1]
		_mesh_panel(Vector3(x0, KICK, fz), Vector3(x1, KICK, fz), Vector3(x1, H, fz), Vector3(x0, H, fz), Vector3(0, 0, -1))
	# 两侧：前半截是网片（里面靠着长凳），后半截是门洞；门洞两边一根门柱、上面一块门楣
	_sides(func(s: float) -> void:
		var x := s * (W + 0.04)
		var z1 := DOOR_Z0 - 0.05
		_bx("body", x - 0.01, x + 0.01, 0.0, KICK, -D, z1)
		_bx("body", x - 0.03, x + 0.03, MID_Y - 0.03, MID_Y + 0.03, -D, z1)
		_mesh_panel(Vector3(x, KICK, -D), Vector3(x, KICK, z1), Vector3(x, H, z1), Vector3(x, H, -D), Vector3(s, 0, 0))
		for z: float in [DOOR_Z0 - 0.025, DOOR_Z1 + 0.025]:
			_bx("body", x - 0.025, x + 0.025, 0.0, H, z - 0.025, z + 0.025)
		_bx("body", x - 0.01, x + 0.01, DOOR_TOP, H, DOOR_Z0, DOOR_Z1))
	# 背后：外面一层钢板（橙）、里面一层衬板（浅灰绿），竖着三道加强筋
	_bx("body", -W, W, 0.0, H, D + 0.03, D + 0.05)
	_bx("inner", -W, W, 0.0, H, D, D + 0.03)
	for x: float in [-0.6, 0.0, 0.6]:
		_bx("body", x - 0.03, x + 0.03, 0.0, H, D + 0.05, D + 0.07)
	# 里面朝井心那面的扶手（安全黄，离网片 7 厘米，三个支架）
	var st := _st("yellow")
	MeshKit.cyl(st, Vector3(-W + 0.12, 1.0, -D + 0.07), Vector3(W - 0.12, 1.0, -D + 0.07), 0.02, 10 if detail == 0 else 6, true, true)
	st.set_color(Color(0.3, 0.25, 0, 1))
	for x: float in [-0.9, 0.0, 0.9]:
		_bx("yellow", x - 0.012, x + 0.012, 0.975, 1.0, -D - 0.02, -D + 0.07)


# ---------------------------------------------------------------------------- 推拉门（关着；在墙外侧，顺着门顶的轨道往前推开）
func _build_doors() -> void:
	_sides(func(s: float) -> void:
		var x := s * DOOR_X
		var z0 := DOOR_Z0 - 0.03
		var z1 := DOOR_Z1 + 0.03
		var y0 := 0.04
		var y1 := DOOR_TOP - 0.02
		var t := 0.02
		# 门框（40 方管）、腰上一道横档、底下一块踢脚板，中间钢丝网
		_bx("yellow", x - t, x + t, y0, y1, z0, z0 + 2.0 * t)
		_bx("yellow", x - t, x + t, y0, y1, z1 - 2.0 * t, z1)
		_bx("yellow", x - t, x + t, y1 - 2.0 * t, y1, z0, z1)
		_bx("yellow", x - t, x + t, y0, y0 + 0.2, z0, z1)
		_bx("yellow", x - t, x + t, MID_Y - t, MID_Y + t, z0, z1)
		_mesh_panel(Vector3(x, y0 + 0.2, z0), Vector3(x, y0 + 0.2, z1), Vector3(x, y1, z1), Vector3(x, y1, z0), Vector3(s, 0, 0))
		# 拉手（门外、门里各一根竖着的圆钢，焊在门框的竖管上）
		for side: float in [1.0, -1.0]:
			var hx := x + s * side * 0.06
			_cy("dark", Vector3(hx, 0.9, z1 - 0.02), Vector3(hx, 1.25, z1 - 0.02), 0.014, 8)
			for hy: float in [0.93, 1.22]:
				_bx("dark", minf(x, hx), maxf(x, hx), hy - 0.01, hy + 0.01, z1 - 0.03, z1 - 0.01)
		# 门顶的轨道（槽钢，一直伸到前面，门推开以后挂在前半截墙外面）、两个吊轮
		_bx("body", x - 0.04, x + 0.05 * s, DOOR_TOP, DOOR_TOP + 0.09, -OUT_Z, DOOR_Z1 + 0.06)
		for z: float in [z0 + 0.12, z1 - 0.12]:
			_cy("rubber", Vector3(x, DOOR_TOP + 0.04, z - 0.04), Vector3(x, DOOR_TOP + 0.04, z + 0.04), 0.035, 12)
			_bx("dark", x - 0.006, x + 0.006, y1, DOOR_TOP + 0.04, z - 0.02, z + 0.02)
		# 门锁的联锁开关（门没关好轿厢不走）
		_bx("dark", x - 0.03, x + 0.03, DOOR_TOP - 0.16, DOOR_TOP - 0.02, DOOR_Z1 + 0.06, DOOR_Z1 + 0.14))


# ---------------------------------------------------------------------------- 背后：驱动架、导靴、小齿轮、滑触线的集电器
func _build_drive() -> void:
	# 驱动架：一块竖着的钢板贴着轿厢背后，从底框一直伸到顶板上面 1.4 米；顶板上面两块三角筋撑着
	_bx("dark", -0.7, 0.7, -0.2, DRIVE_TOP, OUT_Z, OUT_Z + 0.02)
	for x: float in [-0.66, 0.66]:
		var st := _st("dark")
		var a := Vector3(x, ROOF, OUT_Z)
		var b := Vector3(x, ROOF, OUT_Z - 0.45)
		var c := Vector3(x, ROOF + 0.8, OUT_Z)
		for off: float in [-0.008, 0.008]:
			var o := Vector3(off, 0, 0)
			MeshKit.tri(st, a + o, b + o, c + o, Vector3(signf(off), 0, 0), Vector3(signf(off), 0, 0), Vector3(signf(off), 0, 0))
		MeshKit.quad(st, b + Vector3(-0.008, 0, 0), b + Vector3(0.008, 0, 0), c + Vector3(0.008, 0, 0), c + Vector3(-0.008, 0, 0),
			(Vector3(0, 0.45, -0.8)).normalized())
	_bx("dark", -0.72, 0.72, DRIVE_TOP - 0.06, DRIVE_TOP, OUT_Z - 0.12, OUT_Z + 0.02)
	# 两台驱动：减速箱贴着驱动架，电机横着朝井心，尾巴上是制动器和风扇罩，顶上一个接线盒
	for yc: float in [ROOF + 0.38, ROOF + 0.98]:
		_bx("dark", 0.02, 0.44, yc - 0.17, yc + 0.17, OUT_Z - 0.3, OUT_Z)
		_bx("dark", 0.06, 0.4, yc - 0.19, yc - 0.17, OUT_Z - 0.32, OUT_Z)
		var mx := 0.23
		var motor_z0 := OUT_Z - 0.3
		var motor_z1 := motor_z0 - 0.5
		_cy("dark", Vector3(mx, yc, motor_z0), Vector3(mx, yc, motor_z1), 0.13, 20)
		# 散热筋
		if detail == 0:
			for k in 12:
				var ang := TAU * k / 12.0
				var dir := Vector3(cos(ang), sin(ang), 0)
				var c := Vector3(mx, yc, (motor_z0 + motor_z1) * 0.5) + dir * 0.145
				MeshKit.box(_st("dark"), Transform3D(Basis(dir.cross(Vector3.BACK), dir, Vector3.BACK).orthonormalized(), c),
					Vector3(0.008, 0.03, 0.46))
		_cy("dark", Vector3(mx, yc, motor_z1), Vector3(mx, yc, motor_z1 - 0.08), 0.115, 20)
		_cy("dark", Vector3(mx, yc, motor_z1 - 0.08), Vector3(mx, yc, motor_z1 - 0.2), 0.14, 20)
		_bx("dark", mx - 0.08, mx + 0.08, yc + 0.12, yc + 0.22, motor_z0 - 0.3, motor_z0 - 0.12)
		# 小齿轮：减速箱的轴穿过驱动架，在背后咬着齿条（齿面离轿厢背板 0.11 米），旁边一块轴承座
		_bx("dark", 0.05, 0.14, yc - 0.1, yc + 0.1, OUT_Z + 0.02, OUT_Z + 0.09)
		_cy("dark", Vector3(-0.045, yc, OUT_Z + 0.05), Vector3(0.05, yc, OUT_Z + 0.05), 0.06, 18)
	# 防坠安全器（自己一个小齿轮咬齿条，超速就刹死）
	_bx("dark", 0.05, 0.17, 0.55, 0.85, OUT_Z + 0.02, OUT_Z + 0.09)
	_cy("dark", Vector3(-0.04, 0.7, OUT_Z + 0.06), Vector3(0.05, 0.7, OUT_Z + 0.06), 0.05, 14)
	_bx("btn_red", 0.07, 0.15, 0.86, 0.9, OUT_Z + 0.03, OUT_Z + 0.08)
	# 导靴：上中下三组，每组两边的颊板夹着导轨腹板，四个侧轮滚腹板的两面，一个面轮顶着腹板的边
	var web_z0 := OUT_Z + BACK_GAP - 0.255   # 腹板内边（离井壁 0.255 米）在轿厢坐标里的 z
	for y0: float in [0.05, ROOF - 0.08, DRIVE_TOP - 0.2]:
		for gx: float in [-GUIDE_X, GUIDE_X]:
			for s: float in [-1.0, 1.0]:
				_bx("dark", gx + s * 0.07, gx + s * 0.082, y0 - 0.1, y0 + 0.1, OUT_Z, web_z0 + 0.07)
				for dy: float in [-0.055, 0.055]:
					var rx: float = gx + s * (0.009 + 0.032)
					_cy("rubber", Vector3(rx, y0 + dy, web_z0 + 0.025), Vector3(rx, y0 + dy, web_z0 + 0.075), 0.03, 12)
			_cy("rubber", Vector3(gx - 0.035, y0, web_z0 - 0.03), Vector3(gx + 0.035, y0, web_z0 - 0.03), 0.03, 12)
	# 滑触线的集电器：右后角伸出一根臂，四个碳刷压在井壁的滑触线上
	_bx("dark", 0.86, 1.18, 1.0, 1.08, OUT_Z, OUT_Z + 0.06)
	for k in 4:
		var x := 0.95 + 0.06 * k
		_bx("dark", x - 0.012, x + 0.012, 0.98, 1.1, OUT_Z + 0.06, OUT_Z + 0.1)
	_bx("dark", 0.9, 1.15, 0.5, 0.98, OUT_Z + 0.02, OUT_Z + 0.08)


# ---------------------------------------------------------------------------- 顶上：护栏、警示灯；底下：下照灯
func _build_roof_gear() -> void:
	# 护栏：前面、两侧（后面是驱动架），立柱、上下两道横杆、一圈踢脚板
	var y := ROOF
	var xr := OUT_X - 0.03
	var zf := -OUT_Z + 0.03
	var zb := OUT_Z - 0.32
	var st := _st("yellow")
	for h: float in [1.0, 0.52]:
		var pts: Array[Vector3] = [Vector3(-xr, y + h, zb), Vector3(-xr, y + h, zf), Vector3(xr, y + h, zf), Vector3(xr, y + h, zb)]
		MeshKit.tube(st, pts, 0.02, 10 if detail == 0 else 6)
	for p: Vector2 in [Vector2(-xr, zb), Vector2(-xr, zf), Vector2(0.0, zf), Vector2(xr, zf), Vector2(xr, zb), Vector2(-xr, -0.3), Vector2(xr, -0.3)]:
		_cy("yellow", Vector3(p.x, y, p.y), Vector3(p.x, y + 1.0, p.y), 0.02, 10)
	_bx("yellow", -xr, xr, y, y + 0.1, zf - 0.005, zf + 0.005)
	_sides(func(s: float) -> void: _bx("yellow", s * xr - 0.005, s * xr + 0.005, y, y + 0.1, zf, zb))
	# 旋转警示灯：右前角一根短杆上，黑色底座、琥珀色灯罩，里面两盏背靠背的灯转着
	var bp := Vector3(W - 0.12, ROOF, -D + 0.14)
	_cy("dark", bp, bp + Vector3(0, 0.12, 0), 0.02, 8)
	_cy("black", bp + Vector3(0, 0.12, 0), bp + Vector3(0, 0.16, 0), 0.065, 16)
	var dome: Array[Vector2] = [Vector2(0.0, 0.13), Vector2(0.03, 0.125), Vector2(0.05, 0.1), Vector2(0.058, 0.06), Vector2(0.06, 0.0)]
	MeshKit.lathe(_st("glow"), bp + Vector3(0, 0.16, 0), dome, 16 if detail == 0 else 10)
	_beacon = Node3D.new()
	_beacon.position = bp + Vector3(0, 0.22, 0)
	add_child(_beacon)
	for k in 2:
		var sl := SpotLight3D.new()
		sl.rotation.y = PI * k
		sl.rotation.x = deg_to_rad(-1.0)
		sl.light_color = BEACON_COLOR
		sl.spot_range = 26.0
		sl.spot_angle = 11.0
		sl.spot_attenuation = 1.3
		sl.spot_angle_attenuation = 0.6
		sl.light_volumetric_fog_energy = 1.6
		_beacon.add_child(sl)
		_lights.append(sl)
		_light_base.append(9.0)
	# 下照灯：地板底下前沿正中，往下照着导轨和下面的走台（看下面有没有东西挡着）
	var hp := Vector3(0.0, -0.2, -D + 0.12)
	_bx("dark", hp.x - 0.14, hp.x + 0.14, hp.y - 0.12, hp.y, hp.z - 0.09, hp.z + 0.09)
	_bx("lens", hp.x - 0.11, hp.x + 0.11, hp.y - 0.125, hp.y - 0.12, hp.z - 0.07, hp.z + 0.07)
	var hl := SpotLight3D.new()
	hl.position = hp + Vector3(0, -0.14, 0)
	hl.rotation.x = deg_to_rad(-90.0 + 6.0)
	hl.light_color = HEAD_COLOR
	hl.spot_range = 45.0
	hl.spot_angle = 24.0
	hl.spot_attenuation = 1.1
	hl.spot_angle_attenuation = 0.5
	hl.light_volumetric_fog_energy = 1.4
	add_child(hl)
	_lights.append(hl)
	_light_base.append(9.0)


# ---------------------------------------------------------------------------- 顶棚的日光灯
func _build_lamps() -> void:
	for z: float in [-0.42, 0.42]:
		_bx("inner", -0.62, 0.62, H - 0.07, H, z - 0.08, z + 0.08)
		for dz: float in [-0.035, 0.035]:
			_cy("tube", Vector3(-0.58, H - 0.085, z + dz), Vector3(0.58, H - 0.085, z + dz), 0.013, 10, false)
		# 护网：几道 U 形的圆钢兜住灯管
		if detail == 0:
			for x: float in [-0.45, -0.15, 0.15, 0.45]:
				var pts: Array[Vector3] = [Vector3(x, H - 0.07, z - 0.075), Vector3(x, H - 0.12, z - 0.075),
					Vector3(x, H - 0.13, z - 0.04), Vector3(x, H - 0.13, z + 0.04), Vector3(x, H - 0.12, z + 0.075), Vector3(x, H - 0.07, z + 0.075)]
				MeshKit.tube(_st("dark"), pts, 0.003, 4)
			for dz: float in [-0.075, 0.075]:
				_cy("dark", Vector3(-0.6, H - 0.1, z + dz), Vector3(0.6, H - 0.1, z + dz), 0.003, 4, false)
	var n := 2 if detail == 0 else 1
	for i in n:
		var ol := OmniLight3D.new()
		ol.position = Vector3(0, H - 0.2, 0.0 if n == 1 else (-0.42 if i == 0 else 0.42))
		ol.light_color = TUBE_COLOR
		ol.omni_range = 5.5
		ol.omni_attenuation = 1.3
		ol.light_volumetric_fog_energy = 0.6
		ol.light_size = 0.3
		# 近看的时候前面那盏投影：灯光穿过钢丝网，在走台、冰上照出一格格的影子
		ol.shadow_enabled = detail == 0 and i == 0
		ol.shadow_blur = 1.2
		add_child(ol)
		_lights.append(ol)
		# 远看的时候亮一点：几十米外看得出是一个亮着的笼子在往下走
		_light_base.append(1.6 if n == 2 else 4.5)


# ---------------------------------------------------------------------------- 两侧的折叠长凳（每边两个座位）
func _build_seats() -> void:
	_sides(func(s: float) -> void:
		var x0 := s * W
		var x1 := s * (W - SEAT_DEPTH)
		var za := -D + 0.03
		var zb := DOOR_Z0 - 0.08
		# 凳面的框（铰链在墙上）、两根斜撑、两块坐垫；墙上一条靠背垫
		_bx("dark", minf(x0, x1), maxf(x0, x1), SEAT_Y - 0.05, SEAT_Y - 0.02, za, zb)
		for z: float in [za + 0.06, zb - 0.06]:
			MeshKit.beam(_st("dark"), Vector3(x0, 0.12, z), Vector3(x1 + s * 0.04, SEAT_Y - 0.05, z), Vector2(0.03, 0.03), Vector3(0, 0, 1))
			_bx("dark", x0 - s * 0.01, x0 - s * 0.03, 0.08, 0.2, z - 0.03, z + 0.03)
		for zc: float in SEAT_ZS:
			_bx("seat", minf(x0, x1) + 0.01, maxf(x0, x1) - 0.01, SEAT_Y - 0.02, SEAT_Y + 0.03, zc - 0.205, zc + 0.205)
			_bx("seat", x0 - s * 0.05, x0 - s * 0.01, 0.62, 0.95, zc - 0.19, zc + 0.19)
		_bx("dark", x0 - s * 0.01, x0, 0.6, 0.97, za, zb)
		# 座位挂点：眼睛在坐垫上方 0.8 米、离靠背 0.22 米，面朝对面
		for zc: float in SEAT_ZS:
			var seat := Node3D.new()
			seat.name = "Seat%d" % seats.size()
			seat.position = Vector3(s * (W - 0.24), SEAT_Y + 0.8, zc)
			seat.rotation.y = s * PI * 0.5
			add_child(seat)
			seats.append(seat))


# ---------------------------------------------------------------------------- 里面：操纵箱、电话、电气柜、灭火器、电铃（远看不建）
func _build_interior() -> void:
	var bz := D   # 背板衬板的里面
	# 操纵箱（右边）：浅灰箱体、黑色面板；最上面一块深度显示（七段数码管，看得见没亮的笔画），
	# 下面一排按钮（上行、下行、停止）、急停蘑菇头、钥匙开关
	_bx("inner", 0.45, 0.97, 0.95, 1.6, bz - 0.15, bz)
	_bx("black", 0.48, 0.94, 0.98, 1.57, bz - 0.153, bz - 0.15)
	_bx("black", 0.52, 0.9, 1.4, 1.52, bz - 0.156, bz - 0.153)
	var ghost := _seven_seg(Vector3(0.71, 1.46, bz - 0.158), "88888", Color(0.09, 0.02, 0.01))
	ghost.modulate = Color(0.12, 0.03, 0.02)
	_display = _seven_seg(Vector3(0.71, 1.46, bz - 0.159), "!!!!0", Color(2.4, 0.32, 0.08))
	for b in [[0.57, "green"], [0.71, "green"], [0.85, "btn_red"]]:
		var bx: float = b[0]
		_cy("dark", Vector3(bx, 1.25, bz - 0.153), Vector3(bx, 1.25, bz - 0.163), 0.03, 16)
		_cy(b[1], Vector3(bx, 1.25, bz - 0.163), Vector3(bx, 1.25, bz - 0.175), 0.022, 16)
	_cy("btn_yellow", Vector3(0.62, 1.07, bz - 0.153), Vector3(0.62, 1.07, bz - 0.158), 0.05, 20)
	_cy("btn_red", Vector3(0.62, 1.07, bz - 0.158), Vector3(0.62, 1.07, bz - 0.19), 0.022, 16)
	MeshKit.lathe(_st("btn_red"), Vector3(0.62, 1.07, bz - 0.19), [Vector2(0.0, 0.0), Vector2(0.036, 0.0), Vector2(0.038, -0.012),
		Vector2(0.03, -0.022), Vector2(0.0, -0.026)], 16)
	_cy("dark", Vector3(0.84, 1.07, bz - 0.153), Vector3(0.84, 1.07, bz - 0.175), 0.018, 12)
	_bx("black", 0.835, 0.845, 1.06, 1.08, bz - 0.185, bz - 0.175)
	# 操纵箱的电缆管一直走到顶棚
	_cy("dark", Vector3(0.9, 1.6, bz - 0.05), Vector3(0.9, H, bz - 0.05), 0.016, 8)
	# 对讲电话（和井底、井口的调度通话）：灰绿的防水箱，左边竖着挂一个黑听筒（两头的听筒、话筒是圆的），
	# 右边上面一块喇叭的格栅、下面一块拨号盘
	_bx("inner", 0.13, 0.37, 1.16, 1.52, bz - 0.09, bz)
	_bx("black", 0.142, 0.358, 1.172, 1.508, bz - 0.092, bz - 0.09)
	_bx("black", 0.165, 0.2, 1.22, 1.46, bz - 0.125, bz - 0.095)
	for hy: float in [1.24, 1.44]:
		_cy("black", Vector3(0.1825, hy, bz - 0.095), Vector3(0.1825, hy, bz - 0.14), 0.034, 16)
	_bx("black", 0.16, 0.205, 1.33, 1.35, bz - 0.098, bz - 0.09)
	for k in 5:
		_bx("black", 0.24, 0.34, 1.425 + k * 0.014, 1.432 + k * 0.014, bz - 0.094, bz - 0.09)
	_bx("black", 0.24, 0.34, 1.2, 1.38, bz - 0.094, bz - 0.09)
	for k in 12:
		var kx := 0.258 + (k % 3) * 0.032
		var ky := 1.36 - (k / 3) * 0.042
		_bx("inner", kx - 0.011, kx + 0.011, ky - 0.012, ky + 0.012, bz - 0.1, bz - 0.094)
	# 电铃（红色圆盖）
	MeshKit.lathe(_st("btn_red"), Vector3(0.05, 2.05, bz - 0.02), [Vector2(0.0, 0.0), Vector2(0.09, 0.0), Vector2(0.09, -0.01),
		Vector2(0.075, -0.05), Vector2(0.03, -0.07), Vector2(0.0, -0.072)], 20)
	# 电气柜（左边）：门缝、拉手、百叶、电缆管
	_bx("inner", -1.05, -0.38, 0.28, 1.55, bz - 0.24, bz)
	_bx("dark", -1.03, -0.4, 0.3, 0.302, bz - 0.243, bz - 0.24)
	_bx("dark", -0.715, -0.712, 0.3, 1.53, bz - 0.243, bz - 0.24)
	for x: float in [-0.76, -0.67]:
		_bx("dark", x - 0.012, x + 0.012, 0.85, 1.0, bz - 0.27, bz - 0.24)
	for k in 6:
		_bx("dark", -1.0, -0.8, 0.4 + k * 0.035, 0.42 + k * 0.035, bz - 0.245, bz - 0.24)
	_cy("dark", Vector3(-0.41, 1.55, bz - 0.06), Vector3(-0.41, H, bz - 0.06), 0.022, 8)
	_cy("dark", Vector3(-1.02, 1.55, bz - 0.06), Vector3(-1.02, H, bz - 0.06), 0.016, 8)
	# 灭火器：靠背板中间，红筒、黑阀、一道卡箍
	var fx := Vector3(-0.15, 0.08, bz - 0.1)
	_cy("red", fx, fx + Vector3(0, 0.46, 0), 0.075, 18)
	MeshKit.lathe(_st("red"), fx + Vector3(0, 0.46, 0), [Vector2(0.0, 0.06), Vector2(0.04, 0.05), Vector2(0.07, 0.02), Vector2(0.075, 0.0)], 18)
	_cy("black", fx + Vector3(0, 0.52, 0), fx + Vector3(0, 0.6, 0), 0.022, 10)
	_bx("black", fx.x - 0.07, fx.x + 0.02, 0.58, 0.6, fx.z - 0.015, fx.z + 0.015)
	_bx("dark", fx.x - 0.085, fx.x + 0.085, 0.36, 0.4, fx.z - 0.01, bz)
	_build_signs(bz)


## 标牌（黑体，assets/fonts/NotoSansSC-Signs.ttf 是 tools/gen_sign_font.py 从这个脚本的字符串里抽字做的子集，
## 加了新字要重跑）：电气柜上面的铭牌、操纵箱上面的警示、按钮底下的字、电气柜门上的当心触电
func _build_signs(bz: float) -> void:
	var ink := Color(0.06, 0.06, 0.06)
	var red := Color(0.62, 0.05, 0.03)
	# 铭牌：白底黑字，四角铆钉
	_bx("plate", -0.98, -0.46, 1.68, 1.94, bz - 0.006, bz)
	for c: Vector2 in [Vector2(-0.965, 1.695), Vector2(-0.475, 1.695), Vector2(-0.965, 1.925), Vector2(-0.475, 1.925)]:
		_cy("dark", Vector3(c.x, c.y, bz - 0.006), Vector3(c.x, c.y, bz - 0.01), 0.006, 8)
	_sign("06 号升降机", Vector3(-0.72, 1.86, bz - 0.007), 0.058, ink)
	_sign("额定载重 2000 kg　限乘 12 人", Vector3(-0.72, 1.76, bz - 0.007), 0.024, ink)
	_bx("plate", 0.47, 0.95, 1.66, 1.78, bz - 0.006, bz)
	_sign("运行中严禁扒门", Vector3(0.71, 1.72, bz - 0.007), 0.045, red)
	# 操纵箱：按钮底下的字（白字）
	var white := Color(0.85, 0.85, 0.82)
	for b in [[0.57, "上行"], [0.71, "下行"], [0.85, "停止"]]:
		_sign(b[1], Vector3(b[0], 1.2, bz - 0.154), 0.018, white)
	_sign("急停", Vector3(0.62, 1.0, bz - 0.154), 0.018, white)
	_sign("调度", Vector3(0.29, 1.47, bz - 0.095), 0.016, white)
	# 电气柜门上：黄底的当心触电
	_bx("btn_yellow", -0.62, -0.46, 1.18, 1.34, bz - 0.244, bz - 0.24)
	_sign("当心触电", Vector3(-0.54, 1.22, bz - 0.245), 0.026, ink)
	# 闪电（画出来的，字体里没有这个符号）
	var bolt: Array[Vector2] = [Vector2(0.006, 0.03), Vector2(-0.014, -0.003), Vector2(-0.001, -0.003), Vector2(-0.008, -0.03),
		Vector2(0.014, 0.005), Vector2(0.001, 0.005), Vector2(0.012, 0.03)]
	var bc := Vector3(-0.54, 1.285, bz - 0.2445)
	var st := _st("black")
	for i in [[0, 1, 2], [0, 2, 5], [0, 5, 6], [2, 3, 4], [2, 4, 5]]:
		MeshKit.tri(st, bc + Vector3(-bolt[i[0]].x, bolt[i[0]].y, 0), bc + Vector3(-bolt[i[1]].x, bolt[i[1]].y, 0),
			bc + Vector3(-bolt[i[2]].x, bolt[i[2]].y, 0), Vector3.FORWARD, Vector3.FORWARD, Vector3.FORWARD)


func _sign(text: String, p: Vector3, height: float, col: Color) -> Label3D:
	var l := Label3D.new()
	l.font = preload("res://assets/fonts/NotoSansSC-Signs.ttf")
	l.text = text
	l.font_size = 64
	l.pixel_size = height / 64.0
	l.outline_size = 0
	l.modulate = col
	l.shaded = true
	l.double_sided = false
	l.alpha_cut = Label3D.ALPHA_CUT_OPAQUE_PREPASS
	l.position = p
	l.rotation.y = PI   # 背板上的字面朝 -z（轿厢里）
	add_child(l)
	return l


## 一行七段数码管的字（DSEG7，等宽）：贴在 p，面朝 -z
func _seven_seg(p: Vector3, text: String, col: Color) -> Label3D:
	var l := Label3D.new()
	l.font = load("res://assets/fonts/DSEG7Classic-Bold.ttf")
	l.text = text
	l.font_size = 64
	l.pixel_size = 0.0011
	l.outline_size = 0
	l.modulate = col
	l.position = p
	l.rotation.y = PI
	l.double_sided = false
	l.no_depth_test = false
	add_child(l)
	return l
