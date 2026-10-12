"""甲壳高模（只烘焙）：甲片、尖刺按低模同一套解析外形密采样（约 2.5 厘米一个点），再加几毫米到几厘米的细节，
点色 "Curv"（R 凹槽、G 凸棱）、"Area"（R：刺尖 1、甲缘磨白 0.5～1），烘进 shell_normal / shell_mask。

细节（克制：大面干净，重点只有几处）：
  - 几丁质表面：一层很淡的颗粒、成片分布的细小凹坑（有的地方多、有的地方几乎没有）；
  - 沿生长方向的细纹（从甲片中心往甲缘放射）、甲缘附近一圈圈平行于甲缘的生长线；
  - 中棱顶上一道窄的棱线；
  - 缘边：磨圆、磨白（Area 0.5～1，藏在前一圈底下的前缘不磨），缘边上零星的小崩口（Area 1）；
  - 几道旧划痕（两三道一组平行的，像被什么刮过），两处愈合过的裂纹（中间一道细缝、两边鼓起的愈合痂）；
  - 刺：几道纵向细纹、一圈圈很淡的生长环，尖端磨圆磨白（Area 1），纵棱顶上略磨白；基座一圈放射的褶；
    断掉的那根断口参差（Area 0.8）。"""
import math
import time

import bpy
import numpy as np

from watcher import bakeutil
from watcher import shell_np as snp
from watcher import shell_mesh, shell_spike

H_PLATE = 0.032      # 高模点距（米）；再密烘焙峰值内存就过 9GB 了
H_SPIKE = 0.022


# ---------------------------------------------------------------------------- 建网格
def build_high(plates, spikes):
    t0 = time.time()
    cos, tris, atts = [], [], []
    off = 0
    keys = ("reg", "e", "w", "tk", "dk", "r", "lipu", "sig", "pid", "f", "phi", "sid", "q")
    for i, p in enumerate(plates):
        co, t, a = shell_mesh.plate_high(p, i, H_PLATE)
        cos.append(co)
        tris.append(t + off)
        atts.append({k: a.get(k, np.zeros(len(co)) - (1 if k in ("sid",) else 0)) for k in keys})
        off += len(co)
    print(f"  shell high plates: {off:,} verts {time.time() - t0:.1f}s")
    for i, sp in enumerate(spikes):
        co, t, a = shell_spike.spike_high(sp, i, H_SPIKE)
        cos.append(co)
        tris.append(t + off)
        d = {k: a.get(k, np.zeros(len(co))) for k in keys}
        d["pid"] = np.full(len(co), -1.0)
        d["e"] = np.full(len(co), 9.0)
        atts.append(d)
        off += len(co)
    co = np.concatenate(cos)
    tris = np.concatenate(tris)
    A = {k: np.concatenate([a[k] for a in atts]) for k in keys}
    ob = snp.make_mesh("ShellHigh", co, tris, None, None, smooth=True)
    print(f"  shell high: {len(co):,} verts, {len(tris):,} tris {time.time() - t0:.1f}s")
    return ob, co, A


def _mesh_arrays(ob):
    me = ob.data
    n = len(me.vertices)
    nor = np.empty(n * 3, dtype=np.float32)
    me.vertex_normals.foreach_get("vector", nor)
    e = np.empty(len(me.edges) * 2, dtype=np.int32)
    me.edges.foreach_get("vertices", e)
    return nor.reshape(-1, 3).astype(np.float64), e.reshape(-1, 2)


# ---------------------------------------------------------------------------- 细节
def _seg_dist(co, nor, P0, t, L):
    """点到线段（P0 + t·[0,L]）的切向距离（去掉法线方向的分量），以及沿线段的位置。"""
    v = co - P0
    tl = np.clip(v @ t, 0, L)
    perp = v - np.outer(tl, t)
    perp -= nor * (perp * nor).sum(1, keepdims=True)
    return np.linalg.norm(perp, axis=1), tl


def _poly_dist(co, nor, pts):
    d = np.full(len(co), 9.0)
    for a, b in zip(pts[:-1], pts[1:]):
        L = np.linalg.norm(b - a)
        if L < 1e-6:
            continue
        dd, _ = _seg_dist(co, nor, a, (b - a) / L, L)
        d = np.minimum(d, dd)
    return d


