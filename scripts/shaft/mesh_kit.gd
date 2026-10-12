class_name MeshKit
extends RefCounted
## 脚本搭模型用的网格小工具（SurfaceTool）。冰井（scripts/intro/shaft_blackout.gd）、升降机轿厢（lift_cab.gd）共用。
## worn_surface 要顶点色：R 棱边磨损、G 凹槽积垢（调用的地方先 st.set_color）。
## 极坐标的约定和冰井一致：井轴是 Y 轴，方位角 a = atan2(z, x)。

static func pol(r: float, a: float, y: float) -> Vector3:
	return Vector3(r * cos(a), y, r * sin(a))


## 在方位角 a 处：x 沿切向、y 朝上、z 朝外（背着井轴）
static func radial_basis(a: float) -> Basis:
	var radial := Vector3(cos(a), 0, sin(a))
	return Basis(Vector3(-sin(a), 0, cos(a)), Vector3.UP, radial)


static func tri(st: SurfaceTool, a: Vector3, b: Vector3, c: Vector3, na: Vector3, nb: Vector3, nc: Vector3) -> void:
	if (b - a).cross(c - a).dot(na + nb + nc) > 0.0:
		var tp := b
		b = c
		c = tp
		var tn := nb
		nb = nc
		nc = tn
	st.set_normal(na)
	st.add_vertex(a)
	st.set_normal(nb)
	st.add_vertex(b)
	st.set_normal(nc)
	st.add_vertex(c)


static func quad(st: SurfaceTool, a: Vector3, b: Vector3, c: Vector3, d: Vector3, n: Vector3) -> void:
	tri(st, a, b, c, n, n, n)
	tri(st, a, c, d, n, n, n)


static func box(st: SurfaceTool, xf: Transform3D, s: Vector3) -> void:
	var h := s * 0.5
	var axes := [Vector3.RIGHT, Vector3.UP, Vector3.BACK]
	for k in 3:
		for sgn in [-1.0, 1.0]:
			var n: Vector3 = axes[k] * sgn
			var u: Vector3 = axes[(k + 1) % 3]
			var v: Vector3 = axes[(k + 2) % 3]
			var c: Vector3 = n * h[k]
			var du: Vector3 = u * h[(k + 1) % 3]
			var dv: Vector3 = v * h[(k + 2) % 3]
			var wn := (xf.basis * n).normalized()
			quad(st, xf * (c - du - dv), xf * (c + du - dv), xf * (c + du + dv), xf * (c - du + dv), wn)


## 圆柱（worn：顶点色按朝上的程度给，见 tri_worn——踏棍顶上被鞋底磨出钢来；会改 SurfaceTool 当前的颜色）
static func cyl(st: SurfaceTool, a: Vector3, b: Vector3, r: float, sides: int, caps: bool, worn := false) -> void:
	var ax := (b - a).normalized()
	var u := ax.cross(Vector3.UP if absf(ax.y) < 0.9 else Vector3.RIGHT).normalized()
	var v := ax.cross(u)
	for k in sides:
		var a0 := TAU * k / sides
		var a1 := TAU * (k + 1) / sides
		var n0 := u * cos(a0) + v * sin(a0)
		var n1 := u * cos(a1) + v * sin(a1)
		if worn:
			tri_worn(st, a + n0 * r, b + n0 * r, b + n1 * r, n0, n0, n1)
			tri_worn(st, a + n0 * r, b + n1 * r, a + n1 * r, n0, n1, n1)
		else:
			tri(st, a + n0 * r, b + n0 * r, b + n1 * r, n0, n0, n1)
			tri(st, a + n0 * r, b + n1 * r, a + n1 * r, n0, n1, n1)
		if caps:
			tri(st, a, a + n0 * r, a + n1 * r, -ax, -ax, -ax)
			tri(st, b, b + n1 * r, b + n0 * r, ax, ax, ax)


