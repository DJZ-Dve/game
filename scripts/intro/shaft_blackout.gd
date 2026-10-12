extends Node3D
## 开场镜头 3（docs/design.md「八、开场」）：冰井里，冰震，沿井壁一圈圈的灯从上往下一盏一盏灭掉。
## 场景全部由脚本搭：冰壁（程序生成的冰，assets/shaders/ice_wall.gdshader）、每 10 米一圈的环形走台
## （格栅、栏杆、投光灯）、竖着贯穿整口井的加热管、电梯导轨、电缆桥架。一圈的零件合成一个网格，用 MultiMesh 摆满。
## 坐标：井轴是 Y 轴，方位角 a = atan2(z, x)（和冰壁着色器一致）；第 i 圈走台面在 y = -i * RING_STEP（i 从 -1 开始，头顶还有一圈）。
## 声音是 tools/gen_sfx.py 合成的（shaft_*、ice_*、relay_drop……）。每圈灯的继电器声按距离晚到（声速 343 m/s），
## 远的更闷（AudioStreamPlayer3D 的距离滤波）、混响更多（Shaft 总线）。
## 调试：--shot-t=秒  定在这个时刻（截图看某一刻；时间不再走）；--shot-run 从这个时刻开始照常往下走。
##       --lookdev[=弧度]  站在走台上近看井壁（调冰的材质用；数字是视线往旁边偏多少）
## 录像：tools/record.sh .tmp/shaft 36 --scene=shaft

const R := 11.0                # 井的半径（米）
const RING_STEP := 12.0        # 走台的间距
const RING_FIRST := -1         # 头顶那一圈
const RING_LAST := 49
const WALL_TOP := 24.0
const DEPTH := 615.0           # 冰壁往下建到这么深（再往下早就黑了）
const WALK_IN := R - 1.45      # 走台内沿（栏杆）
const WALK_OUT := R - 0.06
const GAP := 0.09              # 电梯导轨两边留出的空档（方位角 0 两侧，弧度；约一米）
const LAMPS := 24              # 每圈几盏灯
const LIFT := 3.0              # 掘进机每一节的高度（节与节之间一道台阶，冰壁着色器里也用）
const LAMP_H := 1.22           # 灯在走台面上方多高（挂在扶手内侧）
const PIPE_ANGLES := [1.05, 2.62, 5.06]
const TRAY_ANGLE := 3.9
const JBOX_ANGLE := 3.66       # 每圈的接线箱（灯的电从这里接）
const LAMP_COLOR := Color(1.0, 0.9, 0.78)
const G := 1.315               # 欧罗巴的重力
const SOUND_SPEED := 343.0

# 时间线（秒）
const FADE_IN := 2.5
const QUAKE_T := 7.0           # 冰震开始：低频轰鸣、掉冰屑、灯跟着电压往下沉
const CRACK_T := 10.4          # 冰裂的一声，掉冰块，墙上开始出裂纹
const CASCADE_T := 12.6        # 头顶那圈灯灭，然后一圈一圈往下
const CASCADE_K := 1.6         # 第 n 圈在 CASCADE_T + K * sqrt(n) 灭：越往下传得越快
const LAST_HOLD := 1.9         # 最底下那圈多挣扎一会儿

var t := 0.0
var _frozen := false
var _rings: Array[Dictionary] = []   # {y, die, flick, lens, lights: [Light3D], base: [float]}
var _events: Array = []              # [时刻, Callable]，按时刻排好
var _ice_mat: ShaderMaterial
var _cam: Camera3D
var _cam_base: Transform3D
var _shake := FastNoiseLite.new()
var _fade: ColorRect
var _hum: AudioStreamPlayer
var _air: AudioStreamPlayer
var _quake_dust: GPUParticles3D
var _globes: MultiMeshInstance3D
var _env: Environment
var _lookdev := DebugArgs.has("lookdev")
var _chunks: Array[Dictionary] = []  # {node, vel, spin}
var _rng := RandomNumberGenerator.new()
var _streams := {}
var _fov := 52.0
var _aim := Vector3.ZERO           # 镜头看着的点（推长焦时移到还亮着那一圈的中心）
var _aim0 := Vector3.ZERO
var _hum_lvl := 1.0


func _ready() -> void:
	_rng.seed = 1998
	_shake.seed = 3
	_shake.frequency = 1.0
	if DebugArgs.has("shot-t"):
		t = float(DebugArgs.get_arg("shot-t"))
		_frozen = not DebugArgs.has("shot-run")
	# 冰的次表面散射：半径调大，灯照到冰上光会渗开一圈（离开场景时调回默认值）
	RenderingServer.sub_surface_scattering_set_scale(0.06, 0.02)
	_build_environment()
	_build_wall()
	_build_verticals()
	_build_rings()
	_build_particles()
	_build_camera()
	_build_overlay()
	_build_audio()
	_schedule()
	_update(0.0)


func _exit_tree() -> void:
	RenderingServer.sub_surface_scattering_set_scale(0.05, 0.01)


# ---------------------------------------------------------------------------- 时间线
func _process(delta: float) -> void:
	if not _frozen:
		t += delta
	while not _events.is_empty() and _events[0][0] <= t:
		var ev: Array = _events.pop_front()
		(ev[1] as Callable).call()
	_update(delta)


## 冰震的强度（0~1，冰裂那一下冲到 2）
func _quake(at: float) -> float:
	var q := smoothstep(QUAKE_T, QUAKE_T + 3.0, at) * (1.0 - smoothstep(CRACK_T + 7.0, CRACK_T + 17.0, at))
	if at > CRACK_T:
		q += 1.1 * exp(-(at - CRACK_T) / 0.9)
	return q


## 第 k 圈第 j 盏灯此刻的亮度（x）和灯丝的余辉（y）
func _lamp_power(k: int, j: int, at: float) -> Vector2:
	var lamp: Dictionary = _rings[k].lamps[j]
	var die: float = lamp.die
	var flick: float = lamp.flick
	if at >= die:
		return Vector2(0.0, exp(-(at - die) / 0.35))
	var p := 1.0
	var q := _quake(at)
	if q > 0.0:
		# 电压跟着往下沉、乱跳（整口井一起，各圈各盏差一点点）
		p -= 0.22 * q * (0.5 + 0.5 * _shake.get_noise_2d(at * 6.0, float(k) * 3.1 + float(j) * 0.7))
	if at >= die - flick:
		# 要灭之前：一阵乱闪（每秒 20 来次，亮灭随机），最后一下电弧闪得比平时还亮
		var slot := floori(at * 22.0)
		var h := fposmod(sin(float(slot) * 12.9898 + float(k) * 78.233 + float(j) * 37.719) * 43758.5453, 1.0)
		p *= 0.08 if h < 0.45 else 0.9
		if at > die - 0.05:
			p = 1.7
	return Vector2(clampf(p, 0.0, 1.8), 0.0)


