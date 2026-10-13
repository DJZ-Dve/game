class_name ShaftKit
extends RefCounted
## 冰井的模型和材质：开场镜头「冰井灯灭」（scripts/intro/shaft_blackout.gd）和开局后的下井（scripts/shaft/lift_ride.gd）共用。
## 坐标：井轴是 Y 轴，方位角 a = atan2(z, x)（和冰壁着色器一致）；第 i 圈走台面在 y = -i * RING_STEP，深度标记「R07 / -84 m」。
## - 冰壁（程序生成的冰，assets/shaders/ice_wall.gdshader）：热水钻出来的井，按两圈走台正中间切成一段段（wall_chunks）
## - 每 12 米一圈的环形走台（镂空的压焊格栅、槽钢边梁、工字钢托梁和斜撑、安全黄扶手；三档细节）、
##   扶手上一圈 24 盏舱壁灯、走台底下的洗墙灯；圈与圈之间的护笼爬梯（从这圈走台的检修口下到下一圈，两个方位交替）
## - 竖着贯穿的（verticals）：加热管、升降机的导轨和齿条、滑触线、电缆桥架
## - 方位角 0 两侧留出升降机的空档（GAP）：轿厢（scripts/shaft/lift_cab.gd）顺着导轨从走台的缺口里穿过去
## 钢件的材质都是这里的变体（不改共用的 .tres）：漆面不给金属度，掉漆露出红丹、再露出钢；朝上的面结一层霜。

const R := 11.0                # 井的半径（米）
const RING_STEP := 12.0        # 走台的间距
const WALK_IN := R - 1.45      # 走台内沿（栏杆）
const WALK_OUT := R - 0.06
const GAP := 0.165             # 升降机导轨两边留出的空档（方位角 0 两侧，弧度）：走台内沿离中线 1.57 米，轿厢最宽 1.35 米
const LAMPS := 24              # 每圈几盏灯
const BORE_STEP := 3.0         # 掘进机每一节的高度（节与节之间一道台阶，冰壁着色器里也用）
const LAMP_H := 1.24           # 灯罩中心在走台面上方多高（坐在从扶手伸出来的横臂上）
const LAMP_R := WALK_IN - 0.17 # 灯罩中心的半径（扶手内侧，悬在井里）
const RAIL_R := WALK_IN + 0.05 # 栏杆立柱、扶手的半径
const RAIL_TOP := 1.08
const DECK_LIGHT := 2.6        # 照走台的那盏灯的亮度
const WALL_GLOW := 0.45        # 灯照在身后冰上的那圈光（ice_wall.gdshader 里算）
const PIPE_ANGLES := [1.05, 2.62, 5.06]
const PIPE_R := R + 0.01       # 加热管贴着井壁走，嵌在它自己化出来的浅槽里
const TRAY_ANGLE := 3.9
const JBOX_ANGLE := 3.66       # 每圈的接线箱（灯的电从这里接）
# 护笼爬梯：第 n 圈走台到第 n+1 圈，在两根托梁中间的一格里（第几格见 bay_a；偶数圈、奇数圈交替，隔四格、5.2 米，
# 上一段梯子掉下来的人落在下一圈的走台上，不会顺着检修口一路掉到底）。避开管子、桥架、接线箱、升降机导轨
const LADDER_BAYS := [34, 38]
const LADDER_OFF := 0.2        # 踏棍中心离冰面多远
const CAGE_FROM := 2.2         # 护笼从下面那圈走台面以上多高开始
const HATCH_W := 0.42          # 检修口半宽（切向）
const HATCH_IN := R - 0.94     # 检修口靠井轴那条边的半径（从这里到井壁都是口子）
# 每圈的深度标记（「R07 / -84 m」，字高 0.42 米、一条三四米长：坐升降机的人隔着井也看得清）喷在哪几个方位角
# （一条字的正中）：三条在开场镜头左边、上边、右边看得见的地方，一条在这圈两段爬梯正中间（-1：两格的中点，
# 见 label_angles；爬上来、下去的人都看得见）；都避开管子、桥架、接线箱、爬梯。字的大小、样子在 ice_wall.gdshader 里
const LABEL_ANGLES := [2.06, 3.142, -1.0, 5.62]
const LAMP_COLOR := Color(1.0, 0.86, 0.68)   # 老的卤素灯
const LAMP_COOL := Color(0.86, 0.93, 1.0)     # 后来换上的 LED

var mat_steel: ShaderMaterial
var mat_rail: ShaderMaterial
var mat_lamp: ShaderMaterial
var ice_mat: ShaderMaterial
var grate_mat: ShaderMaterial
var lens_mat: ShaderMaterial
## 一圈走台的网格，三档细节（0 最细）：格栅、扶手 [[格栅, 扶手], ...]；爬梯；灯具 [近, 远]；洗墙灯壳；灯罩 [近, 远]
var grates: Array = []
var ladders: Array[ArrayMesh] = []
var fixtures: Array[ArrayMesh] = []
var wash: ArrayMesh
var globes: Array[SphereMesh] = []
var _steels := {}


func _init() -> void:
	_build_materials()
	grates = [ring_grating_rail(0), ring_grating_rail(1), ring_grating_rail(2)]
	ladders = [ladder_mesh(0), ladder_mesh(1), ladder_mesh(2)]
	fixtures = [fixture_mesh(true), fixture_mesh(false)]
	wash = wash_mesh()
	for detail in [true, false]:
		var g := SphereMesh.new()
		g.radius = 0.075
		g.height = 0.17
		g.radial_segments = 16 if detail else 8
		g.rings = 8 if detail else 4
		globes.append(g)


