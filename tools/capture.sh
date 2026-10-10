#!/bin/zsh
# 启动游戏、等待若干帧后截图并退出。其余参数原样传给游戏（见 scripts/debug_args.gd）。
# 用法: tools/capture.sh out.png --view=external --orbit=135
#       tools/capture.sh out.png --scene=dorm --at=0.3,1.0 --yaw=-10    （岸上的场景：dorm、office）
# 不给 --scene 就是潜艇（scenes/deep_sea.tscn；游戏的主场景是宿舍，剧情从那里开始）。
# 默认在后台启动（不抢焦点、窗口放到屏幕外）；想看着窗口跑就设 FOREGROUND=1。
set -eu
if (( $# < 1 )); then
  echo "用法: $0 out.png [游戏参数...]" >&2
  exit 1
fi
out=${1:A}  # Godot 会切到项目目录，相对路径先转成绝对路径
shift
root=${0:A:h:h}
source "$root/tools/godot_bg.sh"
scene=(--scene=deep_sea)
[[ " $* " == *" --scene="* ]] && scene=()
godot_window --path "$root" --resolution 1600x900 -- "--capture=$out" --wait=150 $scene "$@" |
  grep -E "ERROR|SCRIPT|captured" || true
