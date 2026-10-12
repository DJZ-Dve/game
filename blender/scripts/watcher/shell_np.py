"""甲壳用的 numpy 工具：身体椭球的向量化版本、以眼睛为极点的球坐标、程序噪声、环带拼网格。
（噪声从 giant/skin_np.py 拷来，不依赖鲨鱼的 spec。）"""
import math

import bpy
import numpy as np

from watcher import spec

_A = np.array([spec.AX, spec.AY, spec.AZ])
_A2 = _A * _A


# ---------------------------------------------------------------------------- 身体
def normalize(v):
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-12)


def surf(d):
    """方向 d (…,3) → 身体表面点（spec.surface 的向量化版本）。"""
    d = normalize(d)
    k = 1.0 / np.sqrt(((d / _A) ** 2).sum(-1, keepdims=True))
    return d * k


def nrm(p):
    """椭球表面点的朝外法线（spec.normal）。"""
    return normalize(p / _A2)


def eye_dir(th, ph):
    """以眼睛方向（+Y）为极点的球坐标 → 方向：th = 离 +Y 的角度，ph = 绕 Y 轴的方位（0 = 背 +Z，+90° = 右 +X，180° = 腹）。"""
    st = np.sin(th)
    return np.stack([st * np.sin(ph), np.cos(th), st * np.cos(ph)], -1)


def eye_tp(d):
    d = normalize(np.asarray(d, dtype=np.float64))
    return np.arccos(np.clip(d[..., 1], -1, 1)), np.arctan2(d[..., 0], d[..., 2])


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


# ---------------------------------------------------------------------------- 噪声
def _hash3(ix, iy, iz, seed):
    h = (ix.astype(np.int64) * 73856093) ^ (iy.astype(np.int64) * 19349663) ^ (iz.astype(np.int64) * 83492791) \
        ^ (seed * 2654435761)
    h = (h ^ (h >> 13)) * 1274126177
    h = h ^ (h >> 16)
    return (h & 0xFFFFFF).astype(np.float64) / float(0xFFFFFF)


_GRAD = np.array([[1, 1, 0], [-1, 1, 0], [1, -1, 0], [-1, -1, 0], [1, 0, 1], [-1, 0, 1], [1, 0, -1], [-1, 0, -1],
                  [0, 1, 1], [0, -1, 1], [0, 1, -1], [0, -1, -1], [1, 1, 0], [-1, 1, 0], [0, -1, 1], [0, -1, -1]],
                 dtype=np.float64)


def perlin(p, seed=0):
    """三维梯度噪声，p: (n,3)（已按频率缩放），约 -1～1。"""
    out = np.empty(len(p))
    for a in range(0, len(p), 400000):
        q = p[a:a + 400000]
        i0 = np.floor(q).astype(np.int64)
        f = q - i0
        w = f * f * f * (f * (f * 6 - 15) + 10)
        acc = 0.0
        for dx in (0, 1):
            for dy in (0, 1):
                for dz in (0, 1):
                    hsh = _hash3(i0[:, 0] + dx, i0[:, 1] + dy, i0[:, 2] + dz, seed)
                    g = _GRAD[(hsh * 16).astype(np.int64) & 15]
                    d = f - np.array([dx, dy, dz], dtype=np.float64)
                    dot = (g * d).sum(1)
                    wx = w[:, 0] if dx else 1 - w[:, 0]
                    wy = w[:, 1] if dy else 1 - w[:, 1]
                    wz = w[:, 2] if dz else 1 - w[:, 2]
                    acc = acc + dot * wx * wy * wz
        out[a:a + 400000] = acc
    return out


def fbm(p, octaves=3, seed=0, lac=2.03, gain=0.5):
    tot = np.zeros(len(p))
    amp, norm = 1.0, 0.0
    q = p.copy()
    for o in range(octaves):
        tot += amp * perlin(q, seed + 17 * o)
        norm += amp
        amp *= gain
        q = q * lac
    return tot / norm


def voronoi(p, seed=0, jitter=0.85):
    """三维 Worley：(F1, F2, 最近点随机值)，p 已按格子大小缩放。"""
    n = len(p)
    f1 = np.full(n, 9.0)
    f2 = np.full(n, 9.0)
    rid = np.zeros(n)
    for a in range(0, n, 300000):
        q = p[a:a + 300000]
        i0 = np.floor(q).astype(np.int64)
        b1 = np.full(len(q), 9.0)
        b2 = np.full(len(q), 9.0)
        br = np.zeros(len(q))
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    cx, cy, cz = i0[:, 0] + dx, i0[:, 1] + dy, i0[:, 2] + dz
                    jx = _hash3(cx, cy, cz, seed)
                    jy = _hash3(cx, cy, cz, seed + 1)
                    jz = _hash3(cx, cy, cz, seed + 2)
                    fp = np.stack([cx + 0.5 + (jx - 0.5) * jitter, cy + 0.5 + (jy - 0.5) * jitter,
                                   cz + 0.5 + (jz - 0.5) * jitter], axis=1)
                    d = np.sqrt(((q - fp) ** 2).sum(1))
                    closer = d < b1
                    b2 = np.where(closer, b1, np.minimum(b2, d))
                    br = np.where(closer, jx * 0.37 + jy * 0.63, br)
                    b1 = np.where(closer, d, b1)
        f1[a:a + 300000] = b1
        f2[a:a + 300000] = b2
        rid[a:a + 300000] = br
    return f1, f2, rid


