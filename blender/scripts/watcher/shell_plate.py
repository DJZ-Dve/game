"""甲壳的甲片：排布（以眼睛为极点一圈一圈往后叠，像瓦片）+ 每片甲的解析外形（低模、高模都从这同一套函数取点）。

排布：以 +Y（眼睛）为极点的球坐标 (θ, φ)：θ = 离眼睛方向的角度，φ = 绕 Y 轴的方位（0 背、±90° 两侧、180° 腹）。
  - 第 0 圈（θ 50°～54° 到 67°，前缘跟着 spec.socket_rim）是眼眶：前缘不往下藏，缘边加厚往外翻；
  - 第 1～5 圈往后，每圈的前缘藏到前一圈的后缘底下（重叠 0.3～0.85 米），后缘厚、有缘边；
  - 尾部一块圆盖（臀板），整圈藏在第 5 圈底下；
  - 每圈沿 φ 切成几片：背中一片（中棱）、背侧、体侧，φ = ±111°（三对桨的根部连成的线）是固定的缝；
    腹面（|φ| > 111°）的甲小而薄，每圈再前后分成两排；腹中线 φ = 180° 是缝；
  - 同一圈相邻的甲片之间留 0.15～0.3 米的缝（露出关节膜），桨根、虹吸口周围把甲缘咬掉一个圆。
每片甲的参数：辐条参数 s ∈ [0,1)（s = 0 指向后缘中点，0.5 指向前缘中点）、径向参数 r ∈ [0,1]（1 = 甲缘）；
(a, b) = r·ρ(s)·(sin 2πs, cos 2πs) 是甲片自己的平面参数（a 横、b 纵，b = +1 后缘），再映射到 (θ, φ) → 身体表面 → 沿法线抬高。
高度（沿身体法线，离 spec.surface 的距离）：底面 Hb 0.05～0.28 米（后缘高、前缘低，像瓦片翘起来），
顶面 = 底面 + 厚度 + 拱 + 中棱 + 缘边（缘边：甲缘往里 0.17 米一道加厚的珠边、0.42 米一道浅沟、最外沿往上翻）。"""
import math

import numpy as np

from watcher import spec
from watcher import shell_np as snp

D = math.radians
NS = 720          # 甲缘的密采样数

# 各区的参数：T 厚度、Tf 前缘藏起来那段的厚度、hbf/hbb 前/后的底面高度、bead/furrow/flare 缘边珠边/浅沟/外翻、
# keel 中棱高、dome 拱、ovl 前缘藏到前一圈底下多少米、sp 低模甲缘点距（米）
ZONES = {
    "dorsal": dict(T=0.50, Tf=0.09, hbf=0.05, hbb=0.28, bead=0.065, furrow=0.012, flare=0.055, keel=0.22, dome=0.26,
                   ovl=0.85, sp=0.62),
    "dlat": dict(T=0.45, Tf=0.09, hbf=0.05, hbb=0.27, bead=0.06, furrow=0.012, flare=0.05, keel=0.16, dome=0.22,
                 ovl=0.75, sp=0.62),
    "lat": dict(T=0.38, Tf=0.09, hbf=0.05, hbb=0.25, bead=0.055, furrow=0.01, flare=0.045, keel=0.10, dome=0.18,
                ovl=0.60, sp=0.6),
    "vent": dict(T=0.24, Tf=0.07, hbf=0.05, hbb=0.17, bead=0.04, furrow=0.008, flare=0.035, keel=0.0, dome=0.09,
                 ovl=0.32, sp=0.55),
    "cap": dict(T=0.45, Tf=0.09, hbf=0.05, hbb=0.24, bead=0.0, furrow=0.0, flare=0.0, keel=0.10, dome=0.26,
                ovl=0.60, sp=0.62),
}
ZONE_ID = {"dorsal": 0, "dlat": 1, "lat": 2, "vent": 3, "cap": 4}

RING_B = [52.0, 67.5, 86.5, 105.5, 124.0, 141.5, 157.0, 170.0]    # 各圈的分界（θ，度）；第 0 条实际用 spec.socket_rim（这里只是名义值）
ORBIT_BEHIND = 2.0                                          # 眼眶那圈甲的前缘比肉的甲缘（spec.socket_rim）再往后多少度
PADDLE_SEAM = 111.0                                         # 三对桨根部连成的线（φ，度）


