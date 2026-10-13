extends Node3D
## 破舱（原型，设计文档「七 · 破舱」）：外面一只带骨刺的东西撞了两下、爪子刮过艇壳，然后一根骨刺扎穿艇壳，
## 顺着艇壳锯开一道九十厘米长的口子再抽出去，海水顶着两百多个大气压从缝里喷进来，水位往上涨。
## 挂在潜艇的 Body 下面（submarine.gd 建），坐标都是舱内局部坐标（x 右舷、y 上、-z 艏，耐压舱轴线在 y = 0）。
##
## 过程（trigger() 之后，秒）：
##   T_RAM1   第一下撞：闷响、整条艇嗡一声、镜头一晃、灯闪
##   T_RAM2   第二下更重：那块艇壳被顶出两道爪尖的裂痕（漆崩开露出钢）
##   T_SCRAPE 爪子从外面刮过艇壳：尖利的金属刮擦，镜头一直在抖
##   T_PIERCE 骨刺扎穿：尖从缝的一头捅进舱里三十厘米，顺着艇壳往另一头锯（CUT_TIME），两边的钢板跟着往舱里翻；
##            锯开的那一段马上喷出水幕，砸在左舷那边的地板上；然后骨刺抽出去（PULL_TIME）
##   之后     按进水量（inflow，立方米/秒）算水位：先灌满地板底下的舱底，再漫过地板往上涨；
##            泡到水的灯短路打火、熄掉；缝没进水里以后水幕变成水下的一团白，水面上翻起一大片；
##            舱里的空气被压缩到外面的压力（1/240）就不再进水，顶上留一层几厘米的气
##
## 真实的进水快得多（这么长的缝在冰底每秒几十立方米，一两秒就灌满），这里按玩法放慢，见 inflow。
## 缝在艇壳着色器里挖（worn_surface_breach.gdshader，只给内壁那块材质换上），翻进来的钢板、水幕、骨刺是这里生成的网格。
## 头没进水里：画面糊、发浑（flood_post.gdshader），舱里的声音闷掉、换成水下的轰鸣（sub_audio.gd 看 ear_under）。
## 骨刺只是一截占位，外面那东西本身还没做；还没做：联机同步（以后主机算水位、广播）、水密门开着时水往另一个舱流、没穿服的人当场死。
##
## 调试：--breach=秒 开场这么多秒以后开始；Ctrl+B 现在开始；--breach-open 跳过前面直接到骨刺抽出去以后；
##       --breach-freeze=秒 过程停在这一刻（看骨刺、截图用；水也不涨）；--no-jet 不画水幕（看口子本身）；
##       --flood=米 开场水位（局部 y，地板 -0.9、眼睛站着 0.72），不撕口子；--flood-rate=立方米每秒

signal ruptured

const SFX := "res://assets/audio/%s.wav"
const WORN_BREACH := preload("res://assets/shaders/worn_surface_breach.gdshader")
const JET_SHADER := preload("res://assets/shaders/breach_jet.gdshader")
const POST_SHADER := preload("res://assets/shaders/flood_post.gdshader")
const SURFACE_SHADER := preload("res://assets/shaders/flood_surface.gdshader")
const PARTICLE_SHADER := preload("res://assets/shaders/flood_particle.gdshader")
const BUBBLE_SHADER := preload("res://assets/shaders/flood_bubble.gdshader")
const CLAW_SHADER := preload("res://assets/shaders/creature_claw.gdshader")
const M_INNER := preload("res://assets/materials/M_HullInner.tres")
const M_OUTER := preload("res://assets/materials/M_HullBlack.tres")
const M_BARE := preload("res://assets/materials/M_BareMetal.tres")
## 全屏后处理单独放一层：舱内的反射探针不画它（_ensure_water 里把这一层从探针里去掉）。
## 不用 water_fx.gd 的第 20 层：第一人称相机为了不画自己的头把第 20 层去掉了（crew_body.gd 的 HEAD_LAYER）
const POST_LAYER := 1 << 18

const R_IN := 1.35       # 耐压壳内壁半径（cockpit.py 的 R_IN）
const BOW_CENTER := -1.6 # 艏部半球的球心（局部 z）
const DECK_Y := -0.9
const SAMPLES := 48      # 缝沿长度的采样数（和 worn_surface.gdshaderinc 的 breach_w / breach_off 一样）
const AIR_RATIO := 1.0 / 240.0  # 冰底约 240 个大气压：舱里的空气压到这么小就和外面平衡了
# 时间线（秒）
const T_RAM1 := 0.0
const T_RAM2 := 1.1
const T_SCRAPE := 1.7
const T_PIERCE := 2.7
const CUT_TIME := 0.55
const PULL_TIME := 0.35
const T_DONE := T_PIERCE + CUT_TIME + 0.08 + PULL_TIME
# 骨刺：根部在艇外，弯锥
const CLAW_LEN := 0.9
const CLAW_CURL := 0.1
const CLAW_R := 0.1
const CLAW_DEPTH := 0.32     # 扎进舱里多深（尖离内壁）
const CLAW_SLANT := 28.0     # 尖往锯的方向斜多少度

## 缝：控制舱舱顶正中，两组管子中间留给顶灯的那条空当里，两盏顶灯之间；斜着划过去，横穿两道肋骨
## （肋骨留着，像被锯开的钢板中间剩下的筋）。一抬头就是整道口子；海水像瀑布一样直接砸在过道中间
@export var hole_z := 0.8
@export var hole_angle_deg := 3.0         # 离正上方往右舷多少度
@export var slit_half_len := 0.5          # 缝长的一半
@export var slit_width := 0.16            # 最宽处的半宽
@export var slit_tilt_deg := 20.0         # 缝从艇轴方向往周向斜多少度（爪子不是正着顺着艇身划的）
@export var plate := 0.06                 # 耐压壳厚度（外表面 1.41）
## 进水量（立方米/秒）：控制舱连舱底大约 30 立方米，1.2 大约 20 秒淹过站着的人的眼睛
@export var inflow := 1.2
## 这个舱的前后范围（局部 z）：艏部半球顶 → 中间隔壁
@export var comp_z := Vector2(-2.95, 2.6)

## 水位（局部 y）；没有水时在舱底以下
var level := -R_IN - 0.01
## 听者的耳朵在水里的程度（0~1），sub_audio.gd 看它
var ear_under := 0.0
var active := false
var opened := false

