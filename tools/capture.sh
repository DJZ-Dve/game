#!/bin/zsh
# 启动游戏、等待若干帧后截图并退出。其余参数原样传给游戏（见 scripts/debug_args.gd）。
# 用法: tools/capture.sh out.png --view=external --orbit=135
set -eu
if (( $# < 1 )); then
  echo "用法: $0 out.png [游戏参数...]" >&2
  exit 1
fi
out=${1:A}  # Godot 会切到项目目录，相对路径先转成绝对路径
shift
root=${0:A:h:h}
godot=${GODOT:-/Applications/Godot.app/Contents/MacOS/Godot}
"$godot" --path "$root" --resolution 1600x900 -- "--capture=$out" --wait=150 "$@" 2>&1 |
  grep -E "ERROR|SCRIPT|captured" || true
