"""甲片的网格：低模（进游戏，一片甲约 200～450 个三角形，UV 两个岛：顶面 + 卷边一块，底面一块藏在甲底下）
和高模（只烘焙，约 2.5 厘米一个点，带逐点属性给 shell_high 加细节）。两者都从 shell_plate.Plate 的同一套解析外形取点。

一片甲从顶面中心一圈圈往外：顶面 →（中棱、拱、浅沟、珠边）→ 甲缘往外卷 → 外壁 → 底面往里卷一小段（内卷边）→ 底面中心。"""
import math

import numpy as np

from watcher import shell_np as snp

UNDER_SQUEEZE = 0.15     # 甲底面在 UV 里径向压扁多少（底面看不见，接在顶面岛外圈，不单占图集）


def _even(x, lo, hi):
    return int(np.clip(2 * round(x / 2), lo, hi))


def low_spokes(p):
    M = _even(p.perim / p.prm["sp"], 12, 36)
    return M


def _cols(rings):
    """同样点数的几圈 → (圈数, M, 3)"""
    return np.stack(rings, 0)


def plate_low(p):
    """→ co, tris, 逐角 UV（未缩放，米）。一片甲一个 UV 岛：以甲片中心为原点沿辐条量 3D 弧长往外摊
    （顶面 → 卷边 → 外壁 → 内卷边 → 底面）。"""
    M = low_spokes(p)
    sig = np.arange(M) / M
    s = p.s_of_sig(sig)
    rA, rB, rC, rD, rd = p.ctrl_r(s)
    lip = p.lip_ctrl(s)
    z1 = np.zeros(1)
    pole, _ = p.top(z1, z1)
    rings = []
    for r in (0.5 * rB, rB, rC, rD):
        rings.append(p.top(s, r)[0])
    rings.append(p.lip_point(s, 0.5 * (lip[1][0] + lip[2][0]), 0.5 * (lip[1][1] + lip[2][1])))
    rings.append(p.lip_point(s, lip[4][0], lip[4][1]))
    dbl = p.under(s, rd, rd)[0]
    rings.append(dbl)
    umid = p.under(s, 0.5 * rd, rd)[0]
    upole = p.under(z1, z1, np.ones(1))[0]
    rm = snp.RingMesh()
    rm.add(pole, [0.0])
    for R in rings:
        rm.add(R, sig)
    rm.add(umid, sig)
    rm.add(upole, [0.0])
    co, tris, band, _, starts = rm.build()
    # ---- UV：顶面岛 = 以甲片中心为原点、沿辐条量 3D 弧长往外摊开（卷边、外壁、内卷边接着往外摊）；底面岛同理、镜像
    O = np.stack([np.interp(s * len(p.O), np.arange(len(p.O) + 1), np.append(p.O[:, i], p.O[0, i]))
                  for i in range(3)], -1)
    dvec = O - p.C
    dirc = np.stack([dvec @ p.ex, dvec @ p.ey], -1)
    dirc /= np.linalg.norm(dirc, axis=1, keepdims=True)
    # 顶面、卷边照实摊开；底面接在内卷边外面，径向压到 0.15（藏在甲底下，省图集）
    uv = np.zeros((len(co), 2))
    cols = _cols(rings + [umid])                       # B/2 B C D lip wall dbl umid
    wts = [1.0] * len(rings) + [UNDER_SQUEEZE]
    arc = np.linalg.norm(cols[0] - pole[0], axis=-1)
    for j in range(len(cols)):
        if j:
            arc = arc + wts[j] * np.linalg.norm(cols[j] - cols[j - 1], axis=-1)
        st = starts[1 + j]
        uv[st:st + M] = dirc * arc[:, None]
    uvc = uv[tris]
    # 底面中心（最后一个点）每个三角形各给一个 UV：沿另外两个角的方向再往外摊一点
    up = starts[-1]
    isp = tris == up
    rows = isp.any(1)
    sub = uvc[rows]
    ip = isp[rows]
    oth = np.where(ip[:, :, None], 0.0, sub).sum(1) * 0.5
    rr = np.linalg.norm(oth, axis=1, keepdims=True)
    ext = UNDER_SQUEEZE * float(np.mean(np.linalg.norm(umid - upole[0], axis=-1)))
    sub[ip] = oth / np.maximum(rr, 1e-9) * (rr + ext)
    uvc[rows] = sub
    return co, tris, uvc.reshape(-1, 2)


# ---------------------------------------------------------------------------- 高模
def _ring_n(perim, h, lo=8):
    return max(lo, int(math.ceil(perim / h)))


def _perim(P):
    return float(np.linalg.norm(np.roll(P, -1, 0) - P, axis=1).sum())


def _catmull(ctrl, t):
    """ctrl: list of (n,3)，t ∈ [0, len-1]（标量），每根辐条一起插值。"""
    k = len(ctrl)
    i = min(int(math.floor(t)), k - 2)
    u = t - i
    p1, p2 = ctrl[i], ctrl[i + 1]
    p0 = ctrl[i - 1] if i > 0 else 2 * p1 - p2
    p3 = ctrl[i + 2] if i + 2 < k else 2 * p2 - p1
    u2, u3 = u * u, u * u * u
    return 0.5 * (2 * p1 + (-p0 + p2) * u + (2 * p0 - 5 * p1 + 4 * p2 - p3) * u2 + (-p0 + 3 * p1 - 3 * p2 + p3) * u3)


