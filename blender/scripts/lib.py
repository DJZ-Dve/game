"""Blender 建模辅助函数：几何体生成、材质、导出前烘焙（曲率顶点色）、glTF 导出。

坐标约定（Blender）：+Y 朝前，+Z 朝上，+X 朝右。导出 glTF 后在 Godot 里就是 -Z 朝前。
"""
import math
import bpy
import bmesh
import numpy as np
from mathutils import Vector, Matrix

V = Vector


# ----------------------------------------------------------------------------- 场景
def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.unit_settings.system = 'METRIC'


def collection(name, parent=None):
    if name in bpy.data.collections:
        return bpy.data.collections[name]
    c = bpy.data.collections.new(name)
    (parent or bpy.context.scene.collection).children.link(c)
    return c


# ----------------------------------------------------------------------------- 材质
def material(name, color, metallic=0.0, roughness=0.6, emission=None, strength=1.0, alpha=1.0):
    """只设置基础参数；正式外观由 Godot 里同名的材质替换。"""
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    m = bpy.data.materials.new(name)
    try:
        m.use_nodes = True
    except AttributeError:
        pass
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    if emission:
        bsdf.inputs["Emission Color"].default_value = (*emission, 1.0)
        bsdf.inputs["Emission Strength"].default_value = strength
    if alpha < 1.0:
        bsdf.inputs["Alpha"].default_value = alpha
    m.diffuse_color = (*color, alpha)
    m.metallic = metallic
    m.roughness = roughness
    return m


# ----------------------------------------------------------------------------- 矩阵
def frame(origin, forward, up=V((0, 0, 1))):
    """局部 Z = forward，局部 Y 尽量贴近 up。"""
    z = V(forward).normalized()
    up = V(up)
    if abs(z.dot(up.normalized())) > 0.999:
        up = V((0, 1, 0)) if abs(z.y) < 0.9 else V((1, 0, 0))
    x = up.cross(z).normalized()
    y = z.cross(x).normalized()
    m = Matrix((
        (x.x, y.x, z.x, origin[0]),
        (x.y, y.y, z.y, origin[1]),
        (x.z, y.z, z.z, origin[2]),
        (0, 0, 0, 1),
    ))
    return m


def T(x=0.0, y=0.0, z=0.0):
    return Matrix.Translation((x, y, z))


def R(angle_deg, axis):
    return Matrix.Rotation(math.radians(angle_deg), 4, axis)


def S(x, y=None, z=None):
    y = x if y is None else y
    z = x if z is None else z
    return Matrix.Diagonal((x, y, z, 1.0))


def sph(az_deg, el_deg, dist):
    """球坐标 -> 点。方位角从 +Y 往 +X 转，仰角向 +Z。"""
    a, e = math.radians(az_deg), math.radians(el_deg)
    return V((math.sin(a) * math.cos(e) * dist, math.cos(a) * math.cos(e) * dist, math.sin(e) * dist))


def wall_frame(az, el, dist, look_at=V((0, 0.15, 0.05))):
    """贴在舱壁上、正面朝向驾驶员的局部坐标系（局部 Z 指向驾驶员，Y 朝上）。"""
    p = sph(az, el, dist)
    return frame(p, (V(look_at) - p).normalized())


# ----------------------------------------------------------------------------- bmesh 基础体
def bm_new():
    return bmesh.new()


def cylinder(bm, r, depth, segs=32, M=Matrix(), r2=None, caps=True):
    """沿局部 Z 的圆柱/圆台，底面在 z=0，顶面在 z=depth。"""
    r2 = r if r2 is None else r2
    bmesh.ops.create_cone(bm, cap_ends=caps, cap_tris=False, segments=segs,
                          radius1=r, radius2=r2, depth=depth, matrix=M @ T(0, 0, depth / 2))


def box(bm, sx, sy, sz, M=Matrix()):
    """中心在原点的长方体。"""
    bmesh.ops.create_cube(bm, size=1.0, matrix=M @ S(sx, sy, sz))


