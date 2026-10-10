class_name PaperDoc
extends SubViewport
## 一张纸（合同、催款单、信、证件……）：在 SubViewport 里排好版，贴图同时给 3D 场景里的纸和阅读界面（StoryUI.read）用，
## 签名、手印盖上去以后两边一起变。正文是 BBCode 文本文件（assets/story/docs/*.txt），{名字} 这样的占位符由场景脚本填。
## 纸的样子：底色、纤维见 assets/shaders/paper.gdshader；发黄、水渍、折痕、泡过水（叠在字上面）见 paper_grime.gdshader。
## style = "lcd"：传呼机的点阵液晶屏（灰绿底、黑字，放大时一格一格的）。

const SERIF := "res://assets/fonts/NotoSerifSC-VF.ttf"
const HAND := "res://assets/fonts/LongCang-Regular.ttf"
const BRUSH := "res://assets/fonts/MaShanZheng-Regular.ttf"
const PAPER := preload("res://assets/shaders/paper.gdshader")
const GRIME := preload("res://assets/shaders/paper_grime.gdshader")
const RED_INK := Color(0.72, 0.08, 0.07)

@export_file("*.txt") var text_path := ""
@export var paper_size := Vector2i(1240, 1754)
@export var style := "paper"
@export var tint := Color(0.93, 0.9, 0.82)
@export var age := 0.3
@export var stains := 0.15
@export var wet := 0.0
@export var folds := Vector2.ZERO
@export var paper_seed := 1.0
@export var margin := Vector2(120, 130)
@export var font_size := 30
## 正文用什么字：serif 宋体、hand 手写（钢笔）、brush 毛笔
@export var font := "serif"
@export var line_spacing := 10
## 奖状那种红色双线花边（0 = 没有）
@export var border := 0.0
@export var border_color := Color(0.7, 0.1, 0.07)

var fields := {}
var _text: RichTextLabel
var _marks: Control
var _top: ColorRect
var _live := 0


func _ready() -> void:
	size = paper_size
	transparent_bg = false
	render_target_update_mode = SubViewport.UPDATE_ONCE
	canvas_item_default_texture_filter = Viewport.DEFAULT_CANVAS_ITEM_TEXTURE_FILTER_LINEAR_WITH_MIPMAPS
	var bg := ColorRect.new()
	bg.size = Vector2(paper_size)
	add_child(bg)
	if style == "lcd":
		bg.color = Color(0.53, 0.58, 0.47)
	else:
		bg.material = _paper_mat(true)
	if border > 0.0:
		var b := Border.new()
		b.width = border
		b.color = border_color
		b.size = Vector2(paper_size)
		add_child(b)
	_text = RichTextLabel.new()
	_text.bbcode_enabled = true
	_text.scroll_active = false
	_text.position = margin
	_text.size = Vector2(paper_size) - margin * 2.0
	_text.autowrap_mode = TextServer.AUTOWRAP_ARBITRARY
	var base := _font(font)
	_text.add_theme_font_override("normal_font", base)
	_text.add_theme_font_override("bold_font", _font("bold"))
	_text.add_theme_font_size_override("normal_font_size", font_size)
	_text.add_theme_font_size_override("bold_font_size", font_size)
	_text.add_theme_constant_override("line_separation", line_spacing)
	_text.add_theme_color_override("default_color", Color(0.12, 0.11, 0.1) if style != "lcd" else Color(0.08, 0.1, 0.07))
	add_child(_text)
	_marks = Control.new()
	_marks.size = Vector2(paper_size)
	add_child(_marks)
	if style != "lcd":
		_top = ColorRect.new()
		_top.size = Vector2(paper_size)
		_top.material = _paper_mat(false)
		add_child(_top)
	refresh()


