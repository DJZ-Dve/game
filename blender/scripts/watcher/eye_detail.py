"""眼的高模（只烘焙）：虹膜一块（平面点阵，6.5 毫米）+ 巩膜一圈（θ × φ 点阵，11 毫米），形体和低模同一套
eye_geo 剖面，细节沿眼轴（虹膜）/ 法线（巩膜）位移。

虹膜（按真眼睛的解剖放大五百倍：人眼 12 毫米的虹膜这里六米）：
  - 纤维（虹膜基质的小梁）：顺着椭圆坐标的 ν（从竖缝往外放射），两层（粗的 110 条、细的 330 条），各自蜿蜒、断断续续；
  - 领圈（collarette）：s ≈ 0.34 一圈锯齿状的厚棱，把瞳孔区和睫状区分开；瞳孔区纤维细、整体略鼓；
  - 隐窝（Fuchs 隐窝）：六十来个深坑（大多在领圈外侧，少数在中间和根部），坑壁陡，坑底更细的纤维，
    有几根粗纤维从坑上跨过去；
  - 收缩沟：睫状区外半三圈断断续续的同心深沟（外侧带一道唇）；
  - 瞳孔边缘一圈串珠状的小褶（pupillary ruff）；根部一圈放射的短突起，再往外是基础剖面里那圈沟（深色环）。
巩膜：大面缓慢起伏、湿组织的细起伏、从后往前（朝角膜缘）蜿蜒分叉的血管（半埋的管，主干 3.5～5.5 厘米粗），
  角膜缘附近一圈细的放射纹（Vogt 栅栏）和细小的毛细血管，两道愈合的旧伤疤（中间一道沟、两边隆起的瘢痕组织，
  血管在疤上断开）。
"Curv"：R（凹槽）= 隐窝、收缩沟、根部的沟、纤维之间的缝、疤中间的沟；
         G（凸棱）= 纤维的脊、领圈、瞳孔缘的褶、巩膜的血管（材质可以拿它当血管遮罩）、瘢痕组织。
"Area"：虹膜 1，根部那段坡上降到角膜缘的 0；巩膜 0。
"""
import math

import numpy as np

from watcher import spec
from watcher import eye_util as U
from watcher import eye_geo as G

IRIS_STEP = 0.0065
SCLERA_STEP = 0.011
SCLERA_TH_END = math.radians(92.0)


def _fix_winding(quads, verts, want):
    """看几个面的法线和期望方向（want(点) → 方向）对不对，整体反了就把四边形倒过来。"""
    k = np.linspace(0, len(quads) - 1, 200).astype(int)
    q = quads[k]
    n = np.cross(verts[q[:, 1]] - verts[q[:, 0]], verts[q[:, 2]] - verts[q[:, 0]])
    w = np.array([want(verts[i]) for i in q[:, 0]])
    if (np.sum(n * w, axis=1) < 0).mean() > 0.5:
        return quads[:, ::-1].copy()
    return quads


# ---------------------------------------------------------------------------- 虹膜
def _fiber_layer(nu_w, s, L, n, seed, wmin, wmax, offmax, gap_m, gap_lo, gap_hi):
    """一层放射纤维：返回 (0～1 的截面高度 × 断续, 每根的随机数)。"""
    t = (nu_w + np.pi) / (2 * np.pi) * n
    i = np.floor(t).astype(np.int64)
    f = t - i
    i = i % n
    amp = 0.5 + 0.5 * U.hash1(i, 0, seed)
    wid = wmin + (wmax - wmin) * U.hash1(i, 1, seed)
    off = (U.hash1(i, 2, seed) - 0.5) * 2 * offmax
    wid = wid * (0.65 + 0.7 * U.noise1(s * L / (gap_m * 0.7) + i * 7.71, seed + 6))
    d = (f - 0.5 - off) / wid
    prof = np.clip(1 - d * d, 0, None) ** 0.7
    cont = U.smoothstep(gap_lo, gap_hi, U.noise1(s * L / gap_m + i * 13.37, seed + 5))
    return amp * prof * cont, U.hash1(i, 3, seed)


