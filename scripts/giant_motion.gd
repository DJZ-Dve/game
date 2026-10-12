class_name GiantMotion
extends RefCounted
## 闷雷（第二版：照格陵兰睡鲨做的深海鲨鱼）的程序化动作（giant.gd 每帧调 update）。
## 骨骼是 blender/scripts/giant/spec.py 的 bones()：Spine_00（吻端）～ Spine_15（尾尖）沿中轴线从头指向尾，
## TailFin_0/1 接在尾尖后面，Jaw 从嘴角铰链指向下颌前端，PecL/R_0/1 胸鳍两节、PelL/R 腹鳍、GillL/R 一侧五道鳃裂后缘的皮瓣，
## ParasiteL/R_0..3 挂在眼睛上的寄生虫卵带。模型（assets/models/giant.glb）-Z 朝前，原点在身体中段（s = 0.5），全长 42 米。
##
## - 游动：鲨鱼的鲹科式游法。身体前三分之二几乎不动，横向行波从 s ≈ 0.3 起、到 0.4 以后才看得出来，往尾巴越来越大；
##   频率、幅度跟着速度走、速度越快涨得越多（停着十几秒一摆、尾巴左右不到半米；巡航 2 米/秒九秒一摆、尾巴左右一米；
##   冲刺 7 米/秒三秒一摆、尾巴甩三米，正在加速的时候再多甩一点）。
##   波形按质量（截面积）去掉平移和整体转动的分量，所以头只有很小的、和尾巴反着的晃动（反冲），重心不跟着晃。
##   尾鳍两节接着同一道行波往后延，每节再晚一点相位，像鞭梢一样晚半拍甩出去。
##   转弯时整条身子顺着弧线弯（中段往外鼓、头尾往里收），上浮下潜时上下也弯一点；所有输入都过平滑，不抖。
## - 头：冲刺时上头（Spine_00～02）往上抬几度（下颌另外往下张），撞上以后头甩几下。头的这些额外动作以颈后（第 7 节）为支点，
##   身子不跟着动。张嘴加抬头一共不超过 GAPE_MAX。
## - 呼吸：一口气是「嘴先张开进水 → 嘴合上、鳃后缘的皮瓣往外翻开出水」。平时五到七秒一口、开得浅；
##   冲刺、吼叫、撞上以后喘得急（两三秒一口）、鳃开得大，慢慢再平下来。左边比右边早一点点。
## - 嘴：二阶弹簧追目标角度（大东西张嘴慢），平时的目标上再加呼吸的那几度；snap() 猛地合上——很硬的弹簧，合到底弹回来一点再合上。
## - 胸鳍：平时自己轻轻起伏；转弯时内侧那片往下压、外侧往上抬（打舵）；上浮下潜两片一起调攻角；冲刺时往后收、贴到身上（减阻）。
##   外面那节跟着里面那节慢一点（鳍梢被水推着弯）。腹鳍跟着轻轻动、冲刺时也收一点。
## - 寄生虫卵带：每条五个点在世界里做质点链（根部钉在眼睛上；水的阻力按点相对静水的速度算，
##   所以游起来往后飘、游得快几乎拉直，停下来靠一点点下沉慢慢垂回去；水里偶尔来一阵乱流扰一下），不钻进头里；再按点转骨骼。
## - 碰撞：沿脊椎八段胶囊（按 spec 第二版的截面估）加下颌一段，挂在 Skeleton3D 底下跟着骨骼走，
##   层 Giant.LAYER、组 sonar_hard（声呐射线打得到）。

const MODEL := "res://assets/models/giant.glb"
const LENGTH := 42.0
const HALF := LENGTH * 0.5
const SPINE := 16
## 尾鳍两节（TailFin_0/1），每节长（spec 的 TAIL_FIN_SEG）
const TAIL_FIN_BONES := 2
const TAIL_FIN_SEG := 3.5
## 尾鳍每节在行波上再晚多少相位（弧度）、幅度包络往后接着长多少（1 = 照着身子的包络往外推）
const TAIL_FIN_LAG := 0.3
const TAIL_FIN_GROW := 0.5
const JAW_OPEN_MAX := 70.0
## 张嘴 + 上头抬起加起来最多这么多（度）
const GAPE_MAX := 80.0
## 下颌骨长（铰链到下巴前端，spec 的 jaw_hinge() → (JAW_FRONT_S, mouth_z(0) - 0.8)）
const JAW_LEN := 9.3
## spec.py 的 _PROFILE（第二版）：s、半宽、背高、腹深、中轴线高度、超椭圆指数
const PROFILE := [
	[0.00, 1.90, 1.10, 1.30, 0.30, 2.2],
	[0.04, 3.30, 2.10, 2.50, 0.30, 2.2],
	[0.10, 4.30, 3.00, 3.50, 0.30, 2.2],
	[0.18, 4.80, 3.60, 4.10, 0.30, 2.2],
	[0.26, 5.00, 4.00, 4.30, 0.35, 2.15],
	[0.36, 5.10, 4.30, 4.30, 0.40, 2.1],
	[0.48, 4.70, 4.10, 3.90, 0.40, 2.1],
	[0.60, 3.90, 3.50, 3.10, 0.35, 2.05],
	[0.72, 2.70, 2.70, 2.20, 0.30, 2.0],
	[0.82, 1.60, 1.95, 1.45, 0.30, 2.0],
	[0.88, 1.00, 1.45, 1.00, 0.30, 2.0],
	[0.94, 0.80, 1.25, 0.90, 0.35, 2.0],
	[1.00, 0.30, 0.60, 0.40, 0.40, 2.0],
]

