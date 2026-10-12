"""甲上的尖刺：长在甲片中棱靠后缘的地方，往后倒、刺身往后弯；根部从甲里长出来（贴着甲面的加厚基座），
刺身五道纵棱，尖端磨圆。排成几条纵列：背中线最长（3～5 米），背侧一对、体侧一对中等，腹面没有；
不是每片都有（左右各自随机缺几根），有一根断了半截。"""
import math

import numpy as np

from watcher import shell_np as snp

NLOW = 10        # 低模一圈 10 个点（5 道棱 + 5 道沟）
RIDGES = 5


class Spike:
    def __init__(self, plate, s, r, L, a0, a1, yaw, broken=None, name=""):
        self.plate, self.s, self.r, self.L = plate, s, r, L
        self.a0, self.a1, self.yaw = a0, a1, yaw
        self.broken = broken
        self.name = name
        self.r0 = 0.07 + 0.075 * L
        self.rt = max(0.03, 0.09 * self.r0)
        self._frame()

    def _frame(self):
        p = self.plate
        s1, r1 = np.array([self.s]), np.array([self.r])
        P0, h = p.top(s1, r1)
        a, b = h["a"], h["b"]
        eps = 0.02
        Pa = p.top(*p.sr(a + eps, b))[0] - p.top(*p.sr(a - eps, b))[0]
        Pb = p.top(*p.sr(a, b + eps))[0] - p.top(*p.sr(a, b - eps))[0]
        n = np.cross(Pa[0], Pb[0])
        n /= np.linalg.norm(n)
        if n.dot(h["N"][0]) < 0:
            n = -n
        th, ph = h["th"][0], h["ph"][0]
        dB = snp.eye_dir(np.array(th + 0.01), np.array(ph)) - snp.eye_dir(np.array(th), np.array(ph))
        B = dB - n * dB.dot(n)
        B /= np.linalg.norm(B)
        # 偏一点方位（绕法线转）
        X = np.cross(n, B)
        B = B * math.cos(self.yaw) + X * math.sin(self.yaw)
        self.P0, self.N, self.B = P0[0], n, B
        self.X = np.cross(n, B)
        self.ab0 = (float(a[0]), float(b[0]))
        self.Ja = Pa[0] / (2 * eps)
        self.Jb = Pb[0] / (2 * eps)
        # 中心线
        steps = 120
        Lc = self.L if self.broken is None else self.L * self.broken
        ls = np.linspace(0, Lc, steps + 1)
        ang = self.a0 + (self.a1 - self.a0) * (ls / self.L) ** 1.4
        dirs = np.outer(np.cos(ang), self.N) + np.outer(np.sin(ang), self.B)
        pos = np.vstack([self.P0, self.P0 + np.cumsum(0.5 * (dirs[1:] + dirs[:-1]) * (Lc / steps), axis=0)])
        self.cl_l, self.cl_p, self.cl_a = ls, pos, ang
        self.Lc = Lc

    # ------------------------------------------------------------ 几何
    def radius(self, l):
        f = np.clip(l / self.L, 0, 1)
        return self.rt + (self.r0 - self.rt) * (1 - f) ** 0.9

    def ridge_amp(self, l):
        f = np.clip(l / self.L, 0, 1)
        return snp.smoothstep(0.0, 0.12, f) * (1 - snp.smoothstep(0.75, 0.95, f))

    def prof(self, phi, l):
        a = 0.14 * self.ridge_amp(l)
        return 1 - a + a * np.abs(np.cos(RIDGES / 2 * (phi - math.pi / RIDGES))) ** 2.5

    def center(self, l):
        """中心线上 l 处：位置、切向、凹侧方向 Y、侧向 X"""
        p = np.stack([np.interp(l, self.cl_l, self.cl_p[:, i]) for i in range(3)], -1)
        a = np.interp(l, self.cl_l, self.cl_a)
        T = np.cos(a) * self.N + np.sin(a) * self.B
        Y = -np.sin(a) * self.N + np.cos(a) * self.B
        return p, T, Y, self.X

    def shaft_ring(self, l, n):
        phi = 2 * math.pi * np.arange(n) / n
        p, T, Y, X = self.center(l)
        # 根部的几圈别跟着刺身斜：圈所在的平面从贴着甲面（法线为轴）慢慢转到垂直刺身，不然往后倒的那一侧会扎进甲里
        beta = float(snp.smoothstep(0.0, 2.8 * self.r0, l))
        Tb = (1 - beta) * self.N + beta * T
        Tb /= np.linalg.norm(Tb)
        Y = Y - Tb * Y.dot(Tb)
        Y /= np.linalg.norm(Y)
        X = np.cross(Tb, Y)
        rad = self.radius(l) * self.prof(phi, l)
        off = rad[:, None] * (np.outer(np.cos(phi), Y) + np.outer(np.sin(phi), X))
        return p + off, phi

    def skirt_ring(self, rho, dh, n):
        """贴着甲面的一圈：甲面切平面里半径 rho 的圆投到甲面上，再沿法线挪 dh。"""
        phi = 2 * math.pi * np.arange(n) / n
        off = rho * (np.outer(np.cos(phi), self.B) + np.outer(np.sin(phi), self.X))
        # 往后（刺倒的方向）多伸一点，基座是顺着刺拉长的
        off += np.outer(np.clip(np.cos(phi), 0, None) * rho * 0.35, self.B)
        J = np.stack([self.Ja, self.Jb], 1)
        G = J.T @ J
        dab = np.linalg.solve(G, (off @ J).T).T
        a = self.ab0[0] + dab[:, 0]
        b = self.ab0[1] + dab[:, 1]
        s, r = self.plate.sr(a, b)
        r = np.minimum(r, 0.985)
        P, _ = self.plate.top(s, r, dh)
        return P, phi

    def tip_ring(self, t, n):
        """磨圆的刺尖：t ∈ (0,1]，半球帽。"""
        lc = self.Lc - self.rt
        phi = 2 * math.pi * np.arange(n) / n
        p, T, Y, X = self.center(np.array(lc))
        ang = t * math.pi / 2
        rad = self.rt * math.cos(ang)
        c = p + T * self.rt * math.sin(ang)
        return c + rad * (np.outer(np.cos(phi), Y) + np.outer(np.sin(phi), X)), phi


