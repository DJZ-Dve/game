# 把 Blender 生成的 glb（assets/models/）导进 UE：每个网格一个静态网格资产（局部坐标，不烘变换），
# 节点树（名字、父子、相对变换、网格）存成 UGuixuSceneAsset（C++ 的 Scene/GuixuSceneAsset.h），运行时按名字找节点，跟 Godot 版的 find_child 一样。
# 做法：用 Interchange 把 glb 当场景导进一个临时关卡（每个节点一个 Actor），读回 Actor 的层级、变换、网格，再把临时关卡扔掉。
# 材质不导（glb 里只有名字）：网格的材质槽名就是 Blender 里的材质名（M_Deck……），由 Scripts/import_materials.py 按槽名套上 UE 材质。
# 用法（命令行无头跑）：UnrealEditor-Cmd.exe Guixu.uproject -run=pythonscript -script=Scripts/import_models.py [-- 名字 …]
import json
import os
import re
import sys
import time
import traceback

import unreal

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
# glb → (内容目录, 是不是要能走上去的复杂碰撞)
MODELS = {
    "submarine_exterior": ("/Game/Models/SubmarineExterior", False),
    "submarine_cockpit": ("/Game/Models/SubmarineCockpit", True),
    "seabed": ("/Game/Models/Seabed", True),
}


def log(msg):
    unreal.log(f"[import] {msg}")


def pipeline(materials=False):
    p = unreal.InterchangeGenericAssetsPipeline()
    p.set_editor_property("use_source_name_for_asset", True)
    common = p.get_editor_property("common_meshes_properties")
    common.set_editor_property("bake_meshes", False)          # 网格留在自己的局部坐标，变换在节点上
    common.set_editor_property("recompute_normals", False)    # 用 Blender 导出的法线（倒角、平滑组都在里面）
    common.set_editor_property("vertex_color_import_option", unreal.InterchangeVertexColorImportOption.IVCIO_REPLACE)
    mesh = p.get_editor_property("mesh_pipeline")
    mesh.set_editor_property("build_nanite", True)
    mesh.set_editor_property("collision", False)              # 碰撞下面按需要自己设
    mesh.set_editor_property("import_skeletal_meshes", False)
    mat = p.get_editor_property("material_pipeline")
    # 自建模型不导材质（按槽名套 build_materials.py 建的）；Poly Haven 道具带 PBR 材质和贴图，原样导
    mat.set_editor_property("import_materials", materials)
    mat.get_editor_property("texture_pipeline").set_editor_property("import_textures", materials)
    return p


