# 打印 glTF 的节点、网格包围盒（米）和材质名，摆道具时用来查尺寸。
# 用法: pwsh tools/gltf_info.ps1 power_box_01 television_02 ...
param([Parameter(ValueFromRemainingArguments)][string[]]$Ids)
$root = Join-Path $PSScriptRoot "..\assets\third_party\polyhaven\models"
foreach ($id in $Ids) {
    $g = Get-Content (Join-Path $root "$id\${id}_2k.gltf") -Raw | ConvertFrom-Json
    Write-Host "== $id  materials: $(($g.materials | ForEach-Object name) -join ', ')"
    for ($i = 0; $i -lt $g.nodes.Count; $i++) {
        $n = $g.nodes[$i]
        $line = "  node[$i] $($n.name)"
        if ($n.translation) { $line += "  t=(" + (($n.translation | ForEach-Object { "{0:N3}" -f $_ }) -join ",") + ")" }
        if ($n.scale) { $line += "  s=(" + (($n.scale | ForEach-Object { "{0:N3}" -f $_ }) -join ",") + ")" }
        if ($null -ne $n.mesh) {
            $m = $g.meshes[$n.mesh]
            $mn = @(1e9, 1e9, 1e9); $mx = @(-1e9, -1e9, -1e9)
            foreach ($p in $m.primitives) {
                $a = $g.accessors[$p.attributes.POSITION]
                for ($k = 0; $k -lt 3; $k++) { $mn[$k] = [Math]::Min($mn[$k], $a.min[$k]); $mx[$k] = [Math]::Max($mx[$k], $a.max[$k]) }
            }
            $line += "  size=(" + ((0..2 | ForEach-Object { "{0:N3}" -f ($mx[$_] - $mn[$_]) }) -join ",") + ")"
            $line += "  min=(" + (($mn | ForEach-Object { "{0:N3}" -f $_ }) -join ",") + ")"
        }
        if ($n.children) { $line += "  children=" + ($n.children -join ",") }
        Write-Host $line
    }
}
