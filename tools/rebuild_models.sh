#!/bin/zsh
# 重新生成自建模型并让 Godot 重新导入。
# 用法: tools/rebuild_models.sh [submarine|seabed|dorm|office|npc ...]   不给参数就全部重新生成
#   submarine  潜艇（外壳 + 舱内），顺带重新烘焙舱内 VoxelGI
#   seabed     海床
#   dorm       序章的宿舍（gen_dorm.py），顺带烘焙宿舍的 VoxelGI
#   office     第一章的东溟办事处（gen_office.py），顺带烘焙办事处的 VoxelGI
#   npc        沈渡（gen_npc.py，要先跑 tools/fetch_rocketbox.sh）
# Blender / Godot 默认在 /Applications 下，装在别处时用环境变量 BLENDER / GODOT 指定。
set -eu
all=(submarine seabed dorm office npc)
want=(${@:-$all})
for k in $want; do
  if (( ! ${all[(Ie)$k]} )); then
    echo "用法: $0 [${(j:|:)all} ...]" >&2
    exit 1
  fi
done
root=${0:A:h:h}
blender=${BLENDER:-/Applications/Blender.app/Contents/MacOS/Blender}
source "$root/tools/godot_bg.sh"

typeset -A gens=(submarine gen_submarine.py seabed gen_seabed.py dorm gen_dorm.py office gen_office.py
  npc gen_npc.py)
typeset -A outs=(submarine "submarine_*" seabed "seabed*" dorm "dorm*" office "office*" npc "npc_*")
for k in $want; do
  "$blender" -b --factory-startup --python "$root/blender/scripts/$gens[$k]" 2>&1 |
    grep -E "Traceback|Error|exported|line [0-9]+" || true
  # 清掉导入缓存，确保导入后处理脚本重新套用材质
  rm -f "$root"/.godot/imported/${~outs[$k]}(N)
done

"$godot" --headless --audio-driver Dummy --path "$root" --import 2>&1 | grep -E "ERROR|SCRIPT ERROR" || true
# 模型变了，VoxelGI 要重新烘焙（需要渲染，在后台开一个屏幕外的窗口，见 godot_bg.sh）
for k in $want; do
  case $k in
    submarine) args=(-- --scene=deep_sea --bake-gi) ;;
    dorm|office) args=(-- --scene=$k --bake-gi) ;;
    *) continue ;;
  esac
  godot_window --path "$root" --resolution 640x360 $args | grep -E "ERROR|SCRIPT ERROR|saved|baked" || true
done
echo "rebuild done"
