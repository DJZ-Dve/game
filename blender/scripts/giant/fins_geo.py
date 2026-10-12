"""鳍的几何底子（fins.py 用）：身体曲面的向量化版本、鳍的平面轮廓、管状鳍（胸/腹/背鳍）和尾鳍（枕头式）的网格生成。

两种做法：
  - 管状鳍（胸鳍、腹鳍、背鳍）：沿「离体表的高度」一排排翼型截面（前缘圆厚、后缘薄），根部往下接一圈圆角（fillet）
    和一道肉褶（凸起的唇，外沿往下钻进皮里 5 厘米），最底下一排压扁成一条线把管口封死（在皮里面，看不见）；
    根部的截面点沿鳍的展向往身体上「投射」（按 spec 的超椭圆截面二分求交），所以根部严丝合缝贴着曲面；
    离体表越高越过渡成平的鳍面。
  - 尾鳍：矢状面上的二维轮廓（上叶、末端缺刻、尾叉、下叶），里面撒三角形格点做约束 Delaunay 三角化，
    左右两面按厚度场鼓起来（中间那排边界点两面共用，鳍缘是一条薄边）；厚度场 = 脊柱轴（伸进上叶的那根）
    + 下叶前缘的软骨 + 膜，再和尾柄末端的身体「光滑取大」，所以尾鳍根部包住尾柄末端、和皮之间是一道很缓的过渡。
所有函数用 numpy 向量化，高模（几十万点）也能几秒算完。
"""
import math

import bpy
import numpy as np
from mathutils import geometry

from giant import spec

# ---------------------------------------------------------------------------- 身体曲面（向量化，和 spec 的算法一致）
_P = spec._PROFILE
_SL = [np.asarray(m) for m in spec._SLOPES]


def section_v(s):
    """spec.section 的向量化版本：返回 (半宽, 背高, 腹深, 中轴 z, 指数) 五个数组。"""
    s = np.clip(np.asarray(s, dtype=np.float64), 0.0, 1.0)
    xs = _P[:, 0]
    i = np.clip(np.searchsorted(xs, s, side="right") - 1, 0, len(xs) - 2)
    h = xs[i + 1] - xs[i]
    t = (s - xs[i]) / h
    h00, h10, h01, h11 = 2 * t**3 - 3 * t**2 + 1, t**3 - 2 * t**2 + t, -2 * t**3 + 3 * t**2, t**3 - t**2
    out = []
    for c in range(1, 6):
        ys, m = _P[:, c], _SL[c]
        out.append(h00 * ys[i] + h10 * h * m[i] + h01 * ys[i + 1] + h11 * h * m[i + 1])
    return out


def body_f(p):
    """体表的「超椭圆半径 − 1」：< 0 在身体里，> 0 在外面（尾尖之后、吻端之前一律算外面）。"""
    p = np.asarray(p, dtype=np.float64)
    s = (spec.HALF - p[:, 1]) / spec.LENGTH
    hw, ht, hb, zc, e = section_v(s)
    dz = p[:, 2] - zc
    h = np.where(dz >= 0, ht, hb)
    u = np.abs(p[:, 0]) / hw
    v = np.abs(dz) / h
    r = (u**e + v**e) ** (1.0 / e)
    f = r - 1.0
    out = (s < 0.0) | (s > 1.0)
    return np.where(out, np.maximum(f, 0.5), f)


def raycast_body(p0, d, lo=-4.0, hi=4.0, it=40):
    """从 p0 沿 d 方向（单位向量）找体表：返回 λ（p0 + λ d 在体表上）；够不着身体的点返回 0。"""
    p0 = np.asarray(p0, dtype=np.float64)
    d = np.asarray(d, dtype=np.float64)
    a = np.full(len(p0), lo)
    b = np.full(len(p0), hi)
    fa = body_f(p0 + a[:, None] * d)
    ok = fa < 0.0
    for _ in range(it):
        m = 0.5 * (a + b)
        fm = body_f(p0 + m[:, None] * d)
        inside = fm < 0.0
        a = np.where(inside, m, a)
        b = np.where(inside, b, m)
    return np.where(ok, 0.5 * (a + b), 0.0)


