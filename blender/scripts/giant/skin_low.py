"""皮的低模（进游戏）：头、身体、尾柄、下颌外侧一整张四边形网格，按 spec 的身体曲面放样。

布线：
  - 环（行）沿身体：头部约 0.19 米一环、身体约 0.3 米一环，渐变；行正好落在吻端、眼睛、嘴角铰链、每道鳃裂上；
  - 列绕身体一圈 120 列：每侧嘴线以上 36 段、以下 24 段，各自按弧长均分；嘴线（s < 铰链）是一条列线，
    沿它把皮切开：上面是上头，下面是下颌（同一张皮，铰链那一环以后连成一圈）；
  - 吻端：上头往前收成钝圆的吻，最前一排正好是上唇前缘；下颌往前伸出（地包天），最前一排是下唇前缘；
  - 唇：上下唇缘各往里卷三排到牙床线（spec.gum_point），嘴角铰链处上下两条唇卷用一小片肉连上（颊膜接在牙床线上）；
  - 鳃裂：每侧五道，鳃裂所在的环在鳃区斜 12°，沿环把皮切开，前唇往前、后唇（皮瓣）往后撑开一条缝，
    往里两面缝壁收到 0.4 米深的缝底（缝底一半用 M_GiantMouth）；
  - 眼窝：眼睛周围 8×8 格重排成同心圆：中间 4×4 往里压成眼窝（眼球挡住），一圈眼睑缘、一圈眼睑褶；
  - 唇缘外侧有一道肉鼓起来（唇的厚度），绕过嘴角。
UV0：接缝在腹中线、唇缘（唇卷单独成岛）、鳃裂缘（缝壁单独成岛）、眼睑缘（眼窝单独成岛），Blender 展开后交给 atlas_uv。
骨骼权重：脊椎骨按 s；下颌和下唇 = Jaw；铰链后面按「嘴角往后下方的楔形」渐变；鳃裂后唇 = GillL/GillR。"""
import math

import bmesh
import bpy
import numpy as np
from mathutils import Vector

from giant import spec
from giant import skin_np as snp

V = Vector
L = spec.LENGTH
H = spec.JAW_HINGE_S
JFS = spec.JAW_FRONT_S

N_UP, N_LO = 36, 24
NC = 2 * (N_UP + N_LO)          # 120 列
C_MR = N_UP                     # 右嘴线
C_BELLY = N_UP + N_LO           # 腹中线
C_ML = NC - N_UP                # 左嘴线
UPPER_COLS = list(range(C_ML, NC)) + list(range(0, C_MR + 1))     # 84..119, 0..36
LOWER_COLS = list(range(C_MR, C_ML + 1))                          # 36..84

DOME_S = 0.035      # 上吻往前收圆的长度（s）
CHIN_S = 0.028      # 下巴往前收圆的长度
LIP_BOW = 0.25      # 上唇前缘往前拱（米）
CHIN_BOW = 0.12
SNOUT_BULGE = 0.75   # 吻往前拱出唇缘（米）
CHIN_DROP = 0.40     # 下巴前段往下垫厚（米）
ROLL_T = (0.34, 0.68, 1.0)     # 唇卷三排

GILL_TILT = math.radians(12.0)
GILL_W = 0.13       # 鳃裂中间张开的宽度（米）
GILL_DEPTH = 0.42
EYE_BLOCK = 5       # 眼窝：中心 ±5 格

ROW_HEAD = 0.19
ROW_BODY = 0.33


def mt_of(s):
    return spec.mouth_theta(min(max(s, 0.0), H))


def dome(x):
    x = min(max(x, 0.0), 1.0)
    return math.sqrt(max(1.0 - (1.0 - x) ** 2, 0.0))


def smooth(a, b, x):
    t = min(max((x - a) / (b - a), 0.0), 1.0)
    return t * t * (3 - 2 * t)


# ---------------------------------------------------------------------------- 曲面
_TH = np.linspace(0.0, math.pi, 1441)


def col_thetas(s):
    """右侧 c = 0..C_BELLY 的 θ（嘴线以上 N_UP 段、以下 N_LO 段，各自按弧长均分）和每列离背中线的弧长。"""
    sc = min(max(s, 0.0), 1.0)
    P = snp.surface(np.full_like(_TH, sc), _TH)
    seg = np.linalg.norm(np.diff(P[:, [0, 2]], axis=0), axis=1)
    arc = np.concatenate([[0.0], np.cumsum(seg)])
    mt = mt_of(s)
    a_m = float(np.interp(mt, _TH, arc))
    up = np.interp(np.linspace(0.0, a_m, N_UP + 1), arc, _TH)
    lo = np.interp(np.linspace(a_m, arc[-1], N_LO + 1), arc, _TH)
    th = np.concatenate([up, lo[1:]])
    th[C_MR] = mt
    return th, np.interp(th, _TH, arc)


