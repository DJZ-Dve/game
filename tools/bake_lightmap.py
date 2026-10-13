#!/usr/bin/env python3
"""烘焙岸上房间的 LightmapGI（间接光烘成光照贴图，直接光和阴影仍然实时；见 scripts/tools/lightmap_baker.gd）。
用法: python tools/bake_lightmap.py office [dorm ...]
      python tools/bake_lightmap.py office --lm-quality=3 --lm-texel_scale=1.5   （-- 开头的参数原样传给导出那一步，见 story_room.gd：
        --lm-<LightmapGI 属性>=值、--lm-sky-energy=倍数、--lm-lights="WindowSky.light_energy=0.5;StreetGlow.light_energy=8"）
      python tools/bake_lightmap.py --bake-scene=res://.tmp/x.tscn            （只做第二步：烘一个现成的场景）
      python tools/bake_lightmap.py dorm --lm-dir=res://lmexp/t1/ --lm-no-variants   （试参数：烘到别的目录、只烘默认那份；
        截图时也带 --lm-dir，见 story_room.gd。目录不能以点开头：编辑器不导入隐藏目录里的贴图）
      --limit=秒  编辑器烘一份最多等多久（默认 900，卡在对话框里就强行结束）
两步，都在后台跑（godot_bg.py：不抢焦点、Dummy 音频）：
  1. 游戏把房间（连同运行时摆上去的道具、灯、纸）导出成 .tmp/lightmap/<房间>_src.scn（--lm-export）
  2. 编辑器打开它，按 LightmapGI 插件的烘焙按钮，烘好的数据存到 assets/gi/<房间>.lmbake + .exr，退出
编辑器用单独一份设置：.godot/lightmap_editor/ 下放一个指向 Godot 的硬链接和 _sc_ 文件（自包含模式），
编辑器设置存在那下面的 editor_data/，不碰 %APPDATA%\\Godot。
模型、道具的 UV2 由导入时生成（.import 里 meshes/light_baking=2），模型改了跑 rebuild_models.py（它最后会调这个脚本重烘）。
材质（反照率）、灯、窗光参数（dorm.gd / office.gd 的 lightmap_*）改了也要重烘。同样的输入烘出来逐字节一样，不会凭空多出 git 改动。
耗时（Mac M4）：办事处约 1.5 分钟，宿舍两份（日光灯关 / 开）约 4 分钟。
"""
import filecmp
import glob
import os
import re
import shutil
import sys
import tempfile

import godot_bg

ROOT = godot_bg.ROOT
rooms, extra = [], []
limit = 900
only_scene = None
for a in sys.argv[1:]:
    if a.startswith("--bake-scene="):
        only_scene = a[len("--bake-scene="):]
    elif a.startswith("--limit="):
        limit = float(a[len("--limit="):])
    elif a == "--":
        pass
    elif a.startswith("--"):
        extra.append(a)
    else:
        rooms.append(a)
if not rooms and not only_scene:
    sys.exit(f"用法: python {sys.argv[0]} 房间 [房间...] [--lm-…=值...]   或   --bake-scene=res://…")


def editor_exe():
    """自包含模式的 Godot：硬链接（不占空间；跨盘符时复制一份）+ _sc_，编辑器设置存在旁边的 editor_data/"""
    d = os.path.join(ROOT, ".godot", "lightmap_editor")
    exe = os.path.join(d, "Godot.exe")
    src = godot_bg.godot()
    os.makedirs(d, exist_ok=True)
    fresh = os.path.exists(exe) and (os.path.samefile(src, exe) or filecmp.cmp(src, exe, shallow=True))
    if not fresh:
        if os.path.exists(exe):
            os.remove(exe)
        try:
            os.link(src, exe)
        except OSError:
            shutil.copy2(src, exe)
    open(os.path.join(d, "_sc_"), "a").close()
    return exe


def project_files():
    """编辑器会顺手改的项目文件：贴图一被 3D 场景用到就改成 VRAM 压缩重新导入（.import）、
    project.godot 里删掉等于默认值的项……（assets/gi/ 下烘出来的除外）"""
    skip = {os.path.join(ROOT, p) for p in (".godot", ".tmp", os.path.join("assets", "gi"), ".git")}
    for dirpath, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if os.path.join(dirpath, d) not in skip]
        for f in files:
            if f.endswith(".import") or f in ("project.godot", "default_bus_layout.tres"):
                yield os.path.relpath(os.path.join(dirpath, f), ROOT)


