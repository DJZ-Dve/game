extends Node3D
## 开场镜头 3（docs/design.md「八、开场」）：冰井里，冰震，沿井壁一圈圈的灯从井底往上一圈圈灭，黑暗涨上来吞掉镜头。
## 场景全部由脚本搭：冰壁（程序生成的冰，assets/shaders/ice_wall.gdshader）、每 12 米一圈的环形走台
## （格栅、工字钢托梁和斜撑、栏杆、舱壁灯、洗墙灯）、圈与圈之间的护笼爬梯（从这圈走台的检修口下到下一圈，
## 两个方位交替）、每圈冰壁上喷的深度标记、竖着贯穿整口井的加热管、升降机导轨和齿条、滑触线、电缆桥架
## （模型和材质在 scripts/shaft/shaft_kit.gd，和开局后的下井共用）。升降机的轿厢（scripts/shaft/lift_cab.gd）在镜头右下方
## 顺着导轨往下走，冰裂时安全器刹死，黑暗涨过它时一起断电（_lift_y、_lift_power）。
## 冰壁按两圈走台中间切成一段段，每圈走台、爬梯是单独的几个节点（灯具、灯罩每圈一个 MultiMesh），按离镜头远近分三档细节：
## 引擎按段、按圈剔除，每盏投影灯只画它照得到的那一两圈。
## 灯光：洗墙灯（走台底下贴着冰往下照）、照走台的短射程灯（前几圈，镜头附近两圈投影）、往井里照的灯（照空气、汽）；
## 更远几圈走台上的光斑、每圈灯照在身后冰上的那圈暖光在着色器里算（bar_grating、ice_wall），亮度跟着灯走。
## 坐标：井轴是 Y 轴，方位角 a = atan2(z, x)（和冰壁着色器一致）；第 i 圈走台面在 y = -i * RING_STEP（i 从 -1 开始，头顶还有一圈）。
## 声音：井里的空气、灯的嗡声、冰震、钢架呻吟、打火是 tools/gen_sfx.py 合成的，冰井的回声烘焙在 *_wet_* 里；
## 每圈灯的电闸是实录卷上 pyroomacoustics 算的冲激响应（relay_ring_*，见 _play_relay），按距离晚到（声速 343 m/s）。
## 机位：站在第 0 圈走台上扶着栏杆往下探（--cam=r,方位,高,看的点r,方位,高 可以临时换机位）；冰裂以后
##       推长焦看着井底，黑暗从井底往上涨，镜头按时间线算出的黑暗前沿一路拉回广角。
## 调试：--shot-t=秒  定在这个时刻（截图看某一刻；时间不再走）；--shot-run 从这个时刻开始照常往下走。
##       --lookdev[=弧度]  站在走台上近看井壁（调冰的材质用；数字是视线往旁边偏多少）
##       --dof=off  近景不虚；--fov=度  焦距定死（配 --cam 换机位看灯具、走台底面）
##       --near-lit=k  前几圈挂真的照走台的灯（默认 NEAR_LIT）；--shadows=off  关掉投影（比性能用）
##       --bench  量第 60~180 帧的平均帧间隔，打一行 BENCH 就退出
## 录像：tools/record.sh .tmp/shaft 36 --scene=shaft

# 冰井的尺寸、灯具、爬梯这些在 ShaftKit（scripts/shaft/shaft_kit.gd），这里只取用得着的
const R := ShaftKit.R
const RING_STEP := ShaftKit.RING_STEP
const WALK_IN := ShaftKit.WALK_IN
const LAMPS := ShaftKit.LAMPS
const LAMP_H := ShaftKit.LAMP_H
const LAMP_R := ShaftKit.LAMP_R
const DECK_LIGHT := ShaftKit.DECK_LIGHT
const WALL_GLOW := ShaftKit.WALL_GLOW
const PIPE_ANGLES := ShaftKit.PIPE_ANGLES
const PIPE_R := ShaftKit.PIPE_R
const JBOX_ANGLE := ShaftKit.JBOX_ANGLE
const LAMP_COLOR := ShaftKit.LAMP_COLOR
const LAMP_COOL := ShaftKit.LAMP_COOL
const RING_FIRST := -1         # 头顶那一圈
const RING_LAST := 49
const WALL_TOP := 24.0
const DEPTH := 615.0           # 冰壁往下建到这么深（再往下早就黑了）
const NEAR_LIT := 4            # 前几圈（k <= NEAR_LIT）的灯真的打光照走台；再远的走台上的光斑在格栅着色器里算
const G := 1.315               # 欧罗巴的重力
const SOUND_SPEED := 343.0
const CAM_A := 1.35            # 镜头站在走台的哪个方位
const BURST_PIPE := 2          # 冰裂时崩开的是哪根加热管（PIPE_ANGLES 里的第几根）、在第几圈走台底下（开场机位的右上方）
const BURST_RING := 2
const FOG_AIR := 0.012         # 井里空气的体积雾密度（平时）；冰震把冰屑、冰晶震进空气里，再加 FOG_QUAKE
const FOG_QUAKE := 0.012
const FOV0 := 50.0
# 投影灯多（镜头附近两圈的灯都投影）：阴影图集多分几格，4 × 2048² + 32 × 1024² + 64 × 512²；离开场景时还原成项目设置
const SHADOW_SUBDIV := [Viewport.SHADOW_ATLAS_QUADRANT_SUBDIV_4, Viewport.SHADOW_ATLAS_QUADRANT_SUBDIV_16,
	Viewport.SHADOW_ATLAS_QUADRANT_SUBDIV_16, Viewport.SHADOW_ATLAS_QUADRANT_SUBDIV_64]
const SHADOW_SUBDIV_DEFAULT := [Viewport.SHADOW_ATLAS_QUADRANT_SUBDIV_1, Viewport.SHADOW_ATLAS_QUADRANT_SUBDIV_4,
	Viewport.SHADOW_ATLAS_QUADRANT_SUBDIV_4, Viewport.SHADOW_ATLAS_QUADRANT_SUBDIV_16]

# 时间线（秒）
const FADE_IN := 2.5
const QUAKE_T := 7.0           # 冰震开始：低频轰鸣、掉冰屑、灯跟着电压往下沉
const CRACK_T := 10.4          # 冰裂的一声，掉冰块，墙上开始出裂纹
const BURST_T := 11.1          # 冰裂的那一下把一根加热管扯断（晚半拍：先震，再崩开，嘶声不被冰裂的轰响盖住）
const CASCADE_T := 12.6        # 井底那圈灯灭，然后一圈一圈往上
const CASCADE_DUR := 11.0      # 黑暗从井底涨到脚下那圈（k = 2）用多久。前沿离镜头的距离按对数匀速缩短：
                               # 远处几百米一眨眼就涨上来，越近越慢，最后几圈一圈一顿