def theta_c(ths, c):
    c %= NC
    return float(ths[c]) if c <= C_BELLY else -float(ths[NC - c])


def arc_c(arcs, c):
    c %= NC
    return float(arcs[c]) if c <= C_BELLY else float(arcs[NC - c])


def hood_pos(s, th):
    """上头外皮：s < DOME_S 时往上唇前缘收成钝圆的吻，吻的中上部往前拱出唇缘（鲨鱼的吻盖在嘴上）。"""
    p = spec.surface(s, th)
    if s >= DOME_S:
        return p
    x = s / DOME_S
    f = dome(x)
    t = th / mt_of(s)
    lip = spec.lip_point(s, 1, True)
    lp = V((lip.x * t, spec.y_of(s) + LIP_BOW * (1 - t * t), lip.z))
    q = lp + (p - lp) * f
    q.y += SNOUT_BULGE * math.sin(math.pi * f) * max(1 - t * t, 0.0) ** 2
    return q


def jaw_pos(s, th):
    """下颌外皮：前段往下垫厚（下巴有肉），最前面 CHIN_S 往下唇前缘收成下巴。唇缘本身不动。"""
    p = spec.jaw_surface(s, th)
    mt = mt_of(s)
    thp = th % (2 * math.pi)
    t = (math.pi - thp) / (math.pi - mt)
    lip = spec.lip_point(s, 1, False)
    w = 1.0 - smooth(JFS + 0.004, 0.05, s)
    k = min(max((lip.z - p.z) / 0.8, 0.0), 1.0)
    p = p + V((0, 0, -CHIN_DROP * w * k))
    x = (s - JFS) / CHIN_S
    if x >= 1.0:
        return p
    f = (1.0 - (1.0 - x) ** 3) ** (1.0 / 3.0)
    lp = V((lip.x * t, spec.y_of(s) + CHIN_BOW * (1 - t * t), lip.z))
    return lp + (p - lp) * f


def body_normal(s, th, eps=1e-4):
    return spec.normal(min(max(s, 0.0), 1.0), th)


# ---------------------------------------------------------------------------- 行
def _rows(a, b, pos, thetas, h_fn, n_min=1):
    """在 [a, b] 之间按「表面长度 / 目标间距」均匀放行（取几条列里最长的那条量长度）。"""
    ss = np.linspace(a, b, 500)
    m = np.zeros(len(ss))
    eps = (b - a) / 2000.0
    for th in thetas:
        d = np.array([(pos(min(s + eps, b), th) - pos(max(s - eps, a), th)).length /
                      (min(s + eps, b) - max(s - eps, a)) for s in ss])
        m = np.maximum(m, d)
    hh = np.array([h_fn(s) for s in ss])
    c = np.concatenate([[0.0], np.cumsum(0.5 * (m[1:] / hh[1:] + m[:-1] / hh[:-1]) * np.diff(ss))])
    n = max(n_min, int(round(c[-1])))
    return [float(x) for x in np.interp(np.linspace(0.0, c[-1], n + 1), c, ss)]


def _h_body(s):
    return ROW_HEAD + (ROW_BODY - ROW_HEAD) * smooth(0.30, 0.42, s)


def eye_metric():
    th = spec.EYE_THETA
    eps = 1e-4
    ms = (spec.surface(spec.EYE_S + eps, th) - spec.surface(spec.EYE_S - eps, th)).length / (2 * eps)
    mt = (spec.surface(spec.EYE_S, th + eps) - spec.surface(spec.EYE_S, th - eps)).length / (2 * eps)
    return ms, mt