def _crypts(rng, n_near, n_mid, n_far):
    """隐窝：[(x, y, 径向半长, 切向半宽, 深, 径向单位向量)]。"""
    out = []
    groups = ((n_near, (G.COLLARETTE_S + 0.03, G.COLLARETTE_S + 0.22), (0.14, 0.42), (0.06, 0.16), (0.06, 0.12)),
              (n_mid, (0.48, 0.82), (0.08, 0.22), (0.04, 0.09), (0.045, 0.08)),
              (n_far, (0.85, 0.95), (0.05, 0.11), (0.03, 0.06), (0.03, 0.05)))
    for cnt, (s0, s1), hl, hw, dp in groups:
        for _ in range(cnt):
            s = rng.uniform(s0, s1)
            nu = rng.uniform(-np.pi, np.pi)
            mu = G.MU_P + s * (float(G.mu_root(nu)) - G.MU_P)
            x, y = G.from_elliptic(mu, nu)
            er = np.array([G.FOC * math.cosh(mu) * math.sin(nu), G.FOC * math.sinh(mu) * math.cos(nu)])
            er /= np.linalg.norm(er) + 1e-12
            out.append((float(x), float(y), rng.uniform(*hl), rng.uniform(*hw), rng.uniform(*dp), er))
    return out


def iris_fields(X, Y, g):
    """X, Y：平面点阵（二维，indexing='ij'，坐标轴都是 g）。返回 (位移 h, 凹槽, 凸棱)，都是二维数组。"""
    rng = spec.rng_for("watcher_eye_iris")
    rho = np.hypot(X, Y)
    mu, nu = G.elliptic(X, Y)
    s = G.iris_s(mu, nu)
    L = G.fiber_len(nu)
    dm = s * L                                   # 离瞳孔边缘多少米（瞳孔里是负的）
    COL = G.COLLARETTE_S
    h = np.zeros_like(X)
    groove = np.zeros_like(X)
    ridge = np.zeros_like(X)
    # 大面的起伏
    h += 0.016 * U.fbm2(X * 0.7, Y * 0.7, 3, 11) + 0.004 * U.fbm2(X * 5, Y * 5, 2, 12)
    # 纤维：ν 加上蜿蜒
    warp = 0.08 * U.fbm2(X * 0.5, Y * 0.5, 3, 21) + 0.035 * U.fbm2(X * 1.6, Y * 1.6, 2, 22)
    warpb = 0.08 * U.fbm2(X * 0.5 + 9.3, Y * 0.5, 3, 24) + 0.035 * U.fbm2(X * 1.6, Y * 1.6 + 4.4, 2, 25)
    cil = U.smoothstep(COL + 0.02, COL + 0.12, s) * (1 - U.smoothstep(0.95, 1.01, s))     # 睫状区
    pup = (1 - U.smoothstep(COL - 0.05, COL + 0.03, s)) * U.smoothstep(0.005, 0.05, dm)   # 瞳孔区（不含瞳孔）
    fa, sel = _fiber_layer(nu + warp, s, L, 64, 31, 0.14, 0.28, 0.2, 0.8, 0.2, 0.42)
    fb, selb = _fiber_layer(nu + warpb, s, L, 86, 33, 0.12, 0.24, 0.2, 0.6, 0.3, 0.5)
    fm = np.maximum(fa, 0.8 * fb)
    sel = np.where(fa >= 0.8 * fb, sel, selb)
    warp2 = warp + 0.03 * U.fbm2(X * 1.3 + 5.1, Y * 1.3, 3, 23)
    ff, _ = _fiber_layer(nu + warp2, s, L, 300, 37, 0.22, 0.36, 0.14, 0.3, 0.35, 0.55)
    ff *= 0.5 + 0.5 * (U.fbm2(X * 2.5, Y * 2.5, 2, 26) * 0.5 + 0.5)
    fp, _ = _fiber_layer(nu + warp2 * 0.6, s, L, 200, 43, 0.25, 0.4, 0.1, 0.25, 0.3, 0.55)
    h_major = 0.045 * fm * cil
    h += h_major + 0.008 * ff * cil + 0.01 * fp * pup
    ridge += 0.65 * fm * cil + 0.2 * ff * cil + 0.3 * fp * pup
    groove += 0.22 * (1 - np.clip(fm + ff, 0, 1)) * cil
    # 根部一圈放射的短突起
    band = U.smoothstep(0.86, 0.92, s) * (1 - U.smoothstep(0.99, 1.04, s))
    fr, _ = _fiber_layer(nu + warp * 0.5, s, L, 72, 47, 0.2, 0.3, 0.15, 0.5, 0.25, 0.45)
    h += 0.02 * fr * band
    ridge += 0.35 * fr * band
    # 领圈：锯齿状的厚棱
    zig = np.abs(((nu * 17 / (2 * np.pi)) % 1.0) - 0.5) * 2 - 0.5
    s_col = COL + 0.035 * (U.noise1(nu * 2.2 + 1.3, 41) - 0.5) * 2 + 0.045 * zig * (0.4 + U.noise1(nu * 4 + 7, 42))
    dc = (s - s_col) * L
    lump = 0.7 + 0.6 * (U.fbm2(X * 5, Y * 5, 2, 44) * 0.5 + 0.5)
    col = np.exp(-(dc / 0.09) ** 2) * lump
    h += 0.065 * col
    ridge += 0.8 * col
    # 收缩沟：外半三圈，断断续续，外侧一道唇
    for k, sk in enumerate((0.6, 0.73, 0.85)):
        skn = sk + 0.025 * (U.noise1(nu * 3 + k * 5, 60 + k) - 0.5) * 2 + 0.012 * (U.noise1(nu * 14 + k, 65 + k) - 0.5) * 2
        dk = (s - skn) * L
        cont = U.smoothstep(0.3, 0.5, U.noise1(nu * 4.5 + k * 17, 70 + k))
        wk = 0.04 * (0.7 + 0.6 * U.noise1(nu * 9 + k * 3, 75 + k))
        g_ = 0.04 * cont * np.exp(-(dk / wk) ** 2)
        h += -g_ + 0.012 * cont * np.exp(-((dk - 1.6 * wk) / wk) ** 2)
        groove += np.clip(g_ / 0.03, 0, 1) * 0.55
    # 瞳孔边缘一圈串珠状的小褶
    beads = 0.35 + 0.65 * U.noise1(nu * 70, 51) * (0.6 + 0.4 * U.noise1(nu * 9, 52))
    ruff = np.exp(-((dm - 0.024) / 0.024) ** 2) * beads
    h += 0.026 * ruff
    ridge += 0.7 * ruff
    # 瞳孔里：平一点，只留很轻的起伏
    inpup = 1 - U.smoothstep(-0.02, 0.01, dm)
    h *= 1 - 0.7 * inpup
    # 隐窝
    cm = np.zeros_like(X)
    cfloor = np.zeros_like(X)
    for k, (cx, cy, hl, hw, dp, er) in enumerate(_crypts(rng, 26, 16, 14)):
        rad = hl * 1.35 + 0.03
        i0, i1 = np.searchsorted(g, cx - rad), np.searchsorted(g, cx + rad)
        j0, j1 = np.searchsorted(g, cy - rad), np.searchsorted(g, cy + rad)
        if i1 <= i0 or j1 <= j0:
            continue
        sx, sy = X[i0:i1, j0:j1] - cx, Y[i0:i1, j0:j1] - cy
        a = sx * er[0] + sy * er[1]
        b = -sx * er[1] + sy * er[0]
        q = np.sqrt((a / hl) ** 2 + (b / hw) ** 2)
        q *= 1 + 0.35 * U.fbm2(X[i0:i1, j0:j1] * 3.5 + k * 3.1, Y[i0:i1, j0:j1] * 3.5, 3, 80 + k)
        m = 1 - U.smoothstep(0.6, 1.0, q)
        fl = -dp * (1 - 0.45 * np.clip(q, 0, 1) ** 2)
        cm[i0:i1, j0:j1] = np.maximum(cm[i0:i1, j0:j1], m)
        cfloor[i0:i1, j0:j1] = np.minimum(cfloor[i0:i1, j0:j1], np.where(m > 0, fl, 0.0))
    hc = h * (1 - cm) + cm * (cfloor + 0.012 * ff + 0.006 * U.fbm2(X * 9, Y * 9, 2, 90))
    # 跨过隐窝的粗纤维（三成左右）
    bp = (fm * (sel > 0.62) * cil) ** 0.4
    bridge = 0.035 * bp - 0.09 * (1 - bp)
    h = np.maximum(hc, np.where(cm > 0.02, bridge, -1.0))
    groove = groove * (1 - cm) + cm * U.smoothstep(-0.012, -0.04, h)
    # 根部的沟（深色环）：按基础剖面
    groove += 0.75 * np.exp(-((rho - G.SULCUS_AT) / 0.07) ** 2)
    # 角膜缘那段坡上不要细节（和巩膜的高模在这里接上）
    fade = 1 - U.smoothstep(G.RHO_L - 0.08, G.RHO_L - 0.01, rho)
    return h * fade, np.clip(groove, 0, 1) * fade, np.clip(ridge, 0, 1) * fade


