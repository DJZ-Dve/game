"""巨物「闷雷」总装：把各部件（blender/scripts/giant/ 下的 skin、fins、mouth、eyes）建出来（加 --bake 时各部件把高模烘成贴图，
assets/textures/giant/<组>_normal.png、_mask.png），合成一个蒙皮网格，按 spec.bones() 建骨架，
导出 assets/models/giant.glb（Godot 里 scripts/giant.gd、giant_motion.gd 驱动骨骼）。
规格（尺寸、曲面、骨骼、挂点、材质名、UV 约定）都在 giant/spec.py。

用法:
  blender -b --factory-startup --python blender/scripts/gen_giant.py -- [选项]
    --bake                 各部件烘焙贴图（慢，几分钟；不加只建低模，看形体够了）
    --parts=skin,mouth     只建这几个部件（默认全部；调试单个部件时配合 --preview 看）
    --preview=目录         渲染几张 Workbench 预览图到这个目录（side、top、front、belly、head、tail、q34、maw）
    --jaw=度               预览时把嘴张开这么多度（看张嘴的样子；导出的 glb 永远是闭嘴的静止姿态）
    --views=side,head      只渲染这几张
    --no-export            不导出 glb（只看预览）
    --out=路径             导出到别处（默认 assets/models/giant.glb）
每个部件模块提供 build(coll, bake=False) -> [低模网格物体]：材质用 spec.MATERIALS 里的名字，UV0 是贴图组的图集，
调过 spec.set_body_uv，顶点组（骨骼权重）已经分好；bake 时自己调 bakeutil.bake_set。
"""
import importlib
import math
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import lib  # noqa: E402
from lib import V  # noqa: E402
from giant import spec  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(ROOT, "assets", "models", "giant.glb")
PARTS = ["skin", "fins", "mouth", "eyes"]

# 预览机位：(相机位置, 看向)
VIEWS = {
    "side": (V((62, 0, 2)), V((0, 0, 0))),
    "q34": (V((34, 40, 14)), V((0, 4, 0))),
    "top": (V((8, 0, 60)), V((0, 0, 0))),
    "belly": (V((20, 6, -30)), V((0, 2, -3))),
    "front": (V((10, 46, -2)), V((0, 16, -1))),
    "head": (V((18, 34, 3)), V((0, 14, -0.5))),
    "maw": (V((3, 50, 2)), V((0, 10, -2.5))),
    "tail": (V((18, -26, 5)), V((0, -15, 0))),
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


def build_parts(names, coll, bake=False):
    objs = {}
    for name in names:
        mod = importlib.import_module("giant." + name)
        built = [o for o in mod.build(coll, bake=bake) if o is not None]
        objs[name] = built
        print(f"part {name}: {len(built)} objects, {lib.stats(built):,} tris"
              f" (budget {spec.TRI_BUDGET.get(name, 0):,})")
    return objs


def bake_curvature(objs):
    """烘曲率顶点色（lib.bake_for_export 会重建物体；顶点组名字新版 Blender 存在网格上会跟过去，
    万一没跟过去就按原顺序补回，权重才对得上）。"""
    groups = {o.name: [g.name for g in o.vertex_groups] for o in objs}
    baked = lib.bake_for_export(objs)
    for o in baked:
        if not o.vertex_groups:
            for g in groups.get(o.name, []):
                o.vertex_groups.new(name=g)
    return baked


def tail_fin_weights(mesh):
    """尾鳍伸出尾尖之外，部件都只给了 Spine_15；按位置把尾巴梢和尾鳍渐变分给 TailFin_0/1，尾鳍才能自己甩。"""
    groups = {}
    for name in ("TailFin_0", "TailFin_1"):
        groups[name] = mesh.vertex_groups.get(name) or mesh.vertex_groups.new(name=name)
    names = {g.index: g.name for g in mesh.vertex_groups}
    mw = mesh.matrix_world
    n = 0
    for v in mesh.data.vertices:
        ws = spec.tail_fin_weights((mw @ v.co).y)
        tot = sum(w for _, w in ws)
        if tot <= 1e-4:
            continue
        for ge in v.groups:
            if not names[ge.group].startswith("TailFin"):
                mesh.vertex_groups[ge.group].add([v.index], ge.weight * (1.0 - tot), 'REPLACE')
        for name, w in ws:
            if w > 1e-4:
                groups[name].add([v.index], w, 'REPLACE')
        n += 1
    print(f"tail fin weights: {n:,} verts")


def triangulate(mesh):
    """导出前三角化：glTF 导出要在三角面上算切线（法线贴图要用），四边形会报「算不出切线」。"""
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(mesh.data)
    bmesh.ops.triangulate(bm, faces=bm.faces[:], quad_method='BEAUTY', ngon_method='BEAUTY')
    bm.to_mesh(mesh.data)
    bm.free()


def build_rig(coll):
    arm = bpy.data.armatures.new("GiantRig")
    rig = bpy.data.objects.new("GiantRig", arm)
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


def pose_jaw(rig, deg):
    """预览用：把 Jaw 骨绕铰链往下转（下颌前端往下）。"""
    pb = rig.pose.bones["Jaw"]
    pb.rotation_mode = 'XYZ'
    pb.rotation_euler = (math.radians(-deg), 0.0, 0.0)
    bpy.context.view_layer.update()


def main():
    a = args()
    lib.reset_scene()
    coll = lib.collection("Giant")
    materials()
    names = a["parts"].split(",") if "parts" in a else PARTS
    parts = build_parts(names, coll, bake="bake" in a)
    allobjs = [o for lst in parts.values() for o in lst]
    allobjs = bake_curvature(allobjs)
    mesh = lib.join(allobjs, "Giant")
    if mesh:
        tail_fin_weights(mesh)
        triangulate(mesh)
    rig = build_rig(coll)
    if mesh:
        mesh.parent = rig
        mod = mesh.modifiers.new("Armature", 'ARMATURE')
        mod.object = rig
        missing = [g.name for g in mesh.vertex_groups if g.name not in rig.data.bones]
        if missing:
            print("WARNING 顶点组没有对应的骨骼:", missing[:10])
        print(f"giant: {lib.stats([mesh]):,} tris, {len(mesh.data.vertices):,} verts, "
              f"{len(rig.data.bones)} bones, materials {[m.name for m in mesh.data.materials]}")
    if "preview" in a:
        if "jaw" in a:
            pose_jaw(rig, float(a["jaw"]))
        d = a["preview"]
        os.makedirs(d, exist_ok=True)
        want = a["views"].split(",") if "views" in a else list(VIEWS)
        for k in want:
            cam, tgt = VIEWS[k]
            lib.render_preview(os.path.join(d, k + ".png"), cam, tgt, lens=35, res=(1280, 720))
        print("preview ->", d)
    if "no-export" not in a and "jaw" not in a and mesh:
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
