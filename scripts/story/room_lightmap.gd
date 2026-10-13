class_name RoomLightmap
extends RefCounted
## 岸上房间的光照贴图（LightmapGI）：运行时挂上烘好的数据、换变体、和 VoxelGI 来回切（截图对比），
## 以及 --lm-export 把房间导出成烘焙用的场景（tools/bake_lightmap.py 第一步）。从 story_room.gd 拆出来的，
## 房间这边只留子类覆盖的 lightmap_*() 钩子。
## 只烘间接光——灯的 bake_mode 是 Dynamic，直接光和阴影照旧实时算；会动的东西（门扇、吊扇、钟、人）不进贴图，
## 由烘出来的探针照亮。
## 网格指纹：导出时把每个烘进贴图的网格（顶点数、索引数、包围盒、相对房间的变换）记到 .tmp/lightmap/<份>.lmkey.json，
## 烘成功后 lightmap_baker.gd 把它放到贴图旁边（assets/gi/<份>.lmkey.json）。运行时逐个核对，模型改了没重烘
## （UV2 跟着变了，贴图对不上，会花成一块一块的）就不用这份贴图，退回 VoxelGI，并在输出里提示重烘。

const LM_BAKER := "res://scripts/tools/lightmap_baker.gd"
## 烘焙用的场景放这儿（.tmp 不进 git、编辑器也不扫描；烘好的数据在 assets/gi/）
const LM_SRC_DIR := "res://.tmp/lightmap/"
## 不进光照贴图、运行时由探针照亮的（会动的、透明的）：名字（或者祖先的名字）以这些开头。
## 门扇不在里面：关门是常态，门扇按关着烘进贴图，门洞才不漏光（门外楼道的灯不会烘到屋里地上）；
## 开门时门扇带着自己那份贴图一起转开（直接光、阴影是实时的，门扇上那点间接光的偏差看不出来）
## 灯泡（Body_LampGlass）也不进：台灯的光源点在灯泡里面（实时阴影有偏移看不出来），烘焙时光线全被灯泡挡住，台灯一点间接光都没有
const LM_DYNAMIC := ["Spin_", "Hide_", "Glass_", "Mirror_", "GaugeGlass", "Body_WindowGlass", "Body_MosquitoNet",
	"Body_LampGlass", "Body_WashWater"]
## 窗外的东西：不烘、不管（光照贴图只管屋里）
const LM_OUTSIDE := ["Body_Out_", "Anchor_Sub"]
## 指纹里的包围盒、变换允许差多少（米）：同一份模型在不同机器上算出来的摆放可能差最后几位
const KEY_TOLERANCE := 0.005
## 闪电的反弹光（见 _add_lightning_fill）
const LIGHTNING_FILL := 0.4

var room: StoryRoom
var node: LightmapGI    # 运行时的 RoomLM（截图对比切到 VoxelGI 时摘下来，不在场景树里）
var lightning_fill: OmniLight3D
var _gi_modes := {}     # 改成 Dynamic 的网格 -> 原来的 GI 模式（切回 VoxelGI 时还原）
var _data := {}         # 变体名（"" 是默认）-> LightmapGIData
var _variant := ""
var _static := {}       # 改成 Static 的灯 -> [{属性: 光照贴图用的值}, {属性: 原来的值}]（切回 VoxelGI 时还原）


func _init(r: StoryRoom) -> void:
	room = r


## 这个节点（或者它的祖先，到房间为止）的名字是不是以 prefixes 里的某个开头；人（StoryNPC）算会动的
func matches(n: Node, prefixes: Array) -> bool:
	while n and n != room:
		if n is StoryNPC:
			return prefixes == LM_DYNAMIC
		var nm := String(n.name)
		for p: String in prefixes:
			if nm.begins_with(p):
				return true
		n = n.get_parent()
	return false


## 烘进贴图的网格：模型里不动的、屋里的、有 UV2 的（导出和核对指纹用同一套条件）
func _bakeable(mi: MeshInstance3D) -> bool:
	if mi.mesh == null or matches(mi, LM_DYNAMIC) or matches(mi, LM_OUTSIDE):
		return false
	return mi.mesh is ArrayMesh and (mi.mesh.surface_get_format(0) & Mesh.ARRAY_FORMAT_TEX_UV2) != 0


