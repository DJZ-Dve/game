"""牙（尖牙鱼式）：少而巨大、长短悬殊、弯、侧扁（刃面朝唇 / 舌两侧，前后两道刃棱）、稀疏地立在牙床脊上。

- 下颌最前一对獠牙（L1）：露出部分沿着「以下颌铰链为圆心」的圆弧弯——闭嘴时插进上颚的牙槽（spec.fang_socket），
  张嘴时整根顺着这条圆弧滑出来，不会刮到牙槽壁；
- 下颌吻前（地包天伸出来的那段）各一颗往前上翘的牙（L0），闭嘴时立在上吻前面，从外面就能看见；
- 其余的牙闭嘴时上下交错，牙尖往舌侧倒、往后弯，落在对面牙床内侧的沟里；
- 左右不完全对称：长短、倾斜各有出入，左下缺一颗、左上缺一颗，右上一颗崩了尖，左下一颗有裂纹。
上牙整颗刚性跟所在脊椎骨，下牙全给 Jaw。"""
import math
import zlib

import numpy as np
from mathutils import Vector as V, Matrix

from giant import spec
from giant import mouth_shape as ms
from giant.mouth_util import MB, fbm, vnoise, ridged, smoothstep, rng

# 名字、上/下、s、设计长度（露出部分，闭嘴放不下会自动缩短）、往舌侧倒（度）、前倾（度，+ 往前）、往后弯（度）、往舌侧弯（度）、截面扁度 b/a
# 长短故意拉开：一长一短地错着，嘴角的只有几十厘米
LAYOUT = [
    ("L0", False, -0.0125, 1.15, -8, 36, 20, 0, 0.66),
    ("L1", False, 0.028, 0.0, 0, 0, 0, 0, 0.74),        # 獠牙：路径另算
    ("L2", False, 0.050, 0.55, 16, 8, 12, 6, 0.62),
    ("L3", False, 0.076, 2.10, 24, 2, 24, 8, 0.64),
    ("L4", False, 0.101, 0.95, 20, -4, 16, 6, 0.62),
    ("L5", False, 0.123, 1.75, 26, -6, 22, 8, 0.62),
    ("L6", False, 0.148, 0.80, 22, -8, 14, 6, 0.62),
    ("L7", False, 0.171, 0.40, 20, -10, 10, 4, 0.62),
    ("U1", True, 0.007, 0.45, 22, 16, 14, 6, 0.64),
    ("U2", True, 0.058, 1.05, 22, 4, 18, 6, 0.62),
    ("U3", True, 0.089, 1.65, 30, 0, 24, 8, 0.62),
    ("U4", True, 0.110, 0.75, 28, -4, 18, 6, 0.62),
    ("U5", True, 0.135, 1.55, 32, -6, 22, 8, 0.62),
    ("U6", True, 0.160, 0.70, 28, -8, 15, 6, 0.62),
    ("U7", True, 0.184, 0.38, 20, -10, 10, 4, 0.62),
]
MISSING = {("L5", -1), ("L7", 1), ("U4", -1)}
CHIPPED = {("U5", 1)}      # 崩尖
CRACKED = {("L3", -1)}     # 裂纹

FANG_TIP_MARGIN = 0.30     # 獠牙尖离头皮至少这么远
FANG_IN_PIT = 2.6         # 獠牙插进牙槽的长度（沿圆弧，米）


def base_radius(L):
    return 0.06 + 0.085 * L


def tag(t):
    return "%s%s" % (t.name, "R" if t.side > 0 else "L")


