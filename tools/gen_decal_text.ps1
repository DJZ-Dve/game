# 生成贴花用的文字底图（白字、透明底），给 scripts/tools/gen_decals.gd 再加喷漆的磨损、飞白。
# 用法: pwsh tools/gen_decal_text.ps1
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$out = Join-Path $root "assets\textures\decals\src"
New-Item -ItemType Directory -Force $out | Out-Null

# name, 文字, 字体, 宽, 高, 箭头(0 无 / 1 朝右 / -1 朝左), 竖排
$items = @(
    @("c03", "C-03", "Stencil", 1024, 410, 0, $false),
    @("fire", "严禁烟火", "Noto Sans SC Black", 256, 1024, 0, $true),
    @("cool", "冷却水", "Noto Sans SC Black", 1024, 174, 1, $false),
    @("firewater", "消防水", "Noto Sans SC Black", 1024, 174, 1, $false),
    @("return", "冷却回水", "Noto Sans SC Black", 1024, 174, -1, $false),
    @("air", "送风", "Noto Sans SC Black", 1024, 376, 1, $false)
)

foreach ($it in $items) {
    $name, $text, $fontName, $w, $h, $arrow, $vertical = $it
    $bmp = New-Object System.Drawing.Bitmap $w, $h, ([System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.Clear([System.Drawing.Color]::Transparent)
    $g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $brush = [System.Drawing.Brushes]::White
    $fmt = New-Object System.Drawing.StringFormat
    $fmt.Alignment = [System.Drawing.StringAlignment]::Center
    $fmt.LineAlignment = [System.Drawing.StringAlignment]::Center
    if ($vertical) {
        # 竖排：一个字一行
        $n = $text.Length
        $cell = $h / $n
        $font = New-Object System.Drawing.Font($fontName, [single]($cell * 0.62), [System.Drawing.FontStyle]::Regular, [System.Drawing.GraphicsUnit]::Pixel)
        for ($i = 0; $i -lt $n; $i++) {
            $rect = New-Object System.Drawing.RectangleF(0, [single]($i * $cell), $w, [single]$cell)
            $g.DrawString($text.Substring($i, 1), $font, $brush, $rect, $fmt)
        }
    } else {
        $textW = if ($arrow -ne 0) { $w * 0.62 } else { $w * 0.94 }
        $size = $h * 0.78
        do {
            $font = New-Object System.Drawing.Font($fontName, [single]$size, [System.Drawing.FontStyle]::Regular, [System.Drawing.GraphicsUnit]::Pixel)
            $m = $g.MeasureString($text, $font)
            $size *= 0.95
        } while ($m.Width -gt $textW)
        $x0 = if ($arrow -eq -1) { $w - $textW - $w * 0.03 } elseif ($arrow -eq 1) { $w * 0.03 } else { ($w - $textW) / 2 }
        $rect = New-Object System.Drawing.RectangleF([single]$x0, 0, [single]$textW, [single]$h)
        $g.DrawString($text, $font, $brush, $rect, $fmt)
        if ($arrow -ne 0) {
            # 流向箭头：杆 + 三角头
            $ax0 = if ($arrow -eq 1) { $w * 0.68 } else { $w * 0.32 }
            $ax1 = if ($arrow -eq 1) { $w * 0.97 } else { $w * 0.03 }
            $cy = $h / 2
            $shaft = $h * 0.14
            $head = $h * 0.36
            $hx = $ax1 - $arrow * $head * 1.1
            $pts = @(
                [System.Drawing.PointF]::new($ax0, $cy - $shaft), [System.Drawing.PointF]::new($hx, $cy - $shaft),
                [System.Drawing.PointF]::new($hx, $cy - $head), [System.Drawing.PointF]::new($ax1, $cy),
                [System.Drawing.PointF]::new($hx, $cy + $head), [System.Drawing.PointF]::new($hx, $cy + $shaft),
                [System.Drawing.PointF]::new($ax0, $cy + $shaft))
            $g.FillPolygon($brush, $pts)
        }
    }
    $g.Dispose()
    $bmp.Save((Join-Path $out "$name.png"), [System.Drawing.Imaging.ImageFormat]::Png)
    $bmp.Dispose()
    Write-Host "text $name"
}
