# 深海测试关卡（Godot 版 scenes/deep_sea.tscn + assets/environment/deep_sea_env.tres）：
# 海床（seabed.glb 的节点树）、潜艇（摆在海床模型里的 Spawn 点上，艇首跟 Godot 版一样朝世界的 -Z，也就是 UE 的 -Y）、
# 后期体积（手动曝光、辉光、饱和度、对比度）、指数高度雾 + 体积雾（Godot 版的雾和体积雾）。
# 灯光、雾的数值先按 Godot 版换算，再对着截图调（Scripts/render_views.py）。
# 用法：UnrealEditor-Cmd.exe Guixu.uproject -run=pythonscript -script=Scripts/build_deep_sea.py
import os

import unreal

MAP = "/Game/Maps/DeepSea"
EAL = unreal.EditorAssetLibrary


def log(msg):
    unreal.log(f"[deep_sea] {msg}")


def srgb(c):
    return [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]


def rerun(actor):
    # 改属性时编辑器会自己重跑构造；这个接口有的版本没导出给 Python，有就再跑一遍保险
    if hasattr(actor, "rerun_construction_scripts"):
        actor.rerun_construction_scripts()


def main():
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    # 每次从空关卡重搭，存的时候覆盖旧的
    world = unreal.EditorLoadingAndSavingUtils.new_blank_map(False)

    # 海床
    seabed_scene = unreal.load_asset("/Game/Models/Seabed/SA_Seabed")
    seabed = actors.spawn_actor_from_class(unreal.GuixuSceneActor, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
    seabed.set_actor_label("Seabed")
    seabed.set_editor_property("scene", seabed_scene)
    rerun(seabed)

    # 潜艇：放到 Spawn 点（节点树里的世界位置）。节点变换是相对父节点的，一路乘上去
    spawn = unreal.Vector(0, 0, 0)
    nodes = seabed_scene.nodes
    for i, n in enumerate(nodes):
        if str(n.name) == "Spawn":
            t = n.transform
            j = n.parent
            while j >= 0:
                t = t.multiply(nodes[j].transform)
                j = nodes[j].parent
            spawn = t.translation
    log(f"出生点 {spawn}")
    sub = actors.spawn_actor_from_class(unreal.Submarine, spawn, unreal.Rotator(0, 0, -90))  # Rotator(roll, pitch, yaw)
    sub.set_actor_label("Submarine")
    sub.set_editor_property("exterior_scene", unreal.load_asset("/Game/Models/SubmarineExterior/SA_SubmarineExterior"))
    sub.set_editor_property("cockpit_scene", unreal.load_asset("/Game/Models/SubmarineCockpit/SA_SubmarineCockpit"))
    rerun(sub)

    # 后期：手动曝光（Godot 版固定曝光 1.35）、辉光、调色（饱和度 0.85、对比度 1.05）
    ppv = actors.spawn_actor_from_class(unreal.PostProcessVolume, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
    ppv.set_actor_label("PostProcess")
    ppv.set_editor_property("unbound", True)
    s = ppv.settings
    s.override_auto_exposure_method = True
    s.auto_exposure_method = unreal.AutoExposureMethod.AEM_MANUAL
    s.override_auto_exposure_apply_physical_camera_exposure = True
    s.auto_exposure_apply_physical_camera_exposure = False
    s.override_auto_exposure_bias = True
    s.auto_exposure_bias = 0.0
    s.override_bloom_intensity = True
    s.bloom_intensity = 0.55
    s.override_color_saturation = True
    s.color_saturation = unreal.Vector4(0.85, 0.85, 0.85, 1.0)
    s.override_color_contrast = True
    s.color_contrast = unreal.Vector4(1.05, 1.05, 1.05, 1.0)
    s.override_vignette_intensity = True
    s.vignette_intensity = 0.25
    s.override_motion_blur_amount = True
    s.motion_blur_amount = 0.0
    ppv.set_editor_property("settings", s)

    # 雾：Godot 版深度雾密度 0.014/米、体积雾密度 0.028/米、反照率 (0.42, 0.66, 0.68)、各向异性 0.35、体积雾 80 米
    fog = actors.spawn_actor_from_class(unreal.ExponentialHeightFog, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
    fog.set_actor_label("SeaFog")
    fc = fog.get_editor_property("component")
    fc.set_editor_property("fog_density", 0.2)  # UE 的密度按每 1000 厘米算：0.2 = 0.02/米（Godot 版舱里：深度雾 0.014 + 体积雾减掉舱内削减后约 0.006）
    fc.set_editor_property("fog_height_falloff", 0.001)   # 深海里上下一样浓
    fc.set_editor_property("fog_inscattering_luminance", unreal.LinearColor(*srgb([0.0, 0.012, 0.016]), 1.0))
    fc.set_editor_property("enable_volumetric_fog", True)
    fc.set_editor_property("volumetric_fog_scattering_distribution", 0.35)
    fc.set_editor_property("volumetric_fog_albedo", unreal.Color(r=107, g=168, b=173, a=255))
    fc.set_editor_property("volumetric_fog_extinction_scale", 1.0)
    fc.set_editor_property("volumetric_fog_distance", 8000.0)
    fc.set_editor_property("volumetric_fog_start_distance", 0.0)

    # 关卡用归墟的游戏模式（开局把人放进驾驶舱）
    ws = world.get_world_settings()
    ws.set_editor_property("default_game_mode", unreal.GuixuGameMode)

    ok = unreal.EditorLoadingAndSavingUtils.save_map(world, MAP)
    log(f"存到 {MAP}：{ok}")


main()