def details(co, nor, A, plates, spikes, rng):
    t0 = time.time()
    n = len(co)
    reg = A["reg"].astype(np.int64)
    top = reg == 0
    lip = reg == 1
    plate = reg <= 2
    shaft = reg == 3
    base = reg == 4
    frac = reg == 5
    spk = reg >= 3
    vis = ~(reg == 2)
    tk = np.where(plate, A["tk"], 0.0)
    e = A["e"]
    w = np.clip(A["w"], 0, 1.6)
    pid = A["pid"].astype(np.int64)
    kz = np.array([p.k for p in plates] + [1.0])[pid]
    hf = np.zeros(n)          # 中等尺度：划痕、裂纹、崩口、棱线、生长线
    hg = np.zeros(n)          # 细颗粒、凹坑
    area = np.zeros(n)

    # ---- 大面：很缓的起伏（几米一个）+ 一层淡颗粒
    hf += 0.004 * snp.fbm(co / 0.9, 2, seed=3) * vis
    grain = snp.fbm(co / 0.05, 2, seed=5)
    patch = snp.smoothstep(-0.35, 0.45, snp.fbm(co / 1.6, 2, seed=7))      # 粗糙的地方 / 光滑的地方
    hg += 0.0009 * grain * (0.5 + 0.5 * patch) * vis
    print(f"  grain {time.time() - t0:.1f}s")

    # ---- 细小凹坑：成片分布，甲缘附近、刺尖少
    f1, f2, rid = snp.voronoi(co / 0.075, seed=11)
    prad = 0.22 + 0.16 * snp._hash3((rid * 1e6).astype(np.int64), np.zeros(n, np.int64), np.zeros(n, np.int64), 13)
    x = f1 / prad
    on = (rid > 0.42) & vis
    dens = patch * np.where(plate, snp.smoothstep(0.08, 0.5, e), 1.0) * (1 - tk)
    dens = np.where(spk, dens * 0.45 * (1 - snp.smoothstep(0.7, 0.85, A["f"])), dens)
    pit = -0.004 * np.clip(1 - x * x, 0, 1) ** 1.5 + 0.0007 * np.exp(-((x - 1.1) / 0.18) ** 2)
    hg += np.where(on, pit, 0.0) * dens
    print(f"  pits {time.time() - t0:.1f}s")

    # ---- 甲片：放射细纹（沿生长方向）、甲缘生长线、中棱棱线
    perim = np.array([p.perim for p in plates] + [1.0])[pid]
    ph = 2 * math.pi * A["sig"] * perim / 0.055 + 2.5 * snp.perlin(co / 0.5, seed=17)
    stri = 0.0005 * np.sin(ph) * snp.smoothstep(0.3, 0.8, A["r"]) * snp.smoothstep(0.0, 0.25, e)
    gl = 2 * math.pi * e / 0.06 + 1.2 * snp.perlin(co / 0.7, seed=19)
    growth = 0.0006 * np.sin(gl) * snp.smoothstep(0.75, 0.2, e)
    gr2 = 0.0012 * np.maximum(0, np.sin(2 * math.pi * e / 0.3 + 0.8 * snp.perlin(co / 1.1, seed=21))) ** 10 \
        * snp.smoothstep(0.9, 0.3, e)
    mod = 0.6 + 0.4 * snp.smoothstep(-0.3, 0.3, snp.perlin(co / 1.4, seed=23))
    hf += np.where(top, (stri + growth + gr2) * mod * (1 - tk), 0.0)
    kh = np.array([p.prm["keel"] for p in plates] + [0.0])[pid]
    hf += np.where(top, 0.05 * kh * np.exp(-(A["dk"] / 0.035) ** 2) * snp.smoothstep(0.05, 0.4, e), 0.0)
    area += np.where(top, 0.3 * np.exp(-(A["dk"] / 0.05) ** 2) * (kh > 0.05) * snp.smoothstep(0.05, 0.4, e), 0.0)

    # ---- 缘边：磨白（Area 0.5～1）、小崩口（Area 1）
    wn = 0.5 + 0.5 * np.clip(0.5 + snp.fbm(co / 0.35, 2, seed=29), 0, 1)
    rim_top = np.where(top, snp.smoothstep(0.3 * kz, 0.02, e) * 0.85
                       + np.exp(-((e - 0.17 * kz) / (0.05 * kz)) ** 2) * 0.6, 0.0)
    rim_lip = np.where(lip, 1.0 - snp.smoothstep(0.35, 0.75, A["lipu"]), 0.0)
    wear = np.clip(np.maximum(rim_top, rim_lip) * np.clip(w, 0, 1), 0, 1) * (1 - tk)
    area = np.maximum(area, np.where(wear > 0.05, wear * wn, 0.0))
    # 崩口：只在甲缘最外那一道（卷边外沿），稀疏、大小不一，平的断面
    edge = lip & (A["lipu"] > 0.04) & (A["lipu"] < 0.5)
    sel = np.nonzero(edge & (w > 0.4))[0]
    c1, c2, crid = snp.voronoi(co[sel] / np.array([0.2, 0.2, 0.2]), seed=31)
    csz = 0.35 + 0.3 * snp._hash3((crid * 1e6).astype(np.int64), np.zeros(len(sel), np.int64),
                                  np.zeros(len(sel), np.int64), 33)
    chip = (crid > 0.9) & (c1 < csz)
    dep = 0.014 * np.clip((csz - c1) / 0.06, 0, 1) * chip
    hf[sel] -= dep
    area[sel] = np.where(chip & (dep > 0.002), 1.0, area[sel])
    print(f"  rim {time.time() - t0:.1f}s")

    # ---- 旧划痕：几组平行的
    vis_top = np.nonzero(top & (tk < 0.2) & (e > 0.35))[0]
    zones = np.array([p.zone for p in plates])
    for g in range(5):
        while True:
            i0 = vis_top[rng.integers(len(vis_top))]
            if zones[pid[i0]] in ("dorsal", "dlat", "lat"):
                break
        P0 = co[i0]
        nn = nor[i0]
        t = rng.normal(size=3)
        t -= nn * t.dot(nn)
        t /= np.linalg.norm(t)
        side = np.cross(nn, t)
        L = rng.uniform(1.2, 3.2)
        nl = int(rng.integers(1, 4))
        gap = rng.uniform(0.06, 0.13)
        near = np.nonzero(np.linalg.norm(co - (P0 + t * L * 0.5), axis=1) < L * 0.5 + 0.4)[0]
        near = near[vis[near]]
        for j in range(nl):
            Pj = P0 + side * gap * (j - 0.5 * (nl - 1)) + t * rng.uniform(-0.15, 0.15)
            Lj = L * rng.uniform(0.7, 1.0)
            wd = rng.uniform(0.006, 0.012)
            dep = rng.uniform(0.003, 0.006)
            d, tl = _seg_dist(co[near], nor[near], Pj, t, Lj)
            taper = np.sin(np.pi * np.clip(tl / Lj, 0, 1)) ** 0.6
            prof = -dep * np.exp(-(d / wd) ** 2) + 0.25 * dep * np.exp(-((d - 1.8 * wd) / (0.7 * wd)) ** 2)
            hf[near] += prof * taper
            area[near] = np.maximum(area[near], 0.4 * np.exp(-(d / wd) ** 2) * taper)
    print(f"  scratches {time.time() - t0:.1f}s")

    # ---- 愈合的裂纹：随机走的折线 + 一两条分叉
    cands = [i for i, p in enumerate(plates) if p.zone in ("dorsal", "dlat") and 2 <= p.ring <= 4]
    for c in range(2):
        pi = cands[rng.integers(len(cands))]
        sel_p = np.nonzero((pid == pi) & top & (e > 0.5))[0]
        i0 = sel_p[rng.integers(len(sel_p))]
        nn = nor[i0]
        t = rng.normal(size=3)
        t -= nn * t.dot(nn)
        t /= np.linalg.norm(t)

        def walk(P, t, steps):
            pts = [P]
            for _ in range(steps):
                ang = rng.normal(0, 0.45)
                side = np.cross(nn, t)
                t = t * math.cos(ang) + side * math.sin(ang)
                t /= np.linalg.norm(t)
                pts.append(pts[-1] + t * rng.uniform(0.05, 0.1))
            return pts, t

        pts, _ = walk(co[i0], t, 26)
        branches = [pts]
        for b in range(int(rng.integers(1, 3))):
            k = int(rng.integers(5, len(pts) - 5))
            tb = pts[k + 1] - pts[k]
            tb /= np.linalg.norm(tb)
            sd = np.cross(nn, tb) * (1 if rng.random() < 0.5 else -1)
            bp, _ = walk(pts[k], tb * 0.5 + sd * 0.85, 9)
            branches.append(bp)
        allp = np.array(pts)
        cen = allp.mean(0)
        R = np.linalg.norm(allp - cen, axis=1).max() + 0.3
        near = np.nonzero((np.linalg.norm(co - cen, axis=1) < R) & vis)[0]
        d = np.full(len(near), 9.0)
        for k, br in enumerate(branches):
            dd = _poly_dist(co[near], nor[near], np.array(br))
            d = np.minimum(d, dd * (1.0 if k == 0 else 1.6))
        hf[near] += 0.009 * np.exp(-(d / 0.05) ** 2) - 0.007 * np.exp(-(d / 0.007) ** 2)
    print(f"  cracks {time.time() - t0:.1f}s")

    # ---- 刺
    f = A["f"]
    phi = A["phi"]
    fs = f * np.array([s.L for s in spikes] + [1.0])[A["sid"].astype(np.int64)]
    rids = np.abs(np.cos(shell_spike.RIDGES / 2 * (phi - math.pi / shell_spike.RIDGES)))
    hf += np.where(shaft, 0.0006 * np.sin(phi * 31 + 2 * snp.perlin(co / 0.3, seed=41))
                   * (1 - snp.smoothstep(0.8, 0.95, f)), 0.0)
    hf += np.where(shaft, 0.0007 * np.sin(2 * math.pi * fs / 0.09 + 2 * snp.perlin(co / 0.6, seed=43))
                   * (1 - snp.smoothstep(0.75, 0.9, f)), 0.0)
    tip = snp.smoothstep(0.8, 0.95, f)
    hg = np.where(shaft, hg * (1 - tip), hg)
    area = np.where(shaft, np.maximum(area, np.maximum(tip, 0.3 * rids ** 8 * snp.smoothstep(0.1, 0.3, f))), area)
    # 刺尖的小崩面
    tsel = np.nonzero(shaft & (f > 0.88))[0]
    if len(tsel):
        a1, a2, ar = snp.voronoi(co[tsel] / 0.035, seed=47)
        hf[tsel] -= 0.004 * ((ar > 0.72) & (a1 < 0.5)) * np.clip((0.5 - a1) / 0.1, 0, 1)
    # 基座放射褶
    q = A["q"]
    hf += np.where(base, 0.003 * np.sin(phi * 17 + 3 * snp.perlin(co / 0.25, seed=53))
                   * np.exp(-((q + 0.5) / 0.25) ** 2), 0.0)
    # 断口
    hf += np.where(frac, 0.025 * snp.fbm(co / 0.07, 3, seed=59) * np.clip(q * 3, 0, 1), 0.0)
    area = np.where(frac, 0.8, area)
    print(f"  spikes {time.time() - t0:.1f}s")
    # 底面不要细节、不磨白
    hf = np.where(reg == 2, 0.0, hf)
    hg = np.where(reg == 2, 0.0, hg)
    area = np.where(reg == 2, 0.0, area)
    return hf, hg, np.clip(area, 0, 1)