const CAM_H := 1.55            # 镜头比第 0 圈走台面高多少
const NEAR_HOLD := 1.9         # 黑暗涨到脚下那圈就停一下：镜头这圈的灯跟着电压往下沉、挣扎，然后才灭
const PUSH_FRAME := 1.6        # 黑暗前沿涨近以后，那一圈最多占画面半高的 1/PUSH_FRAME（再近就拉回广角）
const PUSH_FOV := 10.0         # 推长焦推到多少度
# 升降机（scripts/shaft/lift_cab.gd）：开场时刚从第 1 圈走台下去，在画面右下方顺着导轨往下走；冰震时跟着晃、灯跟着电压沉；
# 冰裂那一下安全器刹死（顿一下、在缓冲弹簧上弹两下，齿条上崩出火星），挂在那儿；黑暗涨过它的时候和那一圈的灯一起断电
const LIFT_V := 4.5            # 往下走的速度（米/秒；20 公里单程一个多小时）
const LIFT_Y0 := -12.5         # 开场时轿厢地板面的高度
const LIFT_BRAKE_T := CRACK_T + 0.15
const LIFT_DECEL := 9.0        # 安全器刹车的减速度

var t := 0.0
var _frozen := false
var _rings: Array[Dictionary] = []   # {y, die, flick, lens, lights: [Light3D], base: [float]}
var _events: Array = []              # [时刻, Callable]，按时刻排好
var _kit: ShaftKit                  # 冰井的模型和材质（scripts/shaft/shaft_kit.gd，和下井共用）
var _ice_mat: ShaderMaterial
var _wall_chunks: Array[Dictionary] = []   # 井壁的一段段：{node, top, bottom}
var _cam: Camera3D
var _cam_base: Transform3D
var _shake := FastNoiseLite.new()
var _fade: ColorRect
var _hum: AudioStreamPlayer
var _air: AudioStreamPlayer
var _quake_dust: GPUParticles3D
var _env: Environment
var _lookdev := DebugArgs.has("lookdev")
var _fixed_fov := DebugArgs.has("fov")   # --fov=度：焦距定死（换机位看细节用）
var _chunks: Array[Dictionary] = []  # {node, vel, spin}
var _rng := RandomNumberGenerator.new()
var _streams := {}
var _fov := FOV0
var _aim := Vector3.ZERO           # 镜头看着的点（推长焦时移到还亮着那一圈的中心）
var _aim0 := Vector3.ZERO
var _hum_lvl := 1.0
var _end_t := 0.0                  # 最后一盏灯灭的时刻
var _steam_noise: NoiseTexture3D
var _jets: Array[GPUParticles3D] = []   # 崩开的管子往外喷的汽（芯 + 外面一团）
var _jet_cloud: ShaderMaterial     # 喷出来以后在那一片积起来的一团
var _burst_at := Vector3.ZERO
var _puff_tex: ImageTexture
var _bench := Vector3(0, 0, -1)    # --bench：x = 开始量的时刻（微秒）；z < 0 = 不量
var _bench_n := 0
var _lift: LiftCab
var _lift_die := 0.0               # 升降机断电的时刻


func _ready() -> void:
	_rng.seed = 1998
	_shake.seed = 3
	_shake.frequency = 1.0
	if DebugArgs.has("shot-t"):
		t = float(DebugArgs.get_arg("shot-t"))
		_frozen = not DebugArgs.has("shot-run")
	# 冰的次表面散射：半径调大，灯照到冰上光会渗开一圈（离开场景时调回默认值）
	RenderingServer.sub_surface_scattering_set_scale(0.06, 0.02)
	_shadow_atlas(SHADOW_SUBDIV)
	_build_environment()
	_kit = ShaftKit.new()
	_build_wall()
	_build_verticals()
	_build_rings()
	_build_lift()
	_build_particles()
	_build_steam()
	_build_camera()
	_build_overlay()
	_build_audio()
	_schedule()
	_update(0.0)
	if DebugArgs.has("bench"):
		_bench = Vector3.ZERO   # --bench：量第 60~180 帧的平均帧间隔，打一行 BENCH 就退出


func _exit_tree() -> void:
	RenderingServer.sub_surface_scattering_set_scale(0.05, 0.01)
	_shadow_atlas(SHADOW_SUBDIV_DEFAULT)


## 阴影图集四个象限各分几格（Viewport.SHADOW_ATLAS_QUADRANT_SUBDIV_*）
func _shadow_atlas(subdiv: Array) -> void:
	for q in 4:
		get_viewport().set_positional_shadow_atlas_quadrant_subdiv(q, subdiv[q])


# ---------------------------------------------------------------------------- 时间线
func _process(delta: float) -> void:
	if _bench.z >= 0.0:
		_bench_frame()
	if not _frozen:
		t += delta
	while not _events.is_empty() and _events[0][0] <= t:
		var ev: Array = _events.pop_front()
		(ev[1] as Callable).call()
	_update(delta)


func _bench_frame() -> void:
	# Mac（Metal）上量不出 GPU 时间：量实际的帧间隔（这个场景是卡在 GPU 上的，帧间隔基本就是 GPU 时间）
	_bench_n += 1
	if _bench_n == 60:
		_bench.x = Time.get_ticks_usec()
	elif _bench_n == 180:
		var ms := (Time.get_ticks_usec() - _bench.x) / 1000.0 / 120.0
		print("BENCH 帧间隔 %.2f ms（%.1f fps），%d 盏灯，%d 盏投影" % [ms, 1000.0 / ms,
			find_children("*", "Light3D", false, false).size(),
			find_children("*", "Light3D", false, false).filter(func(l: Light3D) -> bool: return l.shadow_enabled).size()])
		get_tree().quit()


## 冰震的强度（0~1，冰裂那一下冲到 2）
func _quake(at: float) -> float:
	var q := smoothstep(QUAKE_T, QUAKE_T + 3.0, at) * (1.0 - smoothstep(CRACK_T + 7.0, CRACK_T + 17.0, at))
	if at > CRACK_T:
		q += 1.1 * exp(-(at - CRACK_T) / 0.9)
	return q


## 第 k 圈第 j 盏灯此刻的亮度（x）和灯丝的余辉（y）
func _lamp_power(k: int, j: int, at: float) -> Vector2:
	var lamp: Dictionary = _rings[k].lamps[j]
	if lamp.dead:
		return Vector2.ZERO
	var die: float = lamp.die
	var flick: float = lamp.flick
	if at >= die:
		return Vector2(0.0, exp(-(at - die) / 0.35))
	var p := 1.0
	if lamp.faulty:
		# 接触不良：大部分时间亮着，隔一阵子“噗噗”掉两下
		var nz := _shake.get_noise_2d(at * 3.5, float(lamp.idx) * 1.7)
		if nz < -0.18:
			p = 0.04 if fposmod(at * 17.0 + float(lamp.idx), 1.0) < 0.6 else 0.6
	var q := _quake(at)
	if q > 0.0:
		# 电压跟着往下沉、乱跳（整口井一起，各圈各盏差一点点）
		p -= 0.22 * q * (0.5 + 0.5 * _shake.get_noise_2d(at * 6.0, float(k) * 3.1 + float(j) * 0.7))
	var strain: float = lamp.strain
	if at >= strain and at < die - flick:
		# 黑暗停在脚下的那一会儿：电压一点点塌下去，时不时整个掉一下又挣回来
		var s := (at - strain) / maxf(die - flick - strain, 0.01)
		p *= 1.0 - 0.6 * s * s
		if _shake.get_noise_2d(at * 7.0, float(k) * 5.3 + 40.0) < -0.3 + 0.25 * s:
			p *= 0.12
	if at >= die - flick:
		# 要灭之前：一阵乱闪（每秒 20 来次，亮灭随机），最后一下电弧闪得比平时还亮
		var slot := floori(at * 22.0)
		var h := fposmod(sin(float(slot) * 12.9898 + float(k) * 78.233 + float(j) * 37.719) * 43758.5453, 1.0)
		p *= 0.08 if h < 0.45 else 0.9
		if at > die - 0.05:
			p = 1.7
	return Vector2(clampf(p, 0.0, 1.8), 0.0)


