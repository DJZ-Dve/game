# 在完整的 UE 编辑器里跑（-ExecutePythonScript，由 Scripts/ue_bg.py 开在后台桌面上）：打开关卡，按任务里的机位拍图。
# 机位跟 Godot 版的 tools/capture.py 一样写，好拿两边的图对比：
#   {"name": "aft", "at": [x, z], "yaw": 度, "pitch": 度}   站在舱里：艇身局部坐标（Godot 的米，x 右、z 往艇尾），眼睛离甲板 1.62 米，
#                                                          yaw 0 朝艇首、180 朝艇尾，pitch 正的往上看
#   {"name": "console", "node": "Anchor_Eye", "yaw": 0, "pitch": 0}   挂点（驾驶舱模型里的节点）的位置和朝向，yaw/pitch 是相对偏移
#   {"name": "x", "loc": [x, y, z], "rot": [pitch, yaw, roll]}   UE 世界坐标（厘米）
# 任务文件：{"map": "/Game/Maps/DeepSea", "out_dir": "...", "size": [1600, 900], "fov_v": 72, "frames": 64, "warm_frames": 240,
#           "views": [...], "cvars": ["r.xxx 1"]}
# 拍完写 <任务>.done.json，放开编辑器（-ExecutePythonScript 的执行器会关掉编辑器）。
import json
import math
import os
import time
import traceback

import unreal

JOB_PATH = os.environ.get("GUIXU_MH_JOB", "")
DECK_Y = -0.9      # Godot 版舱里甲板的高度（艇身局部坐标，米）
EYE_HEIGHT = 1.62


def log(msg):
    unreal.log(f"[views] {msg}")


def godot_dir(yaw_deg, pitch_deg):
    """Godot 的视线（-Z 绕 Y 转 yaw，再抬 pitch）→ UE 局部方向（x 不变，y、z 对调）"""
    y, p = math.radians(yaw_deg), math.radians(pitch_deg)
    g = (-math.sin(y) * math.cos(p), math.sin(p), -math.cos(y) * math.cos(p))
    return unreal.Vector(g[0], g[2], g[1])


