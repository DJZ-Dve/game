"""嘴里的肉（一张连着的网格）：上颚（含两个獠牙牙槽）、口底 + 基舌骨垫、嘴角颊膜（双层，前缘卷边）、喉咙（往后收、往下拐，收成黑洞）。

拓扑：每个 s 一圈「环」——上颚（右上牙床线 → 左上牙床线）、左颊膜内层（上 → 下）、口底（左下牙床线 → 右下牙床线）、
右颊膜内层（下 → 上）。嘴的前段（颊膜以前）只有上颚和口底两条，中间是嘴缝；颊膜那段开始整圈闭合；铰链往后是喉咙。
颊膜外层是单独一片，上下两条边塞进唇里（藏在皮后面），前缘和内层卷在一起，后缘塞进嘴角的肉里。
权重：上颚、牙槽、喉咙顶 = 脊椎骨；口底 = Jaw（靠嘴角、中间往脊椎骨过渡）；颊膜从上到下 脊椎骨 → Jaw；喉咙从铰链往后淡出 Jaw。"""
import math

import numpy as np
from mathutils import Vector as V

from giant import spec
from giant import mouth_shape as ms
from giant.mouth_util import MB, sstep, smoothstep, fbm, ridged, merge_weights

S_WEB = 0.140          # 颊膜从这里开始（往后到嘴角）
REG_PAL, REG_FLO, REG_WEBL, REG_WEBR, REG_OUTL, REG_OUTR, REG_PITL, REG_PITR, REG_CAP = range(1, 10)


def stations(res=1):
    s = list(np.linspace(0.0, 0.013, 5)) + list(np.linspace(0.017, 0.062, 16)) + \
        list(np.linspace(0.067, S_WEB, 13)) + list(np.linspace(S_WEB, spec.JAW_HINGE_S, 8))[1:]
    s = sorted(set(round(x, 6) for x in s))
    if res > 1:
        out = []
        for a, b in zip(s[:-1], s[1:]):
            out += list(np.linspace(a, b, res + 1)[:-1])
        out.append(s[-1])
        s = out
    return np.array(s)


def s_lower(su):
    return su + spec.JAW_FRONT_S * max(0.0, 1.0 - su / S_WEB) ** 1.25


def jaw_w_floor(s, d):
    """口底的 Jaw 权重：牙床线附近整块跟下颌，中间（基舌骨垫）靠近嘴角往脊椎骨过渡。"""
    return 1.0 - sstep(0.15, 0.27, s) * sstep(0.35, 1.6, d) * 0.85


def spine_mix(s, wj):
    d = {b: w * (1 - wj) for b, w in spec.spine_weights(min(max(s, 0.0), 1.0))}
    if wj > 0:
        d["Jaw"] = wj
    return d


def throat_path(c0, K, length=4.8, drop=2.3):
    """喉咙中线：从铰链处嘴腔中心往后，后半段往下拐。"""
    pts = []
    for k in range(K + 1):
        t = k / K
        y = c0.y - length * t
        z = c0.z - drop * t ** 2.2
        pts.append(V((0.0, y, z)))
    return pts


