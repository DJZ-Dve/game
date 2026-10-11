extends Node
## 命令行参数（`--` 之后的部分）+ 截图工具，自动加载为 DebugArgs。
## 例：Godot --path . -- --capture=shot.png --wait=120 --view=external --orbit=200
##   --capture=路径   等待若干帧后截图并退出
##   --view=external  舱外视角；--yaw/--pitch 舱内视角角度；--lights=off
##   --at=x,z         起身站在舱内这个位置（舱内局部坐标：控制舱过道 x∈[-0.56,0.56]、z∈[-1.2,1.95]；
##                    水密门在 z=2.6；生活舱过道 z∈[2.85,6.1]，见 cockpit_camera.gd）
##   --door=open      开场时水密门开着
##   --lean=0/1       贴近左/右舷窗（配合 --at 站到舷窗附近）
##   --bake-gi        重新烘焙舱内 VoxelGI（控制舱、生活舱各一个），存到 assets/gi/ 后退出
##   --cruise=油门     一直推着油门（-1~1），看艇开动起来时颗粒的拖影
##   --water=off      关掉水体吸收后处理（对比用，见 water_fx.gd）
##   --sub-yaw=度     开场把潜艇转一个角度（检查舱内 GI、贴花是不是跟着艇走）
##   --actions=帧:动作,...  按帧号自动按键（录音测试用，见 tools/record.sh）。
##                    `60:interact` 在第 60 帧按一下 E；`90:+move_forward` 按住、`150:-move_forward` 松开
##   --only-sfx=a,b / --mute-sfx=a,b  只开 / 关掉这几种声音（名字见 sub_audio.gd 的 VOL）
##   --no-hud         不显示操作提示（录给别人看的视频用）
##   --body-preview   把第一人称的身体摆到视线前方 1.3 米、面朝相机（看身体的姿势、朝向，见 crew_body.gd）
##   --sfx-log        每触发一个音效打一行 `SFX <帧号> <名字>`（tools/audio_report.py 拿它和录音对时间）
##   --look=帧:帧:度每秒[:俯仰度每秒],...  在这两帧之间按这个角速度转头（正的往左转、往上看），配合 --actions 录走动
##                    （例 `--look=120:240:40,240:420:-40`：左转三十度再右转回来；录像对比两种画面设置时输入一模一样）
##   --seed=N         随机数种子（闪电、灯闪……的随机时刻固定下来；配合 --fixed-fps 两次录像逐帧一样）
## 画面（对比用，不改 project.godot）：
##   --aa=msaa|fsr2|taa|off  抗锯齿：msaa = MSAA 2x（project.godot 的默认）；fsr2 = FSR2 原生分辨率（scale 1.0，
##                    MSAA 关）；taa = TAA（MSAA 关）；off 全关。岸上房间另外叠的 SMAA 只在没有时域抗锯齿时开
##   --fsr-sharpness=值  FSR2 的锐化（0 最锐、2 最软，默认 0.25）；--smaa=on|off 强行开关岸上的 SMAA
##   --exposure=auto|off|scale[:最低感光度[:最高感光度]]  岸上房间的自动曝光（默认按房间的 lens_config()，
##                    见 story_room.gd 的 _setup_lens；给数字是调参用，例 `--exposure=0.15:50:800`）
##   --lut=off|<路径>  岸上房间的调色 LUT：off 不挂（对比用），或换一张（比如 res://assets/textures/lut/identity_lut.png）
## 岸上的场景（--scene=dorm|office，scripts/story/）截图：
##   --at=x,z / --yaw / --pitch  站在房间局部坐标（x 东、-z 北）这一点，yaw 0 朝北、90 朝西、-90 朝东、180 朝南
##   --sit=座位名      坐到 Seat_<名字> 上（Desk、Bed、Visitor……），用坐着时的眼睛位置；--yaw/--pitch 变成相对椅子朝向的偏移
##   --shots=json      基准截图：一次启动挨个摆机位、等画面稳定、存 PNG，拍完退出（tools/bench.sh、tools/bench_views.json）。
##                    json 是机位数组，或者 {组名: 机位数组}（--shot-set 挑哪组，默认 --scene 的名字）。一个机位：
##                    {"name", "desc", "at": [x, z], "yaw", "pitch", "sit": 座位名（yaw/pitch 是相对偏移）,
##                     "tube": 宿舍日光灯开不开（默认跟 --tube）, "door": 门开多少 0~1, "fov": 视野（默认 64，坐着 54）,
##                     "free": 不限制在能站的地方, "flash": 窗外闪电的亮度（打到最亮那一下拍）, "settle": 等多少帧（默认 90）,
##                     "gi": "lightmap" / "voxel" 就地切换间接光（同一个进程里轮流比两套 GI 的帧率）,
##                     "aa": 同 --aa，就地切换抗锯齿（同一个进程里轮流比 MSAA / FSR2 的帧率）}
##   --shot-dir=目录   --shots 存到哪（<组名>_<name>.png，另写一份 <组名>_shots.json：每张的帧率、GPU 时间）
##   --shot-only=a,b   只拍这几个机位（按 name）
##   --gi=voxel|both   岸上房间的间接光：默认有烘好的光照贴图（assets/gi/<房间>.lmbake）就用 LightmapGI，
##                    voxel 强制用原来的 VoxelGI，both 两个都开（见 story_room.gd）
##   --lm-export       把房间导出成烘焙光照贴图用的场景后退出（tools/bake_lightmap.sh 第一步）；--lm-<属性>=值 改 LightmapGI 参数
##   截图（--capture、--shots）时为了每次拍出来一样：不打闪电（--lightning=on 照常随机打）、
##   闪的灯停在基础亮度（--flicker=on 照常闪）、窗外按墙上时间闪的障碍灯灭着、坐着不晃、镜子里不眨眼（见 story_room.gd）。
##   --shots 也算截图：凡是看 --capture 的地方（不放开场演出、不显示提示、不抓鼠标）一样生效。
##   bench.sh 还加了 --fixed-fps 60：游戏时间按帧走（吊扇、钟、人的动作停在同一个位置），和机器快慢无关

