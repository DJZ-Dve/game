"""鳍（第二版）：格陵兰睡鲨的肉质鳍——一对胸鳍、一对腹鳍、两片小背鳍、歪尾（上叶长、下叶也不小）。

解剖：鲨鱼的鳍不是硬骨鱼那种鳍条加薄膜，是厚实的肉质鳍：根部厚、和身体长成一体（根部一圈圆角 + 一道肉褶，
外沿钻进皮里，盖住和皮的接缝），往鳍缘渐薄，截面是翼型（前缘圆厚、后缘薄）。
  - 胸鳍：宽、圆钝的桨形，略往后掠，后内角圆；有一点弯度（背面鼓）。
  - 腹鳍：小三角形，往后掠得厉害，后内角略尖。
  - 背鳍：两片都小、低、圆顶，后缘略内凹；第二背鳍更小。
  - 尾鳍：歪尾，上叶长（脊柱伸进上叶，靠上缘一侧厚），末端有个小缺刻（subterminal notch），尾叉凹口，
    下叶也不小、前缘厚；根部包住尾柄末端（皮的尾端盖在尾鳍里面）。
老伤：几处后缘上愈合的旧撕口（缺一小块、边缘不齐，不破成布条），一两道疤（高模）。

低模约 9k 三角面（spec.TRI_BUDGET["fins"]），UV0 = 贴图组 "fins" 的图集（各鳍一个岛：管状鳍沿后缘切开、
尾鳍左右两面各一个岛），UV1 = BodyST。
高模（只烘焙）：同一套参数曲面高分辨率重新生成，加盾鳞颗粒、皮下隐约的辐射状软骨、根部的屈曲皱、后缘的老旧磨损、
撕口边的疤组织、疤；点色 Curv（R 凹槽、G 凸棱/发白）、Area（R：鳍膜薄处 → 1）自己算（见 fins_detail.py）。
权重：胸鳍 Pec?_0 → Pec?_1 沿长度渐变，根部（圆角、肉褶）混所在脊椎骨；腹鳍 Pel?，根部同样混脊椎；
背鳍按位置给脊椎骨；尾鳍按位置给脊椎骨（总装合并后用 spec.tail_fin_weights 再分给 TailFin_0/1）。
"""
import math
import time

import bpy
import numpy as np

from giant import spec, bakeutil
from giant import fins_geo as G

MAT = "M_GiantFin"
SHARP = 70.0      # 低模上夹角超过这么多度的边标硬边（鳍缘）


# ---------------------------------------------------------------------------- 各鳍的形状
def _pectoral(side):
    """胸鳍：根长 3.2，伸出 ≈ 6.3（沿展向），梢往后掠约 2.4 米。"""
    f = spec.FINS["pectoral"]
    O = np.array(spec.fin_root("pectoral", side))
    C = np.array(spec.frame(f["s"], side * f["theta"]).col[1][:3])
    d = np.array((side * 0.75, -0.45, -0.5))
    pts = [(1.60, 0.0), (1.56, 0.55), (1.38, 1.5), (1.00, 2.65), (0.42, 3.85), (-0.30, 4.9), (-1.05, 5.7),
           (-1.75, 6.15), (-2.35, 6.3),
           (-2.85, 6.15), (-3.12, 5.75), (-3.25, 4.9), (-3.28, 3.8), (-3.22, 2.7), (-3.02, 1.85),
           (-2.70, 1.2), (-2.25, 0.6), (-1.60, 0.0)]
    # 后缘的旧撕口：左右不一样
    notches = [(4.35, 0.42, 0.30, 0.3), (2.55, 0.30, 0.16, -0.4)] if side > 0 else [(3.55, 0.50, 0.26, -0.2)]
    pf = G.Planform(pts, notches)
    thk = lambda h: 0.035 + 0.50 * (1.0 - np.clip(h / pf.H, 0, 1)) ** 1.5
    return G.TubeFin("Pec" + ("R" if side > 0 else "L"), O, C, d, pf, thk, R=0.28, flat_h=1.6, camber=0.035,
                     skirt=0.2)