## 一圈走台的钢结构（每档细节 × 检修口在哪一套，按需建、建了留着）
func steel(lod: int, hatch: float) -> ArrayMesh:
	var key := "%d/%.3f" % [lod, hatch]
	if not _steels.has(key):
		_steels[key] = ring_steel(lod, hatch)
	return _steels[key]


## 第一盏灯的方位角、相邻两盏的间隔（每圈的灯整体再错开一个随机角度）
static func lamp_a0() -> float:
	return GAP + 0.6 / R


static func lamp_spacing() -> float:
	return (TAU - 2.0 * GAP - 1.2 / R) / LAMPS


## 每圈四条深度标记的方位角（第三条在两段爬梯正中间）
static func label_angles() -> Vector4:
	return Vector4(LABEL_ANGLES[0], LABEL_ANGLES[1], (bay_a(LADDER_BAYS[0]) + bay_a(LADDER_BAYS[1])) * 0.5, LABEL_ANGLES[3])


# ---------------------------------------------------------------------------- 材质
## 钢件（冰井里的变体，不改共用的 .tres）、冰壁、格栅、灯罩
func _build_materials() -> void:
	var chip: Texture2D = load("res://assets/third_party/ambientcg/PaintedMetal005/PaintedMetal005_2K-JPG_Opacity.jpg")
	var frost := Color(0.72, 0.78, 0.82)
	mat_steel = load("res://assets/materials/M_SteelOld.tres").duplicate()
	mat_steel.set_shader_parameter("paint_color", Color(0.3, 0.31, 0.3))
	mat_steel.set_shader_parameter("paint_metallic", 0.0)
	mat_steel.set_shader_parameter("paint_roughness", 0.62)
	mat_steel.set_shader_parameter("primer_amount", 0.4)
	mat_steel.set_shader_parameter("chip_tex", chip)
	mat_steel.set_shader_parameter("chip_amount", 0.45)
	mat_steel.set_shader_parameter("chip_scale", 3.0)
	mat_steel.set_shader_parameter("chip_cover", 0.35)
	mat_steel.set_shader_parameter("bare_rust", 0.8)
	mat_steel.set_shader_parameter("dust_color", frost)
	mat_steel.set_shader_parameter("dust_amount", 0.35)
	mat_steel.set_shader_parameter("floor_dirt", 0.0)
	# 扶手：安全黄，旧了发脏；顶上被手磨出钢来（顶点色 R 按朝上的程度给），一段段磕掉漆
	mat_rail = load("res://assets/materials/M_Rail.tres").duplicate()
	mat_rail.set_shader_parameter("paint_color", Color(0.72, 0.52, 0.08))
	mat_rail.set_shader_parameter("paint_metallic", 0.0)
	mat_rail.set_shader_parameter("paint_roughness", 0.55)
	mat_rail.set_shader_parameter("paint_variation", 0.25)
	mat_rail.set_shader_parameter("edge_wear", 1.0)
	mat_rail.set_shader_parameter("primer_amount", 0.3)
	mat_rail.set_shader_parameter("chip_tex", chip)
	mat_rail.set_shader_parameter("chip_amount", 0.35)
	mat_rail.set_shader_parameter("chip_scale", 4.0)
	mat_rail.set_shader_parameter("chip_cover", 0.3)
	mat_rail.set_shader_parameter("bare_rust", 0.6)
	mat_rail.set_shader_parameter("bare_roughness", 0.3)
	mat_rail.set_shader_parameter("dust_color", frost)
	mat_rail.set_shader_parameter("dust_amount", 0.2)
	mat_rail.set_shader_parameter("floor_dirt", 0.0)
	# 灯座：铸铝刷的灰绿漆
	mat_lamp = mat_steel.duplicate()
	mat_lamp.set_shader_parameter("paint_color", Color(0.2, 0.24, 0.21))
	mat_lamp.set_shader_parameter("chip_amount", 0.3)
	mat_lamp.set_shader_parameter("dust_amount", 0.2)
	# 冰壁（ice_wall.gdshader）：冰里的东西用实拍的湖冰（ambientCG，CC0；python tools/fetch_ambientcg.py --ids Ice002,Ice004）
	ice_mat = ShaderMaterial.new()
	ice_mat.shader = preload("res://assets/shaders/ice_wall.gdshader")
	ice_mat.set_shader_parameter("radius", R)
	ice_mat.set_shader_parameter("lift", BORE_STEP)
	for pair in [["ice_a", "Ice002"], ["ice_b", "Ice004"]]:
		var path := "res://assets/third_party/ambientcg/%s/%s_2K-JPG_Color.jpg" % [pair[1], pair[1]]
		if ResourceLoader.exists(path):
			ice_mat.set_shader_parameter(pair[0], load(path))
	if ice_mat.get_shader_parameter("ice_b") == null:
		ice_mat.set_shader_parameter("ice_b", ice_mat.get_shader_parameter("ice_a"))
	ice_mat.set_shader_parameter("pipe_angles", Vector3(PIPE_ANGLES[0], PIPE_ANGLES[1], PIPE_ANGLES[2]))
	# 每圈的深度标记：模板字的距离场（tools/gen_stencil_glyphs.py），圈号、深度由着色器按每段井壁的 ring_y 算
	ice_mat.set_shader_parameter("stencil_glyphs", preload("res://assets/textures/stencil_glyphs.png"))
	ice_mat.set_shader_parameter("stencil_angles", label_angles())
	ice_mat.set_shader_parameter("ring_step", RING_STEP)
	# 走台的格栅（bar_grating.gdshader）；远处几圈走台上的光斑、每圈灯照在身后冰上的那圈暖光在着色器里算，要知道灯在哪
	grate_mat = ShaderMaterial.new()
	grate_mat.shader = preload("res://assets/shaders/bar_grating.gdshader")
	grate_mat.set_shader_parameter("radius", R)
	grate_mat.set_shader_parameter("hatch_w", HATCH_W)
	grate_mat.set_shader_parameter("hatch_in", HATCH_IN)
	for m in [grate_mat, ice_mat]:
		m.set_shader_parameter("lamp_r", LAMP_R)
		m.set_shader_parameter("lamp_h", LAMP_H)
		m.set_shader_parameter("lamp_start", lamp_a0())
		m.set_shader_parameter("lamp_step", lamp_spacing())
		m.set_shader_parameter("lamp_count", float(LAMPS))
		m.set_shader_parameter("lamp_color", LAMP_COLOR)
	# 灯罩（lamp_lens.gdshader）：每个实例的自定义数据 r = 亮度、g = 余辉、b = 色温
	lens_mat = ShaderMaterial.new()
	lens_mat.shader = preload("res://assets/shaders/lamp_lens.gdshader")
	lens_mat.set_shader_parameter("lit_color", LAMP_COLOR)
	lens_mat.set_shader_parameter("cool_color", LAMP_COOL)


