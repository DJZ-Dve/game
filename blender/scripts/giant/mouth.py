"""嘴（第二版）：牙床线往里的一切——牙床、上颚（两个獠牙牙槽）、口底 / 基舌骨垫、嘴角颊膜、喉咙，以及全部的牙。

外形纲领（见 spec.py 开头）：尖牙鱼的牙——少而巨大、长短悬殊、半透明发白；下颌最前一对獠牙闭嘴时插进上颚的牙槽；
嘴里黑紫、湿；格陵兰睡鲨的颌和贴着颌骨的牙龈。没有一圈圈的小牙、没有满嘴刺。

部件（低模，进游戏）：
  MouthLining   嘴里的肉（一张连着的网格，见 mouth_lining.py），M_GiantMouth
  MouthGums     每颗牙根的一圈牙龈（领口），M_GiantMouth，权重跟各自的牙
  TeethUpper    上牙（每颗刚性跟所在脊椎骨），M_GiantTooth
  TeethLower    下牙（全给 Jaw），M_GiantTooth
UV0 = 贴图组 "mouth" 的图集（牙：U 绕牙一圈、V 从牙根到牙尖，再由 atlas_uv 统一缩放排布；肉按区域接缝展开）。
高模（只烘焙用）：同一套形状函数按 ~10 倍密度重建 + 雕刻细节（牙的纵纹、刃棱、生长线、牙结石、崩尖、裂纹；
上颚的褶和乳突、口底和基舌骨垫的粗糙、颊膜的皱、喉咙的纵褶、牙龈的点彩）。
烘焙分两遍：法线在闭嘴静止姿态烘（牙和领口临时挪开，免得射线打到对面的牙）；遮罩在下颌张开 35° 时烘
（嘴里不被对面挡成一片黑，AO 只记局部的沟、牙根周围和深处）。"""
import math
import os
import shutil
import time

import bmesh
import bpy
import numpy as np
from mathutils import Vector as V, Matrix

import lib
from giant import spec, bakeutil
from giant import mouth_shape as ms
from giant import mouth_teeth as mt
from giant import mouth_lining as ml
from giant.mouth_util import MB, fbm, ridged, smoothstep, mark_region_seams, unwrap, vnoise

BAKE_JAW_DEG = 35.0
TOOTH_FLIP = {}      # 低模牙：重算法线以后还要按中心线再翻的块数（应该是 0）


# ---------------------------------------------------------------------------- 獠牙 → 牙槽
def fang_info(teeth):
    out = {}
    for t in teeth:
        if t.name != "L1":
            continue
        k0 = 16
        arc = t.crown[k0:]
        acc = t.crown_acc[k0:]
        rad = []
        for l in acc:
            a = t.radius(l)
            rad.append((a, a * t.aspect))
        out[t.side] = dict(O=t.O, arc=arc, rad=rad, r_open=(0.31, 0.42))
    return out


# ---------------------------------------------------------------------------- 网格清理、法线
def cleanup(ob):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    loose = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose, context='VERTS')
    bm.to_mesh(ob.data)
    bm.free()


def orient(ob, score_fn):
    """先让每个连通块的绕向一致，再按 score_fn(面中心, 面法线) 的面积加权和决定整块要不要翻。"""
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bm.faces.ensure_lookup_table()
    seen = set()
    flipped = ncomp = 0
    for f0 in bm.faces:
        if f0.index in seen:
            continue
        comp = []
        stack = [f0]
        seen.add(f0.index)
        while stack:
            f = stack.pop()
            comp.append(f)
            for e in f.edges:
                for g in e.link_faces:
                    if g.index not in seen:
                        seen.add(g.index)
                        stack.append(g)
        sc = sum(f.calc_area() * score_fn(f.calc_center_median(), f.normal) for f in comp)
        ncomp += 1
        if sc < 0:
            bmesh.ops.reverse_faces(bm, faces=comp)
            flipped += 1
    bm.to_mesh(ob.data)
    bm.free()
    return flipped, ncomp


def _recalc(ob):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bm.to_mesh(ob.data)
    bm.free()


