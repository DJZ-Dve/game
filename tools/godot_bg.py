"""tools/ 下脚本的公共部分：找 Godot、Blender，在后台跑 Godot，跑命令行程序。
被 capture.py、record.py、bench.py、bake_lightmap.py、rebuild_models.py 等引用（import godot_bg）。

godot_window(参数...)：运行一个要渲染画面的 Godot（截图、录像、烘焙 GI），默认在后台、不打扰手上的工作：
- 开在一个单独的 Windows 桌面上（CreateDesktop 建的 GuixuBg，跟 Win+Ctrl+D 的虚拟桌面不是一回事）：窗口照常建、照常渲染，
  但这个桌面从来不切过去，所以看不见、不上任务栏，也抢不走焦点（Godot 自己调 SetForegroundWindow 只在那个桌面里生效）。
  试过的别的办法都不行：项目设置 no_focus 编辑器不认（编辑器不读项目的窗口设置，显示窗口时照样 SetForegroundWindow）；
  --position 给屏幕外的坐标，Godot 建窗口时会把它夹回屏幕里，至少露出三分之一。
- 绝不出声：一律 --audio-driver Dummy（要听声音用 tools/record.py 录成文件再放）。
- 本脚本被打断、被强行结束时 Godot 跟着结束（作业对象），不会留下一个看不见的 Godot 在后台一直跑。
环境变量 FOREGROUND=1（或 capture / record / bench 的 --fg）时照常在当前桌面开窗口。
limit=秒数：超时强行结束（编辑器卡在对话框里、烘焙卡死时不会一直挂着；后台桌面上的对话框没人看得见），返回 124。
settings：临时改项目设置（比如录像时的视口大小）：启动前在项目根目录放一个 override.cfg，项目设置只在启动时读一次，
  一看到 Godot 的窗口就删掉（前后一两秒，同时手动开的游戏、编辑器碰不上；几个后台 Godot 同时启动时按锁排队）。

Godot、Blender 的位置：环境变量 GODOT、BLENDER 指定可执行文件；没设就在 D:\\Godot、D:\\Blender 等常见位置和 PATH 里找。
命令行程序（Blender、ffmpeg、无头 Godot）一律不开黑框（CREATE_NO_WINDOW）。
import 时顺手把本进程的 stdout/stderr 改成 UTF-8（中文 Windows 默认 GBK，输出给管道时 PowerShell 7、Git Bash 会显示乱码）。
"""
import ctypes
import glob
import msvcrt
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from ctypes import wintypes as W

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    except (AttributeError, ValueError):
        pass


def _version_key(path):
    return [int(n) for n in re.findall(r"\d+", os.path.basename(os.path.dirname(path)) + os.path.basename(path))]


def _find(env, patterns, names):
    p = os.environ.get(env)
    if p:
        if not os.path.isfile(p):
            raise SystemExit(f"环境变量 {env} 指的文件不存在：{p}")
        return p
    for pat in patterns:
        hits = [h for h in glob.glob(os.path.expandvars(pat)) if not h.lower().endswith("_console.exe")]
        if hits:
            return max(hits, key=_version_key)
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    raise SystemExit(f"找不到 {names[0]}：用环境变量 {env} 指定可执行文件")


_cache = {}


def godot():
    """Godot 编辑器的可执行文件（不带 _console 的那个；有多个版本取最新的）"""
    if "godot" not in _cache:
        _cache["godot"] = _find("GODOT", [r"D:\Godot\Godot_v*_win64.exe", r"C:\Godot\Godot_v*_win64.exe",
                                          r"%LOCALAPPDATA%\Programs\Godot\Godot_v*_win64.exe",
                                          r"C:\Program Files\Godot\Godot_v*_win64.exe"], ["godot"])
    return _cache["godot"]


def blender():
    if "blender" not in _cache:
        _cache["blender"] = _find("BLENDER", [r"D:\Blender\blender.exe",
                                              r"C:\Program Files\Blender Foundation\Blender*\blender.exe"], ["blender"])
    return _cache["blender"]


