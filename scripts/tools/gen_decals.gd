extends SceneTree
## 生成舱内贴花贴图（无界面运行）：
##   Godot --path . --script res://scripts/tools/gen_decal_text.gd   # 先画文字底图
##   Godot --headless --path . --script res://scripts/tools/gen_decals.gd
## 输出 assets/textures/decals/<名字>.png（颜色 + 透明度），部分还有 <名字>_orm.png（AO/粗糙度/金属度，
## 只用来改粗糙度：湿脚印、水洼、手油这类「看颜色看不出来、看反光才看得出来」的东西）。

const OUT := "res://assets/textures/decals/"
const SRC := "res://assets/textures/decals/src/"

var _n := FastNoiseLite.new()
var _n2 := FastNoiseLite.new()


func _init() -> void:
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(OUT))
	_n.seed = 7
	_n.frequency = 0.02
	_n.fractal_octaves = 4
	_n2.seed = 31
	_n2.frequency = 0.08
	_n2.fractal_octaves = 3
	_ring()
	_burn()
	_tape()
	_polish()
	_grease()
	_scuff()
	_boot(false)
	_boot(true)
	_puddle()
	_hazard()
	_rust()
	_streak()
	_hand()
	_text("c03", Color(0.8, 0.78, 0.7), 0.55)
	_text("fire", Color(0.58, 0.05, 0.03), 0.4)
	for t in ["cool", "firewater", "return", "air"]:
		_text(t, Color(0.86, 0.84, 0.76), 0.45)
	print("decals done")
	quit()


# ----------------------------------------------------------------------------- 工具
func _img(w: int, h: int) -> Image:
	return Image.create(w, h, false, Image.FORMAT_RGBA8)


func _save(img: Image, name: String) -> void:
	img.save_png(OUT + name + ".png")


## ORM 图（AO=1、粗糙度 rough_in、金属度 0）。贴花在哪里生效由颜色图的透明度决定，所以这张图是纯色的，
## 只是尺寸跟着颜色图走。
func _orm_from(mask: Image, rough_in: float, name: String) -> void:
	var o := _img(mask.get_width(), mask.get_height())
	for y in mask.get_height():
		for x in mask.get_width():
			o.set_pixel(x, y, Color(1.0, rough_in, 0.0, 1.0))
	_save(o, name + "_orm")


func _n01(x: float, y: float) -> float:
	return _n.get_noise_2d(x, y) * 0.5 + 0.5


func _n201(x: float, y: float) -> float:
	return _n2.get_noise_2d(x, y) * 0.5 + 0.5


func _sstep(e0: float, e1: float, x: float) -> float:
	var t := clampf((x - e0) / (e1 - e0), 0.0, 1.0)
	return t * t * (3.0 - 2.0 * t)


func _seg_dist(p: Vector2, a: Vector2, b: Vector2) -> float:
	var pa := p - a
	var ba := b - a
	var h := clampf(pa.dot(ba) / ba.dot(ba), 0.0, 1.0)
	return (pa - ba * h).length()


# ----------------------------------------------------------------------------- 各种贴花
## 杯底水渍圈：一圈深色的边（干掉的茶水/咖啡），里面淡淡一层，圈不完整
func _ring() -> void:
	var s := 256
	var img := _img(s, s)
	for y in s:
		for x in s:
			var p := Vector2(x, y) / s - Vector2(0.5, 0.5)
			var r := p.length()
			var a := atan2(p.y, p.x)
			var rr := 0.38 + (_n01(cos(a) * 60.0, sin(a) * 60.0) - 0.5) * 0.04
			var ring := exp(-pow((r - rr) / 0.012, 2.0)) * (0.55 + 0.45 * _n201(x * 3.0, y * 3.0))
			ring *= _sstep(0.2, 0.45, _n01(cos(a) * 25.0 + 100.0, sin(a) * 25.0))  # 有一段断开
			var inner := (1.0 - _sstep(rr - 0.03, rr, r)) * 0.12 * _n01(x * 2.0, y * 2.0)
			var al := clampf(ring * 0.8 + inner, 0.0, 1.0)
			img.set_pixel(x, y, Color(0.22, 0.14, 0.07, al))
	_save(img, "ring")


## 烟头烫痕：中间焦黑、往外一圈发黄
func _burn() -> void:
	var s := 128
	var img := _img(s, s)
	for y in s:
		for x in s:
			var p := Vector2(x, y) / s - Vector2(0.5, 0.5)
			var r := p.length() * (1.0 + (_n01(x * 4.0, y * 4.0) - 0.5) * 0.5)
			var core := 1.0 - _sstep(0.08, 0.16, r)
			var halo := (1.0 - _sstep(0.15, 0.42, r)) * 0.6
			var c := Color(0.02, 0.015, 0.01).lerp(Color(0.3, 0.18, 0.06), 1.0 - core)
			img.set_pixel(x, y, Color(c.r, c.g, c.b, clampf(core + halo, 0.0, 1.0) * 0.95))
	_save(img, "burn")