var _sub: Node
var _body: Node3D
var _cam: Camera3D
var _t := 0.0
var _freeze := -1.0
var _cut := 0.0          # 缝锯到哪了（沿缝 0~1）
var _claw_t := -0.85     # 骨刺尖在缝上的位置（-1~1）
var _claw_depth := -0.1  # 骨刺尖扎进舱里多深（负的是还在外面）
var _volume := 0.0
var _vol_table := PackedFloat32Array()  # 水位 → 体积（每厘米一格）
var _vol_full := 0.0
var _rng := RandomNumberGenerator.new()
var _events := {}        # 时间线上已经触发过的事件

# 缝的几何（局部坐标）
var _c := Vector3.ZERO  # 内表面上的中心
var _u := Vector3.ZERO  # 横过缝
var _v := Vector3.BACK  # 沿缝（骨刺从 -v 锯向 +v）
var _n := Vector3.ZERO  # 朝外
var _w := PackedFloat32Array()     # 沿缝每个采样点的半宽（米）
var _off := PackedFloat32Array()   # 中线的横向偏移（米）
var _reach := PackedFloat32Array() # 翻进来的钢板留多长（0~1，边上崩掉一截；平滑起伏，不然断口一块块的）
var _w_flap := PackedFloat32Array() # 钢板长度按的缝宽（去掉锯齿，锯齿只留在口子边上）
var _bend := [deg_to_rad(80.0), deg_to_rad(110.0)]  # 两边钢板最终翻进来的角度（骨刺往一边别得更狠）
var _impact := Vector3.ZERO
var _impact_n := Vector3.UP

var _hull_mat: ShaderMaterial
var _flap_mesh: MeshInstance3D
var _claw: MeshInstance3D
var _jet: MeshInstance3D
var _jet_mat: ShaderMaterial
var _post_mat: ShaderMaterial
var _surface: MeshInstance3D
var _surface_mat: ShaderMaterial
var _mist_fog: FogVolume
var _mist_mat: FogMaterial
var _spray: GPUParticles3D
var _splash: GPUParticles3D
var _burst: GPUParticles3D
var _mist: GPUParticles3D
var _bubbles: GPUParticles3D
var _breath: GPUParticles3D
var _breath_wait := 2.0
var _flood_mats: Array[ShaderMaterial] = []
var _bubble_mats: Array[ShaderMaterial] = []
var _side_st: SurfaceTool
var _fresh_mat: ShaderMaterial

var _lights: Array[Dictionary] = []  # {light, pos, energy, dies_at, dead}
var _surge := 0.0
var _light_frac := 1.0

var _p_ram: AudioStreamPlayer3D
var _p_scrape: AudioStreamPlayer3D
var _p_pierce: AudioStreamPlayer3D
var _p_burst: AudioStreamPlayer3D
var _p_jet: AudioStreamPlayer3D
var _p_churn: AudioStreamPlayer3D
var _p_under: AudioStreamPlayer
var _p_spark: AudioStreamPlayer3D


func _ready() -> void:
	_sub = owner if owner else get_parent().get_parent()
	_body = get_parent() as Node3D
	_rng.seed = 7
	if DebugArgs.has("flood-rate"):
		inflow = float(DebugArgs.get_arg("flood-rate"))
	if DebugArgs.has("breach-freeze"):
		_freeze = float(DebugArgs.get_arg("breach-freeze"))
	_build_volume_table()
	_setup_geometry()
	if DebugArgs.has("flood"):
		_ensure_water()
		_set_level(float(DebugArgs.get_arg("flood")))
	if DebugArgs.has("breach"):
		var wait := float(DebugArgs.get_arg("breach"))
		get_tree().create_timer(wait, true, false, true).timeout.connect(trigger)


func _unhandled_key_input(event: InputEvent) -> void:
	var k := event as InputEventKey
	if k and k.pressed and not k.echo and k.keycode == KEY_B and k.ctrl_pressed:
		trigger()


## 开始（只来一次）
func trigger() -> void:
	if active:
		return
	active = true
	_ensure_water()
	_build_hole()
	_collect_lights()
	_setup_audio()
	if DebugArgs.has("breach-open"):
		_t = T_DONE + 0.05
		for e in ["ram1", "ram2", "scrape", "pierce"]:
			_events[e] = true
		_rupture(null)
	print("BREACH 开始 缝中心=%s 落点=%s" % [_c, _impact])


# ---------------------------------------------------------------------------- 几何
func _setup_geometry() -> void:
	var a := deg_to_rad(hole_angle_deg)
	_n = Vector3(sin(a), cos(a), 0.0)
	var circ := Vector3(cos(a), -sin(a), 0.0)  # 周向（往下）
	var tilt := deg_to_rad(slit_tilt_deg)
	_v = (Vector3.BACK * cos(tilt) + circ * sin(tilt)).normalized()
	_u = _v.cross(_n).normalized()
	_c = _n * R_IN + Vector3(0, 0, hole_z)
	# 水幕：从缝顺着法线往里，打到地板、两舷的柜门（柜门面 |x| = 0.82，桌面以下）或者对面的艇壳，取最近的
	var dir := -_n
	var t := 2.0 * R_IN * 0.97
	_impact_n = _n
	if dir.y < 0.0:
		var td := (DECK_Y - _c.y) / dir.y
		if td < t and absf(_c.x + dir.x * td) < 0.82:
			t = td
			_impact_n = Vector3.UP
	if absf(dir.x) > 0.01:
		var face := -0.82 * signf(dir.x)
		var tc := (face - _c.x) / dir.x
		var y := _c.y + dir.y * tc
		if y > DECK_Y and y < -0.165 and tc < t:
			t = tc
			_impact_n = Vector3(-signf(dir.x), 0, 0)
	_impact = _c + dir * t


