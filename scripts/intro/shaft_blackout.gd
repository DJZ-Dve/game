extends Node3D
## 开场镜头 3（docs/design.md「八、开场」）：冰井里，冰震，沿井壁一圈圈的灯从井底往上一圈圈灭，黑暗涨上来吞掉镜头。
## 场景全部由脚本搭：冰壁（程序生成的冰，assets/shaders/ice_wall.gdshader）、每 12 米一圈的环形走台
## （格栅、工字钢托梁和斜撑、栏杆、舱壁灯、洗墙灯）、圈与圈之间的护笼爬梯（从这圈走台的检修口下到下一圈，
## 两个方位交替）、每圈冰壁上喷的深度标记、竖着贯穿整口井的加热管、电梯导轨、电缆桥架。
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
const LAMP_H := 1.24           # 灯罩中心在走台面上方多高（坐在从扶手伸出来的横臂上）
const LAMP_R := WALK_IN - 0.17 # 灯罩中心的半径（扶手内侧，悬在井里）
const RAIL_R := WALK_IN + 0.05 # 栏杆立柱、扶手的半径
const RAIL_TOP := 1.08
const NEAR_LIT := 4            # 前几圈（k <= NEAR_LIT）的灯真的打光照走台；再远的走台上的光斑在格栅着色器里算
const DECK_LIGHT := 2.6        # 照走台的那盏灯的亮度
const WALL_GLOW := 0.45        # 灯照在身后冰上的那圈光（ice_wall.gdshader 里算）
const PIPE_ANGLES := [1.05, 2.62, 5.06]
const PIPE_R := R + 0.01       # 加热管贴着井壁走，嵌在它自己化出来的浅槽里
const TRAY_ANGLE := 3.9
const JBOX_ANGLE := 3.66       # 每圈的接线箱（灯的电从这里接）
# 护笼爬梯：第 n 圈走台到第 n+1 圈，在两根托梁中间的一格里（第几格见 _bay_a；偶数圈、奇数圈交替，隔四格、5.2 米，
# 上一段梯子掉下来的人落在下一圈的走台上，不会顺着检修口一路掉到底）。避开管子、桥架、接线箱、电梯导轨
const LADDER_BAYS := [34, 38]
const LADDER_OFF := 0.2        # 踏棍中心离冰面多远
const CAGE_FROM := 2.2         # 护笼从下面那圈走台面以上多高开始
const HATCH_W := 0.42          # 检修口半宽（切向）
const HATCH_IN := R - 0.94     # 检修口靠井轴那条边的半径（从这里到井壁都是口子）
# 每圈的深度标记（「R07 / -84 m」，字高 0.42 米、一条三四米长：坐升降机的人隔着井也看得清）喷在哪几个方位角
# （一条字的正中）：三条在开场镜头左边、上边、右边看得见的地方，一条在这圈两段爬梯正中间（4.458，两格的中点；
# 爬上来、下去的人都看得见）；都避开管子、桥架、接线箱、爬梯。字的大小、样子在 ice_wall.gdshader 里
const LABEL_ANGLES := [2.06, 3.142, 4.458, 5.62]
const LAMP_COLOR := Color(1.0, 0.86, 0.68)   # 老的卤素灯
const LAMP_COOL := Color(0.86, 0.93, 1.0)     # 后来换上的 LED
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

