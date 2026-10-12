"""桨的高模（只用来烘焙）：paddle_geo 的同一套参数形体按 ~1.5 厘米重新采样，再沿法线加细节，烘进 paddle_normal / paddle_mask。

细节（克制：桨是它的弱点，软膜要一眼看得出来，硬甲干净）：
  - 硬甲（根节、中节、叶片的桨骨和鳍条）：顺着节的细生长纹、稀疏的细颗粒、大面很浅的起伏、几道旧划痕；
    每节远端一圈加厚的甲唇（珠边）；
  - 鳍条：圆鼓的脊（两面都有），每隔 18 厘米一道浅的分节沟；
  - 鳍条之间的膜：比鳍条低一点（下陷）、顺着鳍条的细纹、靠后缘几处成片的细皱；
  - 关节膜：一圈圈的环褶 + 细皱；根部肉褶：一圈圈环褶 + 放射的浅沟。
点色 "Curv"：R 凹槽、G 凸棱（含后缘、甲唇这些几何上的凸棱）；"Area"：R = 软组织（关节膜、根部肉褶、鳍条之间的膜）。
"""
import math
import time

import bpy
import numpy as np

from watcher import bakeutil
from watcher import shell_np as snp
from watcher import paddle_geo as pg
from watcher import paddles as pm

ss = snp.smoothstep
STEP = 0.015          # 沿长度的采样间距（米）
KV = 28               # 截面点数 = 低模 NV × KV
# AO 不用 Cycles 烘（桨会动，只要细节自己的遮蔽；Cycles 在高模高过低模的地方会成片发黑，后缘又薄得没法往里收），
# 在高模上按凹槽算好写进点色 "AOv"，bakeutil 用 EMIT 烘进 mask.R


def high_stations(pd):
    lo = pg.stations(pd)
    out = []
    for a, b in zip(lo[:-1], lo[1:]):
        n = max(1, int(math.ceil((b - a) / STEP)))
        out.append(a + (b - a) * np.arange(n) / n)
    out.append(lo[-1:])
    # 叶尖：低模最后一圈到叶尖点之间再补几圈（截面越来越小）
    tail = np.linspace(lo[-1], pd.L, 12)[1:-1]
    return np.concatenate(out + [tail])


def high_vcols(n):
    """高模截面的 v：大致按弦长均匀（低模的余弦分布在前后缘挤成零点几毫米，曲率会被噪声放大），前后缘留一点加密。"""
    t = -math.pi + 2 * math.pi * np.arange(n) / n
    u = np.abs(t) / math.pi
    return np.sign(t) * (0.3 * np.abs(t) + 0.7 * np.arccos(1 - 2 * u))


def grid_normals(P):
    """(ni, nj, 3) 的网格（j 方向闭合）→ 顶点法线（朝外，按截面中心判断）。"""
    di = np.gradient(P, axis=0)
    dj = np.roll(P, -1, axis=1) - np.roll(P, 1, axis=1)
    n = np.cross(dj, di)
    n /= np.maximum(np.linalg.norm(n, axis=-1, keepdims=True), 1e-12)
    cen = P.mean(1, keepdims=True)
    if (np.einsum("ijk,ijk->ij", n, P - cen) < 0).mean() > 0.5:
        n = -n
    return n


def blur_grid(h, it):
    """网格上的模糊（j 闭合）。"""
    for _ in range(it):
        h = 0.5 * h + 0.125 * (np.roll(h, 1, 1) + np.roll(h, -1, 1)) + \
            0.125 * (np.concatenate([h[:1], h[:-1]], 0) + np.concatenate([h[1:], h[-1:]], 0))
    return h


