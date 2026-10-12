"""肉的高模（只用来烘焙）：同一套参数形体按 ×k 密度重新采样（低模的点是它的子集），再沿法线加细节，
烘进 flesh_normal / flesh_mask。

细节（克制：大面干净，重点在眼窝、眼睑、腹面）：
  - 关节膜：全身统一方向的横褶（顺着前后轴一道道，像龙虾腹节之间的膜），大小两级，强弱成片变化；
    稀疏的小疣粒、细血管纹的微微隆起；
  - 眼窝外圈：放射状的细褶（往眼睛收拢），唇尖上更密更细；口袋顶、口袋底、结膜很光滑（湿）；
  - 眼睑：外表面顺着睑缘的几道细褶，睑缘一圈细密的竖褶（垂直于睑缘），内表面光滑；
  - 虹吸口：外圈一圈圈环肌褶，口缘放射细褶，喉部光滑。
点色 "Curv"：R 凹槽、G 凸棱；"Area"：R = 眼睑内侧、结膜、口袋、虹吸口喉部这些最湿的肉 = 1。
"""
import math
import time

import bpy
import numpy as np

from giant import skin_np as snp
from watcher import bakeutil
from watcher import flesh_geo as fg
from watcher import flesh_mesh as fm

K_BODY = 18
K_LID = 16
K_SIPH = 8
# 高模整体沿法线往里收 4 厘米再烘：高模贴着或高过低模时，这版 Blender 的 AO 烘焙会成片发黑（实测），
# 收进去以后干净；法线、凹槽、区域图不受影响（细节是相对量）。射线范围跟着调（见 bake）。
SINK = 0.04
D = math.radians
ss = fg.smoothstep


class Nb:
    def __init__(self, e, n):
        self.a, self.b, self.n = e[:, 0], e[:, 1], n
        self.deg = np.maximum(np.bincount(self.a, minlength=n) + np.bincount(self.b, minlength=n), 1)

    def avg(self, x):
        return (np.bincount(self.a, weights=x[self.b], minlength=self.n) +
                np.bincount(self.b, weights=x[self.a], minlength=self.n)) / self.deg

    def blur(self, x, it):
        for _ in range(it):
            x = 0.5 * x + 0.5 * self.avg(x)
        return x


def pleat(u):
    """圆鼓的褶脊、窄的褶沟（均值约 0）。"""
    return np.abs(np.sin(math.pi * u)) - 0.63


def co_of(ob):
    n = len(ob.data.vertices)
    c = np.empty(n * 3, np.float32)
    ob.data.vertices.foreach_get("co", c)
    return c.reshape(-1, 3).astype(np.float64)


def warts(co, sel, cell, h, frac, seed):
    """稀疏的小疣粒：Worley 格子里只有 frac 比例的格子长一颗。"""
    out = np.zeros(len(co))
    if len(sel) == 0:
        return out
    f1, f2, rid = snp.voronoi(co[sel] / cell, seed=seed)
    keep = rid < frac
    dome = np.clip(1 - (f1 / 0.33) ** 2, 0, 1) ** 1.5
    out[sel] = h * dome * keep
    return out


def veins(co, sel, cell, h, seed):
    out = np.zeros(len(co))
    if len(sel) == 0:
        return out
    q = co[sel]
    w = q + 0.25 * cell * np.stack([snp.fbm(q / (cell * 1.3), 2, seed=seed + k) for k in range(3)], 1)
    f1, f2, _ = snp.voronoi(w / cell, seed=seed + 5)
    v = np.exp(-((f2 - f1) / 0.06) ** 2)
    m = ss(0.0, 0.35, snp.fbm(q / (cell * 3.0), 2, seed=seed + 9))   # 只有成片的几处有
    out[sel] = h * v * m
    return out


def finish(ob, h, area, nb, t0, name):
    """沿法线加细节，写 Curv、Area。"""
    co = co_of(ob)
    nor = fm.vertex_normals(ob)
    new = co + nor * (h - SINK)[:, None]
    fm.set_co(ob, new)
    hb = nb.blur(h, 5)
    cav = np.clip((hb - h) / 0.004, 0, 1)
    rid = np.clip((h - hb) / 0.004, 0, 1)
    lap = np.zeros(len(co))
    for k in range(3):
        lap += (nb.avg(new[:, k]) - new[:, k]) * nor[:, k]
    lap = nb.blur(lap, 3)
    cav = np.maximum(cav, np.clip((lap - 0.0003) / 0.0012, 0, 1))
    rid = np.maximum(rid, np.clip((-lap - 0.0003) / 0.0012, 0, 1))
    n = len(co)
    me = ob.data
    a = me.attributes.new("Curv", 'FLOAT_COLOR', 'POINT')
    a.data.foreach_set("color", np.stack([cav, rid, np.zeros(n), np.ones(n)], 1).astype(np.float32).ravel())
    a = me.attributes.new("Area", 'FLOAT_COLOR', 'POINT')
    area = np.clip(area, 0, 1)
    a.data.foreach_set("color", np.stack([area, area, area, np.ones(n)], 1).astype(np.float32).ravel())
    print(f"  {name}: {len(me.polygons):,} faces, {time.time() - t0:.1f}s")