func _lamp_angle(j: int) -> float:
	return GAP + 0.6 / R + (TAU - 2.0 * GAP - 1.2 / R) * j / float(LAMPS - 1)


func _update(delta: float) -> void:
	# 灯
	for k in _rings.size():
		var ring: Dictionary = _rings[k]
		var lamps: Array = ring.lamps
		var pw: Array[Vector2] = []
		var avg := 0.0
		for j in lamps.size():
			var pe := _lamp_power(k, j, t)
			pw.append(pe)
			avg += pe.x + 0.02 * pe.y
			_globes.multimesh.set_instance_custom_data(lamps[j].idx, Color(pe.x, pe.y, 0, 0))
		avg /= lamps.size()
		ring.avg = avg
		var lights: Array = ring.lights
		var lamp_of: Array = ring.lamp_of
		var base: Array = ring.base
		for i in lights.size():
			var l: Light3D = lights[i]
			var lj: int = lamp_of[i]
			var e: float = avg if lj < 0 else pw[lj].x + 0.02 * pw[lj].y
			l.light_energy = base[i] * e
			l.visible = l.light_energy > 0.001
	# 冰壁上的裂纹
	_ice_mat.set_shader_parameter("crack", pow(smoothstep(CRACK_T - 0.2, CRACK_T + 7.0, t), 0.6))
	# 镜头：很慢地往栏杆外探一点 + 手持的微晃 + 冰震的抖
	var q := _quake(t)
	var lean := smoothstep(0.0, 14.0, t) * 0.22
	var xf := _cam_base.translated_local(Vector3(0, -lean * 0.3, -lean))
	# 灯往下灭的时候，镜头推长焦一路追着下面还亮着的那几圈（让它们一直占着画面中间那一块）
	var target := 52.0
	var aim := _aim0
	for k in _rings.size():
		var ry: float = _rings[k].y
		if ry < _cam_base.origin.y - 6.0 and float(_rings[k].avg) > 0.05:
			if k > 1:
				target = clampf(2.0 * rad_to_deg(atan(R * 1.7 / (_cam_base.origin.y - ry + 3.0))), 3.5, 52.0)
				aim = Vector3(0.0, ry - 12.0, 0.0)
			break
		if k == _rings.size() - 1:
			target = _fov
			aim = _aim
	var follow := 1.0 if _frozen else 1.0 - exp(-delta * 1.3)
	_fov = lerpf(_fov, target, follow)
	_aim = _aim.lerp(aim, follow)
	xf.basis = Basis.looking_at(_aim - xf.origin, _cam_base.basis.y)  # 几乎正对下方：拿原来的“上”当参考，免得滚转乱跳
	if not _lookdev:
		_cam.fov = _fov
	var zoom := _fov / 52.0
	var hand := (0.0025 + 0.012 * q) * zoom
	var shake_pos := 0.006 + 0.03 * q
	xf.basis = xf.basis * Basis.from_euler(Vector3(
		_shake.get_noise_2d(t * 0.7, 1.0) * hand + _shake.get_noise_2d(t * 9.0, 5.0) * 0.006 * q * zoom,
		_shake.get_noise_2d(t * 0.6, 2.0) * hand + _shake.get_noise_2d(t * 8.0, 6.0) * 0.006 * q * zoom,
		_shake.get_noise_2d(t * 0.5, 3.0) * hand * 0.5))
	xf.origin += Vector3(_shake.get_noise_2d(t * 11.0, 7.0), _shake.get_noise_2d(t * 10.0, 8.0),
		_shake.get_noise_2d(t * 12.0, 9.0)) * shake_pos * minf(q, 1.0)
	_cam.transform = _cam_base if _lookdev else xf
	# 黑场淡入
	_fade.color.a = 1.0 - smoothstep(0.0, FADE_IN, t)
	# 灯的嗡声：按还亮着的灯（近的权重大）
	var lit := 0.0
	var wsum := 0.0
	for k in _rings.size():
		var w := 1.0 / (1.0 + absf(float(_rings[k].y) - _cam_base.origin.y) / 12.0)
		lit += clampf(float(_rings[k].avg), 0.0, 1.0) * w
		wsum += w
	# 平滑一下（灯乱闪时一帧一跳会出拉链声）
	_hum_lvl = lit / wsum if _frozen else lerpf(_hum_lvl, lit / wsum, 1.0 - exp(-delta / 0.08))
	_hum.volume_db = linear_to_db(maxf(_hum_lvl, 0.0005)) - 15.0
	# 环境光只跟着镜头附近这几圈走：上面的灯一灭，身边就该黑下来
	var near := 0.0
	var nsum := 0.0
	for k in _rings.size():
		var w := exp(-absf(float(_rings[k].y) - _cam_base.origin.y) / 14.0)
		near += clampf(float(_rings[k].avg), 0.0, 1.0) * w
		nsum += w
	_env.ambient_light_energy = 0.12 * near / nsum
	_hum.pitch_scale = 1.0 - 0.03 * minf(q, 1.0)
	# 掉下去的冰块（低重力，一点空气阻力）
	if delta > 0.0 and not _frozen:
		for c in _chunks:
			var node: Node3D = c.node
			if not node.visible or c.rest:
				continue
			var v: Vector3 = c.vel
			v.y -= G * delta
			v *= 1.0 - 0.04 * delta
			c.vel = v
			node.position += v * delta
			node.rotate(c.spin_axis, c.spin * delta)
			if node.position.y < -260.0:
				node.visible = false
			if c.land and node.position.y < 0.15:
				node.position.y = 0.15
				c.rest = true
				_play3d("ice_impact_%d" % _rng.randi_range(0, 2), node.position, -3.0, _rng.randf_range(0.9, 1.2))


func _at(when: float, fn: Callable) -> void:
	if when < t:   # --shot-t 跳过去的那些声音就不放了
		return
	_events.append([when, fn])