def uvsphere(bm, r, u=32, v=16, M=Matrix()):
    bmesh.ops.create_uvsphere(bm, u_segments=u, v_segments=v, radius=r, matrix=M)


def _grid_faces(bm, rings, closed_u=True, flip=False):
    """rings: list[list[BMVert]]，相邻环之间连四边形。"""
    faces = []
    n = len(rings[0])
    for i in range(len(rings) - 1):
        a, b = rings[i], rings[i + 1]
        rng = range(n) if closed_u else range(n - 1)
        for j in rng:
            k = (j + 1) % n
            quad = [a[j], a[k], b[k], b[j]]
            if flip:
                quad.reverse()
            try:
                faces.append(bm.faces.new(quad))
            except ValueError:
                pass
    return faces


def lathe(bm, profile, segs=48, M=Matrix(), cap_start=False, cap_end=False, flip=False):
    """绕局部 Z 旋转剖面。profile: [(r, z), ...]，从下到上排列时法线朝外。"""
    rings = []
    for r, z in profile:
        ring = []
        for i in range(segs):
            a = 2 * math.pi * i / segs
            ring.append(bm.verts.new(M @ V((math.cos(a) * r, math.sin(a) * r, z))))
        rings.append(ring)
    _grid_faces(bm, rings, flip=flip)
    if cap_start and profile[0][0] > 1e-6:
        f = bm.faces.new(list(reversed(rings[0])) if not flip else rings[0])
    if cap_end and profile[-1][0] > 1e-6:
        f = bm.faces.new(rings[-1] if not flip else list(reversed(rings[-1])))
    return rings


def torus(bm, R_, r, segs=48, segs_minor=12, M=Matrix()):
    prof = []
    for i in range(segs_minor + 1):
        a = 2 * math.pi * i / segs_minor
        prof.append((R_ + math.cos(a) * r, math.sin(a) * r))
    rings = lathe(bm, prof[:-1], segs, M)
    # 闭合小圆方向
    _grid_faces(bm, [rings[-1], rings[0]])


def catmull(points, samples=8, closed=False):
    """Catmull-Rom 平滑折线。"""
    pts = [V(p) for p in points]
    if len(pts) < 3:
        return pts
    out = []
    n = len(pts)
    rng = range(n) if closed else range(n - 1)
    for i in rng:
        p0 = pts[(i - 1) % n] if (closed or i > 0) else pts[0] * 2 - pts[1]
        p1 = pts[i]
        p2 = pts[(i + 1) % n]
        p3 = pts[(i + 2) % n] if (closed or i + 2 < n) else pts[-1] * 2 - pts[-2]
        for s in range(samples):
            t = s / samples
            t2, t3 = t * t, t * t * t
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2
                              + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    if not closed:
        out.append(pts[-1])
    return out


def circle_profile(r, segs=16):
    return [(math.cos(2 * math.pi * i / segs) * r, math.sin(2 * math.pi * i / segs) * r) for i in range(segs)]


def rect_profile(w, h, bevel=0.0):
    if bevel <= 0:
        return [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]
    pts = []
    for cx, cy, a0 in ((w / 2 - bevel, -h / 2 + bevel, -90), (w / 2 - bevel, h / 2 - bevel, 0),
                       (-w / 2 + bevel, h / 2 - bevel, 90), (-w / 2 + bevel, -h / 2 + bevel, 180)):
        for k in range(4):
            a = math.radians(a0 + k * 30)
            pts.append((cx + math.cos(a) * bevel, cy + math.sin(a) * bevel))
    return pts


