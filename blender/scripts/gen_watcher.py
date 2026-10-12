"""巨物「大眼」总装：把各部件（blender/scripts/watcher/ 下的 shell、flesh、paddles、eye）建出来（加 --bake 时各部件把高模烘成贴图，
assets/textures/watcher/<组>_normal.png、_mask.png），合成一个蒙皮网格，按 spec.bones() 建骨架，导出 assets/models/watcher.glb
（Godot 里 scripts/watcher.gd、watcher_motion.gd 驱动骨骼）。规格（尺寸、曲面、骨骼、挂点、材质、贴图组）都在 watcher/spec.py。

用法:
  blender -b --factory-startup --python blender/scripts/gen_watcher.py -- [选项]
    --bake                 各部件烘焙贴图（慢；不加只建低模，看形体够了）。很吃内存，同一时间只跑一个
    --parts=shell,eye      只建这几个部件（默认全部）
    --preview=目录         渲染 Workbench 预览图（front、q34、side、top、below、eye、back）
    --views=front,eye      只渲染这几张
    --lid=0~1              预览时眼睑闭合程度（1 全闭）
    --look=左右度,上下度   预览时眼球转动
    --no-export            不导出 glb
    --out=路径             导出到别处（默认 assets/models/watcher.glb）
每个部件模块提供 build(coll, bake=False) -> [低模网格物体]：材质用 spec.MATERIALS 里的名字，UV0 是贴图组的图集，
顶点组（骨骼权重）已经分好；bake 时自己调 bakeutil.bake_set。
"""
import importlib
import math
import os
import sys

import bpy
import bmesh

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import lib  # noqa: E402
from lib import V  # noqa: E402
from watcher import spec  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(ROOT, "assets", "models", "watcher.glb")
PARTS = ["flesh", "shell", "paddles", "eye"]

VIEWS = {
    "front": (V((6, 42, 2)), V((0, 0, 0))),
    "q34": (V((30, 30, 14)), V((0, 0, -1))),
    "side": (V((45, 0, 3)), V((0, 0, -1))),
    "top": (V((4, 2, 46)), V((0, 0, 0))),
    "below": (V((20, 18, -30)), V((0, 0, -2))),
    "back": (V((-10, -40, 8)), V((0, 0, 0))),
    "eye": (V((4, 22, 3)), V((0, spec.EYE_CENTER.y, 0))),
}


def args():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = {}
    for x in a:
        if x.startswith("--"):
            k, _, v = x[2:].partition("=")
            out[k] = v if v else "1"
    return out


def materials():
    for name, (col, rough) in spec.MATERIALS.items():
        lib.material(name, col, roughness=rough)
    # 角膜在 Workbench 预览里半透明（不然整个挡住虹膜）；导出后 Godot 里换成正式材质，不影响
    m = bpy.data.materials["M_WatcherCornea"]
    m.diffuse_color = (*m.diffuse_color[:3], 0.12)
    m.surface_render_method = 'BLENDED'


def build_parts(names, coll, bake=False):
    objs = {}
    for name in names:
        mod = importlib.import_module("watcher." + name)
        built = [o for o in mod.build(coll, bake=bake) if o is not None]
        objs[name] = built
        print(f"part {name}: {len(built)} objects, {lib.stats(built):,} tris"
              f" (budget {spec.TRI_BUDGET.get(name, 0):,})")
    return objs


def bake_curvature(objs):
    """烘低模的曲率顶点色（lib.bake_for_export 会重建物体，顶点组没跟过去的话按原顺序补回）。"""
    groups = {o.name: [g.name for g in o.vertex_groups] for o in objs}
    baked = lib.bake_for_export(objs)
    for o in baked:
        if not o.vertex_groups:
            for g in groups.get(o.name, []):
                o.vertex_groups.new(name=g)
    return baked


def triangulate(mesh):
    """导出前三角化：glTF 导出要在三角面上算切线（法线贴图要用）。"""
    bm = bmesh.new()
    bm.from_mesh(mesh.data)
    bmesh.ops.triangulate(bm, faces=bm.faces[:], quad_method='BEAUTY', ngon_method='BEAUTY')
    bm.to_mesh(mesh.data)
    bm.free()


def build_rig(coll):
    arm = bpy.data.armatures.new("WatcherRig")
    rig = bpy.data.objects.new("WatcherRig", arm)
    coll.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    with bpy.context.temp_override(active_object=rig, object=rig):
        bpy.ops.object.mode_set(mode='EDIT')
        eb = arm.edit_bones
        for name, head, tail, parent in spec.bones():
            b = eb.new(name)
            b.head = head
            b.tail = tail
            b.roll = 0.0
            if parent:
                b.parent = eb[parent]
                b.use_connect = (b.parent.tail - b.head).length < 1e-4
        bpy.ops.object.mode_set(mode='OBJECT')
    return rig


def pose_preview(rig, a):
    """预览用：闭眼、转眼。"""
    if "lid" in a:
        t = float(a["lid"])
        for nm, sgn in (("LidUp", -1), ("LidLo", 1)):
            pb = rig.pose.bones[nm]
            pb.rotation_mode = 'XYZ'
            pb.rotation_euler = (sgn * spec.LID_CLOSE * t, 0.0, 0.0)
    if "look" in a:
        yaw, pitch = (float(x) for x in a["look"].split(","))
        pb = rig.pose.bones["Eye"]
        pb.rotation_mode = 'XYZ'
        pb.rotation_euler = (math.radians(pitch), 0.0, math.radians(-yaw))
    bpy.context.view_layer.update()


def main():
    a = args()
    lib.reset_scene()
    coll = lib.collection("Watcher")
    materials()
    names = a["parts"].split(",") if "parts" in a else PARTS
    parts = build_parts(names, coll, bake="bake" in a)
    allobjs = bake_curvature([o for lst in parts.values() for o in lst])
    mesh = lib.join(allobjs, "Watcher")
    if mesh:
        triangulate(mesh)
    rig = build_rig(coll)
    if mesh:
        mesh.parent = rig
        mod = mesh.modifiers.new("Armature", 'ARMATURE')
        mod.object = rig
        missing = [g.name for g in mesh.vertex_groups if g.name not in rig.data.bones]
        if missing:
            print("WARNING 顶点组没有对应的骨骼:", missing[:10])
        print(f"watcher: {lib.stats([mesh]):,} tris, {len(mesh.data.vertices):,} verts, "
              f"{len(rig.data.bones)} bones, materials {[m.name for m in mesh.data.materials]}")
    posed = "lid" in a or "look" in a
    if "preview" in a:
        pose_preview(rig, a)
        d = a["preview"]
        os.makedirs(d, exist_ok=True)
        for k in (a["views"].split(",") if "views" in a else VIEWS):
            cam, tgt = VIEWS[k]
            lib.render_preview(os.path.join(d, k + ".png"), cam, tgt, lens=35, res=(1280, 720))
        print("preview ->", d)
    if "no-export" not in a and not posed and mesh:
        out = a.get("out", OUT)
        bpy.ops.object.select_all(action='DESELECT')
        mesh.select_set(True)
        rig.select_set(True)
        bpy.ops.export_scene.gltf(
            filepath=out, export_format='GLB', use_selection=True, export_apply=False, export_yup=True,
            export_texcoords=True, export_normals=True, export_tangents=True,
            export_vertex_color='NAME', export_vertex_color_name='Wear', export_all_vertex_colors=False,
            export_skins=True, export_def_bones=False, export_animations=False, export_morph=False,
            export_materials='EXPORT', export_cameras=False, export_lights=False, export_extras=False)
        print("exported", out)


main()