class Tooth:
    def __init__(self, name, upper, side, s, L, tilt, lean, cb, cm, aspect, r):
        self.name, self.upper, self.side, self.s = name, upper, side, s
        self.aspect = aspect
        self.chipped = (name, side) in CHIPPED
        self.cracked = (name, side) in CRACKED
        self.seed = zlib.crc32((name + str(side)).encode()) % 9973
        gap = V((0, 0, -1)) if upper else V((0, 0, 1))
        med = V((-side, 0, 0))
        g0, g1 = spec.gum_point(s - 0.002, side, upper), spec.gum_point(s + 0.002, side, upper)
        fwd = (g0 - g1).normalized()
        self.fwd = fwd
        out = fwd.cross(V((0, 0, 1))) * side
        if out.dot(V((side, 0, 0))) < 0:
            out = -out
        med = -out
        self.B = ms.crest_point(s, upper, side)
        self.pit = None
        if name == "L1":
            pts = self._fang_path()
            L = None
        else:
            pts = []
            n = 48
            p = self.B.copy()
            pts.append(p.copy())
            for k in range(n):
                f = (k + 0.5) / n
                tb = math.radians(lean - cb * f ** 1.2)
                tm = math.radians(tilt + cm * f ** 1.2)
                d = (gap + med * math.tan(tm) + fwd * math.tan(tb)).normalized()
                p = p + d * (L / n)
                pts.append(p.copy())
        self.crown = pts
        # 弧长
        acc = [0.0]
        for i in range(1, len(pts)):
            acc.append(acc[-1] + (pts[i] - pts[i - 1]).length)
        self.crown_acc = np.array(acc)
        self.L = acc[-1]
        if self.chipped:
            self.L_draw = self.L * 0.86
        else:
            self.L_draw = self.L
        self.r = base_radius(self.L) if r is None else r
        if name == "L1":
            self.r = 0.205
        self.d0 = (pts[1] - pts[0]).normalized()
        self._root(med, fwd)
        self.bone = "Jaw" if not upper else spec.bone_at(s)

    # -------------------------------------------------------------- 獠牙：圆弧
    def _fang_path(self):
        side = self.side
        h = spec.jaw_hinge()
        sk = spec.fang_socket(side)
        so = spec.s_of(sk.y)
        oz = ms.cavity_z(so, sk.x, True)
        O = V((sk.x, sk.y, oz))
        self.O = O
        R = math.hypot(O.y - h.y, O.z - h.z)
        aO = math.atan2(O.z - h.z, O.y - h.y)
        self.arc = (h.y, h.z, R, aO)
        # 圆弧部分：从牙槽口往上，最多插 FANG_IN_PIT，牙尖离头皮留 FANG_TIP_MARGIN
        arc = []
        n = 40
        for k in range(n + 1):
            a = aO + (FANG_IN_PIT / R) * k / n
            p = V((O.x, h.y + R * math.cos(a), h.z + R * math.sin(a)))
            lim = ms.outer_z(spec.s_of(p.y), p.x, True) - FANG_TIP_MARGIN
            if p.z > lim:
                break
            arc.append(p)
        # 下段：从下牙床脊到牙槽口，三次贝塞尔，末端切线 = 圆弧切线
        B = self.B
        tO = V((0.0, -math.sin(aO), math.cos(aO)))
        dist = (O - B).length
        tB = (V((0, 0, 1)) * 0.8 + (O - B).normalized() * 0.6).normalized()
        P0, P1, P2, P3 = B, B + tB * dist * 0.35, O - tO * dist * 0.35, O
        low = []
        m = 16
        for k in range(m):
            t = k / m
            low.append(P0 * (1 - t) ** 3 + P1 * 3 * (1 - t) ** 2 * t + P2 * 3 * (1 - t) * t * t + P3 * t ** 3)
        return low + arc

    # -------------------------------------------------------------- 牙根：埋进颌里，别穿出外皮
    def _root(self, med, fwd):
        best = None
        want = (0.7 if self.name == "L1" else 0.55) if self.L > 1.5 else (0.45 if self.L > 0.7 else 0.32)
        for a in np.linspace(0, 1, 11):
            for b in (0.0, 0.3, 0.6, 1.0, 1.6, 2.4):
                d = (-self.d0 * (1 - a) + med * a * 0.9 - fwd * b * 0.5)
                if d.length < 1e-6:
                    continue
                d.normalize()
                # 往里埋能埋多深
                L = 0.0
                ok = 0.0
                for k in range(1, 31):
                    l = want * k / 30
                    p = self.B + d * (l + self.r * 0.9)
                    sp = spec.s_of(p.y)
                    lim = ms.outer_z(sp, p.x, self.upper)
                    margin = (lim - p.z) if self.upper else (p.z - lim)
                    # 也不能从嘴腔面（上颚 / 口底的舌侧壁）钻出来
                    gx = ms.gum_x(min(max(sp, 0.0 if self.upper else spec.JAW_FRONT_S), spec.JAW_HINGE_S), self.upper)
                    if abs(p.x) < gx:
                        cz = ms.cavity_z(min(max(sp, spec.JAW_FRONT_S), spec.JAW_HINGE_S), p.x, self.upper)
                        inner = (p.z - cz) if self.upper else (cz - p.z)
                        if inner < (0.8 * self.r + 0.04) * min(1.0, (l + 0.05) / 0.3):
                            break
                    if margin < self.r + 0.06:
                        break
                    ok = l
                score = ok - 0.15 * a
                if best is None or score > best[0]:
                    best = (score, d, ok)
        _, d, l = best
        self.root_dir = d
        self.root_len = max(min(l, want), 0.12)

    # -------------------------------------------------------------- 中心线 + 截面
    def centerline(self, n_crown, n_root=3, tip_dense=1.35):
        """返回 (ls, pts, tangents)：ls < 0 是牙根，0 是牙床脊，L 是牙尖。"""
        ls, pts = [], []
        for k in range(n_root, 0, -1):
            l = -self.root_len * k / n_root
            # 牙根顺着 root_dir 往里，靠近牙床那段和牙冠方向过渡
            f = k / n_root
            d = (self.root_dir * f + (-self.d0) * (1 - f)).normalized()
            pts.append(self.B + d * (-l))
            ls.append(l)
        Ld = self.L_draw
        for k in range(n_crown + 1):
            t = k / n_crown
            t = 1.0 - (1.0 - t) ** tip_dense
            l = Ld * t
            pts.append(self.crown_at(l))
            ls.append(l)
        tans = []
        for i in range(len(pts)):
            a = pts[max(i - 1, 0)]
            b = pts[min(i + 1, len(pts) - 1)]
            tans.append((b - a).normalized())
        return np.array(ls), pts, tans

    def crown_at(self, l):
        acc = self.crown_acc
        l = min(max(l, 0.0), acc[-1])
        i = int(np.searchsorted(acc, l, side="right") - 1)
        i = min(max(i, 0), len(acc) - 2)
        t = (l - acc[i]) / max(acc[i + 1] - acc[i], 1e-9)
        return self.crown[i].lerp(self.crown[i + 1], t)

    def radius(self, l):
        """截面半宽（沿颌方向 a、唇舌方向 b = a·aspect）。"""
        L = self.L
        if l <= 0:
            f = (0.92 - 0.35 * (-l / max(self.root_len, 1e-3))) * (0.7 if self.name == "L0" else 1.0)
        else:
            t = l / L
            f = (1.0 - min(t, 1.0) ** 1.3) ** 0.9 * (1.0 + 0.08 * math.exp(-((t - 0.06) / 0.08) ** 2))
            if self.name == "L1":
                f = (1.0 - min(t, 1.0) ** 1.2) ** 0.85 * (1.0 + 0.06 * math.exp(-((t - 0.05) / 0.08) ** 2))
        return self.r * f

    def frames(self, pts, tans):
        """平行传输：每个截面的 (刃向 M, 唇舌向 Lb)。M 起始 = 颌的前后方向。"""
        M = self.fwd - tans[0] * self.fwd.dot(tans[0])
        M.normalize()
        # 下颌最前面的牙随便扭一点（有的斜）
        r = rng("twist" + tag(self))
        tw = math.radians(r.uniform(-12, 12))
        M = Matrix.Rotation(tw, 3, tans[0]) @ M
        out = []
        prev = tans[0]
        for t in tans:
            q = prev.rotation_difference(t)
            M = (q @ M)
            M = (M - t * M.dot(t)).normalized()
            prev = t
            out.append((M.copy(), t.cross(M).normalized()))
        return out


