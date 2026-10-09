extends Node3D
## 第一人称的身体：低头看得见自己的身子、腿脚和手（assets/models/crew_body.glb，Rocketbox 的角色改成潜艇兵，
## 见 blender/scripts/gen_crew.py）。挂在 Body 下面，坐标和 cockpit_camera.gd 一样是舱内局部坐标。
## - 动画：站着（idle）、走（walk）、跑（run）、坐（sit）四段，走和跑不按时间播，而是按相机的步伐相位（gait_steps）
##   直接定位到动画里对应的时刻，左右脚落地和脚步声对得上
## - 位置：每帧让模型的头骨落在眼睛（相机）后下方一点；站着时脚踩地板只对齐水平位置，坐着时整个对齐。
##   低头时身体再往后让一点，免得看见胸腔里面；头本身不渲染（第一人称看不见自己的脸）
## - 开关门时两只手握在手轮上（TwoBoneIK3D 拉肩—肘—腕，HandGrip 把手掌转到握轮缘的朝向、手指弯起来），
##   跟着手轮一把一把转，换手时沿轮缘滑回去；手轮够不着时手伸过去够，够得着才握上（见 watertight_door.gd 的 grip_point）
## - 不投影：身体一直有呼吸、走路的动作，要投影的话照得到它的每盏舱内灯都得每帧重画整舱的阴影图

const BODY := preload("res://assets/models/crew_body.glb")
const DECK_Y := -0.9
## 走、跑动画里左脚跟落地在循环里的位置（gen_crew.py 算的，见 assets/models/crew_body_gait.json）
const WALK_L := 0.694
const RUN_L := 0.348
## 头骨（Bip01 Head 关节，在耳朵附近）相对眼睛：往后、往下
const HEAD_BACK := 0.12
const HEAD_DOWN := 0.07
## 低头看脚时身体往后让的距离
const LOOK_DOWN_BACK := 0.06

@export var camera_path: NodePath

var _cam: Camera3D
var _skel: Skeleton3D
var _head := -1
var _tree: AnimationTree
var _yaw := 0.0
var _move := 0.0
var _walk_len := 1.0
var _run_len := 1.0
# 手：0 左 1 右
var _ik: Array[TwoBoneIK3D] = []
var _target: Array[Marker3D] = []
var _pole: Array[Marker3D] = []
var _grip: HandGrip
var _lean: SpineLean
var _hand_w := [0.0, 0.0]
var _held := 0.0
var _shoulder := [-1, -1]
var _arm_len := 0.6


func _ready() -> void:
	_cam = get_node(camera_path)
	var model := BODY.instantiate() as Node3D
	add_child(model)
	_skel = model.find_children("*", "Skeleton3D", true, false)[0]
	_head = _skel.find_bone("Bip01 Head")
	for g in model.find_children("*", "GeometryInstance3D", true, false):
		(g as GeometryInstance3D).cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	var head := model.find_child("Crew_Head", true, false) as Node3D
	if head:
		head.visible = false
	var player := model.find_children("*", "AnimationPlayer", true, false)[0] as AnimationPlayer
	for n in ["idle", "walk", "run", "sit"]:
		player.get_animation(n).loop_mode = Animation.LOOP_LINEAR
	_walk_len = player.get_animation("walk").length
	_run_len = player.get_animation("run").length
	_tree = _build_tree(player)
	_yaw = _cam.yaw
	_setup_hands()


func _setup_hands() -> void:
	for i in 2:
		var s := "L" if i == 0 else "R"
		var t := Marker3D.new()
		var p := Marker3D.new()
		add_child(t)
		add_child(p)
		var ik := TwoBoneIK3D.new()
		_skel.add_child(ik)
		ik.setting_count = 1
		ik.set_root_bone_name(0, "Bip01 %s UpperArm" % s)
		ik.set_middle_bone_name(0, "Bip01 %s Forearm" % s)
		ik.set_end_bone_name(0, "Bip01 %s Hand" % s)
		ik.set_target_node(0, ik.get_path_to(t))
		ik.set_pole_node(0, ik.get_path_to(p))
		ik.influence = 0.0
		_ik.append(ik)
		_target.append(t)
		_pole.append(p)
		_shoulder[i] = _skel.find_bone("Bip01 %s UpperArm" % s)
	_lean = SpineLean.new()
	_skel.add_child(_lean)
	_skel.move_child(_lean, 0)   # 先弯腰，IK 再按弯过以后的肩膀去够
	var r := func(b: String) -> Vector3: return _skel.get_bone_global_rest(_skel.find_bone(b)).origin
	_arm_len = r.call("Bip01 L UpperArm").distance_to(r.call("Bip01 L Forearm")) \
		+ r.call("Bip01 L Forearm").distance_to(r.call("Bip01 L Hand"))
	_grip = HandGrip.new()
	_skel.add_child(_grip)   # 排在 IK 后面：IK 先把手腕拉到位，再转手掌、弯手指


