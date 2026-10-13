#!/usr/bin/env python3
"""离线录一段游戏的画面和声音，给听不见声音的人（和 Claude）检查音效用。
用的是 Godot 的 Movie Maker：固定 60 帧/秒逐帧渲染，音频按帧混出来直接写文件，
不经过声卡，绝不会从扬声器或耳机出声；窗口在后台（见 godot_bg.py）。
用法: python tools/record.py 输出名 秒数 [--res=960x540] [--crf=26] [--mjpeg-q=0.6] [--fg] [游戏参数...]
  例: python tools/record.py .tmp/door 8 --at=0,2.0 --yaw=180 --actions=30:interact,330:interact
不给 --scene 就是潜艇（scenes/deep_sea.tscn）；岸上的场景用 --scene=dorm / --scene=office
--crf 调 mp4 的画质（默认 26，数字越小越清楚、文件越大；给别人看的用 18~20）；
--res 调分辨率（默认 960x540；看抗锯齿、拖影这类细节用 1600x900）
产出: 输出名.mp4（给人看着听）、输出名.wav（给 tools/audio_report.py 分析）、输出名.log（游戏输出，含 SFX 事件）
要用 ffmpeg：在 PATH 里，或者用环境变量 FFMPEG 指定。
"""
import os
import re
import shutil
import sys
import tempfile

import godot_bg

opts = {"res": "960x540", "crf": "26", "mjpeg-q": "0.6"}
args = []
for a in sys.argv[1:]:
    m = re.match(r"--(res|crf|mjpeg-q)=(.+)$", a)
    if m:
        opts[m[1]] = m[2]
    elif a == "--fg":
        os.environ["FOREGROUND"] = "1"
    else:
        args.append(a)
if len(args) < 2:
    sys.exit(f"用法: python {sys.argv[0]} 输出名 秒数 [--res=WxH] [--crf=N] [--mjpeg-q=Q] [--fg] [游戏参数...]")
out = os.path.abspath(args[0])
secs = float(args[1])
game = args[2:]
ffmpeg = os.environ.get("FFMPEG") or shutil.which("ffmpeg")
if not ffmpeg:
    sys.exit("找不到 ffmpeg：装一个放进 PATH，或者用环境变量 FFMPEG 指定")
w, h = opts["res"].split("x")
os.makedirs(os.path.dirname(out), exist_ok=True)
scene = [] if any(a.startswith("--scene=") for a in game) else ["--scene=deep_sea"]
tmp = tempfile.mkdtemp(prefix="record_")
try:
    movie = os.path.join(tmp, "movie.avi")
    # Movie Maker 写的 AVI 到 1 GB 左右就停（后面的帧全丢，ffmpeg 只好一直重复最后一帧）。它按项目的视口大小
    # （1920×1080）录 MJPEG，画面细节多、带胶片颗粒时每帧更大，二三十秒就撞上限。录的时候临时把视口降到 --res、
    # MJPEG 质量调低一点（经 override.cfg，见 godot_bg.py）
    settings = {"display": {"window/size/viewport_width": w, "window/size/viewport_height": h},
                "editor": {"movie_writer/mjpeg_quality": opts["mjpeg-q"]}}
    rc, text = godot_bg.godot_window(["--path", godot_bg.ROOT, "--resolution", opts["res"],
                                      "--write-movie", movie.replace("\\", "/"), "--fixed-fps", "60",
                                      "--quit-after", round(secs * 60), "--", "--sfx-log", *scene, *game],
                                     settings=settings)
    with open(out + ".log", "w", encoding="utf-8", newline="\n") as f:
        f.write(text + "\n")
    for line in [l for l in text.splitlines() if re.search(r"ERROR|SCRIPT ERROR|at: ", l)][:20]:
        print(line)
    godot_bg.grep(text, r"frames at")
    if not os.path.exists(movie) or not os.path.getsize(movie):
        sys.exit(f"没录出来，见 {out}.log")
    for cmd in ([ffmpeg, "-v", "error", "-y", "-i", movie, "-vn", "-c:a", "pcm_s16le", out + ".wav"],
                [ffmpeg, "-v", "error", "-y", "-i", movie, "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
                 "-crf", opts["crf"], "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out + ".mp4"]):
        rc, text = godot_bg.run(cmd)
        if rc:
            sys.exit(text)
    print(f"录好了: {out}.mp4  {out}.wav  {out}.log")
finally:
    shutil.rmtree(tmp, ignore_errors=True)