FIT_CLEAR = 0.08     # 闭嘴时牙离对面嘴腔面 / 别的牙至少这么远


def _samples(t, n=20):
    ls, pts, _ = t.centerline(n, n_root=3)
    return [(p, l, t.radius(l)) for p, l in zip(pts, ls)]


def clearance(t, others):
    """闭嘴时这颗牙的最小余量：对面嘴腔面、对面的唇、同侧已经摆好的牙。"""
    worst = 1e9
    for p, l, r in _samples(t):
        if l < 0.2:
            continue
        s = spec.s_of(p.y)
        opp = not t.upper
        gx = ms.gum_x(max(s, 0.0), opp)
        if abs(p.x) < gx - 0.05:
            cz = ms.cavity_z(s, p.x, opp)
            m = (cz - p.z) if opp else (p.z - cz)
        else:
            gz = ms.gum_z(max(s, 0.0), opp)
            m = (gz - p.z) if opp else (p.z - gz)
            m = min(m, 0.5) + 0.05
        worst = min(worst, m - r)
    for o in others:
        if o.side != t.side:
            continue
        for p, l, r in _samples(t, 14):
            if l < 0.05:
                continue
            for q, lo, ro in _samples(o, 14):
                if lo < 0.05:
                    continue
                worst = min(worst, (p - q).length - r - ro)
    return worst