def iris_high():
    import bpy  # noqa
    lim = G.RHO_L + 0.012
    n = int(math.ceil(lim / IRIS_STEP))
    g = np.arange(-n, n + 1) * IRIS_STEP
    X, Y = np.meshgrid(g, g, indexing="ij")
    keep = np.hypot(X, Y) <= lim
    h, rg, gg = iris_fields(X, Y, g)
    # 角膜缘外那一圈（和巩膜高模重叠的几毫米）往里压一点，让巩膜高模在上面——不然两张面叠在一起，AO 一圈黑点
    z = G.iris_z(X, Y) + h - 0.004 * U.smoothstep(G.RHO_L - 0.002, G.RHO_L + 0.004, np.hypot(X, Y))
    P = G.plane_to_world(X[keep], Y[keep], z[keep])
    quads = U.grid_quads(keep)
    quads = _fix_winding(quads, P, lambda p: G.EZ)
    ob = U.raw_mesh("EyeIrisHigh", P, quads)
    U.set_point_color(ob, "Curv", np.stack([rg[keep], gg[keep], np.zeros(keep.sum())], axis=1))
    U.set_point_color(ob, "Area", G.iris_area(np.hypot(X[keep], Y[keep])))
    return ob


# ---------------------------------------------------------------------------- 巩膜
def _basis(p):
    e_ph = np.cross(G.EZ, p)
    e_ph /= np.linalg.norm(e_ph) + 1e-12
    e_th = np.cross(e_ph, p)
    return e_th, e_ph


