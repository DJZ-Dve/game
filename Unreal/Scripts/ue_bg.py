"""在看不见的后台桌面上跑完整的 UE 编辑器，执行一个编辑器里的 Python 脚本（渲染之类要显卡的活），不弹窗、不抢焦点、不出声。
后台桌面、作业对象（本脚本退出时编辑器跟着结束）沿用 tools/godot_bg.py。

用法：
  py -3.13 Unreal/Scripts/ue_bg.py <编辑器里跑的脚本.py> <任务.json> [--limit=秒]
任务文件由脚本自己定义格式（render_views.py、render_job.py 的见各自开头）；路径经环境变量 GUIXU_MH_JOB 传给编辑器里的脚本，
脚本做完写 <任务.json>.done.json 再退出编辑器。本脚本边跑边打印日志里带 [render] / [views] 的行和报错，
超时（默认 3 小时，第一次要编译大量着色器）或编辑器卡住时强行结束。
"""
import os
import re
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools"))
import godot_bg  # noqa: E402

UE = os.environ.get("UE_EDITOR", r"D:\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe")
PROJECT = os.path.normpath(os.path.join(HERE, "..", "Guixu.uproject"))
LOG = os.path.normpath(os.path.join(HERE, "..", "Saved", "Logs", "Guixu.log"))
DDC = r"D:\UE\DDC"

# 编辑器在后台（不是前台窗口）时默认降到每秒几帧；自动保存、崩溃恢复对话框在后台桌面上没人点得到
INI = [
    "-ini:EditorPerProjectUserSettings:[/Script/UnrealEd.EditorPerformanceSettings]:bThrottleCPUWhenNotForeground=False",
    "-ini:EditorPerProjectUserSettings:[/Script/UnrealEd.EditorLoadingSavingSettings]:bAutoSaveEnable=False",
]
SHOW = r"\[render\]|\[views\]|LogPython: Error|Error: |Fatal|Ensure condition|error X\d|\[SM6\]"


def tail(path, t0, stop, pattern):
    """等编辑器新建日志文件（启动时把旧的改名备份），然后边写边读，挑要紧的行打印"""
    f = None
    while not stop.is_set():
        if f is None:
            try:
                if os.path.getmtime(path) >= t0 - 1:
                    f = open(path, encoding="utf-8", errors="replace")
            except OSError:
                pass
            if f is None:
                time.sleep(0.5)
                continue
        line = f.readline()
        if not line:
            time.sleep(0.3)
            continue
        line = line.rstrip()
        if re.search(pattern, line):
            print(re.sub(r"^\[[\d.:\-]+\]\[\s*\d+\]", "", line), flush=True)
    if f:
        f.close()


def run(script, job, limit=3 * 3600, extra=()):
    job = os.path.abspath(job)
    done = job + ".done.json"
    if os.path.exists(done):
        os.remove(done)
    env = dict(os.environ)
    env["GUIXU_MH_JOB"] = job
    env["UE-LocalDataCachePath"] = DDC
    cmd = [UE, PROJECT, f"-ExecutePythonScript={os.path.abspath(script)}", "-unattended", "-nosplash", "-nosound",
           "-nop4", "-NoLiveCoding", "-AutoDeclinePackageRecovery", f"-LocalDataCachePath={DDC}", *INI, *extra]
    t0 = time.time()
    stop = threading.Event()
    reader = threading.Thread(target=tail, args=(LOG, t0, stop, SHOW), daemon=True)
    reader.start()
    proc = godot_bg._spawn(cmd, env, desktop=not os.environ.get("FOREGROUND"))
    drain = threading.Thread(target=godot_bg._pump, args=(proc, None, []), daemon=True)
    drain.start()
    done_at = None
    try:
        while proc.poll() is None:
            if done_at is None and os.path.exists(done):
                done_at = time.time()
            if done_at and time.time() - done_at > 90:
                print("ue_bg: 任务做完了编辑器还没退出，强行结束", file=sys.stderr)
                proc.kill()
                break
            if limit and time.time() - t0 > limit:
                print(f"ue_bg: 超过 {limit} 秒，强行结束", file=sys.stderr)
                proc.kill()
                break
            time.sleep(1)
        proc.wait()
    finally:
        time.sleep(1)
        stop.set()
        reader.join(5)
    print(f"ue_bg: 编辑器退出码 {proc.returncode}，用时 {time.time() - t0:.0f} 秒", flush=True)
    return os.path.exists(done)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    opts = dict(a[2:].split("=", 1) for a in sys.argv[1:] if a.startswith("--") and "=" in a)
    if len(args) != 2:
        raise SystemExit(__doc__)
    ok = run(args[0], args[1], limit=int(opts.get("limit", 3 * 3600)))
    sys.exit(0 if ok else 1)