def bound(k, ph):
    """第 k 条分界线（θ，弧度），沿 φ 略有起伏（左右不完全对称）。"""
    deg = RING_B[k] + np.zeros_like(ph)
    if k == 0:
        deg = np.degrees(spec.socket_rim(0.5 * math.pi - np.asarray(ph))) + ORBIT_BEHIND + 0.4 * np.sin(2 * ph + 0.5)
    else:
        deg = deg + 0.9 * np.cos(ph + 0.2 * k) + 0.7 * np.sin(2 * ph + 1.7 * k) + 0.35 * np.sin(3 * ph + 0.9 * k)
    return np.radians(deg)


def _cblur(x, sig):
    """周期数组的高斯模糊（sig：采样数）。"""
    r = int(3 * sig)
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sig) ** 2)
    k /= k.sum()
    return np.convolve(np.concatenate([x[-r:], x, x[:r]]), k, mode="valid")


def _rad_at(th, ph):
    return np.linalg.norm(snp.surf(snp.eye_dir(th, ph)), axis=-1)


# ---------------------------------------------------------------------------- 一片甲
class Plate:
    def __init__(self, name, kind, ring, zone, rng, ph0=0.0, ph1=0.0, tha=None, thb=None, orbit=False, row=0):
        self.name = name
        self.kind = kind            # "ring" / "cap"
        self.ring = ring
        self.zone = zone
        self.row = row              # 腹面两排：0 前排、1 后排
        self.orbit = orbit
        self.prm = dict(ZONES[zone])
        self.rng = rng
        self.seed = int(rng.integers(1, 1 << 20))
        self.phc = 0.5 * (ph0 + ph1)
        self.wph = 0.5 * (ph1 - ph0)
        self.tha, self.thb = tha, thb
        j = lambda a: 1.0 + rng.uniform(-a, a)
        self.thick_j = j(0.1)
        self.rim_j = j(0.15)
        self.keel_j = j(0.15)
        self.spikes = []
        if orbit:
            self.prm["Tf"] = self.prm["T"] = self.prm["T"] * 1.1
            self.prm["hbf"] = 0.08

    # ------------------------------------------------------------ 参数 → 方向
    def dirs(self, a, b):
        if self.kind == "ring":
            ph = self.phc + a * self.wph
            ta, tb = self.tha(ph), self.thb(ph)
            th = 0.5 * (ta + tb) + b * 0.5 * (tb - ta)
        else:
            ph = np.arctan2(a, b)
            rr = np.hypot(a, b)
            th = math.pi - rr * (math.pi - self.tha(ph))
        return snp.eye_dir(th, ph), th, ph

    def ab(self, s, r):
        rho = self.rho_at(s)
        ang = 2 * math.pi * s
        return r * rho * np.sin(ang), r * rho * np.cos(ang)

    def sr(self, a, b):
        s = (np.arctan2(a, b) / (2 * math.pi)) % 1.0
        return s, np.hypot(a, b) / self.rho_at(s)

    def _tab(self, tab, s):
        return np.interp(np.asarray(s) * NS, np.arange(NS + 1), np.append(tab, tab[0]))

    def rho_at(self, s):
        return self._tab(self.rho, s)

    # ------------------------------------------------------------ 甲缘
    def setup(self, avoid):
        """avoid：[(点, 半径)]（桨根、虹吸口），甲缘在这些圆里的部分往里收。"""
        rng = self.rng
        s = np.arange(NS) / NS
        ang = 2 * math.pi * s
        sa, ca = np.sin(ang), np.cos(ang)
        if self.kind == "ring":
            pf, pb = 5.5, 2.8 + rng.uniform(-0.3, 0.3)       # 前缘方、后缘圆
            self.pf = pf
            p = np.where(ca < 0, pf, pb)
            rho = 1.0 / (np.abs(sa) ** p + np.abs(ca) ** p) ** (1.0 / p)
        else:
            rho = np.ones(NS)
        for k in (2, 3, 5):
            rho = rho * (1 + 0.018 / k * 2 * np.sin(k * ang + rng.uniform(0, 6.28)))
        # 让开桨根、虹吸口
        notch = np.zeros(NS)
        rr = np.linspace(0, 1, 61)
        self.dropped = False
        for q, rad in avoid:
            a = rr[None, :] * (rho * sa)[:, None]
            b = rr[None, :] * (rho * ca)[:, None]
            d, _, _ = self.dirs(a, b)
            dist = np.linalg.norm(snp.surf(d) - np.asarray(q)[None, None, :], axis=-1)
            inside = dist < rad
            if not inside.any():
                continue
            if inside[:, 0].any():
                self.dropped = True
                return
            first = np.argmax(inside, axis=1)
            has = inside.any(1)
            scale = rr[np.maximum(first - 1, 0)]
            rho = np.where(has, rho * scale, rho)
            notch = np.maximum(notch, has.astype(float))
        if notch.any():
            k = np.exp(-0.5 * (np.arange(-24, 25) / 7.0) ** 2)
            k /= k.sum()
            pad = lambda x: np.concatenate([x[-24:], x, x[:24]])
            blur = np.convolve(pad(rho), k, mode="valid")
            rho = np.minimum(rho, blur)
            notch = np.clip(np.convolve(pad(notch), k, mode="valid") * 1.6, 0, 1)
        self.rho = rho
        self.notch = notch
        # 甲缘点、辐条长、甲缘法向
        d, th, ph = self.dirs(rho * sa, rho * ca)
        O = snp.surf(d)
        self.O = O
        self.No = snp.nrm(O)
        a = rr[None, :] * (rho * sa)[:, None]
        b = rr[None, :] * (rho * ca)[:, None]
        pts = snp.surf(self.dirs(a, b)[0])
        seg = np.linalg.norm(np.diff(pts, axis=1), axis=-1)
        self.L = seg.sum(1)
        T = np.roll(O, -1, 0) - np.roll(O, 1, 0)
        Tn = snp.normalize(T)
        sp = snp.normalize(pts[:, -1] - pts[:, -4])
        sinpsi = np.clip(np.linalg.norm(np.cross(sp, Tn), axis=-1), 0.5, 1.0)
        # 沿辐条到甲缘的「垂直」距离（米）；沿周向抹平，不然转角处的等高线会折出一道道斜棱
        self.Lp = _cblur(self.L * sinpsi, 10)
        self.Lh = float(self.Lp[NS // 2])              # 前缘中点到中心（米）
        Do = snp.normalize(np.cross(Tn, self.No))
        sgn = np.sign((Do * sp).sum(-1, keepdims=True))
        self.Do = Do * np.where(sgn == 0, 1, sgn)
        # 参数平面里甲缘的外法向：朝前（-b）的那段是前缘
        da = np.roll(rho * sa, -1) - np.roll(rho * sa, 1)
        db = np.roll(rho * ca, -1) - np.roll(rho * ca, 1)
        n2 = np.stack([db, -da], 1)
        n2 /= np.linalg.norm(n2, axis=1, keepdims=True) + 1e-12
        n2 *= np.sign((n2[:, 0] * rho * sa + n2[:, 1] * rho * ca))[:, None]
        ff = snp.smoothstep(0.35, 0.8, -n2[:, 1])
        wj = 1 + 0.18 * np.sin(ang * 2 + rng.uniform(0, 6.28)) + 0.1 * np.sin(ang * 5 + rng.uniform(0, 6.28))
        ff = _cblur(ff, 16)
        if self.kind == "cap":
            self.w = np.zeros(NS)
            self.tuck = np.ones(NS)
        elif self.orbit:
            self.w = (1 + 1.6 * ff) * wj * self.rim_j
            self.tuck = np.zeros(NS)
        else:
            self.w = (1 - ff * (1 - notch)) * wj * self.rim_j
            self.tuck = ff * (1 - notch)
        self.brim = _cblur(ff, 24) * wj if self.orbit else np.zeros(NS)      # 眼眶：前缘往上翻起的厚檐
        self.k = float(np.clip(np.percentile(self.Lp, 25) / 1.4, 0.45, 1.0))
        # 甲片中心、局部坐标系（UV 用）
        self.C = snp.surf(self.dirs(np.zeros(1), np.zeros(1))[0])[0]
        self.Nc = snp.nrm(self.C[None])[0]
        back = snp.surf(self.dirs(*self.ab(np.zeros(1), np.full(1, 0.3)))[0])[0] - self.C
        ey = back - self.Nc * back.dot(self.Nc)
        self.ey = ey / np.linalg.norm(ey)
        self.ex = np.cross(self.ey, self.Nc)
        # 周长参数 σ（按甲缘弧长均匀）：σ = 0 ↔ s = 0（后缘中点），σ = 0.5 ↔ s = 0.5（前缘中点）
        seg = np.linalg.norm(np.diff(np.vstack([O, O[:1]]), axis=0), axis=1)
        self.perim = seg.sum()
        tn = np.diff(np.vstack([Tn, Tn[:1]]), axis=0)
        kap = np.linalg.norm(tn, axis=1) / np.maximum(seg, 1e-6)          # 甲缘转弯的曲率（1/米）
        kap = np.convolve(np.concatenate([kap[-8:], kap, kap[:8]]), np.ones(17) / 17, mode="valid")
        cum = np.concatenate([[0], np.cumsum(seg * (1 + 0.6 * np.clip(kap, 0, 4)))])
        h = NS // 2
        sig = np.empty(NS + 1)
        sig[:h + 1] = 0.5 * cum[:h + 1] / cum[h]
        sig[h:] = 0.5 + 0.5 * (cum[h:] - cum[h]) / (cum[-1] - cum[h])
        self._sig_tab = sig
        # 甲缘的总体尺寸
        self.half_w = 0.5 * np.linalg.norm(O[NS // 4] - O[3 * NS // 4])

    def s_of_sig(self, sig):
        return np.interp(np.asarray(sig) % 1.0, self._sig_tab, np.arange(NS + 1) / NS)

    # ------------------------------------------------------------ 高度
    def heights(self, s, r):
        """→ dict：位置用的方向、表面点、法线，顶面 Ht、底面 Hb，以及 e（离甲缘的距离）等。"""
        P = self.prm
        a, b = self.ab(s, r)
        d, th, ph = self.dirs(a, b)
        S = snp.surf(d)
        N = snp.nrm(S)
        Lp = self._tab(self.Lp, s)
        e = (1 - r) * Lp
        k = self.k
        ovl = P["ovl"] * (0.8 if self.row == 1 else 1.0) + 0.05
        w = self._tab(self.w, s)
        if self.kind == "ring":
            # 离前缘的距离：按 b 量（光滑，不像按辐条量的 e 那样在转角折出斜棱；藏到前一圈底下的就是 b 靠前的那一条）
            ef = np.maximum(b + 1, 0) * self.Lh        # b = -1 就是这一圈前缘那条线（θa）
            nt = 1 - self._tab(self.notch, s)
            tk = 0.0 * ef if self.orbit else nt * (1 - snp.smoothstep(ovl, ovl + 0.55, ef))
        else:
            tk = self._tab(self.tuck, s) * (1 - snp.smoothstep(ovl, ovl + 0.55, e))
        if self.kind == "ring":
            Hb = P["hbf"] + (P["hbb"] - P["hbf"]) * snp.smoothstep(-1, 1, b)
            T = P["T"] * self.thick_j * (0.88 + 0.12 * snp.smoothstep(-1, 1, b))
        else:
            Hb = P["hbf"] + (P["hbb"] - P["hbf"]) * (1 - r * r)
            T = P["T"] * self.thick_j
        Tf = min(P["Tf"], P["T"] * self.thick_j * 0.88)
        feat = 1 - tk
        g = lambda x, c, wd: np.exp(-((x - c) / wd) ** 2)
        rim = w * (P["bead"] * k * g(e, 0.17 * k, 0.075 * k) - P["furrow"] * k * g(e, 0.42 * k, 0.11 * k)
                   + P["flare"] * k * np.exp(-e / (0.2 * k)))
        if self.kind == "ring":
            dome = P["dome"] * (1 - np.minimum(np.abs(a) ** 3, 1)) * (1 - np.minimum(np.abs(b) ** 3, 1))
        else:
            dome = P["dome"] * (1 - r * r)
        # 中棱：沿甲片中线（φ = 中心经线）；尾盖沿背中线
        phk = self.phc if self.kind == "ring" else 0.0
        dk = np.abs(np.sin(snp.wrap(ph - phk))) * np.sin(th) * np.linalg.norm(S, axis=-1)
        sk = 0.42 * (0.75 + 0.25 * k)
        keel = P["keel"] * self.keel_j * np.exp(-(dk / sk) ** 2) * snp.smoothstep(0.04, 0.32, e)
        if self.zone == "dorsal":
            c2 = 0.45 * self.half_w
            keel = keel + 0.05 * np.exp(-((dk - c2) / 0.22) ** 2) * snp.smoothstep(0.2, 0.7, e)
        und = 0.022 * snp.perlin(S / 1.9, seed=self.seed)
        if self.orbit:
            rim = rim + nt * 0.3 * self.rim_j * np.exp(-ef / 0.6)
        Ht = Hb + Tf + (T - Tf) * feat + feat * (rim + dome + keel + und)
        return dict(S=S, N=N, Ht=Ht, Hb=Hb, e=e, tk=tk, w=w, dk=dk, th=th, ph=ph, a=a, b=b)

    def top(self, s, r, dh=0.0):
        h = self.heights(s, r)
        return h["S"] + h["N"] * (h["Ht"] + dh)[..., None], h

    def under(self, s, r, rd):
        h = self.heights(s, r)
        hb = h["Hb"] + 0.5 * self.prm["Tf"] * (1 - (r / rd) ** 2)
        return h["S"] + h["N"] * hb[..., None], h

    # ------------------------------------------------------------ 环的径向位置
    def ctrl_r(self, s):
        """顶面几道控制环在辐条 s 上的 r：A（前缘藏起来那段的尽头）、B（开始藏）、C（浅沟）、D（珠边），以及底面的 rd（内卷边的内沿）。"""
        P = self.prm
        Lp = self._tab(self.Lp, s)
        k = self.k
        ovl = P["ovl"] * (0.8 if self.row == 1 else 1.0) + 0.05
        rA = np.clip(1 - (ovl + 0.6) / Lp, 0.12, 0.8)
        rB = np.maximum(1 - (ovl + 0.05) / Lp, rA + 0.06)
        rC = np.maximum(1 - 0.42 * k / Lp, rB + 0.05)
        rD = np.clip(np.maximum(1 - 0.17 * k / Lp, rC + 0.03), 0, 0.985)
        rd = np.clip(1 - (0.22 * k + 0.12) / Lp, 0.3, 0.9)
        return rA, rB, rC, rD, rd

    def lip_ctrl(self, s):
        """甲缘外翻的剖面控制点：[(往外多少米, 高度)]（从顶面甲缘一路卷到底面）。"""
        Ht0 = self.heights(s, np.ones_like(s))["Ht"]
        Hb0 = self.heights(s, np.ones_like(s))["Hb"]
        w = self._tab(self.w, s)
        T0 = Ht0 - Hb0
        c = np.clip(0.3 * T0, 0.035, 0.12) * (0.6 + 0.4 * np.clip(w, 0, 1.5))
        u = np.minimum(0.3 * T0, 0.14)           # 外壁往甲底下收（甲缘卷过来，底下是一道阴影）
        return [(np.zeros_like(s), Ht0), (0.6 * c, Ht0 - 0.25 * c), (0.85 * c, Ht0 - 0.8 * c),
                (0.3 * c - 0.45 * u, 0.5 * (Ht0 + Hb0) - 0.1 * c), (-u, Hb0 + 0.035), (-u - 0.06, Hb0 + 0.004)]

    def lip_point(self, s, out, h):
        O = np.stack([self._tab(self.O[:, i], s) for i in range(3)], -1)
        N = snp.normalize(np.stack([self._tab(self.No[:, i], s) for i in range(3)], -1))
        Do = snp.normalize(np.stack([self._tab(self.Do[:, i], s) for i in range(3)], -1))
        return O + Do * out[..., None] + N * h[..., None]


# ---------------------------------------------------------------------------- 排布
def avoid_list():
    out = []
    for i in range(len(spec.PADDLES)):
        for side in (-1, 1):
            out.append((np.array(spec.paddle_root(i, side)), 1.25))
    out.append((np.array(spec.surface(spec.SIPHON_DIR)), spec.SIPHON_R + 0.15))
    return out


def layout(rng):
    plates = []
    # 桨根连成的缝：有桨的那几圈，缝就对准那支桨的根（φ），桨根周围的甲缘再咬掉一个圆
    pph = [float(snp.eye_tp(np.array(spec.paddle_root(i, 1)))[1]) for i in range(len(spec.PADDLES))]
    seam_k = {0: pph[0], 1: pph[0], 2: pph[1], 3: pph[2]}

    def ring_fn(k, ovl_m):
        """第 k 圈前缘（往前伸 ovl_m 米藏到前一圈底下）。"""
        if k == 0:
            return lambda ph: bound(0, ph)
        return lambda ph: bound(k, ph) - ovl_m / _rad_at(bound(k, ph), ph)

    for k in range(len(RING_B) - 1):
        seam = seam_k.get(k, D(PADDLE_SEAM))
        thm = 0.5 * (D(RING_B[k]) + D(RING_B[k + 1]))
        mpr_d = float(_rad_at(thm, D(50)) * math.sin(thm))      # 每弧度 φ 多少米
        mpr_v = float(_rad_at(thm, D(150)) * math.sin(thm))
        if k == 0:
            base_d = [D(18), D(54), D(82)]
            base_v = [D(145)]
            w0 = D(18)
        else:
            w0 = 2.5 / mpr_d
            nd = max(1, int(round((seam - w0) * mpr_d / 4.9)))
            base_d = [w0 + (seam - w0) * j / nd for j in range(nd)]
            nv = max(1, int(round((math.pi - seam) * mpr_v / 2.8)))
            base_v = [seam + (math.pi - seam) * j / nv for j in range(1, nv)]
        for side in (1, -1):
            # 这一侧的缝（φ ≥ 0 一侧的值，左侧最后取负）：中心片半宽、背侧/体侧的缝、111°、腹面的缝、180°
            sd = [base_d[0] + rng.uniform(-0.06, 0.06) * base_d[0]]
            for x in base_d[1:]:
                sd.append(x + rng.uniform(-0.1, 0.1) * (seam - w0) / max(len(base_d), 1))
            sd.append(seam + D(rng.uniform(-0.5, 0.5)))
            sv = [x + rng.uniform(-0.1, 0.1) * (math.pi - seam) / (len(base_v) + 1) for x in base_v]
            seams = sd + sv + [math.pi]
            if side == 1:
                right_w0 = sd[0]
            else:
                left_w0 = sd[0]
            # 背侧、体侧、腹面
            for j in range(len(seams) - 1):
                p0, p1 = seams[j], seams[j + 1]
                if j < len(sd) - 1:
                    zone = "dlat" if j == 0 else "lat"
                else:
                    zone = "vent"
                gap = (0.17 if zone != "vent" else 0.22) + rng.uniform(-0.05, 0.05)
                g0 = 0.5 * gap / (mpr_d if zone != "vent" else mpr_v)
                gap = (0.17 if zone != "vent" else 0.22) + rng.uniform(-0.05, 0.05)
                g1 = 0.5 * gap / (mpr_d if zone != "vent" else mpr_v)
                lo, hi = p0 + g0, p1 - g1
                if side == -1:
                    lo, hi = -hi, -lo
                rows = [0, 1] if (zone == "vent" and k > 0) else [None]
                for row in rows:
                    ovl = ZONES[zone]["ovl"]
                    if row is None:
                        tha, thb = ring_fn(k, ovl), (lambda ph, k=k: bound(k + 1, ph))
                    else:
                        mj = rng.uniform(-0.08, 0.08)

                        def mid(ph, k=k, mj=mj):
                            a0 = bound(k, ph)
                            return a0 + (0.5 + mj) * (bound(k + 1, ph) - a0)

                        if row == 0:
                            tha, thb = ring_fn(k, ovl), mid
                        else:
                            ovs = 0.8 * ovl
                            tha = (lambda ph, mid=mid, ovs=ovs: mid(ph) - ovs / _rad_at(mid(ph), ph))
                            thb = (lambda ph, k=k: bound(k + 1, ph))
                    nm = "R%d_%s%s_%s%d" % (k, "R" if side == 1 else "L", "" if row is None else "ab"[row], zone, j)
                    plates.append(Plate(nm, "ring", k, zone, np.random.default_rng(rng.integers(1 << 30)),
                                        lo, hi, tha, thb, orbit=(k == 0), row=row or 0))
        # 背中一片
        gl = 0.5 * (0.17 + rng.uniform(-0.05, 0.05)) / mpr_d
        gr = 0.5 * (0.17 + rng.uniform(-0.05, 0.05)) / mpr_d
        plates.append(Plate("R%d_M_dorsal" % k, "ring", k, "dorsal", np.random.default_rng(rng.integers(1 << 30)),
                            -left_w0 + gl, right_w0 - gr, ring_fn(k, ZONES["dorsal"]["ovl"]),
                            (lambda ph, k=k: bound(k + 1, ph)), orbit=(k == 0)))
    # 尾盖
    ovl = ZONES["cap"]["ovl"]
    kc = len(RING_B) - 1
    plates.append(Plate("Cap", "cap", kc, "cap", np.random.default_rng(rng.integers(1 << 30)),
                        tha=lambda ph: bound(kc, ph) - ovl / _rad_at(bound(kc, ph), ph)))
    avoid = avoid_list()
    out = []
    for p in plates:
        p.setup(avoid)
        if p.dropped:
            print("shell: 甲片", p.name, "中心落在让开区里，去掉")
            continue
        out.append(p)
    return out