## 黑暗前沿此刻离镜头多远（米）：从井底那圈开始，按对数匀速往上，到脚下那圈（k = 2）为止
func _front_dist(at: float) -> float:
	var f := clampf((at - CASCADE_T) / CASCADE_DUR, 0.0, 1.0)
	return _d_bottom() * pow(_d_near() / _d_bottom(), f)


func _d_bottom() -> float:
	return CAM_H + float(RING_LAST) * RING_STEP


func _d_near() -> float:
	return CAM_H + RING_STEP


func _update(delta: float) -> void:
	# 灯
	for k in _rings.size():
		var ring: Dictionary = _rings[k]
		var lamps: Array = ring.lamps
		var pw: Array[Vector2] = []
		var avg := 0.0
		var globes: MultiMesh = ring.globes
		for j in lamps.size():
			var pe := _lamp_power(k, j, t)
			pw.append(pe)
			avg += pe.x + 0.02 * pe.y
			globes.set_instance_custom_data(j, Color(pe.x, pe.y, lamps[j].tint, 0))
		avg /= lamps.size()
		ring.avg = avg
		if ring.wall:
			(ring.wall as GeometryInstance3D).set_instance_shader_parameter("ring_power", avg * WALL_GLOW)
		if ring.pool:
			# 远处这圈没挂真灯：格栅上的光斑跟着这圈灯的平均亮度走；越远越淡（井里的空气、冰晶把远处压暗，
			# 深处只剩一圈圈灯点）
			(ring.grating as GeometryInstance3D).set_instance_shader_parameter("pool_power",
				avg * DECK_LIGHT * 0.5 * exp(-maxf(k - 6.0, 0.0) / 9.0))
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
	var lean := smoothstep(0.0, 16.0, t) * 0.28
	var xf := _cam_base
	xf.origin += -Vector3(_cam_base.origin.x, 0, _cam_base.origin.z).normalized() * lean + Vector3(0, -lean * 0.4, 0)
	# 冰裂以后镜头推长焦、看着井轴的深处（一圈套一圈的灯像隧道，没进雾里的黑暗在画面正中）；灯从井底往上灭，
	# 黑暗从画面中间往外一圈圈涨出来、越涨越大；涨到占满大半个画面以后焦距跟着拉回来（黑洞不再变大，
	# 外面那圈亮的还看得见），最后几十米回到广角、看的点回到井壁上的构图点，剩下几圈直接冲到脚下。
	# 前沿的位置直接由时间线算（_front_dist），不靠跟随：远处涨得飞快，跟随总是落后
	var push := smoothstep(BURST_T + 0.9, CASCADE_T + 2.8, t)   # 先让人看清管子崩开
	push = push * push * (3.0 - 2.0 * push)
	var front := CAM_H - _front_dist(t)
	var dist := xf.origin.y - front
	var tele := clampf(2.0 * rad_to_deg(atan(R * PUSH_FRAME / dist)), PUSH_FOV, FOV0)
	_fov = exp(lerpf(log(FOV0), log(tele), push))
	var chase := push * smoothstep(0.0, 1.0, log(FOV0 / tele) / log(FOV0 / 16.0))
	_aim = _aim0.lerp(Vector3(0.0, front, 0.0), chase)
	xf.basis = Basis.looking_at(_aim - xf.origin, _cam_base.basis.y)  # 几乎正对下方：拿原来的“上”当参考，免得滚转乱跳
	if not _lookdev and not _fixed_fov:
		_cam.fov = _fov
	var zoom := _fov / FOV0
	var hand := (0.003 + 0.012 * q) * zoom
	var shake_pos := 0.006 + 0.03 * q
	xf.basis = xf.basis * Basis.from_euler(Vector3(
		_shake.get_noise_2d(t * 0.7, 1.0) * hand + _shake.get_noise_2d(t * 9.0, 5.0) * 0.006 * q * zoom,
		_shake.get_noise_2d(t * 0.6, 2.0) * hand + _shake.get_noise_2d(t * 8.0, 6.0) * 0.006 * q * zoom,
		_shake.get_noise_2d(t * 0.5, 3.0) * hand * 0.5))
	xf.origin += Vector3(_shake.get_noise_2d(t * 11.0, 7.0), _shake.get_noise_2d(t * 10.0, 8.0),
		_shake.get_noise_2d(t * 12.0, 9.0)) * shake_pos * minf(q, 1.0)
	_cam.transform = _cam_base if _lookdev else xf
	# 身边的灯灭了以后眼睛慢慢适应黑暗：曝光往上抬，下面远处的灯显得更亮、光晕更大
	_env.tonemap_exposure = 1.0 + 0.9 * smoothstep(_end_t, _end_t + 5.0, t)
	# 黑场淡入
	_fade.color.a = 1.0 - smoothstep(0.0, FADE_IN, t)
	# 空气：冰震把冰屑、冰晶震进空气里，低重力下好久落不下来
	_env.volumetric_fog_density = FOG_AIR + FOG_QUAKE * smoothstep(QUAKE_T, CRACK_T + 3.0, t)
	# 崩开的管子：先“砰”一大股，然后一直往外喷，压力慢慢掉；喷出来的汽在那一片越积越多
	var since := t - BURST_T
	for jp in _jets:
		jp.emitting = since >= 0.0   # 按时刻算，不排进事件里：--shot-t 跳过冰裂那一刻时也得接着喷
		jp.amount_ratio = 0.35 + 0.65 * exp(-maxf(since, 0.0) / 2.5)
	_jet_cloud.set_shader_parameter("amount", smoothstep(0.0, 6.0, since))
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
	_env.ambient_light_energy = 0.03 * near / nsum
	_hum.pitch_scale = 1.0 - 0.03 * minf(q, 1.0)
	_update_lift(q)
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
				c.rest = true   # 落到走台上不出声（冰砸铁格栅的声音合成、找实录都不像，2026-10-12 决定不要）


func _at(when: float, fn: Callable) -> void:
	if when < t:   # --shot-t 跳过去的那些声音就不放了
		return
	_events.append([when, fn])