class Runner:
    def __init__(self, cfg):
        self.cfg = cfg
        self.views = cfg["views"]
        self.size = cfg.get("size", [1600, 900])
        self.frames = cfg.get("frames", 64)
        self.warm = cfg.get("warm_frames", 240)
        self.out_dir = cfg["out_dir"]
        self.state = "boot"
        self.wait = 0
        self.busy = False
        self.index = 0
        self.capture = None
        self.rt = None
        self.handle = None
        self.results = []
        self.errors = []
        self.actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        self.editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)

    def world(self):
        return self.editor.get_editor_world()

    def console(self, cmd):
        unreal.SystemLibrary.execute_console_command(self.world(), cmd)

    def tick(self, _dt):
        if self.busy:
            return
        self.busy = True
        try:
            if self.wait > 0:
                self.wait -= 1
                if self.state in ("warm", "shoot"):
                    self.capture.capture_component2d.capture_scene()
                return
            getattr(self, "s_" + self.state)()
        except Exception:
            err = traceback.format_exc()
            unreal.log_error(err)
            self.errors.append(err)
            self.state = "done"
        finally:
            self.busy = False

    def s_boot(self):
        for cv in self.cfg.get("cvars", []):
            self.console(cv)
        unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).load_level(self.cfg.get("map", "/Game/Maps/DeepSea"))
        self.state = "stage"
        self.wait = 10

    def s_stage(self):
        w, h = self.size
        self.rt = unreal.RenderingLibrary.create_render_target2d(self.world(), w, h,
                                                                 unreal.TextureRenderTargetFormat.RTF_RGBA8_SRGB,
                                                                 unreal.LinearColor(0, 0, 0, 1), False)
        cap = self.actors.spawn_actor_from_class(unreal.SceneCapture2D, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
        comp = cap.capture_component2d
        comp.set_editor_property("texture_target", self.rt)
        comp.set_editor_property("capture_source", unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR)
        comp.set_editor_property("capture_every_frame", False)
        comp.set_editor_property("capture_on_movement", False)
        comp.set_editor_property("always_persist_rendering_state", True)
        vfov = math.radians(self.cfg.get("fov_v", 72.0))
        hfov = math.degrees(2 * math.atan(math.tan(vfov / 2) * w / h))
        comp.set_editor_property("fov_angle", hfov)
        self.capture = cap
        os.makedirs(self.out_dir, exist_ok=True)
        subs = [a for a in self.actors.get_all_level_actors() if isinstance(a, unreal.Submarine)]
        self.sub = subs[0] if subs else None
        log(f"潜艇：{self.sub.get_actor_label() if self.sub else '没有'}；水平视角 {hfov:.1f}°")
        self.place(self.views[0])
        self.state = "warm"
        self.wait = self.warm // 2

    def s_warm(self):
        t0 = time.time()
        self.console("Editor.AsyncAssetCompilationFinishAll")
        log(f"等编译 {time.time() - t0:.0f} 秒")
        self.state = "warm2"
        self.wait = self.warm // 2

    def s_warm2(self):
        self.console("Editor.AsyncAssetCompilationFinishAll")
        self.start_view()

    def start_view(self):
        self.place(self.views[self.index])
        self.state = "shoot"
        self.wait = self.frames

    def s_shoot(self):
        v = self.views[self.index]
        self.capture.capture_component2d.capture_scene()
        name = f"{v['name']}.png"
        unreal.RenderingLibrary.export_render_target(self.world(), self.rt, self.out_dir, name)
        self.results.append(os.path.join(self.out_dir, name))
        log(f"拍好 {name}")
        self.index += 1
        if self.index < len(self.views):
            self.start_view()
        else:
            self.state = "done"

    def s_done(self):
        with open(JOB_PATH + ".done.json", "w", encoding="utf-8", newline="\n") as f:
            json.dump({"results": self.results, "errors": self.errors}, f, ensure_ascii=False, indent=1)
        if self.handle is not None:
            unreal.unregister_slate_post_tick_callback(self.handle)
            self.handle = None
        log("全部拍完")
        unreal.EditorPythonScripting.set_keep_python_script_alive(False)

    def component(self, name):
        for c in self.sub.get_components_by_class(unreal.SceneComponent):
            if c.get_name() in (name, "Cab_" + name, "Ext_" + name):
                return c
        raise RuntimeError(f"潜艇上找不到节点 {name}")

    def place(self, v):
        if "loc" in v:
            loc = unreal.Vector(*v["loc"])
            r = v.get("rot", [0, 0, 0])
            rot = unreal.Rotator(roll=r[2], pitch=r[0], yaw=r[1])
        else:
            if "node" in v:
                frame = self.component(v["node"]).get_world_transform()
                local = unreal.Vector(0, 0, 0)
            else:
                frame = self.sub.get_editor_property("Body").get_world_transform()
                x, z = v.get("at", [0.0, 0.0])
                local = unreal.Vector(x * 100, z * 100, (DECK_Y + EYE_HEIGHT) * 100)
            # 节点、艇身的缩放不算进来（只要位置和朝向）
            frame = unreal.Transform(frame.translation, frame.rotation.rotator(), unreal.Vector(1, 1, 1))
            loc = frame.transform_location(local)
            d = frame.transform_direction(godot_dir(v.get("yaw", 0.0), v.get("pitch", 0.0)))
            rot = unreal.MathLibrary.make_rot_from_x(d)
        self.capture.set_actor_location_and_rotation(loc, rot, False, False)


def main():
    if not JOB_PATH:
        unreal.log_error("[views] 没有任务文件（环境变量 GUIXU_MH_JOB）")
        return
    with open(JOB_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    unreal.EditorPythonScripting.set_keep_python_script_alive(True)
    runner = Runner(cfg)
    runner.handle = unreal.register_slate_post_tick_callback(runner.tick)
    unreal._guixu_views = runner
    log(f"任务 {JOB_PATH}")


main()