func _schedule() -> void:
	# 冰震之前：加热管偶尔“嗒”一声
	for i in 5:
		var when := 0.8 + i * 1.3 + _rng.randf_range(0.0, 0.8)
		var a: float = PIPE_ANGLES[i % 3]
		_at(when, _play3d.bind("heater_tick_%d" % (i % 4), _pol(R - 0.2, a, 1.0 - _rng.randf_range(0, 6)), -14.0, _rng.randf_range(0.9, 1.1)))
	_at(QUAKE_T, _play2d.bind("ice_boom_0", -1.0, 1.0))
	_at(QUAKE_T, func() -> void: _quake_dust.emitting = true)
	_at(QUAKE_T + 2.2, _play2d.bind("steel_groan_0", -9.0, 0.85))
	_at(CRACK_T, _play2d.bind("ice_crack_0", -1.0, 1.0))
	_at(CRACK_T + 0.15, _play2d.bind("ice_boom_1", -5.0, 1.15))
	_at(CRACK_T + 0.8, _play2d.bind("ice_crack_1", -8.0, 0.9))
	_at(CRACK_T + 3.1, _play2d.bind("steel_groan_1", -8.0, 0.8))
	_at(CRACK_T + 5.4, _play2d.bind("ice_crack_2", -11.0, 0.85))
	_at(CRACK_T + 9.5, _play2d.bind("steel_groan_2", -12.0, 0.75))
	_at(CRACK_T + 11.0, _play2d.bind("ice_crack_3", -16.0, 0.8))
	_at(CRACK_T + 14.0, func() -> void: _quake_dust.emitting = false)
	for i in 9:
		_at(CRACK_T + 0.3 + _rng.randf_range(0.0, 3.5), _drop_chunk)
	# 每圈灯灭：接触器断开的声音，按距离晚到；最近几圈接线箱打火
	for k in _rings.size():
		var ring: Dictionary = _rings[k]
		var jb := _pol(R - 0.25, JBOX_ANGLE, float(ring.y) + 1.3)
		var delay := jb.distance_to(_cam_base.origin) / SOUND_SPEED
		_at(float(ring.die) + delay, _play3d.bind("relay_drop_%d" % (k % 3), jb, 4.0, _rng.randf_range(0.9, 1.08)))
		if k < 4:
			_at(float(ring.die), _sparks.bind(jb))
			_at(float(ring.die) + delay, _play3d.bind("spark_crackle_%d" % (k % 2), jb, -4.0, 1.0))
	# 全黑以后：冰还在挤，下面很远的地方有东西砸下去，最后一声闷响
	var end: float = _rings[-1].die
	_at(end + 1.2, _play2d.bind("steel_groan_0", -16.0, 0.65))
	_at(end + 2.6, _play3d.bind("ice_impact_0", Vector3(0, -180, 0), 6.0, 0.8))
	_at(end + 4.0, _play2d.bind("ice_boom_1", -5.0, 0.7))
	_events.sort_custom(func(x: Array, y: Array) -> bool: return x[0] < y[0])


# ---------------------------------------------------------------------------- 声音
func _build_audio() -> void:
	if AudioServer.get_bus_index("Shaft") == -1:
		AudioServer.add_bus()
		var idx := AudioServer.bus_count - 1
		AudioServer.set_bus_name(idx, "Shaft")
		AudioServer.set_bus_send(idx, "Master")
		var rv := AudioEffectReverb.new()
		rv.room_size = 0.92
		rv.damping = 0.3
		rv.spread = 1.0
		rv.wet = 0.36
		rv.dry = 0.9
		rv.predelay_msec = 70.0
		rv.predelay_feedback = 0.45
		rv.hipass = 0.05
		AudioServer.add_bus_effect(idx, rv)
	_air = AudioStreamPlayer.new()
	_air.stream = _stream("shaft_air")
	_air.volume_db = -13.0
	add_child(_air)
	_air.play()
	_hum = AudioStreamPlayer.new()
	_hum.stream = _stream("shaft_hum")
	_hum.bus = "Shaft"
	add_child(_hum)
	_hum.play()


func _stream(sfx: String) -> AudioStream:
	if not _streams.has(sfx):
		_streams[sfx] = load("res://assets/audio/%s.wav" % sfx)
	return _streams[sfx]


func _play2d(sfx: String, vol_db: float, pitch: float) -> void:
	var p := AudioStreamPlayer.new()
	p.stream = _stream(sfx)
	p.volume_db = vol_db
	p.pitch_scale = pitch
	p.bus = "Shaft"
	add_child(p)
	p.play()
	p.finished.connect(p.queue_free)
	DebugArgs.log_sfx(sfx)


func _play3d(sfx: String, pos: Vector3, vol_db: float, pitch: float) -> void:
	var p := AudioStreamPlayer3D.new()
	p.stream = _stream(sfx)
	p.position = pos
	p.volume_db = vol_db
	p.pitch_scale = pitch
	p.unit_size = 35.0
	p.max_distance = 800.0
	p.attenuation_filter_cutoff_hz = 7000.0
	p.attenuation_filter_db = -20.0
	p.doppler_tracking = AudioStreamPlayer3D.DOPPLER_TRACKING_DISABLED
	p.bus = "Shaft"
	add_child(p)
	p.play()
	p.finished.connect(p.queue_free)
	DebugArgs.log_sfx(sfx)


# ---------------------------------------------------------------------------- 画面：环境、镜头、叠层
func _build_environment() -> void:
	var env := Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color(0, 0, 0)
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	# 冰里透出来的散射光是蓝的：一层很淡的蓝色环境光，亮度跟着还亮着的灯走（全灭了就是全黑）
	env.ambient_light_color = Color(0.3, 0.55, 0.75)
	env.ambient_light_energy = 0.0
	_env = env
	env.tonemap_mode = Environment.TONE_MAPPER_AGX
	env.tonemap_exposure = 1.0
	env.ssao_enabled = true
	env.ssao_radius = 0.6
	env.ssao_intensity = 1.6
	# 不开屏幕空间反射：光滑的冰会把灯泡映成一团团模糊的大白斑
	env.ssr_enabled = false
	env.glow_enabled = true
	env.glow_intensity = 0.7
	env.glow_strength = 1.0
	env.glow_bloom = 0.03
	env.glow_blend_mode = Environment.GLOW_BLEND_MODE_SCREEN
	env.glow_hdr_threshold = 1.6
	env.fog_enabled = true
	env.fog_mode = Environment.FOG_MODE_EXPONENTIAL
	env.fog_light_color = Color(0, 0, 0)
	env.fog_density = 0.0018
	env.volumetric_fog_enabled = true
	env.volumetric_fog_density = 0.005
	env.volumetric_fog_albedo = Color(0.86, 0.9, 0.95)
	env.volumetric_fog_anisotropy = 0.62
	env.volumetric_fog_length = 140.0
	env.volumetric_fog_detail_spread = 1.6
	env.volumetric_fog_ambient_inject = 0.0
	env.volumetric_fog_temporal_reprojection_enabled = true
	env.adjustment_enabled = true
	env.adjustment_contrast = 1.08
	env.adjustment_saturation = 0.92
	var we := WorldEnvironment.new()
	we.environment = env
	add_child(we)


