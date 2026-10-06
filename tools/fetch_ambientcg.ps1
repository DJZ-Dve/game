# 从 ambientCG (CC0) 下载材质到 assets/third_party/ambientcg/<id>/
# 用法: pwsh tools/fetch_ambientcg.ps1 -Ids DiamondPlate008A,Metal016 [-Res 2K] [-Proxy http://127.0.0.1:7900]
# 只保留 Color / NormalGL / Roughness / Metalness / AmbientOcclusion / Opacity。
param(
    [Parameter(Mandatory)][string[]]$Ids,
    [string]$Res = "2K",
    [string]$Proxy = ""
)
$ErrorActionPreference = "Stop"
$root = Join-Path $PSScriptRoot "..\assets\third_party\ambientcg"
New-Item -ItemType Directory -Force $root | Out-Null
$web = @{ TimeoutSec = 300 }
if ($Proxy) { $web.Proxy = $Proxy }
$keep = "_(Color|NormalGL|Roughness|Metalness|AmbientOcclusion|Opacity)\.(jpg|png)$"

foreach ($id in $Ids) {
    $dir = Join-Path $root $id
    if (Test-Path (Join-Path $dir "*_Color.*")) { Write-Host "skip   $id"; continue }
    New-Item -ItemType Directory -Force $dir | Out-Null
    $zip = Join-Path ([IO.Path]::GetTempPath()) "$id.zip"
    for ($i = 1; ; $i++) {
        try { Invoke-WebRequest "https://ambientcg.com/get?file=${id}_$Res-JPG.zip" -OutFile $zip @web; break }
        catch { if ($i -ge 3) { throw }; Write-Host "retry $i $id" }
    }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $z = [IO.Compression.ZipFile]::OpenRead($zip)
    try {
        foreach ($e in $z.Entries) {
            if ($e.Name -match $keep) {
                [IO.Compression.ZipFileExtensions]::ExtractToFile($e, (Join-Path $dir $e.Name), $true)
            }
        }
    } finally { $z.Dispose() }
    [IO.File]::Delete($zip)
    Write-Host "texture $id"
}
