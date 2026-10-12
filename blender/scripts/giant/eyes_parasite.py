"""眼睛上的寄生桡足类（Ommatokoita elongata，雌虫）——照真实解剖放大：
  锚（bulla）：一枚扁圆的纽扣，嵌在角膜正中的浅坑里；
  第二小颚（两条短臂）：从锚往外伸、并在一起成一根细柄（高模上两侧各一道纵沟，看得出是两条臂合起来的）；
  头胸部：细柄顶上一个小肉疙瘩，和躯干之间一道颈沟；
  躯干：发白、略透明的长圆肉团（几十厘米），从头胸部往后弯，顺着水流方向（卵带骨链的方向）垂下去，
    表面一圈圈细横皱、几道纵褶、零星的鼓包；
  两条卵带：从躯干后端并排拖出来，沿 spec.parasite_rest_points 的骨链，长 spec.PARASITE_LENGTH，
    一节一节（节间收细），每节里一颗颗卵的鼓包（多列），从根到梢变细，绕着彼此拧小半圈，梢部往外卷。
低模：躯干 10 边 × 14 圈，卵带 6 边 × 36 圈（每两圈一节，节间那圈收细，侧影看得出一节一节）。
权重：躯干（含锚、臂、头胸）全给 spec.bone_at(EYE_S)；卵带按到骨链根的距离分给 Parasite%s_0..3，相邻两节线性混合，
  根部 0.1～0.3 米从眼睛那节脊椎骨渐变过来（卵带根长在躯干上，不能被骨头拽开）。
"""
import math

import numpy as np

import lib
from giant import spec
from giant import eyes_util as U

SAC_SIDES = 6
SAC_RINGS = 36
BODY_SIDES = 10
BODY_END = 0.38       # 躯干后端在骨链上的位置（从骨链根往后多少米），卵带从这里长出来
SAC_SEP = 0.075        # 两条卵带中心离中线多远（米）
SAC_R0, SAC_R1 = 0.046, 0.030   # 卵带根、梢的半径
SKIN_CLEAR = 0.07     # 卵带离体表至少多远（米，加上卵带半径）
CURL_R = 0.13          # 梢部卷曲的起始半径
CURL_TURN = 1.25 * math.pi


def _eye():
    from giant import eyes
    return eyes


def _smooth_table(keys, length, blur=0.008, step=0.001):
    ds = np.arange(0.0, length + step, step)
    kd = np.array([k[0] for k in keys])
    kr = np.array([k[1] for k in keys])
    r = np.interp(ds, kd, kr)
    n = max(1, int(blur / step))
    ker = np.ones(2 * n + 1) / (2 * n + 1)
    pad = np.concatenate([np.full(n, r[0]), r, np.full(n, r[-1])])
    r = np.convolve(pad, ker, mode="valid")
    return lambda d: float(np.interp(d, ds, r)) if np.ndim(d) == 0 else np.interp(d, ds, r)


