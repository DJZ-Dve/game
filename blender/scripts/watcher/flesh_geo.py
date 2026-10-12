"""肉的参数化形体（numpy）：身体那层肉 + 眼窝（同一张绕眼轴旋转的网格）、上下眼睑、腹面虹吸口。
低模和高模用同一套函数，只是采样密度不同：低模的采样点正好是高模采样点的子集，所以高模天然贴着低模。

眼窝和眼睑的结构（以眼球中心为原点的半径 ρ，从里往外）：
  眼球 4.4（前面的角膜最多鼓到 4.9）
  结膜（眼窝底，静止，Body）：ρ 4.45～4.88，只在离眼轴 77° 以外（眼球转 25° 时角膜也碰不到的地方）
  眼睑（刚性，LidUp / LidLo）：内表面 R_IN = 4.98（闭眼扫过角膜也不碰），外表面 5.1～5.55（睑缘再厚 0.2）
  眼眶唇（静止）：口袋顶 ≥ 眼睑扫过那里的最大半径 + 8 厘米，往外卷成一圈厚唇，再往后接到甲壳边缘下面的身体
闭眼 = 两片眼睑绕过眼心的 X 轴各转 LID_CLOSE，从唇下的口袋里滑出来，在眼轴下方 5° 合拢（重叠 1.5°，压出一道肉缝）。
眼睑根部（权重从 1 过渡到 0、混合 Body）一直藏在口袋深处：线性蒙皮转 75° 会把过渡带往里缩两成，只缩在看不见的地方。

坐标：眼心系 (θ, β)：θ = 离眼轴（+Y）的角度，β = 绕眼轴的方位（0 = +X 右，90° = +Z 上）。
      眼睑系 (ψ, φ)：ψ = 离 +X 轴的角度，φ = 绕 X 轴的角度（0 = +Y 正前，90° = +Z 上）；闭眼只改 φ。
"""
import math

import numpy as np

from watcher import spec

D = math.radians
E = np.array(spec.EYE_CENTER, dtype=np.float64)
AXES = np.array([spec.AX, spec.AY, spec.AZ], dtype=np.float64)

R_EYE = spec.EYE_R
CORNEA = 0.5                    # 角膜最多比眼球鼓出多少（spec：0.3～0.5）
R_IN = R_EYE + CORNEA + 0.08    # 眼睑内表面
FLOOR = R_IN - 0.10             # 结膜（眼窝底）
GAP = 0.08                      # 口袋顶比眼睑扫过的最大半径再高多少
CLOSE = spec.LID_CLOSE
PHI_MEET = D(-5.0)              # 闭眼时上下睑缘在哪合拢（略低于眼轴）
OVERLAP = D(1.5)                # 合拢时上下睑缘互相压进去多少
PHI_UP = PHI_MEET + CLOSE - OVERLAP / 2     # 上睑缘（睁眼）≈ 69.3°（闭眼时越过合缝线 0.75°）
PHI_LO = PHI_MEET - CLOSE + OVERLAP / 2     # 下睑缘（睁眼）≈ -79.3°
PSI0 = D(10.0)                  # 眼睑两头（内外眼角）离 X 轴的角度
FLOOR_EDGE = D(77.5)            # 结膜前缘（离眼轴）
FUNDUS = D(14.0)                # 口袋深度（从唇往后）


