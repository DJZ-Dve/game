@tool
extends EditorScenePostImport
## 所有 glTF/glb 导入后都会经过这里（在 project.godot 的 importer_defaults 里设置）：
## 1. 自建模型：材质名以 M_ 开头的，换成 assets/materials/ 下的同名材质。
## 2. 外部环境素材（岩石、沉船、沉木……）：换成带「海雪沉积」的材质。
## 3. 只保留 LOD0（Poly Haven 有些模型把 LOD1~3 也放在同一个文件里）。

const MATERIAL_DIR := "res://assets/materials/"
const SILTED_SHADER := "res://assets/shaders/silted_pbr.gdshader"
const SILT_TEXTURE := "res://assets/third_party/polyhaven/textures/coast_sand_01/coast_sand_01_diff_2k.jpg"
const SILTED_ASSETS := ["moon_rock", "boulder", "cliff", "dutch_ship", "tree_stump", "treasure_chest",
	"ceramic", "vase"]


func _post_import(scene: Node) -> Object:
	var file := get_source_file().get_file()
	var silted := false
	for key: String in SILTED_ASSETS:
		if file.contains(key):
			silted = true
	_strip_lods(scene)
	_fix_materials(scene, silted)
	return scene


func _strip_lods(node: Node) -> void:
	for child in node.get_children():
		var n := String(child.name)
		var i := n.rfind("_LOD")
		if i >= 0 and n.substr(i + 4) != "0":
			node.remove_child(child)
			child.free()
		else:
			_strip_lods(child)


func _fix_materials(node: Node, silted: bool) -> void:
	if node is MeshInstance3D and node.mesh:
		var mesh: Mesh = node.mesh
		for i in mesh.get_surface_count():
			var m := mesh.surface_get_material(i)
			var r := _replace(m, silted)
			if r:
				mesh.surface_set_material(i, r)
	elif node is ImporterMeshInstance3D and node.mesh:
		var im: ImporterMesh = node.mesh
		for i in im.get_surface_count():
			var r := _replace(im.get_surface_material(i), silted)
			if r:
				im.set_surface_material(i, r)
	for c in node.get_children():
		_fix_materials(c, silted)


func _replace(m: Material, silted: bool) -> Material:
	if m == null:
		return null
	var path := MATERIAL_DIR + m.resource_name + ".tres"
	if m.resource_name.begins_with("M_") and ResourceLoader.exists(path):
		return load(path)
	if silted and m is BaseMaterial3D and m.transparency == BaseMaterial3D.TRANSPARENCY_DISABLED:
		var b := m as BaseMaterial3D
		var s := ShaderMaterial.new()
		s.resource_name = m.resource_name + "_silted"
		s.shader = load(SILTED_SHADER)
		s.set_shader_parameter("albedo_tex", b.albedo_texture)
		s.set_shader_parameter("albedo_tint", b.albedo_color)
		s.set_shader_parameter("normal_tex", b.normal_texture)
		if b.roughness_texture:
			s.set_shader_parameter("orm_tex", b.roughness_texture)
			s.set_shader_parameter("has_orm", true)
		s.set_shader_parameter("base_roughness", b.roughness)
		s.set_shader_parameter("silt_albedo", load(SILT_TEXTURE))
		return s
	return null