func _schedule() -> void:
	_at(QUAKE_T, _play2d.bind("ice_boom_0", -1.0, 1.0, -8.0))
	_at(QUAKE_T, func() -> void: _quake_dust.emitting = true)
	_at(QUAKE_T + 2.2, _play2d.bind("steel_groan_0", -9.0, 0.85))
	_at(CRACK_T + 0.15, _play2d.bind("ice_boom_1", -5.0, 1.15, -8.0))
	_at(CRACK_T + 3.1, _play2d.bind("steel_groan_1", -8.0, 0.8))
	# 管子崩开喷汽（按距离晚到；画面上的喷汽见 _build_steam）
	_at(BURST_T + _burst_at.distance_to(_cam_base.origin) / SOUND_SPEED,
		_play3d.bind("steam_burst", _burst_at, -2.0, 1.0, -5.0))
	_at(CRACK_T + 9.5, _play2d.bind("steel_groan_2", -12.0, 0.75))
	_at(CRACK_T + 14.0, func() -> void: _quake_dust.emitting = false)
	# 升降机的安全器刹死：小齿轮在齿条上崩出一把火星
	_at(LIFT_BRAKE_T, _sparks.bind(LiftCab.mount(R, 0.0, _lift_y(LIFT_BRAKE_T)) * Vector3(0.0, 0.7, LiftCab.OUT_Z + 0.12)))
	for i in 9:
		_at(CRACK_T + 0.3 + _rng.randf_range(0.0, 3.5), _drop_chunk)
	# 每圈灯灭：接触器断开的声音，按距离晚到；最近几圈接线箱打火
	for k in _rings.size():
		var ring: Dictionary = _rings[k]
		var jb := MeshKit.pol(R - 0.42, JBOX_ANGLE, float(ring.y) + 1.3)
		var delay := jb.distance_to(_cam_base.origin) / SOUND_SPEED
		_at(float(ring.die) + delay, _play_relay.bind(k, _rng.randf_range(0.96, 1.04)))
		if k < 4:
			_at(float(ring.die), _sparks.bind(jb))
			_at(float(ring.die) + delay, _play3d.bind("spark_crackle_%d" % (k % 2), jb, -4.0, 1.0))
	# 全黑以后：冰还在挤，钢架呻吟，最后一声闷响
	var end := _end_t
	_at(end + 1.2, _play2d.bind("steel_groan_0", -16.0, 0.65))
	_at(end + 4.0, _play2d.bind("ice_boom_1", -5.0, 0.7, -6.0))
	_events.sort_custom(func(x: Array, y: Array) -> bool: return x[0] < y[0])


# ---------------------------------------------------------------------------- 升降机
func _build_lift() -> void:
	_lift = LiftCab.new()
	_lift.detail = 1
	add_child(_lift)
	# 断电的时刻：黑暗前沿涨过轿厢顶的时候（_front_dist 反过来算，和每圈的灯一样）
	var dk := CAM_H - (_lift_y(LIFT_BRAKE_T + 5.0) + LiftCab.ROOF)
	_lift_die = CASCADE_T + CASCADE_DUR * log(_d_bottom() / dk) / log(_d_bottom() / _d_near())


## 轿厢地板面此刻的高度：匀速往下走 → 安全器刹死（减速 LIFT_DECEL）→ 在缓冲弹簧上弹两下
func _lift_y(at: float) -> float:
	if at < LIFT_BRAKE_T:
		return LIFT_Y0 - LIFT_V * at
	var stop := LIFT_V / LIFT_DECEL
	var y0 := LIFT_Y0 - LIFT_V * LIFT_BRAKE_T
	var tau := at - LIFT_BRAKE_T
	if tau < stop:
		return y0 - (LIFT_V * tau - 0.5 * LIFT_DECEL * tau * tau)
	var u := tau - stop
	return y0 - LIFT_V * stop * 0.5 - 0.06 * exp(-u / 0.45) * sin(TAU * 2.2 * u)


## 轿厢里的电：跟着井里的电压沉、乱跳；刹死那一下猛地一暗（接触器被震开又合上）；断电前一阵乱闪
func _lift_power(at: float) -> float:
	if at >= _lift_die:
		return 0.0
	var p := 1.0
	var q := _quake(at)
	if q > 0.0:
		p -= 0.22 * q * (0.5 + 0.5 * _shake.get_noise_2d(at * 6.0, 77.0))
	var jolt := at - LIFT_BRAKE_T
	if jolt > 0.0 and jolt < 0.7:
		p *= 0.2 + 0.8 * smoothstep(0.08, 0.7, jolt)
	if at >= _lift_die - 0.45:
		var h := fposmod(sin(float(floori(at * 22.0)) * 12.9898 + 311.7) * 43758.5453, 1.0)
		p *= 0.08 if h < 0.45 else 0.9
	return clampf(p, 0.0, 1.6)


func _update_lift(q: float) -> void:
	var xf := LiftCab.mount(R, 0.0, _lift_y(t))
	# 冰震时在导轨上抖；刹死以后往井心那边点一下头（导靴和导轨之间那点间隙）
	var u := t - LIFT_BRAKE_T - LIFT_V / LIFT_DECEL
	var nod := 0.01 * exp(-u / 0.5) * sin(TAU * 1.6 * u) if u > 0.0 else 0.0
	var qq := minf(q, 1.0)
	xf.basis = xf.basis * Basis.from_euler(Vector3(nod + _shake.get_noise_2d(t * 9.0, 41.0) * 0.004 * qq, 0.0,
		_shake.get_noise_2d(t * 8.0, 43.0) * 0.003 * qq))
	xf.origin += xf.basis.x * _shake.get_noise_2d(t * 11.0, 45.0) * 0.015 * qq
	_lift.transform = xf
	_lift.set_power(_lift_power(t))


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
		# 回声已经烘焙进各个声音里了（*_wet），这里只给灯的嗡声和井里的空气加一点点空间感
		rv.wet = 0.1
		rv.dry = 1.0
		rv.predelay_msec = 20.0
		rv.predelay_feedback = 0.0
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


## 冰井里的回声是 tools/gen_sfx.py 按这口井的几何烘焙好的（<名字>_wet_<k>；只有一个变体的不带编号：<名字>_wet。
## 只有回声，RMS 和干声一样），这里跟着干声一起放；wet 是回声比干声低多少 dB（<= -60 不放回声）
func _wet_name(sfx: String) -> String:
	var i := sfx.rfind("_")
	if i >= 0 and sfx.substr(i + 1).is_valid_int():
		return sfx.substr(0, i) + "_wet" + sfx.substr(i)
	return sfx + "_wet"


func _play2d(sfx: String, vol_db: float, pitch: float, wet := -3.0) -> void:
	_player2d(sfx, vol_db, pitch)
	if wet > -60.0:
		_player2d(_wet_name(sfx), vol_db + wet, pitch)


func _player2d(sfx: String, vol_db: float, pitch: float) -> void:
	var p := AudioStreamPlayer.new()
	p.stream = _stream(sfx)
	p.volume_db = vol_db
	p.pitch_scale = pitch
	p.bus = "Shaft"
	add_child(p)
	p.play()
	p.finished.connect(p.queue_free)
	DebugArgs.log_sfx(sfx)


func _play3d(sfx: String, pos: Vector3, vol_db: float, pitch: float, wet := -3.0) -> void:
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
	if wet > -60.0:
		_player2d(_wet_name(sfx), vol_db + wet, pitch)