## 撕掉胶布留下的残胶：一块发灰的长方形，边上积了一道黑垢，还粘着几片没撕干净的纸
func _tape() -> void:
	var w := 256
	var h := 96
	var img := _img(w, h)
	for y in h:
		for x in w:
			var u := float(x) / w
			var v := float(y) / h
			var ragged := (_n01(x * 2.0, 0.0) - 0.5) * 0.08
			var dx := minf(u, 1.0 - u) + ragged
			var dy := minf(v, 1.0 - v) + (_n01(0.0, y * 2.0 + x * 0.3) - 0.5) * 0.12
			var d := minf(dx * w / h, dy)  # 到边的距离（按高度归一）
			var inside := _sstep(0.0, 0.03, d)
			var edge := exp(-pow((d - 0.03) / 0.03, 2.0)) * inside
			var paper := _sstep(0.62, 0.68, _n01(x * 1.5 + 50.0, y * 1.5)) * inside
			var c := Color(0.3, 0.29, 0.25).lerp(Color(0.08, 0.07, 0.06), edge).lerp(Color(0.78, 0.72, 0.58), paper)
			var al := inside * (0.35 + 0.15 * _n201(x * 2.0, y * 2.0)) + edge * 0.5 + paper * 0.6
			img.set_pixel(x, y, Color(c.r, c.g, c.b, clampf(al, 0.0, 1.0)))
	_save(img, "tape")


## 胳膊肘常压的地方磨亮了（只改粗糙度）
func _polish() -> void:
	var w := 128
	var h := 256
	var img := _img(w, h)
	for y in h:
		for x in w:
			var p := Vector2((float(x) / w - 0.5) * 2.0, (float(y) / h - 0.5) * 2.0)
			var r := p.length() + (_n01(x * 3.0, y * 3.0) - 0.5) * 0.5
			var al := (1.0 - _sstep(0.3, 1.0, r)) * (0.6 + 0.4 * _n201(x * 4.0, y * 1.5))
			img.set_pixel(x, y, Color(0.5, 0.5, 0.5, al))
	_save(img, "polish")
	_orm_from(img, 0.18, "polish")


## 把手周围的手油：几道往下抹的黑印
func _grease() -> void:
	var s := 256
	var img := _img(s, s)
	for y in s:
		for x in s:
			var p := Vector2(x, y) / s - Vector2(0.5, 0.45)
			p.y *= 0.7
			var r := p.length() + (_n01(x * 2.5, y * 0.6) - 0.5) * 0.25
			var blob := 1.0 - _sstep(0.12, 0.42, r)
			var streak := _sstep(0.45, 0.75, _n01(x * 6.0, y * 0.4)) * _sstep(0.9, 0.4, float(y) / s)
			var al := clampf(blob * (0.4 + 0.6 * _n201(x * 3.0, y * 3.0)) + streak * blob * 0.5, 0.0, 1.0) * 0.6
			img.set_pixel(x, y, Color(0.06, 0.05, 0.035, al))
	_save(img, "grease")
	_orm_from(img, 0.25, "grease")


## 柜门下沿鞋蹭的印子：黑色胶痕 + 刮掉漆露出的浅色划痕
func _scuff() -> void:
	var w := 512
	var h := 160
	var img := _img(w, h)
	var rng := RandomNumberGenerator.new()
	rng.seed = 3
	var strokes := []
	for i in 40:
		var cx := rng.randf() * w
		var cy := h * (0.35 + rng.randf() * 0.6)
		var L := rng.randf_range(15, 90)
		var ang := rng.randf_range(-0.35, 0.35)
		strokes.append([Vector2(cx, cy), Vector2(cos(ang), sin(ang)) * L, rng.randf() < 0.15, rng.randf_range(1.5, 6.0)])
	for y in h:
		for x in w:
			var p := Vector2(x, y)
			var dark := 0.0
			var light := 0.0
			for st in strokes:
				var a: Vector2 = st[0] - st[1] * 0.5
				var b: Vector2 = st[0] + st[1] * 0.5
				var d := _seg_dist(p, a, b)
				var k := exp(-pow(d / st[3], 2.0))
				if st[2]:
					light = maxf(light, k * 0.45)
				else:
					dark = maxf(dark, k * (0.5 + 0.5 * _n201(x * 4.0, y * 4.0)))
			var c := Color(0.03, 0.03, 0.03).lerp(Color(0.55, 0.55, 0.52), light / maxf(light + dark, 1e-3))
			img.set_pixel(x, y, Color(c.r, c.g, c.b, clampf(maxf(dark * 0.75, light), 0.0, 1.0)))
	_save(img, "scuff")