# ---------------------------------------------------------------------------- 冰壁
## 冰壁的半径起伏（热水钻出来的井：大块的鼓包凹坑 + 一圈圈的细波纹）
static func wall_r(n1: FastNoiseLite, n2: FastNoiseLite, a: float, y: float, ladders: Vector2i) -> float:
	var c := cos(a) * R
	var s := sin(a) * R
	# 每节掘进的半径差一点（刀盘每次重新对位的误差），节与节之间就是一道台阶
	var step := (fposmod(sin(floorf(y / BORE_STEP) * 91.7) * 4375.85, 1.0) - 0.5) * 0.025
	var bump := 0.12 * n1.get_noise_3d(c, y * 0.6, s) + 0.03 * n2.get_noise_3d(c * 3.0, y * 2.0, s * 3.0) + step
	# 走台的托梁、斜撑锚进冰里的那一圈（走台面上 0.45 米到下面 1.45 米）：装的时候把冰壁修平了，锚板贴得严
	var rel := y - roundf(y / RING_STEP) * RING_STEP
	var band := smoothstep(-1.95, -1.45, rel) * (1.0 - smoothstep(0.45, 0.95, rel))
	# 爬梯背后竖着一条也修平了（支架的锚板贴得严）：这个高度是哪圈下去的那段梯子
	var li := floori(-y / RING_STEP)
	if li >= ladders.x and li < ladders.y:
		band = maxf(band, 1.0 - smoothstep(0.45, 0.85, absf(wrapf(a - ladder_a(li), -PI, PI)) * R))
	var r := R + bump * (1.0 - band)
	# 加热管把贴着它的冰化开又冻上：沿着管子一道浅槽（光滑透亮，见着色器的 wet）
	for pa in PIPE_ANGLES:
		var d := absf(wrapf(a - pa, -PI, PI)) * R
		r += 0.15 * exp(-d * d / 0.09)
	return r


## 冰壁的网格：ys 是从上往下每一行的高度，按两圈走台正中间切成一段段：[{mesh, top, bottom}]。
## ladders：哪几圈（x <= i < y）底下有爬梯（爬梯背后那一条冰修平了）。
## period > 0（下井用）：整片首尾接成周期——半径在 r(y) 和 r(y + period) 之间按离最上面一行的距离渐变，
## 最下面一行（ys[0] - period）和最上面一行一模一样，法线按周期接着算，一段段可以循环拼下去
func wall_chunks(ys: Array[float], ladders: Vector2i, period := 0.0) -> Array[Dictionary]:
	var n1 := FastNoiseLite.new()
	n1.seed = 7
	n1.frequency = 0.3
	n1.fractal_octaves = 3
	var n2 := FastNoiseLite.new()
	n2.seed = 11
	n2.frequency = 0.5
	var cols := 360
	var w := cols + 1
	var top := ys[0]
	var rad := func(a: float, y: float) -> float:
		if period <= 0.0:
			return wall_r(n1, n2, a, y, ladders)
		if y > top or y < top - period:
			y = top - fposmod(top - y, period)
		return lerpf(wall_r(n1, n2, a, y, ladders), wall_r(n1, n2, a, y + period, ladders), (top - y) / period)
	# 周期的时候上下各多算一行（按周期接着往外延），最上、最下一行的法线才接得上
	var rows: Array[float] = ys.duplicate()
	if period > 0.0:
		rows.push_front(ys[0] + (ys[0] - ys[1]))
		rows.push_back(ys[-1] - (ys[-2] - ys[-1]))
	var pos: Array[Vector3] = []
	for yy in rows:
		for c in w:
			var a := TAU * c / cols
			pos.append(MeshKit.pol(rad.call(a, yy), a, yy))
	var nrm: Array[Vector3] = []
	for r in rows.size():
		for c in w:
			var p := pos[r * w + c]
			var pa := pos[r * w + (c + 1) % w] if c < cols else pos[r * w + 1]
			var pb := pos[mini(r + 1, rows.size() - 1) * w + c]
			var pc := pos[maxi(r - 1, 0) * w + c]
			var n := (pa - p).cross(pc - pb).normalized()
			if n.dot(-Vector3(p.x, 0, p.z)) < 0.0:
				n = -n
			nrm.append(n)
	if period > 0.0:
		pos = pos.slice(w, pos.size() - w)
		nrm = nrm.slice(w, nrm.size() - w)
	var out: Array[Dictionary] = []
	var r0 := 0
	while r0 < ys.size() - 1:
		# 往下第一道切口（两圈走台正中间：走台面上方 6 米）
		var cut := floorf((ys[r0] - 6.0 - 0.001) / RING_STEP) * RING_STEP + 6.0
		var r1 := r0 + 1
		while r1 < ys.size() - 1 and ys[r1] > cut + 0.001:
			r1 += 1
		var st := SurfaceTool.new()
		st.begin(Mesh.PRIMITIVE_TRIANGLES)
		st.set_color(Color(0, 0, 0, 1))
		for r in range(r0, r1 + 1):
			for c in w:
				st.set_normal(nrm[r * w + c])
				st.add_vertex(pos[r * w + c])
		var sub := pos.slice(r0 * w, (r1 + 1) * w)
		for r in r1 - r0:
			for c in cols:
				var i00 := r * w + c
				_index_tri(st, sub, i00, i00 + w, i00 + w + 1)
				_index_tri(st, sub, i00, i00 + w + 1, i00 + 1)
		out.append({"mesh": st.commit(), "top": ys[r0], "bottom": ys[r1]})
		r0 = r1
	return out