def show(pattern, exclude=None):
    """给 run / godot_window 的 on_line：边跑边打印要紧的行"""
    def on_line(line):
        if re.search(pattern, line) and not (exclude and re.search(exclude, line)):
            print(line)
    return on_line


def grep(text, pattern, exclude=None):
    """按正则挑出要紧的几行打印（相当于 grep -E）"""
    for line in text.splitlines():
        show(pattern, exclude)(line)


# ---- Win32 ----

_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_u32 = ctypes.WinDLL("user32", use_last_error=True)


class _BasicLimit(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", W.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", W.DWORD),
                ("Affinity", ctypes.c_size_t), ("PriorityClass", W.DWORD), ("SchedulingClass", W.DWORD)]


class _ExtendedLimit(ctypes.Structure):
    _fields_ = [("BasicLimitInformation", _BasicLimit), ("IoInfo", ctypes.c_uint64 * 6),
                ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]


class _StartupInfo(ctypes.Structure):
    _fields_ = [("cb", W.DWORD), ("lpReserved", W.LPWSTR), ("lpDesktop", W.LPWSTR), ("lpTitle", W.LPWSTR),
                ("dwX", W.DWORD), ("dwY", W.DWORD), ("dwXSize", W.DWORD), ("dwYSize", W.DWORD),
                ("dwXCountChars", W.DWORD), ("dwYCountChars", W.DWORD), ("dwFillAttribute", W.DWORD),
                ("dwFlags", W.DWORD), ("wShowWindow", W.WORD), ("cbReserved2", W.WORD),
                ("lpReserved2", ctypes.c_void_p), ("hStdInput", W.HANDLE), ("hStdOutput", W.HANDLE),
                ("hStdError", W.HANDLE)]


class _ProcessInfo(ctypes.Structure):
    _fields_ = [("hProcess", W.HANDLE), ("hThread", W.HANDLE), ("dwProcessId", W.DWORD), ("dwThreadId", W.DWORD)]


_k32.CreateJobObjectW.restype = W.HANDLE
_k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, W.LPCWSTR]
_k32.SetInformationJobObject.argtypes = [W.HANDLE, ctypes.c_int, ctypes.c_void_p, W.DWORD]
_k32.AssignProcessToJobObject.argtypes = [W.HANDLE, W.HANDLE]
_k32.CreateProcessW.argtypes = [W.LPCWSTR, W.LPWSTR, ctypes.c_void_p, ctypes.c_void_p, W.BOOL, W.DWORD,
                                ctypes.c_void_p, W.LPCWSTR, ctypes.POINTER(_StartupInfo), ctypes.POINTER(_ProcessInfo)]
_k32.WaitForSingleObject.argtypes = [W.HANDLE, W.DWORD]
_k32.GetExitCodeProcess.argtypes = [W.HANDLE, ctypes.POINTER(W.DWORD)]
_k32.TerminateProcess.argtypes = [W.HANDLE, W.UINT]
_k32.CloseHandle.argtypes = [W.HANDLE]
_u32.CreateDesktopW.restype = W.HANDLE
_u32.CreateDesktopW.argtypes = [W.LPCWSTR, W.LPCWSTR, ctypes.c_void_p, W.DWORD, W.DWORD, ctypes.c_void_p]
_ENUM = ctypes.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
_u32.EnumDesktopWindows.argtypes = [W.HANDLE, _ENUM, W.LPARAM]
_u32.GetWindowThreadProcessId.argtypes = [W.HWND, ctypes.POINTER(W.DWORD)]

_job = None


def _kill_with_us(handle):
    """放进作业对象：本进程退出（包括被强行结束）时，子进程跟着结束"""
    global _job
    if _job is None:
        _job = _k32.CreateJobObjectW(None, None)
        info = _ExtendedLimit()
        info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        _k32.SetInformationJobObject(_job, 9, ctypes.byref(info), ctypes.sizeof(info))  # JobObjectExtendedLimitInformation
    _k32.AssignProcessToJobObject(_job, handle)