def lining_score(c, n):
    """嘴里的肉：法线朝嘴腔（上颚朝下、口底朝上、喉咙朝管心）。"""
    s = spec.s_of(c.y)
    if s <= spec.JAW_HINGE_S:
        mid = V((0.0, c.y, spec.mouth_z(max(s, 0.0))))
        # 颊膜外层朝外（离中线）
        if abs(c.x) > ms.gum_x(max(s, 0.0)) + 0.06:
            return n.x * math.copysign(1.0, c.x)
        return n.dot((mid - c).normalized())
    return 0.0


def tooth_score_factory(teeth):
    def f(c, n):
        best, bp = 1e9, None
        for t in teeth:
            for p in t.crown[::4]:
                d = (p - c).length
                if d < best:
                    best, bp = d, p
        return n.dot((c - bp))
    return f


def collar_score(c, n):
    return -n.z if c.z > spec.mouth_z(max(spec.s_of(c.y), 0.0)) else n.z


def mesh_report(ob):
    me = ob.data
    bm = bmesh.new()
    bm.from_mesh(me)
    nm = sum(1 for e in bm.edges if len(e.link_faces) > 2)
    bd = sum(1 for e in bm.edges if len(e.link_faces) == 1)
    zero = sum(1 for f in bm.faces if f.calc_area() < 1e-6)
    loose = sum(1 for v in bm.verts if not v.link_faces)
    bm.free()
    me.calc_loop_triangles()
    print(f"  {ob.name}: {len(me.loop_triangles):,} tris, {len(me.vertices):,} verts, "
          f"非流形边 {nm}, 开放边 {bd}, 零面积面 {zero}, 孤立点 {loose}")
    return len(me.loop_triangles)


# ---------------------------------------------------------------------------- 低模
def build_low(coll, teeth, fangs):
    mats_mouth = ["M_GiantMouth"]
    mb = MB()
    lin = ml.Lining(1, fangs)
    lin.build(mb)
    lining = mb.to_object("MouthLining", coll, mats_mouth, regions_attr=True)
    cleanup(lining)
    orient(lining, lining_score)
    mark_region_seams(lining)
    unwrap(lining)
    lining.data.attributes.remove(lining.data.attributes["mregion"])

    mb = MB()
    mt.build_collars(mb, teeth)
    gums = mb.to_object("MouthGums", coll, mats_mouth)
    orient(gums, collar_score)

    objs = [lining, gums]
    for up, nm in ((True, "TeethUpper"), (False, "TeethLower")):
        mb = MB()
        tt = [t for t in teeth if t.upper == up]
        mt.build_teeth(mb, tt)
        ob = mb.to_object(nm, coll, ["M_GiantTooth"])
        fl, nc = orient(ob, tooth_score_factory(tt))
        TOOTH_FLIP[up] = (fl, nc)
        objs.append(ob)
    for o in objs:
        spec.set_body_uv(o)
    return objs


