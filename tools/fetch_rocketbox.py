#!/usr/bin/env python3
"""从 Microsoft Rocketbox（MIT 许可，https://github.com/microsoft/Microsoft-Rocketbox）下载角色和动画到
blender/cache/rocketbox/（不进 git）：
  - 船员的身体，男女两套（blender/scripts/gen_crew.py → assets/models/crew_body_m.glb、crew_body_f.glb；
    头是 Vitruvian 的，见 tools/fetch_vitruvian.py）
  - 剧情角色沈渡（blender/scripts/gen_npc.py → assets/models/npc_shen.glb）
用法: python tools/fetch_rocketbox.py
"""
import os
import sys

from fetch_util import download

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(ROOT, "blender", "cache", "rocketbox")
BASE = "https://raw.githubusercontent.com/microsoft/Microsoft-Rocketbox/master/Assets"
ANIM = "Animations/all_animations_max_motextr_static"  # 原地动画（根运动已去掉）

crew, crew_tex = "Construction_Male_05", "m104"     # 一身蓝色连体工装，改成潜艇兵的深蓝作业服
crew_f, crew_f_tex = "Construction_Female_01", "f101"  # 女船员：蓝工装、黄色反光马甲、劳保手套
shen, shen_tex = "Business_Male_02", "m008"         # 东亚面孔、深色西装：沈渡。用带表情形态键的 _facial 版（口型、眨眼、微笑）

files = [
    f"Avatars/Professions/{crew}/Export/{crew}.fbx",
    f"Avatars/Professions/{crew}/Textures/{crew_tex}_body_color.tga",
    f"Avatars/Professions/{crew}/Textures/{crew_tex}_body_normal.tga",
    f"Avatars/Professions/{crew}/Textures/{crew_tex}_body_specular.tga",
    f"Avatars/Professions/{crew}/Textures/{crew_tex}_head_color.tga",
    f"Avatars/Professions/{crew_f}/Export/{crew_f}.fbx",
    f"Avatars/Professions/{crew_f}/Textures/{crew_f_tex}_body_color.tga",
    f"Avatars/Professions/{crew_f}/Textures/{crew_f_tex}_body_normal.tga",
    # 走、跑、站着、坐椅子
    "Animations/all_animations_max_motextr_xy/m_walk_neutral_01.max.fbx",
    "Animations/all_animations_max_motextr_xy/m_run_neutral.max.fbx",
    f"{ANIM}/m_idle_neutral_01.max.fbx",
    f"{ANIM}/m_sit_chair_idle_neutral_01.max.fbx",

    f"Avatars/Professions/{shen}/Export/{shen}_facial.fbx",
    f"Avatars/Professions/{shen}/Textures/{shen_tex}_body_color.tga",
    f"Avatars/Professions/{shen}/Textures/{shen_tex}_body_normal.tga",
    f"Avatars/Professions/{shen}/Textures/{shen_tex}_head_color.tga",
    f"Avatars/Professions/{shen}/Textures/{shen_tex}_head_normal.tga",
    f"Avatars/Professions/{shen}/Textures/{shen_tex}_opacity_color.tga",
    # 坐在桌子后面：待机、呼吸、想事情、摊手、摸脸、等人；站着说话
    f"{ANIM}/m_sit_table_idle_neutral_01.max.fbx",
    f"{ANIM}/m_sit_table_breathe_01.max.fbx",
    f"{ANIM}/m_sit_table_gestic_thoughtful.max.fbx",
    f"{ANIM}/m_sit_table_gestic_shrug_01.max.fbx",
    f"{ANIM}/m_sit_table_idle_touch_face.max.fbx",
    f"{ANIM}/m_sit_table_idle_waiting_01.max.fbx",
    f"{ANIM}/m_idle_neutral_02.max.fbx",
    f"{ANIM}/m_gestic_talk_neutral_01.max.fbx",
]

for f in files:
    if not download(f"{BASE}/{f}", os.path.join(DEST, os.path.basename(f))):
        sys.exit(f"下载失败: {f}")
for name in sorted(os.listdir(DEST)):
    print(f"{os.path.getsize(os.path.join(DEST, name)):>12,}  {name}")
