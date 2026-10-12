"""肉：把 flesh_geo 的参数网格变成 Blender 网格（低模、高模共用），低模再加接缝、UV0、骨骼权重。"""
import math

import bpy
import numpy as np

from watcher import spec
from watcher import flesh_geo as fg

# 低模密度（高模在这基础上 ×k）
NB = 160                       # 身体 + 眼窝绕眼轴分几份（能被 8 整除：UV 接缝在 45° 的倍数上）
LID = (28, 9, 6, 15, 2, 3)     # 眼睑：ψ 分段、内表面、睑缘卷边、外表面、根部过渡带、根部圆头
SIPH_NA = 36


# ---------------------------------------------------------------------------- 通用
def grid_quads(idx, wrap):
    a, b = idx[:-1], idx[1:]
    if wrap:
        a1, b1 = np.roll(a, -1, axis=1), np.roll(b, -1, axis=1)
    else:
        a, b, a1, b1 = a[:, :-1], b[:, :-1], a[:, 1:], b[:, 1:]
    return np.stack([a, a1, b1, b], -1).reshape(-1, 4)


def fan(c, ring, rev=False):
    r1 = np.roll(ring, -1)
    t = np.stack([np.full(len(ring), c), ring, r1], -1) if not rev else np.stack([np.full(len(ring), c), r1, ring], -1)
    return t


def face_normals(co, f):
    p = co[f]
    if f.shape[1] == 4:
        n = np.cross(p[:, 2] - p[:, 0], p[:, 3] - p[:, 1])
    else:
        n = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    return n


def orient(co, faces, ref_faces, ref_dir):
    """按一组参考面（ref_faces 下标，属于 faces[0]）的期望朝向，整体翻转。"""
    n = face_normals(co, faces[0][ref_faces])
    if (np.einsum("ij,ij->i", n, ref_dir) < 0).mean() > 0.5:
        faces = [f[:, ::-1].copy() for f in faces]
    return faces


def make_mesh(name, co, faces, coll=None, mat=None):
    faces = [f for f in faces if len(f)]
    loops = np.concatenate([f.ravel() for f in faces]).astype(np.int32)
    sizes = np.concatenate([np.full(len(f), f.shape[1]) for f in faces])
    starts = np.concatenate([[0], np.cumsum(sizes)[:-1]]).astype(np.int32)
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(co))
    me.vertices.foreach_set("co", co.astype(np.float32).ravel())
    me.loops.add(len(loops))
    me.loops.foreach_set("vertex_index", loops)
    me.polygons.add(len(sizes))
    me.polygons.foreach_set("loop_start", starts)
    me.update(calc_edges=True)
    ob = bpy.data.objects.new(name, me)
    (coll or bpy.context.scene.collection).objects.link(ob)
    if mat is not None:
        me.materials.append(mat)
    me.shade_smooth()
    return ob


def vertex_normals(ob):
    me = ob.data
    n = np.empty(len(me.vertices) * 3, dtype=np.float32)
    me.vertex_normals.foreach_get("vector", n)
    return n.reshape(-1, 3).astype(np.float64)


def set_co(ob, co):
    ob.data.vertices.foreach_set("co", co.astype(np.float32).ravel())
    ob.data.update()


def edges(ob):
    e = np.empty(len(ob.data.edges) * 2, dtype=np.int32)
    ob.data.edges.foreach_get("vertices", e)
    return e.reshape(-1, 2)


def mark_seams(ob, mask):
    ob.data.edges.foreach_set("use_seam", mask.astype(bool))


def unwrap(ob, method='ANGLE_BASED'):
    me = ob.data
    if spec.UV_MAIN not in me.uv_layers:
        me.uv_layers.new(name=spec.UV_MAIN)
    bpy.ops.object.select_all(action='DESELECT')
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.unwrap(method=method, margin=0.002)
    bpy.ops.object.mode_set(mode='OBJECT')
    ob.select_set(False)


def set_weights(ob, groups):
    """groups: {骨名: 每个顶点的权重数组}（0 的不加）。"""
    for name, w in groups.items():
        vg = ob.vertex_groups.get(name) or ob.vertex_groups.new(name=name)
        w = np.asarray(w, dtype=np.float64)
        for val in np.unique(np.round(w[w > 1e-4], 3)):
            idx = np.nonzero(np.abs(np.round(w, 3) - val) < 1e-6)[0]
            vg.add(idx.tolist(), float(val), 'REPLACE')


