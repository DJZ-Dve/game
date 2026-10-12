"""高模 → 低模烘焙（Cycles，后台跑；从 giant/bakeutil.py 拷来，规格换成 watcher/spec.py）。
注意：射线没打到高模的像素是 0（法线、AO 都是），高模要比低模略大一圈、包住低模；薄的东西 extrusion / max_ray 给小。
烘焙很吃内存（几百万面的高模能到 8GB 以上），同一时间只跑一个。
每个贴图组（spec.TEXSETS）出两张图：
  <组>_normal.png  切线空间法线（OpenGL，Y+，和 Godot 一致）
  <组>_mask.png    R = AO，G = 凹槽（缝、孔、褶沟），B = 凸棱（磨损、发白），A = 部件自定的区域图（比如疤、生肉，见 spec.TEXSETS 的说明）
低模的 UV0 是这个组的图集（0～1，等密度），高模不需要 UV。

用法（部件模块里）：
    from watcher import bakeutil
    bakeutil.bake_set("skin", lows=[低模们], highs=[高模们])
高模上可以带两个点色属性（FLOAT_COLOR 或 BYTE_COLOR，点域或面角域都行）：
  "Curv"：R = 凹槽，G = 凸棱（0～1，自己算；没有就用 lib._curvature 现算）
  "Area"：R = 写进 mask.A 的区域值（0～1；没有就是 0）
  "AOv"：R = 自己算好的 AO（0～1）；有它就不用 Cycles 烘 AO（会动的部件只要细节自己的遮蔽，
         也躲开「高模高过低模时 AO 成片发黑」的问题）
烘完高模会被删掉（不进 glb）。
"""
import math
import os

import bpy
import numpy as np

import lib
from watcher import spec

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
OUT_DIR = os.path.join(ROOT, "assets", "textures", "watcher")


def _image(name, size, non_color):
    img = bpy.data.images.get(name)
    if img:
        bpy.data.images.remove(img)
    img = bpy.data.images.new(name, size, size, alpha=True, float_buffer=False)
    img.colorspace_settings.name = "Non-Color" if non_color else "sRGB"
    return img


def _target_material(img):
    """烘焙目标：低模临时用的材质，只有一个选中的图像节点。"""
    m = bpy.data.materials.new("_bake_target")
    m.use_nodes = True
    n = m.node_tree.nodes.new("ShaderNodeTexImage")
    n.image = img
    m.node_tree.nodes.active = n
    return m


def _emit_material(attr, channel_expr):
    """高模临时材质：把点色属性的某个通道当发光输出（EMIT 烘焙用）。channel_expr: 'R' / 'G'"""
    m = bpy.data.materials.new("_bake_emit_" + attr + channel_expr)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    at = nt.nodes.new("ShaderNodeAttribute")
    at.attribute_name = attr
    sep = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(at.outputs["Color"], sep.inputs["Color"])
    nt.links.new(sep.outputs["Red" if channel_expr == "R" else "Green"], em.inputs["Color"])
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    return m