# ---------------------------------------------------------------------------- 排布
def plan(plates, rng):
    """挑哪些甲片长刺。返回 [Spike]。"""
    out = []
    by = {}
    for p in plates:
        by.setdefault((p.ring, p.zone), []).append(p)
    dorsal_L = {1: 3.4, 2: 4.6, 3: 5.0, 4: 4.5, 5: 3.6, 6: 2.6}
    dlat_L = {0: 1.6, 1: 2.6, 2: 3.2, 3: 3.4, 4: 2.9, 5: 2.3, 6: 1.6}
    lat_L = {1: 1.4, 2: 1.8, 3: 1.9, 4: 1.6}
    broke = ("dlat", 3, "L")         # 断掉的那根
    for p in plates:
        if p.kind == "cap":
            continue
        side = "R" if p.phc > 0 else "L"
        is_broke = (p.zone, p.ring, side) == broke
        if p.zone == "dorsal" and p.ring in dorsal_L:
            L = dorsal_L[p.ring] * rng.uniform(0.92, 1.08)
        elif p.zone == "dlat" and p.ring in dlat_L:
            if rng.random() < 0.22 and not is_broke:
                continue
            L = dlat_L[p.ring] * rng.uniform(0.85, 1.12)
        elif p.zone == "lat" and p.ring in lat_L:
            # 体侧：只挑背侧下面紧挨着的那片
            lats = sorted([q for q in plates if q.ring == p.ring and q.zone == "lat" and (q.phc > 0) == (p.phc > 0)],
                          key=lambda q: abs(q.phc))
            if p is not lats[0] or rng.random() < 0.3:
                continue
            L = lat_L[p.ring] * rng.uniform(0.85, 1.15)
        else:
            continue
        r0 = 0.07 + 0.075 * L
        e = 0.17 * p.k + 1.9 * r0 + 0.15
        Lp0 = float(p.Lp[0])
        r = float(np.clip(1 - e / Lp0, 0.2, 0.8))
        br = None
        if is_broke:
            br = 0.48
        out.append(Spike(p, 0.0, r, L, math.radians(rng.uniform(36, 46)), math.radians(rng.uniform(66, 76)),
                         math.radians(rng.uniform(-7, 7)), br, name=p.name))
    cap = [p for p in plates if p.kind == "cap"]
    if cap:
        c = cap[0]
        out.append(Spike(c, 0.97, 0.3, 1.5, math.radians(28), math.radians(45), math.radians(-6), name="cap0"))
    return out