def curv(co0, nor, hf, hg, nb, e):
    """凹槽 / 凸棱：底形曲率（按边长归一化成 1/米）+ 细节和它模糊后的差。"""
    n = len(co0)
    d = co0[e[:, 1]] - co0[e[:, 0]]
    l2 = (d * d).sum(1)
    el2 = (np.bincount(e[:, 0], weights=l2, minlength=n) + np.bincount(e[:, 1], weights=l2, minlength=n)) / nb.deg
    lap = np.zeros(n)
    for k in range(3):
        lap += (nb.avg(co0[:, k]) - co0[:, k]) * nor[:, k]
    kap = nb.blur(4 * lap / np.maximum(el2, 1e-8), 3)
    cav = np.clip((kap - 1.5) / 7.0, 0, 1)
    rid = np.clip((-kap - 2.0) / 8.0, 0, 1)
    hd = hf + hg
    hb = nb.blur(hd, 6)
    cav = np.maximum(cav, np.clip((hb - hd) / 0.004, 0, 1))
    rid = np.maximum(rid, np.clip((hd - hb) / 0.003, 0, 1))
    return cav, rid


def make_high(plates, spikes):
    t0 = time.time()
    rng = np.random.default_rng(20241)
    ob, co, A = build_high(plates, spikes)
    nor, e = _mesh_arrays(ob)
    hf, hg, area = details(co, nor, A, plates, spikes, rng)
    newco = co + nor * (hf + hg)[:, None]
    me = ob.data
    me.vertices.foreach_set("co", newco.astype(np.float32).ravel())
    me.update()
    nb = snp.Nb(e, len(co))
    cav, rid = curv(co, nor, hf, hg, nb, e)
    n = len(co)
    a = me.attributes.new("Curv", 'FLOAT_COLOR', 'POINT')
    a.data.foreach_set("color", np.stack([cav, rid, np.zeros(n), np.ones(n)], 1).astype(np.float32).ravel())
    a = me.attributes.new("Area", 'FLOAT_COLOR', 'POINT')
    a.data.foreach_set("color", np.stack([area, area, area, np.ones(n)], 1).astype(np.float32).ravel())
    print(f"shell high: {n:,} verts, {len(me.polygons):,} tris, {time.time() - t0:.1f}s")
    return ob


def bake(plates, spikes, lows):
    t0 = time.time()
    high = make_high(plates, spikes)
    try:
        bakeutil.bake_set("shell", lows, [high], extrusion=0.1, max_ray=0.28, ao_distance=1.0)
    finally:
        me = high.data
        bpy.data.objects.remove(high)
        bpy.data.meshes.remove(me)
    print(f"shell bake total {time.time() - t0:.1f}s")
