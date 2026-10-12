"""鳍的高模（只烘焙）：用和低模同一套参数曲面高分辨率重新生成（2～3 厘米一个点），再加克制的细节：
  - 盾鳞颗粒：几厘米的细密小疙瘩（和皮同尺度），很浅；
  - 大面的轻微起伏（几十厘米、几毫米高），不要满身噪声；
  - 皮下隐约的辐射状软骨（鳍根到鳍的中段，十几厘米宽、几毫米高的长条隆起，往鳍缘淡出），外半截是更细的纤维纹；
  - 根部的屈曲皱（平行于鳍根的几道浅褶，后半截多）、尾柄接缝后几道竖皱；
  - 后缘的老旧磨损（参差的小疙瘩、发白）、旧撕口边的疤组织（鼓、发白）、一两道疤（隆起的愈合线、中间一道细沟）。
点色：Curv（R 凹槽 / G 凸棱·发白）、Area（R = 鳍膜薄处，1 最薄透光）都在这里按细节函数直接算。
"""
import math
import time

import bpy
import numpy as np

from giant import spec, bakeutil
from giant import fins_geo as G


# ---------------------------------------------------------------------------- 噪声（随机方向余弦叠加，numpy 向量化）
def _waves(P, wavelength, seed, n=14):
    rng = np.random.default_rng(seed)
    d = rng.normal(size=(n, 3))
    d /= np.linalg.norm(d, axis=1)[:, None]
    k = 2 * math.pi / wavelength * rng.uniform(0.75, 1.3, n)
    ph = rng.uniform(0, 2 * math.pi, n)
    out = np.zeros(len(P))
    for i in range(n):
        out += np.cos(P @ (d[i] * k[i]) + ph[i])
    return out / math.sqrt(n / 2)


def fbm(P, wavelength, seed, octaves=3, gain=0.5):
    out = np.zeros(len(P))
    a, tot = 1.0, 0.0
    for o in range(octaves):
        out += a * _waves(P, wavelength / 2.0**o, seed + 17 * o)
        tot += a * a
        a *= gain
    return out / math.sqrt(tot)


def _sm(a, b, x):
    return G.smoothstep(a, b, x)


def _seg_dist(p2, poly):
    poly = np.asarray(poly, dtype=np.float64)
    d, _ = G.polyline_dist(p2, poly, closed=False)
    return d


