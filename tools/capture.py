#!/usr/bin/env python3
"""启动游戏、等待若干帧后截图并退出。其余参数原样传给游戏（见 scripts/debug_args.gd）。
用法: python tools/capture.py out.png --view=external --orbit=135
      python tools/capture.py out.png --scene=dorm --at=0.3,1.0 --yaw=-10    （岸上的场景：dorm、office）
不给 --scene 就是潜艇（scenes/deep_sea.tscn）。
默认在后台运行（不抢焦点、窗口不出现在屏幕上，见 godot_bg.py）；想看着窗口跑就加 --fg。
"""
import os
import sys

import godot_bg

args = sys.argv[1:]
if "--fg" in args:
    args.remove("--fg")
    os.environ["FOREGROUND"] = "1"
if not args:
    sys.exit(f"用法: python {sys.argv[0]} out.png [--fg] [游戏参数...]")
out = os.path.abspath(args[0]).replace("\\", "/")  # Godot 会切到项目目录，相对路径先转成绝对路径
game = args[1:]
scene = [] if any(a.startswith("--scene=") for a in game) else ["--scene=deep_sea"]
before = os.path.getmtime(out) if os.path.exists(out) else None
rc, text = godot_bg.godot_window(["--path", godot_bg.ROOT, "--resolution", "1600x900", "--",
                                  f"--capture={out}", "--wait=150", *scene, *game])
godot_bg.grep(text, r"ERROR|SCRIPT|captured")
if not os.path.exists(out) or os.path.getmtime(out) == before:
    sys.exit(f"没截出来（Godot 退出码 {rc}）")
