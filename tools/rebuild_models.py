#!/usr/bin/env python3
"""重新生成自建模型并让 Godot 重新导入。
用法: python tools/rebuild_models.py [submarine|seabed|dorm|office|npc|giant|watcher ...]   不给参数就全部重新生成
  submarine  潜艇（外壳 + 舱内），顺带重新烘焙舱内 VoxelGI
  seabed     海床
  dorm       序章的宿舍（gen_dorm.py），顺带烘焙宿舍的 VoxelGI 和光照贴图。
             窗外 150 米以外的远景全景条（assets/textures/backdrop/）不在这里：Cycles 渲一遍要几分钟，
             改了远景单独跑 blender/scripts/render_backdrop.py（用法见文件头）
  office     第一章的东溟办事处（gen_office.py），顺带烘焙办事处的 VoxelGI 和光照贴图
  npc        沈渡（gen_npc.py，要先跑 tools/fetch_rocketbox.py）
  giant      巨物「闷雷」（gen_giant.py，部件在 blender/scripts/giant/）
  watcher    巨物「大眼」（gen_watcher.py，部件在 blender/scripts/watcher/）。只导出模型；贴图要烘时
             按部件分开跑（一次一个，单次峰值 5～9GB）：blender -b --factory-startup --python
             blender/scripts/gen_watcher.py -- --parts=shell --bake --no-export（shell / flesh / paddles / eye）
Blender、Godot 的位置见 godot_bg.py（环境变量 BLENDER、GODOT）。
"""
import glob
import os
import subprocess
import sys

import godot_bg

ROOT = godot_bg.ROOT
GENS = {"submarine": "gen_submarine.py", "seabed": "gen_seabed.py", "dorm": "gen_dorm.py", "office": "gen_office.py",
        "npc": "gen_npc.py", "giant": "gen_giant.py", "watcher": "gen_watcher.py"}
OUTS = {"submarine": "submarine_*", "seabed": "seabed*", "dorm": "dorm*", "office": "office*", "npc": "npc_*",
        "giant": "giant*", "watcher": "watcher*"}
want = sys.argv[1:] or list(GENS)
if any(k not in GENS for k in want):
    sys.exit(f"用法: python {sys.argv[0]} [{'|'.join(GENS)} ...]")

for k in want:
    gen = os.path.join(ROOT, "blender", "scripts", GENS[k])
    godot_bg.run([godot_bg.blender(), "-b", "--factory-startup", "--python", gen],
                 on_line=godot_bg.show(r"Traceback|Error|exported|line [0-9]+"))
    # 清掉导入缓存，确保导入后处理脚本重新套用材质
    for f in glob.glob(os.path.join(ROOT, ".godot", "imported", OUTS[k])):
        os.remove(f)

_, log = godot_bg.run([godot_bg.godot(), "--headless", "--audio-driver", "Dummy", "--path", ROOT, "--import"])
godot_bg.grep(log, r"ERROR|SCRIPT ERROR")
# 模型变了，VoxelGI 要重新烘焙（需要渲染，在后台开一个看不见的窗口，见 godot_bg.py）
for k in want:
    if k == "submarine":
        args = ["--", "--scene=deep_sea", "--bake-gi"]
    elif k in ("dorm", "office"):
        args = ["--", f"--scene={k}", "--bake-gi"]
    else:
        continue
    godot_bg.godot_window(["--path", ROOT, "--resolution", "640x360", *args],
                          on_line=godot_bg.show(r"ERROR|SCRIPT ERROR|saved|baked"))
# 岸上的房间用光照贴图（assets/gi/<房间>.lmbake）：模型一变，导入时重新展的 UV2 跟着变，旧的光照贴图就对不上了，
# 接着重新烘（tools/bake_lightmap.py，宿舍连日光灯开着的那份一起，两个房间一共约 6 分钟）
lm = [k for k in want if k in ("dorm", "office") and os.path.exists(os.path.join(ROOT, "assets", "gi", f"{k}.lmbake"))]
if lm and subprocess.run([sys.executable, os.path.join(ROOT, "tools", "bake_lightmap.py"), *lm]).returncode:
    sys.exit(1)
print("rebuild done")
