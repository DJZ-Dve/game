"""皮的高模（只用来烘焙）：低模细分四级（约 1.5 厘米一个点），再按位置一层层加细节，烘进 skin_normal / skin_mask。

细节（克制：大面平滑，重点只有少数几处）：
  - 盾鳞：整张皮细细的一层颗粒（顺着身体往后拉长的小鳞片，背上明显、腹部弱，唇里、缝里、疤上没有）；
  - 皱：鳃裂周围顺着鳃裂的细褶、嘴角往后的唇沟和几道放射纹、眼睛周围一圈细纹、铰链后面喉咙下的横褶；
  - 劳伦氏壶腹孔：吻前、吻下成片的小深孔（一簇一簇，近看才看得见）；
  - 侧线：两侧各一条细细的纵沟，沟里隔一段一个小孔；
  - 旧疤（Area 0.5）：三处很长的愈合隆起（其中一处是两道平行的刮痕），疤上是横的细纹、没有鳞；
  - 达摩鲨咬坑（Area 0.5）：五个直径 0.4～0.7 米的圆形浅坑，愈合的边缘微微隆起；
  - 新伤（Area 1 生肉）：左侧一道撕开的口子，里面坑坑洼洼的肉，边缘肿起、参差。
点色 "Curv"：R = 凹槽，G = 凸棱（按细节高度和底形的曲率算）；"Area"：R = 区域图。"""
import math
import time

import bpy
import numpy as np

from giant import spec, bakeutil
from giant import skin_np as snp
from giant import skin_low

LEVELS = 4
CREASE = 0.55
D = math.radians


