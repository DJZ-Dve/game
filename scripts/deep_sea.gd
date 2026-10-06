extends Node3D
## 深海测试场景：把潜艇放到海床模型里的出生点。

@onready var sub: Submarine = $Submarine


func _ready() -> void:
	var spawn := find_child("Spawn", true, false) as Node3D
	if spawn:
		sub.global_position = spawn.global_position