func _build_camera() -> void:
	# 吊在井中间偏一点的地方往下看：一圈圈走台、灯排成一条隧道，一直缩进下面的黑暗里
	var ca := 1.35
	var pos := _pol(2.6, ca, 4.5)
	var look := Vector3(0.0, -90.0, 0.0) + _pol(1.2, ca + PI, 0.0)
	_cam = Camera3D.new()
	_cam.fov = 52.0
	_cam.near = 0.03
	_cam.far = 900.0
	if _lookdev:
		# 看样机位：站在第 0 圈走台上，离井壁一米多，斜着看墙（调冰的材质用）
		var off := float(DebugArgs.get_arg("lookdev", "0.12"))
		pos = _pol(WALK_IN + 0.45, ca, 1.65)
		look = _pol(R, ca + off, 0.9)
		_cam.fov = 62.0
	_cam_base = Transform3D(Basis.looking_at(look - pos, Vector3.UP), pos)
	_aim0 = look
	_aim = look
	_cam.transform = _cam_base
	add_child(_cam)
	_cam.make_current()


func _build_overlay() -> void:
	var layer := CanvasLayer.new()
	add_child(layer)
	var film := ColorRect.new()
	film.set_anchors_preset(Control.PRESET_FULL_RECT)
	film.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var fm := ShaderMaterial.new()
	fm.shader = preload("res://assets/shaders/film_post.gdshader")
	fm.set_shader_parameter("grain", 0.03)
	fm.set_shader_parameter("vignette", 0.35)
	film.material = fm
	layer.add_child(film)
	# 宽银幕黑边（2.39:1）
	for top in [true, false]:
		var bar := ColorRect.new()
		bar.color = Color(0, 0, 0)
		bar.mouse_filter = Control.MOUSE_FILTER_IGNORE
		bar.anchor_left = 0.0
		bar.anchor_right = 1.0
		var frac := (1.0 - (16.0 / 9.0) / 2.39) * 0.5
		bar.anchor_top = 0.0 if top else 1.0 - frac
		bar.anchor_bottom = frac if top else 1.0
		layer.add_child(bar)
	_fade = ColorRect.new()
	_fade.set_anchors_preset(Control.PRESET_FULL_RECT)
	_fade.color = Color(0, 0, 0, 1)
	_fade.mouse_filter = Control.MOUSE_FILTER_IGNORE
	layer.add_child(_fade)


# ---------------------------------------------------------------------------- 粒子：冰晶、冰屑、火花、冰块
func _build_particles() -> void:
	# 井里的空气里飘着的细冰晶（钻石尘），在灯光里一闪一闪
	var motes := GPUParticles3D.new()
	motes.amount = 4000
	motes.lifetime = 14.0
	motes.preprocess = 14.0
	motes.visibility_aabb = AABB(Vector3(-R, -20, -R), Vector3(2 * R, 30, 2 * R))
	var pm := ParticleProcessMaterial.new()
	pm.emission_shape = ParticleProcessMaterial.EMISSION_SHAPE_BOX
	pm.emission_box_extents = Vector3(R * 0.8, 7.0, R * 0.8)
	pm.gravity = Vector3(0, -0.04, 0)
	pm.initial_velocity_min = 0.0
	pm.initial_velocity_max = 0.05
	pm.turbulence_enabled = true
	pm.turbulence_noise_strength = 0.4
	pm.turbulence_noise_scale = 2.5
	pm.turbulence_noise_speed_random = 0.3
	pm.scale_min = 0.4
	pm.scale_max = 1.3
	motes.process_material = pm
	motes.draw_pass_1 = _speck_mesh(0.008, Color(0.95, 0.97, 1.0, 0.55))
	motes.position = Vector3(0, -9, 0)  # 最近的离镜头也有五米：贴脸的冰晶会被灯照成一团团虚光
	add_child(motes)
	# 冰震时从井壁上震下来的冰屑：沿着井壁一圈往下飘（低重力，落得慢）
	_quake_dust = GPUParticles3D.new()
	_quake_dust.amount = 16000
	_quake_dust.lifetime = 12.0
	_quake_dust.emitting = false
	_quake_dust.visibility_aabb = AABB(Vector3(-R - 1, -90, -R - 1), Vector3(2 * R + 2, 110, 2 * R + 2))
	var qm := ParticleProcessMaterial.new()
	qm.emission_shape = ParticleProcessMaterial.EMISSION_SHAPE_RING
	qm.emission_ring_axis = Vector3(0, 1, 0)
	qm.emission_ring_radius = R - 0.1
	qm.emission_ring_inner_radius = R - 0.35
	qm.emission_ring_height = 34.0
	qm.direction = Vector3(0, -1, 0)
	qm.spread = 35.0
	qm.initial_velocity_min = 0.05
	qm.initial_velocity_max = 0.5
	qm.gravity = Vector3(0, -G, 0)
	qm.damping_min = 0.2
	qm.damping_max = 0.6
	qm.scale_min = 0.5
	qm.scale_max = 2.2
	_quake_dust.process_material = qm
	_quake_dust.draw_pass_1 = _speck_mesh(0.018, Color(0.88, 0.92, 0.96, 0.9))
	_quake_dust.position = Vector3(0, -6, 0)
	add_child(_quake_dust)
	# 冰块（先做好藏着，冰裂以后一块块掉）
	var cm := StandardMaterial3D.new()
	cm.albedo_color = Color(0.6, 0.7, 0.78)
	cm.roughness = 0.4
	cm.subsurf_scatter_enabled = true
	cm.subsurf_scatter_strength = 0.4
	for i in 9:
		var mi := MeshInstance3D.new()
		mi.mesh = _chunk_mesh(_rng.randf_range(0.12, 0.42), i)
		mi.material_override = cm
		mi.visible = false
		add_child(mi)
		_chunks.append({"node": mi, "vel": Vector3.ZERO, "spin": 0.0, "spin_axis": Vector3.UP, "land": false, "rest": false})


func _speck_mesh(size: float, col: Color) -> QuadMesh:
	var q := QuadMesh.new()
	q.size = Vector2(size, size)
	var m := StandardMaterial3D.new()
	m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	m.billboard_mode = BaseMaterial3D.BILLBOARD_PARTICLES
	m.albedo_color = col
	m.roughness = 0.3
	m.vertex_color_use_as_albedo = true
	# 圆的、边缘发虚的一点（不然近处看得出是方块）
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
	return q