# ---------------------------------------------------------------------------- 游动参数
## 行波从这里开始（再往前是硬的），包络 ((s - WAVE_START) / (1 - WAVE_START)) ^ WAVE_POW：s = 0.4 才 1%、0.66 约 23%
const WAVE_START := 0.30
const WAVE_POW := 2.2
## 行波的波长（身体长度的几分之几）：活动段上不到一个波长（鲹科式）
const WAVE_LEN := 1.0
## 尾尖摆幅（米，单侧）= AMP_IDLE + AMP_LIN × v + AMP_SQ × v² + AMP_PER_ACCEL × 加速度，最多 AMP_MAX
const AMP_IDLE := 0.45
const AMP_LIN := 0.25
const AMP_SQ := 0.018
const AMP_PER_ACCEL := 0.5
const AMP_MAX := 3.6
## 摆尾频率（赫兹）= FREQ_IDLE + FREQ_LIN × v + FREQ_SQ × v² + FREQ_PER_ACCEL × 加速度
const FREQ_IDLE := 0.05
const FREQ_LIN := 0.025
const FREQ_SQ := 0.0022
const FREQ_PER_ACCEL := 0.03
## 转弯 / 俯仰时身子的弯曲：曲率 = 角速度 × 系数（每米弧度），有上限
const BEND_PER_TURN := 0.12
const BEND_MAX := 0.011
const PITCH_BEND_PER_RATE := 0.25
const PITCH_BEND_MAX := 0.006
## 上下的小起伏（米，尾尖）
const HEAVE := 0.15
## 上头抬起来时各节分到多少（Spine_00～04）；头甩时各节分到多少（Spine_00～06）
const LIFT_W := [1.0, 1.0, 0.75, 0.3, 0.0]
const SHAKE_W := [1.0, 1.0, 1.0, 1.0, 0.85, 0.45, 0.15]
## 头动的支点：第 7 节关节（颈后），它的位置只跟着身子的波走
const ANCHOR := 7
## 沿脊椎几段胶囊（每段两节骨）
const CAPSULES := 8

# ---------------------------------------------------------------------------- 嘴、呼吸
## 平时张嘴的弹簧：角频率（弧度/秒）、阻尼比
const JAW_W := 2.4
const JAW_ZETA := 1.0
## 猛地合上：很硬、欠阻尼，合到底按这个比例弹回来
const SNAP_W := 24.0
const SNAP_ZETA := 0.5
const SNAP_BOUNCE := 0.32
const SNAP_TIME := 1.1
## 一口气多长（秒，每口在这中间随便取）；喘得最急时乘 BREATH_FAST
const BREATH_PERIOD := Vector2(5.0, 7.0)
const BREATH_FAST := 0.38
## 一口气里嘴张开、鳃打开的时段（一口气的几分之几）：嘴先张，合上的时候鳃开
const BREATH_MOUTH := Vector2(0.0, 0.45)
const BREATH_GILL := Vector2(0.30, 0.82)
## 右边鳃比左边晚这么多（一口气的几分之几）
const BREATH_LR := 0.04
## 呼吸时嘴张多少、鳃皮瓣翻开多少（度）：[平时, 喘得最急]
const BREATH_JAW := Vector2(3.0, 8.0)
const BREATH_GILL_DEG := Vector2(7.0, 28.0)
## 喘：冲刺时涨上去的时间常数、平下来的时间常数（秒）
const EXERT_RISE := 4.0
const EXERT_FALL := 25.0

# ---------------------------------------------------------------------------- 鳍
## 打舵：每 弧度/秒 的转弯角速度，胸鳍上抬 / 下压多少度，最多 PEC_RUDDER_MAX
const PEC_RUDDER := 100.0
const PEC_RUDDER_MAX := 20.0
## 攻角：俯仰角每度给几度、俯仰角速度每 度/秒 给几度，最多 PEC_ATTACK_MAX
const PEC_ATTACK_PER_PITCH := 0.6
const PEC_ATTACK_PER_RATE := 2.0
const PEC_ATTACK_MAX := 18.0
## 冲刺收鳍：从这个速度开始收、到这个速度收满；收满时往后扫多少度、往下（贴身）多少度
const TUCK_SPEED := Vector2(4.0, 6.8)
const PEC_TUCK_SWEEP := 38.0
const PEC_TUCK_DOWN := 10.0
const PEL_TUCK_SWEEP := 20.0

# ---------------------------------------------------------------------------- 寄生虫卵带
## 水的阻力（1/秒，按点相对静水的速度）、往下沉（米/秒²）、回到静止形状的劲（1/秒²，往梢每个点乘 PARA_SOFT）
const PARA_DRAG := 3.0
const PARA_SINK := 0.5
const PARA_STIFF := 5.0
const PARA_SOFT := 0.7
## 挡卵带用的头：spec 截面缩这么多（线性插值的截面比真的皮略鼓，静止姿态的卵带贴着皮，不缩会一直被往外推）
const PARA_BODY := 0.95
## 平时的暗流（米/秒）；偶尔一阵乱流：隔多久（秒）、多快（米/秒）、持续多久（秒）
const PARA_SWAY := 0.12
const GUST_EVERY := Vector2(4.0, 12.0)
const GUST_SPEED := Vector2(0.4, 1.1)
const GUST_TIME := Vector2(1.8, 3.2)

var skel: Skeleton3D
## 现在的嘴（度）、上头抬起（度）；给日志、调试看
var jaw := 0.0
var lift := 0.0
var amp := AMP_IDLE
var freq := FREQ_IDLE
## 头相对身子朝向的偏转（度，正的往左）、尾尖横向偏移（米）：日志用
var head_yaw := 0.0
var tail_x := 0.0
## 呼吸：喘的程度（0 平静 ～ 1 喘得最急）、两边鳃现在翻开多少（度）
var exertion := 0.0
var gill := Vector2.ZERO
## 胸鳍里面那节的上抬（度，左、右；负的往下压）、往后收（度）、攻角（度）
var pec_el := Vector2.ZERO
var pec_sweep := 0.0
var pec_attack := 0.0
## 寄生虫卵带梢相对根往后拖了多远（米，两条平均；骨架空间 +Z）
var para_back := 0.0
## 调试：呼吸快慢倍数；>= 0 时鳃一直翻开这么多（度）；>= 0 时喘的程度固定
var breath_rate := 1.0
var gill_force := -1.0
var exert_force := -1.0
## 调试：身子定住不动的时候（--giant-still），当成水按现在的速度从头往尾流过去（卵带照样往后飘）
var still_flow := false