def make_rows():
    ms, _ = eye_metric()
    de = ROW_HEAD / ms
    e0, e1 = spec.EYE_S - EYE_BLOCK * de, spec.EYE_S + EYE_BLOCK * de
    mt0 = mt_of(0.0)
    hood_th = [0.0, 0.45 * mt0, 0.85 * mt0]
    hood = _rows(0.0, e0, hood_pos, hood_th, lambda s: ROW_HEAD)
    hood += [spec.EYE_S + k * de for k in range(-EYE_BLOCK + 1, EYE_BLOCK + 1)]
    hood += _rows(e1, H, hood_pos, hood_th, lambda s: ROW_HEAD)[1:]
    jaw_th = [math.pi, math.pi - 0.5 * (math.pi - mt0)]
    jaw = _rows(JFS, H, jaw_pos, jaw_th, lambda s: ROW_HEAD)
    g0, g1 = spec.GILL_S[0] - 0.006, spec.GILL_S[-1] + 0.006
    gills = [g0 + 0.006 * k for k in range(int(round((g1 - g0) / 0.006)) + 1)]
    body_th = [0.0, math.pi / 2, math.pi]
    body = _rows(H, g0, spec.surface, body_th, _h_body)
    body += gills[1:]
    body += _rows(g1, 1.0, spec.surface, body_th, _h_body)[1:]
    return hood, jaw, body


# ---------------------------------------------------------------------------- 鳃区斜环
def _gill_arc():
    ths, arcs = col_thetas(spec.GILL_S[2])
    return float(np.interp(spec.GILL_THETA, ths[:C_BELLY + 1], arcs[:C_BELLY + 1]))


def gill_tilt(sig, arc, a_g):
    """鳃区里环往后斜 12°（上端往后、下端往前）：返回 s 的偏移。"""
    band = smooth(spec.GILL_S[0] - 0.034, spec.GILL_S[0] - 0.008, sig) * \
        (1.0 - smooth(spec.GILL_S[-1] + 0.008, spec.GILL_S[-1] + 0.034, sig))
    da = arc - a_g
    band *= 1.0 - smooth(1.4, 2.8, abs(da))
    return -da * math.tan(GILL_TILT) / L * band


# ---------------------------------------------------------------------------- 网格容器
class Mesh:
    def __init__(self):
        self.P = []
        self.meta = []
        self.F = []
        self.fmat = []
        self.seams = set()
        self.crease = set()     # 唇缘、鳃裂缘、眼睑缘：高模细分时半硬，圆角不至于把唇吃掉

    def v(self, p, **kw):
        self.P.append(V(p))
        self.meta.append(kw)
        return len(self.P) - 1

    def f(self, idx, mat=0):
        out = []
        for i in idx:
            if i not in out:
                out.append(i)
        if len(out) >= 3:
            self.F.append(out)
            self.fmat.append(mat)

    def seam(self, a, b, crease=False):
        if a != b:
            self.seams.add((min(a, b), max(a, b)))
            if crease:
                self.crease.add((min(a, b), max(a, b)))

    def vertex_normals(self):
        n = [V((0, 0, 0)) for _ in self.P]
        for f in self.F:
            pts = [self.P[i] for i in f]
            fn = V((0, 0, 0))
            for k in range(len(pts)):
                fn += pts[k].cross(pts[(k + 1) % len(pts)])
            for i in f:
                n[i] += fn
        return [x.normalized() if x.length > 1e-12 else V((0, 0, 1)) for x in n]


