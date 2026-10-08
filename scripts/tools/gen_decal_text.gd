extends SceneTree
## 生成贴花用的文字底图（白字、透明底），给 gen_decals.gd 再加喷漆的磨损、飞白：
##   Godot --path . --script res://scripts/tools/gen_decal_text.gd
## 要用 GPU 画字，所以不能加 --headless（会闪一下窗口）。输出 assets/textures/decals/src/<名字>.png。
## 字体都在 blender/fonts/（SIL OFL）。排版照搬最早的 System.Drawing 版本：字号是 em 的像素数，
## 量字宽时左右各多算 1/6 em（GDI+ MeasureString 默认带的边距），文字在格子里水平、垂直居中。

const OUT := "res://assets/textures/decals/src/"
const FONTS := "res://blender/fonts/"

# name, 文字, 字体, 宽, 高, 箭头(0 无 / 1 朝右 / -1 朝左), 竖排
const ITEMS := [
	["c03", "C-03", "stencil", 1024, 410, 0, false],
	["fire", "严禁烟火", "sans_black", 256, 1024, 0, true],
	["cool", "冷却水", "sans_black", 1024, 174, 1, false],
	["firewater", "消防水", "sans_black", 1024, 174, 1, false],
	["return", "冷却回水", "sans_black", 1024, 174, -1, false],
	["air", "送风", "sans_black", 1024, 376, 1, false],
]


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(OUT))
	# [字体, 垂直居中用的 (上伸 - 下伸) / 2（em）]。GDI+ 按 OS/2 的 typo 上伸/下伸居中，而 Godot 的
	# get_ascent/get_descent 读的是 hhea，Noto Sans SC 这两组不一样（880/120 对 1000/200），所以写死；
	# Stardos Stencil 只在这里用，直接用 Godot 读到的值（-1）
	var fonts := {
		"stencil": [_font("StardosStencil-Bold.ttf"), -1.0],
		"sans_black": [_font("NotoSansSC-VF.ttf", 900), (0.88 - 0.12) / 2.0],
	}
	var vps := []
	for it in ITEMS:
		var vp := SubViewport.new()
		vp.size = Vector2i(it[3], it[4])
		vp.transparent_bg = true
		vp.msaa_2d = Viewport.MSAA_8X  # 箭头是多边形，靠 MSAA 抗锯齿
		vp.render_target_update_mode = SubViewport.UPDATE_ONCE
		var canvas := Node2D.new()
		canvas.draw.connect(_draw_item.bind(canvas, it, fonts[it[2]][0], fonts[it[2]][1]))
		vp.add_child(canvas)
		root.add_child(vp)
		vps.append(vp)
	await RenderingServer.frame_post_draw
	await RenderingServer.frame_post_draw
	for i in ITEMS.size():
		var img: Image = vps[i].get_texture().get_image()
		img.convert(Image.FORMAT_RGBA8)
		# 只有透明度有用（gen_decals.gd 只读 a），颜色统一成纯白，跟原来的底图一样
		for y in img.get_height():
			for x in img.get_width():
				img.set_pixel(x, y, Color(1, 1, 1, img.get_pixel(x, y).a))
		img.save_png(OUT + ITEMS[i][0] + ".png")
		print("text ", ITEMS[i][0])
	quit()


func _font(file: String, weight := 0) -> Font:
	var f := FontFile.new()
	f.load_dynamic_font(FONTS + file)
	if weight == 0:
		return f
	# 可变字体：按字重取实例（Noto Sans SC Black = 900）
	var v := FontVariation.new()
	v.base_font = f
	v.variation_opentype = {TextServerManager.get_primary_interface().name_to_tag("wght"): weight}
	return v


## 文字在矩形里水平、垂直居中（按字体的上伸/下伸居中，跟 GDI+ 一样）
func _text_in(ci: CanvasItem, font: Font, center_em: float, size: int, s: String, rect: Rect2) -> void:
	var tw := font.get_string_size(s, HORIZONTAL_ALIGNMENT_LEFT, -1, size).x
	var mid := center_em * size if center_em >= 0.0 else (font.get_ascent(size) - font.get_descent(size)) / 2.0
	var pos := Vector2(rect.get_center().x - tw / 2.0, rect.get_center().y + mid)
	ci.draw_string(font, pos, s, HORIZONTAL_ALIGNMENT_LEFT, -1, size, Color.WHITE)


func _draw_item(ci: CanvasItem, it: Array, font: Font, center_em: float) -> void:
	var text: String = it[1]
	var w: float = it[3]
	var h: float = it[4]
	var arrow: int = it[5]
	if it[6]:
		# 竖排：一个字一行
		var n := text.length()
		var cell := h / n
		for i in n:
			_text_in(ci, font, center_em, roundi(cell * 0.62), text[i], Rect2(0, i * cell, w, cell))
		return
	var text_w := w * 0.62 if arrow != 0 else w * 0.94
	var size := h * 0.78
	var fs := 0
	while true:
		fs = roundi(size)
		var m := font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, fs).x + fs / 3.0
		size *= 0.95
		if m <= text_w:
			break
	var x0 := w - text_w - w * 0.03 if arrow == -1 else (w * 0.03 if arrow == 1 else (w - text_w) / 2.0)
	_text_in(ci, font, center_em, fs, text, Rect2(x0, 0, text_w, h))
	if arrow != 0:
		# 流向箭头：杆 + 三角头
		var ax0 := w * 0.68 if arrow == 1 else w * 0.32
		var ax1 := w * 0.97 if arrow == 1 else w * 0.03
		var cy := h / 2.0
		var shaft := h * 0.14
		var head := h * 0.36
		var hx := ax1 - arrow * head * 1.1
		ci.draw_colored_polygon(PackedVector2Array([
			Vector2(ax0, cy - shaft), Vector2(hx, cy - shaft), Vector2(hx, cy - head), Vector2(ax1, cy),
			Vector2(hx, cy + head), Vector2(hx, cy + shaft), Vector2(ax0, cy + shaft)]), Color.WHITE)