def _theta(p):
    return math.acos(max(-1.0, min(1.0, float(np.dot(p, G.EZ)))))


def _walk(rng, p, a, r0, r1, length, step, steer, sd, th_stop):
    """在球面上走一根血管：a 是相对「朝角膜缘」的偏角；返回 (点 (n,3) 单位向量, 半径 (n,))。"""
    pts, rs = [p.copy()], [r0]
    n = max(2, int(length / step))
    for k in range(n):
        e_th, e_ph = _basis(p)
        d = math.cos(a) * (-e_th) + math.sin(a) * e_ph
        p = p + d * step / G.R
        p /= np.linalg.norm(p)
        a = a * steer + rng.normal(0, sd)
        pts.append(p.copy())
        rs.append(r0 + (r1 - r0) * (k + 1) / n)
        if _theta(p) < th_stop:
            break
    return np.array(pts), np.array(rs)


def vessels():
    rng = spec.rng_for("watcher_eye_vessels")
    out = []
    th_l = G.TH_L
    for i in range(30):
        th0 = math.radians(rng.uniform(84, 93))
        ph0 = 2 * np.pi * (i + rng.uniform(-0.35, 0.35)) / 30
        p = G.sphere_dir(th0, ph0)
        r0 = rng.uniform(0.035, 0.055)
        stop = th_l + math.radians(rng.uniform(2.0, 6.0))
        pts, rs = _walk(rng, p, rng.normal(0, 0.3), r0, r0 * 0.4, 5.5, 0.04, 0.94, 0.17, stop)
        out.append((pts, rs))
        # 分叉（再分一代）
        stack = [(pts, rs, 1)]
        while stack:
            pp, rr, gen = stack.pop()
            for k in range(3, len(pp) - 2):
                if rr[k] < 0.016 or rng.random() > 0.05 / gen:
                    continue
                cr = rr[k] * rng.uniform(0.45, 0.7)
                ca = rng.choice((-1, 1)) * rng.uniform(0.5, 1.1)
                cp, crs = _walk(rng, pp[k], ca, cr, cr * 0.5, rng.uniform(0.4, 1.6), 0.035, 0.98, 0.22, th_l + math.radians(1.5))
                out.append((cp, crs))
                if gen < 2:
                    stack.append((cp, crs, gen + 1))
    # 角膜缘附近的毛细血管
    for i in range(140):
        th0 = math.radians(rng.uniform(46.0, 60.0))
        p = G.sphere_dir(th0, rng.uniform(0, 2 * np.pi))
        r0 = rng.uniform(0.014, 0.022)
        out.append(_walk(rng, p, rng.uniform(-np.pi, np.pi), r0, r0 * 0.6, rng.uniform(0.15, 0.6), 0.025, 0.9, 0.4,
                         th_l + math.radians(1.2)))
    return out


