class_name StoryNPC
extends Node3D
## 剧情角色（现在只有沈渡，assets/models/npc_shen.glb，见 blender/scripts/gen_npc.py）：
## - 动画：一段循环的底子（坐着待机），说话时不时插一段手势（想事情、摊手、摸脸），淡入淡出
## - 头和眼睛跟着玩家转（头慢、眼睛快），转不过去的角度就只转眼睛
## - 说话时按台词对口型：没有拼音库，按每个字的编码挑一个声母、一个韵母的口型，一秒四五个字；标点处闭嘴停一下
## - 一直挂着一点客气的笑。眨眼的形态键有，故意不用——他不眨眼
## - reach()：右手伸过去按住桌上的东西（TwoBoneIK3D 拉肩—肘—腕，掌心朝下、手指朝前），东西挪到哪手跟到哪，
##   够得远时上身往前探；release() 先把手往回拖、再收回来。签完合同推平安符用（office.gd 的 _give_talisman）
## 节点原点放在臀部正下方的地面上，面朝 -Z。

@export var model: PackedScene
@export var npc_name := "沈渡"
## 底子循环的动画，和说话时随机插进来的手势
@export var base_anim := "sit"
@export var talk_gestures: PackedStringArray = ["sit_think", "sit_shrug", "sit_touch_face"]
## 多大概率每句话插一个手势
@export var gesture_chance := 0.35
## 挂着的笑（0~1）
@export var smile := 0.22
## 看谁：默认是当前相机
@export var watch_camera := true

const VOWELS := ["AA_VI_10_aa", "AA_VI_11_E", "AA_VI_12_I", "AA_VI_13_O", "AA_VI_14_U", "AA_VI_10_aa", "AA_VI_11_E"]
const CONSONANTS := ["AA_VI_01_PP", "AA_VI_02_FF", "AA_VI_04_DD", "AA_VI_05_KK", "AA_VI_06_CH", "AA_VI_07_SS",
	"AA_VI_08_nn", "AA_VI_09_RR", "AA_VI_03_TH"]
const PAUSE_CHARS := "，。？！、；：…—,.?!;:"

var _skel: Skeleton3D
var _tree: AnimationTree
var _faces: Array[MeshInstance3D] = []
var _gaze: Gaze
var _speech := []           # [开始时刻, 结束时刻, 声母, 韵母]（相对说话开始）
var _speech_t := -1.0
var _speech_len := 0.0
var _smile_now := 0.0
var _smile_extra := 0.0
var _gesture_cool := 0.0
var _shape_cache := {}
# 右手伸手按东西（reach）
var _reach_ik: TwoBoneIK3D
var _reach_target: Marker3D
var _reach_pole: Marker3D
var _reach_hand: PalmDown
var _reach_lean: Lean
var _reach_node: Node3D
var _reach_w := 0.0
var _reach_back := 0.0     # 收手时先往回拖了多远（米）
var _reach_tw: Tween
var _lean := 0.0
var _shoulder_r := -1
var _arm_len := 0.55


func _ready() -> void:
	add_to_group("npc")
	var inst := model.instantiate() as Node3D
	add_child(inst)
	_skel = inst.find_children("*", "Skeleton3D", true, false)[0]
	_setup_materials(inst)
	for m in inst.find_children("*", "MeshInstance3D", true, false):
		var mi := m as MeshInstance3D
		if mi.mesh and mi.mesh.get_blend_shape_count() > 0:
			_faces.append(mi)
	var player := inst.find_children("*", "AnimationPlayer", true, false)[0] as AnimationPlayer
	for n in player.get_animation_list():
		var a := player.get_animation(n)
		a.loop_mode = Animation.LOOP_LINEAR if n in [base_anim, "sit_breathe", "stand"] else Animation.LOOP_NONE
	_tree = _build_tree(player)
	_gaze = Gaze.new()
	_skel.add_child(_gaze)
	_setup_reach()
	Story.line_started.connect(_on_line)