func _paper_mat(is_base: bool) -> ShaderMaterial:
	var m := ShaderMaterial.new()
	m.shader = PAPER if is_base else GRIME
	m.set_shader_parameter("seed", paper_seed)
	m.set_shader_parameter("px_size", Vector2(paper_size))
	if is_base:
		m.set_shader_parameter("tint", tint)
	else:
		m.set_shader_parameter("age", age)
		m.set_shader_parameter("stains", stains)
		m.set_shader_parameter("wet", wet)
		m.set_shader_parameter("folds", folds)
	return m


func _font(kind: String) -> Font:
	var path := {"serif": SERIF, "bold": SERIF, "hand": HAND, "brush": BRUSH}.get(kind, SERIF) as String
	var f := FontVariation.new()
	f.base_font = load(path)
	if path == SERIF:
		f.variation_opentype = {"wght": 700 if kind == "bold" else 420}
	return f


## 重新排版（字段变了以后调一次）
func refresh() -> void:
	if _text == null:
		return
	var src := ""
	if not text_path.is_empty():
		var f := FileAccess.open(text_path, FileAccess.READ)
		if f:
			src = f.get_as_text()
	for k in fields:
		src = src.replace("{%s}" % k, str(fields[k]))
	src = src.replace("[hand]", "[font=%s]" % HAND).replace("[/hand]", "[/font]")
	src = src.replace("[brush]", "[font=%s]" % BRUSH).replace("[/brush]", "[/font]")
	_text.text = src
	render_target_update_mode = SubViewport.UPDATE_ONCE


## 盖章：圆形公章（外圈一圈字、中间五角星、下面一行字）
func add_stamp(center: Vector2, radius: float, ring_text: String, bottom := "", rot := 0.0, alpha := 0.85) -> Control:
	var s := Stamp.new()
	s.ring_text = ring_text
	s.bottom = bottom
	s.radius = radius
	s.font = _font("bold")
	s.modulate.a = alpha
	s.position = center
	s.rotation = deg_to_rad(rot)
	_marks.add_child(s)
	refresh()
	return s


## 红手印（按下去的那一下由 amount 0→1 显出来）
func add_thumb(center: Vector2, size_px: float, rot := 0.0) -> Thumbprint:
	var t := Thumbprint.new()
	t.size_px = size_px
	t.position = center
	t.rotation = deg_to_rad(rot)
	_marks.add_child(t)
	refresh()
	return t


## 手写的字（签名、填空）：reveal 0→1 一笔一笔写出来（从左往右露出来）
func add_writing(pos: Vector2, text: String, px: int, kind := "hand", color := Color(0.06, 0.07, 0.12),
		rot := 0.0) -> Writing:
	var w := Writing.new()
	w.text_value = text
	w.font = _font(kind)
	w.px = px
	w.color = color
	w.position = pos
	w.rotation = deg_to_rad(rot)
	_marks.add_child(w)
	refresh()
	return w


## 红笔圈一个圈（挂历上妈圈的日子）：手画的，首尾不齐、有点歪
func add_circle(center: Vector2, radius: float, color := Color(0.72, 0.08, 0.07)) -> Control:
	var c := HandCircle.new()
	c.radius = radius
	c.color = color
	c.position = center
	_marks.add_child(c)
	refresh()
	return c


## 一张海图（白沙门港到外海，归墟那块用红笔圈着）：rect 是画在纸上的范围
func add_chart(rect: Rect2, seed_ := 1, zoom := 1.0) -> Control:
	var c := SeaChart.new()
	c.position = rect.position
	c.size = rect.size
	c.font = _font("serif")
	c.brush = _font("brush")
	c.chart_seed = seed_
	c.zoom = zoom
	_marks.add_child(c)
	refresh()
	return c


## 竖排的字（拓片、碑文）：从右往左一列一列，「□」是磨掉的字（画一块斑）
func add_vertical(rect: Rect2, columns: PackedStringArray, px: int, color: Color, kind := "brush") -> Control:
	var v := VerticalText.new()
	v.position = rect.position
	v.size = rect.size
	v.columns = columns
	v.px = px
	v.color = color
	v.font = _font(kind)
	_marks.add_child(v)
	refresh()
	return v