# ---------------------------------------------------------------------------- 躯干
class Body:
    def __init__(self, side):
        E = _eye()
        O, e1, e2, ax = E.basis(side)
        A = E.apex(side)
        pts = [np.array(p) for p in spec.parasite_rest_points(side)]
        D0 = pts[1] - pts[0]
        D0 /= np.linalg.norm(D0)
        self.D0 = D0
        q = [A - ax * 0.034, A - ax * 0.014, A + ax * 0.05 + e2 * 0.010, A + ax * 0.10 + e2 * 0.02,
             A + ax * 0.15 + e2 * 0.01 + D0 * 0.03, pts[0] + D0 * 0.08, pts[0] + D0 * 0.22, pts[0] + D0 * BODY_END]
        self.path = U.Path(U.catmull_np(q, 40), up=e2)
        L = self.path.length
        self.length = L
        self.neck = 0.168  # 头胸部和躯干之间的颈沟
        tr = 0.175         # 躯干从这里开始
        f = lambda x: tr + (L - tr) * x
        keys = [(0.000, 0.030), (0.006, 0.064), (0.014, 0.070), (0.020, 0.052), (0.030, 0.023), (0.075, 0.021),
                (0.110, 0.040), (0.138, 0.046), (0.162, 0.035),
                (f(0.08), 0.050), (f(0.30), 0.067), (f(0.60), 0.072), (f(0.85), 0.060), (L - 0.012, 0.040),
                (L, 0.01)]
        self.radius = _smooth_table(keys, L, blur=0.005)
        self.trunk = tr
        self.ax = ax
        self.end = self.path.at(L)[0]

    def low_rings(self):
        L = self.length
        t = lambda x: self.trunk + (L - self.trunk) * x
        return [0.003, 0.010, 0.020, 0.032, 0.062, 0.095, 0.125, 0.150, 0.170,
                t(0.12), t(0.32), t(0.52), t(0.72), t(0.88), L - 0.016]

    def disp(self, side):
        rng_seed = 31 if side > 0 else 37
        tr, L, neck = self.trunk, self.length, self.neck

        def f(D, A, P, n):
            sh = D.shape
            Pf = P.reshape(-1, 3)
            Df, Af = D.ravel(), A.ravel()
            h = np.zeros(len(Df))
            trunk = U.smoothstep(tr - 0.02, tr + 0.01, Df) * (1 - U.smoothstep(L - 0.03, L, Df))
            arms = U.smoothstep(0.02, 0.03, Df) * (1 - U.smoothstep(0.085, 0.10, Df))
            head = U.smoothstep(0.095, 0.11, Df) * (1 - U.smoothstep(neck - 0.008, neck, Df))
            # 躯干：一圈圈细横皱（被牵拉的角质膜）+ 几道纵褶 + 零星鼓包
            wob = U.fbm3(Pf * 30, 2, rng_seed)
            ring = np.sin(2 * np.pi * Df / 0.016 * (1 + 0.3 * (wob - 0.5)) + 9 * wob)
            patch = 0.3 + U.smoothstep(0.35, 0.7, U.fbm3(Pf * 9 + 2.2, 3, rng_seed + 3))
            ring = ring * patch
            h += trunk * (0.0004 * ring)
            lng = np.sin(5 * Af + 3 * U.fbm3(Pf * 12, 2, rng_seed + 1))
            h += trunk * 0.0012 * lng
            h += (trunk + 0.5 * head) * 0.003 * (U.fbm3(Pf * 22, 3, rng_seed + 2) - 0.5) * 2
            # 两条臂并成一根柄：两侧各一道纵沟
            groove = np.exp(-(np.sin(Af) / 0.28) ** 2)
            h -= arms * 0.005 * groove
            # 头胸部和躯干之间的颈沟
            ng = np.exp(-((Df - neck) / 0.006) ** 2)
            h -= 0.004 * ng
            # 锚盘边上一圈棱
            rim = np.exp(-((Df - 0.016) / 0.003) ** 2)
            h += 0.0015 * rim
            cav = np.clip(trunk * np.clip(-ring, 0, 1) * 0.35 + trunk * np.clip(-lng, 0, 1) * 0.25
                          + arms * groove * 0.8 + ng * 0.9, 0, 1)
            rid = np.clip(trunk * np.clip(ring, 0, 1) * 0.2 + rim * 0.4, 0, 1)
            f.cav, f.rid = cav, rid
            return h.reshape(sh)
        return f


# ---------------------------------------------------------------------------- 卵带
def _clear_skin(pts, need):
    """spec 的卵带骨链往后下方顺着头侧垂，头往后越来越宽，骨链梢会扎进皮里（梢端在体表以内约 5 厘米）。
    静止姿态的卵带沿体表法线往外推，离理想体表至少 need 米；推的量沿长度平滑过渡（蒙皮跟着骨头转没问题）。"""
    pts = np.asarray(pts, dtype=np.float64)
    push = np.zeros(len(pts))
    nrm = np.zeros_like(pts)
    for i, p in enumerate(pts):
        s, th = spec.body_coords(lib.V(p))
        n = spec.normal(s, th)
        sp = spec.surface(s, th)
        nrm[i] = n[:]
        push[i] = max(0.0, need - float((lib.V(p) - sp).dot(n)))
    k = max(1, int(0.3 / max(np.linalg.norm(np.diff(pts, axis=0), axis=1).mean(), 1e-4)))
    pad = np.concatenate([np.full(k, push[0]), push, np.full(k, push[-1])])
    mx = np.array([pad[i:i + 2 * k + 1].max() for i in range(len(push))])
    ker = np.hanning(2 * k + 1)
    ker /= ker.sum()
    pad = np.concatenate([np.full(k, mx[0]), mx, np.full(k, mx[-1])])
    sm = np.convolve(pad, ker, mode="valid")
    return pts + nrm * sm[:, None]     # 先取窗口最大再同宽模糊：处处不小于原推量，又是光滑的