func _setup_materials(root: Node) -> void:
	for m in root.find_children("*", "MeshInstance3D", true, false):
		var mi := m as MeshInstance3D
		mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
		for i in mi.get_surface_override_material_count():
			var mat := mi.get_active_material(i) as StandardMaterial3D
			if mat == null:
				continue
			mat = mat.duplicate()
			var n := String(mi.name)
			if n.contains("Hair"):
				# 发片：透明度裁切 + MSAA 的 alpha to coverage，双面
				mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR
				mat.alpha_scissor_threshold = 0.5
				mat.alpha_antialiasing_mode = BaseMaterial3D.ALPHA_ANTIALIASING_ALPHA_TO_COVERAGE
				mat.cull_mode = BaseMaterial3D.CULL_DISABLED
				# 发丝贴图偏棕，台灯一照发橙：压掉棕色，头发有一点光泽
				mat.albedo_color = Color(0.55, 0.55, 0.6)
				mat.roughness = 0.38
			elif mat.resource_name.ends_with("Eyes"):
				# 眼球（gen_npc.py 从头上分出来的材质槽）：角膜湿的一层清漆，小而锐利的高光；
				# 贴图上靠上眼睑那一截已经压暗（眼睑的影子），眼睛不再像贴上去的
				mat.clearcoat_enabled = true
				mat.clearcoat = 1.0
				mat.clearcoat_roughness = 0.05
			elif mat.resource_name.ends_with("Lashes"):
				# 睫毛片：半透明混合（远了 mipmap 平均成一道柔和的深色睑缘线，不会像透明度裁切那样一闪一闪），双面
				mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
				mat.cull_mode = BaseMaterial3D.CULL_DISABLED
				mat.roughness = 0.6
				mat.specular_mode = BaseMaterial3D.SPECULAR_DISABLED
			elif n.contains("Head"):
				mat.subsurf_scatter_enabled = true
				mat.subsurf_scatter_skin_mode = true
				mat.subsurf_scatter_strength = 0.35
			elif mat.resource_name.ends_with("Suit"):
				# 呢子西装：掠射角一层很淡的绒光（逆光、窗光下肩膀和袖子的轮廓出来）
				mat.rim_enabled = true
				mat.rim = 0.25
				mat.rim_tint = 0.6
			elif mat.resource_name.ends_with("Hands"):
				mat.subsurf_scatter_enabled = true
				mat.subsurf_scatter_skin_mode = true
				mat.subsurf_scatter_strength = 0.3
			mi.set_surface_override_material(i, mat)


## 底子 + 一次性手势（OneShot），手势的动画在播放前换
func _build_tree(player: AnimationPlayer) -> AnimationTree:
	var bt := AnimationNodeBlendTree.new()
	var base := AnimationNodeAnimation.new()
	base.animation = base_anim
	bt.add_node("base", base)
	var g := AnimationNodeAnimation.new()
	g.animation = talk_gestures[0] if not talk_gestures.is_empty() else base_anim
	bt.add_node("gesture", g)
	var shot := AnimationNodeOneShot.new()
	shot.fadein_time = 0.6
	shot.fadeout_time = 0.8
	shot.fadein_curve = _ease_curve()
	shot.fadeout_curve = _ease_curve()
	bt.add_node("shot", shot)
	# 坐姿底子里混进一点呼吸（胸口、肩膀一起一伏）
	var breathing := base_anim == "sit" and player.has_animation("sit_breathe")
	if breathing:
		var br := AnimationNodeAnimation.new()
		br.animation = "sit_breathe"
		bt.add_node("breathe_anim", br)
		bt.add_node("breathe", AnimationNodeBlend2.new())
		bt.connect_node("breathe", 0, "base")
		bt.connect_node("breathe", 1, "breathe_anim")
		bt.connect_node("shot", 0, "breathe")
	else:
		bt.connect_node("shot", 0, "base")
	bt.connect_node("shot", 1, "gesture")
	bt.connect_node("output", 0, "shot")
	var tree := AnimationTree.new()
	tree.tree_root = bt
	add_child(tree)
	tree.anim_player = tree.get_path_to(player)
	tree.active = true
	if breathing:
		tree.set("parameters/breathe/blend_amount", 0.25)
	return tree