def layout(verbose=False):
    teeth = []
    for side in (1, -1):
        placed = []
        rows = []
        for (name, upper, s, L, tilt, lean, cb, cm, asp) in LAYOUT:
            if (name, side) in MISSING:
                continue
            r = rng("tooth" + name + str(side))
            if name not in ("L1",):
                L = L * r.uniform(0.9, 1.1)
                tilt += r.uniform(-6, 6)
                lean += r.uniform(-5, 5)
                cb += r.uniform(-5, 5)
                s = s + r.uniform(-0.0015, 0.0015)
            rows.append((name, upper, s, L, tilt, lean, cb, cm, asp))
        # 獠牙和吻前的牙先放，其余按设计长度从长到短，放不下就缩短
        rows.sort(key=lambda x: (x[0] not in ("L1", "L0"), -x[3]))
        for (name, upper, s, L, tilt, lean, cb, cm, asp) in rows:
            t = Tooth(name, upper, side, s, L, tilt, lean, cb, cm, asp, None)
            if name not in ("L1", "L0"):
                L0 = L
                while clearance(t, placed) < FIT_CLEAR and L > 0.3:
                    L *= 0.93
                    t = Tooth(name, upper, side, s, L, tilt, lean, cb, cm, asp, None)
                if verbose:
                    print("  fit %s%s %.2f -> %.2f (余 %.2f)" % (name, "R" if side > 0 else "L", L0, L,
                                                             clearance(t, placed)))
            placed.append(t)
        teeth += placed
    teeth.sort(key=lambda t: (t.side, t.upper, t.s))
    return teeth


# ---------------------------------------------------------------------------- 网格
def _ring_counts(t, high):
    if high:
        nu = int(np.clip(2 * math.pi * t.r / 0.011, 48, 160)) // 2 * 2
        nv = int(np.clip(t.L / 0.010, 60, 380))
        return nu, nv, 10
    if t.L > 2.0:
        return 14, 22, 3
    if t.L > 0.9:
        return 12, 14, 2
    if t.L > 0.5:
        return 10, 10, 2
    return 8, 7, 2