func _drop_chunk() -> void:
	for c in _chunks:
		var node: Node3D = c.node
		if node.visible:
			continue
		# 从对面那半圈的井壁上掉（别贴着镜头飞过去）。头两块崩得远，从井中间一路掉下去；
		# 其余的贴着井壁往下掉，砸在下面那圈走台上（不然推长焦时一块块黑影挡在画面中间）
		var through := _chunks.find(c) < 2
		var a := atan2(_cam_base.origin.z, _cam_base.origin.x) + PI + _rng.randf_range(-1.3, 1.3)
		node.position = _pol(R - 0.2, a, _rng.randf_range(3.5, 9.0))
		var inward := -Vector3(cos(a), 0, sin(a))
		var push := _rng.randf_range(1.6, 2.2) if through else _rng.randf_range(0.05, 0.2)
		c.vel = inward * push + Vector3(0, -_rng.randf_range(0.0, 0.4), 0)
		c.land = not through
		c.spin = _rng.randf_range(0.6, 2.4)
		c.spin_axis = Vector3(_rng.randf_range(-1, 1), _rng.randf_range(-1, 1), _rng.randf_range(-1, 1)).normalized()
		node.visible = true
		_play3d("ice_crack_%d" % _rng.randi_range(1, 3), node.position, -14.0, _rng.randf_range(1.2, 1.6))
		return


## 接线箱打火：一把火星往外喷，在低重力里慢慢划着弧线落下去；加一盏一闪就暗的橙色光
func _sparks(at: Vector3) -> void:
	var sp := GPUParticles3D.new()
	sp.amount = 70
	sp.lifetime = 3.0
	sp.one_shot = true
	sp.explosiveness = 0.85
	sp.visibility_aabb = AABB(Vector3(-6, -30, -6), Vector3(12, 34, 12))
	var pm := ParticleProcessMaterial.new()
	var inward := -Vector3(at.x, 0, at.z).normalized()
	pm.direction = (inward + Vector3(0, 0.6, 0)).normalized()
	pm.spread = 55.0
	pm.initial_velocity_min = 1.2
	pm.initial_velocity_max = 4.0
	pm.gravity = Vector3(0, -G, 0)
	pm.damping_min = 0.3
	pm.damping_max = 0.8
	pm.particle_flag_align_y = true
	pm.scale_min = 0.6
	pm.scale_max = 1.2
	var grad := Gradient.new()
	grad.set_color(0, Color(1.0, 0.85, 0.5, 1.0))
	grad.set_color(1, Color(1.0, 0.25, 0.03, 0.0))
	var gt := GradientTexture1D.new()
	gt.gradient = grad
	pm.color_ramp = gt
	sp.process_material = pm
	var q := QuadMesh.new()
	q.size = Vector2(0.007, 0.07)
	var m := StandardMaterial3D.new()
	m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	m.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
	m.billboard_mode = BaseMaterial3D.BILLBOARD_FIXED_Y
	m.billboard_keep_scale = true
	m.vertex_color_use_as_albedo = true
	m.albedo_color = Color(4.0, 2.4, 1.0)
	q.material = m
	sp.draw_pass_1 = q
	sp.position = at
	add_child(sp)
	sp.emitting = true
	sp.finished.connect(sp.queue_free)
	var flash := OmniLight3D.new()
	flash.light_color = Color(1.0, 0.6, 0.25)
	flash.omni_range = 7.0
	flash.light_energy = 5.0
	flash.position = at + inward * 0.3
	add_child(flash)
	var tw := create_tween()
	tw.tween_property(flash, "light_energy", 0.0, 0.5).set_trans(Tween.TRANS_EXPO).set_ease(Tween.EASE_OUT)
	tw.tween_callback(flash.queue_free)


# ---------------------------------------------------------------------------- 冰壁
func _build_wall() -> void:
	_ice_mat = ShaderMaterial.new()
	_ice_mat.shader = preload("res://assets/shaders/ice_wall.gdshader")
	_ice_mat.set_shader_parameter("radius", R)
	_ice_mat.set_shader_parameter("lift", LIFT)
	# 冰里的东西用实拍的湖冰（ambientCG，CC0；tools/fetch_ambientcg.sh --ids Ice002,Ice004）
	for pair in [["ice_a", "Ice002"], ["ice_b", "Ice004"]]:
		var path := "res://assets/third_party/ambientcg/%s/%s_2K-JPG_Color.jpg" % [pair[1], pair[1]]
		if ResourceLoader.exists(path):
			_ice_mat.set_shader_parameter(pair[0], load(path))
	if _ice_mat.get_shader_parameter("ice_b") == null:
		_ice_mat.set_shader_parameter("ice_b", _ice_mat.get_shader_parameter("ice_a"))
	_ice_mat.set_shader_parameter("pipe_angles", Vector3(PIPE_ANGLES[0], PIPE_ANGLES[1], PIPE_ANGLES[2]))
	var mi := MeshInstance3D.new()
	mi.mesh = _wall_mesh()
	mi.material_override = _ice_mat
	add_child(mi)


## 冰壁的半径起伏（热水钻出来的井：大块的鼓包凹坑 + 一圈圈的细波纹）
func _wall_r(n1: FastNoiseLite, n2: FastNoiseLite, a: float, y: float) -> float:
	var c := cos(a) * R
	var s := sin(a) * R
	# 每节掘进的半径差一点（刀盘每次重新对位的误差），节与节之间就是一道台阶
	var step := (fposmod(sin(floorf(y / LIFT) * 91.7) * 4375.85, 1.0) - 0.5) * 0.025
	return R + 0.12 * n1.get_noise_3d(c, y * 0.6, s) + 0.03 * n2.get_noise_3d(c * 3.0, y * 2.0, s * 3.0) + step


func _wall_mesh() -> ArrayMesh:
	var n1 := FastNoiseLite.new()
	n1.seed = 7
	n1.frequency = 0.3
	n1.fractal_octaves = 3
	var n2 := FastNoiseLite.new()
	n2.seed = 11
	n2.frequency = 0.5
	var cols := 360
	var ys: Array[float] = []
	var y := WALL_TOP
	while y > -DEPTH:
		ys.append(y)
		y -= 0.25 if y > -70.0 else 2.5
	ys.append(-DEPTH)
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	st.set_color(Color(0, 0, 0, 1))
	var pos: Array[Vector3] = []
	for yy in ys:
		for c in cols + 1:
			var a := TAU * c / cols
			pos.append(_pol(_wall_r(n1, n2, a, yy), a, yy))
	var w := cols + 1
	for r in ys.size():
		for c in w:
			var p := pos[r * w + c]
			var pa := pos[r * w + (c + 1) % w] if c < cols else pos[r * w + 1]
			var pb := pos[mini(r + 1, ys.size() - 1) * w + c]
			var pc := pos[maxi(r - 1, 0) * w + c]
			var n := (pa - p).cross(pc - pb).normalized()
			if n.dot(-Vector3(p.x, 0, p.z)) < 0.0:
				n = -n
			st.set_normal(n)
			st.add_vertex(p)
	for r in ys.size() - 1:
		for c in cols:
			var i00 := r * w + c
			var i01 := i00 + 1
			var i10 := i00 + w
			var i11 := i10 + 1
			_index_tri(st, pos, i00, i10, i11)
			_index_tri(st, pos, i00, i11, i01)
	return st.commit()


