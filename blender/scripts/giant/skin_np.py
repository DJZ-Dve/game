"""皮用的 numpy 工具：spec 身体曲面的向量化版本（高模几百万个点一起算）、程序噪声。
和 spec.section / surface / body_coords 的公式完全一致（直接用 spec 的关键点和 PCHIP 斜率），只是一次算一整个数组。"""
import math

import numpy as np

from giant import spec

_P = spec._PROFILE
_XS = _P[:, 0]


def section(s):
    """s（数组）→ (半宽, 背高, 腹深, 中轴 z, 指数)，每个都是和 s 一样形状的数组。"""
    s = np.clip(np.asarray(s, dtype=np.float64), 0.0, 1.0)
    i = np.clip(np.searchsorted(_XS, s, side="right") - 1, 0, len(_XS) - 2)
    h = _XS[i + 1] - _XS[i]
    t = (s - _XS[i]) / h
    h00, h10, h01, h11 = 2 * t**3 - 3 * t**2 + 1, t**3 - 2 * t**2 + t, -2 * t**3 + 3 * t**2, t**3 - t**2
    out = []
    for c in range(1, 6):
        ys = _P[:, c]
        m = spec._SLOPES[c]
        out.append(h00 * ys[i] + h10 * h * m[i] + h01 * ys[i + 1] + h11 * h * m[i + 1])
    return out


def _se(c, e):
    return np.sign(c) * np.abs(c) ** (2.0 / e)


def surface(s, th):
    s = np.asarray(s, dtype=np.float64)
    th = np.asarray(th, dtype=np.float64)
    hw, ht, hb, zc, e = section(s)
    c, sn = np.cos(th), np.sin(th)
    x = hw * _se(sn, e)
    z = np.where(c >= 0, ht, hb) * _se(c, e)
    y = spec.HALF - spec.LENGTH * np.clip(s, -1, 2)
    return np.stack([x, np.broadcast_to(y, x.shape), zc + z], axis=-1)


def body_coords(p):
    """p: (n,3) → s, θ（同 spec.body_coords）"""
    s = np.clip((spec.HALF - p[:, 1]) / spec.LENGTH, 0.0, 1.0)
    hw, ht, hb, zc, e = section(s)
    dz = p[:, 2] - zc
    h = np.where(dz >= 0, ht, hb)
    u = p[:, 0] / np.maximum(hw, 1e-3)
    v = dz / np.maximum(h, 1e-3)
    uc = np.sign(u) * np.abs(u) ** (e / 2.0)
    vc = np.sign(v) * np.abs(v) ** (e / 2.0)
    return s, np.arctan2(uc, vc)


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


# ---------------------------------------------------------------------------- 噪声
def _hash3(ix, iy, iz, seed):
    """整数格点 → 0～1 的伪随机数（向量化，结果只取决于格点和 seed）。"""
    h = (ix.astype(np.int64) * 73856093) ^ (iy.astype(np.int64) * 19349663) ^ (iz.astype(np.int64) * 83492791) \
        ^ (seed * 2654435761)
    h = (h ^ (h >> 13)) * 1274126177
    h = h ^ (h >> 16)
    return (h & 0xFFFFFF).astype(np.float64) / float(0xFFFFFF)


_GRAD = np.array([[1, 1, 0], [-1, 1, 0], [1, -1, 0], [-1, -1, 0], [1, 0, 1], [-1, 0, 1], [1, 0, -1], [-1, 0, -1],
                  [0, 1, 1], [0, -1, 1], [0, 1, -1], [0, -1, -1], [1, 1, 0], [-1, 1, 0], [0, -1, 1], [0, -1, -1]],
                 dtype=np.float64)


def perlin(p, seed=0):
    """三维梯度噪声，p: (n,3)（已经按频率缩放好），返回约 -1～1。"""
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
    """三维 Worley：返回 (F1 距离, F2 距离, 最近点的随机值)，p 已经按格子大小缩放。"""
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


def nearest(points, samples):
    """points (n,3) 到采样点集 samples (m,3) 的最近距离和下标（mathutils 的 KD 树）。"""
    from mathutils import kdtree
    kd = kdtree.KDTree(len(samples))
    for i, q in enumerate(samples):
        kd.insert(q, i)
    kd.balance()
    d = np.empty(len(points))
    idx = np.empty(len(points), dtype=np.int64)
    for i, q in enumerate(points):
        _, j, dist = kd.find(q)
        d[i] = dist
        idx[i] = j
    return d, idx