def sweep(bm, path, profile, closed=False, caps=True, up_hint=V((0, 0, 1)), scales=None):
    """沿路径扫掠 2D 剖面（平行传输标架）。"""
    path = [V(p) for p in path]
    n = len(path)
    tangents = []
    for i in range(n):
        if closed:
            t = path[(i + 1) % n] - path[(i - 1) % n]
        else:
            t = path[min(i + 1, n - 1)] - path[max(i - 1, 0)]
        tangents.append(t.normalized())
    nrm = up_hint.cross(tangents[0])
    if nrm.length < 1e-4:
        nrm = V((1, 0, 0)).cross(tangents[0])
    nrm.normalize()
    rings = []
    prev_t = tangents[0]
    for i in range(n):
        t = tangents[i]
        rot = prev_t.rotation_difference(t)
        nrm = (rot @ nrm).normalized()
        prev_t = t
        b = t.cross(nrm).normalized()
        sc = scales[i] if scales else 1.0
        ring = [bm.verts.new(path[i] + (nrm * px + b * py) * sc) for px, py in profile]
        rings.append(ring)
    if closed:
        rings.append(rings[0])
    _grid_faces(bm, rings)
    if caps and not closed:
        try:
            bm.faces.new(list(reversed(rings[0])))
            bm.faces.new(rings[-1])
        except ValueError:
            pass
    return rings


def pipe(bm, points, r, segs=16, samples=10, caps=True, closed=False):
    sweep(bm, catmull(points, samples, closed) if len(points) > 2 else points,
          circle_profile(r, segs), closed=closed, caps=caps)


def helix(center_start, center_end, radius, turns, samples_per_turn=24):
    a, b = V(center_start), V(center_end)
    axis = (b - a)
    L = axis.length
    z = axis.normalized()
    x = z.orthogonal().normalized()
    y = z.cross(x)
    pts = []
    total = int(turns * samples_per_turn)
    for i in range(total + 1):
        t = i / total
        ang = 2 * math.pi * turns * t
        pts.append(a + z * L * t + (x * math.cos(ang) + y * math.sin(ang)) * radius)
    return pts


# ----------------------------------------------------------------------------- 对象
def to_object(bm, name, coll, mat=None, smooth=True, sharp_angle=35.0, recalc=True):
    if recalc:
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-6)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    if mat is not None:
        me.materials.append(mat)
    if smooth:
        me.shade_smooth()
        if sharp_angle:
            me.set_sharp_from_angle(angle=math.radians(sharp_angle))
    else:
        me.shade_flat()
    return ob


def build(name, coll, mat, fn, smooth=True, sharp_angle=35.0, recalc=True, bevel=None, subsurf=0):
    """fn(bm) 往 bmesh 里加几何体，然后生成对象并加修改器。"""
    bm = bm_new()
    fn(bm)
    ob = to_object(bm, name, coll, mat, smooth, sharp_angle, recalc)
    if bevel:
        add_bevel(ob, *bevel) if isinstance(bevel, tuple) else add_bevel(ob, bevel)
    if subsurf:
        add_subsurf(ob, subsurf)
    return ob


def add_bevel(ob, width=0.004, segments=2, angle=30.0):
    m = ob.modifiers.new("Bevel", 'BEVEL')
    m.width = width
    m.segments = segments
    m.limit_method = 'ANGLE'
    m.angle_limit = math.radians(angle)
    m.harden_normals = True
    return m


def add_subsurf(ob, levels=1):
    m = ob.modifiers.new("Subsurf", 'SUBSURF')
    m.levels = levels
    m.render_levels = levels
    return m


def add_solidify(ob, thickness, offset=-1.0):
    m = ob.modifiers.new("Solidify", 'SOLIDIFY')
    m.thickness = thickness
    m.offset = offset
    m.use_even_offset = True
    return m


def empty(name, coll, M, size=0.05):
    ob = bpy.data.objects.new(name, None)
    ob.empty_display_type = 'ARROWS'
    ob.empty_display_size = size
    ob.matrix_world = M
    coll.objects.link(ob)
    return ob


_fonts = {}