## 缝的形状：两头尖、中间宽（骨刺扎进去的那头更宽一点），边上一排锯齿；中线微微扭
func _build_hole() -> void:
	_w.resize(SAMPLES)
	_off.resize(SAMPLES)
	_reach.resize(SAMPLES)
	var ph := [_rng.randf() * TAU, _rng.randf() * TAU, _rng.randf() * TAU]
	for k in SAMPLES:
		var t := -1.0 + 2.0 * k / (SAMPLES - 1)
		var env := pow(maxf(1.0 - t * t, 0.0), 0.55) * (1.1 - 0.25 * (t * 0.5 + 0.5))
		var w := slit_width * env * (1.0 + 0.16 * sin(7.0 * t + ph[0]) + _rng.randf_range(-0.12, 0.12))
		if _rng.randf() < 0.18:
			w += _rng.randf_range(0.01, 0.025) * env  # 撕出来的豁口
		_w[k] = maxf(w, 0.0)
		_off[k] = 0.012 * sin(3.0 * t + ph[1]) + 0.005 * sin(11.0 * t + ph[2])
		_reach[k] = 0.88 + 0.07 * sin(t * 13.0 + ph[2]) + 0.04 * sin(t * 31.0 + ph[0])

	_w_flap.resize(SAMPLES)
	for k in SAMPLES:
		var acc := 0.0
		var wsum := 0.0
		for d in range(-3, 4):
			var kk := clampi(k + d, 0, SAMPLES - 1)
			var wt := 1.0 - absf(d) / 4.0
			acc += _w[kk] * wt
			wsum += wt
		_w_flap[k] = minf(acc / wsum, _w[k] + 0.01)

	# 那块艇壳换成会开缝的材质
	var hull := _find_hull()
	if hull:
		var base := hull.get_active_material(0) as ShaderMaterial
		_hull_mat = base.duplicate() as ShaderMaterial
		_hull_mat.shader = WORN_BREACH
		var to_mesh := (_body.global_transform.affine_inverse() * hull.global_transform).affine_inverse()
		_hull_mat.set_shader_parameter("breach_center", to_mesh * _c)
		_hull_mat.set_shader_parameter("breach_u", (to_mesh.basis * _u).normalized())
		_hull_mat.set_shader_parameter("breach_v", (to_mesh.basis * _v).normalized())
		_hull_mat.set_shader_parameter("breach_n", (to_mesh.basis * _n).normalized())
		_hull_mat.set_shader_parameter("breach_len", slit_half_len)
		_hull_mat.set_shader_parameter("breach_w", _w)
		_hull_mat.set_shader_parameter("breach_off", _off)
		_hull_mat.set_shader_parameter("breach_cut", 0.0)
		_hull_mat.set_shader_parameter("breach_stress", 0.0)
		_hull_mat.set_shader_parameter("breach_score", 0.0)
		for s in hull.mesh.get_surface_count():
			if hull.get_active_material(s) == base:
				hull.set_surface_override_material(s, _hull_mat)
	else:
		push_warning("breach: 找不到艇壳内壁的网格")

	_flap_mesh = MeshInstance3D.new()
	_flap_mesh.name = "Flaps"
	_flap_mesh.layers = 1 | Submarine.CABIN_LAYER
	_flap_mesh.gi_mode = GeometryInstance3D.GI_MODE_DYNAMIC
	add_child(_flap_mesh)
	_build_claw()
	_build_jet()
	_build_particles()


func _find_hull() -> MeshInstance3D:
	for m: MeshInstance3D in _body.find_children("*HullInner*", "MeshInstance3D", true, false):
		return m
	return null


## 缝上沿长度 t（-1~1）这一点：中线偏移 + side·半宽 处的内壁上的点
func _slit_point(t: float, side := 0.0) -> Vector3:
	var a := clampf((t * 0.5 + 0.5) * (SAMPLES - 1), 0.0, SAMPLES - 1.0)
	var i0 := int(floor(a))
	var i1 := mini(i0 + 1, SAMPLES - 1)
	var f := a - i0
	var w := lerpf(_w[i0], _w[i1], f)
	var o := lerpf(_off[i0], _off[i1], f)
	return _c + _v * t * slit_half_len + _u * (o + side * w)


## 翻进来的两片钢板：缝里原来那块钢板被骨刺从中间豁开，两半各自绕缝边往舱里翻（弯成一段圆弧，越往外越弯）。
## 骨刺锯过去的那一段才翻：锯到以后零点一几秒内翻到位。内表面舱里的漆、外表面艇壳外面的黑漆、断口新鲜的钢
func _rebuild_flaps() -> void:
	var inner := SurfaceTool.new()
	var outer := SurfaceTool.new()
	var side := SurfaceTool.new()
	var edge := SurfaceTool.new()  # 外缘的断口：一条连续的面，平滑法线（翻到九十度以后正对着下面的人）
	_side_st = side
	for st in [inner, outer, side, edge]:
		st.begin(Mesh.PRIMITIVE_TRIANGLES)
	const COLS := 9
	for si in 2:
		var sgn := -1.0 if si == 0 else 1.0
		var rows: Array = []  # 每个采样点一列：[[内表面的点...], [外表面的点...], 平均法线]
		for k in SAMPLES:
			var t := -1.0 + 2.0 * k / (SAMPLES - 1)
			var passed := _cut - (t * 0.5 + 0.5)
			if passed <= 0.0 or _w[k] < 0.004:
				rows.append(null)
				continue
			var open := smoothstep(0.0, 0.16, passed)
			var bend: float = _bend[si] * (0.75 + 0.25 * sin(t * 9.0 + si * 2.0)) * open
			var base := _c + _v * t * slit_half_len + _u * (_off[k] + sgn * _w[k])
			var d_in := -_u * sgn
			var L: float = _w_flap[k] * _reach[k]
			var col_in := []
			var col_out := []
			for j in COLS + 1:
				var l := L * j / COLS
				var psi := bend * j / COLS
				var p: Vector3
				if bend < 1e-3:
					p = base + d_in * l
				else:
					var kappa := bend / L
					p = base + d_in * sin(kappa * l) / kappa - _n * (1.0 - cos(kappa * l)) / kappa
				var nrm := _n * cos(psi) + d_in * sin(psi)
				p += nrm * sin(t * 23.0 + j * 1.7 + si) * 0.008 * (float(j) / COLS) * open  # 被挤皱
				col_in.append(p)
				col_out.append(p + nrm * plate)
			# 尖上的切向（断口朝这个方向）
			var tip_dir := d_in * cos(bend) - _n * sin(bend)
			rows.append([col_in, col_out, tip_dir])
		for k in SAMPLES - 1:
			var r0 = rows[k]
			var r1 = rows[k + 1]
			if r0 == null or r1 == null:
				continue
			for j in COLS:
				var wear := 1.0 if j == COLS - 1 else 0.3
				var a: Vector3 = r0[0][j]
				var b: Vector3 = r1[0][j]
				var c: Vector3 = r1[0][j + 1]
				var d: Vector3 = r0[0][j + 1]
				var want := -((r0[1][j] - r0[0][j]) as Vector3).normalized()  # 内表面朝舱里（法线反方向）
				_quad_facing(inner, a, b, c, d, Color(wear, 0.3, 0, 1), want)
				_quad_facing(outer, r0[1][j], r1[1][j], r1[1][j + 1], r0[1][j + 1], Color(wear, 0.3, 0, 1), -want)
			# 外缘的断口
			_quad_facing(edge, r0[0][COLS], r1[0][COLS], r1[1][COLS], r0[1][COLS], Color(1, 0, 0, 1),
				(r0[2] as Vector3) + (r1[2] as Vector3))
		# 两头的断口
		for k in SAMPLES:
			var r = rows[k]
			if r == null:
				continue
			var prev = rows[k - 1] if k > 0 else null
			var next = rows[k + 1] if k < SAMPLES - 1 else null
			if prev == null or next == null:
				for j in COLS:
					_quad(side, r[0][j], r[0][j + 1], r[1][j + 1], r[1][j], Color(1, 0, 0, 1), false)
	var mesh := ArrayMesh.new()
	if _fresh_mat == null:
		_fresh_mat = M_BARE.duplicate() as ShaderMaterial
		_fresh_mat.set_shader_parameter("paint_color", Color(0.36, 0.36, 0.37))
		_fresh_mat.set_shader_parameter("rust_amount", 0.04)
		_fresh_mat.set_shader_parameter("paint_roughness", 0.62)
	for pair in [[inner, M_INNER], [outer, M_OUTER], [edge, _fresh_mat], [side, _fresh_mat]]:
		var st: SurfaceTool = pair[0]
		if st != side:
			st.index()  # 合并重合的顶点，法线才是平滑的（不然每个三角形各算各的，一块块棱角）
		st.generate_normals()
		var arrays := st.commit_to_arrays()
		if (arrays[Mesh.ARRAY_VERTEX] as PackedVector3Array).is_empty():
			continue
		mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
		mesh.surface_set_material(mesh.get_surface_count() - 1, pair[1])
	_flap_mesh.mesh = mesh


