#!/bin/zsh
# 从 Microsoft Rocketbox（MIT 许可，https://github.com/microsoft/Microsoft-Rocketbox）下载第一人称身体用的
# 角色和动画到 blender/cache/rocketbox/（不进 git；blender/scripts/gen_crew.py 读它们，导出 assets/models/crew_body.glb）。
# 用法: tools/fetch_rocketbox.sh
set -eu
root=${0:A:h:h}
dest=$root/blender/cache/rocketbox
base=https://raw.githubusercontent.com/microsoft/Microsoft-Rocketbox/master/Assets
avatar=Construction_Male_05   # 一身蓝色连体工装，改成潜艇兵的深蓝作业服
tex=m104

files=(
  Avatars/Professions/$avatar/Export/$avatar.fbx
  Avatars/Professions/$avatar/Textures/${tex}_body_color.tga
  Avatars/Professions/$avatar/Textures/${tex}_body_normal.tga
  Avatars/Professions/$avatar/Textures/${tex}_body_specular.tga
  Avatars/Professions/$avatar/Textures/${tex}_head_color.tga
  # 原地动画（根运动已去掉）：走、跑、站着、坐椅子
  Animations/all_animations_max_motextr_xy/m_walk_neutral_01.max.fbx
  Animations/all_animations_max_motextr_xy/m_run_neutral.max.fbx
  Animations/all_animations_max_motextr_static/m_idle_neutral_01.max.fbx
  Animations/all_animations_max_motextr_static/m_sit_chair_idle_neutral_01.max.fbx
)

# 先下到 .part，完整下完再改名；失败重试 3 次
for f in $files; do
  out=$dest/${f:t}
  [[ -s $out ]] && continue
  mkdir -p $dest
  for i in 1 2 3; do
    if curl -fsSL --max-time 300 -o "$out.part" "$base/$f"; then
      mv -f "$out.part" "$out"
      break
    fi
    (( i < 3 )) && echo "retry $i $f"
  done
  [[ -s $out ]] || { echo "下载失败: $f" >&2; exit 1 }
done
ls -la $dest