# ---------------------------------------------------------------------------- 主体
def build_mesh():
    m = Mesh()
    hood_rows, jaw_rows, body_rows = make_rows()
    a_g = _gill_arc()
    nb = len(body_rows)

    # 身体（铰链那一环开始，整圈）
    B = {}
    body_ths = []
    for k, sig in enumerate(body_rows):
        ths, arcs = col_thetas(sig)
        body_ths.append(ths)
        for c in range(NC):
            th = theta_c(ths, c)
            s = sig + gill_tilt(sig, arc_c(arcs, c), a_g)
            B[(k, c)] = m.v(spec.surface(s, th), part="body", s=s, th=th, row=k, col=c)
    # 上头（最后一行就是身体第 0 环）
    nh = len(hood_rows)
    Hd = {}
    for i, s in enumerate(hood_rows):
        if i == nh - 1:
            for c in UPPER_COLS:
                Hd[(i, c)] = B[(0, c)]
            continue
        ths, _ = col_thetas(s)
        for c in UPPER_COLS:
            th = theta_c(ths, c)
            Hd[(i, c)] = m.v(hood_pos(s, th), part="hood", s=s, th=th, row=i, col=c)
    # 下颌
    nj = len(jaw_rows)
    J = {}
    for j, s in enumerate(jaw_rows):
        if j == nj - 1:
            for c in LOWER_COLS:
                J[(j, c)] = B[(0, c)]
            continue
        ths, _ = col_thetas(s)
        for c in LOWER_COLS:
            th = theta_c(ths, c)
            J[(j, c)] = m.v(jaw_pos(s, th), part="jaw", s=s, th=th, row=j, col=c)

    ctx = dict(m=m, B=B, Hd=Hd, J=J, hood_rows=hood_rows, jaw_rows=jaw_rows, body_rows=body_rows,
               nb=nb, nh=nh, nj=nj, body_ths=body_ths, a_g=a_g)
    eye_block(ctx)
    pdup = gill_open(ctx)

    def bv(k, c, behind):
        if behind and (k, c % NC) in pdup:
            return pdup[(k, c % NC)]
        return B[(k, c % NC)]

    # 面：上头
    for i in range(nh - 1):
        for a, b in zip(UPPER_COLS[:-1], UPPER_COLS[1:]):
            m.f([Hd[(i, a)], Hd[(i + 1, a)], Hd[(i + 1, b)], Hd[(i, b)]])
    # 下颌
    for j in range(nj - 1):
        for a, b in zip(LOWER_COLS[:-1], LOWER_COLS[1:]):
            m.f([J[(j, a)], J[(j + 1, a)], J[(j + 1, b)], J[(j, b)]])
        m.seam(J[(j, C_BELLY)], J[(j + 1, C_BELLY)])
    # 身体
    for k in range(nb - 1):
        for c in range(NC):
            m.f([bv(k, c, True), bv(k + 1, c, False), bv(k + 1, c + 1, False), bv(k, c + 1, True)])
        m.seam(B[(k, C_BELLY)], B[(k + 1, C_BELLY)])
    tail_cap(ctx)
    lip_bead(ctx)
    gill_pockets(ctx, pdup)
    lips(ctx)
    return m, ctx


# ---------------------------------------------------------------------------- 尾端
def tail_cap(ctx):
    m, B, nb = ctx["m"], ctx["B"], ctx["nb"]
    c0 = spec.center(1.0)
    ring = []
    for c in range(NC):
        p = m.P[B[(nb - 1, c)]]
        q = c0 + (p - c0) * 0.55 + V((0, -0.22, 0))
        ring.append(m.v(q, part="body", s=1.0, th=m.meta[B[(nb - 1, c)]]["th"]))
    pole = m.v(c0 + V((0, -0.32, 0)), part="body", s=1.0, th=0.0)
    for c in range(NC):
        c1 = (c + 1) % NC
        m.f([B[(nb - 1, c)], ring[c], ring[c1], B[(nb - 1, c1)]])
        m.f([ring[c], pole, ring[c1]])
    m.seam(B[(nb - 1, C_BELLY)], ring[C_BELLY])
    m.seam(ring[C_BELLY], pole)


# ---------------------------------------------------------------------------- 眼窝
def _square_loop(l):
    """边长 2l 的方框一圈（逆时针，从 (l, 0) 起）。"""
    pts = []
    for j in range(0, l):
        pts.append((l, j))
    for i in range(l, -l, -1):
        pts.append((i, l))
    for j in range(l, -l, -1):
        pts.append((-l, j))
    for i in range(-l, l):
        pts.append((i, -l))
    for j in range(-l, 0):
        pts.append((l, j))
    return pts


EYE_R = {0: 0.0, 1: 0.24, 2: 0.395, 3: 0.56, 4: 0.80}
EYE_H = {0: -0.30, 1: -0.20, 2: 0.055, 3: 0.05, 4: 0.0}
EYE_BLEND = {3: 0.85, 4: 0.45}   # 外两圈：往圆上靠多少（其余留在原来的网格上）