## --shots 第一张多等这些帧（加载、编译着色器）
const SHOT_WARMUP := 60
## 每张最后这些帧量帧时间、GPU 时间
const SHOT_MEASURE := 30

## 截图时的岸上房间（StoryRoom 就位后自己报到，--shots 等它）
var room: Node

var _args := {}
var _actions: Array = []  # [帧号, 动作名, 0 按一下 / 1 按住 / -1 松开]，按帧号排好
var _release: Array[String] = []
var _looks: Array = []    # --look：[开始帧, 结束帧, 偏航 弧度/秒, 俯仰 弧度/秒]


func _init() -> void:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--"):
			var kv := a.substr(2).split("=", true, 1)
			_args[kv[0]] = kv[1] if kv.size() > 1 else "1"
	# --shots 也是截图：各处按 --capture 判断的（跳过开场演出、不显示提示、不抓鼠标）一样生效
	if _args.has("shots") and not _args.has("capture"):
		_args["capture"] = ""


func has(key: String) -> bool:
	return _args.has(key)


func get_arg(key: String, default := "") -> String:
	return _args.get(key, default)


## 截图模式（--capture、--shots）
func capturing() -> bool:
	return has("capture")


func _ready() -> void:
	if has("seed"):
		seed(int(get_arg("seed")))
	if has("aa"):
		apply_aa(get_viewport(), get_arg("aa"))
	if has("shots"):
		_shots.call_deferred()
	elif has("capture"):
		_capture.call_deferred()
	for item in get_arg("look").split(",", false):
		var p := item.split(":")
		_looks.append([int(p[0]), int(p[1]), deg_to_rad(float(p[2])), deg_to_rad(float(p[3])) if p.size() > 3 else 0.0])
	if has("actions"):
		for item in get_arg("actions").split(",", false):
			var kv := item.split(":")
			var act := kv[1]
			var mode := 0
			if act.begins_with("+") or act.begins_with("-"):
				mode = 1 if act[0] == "+" else -1
				act = act.substr(1)
			_actions.append([int(kv[0]), act, mode])
		_actions.sort_custom(func(a: Array, b: Array) -> bool: return a[0] < b[0])
	set_process(not _actions.is_empty() or not _looks.is_empty())