# ----------------------------------------------------------------------------- 运行时
## 挂上烘好的光照贴图。节点名、层级和导出烘焙场景时一样，数据里记的路径（相对 RoomLM）原样对得上。
## 默认那份的指纹对不上就什么都不做、返回 false（房间退回 VoxelGI）
func load_data() -> bool:
	var why := _stale_reason("")
	if not why.is_empty():
		push_warning("光照贴图 %s 和模型对不上（%s），这次用 VoxelGI；跑 python tools/bake_lightmap.py %s 重烘" % [
			room.lightmap_path(), why, room.room_name])
		return false
	# 会动的东西（还有第一人称的身体）改成 Dynamic：不用贴图（也没烘它们），由 LightmapGI 的探针给间接光
	var movers: Array[Node] = room.body.find_children("*", "GeometryInstance3D", true, false)
	for g: GeometryInstance3D in room.model.find_children("*", "GeometryInstance3D", true, false):
		if matches(g, LM_DYNAMIC):
			movers.append(g)
	for g: GeometryInstance3D in movers:
		_gi_modes[g] = g.gi_mode
		g.gi_mode = GeometryInstance3D.GI_MODE_DYNAMIC
	_data[""] = load(room.lightmap_path())
	for v: String in room.lightmap_variants():
		if not ResourceLoader.exists(room.lightmap_path(v)):
			continue
		var vwhy := _stale_reason(v)
		if vwhy.is_empty():
			_data[v] = load(room.lightmap_path(v))
		else:
			push_warning("光照贴图 %s 和模型对不上（%s），这份不用" % [room.lightmap_path(v), vwhy])
	node = LightmapGI.new()
	node.name = "RoomLM"
	room.add_child(node)
	node.light_data = _data[""]
	pick_variant()
	refresh_probe()
	_add_lightning_fill()
	for l: Light3D in lights():
		var props := static_props(l)
		if props.is_empty():
			continue
		# 实时阴影留着：照在不动的东西上的影子已经烘进贴图了，但会动的东西（蚊帐、人）没有它会整片被照亮
		# （蚊帐的后片在窗框、窗帘的影子里，关了阴影它就在墙前发亮）；实测多花不到 1 毫秒
		var orig := {}
		for k: String in props:
			orig[k] = l.get(k)
		_static[l] = [props, orig]
	apply_static(true)
	return true


## 这盏灯要不要连直接光一起烘（lightmap_static_lights 里有它）：要的话给出烘焙、运行时用的属性，不要就是空的
func static_props(l: Light3D) -> Dictionary:
	var cfg := room.lightmap_static_lights()
	var cli := cli_lights()
	for k: String in cfg:
		if matches(l, [k]):
			var props: Dictionary = (cfg[k] as Dictionary).duplicate()
			props.merge(cli.get(k, {}), true)
			props["light_bake_mode"] = Light3D.BAKE_STATIC
			return props
	return {}


## 试参数：--lm-lights="Light_DeskLamp.light_indirect_energy=3;StreetGlow.light_energy=12" -> {灯名前缀: {属性: 值}}
## （烘焙、截图都带上；Static 的灯运行时也照这个改）
func cli_lights() -> Dictionary:
	var out := {}
	for item in DebugArgs.get_arg("lm-lights").split(";", false):
		var kv := item.split("=", true, 1)
		var key := kv[0].split(".", true, 1)
		if not out.has(key[0]):
			out[key[0]] = {}
		out[key[0]][key[1]] = str_to_var(kv[1])
	return out


## 光照贴图开着：这些灯用烘焙时的设置（Static）；关着（切回 VoxelGI 对比）：还原
func apply_static(on: bool) -> void:
	for l: Light3D in _static:
		var props: Dictionary = _static[l][0 if on else 1]
		for k: String in props:
			l.set(k, props[k])


## 房间退出时：截图对比时光照贴图可能正摘下来（set_mode("voxel")），一起释放
func release() -> void:
	if node and not node.is_inside_tree():
		node.free()


## 变体灯开了 / 关了：换对应的那份光照贴图（set_light 里调；日光灯启辉时那几下 0.25 的闪不换）
func pick_variant() -> void:
	if node == null:
		return
	var want := ""
	var vars := room.lightmap_variants()
	for v: String in vars:
		var l: Light3D = room.lights_by_name.get(vars[v])
		if l and l.visible and l.light_energy >= 0.5 * float(l.get_meta("base_energy", l.light_energy)):
			want = v
			break
	if want != _variant and _data.has(want):
		_variant = want
		node.light_data = _data[want]
		refresh_probe()