## 一张照片（贴图），sepia：发黄的老照片；white_border：相纸的白边
func add_image(tex: Texture2D, rect: Rect2, white_border := 0.0) -> Control:
	var r := TextureRect.new()
	r.texture = tex
	r.position = rect.position
	r.size = rect.size
	r.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	r.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
	_marks.add_child(r)
	refresh()
	return r


## 动画期间一直重画（begin_live / end_live 成对调用）
func begin_live() -> void:
	_live += 1
	render_target_update_mode = SubViewport.UPDATE_ALWAYS


func end_live() -> void:
	_live = maxi(_live - 1, 0)
	if _live == 0:
		render_target_update_mode = SubViewport.UPDATE_ONCE


class Stamp extends Control:
	var ring_text := ""
	var bottom := ""
	var radius := 120.0
	var font: Font

	func _draw() -> void:
		var c := RED_INK
		draw_arc(Vector2.ZERO, radius, 0, TAU, 96, c, radius * 0.045, true)
		draw_arc(Vector2.ZERO, radius * 0.94, 0, TAU, 96, c, radius * 0.012, true)
		# 五角星
		var pts := PackedVector2Array()
		for i in 10:
			var r := radius * (0.3 if i % 2 == 0 else 0.12)
			var a := -PI / 2 + i * PI / 5
			pts.append(Vector2(cos(a), sin(a)) * r)
		draw_colored_polygon(pts, c)
		# 外圈的字：从左下沿着圈顺时针排到右下（字头朝外）
		var n := ring_text.length()
		var fs := int(radius * 0.22)
		var span := deg_to_rad(250.0)
		for i in n:
			var a := -PI / 2 - span / 2 + span * (i + 0.5) / n
			var p := Vector2(cos(a), sin(a)) * radius * 0.72
			draw_set_transform(p, a + PI / 2, Vector2.ONE)
			draw_string(font, Vector2(-fs * 0.5, fs * 0.36), ring_text[i], HORIZONTAL_ALIGNMENT_LEFT, -1, fs, c)
		draw_set_transform(Vector2.ZERO, 0, Vector2.ONE)
		if not bottom.is_empty():
			var bs := int(radius * 0.17)
			var w := font.get_string_size(bottom, HORIZONTAL_ALIGNMENT_LEFT, -1, bs).x
			draw_string(font, Vector2(-w / 2, radius * 0.55), bottom, HORIZONTAL_ALIGNMENT_LEFT, -1, bs, c)


class Thumbprint extends Control:
	## 指纹：一圈圈椭圆的纹路，用噪声扭一扭、打断几处；按得不匀，一边重一边轻
	var size_px := 90.0
	var amount := 0.0:
		set(v):
			amount = v
			queue_redraw()
	var _noise := FastNoiseLite.new()

	func _ready() -> void:
		_noise.frequency = 0.05
		_noise.seed = 7

	func _draw() -> void:
		if amount <= 0.0:
			return
		var a := size_px * 0.5
		var b := size_px * 0.66
		for k in 26:
			var r := 1.0 - k / 26.0
			var pts := PackedVector2Array()
			var seg := 0
			for i in 121:
				var t := TAU * i / 120.0
				var wob := _noise.get_noise_2d(cos(t) * 30.0 + k * 4.0, sin(t) * 30.0) * 0.06
				var p := Vector2(cos(t) * a * (r + wob), sin(t) * b * (r + wob) - b * 0.1 * (1.0 - r))
				var press := 0.55 + 0.45 * sin(t * 0.5 + 1.0) * amount
				var gap := _noise.get_noise_2d(t * 40.0, k * 13.0) > 0.35
				if gap or press < 0.25:
					if pts.size() > 1:
						draw_polyline(pts, Color(RED_INK, 0.75 * amount), size_px * 0.016, true)
					pts.clear()
					seg += 1
					continue
				pts.append(p)
			if pts.size() > 1:
				draw_polyline(pts, Color(RED_INK, 0.75 * amount), size_px * 0.016, true)
		# 底下一层淡淡的印泥
		draw_circle(Vector2.ZERO, size_px * 0.42, Color(RED_INK, 0.12 * amount))