def tooth_detail(t, ls, phi, base_pts, frames, radii_a, aspect):
    """高模：截面上每个点往外推多少（米），以及 Curv（凹槽、凸棱）。phi: (nu,)，返回 (nv, nu) 数组。"""
    nv, nu = len(ls), len(phi)
    L = t.L
    tt = np.clip(ls / L, -1, 1)[:, None] * np.ones((1, nu))
    ph = np.ones((nv, 1)) * phi[None, :]
    a = radii_a[:, None] * np.ones((1, nu))
    disp = np.zeros((nv, nu))
    groove = np.zeros((nv, nu))
    ridge = np.zeros((nv, nu))
    crown = (tt > 0).astype(np.float64)
    # 纵向细纹（牙釉质的棱）：沿牙身走，往牙尖淡出
    nst = max(int(round(2 * math.pi * t.r / 0.045)), 8)
    wob = np.sin(ph * 3 + t.seed) * 0.4 + tt * 2.0
    st = np.sin(ph * nst + wob)
    fade = smoothstep(0.0, 0.06, tt) * (1 - smoothstep(0.75, 0.97, tt))
    amp = 0.0010 + 0.0045 * t.r
    disp += st * amp * fade * crown
    groove += np.clip(-st, 0, 1) ** 2 * 0.3 * fade * crown
    ridge += np.clip(st, 0, 1) ** 3 * 0.15 * fade * crown
    # 前后两道刃棱（φ = 0、π 是刃向 M）
    for c in (0.0, math.pi):
        dd = np.angle(np.exp(1j * (ph - c)))
        e = np.exp(-(dd / 0.10) ** 2)
        disp += e * a * 0.05 * crown * (1 - smoothstep(0.85, 1.0, tt))
        ridge += e * 0.8 * crown
    # 牙尖磨损：最尖那段磨亮、略钝
    tipw = smoothstep(0.82, 0.98, tt)
    ridge += tipw * 0.9
    # 生长线（横向的细环），靠近牙根明显
    gl = np.sin(tt * L / 0.035 * 2 * math.pi + np.sin(ph * 2 + t.seed) * 0.6)
    disp += gl * 0.0012 * (1 - smoothstep(0.1, 0.5, tt)) * crown
    groove += np.clip(-gl, 0, 1) * 0.25 * (1 - smoothstep(0.1, 0.5, tt)) * crown
    # 牙结石：牙根附近一圈疙疙瘩瘩的沉积（牙床线以上 0～15%）
    pts = np.array([[p.x, p.y, p.z] for p in base_pts])
    P = (pts[:, None, :] + np.zeros((1, nu, 1)))
    Mv = np.array([[f[0].x, f[0].y, f[0].z] for f in frames])
    Lv = np.array([[f[1].x, f[1].y, f[1].z] for f in frames])
    surf = P + Mv[:, None, :] * (np.cos(ph) * a)[..., None] + Lv[:, None, :] * (np.sin(ph) * a * aspect)[..., None]
    q = surf.reshape(-1, 3)
    n1 = fbm(q * 14.0, 4, seed=t.seed).reshape(nv, nu)
    tart = (1 - smoothstep(0.04, 0.2 + 0.08 * n1, tt)) * smoothstep(-0.05, 0.0, tt)
    lump = np.clip(n1 * 0.5 + 0.55, 0, 1)
    disp += tart * lump * (0.006 + 0.018 * t.r)
    groove += tart * np.clip(0.5 - n1, 0, 1) * 0.9
    # 大尺度的轻微起伏（不是完美的数学圆锥）
    n2 = fbm(q * 2.2, 3, seed=t.seed + 7).reshape(nv, nu)
    disp += n2 * a * 0.035
    # 崩尖：牙尖一侧斜着崩掉一块，断口凹凸
    if t.chipped:
        cut = smoothstep(0.80, 0.97, tt) * np.clip(np.cos(ph - 1.2) * 1.4 - 0.2, 0, 1)
        rough = fbm(q * 30.0, 3, seed=t.seed + 3).reshape(nv, nu)
        disp -= cut * a * (0.55 + 0.25 * rough)
        ridge += cut * 0.8
        groove += cut * np.clip(rough, 0, 1) * 0.7
    # 裂纹：从牙尖往下一道细裂，弯弯曲曲
    if t.cracked:
        path = 0.9 + 0.25 * np.sin(tt * 9.0 + t.seed) + 0.1 * np.sin(tt * 23.0)
        dd = np.angle(np.exp(1j * (ph - path)))
        band = np.exp(-(dd / 0.03) ** 2) * smoothstep(0.35, 0.55, tt)
        disp -= band * (0.006 + 0.01 * t.r)
        groove += band
    return disp, np.clip(groove, 0, 1), np.clip(ridge, 0, 1)


