@tool
extends Node3D
## 无人值守烘焙 LightmapGI。LightmapGI 的烘焙只有编辑器里那个「烘焙光照贴图」按钮能触发（4.7 没有给脚本的接口），
## 所以分两步（tools/bake_lightmap.py）：
##   1. 游戏跑起来，房间按挂点摆好道具、灯、纸以后，把要烘的东西原样（同名、同层级、同变换）导出成一个烘焙用的场景
##      （story_room.gd 的 --lm-export），根节点挂这个脚本，带一个配好参数、light_data 指向 assets/gi/<房间>.lmbake 的 LightmapGI；
##   2. 后台开编辑器（godot_bg.py：不抢焦点、Dummy 音频）打开这个场景，带 `-- --bake-lightmap=<这个场景的路径>`：这里找到
##      LightmapGI 编辑器插件的烘焙按钮按下去，烘完（贴图存到 .lmbake 旁边的 .exr）退出。
## 运行时 story_room.gd 新建同名的 LightmapGI、把烘好的数据挂上；节点路径和导出时一样，光照贴图能对上每个网格。
## 手动在编辑器里打开这个场景不会自动烘（没有 --bake-lightmap），可以自己按按钮重烘、看探针。
## 编辑器启动时会把上次开着的场景也恢复出来（比如上一次烘的另一个房间）：只有路径和 --bake-lightmap 给的一样、
## 而且正在编辑的是自己的那一份才烘，不然两份都去按按钮，烘到哪个文件就说不准了。

func _ready() -> void:
	if not Engine.is_editor_hint():
		return
	var want := ""
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--bake-lightmap="):
			want = a.get_slice("=", 1)
	if want.is_empty() or scene_file_path != want:
		return
	_bake.call_deferred()


func _bake() -> void:
	# 用主循环等帧（这一份可能被换到后台标签页、出了场景树，那时取不到场景树）
	var tree := Engine.get_main_loop() as SceneTree
	var ei := Engine.get_singleton("EditorInterface")
	if ei == null:
		return
	# 等编辑器把场景、着色器都准备好，并且正在编辑的是这一份
	var waited := 0
	while waited < 30 or ei.get_edited_scene_root() != self:
		await tree.process_frame
		waited += 1
		if waited > 600:
			printerr("lightmap: 等了 600 帧，编辑器正在编辑的还不是 %s" % scene_file_path)
			tree.quit(1)
			return
	var lm := find_child("RoomLM", false, false) as LightmapGI
	if lm == null:
		printerr("lightmap: 场景里没有 RoomLM")
		tree.quit(1)
		return
	# 选中 LightmapGI，插件才知道烘哪个（按钮只在编辑 LightmapGI 时出现）
	ei.edit_node(lm)
	for i in 5:
		await tree.process_frame
	var btn := _find_bake_button(ei.get_base_control())
	if btn == null:
		printerr("lightmap: 找不到 LightmapGI 插件的烘焙按钮")
		tree.quit(1)
		return
	var path := lm.light_data.resource_path if lm.light_data else ""
	print("lightmap: baking %s → %s  quality %d  bounces %d  texel_scale %.2f  directional %s" % [
		name, path, lm.quality, lm.bounces, lm.texel_scale, lm.directional])
	var t0 := Time.get_ticks_msec()
	btn.pressed.emit()   # 同步烘完才返回
	var data := lm.light_data
	if data == null or data.get_user_count() == 0:
		printerr("lightmap: 烘焙失败（没有数据），看上面编辑器的报错")
		tree.quit(1)
		return
	var tex: TextureLayered = data.lightmap_textures[0] if not data.lightmap_textures.is_empty() else null
	print("lightmap baked in %.1f s: %d meshes, %s, saved %s" % [(Time.get_ticks_msec() - t0) / 1000.0,
		data.get_user_count(), "%dx%d x%d layers" % [tex.get_width(), tex.get_height(), tex.get_layers()]
		if tex else "no texture", data.resource_path])
	# 导出时记下的网格指纹（<房间>_src.scn 旁边的 <房间>.lmkey.json）放到贴图旁边：运行时拿它核对模型有没有改过
	var key := scene_file_path.get_basename().trim_suffix("_src") + ".lmkey.json"
	if FileAccess.file_exists(key):
		var dst := path.get_basename() + ".lmkey.json"
		var err := DirAccess.copy_absolute(ProjectSettings.globalize_path(key), ProjectSettings.globalize_path(dst))
		print("lightmap: key %s err=%d" % [dst, err])
		if err != OK:
			tree.quit(1)
			return
	tree.quit()


## 编辑器里所有按钮中，pressed 连到 LightmapGIEditorPlugin 的那个（不按文字找：编辑器可能是中文界面）
func _find_bake_button(n: Node) -> Button:
	if n is Button:
		for c: Dictionary in n.get_signal_connection_list("pressed"):
			var o := (c.callable as Callable).get_object()
			if o and o.get_class() == "LightmapGIEditorPlugin":
				return n
	for ch in n.get_children(true):
		var b := _find_bake_button(ch)
		if b:
			return b
	return null
