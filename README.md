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

## 外观
一艘退役的老式军用小潜艇，艇长约 14 米：单壳体（耐压壳就是艇身），水线以上黑漆、以下红色防污漆；
背上一道带流水孔的上层建筑（甲板），中前部一座高围壳（围壳舵、潜望镜、通气管、天线上系着红布条）；
艉部十字尾舵 + 七叶大侧斜螺旋桨。螺旋桨跟着推进转，方向舵、升降舵跟着转向、上浮下潜偏转（`submarine.gd`）。
外形参数在 `blender/scripts/gen_submarine.py` 开头（艇身半径、艏尖、艉锥、水线、围壳位置）。

## 舱内布局
耐压舱是一段横躺的圆筒（内径 2.7 米），加上艏部半球，长约 8 米，中间一道带水密门的隔壁分成两段：
- **控制舱**（前段）
  - 艏部是驾驶台：主仪表板、左右翼板、顶板报警灯牌、操纵杆，前面是驾驶椅
  - 驾驶台后面左右各一个舷窗
  - 两舷是嵌在舱壁里的连续工作台，开间由肋骨分隔：右舷依次是配电、生命支持、液压站、舱内环境；左舷依次是神龛、导航、照明配电、水声通信
  - 后端是中间隔壁：水密门、氧气瓶、接线盒
- **水密门**：走到门前（两边都行）脸朝着门按 E 开门 / 关门。开门先转手轮再推开门扇，门往控制舱一侧开；
  门关着两段舱互不相通，过门时会低头（`scripts/watertight_door.gd`）
- **生活舱**（后段，`blender/scripts/quarters.py`）
  - 门后是过道：右舷小厨房（水槽、电炉、电饭锅、吊柜），左舷两个衣柜；头顶是出入舱口，直梯立在过道中间
  - 中段两舷各一组上下铺（布帘、床头灯）
  - 最后面右舷储物架、左舷洗手池和镜子；后隔壁上是封死的机舱检修门
- 尺寸都写在 `blender/scripts/cockpit.py` 开头；能站的区域在 `scripts/cockpit_camera.gd` 开头的几个矩形里，改布局时两边要一起改

## 目录
- `blender/scripts/` 生成潜艇（`gen_submarine.py` 外壳，`cockpit.py` 控制舱，`quarters.py` 生活舱）和海床（`gen_seabed.py`）的脚本；`blender/source/` 是生成的 .blend
- `assets/models/` 导出的 glb；`assets/materials/` 材质（由 `scripts/tools/setup_project.gd` 生成）；`assets/shaders/` 着色器
- `assets/textures/decals/` 舱内贴花（水渍圈、脚印、锈水、喷漆字……），由 `scripts/tools/gen_decals.gd` 生成；
  贴在哪、多大写在 `cockpit.py` 的 `decals()` 里（导出成 `Decal_*` 挂点）
- `assets/gi/cabin_gi.res`、`cabin_gi_aft.res` 控制舱、生活舱 VoxelGI 的烘焙数据（改了舱内模型要重新烘焙，`rebuild_models.ps1` 会自动做；舱外视角时舱内 GI 会关掉，免得渗到艇身外表面上）
- `assets/third_party/` 外部素材，授权见 `ASSET_LICENSES.md`；Sketchfab 下载的压缩包放 `sketchfab/_inbox/`
- `scripts/` 游戏脚本；`scripts/import/post_import.gd` 是所有 glTF 导入后的处理（换材质、去 LOD）

## 常用命令（PowerShell）
```
pwsh tools/rebuild_models.ps1                 # 重新生成潜艇+海床并导入（潜艇会顺带重新烘焙舱内 VoxelGI）
pwsh tools/rebuild_models.ps1 -Only submarine
pwsh tools/gen_decal_text.ps1; Godot --headless --path . --script res://scripts/tools/gen_decals.gd   # 重新生成贴花贴图
Godot --path . -- --bake-gi                   # 只重新烘焙舱内 VoxelGI
Godot --headless --path . --script res://scripts/tools/setup_project.gd   # 重写输入映射、重新生成材质
pwsh tools/capture.ps1 shot.png --view=external --orbit=40               # 截图
```