class Writing extends Control:
	var text_value := ""
	var font: Font
	var px := 48
	var color := Color.BLACK
	var reveal := 1.0:
		set(v):
			reveal = v
			queue_redraw()

	func _draw() -> void:
		var w := font.get_string_size(text_value, HORIZONTAL_ALIGNMENT_LEFT, -1, px).x
		var cut := w * reveal
		# 逐字露出来：每个字按它在整行里的位置，过了 cut 就不画（正在写的那个字半透明）
		var x := 0.0
		for ch in text_value:
			var cw := font.get_string_size(ch, HORIZONTAL_ALIGNMENT_LEFT, -1, px).x
			var k := clampf((cut - x) / maxf(cw, 1.0), 0.0, 1.0)
			if k > 0.0:
				draw_string(font, Vector2(x, 0), ch, HORIZONTAL_ALIGNMENT_LEFT, -1, px, Color(color, color.a * k))
			x += cw


class HandCircle extends Control:
	var radius := 40.0
	var color := RED_INK

	func _draw() -> void:
		var pts := PackedVector2Array()
		for i in 73:
			var t := TAU * 1.12 * i / 72.0 - 0.4
			var r := radius * (1.0 + 0.06 * sin(t * 3.0 + 1.0) + 0.03 * sin(t * 7.0))
			pts.append(Vector2(cos(t) * r * 1.15, sin(t) * r))
		draw_polyline(pts, color, maxf(radius * 0.07, 2.0), true)


class Border extends Control:
	var width := 40.0
	var color := RED_INK

	func _draw() -> void:
		var m := width
		var r := Rect2(Vector2(m, m), size - Vector2(m, m) * 2.0)
		draw_rect(r, color, false, width * 0.18, true)
		var r2 := r.grow(-width * 0.45)
		draw_rect(r2, color, false, width * 0.06, true)
		# 四个角上一个小回纹方块
		for c in [r2.position, Vector2(r2.end.x, r2.position.y), r2.end, Vector2(r2.position.x, r2.end.y)]:
			draw_rect(Rect2(c - Vector2(width, width) * 0.3, Vector2(width, width) * 0.6), color, true)