def _smooth_line(pts, window=0.08, step=0.002):
    """折线按 2 毫米重采样后做高斯平滑（去掉推皮、拼接处的折角；高模细到毫米，折角会让一圈圈截面互相穿插）。"""
    p = U.Path(pts, step=step).P
    sig = window / step / 2.5
    n = int(3 * sig)
    x = np.arange(-n, n + 1)
    ker = np.exp(-0.5 * (x / sig) ** 2)
    ker /= ker.sum()
    pad = np.concatenate([2 * p[:1] - p[n:0:-1], p, 2 * p[-1:] - p[-2:-n - 2:-1]], axis=0)
    return np.stack([np.convolve(pad[:, k], ker, mode="valid") for k in range(3)], axis=1)


def _chain(side):
    pts = np.array([np.array(p) for p in spec.parasite_rest_points(side)])
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    acc = np.concatenate([[0.0], np.cumsum(seg)])
    return pts, acc


def chain_at(side, c):
    pts, acc = _chain(side)
    return np.stack([np.interp(c, acc, pts[:, k]) for k in range(3)], axis=-1)


def chain_param(side, p):
    """点 → 到骨链根的距离（投影到折线上）。"""
    pts, acc = _chain(side)
    p = np.atleast_2d(p)
    best = np.full(len(p), 1e9)
    out = np.zeros(len(p))
    for k in range(len(pts) - 1):
        a, b = pts[k], pts[k + 1]
        ab = b - a
        t = np.clip(((p - a) @ ab) / (ab @ ab), 0, 1)
        d = np.linalg.norm(p - (a + t[:, None] * ab), axis=1)
        m = d < best
        best[m] = d[m]
        out[m] = acc[k] + t[m] * np.linalg.norm(ab)
    return out


