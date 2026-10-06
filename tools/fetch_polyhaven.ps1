# 从 Poly Haven (CC0) 下载模型和贴图到 assets/third_party/polyhaven/
# 用法: pwsh tools/fetch_polyhaven.ps1 -Models a,b -Textures c,d [-Res 2k]
param(
    [string[]]$Models = @(),
    [string[]]$Textures = @(),
    [string]$Res = "2k"
)
$ErrorActionPreference = "Stop"
$root = Join-Path $PSScriptRoot "..\assets\third_party\polyhaven" | Resolve-Path -ErrorAction SilentlyContinue
if (-not $root) { $root = New-Item -ItemType Directory -Force (Join-Path $PSScriptRoot "..\assets\third_party\polyhaven") }
$root = "$root"

function Get-File($url, $dest) {
    if (Test-Path $dest) { return }
    New-Item -ItemType Directory -Force (Split-Path $dest) | Out-Null
    # 先下到 .part，完整下完再改名，断线不会留下半截文件；失败重试 3 次
    for ($i = 1; ; $i++) {
        try {
            Invoke-WebRequest $url -OutFile "$dest.part" -TimeoutSec 300
            Move-Item -Force "$dest.part" $dest
            return
        } catch {
            if ($i -ge 3) { throw }
            Write-Host "retry $i $url"
        }
    }
}

foreach ($id in $Models) {
    $files = Invoke-RestMethod "https://api.polyhaven.com/files/$id"
    $g = $files.gltf.$Res.gltf
    $dir = Join-Path $root "models\$id"
    Get-File $g.url (Join-Path $dir ([IO.Path]::GetFileName($g.url)))
    if ($g.include) {
        foreach ($p in $g.include.PSObject.Properties) {
            Get-File $p.Value.url (Join-Path $dir $p.Name)
        }
    }
    Write-Host "model  $id"
}

# 贴图只取颜色、法线(OpenGL)、ARM(AO/粗糙度/金属度) 三张
foreach ($id in $Textures) {
    $files = Invoke-RestMethod "https://api.polyhaven.com/files/$id"
    $dir = Join-Path $root "textures\$id"
    foreach ($map in "Diffuse", "nor_gl", "arm") {
        $m = $files.$map.$Res.jpg
        if ($m) { Get-File $m.url (Join-Path $dir ([IO.Path]::GetFileName($m.url))) }
    }
    Write-Host "texture $id"
}