# ---------------------------------------------------------------------------- 身体 + 眼窝
def body_mesh(name, k, coll=None, mat=None, low_disp=True):
    """返回 (物体, 参数 dict)：dict 里有每个顶点的 ring、bj、reg、seg、loc、θ、β 和低频高度。"""
    G = fg.rev_grid(NB * k if k > 1 else NB, k)
    P = G["P"]
    R, nb = P.shape[:2]
    co = np.concatenate([P.reshape(-1, 3), G["pole"][None, :]], 0)
    idx = np.arange(R * nb).reshape(R, nb)
    pole = R * nb
    quads = grid_quads(idx, True)
    tris = fan(pole, idx[0], rev=True)   # 极点在第 0 圈之前
    # 身体那段朝外（从身体中心往外）
    ref = np.arange(min(500, nb * 3))
    faces = orient(co, [quads, tris], ref, co[quads[ref, 0]])
    ob = make_mesh(name, co, faces, coll, mat)
    ring = np.concatenate([np.repeat(np.arange(R), nb), [-1]])
    bj = np.concatenate([np.tile(np.arange(nb), R), [-1]])
    reg = np.concatenate([np.repeat(G["reg"], nb), [fg.REG_BODY]])
    seg = np.concatenate([np.repeat(G["seg"], nb), [-1]])
    loc = np.concatenate([np.repeat(G["loc"], nb), [0]])
    be = np.concatenate([np.tile(G["be"], R), [0.0]])
    h = np.zeros(len(co))
    if low_disp:
        h = np.concatenate([fg.rev_low(G).ravel(), [fg.rev_low_pole(G["pole"])]])
        n = vertex_normals(ob)
        co = co + n * h[:, None]
        set_co(ob, co)
    info = dict(ring=ring, bj=bj, reg=reg, seg=seg, loc=loc, be=be, hlow=h, R=R, nb=nb, G=G)
    return ob, info