## 按想要的朝向定绕向（Godot 正面是顺时针：几何叉积和正面朝向相反）
func _quad_facing(st: SurfaceTool, a: Vector3, b: Vector3, c: Vector3, d: Vector3, col: Color, want: Vector3) -> void:
	_quad(st, a, b, c, d, col, (b - a).cross(c - a).dot(want) > 0.0)


func _quad(st: SurfaceTool, a: Vector3, b: Vector3, c: Vector3, d: Vector3, col: Color, flip: bool) -> void:
	st.set_color(col)
	if st == _side_st:
		# 断面薄、朝向乱：两面都画，各自平直的法线
		st.set_smooth_group(-1)
		for p in [a, b, c, a, c, d, a, c, b, a, d, c]:
			st.add_vertex(p)
		return
	if flip:
		for p in [a, c, b, a, d, c]:
			st.add_vertex(p)
	else:
		for p in [a, b, c, a, c, d]:
			st.add_vertex(p)


## 骨刺：一根弯锥，截面略扁（像刀背），根粗尖细；局部 +Z 是尖的方向，往 +Y 弯
func _build_claw() -> void:
	const RINGS := 26
	const SEG := 14
	var verts := PackedVector3Array()
	var norms := PackedVector3Array()
	var uvs := PackedVector2Array()
	var idx := PackedInt32Array()
	for i in RINGS + 1:
		var a := float(i) / RINGS
		var center := Vector3(0, CLAW_CURL * a * a, CLAW_LEN * a)
		var tan_ := Vector3(0, 2.0 * CLAW_CURL * a, CLAW_LEN).normalized()
		var bin := Vector3.RIGHT
		var nor := tan_.cross(bin).normalized()
		var r := CLAW_R * pow(1.0 - a, 0.8) + 0.0015
		for j in SEG + 1:
			var ang := float(j) / SEG * TAU
			# 扁的截面：上面（往弯的那边）收成一道棱
			var ry := r * (0.62 + 0.25 * maxf(sin(ang), 0.0))
			var dir := bin * cos(ang) * r + nor * sin(ang) * ry
			verts.append(center + dir)
			norms.append((bin * cos(ang) / r + nor * sin(ang) / ry).normalized())
			uvs.append(Vector2(float(j) / SEG, a))
	for i in RINGS:
		for j in SEG:
			var a := i * (SEG + 1) + j
			var b := a + SEG + 1
			idx.append_array([a, b, a + 1, a + 1, b, b + 1])
	var arr := []
	arr.resize(Mesh.ARRAY_MAX)
	arr[Mesh.ARRAY_VERTEX] = verts
	arr[Mesh.ARRAY_NORMAL] = norms
	arr[Mesh.ARRAY_TEX_UV] = uvs
	arr[Mesh.ARRAY_INDEX] = idx
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arr)
	var mat := ShaderMaterial.new()
	mat.shader = CLAW_SHADER
	_claw = MeshInstance3D.new()
	_claw.name = "Claw"
	_claw.mesh = mesh
	_claw.material_override = mat
	_claw.layers = 1 | Submarine.CABIN_LAYER
	_claw.gi_mode = GeometryInstance3D.GI_MODE_DISABLED
	_claw.visible = false
	add_child(_claw)


## 骨刺摆到位：尖在缝上 _claw_t 处、扎进舱里 _claw_depth；尖往锯的方向（+v）斜着
func _place_claw() -> void:
	var slant := deg_to_rad(CLAW_SLANT)
	var z := (-_n * cos(slant) + _v * sin(slant)).normalized()
	var y := _u
	var x := y.cross(z).normalized()
	y = z.cross(x)
	var b := Basis(x, y, z)
	var tip := _slit_point(_claw_t) - _n * _claw_depth
	_claw.transform = Transform3D(b, tip - b * Vector3(0, CLAW_CURL, CLAW_LEN))
	# 别扎在一个地方不动：锯的时候一抖一抖的
	_claw.position += _u * sin(_t * 47.0) * 0.006 + _n * sin(_t * 31.0) * 0.004