## 动画混合：idle ←move→ (walk ←gait→ run)，再 ←seat→ sit；walk、run 前面各接一个定位节点
func _build_tree(player: AnimationPlayer) -> AnimationTree:
	var bt := AnimationNodeBlendTree.new()
	for n in ["idle", "walk", "run", "sit"]:
		var a := AnimationNodeAnimation.new()
		a.animation = n
		bt.add_node(n, a)
	for n in ["walk", "run"]:
		bt.add_node(n + "_seek", AnimationNodeTimeSeek.new())
		bt.connect_node(n + "_seek", 0, n)
	for n in ["gait", "move", "seat"]:
		bt.add_node(n, AnimationNodeBlend2.new())
	bt.connect_node("gait", 0, "walk_seek")
	bt.connect_node("gait", 1, "run_seek")
	bt.connect_node("move", 0, "idle")
	bt.connect_node("move", 1, "gait")
	bt.connect_node("seat", 0, "move")
	bt.connect_node("seat", 1, "sit")
	bt.connect_node("output", 0, "seat")
	var tree := AnimationTree.new()
	tree.tree_root = bt
	add_child(tree)
	tree.anim_player = tree.get_path_to(player)
	tree.active = true
	return tree


func _process(delta: float) -> void:
	var sit: float = _cam.sit_amount()
	var speed: float = _cam.gait_speed
	var steps: float = _cam.gait_steps
	_move = move_toward(_move, smoothstep(0.05, 0.5, speed / 1.25), delta * 5.0)
	_tree.set("parameters/walk_seek/seek_request", fposmod(WALK_L + steps * 0.5, 1.0) * _walk_len)
	_tree.set("parameters/run_seek/seek_request", fposmod(RUN_L + steps * 0.5, 1.0) * _run_len)
	_tree.set("parameters/gait/blend_amount", _cam.gait_run)
	_tree.set("parameters/move/blend_amount", _move)
	_tree.set("parameters/seat/blend_amount", sit)

	# 朝向：走动时身子跟着视线转（略慢半拍），坐着时朝驾驶台，开关门时对着门
	var want: float = lerp_angle(_cam.door_yaw if _cam.door_op else _cam.yaw, 0.0, sit)
	_yaw = lerp_angle(_yaw, want, 1.0 - exp(-delta * (10.0 if speed > 0.2 else 6.0)))
	rotation = Vector3(0.0, _yaw, 0.0)

	# 位置：头骨落在眼睛后下方
	var eye := _cam.position
	var look := Vector3(-sin(_cam.yaw), 0.0, -cos(_cam.yaw))
	var back := HEAD_BACK + LOOK_DOWN_BACK * smoothstep(-0.2, -1.1, _cam.pitch)
	var want_head := eye - look * back - Vector3.UP * HEAD_DOWN
	var head_world := _skel.global_transform * _skel.get_bone_global_pose(_head).origin
	var head_rel := get_parent_node_3d().global_transform.affine_inverse() * head_world - position
	var p := want_head - head_rel
	p.y = lerpf(DECK_Y, p.y, sit)
	position = p
	_update_hands(delta)
	if DebugArgs.has("body-preview"):
		# 调试：把身体摆到视线前方 1.3 米、转过来面朝相机，从外面看姿势和朝向
		position += look * 1.3
		rotation.y += PI



## 开关门时两只手的目标：握点（跟着手轮转，换手时沿轮缘滑回去）→ 手腕位置、手掌朝向；够不着就伸过去够
func _update_hands(delta: float) -> void:
	_lean.amount = smoothstep(0.0, 1.0, _cam.door_lean)
	_lean.right = global_transform.basis.x
	var door = _cam.get("_door")
	var want: bool = door != null and _cam.door_op and door.hands
	var held := 0.0
	if want:
		held = door.wheel_angle() - door.grip
		# 手跟着手轮转就紧跟；换手时（held 往 0 回）手松开沿轮缘滑回去
		_held = held if absf(held) >= absf(_held) else lerpf(_held, held, 1.0 - exp(-delta * 10.0))
	for i in 2:
		var w := 0.0
		if want:
			var g: Array = door.grip_point(i, _cam.door_aft, _held)
			var point: Vector3 = g[0]
			var radial: Vector3 = g[1]
			var toward: Vector3 = g[2]
			# 手腕在轮缘外侧、靠人这边一点；手指从外往里、往手轮面上包过去，掌心对着轮缘
			var wrist := point + radial * 0.055 + toward * 0.045
			var shoulder := _skel.global_transform * _skel.get_bone_global_pose(_shoulder[i]).origin
			var d := shoulder.distance_to(wrist)
			# 够不着时手伸过去（手腕停在伸直的地方），越近越使劲；太远就不伸了
			w = smoothstep(_arm_len * 1.7, _arm_len * 1.02, d)
			if d > _arm_len * 0.98:
				wrist = shoulder + (wrist - shoulder).normalized() * _arm_len * 0.98
			_target[i].global_position = wrist
			var side := global_transform.basis.x * (-1.0 if i == 0 else 1.0)
			_pole[i].global_position = shoulder + side * 0.45 + Vector3.DOWN * 0.35 + toward * 0.15
			var fingers := (-radial - toward * 0.5).normalized()
			_grip.set_target(i, fingers, -toward, smoothstep(_arm_len * 1.15, _arm_len * 0.98, d))
		_hand_w[i] = move_toward(_hand_w[i], w, delta * (4.0 if w > _hand_w[i] else 3.0))
		_ik[i].influence = smoothstep(0.0, 1.0, _hand_w[i])
		_grip.weight[i] = _ik[i].influence * _grip.grasp[i]