var t := 0.0
var _frozen := false
var _rings: Array[Dictionary] = []   # {y, die, flick, lens, lights: [Light3D], base: [float]}
var _events: Array = []              # [时刻, Callable]，按时刻排好
var _ice_mat: ShaderMaterial
var _mat_steel: ShaderMaterial     # 冰井里钢件的材质变体（_build_materials）
var _mat_rail: ShaderMaterial
var _mat_lamp: ShaderMaterial
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
	_build_materials()
	_build_wall()
	_build_verticals()
	_build_rings()
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
	for i in 9:
		_at(CRACK_T + 0.3 + _rng.randf_range(0.0, 3.5), _drop_chunk)
	# 每圈灯灭：接触器断开的声音，按距离晚到；最近几圈接线箱打火
	for k in _rings.size():
		var ring: Dictionary = _rings[k]
		var jb := _pol(R - 0.42, JBOX_ANGLE, float(ring.y) + 1.3)
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
	# --cam=r,方位,高,看的点r,方位,高  调机位用（极坐标，和 _pol 一样）
	var c := [9.3, CAM_A, 1.55, 10.5, CAM_A + 2.25, -60.0]
	if DebugArgs.has("cam"):
		var parts := str(DebugArgs.get_arg("cam")).split(",")
		for i in mini(parts.size(), 6):
			c[i] = float(parts[i])
	var pos := _pol(c[0], c[1], c[2])
	var look := _pol(c[3], c[4], c[5])
	_cam = Camera3D.new()
	_cam.fov = float(DebugArgs.get_arg("fov", str(FOV0)))
	_cam.near = 0.03
	_cam.far = 1200.0
	if _lookdev:
		# 看样机位：站在第 0 圈走台上，离井壁一米多，斜着看墙（调冰的材质用）
		var off := float(DebugArgs.get_arg("lookdev", "0.12"))
		pos = _pol(WALK_IN + 0.45, CAM_A, 1.65)
		look = _pol(R, CAM_A + off, 0.9)
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
			var la := _ladder_a(i)
			if absf(wrapf(a - la, -PI, PI)) < 0.1:
				a = la + 0.1 * signf(wrapf(a - la, -PI, PI) + 1e-6)
		node.position = _pol(R - 0.2, a, _rng.randf_range(3.5, 9.0))
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
		wp.position = _pol(PIPE_R - 0.3, a, -20.0)
		add_child(wp)
	# 崩开的那根：冰裂把走台上面那道管卡扯开，一股汽横着往井里喷——正好在这圈灯照着的地方，底下是黑的走台
	var ba: float = PIPE_ANGLES[BURST_PIPE]
	_burst_at = _pol(PIPE_R - 0.09, ba, -float(BURST_RING) * RING_STEP + 0.5)
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
## 冰井里的钢件都是这里的变体（不改共用的 .tres）：漆面不给金属度，掉漆露出红丹、再露出钢；朝上的面结一层霜
func _build_materials() -> void:
	var chip: Texture2D = load("res://assets/third_party/ambientcg/PaintedMetal005/PaintedMetal005_2K-JPG_Opacity.jpg")
	var frost := Color(0.72, 0.78, 0.82)
	_mat_steel = load("res://assets/materials/M_SteelOld.tres").duplicate()
	_mat_steel.set_shader_parameter("paint_color", Color(0.3, 0.31, 0.3))
	_mat_steel.set_shader_parameter("paint_metallic", 0.0)
	_mat_steel.set_shader_parameter("paint_roughness", 0.62)
	_mat_steel.set_shader_parameter("primer_amount", 0.4)
	_mat_steel.set_shader_parameter("chip_tex", chip)
	_mat_steel.set_shader_parameter("chip_amount", 0.45)
	_mat_steel.set_shader_parameter("chip_scale", 3.0)
	_mat_steel.set_shader_parameter("chip_cover", 0.35)
	_mat_steel.set_shader_parameter("bare_rust", 0.8)
	_mat_steel.set_shader_parameter("dust_color", frost)
	_mat_steel.set_shader_parameter("dust_amount", 0.35)
	_mat_steel.set_shader_parameter("floor_dirt", 0.0)
	# 扶手：安全黄，旧了发脏；顶上被手磨出钢来（顶点色 R 按朝上的程度给），一段段磕掉漆
	_mat_rail = load("res://assets/materials/M_Rail.tres").duplicate()
	_mat_rail.set_shader_parameter("paint_color", Color(0.72, 0.52, 0.08))
	_mat_rail.set_shader_parameter("paint_metallic", 0.0)
	_mat_rail.set_shader_parameter("paint_roughness", 0.55)
	_mat_rail.set_shader_parameter("paint_variation", 0.25)
	_mat_rail.set_shader_parameter("edge_wear", 1.0)
	_mat_rail.set_shader_parameter("primer_amount", 0.3)
	_mat_rail.set_shader_parameter("chip_tex", chip)
	_mat_rail.set_shader_parameter("chip_amount", 0.35)
	_mat_rail.set_shader_parameter("chip_scale", 4.0)
	_mat_rail.set_shader_parameter("chip_cover", 0.3)
	_mat_rail.set_shader_parameter("bare_rust", 0.6)
	_mat_rail.set_shader_parameter("bare_roughness", 0.3)
	_mat_rail.set_shader_parameter("dust_color", frost)
	_mat_rail.set_shader_parameter("dust_amount", 0.2)
	_mat_rail.set_shader_parameter("floor_dirt", 0.0)
	# 灯座：铸铝刷的灰绿漆
	_mat_lamp = _mat_steel.duplicate()
	_mat_lamp.set_shader_parameter("paint_color", Color(0.2, 0.24, 0.21))
	_mat_lamp.set_shader_parameter("chip_amount", 0.3)
	_mat_lamp.set_shader_parameter("dust_amount", 0.2)


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
	# 每圈的深度标记：模板字的距离场（tools/gen_stencil_glyphs.py），圈号、深度由着色器按每段井壁的 ring_y 算
	_ice_mat.set_shader_parameter("stencil_glyphs", preload("res://assets/textures/stencil_glyphs.png"))
	_ice_mat.set_shader_parameter("stencil_angles", Vector4(LABEL_ANGLES[0], LABEL_ANGLES[1], LABEL_ANGLES[2], LABEL_ANGLES[3]))
	_ice_mat.set_shader_parameter("ring_step", RING_STEP)
	# 井壁在两圈走台正中间切开，一段 12 米：引擎按段剔除，每盏投影灯只画它照得到的那一两段。
	# 冰壁不投影：灯都在井里，冰壁只会挡住它背后，那里什么都没有
	for chunk in _wall_meshes():
		var mi := MeshInstance3D.new()
		mi.mesh = chunk.mesh
		mi.material_override = _ice_mat
		mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		add_child(mi)
		_wall_chunks.append({"node": mi, "top": chunk.top, "bottom": chunk.bottom})