def smoothstep(a, b, x):
    t = np.clip((np.asarray(x, dtype=np.float64) - a) / (b - a), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


# ---------------------------------------------------------------------------- 平面轮廓
def catmull_np(pts, samples=24, closed=False):
    """向心 Catmull-Rom（不会在控制点稀疏处甩出去）。pts: (n, 2)。"""
    P = np.asarray(pts, dtype=np.float64)
    n = len(P)
    if closed:
        ext = np.vstack([P[-1], P, P[0], P[1]])
    else:
        ext = np.vstack([2 * P[0] - P[1], P, 2 * P[-1] - P[-2]])
    segs = n if closed else n - 1
    out = []
    for i in range(segs):
        p0, p1, p2, p3 = ext[i], ext[i + 1], ext[i + 2], ext[i + 3]
        t0 = 0.0
        t1 = t0 + max(np.linalg.norm(p1 - p0), 1e-6) ** 0.5
        t2 = t1 + max(np.linalg.norm(p2 - p1), 1e-6) ** 0.5
        t3 = t2 + max(np.linalg.norm(p3 - p2), 1e-6) ** 0.5
        for k in range(samples):
            t = t1 + (t2 - t1) * k / samples
            a1 = (t1 - t) / (t1 - t0) * p0 + (t - t0) / (t1 - t0) * p1
            a2 = (t2 - t) / (t2 - t1) * p1 + (t - t1) / (t2 - t1) * p2
            a3 = (t3 - t) / (t3 - t2) * p2 + (t - t2) / (t3 - t2) * p3
            b1 = (t2 - t) / (t2 - t0) * a1 + (t - t0) / (t2 - t0) * a2
            b2 = (t3 - t) / (t3 - t1) * a2 + (t - t1) / (t3 - t1) * a3
            out.append((t2 - t) / (t2 - t1) * b1 + (t - t1) / (t2 - t1) * b2)
    if not closed:
        out.append(P[-1])
    return np.array(out)


def notch_shape(u, skew=0.0):
    """缺口的形状：u ∈ [-1, 1]，中间最深，两边光滑收到 0；skew 让一边陡一边缓（愈合的撕口不对称）。"""
    u = np.asarray(u, dtype=np.float64)
    u = np.where(u < 0, u * (1.0 + skew), u * (1.0 - skew))
    return np.where(np.abs(u) < 1.0, (1.0 - u * u) ** 2, 0.0)


class Planform:
    """管状鳍的平面轮廓（c 沿弦向、朝前为正；h 离体表的高度）。
    pts 从根部前缘 (c, 0) 往上经过鳍梢，再沿后缘下来到根部后缘 (c, 0)。
    notches: [(h0, 半宽, 深度, skew)]，后缘往前缺进去（愈合的旧撕口）。"""

    def __init__(self, pts, notches=(), grow=0.0):
        self.pts = pts
        d = catmull_np(pts, samples=40)
        if grow:
            # 往外扩一圈（高模用：比低模大一点，烘焙时低模鳍缘的射线才都打得到高模，不会漏成黑边）
            n = np.roll(d, -1, axis=0) - np.roll(d, 1, axis=0)
            n[0], n[-1] = d[1] - d[0], d[-1] - d[-2]
            n = np.stack([n[:, 1], -n[:, 0]], axis=1)
            n /= np.linalg.norm(n, axis=1)[:, None] + 1e-12
            if n[len(n) // 2, 1] < 0:
                n = -n
            # 只扩后缘（缺口都在后缘上）；梢和前缘不扩，不然低模的梢比高模小一圈，法线烘出一个圈
            k = int(np.argmax(d[:, 1]))
            idx = np.arange(len(d))
            w = smoothstep(0.0, 0.12 * len(d), idx - k) * smoothstep(0.0, 0.4, d[:, 1])
            d = d + n * grow * w[:, None]
        k = int(np.argmax(d[:, 1]))
        self.H = float(d[k, 1])
        le, te = d[:k + 1], d[k:][::-1]
        self._le_h = np.maximum.accumulate(le[:, 1])
        self._le_c = le[:, 0]
        self._te_h = np.maximum.accumulate(te[:, 1])
        self._te_c = te[:, 0]
        self.notches = list(notches)
        self.outline = d

    def le(self, h):
        return np.interp(h, self._le_h, self._le_c)

    def te(self, h, notched=True):
        c = np.interp(h, self._te_h, self._te_c)
        if notched:
            for h0, hw, depth, skew in self.notches:
                c = c + depth * notch_shape((np.asarray(h) - h0) / hw, skew)
        return c


def naca(x):
    """对称翼型的厚度分布（NACA 00xx，后缘闭合），归一到最大值 1（在 x ≈ 0.3）。"""
    x = np.clip(x, 0.0, 1.0)
    return (0.2969 * np.sqrt(x) - 0.1260 * x - 0.3516 * x**2 + 0.2843 * x**3 - 0.1036 * x**4) / 0.1


# ---------------------------------------------------------------------------- 管状鳍
class TubeFin:
    """O：根部中心（体表上）；C：弦向（朝前）；D：展向；T = C × D（朝上）。thk(h)：全厚度（米）；
    camber：弯度（弦长的比例，往 T 方向鼓）；R：根部圆角半径；flat_h：多高以上鳍面不再跟着身体曲面弯。"""

    def __init__(self, name, O, C, D, planform, thk, R, flat_h, camber=0.0, skirt=0.18):
        C = np.asarray(C, dtype=np.float64)
        D = np.asarray(D, dtype=np.float64)
        D = D - C * D.dot(C)
        D /= np.linalg.norm(D)
        T = np.cross(C, D)
        if T[2] < -1e-6:
            T = -T
        self.name, self.O, self.C, self.D, self.T = name, np.asarray(O, dtype=np.float64), C, D, T
        self.pf, self.thk, self.R, self.flat_h, self.camber, self.skirt = planform, thk, R, flat_h, camber, skirt

    # 一排的描述：(hs 平面轮廓取哪个高度, off 截面往外扩多少, hgt 离体表多高, tsc 厚度倍数 0 = 压扁成线)
    def root_rows(self, n_fillet=4, n_skirt=2, dense=False):
        R, sk = self.R, self.skirt
        rows = [(0.0, R + sk + 0.06, -0.32, 0.0)]          # 最底：压扁封口（在皮下 0.3 米）
        if dense:
            for t in np.linspace(0.0, 1.0, n_skirt, endpoint=False):
                rows.append((0.0, R + sk + 0.06 - 0.06 * t, -0.32 + 0.27 * t, 1.0))
        # 肉褶外沿：以 15° 左右的缓坡从皮下 4 厘米冒出来，接到圆角的脚上（圆角脚离皮 1 厘米、和皮几乎相切）
        lip = [(R + sk, -0.045), (R + sk * 0.62, -0.006), (R + sk * 0.3, 0.008)]
        if dense:
            xs = np.linspace(0, 1, 7)
            lc = np.array([list(p) for p in lip] + [[R, 0.012]])
            tt = np.linspace(0, 1, len(lc))
            lip = list(zip(np.interp(xs, tt, lc[:, 0]), np.interp(xs, tt, lc[:, 1])))[:-1]
        for off, hg in lip:
            rows.append((0.0, off, hg, 1.0))
        # 圆角：从和皮相切到竖直的鳍面；下半段略鼓（根部的肌肉）
        for ph in np.linspace(0.0, math.pi / 2, n_fillet + 1):
            off = R * (1.0 - math.sin(ph))
            hg = 0.012 + R * (1.0 - math.cos(ph)) + 0.06 * R * math.sin(2 * ph)
            rows.append((max(hg - 0.012, 0.0), off, hg, 1.0))
        return rows

    def span_rows(self, n, extra=(), ntip=4):
        """圆角以上到鳍梢的各排：大体均匀，靠近鳍梢加密（梢是圆的），缺口附近加几排（缺口才看得出来）。"""
        h0 = 0.012 + self.R
        H = self.pf.H
        # 主体到离梢 tip 米，梢上再按平方收（弦长 ∝ √(H − h)，这样梢的圆头每排差不多一样宽）
        tip = min(0.3 * (H - h0), 0.9)
        k = np.linspace(0.0, 1.0, max(n - ntip + 2, 3))[1:]
        hs = list(h0 + (H - tip - h0) * (0.5 * k + 0.5 * np.sin(k * math.pi / 2)))
        qs = (0.62, 0.36, 0.16, 0.05) if ntip <= 4 else np.linspace(0.66, 0.03, ntip)
        tips = [H - tip * q * q for q in qs]
        must = [h for h in extra if h0 + 0.05 < h < tips[0] - 0.05]
        gap = 0.45 * (H - h0) / n
        out = sorted(must + [h for h in hs if all(abs(h - m) > gap for m in must)])
        out += tips
        return [(h, 0.0, h, 0.0 if i == len(out) - 1 else 1.0) for i, h in enumerate(out)]

    def notch_rows(self, per=5):
        hs = []
        for h0, hw, depth, skew in self.pf.notches:
            for u in np.linspace(-1.0, 1.0, per):
                hs.append(h0 + hw * u)
        return hs

    def build(self, rows, M):
        """返回 dict：P (nr, M, 3) 顶点，及每个点的弦向位置 x、哪一面 sg、离体表高度 hgt、局部全厚度 thick、弦长 chord、
        hs（平面轮廓高度）、c（弦向坐标，米）。"""
        a = np.arange(M) * 2.0 / M
        x = 0.5 * (1.0 - np.cos(math.pi * a))
        sg = np.where(a < 1.0, 1.0, -1.0)
        f = naca(x)
        nr = len(rows)
        P = np.zeros((nr, M, 3))
        X = np.zeros((nr, M))
        HG = np.zeros((nr, M))
        TH = np.zeros((nr, M))
        CH = np.zeros((nr, M))
        HS = np.zeros((nr, M))
        CC = np.zeros((nr, M))
        OF = np.zeros((nr, M))
        for r, (hs, off, hgt, tsc) in enumerate(rows):
            le = float(self.pf.le(hs))
            te0 = float(self.pf.te(hs, notched=False))
            dn = float(self.pf.te(hs)) - te0          # 缺口：只把后半截往前收，前面的厚度分布不动
            chord = max(le - te0, 1e-3)
            c = le - x * chord + dn * smoothstep(0.45, 1.0, x)
            half = 0.5 * float(self.thk(hs)) * f
            cam = self.camber * chord * 4.0 * x * (1.0 - x)
            t = sg * half + cam
            if off > 0.0:
                n = _loop_normals(c, t)
                c = c + off * n[:, 0]
                t = t + off * n[:, 1]
            t = t * tsc if tsc < 1.0 else t
            base = self.O + np.outer(c, self.C) + np.outer(t, self.T)
            lam = raycast_body(base, self.D)
            w = float(smoothstep(0.0, self.flat_h, hgt))
            P[r] = base + np.outer(hgt + (1.0 - w) * lam, self.D)
            X[r], HG[r], TH[r], CH[r], HS[r], CC[r], OF[r] = x, hgt, 2 * half * tsc + 2 * off, chord, hs, c, off
        return dict(P=P, x=X, sg=np.broadcast_to(sg, (nr, M)).copy(), hgt=HG, thick=TH, chord=CH, hs=HS, c=CC, off=OF,
                    collapsed=np.array([r[3] == 0.0 for r in rows]), M=M)


def _loop_normals(c, t, smooth=3):
    """闭合截面上每点往外的法线（二维），磨圆后缘的尖角。"""
    p = np.stack([c, t], axis=1)
    d = np.roll(p, -1, axis=0) - np.roll(p, 1, axis=0)
    n = np.stack([d[:, 1], -d[:, 0]], axis=1)
    n /= np.linalg.norm(n, axis=1)[:, None] + 1e-12
    cen = p.mean(axis=0)
    flip = ((p - cen) * n).sum(axis=1) < 0
    n[flip] *= -1
    for _ in range(smooth):
        n = 0.5 * n + 0.25 * (np.roll(n, 1, axis=0) + np.roll(n, -1, axis=0))
        n /= np.linalg.norm(n, axis=1)[:, None] + 1e-12
    return n


def tube_topology(g):
    """管状鳍的面和合并：压扁的那几排（封口、鳍梢）上下两面的点合成一个。返回 (verts, faces, vid(nr,M))。"""
    P, M = g["P"], g["M"]
    nr = P.shape[0]
    vid = np.arange(nr * M).reshape(nr, M)
    j = np.arange(M)
    jm = np.minimum(j, (M - j) % M)
    for r in range(nr):
        if g["collapsed"][r]:
            vid[r] = r * M + jm
    used, inv = np.unique(vid.ravel(), return_inverse=True)
    vid = inv.reshape(nr, M)
    verts = P.reshape(-1, 3)[used]
    r0 = np.arange(nr - 1)[:, None]
    j0 = j[None, :]
    j1 = (j0 + 1) % M
    faces = np.stack([vid[r0, j0], vid[r0, j1], vid[r0 + 1, j1], vid[r0 + 1, j0]], axis=-1).reshape(-1, 4)
    return verts, faces, used


def tube_uv(g):
    """UV0（米）：u = 沿截面离前缘的弧长（上面为正、下面为负，后缘切开），v = 沿展向累计的长度。每个面角一个。"""
    P, M = g["P"], g["M"]
    nr = P.shape[0]
    seg = np.linalg.norm(np.roll(P, -1, axis=1) - P, axis=2)  # j → j+1
    half = M // 2
    u_top = np.concatenate([np.zeros((nr, 1)), np.cumsum(seg[:, :half], axis=1)], axis=1)  # j = 0..half
    u_bot = -np.cumsum(seg[:, half:][:, ::-1], axis=1)[:, ::-1]  # j = half..M-1：往后到 LE 的弧长（负）
    u_bot = np.concatenate([u_bot, np.zeros((nr, 1))], axis=1)  # j = half..M（M ≡ LE）
    dv = np.linalg.norm(P[1:] - P[:-1], axis=2)
    v = np.concatenate([np.zeros((1, M)), np.cumsum(dv, axis=0)], axis=0)
    uvs = []
    for r in range(nr - 1):
        for jj in range(M):
            j1 = jj + 1
            if jj < half:
                uu = (u_top[r, jj], u_top[r, j1], u_top[r + 1, j1], u_top[r + 1, jj])
            else:
                uu = (u_bot[r, jj - half], u_bot[r, j1 - half], u_bot[r + 1, j1 - half], u_bot[r + 1, jj - half])
            j1m = j1 % M
            vv = (v[r, jj], v[r, j1m], v[r + 1, j1m], v[r + 1, jj])
            uvs.append(list(zip(uu, vv)))
    return np.array(uvs).reshape(-1, 2)


# ---------------------------------------------------------------------------- 尾鳍（矢状面上的枕头）
def polyline_dist(pts, poly, closed=True, chunk=20000):
    """点到折线的距离和最近点在折线上的弧长参数（0～1）。pts (n,2)，poly (m,2)。"""
    A = poly
    B = np.roll(poly, -1, axis=0) if closed else poly[1:]
    if not closed:
        A = poly[:-1]
    AB = B - A
    L = np.linalg.norm(AB, axis=1)
    cum = np.concatenate([[0.0], np.cumsum(L)])
    tot = cum[-1]
    dist = np.empty(len(pts))
    par = np.empty(len(pts))
    for s in range(0, len(pts), chunk):
        p = pts[s:s + chunk]
        AP = p[:, None, :] - A[None, :, :]
        t = np.clip((AP * AB[None]).sum(-1) / (L[None] ** 2 + 1e-12), 0.0, 1.0)
        q = A[None] + t[..., None] * AB[None]
        d = np.linalg.norm(p[:, None, :] - q, axis=-1)
        k = np.argmin(d, axis=1)
        dist[s:s + chunk] = d[np.arange(len(p)), k]
        par[s:s + chunk] = (cum[k] + t[np.arange(len(p)), k] * L[k]) / tot
    return dist, par


def inside_poly(pts, poly, chunk=20000):
    """点在闭合多边形里（射线奇偶）。"""
    A = poly
    B = np.roll(poly, -1, axis=0)
    res = np.empty(len(pts), dtype=bool)
    for s in range(0, len(pts), chunk):
        p = pts[s:s + chunk]
        x, y = p[:, 0:1], p[:, 1:2]
        c1 = (A[None, :, 1] > y) != (B[None, :, 1] > y)
        xi = A[None, :, 0] + (y - A[None, :, 1]) * (B[None, :, 0] - A[None, :, 0]) / (B[None, :, 1] - A[None, :, 1] + 1e-12)
        res[s:s + chunk] = (np.sum(c1 & (x < xi), axis=1) % 2) == 1
    return res


def resample(poly, spacing, closed=True):
    """按弧长等距重采样（保留形状）。"""
    P = np.vstack([poly, poly[:1]]) if closed else poly
    L = np.linalg.norm(np.diff(P, axis=0), axis=1)
    cum = np.concatenate([[0.0], np.cumsum(L)])
    n = max(int(round(cum[-1] / spacing)), 8)
    t = np.linspace(0.0, cum[-1], n, endpoint=not closed)
    return np.stack([np.interp(t, cum, P[:, 0]), np.interp(t, cum, P[:, 1])], axis=1)


def sheet_mesh2d(outline, spacing, extra_pts=None, rings=(0.3, 0.75)):
    """二维轮廓里铺点做约束 Delaunay 三角化：轮廓上等距一圈、往里平行偏移几圈（鳍缘一条条整齐的带子，
    不然鳍缘一排三角形一大一小、看着像锯齿），再往里是三角形格点（行沿第一个坐标）。
    返回 (pts (n,2), tris (m,3), nb 边界点数)；前 nb 个点是轮廓上的点（按顺序）。"""
    bnd = resample(outline, spacing * 0.8)
    lo, hi = outline.min(axis=0), outline.max(axis=0)
    dy = spacing * math.sqrt(3) / 2
    rows = np.arange(lo[1] - dy, hi[1] + dy, dy)
    cand = []
    for i, z in enumerate(rows):
        xs = np.arange(lo[0] - spacing, hi[0] + spacing, spacing) + (spacing * 0.5 if i % 2 else 0.0)
        cand.append(np.stack([xs, np.full_like(xs, z)], axis=1))
    cand = np.vstack(cand)
    keep = inside_poly(cand, bnd)
    cand = cand[keep]
    d, _ = polyline_dist(cand, bnd)
    inner = (max(rings) + 0.55) * spacing if rings else 0.5 * spacing
    cand = cand[d > inner]
    if extra_pts is not None and len(extra_pts):
        e = extra_pts[inside_poly(extra_pts, bnd)]
        de, _ = polyline_dist(e, bnd)
        e = e[de > inner]
        # 额外点附近的格点去掉（不要挤在一起）
        if len(e):
            dd = np.min(np.linalg.norm(cand[:, None, :] - e[None, :, :], axis=-1), axis=1)
            cand = np.vstack([cand[dd > spacing * 0.6], e])
    # 平行偏移的圈：顺时针轮廓，右手法线朝外 → 往里是左手
    nrm = np.roll(bnd, -1, axis=0) - np.roll(bnd, 1, axis=0)
    nrm = np.stack([-nrm[:, 1], nrm[:, 0]], axis=1)
    nrm /= np.linalg.norm(nrm, axis=1)[:, None] + 1e-12
    if not inside_poly(bnd[:1] + nrm[:1] * spacing * 0.05, bnd)[0]:
        nrm = -nrm
    ring_pts = []
    for k, off in enumerate(rings):
        q = bnd + nrm * off * spacing
        if k % 2:
            q = 0.5 * (q + np.roll(q, -1, axis=0))   # 隔圈错开半格，三角形才匀
        ok = inside_poly(q, bnd)
        dq, _ = polyline_dist(q, bnd)
        ok &= dq > off * spacing * 0.8
        ring_pts.append(q[ok])
    if ring_pts:
        cand = np.vstack(ring_pts + [cand])
    pts = np.vstack([bnd, cand])
    nb = len(bnd)
    edges = [(i, (i + 1) % nb) for i in range(nb)]
    out = geometry.delaunay_2d_cdt([tuple(p) for p in pts], edges, [], 1, 1e-7, True)
    vco, _, faces, orig_v = out[0], out[1], out[2], out[3]
    # 输出顶点顺序可能变：按 orig 映射回来（新插入的点不应出现）
    m = np.full(len(vco), -1)
    for k, ov in enumerate(orig_v):
        if ov:
            m[k] = ov[0]
    tris = []
    for f in faces:
        idx = [m[k] for k in f]
        if min(idx) < 0:
            raise RuntimeError("delaunay 插了新点")
        if len(idx) == 3:
            tris.append(idx)
        else:
            for q in range(1, len(idx) - 1):
                tris.append([idx[0], idx[q], idx[q + 1]])
    tris = np.array(tris)
    # 只要轮廓里面的三角形
    cen = pts[tris].mean(axis=1)
    tris = tris[inside_poly(cen, bnd)]
    # 去掉孤立点（被约束吃掉的格点）
    used = np.zeros(len(pts), dtype=bool)
    used[tris.ravel()] = True
    used[:nb] = True
    remap = np.cumsum(used) - 1
    pts = pts[used]
    tris = remap[tris]
    # 统一朝向：二维逆时针
    a = pts[tris[:, 1]] - pts[tris[:, 0]]
    b = pts[tris[:, 2]] - pts[tris[:, 0]]
    cw = (a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0]) < 0
    tris[cw] = tris[cw][:, ::-1]
    return pts, tris, nb


def make_mesh(name, coll, verts, faces, mat, uv=None, smooth=True, sharp=None):
    """numpy → 网格（快）。faces：(n,3) 或 (n,4) 或 list；uv：每个面角一个 (nloops, 2)。"""
    me = bpy.data.meshes.new(name)
    if isinstance(faces, np.ndarray):
        nf, k = faces.shape
        sizes = np.full(nf, k)
        flat = faces.ravel()
    else:
        sizes = np.array([len(f) for f in faces])
        flat = np.concatenate([np.asarray(f) for f in faces])
    starts = np.concatenate([[0], np.cumsum(sizes)[:-1]])
    me.vertices.add(len(verts))
    me.vertices.foreach_set("co", np.asarray(verts, dtype=np.float32).ravel())
    me.loops.add(len(flat))
    me.loops.foreach_set("vertex_index", flat.astype(np.int32))
    me.polygons.add(len(sizes))
    me.polygons.foreach_set("loop_start", starts.astype(np.int32))
    me.update(calc_edges=True)
    if uv is not None:
        lay = me.uv_layers.new(name=spec.UV_MAIN)
        lay.data.foreach_set("uv", np.asarray(uv, dtype=np.float32).ravel())
    if mat is not None:
        me.materials.append(mat)
    if smooth:
        me.polygons.foreach_set("use_smooth", np.ones(len(sizes), dtype=bool))
        if sharp:
            # 鳍缘（后缘、尾鳍边、压扁的梢）上下两面夹角很大：标成硬边，法线不在鳍缘上平均成「朝外平躺」，
            # 不然低模鳍缘一整条带子的法线都是歪的，法线贴图只能用很饱和的颜色去拧回来（烘出来一圈彩边）
            me.set_sharp_from_angle(angle=math.radians(sharp))
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    return ob