var _spine := PackedInt32Array()
var _tail_fin := PackedInt32Array()
var _jaw := -1
var _rest_rot: Array[Quaternion] = []
var _rest_pos := PackedVector3Array()
var _ax_yaw := PackedVector3Array()    # 骨骼局部坐标里的「模型上方」（横摆绕它转）
var _ax_pitch := PackedVector3Array()  # 骨骼局部坐标里的「模型右方」（俯仰绕它转）
var _g: Array[Transform3D] = []        # 这一帧摆好的骨骼（骨架空间）
var _joint_rest := PackedVector3Array()  # 17 个脊椎关节的静止位置（最后一个是尾尖）
var _mass := PackedFloat32Array()
var _seg_len := 0.0

var _speed := 0.0
var _speed_in := 0.0
var _accel := 0.0
var _turn := 0.0
var _prate := 0.0
var _pitch := 0.0
var _phase := 0.0
var _jaw_v := 0.0
var _snap := 0.0
var _shake_t := INF
var _shake_dir := 1.0
var _rng := RandomNumberGenerator.new()
var _time := 0.0

# 呼吸
var _breath_ph := 0.0
var _breath_len := 6.0
var _breath_jaw := 0.0

# 鳍：[左里, 左外, 右里, 右外] / [左, 右]；各骨骼局部的「上抬」「往后扫」「攻角」转轴，攻角的正负（让前缘往上）
var _pec := PackedInt32Array()
var _pel := PackedInt32Array()
var _gill_bones := PackedInt32Array()
var _ax_el := {}
var _ax_sw := {}
var _ax_att := {}
var _att_sign := {}
var _ax_gill := {}
var _tuck := 0.0
var _pec_lp := Vector2.ZERO

# 寄生虫卵带：每条骨骼、挂在哪根骨上；每条 5 个点（世界坐标）、速度、每节长
var _para: Array[PackedInt32Array] = []
var _para_parent := PackedInt32Array()
var _pp: Array[PackedVector3Array] = []
var _pv: Array[PackedVector3Array] = []
var _plen: Array[PackedFloat32Array] = []
var _gust := Vector3.ZERO
var _gust_t := INF
var _gust_len := 2.0
var _gust_wait := 6.0

var _caps: Array[CollisionShape3D] = []
var _jaw_cap: CollisionShape3D

# 调试：骨骼连线
var _bone_lines: ImmediateMesh
var _bone_len := PackedFloat32Array()


## 实例化模型挂到 parent 底下，建碰撞；layer 是碰撞层
func _init(parent: Node3D, layer: int) -> void:
	var model := (load(MODEL) as PackedScene).instantiate() as Node3D
	model.name = "Model"
	parent.add_child(model)
	skel = model.find_children("*", "Skeleton3D", true, false)[0]
	for mi: MeshInstance3D in model.find_children("*", "MeshInstance3D", true, false):
		mi.extra_cull_margin = 6.0  # 尾巴甩出去、嘴张开都会出静止姿态的包围盒
	var n := skel.get_bone_count()
	_g.resize(n)
	_rest_pos.resize(n)
	_ax_yaw.resize(n)
	_ax_pitch.resize(n)
	for b in n:
		var r := skel.get_bone_rest(b)
		_rest_rot.append(r.basis.get_rotation_quaternion())
		_rest_pos[b] = r.origin
		var gi := skel.get_bone_global_rest(b).basis.orthonormalized().inverse()
		_ax_yaw[b] = (gi * Vector3.UP).normalized()
		_ax_pitch[b] = (gi * Vector3.RIGHT).normalized()
	for i in SPINE:
		_spine.append(skel.find_bone("Spine_%02d" % i))
	_jaw = skel.find_bone("Jaw")
	for k in TAIL_FIN_BONES:
		var b := skel.find_bone("TailFin_%d" % k)
		if b >= 0:
			_tail_fin.append(b)
	for i in SPINE:
		_joint_rest.append(skel.get_bone_global_rest(_spine[i]).origin)
	var tail := skel.get_bone_global_rest(_spine[SPINE - 1])
	_seg_len = _rest_pos[_spine[1]].length()
	_joint_rest.append(tail * Vector3(0.0, _seg_len, 0.0))
	for j in SPINE + 1:
		var sec := section(float(j) / SPINE)
		_mass.append(sec[0] * (sec[1] + sec[2]))
	_setup_fins()
	_setup_parasites()
	_build_collision(layer)
	_rng.randomize()
	_breath_ph = _rng.randf()
	_breath_len = _rng.randf_range(BREATH_PERIOD.x, BREATH_PERIOD.y)
	_gust_wait = _rng.randf_range(GUST_EVERY.x, GUST_EVERY.y)
	update(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)


## spec 的截面（线性插值，够估碰撞、质量、卵带别钻进头里用）：[半宽, 背高, 腹深, 中轴线高度, 超椭圆指数]
static func section(s: float) -> Array:
	s = clampf(s, 0.0, 1.0)
	for i in range(1, PROFILE.size()):
		if s <= PROFILE[i][0]:
			var a: Array = PROFILE[i - 1]
			var b: Array = PROFILE[i]
			var t: float = (s - a[0]) / (b[0] - a[0])
			return [lerpf(a[1], b[1], t), lerpf(a[2], b[2], t), lerpf(a[3], b[3], t), lerpf(a[4], b[4], t),
				lerpf(a[5], b[5], t)]
	var e: Array = PROFILE[-1]
	return [e[1], e[2], e[3], e[4], e[5]]


## 猛地合上嘴（撞上 hard = true；扑空咬了个空 hard = false，轻一点、头不甩）。之后喘得急
func snap(hard := true) -> void:
	_snap = SNAP_TIME if hard else SNAP_TIME * 0.6
	exert(1.0 if hard else 0.8)
	if hard:
		_shake_t = -0.1   # 合上一下以后再甩
		_shake_dir = 1.0 if _rng.randf() < 0.5 else -1.0