SCARS = [  # (θ0, φ0, θ1, φ1, 弯（度）, 强度) —— 两道愈合的旧伤
    (56.0, 205.0, 80.0, 232.0, 4.0, 1.0),
    (61.0, -40.0, 70.0, -12.0, -2.5, 0.75),
]


def _seg_window(A, B, pad, th0, dth, nth, dph, ncol):
    """线段 AB（单位向量）周围 pad 米的点阵窗口：(行 slice, 列下标数组)；不在网格上返回 None。"""
    ta, tb = _theta(A), _theta(B)
    tmin, tmax = min(ta, tb) - pad / G.R, max(ta, tb) + pad / G.R
    r0 = max(0, int(math.floor((tmin - th0) / dth)))
    r1 = min(nth, int(math.ceil((tmax - th0) / dth)) + 1)
    if r1 <= r0:
        return None
    pa = math.atan2(float(np.dot(A, G.EY)), float(np.dot(A, G.EX)))
    pb = pa + ((math.atan2(float(np.dot(B, G.EY)), float(np.dot(B, G.EX))) - pa + np.pi) % (2 * np.pi) - np.pi)
    padp = pad / (G.R * max(math.sin(max(tmin, 0.2)), 0.2))
    c0 = int(math.floor((min(pa, pb) - padp) / dph))
    c1 = int(math.ceil((max(pa, pb) + padp) / dph)) + 1
    return slice(r0, r1), np.arange(c0, c1) % ncol