## 朝着井轴的三角形（Godot 的正面是顺时针：(b-a)×(c-a) 要背着视线，也就是背着井轴）
func _index_tri(st: SurfaceTool, pos: Array[Vector3], a: int, b: int, c: int) -> void:
	var n := (pos[b] - pos[a]).cross(pos[c] - pos[a])
	var inward := -Vector3(pos[a].x, 0, pos[a].z)
	if n.dot(inward) > 0.0:
		var tmp := b
		b = c
		c = tmp
	st.add_index(a)
	st.add_index(b)
	st.add_index(c)


# ---------------------------------------------------------------------------- 竖着贯穿整口井的：加热管、电梯导轨、电缆桥架
func _build_verticals() -> void:
	var y0 := WALL_TOP
	var y1 := -DEPTH
	var pipes := SurfaceTool.new()
	pipes.begin(Mesh.PRIMITIVE_TRIANGLES)
	pipes.set_color(Color(0.15, 0.2, 0, 1))
	for a in PIPE_ANGLES:
		_cyl(pipes, _pol(R - 0.12, a, y0), _pol(R - 0.12, a, y1), 0.075, 14, false)
	_add_mesh(pipes.commit(), "res://assets/materials/M_PipeRed.tres")
	var steel := SurfaceTool.new()
	steel.begin(Mesh.PRIMITIVE_TRIANGLES)
	steel.set_color(Color(0.3, 0.25, 0, 1))
	var length := y0 - y1
	var mid := (y0 + y1) * 0.5
	# 电梯的两根 T 形导轨（方位角 0 两侧）
	for side in [-1.0, 1.0]:
		var a: float = side * 0.05
		var b := _radial_basis(a)
		_box(steel, Transform3D(b, _pol(R - 0.2, a, mid)), Vector3(0.018, length, 0.11))
		_box(steel, Transform3D(b, _pol(R - 0.135, a, mid)), Vector3(0.12, length, 0.018))
	# 电缆桥架：背板 + 两条侧边
	var tb := _radial_basis(TRAY_ANGLE)
	_box(steel, Transform3D(tb, _pol(R - 0.07, TRAY_ANGLE, mid)), Vector3(0.56, length, 0.012))
	for side in [-1.0, 1.0]:
		_box(steel, Transform3D(tb, _pol(R - 0.12, TRAY_ANGLE, mid) + tb.x * 0.28 * side), Vector3(0.012, length, 0.1))
	_add_mesh(steel.commit(), "res://assets/materials/M_SteelOld.tres")
	# 桥架里的电缆（黑、橙两种）
	for mat in ["res://assets/materials/M_CableBlack.tres", "res://assets/materials/M_CableOrange.tres"]:
		var cab := SurfaceTool.new()
		cab.begin(Mesh.PRIMITIVE_TRIANGLES)
		for k in 6:
			if (k % 3 == 1) != mat.ends_with("Orange.tres"):
				continue
			var off := -0.22 + k * 0.088
			var rr := 0.026 + 0.008 * (k % 2)
			var p := _pol(R - 0.11, TRAY_ANGLE, 0.0) + tb.x * off
			_cyl(cab, Vector3(p.x, y0, p.z), Vector3(p.x, y1, p.z), rr, 8, false)
		_add_mesh(cab.commit(), mat)


func _add_mesh(mesh: Mesh, mat_path: String) -> MeshInstance3D:
	var mi := MeshInstance3D.new()
	mi.mesh = mesh
	mi.material_override = load(mat_path)
	add_child(mi)
	return mi