def text_mesh(text, name, coll, mat, M, size=0.02, extrude=0.0008, font_path=None, align='CENTER', resolution=3):
    """文字转网格（字体文件需允许嵌入；字体放在 blender/fonts/，都是 SIL OFL 授权）。"""
    if font_path not in _fonts:
        _fonts[font_path] = bpy.data.fonts.load(font_path) if font_path else None
    cu = bpy.data.curves.new(name + "_txt", 'FONT')
    cu.body = text
    if _fonts[font_path]:
        cu.font = _fonts[font_path]
    cu.size = size
    cu.extrude = extrude
    cu.align_x = align
    cu.align_y = 'CENTER'
    cu.resolution_u = resolution
    tmp = bpy.data.objects.new(name + "_tmp", cu)
    coll.objects.link(tmp)
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(tmp.evaluated_get(dg))
    bpy.data.objects.remove(tmp)
    bpy.data.curves.remove(cu)
    # 不同字体的字身大小差别很大：按包围盒把字高统一成 size
    if len(me.vertices):
        ys = [v.co.y for v in me.vertices]
        h = max(ys) - min(ys)
        if h > 1e-6:
            k = size / h
            me.transform(Matrix.Diagonal((k, k, 1.0, 1.0)))
            cy = (max(ys) + min(ys)) / 2 * k
            me.transform(Matrix.Translation((0, -cy, 0)))
    me.transform(M)
    me.materials.clear()
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    return ob


# ----------------------------------------------------------------------------- 导出前处理
def _curvature(me, strength=4.0, blur=6, threshold=0.03):
    n = len(me.vertices)
    if n == 0 or len(me.edges) == 0:
        return None
    co = np.empty(n * 3, dtype=np.float32)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    nor = np.empty(n * 3, dtype=np.float32)
    me.vertex_normals.foreach_get("vector", nor)
    nor = nor.reshape(-1, 3)
    e = np.empty(len(me.edges) * 2, dtype=np.int32)
    me.edges.foreach_get("vertices", e)
    e = e.reshape(-1, 2)
    d = co[e[:, 1]] - co[e[:, 0]]
    d /= (np.linalg.norm(d, axis=1)[:, None] + 1e-9)
    acc = np.zeros(n, dtype=np.float32)
    cnt = np.zeros(n, dtype=np.float32)
    np.add.at(acc, e[:, 0], (d * nor[e[:, 0]]).sum(1))
    np.add.at(acc, e[:, 1], (-d * nor[e[:, 1]]).sum(1))
    np.add.at(cnt, e[:, 0], 1)
    np.add.at(cnt, e[:, 1], 1)
    cnt = np.maximum(cnt, 1)
    c = acc / cnt  # >0 凹（缝隙），<0 凸（棱边）
    for _ in range(blur):
        s = np.zeros(n, dtype=np.float32)
        np.add.at(s, e[:, 0], c[e[:, 1]])
        np.add.at(s, e[:, 1], c[e[:, 0]])
        c = 0.5 * c + 0.5 * s / cnt
    # 去掉细分网格上的微小起伏（否则大曲面上会出现一圈圈条纹）
    edge = np.clip((-c - threshold) * strength, 0, 1)
    cav = np.clip((c - threshold) * strength, 0, 1)
    rnd = np.full(n, np.random.random(), dtype=np.float32)
    return np.stack([edge, cav, rnd, np.ones(n, dtype=np.float32)], axis=1)