## 朝着井轴的三角形（Godot 的正面是顺时针：(b-a)×(c-a) 要背着视线，也就是背着井轴）
static func _index_tri(st: SurfaceTool, pos: Array[Vector3], a: int, b: int, c: int) -> void:
	var n := (pos[b] - pos[a]).cross(pos[c] - pos[a])
	var inward := -Vector3(pos[a].x, 0, pos[a].z)
	if n.dot(inward) > 0.0:
		var tmp := b
		b = c
		c = tmp
	st.add_index(a)
	st.add_index(b)
	st.add_index(c)


# ---------------------------------------------------------------------------- 竖着贯穿整口井的
## 竖着贯穿 y0~y1 的：加热管、升降机导轨和齿条、滑触线、电缆桥架和电缆：[[网格, 材质], ...]
## （管子的法兰、导轨和滑触线的支架这些一段段的零件放在每圈走台的钢结构里，跟着走台一起按圈剔除，见 ring_steel）
func verticals(y0: float, y1: float) -> Array:
	var out := []
	var pipes := SurfaceTool.new()
	pipes.begin(Mesh.PRIMITIVE_TRIANGLES)
	pipes.set_color(Color(0.15, 0.2, 0, 1))
	for a in PIPE_ANGLES:
		MeshKit.cyl(pipes, MeshKit.pol(PIPE_R, a, y0), MeshKit.pol(PIPE_R, a, y1), 0.075, 14, false)
	out.append([pipes.commit(), load("res://assets/materials/M_PipeRed.tres")])
	var steel := SurfaceTool.new()
	steel.begin(Mesh.PRIMITIVE_TRIANGLES)
	steel.set_color(Color(0.3, 0.25, 0, 1))
	var length := y0 - y1
	var mid := (y0 + y1) * 0.5
	# 升降机导轨的安装底板：整条井壁上一道钢板（走台在这里断开，从上往下看缺口里露出的是钢板，不是被照亮的冰）
	MeshKit.box(steel, Transform3D(MeshKit.radial_basis(0.0), MeshKit.pol(R - 0.16, 0.0, mid)), Vector3(2.5, length, 0.02))
	# 两根导轨中间的齿条（轿厢背后驱动架上的小齿轮咬着它往下爬，见 scripts/shaft/lift_cab.gd）
	MeshKit.box(steel, Transform3D(MeshKit.radial_basis(0.0), MeshKit.pol(R - 0.195, 0.0, mid)), Vector3(0.06, length, 0.05))
	# 升降机的两根 T 形导轨（方位角 0 两侧）
	for side in [-1.0, 1.0]:
		var a: float = side * 0.05
		var b := MeshKit.radial_basis(a)
		MeshKit.box(steel, Transform3D(b, MeshKit.pol(R - 0.2, a, mid)), Vector3(0.018, length, 0.11))
		MeshKit.box(steel, Transform3D(b, MeshKit.pol(R - 0.135, a, mid)), Vector3(0.12, length, 0.018))
	# 电缆桥架：背板 + 两条侧边
	var tb := MeshKit.radial_basis(TRAY_ANGLE)
	MeshKit.box(steel, Transform3D(tb, MeshKit.pol(R - 0.07, TRAY_ANGLE, mid)), Vector3(0.56, length, 0.012))
	for side in [-1.0, 1.0]:
		MeshKit.box(steel, Transform3D(tb, MeshKit.pol(R - 0.12, TRAY_ANGLE, mid) + tb.x * 0.28 * side), Vector3(0.012, length, 0.1))
	out.append([steel.commit(), mat_steel])
	# 滑触线：四根包着橙色护套的导电轨，轿厢右后角的集电器压着它取电（轿厢局部 x 0.95~1.13，也就是方位角 0 往负的一边）
	var bus := SurfaceTool.new()
	bus.begin(Mesh.PRIMITIVE_TRIANGLES)
	for k in 4:
		var ba := -(0.95 + 0.06 * k) / (R - 0.215)
		MeshKit.box(bus, Transform3D(MeshKit.radial_basis(ba), MeshKit.pol(R - 0.215, ba, mid)), Vector3(0.022, length, 0.03))
	out.append([bus.commit(), load("res://assets/materials/M_CableOrange.tres")])
	# 桥架里的电缆（黑、橙两种）
	for mat in ["res://assets/materials/M_CableBlack.tres", "res://assets/materials/M_CableOrange.tres"]:
		var cab := SurfaceTool.new()
		cab.begin(Mesh.PRIMITIVE_TRIANGLES)
		for k in 6:
			if (k % 3 == 1) != mat.ends_with("Orange.tres"):
				continue
			var off := -0.22 + k * 0.088
			var rr := 0.026 + 0.008 * (k % 2)
			var p := MeshKit.pol(R - 0.11, TRAY_ANGLE, 0.0) + tb.x * off
			MeshKit.cyl(cab, Vector3(p.x, y0, p.z), Vector3(p.x, y1, p.z), rr, 8, false)
		out.append([cab.commit(), load(mat)])
	return out