## 喘一下（吼叫、撞上以后）：喘的程度至少到 k
func exert(k: float) -> void:
	exertion = maxf(exertion, k)


## 每帧：speed 米/秒、turn_rate 偏航角速度（弧度/秒，正的往左）、pitch_rate 俯仰角速度（弧度/秒，正的抬头）、
## jaw_target 想张多大（度）、lift_target 上头想抬多少（度）；jaw_force >= 0 时嘴直接摆到这个角度（调试）；
## pitch_angle 现在的俯仰角（弧度，正的抬头，胸鳍攻角用）
func update(delta: float, speed: float, turn_rate: float, pitch_rate: float, jaw_target: float,
		lift_target: float, jaw_force := -1.0, pitch_angle := 0.0) -> void:
	_time += delta
	_smooth(delta, speed, turn_rate, pitch_rate, pitch_angle, lift_target)
	_breathe(delta)
	_jaw_step(delta, jaw_target + _breath_jaw)
	if jaw_force >= 0.0:
		jaw = minf(jaw_force, _jaw_limit())
		_jaw_v = 0.0
	_pose_spine()
	_pose_fins(delta)
	_parasites_step(delta)
	_follow_collision()
	if _bone_lines:
		_draw_bones()


# ---------------------------------------------------------------------------- 平滑
func _smooth(delta: float, speed: float, turn_rate: float, pitch_rate: float, pitch_angle: float,
		lift_target: float) -> void:
	# 时间常数都在一秒上下：四十米长的东西，改变要慢慢传过来
	var last := _speed
	_speed = lerpf(_speed, speed, 1.0 - exp(-delta / 1.0))
	if delta > 0.0:
		_accel = lerpf(_accel, (_speed - last) / delta, 1.0 - exp(-delta / 1.2))
	_turn = lerpf(_turn, turn_rate, 1.0 - exp(-delta / 1.4))
	_prate = lerpf(_prate, pitch_rate, 1.0 - exp(-delta / 1.4))
	_pitch = lerpf(_pitch, pitch_angle, 1.0 - exp(-delta / 1.4))
	var v := maxf(_speed, 0.0)
	var acc := maxf(_accel, 0.0)
	var want_f := FREQ_IDLE + FREQ_LIN * v + FREQ_SQ * v * v + FREQ_PER_ACCEL * acc
	var want_a := minf(AMP_IDLE + AMP_LIN * v + AMP_SQ * v * v + AMP_PER_ACCEL * acc, AMP_MAX)
	freq = lerpf(freq, want_f, 1.0 - exp(-delta / 1.5))
	amp = lerpf(amp, want_a, 1.0 - exp(-delta / 2.0))
	_phase = wrapf(_phase + TAU * freq * delta, 0.0, TAU * 64.0)
	# 上头：冲过来时慢慢抬，咬下去那一下跟着嘴一起猛地放下
	if _snap > 0.0:
		lift_target = 0.0
	var tau := 0.12 if _snap > 0.0 else 0.7
	lift = lerpf(lift, lift_target, 1.0 - exp(-delta / tau))
	_shake_t += delta
	# 冲刺收鳍
	_tuck = lerpf(_tuck, smoothstep(TUCK_SPEED.x, TUCK_SPEED.y, v), 1.0 - exp(-delta / 1.0))


# ---------------------------------------------------------------------------- 呼吸
func _breathe(delta: float) -> void:
	# 喘：冲刺时慢慢涨上去，停下来以后慢慢平下来
	var want := smoothstep(3.5, 7.0, _speed)
	if exert_force >= 0.0:
		exertion = exert_force
	elif want > exertion:
		exertion = lerpf(exertion, want, 1.0 - exp(-delta / EXERT_RISE))
	else:
		exertion = lerpf(exertion, want, 1.0 - exp(-delta / EXERT_FALL))
	var period := _breath_len * lerpf(1.0, BREATH_FAST, exertion) / maxf(breath_rate, 0.05)
	_breath_ph += delta / period
	if _breath_ph >= 1.0:
		_breath_ph = fmod(_breath_ph, 1.0)
		_breath_len = _rng.randf_range(BREATH_PERIOD.x, BREATH_PERIOD.y)
	_breath_jaw = lerpf(BREATH_JAW.x, BREATH_JAW.y, exertion) * _hump(_breath_ph, BREATH_MOUTH)
	var deg := lerpf(BREATH_GILL_DEG.x, BREATH_GILL_DEG.y, exertion)
	var want_g := Vector2(_hump(_breath_ph, BREATH_GILL), _hump(wrapf(_breath_ph - BREATH_LR, 0.0, 1.0), BREATH_GILL)) * deg
	if gill_force >= 0.0:
		want_g = Vector2(gill_force, gill_force)
	gill = gill.lerp(want_g, 1.0 - exp(-delta / 0.3))


## 一口气里 [a, b] 这段鼓起来一下（sin²，两头是平的）
static func _hump(ph: float, ab: Vector2) -> float:
	if ph <= ab.x or ph >= ab.y:
		return 0.0
	var s := sin(PI * (ph - ab.x) / (ab.y - ab.x))
	return s * s


# ---------------------------------------------------------------------------- 嘴
## 嘴现在最多张多大：不超过 JAW_OPEN_MAX，加上上头抬起不超过 GAPE_MAX
func _jaw_limit() -> float:
	return minf(JAW_OPEN_MAX, GAPE_MAX - lift)