def scratches(pd, X, S, hard, rng, n=12):
    """硬甲上几道旧划痕（在 (x, 绕截面弧长) 平面里的短线段）。"""
    out = np.zeros_like(X)
    for _ in range(n):
        x0 = rng.uniform(pd.xs + 0.8, pd.L * 0.9)
        s0 = rng.uniform(-1.5, 1.5)
        ang = rng.uniform(-0.6, 0.6) + (0.0 if rng.random() < 0.7 else math.pi / 2)
        ln = rng.uniform(0.25, 0.9)
        dx, ds = math.cos(ang), math.sin(ang)
        t = np.clip((X - x0) * dx + (S - s0) * ds, 0, ln)
        d = np.hypot(X - (x0 + t * dx), S - (s0 + t * ds))
        fade = np.sqrt(np.clip(np.sin(math.pi * t / ln), 0, 1))
        out = np.minimum(out, -0.0035 * np.exp(-(d / 0.007) ** 2) * fade)
    return out * hard


def detail(pd, G, S):
    """高度（沿法线，米）和区域。G 是 paddle_grid 的输出（ni, nj），S 是绕截面的弧长。"""
    P, x, c, W = G["P"], G["x"], G["c"], G["W"]
    sc = pd.sc
    rng = np.random.default_rng(pd.seed)
    flat = P.reshape(-1, 3)
    shp = x.shape
    R, ridx, rdist, rr = pd.ray_field(x, c, W)
    soft = pg.soft_mask(pd, G, R)
    hard = 1.0 - soft
    h = np.zeros(shp)
    # 大面很浅的起伏
    h += 0.010 * snp.fbm(flat / 0.9, 3, seed=pd.seed).reshape(shp) * hard
    # 生长纹（顺着节，绕一圈）
    wob = 3.0 * snp.fbm(flat / 0.6, 2, seed=pd.seed + 3).reshape(shp)
    patch = ss(0.05, 0.45, snp.fbm(flat / 1.1, 2, seed=pd.seed + 4).reshape(shp))
    h += 0.0007 * np.sin(2 * math.pi * x / 0.055 + wob) * hard * patch
    # 细颗粒（稀疏）
    f1, f2, rid = snp.voronoi(flat / 0.04, seed=pd.seed + 5)
    gran = (np.clip(1 - (f1 / 0.35) ** 2, 0, 1) ** 1.5 * (rid < 0.35)).reshape(shp)
    h += 0.0016 * gran * hard
    # 每节远端的甲唇（珠边）+ 关节膜环褶
    for xj in pd.xj:
        bead = ss(xj - 0.17 * sc, xj - 0.12 * sc, x) * ss(xj - 0.03 * sc, xj - 0.07 * sc, x)
        h += 0.014 * bead
        u = (x - (xj - 0.03 * sc)) / (0.20 * sc)
        band = ss(0.0, 0.12, u) * ss(1.0, 0.85, u)
        ph = x / (0.045 * sc) + 0.8 * snp.fbm(flat / 0.5, 2, seed=pd.seed + 7).reshape(shp)
        h += 0.010 * band * (np.abs(np.sin(math.pi * ph)) - 0.63)
    # 根部肉褶：不规则的环褶 + 几道放射浅沟
    u = x - pd.xs
    band = ss(-0.12, 0.0, u) * ss(0.62, 0.40, u)
    ph = u / 0.085 + 1.2 * snp.fbm(flat / 0.7, 2, seed=pd.seed + 9).reshape(shp)
    amp = 0.6 + 0.8 * ss(-0.3, 0.4, snp.fbm(flat / 0.5, 2, seed=pd.seed + 10).reshape(shp))
    h += 0.014 * band * amp * (np.abs(np.sin(math.pi * ph)) - 0.63)
    per = S.max() - S.min() + 1e-6
    for _ in range(7):
        s0 = rng.uniform(S.min(), S.max())
        ds = np.abs(np.mod(S - s0 + 0.5 * per, per) - 0.5 * per)
        wd = rng.uniform(0.03, 0.07)
        ln = rng.uniform(0.25, 0.6)
        h -= rng.uniform(0.006, 0.012) * np.exp(-(ds / wd) ** 2) * ss(ln, 0.0, u) * ss(-0.12, 0.0, u)
    # 细皱（软组织）
    h += 0.0025 * snp.fbm(flat / 0.07, 3, seed=pd.seed + 13).reshape(shp) * soft
    # 鳍条：圆鼓的脊、分节沟；鳍条之间的膜下陷、细纹
    seg = rr / (0.18 * sc)
    groove = np.exp(-(((seg - np.floor(seg)) - 0.5) / 0.07) ** 2)
    h += 0.028 * sc * R - 0.005 * R * groove
    blade = ss(pd.xj[1] + 0.25 * sc, pd.xj[1] + 0.6 * sc, x) * ss(pg.C_SPAR + 0.02, pg.C_SPAR + 0.10, c)
    h -= 0.006 * blade * (1 - R)
    h += 0.0008 * blade * np.sin(2 * math.pi * rdist / 0.035) * (1 - R)
    wr = ss(0.55, 0.95, c) * ss(0.1, 0.5, snp.fbm(flat / 1.5, 2, seed=pd.seed + 15).reshape(shp))
    h += 0.003 * blade * wr * np.sin(2 * math.pi * (rdist / 0.09 + 0.3 * snp.fbm(flat / 0.3, 2, seed=pd.seed + 17)
                                                   .reshape(shp)))
    h += scratches(pd, x, S, hard, rng)
    # 后缘最薄处不往里压（别把两面压穿）
    h = np.maximum(h, -0.6 * (G["half"] - 0.004))
    return h, soft