class SeaChart extends Control:
	## 老海图：经纬网、西边一道海岸线和几个岛、一圈圈等深线、零散的水深数字、罗经花、图名框；
	## 东边一道海沟（等深线围成的长条），红笔圈起来，毛笔写着「归墟」
	var font: Font
	var brush: Font
	var chart_seed := 1
	var zoom := 1.0
	var _n := FastNoiseLite.new()
	const INK := Color(0.16, 0.18, 0.22)
	const LAND := Color(0.78, 0.7, 0.52)

	func _coast(y: float) -> float:
		# 海岸线：x 随 y 起伏（左边是陆地）
		return size.x * (0.16 + 0.07 * _n.get_noise_1d(y * 0.8) + 0.03 * _n.get_noise_1d(y * 3.0))

	func _draw() -> void:
		_n.seed = chart_seed
		_n.frequency = 0.004 / zoom
		var w := size.x
		var h := size.y
		var trench := Vector2(w * 0.72, h * 0.52)
		# 陆地
		var land := PackedVector2Array([Vector2(0, 0)])
		for i in 61:
			var y := h * i / 60.0
			land.append(Vector2(_coast(y), y))
		land.append(Vector2(0, h))
		draw_colored_polygon(land, LAND)
		draw_polyline(land.slice(1, land.size() - 1), INK, 2.5, true)
		# 岛
		for k in 5:
			var c := Vector2(w * (0.28 + 0.06 * k), h * (0.15 + 0.17 * ((k * 37) % 5)))
			var pts := PackedVector2Array()
			for i in 25:
				var a := TAU * i / 24.0
				var r := (14.0 + 10.0 * (k % 3)) * zoom * (1.0 + 0.35 * _n.get_noise_2d(cos(a) * 40 + k * 99, sin(a) * 40))
				pts.append(c + Vector2(cos(a), sin(a)) * r)
			draw_colored_polygon(pts, LAND)
			draw_polyline(pts, INK, 1.5, true)
		# 等深线：和海岸线大致平行，越往东越深；海沟那块自己围成一圈圈
		var depths := [10, 20, 50, 100, 200]
		for k in depths.size():
			var pts := PackedVector2Array()
			for i in 61:
				var y := h * i / 60.0
				pts.append(Vector2(_coast(y) + w * (0.05 + 0.07 * k) + 18.0 * _n.get_noise_2d(y * 2.0, k * 50.0), y))
			draw_polyline(pts, Color(INK, 0.55), 1.2, true)
			draw_string(font, pts[20 + k * 6] + Vector2(4, 0), str(depths[k]), HORIZONTAL_ALIGNMENT_LEFT, -1, int(16 * zoom),
				Color(INK, 0.7))
		for k in 4:
			var pts := PackedVector2Array()
			var rx := w * (0.16 - 0.035 * k)
			var ry := h * (0.07 - 0.014 * k)
			for i in 49:
				var a := TAU * i / 48.0
				var wob := 1.0 + 0.12 * _n.get_noise_2d(cos(a) * 60 + k * 33, sin(a) * 60)
				pts.append(trench + Vector2(cos(a) * rx, sin(a) * ry).rotated(-0.5) * wob)
			draw_polyline(pts, Color(INK, 0.6), 1.2, true)
		# 水深数字：散在海里，越往东越大
		var rng := RandomNumberGenerator.new()
		rng.seed = chart_seed
		for i in 70:
			var p := Vector2(rng.randf_range(w * 0.25, w * 0.97), rng.randf_range(h * 0.04, h * 0.96))
			if p.x < _coast(p.y) + 20:
				continue
			var d := int(8.0 + (p.x - _coast(p.y)) / w * 380.0)
			if p.distance_to(trench) < w * 0.1:
				d = 900 + rng.randi_range(0, 260)
			draw_string(font, p, str(d), HORIZONTAL_ALIGNMENT_LEFT, -1, int(14 * zoom), Color(INK, 0.8))
		# 经纬网和边上的刻度
		for i in 5:
			var x := w * (i + 0.5) / 5.0
			draw_line(Vector2(x, 0), Vector2(x, h), Color(INK, 0.25), 1.0)
			draw_string(font, Vector2(x + 4, 22), "%d°%02d′E" % [122, 20 + i * 12], HORIZONTAL_ALIGNMENT_LEFT, -1, 16, INK)
		for i in 4:
			var y := h * (i + 0.5) / 4.0
			draw_line(Vector2(0, y), Vector2(w, y), Color(INK, 0.25), 1.0)
			draw_string(font, Vector2(w - 110, y - 6), "%d°%02d′N" % [29, 50 - i * 10], HORIZONTAL_ALIGNMENT_LEFT, -1, 16, INK)
		draw_rect(Rect2(Vector2.ZERO, size), INK, false, 3.0)
		# 港口
		var port := Vector2(_coast(h * 0.42) - 6, h * 0.42)
		draw_circle(port, 6, INK)
		draw_string(font, port + Vector2(-110, -10), "白沙门", HORIZONTAL_ALIGNMENT_LEFT, -1, 26, INK)
		# 罗经花
		var rc := Vector2(w * 0.4, h * 0.82)
		draw_arc(rc, 60, 0, TAU, 48, Color(INK, 0.7), 1.5, true)
		draw_arc(rc, 52, 0, TAU, 48, Color(INK, 0.5), 1.0, true)
		for k in 8:
			var a := TAU * k / 8.0 - PI / 2
			var L := 58.0 if k % 2 == 0 else 34.0
			draw_colored_polygon(PackedVector2Array([rc + Vector2(cos(a), sin(a)) * L,
				rc + Vector2(cos(a + 0.2), sin(a + 0.2)) * 9, rc + Vector2(cos(a - 0.2), sin(a - 0.2)) * 9]), Color(INK, 0.8))
		draw_string(font, rc + Vector2(-8, -66), "北", HORIZONTAL_ALIGNMENT_LEFT, -1, 22, INK)
		# 图名框
		var tb := Rect2(Vector2(w * 0.04, h * 0.04), Vector2(w * 0.3, h * 0.13))
		draw_rect(tb, Color(0.95, 0.92, 0.84), true)
		draw_rect(tb, INK, false, 2.0)
		draw_string(font, tb.position + Vector2(16, 40), "白沙门港至东部外海", HORIZONTAL_ALIGNMENT_LEFT, -1, 30, INK)
		draw_string(font, tb.position + Vector2(16, 76), "比例尺 1:250,000　一九五七年测　水深单位：米",
			HORIZONTAL_ALIGNMENT_LEFT, -1, 16, INK)
		# 铅笔：从港口到海沟画了一道线，标着方位、海里数
		draw_dashed_line(port, trench, Color(0.3, 0.3, 0.32, 0.8), 2.0, 10.0)
		draw_string(font, (port + trench) * 0.5 + Vector2(-60, -12), "091°　140 n mile", HORIZONTAL_ALIGNMENT_LEFT, -1, 18,
			Color(0.3, 0.3, 0.32))
		# 红笔圈 + 毛笔字
		var red := Color(0.72, 0.08, 0.07)
		var pts := PackedVector2Array()
		for i in 70:
			var a := TAU * 1.1 * i / 69.0 - 0.3
			var r := 1.0 + 0.06 * sin(a * 3.0 + 1.0)
			pts.append(trench + Vector2(cos(a) * w * 0.2 * r, sin(a) * h * 0.13 * r).rotated(-0.45))
		draw_polyline(pts, red, 4.0, true)
		draw_string(brush, trench + Vector2(w * 0.08, -h * 0.13), "归墟", HORIZONTAL_ALIGNMENT_LEFT, -1, 64, red)


