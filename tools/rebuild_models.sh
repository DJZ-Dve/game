#!/bin/zsh
# 重新生成自建模型（潜艇、海床）并让 Godot 重新导入。
# 用法: tools/rebuild_models.sh [submarine|seabed]
# Blender / Godot 默认在 /Applications 下，装在别处时用环境变量 BLENDER / GODOT 指定。
set -eu
only=${1:-}
if [[ -n $only && $only != (submarine|seabed) ]]; then
  echo "用法: $0 [submarine|seabed]" >&2
  exit 1
fi
root=${0:A:h:h}
blender=${BLENDER:-/Applications/Blender.app/Contents/MacOS/Blender}
source "$root/tools/godot_bg.sh"

typeset -A gens=(submarine gen_submarine.py seabed gen_seabed.py)
for k in submarine seabed; do
  [[ -n $only && $only != $k ]] && continue
  "$blender" -b --factory-startup --python "$root/blender/scripts/$gens[$k]" 2>&1 |
    grep -E "Traceback|Error|exported|line [0-9]+" || true
done

# 清掉导入缓存，确保导入后处理脚本重新套用材质
rm -f "$root"/.godot/imported/(submarine_|seabed)*(N)
"$godot" --headless --path "$root" --import 2>&1 | grep -E "ERROR|SCRIPT ERROR" || true
# 舱内模型变了，VoxelGI 要重新烘焙（需要渲染，在后台开一个屏幕外的窗口，见 godot_bg.sh）
if [[ -z $only || $only == submarine ]]; then
  godot_window --path "$root" --resolution 640x360 -- --bake-gi | grep -E "ERROR|SCRIPT ERROR|saved|baked" || true
fi
echo "rebuild done"