def _pelvic(side):
    f = spec.FINS["pelvic"]
    O = np.array(spec.fin_root("pelvic", side))
    C = np.array(spec.frame(f["s"], side * f["theta"]).col[1][:3])
    d = np.array((side * 0.5, -0.7, -0.5))
    pts = [(1.00, 0.0), (0.97, 0.35), (0.72, 1.0), (0.18, 1.7), (-0.55, 2.25), (-1.25, 2.5), (-1.75, 2.42),
           (-2.12, 2.1), (-2.38, 1.5), (-2.55, 0.85), (-2.62, 0.42), (-2.15, 0.2), (-1.0, 0.0)]
    notches = [(1.35, 0.30, 0.17, 0.2)] if side > 0 else []
    pf = G.Planform(pts, notches)
    thk = lambda h: 0.03 + 0.30 * (1.0 - np.clip(h / pf.H, 0, 1)) ** 1.4
    return G.TubeFin("Pel" + ("R" if side > 0 else "L"), O, C, d, pf, thk, R=0.2, flat_h=1.0, camber=0.02,
                     skirt=0.16)


def _dorsal(name):
    f = spec.FINS[name]
    O = np.array(spec.fin_root(name))
    C = np.array(spec.frame(f["s"], 0.0).col[1][:3])
    sc_c = f["root"] / 2.6
    sc_h = f["span"] / 1.7
    base = [(1.30, 0.0), (1.22, 0.28), (0.90, 0.78), (0.40, 1.28), (-0.15, 1.6), (-0.60, 1.7), (-0.95, 1.6),
            (-1.15, 1.28), (-1.30, 0.80), (-1.52, 0.33), (-1.72, 0.12), (-1.30, 0.0)]
    if name == "dorsal2":
        # 第二背鳍：更低、更圆、略往后靠
        base = [(1.30, 0.0), (1.20, 0.3), (0.85, 0.82), (0.30, 1.32), (-0.25, 1.62), (-0.68, 1.68),
                (-1.02, 1.55), (-1.22, 1.2), (-1.38, 0.72), (-1.58, 0.3), (-1.76, 0.12), (-1.30, 0.0)]
    pts = [(c * sc_c, h * sc_h) for c, h in base]
    notches = [(0.95 * sc_h, 0.22 * sc_h, 0.10 * sc_c, 0.3)] if name == "dorsal1" else []
    pf = G.Planform(pts, notches)
    t0 = 0.30 * sc_c
    thk = lambda h: 0.025 + t0 * (1.0 - np.clip(h / pf.H, 0, 1)) ** 1.3
    return G.TubeFin(name, O, C, (0.0, 0.0, 1.0), pf, thk, R=0.2 * sc_c, flat_h=0.8 * sc_h, skirt=0.15)


# 低模分辨率：(截面点数, 展向排数)
LOW_RES = {"Pec": (28, 15), "Pel": (22, 11), "dorsal1": (22, 9), "dorsal2": (20, 8)}


def _tube_low(fin, coll):
    key = "Pec" if fin.name.startswith("Pec") else "Pel" if fin.name.startswith("Pel") else fin.name
    M, n = LOW_RES[key]
    rows = fin.root_rows() + fin.span_rows(n, fin.notch_rows(5))
    g = fin.build(rows, M)
    verts, faces, used = G.tube_topology(g)
    uv = G.tube_uv(g)
    ob = G.make_mesh(fin.name, coll, verts, faces, bpy.data.materials[MAT], uv=uv, sharp=SHARP)
    _orient(ob)
    ob["hgt"] = 0  # 占位，权重直接用下面的数组
    return ob, g, used


