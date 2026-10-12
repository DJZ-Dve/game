"""桨的参数化形体（numpy）：一支桨 = 沿骨链的一根扁管，截面从根节的椭圆过渡到叶片的翼型。
低模、高模用同一套函数（paddle_grid），只是采样密度不同；高模再沿法线加细节（paddle_high.py）。

解剖（参考海蝎的游泳足 + 海龟鳍肢，苍白、半透明）：
  根部肉褶（x < xs + 0.5，软）：从身体表面鼓起的一圈肉，贴进身体（第一圈压到体表下 5 厘米），盖住接缝；
  根节（0 ～ 0.25L，硬）：粗、近椭圆截面，桶形（中间略鼓）；
  中节（0.25L ～ 0.55L，硬）：变宽变扁，截面开始有翼型；
  叶片（0.55L ～ L）：前缘一根厚的硬「桨骨」（翼型最厚处），往后放射出 6～8 根硬鳍条，鳍条之间是薄的软膜，
    后缘在鳍条之间微微凹进去（扇贝边）；叶尖圆、往后掠、往下卷一点，叶片略拱、沿长度扭 14°；
  关节（两处，软）：前一节的远端甲唇微微外翻，后面一圈收窄的关节膜。

坐标：x = 沿桨轴（骨链方向 d）离 o 的距离，o = 骨链起点往外 0.6 米（关节在 x = 0.25L、0.55L，叶尖 x = L）；
截面参数 v ∈ [-π, π)：c = (1 - cos v) / 2 是弦向位置（0 前缘、1 后缘），v > 0 上表面、v < 0 下表面；
A = 弦向（指向前缘，大致朝前），N = 厚度方向（大致朝上）；左侧的桨是右侧的镜像（A、N 跟着镜像）。
"""
import math

import numpy as np

from watcher import spec
from watcher import shell_np as snp

ss = snp.smoothstep
AXES = np.array([spec.AX, spec.AY, spec.AZ], dtype=np.float64)
C_SPAR = 0.24        # 叶片上桨骨（硬前缘）到弦向哪里为止
T_MIN = 0.03         # 后缘最薄（低模；高模同）


def ell_k(p):
    """> 1 在身体外面。"""
    return np.sqrt(((p / AXES) ** 2).sum(-1))


def nac(c):
    """对称翼型（NACA 00xx）的半厚度，归一化到最大 1（在 c = 0.3）。"""
    c = np.clip(c, 0.0, 1.0)
    return (0.2969 * np.sqrt(c) - 0.1260 * c - 0.3516 * c ** 2 + 0.2843 * c ** 3 - 0.1036 * c ** 4) / 0.1