## 第 k 圈灯的电闸“咔嚓”：每一圈都有自己烘焙好的一条（relay_ring_<k>）——实录的大电闸卷上 pyroomacoustics
## 按冰井的真实尺寸算的、这一圈接线箱到镜头的冲激响应（tools/bake_shaft_rir.py）。近的、远的同一套算法，
## 响度、闷的程度、回声的多少都是算出来的、从近到远连续变化；直达声之前的传播时间由调用的地方按距离延迟
func _play_relay(k: int, pitch: float) -> void:
	_player2d("relay_ring_%d" % k, 0.0, pitch)


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
	# 远处渐渐没进黑暗里：冰井只建到 DEPTH，不加雾的话长焦看井底会看见一个硬边的黑圆口
	env.fog_enabled = true
	env.fog_mode = Environment.FOG_MODE_DEPTH
	env.fog_light_color = Color(0, 0, 0)
	env.fog_depth_begin = 200.0
	env.fog_depth_end = DEPTH - 20.0
	env.fog_depth_curve = 2.0
	env.volumetric_fog_enabled = true
	env.volumetric_fog_density = 0.2
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
	# 站在第 0 圈走台上，扶着栏杆往井里探出身子，斜着往下看：脚边的栏杆和灯是虚的前景，
	# 自己这一侧的井壁带着透视一路冲进下面的黑暗，一圈圈走台和灯排成往下缩的椭圆
	# --cam=r,方位,高,看的点r,方位,高  调机位用（极坐标，和 MeshKit.pol 一样）
	var c := [9.3, CAM_A, 1.55, 10.5, CAM_A + 2.25, -60.0]
	if DebugArgs.has("cam"):
		var parts := str(DebugArgs.get_arg("cam")).split(",")
		for i in mini(parts.size(), 6):
			c[i] = float(parts[i])
	var pos := MeshKit.pol(c[0], c[1], c[2])
	var look := MeshKit.pol(c[3], c[4], c[5])
	_cam = Camera3D.new()
	_cam.fov = float(DebugArgs.get_arg("fov", str(FOV0)))
	_cam.near = 0.03
	_cam.far = 1200.0
	if _lookdev:
		# 看样机位：站在第 0 圈走台上，离井壁一米多，斜着看墙（调冰的材质用）
		var off := float(DebugArgs.get_arg("lookdev", "0.12"))
		pos = MeshKit.pol(WALK_IN + 0.45, CAM_A, 1.65)
		look = MeshKit.pol(R, CAM_A + off, 0.9)
		_cam.fov = 62.0
	elif DebugArgs.get_arg("dof") != "off":   # --dof=off：近景不虚（--cam 换到别的机位看细节用）
		# 前景（栏杆、身边那盏灯）虚掉
		var ca := CameraAttributesPractical.new()
		ca.dof_blur_near_enabled = true
		ca.dof_blur_near_distance = 1.6
		ca.dof_blur_near_transition = 1.0
		ca.dof_blur_amount = 0.12
		_cam.attributes = ca
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
	motes.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
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
	_quake_dust.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
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
		# 别从头顶那圈下来的爬梯的护笼里掉出来，也别落在这圈的检修口上悬着（挪开不再抽随机数，后面的随机序列不变）
		for i in [RING_FIRST, RING_FIRST + 1]:
			var la := ShaftKit.ladder_a(i)
			if absf(wrapf(a - la, -PI, PI)) < 0.1:
				a = la + 0.1 * signf(wrapf(a - la, -PI, PI) + 1e-6)
		node.position = MeshKit.pol(R - 0.2, a, _rng.randf_range(3.5, 9.0))
		var inward := -Vector3(cos(a), 0, sin(a))
		var push := _rng.randf_range(1.6, 2.2) if through else _rng.randf_range(0.05, 0.2)
		c.vel = inward * push + Vector3(0, -_rng.randf_range(0.0, 0.4), 0)
		c.land = not through
		c.spin = _rng.randf_range(0.6, 2.4)
		c.spin_axis = Vector3(_rng.randf_range(-1, 1), _rng.randf_range(-1, 1), _rng.randf_range(-1, 1)).normalized()
		node.visible = true
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


# ---------------------------------------------------------------------------- 水汽：加热管冒的汽、冰裂时崩开的管子
func _build_steam() -> void:
	var fn := FastNoiseLite.new()
	fn.noise_type = FastNoiseLite.TYPE_SIMPLEX_SMOOTH
	fn.frequency = 0.05
	fn.fractal_octaves = 3
	_steam_noise = NoiseTexture3D.new()
	_steam_noise.width = 64
	_steam_noise.height = 64
	_steam_noise.depth = 64
	_steam_noise.seamless = true
	_steam_noise.normalize = true
	_steam_noise.noise = fn
	var shader := preload("res://assets/shaders/steam_fog.gdshader")
	# 加热管冒的汽：热管边上的湿空气往上走、碰到冷空气凝成一团团白汽，贴着管子往上飘、慢慢化开。
	# 用粒子不用体积雾：几十米外体积雾的格子有一米来宽，细细的一缕会被抹平
	var puff := _steam_puff_material(0.18)
	for a in PIPE_ANGLES:
		var wp := GPUParticles3D.new()
		wp.amount = 90
		wp.lifetime = 9.0
		wp.preprocess = 9.0
		wp.visibility_aabb = AABB(Vector3(-3, -40, -3), Vector3(6, 46, 6))
		var pm := ParticleProcessMaterial.new()
		pm.emission_shape = ParticleProcessMaterial.EMISSION_SHAPE_BOX
		pm.emission_box_extents = Vector3(0.1, 17.0, 0.1)
		pm.direction = Vector3(0, 1, 0)
		pm.spread = 20.0
		pm.initial_velocity_min = 0.15
		pm.initial_velocity_max = 0.4
		pm.gravity = Vector3(0, 0.03, 0)
		pm.turbulence_enabled = true
		pm.turbulence_noise_strength = 0.3
		pm.turbulence_noise_scale = 4.0
		pm.angle_min = -180.0
		pm.angle_max = 180.0
		pm.angular_velocity_min = -6.0
		pm.angular_velocity_max = 6.0
		pm.scale_min = 0.5
		pm.scale_max = 1.0
		pm.scale_curve = _curve_tex([Vector2(0.0, 0.3), Vector2(1.0, 1.0)])
		pm.color_ramp = _alpha_ramp([0.0, 0.25, 0.6, 1.0], [0.0, 1.0, 0.6, 0.0])
		wp.process_material = pm
		var q := QuadMesh.new()
		q.size = Vector2(1.4, 1.4)
		q.subdivide_width = 2
		q.subdivide_depth = 2
		q.material = puff
		wp.draw_pass_1 = q
		wp.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		# 贴着管子、在管子外侧（不然一半插在冰里）
		wp.position = MeshKit.pol(PIPE_R - 0.3, a, -20.0)
		add_child(wp)
	# 崩开的那根：冰裂把走台上面那道管卡扯开，一股汽横着往井里喷——正好在这圈灯照着的地方，底下是黑的走台
	var ba: float = PIPE_ANGLES[BURST_PIPE]
	_burst_at = MeshKit.pol(PIPE_R - 0.09, ba, -float(BURST_RING) * RING_STEP + 0.5)
	var inward := -Vector3(cos(ba), 0, sin(ba))
	var cloud := FogVolume.new()
	cloud.shape = RenderingServer.FOG_VOLUME_SHAPE_ELLIPSOID
	cloud.size = Vector3(7.0, 6.0, 7.0)
	cloud.position = _burst_at + inward * 3.0 + Vector3(0, 1.5, 0)
	_jet_cloud = ShaderMaterial.new()
	_jet_cloud.shader = shader
	_jet_cloud.set_shader_parameter("density", 0.5)
	_jet_cloud.set_shader_parameter("amount", 0.0)
	_jet_cloud.set_shader_parameter("noise", _steam_noise)
	cloud.material = _jet_cloud
	add_child(cloud)
	# 一股细的、快的芯（出管口十几米每秒，一秒多就被空气拖住、散开），外面裹着一大团慢慢翻滚、往上浮的汽
	var xf := Transform3D(Basis.looking_at(-inward, Vector3.UP), _burst_at + inward * 0.1)
	_jets.append(_jet_emitter(xf, 220, 1.3, Vector2(11.0, 15.0), 5.0, 0.0, 6.0, 1.4, 0.8,
		[Vector2(0.0, 0.15), Vector2(1.0, 1.0)]))
	_jets.append(_jet_emitter(xf, 200, 5.5, Vector2(3.0, 6.0), 1.0, 0.5, 18.0, 4.2, 0.65,
		[Vector2(0.0, 0.1), Vector2(0.3, 0.55), Vector2(1.0, 1.0)]))


