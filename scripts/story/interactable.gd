class_name Interactable
extends Node3D
## 能按 E 交互的东西（看、读、坐、开门……）。放在物体的中心，RoomWalker 按「离得够近、准星差不多对着」挑出来。
## 简单的查看直接填 lines（几句心声）；要做更多事的，场景脚本连 used 信号。

signal used(it: Interactable)

@export var prompt := "查看"
## 站多近才能用（米，从眼睛量）
@export var reach := 1.6
## 物体大概多大（半径，米）：越大越好对准
@export var size := 0.12
@export var enabled := true
## 按 E 时说的几句心声（场景脚本没连 used 信号时才用）
@export var lines: PackedStringArray = []
## 看过第一遍以后换成这几句（空的话一直说 lines）
@export var lines_again: PackedStringArray = []

var times := 0


func _ready() -> void:
	add_to_group("interactable")


func activate() -> void:
	times += 1
	if used.get_connections().is_empty():
		var ls := lines_again if times > 1 and not lines_again.is_empty() else lines
		if not ls.is_empty():
			await Story.monologue(ls)
	else:
		used.emit(self)
