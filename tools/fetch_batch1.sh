#!/bin/zsh
# 第一批素材（2026-10-06 确认）
set -eu
models=(
  brass_diya_lantern caged_hanging_light vintage_radio_transceiver vintage_spacecraft_instrument
  korean_fire_extinguisher_01 modified_thermos seadogs_compass modular_electric_cables
  modular_industrial_pipes_01 antique_ceramic_vase_01 ceramic_pot brass_vase_03
  treasure_chest pocket_watch moon_rock_01 moon_rock_03 moon_rock_05
  namaqualand_boulder_02 tree_stump_02 coastal_cliff_04 dutch_ship_medium
)
textures=(coast_sand_01 brown_mud_02 dark_rock rusty_painted_metal rusty_metal_02)
${0:A:h}/fetch_polyhaven.sh --models ${(j:,:)models} --textures ${(j:,:)textures}
