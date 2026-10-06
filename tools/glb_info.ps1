# 打印 .glb 里每个网格每个图元（材质）的顶点数和有哪些顶点属性。排查导出问题用。
# 用法: pwsh tools/glb_info.ps1 assets/models/submarine_cockpit.glb [网格名过滤]
param([Parameter(Mandatory)][string]$Path, [string]$Filter = "")
$bytes = [IO.File]::ReadAllBytes((Resolve-Path $Path))
$len = [BitConverter]::ToUInt32($bytes, 12)
$json = [Text.Encoding]::UTF8.GetString($bytes, 20, $len) | ConvertFrom-Json
foreach ($m in $json.meshes) {
    if ($Filter -and $m.name -notlike "*$Filter*") { continue }
    foreach ($p in $m.primitives) {
        $mat = if ($null -ne $p.material) { $json.materials[$p.material].name } else { "-" }
        $n = $json.accessors[$p.attributes.POSITION].count
        $attrs = ($p.attributes.PSObject.Properties.Name) -join ","
        "{0,-14} {1,-22} {2,8}  {3}" -f $m.name, $mat, $n, $attrs
    }
}