## 水幕：沿缝铺开、顺着法线往里冲，越往前越宽（UV.x 沿缝 = 锯的进度坐标，UV.y 从缝口到落点）
func _build_jet() -> void:
	const ALONG := 60
	const OUT := 32
	var length := (_impact - _c).length()
	var verts := PackedVector3Array()
	var norms := PackedVector3Array()
	var uvs := PackedVector2Array()
	var idx := PackedInt32Array()
	for i in ALONG + 1:
		var t := -0.94 + 1.88 * i / ALONG
		for j in OUT + 1:
			var s := float(j) / OUT
			var p := _slit_point(t * (1.0 + 0.22 * s)) - _n * (s * length + 0.01)
			verts.append(p)
			norms.append(_u)
			uvs.append(Vector2(t * 0.5 + 0.5, s))
	for i in ALONG:
		for j in OUT:
			var a := i * (OUT + 1) + j
			var b := a + OUT + 1
			idx.append_array([a, b, a + 1, a + 1, b, b + 1])
	var arr := []
	arr.resize(Mesh.ARRAY_MAX)
	arr[Mesh.ARRAY_VERTEX] = verts
	arr[Mesh.ARRAY_NORMAL] = norms
	arr[Mesh.ARRAY_TEX_UV] = uvs
	arr[Mesh.ARRAY_INDEX] = idx
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arr)
	_jet_mat = _flood_material(JET_SHADER)
	_jet_mat.set_shader_parameter("intensity", 0.0)
	_jet_mat.set_shader_parameter("cut", 0.0)
	_jet = _geom("Jet", mesh, _jet_mat)
	_jet.visible = not DebugArgs.has("no-jet")  # 调试：看口子本身


# ---------------------------------------------------------------------------- 粒子
func _build_particles() -> void:
	var box := Vector3(0.03, 0.03, slit_half_len * 0.9)
	# 缝口的喷雾：顺着水幕往外炸开的细水
	_spray = _particles("Spray", 220, 0.25, _c - _n * 0.03, -_n, 14.0, Vector2(8.0, 16.0), Vector2(0.008, 0.02), 1.5, 0.4, 2)
	_box_emitter(_spray, box)
	# 砸在地板上炸开的水花
	_splash = _particles("Splash", 420, 0.6, _impact + _impact_n * 0.04, _impact_n, 75.0, Vector2(2.0, 6.0),
		Vector2(0.01, 0.03), 1.3, 0.6, 2)
	_box_emitter(_splash, Vector3(0.12, 0.03, slit_half_len * 1.4))
	# 炸开的那一团白（水被打碎成雾）
	_burst = _particles("Burst", 110, 0.5, _impact + _impact_n * 0.08, _impact_n, 70.0, Vector2(0.6, 1.8),
		Vector2(0.1, 0.25), 2.2, 0.28)
	_box_emitter(_burst, Vector3(0.1, 0.03, slit_half_len * 1.3))
	# 水雾：慢慢飘、越来越多，漫满半个舱
	_mist = _particles("Mist", 60, 5.0, (_c + _impact) * 0.5, Vector3.UP, 180.0, Vector2(0.05, 0.4),
		Vector2(0.35, 0.9), 2.0, 0.045)
	_box_emitter(_mist, Vector3(0.9, 0.6, 1.2))
	var mm := _mist.process_material as ParticleProcessMaterial
	mm.gravity = Vector3(0, -0.05, 0)
	mm.damping_min = 0.3
	mm.damping_max = 0.6
	# 水下的气泡：缝没进水以后从缝往上冒；没进水时从水幕扎进水面的地方翻上来
	_bubbles = _particles("Bubbles", 420, 1.4, _impact, Vector3.UP, 50.0, Vector2(0.3, 1.2), Vector2(0.008, 0.03), 1.0, 0.8, 1)
	_box_emitter(_bubbles, Vector3(0.15, 0.05, slit_half_len))
	(_bubbles.process_material as ParticleProcessMaterial).gravity = Vector3(0, 2.2, 0)
	# 头在水里时嘴边冒出的一串气泡（憋不住往外吐的气）
	_breath = _particles("Breath", 30, 1.6, Vector3.ZERO, Vector3.UP, 30.0, Vector2(0.2, 0.6), Vector2(0.004, 0.012), 1.0, 0.8, 1)
	var brm := _breath.process_material as ParticleProcessMaterial
	brm.gravity = Vector3(0, 1.6, 0)
	brm.emission_shape = ParticleProcessMaterial.EMISSION_SHAPE_SPHERE
	brm.emission_sphere_radius = 0.03
	_breath.one_shot = true
	_breath.explosiveness = 0.7

	# 一层体积雾：舱里的顶灯照在水雾里，出光锥
	_mist_fog = FogVolume.new()
	_mist_fog.name = "MistFog"
	_mist_fog.shape = RenderingServer.FOG_VOLUME_SHAPE_BOX
	_mist_fog.size = Vector3(2.75, 2.7, comp_z.y - comp_z.x)
	_mist_fog.position = Vector3(0, 0.04, (comp_z.x + comp_z.y) * 0.5)
	_mist_mat = FogMaterial.new()
	_mist_mat.density = 0.0
	_mist_mat.albedo = Color(0.8, 0.84, 0.83)
	_mist_fog.material = _mist_mat
	add_child(_mist_fog)


## 粒子沿缝的方向铺开发射（盒子转到缝的方向：局部 x 横过缝、y 法线、z 沿缝）
func _box_emitter(p: GPUParticles3D, ext: Vector3) -> void:
	var m := p.process_material as ParticleProcessMaterial
	m.emission_shape = ParticleProcessMaterial.EMISSION_SHAPE_BOX
	m.emission_box_extents = ext
	# 局部坐标的粒子跟着节点转：节点的 z 轴转到沿缝方向，发射方向也换到节点坐标里
	var b := Basis(Vector3.UP.cross(_v).normalized(), Vector3.UP, _v).orthonormalized()
	if absf(_v.dot(Vector3.UP)) > 0.9:
		b = Basis.IDENTITY
	m.direction = b.inverse() * m.direction
	m.gravity = b.inverse() * m.gravity
	p.basis = b