## 冰壁的半径起伏（热水钻出来的井：大块的鼓包凹坑 + 一圈圈的细波纹）
func _wall_r(n1: FastNoiseLite, n2: FastNoiseLite, a: float, y: float) -> float:
	var c := cos(a) * R
	var s := sin(a) * R
	# 每节掘进的半径差一点（刀盘每次重新对位的误差），节与节之间就是一道台阶
	var step := (fposmod(sin(floorf(y / LIFT) * 91.7) * 4375.85, 1.0) - 0.5) * 0.025
	var bump := 0.12 * n1.get_noise_3d(c, y * 0.6, s) + 0.03 * n2.get_noise_3d(c * 3.0, y * 2.0, s * 3.0) + step
	# 走台的托梁、斜撑锚进冰里的那一圈（走台面上 0.45 米到下面 1.45 米）：装的时候把冰壁修平了，锚板贴得严
	var rel := y - roundf(y / RING_STEP) * RING_STEP
	var band := smoothstep(-1.95, -1.45, rel) * (1.0 - smoothstep(0.45, 0.95, rel))
	# 爬梯背后竖着一条也修平了（支架的锚板贴得严）：这个高度是哪圈下去的那段梯子
	var li := floori(-y / RING_STEP)
	if li >= RING_FIRST and li < RING_LAST:
		band = maxf(band, 1.0 - smoothstep(0.45, 0.85, absf(wrapf(a - _ladder_a(li), -PI, PI)) * R))
	var r := R + bump * (1.0 - band)
	# 加热管把贴着它的冰化开又冻上：沿着管子一道浅槽（光滑透亮，见着色器的 wet）
	for pa in PIPE_ANGLES:
		var d := absf(wrapf(a - pa, -PI, PI)) * R
		r += 0.15 * exp(-d * d / 0.09)
	return r