def _orient(ob):
    """闭合网格整体朝外（有符号体积 > 0），不对就全部翻面。"""
    me = ob.data
    n = len(me.vertices)
    co = np.empty(n * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    me.calc_loop_triangles()
    tri = np.empty(len(me.loop_triangles) * 3, dtype=np.int64)
    me.loop_triangles.foreach_get("vertices", tri)
    tri = tri.reshape(-1, 3)
    a, b, c = co[tri[:, 0]], co[tri[:, 1]], co[tri[:, 2]]
    vol = np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0
    if vol < 0:
        me.flip_normals()
    return abs(vol)


# ---------------------------------------------------------------------------- 尾鳍
Y0 = spec.y_of(spec.FINS["caudal"]["s"])     # b = Y0 - y：离尾鳍起点往后的距离


def _caudal_outline():
    """矢状面轮廓 (b, z, lead)：lead = 1 前缘（圆厚）/ 0 后缘（薄）。顺时针，从尾柄里面的前上角开始。"""
    cp = [
        (-0.90, 0.95, 1), (-0.45, 1.36, 1), (0.05, 1.52, 1), (0.8, 1.73, 1), (2.0, 2.13, 1), (3.5, 2.72, 1),
        (5.0, 3.38, 1), (6.4, 4.03, 1), (7.45, 4.52, 1), (8.02, 4.72, 1),            # 上叶前缘 → 梢
        (8.18, 4.50, 0.6), (7.95, 4.20, 0), (7.52, 3.97, 0), (7.10, 3.84, 0),       # 末端小叶
        (6.86, 3.74, 0), (6.80, 3.52, 0),                                           # 末端缺刻
        (6.30, 3.05, 0), (5.50, 2.36, 0), (4.62, 1.66, 0), (3.82, 1.06, 0),         # 上叶后缘
        (3.32, 0.62, 0), (3.16, 0.36, 0), (3.30, 0.08, 0),                          # 尾叉
        (3.70, -0.52, 0), (4.20, -1.38, 0), (4.62, -2.28, 0), (4.98, -3.08, 0.3),   # 下叶后缘
        (5.08, -3.56, 0.8), (4.88, -3.82, 1), (4.48, -3.72, 1),                      # 下叶梢
        (3.60, -3.06, 1), (2.60, -2.30, 1), (1.60, -1.62, 1), (0.80, -1.04, 1), (0.10, -0.62, 1),
        (-0.50, -0.36, 1), (-0.90, -0.10, 1),                                        # 下叶前缘 → 尾柄里
    ]
    a = np.array(cp, dtype=np.float64)
    return a


# 旧撕口（尾鳍）：沿轮廓参数（0～1）的位置、半宽（米）、深度（米）
CAUDAL_NOTCHES = [(0.405, 0.5, 0.2), (0.468, 0.42, 0.13), (0.63, 0.45, 0.18)]


def _caudal_poly(spacing, grow=0.0):
    cp = _caudal_outline()
    d = G.catmull_np(cp[:, :2], samples=16, closed=True)
    lead = np.interp(np.linspace(0, len(cp), len(d), endpoint=False), np.arange(len(cp) + 1),
                     np.append(cp[:, 2], cp[0, 2]))
    # 撕口：沿轮廓法线往里缩
    L = np.linalg.norm(np.diff(np.vstack([d, d[:1]]), axis=0), axis=1)
    cum = np.concatenate([[0.0], np.cumsum(L)[:-1]])
    tot = L.sum()
    t = cum / tot
    nrm = np.roll(d, -1, axis=0) - np.roll(d, 1, axis=0)
    nrm = np.stack([nrm[:, 1], -nrm[:, 0]], axis=1)
    nrm /= np.linalg.norm(nrm, axis=1)[:, None]
    area = lambda q: abs(np.sum(q[:, 0] * np.roll(q[:, 1], -1) - np.roll(q[:, 0], -1) * q[:, 1]))
    if area(d + nrm * 0.01) < area(d):
        nrm = -nrm                                    # 保证朝外
    for t0, hw, depth in CAUDAL_NOTCHES:
        u = (t - t0) * tot / hw
        d = d - nrm * (depth * G.notch_shape(u, 0.15))[:, None]
    if grow:
        d = d + nrm * grow
    return d, lead, tot


def _body_halfwidth(b, z):
    """尾柄（和尾尖之后一小段圆帽）的半宽：矢状面 (b, z) 处身体左右的厚度的一半；在身体外面为负（离开多远）。"""
    y = Y0 - b
    s = (spec.HALF - y) / spec.LENGTH
    hw, ht, hb, zc, e = G.section_v(np.minimum(s, 1.0))
    # 尾尖之后：皮的尾端可能是个小圆帽，按 0.35 米长的椭球帽估
    k = np.sqrt(np.clip(1.0 - ((np.maximum(s, 1.0) - 1.0) * spec.LENGTH / 0.35) ** 2, 0.0, 1.0))
    hw, ht, hb = hw * k + 1e-4, ht * k + 1e-4, hb * k + 1e-4
    dz = z - zc
    h = np.where(dz >= 0, ht, hb)
    v = np.abs(dz) / h
    inside = np.clip(1.0 - v**e, 0.0, 1.0) ** (1.0 / e) * hw
    return np.where(v < 1.0, inside, -(v - 1.0) * h - 0.02)


def _smax(a, b, k):
    h = np.clip(0.5 + 0.5 * (a - b) / k, 0.0, 1.0)
    return b + (a - b) * h + k * h * (1.0 - h)


# 疤（矢状面 (b, z) 折线，宽度米）：上叶中段一道斜的旧咬痕
CAUDAL_SCARS = [([(3.9, 2.55), (4.5, 2.35), (5.1, 2.05), (5.5, 1.95)], 0.05)]
HUB = np.array((1.5, 0.45))     # 尾鳍最厚的地方（尾柄末端），越往外越薄
SEAM_B = 1.55                   # 尾鳍的皮从这里（尾尖往前约 0.55 米）盖过尾柄的皮


def _nearest(p, q, chunk=4000):
    """p 到点云 q 的最近距离（q 是很密的轮廓采样，当折线用）。"""
    out = np.empty(len(p))
    for s in range(0, len(p), chunk):
        d = np.linalg.norm(p[s:s + chunk, None, :] - q[None, :, :], axis=-1)
        out[s:s + chunk] = d.min(axis=1)
    return out


def caudal_thickness(p, poly, lead_arr):
    """矢状面上一点的半厚度（米）。每片叶子的横截面是翼型：前缘（上叶上缘、下叶下缘）圆厚，后缘薄；
    厚度随离尾柄的距离变薄；尾柄末端和身体光滑取大（尾鳍的皮从 SEAM_B 往后盖住尾柄的皮）。"""
    dense = G.resample(poly, 0.02)
    _, par_d = G.polyline_dist(dense, poly)
    lead_d = np.interp(par_d, np.linspace(0, 1, len(lead_arr), endpoint=False), lead_arr)
    dl = _nearest(p, dense[lead_d >= 0.5])
    dt = _nearest(p, dense[lead_d < 0.5])
    d, par = G.polyline_dist(p, poly)
    chord = dl + dt + 1e-6
    x = dl / chord
    r = np.linalg.norm(p - HUB, axis=1)
    tmax = 0.075 + 0.6 * np.exp(-r / 1.9)
    full = -_smax(-0.16 * chord, -tmax, 0.04)        # 光滑取小
    tf = 0.5 * full * G.naca(x)
    # 脊柱：尾柄末端往后接着伸进上叶（靠上缘），尾柄末端那一截和尾柄一样粗，往梢渐细
    ax = np.array([(0.6, 0.40), (2.1, 0.50), (3.0, 0.95), (3.9, 1.6)])
    da, pa = G.polyline_dist(p, ax, closed=False)
    L = np.linalg.norm(np.diff(ax, axis=0), axis=1)
    cum = np.concatenate([[0.0], np.cumsum(L)]) / L.sum()
    hh = np.interp(pa, cum, [0.40, 0.33, 0.15, 0.0])
    rr = np.interp(pa, cum, [0.9, 0.8, 0.7, 0.6])
    u = np.clip(da / rr, 0.0, 1.0)
    core = hh * (1.0 - u * u) ** 2 * np.clip(d / 0.25, 0.0, 1.0) ** 0.5
    tf = np.sqrt(tf * tf + core * core)
    b, z = p[:, 0], p[:, 1]
    xb = _body_halfwidth(b, z)
    delta = -0.07 + 0.1 * G.smoothstep(SEAM_B - 0.12, SEAM_B + 0.12, b)
    tt = _smax(tf, xb + delta, 0.12)
    # 边界上严格为 0（左右两面在鳍缘合成一条边；尾柄里的那段边在皮下）
    tt = np.where(d < 1e-6, 0.0, np.maximum(tt, 0.0))
    lead = np.interp(par, np.linspace(0, 1, len(lead_arr), endpoint=False), lead_arr)
    t_eff = np.maximum(tt, 0.5 * full * G.naca(np.maximum(x, 0.3)))
    return tt, dict(d_edge=d, lead=lead, tf=tf, xb=xb, par=par, x=x, chord=chord, T_eff=t_eff)


def _seam_pts(spacing):
    """尾柄上皮的接缝附近按竖列加点（接缝才是一条齐的线）。"""
    pts = []
    for b in np.arange(SEAM_B - 0.3, SEAM_B + 0.31, spacing * 0.45):
        for z in np.arange(-0.6, 1.8, spacing * 0.55):
            pts.append((b, z))
    return np.array(pts)


def caudal_sheet(spacing, coll, name, mat, with_uv=True, seam=True, grow=0.0):
    poly, lead, tot = _caudal_poly(spacing, grow)
    pts, tris, nb = G.sheet_mesh2d(poly, spacing, _seam_pts(spacing) if seam else None)
    T, info = caudal_thickness(pts, poly, lead)
    n = len(pts)
    ni = n - nb
    # 顶点：右面（+x）全部；左面（-x）只要内部点（边界共用）
    idx_l = np.concatenate([np.arange(nb), n + np.arange(ni)])
    y = Y0 - pts[:, 0]
    vr = np.stack([T, y, pts[:, 1]], axis=1)
    vl = np.stack([-T[nb:], y[nb:], pts[nb:, 1]], axis=1)
    verts = np.vstack([vr, vl])
    fr = tris.copy()
    fl = idx_l[tris][:, ::-1]
    faces = np.vstack([fr, fl])
    uv = None
    if with_uv:
        # 右面：u = -b（从侧面看往后是 -u），左面镜像；单位米
        uvr = np.stack([-pts[tris.ravel(), 0], pts[tris.ravel(), 1]], axis=1)
        tl = tris[:, ::-1].ravel()
        uvl = np.stack([pts[tl, 0], pts[tl, 1]], axis=1)
        uv = np.vstack([uvr, uvl])
    ob = G.make_mesh(name, coll, verts, faces, mat, uv=uv, sharp=SHARP if with_uv else None)
    _orient(ob)
    side = np.concatenate([np.where(np.arange(n) < nb, 0.0, 1.0), -np.ones(ni)])
    pts2 = np.vstack([pts, pts[nb:]])
    info2 = {k: np.concatenate([v, v[nb:]]) for k, v in info.items()}
    info2["T"] = np.concatenate([T, T[nb:]])
    return ob, dict(p2=pts2, side=side, **info2)


# ---------------------------------------------------------------------------- 权重
def _add(groups, ob, name, idx, w):
    g = groups.get(name)
    if g is None:
        g = groups[name] = ob.vertex_groups.get(name) or ob.vertex_groups.new(name=name)
    for i, wi in zip(idx, w):
        if wi > 1e-4:
            g.add([int(i)], float(wi), 'ADD')


def _weights_paired(ob, fin, hgt, bones, span):
    """bones: [根骨, 梢骨] 或 [骨]；沿骨轴渐变，根部（圆角、肉褶）混脊椎骨。"""
    me = ob.data
    n = len(me.vertices)
    co = np.empty(n * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    groups = {}
    sp = 1.0 - G.smoothstep(-0.05, 0.9, hgt)        # 混脊椎的比例
    sp = 0.88 * sp
    if len(bones) == 2:
        r = fin.O
        d = np.array((fin.dir_bone))
        t = np.clip(((co - r) @ d) / span, 0.0, 1.0)
        w1 = G.smoothstep(0.28, 0.72, t)
        _add(groups, ob, bones[0], range(n), (1 - w1) * (1 - sp))
        _add(groups, ob, bones[1], range(n), w1 * (1 - sp))
    else:
        _add(groups, ob, bones[0], range(n), 1 - sp)
    ss = (spec.HALF - co[:, 1]) / spec.LENGTH
    for i in range(n):
        if sp[i] > 1e-4:
            for name, w in spec.spine_weights(ss[i]):
                _add(groups, ob, name, [i], [w * sp[i]])


# ---------------------------------------------------------------------------- 总入口
def _fins():
    out = []
    for side in (-1, 1):
        p = _pectoral(side)
        tag = "R" if side > 0 else "L"
        p.dir_bone = np.array((side * 0.75, -0.45, -0.5)) / np.linalg.norm((0.75, 0.45, 0.5))
        p.bones = ["Pec%s_0" % tag, "Pec%s_1" % tag]
        p.bspan = spec.FINS["pectoral"]["span"]
        # 疤（平面轮廓坐标 (c, h)）：左胸鳍一道长的斜疤，右胸鳍根部附近一道短的
        p.scars = ([([(0.9, 1.4), (0.2, 2.2), (-0.6, 2.8), (-1.5, 3.25)], 0.055)] if side < 0 else
                   [([(-0.6, 1.0), (-1.2, 1.35), (-1.6, 1.45)], 0.045)])
        out.append(p)
        q = _pelvic(side)
        q.bones = ["Pel%s" % tag]
        q.bspan = spec.FINS["pelvic"]["span"]
        out.append(q)
    for nm in ("dorsal1", "dorsal2"):
        d = _dorsal(nm)
        d.bones = None
        d.scars = [([(0.55, 0.6), (0.1, 0.75), (-0.3, 0.8)], 0.04)] if nm == "dorsal1" else []
        out.append(d)
    return out


def build(coll, bake=False):
    t0 = time.time()
    mat = bpy.data.materials[MAT]
    lows = []
    tubes = []
    for fin in _fins():
        ob, g, used = _tube_low(fin, coll)
        hgt = g["hgt"].ravel()[used]
        if fin.bones:
            _weights_paired(ob, fin, hgt, fin.bones, fin.bspan)
        else:
            spec.assign_spine(ob)
        spec.set_body_uv(ob)
        lows.append(ob)
        tubes.append(fin)
    cau, _ = caudal_sheet(0.26, coll, "Caudal", mat)
    spec.assign_spine(cau)
    spec.set_body_uv(cau)
    lows.append(cau)
    for o in lows:
        if "hgt" in o.keys():
            del o["hgt"]
    meters = bakeutil.atlas_uv(lows, "fins")
    print(f"fins low: {sum(len(o.data.polygons) for o in lows)} faces, atlas {meters:.2f} m, {time.time() - t0:.1f}s")
    if bake:
        from giant import fins_detail
        fins_detail.bake(lows, tubes, coll)
    return lows