class Paddle:
    def __init__(self, i, side):
        self.i, self.side = i, side
        self.name = "Paddle%s%d" % ("L" if side < 0 else "R", i)
        P = spec.PADDLES[i]
        self.L, self.Wmax = P["length"], P["width"]
        self.sc = self.Wmax / 3.4
        pts = [np.array(p, dtype=np.float64) for p in spec.paddle_rest_points(i, side)]
        self.pts = pts
        d = pts[-1] - pts[0]
        self.d = d / np.linalg.norm(d)
        self.o = pts[0]                 # 骨链起点（spec 里 start + 0.6d）
        self.xj = [float((pts[k] - self.o) @ self.d) for k in (1, 2)]
        up = np.array([0.0, 0.0, 1.0])
        A = side * np.cross(up, self.d)
        self.A0 = A / np.linalg.norm(A)
        self.N0 = side * np.cross(self.d, self.A0)
        # 桨轴穿出体表的位置
        lo, hi = -0.6, 3.0
        for _ in range(50):
            m = 0.5 * (lo + hi)
            if ell_k(self.o + self.d * m) < 1.0:
                lo = m
            else:
                hi = m
        self.xs = 0.5 * (lo + hi)
        # 鳍条（叶片上从桨骨放射出去；左右、各支不一样）
        rng = spec.rng_for(self.name)
        n = int(rng.integers(6, 9))
        phis = np.linspace(math.radians(9), math.radians(74), n)
        phis += rng.uniform(-0.25, 0.25, n) * (phis[1] - phis[0])
        self.rays = np.sort(phis)
        self.ray_w = rng.uniform(0.85, 1.15, n)
        self.seed = int(rng.integers(1, 1 << 20))

    # ------------------------------------------------------------ 沿长度的剖面参数
    def prof(self, x):
        L, sc, Wm = self.L, self.sc, self.Wmax
        x = np.asarray(x, dtype=np.float64)
        xn = x / L
        q = np.clip((xn - 0.55) / 0.45, 0.0, 1.0)
        bar0 = np.sin(math.pi * np.clip(xn / 0.25, 0, 1))
        bar1 = np.sin(math.pi * np.clip((xn - 0.25) / 0.30, 0, 1))
        tipf = np.sqrt(np.clip(1 - (np.clip(q - 0.58, 0, None) / 0.42) ** 2, 0, 1))
        w0 = 2.25 * sc                     # 根节最粗处
        w1 = 2.9 * sc                      # 中节末（叶片起点）
        rise = w1 + (1.15 * Wm - w1) * ss(0.0, 0.45, q)
        W = np.where(xn < 0.25, (w0 - 0.30 * sc * ss(0, 0.25, xn)) * (1 + 0.04 * bar0),
                     np.where(xn < 0.55, (1.95 * sc + (w1 - 1.95 * sc) * ss(0.25, 0.55, xn)) * (1 + 0.03 * bar1),
                              rise * tipf))
        T = np.where(xn < 0.25, sc * (1.45 - 0.40 * ss(0, 0.25, xn)) * (1 + 0.05 * bar0),
                     np.where(xn < 0.55, sc * (1.0 - 0.45 * ss(0.25, 0.55, xn)) * (1 + 0.03 * bar1),
                              sc * (0.55 - 0.30 * q) * (0.45 + 0.55 * tipf)))
        f = np.where(xn < 0.25, 0.5, np.where(xn < 0.55, 0.5 - 0.08 * ss(0.25, 0.55, xn),
                                              0.42 - 0.12 * ss(0.0, 0.3, q) + 0.2 * ss(0.6, 1.0, q)))
        a = np.where(xn < 0.25, 0.0, np.where(xn < 0.55, 0.6 * ss(0.27, 0.55, xn), 0.6 + 0.4 * ss(0.0, 0.25, q)))
        # 关节：远端甲唇略外翻、关节膜收窄
        fac = np.ones_like(x)
        for xj in self.xj:
            lip = np.exp(-((x - (xj - 0.10 * sc)) / (0.06 * sc)) ** 2)
            mem = np.exp(-((x - (xj + 0.05 * sc)) / (0.09 * sc)) ** 2)
            fac = fac + 0.035 * lip - 0.10 * mem
        # 根部肉褶往外张
        u = x - self.xs
        fl = 1.0 + 0.32 * np.exp(-np.maximum(u, 0.0) / 0.28)
        W = W * fac * fl
        T = T * fac * (1.0 + 0.8 * (fl - 1.0))
        return dict(W=W, T=T, f=f, a=a, q=q, xn=xn, tipf=tipf)

    # ------------------------------------------------------------ 叶片上的鳍条坐标
    def fan(self, x, c, W):
        """(X, Y) = 叶片上的米制坐标（沿长度、从桨骨往后），返回到扇心的距离 r 和角度 φ。"""
        X = (x - self.xj[1]) + 0.6 * self.sc
        Y = (c - C_SPAR) * W + 0.08 * self.sc
        return np.hypot(X, Y), np.arctan2(Y, X)

    def ray_field(self, x, c, W, width=1.0):
        """鳍条脊（0～1）和最近一根鳍条的编号、离它的米数、沿它的位置 r。"""
        r, ph = self.fan(x, c, W)
        best = np.full(np.shape(r), 9.0)
        idx = np.zeros(np.shape(r), dtype=np.int32)
        for k, p in enumerate(self.rays):
            dd = np.abs(r * np.sin(ph - p))
            closer = dd < best
            best = np.where(closer, dd, best)
            idx = np.where(closer, k, idx)
        rr = r / (0.45 * self.L + 0.6 * self.sc)
        hw = 0.085 * self.sc * width * self.ray_w[idx] * (1.0 - 0.45 * np.clip(rr, 0, 1))
        on = ss(C_SPAR - 0.02, C_SPAR + 0.06, c) * ss(self.xj[1] - 0.1, self.xj[1] + 0.35, x)
        return np.exp(-(best / hw) ** 2) * on, idx, best, r

    def scallop(self, x, W, q, tipf):
        """后缘在鳍条之间凹进去多少（米）。"""
        r, ph = self.fan(x, np.ones_like(x), W)
        near = np.zeros_like(r)
        for p in self.rays:
            near = np.maximum(near, np.exp(-((ph - p) * r / (0.24 * self.sc)) ** 2))
        return 0.075 * self.sc * (1.0 - near) * ss(0.02, 0.14, q) * ss(0.25, 0.6, tipf)

    # ------------------------------------------------------------ 网格
    def grid(self, xs, vs):
        """xs (ni,)、vs (nj,) → dict：P (ni, nj, 3) 和各种参数场。"""
        x = np.asarray(xs, dtype=np.float64)[:, None]
        v = np.asarray(vs, dtype=np.float64)[None, :]
        pr = self.prof(x)
        W, T, f, a, q, tipf = pr["W"], pr["T"], pr["f"], pr["a"], pr["q"], pr["tipf"]
        c = 0.5 * (1.0 - np.cos(v)) + 0 * x
        top = np.sign(np.sin(v)) + 0 * x
        half = 0.5 * T * ((1 - a) * 2 * np.sqrt(np.clip(c * (1 - c), 0, None)) + a * nac(c))
        half = np.maximum(half, 0.5 * T_MIN)
        sc_ = self.scallop(x[:, 0], W[:, 0], q[:, 0], tipf[:, 0])[:, None]
        ac = W * (f - c) - sc_ * c ** 4
        blade = ss(0.0, 0.3, q)
        nc = top * half + 0.035 * W * 4 * c * (1 - c) * blade
        # 扭转（前缘往下）、叶片后掠 + 下卷
        tw = math.radians(4) * ss(0.25, 1.0, pr["xn"]) + math.radians(10) * q ** 1.5
        ct, st = np.cos(tw)[..., None], np.sin(tw)[..., None]
        A = self.A0 * ct - self.N0 * st
        N = self.N0 * ct + self.A0 * st
        bk = 0.12 * self.Wmax * q ** 2
        dn = 0.30 * self.sc * q ** 2
        C = self.o + self.d * x[..., None] - self.A0 * bk[..., None] - self.N0 * dn[..., None]
        P = C + A * ac[..., None] + N * nc[..., None]
        # 贴体：第一圈压到体表下，其余在体表下的点推到体表外 1.5 厘米（根部自然成了圆角）
        k = ell_k(P)
        surf = P / k[..., None]
        nrm = snp.nrm(surf)
        first = (x - self.xs) < -0.05
        P = np.where(first[..., None], surf - nrm * 0.05,
                     np.where((k < 1.0 + 0.002)[..., None], surf + nrm * 0.015, P))
        return dict(P=P, x=np.broadcast_to(x, c.shape), c=c, top=top, W=W + 0 * c, T=T + 0 * c, q=q + 0 * c,
                    half=half, tipf=tipf + 0 * c, A=A, N=N)

    def tip(self):
        """叶尖点（截面缩成一点的地方）。"""
        return self.o + self.d * self.L - self.A0 * 0.12 * self.Wmax - self.N0 * 0.30 * self.sc