func _process(delta: float) -> void:
	_look(delta)
	for act in _release:
		Input.action_release(act)
	_release.clear()
	var frame := Engine.get_process_frames()
	while not _actions.is_empty() and _actions[0][0] <= frame:
		var a: Array = _actions.pop_front()
		match a[2]:
			1:
				Input.action_press(a[1])
			-1:
				Input.action_release(a[1])
			_:
				var ev := InputEventAction.new()
				ev.action = a[1]
				ev.pressed = true
				Input.parse_input_event(ev)
				_release.append(a[1])
	if _actions.is_empty() and _release.is_empty() and _looks.is_empty():
		set_process(false)


## --look：当前相机（岸上的 RoomWalker、艇里的 cockpit_camera，都有 yaw / pitch）按角速度转
func _look(delta: float) -> void:
	var frame := Engine.get_process_frames()
	while not _looks.is_empty() and _looks[0][1] <= frame:
		_looks.pop_front()
	if _looks.is_empty() or _looks[0][0] > frame:
		return
	var cam := get_viewport().get_camera_3d()
	if cam and "yaw" in cam:
		cam.set("yaw", float(cam.get("yaw")) + _looks[0][2] * delta)
		cam.set("pitch", clampf(float(cam.get("pitch")) + _looks[0][3] * delta, deg_to_rad(-80.0), deg_to_rad(75.0)))


## 抗锯齿（--aa、机位的 "aa"）：
##   msaa  MSAA 2x（project.godot 的默认），岸上房间另外叠 SMAA（见 story_room.gd 的 _setup_lens）
##   fsr2  FSR2 原生分辨率（scale 1.0，只做时域抗锯齿不放大）：静帧里 MSAA 管不到的高光、贴图、软阴影的噪点都收得掉，
##         但没有运动矢量的雨丝会拖成一串点、走动时墙上挂历的小字糊掉（Mac 上录像实测），所以没当默认
##   taa   引擎自带的 TAA（偏糊，玻璃上的雨点会被抹掉）
##   off   全关
func apply_aa(vp: Viewport, mode: String) -> void:
	vp.msaa_3d = Viewport.MSAA_2X if mode == "msaa" else Viewport.MSAA_DISABLED
	vp.use_taa = mode == "taa"
	vp.scaling_3d_scale = 1.0
	if mode == "fsr2":
		vp.scaling_3d_mode = Viewport.SCALING_3D_MODE_FSR2
		vp.fsr_sharpness = float(get_arg("fsr-sharpness", "0.25"))
	else:
		vp.scaling_3d_mode = Viewport.SCALING_3D_MODE_BILINEAR
	if room and room.has_method("update_aa"):
		room.update_aa()


## 音效日志（--sfx-log）
func log_sfx(sfx_name: String) -> void:
	if has("sfx-log"):
		print("SFX %d %s" % [Engine.get_process_frames(), sfx_name])


## 循环音起停（--sfx-log）：`LOOP <帧号> +名字` / `-名字`
func log_loop(sfx_name: String, on: bool) -> void:
	if has("sfx-log"):
		print("LOOP %d %s%s" % [Engine.get_process_frames(), "+" if on else "-", sfx_name])


func _capture() -> void:
	for i in int(get_arg("wait", "120")):
		await get_tree().process_frame
	await RenderingServer.frame_post_draw
	var img := get_viewport().get_texture().get_image()
	img.save_png(get_arg("capture"))
	print("captured ", get_arg("capture"), "  fps ", Engine.get_frames_per_second())
	get_tree().quit()