## 沿水平折线扫一条竖着放的扁钢（厚 th、高 h：护笼的箍）。侧面按顶点算法线（弯的那段看着是圆的），
## 每个节点的截面放在前后两段的平均方向上；ends = false 不画顶面、底面（远了几毫米宽的面看不见）
static func strip(st: SurfaceTool, pts: Array[Vector3], th: float, h: float, ends := true) -> void:
	var n := pts.size()
	var side: Array[Vector3] = []
	for i in n:
		var d := pts[mini(i + 1, n - 1)] - pts[maxi(i - 1, 0)]
		side.append(Vector3(-d.z, 0.0, d.x).normalized())
	var up := Vector3(0, h * 0.5, 0)
	for i in n - 1:
		var a := pts[i]
		var b := pts[i + 1]
		var sa := side[i] * th * 0.5
		var sb := side[i + 1] * th * 0.5
		for sg in [1.0, -1.0]:
			var na: Vector3 = side[i] * sg
			var nb: Vector3 = side[i + 1] * sg
			tri(st, a + sa * sg - up, b + sb * sg - up, b + sb * sg + up, na, nb, nb)
			tri(st, a + sa * sg - up, b + sb * sg + up, a + sa * sg + up, na, nb, na)
		if ends:
			quad(st, a - sa + up, a + sa + up, b + sb + up, b - sb + up, Vector3.UP)
			quad(st, a - sa - up, b - sb - up, b + sb - up, a + sa - up, Vector3.DOWN)


## 两点之间一根方钢（截面 size：x 沿 side 方向）
static func beam(st: SurfaceTool, a: Vector3, b: Vector3, size: Vector2, side: Vector3) -> void:
	var z := (b - a).normalized()
	var x := (side - z * side.dot(z)).normalized()
	box(st, Transform3D(Basis(x, z.cross(x), z), (a + b) * 0.5), Vector3(size.x, size.y, a.distance_to(b)))


## 沿折线扫一根圆管：每个节点一圈顶点，截面放在前后两段的平均方向上（拐弯处不留缝），截面的朝向顺着折线平移（不打扭）
static func tube(st: SurfaceTool, pts: Array[Vector3], r: float, sides: int) -> void:
	var n := pts.size()
	var rings: Array = []
	var u := Vector3.ZERO
	for i in n:
		var t: Vector3
		if i == 0:
			t = (pts[1] - pts[0]).normalized()
		elif i == n - 1:
			t = (pts[i] - pts[i - 1]).normalized()
		else:
			t = ((pts[i] - pts[i - 1]).normalized() + (pts[i + 1] - pts[i]).normalized()).normalized()
		if i == 0:
			u = t.cross(Vector3.UP if absf(t.y) < 0.9 else Vector3.RIGHT).normalized()
		else:
			u = (u - t * u.dot(t)).normalized()
		var v := t.cross(u)
		var ring: Array[Vector3] = []
		for k in sides:
			var ang := TAU * k / sides
			ring.append(u * cos(ang) + v * sin(ang))
		rings.append(ring)
	for i in n - 1:
		var ra: Array[Vector3] = rings[i]
		var rb: Array[Vector3] = rings[i + 1]
		for k in sides:
			var k1 := (k + 1) % sides
			tri(st, pts[i] + ra[k] * r, pts[i + 1] + rb[k] * r, pts[i + 1] + rb[k1] * r, ra[k], rb[k], rb[k1])
			tri(st, pts[i] + ra[k] * r, pts[i + 1] + rb[k1] * r, pts[i] + ra[k1] * r, ra[k], rb[k1], ra[k1])


## 一圈水平的圆环管（护罩腰上的箍）
static func ring_tube(st: SurfaceTool, c: Vector3, rr: float, tr: float, segs: int, sides: int) -> void:
	var pts: Array[Vector3] = []
	for i in segs + 1:
		var ang := TAU * i / segs
		pts.append(c + Vector3(cos(ang), 0, sin(ang)) * rr)
	tube(st, pts, tr, sides)


## 车床回转体：prof 是 (半径, 高) 的折线，从轴上的顶点往外、往下走（这样算出来的法线朝外）；绕着过 c 的竖直轴转一圈
static func lathe(st: SurfaceTool, c: Vector3, prof: Array[Vector2], sides: int) -> void:
	for i in prof.size() - 1:
		var p0 := prof[i]
		var p1 := prof[i + 1]
		var e := p1 - p0
		var pn := Vector2(-e.y, e.x).normalized()
		for k in sides:
			var f0 := TAU * k / sides
			var f1 := TAU * (k + 1) / sides
			var d0 := Vector3(cos(f0), 0, sin(f0))
			var d1 := Vector3(cos(f1), 0, sin(f1))
			var n0 := d0 * pn.x + Vector3(0, pn.y, 0)
			var n1 := d1 * pn.x + Vector3(0, pn.y, 0)
			var a0 := c + d0 * p0.x + Vector3(0, p0.y, 0)
			var a1 := c + d1 * p0.x + Vector3(0, p0.y, 0)
			var b0 := c + d0 * p1.x + Vector3(0, p1.y, 0)
			var b1 := c + d1 * p1.x + Vector3(0, p1.y, 0)
			tri(st, a0, b0, b1, n0, n0, n1)
			tri(st, a0, b1, a1, n0, n1, n1)


