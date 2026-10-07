# 重新生成自建模型（潜艇、海床）并让 Godot 重新导入。
# 用法: pwsh tools/rebuild_models.ps1 [-Only submarine|seabed]
param([string]$Only = "")
$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$blender = if ($env:BLENDER) { $env:BLENDER } else { "D:\Blender\blender.exe" }
$godot = if ($env:GODOT) { $env:GODOT } else { "D:\Godot\Godot_v4.7.2-stable_win64_console.exe" }

$gens = @{ submarine = "gen_submarine.py"; seabed = "gen_seabed.py" }
foreach ($k in $gens.Keys) {
    if ($Only -and $Only -ne $k) { continue }
    $script = Join-Path $root "blender\scripts\$($gens[$k])"
    & $blender -b --factory-startup --python $script 2>&1 |
        Where-Object { $_ -match "Traceback|Error|exported|line \d+" } | ForEach-Object { Write-Host $_ }
}

# 清掉导入缓存，确保导入后处理脚本重新套用材质
$cache = Join-Path $root ".godot\imported"
if (Test-Path $cache) {
    Get-ChildItem $cache -File | Where-Object { $_.Name -like "submarine_*" -or $_.Name -like "seabed*" } |
        ForEach-Object { [IO.File]::Delete($_.FullName) }
}
& $godot --headless --path $root --import 2>&1 |
    Where-Object { $_ -match "ERROR|SCRIPT ERROR" } | ForEach-Object { Write-Host $_ }
# 舱内模型变了，VoxelGI 要重新烘焙（需要渲染，会闪一下游戏窗口）
if (-not $Only -or $Only -eq "submarine") {
    & $godot --path $root --resolution 640x360 -- --bake-gi 2>&1 |
        Where-Object { $_ -match "ERROR|SCRIPT ERROR|saved|baked" } | ForEach-Object { Write-Host $_ }
}
Write-Host "rebuild done"
