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
| 跑（起身后） | 按住 Shift 往前走 |
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

## 舱外的水（`scripts/water_fx.gd`）
- **水体吸收**：全屏后处理按光程衰减颜色，红光最快、绿次之、蓝最慢，东西越远越偏蓝绿、越暗（`assets/shaders/underwater.gdshader`）。
  耐压舱里是空气，不衰减；系数在 `water_fx.gd` 的 `absorption`，几个水下着色器共用
- **光柱**：探照灯在体积雾里打出光柱。体积雾的各向异性只有 0.35，从舷窗顺着侧灯往外看也看得见光
- **颗粒**：海雪、细悬浮物两层颗粒绕着相机铺开，颗粒本身固定在世界里随洋流漂，只有被灯照到才看得见（迎着光最亮）；
  艇开起来颗粒会拉成拖影从舷窗外划过去（`assets/shaders/marine_snow.gdshader`）
- **生物发光**：零星几个蓝绿色的小光点，隔一阵亮一下再熄掉，关了探照灯才看得清（`assets/shaders/bioluminescence.gdshader`）
- 舱外视角的补光是一盏对着艇身的聚光灯（像跟拍的水下机器人），只照得到艇和艇底下一小片海床

## 舱内布局
耐压舱是一段横躺的圆筒（内径 2.7 米），加上艏部半球，长约 8 米，中间一道带水密门的隔壁分成两段：
- **控制舱**（前段）
  - 艏部是驾驶台：一体式三段环绕操纵台（主板正对驾驶椅，左右翼板往驾驶椅方向折 30°，转角共用立柱，
    下沿一道人造革扶手台沿，上沿一道帽檐），上方顶板报警灯牌，桌上操纵杆，前面是驾驶椅
    - 主板正中是机架式主动声呐显示器：圆形显像管、方位刻度环、遮光檐。声呐真的在扫：换能器每转一步往该方位打一扇射线，
      海底连成一片、礁石沉船回波强且后面留声影，艏向朝上显示，带余辉、距离环、电子方位线和读数（`sonar_display.gd`）
  - 驾驶台后面左右各一个舷窗
  - 两舷是嵌在舱壁里的连续工作台，开间由肋骨分隔：右舷依次是配电、生命支持、液压站、舱内环境；左舷依次是神龛、导航、照明配电、水声通信
  - 后端是中间隔壁：水密门、氧气瓶（紫铜管沿隔壁、舱顶接到生命支持柜）、接线盒（线顺着隔壁爬进左舷桥架）
  - 头顶：五根管子（通风、冷却水、消防水、回水、高压空气）从中间隔壁的穿舱套管出来，每道肋骨一个吊架，
    到驾驶台上方往上弯、经穿壳接管座穿出耐压壳（通风管是往下弯，接一个对着驾驶员的球形风口）；
    两舷是梯式电缆桥架，电缆平铺在横档上，从后隔壁的穿舱框（MCT）一路穿过中间隔壁，到艏部整排垂进驾驶台两边高机柜顶上的过线板；
    壳体上三个电缆穿舱件的线从外侧翻过边梁并进桥架
- **水密门**：快速水密门——中间一个手轮，经铸铁减速箱带动曲柄盘，六根连杆（带花篮螺母）同时拨动门扇四周的锻钢压紧把手，
  把手压在门框外圈的楔块上，门扇背面的胶条压在门框的刀口上；门框外两面焊补强板（鱼鳞纹角焊），门轴在左舷（两个粗铰链，带黄油嘴）。
  门扇是 18 毫米钢板，正面一圈包边、一圈加强环，背面 T 型横筋加竖筋；楔块旁刷着把手编号，把手尖和楔块外各一道红漆对位线；
  曲柄盘上的指针对着手轮下面的「关 / 开」黄铜指示牌。
  走到门前（两边都行）脸朝着门按 E 开门 / 关门（`scripts/watertight_door.gd`，连杆机构在脚本里按四连杆实时解算）：
  - 开门：先使劲掰手轮（把手咬在楔块上只挪几度），掰动了把手一起蹦开，再一把一把拧开；胶条“啵”地松开一条缝，门扇起步慢、荡开、略过头再回来
  - 关门：先拉一把、靠惯性甩过去撞上门框，弹回来一点又贴上（把手、手轮被震得晃几下）；再一把一把拧紧，
    把手骑上楔块后越拧越沉、每把转得更少，换手时手轮被顶回来一点，最后一把咬死上锁
  - 门往控制舱一侧开；门关着两段舱互不相通，过门时会低头
- **生活舱**（后段，`blender/scripts/quarters.py`）
  - 门后是过道：右舷小厨房（水槽、电炉、电饭锅、吊柜），左舷两个衣柜；头顶是出入舱口，直梯立在过道中间
  - 中段两舷各一组上下铺（布帘、床头灯）
  - 最后面右舷储物架、左舷洗手池和镜子；后隔壁上是封死的机舱检修门