# ---------------------------------------------------------------------------- 细节
def details(P, N, info, seed):
    """P、N：顶点和法线 (n,3)；info：各种鳍上的坐标（见调用处）。返回 (位移, curvR, curvG, area)。"""
    n = len(P)
    h = np.zeros(n)
    cR = np.zeros(n)
    cG = np.zeros(n)
    along, ray, d_edge, trail = info["along"], info["ray"], info["d_edge"], info["trail"]
    thick, span = info["thick"], info["span"]
    rootw = info.get("rootw", np.zeros(n))       # 1 = 根部圆角/肉褶区（不加鳍上的纹理）
    fin = 1.0 - rootw
    # 弦很短的地方（鳍梢）不要辐射纹：x 等值线在梢上挤成一束，看着像扇贝壳
    wide = _sm(0.9, 1.7, info["chord"]) if "chord" in info else np.ones(n)

    # 盾鳞颗粒：很浅的小疙瘩（取绝对值做成一粒粒的感觉）
    # （波长别小于高模点距的 2.5 倍，不然烘出来是一道道摩尔纹）
    g1 = np.abs(_waves(P, 0.07, seed + 1, 16))
    g2 = np.abs(_waves(P, 0.11, seed + 2, 12))
    h += 0.0009 * (g1 - 0.75) + 0.0006 * (g2 - 0.75)
    # 大面的轻微起伏
    h += 0.0035 * fbm(P, 0.9, seed + 3, 2) * fin

    # 皮下的辐射状软骨：沿 ray 方向的长条隆起，鳍根往外渐显、到中段往外淡出，鳍缘附近没有
    wob = 0.18 * fbm(P, 1.6, seed + 4, 2)
    rp = ray + wob
    rid = 0.5 + 0.5 * np.cos(2 * math.pi * rp)
    amp = 1.0 + 0.35 * np.sin(np.floor(rp) * 2.39 + seed)          # 每根粗细不一
    env = _sm(0.15, 0.7, along) * (1.0 - _sm(0.45, 0.9, along / span)) * _sm(0.06, 0.35, d_edge) * fin * wide
    h += 0.0045 * amp * (rid**2 - 0.38) * env
    cR += 0.18 * (1.0 - rid) ** 3 * env
    cG += 0.08 * rid**4 * env
    # 外半截：更细的纤维纹（角质鳍条在皮下），很淡
    env2 = _sm(0.35, 0.65, along / span) * (1.0 - _sm(0.7, 0.88, along / span)) * _sm(0.03, 0.2, d_edge) * fin * wide
    rf = 0.5 + 0.5 * np.cos(2 * math.pi * (ray * 3.0 + 0.6 * wob))
    h += 0.0007 * (rf - 0.5) * env2

    # 根部的屈曲皱：平行于鳍根的几道浅褶，后半截（靠后缘）多
    wr = info.get("wrinkle")
    if wr is not None:
        coord, wenv = wr
        ph = 2 * math.pi * coord / 0.24 + 2.2 * fbm(P, 1.1, seed + 5, 2)
        s = np.sin(ph)
        h += 0.0035 * s * wenv
        cR += 0.45 * np.clip(-s, 0, 1) ** 2 * wenv

    # 后缘磨损：参差的小疙瘩、发白
    band = float(np.clip(0.05 * span + 0.07, 0.12, 0.28))      # 磨损带宽度跟着鳍的大小
    we = (1.0 - _sm(0.0, band, d_edge)) * (0.35 + 0.65 * trail)
    small = float(np.clip(span / 5.0, 0.45, 1.0))                # 小鳍上的磨损也小
    rough = fbm(P, 0.09, seed + 6, 2)
    h += 0.0022 * small * rough * we
    nick = np.clip(_waves(P, 0.18, seed + 7, 10) - 1.1, 0, None)    # 零星的小缺口（往里凹）
    h -= 0.0035 * small * nick * we
    cG += we * (0.2 + 0.12 * np.clip(rough, -1, 1)) * trail + 0.08 * we
    cR += 0.4 * np.clip(nick, 0, 1) * we

    # 旧撕口边的疤组织
    for (p0, rad) in info.get("notch_pts", []):
        dn = np.linalg.norm(info["p2"] - np.asarray(p0)[None, :], axis=1)
        w = 1.0 - _sm(rad * 0.4, rad, dn)
        lump = fbm(P, 0.08, seed + 8, 2)
        h += w * (0.002 + 0.0018 * lump)
        cG += w * (0.45 + 0.25 * lump)

    # 疤：一道隆起的愈合线，中间一道细沟，发白
    for poly, width in info.get("scars", []):
        ds = _seg_dist(info["p2"], poly)
        wig = 1.0 + 0.3 * fbm(P, 0.3, seed + 9, 2)
        ds = ds * wig
        h += 0.0065 * np.exp(-(ds / width) ** 2) - 0.0035 * np.exp(-(ds / (width * 0.25)) ** 2)
        cG += 0.8 * np.exp(-(ds / (width * 1.3)) ** 2)
        cR += 0.55 * np.exp(-(ds / (width * 0.3)) ** 2)

    # 根部的肉褶沟
    if "fold" in info:
        cR += info["fold"]

    # 薄处（鳍缘、梢）位移按厚度收：只限往里会让噪声在鳍缘全变成往外鼓，烘出来一圈「卷边」
    lim = 0.3 * 0.5 * thick + 0.0006
    h = np.clip(h, -lim, lim)
    # 透光看「这一截鳍有多厚」：前缘虽然尖到 0，但它是圆厚的前缘，不透光；所以用 thick_eff（前缘按最厚处算）
    area = 1.0 - _sm(0.02, 0.24, info.get("thick_eff", thick))
    return h, np.clip(cR, 0, 1), np.clip(cG, 0, 1), area