def eye_block(ctx):
    m, Hd, hood_rows = ctx["m"], ctx["Hd"], ctx["hood_rows"]
    ie = int(np.argmin([abs(s - spec.EYE_S) for s in hood_rows]))
    ths, _ = col_thetas(spec.EYE_S)
    ce = int(np.argmin([abs(ths[c] - spec.EYE_THETA) for c in range(C_MR)]))
    ms, mtm = eye_metric()
    ctx["eye_rim"] = {}
    ctx["eye_level"] = {}
    for side in (-1, 1):
        ang = {}
        for l in range(1, EYE_BLOCK):
            loop = _square_loop(l)
            for k, ij in enumerate(loop):
                ang[ij] = 2 * math.pi * k / len(loop)
        rim = []
        for j in range(-EYE_BLOCK, EYE_BLOCK + 1):
            for i in range(-EYE_BLOCK, EYE_BLOCK + 1):
                lvl = max(abs(i), abs(j))
                c = ce + i if side > 0 else NC - (ce + i)
                vi = Hd[(ie + j, c)]
                m.meta[vi]["eye"] = (side, lvl)
                ctx["eye_level"][vi] = (side, lvl)
                if lvl >= EYE_BLOCK:
                    continue
                phi = ang.get((i, j), 0.0)
                r = EYE_R[lvl]
                # 眼形略呈杏仁形：沿身体方向长一点
                a = r * math.cos(phi) * 0.93
                b = r * math.sin(phi) * 1.07
                s = spec.EYE_S + b / ms
                th = side * (spec.EYE_THETA + a / mtm)
                h = EYE_H[lvl]
                if lvl == 3:
                    # 眼睑褶：上（背侧，a < 0）厚一点
                    h *= 1.0 + 0.45 * max(-math.cos(phi), 0.0)
                p = spec.surface(s, th) + spec.normal(s, th) * h
                if lvl in EYE_BLEND:
                    bl = EYE_BLEND[lvl]
                    p = m.P[vi].lerp(p - spec.normal(s, th) * h, bl) + spec.normal(s, th) * h
                m.P[vi] = p
                m.meta[vi]["s"] = s
                m.meta[vi]["th"] = th
                if lvl == 2:
                    rim.append((math.atan2(j, i), vi))
        rim.sort()
        ctx["eye_rim"][side] = [v for _, v in rim]
        loop = ctx["eye_rim"][side]
        for k in range(len(loop)):
            m.seam(loop[k], loop[(k + 1) % len(loop)], crease=True)
    # 眼睛周围很浅的一圈凹（小眼窝）
    for side in (-1, 1):
        ec = spec.eye_center(side)
        for vi, mt_ in enumerate(m.meta):
            if mt_.get("part") != "hood":
                continue
            if "eye" in mt_ and mt_["eye"][1] < EYE_BLOCK:
                continue
            d = (m.P[vi] - ec).length
            if d < 2.2:
                n = spec.normal(mt_["s"], mt_["th"])
                m.P[vi] = m.P[vi] - n * 0.035 * math.exp(-(d / 0.95) ** 2)


# ---------------------------------------------------------------------------- 鳃裂
def gill_slits(ctx):
    """每道鳃裂：(side, k, 行号, c0, c1)，c 是右侧的列号（左侧镜像）。"""
    body_rows = ctx["body_rows"]
    out = []
    for k, gs in enumerate(spec.GILL_S):
        kr = int(np.argmin([abs(s - gs) for s in body_rows]))
        ths, arcs = col_thetas(gs)
        a_c = float(np.interp(spec.GILL_THETA, ths[:C_BELLY + 1], arcs[:C_BELLY + 1]))
        half = spec.GILL_LENGTH[k] / 2.0
        ac = arcs[:C_BELLY + 1]
        c0 = int(np.argmin(np.abs(ac - (a_c - half))))
        c1 = int(np.argmin(np.abs(ac - (a_c + half))))
        for side in (-1, 1):
            out.append((side, k, kr, c0, c1))
    return out


def _col(side, c):
    return c if side > 0 else (NC - c) % NC