# ---------------------------------------------------------------------------- 网格
LOW_F = [0.1, 0.22, 0.36, 0.5, 0.64, 0.78, 0.9]


def _onto(P, N, bvh, dh):
    """把点沿 -N 投到低模甲面上（bvh），再沿 N 挪 dh。没打到就不动。"""
    from mathutils import Vector
    out = P.copy()
    d = Vector(-N)
    for i, p in enumerate(P):
        hit = bvh.ray_cast(Vector(p + N * 0.8), d, 2.0)
        if hit[0] is not None:
            out[i] = np.array(hit[0]) + N * dh
    return out


def spike_low(sp, bvh=None):
    """→ co, tris, 逐角 UV（米）。bvh：甲片低模，基座那两圈贴着低模的甲面放（低模甲面是折线，比解析面低一点）。"""
    n = NLOW
    rings = []
    P, phi = sp.skirt_ring(1.6 * sp.r0, -0.15, n)
    if bvh is not None:
        P = _onto(P, sp.N, bvh, -0.15)
    rings.append(P)
    P = sp.skirt_ring(1.95 * sp.r0, 0.0, n)[0]
    if bvh is not None:
        P = _onto(P, sp.N, bvh, 0.012)
    rings.append(P)
    P = sp.skirt_ring(1.45 * sp.r0, 0.0, n)[0]
    if bvh is not None:
        P = _onto(P, sp.N, bvh, 0.05)
    rings.append(0.75 * P + 0.25 * sp.shaft_ring(np.array(0.9 * sp.r0), n)[0])
    ls = [f * sp.L for f in LOW_F if f * sp.L < sp.Lc - sp.rt * 1.5]
    for l in ls:
        rings.append(sp.shaft_ring(np.array(l), n)[0])
    if sp.broken is None:
        rings.append(sp.tip_ring(0.0, n)[0])
        tip = sp.center(np.array(sp.Lc))[0]
    else:
        rings.append(sp.shaft_ring(np.array(sp.Lc), n)[0])
        tip = sp.center(np.array(sp.Lc))[0] + sp.center(np.array(sp.Lc))[1] * 0.04
    bottom = sp.P0 - sp.N * 0.28
    rm = snp.RingMesh()
    sig = np.arange(n) / n
    rm.add(bottom, [0.0], k=-1)
    for R in rings:
        rm.add(R, sig, k=np.arange(n))
    rm.add(tip, [0.0], k=-1)
    co, tris, band, attrs, starts = rm.build()
    # UV：沿刺展开（v = 沿中心线的长度，u = 周向弧长），缝在凹侧（朝后、朝甲面那一边）
    kidx = attrs["k"].astype(np.int64)
    u = np.zeros(len(co))
    v = np.zeros(len(co))
    half = np.zeros(len(co))
    acc = 0.0
    prev = None
    for j, R in enumerate(rings):
        c = R.mean(0)
        if prev is not None:
            acc += np.linalg.norm(c - prev)
        prev = c
        per = snp_perim(R)
        st = starts[1 + j]
        u[st:st + n] = (np.arange(n) / n - 0.5) * per
        v[st:st + n] = acc
        half[st:st + n] = per
    v[starts[0]] = -2.0 * sp.r0
    v[starts[-1]] = acc + np.linalg.norm(tip - prev)
    tu = u[tris]
    tk = kidx[tris]
    wrapc = (tk.max(1) == n - 1)[:, None] & (tk == 0)
    tu = np.where(wrapc, tu + half[tris], tu)
    pole = tk < 0
    others = np.where(pole, 0.0, tu).sum(1) / np.maximum((~pole).sum(1), 1)
    tu = np.where(pole, others[:, None], tu)
    uvc = np.stack([tu, v[tris]], -1)
    return co, tris, uvc.reshape(-1, 2)


def snp_perim(R):
    return float(np.linalg.norm(np.roll(R, -1, 0) - R, axis=1).sum())