def _dup_join(objs, name):
    """复制一份（含修改器实化）合成一个物体，原物体不动。"""
    dg = bpy.context.evaluated_depsgraph_get()
    copies = []
    coll = bpy.context.scene.collection
    for o in objs:
        me = bpy.data.meshes.new_from_object(o.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
        c = bpy.data.objects.new(o.name + "_bk", me)
        c.matrix_world = o.matrix_world.copy()
        coll.objects.link(c)
        copies.append(c)
    return lib.join(copies, name)


def _ensure_curv(ob):
    me = ob.data
    if "Curv" in me.attributes:
        return
    cols = lib._curvature(me, ob.name)
    n = len(me.vertices)
    a = me.attributes.new("Curv", 'FLOAT_COLOR', 'POINT')
    if cols is None:
        a.data.foreach_set("color", np.zeros(n * 4, dtype=np.float32))
        return
    c = np.stack([cols[:, 1], cols[:, 0], np.zeros(n), np.ones(n)], axis=1).astype(np.float32)
    a.data.foreach_set("color", c.flatten())


def _bake(kind, low, highs, img, extrusion, max_ray, samples=1):
    scn = bpy.context.scene
    scn.cycles.samples = samples
    # 只让高模挡光：别的物体全藏起来，低模（烘焙目标）对光线隐身——不然 AO 会被低模自己和别的部件挡出一片黑斑
    hidden = []
    for o in scn.objects:
        if o is not low and o not in highs and not o.hide_render:
            o.hide_render = True
            hidden.append(o)
    vis = {k: getattr(low, k) for k in ("visible_camera", "visible_diffuse", "visible_glossy",
                                         "visible_transmission", "visible_volume_scatter", "visible_shadow")}
    for k in vis:
        setattr(low, k, False)
    tgt = _target_material(img)
    saved = [s.material for s in low.material_slots]
    if not low.material_slots:
        low.data.materials.append(tgt)
    for s in low.material_slots:
        s.material = tgt
    bpy.ops.object.select_all(action='DESELECT')
    for h in highs:
        h.select_set(True)
    low.select_set(True)
    bpy.context.view_layer.objects.active = low
    kw = dict(type=kind, use_selected_to_active=True, cage_extrusion=extrusion, max_ray_distance=max_ray,
              margin=8, margin_type='EXTEND', use_clear=True)
    if kind == 'NORMAL':
        kw.update(normal_space='TANGENT', normal_r='POS_X', normal_g='POS_Y', normal_b='POS_Z')
    bpy.ops.object.bake(**kw)
    for s, m in zip(low.material_slots, saved):
        s.material = m
    bpy.data.materials.remove(tgt)
    for k, v in vis.items():
        setattr(low, k, v)
    for o in hidden:
        o.hide_render = False


def _pixels(img):
    a = np.empty(img.size[0] * img.size[1] * 4, dtype=np.float32)
    img.pixels.foreach_get(a)
    return a.reshape(-1, 4)


def bake_set(name, lows, highs, extrusion=0.1, max_ray=0.3, ao_samples=48, ao_distance=1.0):
    """把 highs 的细节烘到 lows（共用 spec.TEXSETS[name] 的图集 UV0）上，写 assets/textures/giant/<name>_*.png。"""
    size = spec.TEXSETS[name]["size"]
    os.makedirs(OUT_DIR, exist_ok=True)
    scn = bpy.context.scene
    scn.render.engine = 'CYCLES'
    scn.cycles.device = 'CPU'
    scn.render.bake.use_selected_to_active = True
    # AO 只看附近（默认是世界设置里的 10 米，整个大球都会互相遮成一片灰）
    world = scn.world or bpy.data.worlds.new("World")
    scn.world = world
    ao_saved = world.light_settings.distance
    world.light_settings.distance = ao_distance
    low = _dup_join(lows, "_bake_low_" + name)
    low.data.uv_layers.active = low.data.uv_layers[spec.UV_MAIN]
    # 只有一个高模、又没有修改器时直接用它（不再复制一份：4096 的高模复制一份要多吃好几 GB 内存）
    own_high = not (len(highs) == 1 and highs[0].type == 'MESH' and not highs[0].modifiers)
    high = _dup_join(highs, "_bake_high_" + name) if own_high else highs[0]
    _ensure_curv(high)
    # 法线
    img_n = _image(name + "_normal", size, True)
    _bake('NORMAL', low, [high], img_n, extrusion, max_ray)
    img_n.filepath_raw = os.path.join(OUT_DIR, name + "_normal.png")
    img_n.file_format = 'PNG'
    img_n.save()
    # AO、凹槽、凸棱、区域
    chans = []
    img = _image(name + "_tmp", size, True)
    hm = [s.material for s in high.material_slots]
    own_ao = "AOv" in high.data.attributes
    if not own_ao:
        _bake('AO', low, [high], img, extrusion, max_ray, samples=ao_samples)
        chans.append(_pixels(img)[:, 0].copy())
    for attr, ch in ((("AOv", "R"),) if own_ao else ()) + (("Curv", "R"), ("Curv", "G"), ("Area", "R")):
        if attr not in high.data.attributes:
            chans.append(np.zeros(size * size, dtype=np.float32))
            continue
        em = _emit_material(attr, ch)
        high.data.materials.clear()
        high.data.materials.append(em)
        _bake('EMIT', low, [high], img, extrusion, max_ray)
        chans.append(_pixels(img)[:, 0].copy())
        bpy.data.materials.remove(em)
    high.data.materials.clear()
    for m in hm:
        high.data.materials.append(m)
    mask = _image(name + "_mask", size, True)
    mask.pixels.foreach_set(np.stack(chans, axis=1).astype(np.float32).flatten())
    mask.filepath_raw = os.path.join(OUT_DIR, name + "_mask.png")
    mask.file_format = 'PNG'
    mask.save()
    for im in (img, img_n, mask):
        bpy.data.images.remove(im)
    for o in ((low, high) if own_high else (low,)):
        me = o.data
        bpy.data.objects.remove(o)
        if me.users == 0:
            bpy.data.meshes.remove(me)   # 删物体不会释放网格数据，复制出来的高模要手动删
    world.light_settings.distance = ao_saved
    print(f"baked {name}: {size}px -> {OUT_DIR}")


def atlas_uv(objs, name):
    """把这一组物体的 UV0 统一摆进一张图集：各岛按实际面积统一密度、转着排满 0～1、互不重叠。
    各物体先自己展好 UV0（岛的形状、接缝位置由部件决定），这里只负责缩放和排布。
    返回实际的「1 个 UV 单位 = 多少米」，同时写到 assets/textures/giant/<组>.json（着色器按它铺细节）。"""
    import json
    objs = [o for o in objs if o.type == 'MESH']
    bpy.ops.object.select_all(action='DESELECT')
    for o in objs:
        o.select_set(True)
        o.data.uv_layers.active = o.data.uv_layers[spec.UV_MAIN]
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.select_all(action='SELECT')
    bpy.ops.uv.average_islands_scale()
    bpy.ops.uv.pack_islands(rotate=True, margin=0.004, scale=True)
    bpy.ops.object.mode_set(mode='OBJECT')
    a3, auv = 0.0, 0.0
    for o in objs:
        me = o.data
        uv = me.uv_layers[spec.UV_MAIN].data
        sc2 = abs(o.matrix_world.determinant()) ** (2 / 3)   # 物体缩放对面积的影响
        for p in me.polygons:
            a3 += p.area * sc2
            pts = [uv[li].uv for li in p.loop_indices]
            s = 0.0
            for i in range(len(pts)):
                x0, y0 = pts[i]
                x1, y1 = pts[(i + 1) % len(pts)]
                s += x0 * y1 - x1 * y0
            auv += abs(s) * 0.5
    meters = math.sqrt(a3 / max(auv, 1e-9))
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, name + ".json"), "w") as f:
        json.dump({"meters": round(meters, 3), "size": spec.TEXSETS[name]["size"],
                   "texel_mm": round(meters / spec.TEXSETS[name]["size"] * 1000, 2)}, f)
    print(f"atlas {name}: 1 UV = {meters:.2f} m, texel {meters / spec.TEXSETS[name]['size'] * 1000:.1f} mm")
    return meters
