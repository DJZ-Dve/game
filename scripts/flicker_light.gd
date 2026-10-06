extends Light3D
## 火苗式闪烁：在基础亮度附近随机起伏，偶尔猛地一暗。

@export var amount := 0.25
@export var speed := 9.0

var _base := 1.0
var _noise := FastNoiseLite.new()
var _dip := 0.0


func _ready() -> void:
	_base = light_energy
	_noise.seed = randi()
	_noise.frequency = 0.8


func _process(delta: float) -> void:
	var t := Time.get_ticks_msec() / 1000.0
	if randf() < delta * 0.15:
		_dip = 0.6
	_dip = move_toward(_dip, 0.0, delta * 2.0)
	light_energy = _base * (1.0 + _noise.get_noise_1d(t * speed) * amount * 2.0 - _dip)