func _jaw_step(delta: float, target: float) -> void:
	if _snap > 0.0:
		_snap -= delta
		target = 0.0
	target = clampf(target, 0.0, _jaw_limit())
	# 硬弹簧要分小步算才稳
	var steps := maxi(1, ceili(delta / (1.0 / 240.0)))
	var h := delta / steps
	for k in steps:
		var w := SNAP_W if _snap > 0.0 else JAW_W
		var z := SNAP_ZETA if _snap > 0.0 else JAW_ZETA
		_jaw_v += (w * w * (target - jaw) - 2.0 * z * w * _jaw_v) * h
		jaw += _jaw_v * h
		if jaw < 0.0:
			jaw = 0.0
			if _jaw_v < 0.0:
				_jaw_v = -_jaw_v * (SNAP_BOUNCE if _snap > 0.0 else 0.0)
		elif jaw > JAW_OPEN_MAX:
			jaw = JAW_OPEN_MAX
			_jaw_v = minf(_jaw_v, 0.0)


# ---------------------------------------------------------------------------- 身子
## 第 j 个点（0..SPINE 是脊椎关节，再往后是尾鳍的关节）在身体上的 s
func _joint_s(j: int) -> float:
	if j <= SPINE:
		return float(j) / SPINE
	return 1.0 + (j - SPINE) * TAIL_FIN_SEG / LENGTH


func _pose_spine() -> void:
	# 脊椎 17 个关节 + 尾鳍 2 个关节上的横向（x）、上下（y）偏移：行波 + 转弯的弯 + 起伏
	var nj := SPINE + 1 + TAIL_FIN_BONES
	var xs := PackedFloat32Array()
	var ys := PackedFloat32Array()
	xs.resize(nj)
	ys.resize(nj)
	var kappa := clampf(_turn * BEND_PER_TURN, -BEND_MAX, BEND_MAX)
	var kappa_v := clampf(_prate * PITCH_BEND_PER_RATE, -PITCH_BEND_MAX, PITCH_BEND_MAX)
	for j in nj:
		var s := _joint_s(j)
		var e := pow(maxf((s - WAVE_START) / (1.0 - WAVE_START), 0.0), WAVE_POW)
		var lag := 0.0
		if j > SPINE:
			# 尾鳍：包络接着长（TAIL_FIN_GROW），每节再晚一点相位
			e = 1.0 + (e - 1.0) * TAIL_FIN_GROW
			lag = TAIL_FIN_LAG * (j - SPINE)
		var u := s - WAVE_START
		var arm := LENGTH * maxf(s - 0.3, 0.0)
		xs[j] = amp * e * sin(_phase - TAU * u / WAVE_LEN - lag) - 0.5 * kappa * arm * arm
		ys[j] = HEAVE * e * sin(_phase * 0.5 - TAU * u * 0.6 - lag * 0.5) - 0.5 * kappa_v * arm * arm
	_remove_rigid(xs)
	_remove_rigid(ys)
	tail_x = xs[SPINE]
	# 每节的绝对横摆 / 俯仰（模型坐标，骨骼从头指向尾：横摆正的尾巴往 +X，俯仰正的尾巴往下）
	var dz := _seg_len
	var yaw := PackedFloat32Array()
	var pit := PackedFloat32Array()
	yaw.resize(SPINE)
	pit.resize(SPINE)
	var shake := _shake()
	for i in SPINE:
		yaw[i] = atan2(xs[i + 1] - xs[i], dz)
		pit[i] = atan2(-(ys[i + 1] - ys[i]), dz)
		if i < LIFT_W.size():
			pit[i] += deg_to_rad(lift) * LIFT_W[i]
		if i < SHAKE_W.size():
			yaw[i] += shake.x * SHAKE_W[i]
			pit[i] += shake.y * SHAKE_W[i]
	head_yaw = rad_to_deg(yaw[0])
	# 相对父骨的转动 → 骨骼姿态，顺手正向运动学算出各骨（骨架空间）
	var py := 0.0
	var pp := 0.0
	for i in SPINE:
		var b := _spine[i]
		var q := _rest_rot[b] * Quaternion(_ax_yaw[b], yaw[i] - py) * Quaternion(_ax_pitch[b], pit[i] - pp)
		py = yaw[i]
		pp = pit[i]
		skel.set_bone_pose_rotation(b, q)
		var parent := skel.get_bone_parent(b)
		var local := Transform3D(Basis(q), _rest_pos[b])
		_g[b] = local if parent < 0 else _g[parent] * local
	# 整条挪一下，让支点关节落在行波算出来的位置上（头抬、头甩都绕着它，不带着身子动）
	var root := _spine[0]
	var anchor := _joint_rest[ANCHOR] + Vector3(xs[ANCHOR], ys[ANCHOR], 0.0)
	var shift := anchor - _g[_spine[ANCHOR]].origin
	skel.set_bone_pose_position(root, _rest_pos[root] + shift)
	for i in SPINE:
		_g[_spine[i]].origin += shift
	# 尾鳍：同一道行波接着往后，晚半拍甩出去（像鞭梢）
	var pyaw := yaw[SPINE - 1]
	var gp := _g[_spine[SPINE - 1]]
	for k in _tail_fin.size():
		var b := _tail_fin[k]
		var j := SPINE + k
		var fy := atan2(xs[j + 1] - xs[j], TAIL_FIN_SEG)
		var tq := _rest_rot[b] * Quaternion(_ax_yaw[b], fy - pyaw)
		pyaw = fy
		skel.set_bone_pose_rotation(b, tq)
		gp = gp * Transform3D(Basis(tq), _rest_pos[b])
		_g[b] = gp
	# 下颌：绕铰链的横轴往下
	var jq := _rest_rot[_jaw] * Quaternion(_ax_pitch[_jaw], -deg_to_rad(jaw))
	skel.set_bone_pose_rotation(_jaw, jq)
	_g[_jaw] = _g[skel.get_bone_parent(_jaw)] * Transform3D(Basis(jq), _rest_pos[_jaw])


## 按质量去掉偏移里的平移和整体转动（游起来重心不晃，大头自然有一点反着的晃动）。
## 只按脊椎的 17 个关节算（尾鳍很轻），减的时候尾鳍的点跟着一起减
func _remove_rigid(v: PackedFloat32Array) -> void:
	var m := 0.0
	var ms := 0.0
	var mv := 0.0
	for j in SPINE + 1:
		var s := float(j) / SPINE
		m += _mass[j]
		ms += _mass[j] * s
		mv += _mass[j] * v[j]
	var sc := ms / m
	var vc := mv / m
	var num := 0.0
	var den := 0.0
	for j in SPINE + 1:
		var ds := float(j) / SPINE - sc
		num += _mass[j] * ds * (v[j] - vc)
		den += _mass[j] * ds * ds
	var slope := num / den
	for j in v.size():
		v[j] -= vc + slope * (_joint_s(j) - sc)