- 尺寸都写在 `blender/scripts/cockpit.py` 开头；能站的区域在 `scripts/cockpit_camera.gd` 开头的几个矩形里，改布局时两边要一起改

## 第一人称（`scripts/cockpit_camera.gd`、`scripts/crew_body.gd`）
- **步伐**：按实际挪动的距离走步伐相位，步频随速度变（走 1.25 米/秒约每秒 1.7 步，跑 2.5 米/秒约 2.6 步，和动作捕捉的动画一致）；
  起步迈出半步就落脚，停下时一步迈到一半以上的会把后脚收过来落一下。跑起来镜头起伏更大更尖、视野略宽；门洞跟前跑不起来
- **身体**：低头看得见自己的身子、腿脚和双手——Microsoft Rocketbox 的角色（MIT），工装改成深海军蓝、劳保鞋改成黑皮靴
  （`blender/scripts/gen_crew.py`，先跑 `tools/fetch_rocketbox.sh` 下载原始素材）。站、走、跑、坐四段动画，
  走和跑按步伐相位定位到动画里对应的时刻，左右脚落地和脚步声对得上；坐在驾驶椅上是坐姿、手搭在腿上。
  每帧让模型的头骨落在眼睛后下方，头不渲染；身体不投影（会让照得到它的舱内灯每帧重画阴影图）
- **开关门**：走到手轮跟前、低头探身，双手握在手轮上一把一把拧（`TwoBoneIK3D` 拉手臂，手掌转到握轮缘的朝向、手指弯起来），
  换手时沿轮缘滑回去；控制舱这边门扇朝人甩过来，开门时往右后方让开，关门时先站在右后方伸手够，抓住手轮推上，再上前拧紧。
  调试用 `--body-preview` 把身体摆到视线前方看姿势

## 声音（`scripts/sub_audio.gd`）
音效全部是程序化合成的（`tools/gen_sfx.py`，只用 numpy），写到 `assets/audio/`；`sub_audio.gd` 负责摆位置、按游戏状态调音量音高。
- **环境声**：艇体低鸣（深水压在耐压壳上的低频）、头顶球形风口的出风、右舷配电柜的变压器嗡声、
  闪烁的那根坏灯管的电流声（音量跟着灯闪）、漏水滴到地板积水里的“嘀”（和水珠落地的时刻对齐，见 `cockpit_props.gd`）
- **航行**：推进电机（音高跟转速）、艇外水流（跟航速）、螺旋桨搅水（七叶桨的叶频）、按住上浮/下潜时的压载泵（有起停爬升）
- **艇壳**：每隔一阵来一声低沉的吱嘎或“嘣”，升降、转向时更勤；撞礁有整个艇壳的嗡鸣和刮擦
- **主动声呐**：扫描线每转回艏向一圈 ping 一声（从艏部换能器方向传来）：950 Hz 的低沉纯音，后面是海里多径反射的长余音，2 秒后一声远处回波
- **交互**：水密门（掰手轮时机构绷紧的闷哼、把手从楔块上蹦开、减速箱齿轮咬合和摩擦、胶条松开的气压“噗”、
  铰链低沉的“嘎——”、门扇快关上时挤出的风、撞上门框的重击（门扇最低六十赫兹的“咚”、隔壁和艇壳的低频轰鸣、金属余音、气压一压、把手叮当）、
  弹回再贴上的一下、拧紧时把手在楔块上刮、最后上锁：把手压死的一串闷响 + 减速箱顶到头的“哐” + 棘爪落下的“咔哒”），
  脚步（按落脚的地面挑：过道中间的扁钢格栅——一串很密的亮“嚓”、格栅在框上颠一下；两边 6 mm 花纹钢板——板的模态、底下空舱的嗡声、
  没压实的钢板在龙骨上磕一下；门洞里的厚钢门槛——闷而短的“咚”。走路脚跟先着地、脚掌跟着落下，跑步更硬更快、最后蹬地蹭一下，
  停下时收脚轻轻一放；每一步都带工装布料擦一下的沙沙声）、探照灯拨杆开关
- **总线**（`default_bus_layout.tres`）：`Cabin` 舱里的声音（小钢舱的短混响），下面分 `CabinFwd`、`CabinAft` 两个舱，
  水密门关着时听者不在的那个舱隔着门闷掉；`Sea` 艇外的水声，在舱里只剩隔着艇壳的低频，贴近舷窗亮一点。
  切到舱外视角时反过来：舱里的声音闷掉，水声全开。Master 上一个 -1 dB 的限幅器
- 循环音在 Godot 里导入成不压缩的 PCM，循环终点后面接了 16 个循环开头的采样：默认的 QOA 压缩、
  以及变调时插值读到终点之后，都会让每圈接缝处出一个毛刺（`gen_sfx.py` 里有说明）

