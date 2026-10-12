"""眼（第二版）：两只浑浊的小眼球 + 每只眼上咬着一只寄生桡足类（Ommatokoita elongata，寄生虫见 eyes_parasite.py）。

眼球：沿 spec.normal 的轴旋转出来的球冠——露出的角膜半径 spec.EYE_RADIUS、比体表鼓出 EYE_BULGE，
  角膜边缘往下接一圈「裙边」（先顺着球面再折下去，埋进眼窝），皮上的眼窝洞开在半径 0.40～0.44 都盖得住，
  眼窝往里凹 0.15 米以内都不露缝。
  高模（只烘焙）：角膜上被啃出来的划痕（细沟 + 两边略鼓的唇）、不规则的白色瘢痕（略隆起、表面粗）、
  锚咬住的中央坑和周围一圈肿起的白翳、边缘一圈发灰的薄膜（瞬膜感：内缘不规则卷边、同心细皱），
  角膜整体还有一层轻微的水肿起伏。
贴图组 "eyes"：mask.A（Area）眼球 0 / 寄生虫 1；Curv 自己写——R（凹槽）= 划痕沟、锚坑、薄膜卷边下的折缝，
  薄膜整片也给一点（让它发灰）；G（凸棱/发白）= 白色瘢痕、锚周围的白翳。
低模：每只眼 18 段 × 9 圈（306 三角），UV0 按方位等距展开（弧长当半径，一个圆盘岛）。
权重：眼球、寄生虫身体全给 spec.bone_at(EYE_S)；卵带沿 Parasite%s_0..3（见 eyes_parasite.py）。
"""
import math
import time

import bpy
import numpy as np

import lib
from giant import spec, bakeutil
from giant import eyes_util as U
from giant import eyes_parasite

EYE_BULGE = 0.09          # 角膜顶比体表（spec.surface）鼓出多少米
EYE_SEGS = 18             # 低模一圈几段
SKIRT_R = 0.43            # 球面延续到这个半径，再往下折成裙边
SKIRT_END = (0.462, -0.17)  # 裙边底（半径，轴向高度）
HIGH_STEP = 0.0025        # 高模网格间距（米）


def basis(side):
    """眼睛的局部坐标：O（体表上的眼心）、e1、e2（切向，e2 朝头）、ax（朝外的眼轴）。"""
    m = spec.frame(spec.EYE_S, side * spec.EYE_THETA)
    col = lambda k: np.array(m.col[k][:3], dtype=np.float64)
    return col(3), col(0), col(1), col(2)


def _profile():
    """眼球剖面（从角膜顶往外）：稠密表 ρ（沿剖面的弧长）→ (r, z) 和剖面法线 (nr, nz)。"""
    a, h = spec.EYE_RADIUS, EYE_BULGE
    rb = (a * a + h * h) / (2 * h)
    zc = h - rb
    al_end = math.asin(SKIRT_R / rb)
    al = np.linspace(0.0, al_end, 400)
    pts = [np.stack([rb * np.sin(al), zc + rb * np.cos(al)], axis=1)]
    p0 = pts[0][-1]
    t0 = np.array([math.cos(al_end), -math.sin(al_end)])
    p2 = np.array(SKIRT_END)
    p1 = p0 + t0 * 0.05
    t = np.linspace(0, 1, 120)[1:, None]
    pts.append((1 - t) ** 2 * p0 + 2 * (1 - t) * t * p1 + t * t * p2)
    rz = np.concatenate(pts, axis=0)
    seg = np.linalg.norm(np.diff(rz, axis=0), axis=1)
    rho = np.concatenate([[0.0], np.cumsum(seg)])
    d = np.gradient(rz, axis=0)
    d /= np.linalg.norm(d, axis=1)[:, None]
    nrm = np.stack([-d[:, 1], d[:, 0]], axis=1)
    nrm[0] = (0.0, 1.0)
    rho_rim = rb * math.asin(a / rb)
    return rho, rz, nrm, rho_rim


PROF_RHO, PROF_RZ, PROF_N, RHO_RIM = _profile()
RHO_END = float(PROF_RHO[-1])
RHO_SKIRT = float(PROF_RHO[399])


