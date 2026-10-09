#!/bin/zsh
# 离线录一段游戏的画面和声音，给听不见声音的人（和 Claude）检查音效用。
# 用的是 Godot 的 Movie Maker：固定 60 帧/秒逐帧渲染，音频按帧混出来直接写文件，
# 不经过声卡，绝不会从扬声器或耳机出声；窗口在后台（见 godot_bg.sh）。
# 用法: tools/record.sh 输出名 秒数 [游戏参数...]
#   例: tools/record.sh .tmp/door 8 --at=0,2.0 --yaw=180 --actions=30:interact,330:interact
# 产出: 输出名.mp4（给人看着听）、输出名.wav（给 tools/audio_report.py 分析）、输出名.log（游戏输出，含 SFX 事件）
set -eu
if (( $# < 2 )); then
  echo "用法: $0 输出名 秒数 [游戏参数...]" >&2
  exit 1
fi
out=${1:A}
secs=$2
shift 2
root=${0:A:h:h}
source "$root/tools/godot_bg.sh"
mkdir -p ${out:h}
tmp=$(mktemp -d)
godot_window --path "$root" --resolution 960x540 --write-movie "$tmp/movie.avi" --fixed-fps 60 \
  --quit-after $((secs * 60)) -- --sfx-log "$@" > "$out.log" || true
grep -E "ERROR|SCRIPT ERROR|at: " "$out.log" | head -20 || true
if [[ ! -s $tmp/movie.avi ]]; then
  echo "没录出来，见 $out.log" >&2
  exit 1
fi
ffmpeg -v error -y -i "$tmp/movie.avi" -vn -c:a pcm_s16le "$out.wav"
ffmpeg -v error -y -i "$tmp/movie.avi" -c:v libx264 -preset veryfast -pix_fmt yuv420p -crf 26 \
  -c:a aac -b:a 192k -movflags +faststart "$out.mp4"
rm -rf "$tmp"
echo "录好了: $out.mp4  $out.wav  $out.log"
