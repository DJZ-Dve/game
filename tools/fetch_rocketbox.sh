#!/bin/zsh
# 从 Microsoft Rocketbox（MIT 许可，https://github.com/microsoft/Microsoft-Rocketbox）下载角色和动画到
# blender/cache/rocketbox/（不进 git）：
#   - 第一人称的身体（blender/scripts/gen_crew.py → assets/models/crew_body.glb）
#   - 剧情角色沈渡（blender/scripts/gen_npc.py → assets/models/npc_shen.glb）
# 用法: tools/fetch_rocketbox.sh
set -eu
root=${0:A:h:h}
dest=$root/blender/cache/rocketbox
base=https://raw.githubusercontent.com/microsoft/Microsoft-Rocketbox/master/Assets
anim=Animations/all_animations_max_motextr_static   # 原地动画（根运动已去掉）

crew=Construction_Male_05   # 一身蓝色连体工装，改成潜艇兵的深蓝作业服
crew_tex=m104
shen=Business_Male_02       # 东亚面孔、深色西装：沈渡。用带表情形态键的 _facial 版（口型、眨眼、微笑）
shen_tex=m008
face=Police_Male_05         # 主角周海生的脸（东亚面孔、短发），头换到工装身体上；帽子去掉
face_tex=m169

files=(
  Avatars/Professions/$crew/Export/$crew.fbx
  Avatars/Professions/$crew/Textures/${crew_tex}_body_color.tga
  Avatars/Professions/$crew/Textures/${crew_tex}_body_normal.tga
  Avatars/Professions/$crew/Textures/${crew_tex}_body_specular.tga
  Avatars/Professions/$crew/Textures/${crew_tex}_head_color.tga
  # 走、跑、站着、坐椅子
  Animations/all_animations_max_motextr_xy/m_walk_neutral_01.max.fbx
  Animations/all_animations_max_motextr_xy/m_run_neutral.max.fbx
  $anim/m_idle_neutral_01.max.fbx
  $anim/m_sit_chair_idle_neutral_01.max.fbx

  Avatars/Professions/$face/Export/${face}_facial.fbx
  Avatars/Professions/$face/Textures/${face_tex}_head_color.tga
  Avatars/Professions/$face/Textures/${face_tex}_head_normal.tga

  Avatars/Professions/$shen/Export/${shen}_facial.fbx
  Avatars/Professions/$shen/Textures/${shen_tex}_body_color.tga
  Avatars/Professions/$shen/Textures/${shen_tex}_body_normal.tga
  Avatars/Professions/$shen/Textures/${shen_tex}_head_color.tga
  Avatars/Professions/$shen/Textures/${shen_tex}_head_normal.tga
  Avatars/Professions/$shen/Textures/${shen_tex}_opacity_color.tga
  # 坐在桌子后面：待机、呼吸、想事情、摊手、摸脸、等人；站着说话
  $anim/m_sit_table_idle_neutral_01.max.fbx
  $anim/m_sit_table_breathe_01.max.fbx
  $anim/m_sit_table_gestic_thoughtful.max.fbx
  $anim/m_sit_table_gestic_shrug_01.max.fbx
  $anim/m_sit_table_idle_touch_face.max.fbx
  $anim/m_sit_table_idle_waiting_01.max.fbx
  $anim/m_idle_neutral_02.max.fbx
  $anim/m_gestic_talk_neutral_01.max.fbx
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