func _particles(nm: String, amount: int, life: float, pos: Vector3, dir: Vector3, spread: float,
		speed: Vector2, size: Vector2, grow: float, alpha: float, kind := 0) -> GPUParticles3D:
	var p := GPUParticles3D.new()
	p.name = nm
	p.amount = amount
	p.lifetime = life
	p.position = pos
	p.local_coords = true
	p.emitting = false
	p.layers = 1 | Submarine.CABIN_LAYER
	p.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	p.gi_mode = GeometryInstance3D.GI_MODE_DISABLED
	p.visibility_aabb = AABB(Vector3(-3, -3, -4), Vector3(6, 6, 8))
	var m := ParticleProcessMaterial.new()
	m.direction = dir
	m.spread = spread
	m.initial_velocity_min = speed.x
	m.initial_velocity_max = speed.y
	m.gravity = Vector3(0, -9.8, 0)
	m.damping_min = 1.5
	m.damping_max = 3.0
	m.scale_min = size.x
	m.scale_max = size.y
	var curve := Curve.new()
	curve.add_point(Vector2(0, 1.0 / grow))
	curve.add_point(Vector2(1, 1.0))
	var ct := CurveTexture.new()
	ct.curve = curve
	m.scale_curve = ct
	m.angle_min = -180.0
	m.angle_max = 180.0
	var g := Gradient.new()
	g.set_color(0, Color(1, 1, 1, alpha))
	g.set_color(1, Color(1, 1, 1, 0))
	g.add_point(0.15, Color(1, 1, 1, alpha))
	var gt := GradientTexture1D.new()
	gt.gradient = g
	m.color_ramp = gt
	p.process_material = m
	var quad := QuadMesh.new()
	quad.size = Vector2.ONE
	var mat := _flood_material(BUBBLE_SHADER if kind == 1 else PARTICLE_SHADER)
	if kind == 1:
		_bubble_mats.append(mat)
	else:
		mat.set_shader_parameter("kind", kind)
	if kind == 2:
		m.particle_flag_align_y = true
		m.angle_min = 0.0
		m.angle_max = 0.0
	quad.material = mat
	p.draw_pass_1 = quad
	add_child(p)
	return p


# ---------------------------------------------------------------------------- 水
func _ensure_water() -> void:
	if _surface:
		return
	# 全屏的浑水
	var quad := QuadMesh.new()
	quad.size = Vector2(1, 1)
	_post_mat = _flood_material(POST_SHADER)
	_post_mat.render_priority = -100
	var post := _geom("FloodPost", quad, _post_mat)
	post.layers = POST_LAYER
	for probe: ReflectionProbe in _sub.find_children("*", "ReflectionProbe", true, false):
		probe.cull_mask &= ~POST_LAYER
	post.custom_aabb = AABB(Vector3.ONE * -5000.0, Vector3.ONE * 10000.0)
	# 水面
	var plane := PlaneMesh.new()
	var length := comp_z.y - comp_z.x
	plane.size = Vector2(2.8, length + 0.1)
	plane.subdivide_width = 70
	plane.subdivide_depth = int(length * 25.0)
	_surface_mat = _flood_material(SURFACE_SHADER)
	_surface_mat.set_shader_parameter("bow_center", BOW_CENTER)
	_surface_mat.set_shader_parameter("z_offset", (comp_z.x + comp_z.y) * 0.5)
	_surface_mat.set_shader_parameter("agitation", 0.0)
	_surface = _geom("WaterSurface", plane, _surface_mat)
	_surface.position = Vector3(0, level, (comp_z.x + comp_z.y) * 0.5)
	_surface.extra_cull_margin = 0.3
	_surface.visible = false


func _flood_material(shader: Shader) -> ShaderMaterial:
	var m := ShaderMaterial.new()
	m.shader = shader
	m.set_shader_parameter("flood_z", comp_z)
	m.set_shader_parameter("flood_radius", R_IN)
	_flood_mats.append(m)
	return m


func _geom(nm: String, mesh: Mesh, mat: Material) -> MeshInstance3D:
	var mi := MeshInstance3D.new()
	mi.name = nm
	mi.mesh = mesh
	mi.material_override = mat
	mi.layers = 1 | Submarine.CABIN_LAYER
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	mi.gi_mode = GeometryInstance3D.GI_MODE_DISABLED
	add_child(mi)
	return mi


## 水位 → 体积：耐压舱圆筒（艏部是半球）里、这个舱的前后范围、水位以下，按 5 厘米一片沿 z 积分
func _build_volume_table() -> void:
	_vol_table.resize(int(R_IN * 200.0) + 1)
	for k in _vol_table.size():
		var y := -R_IN + k * 0.01
		var vol := 0.0
		var z := comp_z.x + 0.025
		while z < comp_z.y:
			var rho := R_IN
			if z < BOW_CENTER:
				rho = sqrt(maxf(R_IN * R_IN - (z - BOW_CENTER) * (z - BOW_CENTER), 0.0))
			vol += _segment(rho, y) * 0.05
			z += 0.05
		_vol_table[k] = vol
	_vol_full = _vol_table[_vol_table.size() - 1]


static func _segment(rho: float, y: float) -> float:
	if y <= -rho:
		return 0.0
	if y >= rho:
		return PI * rho * rho
	return rho * rho * acos(-y / rho) + y * sqrt(rho * rho - y * y)


func _level_of(vol: float) -> float:
	var lo := 0
	var hi := _vol_table.size() - 1
	if vol <= 0.0:
		return -R_IN - 0.01
	while hi - lo > 1:
		var mid := (lo + hi) / 2
		if _vol_table[mid] < vol:
			lo = mid
		else:
			hi = mid
	var f := (vol - _vol_table[lo]) / maxf(_vol_table[hi] - _vol_table[lo], 1e-6)
	return -R_IN + (lo + f) * 0.01


func _set_level(y: float) -> void:
	level = clampf(y, -R_IN - 0.01, R_IN)
	var k := clampi(int((level + R_IN) * 100.0), 0, _vol_table.size() - 1)
	_volume = _vol_table[k]


# ---------------------------------------------------------------------------- 灯
func _collect_lights() -> void:
	_lights.clear()
	for l: Light3D in _body.find_children("*", "Light3D", true, false):
		var p := _body.to_local(l.global_position)
		if p.z < comp_z.x - 0.1 or p.z > comp_z.y or Vector2(p.x, p.y).length() > R_IN + 0.05:
			continue  # 艇外的探照灯、生活舱的灯
		_lights.append({"light": l, "pos": p, "energy": l.light_energy, "dies_at": -1.0, "dead": false})


func _update_lights(delta: float) -> void:
	_surge = maxf(_surge - delta, 0.0)
	var alive := 0.0
	var total := 0.0
	for d: Dictionary in _lights:
		var l: Light3D = d.light
		total += d.energy
		if d.dead:
			continue
		var p: Vector3 = d.pos
		if d.dies_at < 0.0 and p.y < level - 0.02:
			d.dies_at = _t + _rng.randf_range(0.15, 0.7)
			_play3d(_p_spark, p)
		var flick: bool = _surge > 0.0 or d.dies_at >= 0.0
		if d.dies_at >= 0.0 and _t >= d.dies_at:
			d.dead = true
			l.visible = false
			continue
		l.visible = not flick or _rng.randf() > 0.45
		if l.visible:
			alive += d.energy
	if total > 0.0:
		_light_frac = alive / total


