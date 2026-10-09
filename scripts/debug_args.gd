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

var _args := {}
var _actions: Array = []  # [帧号, 动作名, 0 按一下 / 1 按住 / -1 松开]，按帧号排好
var _release: Array[String] = []


func _init() -> void:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--"):
			var kv := a.substr(2).split("=", true, 1)
			_args[kv[0]] = kv[1] if kv.size() > 1 else "1"


func has(key: String) -> bool:
	return _args.has(key)


func get_arg(key: String, default := "") -> String:
	return _args.get(key, default)


func _ready() -> void:
	if has("capture"):
		_capture.call_deferred()
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
	set_process(not _actions.is_empty())


func _process(_delta: float) -> void:
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
	if _actions.is_empty() and _release.is_empty():
		set_process(false)


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