## 一段环形的管子（栏杆扶手）：沿半径 rr、高 y 的圆弧扫一个圆截面，两头封口。
## 顶点色 R（棱边磨损）按朝上的程度给：扶手顶上被手磨亮，底下没人碰
static func arc_tube(st: SurfaceTool, rr: float, y: float, a0: float, a1: float, tr: float, segs: int, sides := 8) -> void:
	for s in segs:
		var t0 := lerpf(a0, a1, float(s) / segs)
		var t1 := lerpf(a0, a1, float(s + 1) / segs)
		for k in sides:
			var b0 := TAU * k / sides
			var b1 := TAU * (k + 1) / sides
			var n00 := Vector3(cos(t0) * cos(b0), sin(b0), sin(t0) * cos(b0))
			var n01 := Vector3(cos(t0) * cos(b1), sin(b1), sin(t0) * cos(b1))
			var n10 := Vector3(cos(t1) * cos(b0), sin(b0), sin(t1) * cos(b0))
			var n11 := Vector3(cos(t1) * cos(b1), sin(b1), sin(t1) * cos(b1))
			var p00 := pol(rr, t0, y) + n00 * tr
			var p01 := pol(rr, t0, y) + n01 * tr
			var p10 := pol(rr, t1, y) + n10 * tr
			var p11 := pol(rr, t1, y) + n11 * tr
			tri_worn(st, p00, p10, p11, n00, n10, n11)
			tri_worn(st, p00, p11, p01, n00, n11, n01)
	for end in [[a0, -1.0], [a1, 1.0]]:
		var ea: float = end[0]
		var tn := Vector3(-sin(ea), 0, cos(ea)) * float(end[1])
		var c := pol(rr, ea, y)
		for k in sides:
			var b0 := TAU * k / sides
			var b1 := TAU * (k + 1) / sides
			var q0 := c + (Vector3(cos(ea), 0, sin(ea)) * cos(b0) + Vector3.UP * sin(b0)) * tr
			var q1 := c + (Vector3(cos(ea), 0, sin(ea)) * cos(b1) + Vector3.UP * sin(b1)) * tr
			tri_worn(st, c, q0, q1, tn, tn, tn)


## 带磨损顶点色的三角形（朝上的顶点 R 大）
static func tri_worn(st: SurfaceTool, a: Vector3, b: Vector3, c: Vector3, na: Vector3, nb: Vector3, nc: Vector3) -> void:
	if (b - a).cross(c - a).dot(na + nb + nc) > 0.0:
		var tp := b
		b = c
		c = tp
		var tn := nb
		nb = nc
		nc = tn
	for v in [[a, na], [b, nb], [c, nc]]:
		var n: Vector3 = v[1]
		st.set_color(Color(0.12 + 0.62 * pow(maxf(n.y, 0.0), 3.0), 0.12, 0, 1))
		st.set_normal(n)
		st.add_vertex(v[0])


## 环形扇区的盒子（走台面、梁、踢脚板）：半径 r0~r1、高 y0~y1、方位 a0~a1
static func arc_box(st: SurfaceTool, r0: float, r1: float, y0: float, y1: float, a0: float, a1: float, segs: int) -> void:
	for s in segs:
		var t0 := lerpf(a0, a1, float(s) / segs)
		var t1 := lerpf(a0, a1, float(s + 1) / segs)
		var tm := (t0 + t1) * 0.5
		var radial := Vector3(cos(tm), 0, sin(tm))
		quad(st, pol(r0, t0, y1), pol(r1, t0, y1), pol(r1, t1, y1), pol(r0, t1, y1), Vector3.UP)
		quad(st, pol(r0, t0, y0), pol(r0, t1, y0), pol(r1, t1, y0), pol(r1, t0, y0), Vector3.DOWN)
		quad(st, pol(r0, t0, y0), pol(r0, t0, y1), pol(r0, t1, y1), pol(r0, t1, y0), -radial)
		quad(st, pol(r1, t0, y0), pol(r1, t1, y0), pol(r1, t1, y1), pol(r1, t0, y1), radial)
	for end in [[a0, -1.0], [a1, 1.0]]:
		var ea: float = end[0]
		var tn := Vector3(-sin(ea), 0, cos(ea)) * float(end[1])
		quad(st, pol(r0, ea, y0), pol(r1, ea, y0), pol(r1, ea, y1), pol(r0, ea, y1), tn)