# ---------------------------------------------------------------------------- 高模
def lining_detail(ob):
    """高模肉：沿法线推雕刻细节，写 Curv（凹槽 / 凸棱）。"""
    me = ob.data
    n = len(me.vertices)
    co = np.empty(n * 3, dtype=np.float32)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3).astype(np.float64)
    nor = np.empty(n * 3, dtype=np.float32)
    me.vertex_normals.foreach_get("vector", nor)
    nor = nor.reshape(-1, 3).astype(np.float64)
    reg = np.zeros(n, dtype=np.int32)
    if "vregion" in me.attributes:
        me.attributes["vregion"].data.foreach_get("value", reg)
    y = co[:, 1]
    s = (spec.HALF - y) / spec.LENGTH
    disp = np.zeros(n)
    grv = np.zeros(n)
    rdg = np.zeros(n)
    # 通用：湿黏膜的小起伏 + 乳突
    b1 = fbm(co * 3.0, 4, seed=5)
    disp += b1 * 0.010
    pap = vnoise(co * 22.0, seed=9)
    pap = np.clip(pap * 1.6 - 0.6, 0, 1)
    disp += pap * 0.004
    rdg += pap * 0.3
    # 上颚：纵向的细褶（沿 y 拉长的脊状噪声）+ 横向的波纹
    pal = (reg == ml.REG_PAL) & (co[:, 2] > -1.2) & (s < 0.21)
    q = co * np.array([2.2, 0.35, 2.2])
    w = ridged(q * 2.0, 3, seed=21)
    wr = (w - 0.55) * 0.05
    disp += np.where(pal, wr, 0.0)
    rdg += np.where(pal, np.clip(w - 0.7, 0, 1) * 2.0, 0)
    grv += np.where(pal, np.clip(0.45 - w, 0, 1) * 1.6, 0)
    # 口底 / 基舌骨垫：粗糙的软骨垫（颗粒更粗）、口底的皱
    flo = (reg == ml.REG_FLO)
    g = fbm(co * 9.0, 3, seed=31)
    disp += np.where(flo, g * 0.008, 0.0)
    w2 = ridged(co * np.array([1.6, 0.6, 1.6]) * 2.5, 3, seed=33)
    disp += np.where(flo, (w2 - 0.55) * 0.035, 0.0)
    grv += np.where(flo, np.clip(0.4 - w2, 0, 1) * 1.4, 0)
    # 颊膜：静止时折着，顺着长边的皱
    web = np.isin(reg, [ml.REG_WEBL, ml.REG_WEBR, ml.REG_OUTL, ml.REG_OUTR])
    w3 = ridged(co * np.array([0.6, 1.2, 4.5]) * 2.0, 3, seed=41)
    disp += np.where(web, (w3 - 0.5) * 0.03, 0.0)
    grv += np.where(web, np.clip(0.4 - w3, 0, 1) * 1.8, 0)
    # 喉咙：深的纵褶
    thr = s > spec.JAW_HINGE_S + 0.003
    tt = np.clip((s - spec.JAW_HINGE_S) / 0.1, 0, 1)
    ang = np.arctan2(co[:, 2] + 0.5, co[:, 0])
    w4 = ridged(np.stack([np.cos(ang) * 3, np.sin(ang) * 3, y * 0.4], axis=1), 3, seed=51)
    disp += np.where(thr, (w4 - 0.5) * 0.06 * tt, 0.0)
    grv += np.where(thr, np.clip(0.45 - w4, 0, 1) * 2.0 * tt, 0)
    # 牙槽口：一圈放射状的皱
    pit = np.isin(reg, [ml.REG_PITL, ml.REG_PITR])
    for side in (-1, 1):
        O = spec.fang_socket(side)
        a = np.arctan2(co[:, 1] - O.y, co[:, 0] - O.x)
        rr = np.hypot(co[:, 1] - O.y, co[:, 0] - O.x)
        near = np.exp(-((rr - 0.42) / 0.25) ** 2) * (co[:, 2] > -1.4)
        wav = np.sin(a * 14 + fbm(co * 4, 2, seed=61) * 2)
        disp += near * wav * 0.012 * (reg == ml.REG_PAL)
        grv += near * np.clip(-wav, 0, 1) * 0.8 * (reg == ml.REG_PAL)
    # 牙床：点彩（细小的凹点），沿牙床线的一条带
    gum = np.zeros(n, dtype=bool)
    if "vgum" in me.attributes:
        gv = np.zeros(n, dtype=np.float32)
        me.attributes["vgum"].data.foreach_get("value", gv)
        gum = gv > 0.5
    st = vnoise(co * 40.0, seed=71)
    disp += np.where(gum, -np.clip(st - 0.3, 0, 1) * 0.004, 0)
    grv += np.where(gum, np.clip(st - 0.3, 0, 1) * 1.2, 0)
    co += nor * disp[:, None]
    me.vertices.foreach_set("co", co.astype(np.float32).reshape(-1))
    cv = np.zeros((n, 4), dtype=np.float32)
    cv[:, 0] = np.clip(grv, 0, 1)
    cv[:, 1] = np.clip(rdg, 0, 1)
    cv[:, 3] = 1
    a = me.attributes.new("Curv", 'FLOAT_COLOR', 'POINT')
    a.data.foreach_set("color", cv.reshape(-1))
    ar = np.zeros((n, 4), dtype=np.float32)
    ar[:, 3] = 1
    a = me.attributes.new("Area", 'FLOAT_COLOR', 'POINT')
    a.data.foreach_set("color", ar.reshape(-1))
    me.update()


