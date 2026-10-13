#!/usr/bin/env python3
"""基准截图：固定机位（tools/bench_views.json）一次拍一组，再拼成带标注的总览图，给改画面前后对比用。
用法: python tools/bench.py 输出目录 [dorm|office|cabin ...] [--only=机位,机位] [--views=机位文件] [--fg] [其他游戏参数...]
  例: python tools/bench.py .tmp/bench/baseline                        三个场景都拍
      python tools/bench.py .tmp/bench/try1 office --only=visitor,window_out
      python tools/compare.py .tmp/bench/baseline .tmp/bench/try1 .tmp/bench/cmp1
岸上的场景（dorm、office）每个只启动一次 Godot（--shots，见 scripts/debug_args.gd）；潜艇舱内（cabin）是质感标杆，
每个机位启动一次（用 capture.py 那一套参数：--at、--yaw、--door……）。
产出: 输出目录/<场景>_<机位>.png、<场景>_shots.json（每张的帧率、帧时间、GPU 时间）、<场景>_sheet.jpg（带标注的拼图）
1600x900，后台跑（godot_bg.py：不抢焦点、Dummy 音频，绝不出声）；--fixed-fps 60 让游戏时间按帧走，
吊扇、钟、人的动作每次停在同一个位置。--views 换一份机位文件（格式同 bench_views.json）。
"""
import glob
import json
import os
import re
import subprocess
import sys

import godot_bg

ROOT = godot_bg.ROOT
args = sys.argv[1:]
if not args:
    sys.exit(f"用法: python {sys.argv[0]} 输出目录 [dorm|office|cabin ...] [--only=机位,...] [--views=文件] [游戏参数...]")
out = os.path.abspath(args[0])
views = os.path.join(ROOT, "tools", "bench_views.json")
scenes, extra, only = [], [], ""
for a in args[1:]:
    if a in ("dorm", "office", "cabin"):
        scenes.append(a)
    elif a.startswith("--only="):
        only = a[len("--only="):]
    elif a.startswith("--views="):
        views = os.path.abspath(a[len("--views="):])
    elif a == "--fg":
        os.environ["FOREGROUND"] = "1"
    else:
        extra.append(a)
scenes = scenes or ["dorm", "office", "cabin"]
os.makedirs(out, exist_ok=True)
game = ["--path", ROOT, "--resolution", "1600x900", "--fixed-fps", "60"]
def fwd(p):
    return p.replace("\\", "/")


def clear(s):
    for f in glob.glob(os.path.join(out, f"{s}_*.png")) + [os.path.join(out, f"{s}_shots.json")]:
        if os.path.exists(f):
            os.remove(f)


def shore(s):
    """岸上：一次启动拍完一组（没给 --only 时先清掉这个场景上一次的图，免得留着改了名的旧机位）"""
    a = [f"--shots={fwd(views)}", f"--shot-dir={fwd(out)}", f"--scene={s}"]
    if only:
        a.append(f"--shot-only={only}")
    else:
        clear(s)
    godot_bg.godot_window(game + ["--", *a, *extra], on_line=godot_bg.show(r"ERROR|SCRIPT|^shot "))


def cabin():
    """潜艇舱内：每个机位一次 --capture；清单（帧率）按截图输出拼出来"""
    if not only:
        clear("cabin")
    pick = [n for n in only.split(",") if n]
    with open(views, encoding="utf-8") as f:
        all_views = json.load(f).get("cabin", [])
    fps = {}
    for v in all_views:
        if pick and v["name"] not in pick:
            continue
        png = os.path.join(out, f"cabin_{v['name']}.png")
        _, text = godot_bg.godot_window(game + ["--", f"--capture={fwd(png)}", "--wait=150", "--scene=deep_sea",
                                               *v.get("args", []), *extra], on_line=godot_bg.show(r"ERROR|SCRIPT|captured"))
        for line in text.splitlines():
            m = re.search(r"captured \S*cabin_(\S+)\.png\s+fps (\S+)", line)
            if m:
                fps[m[1]] = float(m[2])
    path = os.path.join(out, "cabin_shots.json")
    old = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            old = {r["name"]: r for r in json.load(f)["shots"]}
    shots = []
    for v in all_views:
        n = v["name"]
        if n in fps:
            shots.append({"name": n, "file": f"cabin_{n}.png", "desc": v.get("desc", ""), "fps": fps[n]})
        elif n in old and os.path.exists(os.path.join(out, old[n]["file"])):
            shots.append(old[n])
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump({"set": "cabin", "scene": "deep_sea", "resolution": [1600, 900], "shots": shots},
                  f, ensure_ascii=False, indent=2)


for s in scenes:
    print(f"== {s}")
    if s == "cabin":
        cabin()
    else:
        shore(s)
    subprocess.run([sys.executable, os.path.join(ROOT, "tools", "contact_sheet.py"), out, s])