## 喷汽的一个发射器：粒子系统的 +Z 朝井里
func _jet_emitter(xf: Transform3D, amount: int, life: float, vel: Vector2, damping: float, buoy: float,
		spread: float, size: float, alpha: float, grow: Array[Vector2]) -> GPUParticles3D:
	var jp := GPUParticles3D.new()
	jp.amount = amount
	jp.lifetime = life
	jp.emitting = false
	jp.local_coords = false
	jp.visibility_aabb = AABB(Vector3(-14, -8, -14), Vector3(28, 20, 28))
	var pm := ParticleProcessMaterial.new()
	pm.direction = Vector3(0, 0.1, 1)
	pm.spread = spread
	pm.initial_velocity_min = vel.x
	pm.initial_velocity_max = vel.y
	pm.damping_min = damping * 0.8
	pm.damping_max = damping * 1.2
	pm.gravity = Vector3(0, buoy, 0)   # 汽比冷空气轻，慢慢往上浮
	pm.turbulence_enabled = true
	pm.turbulence_noise_strength = 1.2
	pm.turbulence_noise_scale = 3.0
	pm.turbulence_influence_min = 0.03
	pm.turbulence_influence_max = 0.12
	pm.angle_min = -180.0
	pm.angle_max = 180.0
	pm.angular_velocity_min = -30.0
	pm.angular_velocity_max = 30.0
	pm.scale_min = 0.8
	pm.scale_max = 1.2
	pm.scale_curve = _curve_tex(grow)
	pm.color_ramp = _alpha_ramp([0.0, 0.06, 0.45, 1.0], [0.0, 1.0, 0.5, 0.0])
	jp.process_material = pm
	var q := QuadMesh.new()
	q.size = Vector2(size, size)
	q.material = _steam_puff_material(alpha, true)
	jp.draw_pass_1 = q
	jp.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	jp.transform = xf
	add_child(jp)
	return jp


## 一团汽的材质：灯在汽后面也能把它照亮（半透明），贴近井壁、走台的地方淡掉（不然切出一道硬边）。
## 加热管平时冒的汽逐顶点算光（面片细分 2×2）：一直在画面里，层层叠着的透明面片逐像素把几十盏灯算一遍太贵，
## 汽本来就是软的，看不出差别。断管喷的汽逐像素算（per_pixel）：它主要靠背光（灯在汽后面把它透亮），
## 逐顶点不算背光，整团发暗；只在喷的那几秒有开销
func _steam_puff_material(alpha: float, per_pixel := false) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	if not per_pixel:
		m.shading_mode = BaseMaterial3D.SHADING_MODE_PER_VERTEX
	m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	m.billboard_mode = BaseMaterial3D.BILLBOARD_PARTICLES
	m.vertex_color_use_as_albedo = true
	m.albedo_color = Color(0.9, 0.93, 0.96, alpha)
	m.albedo_texture = _puff_texture()
	m.roughness = 1.0
	m.specular_mode = BaseMaterial3D.SPECULAR_DISABLED
	m.diffuse_mode = BaseMaterial3D.DIFFUSE_LAMBERT_WRAP
	m.backlight_enabled = true
	m.backlight = Color(0.75, 0.75, 0.75)
	m.proximity_fade_enabled = true
	m.proximity_fade_distance = 0.8
	# 不接收阴影：汽是软的，看不出有没有影子；附近几十盏投影灯的阴影图每个像素都要采样，层层叠着的汽上这笔很贵
	m.disable_receive_shadows = true
	return m


func _curve_tex(pts: Array[Vector2]) -> CurveTexture:
	var c := Curve.new()
	for p in pts:
		c.add_point(p)
	var ct := CurveTexture.new()
	ct.curve = c
	return ct


## 只变透明度的颜色渐变（粒子一生里先浮现、再化开）
func _alpha_ramp(offsets: Array[float], alphas: Array[float]) -> GradientTexture1D:
	var g := Gradient.new()
	g.offsets = PackedFloat32Array(offsets)
	var cols := PackedColorArray()
	for a in alphas:
		cols.append(Color(1, 1, 1, a))
	g.colors = cols
	var gt := GradientTexture1D.new()
	gt.gradient = g
	return gt


## 一团汽的贴图：边缘发虚的圆，里面是一团团的噪声（白色，透明度在 alpha 里）
func _puff_texture() -> ImageTexture:
	if _puff_tex:
		return _puff_tex
	var n := FastNoiseLite.new()
	n.noise_type = FastNoiseLite.TYPE_SIMPLEX_SMOOTH
	n.frequency = 0.045
	n.fractal_octaves = 4
	var size := 128
	var img := Image.create(size, size, false, Image.FORMAT_RGBA8)
	for y in size:
		for x in size:
			var u := (float(x) + 0.5) / size * 2.0 - 1.0
			var v := (float(y) + 0.5) / size * 2.0 - 1.0
			var r := sqrt(u * u + v * v)
			var fall := clampf(1.0 - r, 0.0, 1.0)
			fall = fall * fall * (3.0 - 2.0 * fall)
			var c := clampf(0.5 + 0.8 * n.get_noise_2d(x, y), 0.0, 1.0)
			img.set_pixel(x, y, Color(1, 1, 1, clampf(fall * (0.35 + 0.9 * c) * fall, 0.0, 1.0)))
	_puff_tex = ImageTexture.create_from_image(img)
	return _puff_tex