# ---------------------------------------------------------------------------- 身体 + 眼窝
def body_high():
    t0 = time.time()
    ob, I = fm.body_mesh("FleshBodyHigh", K_BODY)
    co = co_of(ob)
    n = len(co)
    nb = Nb(fm.edges(ob), n)
    reg, seg, loc, be = I["reg"], I["seg"], I["loc"], I["be"]
    sp = np.where(seg < 0, -1.0, seg + loc)
    h = np.zeros(n)
    area = np.zeros(n)
    # 关节膜（身体 + 眼窝外圈靠甲缘那半）：横褶
    w_body = np.where(reg == fg.REG_BODY, 1.0, np.interp(sp, [0, 1.5, 3.0], [1.0, 0.7, 0.0]))
    sel = np.nonzero(w_body > 0.01)[0]
    q = co[sel]
    belly = 1.0 + 0.5 * ss(-0.3, -0.7, q[:, 2] / 7.2)
    m1 = 0.25 + 0.75 * ss(-0.35, 0.35, snp.fbm(q / 2.2, 2, seed=1))
    y = q[:, 1] + 0.10 * snp.fbm(q / 1.8, 2, seed=2) + 0.035 * snp.fbm(q / 0.5, 2, seed=3)
    h[sel] += 0.005 * m1 * belly * pleat(y / 0.095) * w_body[sel]
    m2 = 0.3 + 0.7 * ss(-0.3, 0.3, snp.fbm(q / 3.0, 2, seed=4))
    y2 = q[:, 1] + 0.35 * snp.fbm(q / 3.0, 2, seed=5)
    h[sel] += 0.011 * m2 * belly * pleat(y2 / 0.42) * w_body[sel]
    print(f"  body pleats {time.time() - t0:.1f}s")
    # 眼窝外圈 + 唇：放射细褶（往眼睛收）
    w_rad = np.interp(sp, [0, 1, 2, 3, 4, 5, 6], [0, 0.25, 0.7, 1.0, 1.0, 0.5, 0.0])
    w_rad = np.where(seg < 0, 0.0, w_rad)
    sel = np.nonzero(w_rad > 0.01)[0]
    q = co[sel]
    bw = be[sel] + 0.045 * snp.fbm(q / 1.1, 2, seed=6)
    u = bw * 84 / (2 * math.pi)
    amp = 0.4 + 0.6 * ss(-0.3, 0.3, snp.fbm(q / 1.4, 2, seed=7))
    fine = np.where(sp[sel] > 3.6, 0.6 * pleat(bw * 190 / (2 * math.pi) + 0.3 * snp.fbm(q / 0.6, 2, seed=8)), 0.0)
    h[sel] += (0.008 * amp * pleat(u) + 0.004 * fine) * w_rad[sel]
    # 眼窝外圈靠唇的一小圈同心细纹（被眼球转动挤出来的）
    con = np.exp(-((sp[sel] - 3.6) / 0.6) ** 2)
    h[sel] += 0.0025 * con * pleat(sp[sel] * 9 + 0.4 * snp.fbm(q / 0.8, 2, seed=9))
    print(f"  socket folds {time.time() - t0:.1f}s")
    # 疣粒、血管纹（只在外面那层）
    outer = np.nonzero((reg == fg.REG_BODY) | (sp < 3.5))[0]
    h += warts(co, outer, 0.11, 0.006, 0.10, 21)
    h += veins(co, outer, 0.6, 0.0022, 31)
    print(f"  warts/veins {time.time() - t0:.1f}s")
    # 口袋、结膜：很光滑，轻轻起伏
    wet = np.nonzero(sp >= 5)[0]
    h[wet] += 0.003 * snp.fbm(co[wet] / 0.7, 2, seed=11)
    area = np.where(seg < 0, 0.0, np.interp(sp, [0, 3, 4, 5, 6, 20], [0, 0, 0.25, 0.7, 1.0, 1.0]))
    finish(ob, h, area, nb, t0, "body high")
    return ob