def _apply(ob, h, cR, cG, area):
    me = ob.data
    n = len(me.vertices)
    co = np.empty(n * 3)
    me.vertices.foreach_get("co", co)
    nor = np.empty(n * 3)
    me.vertex_normals.foreach_get("vector", nor)
    co = co.reshape(-1, 3) + nor.reshape(-1, 3) * h[:, None]
    me.vertices.foreach_set("co", co.ravel())
    me.update()
    a = me.attributes.new("Curv", 'FLOAT_COLOR', 'POINT')
    a.data.foreach_set("color", np.stack([cR, cG, np.zeros(n), np.ones(n)], axis=1).astype(np.float32).ravel())
    b = me.attributes.new("Area", 'FLOAT_COLOR', 'POINT')
    b.data.foreach_set("color", np.stack([area, area, area, np.ones(n)], axis=1).astype(np.float32).ravel())


def _normals(ob):
    me = ob.data
    n = len(me.vertices)
    co = np.empty(n * 3)
    me.vertices.foreach_get("co", co)
    nor = np.empty(n * 3)
    me.vertex_normals.foreach_get("vector", nor)
    return co.reshape(-1, 3), nor.reshape(-1, 3)


# ---------------------------------------------------------------------------- 管状鳍高模
GROW = 0.035      # 高模的轮廓比低模往外扩这么多（米）
def tube_high(fin, coll, step=0.025):
    import copy
    from giant.fins import _orient
    fin = copy.copy(fin)
    fin.pf = G.Planform(fin.pf.pts, fin.pf.notches, grow=GROW)
    H = fin.pf.H
    per = 2 * (fin.pf.le(0.0) - fin.pf.te(0.0)) + 4 * fin.R + 1.0
    M = int(math.ceil(per / step / 2)) * 2
    n = int(H / step)
    rows = fin.root_rows(n_fillet=int(fin.R / step * 1.6) + 4, n_skirt=6, dense=True)
    rows += fin.span_rows(n, fin.notch_rows(41), ntip=max(8, n // 12))
    g = fin.build(rows, M)
    verts, faces, used = G.tube_topology(g)
    ob = G.make_mesh(fin.name + "_high", coll, verts, faces, None)
    _orient(ob)
    P, N = _normals(ob)
    f = {k: g[k].ravel()[used] for k in ("x", "sg", "hgt", "thick", "chord", "hs", "c", "off")}
    x, chord, hs, hgt, off = f["x"], f["chord"], f["hs"], f["hgt"], f["off"]
    rootw = (off > 1e-6).astype(np.float64) * 1.0
    rootw = np.maximum(rootw, 1.0 - _sm(fin.R * 0.6, fin.R + 0.1, hgt))
    chord0 = fin.pf.le(0.0) - fin.pf.te(0.0, notched=False)
    nrays = max(int(round(chord0 / 0.42)), 4)
    d_edge = np.minimum.reduce([x * chord, (1 - x) * chord, (H - hs) * 1.2]) + off * 3.0
    trail = _sm(-0.2, 0.2, x * chord - (1 - x) * chord)
    # 根部屈曲皱：沿离体表的高度，0.1～1 米，后半截（x 大）多
    wtop = min(1.3, 0.3 * H)                     # 皱只在根部那一截（小背鳍上就很短）
    wenv = _sm(0.08, 0.25, hgt) * (1.0 - _sm(wtop * 0.45, wtop, hgt)) * (0.3 + 0.7 * _sm(0.3, 0.9, x)) * (off < 1e-6)
    # 肉褶沟：圆角脚（贴皮那圈）
    fold = 0.6 * np.exp(-((hgt - 0.012) / 0.025) ** 2) * (off > fin.R * 0.5)
    p2 = np.stack([f["c"], hs], axis=1)
    notch_pts = [((float(fin.pf.te(h0)), h0), hw * 0.8) for h0, hw, dep, sk in fin.pf.notches]
    thk_eff = np.asarray(fin.thk(hs), dtype=np.float64) * G.naca(np.maximum(x, 0.3)) + 2 * off
    info = dict(thick_eff=thk_eff, chord=chord, along=hgt, ray=x * nrays, d_edge=d_edge, trail=trail, thick=f["thick"], span=H,
                rootw=rootw, wrinkle=(hgt, wenv), fold=fold, p2=p2, notch_pts=notch_pts,
                scars=getattr(fin, "scars", []))
    h, cR, cG, area = details(P, N, info, spec.rng_for(fin.name).integers(1 << 20))
    _apply(ob, h, cR, cG, area)
    return ob


def caudal_high(coll, step=0.025):
    from giant import fins as F
    ob, inf = F.caudal_sheet(step, coll, "Caudal_high", None, with_uv=False, seam=False, grow=GROW)
    P, N = _normals(ob)
    p2 = inf["p2"]
    rel = p2 - F.HUB[None, :]
    r = np.linalg.norm(rel, axis=1)
    ang = np.arctan2(rel[:, 1], rel[:, 0])
    # 尾柄（身体那段）：不加鳍上的纹理
    rootw = 1.0 - _sm(-0.02, 0.05, inf["tf"] - inf["xb"])
    rootw = np.where(p2[:, 0] < F.SEAM_B - 0.2, 1.0, rootw)
    b = p2[:, 0]
    wenv = 0.6 * _sm(F.SEAM_B, F.SEAM_B + 0.3, b) * (1.0 - _sm(2.2, 3.0, b)) * (1.0 - _sm(1.2, 2.0, np.abs(p2[:, 1] - 0.5)))
    fold = 0.5 * np.exp(-((b - F.SEAM_B) / 0.06) ** 2) * (np.abs(p2[:, 1] - 0.5) < 1.3)
    poly, lead, tot = F._caudal_poly(step, GROW)
    notch_pts = []
    for t0, hw, dep in F.CAUDAL_NOTCHES:
        L = np.linalg.norm(np.diff(np.vstack([poly, poly[:1]]), axis=0), axis=1)
        cum = np.concatenate([[0.0], np.cumsum(L)[:-1]]) / L.sum()
        k = int(np.argmin(np.abs(cum - t0)))
        notch_pts.append((poly[k], hw * 0.8))
    info = dict(thick_eff=2 * inf["T_eff"], along=np.maximum(r - 1.7, 0.0), ray=ang / 0.085, d_edge=inf["d_edge"], trail=1.0 - inf["lead"], thick=2 * inf["T"],
                span=7.5, rootw=rootw, wrinkle=(b, wenv), fold=fold, p2=p2, notch_pts=notch_pts,
                scars=F.CAUDAL_SCARS)
    h, cR, cG, area = details(P, N, info, 911)
    _apply(ob, h, cR, cG, area)
    return ob


def bake(lows, tubes, coll):
    t0 = time.time()
    highs = [tube_high(f, coll) for f in tubes]
    highs.append(caudal_high(coll))
    nt = 0
    for o in highs:
        o.data.calc_loop_triangles()
        nt += len(o.data.loop_triangles)
    print(f"fins high: {nt:,} tris, {time.time() - t0:.1f}s")
    t1 = time.time()
    # 高模和低模是同一个参数曲面（细节位移 ≤ 1 厘米），笼子收紧：鳍缘很薄，笼子太大射线会打到另一面
    # AO 距离：世界默认 10 米，薄鳍上 AO 会被远处的几何压暗一片；临时设成 0.8 米，烘完还原
    scn = bpy.context.scene
    made = scn.world is None
    if made:
        scn.world = bpy.data.worlds.new("_fins_bake_world")
    old = scn.world.light_settings.distance
    scn.world.light_settings.distance = 0.8
    try:
        bakeutil.bake_set("fins", lows, highs, extrusion=0.07, max_ray=0.22)
    finally:
        scn.world.light_settings.distance = old
        if made:
            w = scn.world
            scn.world = None
            bpy.data.worlds.remove(w)
    print(f"fins bake: {time.time() - t1:.1f}s")
    for o in highs:
        me = o.data
        bpy.data.objects.remove(o)
        bpy.data.meshes.remove(me)