# ---------------------------------------------------------------------------- 材质
# ---------------------------------------------------------------------------- 冰壁
func _build_wall() -> void:
	_ice_mat = _kit.ice_mat
	# 行距：镜头附近 25 厘米（节缝的台阶、贴着看的起伏），往下越来越疏
	var ys: Array[float] = []
	var y := WALL_TOP
	while y > -DEPTH:
		ys.append(y)
		y -= 0.25 if y > -64.0 else (1.0 if y > -200.0 else 2.5)
	ys.append(-DEPTH)
	# 井壁在两圈走台正中间切开，一段 12 米：引擎按段剔除，每盏投影灯只画它照得到的那一两段。
	# 冰壁不投影：灯都在井里，冰壁只会挡住它背后，那里什么都没有
	for chunk in _kit.wall_chunks(ys, Vector2i(RING_FIRST, RING_LAST)):
		var mi := MeshInstance3D.new()
		mi.mesh = chunk.mesh
		mi.material_override = _ice_mat
		mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		add_child(mi)
		_wall_chunks.append({"node": mi, "top": chunk.top, "bottom": chunk.bottom})


# ---------------------------------------------------------------------------- 竖着贯穿整口井的：加热管、电梯导轨、电缆桥架
## 竖着贯穿整口井的：加热管、升降机导轨和齿条、滑触线、电缆桥架（ShaftKit.verticals）
func _build_verticals() -> void:
	for m in _kit.verticals(WALL_TOP, -DEPTH):
		_add_mesh(m[0], m[1])


func _add_mesh(mesh: Mesh, mat: Material) -> MeshInstance3D:
	var mi := MeshInstance3D.new()
	mi.mesh = mesh
	mi.material_override = mat
	add_child(mi)
	return mi