## 房间的反射探针（RoomProbe，只拍一次）重拍：光照贴图刚挂上、换了一份（日光灯开关）以后。光照贴图只管漫反射，
## 光滑东西上的间接反射全靠这个探针（VoxelGI 自己会实时出反射，光照贴图不会），不重拍就一直反射着原来的明暗
func refresh_probe() -> void:
	var probe := room.find_child("RoomProbe", false, false) as ReflectionProbe
	if probe == null or not room.is_inside_tree():
		return
	probe.update_mode = ReflectionProbe.UPDATE_ALWAYS
	for i in 2:
		await room.get_tree().process_frame
	probe.update_mode = ReflectionProbe.UPDATE_ONCE


## 截图对比：就地在光照贴图（"lightmap"）和 VoxelGI（"voxel"）之间切换，"off" 都关（--shots 机位的 "gi" 字段）
func set_mode(mode: String) -> void:
	var gi := room.find_child("RoomGI", false, false) as VoxelGI
	if node == null or gi == null:
		return
	var lm_on := mode == "lightmap"
	gi.visible = mode == "voxel"      # "off"：两个都关，只剩直接光（查问题用）
	if lm_on != node.is_inside_tree():
		if lm_on:
			room.add_child(node)
		else:
			room.remove_child(node)
	for g: GeometryInstance3D in _gi_modes:
		g.gi_mode = GeometryInstance3D.GI_MODE_DYNAMIC if lm_on else _gi_modes[g]
	apply_static(lm_on)
	if lightning_fill:
		lightning_fill.set_meta("off", not lm_on)
	refresh_probe()


## 闪电的反弹光：光照贴图是烘死的，闪电（实时的 DirectionalLight）照进来只有窗下地上一块亮斑，墙和顶不会跟着亮
## （VoxelGI 会实时算这次反弹）。在那块亮斑上方放一盏不投影、不出高光的补光，跟着闪电一起闪，代替地面反弹到四周的光
func _add_lightning_fill() -> void:
	var lightning := room.lightning_light()
	if lightning == null:
		return
	var win := room.pos_of("Use_Window")
	# 闪电的水平方向（从窗外往屋里），亮斑大致在窗里 1.2 米的地上
	var d := -lightning.global_basis.z
	d.y = 0.0
	lightning_fill = OmniLight3D.new()
	lightning_fill.name = "LightningFill"
	lightning_fill.light_color = lightning.light_color
	lightning_fill.omni_range = 6.0
	lightning_fill.omni_attenuation = 1.0
	lightning_fill.shadow_enabled = false
	lightning_fill.light_specular = 0.0
	lightning_fill.light_volumetric_fog_energy = 0.0
	lightning_fill.light_energy = 0.0
	lightning_fill.light_bake_mode = Light3D.BAKE_DISABLED
	lightning_fill.visible = false
	room.add_child(lightning_fill)
	lightning_fill.position = Vector3(win.x, 0.4, win.z) + d.normalized() * 1.2


# ----------------------------------------------------------------------------- 网格指纹
## 一个网格的指纹：顶点数、索引数（UV2 是导入时按网格展的，网格不变它就不变）、包围盒、相对房间的变换
func _signature(mi: MeshInstance3D) -> Dictionary:
	var v := 0
	var i := 0
	for s in mi.mesh.get_surface_count():
		v += mi.mesh.surface_get_array_len(s)
		i += mi.mesh.surface_get_array_index_len(s)
	var ab := mi.get_aabb()
	var xf := room.global_transform.affine_inverse() * mi.global_transform
	return {"v": v, "i": i, "aabb": [ab.position.x, ab.position.y, ab.position.z, ab.size.x, ab.size.y, ab.size.z],
		"xf": [xf.basis.x.x, xf.basis.x.y, xf.basis.x.z, xf.basis.y.x, xf.basis.y.y, xf.basis.y.z,
			xf.basis.z.x, xf.basis.z.y, xf.basis.z.z, xf.origin.x, xf.origin.y, xf.origin.z]}


func _same(a: Dictionary, b: Dictionary) -> bool:
	if int(a.v) != int(b.v) or int(a.i) != int(b.i):
		return false
	for k in ["aabb", "xf"]:
		var x: Array = a[k]
		var y: Array = b[k]
		if x.size() != y.size():
			return false
		for j in x.size():
			if absf(float(x[j]) - float(y[j])) > KEY_TOLERANCE:
				return false
	return true


