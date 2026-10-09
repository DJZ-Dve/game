class_name SonarDisplay
extends Node
## 驾驶台主动声呐（扫描式，艏向朝上的 PPI 显示）。
## 换能器每转一小步发一次声脉冲：往这个方位打一扇从陡到平的射线，命中的海底、礁石按距离写进极坐标回波图的一列
## （海底连成一片，凸起的东西后面留下声影），屏幕上按扫过的先后算余辉。画面在离屏 SubViewport 里画好
## （sonar_ppi.gdshader + 屏上的字），再由显像管材质（crt_sonar.gdshader）贴到 Screen_Sonar 上。

const RES := 512                    # 离屏画面分辨率
const BEARINGS := 256               # 一圈分多少个方位
const BINS := 160                   # 距离分多少格
const SONAR_HEAD := Vector3(0, -0.9, -5.2)   # 换能器在艇上的位置（艏部下方）
const FONT := preload("res://assets/fonts/DSEG14Classic-Regular.ttf")
const PPI := preload("res://assets/shaders/sonar_ppi.gdshader")
const INK := Color(0.45, 1.0, 0.5, 0.85)

## 扫描线转回艏向（每转一圈一次），这时发一声能听见的 ping
signal pinged

@export var range_m := 100.0        # 量程（面板上档位开关指在 100）
@export var period := 8.0           # 转一圈的秒数
@export var gain := 1.15
@export var cursor_brg := 42.0      # 电子方位线（度）
@export var cursor_rng := 37.5      # 活动距离圈（米）

var sub: Submarine
var _img: Image
var _tex: ImageTexture
var _ppi: ShaderMaterial
var _vp: SubViewport
var _overlay: Node2D
var _lamp: StandardMaterial3D
var _sweep := 0.0
var _next_col := 0
var _col := PackedFloat32Array()
var _fan := PackedFloat32Array()    # 一次发射的射线：往下的斜率（tan），从陡到平
var _heading := -1


func setup(p_sub: Submarine, screen: MeshInstance3D, lamp: MeshInstance3D) -> void:
	sub = p_sub
	_img = Image.create(BEARINGS, BINS, false, Image.FORMAT_R8)
	_tex = ImageTexture.create_from_image(_img)
	_col.resize(BINS)
	for k in 23:
		_fan.append(3.0 * pow(0.75, k))
	_fan.append(0.0)
	_fan.append(-0.04)

	_vp = SubViewport.new()
	_vp.size = Vector2i(RES, RES)
	_vp.disable_3d = true
	_vp.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	add_child(_vp)
	var rect := ColorRect.new()
	rect.size = Vector2(RES, RES)
	_ppi = ShaderMaterial.new()
	_ppi.shader = PPI
	_ppi.set_shader_parameter("returns", _tex)
	_ppi.set_shader_parameter("gain", gain)
	_ppi.set_shader_parameter("px", 2.0 / RES / 0.96)
	_ppi.set_shader_parameter("cursor_brg", cursor_brg / 360.0)
	_ppi.set_shader_parameter("cursor_rng", cursor_rng / range_m)
	rect.material = _ppi
	_vp.add_child(rect)
	_overlay = Node2D.new()
	_overlay.draw.connect(_draw_overlay)
	_vp.add_child(_overlay)

	var crt := (screen.get_active_material(0) as ShaderMaterial).duplicate() as ShaderMaterial
	crt.set_shader_parameter("screen_tex", _vp.get_texture())
	screen.set_surface_override_material(0, crt)
	if lamp and lamp.get_active_material(0) is StandardMaterial3D:
		_lamp = lamp.get_active_material(0).duplicate()
		lamp.set_surface_override_material(0, _lamp)


func _process(delta: float) -> void:
	if sub == null:
		return
	var before := _sweep
	_sweep = fmod(_sweep + delta / period, 1.0)
	if _sweep < before:
		pinged.emit()
	var target := int(_sweep * BEARINGS)
	var dirty := false
	while _next_col != target:
		_ping(_next_col)
		_next_col = (_next_col + 1) % BEARINGS
		dirty = true
	if dirty:
		_tex.update(_img)
	_ppi.set_shader_parameter("sweep", _sweep)
	var hdg := int(roundf(sub.heading_deg())) % 360
	if hdg != _heading:
		_heading = hdg
		_overlay.queue_redraw()
	if _lamp:
		var t := Time.get_ticks_msec() / 1000.0
		_lamp.emission_energy_multiplier = 3.0 if fmod(t * 3.0, 1.0) < 0.22 else 0.08