class Lining:
    def __init__(self, res=1, fangs=None):
        self.res = res
        self.nhp = 15 if res == 1 else 14 * res + 1
        self.nhf = 15 if res == 1 else 14 * res + 1
        self.ngum = 7 if res == 1 else 6 * res + 1
        self.nw = 8 if res == 1 else 8 * res
        self.fangs = fangs or {}

    # ---------------------------------------------------------------- 环
    def ring_layout(self):
        Np = 2 * self.nhp - 1
        Nf = 2 * self.nhf - 1
        nwi = self.nw - 1
        self.Np, self.Nf, self.nwi = Np, Nf, nwi
        self.iL = Np                     # 左颊膜内层起点
        self.iF = Np + nwi               # 口底起点（左牙床线）
        self.iR = Np + nwi + Nf          # 右颊膜内层起点（靠下）
        self.Nr = Np + 2 * nwi + Nf
        return self.Nr

    def web_inner(self, sU, sL, side, k):
        """颊膜内层第 k 个点（0 = 上牙床线，nw = 下牙床线）。静止时折着：一道道褶。"""
        gU = spec.gum_point(sU, side, True)
        gL = spec.gum_point(sL, side, False)
        f = k / self.nw
        p = gU.lerp(gL, f)
        env = math.sin(math.pi * f)
        acc = math.sin(math.pi * f * 4) if self.res == 1 else math.sin(math.pi * f * 4)
        bul = 0.045 * env + 0.035 * acc * env
        return p + V((side * bul, 0.0, 0.0))

    def web_outer(self, sU, sL, side, k, back=0.0):
        gU = spec.gum_point(sU, side, True)
        gL = spec.gum_point(sL, side, False)
        f = k / self.nw
        a = gU + V((side * 0.13, 0.0, 0.07))
        b = gL + V((side * 0.13, 0.0, -0.07))
        p = a.lerp(b, f)
        env = math.sin(math.pi * f)
        acc = math.sin(math.pi * f * 4)
        p = p + V((side * (0.04 * env + 0.03 * acc * env + back), 0.0, 0.0))
        return p

    def build_rings(self, S):
        Nr = self.ring_layout()
        nst = len(S)
        P = np.zeros((nst, Nr, 3))
        D = np.zeros((nst, Nr))          # 离牙床线的距离（权重 / 细节用）
        W = np.zeros((nst, Nr))          # Jaw 权重
        REG = np.zeros((nst, Nr), dtype=np.int32)
        for i, su in enumerate(S):
            sl = s_lower(su)
            pal, dp = ms.full_row(su, True, self.nhp, n_gum=self.ngum)
            flo, df = ms.full_row(sl, False, self.nhf, n_gum=self.ngum)
            flo = flo[::-1]
            df = df[::-1]
            row = list(pal)
            dd = list(dp)
            ww = [0.0] * len(pal)
            rr = [REG_PAL] * len(pal)
            for k in range(1, self.nw):
                row.append(self.web_inner(su, sl, -1, k))
                dd.append(0.0)
                ww.append(sstep(0.0, 1.0, k / self.nw))
                rr.append(REG_WEBL)
            row += flo
            dd += list(df)
            ww += [jaw_w_floor(sl, d) for d in df]
            rr += [REG_FLO] * len(flo)
            for k in range(self.nw - 1, 0, -1):
                row.append(self.web_inner(su, sl, 1, k))
                dd.append(0.0)
                ww.append(sstep(0.0, 1.0, k / self.nw))
                rr.append(REG_WEBR)
            P[i] = np.array([p[:] for p in row])
            D[i] = dd
            W[i] = ww
            REG[i] = rr
        return P, D, W, REG

    # ---------------------------------------------------------------- 喉咙
    def build_throat(self, ring_h, W_h, REG_h, D_h):
        K = 12 * self.res
        pal_mid = ring_h[self.nhp - 1]
        flo_mid = ring_h[self.iF + self.nhf - 1]
        c0 = V(((0.0), pal_mid[1], 0.5 * (pal_mid[2] + flo_mid[2]) + 0.15))
        path = throat_path(c0, K)
        off = ring_h - np.array(c0[:])[None, :]
        rx_h = np.abs(off[:, 0]).max()
        rz_h = np.abs(off[:, 2]).max()
        psi = np.arctan2(off[:, 2] / rz_h, off[:, 0] / rx_h)
        rings, ws, regs, dds, ss = [], [], [], [], []
        for k in range(1, K + 1):
            t = k / K
            c = path[k]
            tan = (path[min(k + 1, K)] - path[k - 1]).normalized()
            # 截面：先保持嘴腔的样子，往后变成椭圆管，越来越细；里面有几道纵向的褶
            m = sstep(0.0, 0.55, t)
            rx = rx_h + (0.32 - rx_h) * t ** 0.62
            rz = rz_h + (0.30 - rz_h) * t ** 0.75
            sc = np.array([rx / rx_h, 1.0, rz / rz_h])
            e = np.stack([rx * np.cos(psi), np.zeros_like(psi), rz * np.sin(psi)], axis=1)
            o = (1 - m) * off * sc[None, :] + m * e
            o[:, 1] = 0.0
            pleat = 1.0 + 0.07 * sstep(0.1, 0.5, t) * np.sin(psi * 9 + 0.6)
            o[:, 0] *= pleat
            o[:, 2] *= pleat
            # 截面平面转到和中线垂直（绕 X 轴）
            ang = math.atan2(-tan.z, -tan.y)
            ca, sa = math.cos(ang), math.sin(ang)
            ro = np.stack([o[:, 0], -o[:, 2] * sa, o[:, 2] * ca], axis=1)
            rings.append(ro + np.array(c[:])[None, :])
            sk = spec.s_of(c.y)
            ws.append(W_h * (1.0 - sstep(0.2, 0.28, sk)))
            regs.append(REG_h)
            dds.append(D_h)
            ss.append(sk)
        end = path[-1] + (path[-1] - path[-2]).normalized() * 0.25
        return np.array(rings), np.array(ws), np.array(regs), np.array(dds), ss, end

    # ---------------------------------------------------------------- 牙槽
    def cut_pits(self, S, P, mask):
        """在上颚上开两个牙槽：删掉牙槽口里的格子，口沿的点吸到圆上。返回 [(side, 有序口沿格点 [(i,j)], 圆心 O)]。"""
        out = []
        for side, fang in self.fangs.items():
            O = fang["O"]
            rx, ry = fang["r_open"]
            cells = []
            for i in range(len(S) - 1):
                for j in range(2, self.Np - 3):
                    c = 0.25 * (P[i, j] + P[i, j + 1] + P[i + 1, j] + P[i + 1, j + 1])
                    if math.hypot((c[0] - O.x) / rx, (c[1] - O.y) / ry) < 1.0:
                        cells.append((i, j))
            cs = set(cells)
            nI, nJ = len(S) - 1, self.Np - 1

            def boundary(cs):
                adj = {}
                for (i, j) in cs:
                    for (nb, e) in (((i - 1, j), ((i, j), (i, j + 1))), ((i + 1, j), ((i + 1, j), (i + 1, j + 1))),
                                    ((i, j - 1), ((i, j), (i + 1, j))), ((i, j + 1), ((i, j + 1), (i + 1, j + 1)))):
                        if nb not in cs and 0 <= nb[0] < nI and 0 <= nb[1] < nJ:
                            adj.setdefault(e[0], []).append(e[1])
                            adj.setdefault(e[1], []).append(e[0])
                return adj
            # 只在角上碰着的格子会让口沿打结：把打结点周围的格子都删掉，直到口沿是一个简单的圈
            for _ in range(8):
                adj = boundary(cs)
                bad = [v for v, nb in adj.items() if len(nb) != 2]
                if not bad:
                    break
                for (a_, b_) in bad:
                    for c in ((a_ - 1, b_ - 1), (a_ - 1, b_), (a_, b_ - 1), (a_, b_)):
                        if 0 <= c[0] < nI and 2 <= c[1] < nJ - 2:
                            cs.add(c)
            cells = sorted(cs)
            for (i, j) in cells:
                mask[i, j] = False
            start = min(adj)
            order = [start]
            prev, cur = None, start
            while True:
                nxt = [w for w in adj[cur] if w != prev]
                if not nxt or nxt[0] == start:
                    break
                prev, cur = cur, nxt[0]
                order.append(cur)
            if len(order) != len(adj):
                print("  [mouth] 牙槽口沿不是一个简单的圈", len(order), len(adj))
            # 统一成绕 O 逆时针
            ang = [math.atan2(P[a_, b_][1] - O.y, P[a_, b_][0] - O.x) for a_, b_ in order]
            tot = sum(math.remainder(ang[(k + 1) % len(ang)] - ang[k], 2 * math.pi) for k in range(len(ang)))
            if tot < 0:
                order = order[::-1]
            # 吸到椭圆上（保留一点原来的参差，免得两个点吸到一处）
            es = [math.hypot((P[a_, b_][0] - O.x) / rx, (P[a_, b_][1] - O.y) / ry) for a_, b_ in order]
            em = float(np.mean(es))
            dist = em * math.sqrt(rx * ry)
            for (a_, b_), e in zip(order, es):
                dx, dy = P[a_, b_][0] - O.x, P[a_, b_][1] - O.y
                f = (em + 0.3 * (e - em)) / e
                nx, ny = O.x + dx * f, O.y + dy * f
                sv = spec.s_of(ny)
                P[a_, b_] = (nx, ny, ms.cavity_z(sv, nx, True))
            out.append((side, order, O, dist))
        return out

    def pit_geometry(self, fang, rim_pts, high=False):
        """牙槽：从口沿往里（顺着獠牙的圆弧），口上一圈软组织唇，往里收、顶上封口。返回 (rings 列表, 顶点)。"""
        O = fang["O"]
        cl = fang["arc"]                 # 圆弧上的点（从 O 往上）
        rad = fang["rad"]                # 每个点獠牙的半宽 (a, b)
        n = len(rim_pts)
        t0 = (cl[1] - cl[0]).normalized()
        e1 = V((0, 1, 0)) - t0 * t0.y
        e1.normalize()
        e2 = t0.cross(e1).normalized()
        psi = [math.atan2((p - O).dot(e2), (p - O).dot(e1)) for p in rim_pts]
        rings = []
        # 口沿往里一点、往下鼓：软组织唇（用光滑的椭圆，不跟着格子的参差走）
        rx, ry = fang["r_open"]
        es = [math.hypot((p.x - O.x) / rx, (p.y - O.y) / ry) for p in rim_pts]
        em = float(np.mean(es))
        ideal = [O + V(((p.x - O.x) * em / e, (p.y - O.y) * em / e, 0.0)) for p, e in zip(rim_pts, es)]
        rim = [O + (p - O) * 0.84 - t0 * 0.09 for p in ideal]
        rings.append(rim)
        rim2 = [O + (p - O) * 0.64 + t0 * 0.02 for p in ideal]
        rings.append(rim2)
        nseg = 8 if not high else 8 * self.res
        acc = [0.0]
        for i in range(1, len(cl)):
            acc.append(acc[-1] + (cl[i] - cl[i - 1]).length)
        Lmax = acc[-1] + 0.12
        prev_t = t0
        E1, E2 = e1.copy(), e2.copy()
        for k in range(1, nseg + 1):
            l = 0.12 + (Lmax - 0.12) * k / nseg
            # 沿弧找点
            if l <= acc[-1]:
                ii = int(np.searchsorted(acc, l) - 1)
                ii = min(max(ii, 0), len(cl) - 2)
                f = (l - acc[ii]) / max(acc[ii + 1] - acc[ii], 1e-9)
                c = cl[ii].lerp(cl[ii + 1], f)
                tan = (cl[ii + 1] - cl[ii]).normalized()
                ra, rb = rad[ii]
            else:
                tan = (cl[-1] - cl[-2]).normalized()
                c = cl[-1] + tan * (l - acc[-1])
                ra, rb = rad[-1]
            q = prev_t.rotation_difference(tan)
            E1 = (q @ E1).normalized()
            E2 = tan.cross(E1).normalized()
            prev_t = tan
            gap = 0.10 - 0.03 * k / nseg
            # 顶上收成圆顶（按长度连续收，低模高模一样）
            u = max(0.0, (l - (Lmax - 0.4)) / 0.4)
            dome = max(math.sqrt(max(1.0 - u * u, 0.0)), 0.35)
            ring = [c + (E1 * math.cos(p) * (ra + gap) + E2 * math.sin(p) * (rb + gap)) * dome for p in psi]
            rings.append(ring)
        top = cl[-1] + (cl[-1] - cl[-2]).normalized() * (Lmax - acc[-1] + 0.07)
        return rings, top

    # ---------------------------------------------------------------- 总装
    def build(self, mb, high=False):
        S = stations(self.res)
        P, D, W, REG = self.build_rings(S)
        nst = len(S)
        Nr = self.Nr
        # 面的掩码：嘴前段没有颊膜
        mask = np.ones((nst - 1, Nr), dtype=bool)
        web_cols = list(range(self.iL - 1, self.iF)) + list(range(self.iR - 1, Nr))
        iw = int(np.argmin(np.abs(S - S_WEB)))
        self.iw = iw
        for i in range(nst - 1):
            if i < iw:
                mask[i, web_cols] = False
        # 牙槽
        pits = self.cut_pits(S, P, mask)
        # 喉咙
        th, thW, thREG, thD, ths, end = self.build_throat(P[-1], W[-1], REG[-1], D[-1])
        allP = np.concatenate([P, th], axis=0)
        allW = np.concatenate([W, thW], axis=0)
        allREG = np.concatenate([REG, thREG], axis=0)
        allD = np.concatenate([D, thD], axis=0)
        allS = list(S) + list(ths)
        # 口底那几列的 s 用 s_lower
        nall = len(allP)
        mask_all = np.ones((nall - 1, Nr), dtype=bool)
        mask_all[:nst - 1] = mask
        weights = []
        for i in range(nall):
            for j in range(Nr):
                if i < nst:
                    s = s_lower(S[i]) if REG[i, j] == REG_FLO else S[i]
                else:
                    s = allS[i]
                weights.append(spine_mix(s, allW[i, j]))
        ids = mb.grid(allP, closed=True, region=REG_PAL, mask=mask_all, weights=weights)
        # 每个格子按列分区域（UV 接缝）：边 j 连 ring[j] → ring[j+1]
        last = mb.faces.pop()
        quads = last[0]
        colreg = np.empty(Nr, dtype=np.int32)
        colreg[:self.Np - 1] = REG_PAL
        colreg[self.Np - 1:self.iF] = REG_WEBL
        colreg[self.iF:self.iR - 1] = REG_FLO
        colreg[self.iR - 1:] = REG_WEBR
        regs = np.array([colreg[j] for i in range(nall - 1) for j in range(Nr) if mask_all[i, j]])
        for r in np.unique(regs):
            mb.add_faces(quads[regs == r], region=int(r))
        # 喉咙尽头封口
        endi = mb.add_verts([end[:]], spine_mix(spec.s_of(end.y), 0.0))
        tri = [[ids[-1, (j + 1) % Nr], ids[-1, j], endi] for j in range(Nr)]
        mb.add_faces(tri, region=REG_CAP)
        # 颊膜外层 + 前缘卷边
        self._outer_webs(mb, S, ids, iw, high)
        # 牙槽
        for side, order, O, dist in pits:
            fang = self.fangs[side]
            rim_pts = [V(allP[a, b]) for a, b in order]
            rings, top = self.pit_geometry(fang, rim_pts, high)
            prev = [ids[a, b] for a, b in order]
            reg = REG_PITR if side > 0 else REG_PITL
            n = len(order)
            for ring in rings:
                st = mb.add_verts([p[:] for p in ring], spine_mix(spec.s_of(O.y), 0.0))
                cur = [st + k for k in range(n)]
                quads = [[prev[k], prev[(k + 1) % n], cur[(k + 1) % n], cur[k]] for k in range(n)]
                # 第 0 列单独一个区域：两边都是接缝，深坑展开成一条（不是一个扭曲的圆盘）
                mb.add_faces(quads[1:], region=reg)
                mb.add_faces(quads[:1], region=reg + 20)
                prev = cur
            ti = mb.add_verts([top[:]], spine_mix(spec.s_of(O.y), 0.0))
            tris = [[prev[(k + 1) % n], prev[k], ti] for k in range(n)]
            mb.add_faces(tris[1:], region=reg)
            mb.add_faces(tris[:1], region=reg + 20)
        self.S = S
        self.ids = ids
        self.allP = allP
        return ids

    def _outer_webs(self, mb, S, ids, iw, high):
        nw = self.nw
        for side in (-1, 1):
            rows, ws = [], []
            idx = list(range(iw, len(S)))
            for i in idx:
                su = S[i]
                sl = s_lower(su)
                rows.append([self.web_outer(su, sl, side, k)[:] for k in range(nw + 1)])
            # 后缘：再往后、往外塞进嘴角的肉里
            su = S[-1]
            rows.append([(self.web_outer(su, su, side, k, back=0.22) + V((0, -0.22, 0)))[:] for k in range(nw + 1)])
            rows = np.array(rows)
            wts = []
            for r, i in enumerate(idx + [len(S) - 1]):
                for k in range(nw + 1):
                    wts.append(spine_mix(S[i], sstep(0.0, 1.0, k / nw)))
            reg = REG_OUTR if side > 0 else REG_OUTL
            oid = mb.grid(rows, closed=False, region=reg, weights=wts)
            # 前缘卷边：内层（环上的点）→ 中间一排（往前、居中）→ 外层第一排
            if side < 0:
                inner = [ids[iw, self.Np - 1]] + [ids[iw, self.iL + k - 1] for k in range(1, nw)] + [ids[iw, self.iF]]
            else:
                inner = [ids[iw, 0]] + [ids[iw, self.Nr - k] for k in range(1, nw)] + [ids[iw, self.iF + self.Nf - 1]]
            mids = []
            for k in range(nw + 1):
                a = V(mb_vert(mb, inner[k]))
                b = V(rows[0, k])
                m = (a + b) * 0.5 + V((side * 0.02, 0.07, 0.0))
                mids.append(m[:])
            mst = mb.add_verts(mids, [spine_mix(S[iw], sstep(0.0, 1.0, k / nw)) for k in range(nw + 1)])
            mid = [mst + k for k in range(nw + 1)]
            q1 = [[inner[k], inner[k + 1], mid[k + 1], mid[k]] for k in range(nw)]
            q2 = [[mid[k], mid[k + 1], oid[0, k + 1], oid[0, k]] for k in range(nw)]
            mb.add_faces(q1 + q2, region=reg)


def mb_vert(mb, i):
    """MB 里第 i 个顶点的位置。"""
    acc = 0
    for arr in mb.verts:
        if i < acc + len(arr):
            return arr[i - acc]
        acc += len(arr)
    raise IndexError(i)