# ---------------------------------------------------------------------------- 底形
def _base(low, m, levels):
    """低模（不带 UV、权重）→ 细分 levels 级后的网格物体，带几个区域遮罩属性（细分时跟着插值）。"""
    me0 = low.data
    n = len(me0.vertices)
    co = np.empty(n * 3, dtype=np.float32)
    me0.vertices.foreach_get("co", co)
    me = bpy.data.meshes.new("SkinHighBase")
    me.vertices.add(n)
    me.vertices.foreach_set("co", co)
    nl = len(me0.loops)
    lv = np.empty(nl, dtype=np.int32)
    me0.loops.foreach_get("vertex_index", lv)
    ls = np.empty(len(me0.polygons), dtype=np.int32)
    me0.polygons.foreach_get("loop_start", ls)
    lt = np.empty(len(me0.polygons), dtype=np.int32)
    me0.polygons.foreach_get("loop_total", lt)
    me.loops.add(nl)
    me.loops.foreach_set("vertex_index", lv)
    me.polygons.add(len(me0.polygons))
    me.polygons.foreach_set("loop_start", ls)
    me.update(calc_edges=True)
    # 唇缘、鳃裂缘、眼睑缘半硬（细分时不至于圆得太多，和低模差太远烘出来一片斜）
    ne = len(me.edges)
    ev = np.empty(ne * 2, dtype=np.int32)
    me.edges.foreach_get("vertices", ev)
    ev = ev.reshape(-1, 2)
    cr = np.zeros(ne, dtype=np.float32)
    keys = {(min(a, b), max(a, b)) for a, b in m.crease}
    for i, (a, b) in enumerate(ev):
        if (min(a, b), max(a, b)) in keys:
            cr[i] = CREASE
    ca = me.attributes.new("crease_edge", 'FLOAT', 'EDGE')
    ca.data.foreach_set("value", cr)
    masks = {k: np.zeros(n, dtype=np.float32) for k in ("m_out", "m_lip", "m_pocket", "m_sock")}
    for i, mt in enumerate(m.meta):
        part = mt.get("part")
        eye = mt.get("eye")
        if part in ("uroll", "lroll"):
            masks["m_lip"][i] = 1.0
        elif part == "pocket":
            masks["m_pocket"][i] = 1.0
        elif eye is not None and eye[1] <= 2:
            masks["m_sock"][i] = 1.0 if eye[1] < 2 else 0.5
            masks["m_out"][i] = 0.0 if eye[1] < 2 else 0.5
        else:
            masks["m_out"][i] = 1.0
    for k, v in masks.items():
        a = me.attributes.new(k, 'FLOAT', 'POINT')
        a.data.foreach_set("value", v)
    ob = bpy.data.objects.new("SkinHighBase", me)
    bpy.context.scene.collection.objects.link(ob)
    mod = ob.modifiers.new("sub", 'SUBSURF')
    mod.levels = levels
    mod.render_levels = levels
    mod.quality = 3
    mod.boundary_smooth = 'PRESERVE_CORNERS'
    dg = bpy.context.evaluated_depsgraph_get()
    hm = bpy.data.meshes.new_from_object(ob.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
    bpy.data.objects.remove(ob)
    bpy.data.meshes.remove(me)
    high = bpy.data.objects.new("SkinHigh", hm)
    bpy.context.scene.collection.objects.link(high)
    return high


def _arrays(ob):
    me = ob.data
    n = len(me.vertices)
    co = np.empty(n * 3, dtype=np.float32)
    me.vertices.foreach_get("co", co)
    nor = np.empty(n * 3, dtype=np.float32)
    me.vertex_normals.foreach_get("vector", nor)
    e = np.empty(len(me.edges) * 2, dtype=np.int32)
    me.edges.foreach_get("vertices", e)
    att = {}
    for k in ("m_out", "m_lip", "m_pocket", "m_sock"):
        v = np.empty(n, dtype=np.float32)
        me.attributes[k].data.foreach_get("value", v)
        att[k] = np.clip(v.astype(np.float64), 0, 1)
    return co.reshape(-1, 3).astype(np.float64), nor.reshape(-1, 3).astype(np.float64), e.reshape(-1, 2), att


class Nb:
    """顶点邻接平均（细节模糊、曲率用）。"""

    def __init__(self, e, n):
        self.a, self.b = e[:, 0], e[:, 1]
        self.n = n
        self.deg = np.maximum(np.bincount(self.a, minlength=n) + np.bincount(self.b, minlength=n), 1)

    def avg(self, x):
        return (np.bincount(self.a, weights=x[self.b], minlength=self.n) +
                np.bincount(self.b, weights=x[self.a], minlength=self.n)) / self.deg

    def blur(self, x, it):
        for _ in range(it):
            x = 0.5 * x + 0.5 * self.avg(x)
        return x


def _theta_metric(s, th):
    eps = 1e-3
    return np.linalg.norm(snp.surface(s, th + eps) - snp.surface(s, th - eps), axis=1) / (2 * eps)


def _curve_pts(ctrl, step=0.015, side=1):
    """(s, θ) 控制点 → 表面上每 1.5 厘米一个点的折线（Catmull-Rom 过控制点）。返回点、累计长度。"""
    ctrl = np.array(ctrl, dtype=np.float64)
    dense = []
    for i in range(len(ctrl) - 1):
        p0 = ctrl[max(i - 1, 0)]
        p1, p2 = ctrl[i], ctrl[i + 1]
        p3 = ctrl[min(i + 2, len(ctrl) - 1)]
        for t in np.linspace(0, 1, 40, endpoint=False):
            t2, t3 = t * t, t * t * t
            dense.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 +
                                (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    dense.append(ctrl[-1])
    dense = np.array(dense)
    P = snp.surface(dense[:, 0], side * dense[:, 1])
    seg = np.linalg.norm(np.diff(P, axis=0), axis=1)
    acc = np.concatenate([[0], np.cumsum(seg)])
    n = max(int(acc[-1] / step), 2)
    tt = np.linspace(0, acc[-1], n)
    out = np.stack([np.interp(tt, acc, P[:, k]) for k in range(3)], axis=1)
    return out, tt


def _near_curve(co, idx, pts, reach):
    """候选点（idx）到折线的距离和最近点的弧长下标；只算包围盒附近的点。"""
    lo, hi = pts.min(0) - reach, pts.max(0) + reach
    sel = idx[np.all((co[idx] >= lo) & (co[idx] <= hi), axis=1)]
    if len(sel) == 0:
        return sel, np.zeros(0), np.zeros(0, dtype=np.int64)
    d, j = snp.nearest(co[sel], pts)
    keep = d < reach
    return sel[keep], d[keep], j[keep]


# ---------------------------------------------------------------------------- 细节
SCARS = [
    # (侧, [(s, θ°)...], 半宽米)：很长的旧疤，愈合后隆起
    (1, [(0.318, 52), (0.36, 70), (0.41, 92), (0.455, 112), (0.478, 124)], 0.15),
    (-1, [(0.205, 14), (0.232, 26), (0.262, 38), (0.29, 47)], 0.11),
    (1, [(0.575, 100), (0.61, 92), (0.645, 80), (0.672, 70)], 0.08),
    (1, [(0.584, 108), (0.619, 100), (0.653, 88), (0.678, 79)], 0.06),   # 和上一道平行的刮痕
]
BITES = [
    # (侧, s, θ°, 半径米, 长短轴比, 转角°)
    (1, 0.395, 132, 0.33, 1.15, 20),
    (-1, 0.515, 104, 0.25, 1.1, -35),
    (1, 0.625, 138, 0.21, 1.2, 60),
    (-1, 0.455, 62, 0.36, 1.08, 10),
    (1, 0.735, 112, 0.22, 1.15, -15),
]
WOUND = (-1, [(0.405, 72), (0.418, 79), (0.432, 87), (0.444, 93)], 0.13)   # 新伤：撕开的口子


def details(co, nor, att, nb):
    t0 = time.time()
    n = len(co)
    h_feat = np.zeros(n)      # 大一点的细节（疤、坑、皱、孔）
    h_ll = np.zeros(n)        # 侧线（疤和伤会把它截断）
    h_grain = np.zeros(n)     # 盾鳞颗粒
    area = np.zeros(n)
    no_grain = np.zeros(n)    # 0～1：这里不长鳞（疤、伤、唇里）
    out = att["m_out"]
    s, th = snp.body_coords(co)
    ath = np.abs(th)
    side = np.where(co[:, 0] >= 0, 1.0, -1.0)
    outer = np.nonzero(out > 0.01)[0]

    # ---- 侧线
    for sd in (-1, 1):
        sel = outer[(side[outer] == sd) & (s[outer] > 0.09) & (s[outer] < 0.97)]
        ss = s[sel]
        tll = D(70) + D(18) * snp.smoothstep(0.1, 0.45, ss) + D(1.2) * np.sin(ss * 47.0 + 1.3)
        mt = _theta_metric(ss, th[sel])
        dist = np.abs(ath[sel] - tll) * mt
        env = snp.smoothstep(0.09, 0.13, ss) * (1 - snp.smoothstep(0.92, 0.97, ss))
        g = np.exp(-(dist / 0.018) ** 2) * env
        # 沟里隔 0.16 米一个小孔
        along = co[sel, 1] / 0.16
        pore = np.exp(-((along - np.round(along)) * 0.16 / 0.012) ** 2) * np.exp(-(dist / 0.014) ** 2) * env
        h_ll[sel] -= 0.007 * g + 0.008 * pore
    print(f"  lateral line {time.time() - t0:.1f}s")

    # ---- 鳃区细褶（顺着鳃裂斜 12°）
    sel = outer[(s[outer] > 0.205) & (s[outer] < 0.33) & (ath[outer] > D(60)) & (ath[outer] < D(140))]
    q = co[sel]
    w = q[:, 1] + math.tan(D(12)) * q[:, 2]
    ph = w / 0.115 + 0.8 * snp.fbm(q / 0.7, 2, seed=11)
    groove = (1 - np.abs(np.sin(math.pi * ph))) ** 6
    env = snp.smoothstep(0.205, 0.225, s[sel]) * (1 - snp.smoothstep(0.29, 0.33, s[sel])) * \
        snp.smoothstep(D(60), D(80), ath[sel]) * (1 - snp.smoothstep(D(122), D(140), ath[sel]))
    env *= 0.55 + 0.45 * snp.fbm(q / 0.9, 2, seed=12)
    h_feat[sel] -= 0.006 * groove * np.clip(env, 0, 1)
    # 喉咙下（铰链后面）的横褶：张嘴时这里被撑开
    sel = outer[(s[outer] > 0.19) & (s[outer] < 0.31) & (ath[outer] > D(120))]
    q = co[sel]
    ph = q[:, 1] / 0.24 + 0.9 * snp.fbm(q / 1.1, 2, seed=13) + 0.15 * q[:, 0]
    groove = (1 - np.abs(np.sin(math.pi * ph))) ** 5
    env = snp.smoothstep(0.19, 0.21, s[sel]) * (1 - snp.smoothstep(0.27, 0.31, s[sel])) * \
        snp.smoothstep(D(120), D(145), ath[sel])
    h_feat[sel] -= 0.009 * groove * env
    print(f"  folds {time.time() - t0:.1f}s")

    # ---- 嘴角：往后的唇沟 + 几道放射纹
    hz = spec.jaw_hinge()
    for sd in (-1, 1):
        cc = spec.lip_point(spec.JAW_HINGE_S, sd, True)
        sel = outer[(side[outer] == sd) & (np.linalg.norm(co[outer] - np.array(cc), axis=1) < 1.8)]
        q = co[sel]
        dy = cc.y - q[:, 1]          # 往后为正
        dz = q[:, 2] - cc.z
        r = np.sqrt(dy * dy + dz * dz)
        # 唇沟：从嘴角往后 1.3 米，略往下
        fur = np.exp(-((dz + 0.03 * dy) / 0.035) ** 2) * snp.smoothstep(-0.1, 0.1, dy) * (1 - snp.smoothstep(0.7, 1.3, dy))
        h_feat[sel] -= 0.016 * fur
        # 放射纹：嘴角周围 0.25～1 米
        phi = np.arctan2(dz, dy + 0.3)
        rad = (1 - np.abs(np.sin(phi * 9.0 + 0.6 * snp.fbm(q / 0.5, 2, seed=14)))) ** 8
        env = snp.smoothstep(0.2, 0.35, r) * (1 - snp.smoothstep(0.6, 1.1, r))
        h_feat[sel] -= 0.004 * rad * env
    print(f"  mouth corner {time.time() - t0:.1f}s")

    # ---- 眼睛周围一圈细纹
    for sd in (-1, 1):
        ec = np.array(spec.eye_center(sd))
        d = np.linalg.norm(co - ec, axis=1)
        sel = np.nonzero((d < 1.3) & (out > 0.3))[0]
        r = d[sel] + 0.03 * snp.fbm(co[sel] / 0.25, 2, seed=15)
        ring = (1 - np.abs(np.sin(math.pi * r / 0.075))) ** 6
        env = snp.smoothstep(0.62, 0.72, d[sel]) * (1 - snp.smoothstep(0.9, 1.25, d[sel]))
        h_feat[sel] -= 0.003 * ring * env
        no_grain[sel] = np.maximum(no_grain[sel], 0.5 * (1 - snp.smoothstep(0.55, 0.75, d[sel])))
    print(f"  eye {time.time() - t0:.1f}s")

    # ---- 旧疤
    for k, (sd, ctrl, hw) in enumerate(SCARS):
        pts, acc = _curve_pts([(a, D(b)) for a, b in ctrl], side=sd)
        sel, d, j = _near_curve(co, outer, pts, hw * 2.2)
        tl = acc[j] / acc[-1]
        q = co[sel]
        width = hw * (0.75 + 0.35 * snp.fbm(np.stack([acc[j] / 0.6, np.full(len(j), k * 7.0), np.zeros(len(j))], 1),
                                                2, seed=20 + k)) * np.sin(math.pi * np.clip(tl, 0, 1)) ** 0.35
        width = np.maximum(width, 1e-3)
        x = d / width
        core = np.clip(1 - x * x, 0, 1) ** 1.5
        # 疤上横着的细纹（愈合的皮被拉过）
        stri = np.sin(2 * math.pi * acc[j] / 0.07 + 5.0 * snp.fbm(q / 0.25, 2, seed=30 + k))
        stri *= np.clip(0.3 + snp.fbm(q / 0.4, 2, seed=35 + k), 0, 1)
        h_feat[sel] += 0.018 * core + 0.002 * stri * core
        # 疤两边略往下陷一点（拉紧的皮）
        h_feat[sel] -= 0.004 * np.exp(-((x - 1.25) / 0.3) ** 2)
        a = 0.5 * snp.smoothstep(1.15, 0.75, x)
        area[sel] = np.maximum(area[sel], a)
        no_grain[sel] = np.maximum(no_grain[sel], snp.smoothstep(1.2, 0.8, x))
    print(f"  scars {time.time() - t0:.1f}s")

    # ---- 达摩鲨咬坑
    for k, (sd, sb, tb, r0, asp, rot) in enumerate(BITES):
        c = np.array(spec.surface(sb, sd * D(tb)))
        nrm = np.array(spec.normal(sb, sd * D(tb)))
        d3 = np.linalg.norm(co - c, axis=1)
        sel = np.nonzero((d3 < r0 * 1.8) & (out > 0.5))[0]
        v = co[sel] - c
        v = v - np.outer(v @ nrm, nrm)
        e1 = np.cross(nrm, [0, 0, 1.0])
        if np.linalg.norm(e1) < 1e-6:
            e1 = np.array([1.0, 0, 0])
        e1 /= np.linalg.norm(e1)
        e2 = np.cross(nrm, e1)
        ca, sa = math.cos(D(rot)), math.sin(D(rot))
        u1, u2 = v @ (e1 * ca + e2 * sa), v @ (-e1 * sa + e2 * ca)
        ang = np.arctan2(u2, u1)
        rr = np.sqrt((u1 / asp) ** 2 + u2 ** 2) / (r0 * (1 + 0.06 * np.sin(ang * 3 + k) + 0.04 * np.sin(ang * 7 + 2 * k)))
        bowl = -0.05 * (1 - np.clip(rr, 0, 1) ** 2) ** 1.3 * (0.8 + 0.2 * r0 / 0.3)
        rim = 0.007 * np.exp(-((rr - 1.0) / 0.12) ** 2)
        # 坑底愈合的皮：浅浅的不平
        bump = 0.004 * snp.fbm(co[sel] / 0.08, 2, seed=40 + k) * (rr < 1)
        h_feat[sel] += bowl + rim + bump
        a = 0.5 * snp.smoothstep(1.12, 0.9, rr)
        area[sel] = np.maximum(area[sel], a)
        no_grain[sel] = np.maximum(no_grain[sel], snp.smoothstep(1.1, 0.85, rr))
    print(f"  bites {time.time() - t0:.1f}s")

    # ---- 新伤
    sd, ctrl, hw = WOUND
    pts, acc = _curve_pts([(a, D(b)) for a, b in ctrl], side=sd)
    sel, d, j = _near_curve(co, outer, pts, hw * 3.0)
    tl = acc[j] / acc[-1]
    q = co[sel]
    width = hw * np.sin(math.pi * np.clip(tl, 0, 1)) ** 0.6 * \
        (0.8 + 0.4 * snp.fbm(np.stack([acc[j] / 0.45, np.zeros(len(j)), np.ones(len(j))], 1), 2, seed=50))
    width = np.maximum(width, 1e-3)
    x = d / width
    inside = snp.smoothstep(1.05, 0.85, x)
    flesh = -0.075 * np.clip(1 - x * x, 0, 1) ** 0.7 + 0.018 * snp.fbm(q / 0.05, 3, seed=51)
    swell = 0.012 * np.exp(-((x - 1.2) / 0.35) ** 2)
    h_feat[sel] += flesh * inside + swell * (1 - inside)
    area[sel] = np.maximum(area[sel], inside)
    no_grain[sel] = np.maximum(no_grain[sel], snp.smoothstep(1.6, 1.0, x))
    print(f"  wound {time.time() - t0:.1f}s")

    # ---- 劳伦氏壶腹孔：吻前、吻下，一簇一簇
    reg = outer[(s[outer] < 0.11) & (out[outer] > 0.9)]
    rs, rth = s[reg], ath[reg]
    mt_s = np.array([skin_low.mt_of(x) for x in np.linspace(0, 0.12, 61)])
    mt_r = np.interp(rs, np.linspace(0, 0.12, 61), mt_s)
    under = snp.smoothstep(D(55), D(80), rth) * (rth < mt_r + D(4)) * (1 - snp.smoothstep(0.07, 0.11, rs))
    front = (1 - snp.smoothstep(0.012, 0.03, rs)) * (rth < mt_r + D(4))
    jawfront = (co[reg, 1] > spec.y_of(0.025)) * (rth > mt_r)   # 下巴前面也有零星几个
    dens = np.clip(np.maximum(under, front) + 0.35 * jawfront, 0, 1)
    dens *= np.clip(0.5 + 0.9 * snp.fbm(co[reg] / 0.6, 2, seed=60), 0, 1)
    # 离唇缘太近的不要
    up, lo = skin_low.lip_lines(80)
    dl, _ = snp.nearest(co[reg], np.array([tuple(p) for p in up + lo]))
    dens *= snp.smoothstep(0.12, 0.3, dl)
    for sd in (-1, 1):
        de = np.linalg.norm(co[reg] - np.array(spec.eye_center(sd)), axis=1)
        dens *= snp.smoothstep(0.9, 1.5, de)
    dens = np.clip(dens - 0.15, 0, 1) ** 1.3
    rng = spec.rng_for("skin_pores")
    order = rng.permutation(len(reg))
    cell = 0.1
    grid = {}
    pores = []
    for o in order:
        if rng.random() > dens[o] * 0.5:
            continue
        p = co[reg[o]]
        key = (int(p[0] // cell), int(p[1] // cell), int(p[2] // cell))
        ok = True
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for qq in grid.get((key[0] + dx, key[1] + dy, key[2] + dz), ()):
                        if ((p - qq) ** 2).sum() < 0.11 ** 2:
                            ok = False
                            break
                    if not ok:
                        break
                if not ok:
                    break
            if not ok:
                break
        if ok:
            grid.setdefault(key, []).append(p)
            pores.append(p)
        if len(pores) >= 3000:
            break
    pores = np.array(pores)
    if len(pores):
        dp, jp = snp.nearest(co[reg], pores)
        pr = 0.013 + 0.009 * snp._hash3(jp, jp * 3, jp * 7, 61)
        x = dp / pr
        h_feat[reg] += -0.014 * np.clip(1 - x * x, 0, 1) ** 1.5 + 0.0015 * np.exp(-((x - 1.15) / 0.2) ** 2)
    print(f"  pores {len(pores)} {time.time() - t0:.1f}s")

    # ---- 盾鳞颗粒：顺着身体往后拉长的小鳞，背上明显、腹部弱
    gsel = np.nonzero(out > 0.01)[0]
    q = co[gsel] / np.array([0.024, 0.042, 0.024])
    f1, f2, rid = snp.voronoi(q, seed=70)
    scale = snp.smoothstep(0.0, 0.32, f2 - f1)          # 鳞和鳞之间一道细缝
    # 每片鳞后半截略高（尖朝后）
    tip = np.clip(0.5 + 0.5 * snp.perlin(co[gsel] / np.array([0.05, 0.02, 0.05]), seed=71), 0, 1)
    gr = 0.0024 * scale + 0.0006 * tip + 0.0004 * (rid - 0.5)
    belly = 1 - 0.55 * snp.smoothstep(D(100), D(160), ath[gsel])
    fine = 0.6 + 0.4 * snp.fbm(co[gsel] / 2.5, 2, seed=72)   # 大片区域里颗粒感有强有弱
    h_grain[gsel] = gr * belly * fine * out[gsel] * (1 - no_grain[gsel])
    print(f"  grain {time.time() - t0:.1f}s")

    h_feat += h_ll * (1 - no_grain)
    h_feat *= out
    return h_feat, h_grain, area


def curv(co, nor, h_feat, h_grain, nb):
    """凹槽 / 凸棱：细节高度减去它模糊后的样子（几厘米尺度），加上底形的折（唇缘、鳃裂缘、眼睑）。"""
    hb = nb.blur(h_feat, 6)
    cav = np.clip((hb - h_feat) / 0.006, 0, 1)
    rid = np.clip((h_feat - hb) / 0.005, 0, 1)
    gb = nb.blur(h_grain, 2)
    cav = np.maximum(cav, 0.35 * np.clip((gb - h_grain) / 0.0012, 0, 1))
    # 底形曲率：邻点平均和自己的差在法线上的分量（米），模糊后按尺度映射
    lap = np.zeros(len(co))
    for k in range(3):
        lap += (nb.avg(co[:, k]) - co[:, k]) * nor[:, k]
    lap = nb.blur(lap, 4)
    cav = np.maximum(cav, np.clip((lap - 0.0004) / 0.0015, 0, 1))
    rid = np.maximum(rid, np.clip((-lap - 0.0004) / 0.0015, 0, 1))
    return cav, rid


def make_high(low, m, ctx, levels=LEVELS):
    t0 = time.time()
    high = _base(low, m, levels)
    co, nor, e, att = _arrays(high)
    print(f"skin high base: {len(co):,} verts ({time.time() - t0:.1f}s)")
    nb = Nb(e, len(co))
    h_feat, h_grain, area = details(co, nor, att, nb)
    newco = co + nor * (h_feat + h_grain)[:, None]
    me = high.data
    me.vertices.foreach_set("co", newco.astype(np.float32).ravel())
    me.update()
    cav, rid = curv(newco, nor, h_feat, h_grain, nb)
    n = len(co)
    a = me.attributes.new("Curv", 'FLOAT_COLOR', 'POINT')
    a.data.foreach_set("color", np.stack([cav, rid, np.zeros(n), np.ones(n)], 1).astype(np.float32).ravel())
    a = me.attributes.new("Area", 'FLOAT_COLOR', 'POINT')
    a.data.foreach_set("color", np.stack([area, area, area, np.ones(n)], 1).astype(np.float32).ravel())
    for k in ("m_out", "m_lip", "m_pocket", "m_sock"):
        me.attributes.remove(me.attributes[k])
    print(f"skin high: {len(me.polygons):,} faces, {time.time() - t0:.1f}s")
    return high


def bake(low, m, ctx):
    t0 = time.time()
    high = make_high(low, m, ctx)
    scn = bpy.context.scene
    if scn.world is None:
        scn.world = bpy.data.worlds.new("World")
    old = scn.world.light_settings.distance
    # AO 只看局部（缝、孔、唇、鳃、眼窝），身体尺度的遮挡交给引擎
    scn.world.light_settings.distance = 1.2
    try:
        bakeutil.bake_set("skin", [low], [high], extrusion=0.06, max_ray=0.3)
    finally:
        scn.world.light_settings.distance = old
        me = high.data
        bpy.data.objects.remove(high)
        bpy.data.meshes.remove(me)
    print(f"skin bake total {time.time() - t0:.1f}s")