## 右臂的 IK（照 crew_body.gd 的 _setup_hands）：探身（Lean）→ 拉手臂（TwoBoneIK3D）→ 掌心朝下（PalmDown），
## 排在 Gaze 后面；平时关着，不影响动画
func _setup_reach() -> void:
	_reach_target = Marker3D.new()
	_reach_pole = Marker3D.new()
	add_child(_reach_target)
	add_child(_reach_pole)
	_reach_lean = Lean.new()
	_skel.add_child(_reach_lean)
	_reach_ik = TwoBoneIK3D.new()
	_skel.add_child(_reach_ik)
	_reach_ik.setting_count = 1
	_reach_ik.set_root_bone_name(0, "Bip01 R UpperArm")
	_reach_ik.set_middle_bone_name(0, "Bip01 R Forearm")
	_reach_ik.set_end_bone_name(0, "Bip01 R Hand")
	_reach_ik.set_target_node(0, _reach_ik.get_path_to(_reach_target))
	_reach_ik.set_pole_node(0, _reach_ik.get_path_to(_reach_pole))
	_reach_ik.influence = 0.0
	_reach_hand = PalmDown.new()
	_skel.add_child(_reach_hand)
	for m: SkeletonModifier3D in [_reach_lean, _reach_ik, _reach_hand]:
		m.active = false
	_shoulder_r = _skel.find_bone("Bip01 R UpperArm")
	var r := func(b: String) -> Vector3: return _skel.get_bone_global_rest(_skel.find_bone(b)).origin
	_arm_len = (r.call("Bip01 R UpperArm").distance_to(r.call("Bip01 R Forearm"))
		+ r.call("Bip01 R Forearm").distance_to(r.call("Bip01 R Hand"))) * _skel.global_basis.get_scale().x


## 右手伸过去，掌心朝下按在 target 上方（target 动，手跟着动）；secs 秒渐入
func reach(target: Node3D, secs := 0.4) -> void:
	_reach_node = target
	_reach_back = 0.0
	_new_reach_tween().tween_property(self, "_reach_w", 1.0, secs)


## 手收回去（secs 秒）。back > 0：前一半时间先把手从东西上抬起一点、往自己这边拖回 back 米，后一半再渐出——
## 直接渐出的话，手是从最远处斜着划回两手交叉的姿势，会扫过桌上别的东西（推平安符时扫过墨水瓶）
func release(secs := 0.6, back := 0.0) -> void:
	var tw := _new_reach_tween()
	if back > 0.0:
		tw.tween_property(self, "_reach_back", back, secs * 0.45)
		secs *= 0.55
	tw.tween_property(self, "_reach_w", 0.0, secs)


func _new_reach_tween() -> Tween:
	if _reach_tw:
		_reach_tw.kill()
	_reach_tw = create_tween().set_trans(Tween.TRANS_SINE).set_ease(Tween.EASE_IN_OUT)
	return _reach_tw


func _update_reach(delta: float) -> void:
	var w := _reach_w
	# 不伸手的时候三个修改器整个关掉：一直开着的话（权重 0、目标点没摆），实测主画面帧时间 25 → 47 毫秒
	var on := w > 0.001 and _reach_node != null
	for m: SkeletonModifier3D in [_reach_lean, _reach_ik, _reach_hand]:
		m.active = on
	if not on:
		_lean = 0.0
		return
	_reach_ik.influence = w
	_reach_hand.weight = w
	var fwd := -global_basis.z
	var right := global_basis.x
	# 掌心在东西正上方 2 厘米，手腕在掌心后面 7 厘米、高出手掌厚度一点；收手往回拖时先抬起 2 厘米，不蹭着东西
	var p := _reach_node.global_position - fwd * _reach_back + Vector3.UP * (0.02 * smoothstep(0.0, 0.05, _reach_back))
	var wrist := p + Vector3.UP * 0.05 - fwd * 0.07
	# 这一帧动画里的肩膀（_process 里读到的是修改器套上去之前的姿势，不含探身）
	var shoulder := _skel.global_transform * _skel.get_bone_global_pose(_shoulder_r).origin
	# 胳膊伸到八成以上就往前探身（探身在 IK 之前，肩膀先过去），平滑地跟过去
	var d := shoulder.distance_to(wrist) / _arm_len
	_lean = lerpf(_lean, w * smoothstep(0.8, 1.1, d), 1.0 - exp(-delta * 4.0))
	_reach_lean.amount = _lean
	_reach_lean.right = right
	# 再远也只伸到九成八——按探过身以后的肩膀算（不然手总差着探身挪过去的那七八厘米，变成指尖顶着东西推）
	var sh := _reach_lean.moved(_skel, shoulder)
	if sh.distance_to(wrist) > _arm_len * 0.98:
		wrist = sh + (wrist - sh).normalized() * _arm_len * 0.98
	# 渐入渐出的半路上手腕往上提（IK 按权重在动画姿势和伸直的姿势之间转，半路手会往下沉、指头插进桌面）：
	# 目标点提 0.2·(1-w)，乘上 IK 的权重 w，实际抬起来最多 5 厘米（w=0.5 时），两头都是 0
	wrist += Vector3.UP * 0.2 * (1.0 - w)
	_reach_target.global_position = wrist
	# 肘往外、往下（坐着按桌面的姿势），不往身子里收
	_reach_pole.global_position = shoulder + right * 0.4 + Vector3.DOWN * 0.4 - fwd * 0.1
	_reach_hand.fingers = (fwd - Vector3.UP * 0.08).normalized()
	_reach_hand.palm = Vector3.DOWN