## 这份贴图和现在的模型对不上的原因（对得上是空字符串）。没有指纹文件（旧的烘焙）当作对得上，只提示一下
func _stale_reason(variant: String) -> String:
	var path := room.lightmap_path(variant).get_basename() + ".lmkey.json"
	if not FileAccess.file_exists(path):
		push_warning("光照贴图 %s 没有指纹文件，不核对" % room.lightmap_path(variant))
		return ""
	var key: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	if not key is Dictionary or not (key as Dictionary).has("meshes"):
		return "指纹文件读不出来"
	var meshes: Dictionary = key.meshes
	for p: String in meshes:
		var mi := room.get_node_or_null(NodePath(p)) as MeshInstance3D
		if mi == null or mi.mesh == null:
			return "少了 " + p
		if not _same(_signature(mi), meshes[p]):
			return "变了 " + p
	# 新加的、没烘过的网格（只看现在显示着的：剧情里藏起来的东西导出时也不在）
	for mi: MeshInstance3D in room.model.find_children("*", "MeshInstance3D", true, false):
		if mi.is_visible_in_tree() and _bakeable(mi) and not meshes.has(String(room.get_path_to(mi))):
			return "多了 " + String(room.get_path_to(mi))
	return ""


# ----------------------------------------------------------------------------- 导出烘焙场景
## --lm-export：把房间原样导出成烘焙用的场景（tools/bake_lightmap.py 第一步），存到 .tmp/lightmap/<房间>_src.scn 后退出。
## 只要烘焙用得到的：不动的网格（Static，进贴图）、屋里的灯、环境和天光；会动的、窗外的、贴花、粒子、声音都不要。
## 节点同名、同层级、同变换（中间的挂点用空的 Node3D 占位），根节点挂 lightmap_baker.gd，带一个配好参数的 RoomLM
func export() -> void:
	# 等纸、道具都就位
	for i in 3:
		await room.get_tree().process_frame
	_export_one("")
	var vars := room.lightmap_variants() if not DebugArgs.has("lm-no-variants") else {}
	for v: String in vars:
		room.set_light(vars[v], true)
		_export_one(v)
		room.set_light(vars[v], false)
	room.get_tree().quit()


## 导出一份烘焙场景（variant：变体名，这时变体的灯已经开着）
func _export_one(variant: String) -> void:
	var root := Node3D.new()
	root.name = room.name
	root.set_script(load(LM_BAKER))
	for c in room.get_children():
		if c is WorldEnvironment:
			var we := WorldEnvironment.new()
			we.name = c.name
			we.environment = (c as WorldEnvironment).environment
			var sky := room.lightmap_sky()
			var k := float(room.lightmap_config().get("sky_energy", 1.0)) * float(DebugArgs.get_arg("lm-sky-energy", "1.0"))
			if sky or k != 1.0:
				# 烘焙用的天要真的被画出来（当背景）才有辐照度：没画过的 Sky 交给 LightmapGI 的 CUSTOM_SKY 烘出来是全黑的，
				# 所以换掉烘焙场景里的背景，LightmapGI 用 SCENE 模式
				var env := we.environment.duplicate() as Environment
				if sky:
					env.background_mode = Environment.BG_SKY
					env.sky = sky
					env.background_energy_multiplier = k
				else:
					env.background_energy_multiplier *= k
				we.environment = env
			root.add_child(we)
	var bounds := AABB()
	var meshes := 0
	var key := {}
	for mi: MeshInstance3D in room.model.find_children("*", "MeshInstance3D", true, false):
		if mi.mesh == null or not mi.is_visible_in_tree() or matches(mi, LM_DYNAMIC) or matches(mi, LM_OUTSIDE):
			continue
		if not _bakeable(mi):
			push_warning("lightmap: %s 没有 UV2（导入时 meshes/light_baking 要选 Static Lightmaps），不烘" % room.get_path_to(mi))
			continue
		_attach(root, mi, _mesh(mi))
		key[String(room.get_path_to(mi))] = _signature(mi)
		var box := mi.global_transform * mi.get_aabb()
		bounds = box if meshes == 0 else bounds.merge(box)
		meshes += 1
	var lights_n := 0
	for l: Light3D in lights():
		# 亮着、照得到屋里的灯（窗外照不到屋里的灯塔、桅灯不要；一闪一闪的不要）
		if l.is_visible_in_tree() and l.light_energy > 0.0 and l.light_bake_mode != Light3D.BAKE_DISABLED \
				and _reaches(l, bounds) and not matches(l, room.lightmap_skip_lights()):
			var dst := _light(l)
			var props := static_props(l)
			var bo := room.lightmap_bake_overrides()
			bo.merge(cli_lights(), true)
			for k: String in bo:
				if matches(l, [k]):
					props.merge(bo[k], true)
			_attach(root, l, dst)
			for k: String in props:
				dst.set(k, props[k])
			lights_n += 1
	var cli := cli_lights()
	for l: Light3D in room.lightmap_bake_lights():
		l.light_bake_mode = Light3D.BAKE_STATIC
		for k: String in cli:
			if String(l.name).begins_with(k):
				for p: String in cli[k]:
					l.set(p, cli[k][p])
		root.add_child(l)
		lights_n += 1
	var lm := LightmapGI.new()
	lm.name = "RoomLM"
	var cfg := room.lightmap_config()
	for k: String in cfg:
		if k in lm:
			lm.set(k, cfg[k])
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--lm-") and a.contains("="):
			var kv := a.substr(5).split("=", true, 1)
			if kv[0] in lm:
				lm.set(kv[0], str_to_var(kv[1]))
	var data_path := room.lightmap_path(variant)
	if not ResourceLoader.exists(data_path):
		DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(data_path.get_base_dir()))
		ResourceSaver.save(LightmapGIData.new(), data_path)
	lm.light_data = load(data_path)
	root.add_child(lm)
	for n in root.find_children("*", "", true, false):
		n.owner = root
	var ps := PackedScene.new()
	ps.pack(root)
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(LM_SRC_DIR))
	var base := LM_SRC_DIR + data_path.get_file().get_basename()
	var err := ResourceSaver.save(ps, base + "_src.scn")
	var f := FileAccess.open(base + ".lmkey.json", FileAccess.WRITE)
	if f == null:
		err = FileAccess.get_open_error()
	else:
		f.store_string(JSON.stringify({"room": room.room_name, "variant": variant, "meshes": key}, "\t", true))
		f.close()
	print("lightmap: exported %s (%d meshes, %d lights, bounds %s) err=%d" % [base + "_src.scn", meshes, lights_n,
		bounds, err])
	root.free()