# ---------------------------------------------------------------------------- 一圈走台 + 灯
## 每一圈走台是单独的几个节点（格栅、钢结构、扶手；灯具、灯罩每圈一个 MultiMesh）：引擎按圈剔除，
## 每盏投影灯只重画它照得到的那一两圈（以前整口井一个 MultiMesh，每盏投影灯都要把五十圈全画一遍）。
## 按离镜头远近分三档细节（镜头在第 0 圈，第 k 圈离镜头约 12k 米）：近处一圈 330 段、灯具带散热片和护罩；
## 远处 60 段也看不出折线（推长焦时远处会被放大，所以远档也不能太糙）。
func _build_rings() -> void:
	var ys: Array[float] = []
	for i in range(RING_FIRST, RING_LAST + 1):
		ys.append(-i * RING_STEP)
	# 格栅、扶手、爬梯、灯具每档细节一套；钢结构每档细节 × 检修口在哪（两个方位交替，最底下那圈没有）一套（ShaftKit）
	var spacing := ShaftKit.lamp_spacing()
	var lamp_a0 := ShaftKit.lamp_a0()
	var near_lit := int(DebugArgs.get_arg("near-lit", str(NEAR_LIT)))
	var shadows := DebugArgs.get_arg("shadows") != "off"
	for k in ys.size():
		var y := ys[k]
		var lod := 0 if k <= 2 else (1 if k <= 10 else 2)
		# 这圈的检修口（爬梯从这里下到下一圈）
		var hatch := ShaftKit.ladder_a(k + RING_FIRST) if k < ys.size() - 1 else -1.0
		var nodes: Array[MeshInstance3D] = []
		for i in 3:
			var mi := MeshInstance3D.new()
			mi.mesh = [_kit.grates[lod][0], _kit.steel(lod, hatch), _kit.grates[lod][1]][i]
			mi.material_override = [_kit.grate_mat, _kit.mat_steel, _kit.mat_rail][i]
			mi.position = Vector3(0, y, 0)
			add_child(mi)
			nodes.append(mi)
		if hatch >= 0.0:
			nodes[0].set_instance_shader_parameter("hatch_a", hatch)
			# 这圈下到下一圈的爬梯：单独一个节点（一样按圈剔除、按档细节），网格是方位角 0 处的，转过去
			var lad := MeshInstance3D.new()
			lad.mesh = _kit.ladders[lod]
			lad.transform = Transform3D(Basis(Vector3.UP, -hatch), Vector3(0, y, 0))
			add_child(lad)
		# 从井底往上灭：黑暗前沿涨过哪一圈，那一圈就灭（_front_dist 反过来算）；涨到脚下那圈（k = 2）停一下，
		# 镜头这圈（k = 1）挣扎 NEAR_HOLD 秒才灭，头顶那圈（k = 0）紧跟着灭，全黑
		var dk := CAM_H - ys[maxi(k, 2)]
		var die := CASCADE_T + CASCADE_DUR * log(_d_bottom() / dk) / log(_d_bottom() / _d_near())
		die += _rng.randf_range(-0.04, 0.04) * float(k > 2)
		var hold := 0.0
		if k <= 1:
			hold = NEAR_HOLD
			die += NEAR_HOLD + (0.7 if k == 0 else 0.0)
		# 一圈里也是一盏接一盏灭：从随机的一盏开始，顺着圈扫过去（灯多了，扫得快一点）
		var first := _rng.randi_range(0, LAMPS - 1)
		var sweep := _rng.randf_range(0.012, 0.02) * (2.5 if k == 1 else 1.0)
		# 每圈的灯整体错开一个随机角度、每盏再偏一点（不然推长焦时各圈的灯上下对齐，排成一条条放射线）
		var ring_off := _rng.randf()
		var fix_mm := MultiMesh.new()
		fix_mm.transform_format = MultiMesh.TRANSFORM_3D
		fix_mm.mesh = _kit.fixtures[0 if k <= 3 else 1]
		fix_mm.instance_count = LAMPS
		var wash_mm := MultiMesh.new()
		wash_mm.transform_format = MultiMesh.TRANSFORM_3D
		wash_mm.mesh = _kit.wash
		wash_mm.instance_count = LAMPS / 2
		# 灯罩：每个实例的自定义数据 r = 亮度、g = 余辉、b = 色温（lamp_lens.gdshader）
		var globes := MultiMesh.new()
		globes.transform_format = MultiMesh.TRANSFORM_3D
		globes.use_custom_data = true
		globes.mesh = _kit.globes[0 if k <= 3 else 1]
		globes.instance_count = LAMPS
		var lamps: Array[Dictionary] = []
		for j in LAMPS:
			var la := lamp_a0 + spacing * (j + ring_off + _rng.randf_range(-0.12, 0.12))
			var rot := Basis(Vector3.UP, -la)
			fix_mm.set_instance_transform(j, Transform3D(rot, Vector3(0, y, 0)))
			if j % 2 == 0:
				wash_mm.set_instance_transform(j / 2, Transform3D(Basis(Vector3.UP, -ShaftKit.wash_a(la, hatch)), Vector3(0, y, 0)))
			var p := MeshKit.pol(LAMP_R, la, LAMP_H + y)
			# 老设施：少数几盏早就坏了（罩子碎了，灯座沿上只剩一圈碴子），几盏接触不良一直在跳，换过的几盏是冷白的 LED
			var dead := _rng.randf() < 0.05 and k != 1
			var faulty := not dead and _rng.randf() < 0.04
			var tint := 1.0 if _rng.randf() < 0.12 else _rng.randf_range(-0.15, 0.15)
			globes.set_instance_transform(j, Transform3D(Basis(), p) if not dead
				else Transform3D(Basis().scaled(Vector3(1.05, 0.2, 1.05)), p + Vector3(0, 0.072, 0)))
			globes.set_instance_custom_data(j, Color(0 if dead else 1, 0, maxf(tint, 0.0), 0))
			var order := (j - first + LAMPS) % LAMPS
			var lamp_die := die + order * sweep
			_end_t = maxf(_end_t, lamp_die)
			lamps.append({"idx": k * LAMPS + j, "a": la, "pos": p, "dead": dead, "faulty": faulty, "tint": maxf(tint, 0.0),
				"die": lamp_die, "flick": _rng.randf_range(0.15, 0.5), "strain": lamp_die - hold - 0.4 if hold > 0.0 else INF})
		for mm_ in [fix_mm, wash_mm]:
			var mmi := MultiMeshInstance3D.new()
			mmi.multimesh = mm_
			mmi.material_override = _kit.mat_lamp
			# 灯具不投影：照走台的那盏光从罩子中心发出来，灯座就在它正下方，投影的话脚下整片都被灯座挡黑
			if mm_ == fix_mm:
				mmi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
			add_child(mmi)
		var gi := MultiMeshInstance3D.new()
		gi.multimesh = globes
		gi.material_override = _kit.lens_mat
		gi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		add_child(gi)
		var lights: Array[Light3D] = []
		var lamp_of: Array[int] = []   # 每个光源跟着哪盏灯（-1 = 跟着这一圈的平均亮度）
		var base: Array[float] = []
		if k <= 5:
			for j in LAMPS:
				var lamp: Dictionary = lamps[j]
				if lamp.dead:
					continue
				var la: float = lamp.a
				var col := LAMP_COLOR.lerp(LAMP_COOL, lamp.tint)
				var radial := Vector3(cos(la), 0, sin(la))
				if j % 2 == 0:
					# 洗墙灯：朝下、略往井壁偏，光贴着冰面扫下去——切削纹、台阶、崩口全靠这道掠射光显出来。
					# 挂在两根斜撑正中间（不然斜撑在冰上拖出一道长影子）；光斑边缘软（冰把光散开），每盏亮度、朝向差一点
					var wa := ShaftKit.wash_a(la, hatch)
					var wr := Vector3(cos(wa), 0, sin(wa))
					var wl := SpotLight3D.new()
					var wdir := (wr * (0.22 + 0.06 * ShaftKit.hash3(k, j, 1)) + Vector3.DOWN).normalized()
					wl.transform = Transform3D(Basis.looking_at(wdir, wr), MeshKit.pol(R - 0.55, wa, y - 0.58))
					wl.light_color = col
					wl.spot_range = 15.0
					wl.spot_angle = 58.0
					wl.spot_attenuation = 1.2
					wl.spot_angle_attenuation = 0.55
					wl.light_size = 0.15
					wl.shadow_enabled = shadows and k <= 2 and j % 4 == 0
					wl.light_volumetric_fog_energy = 0.8
					add_child(wl)
					lights.append(wl)
					lamp_of.append(j)
					base.append(7.0 * (0.8 + 0.35 * ShaftKit.hash3(k, j, 2)))   # 光锥放宽、边缘放软以后，总光量和原来差不多
				if k <= near_lit and j % 2 == 1:
					# 灯罩往下照：只管脚下这一片格栅、扶手、踢脚板（射程短：不然光穿过格栅的孔，把底下的冰壁也照亮了）；
					# 身后冰上的那圈光在 ice_wall.gdshader 里算
					var sl := SpotLight3D.new()
					var dir := (Vector3.DOWN - radial * 0.35).normalized()
					sl.transform = Transform3D(Basis.looking_at(dir, radial), lamp.pos)
					sl.light_color = col
					sl.spot_range = 3.2
					sl.spot_angle = 80.0
					sl.spot_attenuation = 1.6
					sl.spot_angle_attenuation = 0.7
					sl.light_size = 0.12
					sl.shadow_enabled = shadows and (k == 1 or k == 2)
					sl.shadow_blur = 1.5
					sl.light_volumetric_fog_energy = 1.4
					add_child(sl)
					lights.append(sl)
					lamp_of.append(j)
					base.append(DECK_LIGHT)
				if j % 4 == 1:
					# 往井里照的光（照亮空气里的体积雾、冰晶、汽，也照到对面往下几圈的走台）：射程长，不投影
					var vl := SpotLight3D.new()
					var vdir := (-radial + Vector3(0, -0.45, 0)).normalized()
					vl.transform = Transform3D(Basis.looking_at(vdir, Vector3.UP), lamp.pos)
					vl.light_color = col
					vl.spot_range = 13.0
					vl.spot_angle = 70.0
					vl.spot_attenuation = 1.4
					vl.spot_angle_attenuation = 0.7
					vl.light_size = 0.09
					vl.light_volumetric_fog_energy = 1.6
					add_child(vl)
					lights.append(vl)
					lamp_of.append(j)
					base.append(2.0)
		elif k <= 16:
			# 中间几圈：每四盏灯一个洗墙灯，井壁上照出一块一块的光，两圈之间是暗的
			for j in range(2, LAMPS, 4):   # 离电梯导轨那道缺口远一点（不然缺口两头的走台断面被照成一串亮点）
				var la := ShaftKit.off_hatch(lamps[j].a, hatch)
				var radial := Vector3(cos(la), 0, sin(la))
				var wl := SpotLight3D.new()
				var wdir := (radial * 0.3 + Vector3.DOWN).normalized()
				wl.transform = Transform3D(Basis.looking_at(wdir, radial), MeshKit.pol(R - 0.7, la, y - 0.58))
				wl.light_color = LAMP_COLOR
				wl.spot_range = 16.0
				wl.spot_angle = 60.0
				wl.spot_attenuation = 1.2
				wl.spot_angle_attenuation = 0.6
				wl.light_volumetric_fog_energy = 1.0
				add_child(wl)
				lights.append(wl)
				lamp_of.append(-1)
				base.append(23.0)
		else:
			# 远处：每圈三盏贴着井壁的全向灯，远看是一圈光带
			for j in [4, 12, 20]:
				var la := ShaftKit.off_hatch(lamps[j].a, hatch)
				var ol := OmniLight3D.new()
				ol.position = MeshKit.pol(R - 1.1, la, y - 2.0)
				ol.light_color = LAMP_COLOR
				ol.omni_range = 16.0
				ol.omni_attenuation = 1.2
				ol.light_volumetric_fog_energy = 1.2
				add_child(ol)
				lights.append(ol)
				lamp_of.append(-1)
				base.append(30.0)
		var pool := k > near_lit
		if pool:
			nodes[0].set_instance_shader_parameter("ring_phase", ring_off)
		# 这圈灯照在身后冰上的那圈光（ice_wall.gdshader）：找到这圈所在的那段井壁
		var wall: MeshInstance3D = null
		for ch in _wall_chunks:
			if y < float(ch.top) and y > float(ch.bottom):
				wall = ch.node
				wall.set_instance_shader_parameter("ring_y", y)
				wall.set_instance_shader_parameter("ring_phase", ring_off)
		_rings.append({"y": y, "die": die, "lamps": lamps, "lights": lights, "lamp_of": lamp_of, "base": base, "avg": 1.0,
			"globes": globes, "grating": nodes[0], "pool": pool, "wall": wall})


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