## 头的世界坐标（坐着谈话时镜头对焦用）
func head_position() -> Vector3:
	var b := _skel.find_bone("Bip01 Head") if _skel else -1
	if b < 0:
		return global_position + Vector3.UP * 1.2
	return _skel.global_transform * _skel.get_bone_global_pose(b).origin


func _ease_curve() -> Curve:
	var c := Curve.new()
	c.add_point(Vector2(0, 0), 0, 0)
	c.add_point(Vector2(1, 1), 0, 0)
	return c


## 插一段手势（动画名见 gen_npc.py 的 ANIMS）
func gesture(anim: String) -> void:
	var bt := _tree.tree_root as AnimationNodeBlendTree
	(bt.get_node("gesture") as AnimationNodeAnimation).animation = anim
	_tree.set("parameters/shot/request", AnimationNodeOneShot.ONE_SHOT_REQUEST_FIRE)
	_gesture_cool = 6.0


## 笑一下（多笑 amount，持续 secs 秒）
func grin(amount := 0.5, secs := 2.5) -> void:
	_smile_extra = amount
	var tw := create_tween()
	tw.tween_interval(secs)
	tw.tween_property(self, "_smile_extra", 0.0, 1.2)


## 看哪儿：Node3D（跟着它）或 null（看当前相机）
func look_at_target(n: Node3D) -> void:
	_gaze.target_node = n


func _on_line(who: String, text: String, duration: float) -> void:
	if who != npc_name:
		return
	_plan_speech(text, duration)
	if _gesture_cool <= 0.0 and randf() < gesture_chance and not talk_gestures.is_empty():
		gesture(talk_gestures[randi() % talk_gestures.size()])


## 每个字一个音节：声母（可能没有）+ 韵母；标点处闭嘴停顿
func _plan_speech(text: String, duration: float) -> void:
	_speech.clear()
	var syl := 0
	var pauses := 0
	for ch in text:
		if PAUSE_CHARS.contains(ch):
			pauses += 1
		elif ch != " " and ch != "（" and ch != "）":
			syl += 1
	var pause_len := 0.28
	var per := maxf(0.12, (duration - pauses * pause_len) / maxf(syl, 1))
	var t := 0.05
	for ch in text:
		if PAUSE_CHARS.contains(ch):
			t += pause_len
			continue
		if ch == " ":
			continue
		var h := ch.unicode_at(0)
		var cons: String = CONSONANTS[h % CONSONANTS.size()] if (h >> 3) % 4 != 0 else ""
		_speech.append([t, t + per, cons, VOWELS[(h >> 1) % VOWELS.size()]])
		t += per
	_speech_len = t
	_speech_t = 0.0


func _process(delta: float) -> void:
	_gesture_cool -= delta
	if watch_camera and _gaze.target_node == null:
		var cam := get_viewport().get_camera_3d()
		if cam:
			_gaze.target = cam.global_position
	elif _gaze.target_node:
		_gaze.target = _gaze.target_node.global_position
	_gaze.forward = -global_basis.z
	_update_reach(delta)
	_update_face(delta)