def import_one(name, content_dir, walkable, src=None, materials=False, asset_name=None):
    src = src or os.path.join(REPO, "assets", "models", name + ".glb")
    if not os.path.exists(src):
        raise RuntimeError(f"找不到 {src}")
    unreal.EditorLoadingAndSavingUtils.new_blank_map(False)
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    actors_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    before = set(a.get_path_name() for a in actors_sub.get_all_level_actors())

    mgr = unreal.InterchangeManager.get_interchange_manager_scripted()
    params = unreal.ImportAssetParameters()
    params.is_automated = True
    params.replace_existing = True
    # 覆盖的管线只收软路径：临时对象活着的时候按它的路径找得到（Epic 文档的写法）；先留着引用，别被回收
    pipes = [pipeline(materials), unreal.InterchangeGenericLevelPipeline()]
    params.override_pipelines = [unreal.SoftObjectPath(x.get_path_name()) for x in pipes]
    t0 = time.time()
    ok = mgr.import_scene(content_dir, mgr.create_source_data(src), params)
    mgr.wait_until_all_tasks_done(True)
    log(f"{name}: import_scene={ok} 用时 {time.time() - t0:.0f} 秒")

    actors = [a for a in actors_sub.get_all_level_actors() if a.get_path_name() not in before]
    # Poly Haven 有的模型把 LOD1~3 也放在同一个文件里：只留 LOD0（Godot 版 post_import.gd 也是这么做的）
    actors = [a for a in actors if not re.search(r"_LOD[1-9]$", a.get_actor_label())]
    by_actor = {a.get_path_name(): a for a in actors}
    # 父在前：从根开始一层层往下
    children = {}
    roots = []
    for a in actors:
        par = a.get_attach_parent_actor()
        if par is not None and par.get_path_name() in by_actor:
            children.setdefault(par.get_path_name(), []).append(a)
        else:
            roots.append(a)
    order = []
    stack = sorted(roots, key=lambda x: x.get_actor_label())
    parent_of = {}
    while stack:
        a = stack.pop(0)
        order.append(a)
        kids = sorted(children.get(a.get_path_name(), []), key=lambda x: x.get_actor_label())
        for k in kids:
            parent_of[k.get_path_name()] = a.get_path_name()
        stack = kids + stack
    index = {a.get_path_name(): i for i, a in enumerate(order)}

    nodes = []
    meshes = set()
    for a in order:
        node = unreal.GuixuSceneNode()
        node.name = a.get_actor_label()
        pp = parent_of.get(a.get_path_name())
        node.parent = index[pp] if pp else -1
        root = a.root_component
        node.transform = root.get_relative_transform() if pp else a.get_actor_transform()
        sm = None
        if isinstance(a, unreal.StaticMeshActor):
            sm = a.static_mesh_component.static_mesh
        node.mesh = sm
        if sm:
            meshes.add(sm)
        nodes.append(node)

    asset_name = asset_name or "SA_" + "".join(w.capitalize() for w in name.split("_"))
    asset_path = f"{content_dir}/{asset_name}"
    if unreal.EditorAssetLibrary.does_asset_exist(asset_path):
        asset = unreal.load_asset(asset_path)
    else:
        asset = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
            asset_name, content_dir, unreal.GuixuSceneAsset, unreal.DataAssetFactory())
    asset.set_editor_property("source_file", f"assets/models/{name}.glb")
    asset.set_editor_property("nodes", nodes)

    # 能走上去的模型（舱内、海床）用三角面当碰撞
    for sm in meshes:
        if walkable:
            body = sm.get_editor_property("body_setup")
            if body:
                body.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
        unreal.EditorAssetLibrary.save_loaded_asset(sm, only_if_is_dirty=False)
    unreal.EditorAssetLibrary.save_loaded_asset(asset, only_if_is_dirty=False)

    slots = sorted({str(s.material_slot_name) for sm in meshes for s in sm.static_materials})
    log(f"{name}: {len(nodes)} 个节点，{len(meshes)} 个网格，材质槽 {len(slots)} 种 → {asset_path}")
    return {"nodes": len(nodes), "meshes": len(meshes), "slots": slots}


# Godot 版 cockpit_props.gd 的 PROPS 用到的 Poly Haven 道具（摆放规则在 C++ 的 Submarine.cpp 里）
PROPS = ["brass_diya_lantern", "vintage_radio_transceiver", "power_box_01", "vintage_spacecraft_instrument", "old_gas_mask",
         "korean_fire_extinguisher_01", "plastic_thermos", "clipboard", "binder_notebook", "signal_flashlight", "retro_multimeter",
         "medical_box", "portable_cassette_player", "round_spectacles", "digital_wrist_watch", "screwdriver", "pliers",
         "medical_tape", "modified_thermos", "office_notepads", "pocket_watch", "adjustable_wrench", "seadogs_compass"]


# 海床上摆的 Poly Haven 素材（seabed.glb 里的 Place__素材名__编号 点；Godot 版 seabed_props.gd），要有碰撞（声呐、艇撞上去）
SEABED_PROPS = ["antique_ceramic_vase_01", "brass_vase_03", "ceramic_pot", "coastal_cliff_04", "dutch_ship_medium", "moon_rock_01",
                "moon_rock_03", "moon_rock_05", "namaqualand_boulder_02", "treasure_chest", "tree_stump_02"]


def import_prop(asset):
    src = os.path.join(REPO, "assets", "third_party", "polyhaven", "models", asset, f"{asset}_2k.gltf")
    return import_one(asset, f"/Game/Props/{asset}", asset in SEABED_PROPS, src=src, materials=True, asset_name=f"SA_{asset}")


def main():
    # 一次进程只导一个（Interchange 在命令行模式下连导第二个时任务没跑完就返回了）：环境变量 GUIXU_IMPORT 指定
    names = [n for n in os.environ.get("GUIXU_IMPORT", "").split(",") if n] or list(MODELS)[:1]
    report = {}
    if names == ["props"]:
        names = ["prop:" + a for a in PROPS]
    for n in names:
        try:
            report[n] = import_prop(n[5:]) if n.startswith("prop:") else import_one(n, *MODELS[n])
        except Exception:
            report[n] = {"error": traceback.format_exc()}
            unreal.log_error(report[n]["error"])
    out = os.path.join(REPO, ".tmp", "ue", "import_" + re.sub(r"[^A-Za-z0-9_]+", "_", "_".join(names))[:80] + ".json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    log(f"结果写到 {out}")


main()