## 撞上以后头甩几下：(横摆, 俯仰) 弧度
func _shake() -> Vector2:
	if _shake_t < 0.0 or _shake_t > 4.0:
		return Vector2.ZERO
	var t := _shake_t
	var fade := exp(-t / 0.8)
	return Vector2(deg_to_rad(10.0) * _shake_dir * fade * sin(TAU * 0.9 * t),
		deg_to_rad(4.0) * exp(-t / 0.45) * sin(TAU * 1.4 * t + 0.6))


# ---------------------------------------------------------------------------- 鳍、鳃
func _setup_fins() -> void:
	for tag in ["L", "R"]:
		for nm in ["Pec%s_0" % tag, "Pec%s_1" % tag]:
			_pec.append(skel.find_bone(nm))
		_pel.append(skel.find_bone("Pel%s" % tag))
		_gill_bones.append(skel.find_bone("Gill%s" % tag))
	for b: int in Array(_pec) + Array(_pel):
		if b < 0:
			continue
		var gr := skel.get_bone_global_rest(b)
		var gi := gr.basis.orthonormalized().inverse()
		var d := gr.basis.y.normalized()
		# 转 +角度：上抬 = 梢往上，往后扫 = 梢往尾巴（+Z）
		_ax_el[b] = (gi * d.cross(Vector3.UP)).normalized()
		_ax_sw[b] = (gi * d.cross(Vector3.BACK)).normalized()
		_ax_att[b] = (gi * d).normalized()
		# 绕鳍的展向转：正的让前缘（-Z 那边）往上
		_att_sign[b] = signf(d.cross(Vector3.FORWARD).y) if absf(d.cross(Vector3.FORWARD).y) > 1e-3 else 1.0
	for b in _gill_bones:
		if b < 0:
			continue
		# 鳃皮瓣：铰链是鳃裂那条线（垂直于骨头、贴着皮），转 +角度骨梢往体外（截面法线方向）翻
		var gr := skel.get_bone_global_rest(b)
		var p := gr.origin
		var sec := section((p.z + HALF) / LENGTH)
		var h: float = sec[1] if p.y >= sec[3] else sec[2]
		var nrm := Vector3(p.x / (sec[0] * sec[0]), (p.y - sec[3]) / (h * h), 0.0).normalized()
		var d := gr.basis.y.normalized()
		var gi := gr.basis.orthonormalized().inverse()
		_ax_gill[b] = (gi * d.cross(nrm)).normalized()


func _fin_rot(b: int, el: float, sw: float, att: float) -> Quaternion:
	return _rest_rot[b] * Quaternion(_ax_el[b], deg_to_rad(el)) * Quaternion(_ax_sw[b], deg_to_rad(sw)) \
		* Quaternion(_ax_att[b], deg_to_rad(att) * _att_sign[b])


func _pose_fins(delta: float) -> void:
	var t := _time
	var turn_deg := clampf(_turn * PEC_RUDDER, -PEC_RUDDER_MAX, PEC_RUDDER_MAX)
	pec_attack = clampf(rad_to_deg(_pitch) * PEC_ATTACK_PER_PITCH + rad_to_deg(_prate) * PEC_ATTACK_PER_RATE,
		-PEC_ATTACK_MAX, PEC_ATTACK_MAX) * (1.0 - 0.6 * _tuck)
	pec_sweep = PEC_TUCK_SWEEP * _tuck
	for side in 2:
		var sg := -1.0 if side == 0 else 1.0
		var b0 := _pec[side * 2]
		var b1 := _pec[side * 2 + 1]
		if b0 < 0 or b1 < 0:
			continue
		# 平时轻轻起伏（两个慢的正弦，左右错开）；打舵：往左转（turn > 0）左边是内侧往下压、右边往上抬
		var idle := 2.5 * sin(TAU * 0.085 * t + sg * 0.9) + 1.0 * sin(TAU * 0.21 * t + sg * 2.0)
		var el := idle * (1.0 - 0.7 * _tuck) + sg * turn_deg * (1.0 - 0.5 * _tuck) - PEC_TUCK_DOWN * _tuck \
			+ 0.25 * pec_attack
		pec_el[side] = el
		skel.set_bone_pose_rotation(b0, _fin_rot(b0, el, pec_sweep, pec_attack))
		# 外面那节：顺着弯一点，再被水推着慢半拍（里面那节动了，梢还停在原来那边）
		_pec_lp[side] = lerpf(_pec_lp[side], el, 1.0 - exp(-delta / 0.7))
		var el1 := 0.3 * el + 0.8 * (_pec_lp[side] - el)
		skel.set_bone_pose_rotation(b1, _fin_rot(b1, el1, 6.0 * _tuck, 0.3 * pec_attack))
	for side in 2:
		var b := _pel[side]
		if b < 0:
			continue
		var sg := -1.0 if side == 0 else 1.0
		var el := 2.0 * sin(TAU * 0.13 * t + sg * 1.3 + 0.7) + sg * clampf(_turn * 30.0, -6.0, 6.0) * (1.0 - _tuck)
		skel.set_bone_pose_rotation(b, _fin_rot(b, el, PEL_TUCK_SWEEP * _tuck, 0.0))
	for side in 2:
		var b := _gill_bones[side]
		if b >= 0:
			skel.set_bone_pose_rotation(b, _rest_rot[b] * Quaternion(_ax_gill[b], deg_to_rad(gill[side])))


