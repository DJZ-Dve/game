# 启动游戏、等待若干帧后截图并退出。其余参数原样传给游戏（见 scripts/debug_args.gd）。
# 用法: pwsh tools/capture.ps1 out.png --view=external --orbit=135
param([Parameter(Mandatory)][string]$Out, [Parameter(ValueFromRemainingArguments)][string[]]$Rest)
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$godot = if ($env:GODOT) { $env:GODOT } else { "D:\Godot\Godot_v4.7.2-stable_win64_console.exe" }
$wait = "--wait=150"
& $godot --path $root --resolution 1600x900 -- "--capture=$Out" $wait @Rest 2>&1 |
    Where-Object { $_ -match "ERROR|SCRIPT|captured" } | ForEach-Object { Write-Host $_ }