# ---------------------------------------------------------------------------- 声音
func _setup_audio() -> void:
	if _p_jet:
		return
	_p_ram = _player3d("creature_ram", 4.0, 6.0)
	_p_scrape = _player3d("claw_scrape", 3.0, 3.0)
	_p_pierce = _player3d("claw_pierce", 3.0, 5.0)
	_p_burst = _player3d("breach_burst", 3.0, 0.0)
	_p_jet = _player3d("breach_jet", 2.5, 3.0)
	_p_churn = _player3d("flood_churn", 2.0, -3.0)
	_p_spark = _player3d("spark_crackle_0", 1.0, -10.0)
	_p_under = AudioStreamPlayer.new()
	_p_under.name = "underwater_roar"
	_p_under.stream = load(SFX % "underwater_roar")
	_p_under.bus = &"Master"
	_p_under.volume_db = -80.0
	add_child(_p_under)


func _player3d(sfx: String, unit: float, vol: float) -> AudioStreamPlayer3D:
	var p := AudioStreamPlayer3D.new()
	p.name = sfx
	if ResourceLoader.exists(SFX % sfx):
		p.stream = load(SFX % sfx)
	else:
		# 有几个变体（creature_ram_0、_1……）：随机挑
		var r := AudioStreamRandomizer.new()
		r.playback_mode = AudioStreamRandomizer.PLAYBACK_SEQUENTIAL
		var k := 0
		while ResourceLoader.exists(SFX % ("%s_%d" % [sfx, k])):
			r.add_stream(k, load(SFX % ("%s_%d" % [sfx, k])))
			k += 1
		p.stream = r
	p.unit_size = unit
	p.max_db = 6.0
	p.volume_db = vol
	p.set_meta("vol", vol)
	p.attenuation_filter_db = -6.0
	p.bus = &"CabinFwd"
	add_child(p)
	return p


func _play3d(p: AudioStreamPlayer3D, pos: Vector3) -> void:
	if p == null:
		return
	p.position = pos
	p.play()
	DebugArgs.log_sfx(String(p.name))


func _loop(p: Node, level_lin: float, base_db: float, pitch := 1.0) -> void:
	if level_lin < 0.002:
		if p.playing:
			p.stop()
			DebugArgs.log_loop(String(p.name), false)
		return
	p.set("volume_db", base_db + linear_to_db(level_lin))
	p.set("pitch_scale", pitch)
	if not p.playing:
		p.play()
		DebugArgs.log_loop(String(p.name), true)


# ---------------------------------------------------------------------------- 每帧
func _process(delta: float) -> void:
	if _cam == null:
		_cam = get_viewport().get_camera_3d()
	if active:
		var frozen := _freeze >= 0.0 and _t >= _freeze
		if not frozen:
			_t += delta
		_update_attack(delta)
		if opened:
			_update_flood(0.0 if frozen else delta)
	if _surface:
		_update_water(delta)


func _once(e: String, at: float) -> bool:
	if _t < at or _events.has(e):
		return false
	_events[e] = true
	return true


## 外面那东西：撞两下、爪子刮过、骨刺扎穿锯开再抽出去
func _update_attack(delta: float) -> void:
	if _hull_mat == null:
		return
	var cam := _sub.get_node_or_null("%CockpitCamera")
	if _once("ram1", T_RAM1):
		_play3d(_p_ram, _c + _n * 0.3)
		_shake(cam, 0.7)
		_surge = 0.15
		_hull_mat.set_shader_parameter("breach_stress", 0.15)
	if _once("ram2", T_RAM2):
		_play3d(_p_ram, _c + _n * 0.3)
		_shake(cam, 0.9)
		_surge = 0.25
	if _t > T_RAM2:
		# 第二下撞出两道爪尖顶出来的裂痕
		_hull_mat.set_shader_parameter("breach_score", smoothstep(T_RAM2, T_RAM2 + 0.08, _t))
	if _once("scrape", T_SCRAPE):
		_play3d(_p_scrape, _c + _n * 0.2)
	if _t > T_SCRAPE and _t < T_PIERCE and cam and _rng.randf() < delta * 12.0:
		cam.add_shake(0.12)
		_hull_mat.set_shader_parameter("breach_stress", lerpf(0.15, 0.5, (_t - T_SCRAPE) / (T_PIERCE - T_SCRAPE)))
	if _once("pierce", T_PIERCE):
		_play3d(_p_pierce, _slit_point(-0.85))
		_play3d(_p_burst, _c)
		_shake(cam, 1.0)
		_rupture(cam)
	if _t < T_PIERCE:
		return
	# 骨刺：扎进来 → 顺着缝锯过去 → 抽出去
	var since := _t - T_PIERCE
	var cut_end := 0.07 + CUT_TIME
	if since < 0.07:
		_claw_t = -0.85
		_claw_depth = lerpf(-0.05, CLAW_DEPTH, since / 0.07)
	elif since < cut_end:
		var k := smoothstep(0.0, 1.0, (since - 0.07) / CUT_TIME)
		_claw_t = lerpf(-0.85, 0.85, k)
		_claw_depth = lerpf(CLAW_DEPTH, CLAW_DEPTH * 0.8, k)
	elif since < cut_end + 0.08:
		_claw_t = 0.85
	else:
		var k := clampf((since - cut_end - 0.08) / PULL_TIME, 0.0, 1.0)
		_claw_t = 0.85
		_claw_depth = lerpf(CLAW_DEPTH * 0.8, -0.7, k * k)
	_claw.visible = _claw_depth > -0.65
	if _claw.visible:
		_place_claw()
		if since < cut_end and cam and _rng.randf() < delta * 20.0:
			cam.add_shake(0.15)
	var cut := clampf(_claw_t * 0.5 + 0.5 + 0.04, 0.0, 1.0) if since < cut_end else 1.0
	if cut != _cut or since < cut_end + 0.3:
		_cut = cut
		_hull_mat.set_shader_parameter("breach_cut", _cut)
		_jet_mat.set_shader_parameter("cut", _cut)
		_rebuild_flaps()


func _shake(cam: Node, s: float) -> void:
	if cam:
		cam.add_shake(s)