def gill_open(ctx):
    """把鳃裂所在的环沿裂缝拆开：原来的顶点当前唇（往前挪），新的一份当后唇（往后挪、往外翘一点）。"""
    m, B = ctx["m"], ctx["B"]
    pdup = {}
    ctx["slits"] = []
    for side, k, kr, c0, c1 in gill_slits(ctx):
        A, P = [], []
        for c in range(c0, c1 + 1):
            cc = _col(side, c)
            vi = B[(kr, cc)]
            u = (c - c0) / (c1 - c0)
            prof = math.sin(math.pi * u)
            if c in (c0, c1):
                A.append(vi)
                P.append(vi)
                continue
            fwd = (m.P[B[(kr - 1, cc)]] - m.P[B[(kr + 1, cc)]]).normalized()
            mt_ = m.meta[vi]
            n = spec.normal(mt_["s"], mt_["th"])
            w = GILL_W * prof ** 0.7
            base = m.P[vi].copy()
            m.P[vi] = base + fwd * (w * 0.45) - n * 0.012 * prof
            # 后唇 = 皮瓣（GillL/R 绕裂缝像门一样往外翻）：缝边 1.0，往后 0.25 米 0.45，再往后（下一道的前唇）0
            pv = m.v(base - fwd * (w * 0.55) + n * 0.04 * prof ** 0.6, part="body", s=mt_["s"], th=mt_["th"],
                     row=kr, col=cc, gflap=prof ** 0.3, gside=side)
            m.meta[vi]["gill_front"] = True
            pdup[(kr, cc)] = pv
            A.append(vi)
            P.append(pv)
            m.meta[B[(kr + 1, cc)]]["gflap"] = 0.45 * prof ** 0.3
            m.meta[B[(kr + 1, cc)]]["gside"] = side
            if k == len(spec.GILL_S) - 1:
                m.meta[B[(kr + 2, cc)]]["gflap"] = 0.12 * prof ** 0.3
                m.meta[B[(kr + 2, cc)]]["gside"] = side
        for a, b in zip(A[:-1], A[1:]):
            m.seam(a, b, crease=True)
        for a, b in zip(P[:-1], P[1:]):
            m.seam(a, b, crease=True)
        ctx["slits"].append(dict(side=side, k=k, kr=kr, c0=c0, c1=c1, A=A, P=P))
    return pdup


def gill_pockets(ctx, pdup):
    """鳃裂往里的缝：前唇、后唇各往里一排，收到缝底一条线（缝底那一半用 M_GiantMouth）。"""
    m = ctx["m"]
    for sl in ctx["slits"]:
        A, P = sl["A"], sl["P"]
        n_ = len(A)
        A1, P1, Bt = [], [], []
        for idx in range(n_):
            if idx in (0, n_ - 1):
                A1.append(A[idx])
                P1.append(P[idx])
                Bt.append(A[idx])
                continue
            u = idx / (n_ - 1)
            prof = math.sin(math.pi * u) ** 0.5
            mt_ = m.meta[A[idx]]
            n = spec.normal(mt_["s"], mt_["th"])
            pa, pp = m.P[A[idx]], m.P[P[idx]]
            mid = (pa + pp) * 0.5
            fwd = (pa - pp).normalized()
            d = GILL_DEPTH * prof
            A1.append(m.v(pa.lerp(mid, 0.3) - n * d * 0.42 + fwd * 0.02, part="pocket", s=mt_["s"], th=mt_["th"],
                          gside=sl["side"], gflap=0.0))
            P1.append(m.v(pp.lerp(mid, 0.3) - n * d * 0.42, part="pocket", s=mt_["s"], th=mt_["th"],
                          gside=sl["side"], gflap=0.8 * prof))
            Bt.append(m.v(mid - n * d + fwd * 0.08 * prof, part="pocket", s=mt_["s"], th=mt_["th"],
                          gside=sl["side"], gflap=0.4 * prof, deep=True))
        for i in range(n_ - 1):
            m.f([A[i], A1[i], A1[i + 1], A[i + 1]], 0)
            m.f([A1[i], Bt[i], Bt[i + 1], A1[i + 1]], 1)
            m.f([P[i], P[i + 1], P1[i + 1], P1[i]], 0)
            m.f([P1[i], P1[i + 1], Bt[i + 1], Bt[i]], 1)
        sl["A1"], sl["P1"], sl["Bt"] = A1, P1, Bt


# ---------------------------------------------------------------------------- 唇
def lip_lines(n=700):
    """上下唇缘的采样点（含前缘），给唇鼓包、高模细节量距离。"""
    up, lo = [], []
    mt0 = mt_of(0.0)
    for side in (-1, 1):
        for s in np.linspace(0.0, H, n):
            up.append(spec.lip_point(float(s), side, True))
        for s in np.linspace(JFS, H, n):
            lo.append(spec.lip_point(float(s), side, False))
    for t in np.linspace(-1, 1, 240):
        up.append(hood_pos(0.0, float(t) * mt0))
        lo.append(jaw_pos(JFS, math.pi - float(t) * (math.pi - mt0)))
    return up, lo