class Backup:
    """烘焙前备份编辑器会改的文件，烘完原样还回去。编辑器启动时还会把上次开着的场景都打开
    （.godot/editor/editor_layout.cfg），退出时又把烘焙场景记进去：这份也备份，启动前去掉开着的场景"""

    def __init__(self):
        self.dir = tempfile.mkdtemp(prefix="lmbake_")
        self.files = list(project_files())
        for f in self.files:
            os.makedirs(os.path.dirname(os.path.join(self.dir, f)), exist_ok=True)
            shutil.copy2(os.path.join(ROOT, f), os.path.join(self.dir, f))
        self.layout = os.path.join(ROOT, ".godot", "editor", "editor_layout.cfg")
        if os.path.exists(self.layout):
            shutil.copy2(self.layout, os.path.join(self.dir, "editor_layout.cfg"))
            with open(self.layout, encoding="utf-8") as f:
                kept = [l for l in f if not re.match(r"(open_scenes|current_scene)=", l)]
            with open(self.layout, "w", encoding="utf-8", newline="\n") as f:
                f.writelines(kept)

    def restore(self):
        restored = 0
        for f in self.files:
            b, p = os.path.join(self.dir, f), os.path.join(ROOT, f)
            if not os.path.exists(p) or not filecmp.cmp(b, p, shallow=False):
                shutil.copy2(b, p)
                restored += 1
        if restored:
            print(f"lightmap: 还原了编辑器改动的 {restored} 个设置文件")
        saved = os.path.join(self.dir, "editor_layout.cfg")
        if os.path.exists(saved):
            shutil.copy2(saved, self.layout)
        shutil.rmtree(self.dir, ignore_errors=True)


# 不碍事的：Metal 烘焙时偶尔等 GPU 超时（会接着烘完）、编辑器退出时的节点路径报错
NOISE = r"resources still in use|timeout waiting for fence|absolute paths from outside the active scene tree"


def editor_bake(scene):
    """烘一个场景；失败（编辑器报错退出、超时、没烘出数据）返回 False"""
    backup = Backup()
    try:
        rc, log = godot_bg.godot_window(["-e", "--path", ROOT, "--resolution", "960x540", scene, "--",
                                         f"--bake-lightmap={scene}"], limit=limit, exe=editor_exe())
    finally:
        backup.restore()
    godot_bg.grep(log, r"^lightmap|ERROR|error|Error", NOISE)
    if rc or not re.search(r"^lightmap baked in", log, re.M):
        print(f"lightmap: 烘焙 {scene} 失败（退出码 {rc}），完整日志：", file=sys.stderr)
        print("\n".join(log.splitlines()[-60:]), file=sys.stderr)
        return False
    return True


if only_scene:
    sys.exit(0 if editor_bake(only_scene) else 1)

# 先把导入做完（模型、.import 改过的话在这里重新导入、重新展 UV2）：导出烘焙场景的游戏和运行时用的必须是同一份网格，
# 不能等到编辑器那一步才发现模型变了、重新导入（贴图就对不上 UV2 了）
_, log = godot_bg.run([editor_exe(), "--headless", "--audio-driver", "Dummy", "--path", ROOT, "--import"])
godot_bg.grep(log, r"ERROR|SCRIPT ERROR")
lm_dir = os.path.join(ROOT, ".tmp", "lightmap")
failed = []
for k in rooms:
    print(f"== {k}: 导出烘焙场景")
    for f in glob.glob(os.path.join(lm_dir, f"{k}_src.scn")) + glob.glob(os.path.join(lm_dir, f"{k}_*_src.scn")) + \
            glob.glob(os.path.join(lm_dir, f"{k}.lmkey.json")) + glob.glob(os.path.join(lm_dir, f"{k}_*.lmkey.json")):
        os.remove(f)
    rc, log = godot_bg.godot_window(["--path", ROOT, "--resolution", "640x360", "--", f"--scene={k}", "--lm-export", *extra],
                                    limit=300)
    godot_bg.grep(log, r"^lightmap|ERROR|SCRIPT", r"resources still in use")
    if rc or not re.search(r"^lightmap: exported", log, re.M) or re.search(r"^lightmap: exported.*err=[1-9]", log, re.M):
        print(f"lightmap: 导出 {k} 的烘焙场景失败（退出码 {rc}）", file=sys.stderr)
        print("\n".join(log.splitlines()[-40:]), file=sys.stderr)
        failed.append(k)
        continue
    # 默认一份，再加每个变体一份（宿舍：日光灯开着的 dorm_tube）
    for src in glob.glob(os.path.join(lm_dir, f"{k}_src.scn")) + sorted(glob.glob(os.path.join(lm_dir, f"{k}_*_src.scn"))):
        name = os.path.basename(src)
        print(f"== {name}: 编辑器里烘焙")
        # 烘成功后 lightmap_baker.gd 把导出时记下的网格指纹放到贴图旁边（<房间>.lmkey.json），运行时对不上就退回 VoxelGI
        if not editor_bake(f"res://.tmp/lightmap/{name}"):
            failed.append(name)
if failed:
    sys.exit(f"lightmap: 失败的：{' '.join(failed)}")
