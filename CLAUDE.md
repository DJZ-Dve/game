# 归墟 · 给 Claude 的协作笔记

这份是从 Mac 上 Claude Code 的本地记忆整理出来的（2026-10-13），开发搬到 Windows 以后靠它接上。
项目怎么跑、每个系统怎么做的见 `README.md`；玩法和设定见 `docs/design.md`（标 ❓ 的是还没定的）。
和用户交流用中文；代码注释、提交说明照仓库现有的写法（中文、说清楚为什么）。提交说明第一行是标题，**标题后空一行**再写正文。

## 迁移到 UE5（2026-10-14 起，进行中）
- 用户看了 MetaHuman 的渲染后决定整个项目迁到 **UE 5.8**（装在 `D:\Epic Games\UE_5.8`），工程在 `Unreal/`（`Guixu.uproject`）；
  Godot 版原样留着当参照，搬完再清理。下面几节讲 Godot 的规矩，UE 这边照样适用（不出声、不弹窗、素材先问）。
- 逻辑写 C++（`Unreal/Source/Guixu/`）；关卡、材质、导入用编辑器 Python 脚本搭（`Unreal/Scripts/`，每个脚本开头写了用法）；
  着色器逻辑写在 `Unreal/Shaders/*.ush`（从 .gdshader 移植，参数名、默认值不变，母材质是一个 Custom 节点 #include 它）。UE 的二进制资产走 Git LFS
- 编译：`D:\Epic Games\UE_5.8\Engine\Build\BatchFiles\Build.bat GuixuEditor Win64 Development -Project=D:\Project\Guixu\Unreal\Guixu.uproject -WaitMutex -NoHotReload`
  （VS 生成工具在 `D:\VS\BuildTools2022`，cl 实际是 14.44.35229，UE 5.8 认）
- 看效果：`py -3.13 Unreal/Scripts/ue_shot.py 任务.json`——后台桌面跑 `-game` 截图、截完退出，机位写法同 `tools/capture.py`，
  一律和 Godot 版同机位对比。编辑器里的场景捕获（render_views.py）没有 Lumen 全局光，只适合看材质
- 跑 UE 的规矩同 Godot：要渲染的走后台桌面（`ue_bg.py` / `ue_shot.py`），一律 `-nosound`；无头的用 `UnrealEditor-Cmd.exe -nullrhi`
- 已搬：潜艇驾驶舱（材质、灯、贴花、道具、仪表、数码管、声呐）、舱外和海床、开船、坐驾驶椅 / 走动 / 舱外视角。
  还没搬：海雪粒子、声呐屏上的字、水密门、破舱进水、巨物、联机、音效、船员（MetaHuman）、大厅、冰井开场、岸上场景

## 方向与画面
- **游戏方向**（2026-10-12 定）：木卫二（欧罗巴）20 公里冰壳下的 4 人合作潜艇，局域网联机，杀戮尖塔式竖向节点地图，不做 PvP。
  2026-10-13 加了战斗（小、中型生物能击杀，潜艇可武装升级），不是纯恐怖。旧的 1998 年浙东沿海、沉棺剧情已归档在 `docs/archive/`，不要再按它设计。
  用户在乎“使命感”和“画面感”，喜欢有现实科学依据的设定（冰壳厚度、潮汐、压力……），提方案时给依据。
- **画风锁定写实 PBR**：用户试玩后对现在的画质很满意（Poly Haven 贴图 + `worn_surface` 着色器 + 深海环境的体积雾/SSAO/SSIL/辉光）。
  不要建议卡通、PS1、风格化后处理；改环境参数别破坏现在的观感。
- **不要干净的金属**（用户原话：“跟干净的铁餐盘一样……看着就很简陋”）：漆面不给金属度（粗糙度 0.55~0.65），金属度只给裸钢、锻钢件；
  掉漆分层（漆 → 红丹底漆 → 钢），棱边掉漆断断续续，露出的钢发锈发暗，只有手常磨的地方亮；大平面加一点焊接变形的起伏。
  新金属件优先用 `worn_surface.gdshader` 的 primer / chip / bare_rust / paint_depth / warp 参数。
