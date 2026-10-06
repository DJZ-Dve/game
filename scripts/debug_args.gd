extends Node
## 命令行参数（`--` 之后的部分）+ 截图工具，自动加载为 DebugArgs。
## 例：Godot --path . -- --capture=shot.png --wait=120 --view=external --orbit=200
##   --capture=路径   等待若干帧后截图并退出
##   --view=external  舱外视角；--yaw/--pitch 舱内视角角度；--lights=off
##   --at=x,z         起身站在舱内这个位置（舱内局部坐标，过道 x∈[-0.56,0.56]、z∈[-1.2,1.95]）
##   --lean=0/1       贴近左/右舷窗（配合 --at 站到舷窗附近）

var _args := {}


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


func _capture() -> void:
	for i in int(get_arg("wait", "120")):
		await get_tree().process_frame
	await RenderingServer.frame_post_draw
	var img := get_viewport().get_texture().get_image()
	img.save_png(get_arg("capture"))
	print("captured ", get_arg("capture"), "  fps ", Engine.get_frames_per_second())
	get_tree().quit()