def _eval(rho):
    r = np.interp(rho, PROF_RHO, PROF_RZ[:, 0])
    z = np.interp(rho, PROF_RHO, PROF_RZ[:, 1])
    nr = np.interp(rho, PROF_RHO, PROF_N[:, 0])
    nz = np.interp(rho, PROF_RHO, PROF_N[:, 1])
    return r, z, nr, nz


def apex(side):
    O, e1, e2, ax = basis(side)
    return O + ax * EYE_BULGE


def to_world(side, u, v, h=None):
    """方位等距坐标 (u, v)（米，|uv| = 弧长 ρ）→ 世界坐标和法线；h：沿法线的位移。"""
    O, e1, e2, ax = basis(side)
    rho = np.hypot(u, v)
    phi = np.arctan2(v, u)
    r, z, nr, nz = _eval(rho)
    rad = np.cos(phi)[:, None] * e1[None] + np.sin(phi)[:, None] * e2[None]
    p = O[None] + rad * r[:, None] + ax[None] * z[:, None]
    n = rad * nr[:, None] + ax[None] * nz[:, None]
    n /= np.linalg.norm(n, axis=1)[:, None]
    if h is not None:
        p = p + n * h[:, None]
    return p, n


# ---------------------------------------------------------------------------- 低模
def build_low(side, tag, coll, mat):
    rings = [0.07, 0.14, 0.21, 0.28, 0.335, RHO_RIM, RHO_SKIRT, RHO_SKIRT + 0.055, RHO_END]
    S = EYE_SEGS
    phi = 2 * np.pi * np.arange(S) / S
    verts, uvs2 = [], []
    for rho in rings:
        u, v = rho * np.cos(phi), rho * np.sin(phi)
        p, _ = to_world(side, u, v)
        verts += list(p)
        uvs2 += list(zip(u, v))
    pole, _ = to_world(side, np.zeros(1), np.zeros(1))
    k = len(verts)
    verts.append(pole[0])
    uvs2.append((0.0, 0.0))
    faces = []
    for j in range(S):
        faces.append((k, j, (j + 1) % S))
    for i in range(len(rings) - 1):
        for j in range(S):
            j1 = (j + 1) % S
            faces.append((i * S + j, (i + 1) * S + j, (i + 1) * S + j1, i * S + j1))
    uvs = [[uvs2[i] for i in f] for f in faces]
    ob = U.mesh_object("Eye" + tag, coll, np.array(verts), faces, uvs, mat)
    O, e1, e2, ax = basis(side)
    zc = EYE_BULGE - (spec.EYE_RADIUS ** 2 + EYE_BULGE ** 2) / (2 * EYE_BULGE)
    ctr = O + ax * zc
    U.check_outward(ob, lambda c: lib.V(ctr))
    spec.assign_bone(ob, spec.bone_at(spec.EYE_S))
    return ob


