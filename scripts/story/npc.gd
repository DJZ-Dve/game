class_name StoryNPC
extends Node3D
## 剧情角色（现在只有沈渡，assets/models/npc_shen.glb，见 blender/scripts/gen_npc.py）：
## - 动画：一段循环的底子（坐着待机），说话时不时插一段手势（想事情、摊手、摸脸），淡入淡出
## - 头和眼睛跟着玩家转（头慢、眼睛快），转不过去的角度就只转眼睛
## - 说话时按台词对口型：没有拼音库，按每个字的编码挑一个声母、一个韵母的口型，一秒四五个字；标点处闭嘴停一下
## - 一直挂着一点客气的笑。眨眼的形态键有，故意不用——他不眨眼
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
				mat.alpha_scissor_threshold = 0.35
				mat.alpha_antialiasing_mode = BaseMaterial3D.ALPHA_ANTIALIASING_ALPHA_TO_COVERAGE
				mat.cull_mode = BaseMaterial3D.CULL_DISABLED
				mat.roughness = 0.6
			elif n.contains("Head"):
				mat.subsurf_scatter_enabled = true
				mat.subsurf_scatter_skin_mode = true
				mat.subsurf_scatter_strength = 0.35
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
	bt.connect_node("shot", 0, "base")
	bt.connect_node("shot", 1, "gesture")
	bt.connect_node("output", 0, "shot")
	var tree := AnimationTree.new()
	tree.tree_root = bt
	add_child(tree)
	tree.anim_player = tree.get_path_to(player)
	tree.active = true
	return tree


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
	const MAX_YAW := deg_to_rad(60.0)
	const MAX_PITCH := deg_to_rad(30.0)
	const EYE_YAW := deg_to_rad(22.0)
	const EYE_PITCH := deg_to_rad(14.0)
	var target := Vector3.ZERO
	var target_node: Node3D
	var forward := Vector3.FORWARD   # 角色身体的朝向（世界坐标）
	var _yaw := 0.0
	var _pitch := 0.0
	var _eye_yaw := 0.0
	var _eye_pitch := 0.0
	var _bones := {}

	func _ready() -> void:
		var sk := get_skeleton()
		for n in ["Bip01 Neck", "Bip01 Head", "Bip01 LEye", "Bip01 REye"]:
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
		_eye_yaw = lerpf(_eye_yaw, clampf(want_yaw - _yaw, -EYE_YAW, EYE_YAW), 1.0 - exp(-dt * 18.0))
		_eye_pitch = lerpf(_eye_pitch, clampf(want_pitch - _pitch, -EYE_PITCH, EYE_PITCH), 1.0 - exp(-dt * 18.0))
		for n: String in ["Bip01 Neck", "Bip01 Head"]:
			var w := 0.4 if n == "Bip01 Neck" else 0.6
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