# ---------------------------------------------------------------------------- 寄生虫卵带
func _setup_parasites() -> void:
	for tag in ["L", "R"]:
		var chain := PackedInt32Array()
		var k := 0
		while skel.find_bone("Parasite%s_%d" % [tag, k]) >= 0:
			chain.append(skel.find_bone("Parasite%s_%d" % [tag, k]))
			k += 1
		if chain.is_empty():
			continue
		_para.append(chain)
		_para_parent.append(skel.get_bone_parent(chain[0]))
		_pp.append(PackedVector3Array())
		_pv.append(PackedVector3Array())
		_plen.append(PackedFloat32Array())


## 父骨现在的姿态（骨架空间）：脊椎、下颌已经在 _g 里；别的骨头现查
func _posed(b: int) -> Transform3D:
	if _spine.has(b) or b == _jaw:
		return _g[b]
	return skel.get_bone_global_pose(b)


func _parasites_step(delta: float) -> void:
	if _para.is_empty():
		return
	var xf := skel.global_transform
	var inv := xf.affine_inverse()
	# 偶尔一阵乱流：方向随便（横着、上下多一点），起来、落下都是平滑的
	_gust_wait -= delta
	if _gust_wait <= 0.0:
		_gust_wait = _rng.randf_range(GUST_EVERY.x, GUST_EVERY.y)
		_gust_t = 0.0
		_gust_len = _rng.randf_range(GUST_TIME.x, GUST_TIME.y)
		var dir := Vector3(_rng.randf_range(-1.0, 1.0), _rng.randf_range(-0.8, 0.8), _rng.randf_range(-0.5, 0.5))
		_gust = dir.normalized() * _rng.randf_range(GUST_SPEED.x, GUST_SPEED.y)
	_gust_t += delta
	var water := Vector3.ZERO
	if still_flow:
		water = (xf.basis * Vector3.BACK).normalized() * _speed
	var back := 0.0
	for c in _para.size():
		var chain := _para[c]
		var nb := chain.size()
		var parent := _para_parent[c]
		var gpar := _posed(parent)
		# 原形：卵带保持静止姿态、挂在现在的头上
		var rest := PackedVector3Array()
		var g := gpar
		for k in nb:
			g = g * Transform3D(Basis(_rest_rot[chain[k]]), _rest_pos[chain[k]])
			rest.append(xf * g.origin)
		rest.append(xf * (g * Vector3(0.0, _rest_pos[chain[nb - 1]].length(), 0.0)))
		if _pp[c].size() != nb + 1 or _pp[c][0].distance_to(rest[0]) > 8.0:
			_reset_parasite(c, rest)
		var p := _pp[c]
		var v := _pv[c]
		var lens := _plen[c]
		p[0] = rest[0]
		# 卵带离头皮多近：按父骨（Spine_01）把点挪回静止姿态的骨架空间，再查 spec 的截面
		var to_rest := skel.get_bone_global_rest(parent) * gpar.affine_inverse() * inv
		var from_rest := xf * gpar * skel.get_bone_global_rest(parent).affine_inverse()
		var steps := ceili(delta / (1.0 / 120.0))
		var h := delta / maxi(steps, 1)
		for st in steps:
			var tt := _time - delta + h * (st + 1)
			var old := p.duplicate()
			for k in range(1, nb + 1):
				# 水：一点暗流慢慢地飘 + 偶尔的乱流（往梢晚一点到）
				var flow := Vector3(sin(tt * 0.31 + k * 0.7 + c * 2.1), 0.4 * sin(tt * 0.23 + k * 0.5 + c),
					cos(tt * 0.27 + k * 0.9 + c)) * PARA_SWAY
				flow += water
				var gt := _gust_t - 0.15 * k
				if gt > 0.0 and gt < _gust_len:
					flow += _gust * sin(PI * gt / _gust_len)
				var stiff := PARA_STIFF * pow(PARA_SOFT, k - 1)
				var acc := (flow - v[k]) * PARA_DRAG + (rest[k] - p[k]) * stiff + Vector3.DOWN * PARA_SINK
				v[k] += acc * h
				p[k] += v[k] * h
			# 一节一节拉回原长（跟着前一节走）
			for it in 2:
				for k in range(1, nb + 1):
					var d := p[k] - p[k - 1]
					p[k] = p[k - 1] + d.normalized() * lens[k - 1]
			# 别钻进头里：推回皮外，只去掉往里钻的那部分速度（推的那一下不算进速度，不然会被弹飞）
			for k in range(1, nb + 1):
				var vel := (p[k] - old[k]) / h
				var q := to_rest * p[k]
				var qo := _out_of_body(q)
				if qo != q:
					var nrm := (from_rest.basis * (qo - q)).normalized()
					p[k] = from_rest * qo
					var vn := vel.dot(nrm)
					if vn < 0.0:
						vel -= nrm * vn
				v[k] = vel.limit_length(30.0)
		_pp[c] = p
		_pv[c] = v
		back += (inv * p[nb]).z - (inv * p[0]).z
		# 按点转骨骼
		var gp := gpar
		for k in nb:
			var b := chain[k]
			var base := (gp.basis * Basis(_rest_rot[b])).orthonormalized()
			var start := gp * _rest_pos[b]
			var want := (inv * p[k + 1]) - start
			var q := Quaternion.IDENTITY
			if want.length() > 1e-3:
				q = Quaternion(base.y.normalized(), want.normalized())
			var local := (gp.basis.orthonormalized().inverse() * (Basis(q) * base)).get_rotation_quaternion()
			skel.set_bone_pose_rotation(b, local)
			gp = gp * Transform3D(Basis(local), _rest_pos[b])
	para_back = back / _para.size()


func _reset_parasite(c: int, rest: PackedVector3Array) -> void:
	_pp[c] = rest.duplicate()
	var v := PackedVector3Array()
	v.resize(rest.size())
	_pv[c] = v
	var lens := PackedFloat32Array()
	for k in rest.size() - 1:
		lens.append(rest[k].distance_to(rest[k + 1]))
	_plen[c] = lens