DESKTOP = "GuixuBg"
_desktop = None


def _bg_desktop():
    """后台桌面（同名的已经有了就打开它）；句柄留到本进程退出，最后一个句柄关掉、上面没有进程了它就自动没了"""
    global _desktop
    if _desktop is None:
        _desktop = _u32.CreateDesktopW(DESKTOP, None, None, 0, 0x10000000, None)  # GENERIC_ALL
        if not _desktop:
            raise OSError(ctypes.get_last_error(), "CreateDesktop 失败")
    return _desktop


class _DesktopProcess:
    """开在后台桌面上的进程（subprocess.Popen 不能指定桌面，只好自己调 CreateProcessW），接口学 Popen"""

    def __init__(self, cmd, env=None, cwd=None):
        _bg_desktop()
        r, w = os.pipe()
        hout = msvcrt.get_osfhandle(w)
        os.set_handle_inheritable(hout, True)
        devnull = open(os.devnull, "rb")
        hin = msvcrt.get_osfhandle(devnull.fileno())
        os.set_handle_inheritable(hin, True)
        si = _StartupInfo()
        si.cb = ctypes.sizeof(si)
        si.lpDesktop = "WinSta0\\" + DESKTOP
        si.dwFlags = 0x100  # STARTF_USESTDHANDLES
        si.hStdInput, si.hStdOutput, si.hStdError = hin, hout, hout
        block = None
        flags = NO_WINDOW
        if env is not None:
            block = ctypes.create_unicode_buffer("".join(f"{k}={v}\0" for k, v in env.items()) + "\0")
            flags |= 0x400  # CREATE_UNICODE_ENVIRONMENT
        pi = _ProcessInfo()
        ok = _k32.CreateProcessW(None, ctypes.create_unicode_buffer(subprocess.list2cmdline(cmd)), None, None, True,
                                 flags, block, cwd, ctypes.byref(si), ctypes.byref(pi))
        err = ctypes.get_last_error()
        os.close(w)  # 自己这头的写端关掉，子进程退出时读端才会读到结尾
        devnull.close()
        if not ok:
            os.close(r)
            raise OSError(err, f"启动失败: {cmd[0]}")
        _k32.CloseHandle(pi.hThread)
        self._handle, self.pid, self.returncode = pi.hProcess, pi.dwProcessId, None
        self.stdout = os.fdopen(r, "rb")

    def poll(self):
        if self.returncode is None and _k32.WaitForSingleObject(self._handle, 0) == 0:
            code = W.DWORD()
            _k32.GetExitCodeProcess(self._handle, ctypes.byref(code))
            self.returncode = code.value
        return self.returncode

    def wait(self):
        _k32.WaitForSingleObject(self._handle, 0xFFFFFFFF)
        return self.poll()

    def kill(self):
        if self.poll() is None:
            _k32.TerminateProcess(self._handle, 1)


def _spawn(cmd, env=None, cwd=None, desktop=False):
    if desktop:
        proc = _DesktopProcess(cmd, env, cwd)
    else:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                creationflags=NO_WINDOW, env=env, cwd=cwd)
    _kill_with_us(int(proc._handle))
    return proc


def _decode(raw):
    # Godot 输出 UTF-8；Blender 里的 Python 输出给管道时按系统代码页（GBK）
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("gbk", "replace")


def _pump(proc, on_line, lines):
    for raw in proc.stdout:
        line = _decode(raw).rstrip("\r\n")
        lines.append(line)
        if on_line:
            on_line(line)


def run(cmd, on_line=None, env=None, cwd=None):
    """运行一个命令行程序（不开窗口），返回 (退出码, 全部输出)；on_line 每来一行调一次"""
    proc = _spawn([str(c) for c in cmd], env, cwd)
    lines = []
    try:
        _pump(proc, on_line, lines)
        rc = proc.wait()
    except BaseException:
        proc.kill()
        raise
    return rc, "\n".join(lines)