# ---------------------------------------------------------------------------- 高模
def _scratches(rng, n, u, v, rho_sigma, wmin, wmax, dmin, dmax, lmin, lmax):
    """一批划痕：返回 (沟深 ≥0, 唇高 ≥0)。沟取各条最深的（交叉处不叠加成坑），唇叠加。"""
    groove = np.zeros_like(u)
    lip = np.zeros_like(u)
    for _ in range(n):
        r0 = min(abs(rng.normal(0.0, rho_sigma)), RHO_RIM - 0.04)
        f0 = rng.uniform(0, 2 * np.pi)
        c = np.array([r0 * math.cos(f0), r0 * math.sin(f0)])
        if rng.random() < 0.6:   # 绕着锚啃出来的弧
            ang = f0 + math.pi / 2 + rng.normal(0, 0.5)
            kcurv = (1.0 / max(r0, 0.05)) * rng.choice((-1, 1)) * rng.uniform(0.5, 1.0)
        else:
            ang = rng.uniform(0, 2 * np.pi)
            kcurv = rng.normal(0, 5.0)
        L = rng.uniform(lmin, lmax)
        w = rng.uniform(wmin, wmax)
        dep = rng.uniform(dmin, dmax)
        dvec = np.array([math.cos(ang), math.sin(ang)])
        pvec = np.array([-dvec[1], dvec[0]])
        ts = np.linspace(-0.5, 0.5, 11)
        pl = c[None] + dvec[None] * (L * ts)[:, None] + pvec[None] * (0.5 * kcurv * (L * ts) ** 2)[:, None]
        lo, hi = pl.min(0) - 3 * w, pl.max(0) + 3 * w
        m = (u > lo[0]) & (u < hi[0]) & (v > lo[1]) & (v < hi[1])
        if not m.any():
            continue
        q = np.stack([u[m], v[m]], axis=1)
        best = np.full(len(q), 1e9)
        bt = np.zeros(len(q))
        for s in range(len(pl) - 1):
            a, b = pl[s], pl[s + 1]
            ab = b - a
            t = np.clip(((q - a) @ ab) / (ab @ ab), 0, 1)
            dd = np.linalg.norm(q - (a + t[:, None] * ab[None]), axis=1)
            better = dd < best
            best[better] = dd[better]
            bt[better] = (s + t[better]) / (len(pl) - 1)
        taper = np.sin(np.pi * np.clip(bt, 0, 1)) ** 0.6
        # 沟的宽深沿长度也有点抖
        wob = 0.75 + 0.5 * U.noise1(bt * 6 + rng.uniform(0, 50), seed=int(rng.integers(1 << 20)))
        g = dep * taper * wob * np.clip(1 - (best / w) ** 2, 0, None)
        l_ = 0.22 * dep * taper * np.exp(-((best - 1.6 * w) / (0.6 * w)) ** 2)
        groove[m] = np.maximum(groove[m], g)
        lip[m] += l_
    return groove, lip


def eye_fields(side, u, v):
    """角膜细节：返回 (位移 h, 凹槽 R, 凸棱 G)，都是沿法线的米 / 0～1。"""
    rng = spec.rng_for("eye_detail_%d" % side)
    seed = 7 if side > 0 else 13
    rho = np.hypot(u, v)
    phi = np.arctan2(v, u)
    P3 = np.stack([u, v, np.zeros_like(u)], axis=1)
    cornea = 1 - U.smoothstep(RHO_RIM - 0.01, RHO_RIM + 0.02, rho)
    h = np.zeros_like(u)
    R = np.zeros_like(u)
    G = np.zeros_like(u)
    # 水肿：整片角膜轻微起伏（1～2 厘米）
    h += 0.00035 * (U.fbm3(P3 * 60, 3, seed) - 0.5) * 2 * cornea
    # 白色瘢痕：不规则的片（越靠中间越多），略隆起、表面粗
    blob = U.fbm3(P3 * 7 + 3.1, 4, seed + 1)
    scar = U.smoothstep(0.56, 0.64, blob) * (1 - U.smoothstep(0.22, 0.34, rho))
    halo = U.smoothstep(0.45, 0.6, U.fbm3(P3 * 16 + 9.7, 4, seed + 2)) * np.exp(-((rho - 0.1) / 0.05) ** 2)
    scar = np.clip(scar + halo, 0, 1) * cornea
    rough = (U.fbm3(P3 * 220, 2, seed + 3) - 0.5) * 2
    h += scar * (0.0009 + 0.0003 * rough)
    G += scar * 0.85
    # 划痕：主划痕 + 细划痕
    g1, l1 = _scratches(rng, 70, u, v, 0.13, 0.0025, 0.005, 0.0005, 0.0012, 0.03, 0.16)
    g2, l2 = _scratches(rng, 140, u, v, 0.17, 0.0016, 0.0026, 0.00018, 0.0004, 0.02, 0.09)
    groove = np.maximum(g1, g2) * cornea
    lip = np.clip(l1 + l2, 0, 0.0004) * cornea
    h += lip - groove
    R += np.clip(groove / 0.0007, 0, 1) * 0.9
    G += np.clip(lip / 0.0003, 0, 1) * 0.25
    # 锚咬住的地方：中央一个浅坑（锚盘坐在里面），周围一圈肿起的白翳
    crater = 1 - U.smoothstep(0.035, 0.058, rho)
    swell = np.exp(-((rho - 0.075) / 0.022) ** 2) * (0.6 + 0.8 * U.noise1(phi * 3 + 1.0, seed + 4))
    h += -0.0035 * crater + 0.0018 * swell
    R += crater * 0.6
    G += swell * 0.45
    # 边缘发灰的薄膜：内缘不规则、卷一点边，膜上一道道同心细皱
    rm = RHO_RIM - 0.095 + 0.03 * U.noise1(phi * 2.2, seed + 5) + 0.012 * U.noise1(phi * 9, seed + 6)
    M = U.smoothstep(rm - 0.003, rm + 0.005, rho)
    lipm = np.exp(-((rho - rm - 0.004) / 0.003) ** 2)
    warp = U.fbm3(P3 * 10, 3, seed + 7)
    wr = np.sin(2 * np.pi * rho / 0.012 * (1 + 0.35 * (warp - 0.5)) + 9 * warp)
    patch = U.smoothstep(0.38, 0.66, U.fbm3(P3 * 6 + 4.4, 3, seed + 9))
    radial = np.sin(phi * 110 + 9 * U.fbm3(P3 * 9, 2, seed + 8))
    h += M * (0.0022 + (0.0002 * wr + 0.00015 * radial * U.smoothstep(RHO_RIM - 0.05, RHO_RIM, rho)) * patch) \
        + 0.0009 * lipm
    crease = np.exp(-((rho - rm + 0.0005) / 0.0025) ** 2)
    R += crease * 0.8 + M * (0.22 + 0.15 * np.clip(-wr, 0, 1) * patch)
    return h, np.clip(R, 0, 1), np.clip(G, 0, 1)


