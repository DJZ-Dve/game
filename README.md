# 归墟 Guixu

深海 · 潜艇 · 中式恐怖。Godot 4.7（Forward+）+ Blender 5.2。

## 运行
用 Godot 4.7 打开本文件夹，按 F5。主场景是 `scenes/deep_sea.tscn`。

开局坐在驾驶椅上。按 E 起身，就能在舱里走动；走回驾驶椅旁边再按 E 坐下。起身时艇不受操纵，只靠惯性漂。

| 操作 | 按键 |
|---|---|
| 前进 / 后退（驾驶） | W / S |
| 转向（驾驶） | A / D |
| 上浮 / 下潜（驾驶） | 空格 / Ctrl（或 R / C） |
| 走动（起身后） | W A S D |
| 起身 / 坐下驾驶 | E |
| 贴近舷窗 | 走到左右舷窗边，按住鼠标右键 |
| 探照灯 | F |
| 舱内 / 舱外视角 | Tab |
| 释放鼠标 / 操作提示 | Esc / F1 |

## 舱内布局
耐压舱是一段横躺的圆筒（内径 2.7 米），加上艏部半球，长约 5.5 米：
- 艏部是驾驶台：主仪表板、左右翼板、顶板报警灯牌、操纵杆，前面是驾驶椅
- 驾驶台后面左右各一个舷窗
- 两舷是嵌在舱壁里的连续工作台，开间由肋骨分隔：右舷依次是配电、生命支持、液压站、舱内环境；左舷依次是神龛、导航、照明配电、水声通信
- 后端是隔壁：水密门（通后舱）、通往顶部舱口的直梯、氧气瓶
- 尺寸都写在 `blender/scripts/cockpit.py` 开头；能站的区域在 `scripts/cockpit_camera.gd` 的 `WALK_AREAS` 里，改布局时两边要一起改

## 目录
- `blender/scripts/` 生成潜艇（`gen_submarine.py`）和海床（`gen_seabed.py`）的脚本；`blender/source/` 是生成的 .blend
- `assets/models/` 导出的 glb；`assets/materials/` 材质（由 `scripts/tools/setup_project.gd` 生成）；`assets/shaders/` 着色器
- `assets/third_party/` 外部素材，授权见 `ASSET_LICENSES.md`；Sketchfab 下载的压缩包放 `sketchfab/_inbox/`
- `scripts/` 游戏脚本；`scripts/import/post_import.gd` 是所有 glTF 导入后的处理（换材质、去 LOD）

## 常用命令（PowerShell）
```
pwsh tools/rebuild_models.ps1                 # 重新生成潜艇+海床并导入
pwsh tools/rebuild_models.ps1 -Only submarine
Godot --headless --path . --script res://scripts/tools/setup_project.gd   # 重写输入映射、重新生成材质
pwsh tools/capture.ps1 shot.png --view=external --orbit=40               # 截图
```