## 湿脚印（胶靴鞋底）：前掌、后跟，中间足弓不着地；花纹是人字形的胶钉。印子不完整。
func _boot(right: bool) -> void:
	var w := 128
	var h := 320
	var img := _img(w, h)
	for y in h:
		for x in w:
			var u := float(x) / w
			if right:
				u = 1.0 - u
			var v := float(y) / h  # 0 = 脚尖
			# 前掌：脚尖收窄、大脚趾一侧（u 小）更饱满；后跟是一块圆角方
			var taper := 1.0 + maxf(0.0, 0.22 - v) * 1.1 + maxf(0.0, v - 0.4) * 1.5
			var fore := pow((u - 0.46) * taper / 0.42, 2.0) + pow((v - 0.3) / 0.29, 2.0)
			var heel := pow(absf(u - 0.52) / 0.34, 3.0) + pow(absf(v - 0.84) / 0.14, 3.0)
			var shape := maxf(1.0 - _sstep(0.85, 1.0, fore), 1.0 - _sstep(0.85, 1.0, heel))
			var lug: float
			if v < 0.6:
				lug = 1.0 if fposmod(v * 16.0 + absf(u - 0.48) * 5.0, 1.0) >= 0.45 else 0.0
			else:
				lug = 1.0 if fposmod(v * 14.0, 1.0) >= 0.4 else 0.0
			var wet := _sstep(0.3, 0.55, _n01(x * 3.0 + (200.0 if right else 0.0), y * 3.0))
			var al := shape * (0.25 + 0.75 * lug) * wet * 0.85
			img.set_pixel(x, y, Color(0.04, 0.045, 0.04, al))
	var name := "boot_r" if right else "boot_l"
	_save(img, name)
	_orm_from(img, 0.12, name)


## 水洼：不规则的一摊，边缘一圈干了以后留下的印子
func _puddle() -> void:
	var s := 256
	var img := _img(s, s)
	for y in s:
		for x in s:
			var p := Vector2(x, y) / s - Vector2(0.5, 0.5)
			var f := p.length() * 2.0 + (_n01(x * 1.5, y * 1.5) - 0.5) * 0.7
			var water := 1.0 - _sstep(0.55, 0.62, f)
			var rim := exp(-pow((f - 0.66) / 0.04, 2.0)) * 0.5
			var c := Color(0.02, 0.025, 0.02).lerp(Color(0.25, 0.2, 0.14), rim / maxf(rim + water, 1e-3))
			img.set_pixel(x, y, Color(c.r, c.g, c.b, clampf(water * 0.45 + rim, 0.0, 1.0)))
	_save(img, "puddle")
	_orm_from(img, 0.03, "puddle")


## 门口地上的黄黑斑马线，被鞋底磨掉了不少
func _hazard() -> void:
	var w := 512
	var h := 72
	var img := _img(w, h)
	for y in h:
		for x in w:
			var stripe := fmod(float(x + y) / 36.0, 2.0) < 1.0
			var c := Color(0.62, 0.45, 0.05) if stripe else Color(0.04, 0.04, 0.035)
			var wear := _sstep(0.38, 0.5, _n01(x * 2.0, y * 2.0) + _n201(x * 1.2, y * 6.0) * 0.25)
			var edge := minf(minf(x, w - 1 - x), minf(y, h - 1 - y))
			var al := wear * _sstep(0.0, 3.0, edge) * 0.92
			c = c.lerp(Color(0.18, 0.16, 0.12), (1.0 - _n201(x * 3.0, y * 3.0)) * 0.35)
			img.set_pixel(x, y, Color(c.r, c.g, c.b, al))
	_save(img, "hazard")
	_orm_from(img, 0.6, "hazard")


## 锈水：上面一小块锈斑，往下流成几道越来越细、越来越淡的痕
func _rust() -> void:
	var w := 128
	var h := 512
	var img := _img(w, h)
	for y in h:
		for x in w:
			var u := float(x) / w - 0.5
			var v := float(y) / h
			var spot := 1.0 - _sstep(0.12, 0.3, Vector2(u, (v - 0.06) * 2.0).length()
				+ (_n01(x * 4.0, y * 4.0) - 0.5) * 0.15)
			var width := 0.36 * (1.0 - v * 0.6)
			var lanes := _n01(x * 5.0, v * 12.0)
			var streak := 1.0 - _sstep(width * 0.4, width, absf(u + (_n201(0, y * 0.5) - 0.5) * 0.12))
			streak *= _sstep(0.3, 0.55, lanes) * (1.0 - _sstep(0.35, 1.0, v)) * _sstep(0.0, 0.06, v)
			var al := clampf(spot * 0.8 + streak * (0.35 + 0.4 * lanes), 0.0, 1.0)
			var c := Color(0.36, 0.15, 0.05).lerp(Color(0.18, 0.08, 0.03), _n201(x * 4.0, y * 2.0))
			img.set_pixel(x, y, Color(c.r, c.g, c.b, al))
	_save(img, "rust")