## 冰壁的网格，按段切开（见 _build_wall）：[{mesh, top, bottom}]
func _wall_meshes() -> Array[Dictionary]:
	var n1 := FastNoiseLite.new()
	n1.seed = 7
	n1.frequency = 0.3
	n1.fractal_octaves = 3
	var n2 := FastNoiseLite.new()
	n2.seed = 11
	n2.frequency = 0.5
	var cols := 360
	# 行距：镜头附近 25 厘米（节缝的台阶、贴着看的起伏），往下越来越疏
	var ys: Array[float] = []
	var y := WALL_TOP
	while y > -DEPTH:
		ys.append(y)
		y -= 0.25 if y > -64.0 else (1.0 if y > -200.0 else 2.5)
	ys.append(-DEPTH)
	var w := cols + 1
	var pos: Array[Vector3] = []
	for yy in ys:
		for c in w:
			var a := TAU * c / cols
			pos.append(_pol(_wall_r(n1, n2, a, yy), a, yy))
	var nrm: Array[Vector3] = []
	for r in ys.size():
		for c in w:
			var p := pos[r * w + c]
			var pa := pos[r * w + (c + 1) % w] if c < cols else pos[r * w + 1]
			var pb := pos[mini(r + 1, ys.size() - 1) * w + c]
			var pc := pos[maxi(r - 1, 0) * w + c]
			var n := (pa - p).cross(pc - pb).normalized()
			if n.dot(-Vector3(p.x, 0, p.z)) < 0.0:
				n = -n
			nrm.append(n)
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
## （管子的法兰、导轨的支架这些一段段的零件放在每圈走台的网格里，跟着走台一起按圈剔除，见 _ring_parts）
func _build_verticals() -> void:
	var y0 := WALL_TOP
	var y1 := -DEPTH
	var pipes := SurfaceTool.new()
	pipes.begin(Mesh.PRIMITIVE_TRIANGLES)
	pipes.set_color(Color(0.15, 0.2, 0, 1))
	for a in PIPE_ANGLES:
		_cyl(pipes, _pol(PIPE_R, a, y0), _pol(PIPE_R, a, y1), 0.075, 14, false)
	_add_mesh(pipes.commit(), load("res://assets/materials/M_PipeRed.tres"))
	var steel := SurfaceTool.new()
	steel.begin(Mesh.PRIMITIVE_TRIANGLES)
	steel.set_color(Color(0.3, 0.25, 0, 1))
	var length := y0 - y1
	var mid := (y0 + y1) * 0.5
	# 电梯导轨的安装底板：整条井壁上一道钢板（走台在这里断开，从上往下看缺口里露出的是钢板，不是被照亮的冰）
	_box(steel, Transform3D(_radial_basis(0.0), _pol(R - 0.16, 0.0, mid)), Vector3(1.7, length, 0.02))
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
	_add_mesh(steel.commit(), _mat_steel)
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
		_add_mesh(cab.commit(), load(mat))


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
	# 格栅、扶手每档细节一套；钢结构每档细节 × 检修口在哪（两个方位交替，最底下那圈没有）一套：
	# 检修口那里外圈箱形梁断开、加一圈口框
	var grates: Array = [_ring_grating_rail(0), _ring_grating_rail(1), _ring_grating_rail(2)]
	var steels := {}
	var ladders: Array[ArrayMesh] = [_ladder_mesh(0), _ladder_mesh(1), _ladder_mesh(2)]
	var fixtures: Array[ArrayMesh] = [_fixture_mesh(true), _fixture_mesh(false)]
	var wash_mesh := _wash_mesh()
	var globe_mesh: Array[SphereMesh] = []
	for detail in [true, false]:
		var g := SphereMesh.new()
		g.radius = 0.075
		g.height = 0.17
		g.radial_segments = 16 if detail else 8
		g.rings = 8 if detail else 4
		globe_mesh.append(g)
	var spacing := (TAU - 2.0 * GAP - 1.2 / R) / LAMPS
	var lamp_a0 := GAP + 0.6 / R
	var grate_mat := ShaderMaterial.new()
	grate_mat.shader = preload("res://assets/shaders/bar_grating.gdshader")
	grate_mat.set_shader_parameter("radius", R)
	grate_mat.set_shader_parameter("hatch_w", HATCH_W)
	grate_mat.set_shader_parameter("hatch_in", HATCH_IN)
	for mat in [grate_mat, _ice_mat]:
		mat.set_shader_parameter("lamp_r", LAMP_R)
		mat.set_shader_parameter("lamp_h", LAMP_H)
		mat.set_shader_parameter("lamp_start", lamp_a0)
		mat.set_shader_parameter("lamp_step", spacing)
		mat.set_shader_parameter("lamp_count", float(LAMPS))
		mat.set_shader_parameter("lamp_color", LAMP_COLOR)
	var lens_mat := ShaderMaterial.new()
	lens_mat.shader = preload("res://assets/shaders/lamp_lens.gdshader")
	lens_mat.set_shader_parameter("lit_color", LAMP_COLOR)
	lens_mat.set_shader_parameter("cool_color", LAMP_COOL)
	var near_lit := int(DebugArgs.get_arg("near-lit", str(NEAR_LIT)))
	var shadows := DebugArgs.get_arg("shadows") != "off"
	for k in ys.size():
		var y := ys[k]
		var lod := 0 if k <= 2 else (1 if k <= 10 else 2)
		# 这圈的检修口（爬梯从这里下到下一圈）
		var hatch := _ladder_a(k + RING_FIRST) if k < ys.size() - 1 else -1.0
		var skey := "%d/%.3f" % [lod, hatch]
		if not steels.has(skey):
			steels[skey] = _ring_steel(lod, hatch)
		var nodes: Array[MeshInstance3D] = []
		for i in 3:
			var mi := MeshInstance3D.new()
			mi.mesh = [grates[lod][0], steels[skey], grates[lod][1]][i]
			mi.material_override = [grate_mat, _mat_steel, _mat_rail][i]
			mi.position = Vector3(0, y, 0)
			add_child(mi)
			nodes.append(mi)
		if hatch >= 0.0:
			nodes[0].set_instance_shader_parameter("hatch_a", hatch)
			# 这圈下到下一圈的爬梯：单独一个节点（一样按圈剔除、按档细节），网格是方位角 0 处的，转过去
			var lad := MeshInstance3D.new()
			lad.mesh = ladders[lod]
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
		fix_mm.mesh = fixtures[0 if k <= 3 else 1]
		fix_mm.instance_count = LAMPS
		var wash_mm := MultiMesh.new()
		wash_mm.transform_format = MultiMesh.TRANSFORM_3D
		wash_mm.mesh = wash_mesh
		wash_mm.instance_count = LAMPS / 2
		# 灯罩：每个实例的自定义数据 r = 亮度、g = 余辉、b = 色温（lamp_lens.gdshader）
		var globes := MultiMesh.new()
		globes.transform_format = MultiMesh.TRANSFORM_3D
		globes.use_custom_data = true
		globes.mesh = globe_mesh[0 if k <= 3 else 1]
		globes.instance_count = LAMPS
		var lamps: Array[Dictionary] = []
		for j in LAMPS:
			var la := lamp_a0 + spacing * (j + ring_off + _rng.randf_range(-0.12, 0.12))
			var rot := Basis(Vector3.UP, -la)
			fix_mm.set_instance_transform(j, Transform3D(rot, Vector3(0, y, 0)))
			if j % 2 == 0:
				wash_mm.set_instance_transform(j / 2, Transform3D(Basis(Vector3.UP, -_wash_a(la, hatch)), Vector3(0, y, 0)))
			var p := _pol(LAMP_R, la, LAMP_H + y)
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
			mmi.material_override = _mat_lamp
			# 灯具不投影：照走台的那盏光从罩子中心发出来，灯座就在它正下方，投影的话脚下整片都被灯座挡黑
			if mm_ == fix_mm:
				mmi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
			add_child(mmi)
		var gi := MultiMeshInstance3D.new()
		gi.multimesh = globes
		gi.material_override = lens_mat
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
					var wa := _wash_a(la, hatch)
					var wr := Vector3(cos(wa), 0, sin(wa))
					var wl := SpotLight3D.new()
					var wdir := (wr * (0.22 + 0.06 * _hash(k, j, 1)) + Vector3.DOWN).normalized()
					wl.transform = Transform3D(Basis.looking_at(wdir, wr), _pol(R - 0.55, wa, y - 0.58))
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
					base.append(7.0 * (0.8 + 0.35 * _hash(k, j, 2)))   # 光锥放宽、边缘放软以后，总光量和原来差不多
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
				var la := _off_hatch(lamps[j].a, hatch)
				var radial := Vector3(cos(la), 0, sin(la))
				var wl := SpotLight3D.new()
				var wdir := (radial * 0.3 + Vector3.DOWN).normalized()
				wl.transform = Transform3D(Basis.looking_at(wdir, radial), _pol(R - 0.7, la, y - 0.58))
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
				var la := _off_hatch(lamps[j].a, hatch)
				var ol := OmniLight3D.new()
				ol.position = _pol(R - 1.1, la, y - 2.0)
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


## 离方位角 a 最近的两根托梁（斜撑）正中间的方位角
func _between_joists(a: float) -> float:
	var a0 := GAP + 0.6 / R
	var step := 1.3 / R
	return a0 + (floorf((a - a0) / step) + 0.5) * step