def build_high(side, tag):
    n = int(math.ceil(RHO_END / HIGH_STEP))
    g = np.arange(-n, n + 1) * HIGH_STEP
    C = len(g)
    uu, vv = np.meshgrid(g, g, indexing="ij")
    uu, vv = uu.ravel(), vv.ravel()
    keep = np.hypot(uu, vv) <= RHO_END + 1e-9
    idx = np.full(len(uu), -1, dtype=np.int64)
    idx[keep] = np.arange(keep.sum())
    i, j = np.meshgrid(np.arange(C - 1), np.arange(C - 1), indexing="ij")
    i, j = i.ravel(), j.ravel()
    q = np.stack([i * C + j, (i + 1) * C + j, (i + 1) * C + j + 1, i * C + j + 1], axis=1)
    q = idx[q]
    q = q[(q >= 0).all(axis=1)]
    u, v = uu[keep], vv[keep]
    h, R, G = eye_fields(side, u, v)
    p, _ = to_world(side, u, v, h)
    ob = U.raw_mesh("EyeHigh" + tag, p, [q])
    O, e1, e2, ax = basis(side)
    zc = EYE_BULGE - (spec.EYE_RADIUS ** 2 + EYE_BULGE ** 2) / (2 * EYE_BULGE)
    ctr = O + ax * zc
    U.check_outward(ob, lambda c: lib.V(ctr))
    U.set_point_color(ob, "Curv", np.stack([R, G, np.zeros_like(R)], axis=1))
    U.set_point_color(ob, "Area", np.zeros_like(R))
    return ob


# ---------------------------------------------------------------------------- 总装接口
def build_highs():
    highs = []
    for side, tag in ((-1, "L"), (1, "R")):
        highs.append(build_high(side, tag))
        highs += eyes_parasite.build_high(side, tag)
    return highs


def build(coll, bake=False):
    mat = bpy.data.materials["M_GiantEye"]
    obs = []
    for side, tag in ((-1, "L"), (1, "R")):
        obs.append(build_low(side, tag, coll, mat))
        obs.append(eyes_parasite.build_low(side, tag, coll, mat))
    for o in obs:
        spec.set_body_uv(o)
    bakeutil.atlas_uv(obs, "eyes")
    if bake:
        t0 = time.time()
        highs = build_highs()
        print(f"eyes high: {lib.stats(highs):,} tris ({time.time() - t0:.1f}s)")
        # 眼睛这一组东西都很小、挨得近（两条卵带、锚盘贴着角膜）：笼子只往外推 2.5 厘米，射线 6 厘米，免得烘到邻居身上
        bakeutil.bake_set("eyes", obs, highs, extrusion=0.025, max_ray=0.06)
        for h in highs:
            bpy.data.objects.remove(h)
        print(f"eyes bake: {time.time() - t0:.1f}s")
    return obs