def bake_for_export(objs, curvature=True):
    """把修改器、曲线、文字全部实化成网格，并写入曲率顶点色（R=棱边 G=凹槽 B=随机）。"""
    dg = bpy.context.evaluated_depsgraph_get()
    out = []
    for ob in objs:
        if ob.type not in {'MESH', 'CURVE', 'FONT'}:
            out.append(ob)
            continue
        me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
        if curvature:
            cols = _curvature(me)
            if cols is not None:
                # 统一按面角（CORNER）存，合并不同对象时才不会因为域不同出问题
                attr = me.color_attributes.new("Wear", 'BYTE_COLOR', 'CORNER')
                lv = np.empty(len(me.loops), dtype=np.int32)
                me.loops.foreach_get("vertex_index", lv)
                c = cols[lv].copy()
                bev = me.attributes.get("bev")
                if bev is not None and bev.domain == 'FACE':
                    # 倒角盒子：同一个顶点在平面上不磨、在倒角上磨
                    fb = np.empty(len(me.polygons), dtype=np.int32)
                    bev.data.foreach_get("value", fb)
                    ls = np.empty(len(me.polygons), dtype=np.int32)
                    me.polygons.foreach_get("loop_total", ls)
                    lb = np.repeat(fb, ls)
                    c[lb == 1, 0] = 0.0
                    c[lb == 2, 0] = 1.0
                attr.data.foreach_set("color", c.flatten())
                me.color_attributes.active_color = attr
                me.color_attributes.render_color_index = me.color_attributes.active_color_index
        new = bpy.data.objects.new(ob.name, me)
        name = ob.name
        for c in ob.users_collection:
            c.objects.link(new)
        mw = ob.matrix_world.copy()
        bpy.data.objects.remove(ob)
        new.name = name
        new.data.name = name
        new.matrix_world = mw
        out.append(new)
    return out


def join(objs, name):
    objs = [o for o in objs if o.type == 'MESH']
    if not objs:
        return None
    if len(objs) == 1:
        objs[0].name = name
        return objs[0]
    bpy.ops.object.select_all(action='DESELECT')
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    with bpy.context.temp_override(active_object=objs[0], object=objs[0],
                                   selected_objects=objs, selected_editable_objects=objs):
        bpy.ops.object.join()
    objs[0].name = name
    objs[0].data.name = name
    return objs[0]


def export_glb(path, objs):
    bpy.ops.object.select_all(action='DESELECT')
    for o in objs:
        o.select_set(True)
    bpy.ops.export_scene.gltf(
        filepath=path, export_format='GLB', use_selection=True, export_apply=True,
        export_yup=True, export_texcoords=True, export_normals=True, export_tangents=False,
        # 按名字导出 Wear：'ACTIVE' 模式下多材质网格只有第一个材质的图元带顶点色，其余全变成白色
        export_vertex_color='NAME', export_vertex_color_name='Wear', export_all_vertex_colors=False,
        export_materials='EXPORT', export_cameras=False,
        export_lights=False, export_animations=False, export_extras=False)


def stats(objs):
    tris = 0
    for o in objs:
        if o.type == 'MESH':
            o.data.calc_loop_triangles()
            tris += len(o.data.loop_triangles)
    return tris


# ----------------------------------------------------------------------------- 预览渲染
def render_preview(path, cam_pos, target, lens=35, res=(1280, 720), hide=()):
    scn = bpy.context.scene
    scn.render.engine = 'BLENDER_WORKBENCH'
    scn.display.shading.light = 'STUDIO'
    scn.display.shading.color_type = 'MATERIAL'
    scn.display.shading.show_cavity = True
    scn.display.shading.cavity_type = 'BOTH'
    scn.display.shading.show_shadows = False
    scn.display.shading.show_specular_highlight = True
    scn.render.resolution_x, scn.render.resolution_y = res
    scn.render.film_transparent = False
    world = scn.world or bpy.data.worlds.new("World")
    scn.world = world
    world.color = (0.05, 0.06, 0.07)
    cam_data = bpy.data.cameras.get("PreviewCam") or bpy.data.cameras.new("PreviewCam")
    cam_data.lens = lens
    cam_data.clip_start = 0.01
    cam = bpy.data.objects.get("PreviewCam") or bpy.data.objects.new("PreviewCam", cam_data)
    if cam.name not in scn.collection.objects:
        scn.collection.objects.link(cam)
    d = (V(target) - V(cam_pos)).normalized()
    cam.matrix_world = frame(cam_pos, -d)  # 相机看向 -Z
    scn.camera = cam
    hidden = []
    for o in hide:
        if not o.hide_render:
            o.hide_render = True
            hidden.append(o)
    scn.render.filepath = path
    bpy.ops.render.render(write_still=True)
    for o in hidden:
        o.hide_render = False