def smoothstep(a, b, x):
    t = np.clip((np.asarray(x, dtype=np.float64) - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


# ---------------------------------------------------------------------------- 方向、椭球
def eye_dir(th, be):
    th, be = np.broadcast_arrays(np.asarray(th, dtype=np.float64), np.asarray(be, dtype=np.float64))
    return np.stack([np.sin(th) * np.cos(be), np.cos(th), np.sin(th) * np.sin(be)], axis=-1)


def lid_dir(psi, phi):
    psi, phi = np.broadcast_arrays(np.asarray(psi, dtype=np.float64), np.asarray(phi, dtype=np.float64))
    return np.stack([np.cos(psi), np.sin(psi) * np.cos(phi), np.sin(psi) * np.sin(phi)], axis=-1)


def theta_beta(d):
    d = d / np.linalg.norm(d, axis=-1, keepdims=True)
    return np.arccos(np.clip(d[..., 1], -1, 1)), np.arctan2(d[..., 2], d[..., 0])


def psi_phi(q):
    """眼心系的向量 → (ψ, φ, ρ)。"""
    r = np.linalg.norm(q, axis=-1)
    return np.arccos(np.clip(q[..., 0] / np.maximum(r, 1e-9), -1, 1)), np.arctan2(q[..., 2], q[..., 1]), r


def ell_rho(d):
    """从眼心沿单位方向 d 到身体椭球面（spec.surface）的距离。"""
    a = ((d / AXES) ** 2).sum(-1)
    b = 2 * (E * d / AXES ** 2).sum(-1)
    c = ((E / AXES) ** 2).sum() - 1
    return (-b + np.sqrt(b * b - 4 * a * c)) / (2 * a)


def ell_normal(p):
    n = p / AXES ** 2
    return n / np.linalg.norm(n, axis=-1, keepdims=True)


def ell_project(p):
    """点 p 沿身体中心方向投到椭球面上。"""
    k = 1.0 / np.sqrt(((p / AXES) ** 2).sum(-1, keepdims=True))
    return p * k


def theta_at_body_angle(be, ang):
    """方位 β 上，眼心射线打到椭球面、且该点离 +Y（从身体中心看）的角度 = ang 时的 θ（二分）。"""
    be = np.asarray(be, dtype=np.float64)
    lo = np.full(be.shape, D(30))
    hi = np.full(be.shape, D(175))
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        d = eye_dir(mid, be)
        p = E + d * ell_rho(d)[..., None]
        a = np.arccos(np.clip(p[..., 1] / np.linalg.norm(p, axis=-1), -1, 1))
        big = a > ang
        hi = np.where(big, mid, hi)
        lo = np.where(big, lo, mid)
    return 0.5 * (lo + hi)


def theta_lip(be):
    """眼眶唇最前沿离眼轴的角度：两侧 80°，上 81°，下 88°（下睑露得少一点、下面的唇往后退一点）。"""
    s = np.sin(be)
    wob = 0.5 * np.sin(3 * be + 0.4) + 0.3 * np.sin(5 * be + 1.9) + 0.2 * np.sin(7 * be + 0.3)   # 不是正圆
    return D(80.0) + D(1.0) * np.maximum(s, 0) ** 2 + D(8.0) * np.maximum(-s, 0) ** 2 + D(1.3) * wob


# ---------------------------------------------------------------------------- 中心向 Catmull-Rom（向量化）
def catmull(Q, counts):
    """Q: (nb, K, 2) 控制点（含首尾各一个只管切线的虚点）；counts: K-3 个区间各采几点（含起点不含终点）。
    返回 (nb, sum(counts) + 1, 2)（最后补上终点）和每个采样点所在的区间号。"""
    out, seg = [], []
    for i, n in enumerate(counts):
        p0, p1, p2, p3 = Q[:, i], Q[:, i + 1], Q[:, i + 2], Q[:, i + 3]
        def dt(a, b):
            return np.maximum(np.linalg.norm(b - a, axis=-1) ** 0.5, 1e-4)[:, None, None]
        t0 = np.zeros_like(dt(p0, p1))
        t1 = t0 + dt(p0, p1)
        t2 = t1 + dt(p1, p2)
        t3 = t2 + dt(p2, p3)
        u = (np.arange(n) / n)[None, :, None]
        t = t1 + (t2 - t1) * u
        P0, P1, P2, P3 = (p[:, None, :] for p in (p0, p1, p2, p3))
        A1 = (t1 - t) / (t1 - t0) * P0 + (t - t0) / (t1 - t0) * P1
        A2 = (t2 - t) / (t2 - t1) * P1 + (t - t1) / (t2 - t1) * P2
        A3 = (t3 - t) / (t3 - t2) * P2 + (t - t2) / (t3 - t2) * P3
        B1 = (t2 - t) / (t2 - t0) * A1 + (t - t0) / (t2 - t0) * A2
        B2 = (t3 - t) / (t3 - t1) * A2 + (t - t1) / (t3 - t1) * A3
        out.append((t2 - t) / (t2 - t1) * B1 + (t - t1) / (t2 - t1) * B2)
        seg += [i] * n
    out.append(Q[:, -2][:, None, :])
    seg.append(len(counts))
    return np.concatenate(out, axis=1), np.array(seg)


# ---------------------------------------------------------------------------- 眼睑
def lid_cfg(lower):
    """(方向号, 睑缘 φ, 最大厚度, 睑缘加厚)"""
    return (-1.0, PHI_LO, 0.45, 0.16) if lower else (1.0, PHI_UP, 0.57, 0.22)


def lid_thick(psi, tmax):
    m = np.minimum(psi, math.pi - psi)
    return 0.12 + (tmax - 0.12) * smoothstep(PSI0, D(48), m)


def lid_rigid(psi, lower):
    """每个 ψ 上眼睑的刚性部分要伸到哪（φ）：闭眼后刚性部分的末端仍在眼眶唇下面 2.5° 以上。"""
    sg, phi_m, _, _ = lid_cfg(lower)
    steps = np.radians(np.arange(0.0, 160.0, 0.25))
    pc = (phi_m - sg * CLOSE) + sg * steps
    th, be = theta_beta(lid_dir(psi[:, None], pc[None, :]))
    ok = th >= theta_lip(be) + D(2.5)
    idx = np.where(~ok, np.arange(len(pc))[None, :], -1).max(1) + 1
    phi_r = pc[np.clip(idx, 0, len(pc) - 1)] + sg * CLOSE
    return sg * np.maximum(sg * phi_r, sg * phi_m + D(15))


def lid_bulge(psi, phi, lower):
    """睑缘加厚（只在睁眼时露在唇外面的那一截，滑进口袋的部分不加厚）。"""
    sg, phi_m, _, bmax = lid_cfg(lower)
    th, be = theta_beta(lid_dir(psi, phi))
    vis = smoothstep(theta_lip(be) - D(3), theta_lip(be) - D(7), th)
    prof = smoothstep(D(10), D(2.5), sg * (phi - phi_m))
    return bmax * vis * prof


def lid_grid(lower, n_psi, n_in, n_roll, n_out, n_bl, n_cap):
    """一片眼睑（静止 = 睁眼）。截面是一圈闭合的环：根部过渡带（内）、内表面（刚性末端 → 缘）、睑缘卷边、
    外表面（缘 → 刚性末端）、根部过渡带（外）、根部圆头。刚性末端 φ_r 正好是一圈顶点（权重 1 到这里为止）。
    返回 dict：P (n_psi+1, L, 3)、各点的 ψ、φ、ρ、部位 part（0 内 1 缘 2 外 3 根）、离睑缘的距离 dm（米）、
    卷边角 gam、蒙皮权重 w（1 = 刚性跟着眼睑骨）。"""
    sg, phi_m, tmax, _ = lid_cfg(lower)
    psi = PSI0 + (math.pi - 2 * PSI0) * np.arange(n_psi + 1) / n_psi
    phi_r = lid_rigid(psi, lower)
    phi_e = phi_r + sg * D(8)
    t = lid_thick(psi, tmax)
    sp = np.sin(psi)
    b_m = lid_bulge(psi, np.full_like(psi, phi_m), lower)
    r_m = 0.5 * (t + b_m)
    rho_c = R_IN + r_m
    phi_c = phi_m + sg * r_m / (rho_c * sp)
    cols = []   # 每段：(phi, rho, part, gam)

    def col(phi, rho, part, gam):
        cols.append((phi, rho, np.full(phi.shape, part, dtype=np.int8), gam))

    P1 = psi[:, None]
    half = np.full((len(psi), 1), -0.5 * math.pi)
    # 内表面：根部过渡带（φ_e → φ_r）、刚性部分（φ_r → 缘，靠缘处略密）
    u = (np.arange(n_bl) / n_bl)[None, :]
    ph = phi_e[:, None] + (phi_r - phi_e)[:, None] * u
    col(ph, np.full(ph.shape, R_IN), 0, np.broadcast_to(half, ph.shape).copy())
    u = np.arange(n_in) / n_in
    g = 1 - (1 - u) ** 1.35
    ph = phi_r[:, None] + (phi_c - phi_r)[:, None] * g[None, :]
    col(ph, np.full(ph.shape, R_IN), 0, np.broadcast_to(half, ph.shape).copy())
    # 睑缘卷边：从内侧绕过最前沿到外侧
    gam = -0.5 * math.pi + math.pi * np.arange(n_roll) / n_roll
    G = np.broadcast_to(gam[None, :], (len(psi), n_roll))
    ph = phi_c[:, None] - sg * r_m[:, None] * np.cos(G) / (rho_c[:, None] * sp[:, None])
    col(ph, rho_c[:, None] + r_m[:, None] * np.sin(G), 1, G.copy())
    # 外表面：缘 → 刚性末端（靠缘处略密）、根部过渡带
    u = np.arange(n_out) / n_out
    ph = phi_c[:, None] + (phi_r - phi_c)[:, None] * (u ** 1.3)[None, :]
    rho = R_IN + t[:, None] + lid_bulge(P1, ph, lower)
    col(ph, rho, 2, np.full(ph.shape, 0.5 * math.pi))
    u = (np.arange(n_bl) / n_bl)[None, :]
    ph = phi_r[:, None] + (phi_e - phi_r)[:, None] * u
    col(ph, R_IN + t[:, None] + 0 * ph, 2, np.full(ph.shape, 0.5 * math.pi))
    # 根部圆头：外 → 内
    gam = 0.5 * math.pi - math.pi * np.arange(n_cap) / n_cap
    G = np.broadcast_to(gam[None, :], (len(psi), n_cap))
    rc = 0.5 * t[:, None]
    ph = phi_e[:, None] + sg * rc * np.cos(G) / ((R_IN + rc) * sp[:, None])
    col(ph, R_IN + rc + rc * np.sin(G), 3, G.copy())

    phi = np.concatenate([c[0] for c in cols], axis=1)
    rho = np.concatenate([c[1] for c in cols], axis=1)
    part = np.concatenate([c[2] for c in cols], axis=1)
    gam = np.concatenate([c[3] for c in cols], axis=1)
    PSI = np.broadcast_to(P1, phi.shape).copy()
    P = E + rho[..., None] * lid_dir(PSI, phi)
    # 低频起伏：露在外面那截的外表面上两道顺着睑缘的浅沟
    dm = sg * (phi - phi_m) * rho * np.sin(PSI)
    outer = part == 2
    vis = smoothstep(D(10), D(5), sg * (phi - phi_m)) * smoothstep(PSI0, D(40), np.minimum(PSI, math.pi - PSI))
    gro = np.exp(-((dm - 0.48) / 0.09) ** 2) + 0.7 * np.exp(-((dm - 0.9) / 0.1) ** 2)
    hlow = np.where(outer, -0.035 * gro * vis, 0.0)
    w = np.where(sg * (phi - phi_r[:, None]) <= 1e-6, 1.0,
                 smoothstep(phi_e[:, None] * sg, phi_r[:, None] * sg, sg * phi))
    w = np.where(part == 3, 0.0, w)
    return dict(P=P, psi=PSI, phi=phi, rho=rho, part=part, gam=gam, dm=dm, w=w, hlow=hlow,
                sg=sg, lower=lower, phi_r=phi_r, phi_e=phi_e)


# ---------------------------------------------------------------------------- 口袋顶（眼睑扫过的包络）
_ROOF = {}


def _envelope():
    """眼睑外表面扫过的最大半径表：env[ψ°, φ°+180]（1° 一格），任何状态（睁 → 闭）。"""
    if "env" in _ROOF:
        return _ROOF["env"]
    env = np.zeros((181, 361))
    for lower in (False, True):
        L = lid_grid(lower, 160, 24, 18, 48, 4, 10)
        q = L["P"].reshape(-1, 3) - E
        psi, phi, r = psi_phi(q)
        pi = np.clip(np.round(np.degrees(psi)).astype(int), 0, 180)
        fi = np.clip(np.round(np.degrees(phi)).astype(int) + 180, 0, 360)
        T = np.zeros((181, 361))
        np.maximum.at(T, (pi, fi), r)
        # 扫掠：静止在 φ 的点闭眼时经过 [φ - 75°, φ]（上）或 [φ, φ + 75°]（下）
        S = np.zeros_like(T)
        n = int(round(math.degrees(CLOSE)))
        for k in range(n + 1):
            if not lower:
                S[:, :361 - k] = np.maximum(S[:, :361 - k], T[:, k:])
            else:
                S[:, k:] = np.maximum(S[:, k:], T[:, :361 - k])
        env = np.maximum(env, S)
    # 加宽一点（ψ ±3°、φ ±2°）
    out = env.copy()
    for dp in range(-3, 4):
        for df in range(-2, 3):
            out = np.maximum(out, np.roll(np.roll(env, dp, 0), df, 1))
    _ROOF["env"] = out
    return out


def env_at(p):
    env = _envelope()
    psi, phi, _ = psi_phi(p - E)
    pi = np.clip(np.round(np.degrees(psi)).astype(int), 0, 180)
    fi = np.clip(np.round(np.degrees(phi)).astype(int) + 180, 0, 360)
    return env[pi, fi]


def roof_rho(be):
    """方位 β 上口袋顶（含唇的内卷）的半径：唇到口袋底这一段里眼睑扫过的最大半径 + GAP，绕一圈平滑。"""
    if "tab" not in _ROOF:
        nb = 720
        bb = 2 * math.pi * np.arange(nb) / nb
        tl = theta_lip(bb)
        ths = tl[:, None] + np.radians(np.arange(-3.0, math.degrees(FUNDUS) + 4.0, 0.5))[None, :]
        d = eye_dir(ths, np.broadcast_to(bb[:, None], ths.shape))
        need = env_at(E + d * 5.3).max(1) + GAP
        need = np.maximum(need, FLOOR + 0.27)
        # 方位上先取邻域最大再平滑，最后再和原值取大（保证不低于需要的）
        m = need.copy()
        for k in range(-8, 9):
            m = np.maximum(m, np.roll(need, k))
        ker = np.exp(-(np.arange(-12, 13) / 6.0) ** 2)
        ker /= ker.sum()
        sm = sum(np.roll(m, k) * ker[k + 12] for k in range(-12, 13))
        _ROOF["tab"] = (bb, np.maximum(sm, need))
    bb, tab = _ROOF["tab"]
    be = np.mod(np.asarray(be, dtype=np.float64), 2 * math.pi)
    return np.interp(be, np.append(bb, 2 * math.pi), np.append(tab, tab[0]))


# ---------------------------------------------------------------------------- 身体 + 眼窝（绕眼轴的旋转网格）
# 剖面：后极 → 椭球面（身体）→ 甲壳边缘下（join）→ 甲缘（rim）→ 隆起 → 唇峰 → 唇尖 → 卷进口袋顶 → 口袋底 → 结膜 → 结膜前缘
BODY_COUNTS = (6, 13)                  # 后极 → θ 140°、140° → join
SOCK_COUNTS = (2, 3, 3, 3, 2, 2, 2, 2, 2, 2, 2, 2, 2, 1)
# 各区间属于哪一段：0 外表面（甲缘下 → 唇峰）、1 唇（峰 → 唇尖 → 卷进去）、2 口袋顶、3 口袋底、4 结膜
SOCK_REGION = (0, 0, 0, 1, 1, 1, 2, 2, 3, 3, 4, 4, 4, 4)
REG_BODY = -1
TH_BACK = D(140)


def socket_keys(be):
    """每个方位的剖面控制点（θ, ρ），shape (nb, K, 2)，含首尾虚点。"""
    nb = len(be)
    tj = theta_at_body_angle(be, D(61))
    tr = theta_at_body_angle(be, D(56))
    tl = theta_lip(be)
    rf = roof_rho(be)
    tf = tl + FUNDUS

    def er(th):
        return ell_rho(eye_dir(th, be))
    rr = er(tr)
    tpk = tl + D(6)
    rpk = rf + 0.62
    tm = tr - 0.5 * (tr - tpk)
    rm = np.maximum(0.5 * (rr + rpk) + 0.03, er(tm) + 0.03)
    one = np.ones(nb)
    keys = [
        (tj + D(3), er(tj + D(3))),                       # 虚点（切线顺着椭球）
        (tj, er(tj)),                                       # join（甲壳下面）
        (tr, rr),                                           # 甲缘
        (tm, rm),
        (tpk, rpk),                                         # 唇峰
        (tl, rf + 0.30),                                    # 唇尖（最前）
        (tl + D(1.2), rf + 0.08),
        (tl + D(3.5), rf),                                  # 口袋顶起点
        (0.5 * (tl + D(3.5) + tf), rf),
        (tf, rf),                                           # 口袋顶终点
        (tf + D(3.5), 0.5 * (rf + FLOOR)),                  # 口袋底
        (tf, FLOOR * one),                                  # 结膜起点
        (np.maximum(tf - D(6), D(87)), FLOOR * one),
        (D(83) * one, (FLOOR - 0.06) * one),
        (D(79.5) * one, 4.58 * one),
        (FLOOR_EDGE * one, 4.45 * one),                     # 结膜前缘（贴着眼球）
        ((FLOOR_EDGE - D(1)) * one, 4.41 * one),            # 虚点
    ]
    th = np.stack([k[0] * one for k in keys], 1)
    rh = np.stack([k[1] * one for k in keys], 1)
    return th, rh


def rev_grid(nb, k):
    """身体 + 眼窝的旋转网格。nb 个方位、剖面采样数 ×k。
    返回 dict：P (R, nb, 3)、pole（后极点）、每圈的段号 reg、每圈在剖面上的参数 s（0～1 在各段里）、β、θ 等。"""
    be = 2 * math.pi * np.arange(nb) / nb
    th, rh = socket_keys(be)
    # 眼窝段：在 (a, b) = (离眼轴距离, 沿眼轴) 平面里插值
    Q = np.stack([rh * np.sin(th), rh * np.cos(th)], -1)
    counts = [c * k for c in SOCK_COUNTS]
    C, seg = catmull(Q, counts)
    reg_s = np.array([SOCK_REGION[min(s, len(SOCK_REGION) - 1)] for s in seg])
    # 每圈在本区间里的位置（0～1）
    loc = np.concatenate([np.arange(n) / n for n in counts] + [np.ones(1)])
    # 身体段：椭球面
    tj = theta_at_body_angle(be, D(61))
    n1, n2 = BODY_COUNTS[0] * k, BODY_COUNTS[1] * k
    rings_th = [np.full(nb, math.pi - (math.pi - TH_BACK) * j / n1) for j in range(1, n1 + 1)]
    rings_th += [TH_BACK + (tj - TH_BACK) * j / n2 for j in range(1, n2)]
    TH = np.stack(rings_th, 0)
    Pb = E + ell_rho(eye_dir(TH, be[None, :]))[..., None] * eye_dir(TH, be[None, :])
    a, b = C[..., 0].T, C[..., 1].T          # (Rs, nb)
    Ps = E + np.stack([a * np.cos(be)[None, :], b, a * np.sin(be)[None, :]], -1)
    P = np.concatenate([Pb, Ps], 0)
    reg = np.concatenate([np.full(len(Pb), REG_BODY), reg_s])
    segi = np.concatenate([np.full(len(Pb), -1), seg])
    loc = np.concatenate([np.zeros(len(Pb)), loc])
    pole = E + np.array([0.0, -ell_rho(np.array([0.0, -1.0, 0.0])), 0.0])
    ring_back = n1 - 1               # θ = 140° 那一圈（UV 分块）
    ring_join = len(Pb)              # join 那一圈
    ring_fundus = len(Pb) + sum(counts[:9])   # 口袋顶 → 口袋底
    return dict(P=P, pole=pole, be=be, reg=reg, seg=segi, loc=loc, nb=nb, k=k,
                ring_back=ring_back, ring_join=ring_join, ring_fundus=ring_fundus)


# ---------------------------------------------------------------------------- 身体上的低频起伏（低模、高模都加；只往里凹，不顶甲壳）
SIPHON_N = None


def siphon_frame():
    s = ell_project(np.array(spec.SIPHON_DIR, dtype=np.float64) * 7.0)
    n = ell_normal(s)
    y = np.array([0.0, 1.0, 0.0]) - n * n[1]
    y /= np.linalg.norm(y)
    x = np.cross(y, n)
    return s, x, y, n


DENTS = [  # (纬度°, 经度°, 深, 半径)：几处大的浅凹
    (35, 150, 0.12, 1.4), (-10, -160, 0.10, 1.6), (55, -60, 0.10, 1.2), (-48, 120, 0.12, 1.3),
    (-50, -95, 0.10, 1.5), (15, -125, 0.09, 1.3),
]


def paddle_roots():
    out = []
    for i in range(len(spec.PADDLES)):
        for side in (-1, 1):
            out.append(np.array(spec.paddle_root(i, side), dtype=np.float64))
    return np.array(out)


def body_low(P):
    """身体（椭球面那段 + 甲缘下）上的低频起伏，沿法线的高度（≤ 0）。"""
    h = np.zeros(len(P))
    z = P[:, 2] / spec.AZ
    # 腹面横褶（顺着前后轴的一道道沟，腹面甲薄，露得多）
    roots = paddle_roots()
    dr = np.min(np.linalg.norm(P[:, None, :] - roots[None, :, :], axis=-1), axis=1)
    s0, sx, sy, sn = siphon_frame()
    ds = np.linalg.norm(P - s0, axis=1)
    mv = smoothstep(-0.30, -0.62, z) * smoothstep(1.4, 2.4, dr) * smoothstep(2.0, 3.0, ds)
    ph = P[:, 1] / 1.15 + 0.18 * np.sin(P[:, 0] * 0.55 + 1.3) + 0.12 * np.sin(P[:, 0] * 1.3)
    fr = ph - np.floor(ph) - 0.5
    h -= 0.055 * mv * np.exp(-(fr / 0.13) ** 2)
    # 几处大的浅凹
    for lat, lon, dep, rad in DENTS:
        c = np.array(spec.surface(spec.from_lat_lon(D(lat), D(lon))))
        h -= dep * np.exp(-(np.linalg.norm(P - c, axis=1) / rad) ** 2)
    # 虹吸口下面往里凹（口子里面看不见身体）
    q = P - s0
    rr = np.linalg.norm(q - np.outer(q @ sn, sn), axis=1)
    h -= 0.95 * smoothstep(1.6 * spec.SIPHON_R, 1.2 * spec.SIPHON_R, rr) * (q @ sn > -2.0)
    return h


def socket_folds(be, w, seed=3):
    """眼窝外圈的放射状大褶（低频；转眼时这圈肉被牵动的样子）。be: 方位，w: 强度 0～1。"""
    rng = np.random.default_rng(seed)
    n = 27
    cen = 2 * math.pi * (np.arange(n) + rng.uniform(-0.35, 0.35, n)) / n
    sig = D(2.2) + D(2.0) * rng.random(n)
    amp = 0.5 + 0.9 * rng.random(n)
    tw = D(3.0) * np.sin(3 * be + 0.7) * w          # 略带一点旋
    acc = np.zeros_like(be)
    for c, s, a in zip(cen, sig, amp):
        dd = np.angle(np.exp(1j * (be + tw - c)))
        acc += a * np.exp(-(dd / s) ** 2)
    return 0.15 * (acc - 0.45) * w


def rev_low(G):
    """旋转网格各点的低频高度（沿法线）。"""
    P = G["P"]
    R, nb = P.shape[:2]
    reg = np.broadcast_to(G["reg"][:, None], (R, nb))
    seg = np.broadcast_to(G["seg"][:, None], (R, nb))
    loc = np.broadcast_to(G["loc"][:, None], (R, nb))
    be = np.broadcast_to(G["be"][None, :], (R, nb))
    # 眼窝外圈放射褶的强度：甲缘 0 → 隆起 → 唇峰最强 → 唇尖一半 → 卷进去没有
    sp = seg + loc   # 区间号 + 区间内位置
    w = np.interp(sp, [0, 1, 2, 3, 4, 5, 6], [0, 0.15, 0.6, 1.0, 0.9, 0.2, 0.0])
    w = np.where(seg < 0, 0.0, w)
    h = socket_folds(be.ravel(), w.ravel()).reshape(R, nb)
    # 身体那段（含甲缘下）加身体起伏
    body = (reg == REG_BODY) | (seg <= 1)
    hb = body_low(P.reshape(-1, 3)).reshape(R, nb)
    fade = np.where(reg == REG_BODY, 1.0, np.interp(sp, [0, 1, 2], [1.0, 0.6, 0.0]))
    h = h + np.where(body, hb * fade, 0.0)
    return h


def rev_low_pole(pole):
    return body_low(pole[None, :])[0]


# ---------------------------------------------------------------------------- 虹吸口
SIPHON_KEYS = [  # (r / SIPHON_R, 高出体表米)
    (1.85, -0.22), (1.65, -0.10), (1.48, 0.0), (1.28, 0.10), (1.08, 0.24), (0.94, 0.36), (0.82, 0.42),
    (0.70, 0.385), (0.60, 0.26), (0.52, 0.06), (0.46, -0.22), (0.36, -0.50), (0.20, -0.70), (0.0, -0.80),
    (-0.12, -0.80),
]
SIPHON_COUNTS = (1, 1, 1, 2, 1, 1, 1, 2, 2, 1, 1, 1)
SIPHON_REGION = (0, 0, 0, 0, 0, 1, 1, 1, 2, 2, 2, 2)   # 0 外圈环肌、1 口缘、2 喉


def siphon_grid(na, k):
    """返回 dict：P (R, na, 3)（最后一圈半径 0 → 换成底点）、每圈 r、h、段号、方位角。"""
    Q = np.array(SIPHON_KEYS, dtype=np.float64)
    Q[:, 0] *= spec.SIPHON_R
    counts = [c * k for c in SIPHON_COUNTS]
    C, seg = catmull(Q[None], counts)
    C = C[0]
    rr, hh = C[:, 0], C[:, 1]
    s0, sx, sy, sn = siphon_frame()
    a = 2 * math.pi * np.arange(na) / na
    off = rr[:, None, None] * (np.cos(a)[None, :, None] * sx + np.sin(a)[None, :, None] * sy)
    base = ell_project(s0 + off)
    nrm = ell_normal(base)
    P = base + nrm * hh[:, None, None]
    reg = np.array([SIPHON_REGION[min(s, len(SIPHON_REGION) - 1)] for s in seg])
    return dict(P=P[:-1], bottom=P[-1].mean(0), r=rr[:-1], h=hh[:-1], reg=reg[:-1], a=a, seg=seg[:-1],
                frame=(s0, sx, sy, sn))


def papillae(k_side=5, k_len=2, seed=7):
    """口缘的小触须：两圈小锥，往上、往口里弯。返回 [(点 (L+1, ks, 3) 环, 尖点)]。"""
    rng = np.random.default_rng(seed)
    s0, sx, sy, sn = siphon_frame()
    R = spec.SIPHON_R
    out = []
    for ring_r, h0, n, L0, L1, rad in ((0.80 * R, 0.415, 24, 0.09, 0.15, 0.045),
                                         (0.63 * R, 0.30, 17, 0.07, 0.11, 0.038)):
        for i in range(n):
            a = 2 * math.pi * (i + rng.uniform(-0.25, 0.25)) / n + (0.13 if ring_r < 0.7 * R else 0.0)
            radial = math.cos(a) * sx + math.sin(a) * sy
            base = ell_project(s0 + ring_r * radial)
            base = base + ell_normal(base) * (h0 - 0.04)
            L = rng.uniform(L0, L1)
            # 方向：主要朝上（体表法线），往口里倾
            d0 = sn - 0.35 * radial
            d0 /= np.linalg.norm(d0)
            bend = -0.55 * radial + 0.25 * np.cross(sn, radial) * rng.uniform(-1, 1)
            side1 = np.cross(d0, radial)
            side1 /= np.linalg.norm(side1)
            side2 = np.cross(d0, side1)
            n_l = 2 * k_len
            ks = k_side
            rings = []
            for j in range(n_l):
                t = j / n_l
                c = base + d0 * L * t + bend * L * 0.35 * t * t
                r = rad * (1 - 0.45 * t ** 1.5) * (1.0 if j else 1.15)
                ang = 2 * math.pi * np.arange(ks) / ks
                rings.append(c + r * (np.cos(ang)[:, None] * side1 + np.sin(ang)[:, None] * side2))
            tip = base + d0 * (L + 0.5 * rad) + bend * L * 0.35   # 圆钝的头
            out.append((np.array(rings), tip))
    return out