# ---------------------------------------------------------------------------- 环带网格
def stitch(ia, sa, ib, sb):
    """两圈闭合的环（顶点下标 ia / ib，各自的周向参数 sa / sb 从 0 开始递增、< 1）之间铺三角形。
    单个点（极点）也行。返回 (m,3) 的三角形（去掉退化的）。"""
    na, nb = len(ia), len(ib)
    ea = np.concatenate([sa[1:], [sa[0] + 1.0]])
    eb = np.concatenate([sb[1:], [sb[0] + 1.0]])
    keys = np.concatenate([ea, eb])
    isa = np.concatenate([np.ones(na, dtype=np.int64), np.zeros(nb, dtype=np.int64)])
    order = np.argsort(keys, kind="stable")
    isa = isa[order]
    ca = np.cumsum(isa) - isa
    cb = np.cumsum(1 - isa) - (1 - isa)
    a0 = ia[ca % na]
    a1 = ia[(ca + 1) % na]
    b0 = ib[cb % nb]
    b1 = ib[(cb + 1) % nb]
    t = np.where(isa[:, None] == 1, np.stack([a0, a1, b0], 1), np.stack([a0, b1, b0], 1))
    ok = (t[:, 0] != t[:, 1]) & (t[:, 1] != t[:, 2]) & (t[:, 0] != t[:, 2])
    return t[ok]


class RingMesh:
    """一圈一圈往外长的封闭网格（极点 → 环 → … → 极点）。每圈：位置 (n,3)、周向参数 (n,)、任意逐点属性。"""

    def __init__(self):
        self.rings = []

    def add(self, p, sig, **attrs):
        p = np.asarray(p, dtype=np.float64).reshape(-1, 3)
        self.rings.append((p, np.asarray(sig, dtype=np.float64).reshape(-1), attrs))

    def build(self):
        """→ co (n,3)、tris (m,3)、band (m,)（三角形在第几条带上）、属性 dict、每圈的起始下标"""
        cos, tris, bands, starts = [], [], [], []
        keys = set()
        for _, _, at in self.rings:
            keys |= set(at)
        attrs = {k: [] for k in keys}
        off = 0
        for p, s, at in self.rings:
            starts.append(off)
            cos.append(p)
            for k in keys:
                v = np.asarray(at.get(k, 0.0), dtype=np.float64)
                attrs[k].append(np.full(len(p), float(v)) if v.ndim == 0 else v.reshape(len(p)))
            off += len(p)
        for j in range(len(self.rings) - 1):
            ia = np.arange(starts[j], starts[j] + len(self.rings[j][0]))
            ib = np.arange(starts[j + 1], starts[j + 1] + len(self.rings[j + 1][0]))
            t = stitch(ia, self.rings[j][1], ib, self.rings[j + 1][1])
            tris.append(t)
            bands.append(np.full(len(t), j))
        co = np.concatenate(cos)
        tris = np.concatenate(tris)
        band = np.concatenate(bands)
        # 朝向：封闭网格的有向体积为正 = 法线朝外
        a, b, c = co[tris[:, 0]], co[tris[:, 1]], co[tris[:, 2]]
        vol = np.einsum("ij,ij->i", a, np.cross(b, c)).sum()
        if vol < 0:
            tris = tris[:, [0, 2, 1]]
        return co, tris, band, {k: np.concatenate(v) for k, v in attrs.items()}, starts


def make_mesh(name, co, tris, coll=None, uv=None, smooth=True):
    """numpy → Blender 网格物体。uv：(m*3,2) 逐角 UV（可选，写进 spec.UV_MAIN）。"""
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(co))
    me.vertices.foreach_set("co", co.astype(np.float32).ravel())
    me.loops.add(len(tris) * 3)
    me.loops.foreach_set("vertex_index", tris.astype(np.int32).ravel())
    me.polygons.add(len(tris))
    me.polygons.foreach_set("loop_start", np.arange(0, len(tris) * 3, 3, dtype=np.int32))
    me.update(calc_edges=True)
    if uv is not None:
        lay = me.uv_layers.new(name=spec.UV_MAIN)
        lay.data.foreach_set("uv", uv.astype(np.float32).ravel())
    if smooth:
        me.shade_smooth()
    ob = bpy.data.objects.new(name, me)
    (coll or bpy.context.scene.collection).objects.link(ob)
    return ob


class Nb:
    """顶点邻接平均（模糊、曲率用）。"""

    def __init__(self, e, n):
        self.a, self.b = e[:, 0], e[:, 1]
        self.n = n
        self.deg = np.maximum(np.bincount(self.a, minlength=n) + np.bincount(self.b, minlength=n), 1)

    def avg(self, x):
        return (np.bincount(self.a, weights=x[self.b], minlength=self.n) +
                np.bincount(self.b, weights=x[self.a], minlength=self.n)) / self.deg

    def blur(self, x, it):
        for _ in range(it):
            x = 0.5 * x + 0.5 * self.avg(x)
        return x