func _update_face(delta: float) -> void:
	var w := {}
	if _speech_t >= 0.0:
		_speech_t += delta
		for s in _speech:
			var a: float = s[0]
			var b: float = s[1]
			if _speech_t < a - 0.08 or _speech_t > b + 0.08:
				continue
			var u := clampf((_speech_t - a) / (b - a), 0.0, 1.0)
			if not (s[2] as String).is_empty():
				w[s[2]] = maxf(w.get(s[2], 0.0), 0.8 * (1.0 - smoothstep(0.0, 0.35, u)))
			var open := sin(PI * clampf((u - 0.15) / 0.85, 0.0, 1.0))
			w[s[3]] = maxf(w.get(s[3], 0.0), open * 0.85)
			w["AK_25_JawOpen"] = maxf(w.get("AK_25_JawOpen", 0.0), open * 0.18)
		if _speech_t > _speech_len + 0.2:
			_speech_t = -1.0
	# 笑：说话时收一点
	var want := smile * (0.6 if _speech_t >= 0.0 else 1.0) + _smile_extra
	_smile_now = lerpf(_smile_now, want, 1.0 - exp(-delta * 4.0))
	w["AK_44_MouthSmileLeft"] = _smile_now
	w["AK_45_MouthSmileRight"] = _smile_now * 0.92
	w["AK_19_EyeSquintLeft"] = _smile_now * 0.35
	w["AK_20_EyeSquintRight"] = _smile_now * 0.35
	for mi in _faces:
		for i in mi.mesh.get_blend_shape_count():
			var n := _shape_name(mi, i)
			var target: float = w.get(n, 0.0)
			var cur := mi.get_blend_shape_value(i)
			mi.set_blend_shape_value(i, lerpf(cur, target, 1.0 - exp(-delta * 22.0)))


func _shape_name(mi: MeshInstance3D, i: int) -> String:
	var key := "%d:%d" % [mi.get_instance_id(), i]
	if not _shape_cache.has(key):
		_shape_cache[key] = String(mi.mesh.get_blend_shape_name(i))
	return _shape_cache[key]


## 头和眼睛看向目标：脖子、头分着转（头慢慢跟过去），眼睛先到；角度有上限，超过的部分只转眼睛
class Gaze extends SkeletonModifier3D:
	# 头最多转 45°（Rocketbox 的脖子权重扛不住更大的扭转，颈侧拉花、领口下的暗带露出来），再多的交给眼睛——
	# 超过了只转眼珠不转头，反而更瘆人
	const MAX_YAW := deg_to_rad(45.0)
	const MAX_PITCH := deg_to_rad(30.0)
	const EYE_YAW := deg_to_rad(28.0)
	const EYE_PITCH := deg_to_rad(14.0)
	var target := Vector3.ZERO
	var target_node: Node3D
	var forward := Vector3.FORWARD   # 角色身体的朝向（世界坐标）
	var _yaw := 0.0
	var _pitch := 0.0
	var _eye_yaw := 0.0
	var _eye_pitch := 0.0
	var _bones := {}
	# 眼跳：眼睛不是平滑地跟着，而是盯住一点不动、隔一会儿猛地跳到下一点（左眼、右眼、嘴……差不到一度）
	var _sacc_t := 0.0
	var _sacc_off := Vector2.ZERO
	var _saccading := true

	func _ready() -> void:
		var sk := get_skeleton()
		for n in ["Bip01 Spine2", "Bip01 Neck", "Bip01 Head", "Bip01 LEye", "Bip01 REye"]:
			_bones[n] = sk.find_bone(n)

	func _process_modification() -> void:
		var sk := get_skeleton()
		if sk == null or _bones.is_empty():
			return
		var dt := get_process_delta_time() if is_inside_tree() else 0.016
		var inv := sk.global_transform.affine_inverse()
		var eye := (sk.get_bone_global_pose(_bones["Bip01 LEye"]).origin
			+ sk.get_bone_global_pose(_bones["Bip01 REye"]).origin) * 0.5
		var to := (inv * target - eye).normalized()
		var fwd := (inv.basis * forward).normalized()
		var up := (inv.basis * Vector3.UP).normalized()
		var right := fwd.cross(up).normalized()
		# 目标方向相对身体：左右（绕 up）、上下（绕 right）
		var want_yaw := atan2(-to.dot(right), to.dot(fwd))
		var want_pitch := asin(clampf(to.dot(up), -1.0, 1.0))
		var hy := clampf(want_yaw, -MAX_YAW, MAX_YAW)
		var hp := clampf(want_pitch, -MAX_PITCH, MAX_PITCH)
		_yaw = lerpf(_yaw, hy, 1.0 - exp(-dt * 3.0))
		_pitch = lerpf(_pitch, hp, 1.0 - exp(-dt * 3.0))
		_sacc_t -= dt
		if _sacc_t <= 0.0:
			_sacc_t = randf_range(0.6, 1.8)
			_sacc_off = Vector2(randf_range(-1.0, 1.0), randf_range(-0.6, 0.6)) * deg_to_rad(0.8)
			_saccading = true
		var ey := clampf(want_yaw - _yaw + _sacc_off.x, -EYE_YAW, EYE_YAW)
		var ep := clampf(want_pitch - _pitch + _sacc_off.y, -EYE_PITCH, EYE_PITCH)
		if absf(ey - _eye_yaw) > deg_to_rad(2.0) or absf(ep - _eye_pitch) > deg_to_rad(2.0):
			_saccading = true
		if _saccading:
			# 一次扫视三四十毫秒就到
			_eye_yaw = lerpf(_eye_yaw, ey, 1.0 - exp(-dt * 45.0))
			_eye_pitch = lerpf(_eye_pitch, ep, 1.0 - exp(-dt * 45.0))
			if absf(ey - _eye_yaw) < 0.002 and absf(ep - _eye_pitch) < 0.002:
				_saccading = false
		# 转头分到上胸、脖子、头上（0.15 / 0.3 / 0.55）
		for n: String in ["Bip01 Spine2", "Bip01 Neck", "Bip01 Head"]:
			if _bones[n] < 0:
				continue
			var w: float = {"Bip01 Spine2": 0.15, "Bip01 Neck": 0.3, "Bip01 Head": 0.55}[n]
			var b: int = _bones[n]
			var gp := sk.get_bone_global_pose(b)
			gp.basis = Basis(up, _yaw * w) * Basis(right, _pitch * w) * gp.basis
			sk.set_bone_global_pose(b, gp)
		for n: String in ["Bip01 LEye", "Bip01 REye"]:
			# 眼球已经跟着头转过去了，再补上眼睛自己的那一点（绕眼球中心转）
			var b: int = _bones[n]
			var gp := sk.get_bone_global_pose(b)
			gp.basis = Basis(up, _eye_yaw) * Basis(right, _eye_pitch) * gp.basis
			sk.set_bone_global_pose(b, gp)


