# 第二批素材：写实驾驶舱（2026-10-06）
param([string]$Proxy = "http://127.0.0.1:7900")
$models = @(
    "power_box_01", "industrial_caged_sconce", "medical_box", "portable_cassette_player", "television_02",
    "retro_multimeter", "clipboard", "binder_notebook", "signal_flashlight", "plastic_thermos", "medical_tape",
    "office_notepads", "round_spectacles", "digital_wrist_watch", "old_gas_mask", "screwdriver", "pliers",
    "adjustable_wrench"
)
& (Join-Path $PSScriptRoot "fetch_polyhaven.ps1") -Models $models
$acg = @(
    "DiamondPlate008A", "Metal016", "PaintedMetal005", "Plastic012B", "Plastic018B", "Leather033A", "Fabric045",
    "Rubber004", "Fingerprints001", "Smear004", "SurfaceImperfections003", "Leaking004", "Tape001"
)
& (Join-Path $PSScriptRoot "fetch_ambientcg.ps1") -Ids $acg -Proxy $Proxy