## 第 m 格（第 m、m+1 根托梁中间）正中的方位角
func _bay_a(m: int) -> float:
	return GAP + 0.6 / R + (m + 0.5) * 1.3 / R


## 第 i 圈下到第 i+1 圈的爬梯（也就是第 i 圈的检修口）在哪个方位角：偶数圈、奇数圈交替
func _ladder_a(i: int) -> float:
	return _bay_a(LADDER_BAYS[posmod(i, 2)])


## 方位角 la 那盏灯底下的洗墙灯挂在哪：两根斜撑正中间。离这圈的检修口不到两格的挪到隔两格的地方：
## 爬梯从那一格下去；洗墙灯照在走台底下冰上的那块最亮的光斑平时被走台挡着，从检修口露出来就是远处一块块刺眼的白方块
func _wash_a(la: float, hatch: float) -> float:
	var wa := _between_joists(la)
	if hatch >= 0.0:
		var d := wrapf(wa - hatch, -PI, PI) / (1.3 / R)   # 隔几格
		if absf(d) < 1.5:
			wa = hatch + 2.6 / R * (signf(d) if absf(d) > 0.5 else signf(wrapf(la - hatch, -PI, PI) + 1e-6))
	return wa


## 远处几圈走台底下那几盏代表一片灯的光源（不在格子里）：离检修口近的也挪开两格（同上，不然从检修口露出亮斑）
func _off_hatch(a: float, hatch: float) -> float:
	var d := wrapf(a - hatch, -PI, PI)
	if hatch >= 0.0 and absf(d) * R < 2.0:
		return hatch + 2.6 / R * signf(d + 1e-6)
	return a


## 0~1 的伪随机数（按圈号、灯号；不动 _rng，免得后面的随机序列全变，灯的排布跟着变）
func _hash(k: int, j: int, salt: int) -> float:
	return fposmod(sin(float(k) * 12.9898 + float(j) * 78.233 + float(salt) * 37.719) * 43758.5453, 1.0)


## 一圈走台的格栅、扶手（lod 0 最细）：[格栅, 扶手]。检修口在格栅着色器里切（hatch_a）
func _ring_grating_rail(lod: int) -> Array[ArrayMesh]:
	var segs: int = [330, 120, 60][lod]
	var sides: int = [8, 6, 5][lod]
	var grating := SurfaceTool.new()
	grating.begin(Mesh.PRIMITIVE_TRIANGLES)
	grating.set_color(Color(0.06, 0.2, 0, 1))
	_arc_box(grating, WALK_IN, WALK_OUT, -0.045, 0.0, GAP, TAU - GAP, segs)
	var rail := SurfaceTool.new()
	rail.begin(Mesh.PRIMITIVE_TRIANGLES)
	_arc_tube(rail, RAIL_R, RAIL_TOP, GAP, TAU - GAP, 0.026, segs, sides)
	_arc_tube(rail, RAIL_R, 0.56, GAP, TAU - GAP, 0.019, segs, sides)
	return [grating.commit(), rail.commit()]