- **死亡不血腥**：被高压水压死就是直接死（参照潜渊症），不做挤爆、不出血肉。

## 平台与机器
- **目标平台是 Windows PC 独显**，性能取舍以它为准；Mac M4 只是以前的开发机，帧时间只当相对对比。
  优化先找不掉画质的（剔除、LOD、阴影范围），会掉画质的省法要先给用户看对比图。
- **Windows 开发机**：AMD Radeon RX 9070 XT（16 GB 显存，RDNA4），24 GB 内存。不是 N 卡：本地跑 PyTorch 要用 AMD 的 ROCm 版，
  依赖 CUDA 专用库（flash-attn、xformers、bitsandbytes）的项目要绕开。
- **烘焙内存**：巨物 4096 贴图的 Cycles 烘焙单次峰值 9 GB 多，以前两个烘焙并发把 16 GB 的 Mac 撑到重启过。
  同时只跑一个烘焙；总装重烘时每个部件单独开一个 Blender 进程（`--parts=X --bake --no-export`），最后再导出；烘焙期间不跑 Godot 截图。
- **Windows 上的软件**：Godot 4.7.2 在 `D:\Godot`、Blender 5.2.0 在 `D:\Blender`（`tools/godot_bg.py` 会自己找，或用环境变量
  `GODOT`、`BLENDER`）。Mac 上的 Blender 是更新的补丁版（glTF 导出器 5.2.40，这边 5.2.39），这边重新生成的模型浮点数有细微差别，
  不是改坏了；屏幕 2560×1440、系统缩放 150%。
- **`tools/` 是 Python 脚本**（2026-10-13 从 zsh 改写）：`python tools/xxx.py ...`。不写 PowerShell 脚本：PowerShell 调 .ps1 时
  `--at=0.3,1.0` 的逗号会变成数组（`1.0` 还变成 `1`）、`--` 被吃掉；调 python 这类外部程序时参数原样传。
  Python 3.13（用户目录，带 numpy、scipy、Pillow、fonttools、pyroomacoustics）、ffmpeg 都是 winget 装的，设了 `PYTHONUTF8=1`；
  新写的脚本读写文本照样写明 `encoding="utf-8"`、`newline="\n"`（别的机器、Blender 里的 Python 不一定是 UTF-8 模式）。

## 跑 Godot 的规矩
- **绝不出声**：用户的工作环境不能有声音外放（蓝牙耳机一断会回落到扬声器）。自己运行 Godot（截图、烘焙、检查声音）一律
  `--audio-driver Dummy`，或者用 `python tools/record.py`（Movie Maker 离线录制，不经过声卡）；不用任何会播放声音的命令。
  要听的东西做成文件交给用户戴耳机听；检查声音用 `tools/audio_report.py`（响度、事件对齐、频谱图）。跑 UE 命令行加 `-nosound`。
- **不弹窗、不抢焦点**：要渲染的 Godot 一律经 `tools/` 的脚本或 `godot_bg.godot_window()` 跑，它开在单独的 Windows 桌面上
  （CreateDesktop，看不见、抢不走焦点，编辑器也一样）。别直接起带窗口的 Godot：项目设置 no_focus 编辑器不认，
  `--position` 屏幕外的坐标会被夹回屏幕里；无头能做的（导入、跑脚本、联机测试）用 `--headless`。实在避免不了先告诉用户。
- 截图、录像产物放 `.tmp/`（不进 git）。

## 额度
- 用户是 Max 套餐，瓶颈是 5 小时窗口。并行子代理非常费（一次 3 个高思考子代理就吃掉 17%，10 个并行 1.5 小时吃到 76%）。
  **默认自己一个代理做，不派子代理**；确实需要并行先问用户。干活过程中查额度，过 60% 主动提醒。