## 伸手按桌上东西时往前探身：三节脊柱各往前弯一点（绕身体的左右轴）。排在右臂 IK 前面
class Lean extends SkeletonModifier3D:
	const BONES := {"Bip01 Spine": 4.0, "Bip01 Spine1": 5.0, "Bip01 Spine2": 5.0}
	var amount := 0.0
	var right := Vector3.RIGHT

	func _process_modification() -> void:
		var sk := get_skeleton()
		if sk == null or amount <= 0.001:
			return
		var axis := (sk.global_transform.basis.inverse() * right).normalized()
		for n: String in BONES:
			var b := sk.find_bone(n)
			var gp := sk.get_bone_global_pose(b)
			gp.basis = Basis(axis, -deg_to_rad(BONES[n]) * amount) * gp.basis
			sk.set_bone_global_pose(b, gp)

	## 上身的一点 p（世界坐标，没探身时的位置）探过身以后在哪：和上面一样从下往上绕每节脊柱转，后面几节的转轴跟着挪
	func moved(sk: Skeleton3D, p: Vector3) -> Vector3:
		var pivots: Array[Vector3] = []
		for n: String in BONES:
			pivots.append(sk.global_transform * sk.get_bone_global_pose(sk.find_bone(n)).origin)
		var i := 0
		for n: String in BONES:
			var r := Basis(right.normalized(), -deg_to_rad(BONES[n]) * amount)
			p = pivots[i] + r * (p - pivots[i])
			for j in range(i + 1, pivots.size()):
				pivots[j] = pivots[i] + r * (pivots[j] - pivots[i])
			i += 1
		return p