## 冷凝水往下淌的痕：几道细细的湿痕（只是发暗、发亮）
func _streak() -> void:
	var w := 128
	var h := 256
	var img := _img(w, h)
	for y in h:
		for x in w:
			var v := float(y) / h
			var t := _sstep(0.55, 0.8, _n01(x * 9.0, v * 8.0)) * (1.0 - _sstep(0.5, 1.0, v))
			img.set_pixel(x, y, Color(0.05, 0.05, 0.045, t * 0.5))
	_save(img, "streak")
	_orm_from(img, 0.06, "streak")


## 门上一个油乎乎的手印，手掌往下拖出几道印子
func _hand() -> void:
	var w := 256
	var h := 448
	var img := _img(w, h)
	var fingers := [
		[Vector2(0.3, 0.62), Vector2(0.13, 0.5), 0.065],   # 拇指
		[Vector2(0.36, 0.45), Vector2(0.31, 0.18), 0.05],
		[Vector2(0.47, 0.43), Vector2(0.47, 0.13), 0.052],
		[Vector2(0.58, 0.45), Vector2(0.62, 0.17), 0.049],
		[Vector2(0.67, 0.5), Vector2(0.76, 0.3), 0.042],
	]
	var aspect := float(h) / w
	for y in h:
		for x in w:
			var p := Vector2(float(x) / w, float(y) / h * aspect)
			var palm_c := Vector2(0.5, 0.64 * aspect)
			var q := (p - palm_c) / Vector2(0.27, 0.25)
			var edge_n := (_n01(x * 6.0, y * 6.0) - 0.5) * 0.3
			var palm := 1.0 - _sstep(0.8, 1.05, q.length() + edge_n)
			var fing := 0.0
			for f in fingers:
				var a: Vector2 = f[0] * Vector2(1, aspect)
				var b: Vector2 = f[1] * Vector2(1, aspect)
				# 指尖、指节压得重，中间轻
				var d: float = _seg_dist(p, a, b) + edge_n * f[2]
				fing = maxf(fing, 1.0 - _sstep(f[2] * 0.7, f[2], d))
			# 手掌中间不怎么着力，印子淡
			var shape := maxf(palm * (0.45 + 0.55 * _sstep(0.3, 0.9, q.length())), fing)
			shape *= _sstep(0.25, 0.55, _n01(x * 2.5 + 77.0, y * 2.5))
			# 往下拖的痕
			var v := float(y) / h
			var drag := _sstep(0.4, 0.7, _n01(x * 5.0, 0.0)) * _sstep(0.72, 0.8, v) * (1.0 - _sstep(0.8, 1.0, v))
			drag *= 1.0 - _sstep(0.25, 0.3, absf(float(x) / w - 0.5))
			var texture := 0.45 + 0.55 * _n201(x * 4.0, y * 4.0)
			var al := clampf(shape * texture + drag * 0.6, 0.0, 1.0) * 0.6
			img.set_pixel(x, y, Color(0.045, 0.035, 0.03, al))
	_save(img, "hand")
	_orm_from(img, 0.3, "hand")


## 喷漆字：在白字底图上加飞白、磨损，边缘一点喷枪的雾
func _text(name: String, color: Color, wear_amt: float) -> void:
	var src := Image.load_from_file(ProjectSettings.globalize_path(SRC + name + ".png"))
	src.convert(Image.FORMAT_RGBA8)
	var w := src.get_width()
	var h := src.get_height()
	var blur := src.duplicate() as Image
	blur.resize(w / 8, h / 8, Image.INTERPOLATE_BILINEAR)
	blur.resize(w, h, Image.INTERPOLATE_BILINEAR)
	var img := _img(w, h)
	for y in h:
		for x in w:
			var a := src.get_pixel(x, y).a
			var fog := blur.get_pixel(x, y).a * 0.18
			var wear := _sstep(wear_amt - 0.12, wear_amt + 0.08, _n01(x * 1.5, y * 1.5) * 0.7 + _n201(x * 2.0, y * 2.0) * 0.5)
			var al := clampf(a * wear + fog * (1.0 - a), 0.0, 1.0) * 0.92
			var c := color.lerp(color * 0.75, _n201(x * 0.8, y * 0.8))
			img.set_pixel(x, y, Color(c.r, c.g, c.b, al))
	_save(img, "text_" + name)