## 握手轮的手：把手掌转到掌心对着轮缘、手指往里包，四根手指弯起来（拇指不动）。排在两个 IK 后面
class HandGrip extends SkeletonModifier3D:
	const CURL := [deg_to_rad(50.0), deg_to_rad(75.0), deg_to_rad(55.0)]
	var weight := [0.0, 0.0]
	var grasp := [0.0, 0.0]
	var _fingers := [Vector3.ZERO, Vector3.ZERO]   # 目标：手指方向、掌心朝向（世界坐标）
	var _palm := [Vector3.ZERO, Vector3.ZERO]
	var _local := []      # 每只手在自己骨骼坐标里的 [手指方向, 掌心朝向]
	var _hand := [-1, -1]
	var _chains := [[], []]

	func set_target(i: int, fingers: Vector3, palm: Vector3, g: float) -> void:
		_fingers[i] = fingers
		_palm[i] = palm
		grasp[i] = g

	func _setup(sk: Skeleton3D) -> void:
		_local = []
		for i in 2:
			var s := "L" if i == 0 else "R"
			var h := sk.find_bone("Bip01 %s Hand" % s)
			_hand[i] = h
			var rest := sk.get_bone_global_rest(h)
			var f := rest.basis.inverse() * (sk.get_bone_global_rest(sk.find_bone("Bip01 %s Finger2" % s)).origin - rest.origin)
			var t := rest.basis.inverse() * (sk.get_bone_global_rest(sk.find_bone("Bip01 %s Finger0" % s)).origin - rest.origin)
			f = f.normalized()
			# 掌心：拇指 × 手指（Biped 的左右手骨骼是镜像的，两只手算法一样）
			var p := t.normalized().cross(f)
			p = (p - f * p.dot(f)).normalized()
			_local.append([f, p])
			var chains := []
			for k in [1, 2, 3, 4]:
				chains.append([sk.find_bone("Bip01 %s Finger%d" % [s, k]), sk.find_bone("Bip01 %s Finger%d1" % [s, k]),
					sk.find_bone("Bip01 %s Finger%d2" % [s, k])])
			_chains[i] = chains

	func _process_modification() -> void:
		var sk := get_skeleton()
		if sk == null:
			return
		if _local.is_empty():
			_setup(sk)
		var inv := sk.global_transform.basis.inverse()
		for i in 2:
			var w: float = weight[i]
			if w <= 0.001:
				continue
			var hp := sk.get_bone_global_pose(_hand[i])
			var fs: Vector3 = (inv * _fingers[i]).normalized()
			var ps: Vector3 = inv * _palm[i]
			ps = (ps - fs * ps.dot(fs)).normalized()
			var fl: Vector3 = _local[i][0]
			var pl: Vector3 = _local[i][1]
			var want := Basis(fs, ps, fs.cross(ps)) * Basis(fl, pl, fl.cross(pl)).inverse()
			var q := hp.basis.get_rotation_quaternion().slerp(want.get_rotation_quaternion(), w)
			sk.set_bone_global_pose(_hand[i], Transform3D(Basis(q), hp.origin))
			# 手指往掌心弯：绕「手指 × 掌心」转（转过去手指就朝掌心那边）
			var hb := Basis(q)
			var axis := (hb * fl).cross(hb * pl).normalized()
			for chain in _chains[i]:
				for j in 3:
					var b: int = chain[j]
					var gp := sk.get_bone_global_pose(b)
					gp.basis = Basis(axis, CURL[j] * w) * gp.basis
					sk.set_bone_global_pose(b, gp)


## 拧手轮时弯腰：三节脊柱各往前弯一点（绕身体的左右轴），肩膀往前下方去。排在 IK 前面
class SpineLean extends SkeletonModifier3D:
	const BONES := {"Bip01 Spine": 7.0, "Bip01 Spine1": 8.0, "Bip01 Spine2": 6.0}
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