def paddle_high(pd):
    t0 = time.time()
    xs = high_stations(pd)
    vs = high_vcols(pm.NV * KV)
    G = pd.grid(xs, vs)
    P = G["P"]
    ni, nj = P.shape[:2]
    ring = np.concatenate([P, P[:, :1]], 1)
    S = np.concatenate([np.zeros((ni, 1)), np.cumsum(np.linalg.norm(ring[:, 1:] - ring[:, :-1], axis=-1), 1)], 1)
    S = (S - S[:, nj // 2][:, None])[:, :nj]
    h, soft = detail(pd, G, S)
    nrm = grid_normals(P)
    Q = P + nrm * h[..., None]
    # 凹槽 / 凸棱：细节高度的高通 + 截面几何曲率（后缘、甲唇是凸棱，关节沟是凹槽）
    hb = blur_grid(h, 6)
    cav = np.clip((hb - h) / 0.003, 0, 1)
    rid = np.clip((h - hb) / 0.003, 0, 1)
    # 几何曲率用加细节前的光滑面算（细节的起伏上面已经算过了）
    lap_j = ((np.roll(P, 1, 1) + np.roll(P, -1, 1) - 2 * P) * nrm).sum(-1)
    dj = 0.5 * (np.linalg.norm(np.roll(P, -1, 1) - P, axis=-1) + np.linalg.norm(np.roll(P, 1, 1) - P, axis=-1))
    kj = -lap_j / np.maximum(dj * dj, 1e-6)              # > 0 凸
    Pp = np.concatenate([P[:1], P[:-1]], 0)
    Pn = np.concatenate([P[1:], P[-1:]], 0)
    lap_i = ((Pp + Pn - 2 * P) * nrm).sum(-1)
    di = np.maximum(0.5 * (np.linalg.norm(Pn - P, axis=-1) + np.linalg.norm(Pp - P, axis=-1)), 1e-4)
    ki = -lap_i / (di * di)
    k = blur_grid(kj + ki, 2)
    rid = np.maximum(rid, np.clip((k - 6.0) / 25.0, 0, 1))
    cav = np.maximum(cav, np.clip((-k - 3.0) / 12.0, 0, 1))
    # AO：两个尺度的凹陷 + 几何上凹的地方（关节沟、鳍条根），根部贴着身体的那圈最暗
    occ = 0.5 * np.clip((blur_grid(h, 4) - h) / 0.004, 0, 1) + 0.5 * np.clip((blur_grid(h, 16) - h) / 0.008, 0, 1)
    occ = np.maximum(occ, np.clip(-blur_grid(k, 4) / 8.0, 0, 1))
    ao = (1.0 - 0.5 * np.clip(occ, 0, 1)) * (0.5 + 0.5 * ss(pd.xs - 0.05, pd.xs + 0.5, G["x"]))
    # 网格：圈与圈之间的四边形（j 闭合）+ 叶尖扇
    tip = pd.tip()
    co = np.concatenate([Q.reshape(-1, 3), tip[None]], 0)
    i, j = np.meshgrid(np.arange(ni - 1), np.arange(nj), indexing="ij")
    a = i * nj + j
    b = i * nj + (j + 1) % nj
    tris = np.concatenate([np.stack([a, b, b + nj], -1).reshape(-1, 3), np.stack([a, b + nj, a + nj], -1).reshape(-1, 3),
                           np.stack([(ni - 1) * nj + np.arange(nj), np.full(nj, ni * nj),
                                     (ni - 1) * nj + (np.arange(nj) + 1) % nj], -1)], 0)
    attrs = dict(cav=np.append(cav.ravel(), 0.0), rid=np.append(rid.ravel(), 0.0), soft=np.append(soft.ravel(), 0.0),
                 ao=np.append(ao.ravel(), 1.0))
    print(f"  {pd.name} high: {ni} x {nj} = {len(co):,} verts, {time.time() - t0:.1f}s")
    return co, tris, attrs


def bake(pads, lows):
    t0 = time.time()
    cos, tris, cav, rid, soft, ao = [], [], [], [], [], []
    off = 0
    for pd in pads:
        co, t, at = paddle_high(pd)
        # 朝向和低模一致：按低模同一套规则（中节截面朝外）翻
        cen = co[t].mean(1)
        n = np.cross(co[t[:, 1]] - co[t[:, 0]], co[t[:, 2]] - co[t[:, 0]])
        xm = (cen - pd.o) @ pd.d
        sel = (xm > pd.xj[0] + 0.5) & (xm < pd.xj[1] - 0.5)
        axis = pd.o + np.outer(xm, pd.d)
        if (np.einsum("ij,ij->i", n[sel], (cen - axis)[sel]) < 0).mean() > 0.5:
            t = t[:, ::-1].copy()
        cos.append(co)
        tris.append(t + off)
        off += len(co)
        cav.append(at["cav"])
        rid.append(at["rid"])
        soft.append(at["soft"])
        ao.append(at["ao"])
    co = np.concatenate(cos)
    tr = np.concatenate(tris)
    ob = snp.make_mesh("PaddlesHigh", co, tr, bpy.context.scene.collection)
    del cos, tris
    me = ob.data
    nv = len(co)
    cav, rid, soft, ao = np.concatenate(cav), np.concatenate(rid), np.concatenate(soft), np.concatenate(ao)
    a = me.attributes.new("Curv", 'FLOAT_COLOR', 'POINT')
    a.data.foreach_set("color", np.stack([cav, rid, np.zeros(nv), np.ones(nv)], 1).astype(np.float32).ravel())
    a = me.attributes.new("Area", 'FLOAT_COLOR', 'POINT')
    a.data.foreach_set("color", np.stack([soft, soft, soft, np.ones(nv)], 1).astype(np.float32).ravel())
    a = me.attributes.new("AOv", 'FLOAT_COLOR', 'POINT')
    a.data.foreach_set("color", np.stack([ao, ao, ao, np.ones(nv)], 1).astype(np.float32).ravel())
    print(f"paddle high: {len(me.polygons):,} faces, {time.time() - t0:.1f}s")
    bakeutil.bake_set("paddle", lows, [ob], extrusion=0.04, max_ray=0.14, ao_distance=0.6)
    if ob.name in bpy.data.objects:
        me = ob.data
        bpy.data.objects.remove(ob)
        bpy.data.meshes.remove(me)
    print(f"paddle bake total {time.time() - t0:.1f}s")