def build_high(coll, teeth, fangs, res=8):
    t0 = time.time()
    mb = MB()
    lin = ml.Lining(res, fangs)
    lin.build(mb, high=True)
    # 高模不要骨骼权重（只烘焙）；记下每个顶点的区域、Jaw 权重（烘焙时张嘴用）
    nv = mb.nv
    jw = np.zeros(nv, dtype=np.float32)
    for start, count, w in mb.wblocks:
        if isinstance(w, dict):
            jw[start:start + count] = w.get("Jaw", 0.0)
        else:
            jw[start:start + count] = [d.get("Jaw", 0.0) for d in w]
    mb.wblocks = []
    vreg = np.zeros(nv, dtype=np.int32)
    for idx, r, m, uv in mb.faces:
        vreg[idx.reshape(-1)] = np.maximum(vreg[idx.reshape(-1)], r)
    lining = mb.to_object("MouthLining_high", coll, ["M_GiantMouth"])
    me = lining.data
    a = me.attributes.new("vregion", 'INT', 'POINT')
    a.data.foreach_set("value", vreg)
    # 牙床带：离牙床线 0.6 米以内
    a = me.attributes.new("jaww", 'FLOAT', 'POINT')
    a.data.foreach_set("value", jw)
    co = mb.all_verts()
    a = me.attributes.new("vgum", 'FLOAT', 'POINT')
    a.data.foreach_set("value", _gum_band(co, vreg))
    cleanup(lining)
    orient(lining, lining_score)
    lining_detail(lining)
    print(f"  high lining {len(lining.data.vertices):,} verts ({time.time() - t0:.1f}s)")
    mb = MB()
    mt.build_collars(mb, teeth, high=True)
    gums = mb.to_object("MouthGums_high", coll, ["M_GiantMouth"])
    orient(gums, collar_score)
    _set_attr(gums, "jaww", np.array([1.0 if not t.upper else 0.0 for t in teeth]), teeth, mb)
    highs = [lining, gums]
    for up, nm in ((True, "TeethUpper_high"), (False, "TeethLower_high")):
        mb = MB()
        tt = [t for t in teeth if t.upper == up]
        mt.build_teeth(mb, tt, high=True)
        mb.wblocks = []
        ob = mb.to_object(nm, coll, ["M_GiantTooth"])
        # 牙是封闭的，重算法线就是朝外（低模逐块核对过：TOOTH_FLIP 应该全是 0）
        _recalc(ob)
        a = ob.data.attributes.new("jaww", 'FLOAT', 'POINT')
        a.data.foreach_set("value", np.full(len(ob.data.vertices), 0.0 if up else 1.0, dtype=np.float32))
        highs.append(ob)
    print(f"  high total {sum(len(o.data.vertices) for o in highs):,} verts ({time.time() - t0:.1f}s)")
    return highs


def _gum_band(co, vreg):
    out = np.zeros(len(co), dtype=np.float32)
    s = (spec.HALF - co[:, 1]) / spec.LENGTH
    for upper, reg in ((True, ml.REG_PAL), (False, ml.REG_FLO)):
        sel = (vreg == reg) & (s < spec.JAW_HINGE_S + 0.002)
        idx = np.nonzero(sel)[0]
        for i in idx:
            si = min(max(s[i], spec.JAW_FRONT_S if not upper else 0.0), spec.JAW_HINGE_S)
            gx = ms.gum_x(si, upper)
            if gx - abs(co[i, 0]) < 0.6:
                out[i] = 1.0
    return out


def _set_attr(ob, name, per_tooth, teeth, mb):
    """领口：下牙的领口 Jaw 权重 1。按顶点块（每颗牙一块）写。"""
    n = len(ob.data.vertices)
    vals = np.zeros(n, dtype=np.float32)
    # 领口按牙的顺序一块一块加的，块大小相同的话可以直接切；这里按位置判断离哪颗牙近
    co = np.empty(n * 3, dtype=np.float32)
    ob.data.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    bases = np.array([t.B[:] for t in teeth])
    d = ((co[:, None, :] - bases[None, :, :]) ** 2).sum(-1)
    near = d.argmin(1)
    vals = np.array([0.0 if teeth[k].upper else 1.0 for k in near], dtype=np.float32)
    a = ob.data.attributes.new(name, 'FLOAT', 'POINT')
    a.data.foreach_set("value", vals)


# ---------------------------------------------------------------------------- 烘焙时张嘴
def _rot_jaw(co, w, deg):
    h = spec.jaw_hinge()
    a = math.radians(-deg)
    ca, sa = math.cos(a), math.sin(a)
    dy = co[:, 1] - h.y
    dz = co[:, 2] - h.z
    ry = h.y + dy * ca - dz * sa
    rz = h.z + dy * sa + dz * ca
    out = co.copy()
    out[:, 1] = co[:, 1] * (1 - w) + ry * w
    out[:, 2] = co[:, 2] * (1 - w) + rz * w
    return out