def lip_bead(ctx):
    """唇缘外侧鼓起一道肉（唇的厚度），绕过嘴角往后渐没。唇缘本身不动。"""
    m = ctx["m"]
    up, lo = lip_lines()
    pts = np.array([tuple(p) for p in up + lo])
    idx = [i for i, mt_ in enumerate(m.meta) if mt_.get("part") in ("hood", "jaw", "body")
           and mt_.get("s", 1) < H + 0.06 and "eye" not in mt_]
    if not idx:
        return
    P = np.array([tuple(m.P[i]) for i in idx])
    d, _ = snp.nearest(P, pts)
    nrm = m.vertex_normals()
    d0 = 0.30
    for i, dist in zip(idx, d):
        s = m.meta[i]["s"]
        fade = 1.0 - smooth(H, H + 0.025, s)
        fade *= 0.3 + 0.7 * (1.0 - smooth(H - 0.05, H, s))   # 到嘴角唇鼓包变小，裂缝收住
        o = 0.11 * (dist / d0) * math.exp(1.0 - dist / d0) * fade
        if o > 1e-4:
            m.P[i] = m.P[i] + nrm[i] * o


def _roll(m, chain, gums, part, jawv):
    """唇缘一串顶点往里卷到牙床线：每个点三排，二次贝塞尔（先水平往里，再往牙床拐）。"""
    rows = [chain]
    rr = []
    for b, g in zip(chain, gums):
        lp = m.P[b]
        dh = g - lp
        hz = V((dh.x, dh.y, 0.0))
        c = lp + hz * 0.62 + V((0, 0, dh.z * 0.12))
        seq = []
        for t in ROLL_T:
            p = lp * (1 - t) ** 2 + c * (2 * t * (1 - t)) + g * (t * t)
            seq.append(m.v(p, part=part, s=m.meta[b]["s"], th=m.meta[b].get("th", 0.0), jaw=jawv,
                           roll=t, gum=(t >= 1.0)))
        rr.append(seq)
    for k in range(len(ROLL_T)):
        rows.append([seq[k] for seq in rr])
    for i in range(len(chain) - 1):
        for k in range(len(ROLL_T)):
            m.f([rows[k][i], rows[k + 1][i], rows[k + 1][i + 1], rows[k][i + 1]])
        m.seam(chain[i], chain[i + 1], crease=True)
    return rows


def lips(ctx):
    m, Hd, J = ctx["m"], ctx["Hd"], ctx["J"]
    hood_rows, jaw_rows = ctx["hood_rows"], ctx["jaw_rows"]
    nh, nj = ctx["nh"], ctx["nj"]
    mt0 = mt_of(0.0)
    # 上唇：右嘴角 → 右侧唇缘往前 → 前缘 → 左侧往后 → 左嘴角
    chain, gums = [], []
    for i in reversed(range(nh)):
        chain.append(Hd[(i, C_MR)])
        gums.append(spec.gum_point(hood_rows[i], 1, True))
    g0 = spec.gum_point(0.0, 1, True)
    front_cols = list(range(C_MR - 1, 0, -1)) + [0] + list(range(NC - 1, C_ML, -1))
    ths, _ = col_thetas(0.0)
    for c in front_cols:
        t = theta_c(ths, c) / mt0
        chain.append(Hd[(0, c)])
        gums.append(V((g0.x * t, spec.HALF, g0.z)))
    for i in range(nh):
        chain.append(Hd[(i, C_ML)])
        gums.append(spec.gum_point(hood_rows[i], -1, True))
    up = _roll(m, chain, gums, "uroll", 0.0)
    ic = chain.index(Hd[(0, 0)])
    for k in range(len(ROLL_T)):
        m.seam(up[k][ic], up[k + 1][ic])
    # 下唇：右嘴角 → 往前 → 下巴前缘 → 左侧往后
    chain, gums = [], []
    for j in reversed(range(nj)):
        chain.append(J[(j, C_MR)])
        gums.append(spec.gum_point(jaw_rows[j], 1, False))
    g0 = spec.gum_point(JFS, 1, False)
    for c in range(C_MR + 1, C_ML):
        thp = theta_c(col_thetas(JFS)[0], c) % (2 * math.pi)
        t = (math.pi - thp) / (math.pi - mt0)
        chain.append(J[(0, c)])
        gums.append(V((g0.x * t, spec.y_of(JFS), g0.z)))
    for j in range(nj):
        chain.append(J[(j, C_ML)])
        gums.append(spec.gum_point(jaw_rows[j], -1, False))
    lo = _roll(m, chain, gums, "lroll", 1.0)
    ic = chain.index(J[(0, C_BELLY)])
    for k in range(len(ROLL_T)):
        m.seam(lo[k][ic], lo[k + 1][ic])
    # 嘴角：上下两条唇卷在铰链那一环用一小片肉连起来（最外一条边是上牙床 → 下牙床，颊膜接这里）
    ctx["corner_web"] = {}
    for side, iu, il in ((1, 0, 0), (-1, -1, -1)):
        U = [up[k][iu] for k in range(len(up))]
        Lw = [lo[k][il] for k in range(len(lo))]
        for k in range(1, len(U)):
            m.meta[U[k]]["web"] = True
            m.meta[Lw[k]]["web"] = True
        for k in range(len(U) - 1):
            m.f([U[k], U[k + 1], Lw[k + 1], Lw[k]])
        ctx["corner_web"][side] = (U, Lw)
    ctx["lip_up"], ctx["lip_lo"] = up, lo