class VerticalText extends Control:
	var columns := PackedStringArray()
	var px := 48
	var color := Color.WHITE
	var font: Font
	var _n := FastNoiseLite.new()

	func _draw() -> void:
		_n.seed = 3
		_n.frequency = 0.08
		var step_x := size.x / maxf(columns.size(), 1)
		for c in columns.size():
			var x := size.x - step_x * (c + 0.5) - px * 0.5
			var col := columns[c]
			for i in col.length():
				var ch := col[i]
				var y := px * 1.15 * (i + 1)
				if ch == "□":
					# 磨掉的字：一块斑驳的浅色
					for k in 6:
						var p := Vector2(x + px * 0.5, y - px * 0.4) + Vector2(_n.get_noise_2d(c * 50 + i * 7, k * 13.0),
							_n.get_noise_2d(k * 17.0, c * 31 + i * 3)) * px * 0.35
						draw_circle(p, px * (0.12 + 0.06 * abs(_n.get_noise_2d(i * 9.0, k * 5.0))), Color(color, 0.18))
					continue
				var a := 0.65 + 0.35 * _n.get_noise_2d(c * 40.0 + i * 11.0, 3.0)
				draw_string(font, Vector2(x, y), ch, HORIZONTAL_ALIGNMENT_LEFT, -1, px, Color(color, clampf(a, 0.35, 1.0)))