## 右手掌转到掌心朝下、手指朝前（按住东西推），手指伸开、只微微弯一点（坐着的动画里两手十指交叉，
## 手指是蜷着的，不放开的话按下去像鸡爪）。排在右臂 IK 后面
class PalmDown extends SkeletonModifier3D:
	const CURL := 5.0                 # 伸开以后每节手指再往掌心弯的度数
	const CLOSE := 0.6                # 手指往中指那边并拢多少（0 不动，1 全并到一个方向）
	var weight := 0.0
	var fingers := Vector3.FORWARD    # 目标：手指方向、掌心朝向（世界坐标）
	var palm := Vector3.DOWN
	var _hand := -1
	var _local := []                  # 手在自己骨骼坐标里的 [手指方向, 掌心朝向]
	var _chain := []                  # 四根手指（不含拇指）的三节
	var _thumb := []

	func _setup(sk: Skeleton3D) -> void:
		_hand = sk.find_bone("Bip01 R Hand")
		var rest := sk.get_bone_global_rest(_hand)
		var f := rest.basis.inverse() * (sk.get_bone_global_rest(sk.find_bone("Bip01 R Finger2")).origin - rest.origin)
		var t := rest.basis.inverse() * (sk.get_bone_global_rest(sk.find_bone("Bip01 R Finger0")).origin - rest.origin)
		f = f.normalized()
		# 掌心：拇指 × 手指（同 crew_body.gd 的 HandGrip）
		var p := t.normalized().cross(f)
		p = (p - f * p.dot(f)).normalized()
		_local = [f, p]
		for k in [1, 2, 3, 4]:
			for suffix in ["", "1", "2"]:
				_chain.append(sk.find_bone("Bip01 R Finger%d%s" % [k, suffix]))
		for suffix in ["", "1", "2"]:
			_thumb.append(sk.find_bone("Bip01 R Finger0" + suffix))

	func _process_modification() -> void:
		var sk := get_skeleton()
		if sk == null or weight <= 0.001:
			return
		if _local.is_empty():
			_setup(sk)
		var inv := sk.global_transform.basis.inverse()
		var hp := sk.get_bone_global_pose(_hand)
		var fs: Vector3 = (inv * fingers).normalized()
		var ps: Vector3 = inv * palm
		ps = (ps - fs * ps.dot(fs)).normalized()
		var fl: Vector3 = _local[0]
		var pl: Vector3 = _local[1]
		var want := Basis(fs, ps, fs.cross(ps)) * Basis(fl, pl, fl.cross(pl)).inverse()
		var q := hp.basis.get_rotation_quaternion().slerp(want.get_rotation_quaternion(), weight)
		sk.set_bone_global_pose(_hand, Transform3D(Basis(q), hp.origin))
		# 手指、拇指先回到绑定姿势（伸开），每节再往掌心弯一点：按着东西，不是僵直的
		for b: int in _chain + _thumb:
			if b >= 0:
				var rest := sk.get_bone_rest(b).basis.get_rotation_quaternion()
				sk.set_bone_pose_rotation(b, sk.get_bone_pose_rotation(b).slerp(rest, weight))
		var hb := Basis(q)
		var axis := (hb * fl).cross(hb * pl).normalized()
		# 并拢：绑定姿势（T 字形）里五指张得很开，从正面看按着东西像爪子。食指、无名指、小指在手掌平面里往中指那边
		# 转回 CLOSE 那么多，拇指转一半
		var pn := (hb * pl).normalized()
		var mid := _dir(sk, 1)
		for k: int in [0, 2, 3]:
			_close(sk, _chain[k * 3], mid, pn, CLOSE * weight)
		if _thumb[0] >= 0 and _thumb[1] >= 0:
			var td := sk.get_bone_global_pose(_thumb[1]).origin - sk.get_bone_global_pose(_thumb[0]).origin
			_close(sk, _thumb[0], td.slide(pn).normalized().lerp(mid, 0.5).normalized(), pn, weight)
		for b: int in _chain:
			if b < 0:
				continue
			var gp := sk.get_bone_global_pose(b)
			gp.basis = Basis(axis, deg_to_rad(CURL) * weight) * gp.basis
			sk.set_bone_global_pose(b, gp)

	## 第 i 根手指（0 食指…3 小指）第一节的方向，投到手掌平面里（骨骼坐标）
	func _dir(sk: Skeleton3D, i: int) -> Vector3:
		var a: int = _chain[i * 3]
		var b: int = _chain[i * 3 + 1]
		return (sk.get_bone_global_pose(b).origin - sk.get_bone_global_pose(a).origin).normalized()

	## 骨头 b 绕掌心法线 pn 转，让它的方向往 to 靠 k（0~1）
	func _close(sk: Skeleton3D, b: int, to: Vector3, pn: Vector3, k: float) -> void:
		if b < 0:
			return
		var kids := sk.get_bone_children(b)
		if kids.is_empty():
			return
		var gp := sk.get_bone_global_pose(b)
		var d := (sk.get_bone_global_pose(kids[0]).origin - gp.origin).slide(pn).normalized()
		var t := to.slide(pn).normalized()
		var ang := d.signed_angle_to(t, pn) * k
		gp.basis = Basis(pn, ang) * gp.basis
		sk.set_bone_global_pose(b, gp)