class Sac:
    def __init__(self, side, k, body):
        """k = -1 / +1：并排的两条。"""
        E = _eye()
        O, e1, e2, ax = E.basis(side)
        self.k = k
        cs = [BODY_END + 0.02, 0.70, 1.0, 1.35, 1.7, 2.0, 2.22]
        # 两条一起推：按「整对里最靠皮的那条」算，免得各推各的挤到一起
        bp = U.catmull_np([chain_at(side, c) for c in cs], 60)
        base = U.Path(_clear_skin(U.Path(bp).P[::4], SKIN_CLEAR + SAC_R0 + SAC_SEP * 1.15), up=ax)
        Lb = base.length
        d = base.d
        P, T = base.P, base.T
        w = np.cross(T, ax[None])
        w /= np.linalg.norm(w, axis=1)[:, None]
        v = np.cross(T, w)
        tw = 0.45 * np.pi * d / Lb
        sep = 0.035 + (SAC_SEP - 0.035) * U.smoothstep(0.0, 0.28, d)
        sep = sep * (1 + 0.15 * np.sin(2 * np.pi * d / 1.1 + 0.7))
        off = k * sep[:, None] * (w * np.cos(tw)[:, None] + v * np.sin(tw)[:, None])
        # 不是硬棍：各自轻轻地蜿蜒
        mean = 0.022 * np.sin(2 * np.pi * d / 0.85 + (1.3 if k > 0 else 4.1)) * U.smoothstep(0.2, 0.6, d)
        off += (v * np.cos(tw)[:, None] - w * np.sin(tw)[:, None]) * mean[:, None]
        cl = P + off
        # 梢部往外卷
        Pc = cl[-1]
        Tc = (cl[-1] - cl[-25]) / np.linalg.norm(cl[-1] - cl[-25])
        sn = np.array(spec.normal(*spec.body_coords(lib.V(Pc))))   # 梢往离开皮的方向卷，两条再往两边分一点
        cdir = k * (w[-1] * np.cos(tw[-1]) + v[-1] * np.sin(tw[-1])) * 0.55 + sn * 0.8
        cdir -= Tc * np.dot(cdir, Tc)
        cdir /= np.linalg.norm(cdir)
        ctr = Pc + cdir * CURL_R
        bs = np.linspace(0, CURL_TURN, 90)[1:]
        Rb = CURL_R * (1 - 0.5 * bs / CURL_TURN)
        curl = ctr[None] + Rb[:, None] * (-cdir[None] * np.cos(bs)[:, None] + Tc[None] * np.sin(bs)[:, None])
        start = body.end - body.D0 * 0.06 + k * 0.025 * w[0]
        pts = np.concatenate([[start], cl, curl], axis=0)
        pts = _smooth_line(_clear_skin(pts, SKIN_CLEAR + SAC_R0))
        self.path = U.Path(pts, up=ax)
        L = self.path.length
        self.length = L
        self.seg = (L - 0.03) / ((SAC_RINGS - 1) / 2.0)   # 低模每两圈一节
        r_keys = [(0.0, 0.026), (0.035, SAC_R0 * 0.95), (0.08, SAC_R0), (L * 0.55, (SAC_R0 + SAC_R1) / 2 + 0.002),
                  (L - 0.04, SAC_R1), (L - 0.01, SAC_R1 * 0.8), (L, SAC_R1 * 0.5)]
        self.base_r = _smooth_table(r_keys, L, blur=0.01)
        self.d0 = 0.015

    def constrict(self, d):
        ph = (np.asarray(d) - self.d0) / self.seg
        delta = np.abs(ph - np.round(ph))
        return np.exp(-(delta / 0.13) ** 2) * U.smoothstep(0.04, 0.12, np.asarray(d))

    def radius(self, d):
        return self.base_r(d) * (1 - 0.18 * self.constrict(d))

    def low_rings(self):
        return [self.d0 + self.seg * 0.5 * i for i in range(SAC_RINGS)]

    def disp(self, side):
        seed = (41 if side > 0 else 43) + (0 if self.k > 0 else 5)
        sacr = self

        def f(D, A, P, n):
            sh = D.shape
            Df, Af = D.ravel(), A.ravel()
            Pf = P.reshape(-1, 3)
            E = 7
            NR = 3                             # 每节三排卵（多列卵，交错排）
            ph = (Df - sacr.d0) / sacr.seg
            x = ph * NR
            rr = sacr.base_r(Df)
            cx_m = sacr.seg / NR
            cy_m = 2 * np.pi * rr / E
            erad = 0.56 * np.minimum(cx_m, cy_m)
            row0 = np.floor(x).astype(np.int64)
            dome = np.zeros(len(Df))
            # 每颗卵的位置、大小抖一下；邻近格子一起算取最大，卵可以挤出格子边，不会被切出台阶
            for dr in (-1, 0, 1):
                row = row0 + dr
                y = Af / (2 * np.pi) * E + 0.5 * (row % 2)
                col0 = np.floor(y).astype(np.int64)
                for dc in (-1, 0, 1):
                    col = col0 + dc
                    cw = col % E
                    j1 = U._hash(row, cw, np.zeros_like(row), seed)
                    j2 = U._hash(row, cw, np.ones_like(row), seed)
                    j3 = U._hash(row, cw, np.full_like(row, 2), seed)
                    lx = (x - (row + 0.5 + (j1 - 0.5) * 0.3)) * cx_m
                    ly = (y - (col + 0.5 + (j2 - 0.5) * 0.3)) * cy_m
                    er = erad * (0.85 + 0.3 * j3)
                    dome = np.maximum(dome, np.sqrt(np.clip(1 - (lx ** 2 + ly ** 2) / er ** 2, 0, 1)) ** 0.8)
            con = sacr.constrict(Df)
            live = U.smoothstep(0.05, 0.1, Df) * (1 - U.smoothstep(sacr.length - 0.05, sacr.length - 0.015, Df))
            h = live * (1 - 0.7 * con) * (0.003 * dome - 0.0011)
            h += live * 0.0005 * (U.fbm3(Pf * 40, 2, seed) - 0.5)
            h -= live * 0.002 * con
            f.cav = np.clip(live * ((1 - dome) * 0.45 + con * 0.8), 0, 1)
            f.rid = np.clip(live * dome ** 2 * 0.3, 0, 1)
            return h.reshape(sh)
        return f