def build_teeth(mb, teeth, high=False, upper=None):
    """把牙加进 MB（低模：UV0 绕牙一圈 / 从根到尖；高模：细节 + Curv / Area）。返回每颗牙的截面数据（领口用）。"""
    info = {}
    for t in teeth:
        if upper is not None and t.upper != upper:
            continue
        nu, nv, nr = _ring_counts(t, high)
        ls, pts, tans = t.centerline(nv, n_root=nr)
        frames = t.frames(pts, tans)
        phi = np.linspace(0, 2 * math.pi, nu, endpoint=False)
        ra = np.array([t.radius(l) for l in ls])
        asp = t.aspect
        # 牙尖最后一圈不要太小（避免零面积三角），牙尖单独一个点
        ra[-1] = max(ra[-1], t.r * 0.07)
        P = np.zeros((len(ls), nu, 3))
        for i, (p, (M, Lb)) in enumerate(zip(pts, frames)):
            Mv = np.array(M[:])
            Lv = np.array(Lb[:])
            P[i] = np.array(p[:])[None, :] + np.cos(phi)[:, None] * Mv * ra[i] + np.sin(phi)[:, None] * Lv * ra[i] * asp
        if high:
            disp, grv, rdg = tooth_detail(t, ls, phi, pts, frames, ra, asp)
            # 沿截面法向推（椭圆的法向）
            for i, (M, Lb) in enumerate(frames):
                Mv = np.array(M[:])
                Lv = np.array(Lb[:])
                nrm = np.cos(phi)[:, None] * Mv * asp + np.sin(phi)[:, None] * Lv
                nrm /= np.linalg.norm(nrm, axis=1)[:, None]
                P[i] += nrm * disp[i][:, None]
        # 牙尖：最后一圈之后再往前一点收成一个点
        tip = pts[-1] + tans[-1] * (ra[-1] * 1.5)
        rootc = pts[0] - tans[0] * (ra[0] * 0.5)
        uv = None
        if not high:
            # UV0：U 绕牙一圈（按周长，牙尖那头窄）、V 从牙根到牙尖（米）
            per = 2 * math.pi * ra * math.sqrt((1 + asp * asp) / 2)
            uu = (np.arange(nu + 1)[None, :] / nu - 0.5) * per[:, None]
            vv = (ls - ls[0])[:, None] * np.ones((1, nu + 1))
            uv = np.stack([uu, vv], axis=-1)
        ids = mb.grid(P, closed=True, mat=0, region=100, uv=uv, flip=True, weights={t.bone: 1.0})
        tip_i = mb.add_verts([tip[:]], {t.bone: 1.0})
        root_i = mb.add_verts([rootc[:]], {t.bone: 1.0})
        tris_tip = [[ids[-1, j], ids[-1, (j + 1) % nu], tip_i] for j in range(nu)]
        tris_root = [[ids[0, (j + 1) % nu], ids[0, j], root_i] for j in range(nu)]
        uvt = uvr = None
        if not high:
            vt = uv[-1, 0, 1] + ra[-1] * 1.5
            uvt = [[uv[-1, j], uv[-1, j + 1], (0.5 * (uv[-1, j, 0] + uv[-1, j + 1, 0]), vt)] for j in range(nu)]
            uvr = [[uv[0, j + 1], uv[0, j], (0.5 * (uv[0, j, 0] + uv[0, j + 1, 0]), -ra[0] * 0.5)] for j in range(nu)]
        mb.add_faces(tris_tip, region=100, mat=0, uv=uvt)
        mb.add_faces(tris_root, region=100, mat=0, uv=uvr)
        if high:
            nverts = P.shape[0] * P.shape[1]
            cv = np.zeros((nverts + 2, 4))
            cv[:nverts, 0] = grv.reshape(-1)
            cv[:nverts, 1] = rdg.reshape(-1)
            cv[nverts, 1] = 1.0
            cv[:, 3] = 1.0
            mb.add_attr("Curv", ids[0, 0], cv)
            ar = np.zeros((nverts + 2, 4))
            ar[:, 0] = 1.0
            ar[:, 3] = 1.0
            mb.add_attr("Area", ids[0, 0], ar)
        info[tag(t)] = dict(ls=ls, pts=pts, frames=frames, ra=ra)
    return info