# ---------------------------------------------------------------------------- 一圈走台 + 灯
func _build_rings() -> void:
	var segs := int(R * 30.0)
	var grating := SurfaceTool.new()
	grating.begin(Mesh.PRIMITIVE_TRIANGLES)
	grating.set_color(Color(0.06, 0.2, 0, 1))
	_arc_box(grating, WALK_IN, WALK_OUT, -0.045, 0.0, GAP, TAU - GAP, segs)
	var steel := SurfaceTool.new()
	steel.begin(Mesh.PRIMITIVE_TRIANGLES)
	steel.set_color(Color(0.12, 0.25, 0, 1))
	# 走台内沿的踢脚板、下面两道弧形梁
	_arc_box(steel, WALK_IN - 0.006, WALK_IN, -0.16, 0.1, GAP, TAU - GAP, segs)
	_arc_box(steel, WALK_IN + 0.02, WALK_IN + 0.16, -0.36, -0.045, GAP, TAU - GAP, segs)
	_arc_box(steel, R - 0.32, R - 0.18, -0.36, -0.045, GAP, TAU - GAP, segs)
	# 径向的托梁（每 1.3 米一根），一头插进冰里
	var a := GAP + 0.6 / R
	while a < TAU - GAP:
		var b := _radial_basis(a)
		var r0 := WALK_IN + 0.02
		var r1 := R + 0.25
		_box(steel, Transform3D(b, _pol((r0 + r1) * 0.5, a, -0.2)), Vector3(0.08, 0.3, r1 - r0))
		_box(steel, Transform3D(b, _pol(R - 0.04, a, -0.08)), Vector3(0.24, 0.5, 0.02))
		a += 1.3 / R
	# 栏杆立柱（每 1.5 米一根）
	a = GAP + 0.03 / R
	while a < TAU - GAP + 0.01:
		_cyl(steel, _pol(WALK_IN + 0.05, a, 0.0), _pol(WALK_IN + 0.05, a, 1.08), 0.021, 8, true)
		a += 1.5 / R
	# 管卡、桥架卡子、接线箱
	for pa in PIPE_ANGLES:
		_box(steel, Transform3D(_radial_basis(pa), _pol(R - 0.12, pa, 0.45)), Vector3(0.24, 0.06, 0.2))
	_box(steel, Transform3D(_radial_basis(TRAY_ANGLE), _pol(R - 0.12, TRAY_ANGLE, 0.6)), Vector3(0.62, 0.05, 0.14))
	_box(steel, Transform3D(_radial_basis(JBOX_ANGLE), _pol(R - 0.16, JBOX_ANGLE, 1.3)), Vector3(0.42, 0.55, 0.2))
	# 舱壁灯：从扶手上往井里伸出一根短臂，吊着一个带护罩的玻璃球。
	# 必须挂在扶手内侧：装在井壁上的话，从上面往下看远处的灯，视线会被上一圈走台挡住
	var lamp_pos: Array[Vector3] = []
	for j in LAMPS:
		var la := _lamp_angle(j)
		var b := _radial_basis(la)
		var p := _pol(WALK_IN - 0.17, la, LAMP_H)
		lamp_pos.append(p)
		_box(steel, Transform3D(b, _pol(WALK_IN - 0.06, la, LAMP_H + 0.13)), Vector3(0.035, 0.035, 0.26))
		_cyl(steel, p + Vector3(0, 0.08, 0), p + Vector3(0, 0.13, 0), 0.012, 6, false)
		_box(steel, Transform3D(b, p + b.z * 0.12), Vector3(0.24, 0.26, 0.012))  # 反光背板（挡着井壁那一侧）
		# 护罩：四根竖条 + 顶上一个小帽、下面一块托板（顶上不能盖严，从上往下看得见灯泡）
		for c in 4:
			var ca := TAU * c / 4.0 + PI / 4.0
			var off := (b.x * cos(ca) + b.z * sin(ca)) * 0.105
			_cyl(steel, p + off + Vector3(0, -0.1, 0), p + off + Vector3(0, 0.1, 0), 0.006, 5, false)
		_box(steel, Transform3D(b, p + Vector3(0, 0.11, 0)), Vector3(0.05, 0.015, 0.05))
		_box(steel, Transform3D(b, p + Vector3(0, -0.11, 0)), Vector3(0.12, 0.02, 0.12))
		# 走台底下的洗墙灯（每两盏球灯配一个）：灯壳挂在外梁下面，朝下贴着井壁照
		if j % 2 == 0:
			_box(steel, Transform3D(b, _pol(R - 0.55, la, -0.48)), Vector3(0.4, 0.16, 0.22))
	var rail := SurfaceTool.new()
	rail.begin(Mesh.PRIMITIVE_TRIANGLES)
	rail.set_color(Color(0.12, 0.15, 0, 1))
	_arc_tube(rail, WALK_IN + 0.05, 1.08, GAP, TAU - GAP, 0.026, segs)
	_arc_tube(rail, WALK_IN + 0.05, 0.56, GAP, TAU - GAP, 0.019, segs)

	var ys: Array[float] = []
	for i in range(RING_FIRST, RING_LAST + 1):
		ys.append(-i * RING_STEP)
	var rail_mat: ShaderMaterial = load("res://assets/materials/M_Rail.tres").duplicate()
	rail_mat.set_shader_parameter("paint_color", Color(0.5, 0.36, 0.06))
	var grate_mat: ShaderMaterial = load("res://assets/materials/M_Grating.tres").duplicate()
	grate_mat.set_shader_parameter("paint_color", Color(0.13, 0.13, 0.125))
	grate_mat.set_shader_parameter("rust_amount", 0.15)
	grate_mat.set_shader_parameter("tex_scale", 7.0)
	_multi(grating.commit(), grate_mat, ys)
	_multi(steel.commit(), load("res://assets/materials/M_SteelOld.tres"), ys)
	_multi(rail.commit(), rail_mat, ys)

	# 所有灯泡放进一个 MultiMesh：每个实例的自定义数据 r = 亮度、g = 余辉（lamp_lens.gdshader）
	var globe := SphereMesh.new()
	globe.radius = 0.085
	globe.height = 0.17
	globe.radial_segments = 16
	globe.rings = 8
	var lens_mat := ShaderMaterial.new()
	lens_mat.shader = preload("res://assets/shaders/lamp_lens.gdshader")
	lens_mat.set_shader_parameter("lit_color", LAMP_COLOR)
	var mm := MultiMesh.new()
	mm.transform_format = MultiMesh.TRANSFORM_3D
	mm.use_custom_data = true
	mm.mesh = globe
	mm.instance_count = ys.size() * LAMPS
	_globes = MultiMeshInstance3D.new()
	_globes.multimesh = mm
	_globes.material_override = lens_mat
	_globes.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(_globes)
	for k in ys.size():
		var y := ys[k]
		var n := float(k)
		var die := CASCADE_T + CASCADE_K * sqrt(n) + _rng.randf_range(-0.06, 0.06) * minf(n, 1.0)
		var last := k == ys.size() - 1
		# 一圈里也是一盏接一盏灭：从随机的一盏开始，顺着圈扫过去（灯多了，扫得快一点）
		var first := _rng.randi_range(0, LAMPS - 1)
		var sweep := _rng.randf_range(0.012, 0.02) * (2.5 if last else 1.0)
		var lamps: Array[Dictionary] = []
		for j in LAMPS:
			var idx := k * LAMPS + j
			mm.set_instance_transform(idx, Transform3D(Basis(), lamp_pos[j] + Vector3(0, y, 0)))
			mm.set_instance_custom_data(idx, Color(1, 0, 0, 0))
			var order := (j - first + LAMPS) % LAMPS
			var hold := LAST_HOLD if last else 0.0
			lamps.append({"idx": idx, "die": die + order * sweep + hold, "flick": _rng.randf_range(0.15, 0.5) + hold})
		var lights: Array[Light3D] = []
		var lamp_of: Array[int] = []   # 每个光源跟着哪盏灯（-1 = 跟着这一圈的平均亮度）
		var base: Array[float] = []
		if k <= 5:
			for j in LAMPS:
				var la := _lamp_angle(j)
				var radial := Vector3(cos(la), 0, sin(la))
				if j % 2 == 0:
					# 洗墙灯：朝下、略往井壁偏，光贴着冰面扫下去——切削纹、台阶、崩口全靠这道掠射光显出来
					var wl := SpotLight3D.new()
					var wdir := (radial * 0.22 + Vector3.DOWN).normalized()
					wl.transform = Transform3D(Basis.looking_at(wdir, radial), _pol(R - 0.55, la, y - 0.58))
					wl.light_color = LAMP_COLOR
					wl.spot_range = 16.0
					wl.spot_angle = 48.0
					wl.spot_attenuation = 0.8
					wl.light_size = 0.15
					wl.shadow_enabled = k <= 1 and j % 4 == 0
					wl.light_volumetric_fog_energy = 0.6
					add_child(wl)
					lights.append(wl)
					lamp_of.append(j)
					base.append(8.0)
				if j % 4 == 1:
					# 球灯朝井里的光（照走台、栏杆和空气里的冰晶；背后有反光板，不照身后的井壁）
					var sl := SpotLight3D.new()
					var dir := (-radial + Vector3(0, -0.45, 0)).normalized()
					sl.transform = Transform3D(Basis.looking_at(dir, Vector3.UP), lamp_pos[j] + Vector3(0, y, 0))
					sl.light_color = LAMP_COLOR
					sl.spot_range = 16.0
					sl.spot_angle = 75.0
					sl.spot_attenuation = 1.0
					sl.light_size = 0.09
					sl.light_volumetric_fog_energy = 1.4
					add_child(sl)
					lights.append(sl)
					lamp_of.append(j)
					base.append(2.4)
		else:
			# 远处：每圈三盏贴着井壁的全向灯，远看是一圈光带
			for j in [0, 8, 16]:
				var la := _lamp_angle(j)
				var ol := OmniLight3D.new()
				ol.position = _pol(R - 1.1, la, y - 2.0)
				ol.light_color = LAMP_COLOR
				ol.omni_range = 17.0
				ol.omni_attenuation = 1.0
				ol.light_volumetric_fog_energy = 1.0
				add_child(ol)
				lights.append(ol)
				lamp_of.append(-1)
				base.append(14.0)
		_rings.append({"y": y, "die": die, "lamps": lamps, "lights": lights, "lamp_of": lamp_of, "base": base, "avg": 1.0})