### 不用耳朵检查声音
`tools/record.sh` 用 Godot 的 Movie Maker 离线录一段（固定 60 帧/秒逐帧渲染，音频直接混进文件，**不经过声卡，绝不出声**），
`--actions` 按帧号自动按键；`tools/audio_report.py` 分析录音：响度（LUFS、真峰值、削波）、每 0.5 秒的响度、
孤立的咔哒声（接缝、硬起停、断音）、每个音效事件在录音里的起音延迟和显著度（< 6 dB 基本就是被别的声音盖住了），
可以输出频谱图。`--only-sfx=` / `--mute-sfx=` 只开 / 关掉某几种声音，用来单独查某一路。
后台跑的 Godot（`godot_bg.sh`）一律用 Dummy 音频驱动，截图、烘焙时也不会出声。

## 目录
- `blender/scripts/` 生成潜艇（`gen_submarine.py` 外壳，`cockpit.py` 控制舱，`quarters.py` 生活舱）和海床（`gen_seabed.py`）的脚本；`blender/source/` 是生成的 .blend
- 铺位上的床单、被子、枕头、布帘、毛巾是用 Blender 布料模拟摆出来的（`blender/scripts/bedding.py`），床垫是带绗缝凹坑的软垫；
  模拟结果缓存在 `blender/cache/`（不进仓库），参数不变就不重算，第一次生成会多花十几秒。布料材质见 `assets/shaders/fabric.gdshader`
- `assets/models/` 导出的 glb；`assets/materials/` 材质（由 `scripts/tools/setup_project.gd` 生成）；`assets/shaders/` 着色器
- `assets/textures/decals/` 舱内贴花（水渍圈、脚印、锈水、喷漆字……），由 `scripts/tools/gen_decals.gd` 生成；
  贴在哪、多大写在 `cockpit.py` 的 `decals()` 里（导出成 `Decal_*` 挂点）
- `assets/gi/cabin_gi.res`、`cabin_gi_aft.res` 控制舱、生活舱 VoxelGI 的烘焙数据（改了舱内模型要重新烘焙，`rebuild_models.sh` 会自动做；舱外视角时舱内 GI 会关掉，免得渗到艇身外表面上）
- `assets/third_party/` 外部素材，授权见 `ASSET_LICENSES.md`；Sketchfab 下载的压缩包放 `sketchfab/_inbox/`
- `scripts/` 游戏脚本；`scripts/import/post_import.gd` 是所有 glTF 导入后的处理（换材质、去 LOD）

## 开发环境（macOS）
- Godot **4.7.2**（版本要一致，否则导入设置、场景文件会被改写）、Blender 5.2、Git LFS：
  `brew install --cask godot blender`、`brew install git-lfs && git lfs install`
- tools/ 下都是 zsh 脚本，只用到系统自带的 curl、jq、unzip。Godot / Blender 默认在 `/Applications`，
  装在别处时用环境变量 `GODOT`、`BLENDER` 指定可执行文件（`.app/Contents/MacOS/` 里那个）
- 生成模型、贴花文字用的字体都在 `blender/fonts/`（SIL OFL），不依赖系统字体

## 常用命令
```
tools/rebuild_models.sh                       # 重新生成潜艇+海床并导入（潜艇会顺带重新烘焙舱内 VoxelGI）
tools/rebuild_models.sh submarine
godot --path . --script res://scripts/tools/gen_decal_text.gd             # 重新画贴花的文字底图（会闪一下窗口）
godot --headless --path . --script res://scripts/tools/gen_decals.gd      # 重新生成贴花贴图
godot --path . -- --bake-gi                   # 只重新烘焙舱内 VoxelGI
godot --headless --path . --script res://scripts/tools/setup_project.gd   # 重写输入映射、重新生成材质
tools/capture.sh shot.png --view=external --orbit=40                      # 截图（后台运行、不弹窗；FOREGROUND=1 前台；其余参数见 scripts/debug_args.gd）
tools/glb_info.sh assets/models/submarine_cockpit.glb [网格名]            # 查看 glb 里的网格、顶点数
tools/fetch_polyhaven.sh --models a,b --textures c,d                      # 下载 Poly Haven 素材（ambientCG 用 fetch_ambientcg.sh --ids）
tools/fetch_rocketbox.sh && blender -b --factory-startup --python blender/scripts/gen_crew.py   # 重新生成第一人称的身体
python3 tools/gen_sfx.py [名字前缀...]                                   # 重新合成音效（之后让 Godot 导入一次：godot --headless --path . --import）
tools/record.sh .tmp/door 12 --at=0,2.0 --yaw=180 --actions=30:interact   # 离线录一段画面+声音（.mp4/.wav/.log），不出声
python3 tools/audio_report.py .tmp/door.wav --log .tmp/door.log --png .tmp/door.png   # 分析录音
```