# ---------------------------------------------------------------------------- 低模、高模
def _sac_weights(ob, side, tag):
    me = ob.data
    co = np.array([v.co[:] for v in me.vertices])
    c = chain_param(side, co)
    seg = spec.PARASITE_LENGTH / spec.PARASITE_BONES
    groups = [ob.vertex_groups.get("Parasite%s_%d" % (tag, k)) or ob.vertex_groups.new(name="Parasite%s_%d" % (tag, k))
              for k in range(spec.PARASITE_BONES)]
    sp = ob.vertex_groups.get(spec.bone_at(spec.EYE_S)) or ob.vertex_groups.new(name=spec.bone_at(spec.EYE_S))
    for i, ci in enumerate(c):
        root = 1.0 - float(U.smoothstep(BODY_END - 0.08, BODY_END + 0.2, ci))
        f = ci / seg - 0.5
        i0 = int(math.floor(f))
        t = f - i0
        ws = {}
        if i0 < 0:
            ws[0] = 1.0
        elif i0 >= spec.PARASITE_BONES - 1:
            ws[spec.PARASITE_BONES - 1] = 1.0
        else:
            ws[i0] = 1.0 - t
            ws[i0 + 1] = t
        for kk, w in ws.items():
            if w * (1 - root) > 1e-4:
                groups[kk].add([i], w * (1 - root), 'REPLACE')
        if root > 1e-4:
            sp.add([i], root, 'REPLACE')


def build_low(side, tag, coll, mat):
    body = Body(side)
    parts = [U.tube_low("ParasiteBody" + tag, coll, mat, body.path, body.low_rings(), body.radius, BODY_SIDES,
                        pole_k=0.5)]
    spec.assign_bone(parts[0], spec.bone_at(spec.EYE_S))
    for k in (-1, 1):
        s = Sac(side, k, body)
        o = U.tube_low("ParasiteSac%s%d" % (tag, (k + 1) // 2), coll, mat, s.path, s.low_rings(), s.radius,
                       SAC_SIDES, pole_k=0.6)
        _sac_weights(o, side, tag)
        parts.append(o)
    return lib.join(parts, "Parasite" + tag)


def build_high(side, tag):
    body = Body(side)
    out = []
    L = body.length
    ds = np.arange(0.002, L - 0.004, 0.0018)
    f = body.disp(side)
    P, D, A, C, T = U.tube_high_points(body.path, ds, body.radius, 144, disp_fn=f)
    pe = body.path.at(L)[0]
    ps = body.path.at(0.0)[0]
    ob = U.grid_mesh("ParasiteBodyHigh" + tag, P, pole_start=ps, pole_end=pe)
    cav = np.concatenate([f.cav, [0.0, 0.0]])
    rid = np.concatenate([f.rid, [0.0, 0.0]])
    U.set_point_color(ob, "Curv", np.stack([cav, rid, np.zeros_like(cav)], axis=1))
    U.set_point_color(ob, "Area", np.ones(len(cav)))
    out.append(ob)
    for k in (-1, 1):
        s = Sac(side, k, body)
        L = s.length
        ds = np.arange(0.004, L - 0.004, 0.003)
        f = s.disp(side)
        P, D, A, C, T = U.tube_high_points(s.path, ds, s.radius, 64, disp_fn=f)
        ob = U.grid_mesh("ParasiteSacHigh%s%d" % (tag, (k + 1) // 2), P,
                         pole_start=s.path.at(0.0)[0], pole_end=s.path.at(L)[0])
        cav = np.concatenate([f.cav, [0.0, 0.0]])
        rid = np.concatenate([f.rid, [0.0, 0.0]])
        U.set_point_color(ob, "Curv", np.stack([cav, rid, np.zeros_like(cav)], axis=1))
        U.set_point_color(ob, "Area", np.ones(len(cav)))
        out.append(ob)
    return out