def plate_high(p, pid, h=0.025, hu=0.12):
    """→ co, tris, 属性 dict（reg：0 顶面 / 1 卷边外壁 / 2 底面；e、w、tk、dk、sig、r、lipu、pid）"""
    rm = snp.RingMesh()
    # 用一圈粗采样估计每段要几圈
    sig64 = np.arange(64) / 64
    s64 = p.s_of_sig(sig64)
    L64 = np.interp(s64 * len(p.L), np.arange(len(p.L) + 1), np.append(p.L, p.L[0]))
    c64 = p.ctrl_r(s64)
    segs = [(None, 1), (1, 2), (2, 3), (3, "E")]       # pole→B, B→C, C→D, D→甲缘

    def r_ctrl(c, key):
        if key is None:
            return np.zeros_like(c[0])
        if key == "E":
            return np.ones_like(c[0])
        return c[key]

    z1 = np.zeros(1)
    P0, h0 = p.top(z1, z1)
    rm.add(P0, [0.0], reg=0, e=h0["e"], w=h0["w"], tk=h0["tk"], dk=h0["dk"], r=0.0, lipu=0.0, pid=pid)
    for k0, k1 in segs:
        span = (r_ctrl(c64, k1) - r_ctrl(c64, k0)) * L64
        nseg = max(1, int(math.ceil(np.percentile(span, 70) / h)))
        for i in range(1, nseg + 1):
            t = i / nseg
            rr64 = r_ctrl(c64, k0) + t * (r_ctrl(c64, k1) - r_ctrl(c64, k0))
            n = _ring_n(_perim(p.top(s64, rr64)[0]) * 1.02, h)
            sg = np.arange(n) / n
            s = p.s_of_sig(sg)
            c = p.ctrl_r(s)
            rr = r_ctrl(c, k0) + t * (r_ctrl(c, k1) - r_ctrl(c, k0))
            P, hh = p.top(s, rr)
            rm.add(P, sg, reg=0, e=hh["e"], w=hh["w"], tk=hh["tk"], dk=hh["dk"], r=rr, lipu=0.0, pid=pid)
    # 卷边、外壁：同一套周向采样
    n = _ring_n(p.perim * 1.03, h)
    sg = np.arange(n) / n
    s = p.s_of_sig(sg)
    c = p.ctrl_r(s)
    rd = c[4]
    lip = p.lip_ctrl(s)
    Lp = np.interp(s * len(p.Lp), np.arange(len(p.Lp) + 1), np.append(p.Lp, p.Lp[0]))
    r6 = np.clip(1 - 0.06 / Lp, rd + 0.01, 0.999)
    ctrl = [p.top(s, np.ones_like(s))[0]] + [p.lip_point(s, o, hh) for o, hh in lip[1:5]] + [p.under(s, r6, rd)[0]]
    hE = p.heights(s, np.ones_like(s))
    w, tk = hE["w"], hE["tk"]
    for i in range(len(ctrl) - 1):
        seg = np.linalg.norm(ctrl[i + 1] - ctrl[i], axis=1).max()
        nk = max(1, int(math.ceil(seg * 1.15 / h)))
        for j in range(1, nk + 1):
            t = i + j / nk
            P = _catmull(ctrl, t)
            lu = t / (len(ctrl) - 1)
            rm.add(P, sg, reg=1, e=-0.05 * lu, w=w, tk=tk, dk=9.0, r=1.0, lipu=lu, pid=pid)
    # 底面：r6 → rd → 中心（粗）
    nu = _ring_n(p.perim, hu)
    sgu = np.arange(nu) / nu
    su = p.s_of_sig(sgu)
    cu = p.ctrl_r(su)
    rdu = cu[4]
    r6u = np.clip(1 - 0.06 / np.interp(su * len(p.Lp), np.arange(len(p.Lp) + 1), np.append(p.Lp, p.Lp[0])),
                  rdu + 0.01, 0.999)
    span = (r6 - rd).max() * p.L.max()
    for t in np.linspace(0, 1, max(2, int(math.ceil(span / h)) + 1))[1:]:
        rr = r6u + t * (rdu - r6u)
        P, hh = p.under(su, rr, rdu)
        rm.add(P, sgu, reg=2, e=hh["e"], w=0.0, tk=1.0, dk=9.0, r=rr, lipu=1.0, pid=pid)
    nin = max(2, int(math.ceil(p.L.max() * 0.8 / hu)))
    for i in range(1, nin):
        t = 1 - i / nin
        rr64 = c64[4] * t
        nn = max(6, _ring_n(_perim(p.under(s64, rr64, c64[4])[0]), hu))
        sg2 = np.arange(nn) / nn
        s2 = p.s_of_sig(sg2)
        rd2 = p.ctrl_r(s2)[4]
        P, hh = p.under(s2, rd2 * t, rd2)
        rm.add(P, sg2, reg=2, e=hh["e"], w=0.0, tk=1.0, dk=9.0, r=rd2 * t, lipu=1.0, pid=pid)
    P, hh = p.under(z1, z1, np.ones(1))
    rm.add(P, [0.0], reg=2, e=hh["e"], w=0.0, tk=1.0, dk=9.0, r=0.0, lipu=1.0, pid=pid)
    co, tris, band, attrs, _ = rm.build()
    attrs["sig"] = np.concatenate([np.asarray(r[1]) if len(r[1]) == len(r[0]) else np.zeros(len(r[0]))
                                   for r in rm.rings])
    return co, tris, attrs
