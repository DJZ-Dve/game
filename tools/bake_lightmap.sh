#!/bin/zsh
# 烘焙岸上房间的 LightmapGI（间接光烘成光照贴图，直接光和阴影仍然实时；见 scripts/tools/lightmap_baker.gd）。
# 用法: tools/bake_lightmap.sh office [dorm ...]
#       tools/bake_lightmap.sh office -- --lm-quality=3 --lm-texel_scale=1.5   （-- 后面的参数原样传给导出那一步，见 story_room.gd：
#         --lm-<LightmapGI 属性>=值、--lm-sky-energy=倍数、--lm-lights="WindowSky.light_energy=0.5;StreetGlow.light_energy=8"）
#       SCENE=res://.tmp/x.tscn tools/bake_lightmap.sh                   （只做第二步：烘一个现成的场景）
#       tools/bake_lightmap.sh dorm -- --lm-dir=res://lmexp/t1/ --lm-no-variants   （试参数：烘到别的目录、只烘默认那份；
#         截图时也带 --lm-dir，见 story_room.gd。目录不能以点开头：编辑器不导入隐藏目录里的贴图）
# 两步，都在后台跑（godot_bg.sh：不抢焦点、Dummy 音频）：
#   1. 游戏把房间（连同运行时摆上去的道具、灯、纸）导出成 .tmp/lightmap/<房间>_src.scn（--lm-export）
#   2. 编辑器打开它，按 LightmapGI 插件的烘焙按钮，烘好的数据存到 assets/gi/<房间>.lmbake + .exr，退出
# 编辑器用单独一份全局设置（.godot/lightmap_editor/，不碰 ~/Library/Application Support/Godot）。
# 模型、道具的 UV2 由导入时生成（.import 里 meshes/light_baking=2），模型改了跑 rebuild_models.sh（它最后会调这个脚本重烘）。
# 材质（反照率）、灯、窗光参数（dorm.gd / office.gd 的 lightmap_*）改了也要重烘。同样的输入烘出来逐字节一样，不会凭空多出 git 改动。
# 耗时（M4）：办事处约 1.5 分钟，宿舍两份（日光灯关 / 开）约 4 分钟。
set -eu
root=${0:A:h:h}
source "$root/tools/godot_bg.sh"
rooms=()
extra=()
seen_dash=0
for a in "$@"; do
  if (( seen_dash )); then
    extra+=$a
  elif [[ $a == -- ]]; then
    seen_dash=1
  else
    rooms+=$a
  fi
done

# 编辑器会顺手改项目里的文件（贴图一被 3D 场景用到就改成 VRAM 压缩重新导入、project.godot 里删掉等于默认值的项……），
# 启动时还会把上次开着的场景都打开（.godot/editor/editor_layout.cfg），退出时又把烘焙场景记进去：
# 烘焙前备份这些文件，烘完原样还回去（assets/gi/ 下烘出来的除外）。中途出错、超时、Ctrl-C 也一样还原（trap）
backup=""
files=()
restore_files() {
  [[ -n $backup && -d $backup ]] || return 0
  local f restored=0
  for f in $files; do
    if ! cmp -s $backup/$f $root/$f; then
      cp -p $backup/$f $root/$f
      (( restored += 1 ))
    fi
  done
  if (( restored )); then
    echo "lightmap: 还原了编辑器改动的 $restored 个设置文件"
  fi
  if [[ -f $backup/editor_layout.cfg ]]; then
    cp -p $backup/editor_layout.cfg $root/.godot/editor/editor_layout.cfg
  fi
  rm -r $backup
  backup=""
}
trap 'echo "lightmap: 被中断" >&2; exit 130' INT TERM

# 一次运行的日志：失败时整份打出来（平时只挑要紧的几行）
log=$(mktemp -t lmbake_log)
trap 'restore_files; rm -f $log' EXIT