# ---------------------------------------------------------------------------- 权重
def jaw_weight(p):
    """铰链后面的皮分给 Jaw 多少：嘴角往后下方的楔形（正下方全给、沿嘴线往后不给），往后 3 米渐没。"""
    h = spec.jaw_hinge()
    behind = h.y - p.y
    depth = h.z - p.z
    if depth <= 0.0:
        return 0.0
    a = math.atan2(depth, max(behind, 1e-6))
    return smooth(math.radians(18), math.radians(70), a) * (1.0 - smooth(0.0, 3.0, max(behind, 0.0)))


def weights(m):
    """每个顶点 → {骨名: 权重}"""
    out = []
    for p, mt_ in zip(m.P, m.meta):
        part = mt_.get("part")
        if part in ("jaw", "lroll"):
            wj = 1.0
        elif part in ("hood", "uroll"):
            wj = 0.0
        else:
            wj = jaw_weight(p)
        wg = mt_.get("gflap", 0.0)
        tot = wj + wg
        if tot > 1.0:
            wj, wg = wj / tot, wg / tot
        rest = 1.0 - wj - wg
        w = {}
        for name, x in spec.spine_weights(spec.s_of(p.y)):
            if x * rest > 1e-4:
                w[name] = w.get(name, 0.0) + x * rest
        if wj > 1e-4:
            w["Jaw"] = wj
        if wg > 1e-4:
            w["GillR" if mt_.get("gside", 1) > 0 else "GillL"] = wg
        out.append(w)
    return out


# ---------------------------------------------------------------------------- 出物体
def to_object(m, coll, name="Skin"):
    bm = bmesh.new()
    vs = [bm.verts.new(p) for p in m.P]
    bm.verts.index_update()
    bm.verts.ensure_lookup_table()
    for f, mat in zip(m.F, m.fmat):
        try:
            face = bm.faces.new([vs[i] for i in f])
        except ValueError:
            print("WARNING skin: 重复的面", f)
            continue
        face.material_index = mat
        face.smooth = True
    bm.edges.ensure_lookup_table()
    for e in bm.edges:
        a, b = e.verts[0].index, e.verts[1].index
        if (min(a, b), max(a, b)) in m.seams:
            e.seam = True
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    # 朝外检查：身体面法线应该背离中轴
    bm.normal_update()
    score = 0.0
    for f in list(bm.faces)[::7]:
        c = f.calc_center_median()
        s = spec.s_of(c.y)
        if 0.3 < s < 0.9:
            score += f.normal.dot(c - spec.center(s))
    if score < 0:
        bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    me.materials.append(bpy.data.materials["M_GiantSkin"])
    me.materials.append(bpy.data.materials["M_GiantMouth"])
    return ob


def unwrap(ob):
    me = ob.data
    if spec.UV_MAIN not in me.uv_layers:
        me.uv_layers.new(name=spec.UV_MAIN)
    me.uv_layers.active = me.uv_layers[spec.UV_MAIN]
    bpy.ops.object.select_all(action='DESELECT')
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.unwrap(method='MINIMUM_STRETCH', fill_holes=True, margin=0.002, iterations=40)
    bpy.ops.object.mode_set(mode='OBJECT')


def assign_weights(ob, m):
    ws = weights(m)
    groups = {}
    for vi, w in enumerate(ws):
        for name, x in w.items():
            g = groups.get(name)
            if g is None:
                g = groups[name] = ob.vertex_groups.new(name=name)
            g.add([vi], x, 'REPLACE')


def build(coll):
    m, ctx = build_mesh()
    ob = to_object(m, coll)
    unwrap(ob)
    spec.set_body_uv(ob)
    assign_weights(ob, m)
    return ob, m, ctx