## 素材与网络
- **网络慢**（Mac 上量的，Windows 这边还没量过）：PyPI 直连约 30 KB/s，ambientCG 约 40 KB/s。
  做法：先开代理（以前用 `127.0.0.1:7900`，`fetch_polyhaven.py`、`fetch_ambientcg.py` 有 `--proxy`，其余的认环境变量 `HTTPS_PROXY`）；`fetch_*.py` 断了再跑一遍会接着下（`.part` 续传）。
  **下载素材前先问用户。**
- 每引入一个外部素材都登记到 `assets/third_party/ASSET_LICENSES.md`。

## 音效
- 用户嫌 numpy 合成的“太干净”（冰井开场的继电器、冰块连做三批都不满意）。
- **首选 ElevenLabs 生成**（2026-10-13 起，用户订了 Starter 套餐，每月 4 万积分，实测大约每秒 9 积分；听了破舱那批说很喜欢）：
  `tools/gen_sfx_el.py` 批量生成，每条 3 个版本，原始文件和描述（`prompts.json`，授权凭据）存 `assets/third_party/elevenlabs/`；
  用频谱、响度初筛后交用户戴耳机挑；`tools/gen_sfx.py` 的 `*_el` 函数挑版本、裁剪、加工。额度内生成不用每次问。
  模型做不出几秒内的渐强之类的，在 `gen_sfx.py` 里后期做。
  **密钥不进 git**：放在 `~/.config/guixu/elevenlabs_key`（Windows 上是 `%USERPROFILE%\.config\guixu\elevenlabs_key`）或环境变量 `ELEVENLABS_API_KEY`；
  换机器后让用户在 ElevenLabs 后台重新生成一个（以 `sk_` 开头，只在创建时显示一次；权限要勾上音效生成和读取账户）。
  套餐页写的是“语音和音乐的商业许可”，音效是否明确包含，上架前要去服务条款里确认。
- 其次是 Freesound 的 CC0 实录（冰井的电闸就是 Freesound 131599）。
- 距离、空间感用 `tools/bake_shaft_rir.py`（pyroomacoustics）按真实几何算，别分档硬切——用户对“过渡不自然”很敏感。

## 船员的脸
- Vitruvian 开源头 + 脚本生成发片“怎么调都不好看，特别是头发”（对标逆水寒、燕云十六声）。2026-10-13 定了改用 **MetaHuman**
  （年收入 100 万美元以下免费；只能在 UE 5.6+ 编辑器里捏）。迁到 UE5 以后直接用，不再写导出到 Godot 的管线。
- UE 5.8 的 MetaHuman Creator 有 Python 接口，能无头建角色、改脸型系数（1397 个）、改皮肤 / 妆 / 发型；
  自动绑定和高清贴图在 Epic 云端算，要用户在 UE 里登录 Epic。游戏内捏脸打算在预设真人脸之间混合再微调。
  之前的捏人试验工程在 `D:\Project\GuixuMetaHuman`（可删）。Vitruvian 那套（a18eeeb）先留着能跑。

## 待办（2026-10-13 破舱原型之后，用户说下次再挑先做哪个）
- 外面那只带骨刺的生物本身（`scripts/breach.gd` 现在只有一截占位骨刺）
- 联机同步水位（主机算、广播）；水密门开着时水往另一个舱流；没穿潜水服的人当场死
- 老问题：`crew_body.gd` 的 `HEAD_LAYER = 20` 和 `water_fx.gd` 的 `POST_LAYER`（`1 << 19`）撞层，第一人称相机看不到舱外海水的吸收后处理。
  修好以后舷窗外的海会变暗变青，修之前给用户看对比图
- 老问题：第一人称抬头很高（60° 以上）能看到自己的头发
- 破舱的性能：Mac M4 上同一机位 19 → 14 帧，还没优化（以 Windows 独显为准再看）
- 设计上待定的（见 `docs/design.md` 的 ❓）：潜艇武装谁来开、武器清单、破舱的预警窗口和硬壳服