# ---------------------------------------------------------------------------- 方位角
## 离方位角 a 最近的两根托梁（斜撑）正中间的方位角
static func between_joists(a: float) -> float:
	var a0 := GAP + 0.6 / R
	var step := 1.3 / R
	return a0 + (floorf((a - a0) / step) + 0.5) * step


## 第 m 格（第 m、m+1 根托梁中间）正中的方位角
static func bay_a(m: int) -> float:
	return GAP + 0.6 / R + (m + 0.5) * 1.3 / R


## 第 i 圈下到第 i+1 圈的爬梯（也就是第 i 圈的检修口）在哪个方位角：偶数圈、奇数圈交替
static func ladder_a(i: int) -> float:
	return bay_a(LADDER_BAYS[posmod(i, 2)])


## 方位角 la 那盏灯底下的洗墙灯挂在哪：两根斜撑正中间。离这圈的检修口不到两格的挪到隔两格的地方：
## 爬梯从那一格下去；洗墙灯照在走台底下冰上的那块最亮的光斑平时被走台挡着，从检修口露出来就是远处一块块刺眼的白方块
static func wash_a(la: float, hatch: float) -> float:
	var wa := between_joists(la)
	if hatch >= 0.0:
		var d := wrapf(wa - hatch, -PI, PI) / (1.3 / R)   # 隔几格
		if absf(d) < 1.5:
			wa = hatch + 2.6 / R * (signf(d) if absf(d) > 0.5 else signf(wrapf(la - hatch, -PI, PI) + 1e-6))
	return wa


## 远处几圈走台底下那几盏代表一片灯的光源（不在格子里）：离检修口近的也挪开两格（同上，不然从检修口露出亮斑）
static func off_hatch(a: float, hatch: float) -> float:
	var d := wrapf(a - hatch, -PI, PI)
	if hatch >= 0.0 and absf(d) * R < 2.0:
		return hatch + 2.6 / R * signf(d + 1e-6)
	return a


## 0~1 的伪随机数（按圈号、灯号；不用随机数生成器：开场镜头里后面的随机序列不变，灯的排布不跟着变）
static func hash3(k: int, j: int, salt: int) -> float:
	return fposmod(sin(float(k) * 12.9898 + float(j) * 78.233 + float(salt) * 37.719) * 43758.5453, 1.0)


# ---------------------------------------------------------------------------- 一圈走台、灯具、爬梯的网格
## 一圈走台的格栅、扶手（lod 0 最细）：[格栅, 扶手]。检修口在格栅着色器里切（hatch_a）
func ring_grating_rail(lod: int) -> Array[ArrayMesh]:
	var segs: int = [330, 120, 60][lod]
	var sides: int = [8, 6, 5][lod]
	var grating := SurfaceTool.new()
	grating.begin(Mesh.PRIMITIVE_TRIANGLES)
	grating.set_color(Color(0.06, 0.2, 0, 1))
	MeshKit.arc_box(grating, WALK_IN, WALK_OUT, -0.045, 0.0, GAP, TAU - GAP, segs)
	var rail := SurfaceTool.new()
	rail.begin(Mesh.PRIMITIVE_TRIANGLES)
	MeshKit.arc_tube(rail, RAIL_R, RAIL_TOP, GAP, TAU - GAP, 0.026, segs, sides)
	MeshKit.arc_tube(rail, RAIL_R, 0.56, GAP, TAU - GAP, 0.019, segs, sides)
	return [grating.commit(), rail.commit()]