## 进水：水幕、水花、水雾、气泡、水位
func _update_flood(delta: float) -> void:
	var since := _t - T_PIERCE
	_jet_mat.set_shader_parameter("reach", clampf(since / 0.06, 0.0, 1.0))
	# 骨刺插在缝里的时候堵住了大半，水只从两边滋出来；抽出去的一瞬间整条缝全开
	var plug := 1.0 - smoothstep(T_DONE - PULL_TIME, T_DONE, _t)
	# 舱里的空气压到外面的压力就不再进水；锯开的长度越长进得越多
	var flowing := 1.0 - smoothstep(_vol_full * (1.0 - AIR_RATIO * 3.0), _vol_full * (1.0 - AIR_RATIO), _volume)
	var open_frac := clampf(_cut, 0.15, 1.0)
	_volume = minf(_volume + inflow * open_frac * flowing * delta, _vol_full * (1.0 - AIR_RATIO))
	level = _level_of(_volume)
	var hole_under := smoothstep(_c.y - 0.1, _c.y + 0.15, level)
	_jet_mat.set_shader_parameter("intensity", flowing * lerpf(1.0, 0.6, hole_under) * lerpf(1.0, 0.35, plug))
	_spray.emitting = flowing > 0.05 and hole_under < 0.9
	_spray.amount_ratio = (1.0 - hole_under) * open_frac
	# 落点没进水以前炸水花；没进水以后水幕扎进水里
	var impact_under := smoothstep(_impact.y - 0.05, _impact.y + 0.1, level)
	_splash.emitting = flowing > 0.05 and impact_under < 0.95
	_splash.amount_ratio = (1.0 - impact_under) * open_frac
	_burst.emitting = _splash.emitting
	_burst.amount_ratio = _splash.amount_ratio
	_mist.emitting = flowing > 0.05
	_mist_mat.density = lerpf(0.0, 0.045, smoothstep(0.0, 4.0, since)) * lerpf(1.0, 0.4, hole_under) * maxf(flowing, 0.3)
	# 气泡：水幕扎进水面的地方，或者缝本身（没进水以后）
	var bubble_at := _impact
	if hole_under > 0.5:
		bubble_at = _c - _n * 0.25
	elif level > DECK_Y - 0.4:
		var dir := (_impact - _c).normalized()
		var t := (level - _c.y) / dir.y if absf(dir.y) > 0.01 else 0.0
		bubble_at = _c + dir * clampf(t, 0.0, (_impact - _c).length())
	_bubbles.position = bubble_at
	_bubbles.emitting = flowing > 0.05 and level > bubble_at.y - 0.3 and level > DECK_Y - 0.3
	_surface_mat.set_shader_parameter("jet_on", flowing * (1.0 - hole_under * 0.3))
	_surface_mat.set_shader_parameter("jet_xz", Vector2(bubble_at.x, bubble_at.z))
	_surface_mat.set_shader_parameter("agitation", clampf(flowing * 1.2, 0.15, 1.0))
	_post_mat.set_shader_parameter("churn", flowing)
	_update_lights(delta)
	var cam := _sub.get_node_or_null("%CockpitCamera")
	if cam and flowing > 0.05 and _rng.randf() < delta * 2.0:
		cam.add_shake(0.08 * flowing)
	# 声音
	_loop(_p_jet, flowing * open_frac * (1.0 - hole_under * 0.7), _p_jet.get_meta("vol"), lerpf(1.0, 0.7, hole_under))
	_p_jet.position = _c - _n * 0.1
	_loop(_p_churn, flowing * smoothstep(-1.4, -0.8, level), _p_churn.get_meta("vol"))
	_p_churn.position = Vector3(bubble_at.x, maxf(level, DECK_Y), bubble_at.z)
	_loop(_p_under, ear_under * maxf(flowing, 0.25), -4.0)


func _rupture(cam: Node) -> void:
	opened = true
	_hull_mat.set_shader_parameter("breach_stress", 1.0)
	_hull_mat.set_shader_parameter("breach_score", 1.0)
	_jet_mat.set_shader_parameter("intensity", 1.0)
	_spray.emitting = true
	_surge = 0.35
	_surface.visible = true
	if DebugArgs.has("breach-open"):
		_cut = 1.0
		_hull_mat.set_shader_parameter("breach_cut", 1.0)
		_jet_mat.set_shader_parameter("cut", 1.0)
		_rebuild_flaps()
	ruptured.emit()
	print("BREACH 扎穿")


func _update_water(delta: float) -> void:
	_surface.visible = level > -R_IN + 0.02
	_surface.position.y = level
	# 舱内局部坐标系（世界坐标）告诉所有水的着色器
	var xf := _body.global_transform
	var o := xf.origin
	var ax := xf.basis.x.normalized()
	var ay := xf.basis.y.normalized()
	var az := xf.basis.z.normalized()
	var lit := lerpf(0.12, 1.0, _light_frac)
	for m in _flood_mats:
		m.set_shader_parameter("flood_origin", o)
		m.set_shader_parameter("flood_ax", ax)
		m.set_shader_parameter("flood_ay", ay)
		m.set_shader_parameter("flood_az", az)
		m.set_shader_parameter("flood_level", level)
		m.set_shader_parameter("flood_color", Color(0.06, 0.075, 0.068) * lit)
	for m in _bubble_mats:
		m.set_shader_parameter("glow", lerpf(0.12, 0.7, _light_frac))
	# 耳朵（眼睛）在不在水里：过水面那一下有几厘米的过渡
	var eye_y := -10.0
	if _cam:
		var e := _body.to_local(_cam.global_position)
		if e.z > comp_z.x and e.z < comp_z.y:
			eye_y = e.y
	ear_under = smoothstep(-0.02, 0.03, level - eye_y)
	_post_mat.set_shader_parameter("submerged", ear_under)
	var cam := _sub.get_node_or_null("%CockpitCamera")
	if cam:
		# 蹚水：水到膝盖开始慢，到胸口只剩三分之一
		cam.set("wade", lerpf(1.0, 0.35, smoothstep(0.25, 1.3, level - DECK_Y)))
	# 憋气：头在水里时隔几秒从嘴边冒一串气泡
	if ear_under > 0.5 and _cam and _breath:
		_breath_wait -= delta
		if _breath_wait <= 0.0:
			_breath_wait = _rng.randf_range(2.5, 4.5)
			_breath.position = _body.to_local(_cam.global_position + _cam.global_basis.z * -0.12 + Vector3.DOWN * 0.08)
			_breath.restart()
			_breath.emitting = true