def build_collars(mb, teeth, high=False):
    """每颗牙根周围一圈牙龈（领口）：内圈贴着牙、往外鼓一圈、外缘沉到牙床面以下。肉的材质，权重跟牙一样。"""
    for t in teeth:
        nu = 10 if t.L < 0.9 else (12 if t.L < 2 else 16)
        nrings = 3
        if high:
            nu *= 8
            nrings = 18
        phi = np.linspace(0, 2 * math.pi, nu, endpoint=False)
        ls, pts, tans = t.centerline(4, n_root=1)
        frames = t.frames(pts, tans)
        # 牙床脊处的截面（l = 0），往牙尖 0.06～0.12 米处收口
        hc = 0.03 + 0.18 * t.r
        p0 = t.crown_at(hc)
        p_base = t.B
        M, Lb = frames[1]
        Mv, Lv = np.array(M[:]), np.array(Lb[:])
        a0 = t.radius(hc)
        asp = t.aspect
        gapdir = np.array([0, 0, -1.0]) if t.upper else np.array([0, 0, 1.0])
        rows = []
        cols = []
        for k in range(nrings + 1):
            f = k / nrings
            # 剖面：从贴牙（f=0）→ 鼓起（f≈0.4）→ 外缘沉下去（f=1）
            rad = 1.02 + 0.85 * f ** 0.85
            lift = hc * (1 - f) ** 2.2 + 0.02 * math.sin(math.pi * min(f / 0.7, 1.0)) - 0.05 * f ** 3
            ring = []
            base = np.array(p_base[:]) * f + np.array(p0[:]) * (1 - f) if f < 1 else np.array(p_base[:])
            for ph in phi:
                off = (math.cos(ph) * Mv + math.sin(ph) * Lv * asp) * a0 * rad
                q = np.array(p_base[:]) + off
                # 落到牙床面上
                sq = spec.s_of(q[1])
                zs = ms.cavity_z(sq, q[0], t.upper)
                surf_z = zs
                z = surf_z + gapdir[2] * lift
                if f == 0:
                    # 内圈贴牙
                    pc = np.array(p0[:]) + (math.cos(ph) * Mv + math.sin(ph) * Lv * asp) * a0 * 1.03
                    ring.append(pc)
                    continue
                q = np.array([q[0], q[1], z])
                ring.append(q)
            rows.append(ring)
        P = np.array(rows)
        if high:
            q = P.reshape(-1, 3)
            n = fbm(q * 9.0, 4, seed=t.seed + 11).reshape(P.shape[:2])
            wr = ridged(q * np.array([5, 5, 5]) * 3.0, 2, seed=t.seed).reshape(P.shape[:2])
            P[..., 2] += gapdir[2] * (n * 0.012 + wr * 0.008) * np.linspace(0.2, 1, nrings + 1)[:, None]
        uv = None
        if not high:
            per = 2 * math.pi * a0 * np.linspace(1.0, 2.3, nrings + 1)
            uu = (np.arange(nu + 1)[None, :] / nu - 0.5) * per[:, None]
            vv = np.linspace(0, a0 * 1.6 + hc, nrings + 1)[:, None] * np.ones((1, nu + 1))
            uv = np.stack([uu, vv], axis=-1)
        ids = mb.grid(P, closed=True, mat=0, region=200 + len(mb.faces), uv=uv, weights={t.bone: 1.0})
        if high:
            nv = P.shape[0] * P.shape[1]
            q = P.reshape(-1, 3)
            f = np.repeat(np.linspace(0, 1, nrings + 1), nu)
            cv = np.zeros((nv, 4))
            cv[:, 0] = np.clip(1 - f * 4, 0, 1) * 0.9   # 贴牙那圈是沟
            cv[:, 1] = np.exp(-((f - 0.35) / 0.15) ** 2) * 0.4
            cv[:, 3] = 1
            mb.add_attr("Curv", ids[0, 0], cv)