## --shots：等房间就位 → 每个机位摆好、等 settle 帧、（打闪电）、存 PNG → 写清单 → 退出
func _shots() -> void:
	var list := _load_shots()
	if list.is_empty():
		push_error("--shots: %s 里没有机位（组 %s）" % [get_arg("shots"), _shot_set()])
		get_tree().quit(1)
		return
	var dir := get_arg("shot-dir", ProjectSettings.globalize_path("res://.tmp/shots"))
	DirAccess.make_dir_recursive_absolute(dir)
	# 主场景是宿舍：--scene=office 时宿舍先加载一下再换掉，等 --scene 要的那个房间报到
	var waited := 0
	while not is_instance_valid(room):
		await get_tree().process_frame
		waited += 1
		if waited > 1200:
			push_error("--shots: 没等到岸上的房间（只支持 --scene=dorm|office）")
			get_tree().quit(1)
			return
	seed(1998)
	var vp := get_viewport().get_viewport_rid()
	RenderingServer.viewport_set_measure_render_time(vp, true)
	var out := []
	var res := Vector2i.ZERO
	for i in list.size():
		var s: Dictionary = list[i]
		var shot_name := String(s.get("name", "%02d" % i))
		room.shot_pose(s)
		if s.has("aa"):
			apply_aa(get_viewport(), String(s.aa))
		# "debug_draw": 2 只看光照（反照率全白），查间接光、光照贴图用
		get_viewport().debug_draw = int(s.get("debug_draw", 0)) as Viewport.DebugDraw
		var settle := maxi(int(s.get("settle", 90)), 2) + (SHOT_WARMUP if i == 0 else 0)
		var measure := mini(SHOT_MEASURE, settle - 1)
		var gpu := 0.0
		var cpu := 0.0
		var t_first := 0
		for k in settle:
			await get_tree().process_frame
			if k == settle - measure - 1:
				t_first = Time.get_ticks_usec()
			elif k >= settle - measure:
				gpu += RenderingServer.viewport_get_measured_render_time_gpu(vp)
				cpu += RenderingServer.viewport_get_measured_render_time_cpu(vp)
		var t_last := Time.get_ticks_usec()
		if s.has("flash"):
			await room.shot_flash(float(s.flash))
		await RenderingServer.frame_post_draw
		var file := "%s_%s.png" % [_shot_set(), shot_name]
		var img := get_viewport().get_texture().get_image()
		img.save_png(dir.path_join(file))
		res = img.get_size()
		var frame_ms := (t_last - t_first) / 1000.0 / measure
		var rec := {"name": shot_name, "file": file, "desc": s.get("desc", ""),
			"fps": snappedf(1000.0 / maxf(frame_ms, 0.001), 0.1), "frame_ms": snappedf(frame_ms, 0.01),
			"gpu_ms": snappedf(gpu / measure, 0.01), "cpu_ms": snappedf(cpu / measure, 0.01)}
		out.append(rec)
		# GPU 时间：Mac（Metal）上量不出来，是 0 就不打
		print("shot %s  fps %.1f  frame %.1f ms%s" % [file, rec.fps, rec.frame_ms,
			"  gpu %.1f ms" % rec.gpu_ms if rec.gpu_ms > 0.0 else ""])
	var path := dir.path_join(_shot_set() + "_shots.json")
	if has("shot-only") and FileAccess.file_exists(path):
		# 只重拍了几张：清单里别的几张照旧留着，按 json 里的顺序排
		var old: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
		var taken := out.map(func(r: Dictionary) -> String: return r.name)
		var order := _load_shots(false).map(func(v: Dictionary) -> String: return String(v.get("name", "")))
		if old is Dictionary:
			for r: Dictionary in old.get("shots", []):
				if r.get("name") in order and not r.get("name") in taken:
					out.append(r)
		out.sort_custom(func(a: Dictionary, b: Dictionary) -> bool: return order.find(a.name) < order.find(b.name))
	var manifest := {"set": _shot_set(), "scene": get_arg("scene"), "resolution": [res.x, res.y], "shots": out}
	var fa := FileAccess.open(path, FileAccess.WRITE)
	fa.store_string(JSON.stringify(manifest, "  ", false))
	fa.close()
	get_tree().quit()


func _shot_set() -> String:
	return get_arg("shot-set", get_arg("scene", "dorm"))


## 读 --shots 的 json：机位数组，或者 {组名: 机位数组}；only_some：按 --shot-only 过滤
func _load_shots(only_some := true) -> Array:
	var data: Variant = JSON.parse_string(FileAccess.get_file_as_string(get_arg("shots")))
	if data is Dictionary:
		data = data.get(_shot_set(), [])
	if not data is Array:
		return []
	var only := get_arg("shot-only").split(",", false)
	var list: Array = data
	if only_some and not only.is_empty():
		list = list.filter(func(s: Dictionary) -> bool: return String(s.get("name", "")) in only)
	return list
