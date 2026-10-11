#!/bin/zsh
# 基准截图：固定机位（tools/bench_views.json）一次拍一组，再拼成带标注的总览图，给改画面前后对比用。
# 用法: tools/bench.sh 输出目录 [dorm|office|cabin ...] [--only=机位,机位] [其他游戏参数...]
#   例: tools/bench.sh .tmp/bench/baseline                        三个场景都拍
#       tools/bench.sh .tmp/bench/try1 office --only=visitor,window_out
#       python3 tools/compare.py .tmp/bench/baseline .tmp/bench/try1 .tmp/bench/cmp1
# 岸上的场景（dorm、office）每个只启动一次 Godot（--shots，见 scripts/debug_args.gd）；潜艇舱内（cabin）是质感标杆，
# 每个机位启动一次（用 capture.sh 那一套参数：--at、--yaw、--door……）。
# 产出: 输出目录/<场景>_<机位>.png、<场景>_shots.json（每张的帧率、帧时间、GPU 时间）、<场景>_sheet.jpg（带标注的拼图）
# 1600x900，后台跑（godot_bg.sh：不抢焦点、Dummy 音频，绝不出声）；--fixed-fps 60 让游戏时间按帧走，
# 吊扇、钟、人的动作每次停在同一个位置。环境变量 VIEWS 换一份机位文件（格式同 bench_views.json）。
set -eu
if (( $# < 1 )); then
  echo "用法: $0 输出目录 [dorm|office|cabin ...] [--only=机位,...] [游戏参数...]" >&2
  exit 1
fi
out=${1:A}
shift
root=${0:A:h:h}
views=${VIEWS:-$root/tools/bench_views.json}
views=${views:A}
source "$root/tools/godot_bg.sh"
scenes=()
extra=()
only=""
for a in "$@"; do
  case $a in
    dorm|office|cabin) scenes+=$a ;;
    --only=*) only=${a#--only=} ;;
    *) extra+=$a ;;
  esac
done
(( ${#scenes} )) || scenes=(dorm office cabin)
mkdir -p $out
game=(--path "$root" --resolution 1600x900 --fixed-fps 60)

# 岸上：一次启动拍完一组（没给 --only 时先清掉这个场景上一次的图，免得留着改了名的旧机位）
shore() {
  local s=$1
  local args=(--shots=$views --shot-dir=$out --scene=$s)
  if [[ -n $only ]]; then
    args+=--shot-only=$only
  else
    rm -f $out/${s}_*.png(N) $out/${s}_shots.json
  fi
  godot_window $game -- $args $extra | grep -E "ERROR|SCRIPT|^shot " || true
}

# 潜艇舱内：每个机位一次 --capture；清单（帧率）由下面的 python 按截图输出拼出来
cabin() {
  local log=$(mktemp -t bench_cabin)
  [[ -z $only ]] && rm -f $out/cabin_*.png(N) $out/cabin_shots.json
  python3 - $views "$only" <<'EOF' > $log.list
import json, sys
only = [n for n in sys.argv[2].split(",") if n]
for v in json.load(open(sys.argv[1])).get("cabin", []):
    if not only or v["name"] in only:
        print(v["name"] + "\t" + " ".join(v.get("args", [])))
EOF
  local name rest
  while IFS=$'\t' read -r name rest; do
    godot_window $game -- --capture=$out/cabin_$name.png --wait=150 --scene=deep_sea ${=rest} $extra |
      grep -E "ERROR|SCRIPT|captured" | tee -a $log || true
  done < $log.list
  python3 - $views $out $log <<'EOF'
import json, os, re, sys
views, out, log = sys.argv[1:]
path = os.path.join(out, "cabin_shots.json")
old = {r["name"]: r for r in json.load(open(path))["shots"]} if os.path.exists(path) else {}
fps = {}
for line in open(log):
    m = re.search(r"captured \S*cabin_(\S+)\.png\s+fps (\S+)", line)
    if m:
        fps[m.group(1)] = float(m.group(2))
shots = []
for v in json.load(open(views)).get("cabin", []):
    n = v["name"]
    if n in fps:
        shots.append({"name": n, "file": f"cabin_{n}.png", "desc": v.get("desc", ""), "fps": fps[n]})
    elif n in old and os.path.exists(os.path.join(out, old[n]["file"])):
        shots.append(old[n])
json.dump({"set": "cabin", "scene": "deep_sea", "resolution": [1600, 900], "shots": shots},
          open(path, "w"), ensure_ascii=False, indent=2)
EOF
  rm -f $log $log.list
}

for s in $scenes; do
  echo "== $s"
  if [[ $s == cabin ]]; then
    cabin
  else
    shore $s
  fi
  python3 $root/tools/contact_sheet.py $out $s
done
