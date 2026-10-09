@tool
extends Node3D
## 根据海床模型里的放置点（Place__素材名__编号）实例化 Poly Haven 素材，并在运行时加碰撞。
## 放置点由 blender/scripts/gen_seabed.py 生成。编辑器里也会显示（不保存进场景）。

const MODEL := "res://assets/third_party/polyhaven/models/%s/%s_2k.gltf"
## 用三角网格碰撞的素材（其余用凸包）
const TRIMESH := ["dutch_ship_medium", "coastal_cliff_04"]
## 太小的东西不加碰撞
const NO_COLLISION := ["pocket_watch", "brass_vase_03"]

var _cache := {}


func _ready() -> void:
	_populate()


func _populate() -> void:
	var count := 0
	for marker in find_children("Place__*", "Node3D", true, false):
		if marker.get_child_count() > 0:
			continue
		var parts := String(marker.name).split("__")
		if parts.size() < 2:
			continue
		var asset := parts[1]
		var scene := _load(asset)
		if scene == null:
			continue
		var inst := scene.instantiate() as Node3D
		marker.add_child(inst)  # 不设 owner：不写进场景文件
		count += 1
		if not Engine.is_editor_hint() and asset not in NO_COLLISION:
			_add_collision(inst, asset in TRIMESH)
	if not Engine.is_editor_hint():
		print("seabed props: ", count)
		Submarine.add_layer(self, Submarine.SEABED_LAYER)


func _load(asset: String) -> PackedScene:
	if not _cache.has(asset):
		var path := MODEL % [asset, asset]
		_cache[asset] = load(path) if ResourceLoader.exists(path) else null
		if _cache[asset] == null:
			push_warning("缺少素材 " + path)
	return _cache[asset]


func _add_collision(root: Node3D, trimesh: bool) -> void:
	for mi in root.find_children("*", "MeshInstance3D", true, false):
		var m := mi as MeshInstance3D
		if m.mesh == null:
			continue
		var body := StaticBody3D.new()
		body.add_to_group("sonar_hard")  # 声呐上当硬目标（回波强、后面有声影），见 sonar_display.gd
		var shape := CollisionShape3D.new()
		shape.shape = m.mesh.create_trimesh_shape() if trimesh else m.mesh.create_convex_shape(true, true)
		body.add_child(shape)
		m.add_child(body)