def _jaw_w(o):
    me = o.data
    n = len(me.vertices)
    w = np.zeros(n)
    if "jaww" in me.attributes:
        tmp = np.zeros(n, dtype=np.float32)
        me.attributes["jaww"].data.foreach_get("value", tmp)
        return tmp.astype(np.float64)
    vg = o.vertex_groups.get("Jaw")
    if vg:
        gi = vg.index
        for v in me.vertices:
            for g in v.groups:
                if g.group == gi:
                    w[v.index] = g.weight
    return w


def pose_bake(objs, deg=0.0, explode=False):
    """烘焙姿态：deg > 0 按 Jaw 权重（低模读顶点组、高模读 jaww 属性）把下颌张开；
    explode 时嘴里的肉不动，牙和牙龈领口整个挪开（上牙往上、下牙往下 15 米）——牙尖离对面的肉只有十来厘米，
    不挪开的话烘焙射线会打到对面的牙上。返回还原用的原坐标。"""
    saved = []
    for o in objs:
        me = o.data
        n = len(me.vertices)
        co = np.empty(n * 3, dtype=np.float32)
        me.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3).astype(np.float64)
        w = _jaw_w(o)
        saved.append((o, co.copy()))
        new = co
        if deg:
            new = _rot_jaw(co, w, deg)
        if explode and (o.name.startswith("Teeth") or o.name.startswith("MouthGums")):
            new = new.copy()
            new[:, 2] += np.where(w > 0.5, -15.0, 15.0)
        me.vertices.foreach_set("co", new.astype(np.float32).reshape(-1))
        me.update()
    return saved


def restore(saved):
    for o, co in saved:
        o.data.vertices.foreach_set("co", co.astype(np.float32).reshape(-1))
        o.data.update()


# ---------------------------------------------------------------------------- 入口
def build(coll, bake=False):
    t0 = time.time()
    teeth = mt.layout()
    probs = mt.check(teeth, verbose=False)
    for p in probs:
        print("  [mouth] 自查:", p)
    fangs = fang_info(teeth)
    lows = build_low(coll, teeth, fangs)
    meters = bakeutil.atlas_uv(lows, "mouth")
    if meters > spec.TEXSETS["mouth"]["meters"] * 1.02:
        print(f"  [mouth] 图集密度 {meters:.1f} m/UV 超过 spec 的 {spec.TEXSETS['mouth']['meters']} m")
    print("  teeth orient flips:", TOOTH_FLIP)
    tot = 0
    for o in lows:
        tot += mesh_report(o)
    print(f"  mouth low total {tot:,} tris ({time.time() - t0:.1f}s)")
    if bake:
        tb = time.time()
        highs = build_high(bpy.context.scene.collection, teeth, fangs)
        scn = bpy.context.scene
        world = scn.world or bpy.data.worlds.new("World")
        scn.world = world
        old_dist = world.light_settings.distance
        world.light_settings.distance = 1.2
        nrm = os.path.join(bakeutil.OUT_DIR, "mouth_normal.png")
        keep = nrm + ".keep.png"
        try:
            # 第一遍：法线。闭嘴静止姿态（没有张嘴的拉伸、折叠），牙挪开
            saved = pose_bake(lows + highs, 0.0, explode=True)
            bakeutil.bake_set("mouth", lows, highs, extrusion=0.05, max_ray=0.14, ao_samples=4)
            restore(saved)
            shutil.copyfile(nrm, keep)
            # 第二遍：遮罩（AO、凹槽、凸棱、区域）。下颌张开 35°：嘴里不被对面挡成一片黑，牙对牙龈的遮挡还在
            saved = pose_bake(lows + highs, BAKE_JAW_DEG, explode=False)
            bakeutil.bake_set("mouth", lows, highs, extrusion=0.05, max_ray=0.14, ao_samples=64)
            restore(saved)
            shutil.move(keep, nrm)
        finally:
            world.light_settings.distance = old_dist
            for h in highs:
                me = h.data
                bpy.data.objects.remove(h)
                bpy.data.meshes.remove(me)
        print(f"  mouth bake {time.time() - tb:.1f}s")
    return lows