def _has_window(pid, desktop):
    """这个进程在那个桌面上有没有建出窗口（Godot 读完项目设置以后才建窗口）"""
    found = []

    def cb(h, _):
        p = W.DWORD()
        _u32.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value == pid:
            found.append(h)
            return False
        return True

    if desktop:
        _u32.EnumDesktopWindows(desktop, _ENUM(cb), 0)
    else:
        _u32.EnumWindows(_ENUM(cb), 0)
    return bool(found)


# ---- 临时 override.cfg ----

MARK = "; tools/godot_bg.py"
OVERRIDE = os.path.join(ROOT, "override.cfg")


class _StartLock:
    """几个要改项目设置的 Godot 同时启动时排队：override.cfg 同一时间只属于一个（锁在本进程退出时自动释放）"""

    def __init__(self):
        os.makedirs(os.path.join(ROOT, ".godot"), exist_ok=True)
        self.f = open(os.path.join(ROOT, ".godot", "godot_bg.lock"), "a+b")
        self.f.seek(0)
        while True:
            try:
                msvcrt.locking(self.f.fileno(), msvcrt.LK_LOCK, 1)  # 拿不到时每秒重试，十次后报错，接着等
                return
            except OSError:
                pass

    def release(self):
        self.f.seek(0)
        msvcrt.locking(self.f.fileno(), msvcrt.LK_UNLCK, 1)
        self.f.close()


def _write_override(settings):
    """写 override.cfg（{节: {键: 值}}，值按 Godot 的写法给字符串）；项目里有自己的 override.cfg 就不动它"""
    if os.path.exists(OVERRIDE):
        with open(OVERRIDE, encoding="utf-8", errors="replace") as f:
            if not f.read().startswith(MARK):
                print("godot_bg: 项目里有自己的 override.cfg，这次没法临时改项目设置", file=sys.stderr)
                return False
    out = [MARK + " 临时放的（后台跑 Godot 用），Godot 一启动就删；留下来了说明上次被强行打断，可以直接删掉"]
    for sec, kv in settings.items():
        out.append(f"\n[{sec}]\n")
        out += [f"{k}={v}" for k, v in kv.items()]
    with open(OVERRIDE, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out) + "\n")
    return True


def godot_window(args, limit=None, on_line=None, env=None, settings=None, exe=None):
    """运行一个要渲染画面的 Godot，返回 (退出码, 全部输出)；超过 limit 秒强行结束，返回 124。
    settings：临时改的项目设置（{节: {键: 值}}，经 override.cfg）
    exe：换一个 Godot 可执行文件（烘光照贴图时用自包含模式的那份，见 bake_lightmap.py）"""
    cmd = [exe or godot(), "--audio-driver", "Dummy"] + [str(a) for a in args]
    bg = not os.environ.get("FOREGROUND")
    lock = _StartLock() if settings else None
    wrote = bool(settings) and _write_override(settings)

    def started():
        # Godot 的窗口出来了（项目设置早就读完了）：撤掉 override.cfg，放下一个启动
        nonlocal wrote, lock
        if wrote and os.path.exists(OVERRIDE):
            os.remove(OVERRIDE)
        wrote = False
        if lock:
            lock.release()
            lock = None

    lines = []
    proc = None
    t0 = time.monotonic()
    try:
        proc = _spawn(cmd, env, desktop=bg)
        pump = threading.Thread(target=_pump, args=(proc, on_line, lines), daemon=True)
        pump.start()
        while proc.poll() is None:
            if lock and _has_window(proc.pid, _desktop if bg else None):
                started()
            if limit and time.monotonic() - t0 > limit:
                proc.kill()
                proc.wait()
                pump.join(5)
                print(f"godot_bg: 超过 {limit} 秒，强行结束", file=sys.stderr)
                return 124, "\n".join(lines)
            time.sleep(0.05 if lock else 0.2)
        pump.join(5)
        return proc.returncode, "\n".join(lines)
    except BaseException:
        if proc:
            proc.kill()
        raise
    finally:
        started()