## 一圈走台的钢结构（lod 0 最细）。也放这一圈上下几米里一段段的零件（管子的法兰、导轨的支架）。
## hatch >= 0：这个方位角有检修口（爬梯从这里下到下一圈）：外圈箱形梁在口子两边断开，补口框和两根短梁（_hatch_frame）
func _ring_steel(lod: int, hatch: float) -> ArrayMesh:
	var segs: int = [330, 120, 60][lod]
	var sides: int = [8, 6, 5][lod]
	var steel := SurfaceTool.new()
	steel.begin(Mesh.PRIMITIVE_TRIANGLES)
	steel.set_color(Color(0.12, 0.25, 0, 1))
	# 走台内沿的边梁是槽钢：腹板往上伸出 10 厘米当踢脚板，底下一道翼缘；里圈、外圈（靠井壁）各一道箱形梁
	_arc_box(steel, WALK_IN - 0.006, WALK_IN, -0.2, 0.1, GAP, TAU - GAP, segs)
	_arc_box(steel, WALK_IN - 0.006, WALK_IN + 0.07, -0.212, -0.2, GAP, TAU - GAP, segs)
	_arc_box(steel, WALK_IN + 0.02, WALK_IN + 0.16, -0.36, -0.045, GAP, TAU - GAP, segs)
	if hatch < 0.0:
		_arc_box(steel, R - 0.32, R - 0.18, -0.36, -0.045, GAP, TAU - GAP, segs)
	else:
		# 断到口子两边短梁的腹板上
		var cut := (HATCH_W + 0.036) / (R - 0.25)
		var span := TAU - 2.0 * GAP
		_arc_box(steel, R - 0.32, R - 0.18, -0.36, -0.045, GAP, hatch - cut, maxi(4, roundi(segs * (hatch - cut - GAP) / span)))
		_arc_box(steel, R - 0.32, R - 0.18, -0.36, -0.045, hatch + cut, TAU - GAP,
			maxi(4, roundi(segs * (TAU - GAP - hatch - cut) / span)))
		_hatch_frame(steel, lod, hatch)
	# 径向托梁（每 1.3 米一根，工字钢，一头插进冰里，根上一块锚板）+ 斜撑（三角托架：从托梁里头那端斜着撑到
	# 下面的井壁上，底下也压一块锚板）。锚板背面正好贴着冰：那一圈冰壁修平了（_wall_r）
	var a := GAP + 0.6 / R
	while a < TAU - GAP:
		var b := _radial_basis(a)
		var r0 := WALK_IN + 0.02
		var r1 := R + 0.25
		var mid := _pol((r0 + r1) * 0.5, a, 0.0)
		_box(steel, Transform3D(b, mid + Vector3(0, -0.051, 0)), Vector3(0.1, 0.012, r1 - r0))
		_box(steel, Transform3D(b, mid + Vector3(0, -0.2, 0)), Vector3(0.008, 0.286, r1 - r0))
		_box(steel, Transform3D(b, mid + Vector3(0, -0.349, 0)), Vector3(0.1, 0.012, r1 - r0))
		_box(steel, Transform3D(b, _pol(R - 0.012, a, -0.2)), Vector3(0.24, 0.5, 0.024))
		if lod < 2:
			_beam(steel, _pol(WALK_IN + 0.32, a, -0.355), _pol(R - 0.03, a, -1.2), Vector2(0.06, 0.06), b.x)
			_box(steel, Transform3D(b, _pol(R - 0.012, a, -1.22)), Vector3(0.2, 0.32, 0.024))
		a += 1.3 / R
	# 栏杆立柱（每 1.5 米一根），底下一块法兰压在格栅边上
	a = GAP + 0.03 / R
	while a < TAU - GAP + 0.01:
		_cyl(steel, _pol(RAIL_R, a, 0.0), _pol(RAIL_R, a, RAIL_TOP), 0.021, sides, true)
		if lod == 0:
			_box(steel, Transform3D(_radial_basis(a), _pol(RAIL_R, a, 0.006)), Vector3(0.11, 0.012, 0.09))
		a += 1.5 / R
	# 管卡（从走台外沿伸过去抱住加热管）、桥架卡子、接线箱（灯的电从这里接，架在走台外沿的角钢上，离冰面留一点）
	for pa in PIPE_ANGLES:
		_box(steel, Transform3D(_radial_basis(pa), _pol(PIPE_R - 0.08, pa, 0.45)), Vector3(0.22, 0.06, 0.26))
	_box(steel, Transform3D(_radial_basis(TRAY_ANGLE), _pol(R - 0.12, TRAY_ANGLE, 0.6)), Vector3(0.62, 0.05, 0.14))
	_box(steel, Transform3D(_radial_basis(JBOX_ANGLE), _pol(R - 0.3, JBOX_ANGLE, 1.3)), Vector3(0.42, 0.55, 0.2))
	_box(steel, Transform3D(_radial_basis(JBOX_ANGLE), _pol(R - 0.3, JBOX_ANGLE, 0.5)), Vector3(0.05, 1.0, 0.05))
	# 竖着的东西上一段段的零件：加热管每 6 米一道法兰（这圈上下各 3 米），电梯导轨每 3 米一道支架
	if lod < 2:
		for dy in [3.0, -3.0]:
			for pa in PIPE_ANGLES:
				_cyl(steel, _pol(PIPE_R, pa, dy - 0.025), _pol(PIPE_R, pa, dy + 0.025), 0.11, 14 if lod == 0 else 8, true)
		for dy in [4.5, 1.5, -1.5, -4.5]:
			for side in [-1.0, 1.0]:
				var ga: float = side * 0.05
				_box(steel, Transform3D(_radial_basis(ga), _pol(R - 0.2, ga, dy)), Vector3(0.16, 0.08, 0.1))
	return steel.commit()


## 检修口的口框（方位角 hatch；口子径向从 HATCH_IN 到走台外沿，切向 ±HATCH_W）：一圈 L50×50×6 角钢，竖肢朝着口子、
## 顶面和格栅齐平，平肢伸到格栅底下托着切断的扁钢。近处还有两边的短梁（槽钢）：从里圈箱形梁伸进冰里，
## 托住口框、接住断开的外圈箱形梁，根上一块锚板
func _hatch_frame(st: SurfaceTool, lod: int, hatch: float) -> void:
	var hb := Basis(Vector3.UP, -hatch)   # 局部 x 径向朝外、z 切向（方位角 0 处），转到 hatch
	var box := func(c: Vector3, sz: Vector3) -> void: _box(st, Transform3D(hb, hb * c), sz)
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
func _fixture_mesh(detail: bool) -> ArrayMesh:
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	st.set_color(Color(0.3, 0.3, 0, 1))
	var c := _pol(LAMP_R, 0.0, LAMP_H)   # 罩子的中心
	var arm_y := LAMP_H - 0.165
	_box(st, Transform3D(_radial_basis(0.0), _pol(RAIL_R, 0.0, RAIL_TOP)), Vector3(0.05, 0.075, 0.075))
	_beam(st, _pol(RAIL_R + 0.02, 0.0, arm_y), _pol(LAMP_R - 0.03, 0.0, arm_y), Vector2(0.03, 0.03), Vector3(0, 0, 1))
	if detail:
		# 抱箍到横臂的短立板
		_box(st, Transform3D(_radial_basis(0.0), _pol(RAIL_R, 0.0, (RAIL_TOP + arm_y) * 0.5)), Vector3(0.04, absf(RAIL_TOP - arm_y) + 0.04, 0.01))
	# 灯座：铸铝，下面接横臂，上面一道螺口压着罩子（剖面：半径, 离罩子中心的高度；从顶上的轴往外、往下）
	var prof: Array[Vector2] = [Vector2(0.0, -0.06), Vector2(0.047, -0.06), Vector2(0.05, -0.068), Vector2(0.062, -0.074),
		Vector2(0.067, -0.09), Vector2(0.067, -0.132), Vector2(0.06, -0.148), Vector2(0.0, -0.15)]
	if not detail:
		prof = [Vector2(0.0, -0.06), Vector2(0.06, -0.07), Vector2(0.067, -0.13), Vector2(0.0, -0.15)]
	_lathe(st, c, prof, 16 if detail else 6)
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
			_tube(st, pts, 0.0032, 4)
		_ring_tube(st, c, 0.0855, 0.0032, 24, 4)
		_ring_tube(st, c + Vector3(0, 0.099, 0), 0.032, 0.004, 12, 4)
	else:
		_ring_tube(st, c + Vector3(0, 0.099, 0), 0.032, 0.005, 6, 3)
	return st.commit()