## 一圈走台的钢结构（lod 0 最细）。也放这一圈上下几米里一段段的零件（管子的法兰、导轨的支架）。
## hatch >= 0：这个方位角有检修口（爬梯从这里下到下一圈）：外圈箱形梁在口子两边断开，补口框和两根短梁（_hatch_frame）
func ring_steel(lod: int, hatch: float) -> ArrayMesh:
	var segs: int = [330, 120, 60][lod]
	var sides: int = [8, 6, 5][lod]
	var steel := SurfaceTool.new()
	steel.begin(Mesh.PRIMITIVE_TRIANGLES)
	steel.set_color(Color(0.12, 0.25, 0, 1))
	# 走台内沿的边梁是槽钢：腹板往上伸出 10 厘米当踢脚板，底下一道翼缘；里圈、外圈（靠井壁）各一道箱形梁
	MeshKit.arc_box(steel, WALK_IN - 0.006, WALK_IN, -0.2, 0.1, GAP, TAU - GAP, segs)
	MeshKit.arc_box(steel, WALK_IN - 0.006, WALK_IN + 0.07, -0.212, -0.2, GAP, TAU - GAP, segs)
	MeshKit.arc_box(steel, WALK_IN + 0.02, WALK_IN + 0.16, -0.36, -0.045, GAP, TAU - GAP, segs)
	if hatch < 0.0:
		MeshKit.arc_box(steel, R - 0.32, R - 0.18, -0.36, -0.045, GAP, TAU - GAP, segs)
	else:
		# 断到口子两边短梁的腹板上
		var cut := (HATCH_W + 0.036) / (R - 0.25)
		var span := TAU - 2.0 * GAP
		MeshKit.arc_box(steel, R - 0.32, R - 0.18, -0.36, -0.045, GAP, hatch - cut, maxi(4, roundi(segs * (hatch - cut - GAP) / span)))
		MeshKit.arc_box(steel, R - 0.32, R - 0.18, -0.36, -0.045, hatch + cut, TAU - GAP,
			maxi(4, roundi(segs * (TAU - GAP - hatch - cut) / span)))
		_hatch_frame(steel, lod, hatch)
	# 径向托梁（每 1.3 米一根，工字钢，一头插进冰里，根上一块锚板）+ 斜撑（三角托架：从托梁里头那端斜着撑到
	# 下面的井壁上，底下也压一块锚板）。锚板背面正好贴着冰：那一圈冰壁修平了（_wall_r）
	var a := GAP + 0.6 / R
	while a < TAU - GAP:
		var b := MeshKit.radial_basis(a)
		var r0 := WALK_IN + 0.02
		var r1 := R + 0.25
		var mid := MeshKit.pol((r0 + r1) * 0.5, a, 0.0)
		MeshKit.box(steel, Transform3D(b, mid + Vector3(0, -0.051, 0)), Vector3(0.1, 0.012, r1 - r0))
		MeshKit.box(steel, Transform3D(b, mid + Vector3(0, -0.2, 0)), Vector3(0.008, 0.286, r1 - r0))
		MeshKit.box(steel, Transform3D(b, mid + Vector3(0, -0.349, 0)), Vector3(0.1, 0.012, r1 - r0))
		MeshKit.box(steel, Transform3D(b, MeshKit.pol(R - 0.012, a, -0.2)), Vector3(0.24, 0.5, 0.024))
		if lod < 2:
			MeshKit.beam(steel, MeshKit.pol(WALK_IN + 0.32, a, -0.355), MeshKit.pol(R - 0.03, a, -1.2), Vector2(0.06, 0.06), b.x)
			MeshKit.box(steel, Transform3D(b, MeshKit.pol(R - 0.012, a, -1.22)), Vector3(0.2, 0.32, 0.024))
		a += 1.3 / R
	# 栏杆立柱（每 1.5 米一根），底下一块法兰压在格栅边上
	a = GAP + 0.03 / R
	while a < TAU - GAP + 0.01:
		MeshKit.cyl(steel, MeshKit.pol(RAIL_R, a, 0.0), MeshKit.pol(RAIL_R, a, RAIL_TOP), 0.021, sides, true)
		if lod == 0:
			MeshKit.box(steel, Transform3D(MeshKit.radial_basis(a), MeshKit.pol(RAIL_R, a, 0.006)), Vector3(0.11, 0.012, 0.09))
		a += 1.5 / R
	# 管卡（从走台外沿伸过去抱住加热管）、桥架卡子、接线箱（灯的电从这里接，架在走台外沿的角钢上，离冰面留一点）
	for pa in PIPE_ANGLES:
		MeshKit.box(steel, Transform3D(MeshKit.radial_basis(pa), MeshKit.pol(PIPE_R - 0.08, pa, 0.45)), Vector3(0.22, 0.06, 0.26))
	MeshKit.box(steel, Transform3D(MeshKit.radial_basis(TRAY_ANGLE), MeshKit.pol(R - 0.12, TRAY_ANGLE, 0.6)), Vector3(0.62, 0.05, 0.14))
	MeshKit.box(steel, Transform3D(MeshKit.radial_basis(JBOX_ANGLE), MeshKit.pol(R - 0.3, JBOX_ANGLE, 1.3)), Vector3(0.42, 0.55, 0.2))
	MeshKit.box(steel, Transform3D(MeshKit.radial_basis(JBOX_ANGLE), MeshKit.pol(R - 0.3, JBOX_ANGLE, 0.5)), Vector3(0.05, 1.0, 0.05))
	# 竖着的东西上一段段的零件：加热管每 6 米一道法兰（这圈上下各 3 米），电梯导轨每 3 米一道支架
	if lod < 2:
		for dy in [3.0, -3.0]:
			for pa in PIPE_ANGLES:
				MeshKit.cyl(steel, MeshKit.pol(PIPE_R, pa, dy - 0.025), MeshKit.pol(PIPE_R, pa, dy + 0.025), 0.11, 14 if lod == 0 else 8, true)
		for dy in [4.5, 1.5, -1.5, -4.5]:
			for side in [-1.0, 1.0]:
				var ga: float = side * 0.05
				MeshKit.box(steel, Transform3D(MeshKit.radial_basis(ga), MeshKit.pol(R - 0.2, ga, dy)), Vector3(0.16, 0.08, 0.1))
			# 滑触线的绝缘支架：一根横担托着四根导电轨
			var bb := -1.04 / (R - 0.2)
			MeshKit.box(steel, Transform3D(MeshKit.radial_basis(bb), MeshKit.pol(R - 0.19, bb, dy)), Vector3(0.3, 0.05, 0.05))
	return steel.commit()