## 往第 col 个方位发一次声脉冲，结果写进回波图的那一列。
func _ping(col: int) -> void:
	var fwd := -sub.global_basis.z
	fwd.y = 0.0
	var h := fwd.normalized().rotated(Vector3.UP, -TAU * (col + 0.5) / BEARINGS)
	var origin := sub.global_transform * SONAR_HEAD
	var space := sub.get_world_3d().direct_space_state
	_col.fill(0.0)
	var prev_d := -1.0
	var prev_s := 0.0
	var prev_hard := false
	for t in _fan:
		var dir := (h + Vector3.DOWN * t).normalized()
		var q := PhysicsRayQueryParameters3D.create(origin, origin + dir * range_m)
		q.exclude = [sub.get_rid()]
		var hit := space.intersect_ray(q)
		if hit.is_empty():
			prev_d = -1.0
			continue
		var d := origin.distance_to(hit.position) / range_m
		var n: Vector3 = hit.normal
		var facing := absf(n.dot(-dir))
		# 海底（包括缓坡）是软泥沙，回波弱；陡的东西（礁石、沉船）当硬目标，迎着声波的那一面回波很强
		var hard := n.y < 0.35 or (hit.collider as Node).is_in_group("sonar_hard")
		var s := (0.7 + 0.6 * facing) if hard else (0.22 + 0.7 * facing)
		_splat(d, s)
		# 相邻两条射线落在同一片海底上：中间这段也是海底，连成一片；前一条打在硬目标上，中间就是它的声影
		if prev_d >= 0.0 and not prev_hard and not hard and d > prev_d and d - prev_d < 0.45:
			var i0 := int(prev_d * BINS)
			var i1 := int(d * BINS)
			for i in range(i0 + 1, i1):
				_col[i] += lerpf(prev_s, s, float(i - i0) / (i1 - i0)) * 0.7
		prev_d = d
		prev_s = s
		prev_hard = hard
	for i in BINS:
		var r := (i + 0.5) / BINS
		var v := _col[i] * randf_range(0.4, 1.3) * (1.0 - 0.3 * r)   # 斑点噪声、传播损失
		v += randf() * 0.045                                         # 底噪
		if i < 3:
			v += randf() * 0.5                                       # 发射余震：中心一小圈
		_img.set_pixel(col, i, Color(clampf(v, 0.0, 1.0), 0, 0))


func _splat(d: float, s: float) -> void:
	var i := int(d * BINS)
	for k in range(-1, 2):
		if i + k >= 0 and i + k < BINS:
			_col[i + k] += s * (1.0 if k == 0 else 0.45)


## 屏上的字：量程、艏向、游标的方位和距离、距离环刻度。
func _draw_overlay() -> void:
	var c := Vector2(RES, RES) / 2.0
	var R := RES / 2.0 * 0.96
	_text(c + Vector2(-R * 0.82, -R * 0.42), "R %dM" % int(range_m), false)
	_text(c + Vector2(R * 0.82, -R * 0.42), "HDG %03d" % _heading, true)
	_text(c + Vector2(-R * 0.82, R * 0.52), "B %03d" % int(cursor_brg), false)
	_text(c + Vector2(R * 0.82, R * 0.52), "D %05.1f" % cursor_rng, true)
	for k in range(1, 4):
		_text(c + Vector2(5, -R * k / 4.0 + 15), str(int(range_m * k / 4.0)), false, 12, 0.6)


func _text(pos: Vector2, s: String, right: bool, size := 17, alpha := 1.0) -> void:
	if right:
		pos.x -= FONT.get_string_size(s, HORIZONTAL_ALIGNMENT_LEFT, -1, size).x
	_overlay.draw_string(FONT, pos, s, HORIZONTAL_ALIGNMENT_LEFT, -1, size, Color(INK, INK.a * alpha))