## 走台底下的洗墙灯灯壳：吊在托梁底下，朝下那面是玻璃（看不见）
func _wash_mesh() -> ArrayMesh:
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	st.set_color(Color(0.3, 0.3, 0, 1))
	var b0 := _radial_basis(0.0)
	_box(st, Transform3D(b0, _pol(R - 0.55, 0.0, -0.48)), Vector3(0.4, 0.16, 0.22))
	for side in [-1.0, 1.0]:
		_box(st, Transform3D(b0, _pol(R - 0.55, 0.0, -0.38) + b0.x * 0.15 * side), Vector3(0.025, 0.06, 0.025))
	return st.commit()


## 一段护笼爬梯：从这圈走台的检修口下到下一圈。方位角 0 处的局部坐标（x 径向朝外、z 切向），这圈走台面是 y = 0，
## 下面那圈是 y = -RING_STEP。两根扁钢梯梁（60×12）从下面那圈的走台面一直伸到这圈走台面以上 1.1 米当扶手；
## 圆钢踏棍每 0.3 米一根，最上面一根和这圈走台面齐平，顶上被鞋底磨出钢来（顶点色）；每 3 米一对扁钢支架伸到冰上，
## 锚板贴着修平的那条冰（_wall_r）。下面那圈走台面以上 CAGE_FROM 起护笼：扁钢箍每 0.9 米一道
## （从梯梁外侧往外张开、再绕半圈，前沿离踏棍 0.7 米），里面贴 5 根竖向扁钢，最上面一道箍在检修口里。
## 整副梯子连支架、锚板一起刷安全黄（_mat_rail），一个面：每圈只多一次绘制
func _ladder_mesh(lod: int) -> ArrayMesh:
	var x := R - LADDER_OFF
	var y0 := -RING_STEP
	var zs := 0.235                    # 梯梁中心离中线（内净宽 0.458）
	var yel := SurfaceTool.new()
	yel.begin(Mesh.PRIMITIVE_TRIANGLES)
	yel.set_color(Color(0.12, 0.25, 0, 1))
	var id := Basis()
	for s in [-1.0, 1.0]:
		_box(yel, Transform3D(id, Vector3(x, (y0 + 1.1) * 0.5, s * zs)), Vector3(0.06, 1.1 - y0, 0.012))
		if lod < 2:
			# 脚板：梯梁落在下面那圈的格栅上，螺栓压住
			_box(yel, Transform3D(id, Vector3(x, y0 + 0.004, s * (zs + 0.03))), Vector3(0.1, 0.008, 0.07))
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
		_strip(yel, pts, 0.006, 0.05, lod == 0)
	# 竖向扁钢：贴在箍里面
	var top := hy[-1] + 0.025
	var bot := hy[0] - 0.025
	for i in 5:
		var th := PI * 0.5 - PI * i / 4.0
		var c := Vector3(xc - (rho - 0.006) * cos(th), (top + bot) * 0.5, (rho - 0.006) * sin(th))
		_box(yel, Transform3D(Basis(Vector3(sin(th), 0, cos(th)), Vector3.UP, Vector3(-cos(th), 0, sin(th))), c),
			Vector3(0.05, top - bot, 0.006))
	# 支架：每 3 米一对，扁钢贴着梯梁外侧伸到冰上，锚板，近处看得见两颗锚栓的螺母
	var yb := y0 + 1.5
	while yb < 0.0:
		for s in [-1.0, 1.0]:
			var z: float = s * (zs + 0.011)
			var xa := x - 0.03
			var xb := R - 0.012
			_box(yel, Transform3D(id, Vector3((xa + xb) * 0.5, yb, z)), Vector3(xb - xa, 0.05, 0.01))
			_box(yel, Transform3D(id, Vector3(R - 0.006, yb, z)), Vector3(0.012, 0.16, 0.12))
			if lod == 0:
				for dy in [-0.055, 0.055]:
					_box(yel, Transform3D(id, Vector3(R - 0.019, yb + dy, z)), Vector3(0.014, 0.024, 0.024))
		yb += 3.0
	# 踏棍放最后画（顶点色按朝上的程度给，会改 SurfaceTool 当前的颜色）；远档细得比像素还细，不画
	if lod < 2:
		for i in range(1, roundi(RING_STEP / 0.3) + 1):
			var yy := y0 + 0.3 * i
			_cyl(yel, Vector3(x, yy, -zs + 0.006), Vector3(x, yy, zs - 0.006), 0.011, 8 if lod == 0 else 4, false, true)
	var mesh := yel.commit()
	mesh.surface_set_material(0, _mat_rail)
	return mesh


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