def stations(pd):
    """低模沿长度的采样（x，米）。"""
    sc, L = pd.sc, pd.L
    xs, (j1, j2) = pd.xs, pd.xj
    out = [xs - 0.15, xs, xs + 0.12, xs + 0.30, xs + 0.55]
    out += list(np.linspace(xs + 0.9, j1 - 0.35 * sc, 4))
    jt = [-0.20, -0.10, -0.02, 0.06, 0.15, 0.28]
    out += [j1 + t * sc for t in jt]
    out += list(np.linspace(j1 + 0.55 * sc, j2 - 0.35 * sc, 5))
    out += [j2 + t * sc for t in jt]
    qs = np.linspace(0.0, 1.0, 27) ** 0.85
    qs = 1 - (1 - qs) ** 1.25
    xb = L * (0.55 + 0.45 * qs)
    out += [x for x in xb if x > j2 + 0.5 * sc and x < L * 0.997]
    return np.array(out)


def soft_mask(pd, G, rays=None):
    """软组织（关节膜、根部肉褶、叶片鳍条之间的膜）= 1，硬的甲 = 0。"""
    x, c = G["x"], G["c"]
    sc = pd.sc
    jm = np.zeros_like(x)
    for xj in pd.xj:
        jm = np.maximum(jm, ss(xj - 0.07 * sc, xj - 0.02 * sc, x) * ss(xj + 0.22 * sc, xj + 0.13 * sc, x))
    cm = ss(pd.xs + 0.62, pd.xs + 0.40, x)
    if rays is None:
        rays = pd.ray_field(x, c, G["W"])[0]
    bm = ss(C_SPAR + 0.02, C_SPAR + 0.10, c) * ss(pd.xj[1] + 0.25 * sc, pd.xj[1] + 0.6 * sc, x) * (1 - rays)
    return np.maximum(np.maximum(jm, cm), bm)


def bone_weights(pd, x):
    """沿长度的骨骼权重：Body（根部肉褶）、三节。"""
    sc = pd.sc
    t1 = ss(pd.xj[0] - 0.15 * sc, pd.xj[0] + 0.20 * sc, x)
    t2 = ss(pd.xj[1] - 0.15 * sc, pd.xj[1] + 0.20 * sc, x)
    wb = ss(pd.xs + 0.45, pd.xs - 0.05, x)
    ws = [(1 - t1), (t1 - t2), t2]
    return wb, [w * (1 - wb) for w in ws]


def all_paddles():
    return [Paddle(i, side) for i in range(len(spec.PADDLES)) for side in (1, -1)]