def body_low(coll, mat):
    ob, I = body_mesh("FleshBody", 1, coll, mat)
    G = I["G"]
    nb = I["nb"]
    e = edges(ob)
    ring, bj = I["ring"], I["bj"]
    a, b = e[:, 0], e[:, 1]
    mer = set(range(nb // 8, nb, nb // 4))                 # β = 45°、135°、225°、315°
    is_mer = np.isin(bj, list(mer))
    seam = (bj[a] == bj[b]) & is_mer[a] & is_mer[b]
    seam |= ((ring[a] == -1) & is_mer[b]) | ((ring[b] == -1) & is_mer[a])
    rings = {G["ring_back"], G["ring_join"], G["ring_fundus"]}
    is_r = np.isin(ring, list(rings))
    seam |= (ring[a] == ring[b]) & is_r[a] & is_r[b]
    mark_seams(ob, seam)
    unwrap(ob)
    # 权重：全给 Body；结膜前缘带一点 Eye（转眼时这圈湿肉跟着动一点）
    q = np.array([v.co for v in ob.data.vertices]) - fg.E
    th = np.arccos(np.clip(q[:, 1] / np.linalg.norm(q, axis=1), -1, 1))
    w_eye = np.where(I["reg"] == 4, 0.3 * fg.smoothstep(math.radians(90), math.radians(78), th), 0.0)
    set_weights(ob, {"Body": 1.0 - w_eye, "Eye": w_eye})
    return ob, I


# ---------------------------------------------------------------------------- 眼睑
def lid_mesh(name, lower, k, coll=None, mat=None, low_disp=True):
    L = fg.lid_grid(lower, *[c * k for c in LID])
    P = L["P"]
    I, Lp = P.shape[:2]
    co = P.reshape(-1, 3)
    c0 = P[0].mean(0)
    c1 = P[-1].mean(0)
    co = np.concatenate([co, c0[None], c1[None]], 0)
    idx = np.arange(I * Lp).reshape(I, Lp)
    quads = _lid_quads(idx)
    t0 = fan(I * Lp, idx[0], rev=True)        # 端盖在第 0 条截面之前
    t1 = fan(I * Lp + 1, idx[-1])
    # 外表面朝外（离开眼心）
    outer = np.nonzero(L["part"][:-1, :-1].ravel() == 2)[0][:300]
    faces = orient(co, [quads, t0, t1], outer, co[quads[outer, 0]] - fg.E)
    ob = make_mesh(name, co, faces, coll, mat)
    flat = lambda a, end: np.concatenate([a.ravel(), [end, end]])
    info = dict(psi=flat(L["psi"], 0.0), phi=flat(L["phi"], 0.0), rho=flat(L["rho"], 0.0),
                part=flat(L["part"], 4), gam=flat(L["gam"], 0.0), dm=flat(L["dm"], 0.0),
                w=flat(L["w"], 0.0), li=np.concatenate([np.repeat(np.arange(I), Lp), [-1, -1]]),
                ll=np.concatenate([np.tile(np.arange(Lp), I), [-1, -1]]), I=I, Lp=Lp, L=L)
    info["hlow"] = np.concatenate([L["hlow"].ravel(), [0.0, 0.0]])
    if low_disp:
        n = vertex_normals(ob)
        co = co + n * info["hlow"][:, None]
        set_co(ob, co)
    return ob, info


def _lid_quads(idx):
    """眼睑：沿 ψ 方向相邻两条截面环之间连四边形（环是闭合的）。"""
    a, b = idx[:-1], idx[1:]
    a1, b1 = np.roll(a, -1, axis=1), np.roll(b, -1, axis=1)
    return np.stack([a, a1, b1, b], -1).reshape(-1, 4)


def lid_low(coll, mat, lower):
    nm = "LidLo" if lower else "LidUp"
    ob, I = lid_mesh("Flesh" + nm, lower, 1, coll, mat)
    e = edges(ob)
    a, b = e[:, 0], e[:, 1]
    li, ll = I["li"], I["ll"]
    end = (li == 0) | (li == I["I"] - 1)
    seam = (ll[a] == 0) & (ll[b] == 0)                       # 根部内侧一条缝
    seam |= (li[a] == li[b]) & end[a] & end[b]               # 两头的端盖
    mark_seams(ob, seam)
    unwrap(ob)
    w = I["w"]
    set_weights(ob, {nm: w, "Body": 1.0 - w})
    return ob, I


# ---------------------------------------------------------------------------- 虹吸口
def siphon_mesh(name, k, coll=None, mat=None, k_pap=1):
    S = fg.siphon_grid(SIPH_NA * k, k)
    P = S["P"]
    R, na = P.shape[:2]
    co = [P.reshape(-1, 3), S["bottom"][None]]
    idx = np.arange(R * na).reshape(R, na)
    quads = [grid_quads(idx, True)]
    tris = [fan(R * na, idx[-1])]          # 喉底在最后一圈之后
    base = R * na + 1
    pap_id = [np.full(R * na + 1, -1)]
    pap_t = [np.zeros(R * na + 1)]
    pap_side = [np.zeros(R * na + 1, dtype=np.int32)]
    for pi, (rings, tip) in enumerate(fg.papillae(5 * k_pap, k_pap)):
        nl, ks = rings.shape[:2]
        co.append(rings.reshape(-1, 3))
        co.append(tip[None])
        id2 = base + np.arange(nl * ks).reshape(nl, ks)
        quads.append(grid_quads(id2, True))
        tris.append(fan(base + nl * ks, id2[-1]))
        pap_id.append(np.full(nl * ks + 1, pi))
        pap_t.append(np.concatenate([np.repeat(np.arange(nl) / nl, ks), [1.0]]))
        pap_side.append(np.concatenate([np.tile(np.arange(ks), nl), [-1]]))
        base += nl * ks + 1
    co = np.concatenate(co, 0)
    s0, sx, sy, sn = S["frame"]
    # 外圈朝外（沿虹吸口轴线往外）
    ref = np.arange(min(200, na * 4))
    q = quads[0]
    nr = face_normals(co, q[ref])
    if (nr @ sn < 0).mean() > 0.5:
        quads[0] = q[:, ::-1].copy()
        tris[0] = tris[0][:, ::-1].copy()
    # 小触须朝外：法线离开轴心线
    for j in range(1, len(quads)):
        qq = quads[j]
        nr = face_normals(co, qq)
        cc = co[qq].mean(1)
        # 环心：同一条环上 ks 个四边形的面心平均
        ks = 5 * k_pap
        rc = np.repeat(cc.reshape(-1, ks, 3).mean(1), ks, axis=0)
        if (np.einsum("ij,ij->i", nr, cc - rc) < 0).mean() > 0.5:
            quads[j] = qq[:, ::-1].copy()
            tris[j] = tris[j][:, ::-1].copy()
    ob = make_mesh(name, co, [np.concatenate(quads), np.concatenate(tris)], coll, mat)
    ring = np.concatenate([np.repeat(np.arange(R), na), [R]] + [np.full(len(p), -1) for p in pap_id[1:]])
    aj = np.concatenate([np.tile(np.arange(na), R), [-1]] + [np.full(len(p), -1) for p in pap_id[1:]])
    info = dict(ring=ring, aj=aj, pap=np.concatenate(pap_id), pap_t=np.concatenate(pap_t),
                pap_side=np.concatenate(pap_side), S=S, R=R, na=na,
                reg=np.concatenate([np.repeat(S["reg"], na), [2]] + [np.full(len(p), 3) for p in pap_id[1:]]),
                r=np.concatenate([np.repeat(S["r"], na), [0.0]] + [np.zeros(len(p)) for p in pap_id[1:]]),
                h=np.concatenate([np.repeat(S["h"], na), [-0.8]] + [np.zeros(len(p)) for p in pap_id[1:]]))
    return ob, info


def siphon_low(coll, mat):
    ob, I = siphon_mesh("FleshSiphon", 1, coll, mat)
    e = edges(ob)
    a, b = e[:, 0], e[:, 1]
    aj, pap, side = I["aj"], I["pap"], I["pap_side"]
    seam = (aj[a] == 0) & (aj[b] == 0)
    seam |= ((I["ring"][a] == I["R"]) & (aj[b] == 0)) | ((I["ring"][b] == I["R"]) & (aj[a] == 0))
    seam |= (pap[a] >= 0) & (pap[a] == pap[b]) & (side[a] == 0) & (side[b] == 0)
    seam |= (pap[a] >= 0) & (pap[a] == pap[b]) & (((side[a] == -1) & (side[b] == 0)) | ((side[b] == -1) & (side[a] == 0)))
    mark_seams(ob, seam)
    unwrap(ob)
    set_weights(ob, {"Body": np.ones(len(ob.data.vertices))})
    return ob, I