# ---------------------------------------------------------------------------- 眼睑
def lid_high(lower):
    t0 = time.time()
    ob, I = fm.lid_mesh("FleshLidHigh" + ("Lo" if lower else "Up"), lower, K_LID)
    co = co_of(ob)
    n = len(co)
    nb = Nb(fm.edges(ob), n)
    part, dm, psi, gam = I["part"], I["dm"], I["psi"], I["gam"]
    h = np.zeros(n)
    seed = 40 + 10 * int(lower)
    adm = np.abs(dm)
    # 外表面：顺着睑缘的细褶（离缘越远越疏、越弱）
    sel = np.nonzero(part == 2)[0]
    q = co[sel]
    d = adm[sel]
    u = (d + 0.08 * snp.fbm(q / 1.3, 2, seed=seed)) / (0.16 + 0.07 * d)
    h[sel] += 0.011 * pleat(u) * ss(2.2, 0.25, d) * (0.5 + 0.5 * ss(-0.3, 0.3, snp.fbm(q / 1.8, 2, seed=seed + 1)))
    # 睑缘一圈竖褶（垂直于睑缘），外侧和卷边上
    sel = np.nonzero((part == 1) | ((part == 2) & (adm < 0.6)) | ((part == 0) & (adm < 0.3)))[0]
    q = co[sel]
    a = psi[sel] * 5.3 + 0.05 * snp.fbm(q / 0.7, 2, seed=seed + 2)
    env = np.exp(-(adm[sel] / 0.32) ** 2)
    h[sel] += 0.007 * pleat(a / 0.13) * env
    # 外表面的疣粒，内表面很淡的褶
    h += warts(co, np.nonzero(part == 2)[0], 0.10, 0.005, 0.08, seed + 3)
    sel = np.nonzero(part == 0)[0]
    h[sel] += 0.0018 * pleat((adm[sel] + 0.1 * snp.fbm(co[sel] / 1.0, 2, seed=seed + 4)) / 0.2)
    area = np.select([part == 0, part == 1, part == 3, part == 4],
                     [1.0, np.clip(0.55 - 0.45 * np.sin(gam), 0, 1), 1.0, 0.6],
                     0.12 * np.exp(-adm / 0.35))
    finish(ob, h, area, nb, t0, "lid high " + ("lo" if lower else "up"))
    return ob


# ---------------------------------------------------------------------------- 虹吸口
def siphon_high():
    t0 = time.time()
    ob, I = fm.siphon_mesh("FleshSiphonHigh", K_SIPH, k_pap=3)
    co = co_of(ob)
    n = len(co)
    nb = Nb(fm.edges(ob), n)
    reg, r, hh = I["reg"], I["r"], I["h"]
    h = np.zeros(n)
    sel = np.nonzero(reg == 0)[0]
    q = co[sel]
    h[sel] += 0.0045 * pleat((r[sel] + 0.05 * snp.fbm(q / 0.35, 2, seed=61)) / 0.075) * ss(1.65, 1.4, r[sel] / 1.1)
    s0, sx, sy, sn = I["S"]["frame"]
    sel = np.nonzero(reg == 1)[0]
    rel = co[sel] - s0
    ang = np.arctan2(rel @ sy, rel @ sx)
    h[sel] += 0.004 * pleat(ang * 56 / (2 * math.pi) + 0.2 * snp.fbm(co[sel] / 0.4, 2, seed=62))
    area = np.select([reg == 2, reg == 1, reg == 3], [1.0, 0.6, 0.4], 0.0)
    area = np.where((reg == 1) & (hh < 0.36), 0.85, area)
    finish(ob, h, area, nb, t0, "siphon high")
    return ob


def bake(lows):
    t0 = time.time()
    highs = [body_high(), lid_high(False), lid_high(True), siphon_high()]
    print(f"flesh high: {sum(len(h.data.polygons) for h in highs):,} faces, {time.time() - t0:.1f}s")
    bakeutil.bake_set("flesh", lows, highs, extrusion=0.02, max_ray=0.12, ao_distance=0.8)
    for h in highs:
        if h.name in bpy.data.objects:
            me = h.data
            bpy.data.objects.remove(h)
            bpy.data.meshes.remove(me)
    print(f"flesh bake total {time.time() - t0:.1f}s")