## 圆柱（worn：顶点色按朝上的程度给，见 _tri_worn——踏棍顶上被鞋底磨出钢来；会改 SurfaceTool 当前的颜色）
func _cyl(st: SurfaceTool, a: Vector3, b: Vector3, r: float, sides: int, caps: bool, worn := false) -> void:
	var ax := (b - a).normalized()
	var u := ax.cross(Vector3.UP if absf(ax.y) < 0.9 else Vector3.RIGHT).normalized()
	var v := ax.cross(u)
	var tri := _tri_worn if worn else _tri
	for k in sides:
		var a0 := TAU * k / sides
		var a1 := TAU * (k + 1) / sides
		var n0 := u * cos(a0) + v * sin(a0)
		var n1 := u * cos(a1) + v * sin(a1)
		tri.call(st, a + n0 * r, b + n0 * r, b + n1 * r, n0, n0, n1)
		tri.call(st, a + n0 * r, b + n1 * r, a + n1 * r, n0, n1, n1)
		if caps:
			_tri(st, a, a + n0 * r, a + n1 * r, -ax, -ax, -ax)
			_tri(st, b, b + n1 * r, b + n0 * r, ax, ax, ax)


## 沿水平折线扫一条竖着放的扁钢（厚 th、高 h：护笼的箍）。侧面按顶点算法线（弯的那段看着是圆的），
## 每个节点的截面放在前后两段的平均方向上；ends = false 不画顶面、底面（远了几毫米宽的面看不见）
func _strip(st: SurfaceTool, pts: Array[Vector3], th: float, h: float, ends := true) -> void:
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
			_tri(st, a + sa * sg - up, b + sb * sg - up, b + sb * sg + up, na, nb, nb)
			_tri(st, a + sa * sg - up, b + sb * sg + up, a + sa * sg + up, na, nb, na)
		if ends:
			_quad(st, a - sa + up, a + sa + up, b + sb + up, b - sb + up, Vector3.UP)
			_quad(st, a - sa - up, b - sb - up, b + sb - up, a + sa - up, Vector3.DOWN)


## 两点之间一根方钢（截面 size：x 沿 side 方向）
func _beam(st: SurfaceTool, a: Vector3, b: Vector3, size: Vector2, side: Vector3) -> void:
	var z := (b - a).normalized()
	var x := (side - z * side.dot(z)).normalized()
	_box(st, Transform3D(Basis(x, z.cross(x), z), (a + b) * 0.5), Vector3(size.x, size.y, a.distance_to(b)))


## 沿折线扫一根圆管：每个节点一圈顶点，截面放在前后两段的平均方向上（拐弯处不留缝），截面的朝向顺着折线平移（不打扭）
func _tube(st: SurfaceTool, pts: Array[Vector3], r: float, sides: int) -> void:
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
			_tri(st, pts[i] + ra[k] * r, pts[i + 1] + rb[k] * r, pts[i + 1] + rb[k1] * r, ra[k], rb[k], rb[k1])
			_tri(st, pts[i] + ra[k] * r, pts[i + 1] + rb[k1] * r, pts[i] + ra[k1] * r, ra[k], rb[k1], ra[k1])


## 一圈水平的圆环管（护罩腰上的箍）
func _ring_tube(st: SurfaceTool, c: Vector3, rr: float, tr: float, segs: int, sides: int) -> void:
	var pts: Array[Vector3] = []
	for i in segs + 1:
		var ang := TAU * i / segs
		pts.append(c + Vector3(cos(ang), 0, sin(ang)) * rr)
	_tube(st, pts, tr, sides)


## 车床回转体：prof 是 (半径, 高) 的折线，从轴上的顶点往外、往下走（这样算出来的法线朝外）；绕着过 c 的竖直轴转一圈
func _lathe(st: SurfaceTool, c: Vector3, prof: Array[Vector2], sides: int) -> void:
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
			_tri(st, a0, b0, b1, n0, n0, n1)
			_tri(st, a0, b1, a1, n0, n1, n1)


## 一段环形的管子（栏杆扶手）：沿半径 rr、高 y 的圆弧扫一个圆截面，两头封口。
## 顶点色 R（棱边磨损）按朝上的程度给：扶手顶上被手磨亮，底下没人碰
func _arc_tube(st: SurfaceTool, rr: float, y: float, a0: float, a1: float, tr: float, segs: int, sides := 8) -> void:
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
			_tri_worn(st, p00, p10, p11, n00, n10, n11)
			_tri_worn(st, p00, p11, p01, n00, n11, n01)
	for end in [[a0, -1.0], [a1, 1.0]]:
		var ea: float = end[0]
		var tn := Vector3(-sin(ea), 0, cos(ea)) * float(end[1])
		var c := _pol(rr, ea, y)
		for k in sides:
			var b0 := TAU * k / sides
			var b1 := TAU * (k + 1) / sides
			var q0 := c + (Vector3(cos(ea), 0, sin(ea)) * cos(b0) + Vector3.UP * sin(b0)) * tr
			var q1 := c + (Vector3(cos(ea), 0, sin(ea)) * cos(b1) + Vector3.UP * sin(b1)) * tr
			_tri_worn(st, c, q0, q1, tn, tn, tn)


## 带磨损顶点色的三角形（朝上的顶点 R 大）
func _tri_worn(st: SurfaceTool, a: Vector3, b: Vector3, c: Vector3, na: Vector3, nb: Vector3, nc: Vector3) -> void:
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