## 烘一个场景；失败（编辑器报错退出、超时、没烘出数据）返回非 0
editor_bake() {
  local scene=$1
  local cfg=$root/.godot/lightmap_editor
  mkdir -p $cfg
  backup=$(mktemp -d -t lmbake)
  files=(${(f)"$(cd $root && find . \( -name '*.import' -o -name project.godot -o -name default_bus_layout.tres \) \
    -not -path './.godot/*' -not -path './.tmp/*' -not -path './assets/gi/*')"})
  local f
  for f in $files; do
    mkdir -p $backup/${f:h}
    cp -p $root/$f $backup/$f
  done
  local layout=$root/.godot/editor/editor_layout.cfg
  if [[ -f $layout ]]; then
    cp -p $layout $backup/editor_layout.cfg
    grep -vE '^(open_scenes|current_scene)=' $backup/editor_layout.cfg > $layout || true
  fi
  local rc=0
  # 一份最多 15 分钟（宿舍超采样一份约 2 分钟）；卡在编辑器对话框里就强行结束
  LIMIT=${BAKE_LIMIT:-900} XDG_CONFIG_HOME=$cfg/config XDG_DATA_HOME=$cfg/data XDG_CACHE_HOME=$cfg/cache \
    godot_window -e --path "$root" --resolution 960x540 "$scene" -- --bake-lightmap=$scene > $log || rc=$?
  # 不碍事的：Metal 烘焙时偶尔等 GPU 超时（会接着烘完）、编辑器退出时的节点路径报错
  grep -E "^lightmap|ERROR|error|Error" $log |
    grep -vE "resources still in use|timeout waiting for fence|absolute paths from outside the active scene tree" || true
  restore_files
  if (( rc )) || ! grep -q "^lightmap baked in" $log; then
    echo "lightmap: 烘焙 $scene 失败（退出码 $rc），完整日志：" >&2
    tail -60 $log >&2
    return 1
  fi
}

if [[ -n ${SCENE:-} ]]; then
  editor_bake $SCENE
  exit
fi
# 先把导入做完（模型、.import 改过的话在这里重新导入、重新展 UV2）：导出烘焙场景的游戏和运行时用的必须是同一份网格，
# 不能等到编辑器那一步才发现模型变了、重新导入（贴图就对不上 UV2 了）
"$godot" --headless --audio-driver Dummy --path "$root" --import 2>&1 | grep -E "ERROR|SCRIPT ERROR" || true
failed=()
for k in $rooms; do
  echo "== $k: 导出烘焙场景"
  rm -f $root/.tmp/lightmap/${k}_src.scn $root/.tmp/lightmap/${k}_*_src.scn(N) \
    $root/.tmp/lightmap/${k}.lmkey.json $root/.tmp/lightmap/${k}_*.lmkey.json(N)
  rc=0
  LIMIT=300 godot_window --path "$root" --resolution 640x360 -- --scene=$k --lm-export $extra > $log || rc=$?
  grep -E "^lightmap|ERROR|SCRIPT" $log | grep -v "resources still in use" || true
  if (( rc )) || ! grep -q "^lightmap: exported" $log || grep -q "^lightmap: exported.*err=[1-9]" $log; then
    echo "lightmap: 导出 $k 的烘焙场景失败（退出码 $rc）" >&2
    tail -40 $log >&2
    failed+=$k
    continue
  fi
  # 默认一份，再加每个变体一份（宿舍：日光灯开着的 dorm_tube）
  for src in $root/.tmp/lightmap/${k}_src.scn(N) $root/.tmp/lightmap/${k}_*_src.scn(N); do
    echo "== ${src:t}: 编辑器里烘焙"
    # 烘成功后 lightmap_baker.gd 把导出时记下的网格指纹放到贴图旁边（<房间>.lmkey.json），运行时对不上就退回 VoxelGI
    editor_bake res://.tmp/lightmap/${src:t} || failed+=${src:t}
  done
done
if (( ${#failed} )); then
  echo "lightmap: 失败的：${failed}" >&2
  exit 1
fi