## 检修口的口框（方位角 hatch；口子径向从 HATCH_IN 到走台外沿，切向 ±HATCH_W）：一圈 L50×50×6 角钢，竖肢朝着口子、
## 顶面和格栅齐平，平肢伸到格栅底下托着切断的扁钢。近处还有两边的短梁（槽钢）：从里圈箱形梁伸进冰里，
## 托住口框、接住断开的外圈箱形梁，根上一块锚板
func _hatch_frame(st: SurfaceTool, lod: int, hatch: float) -> void:
	var hb := Basis(Vector3.UP, -hatch)   # 局部 x 径向朝外、z 切向（方位角 0 处），转到 hatch
	var box := func(c: Vector3, sz: Vector3) -> void: MeshKit.box(st, Transform3D(hb, hb * c), sz)
	var x0 := HATCH_IN
	var x1 := WALK_OUT
	var w := HATCH_W
	var t := 0.006
	var xm := (x0 + x1) * 0.5
	# 竖肢（高 51 毫米，顶面齐着格栅）
	box.call(Vector3(x0 - t * 0.5, -0.0255, 0.0), Vector3(t, 0.051, 2.0 * w + 2.0 * t))
	box.call(Vector3(x1 + t * 0.5, -0.0255, 0.0), Vector3(t, 0.051, 2.0 * w + 2.0 * t))
	for s in [-1.0, 1.0]:
		box.call(Vector3(xm, -0.0255, s * (w + t * 0.5)), Vector3(x1 - x0 + 2.0 * t, 0.051, t))
	if lod == 2:
		return
	# 平肢（在格栅底下，往口子外面伸）
	box.call(Vector3(x0 - t - 0.025, -0.048, 0.0), Vector3(0.05, t, 2.0 * w + 2.0 * t))
	box.call(Vector3(x1 + t + 0.022, -0.048, 0.0), Vector3(0.044, t, 2.0 * w + 2.0 * t))
	for s in [-1.0, 1.0]:
		box.call(Vector3(xm, -0.048, s * (w + t + 0.025)), Vector3(x1 - x0 + 2.0 * t, t, 0.05))
		# 短梁：腹板贴着口框外侧，上下翼缘朝外
		var xa := WALK_IN + 0.16
		var xb := R + 0.1
		var zw: float = s * (w + 0.04)
		box.call(Vector3((xa + xb) * 0.5, -0.2055, zw), Vector3(xb - xa, 0.309, 0.008))
		for fy in [-0.056, -0.355]:
			box.call(Vector3((xa + xb) * 0.5, fy, zw + s * 0.032), Vector3(xb - xa, 0.01, 0.064))
		box.call(Vector3(R - 0.012, -0.2, zw + s * 0.03), Vector3(0.024, 0.42, 0.18))


## 一盏舱壁灯（老式的井用防爆灯）：卡在扶手上的抱箍，一根方管横臂伸到井里，臂头上坐着铸铝灯座，
## 灯座上拧着磨砂玻璃罩（罩子朝上：镜头从上往下看，看得见发光的罩子；另一个 MultiMesh，亮度单独控制），
## 外面一个护罩：四根筋从灯座沿上来兜住罩子，腰上一道箍，顶上一个小圈（顶上不封，从上往下看得见罩子）。
## 方位角 0 处的局部坐标
func fixture_mesh(detail: bool) -> ArrayMesh:
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	st.set_color(Color(0.3, 0.3, 0, 1))
	var c := MeshKit.pol(LAMP_R, 0.0, LAMP_H)   # 罩子的中心
	var arm_y := LAMP_H - 0.165
	MeshKit.box(st, Transform3D(MeshKit.radial_basis(0.0), MeshKit.pol(RAIL_R, 0.0, RAIL_TOP)), Vector3(0.05, 0.075, 0.075))
	MeshKit.beam(st, MeshKit.pol(RAIL_R + 0.02, 0.0, arm_y), MeshKit.pol(LAMP_R - 0.03, 0.0, arm_y), Vector2(0.03, 0.03), Vector3(0, 0, 1))
	if detail:
		# 抱箍到横臂的短立板
		MeshKit.box(st, Transform3D(MeshKit.radial_basis(0.0), MeshKit.pol(RAIL_R, 0.0, (RAIL_TOP + arm_y) * 0.5)), Vector3(0.04, absf(RAIL_TOP - arm_y) + 0.04, 0.01))
	# 灯座：铸铝，下面接横臂，上面一道螺口压着罩子（剖面：半径, 离罩子中心的高度；从顶上的轴往外、往下）
	var prof: Array[Vector2] = [Vector2(0.0, -0.06), Vector2(0.047, -0.06), Vector2(0.05, -0.068), Vector2(0.062, -0.074),
		Vector2(0.067, -0.09), Vector2(0.067, -0.132), Vector2(0.06, -0.148), Vector2(0.0, -0.15)]
	if not detail:
		prof = [Vector2(0.0, -0.06), Vector2(0.06, -0.07), Vector2(0.067, -0.13), Vector2(0.0, -0.15)]
	MeshKit.lathe(st, c, prof, 16 if detail else 6)
	if detail:
		# 护罩
		var guard: Array[Vector2] = [Vector2(0.064, -0.074), Vector2(0.079, -0.058), Vector2(0.085, -0.02), Vector2(0.085, 0.02),
			Vector2(0.078, 0.056), Vector2(0.058, 0.086), Vector2(0.032, 0.099)]
		for g in 4:
			var ga := TAU * g / 4.0 + PI / 4.0
			var gd := Vector3(cos(ga), 0, sin(ga))
			var pts: Array[Vector3] = []
			for q in guard:
				pts.append(c + gd * q.x + Vector3(0, q.y, 0))
			MeshKit.tube(st, pts, 0.0032, 4)
		MeshKit.ring_tube(st, c, 0.0855, 0.0032, 24, 4)
		MeshKit.ring_tube(st, c + Vector3(0, 0.099, 0), 0.032, 0.004, 12, 4)
	else:
		MeshKit.ring_tube(st, c + Vector3(0, 0.099, 0), 0.032, 0.005, 6, 3)
	return st.commit()