def sclera_fields(D, th, ph):
    """D：(行, 列, 3) 的球面方向。返回 (位移, 凹槽, 凸棱)。"""
    nth, ncol = D.shape[:2]
    dth = th[1] - th[0]
    dph = 2 * np.pi / ncol
    TH = np.broadcast_to(th[:, None], (nth, ncol))
    PH = np.broadcast_to(ph[None, :], (nth, ncol))
    P = (D * G.R).reshape(-1, 3)
    h = np.zeros((nth, ncol))
    groove = np.zeros((nth, ncol))
    ridge = np.zeros((nth, ncol))
    # 大面起伏 + 湿组织的细起伏
    h += (0.028 * (U.fbm3(P * 0.35, 3, 101) - 0.5) * 2 + 0.006 * (U.fbm3(P * 3.0, 2, 102) - 0.5) * 2
          + 0.0015 * (U.fbm3(P * 14.0, 2, 103) - 0.5) * 2).reshape(nth, ncol)
    # 血管
    hv = np.zeros((nth, ncol))
    vm = np.zeros((nth, ncol))
    nseg = 0
    for pts, rs in vessels():
        for k in range(len(pts) - 1):
            A, B = pts[k], pts[k + 1]
            ra, rb = rs[k], rs[k + 1]
            win = _seg_window(A, B, max(ra, rb, 0.022) + 0.012, th[0], dth, nth, dph, ncol)
            if win is None:
                continue
            rsl, cols = win
            Q = D[rsl][:, cols] * G.R
            a3, b3 = A * G.R, B * G.R
            ab = b3 - a3
            t = np.clip(((Q - a3) @ ab) / max(ab @ ab, 1e-12), 0, 1)
            dist = np.linalg.norm(Q - (a3 + t[..., None] * ab), axis=-1)
            rr = ra + (rb - ra) * t
            rw = np.maximum(rr, 0.022)          # 细血管也至少两三个网格宽（不然沿着网格出锯齿）
            tube = np.clip(1 - (dist / rw) ** 2, 0, 1)
            hv[rsl, cols] = np.maximum(hv[rsl, cols], 0.5 * rr * tube ** 1.5)
            vm[rsl, cols] = np.maximum(vm[rsl, cols], tube * (0.45 + 0.55 * np.minimum(1.0, rr / 0.04)))
            nseg += 1
    # 伤疤
    sd = np.full((nth, ncol), 1e3)
    st = np.zeros((nth, ncol))
    sk = np.zeros((nth, ncol))
    for si, (t0, p0, t1, p1, bow, strength) in enumerate(SCARS):
        n = 160
        tt = np.linspace(0, 1, n)
        wig = 0.6 * (U.noise1(tt * 9 + si * 3, 120 + si) - 0.5)
        ths = np.radians(t0 + (t1 - t0) * tt + wig)
        phs = np.radians(p0 + (p1 - p0) * tt + bow * np.sin(np.pi * tt))
        pts = G.sphere_dir(ths, phs)
        for k in range(n - 1):
            win = _seg_window(pts[k], pts[k + 1], 0.16, th[0], dth, nth, dph, ncol)
            if win is None:
                continue
            rsl, cols = win
            Q = D[rsl][:, cols] * G.R
            a3, b3 = pts[k] * G.R, pts[k + 1] * G.R
            ab = b3 - a3
            t = np.clip(((Q - a3) @ ab) / max(ab @ ab, 1e-12), 0, 1)
            dist = np.linalg.norm(Q - (a3 + t[..., None] * ab), axis=-1)
            closer = dist < sd[rsl, cols]
            sd[rsl, cols] = np.where(closer, dist, sd[rsl, cols])
            st[rsl, cols] = np.where(closer, (k + t) / (n - 1), st[rsl, cols])
            sk[rsl, cols] = np.where(closer, strength, sk[rsl, cols])
    taper = np.sin(np.pi * np.clip(st, 0, 1)) ** 0.4 * sk
    wob = 0.8 + 0.4 * U.noise1(st * 8 + sk * 5, 130)
    tissue = (1 - U.smoothstep(0.03, 0.11 * wob, sd)) * np.sqrt(np.clip(taper, 0, 1))
    lumps = 0.6 + 0.8 * U.fbm3(P * 9.0, 2, 131).reshape(nth, ncol)
    sgroove = 0.026 * taper * np.exp(-(sd / 0.02) ** 2) * (0.7 + 0.6 * U.noise1(st * 25 + sk, 132))
    hv *= 1 - 0.85 * tissue
    vm *= 1 - 0.85 * tissue
    h += hv + 0.018 * tissue * lumps - sgroove
    groove += np.clip(sgroove / 0.018, 0, 1) * 0.9
    ridge += vm + 0.35 * tissue
    # 角膜缘的放射细纹（Vogt 栅栏）
    band = U.smoothstep(G.TH_L + math.radians(0.3), G.TH_L + math.radians(0.9), TH) * \
        (1 - U.smoothstep(G.TH_L + math.radians(2.0), G.TH_L + math.radians(4.0), TH))
    pal = np.sin(PH * 180 + 6 * U.noise1(PH * 25, 140) + 3 * (TH - G.TH_L) / 0.05) * \
        U.smoothstep(0.35, 0.75, U.noise1(PH * 30 + 3, 141)) * (0.4 + 0.6 * U.noise1(PH * 90, 142))
    h += 0.004 * band * pal
    ridge += 0.25 * band * np.clip(pal, 0, 1)
    # 角膜缘处没有细节（和虹膜的高模接上）
    fade = U.smoothstep(G.TH_L + math.radians(0.25), G.TH_L + math.radians(1.0), TH)
    print(f"eye sclera: {nseg} vessel segments")
    return h * fade, np.clip(groove, 0, 1) * fade, np.clip(ridge, 0, 1) * fade


def sclera_high():
    nth = int(math.ceil((SCLERA_TH_END - G.TH_L) * G.R / SCLERA_STEP)) + 1
    th = np.linspace(G.TH_L, SCLERA_TH_END, nth)
    ncol = int(round(2 * np.pi * G.R / SCLERA_STEP))
    ph = 2 * np.pi * np.arange(ncol) / ncol
    D = G.sphere_dir(np.broadcast_to(th[:, None], (nth, ncol)), np.broadcast_to(ph[None, :], (nth, ncol)))
    h, rg, gg = sclera_fields(D, th, ph)
    P = (G.C + (G.R + h)[..., None] * D).reshape(-1, 3)
    i, j = np.meshgrid(np.arange(nth - 1), np.arange(ncol), indexing="ij")
    i, j = i.ravel(), j.ravel()
    j1 = (j + 1) % ncol
    quads = np.stack([i * ncol + j, i * ncol + j1, (i + 1) * ncol + j1, (i + 1) * ncol + j], axis=1)
    quads = _fix_winding(quads, P, lambda p: p - G.C)
    ob = U.raw_mesh("EyeScleraHigh", P, quads)
    n = len(P)
    U.set_point_color(ob, "Curv", np.stack([rg.ravel(), gg.ravel(), np.zeros(n)], axis=1))
    U.set_point_color(ob, "Area", np.zeros(n))
    return ob


def build_highs():
    return [iris_high(), sclera_high()]