def check(teeth, verbose=True):
    """自查：闭嘴时牙和牙之间、牙和对面的嘴腔面 / 外皮之间有没有穿插。返回问题列表。"""
    probs = []
    samp = {}
    for t in teeth:
        ls, pts, tans = t.centerline(24, n_root=4)
        samp[tag(t)] = (t, ls, pts)
    # 牙对牙
    keys = list(samp)
    for i in range(len(keys)):
        ti, li, pi = samp[keys[i]]
        for j in range(i + 1, len(keys)):
            tj, lj, pj = samp[keys[j]]
            if ti.side != tj.side:
                continue
            best = 1e9
            for a, la in zip(pi, li):
                if la < 0.05:
                    continue
                for b, lb in zip(pj, lj):
                    if lb < 0.05:
                        continue
                    dd = (a - b).length - ti.radius(la) - tj.radius(lb)
                    best = min(best, dd)
            if best < 0.04:
                probs.append(f"牙碰牙 {keys[i]}-{keys[j]} 间隙 {best:.2f}")
    # 牙对嘴腔面 / 外皮
    for k, (t, ls, pts) in samp.items():
        worst = 1e9
        what = ""
        for p, l in zip(pts, ls):
            r = t.radius(l)
            s = spec.s_of(p.y)
            if l < 0:
                lim = ms.outer_z(s, p.x, t.upper)
                m = (lim - p.z) if t.upper else (p.z - lim)
                if m - r < 0.02:
                    probs.append(f"牙根穿皮 {k} l={l:.2f} 余 {m - r:.2f}")
                sc = min(max(s, spec.JAW_FRONT_S), spec.JAW_HINGE_S)
                if l < -0.15 and abs(p.x) < ms.gum_x(max(sc, 0.0) if t.upper else sc, t.upper):
                    cz = ms.cavity_z(sc, p.x, t.upper)
                    inner = (p.z - cz) if t.upper else (cz - p.z)
                    if inner - r < 0.0:
                        probs.append(f"牙根钻出嘴腔面 {k} l={l:.2f} 余 {inner - r:.2f}")
                continue
            if l < 0.25:
                continue
            if t.name == "L1":
                continue
            if t.name == "L0":
                # 吻前：别碰上吻（上吻前面 s<0.01 的皮大概往前鼓 0.25）
                if p.y < spec.y_of(0.0) + 0.3 and p.z > spec.mouth_z(0.0) - 0.1:
                    probs.append(f"L0 太靠后 {k} y={p.y:.2f}")
                continue
            # 对面那半边嘴腔
            opp = not t.upper
            if abs(p.x) < ms.gum_x(max(s, 0.0), opp) - 0.05:
                cz = ms.cavity_z(s, p.x, opp)
                m = (cz - p.z) if opp else (p.z - cz)
                if m - r < worst:
                    worst = m - r
                    what = f"l={l:.2f}"
            else:
                # 在牙床线外侧：就是在唇里了
                d = abs(p.x) - ms.gum_x(max(s, 0.0), opp)
                gz = ms.gum_z(max(s, 0.0), opp)
                beyond = (gz - p.z) if opp else (p.z - gz)
                if beyond > -0.05:
                    probs.append(f"牙伸进对面的唇 {k} l={l:.2f} 外 {d:.2f}")
        if worst < 0.06:
            probs.append(f"牙顶到对面的嘴腔 {k} {what} 余 {worst:.2f}")
    if verbose:
        for p in probs:
            print("  [teeth]", p)
        for t in teeth:
            print("  tooth %-4s L=%.2f r=%.2f root=%.2f s=%.3f" % (tag(t), t.L, t.r, t.root_len, t.s))
    return probs