def spike_high(sp, sid, h=0.022):
    """→ co, tris, 属性（reg 3 刺身 / 4 基座 / 5 断口；f = l/L，phi 周向角，sid）"""
    rm = snp.RingMesh()
    nmax = max(16, int(math.ceil(2 * math.pi * 2.0 * sp.r0 * 1.25 / h)))
    rm.add(sp.P0 - sp.N * 0.28, [0.0], reg=4, f=0.0, phi=0.0, sid=sid, q=0.0)
    # 基座：贴甲面的几圈（半径 2.0 → 1.65 r0，高度 -0.12 → +0.02）
    nsk = max(2, int(math.ceil(0.4 * sp.r0 / h)))
    for i in range(nsk + 1):
        t = i / nsk
        P, phi = sp.skirt_ring((1.6 + 0.35 * t) * sp.r0, -0.15 * (1 - t) ** 2 - 0.012, nmax)
        rm.add(P, phi / (2 * math.pi), reg=4, f=0.0, phi=phi, sid=sid, q=-1 + 0.5 * t)
    # 基座 → 刺身：从贴面的圈过渡到中心线上 l0 处的圈（凹的圆角）
    l0 = 0.9 * sp.r0
    sk = sp.skirt_ring(1.95 * sp.r0, 0.0, nmax)[0]
    sh, phi = sp.shaft_ring(np.array(l0), nmax)
    nf = max(4, int(math.ceil(np.linalg.norm(sh - sk, axis=1).max() * 1.5 / h)))
    for i in range(1, nf + 1):
        t = i / nf
        # 凹的圆角：先贴着甲面往里收，再往上长成刺身
        hug = sp.skirt_ring((1.95 - 0.75 * t) * sp.r0, -0.012 * (1 - t), nmax)[0]
        tt = t ** 2.2
        P = hug * (1 - tt) + sh * tt
        rm.add(P, phi / (2 * math.pi), reg=4, f=l0 / sp.L * t, phi=phi, sid=sid, q=-0.5 + 0.5 * t)
    # 刺身
    lend = sp.Lc - (sp.rt if sp.broken is None else 0.0)
    nl = max(2, int(math.ceil((lend - l0) / h)))
    for i in range(1, nl + 1):
        l = l0 + (lend - l0) * i / nl
        n = max(12, int(math.ceil(2 * math.pi * float(sp.radius(np.array(l))) * 1.1 / h)))
        P, phi = sp.shaft_ring(np.array(l), n)
        rm.add(P, phi / (2 * math.pi), reg=3, f=l / sp.L, phi=phi, sid=sid, q=l)
    if sp.broken is None:
        nt = max(2, int(math.ceil(sp.rt * 1.6 / h)))
        for i in range(1, nt):
            t = i / nt
            n = max(8, int(math.ceil(2 * math.pi * sp.rt * math.cos(t * math.pi / 2) / h)))
            P, phi = sp.tip_ring(t, n)
            rm.add(P, phi / (2 * math.pi), reg=3, f=1.0, phi=phi, sid=sid, q=sp.Lc)
        rm.add(sp.center(np.array(sp.Lc))[0], [0.0], reg=3, f=1.0, phi=0.0, sid=sid, q=sp.Lc)
    else:
        # 断口：一圈圈往中心收，起伏交给 shell_high
        p, T, Y, X = sp.center(np.array(sp.Lc))
        rad = float(sp.radius(np.array(sp.Lc)))
        nb = max(2, int(math.ceil(rad / h)))
        for i in range(1, nb):
            t = 1 - i / nb
            n = max(8, int(math.ceil(2 * math.pi * rad * t / h)))
            phi = 2 * math.pi * np.arange(n) / n
            P = p + T * 0.02 * (1 - t) + rad * t * (np.outer(np.cos(phi), Y) + np.outer(np.sin(phi), X))
            rm.add(P, phi / (2 * math.pi), reg=5, f=sp.Lc / sp.L, phi=phi, sid=sid, q=t)
        rm.add(p + T * 0.03, [0.0], reg=5, f=sp.Lc / sp.L, phi=0.0, sid=sid, q=0.0)
    co, tris, band, attrs, _ = rm.build()
    return co, tris, attrs
