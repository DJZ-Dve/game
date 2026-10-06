extends CanvasLayer
## 原型阶段的操作提示，几秒后淡出，F1 再次显示；屏幕下方显示当前能做的交互（起身、坐下、贴近舷窗）。

@onready var label: Label = $Help
@onready var prompt: Label = $Prompt

var _timer := 10.0


func _ready() -> void:
	if DebugArgs.has("capture"):
		visible = false


func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("toggle_help"):
		_timer = 10.0


func _process(delta: float) -> void:
	_timer = maxf(_timer - delta, 0.0)
	label.modulate.a = clampf(_timer / 2.0, 0.0, 1.0)
	var crew := get_tree().get_first_node_in_group("crew")
	prompt.text = crew.prompt if crew else ""
