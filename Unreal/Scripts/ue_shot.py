"""在后台桌面上跑游戏（-game，不经编辑器界面），按任务文件的机位截图，截完自己退出。不弹窗、不出声。
相当于 Godot 版的 tools/capture.py；游戏里那边是 C++ 的 UGuixuShotSubsystem（Source/Guixu/Tools/）。

用法：
  py -3.13 Unreal/Scripts/ue_shot.py <任务.json> [--res=1600x900] [--limit=秒]
任务文件：{"out_dir": "...", "fov_v": 72, "warm_frames": 300, "settle_frames": 90,
          "views": [{"name": "console", "node": "Anchor_Eye"}, {"name": "aft", "at": [0, 0.8], "yaw": 180, "pitch": -5}]}
机位写法见 Scripts/render_views.py 开头。
"""
import os
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ue_bg  # noqa: E402

godot_bg = ue_bg.godot_bg


def run(job, res="1600x900", limit=1800, extra=()):
    job = os.path.abspath(job)
    done = job + ".done.json"
    if os.path.exists(done):
        os.remove(done)
    w, h = res.split("x")
    env = dict(os.environ)
    env["UE-LocalDataCachePath"] = ue_bg.DDC
    cmd = [ue_bg.UE, ue_bg.PROJECT, "-game", "-windowed", f"-ResX={w}", f"-ResY={h}", f"-GuixuShotJob={job}",
           "-unattended", "-nosplash", "-nosound", "-nop4", "-NoLiveCoding", f"-LocalDataCachePath={ue_bg.DDC}", *extra]
    t0 = time.time()
    stop = threading.Event()
    reader = threading.Thread(target=ue_bg.tail, args=(ue_bg.LOG, t0, stop, r"\[shot\]|Error: |Fatal|Ensure condition"),
                              daemon=True)
    reader.start()
    proc = godot_bg._spawn(cmd, env, desktop=not os.environ.get("FOREGROUND"))
    threading.Thread(target=godot_bg._pump, args=(proc, None, []), daemon=True).start()
    try:
        while proc.poll() is None:
            if limit and time.time() - t0 > limit:
                print(f"ue_shot: 超过 {limit} 秒，强行结束", file=sys.stderr)
                proc.kill()
                break
            time.sleep(1)
        proc.wait()
    finally:
        time.sleep(1)
        stop.set()
        reader.join(5)
    print(f"ue_shot: 退出码 {proc.returncode}，用时 {time.time() - t0:.0f} 秒", flush=True)
    return os.path.exists(done)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    opts = dict(a[2:].split("=", 1) for a in sys.argv[1:] if a.startswith("--") and "=" in a)
    if len(args) != 1:
        raise SystemExit(__doc__)
    ok = run(args[0], res=opts.get("res", "1600x900"), limit=int(opts.get("limit", 1800)))
    sys.exit(0 if ok else 1)