## 房间里所有的灯：模型挂点上的、子类自己加的（宿舍的路灯）、天光；不算闪电和它的补光、第一人称身上的
func lights() -> Array[Light3D]:
	var out: Array[Light3D] = []
	for l: Light3D in room.find_children("*", "Light3D", true, false):
		if l != room.lightning_light() and l != lightning_fill and not (room.body and room.body.is_ancestor_of(l)):
			out.append(l)
	return out


## 灯照得到烘焙范围吗（光源到包围盒的距离不超过灯的范围）
func _reaches(l: Light3D, bounds: AABB) -> bool:
	var r := 0.0
	if l is DirectionalLight3D:
		return true
	elif l is OmniLight3D:
		r = (l as OmniLight3D).omni_range
	elif l is SpotLight3D:
		r = (l as SpotLight3D).spot_range
	elif l is AreaLight3D:
		r = (l as AreaLight3D).area_range
	var p := l.global_position
	return p.distance_to(p.clamp(bounds.position, bounds.end)) <= r


## 在烘焙场景里按 src 在房间里的路径放 dst：中间缺的挂点补一个同名、同变换的 Node3D
func _attach(root: Node3D, src: Node3D, dst: Node3D) -> void:
	var path := room.get_path_to(src)
	var at: Node3D = root
	var cur: Node = room
	for i in path.get_name_count() - 1:
		var nm := String(path.get_name(i))
		cur = cur.get_node(NodePath(nm))
		var next := at.get_node_or_null(NodePath(nm)) as Node3D
		if next == null:
			next = Node3D.new()
			next.name = nm
			next.transform = (cur as Node3D).transform
			at.add_child(next)
		at = next
	dst.name = src.name
	dst.transform = src.transform
	at.add_child(dst)


func _mesh(src: MeshInstance3D) -> MeshInstance3D:
	var mi := MeshInstance3D.new()
	mi.mesh = src.mesh
	mi.material_override = src.material_override
	for i in src.get_surface_override_material_count():
		mi.set_surface_override_material(i, src.get_surface_override_material(i))
	mi.cast_shadow = src.cast_shadow
	mi.gi_mode = GeometryInstance3D.GI_MODE_STATIC
	mi.gi_lightmap_texel_scale = src.gi_lightmap_texel_scale
	# 纸的贴图是 SubViewport 现画的，存不进场景：烘焙时换成纸的底色（反弹光只看大面颜色）
	if String(src.name).begins_with("Paper_"):
		var doc: PaperDoc = room.papers.get(String(src.name).substr(6))
		var m := StandardMaterial3D.new()
		m.albedo_color = doc.tint if doc else Color(0.9, 0.88, 0.8)
		m.roughness = 0.85
		mi.material_override = m
	return mi


## 灯复制一份（不带闪烁脚本，亮度用基础亮度）
func _light(src: Light3D) -> Light3D:
	var l := src.duplicate(0) as Light3D
	if src.get_script() == StoryRoom.FLICKER:
		l.light_energy = src.get("_base")
	l.visible = true
	return l