func _multi(mesh: Mesh, mat: Material, ys: Array[float]) -> void:
	var mm := MultiMesh.new()
	mm.transform_format = MultiMesh.TRANSFORM_3D
	mm.mesh = mesh
	mm.instance_count = ys.size()
	for k in ys.size():
		mm.set_instance_transform(k, Transform3D(Basis(), Vector3(0, ys[k], 0)))
	var mmi := MultiMeshInstance3D.new()
	mmi.multimesh = mm
	mmi.material_override = mat
	add_child(mmi)


# ---------------------------------------------------------------------------- 网格小工具（SurfaceTool；worn_surface 要顶点色：R 棱边磨损、G 凹槽积垢）
func _pol(r: float, a: float, y: float) -> Vector3:
	return Vector3(r * cos(a), y, r * sin(a))


## 在方位角 a 处：x 沿切向、y 朝上、z 朝外（背着井轴）
func _radial_basis(a: float) -> Basis:
	var radial := Vector3(cos(a), 0, sin(a))
	return Basis(Vector3(-sin(a), 0, cos(a)), Vector3.UP, radial)


func _tri(st: SurfaceTool, a: Vector3, b: Vector3, c: Vector3, na: Vector3, nb: Vector3, nc: Vector3) -> void:
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


func _quad(st: SurfaceTool, a: Vector3, b: Vector3, c: Vector3, d: Vector3, n: Vector3) -> void:
	_tri(st, a, b, c, n, n, n)
	_tri(st, a, c, d, n, n, n)


func _box(st: SurfaceTool, xf: Transform3D, s: Vector3) -> void:
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
			_quad(st, xf * (c - du - dv), xf * (c + du - dv), xf * (c + du + dv), xf * (c - du + dv), wn)


func _cyl(st: SurfaceTool, a: Vector3, b: Vector3, r: float, sides: int, caps: bool) -> void:
	var ax := (b - a).normalized()
	var u := ax.cross(Vector3.UP if absf(ax.y) < 0.9 else Vector3.RIGHT).normalized()
	var v := ax.cross(u)
	for k in sides:
		var a0 := TAU * k / sides
		var a1 := TAU * (k + 1) / sides
		var n0 := u * cos(a0) + v * sin(a0)
		var n1 := u * cos(a1) + v * sin(a1)
		_tri(st, a + n0 * r, b + n0 * r, b + n1 * r, n0, n0, n1)
		_tri(st, a + n0 * r, b + n1 * r, a + n1 * r, n0, n1, n1)
		if caps:
			_tri(st, a, a + n0 * r, a + n1 * r, -ax, -ax, -ax)
			_tri(st, b, b + n1 * r, b + n0 * r, ax, ax, ax)


## 一段环形的管子（栏杆扶手）：沿半径 rr、高 y 的圆弧扫一个圆截面
func _arc_tube(st: SurfaceTool, rr: float, y: float, a0: float, a1: float, tr: float, segs: int) -> void:
	var sides := 8
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
			var p00 := _pol(rr, t0, y) + n00 * tr
			var p01 := _pol(rr, t0, y) + n01 * tr
			var p10 := _pol(rr, t1, y) + n10 * tr
			var p11 := _pol(rr, t1, y) + n11 * tr
			_tri(st, p00, p10, p11, n00, n10, n11)
			_tri(st, p00, p11, p01, n00, n11, n01)


## 环形扇区的盒子（走台面、梁、踢脚板）：半径 r0~r1、高 y0~y1、方位 a0~a1
func _arc_box(st: SurfaceTool, r0: float, r1: float, y0: float, y1: float, a0: float, a1: float, segs: int) -> void:
	for s in segs:
		var t0 := lerpf(a0, a1, float(s) / segs)
		var t1 := lerpf(a0, a1, float(s + 1) / segs)
		var tm := (t0 + t1) * 0.5
		var radial := Vector3(cos(tm), 0, sin(tm))
		_quad(st, _pol(r0, t0, y1), _pol(r1, t0, y1), _pol(r1, t1, y1), _pol(r0, t1, y1), Vector3.UP)
		_quad(st, _pol(r0, t0, y0), _pol(r0, t1, y0), _pol(r1, t1, y0), _pol(r1, t0, y0), Vector3.DOWN)
		_quad(st, _pol(r0, t0, y0), _pol(r0, t0, y1), _pol(r0, t1, y1), _pol(r0, t1, y0), -radial)
		_quad(st, _pol(r1, t0, y0), _pol(r1, t1, y0), _pol(r1, t1, y1), _pol(r1, t0, y1), radial)
	for end in [[a0, -1.0], [a1, 1.0]]:
		var ea: float = end[0]
		var tn := Vector3(-sin(ea), 0, cos(ea)) * float(end[1])
		_quad(st, _pol(r0, ea, y0), _pol(r1, ea, y0), _pol(r1, ea, y1), _pol(r0, ea, y1), tn)


## 一块冰：二十面体细分两次，按噪声把顶点往里往外推，再压扁一点
func _chunk_mesh(size: float, sd: int) -> ArrayMesh:
	var sm := SphereMesh.new()
	sm.radius = size
	sm.height = size * 2.0
	sm.radial_segments = 10
	sm.rings = 6
	var arr := sm.get_mesh_arrays()
	var verts: PackedVector3Array = arr[Mesh.ARRAY_VERTEX]
	var nz := FastNoiseLite.new()
	nz.seed = 100 + sd
	nz.frequency = 2.2 / size
	var squash := Vector3(1.0, _rng.randf_range(0.5, 0.8), _rng.randf_range(0.7, 1.0))
	for i in verts.size():
		var v := verts[i]
		verts[i] = v * (1.0 + 0.45 * nz.get_noise_3dv(v)) * squash
	arr[Mesh.ARRAY_VERTEX] = verts
	arr[Mesh.ARRAY_NORMAL] = null
	arr[Mesh.ARRAY_TANGENT] = null
	var st := SurfaceTool.new()
	st.create_from_arrays(arr)
	st.generate_normals()
	return st.commit()