## 走台底下的洗墙灯灯壳：吊在托梁底下，朝下那面是玻璃（看不见）
func wash_mesh() -> ArrayMesh:
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	st.set_color(Color(0.3, 0.3, 0, 1))
	var b0 := MeshKit.radial_basis(0.0)
	MeshKit.box(st, Transform3D(b0, MeshKit.pol(R - 0.55, 0.0, -0.48)), Vector3(0.4, 0.16, 0.22))
	for side in [-1.0, 1.0]:
		MeshKit.box(st, Transform3D(b0, MeshKit.pol(R - 0.55, 0.0, -0.38) + b0.x * 0.15 * side), Vector3(0.025, 0.06, 0.025))
	return st.commit()


## 一段护笼爬梯：从这圈走台的检修口下到下一圈。方位角 0 处的局部坐标（x 径向朝外、z 切向），这圈走台面是 y = 0，
## 下面那圈是 y = -RING_STEP。两根扁钢梯梁（60×12）从下面那圈的走台面一直伸到这圈走台面以上 1.1 米当扶手；
## 圆钢踏棍每 0.3 米一根，最上面一根和这圈走台面齐平，顶上被鞋底磨出钢来（顶点色）；每 3 米一对扁钢支架伸到冰上，
## 锚板贴着修平的那条冰（_wall_r）。下面那圈走台面以上 CAGE_FROM 起护笼：扁钢箍每 0.9 米一道
## （从梯梁外侧往外张开、再绕半圈，前沿离踏棍 0.7 米），里面贴 5 根竖向扁钢，最上面一道箍在检修口里。
## 整副梯子连支架、锚板一起刷安全黄（mat_rail），一个面：每圈只多一次绘制
func ladder_mesh(lod: int) -> ArrayMesh:
	var x := R - LADDER_OFF
	var y0 := -RING_STEP
	var zs := 0.235                    # 梯梁中心离中线（内净宽 0.458）
	var yel := SurfaceTool.new()
	yel.begin(Mesh.PRIMITIVE_TRIANGLES)
	yel.set_color(Color(0.12, 0.25, 0, 1))
	var id := Basis()
	for s in [-1.0, 1.0]:
		MeshKit.box(yel, Transform3D(id, Vector3(x, (y0 + 1.1) * 0.5, s * zs)), Vector3(0.06, 1.1 - y0, 0.012))
		if lod < 2:
			# 脚板：梯梁落在下面那圈的格栅上，螺栓压住
			MeshKit.box(yel, Transform3D(id, Vector3(x, y0 + 0.004, s * (zs + 0.03))), Vector3(0.1, 0.008, 0.07))
	# 护笼的箍：扁钢 50×6 竖着放；半圆的圆心离踏棍 0.34 米
	var xc := x - 0.34
	var rho := 0.36
	var arc: int = [12, 6, 4][lod]
	var hoop: Array[Vector3] = [Vector3(x - 0.025, 0, zs + 0.009)]
	for i in arc + 1:
		var th := PI * 0.5 - PI * i / arc
		hoop.append(Vector3(xc - rho * cos(th), 0, rho * sin(th)))
	hoop.append(Vector3(x - 0.025, 0, -zs - 0.009))
	var hy: Array[float] = []
	var h := y0 + CAGE_FROM
	while h <= -0.75:
		hy.append(h)
		h += 0.9 if lod < 2 else 1.8   # 远档隔一道画一道（远了 0.9 米的间距只剩一两个像素，糊成一片）
	hy.append(-0.12)   # 最上面一道在检修口里，焊在口框底下
	for yy in hy:
		var pts: Array[Vector3] = []
		for q in hoop:
			pts.append(q + Vector3(0, yy, 0))
		MeshKit.strip(yel, pts, 0.006, 0.05, lod == 0)
	# 竖向扁钢：贴在箍里面
	var top := hy[-1] + 0.025
	var bot := hy[0] - 0.025
	for i in 5:
		var th := PI * 0.5 - PI * i / 4.0
		var c := Vector3(xc - (rho - 0.006) * cos(th), (top + bot) * 0.5, (rho - 0.006) * sin(th))
		MeshKit.box(yel, Transform3D(Basis(Vector3(sin(th), 0, cos(th)), Vector3.UP, Vector3(-cos(th), 0, sin(th))), c),
			Vector3(0.05, top - bot, 0.006))
	# 支架：每 3 米一对，扁钢贴着梯梁外侧伸到冰上，锚板，近处看得见两颗锚栓的螺母
	var yb := y0 + 1.5
	while yb < 0.0:
		for s in [-1.0, 1.0]:
			var z: float = s * (zs + 0.011)
			var xa := x - 0.03
			var xb := R - 0.012
			MeshKit.box(yel, Transform3D(id, Vector3((xa + xb) * 0.5, yb, z)), Vector3(xb - xa, 0.05, 0.01))
			MeshKit.box(yel, Transform3D(id, Vector3(R - 0.006, yb, z)), Vector3(0.012, 0.16, 0.12))
			if lod == 0:
				for dy in [-0.055, 0.055]:
					MeshKit.box(yel, Transform3D(id, Vector3(R - 0.019, yb + dy, z)), Vector3(0.014, 0.024, 0.024))
		yb += 3.0
	# 踏棍放最后画（顶点色按朝上的程度给，会改 SurfaceTool 当前的颜色）；远档细得比像素还细，不画
	if lod < 2:
		for i in range(1, roundi(RING_STEP / 0.3) + 1):
			var yy := y0 + 0.3 * i
			MeshKit.cyl(yel, Vector3(x, yy, -zs + 0.006), Vector3(x, yy, zs - 0.006), 0.011, 8 if lod == 0 else 4, false, true)
	var mesh := yel.commit()
	mesh.surface_set_material(0, mat_rail)
	return mesh