## 静止姿态骨架空间里的一点：在身体（spec 截面 × PARA_BODY，超椭圆）里面就沿截面推到皮上
func _out_of_body(q: Vector3) -> Vector3:
	var s := (q.z + HALF) / LENGTH
	if s < 0.0 or s > 1.0:
		return q
	var sec := section(s)
	var hw: float = sec[0] * PARA_BODY
	var dy: float = q.y - sec[3]
	var hh: float = (sec[1] if dy >= 0.0 else sec[2]) * PARA_BODY
	var e: float = sec[4]
	var r := pow(absf(q.x) / hw, e) + pow(absf(dy) / hh, e)
	if r >= 1.0 or r < 1e-6:
		return q
	var k := pow(r, -1.0 / e)
	return Vector3(q.x * k, sec[3] + dy * k, q.z)


# ---------------------------------------------------------------------------- 碰撞
func _build_collision(layer: int) -> void:
	for k in CAPSULES:
		var s := (2.0 * k + 1.0) / SPINE
		var sec := section(s)
		var r: float = 0.9 * (sec[0] + 0.5 * (sec[1] + sec[2])) * 0.5
		_caps.append(_add_capsule(layer, r, _seg_len * 2.0, "Spine%d" % k))
	_jaw_cap = _add_capsule(layer, 2.2, JAW_LEN, "Jaw")


func _add_capsule(layer: int, r: float, length: float, label: String) -> CollisionShape3D:
	var body := StaticBody3D.new()
	body.name = "Hit" + label
	body.collision_layer = layer
	body.collision_mask = 0
	body.add_to_group("sonar_hard")
	var shape := CollisionShape3D.new()
	var cap := CapsuleShape3D.new()
	cap.radius = r
	cap.height = maxf(length + r, r * 2.0 + 0.1)
	shape.shape = cap
	body.add_child(shape)
	skel.add_child(body)
	return shape


## 胶囊跟着骨骼：每段从第 2k 节关节到第 2k+2 节关节，截面中心比中轴线偏一点（背高、腹深不一样）
func _follow_collision() -> void:
	for k in _caps.size():
		var a := _g[_spine[2 * k]]
		var b_origin: Vector3
		if 2 * k + 2 < SPINE:
			b_origin = _g[_spine[2 * k + 2]].origin
		else:
			b_origin = _g[_spine[SPINE - 1]] * Vector3(0.0, _seg_len, 0.0)
		var sec := section((2.0 * k + 1.0) / SPINE)
		var mid := (a.origin + b_origin) * 0.5
		mid.y += 0.5 * (sec[1] - sec[2])
		_place(_caps[k], mid, b_origin - a.origin)
	# 下颌：铰链到下巴中间，往下偏一点（下颌是嘴线以下那一大块）
	var j := _g[_jaw]
	var tip := j * Vector3(0.0, JAW_LEN, 0.0)
	_place(_jaw_cap, (j.origin + tip) * 0.5 + Vector3.DOWN * 1.0, tip - j.origin)


func _place(shape: CollisionShape3D, at: Vector3, along: Vector3) -> void:
	var y := along.normalized()
	var x := Vector3.UP.cross(y)
	if x.length() < 1e-3:
		x = Vector3.RIGHT
	x = x.normalized()
	(shape.get_parent() as Node3D).transform = Transform3D(Basis(x, y, x.cross(y)), at)


# ---------------------------------------------------------------------------- 调试：骨骼连线
## 把骨骼画成线（不挡、不受光；脊椎白、尾鳍蓝、下颌青、胸鳍腹鳍黄、鳃红、卵带绿），灰模上没刷权重的骨头也看得见在动
func show_bones() -> void:
	var n := skel.get_bone_count()
	_bone_len.resize(n)
	for b in n:
		var nm := skel.get_bone_name(b)
		var kids := skel.get_bone_children(b)
		if not kids.is_empty():
			# 接在骨梢上的那个孩子（脊椎 01 底下还挂着卵带，不能拿第一个）
			var best := kids[0]
			for k in kids:
				if _rest_pos[k].normalized().y > _rest_pos[best].normalized().y:
					best = k
			_bone_len[b] = _rest_pos[best].length()
		elif nm == "Jaw":
			_bone_len[b] = JAW_LEN
		elif nm.begins_with("Gill"):
			_bone_len[b] = 1.0
		elif nm.begins_with("Pel"):
			_bone_len[b] = 3.4
		else:
			_bone_len[b] = _rest_pos[b].length()
	_bone_lines = ImmediateMesh.new()
	var mi := MeshInstance3D.new()
	mi.name = "BoneLines"
	mi.mesh = _bone_lines
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	mi.extra_cull_margin = 100.0
	var mat := StandardMaterial3D.new()
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	mat.vertex_color_use_as_albedo = true
	mat.no_depth_test = true
	mat.render_priority = 10
	mi.material_override = mat
	skel.add_child(mi)


func _draw_bones() -> void:
	_bone_lines.clear_surfaces()
	_bone_lines.surface_begin(Mesh.PRIMITIVE_LINES)
	for b in skel.get_bone_count():
		var nm := skel.get_bone_name(b)
		var c := Color.WHITE
		if nm.begins_with("Tail"):
			c = Color(0.4, 0.6, 1.0)
		elif nm == "Jaw":
			c = Color.CYAN
		elif nm.begins_with("Pec") or nm.begins_with("Pel"):
			c = Color.YELLOW
		elif nm.begins_with("Gill"):
			c = Color.RED
		elif nm.begins_with("Parasite"):
			c = Color.GREEN
		var g := skel.get_bone_global_pose(b)
		var a := g.origin
		var e := g * Vector3(0.0, _bone_len[b], 0.0)
		# 三条错开一点的线，看着粗一点
		for o in [Vector3.ZERO, Vector3(0.04, 0.04, 0.0), Vector3(-0.04, 0.0, 0.04)]:
			_bone_lines.surface_set_color(c)
			_bone_lines.surface_add_vertex(a + o)
			_bone_lines.surface_set_color(c)
			_bone_lines.surface_add_vertex(e + o)
	_bone_lines.surface_end()
