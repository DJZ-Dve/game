"""眼睛部件的工具：numpy 值噪声、用数组快速建网格（低模带 UV0）、沿路径的平行传输标架、扫管。
只给 eyes.py / eyes_parasite.py 用。"""
import math

import bpy
import numpy as np

from giant import spec


# ---------------------------------------------------------------------------- 噪声（numpy 向量化，确定性）
def _hash(ix, iy, iz, seed):
    h = (ix * 73856093) ^ (iy * 19349663) ^ (iz * 83492791) ^ (seed * 2654435761)
    h = h & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    h = h ^ (h >> 16)
    return (h & 0xFFFFFF).astype(np.float64) / float(0xFFFFFF)


def vnoise3(p, seed=0):
    """3D 值噪声，p: (N,3)，返回 [0,1]。五次插值，没有块状接缝。"""
    p = np.asarray(p, dtype=np.float64)
    i = np.floor(p).astype(np.int64)
    f = p - i
    w = f * f * f * (f * (f * 6 - 15) + 10)
    out = np.zeros(len(p))
    for dx in (0, 1):
        wx = w[:, 0] if dx else 1 - w[:, 0]
        for dy in (0, 1):
            wy = w[:, 1] if dy else 1 - w[:, 1]
            for dz in (0, 1):
                wz = w[:, 2] if dz else 1 - w[:, 2]
                out += wx * wy * wz * _hash(i[:, 0] + dx, i[:, 1] + dy, i[:, 2] + dz, seed)
    return out


def fbm3(p, octaves=4, seed=0, lac=2.03, gain=0.5):
    """分形噪声，大约 [0,1]（均值 0.5）。"""
    p = np.asarray(p, dtype=np.float64)
    acc = np.zeros(len(p))
    amp, tot = 1.0, 0.0
    for o in range(octaves):
        acc += amp * vnoise3(p * (lac ** o) + o * 17.3, seed + o * 101)
        tot += amp
        amp *= gain
    return acc / tot


def noise1(x, seed=0):
    """1D 值噪声（周期用不着，φ 方向自己乘半径换成弧长）。"""
    x = np.atleast_1d(np.asarray(x, dtype=np.float64))
    z = np.zeros_like(x)
    return vnoise3(np.stack([x, z + 0.37, z + 0.71], axis=1), seed)


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


# ---------------------------------------------------------------------------- 网格
def mesh_object(name, coll, verts, faces, uvs=None, mat=None, smooth=True):
    """verts: (N,3)；faces: 每个面一个顶点下标序列（三角、四边混用）；uvs: 和 faces 同结构的每角 UV（米）。"""
    me = bpy.data.meshes.new(name)
    verts = np.asarray(verts, dtype=np.float64)
    faces = [list(map(int, f)) for f in faces]
    me.vertices.add(len(verts))
    me.vertices.foreach_set("co", verts.astype(np.float32).ravel())
    tot = sum(len(f) for f in faces)
    me.loops.add(tot)
    me.loops.foreach_set("vertex_index", np.fromiter((v for f in faces for v in f), dtype=np.int32, count=tot))
    me.polygons.add(len(faces))
    starts = np.zeros(len(faces), dtype=np.int32)
    if len(faces) > 1:
        starts[1:] = np.cumsum([len(f) for f in faces[:-1]])
    me.polygons.foreach_set("loop_start", starts)
    me.update(calc_edges=True)
    if uvs is not None:
        uvl = me.uv_layers.new(name=spec.UV_MAIN)
        flat = np.array([uv for f in uvs for uv in f], dtype=np.float32)
        uvl.data.foreach_set("uv", flat.ravel())
    me.validate(clean_customdata=False)
    ob = bpy.data.objects.new(name, me)
    (coll or bpy.context.scene.collection).objects.link(ob)
    if mat is not None:
        me.materials.append(mat)
    if smooth:
        me.shade_smooth()
    return ob


def grid_mesh(name, P, closed_u=True, coll=None, pole_start=None, pole_end=None):
    """高模：P (R,C,3) 一排排点（每排 C 个，排内绕一圈 closed_u），相邻排连四边形，绕向由调用者保证朝外。
    pole_start / pole_end：首尾封口的极点（扇形三角）。用 foreach_set 建，几十万面也快。"""
    R, C = P.shape[:2]
    verts = P.reshape(-1, 3)
    cols = C if closed_u else C - 1
    i, j = np.meshgrid(np.arange(R - 1), np.arange(cols), indexing="ij")
    i, j = i.ravel(), j.ravel()
    j1 = (j + 1) % C
    quads = np.stack([i * C + j, i * C + j1, (i + 1) * C + j1, (i + 1) * C + j], axis=1)
    polys = [quads]
    extra = []
    if pole_start is not None:
        k = len(verts) + len(extra)
        extra.append(pole_start)
        jj = np.arange(C)
        polys.append(np.stack([np.full(C, k), (jj + 1) % C, jj], axis=1))
    if pole_end is not None:
        k = len(verts) + len(extra)
        extra.append(pole_end)
        jj = np.arange(C)
        base = (R - 1) * C
        polys.append(np.stack([base + jj, base + (jj + 1) % C, np.full(C, k)], axis=1))
    if extra:
        verts = np.concatenate([verts, np.array(extra)], axis=0)
    return raw_mesh(name, verts, polys, coll)


def raw_mesh(name, verts, poly_arrays, coll=None):
    """poly_arrays：若干 (F,k) 数组（同一数组里面的边数相同）。"""
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(verts))
    me.vertices.foreach_set("co", np.asarray(verts, dtype=np.float32).ravel())
    idx = np.concatenate([a.ravel() for a in poly_arrays]).astype(np.int32)
    sizes = np.concatenate([np.full(len(a), a.shape[1]) for a in poly_arrays])
    me.loops.add(len(idx))
    me.loops.foreach_set("vertex_index", idx)
    me.polygons.add(len(sizes))
    starts = np.zeros(len(sizes), dtype=np.int32)
    starts[1:] = np.cumsum(sizes[:-1])
    me.polygons.foreach_set("loop_start", starts)
    me.update(calc_edges=True)
    ob = bpy.data.objects.new(name, me)
    (coll or bpy.context.scene.collection).objects.link(ob)
    me.shade_smooth()
    return ob


def set_point_color(ob, name, rgb):
    """点域 FLOAT_COLOR 属性（高模的 "Curv"、"Area"）。rgb: (N,3) 或 (N,)（只写 R）。"""
    me = ob.data
    n = len(me.vertices)
    rgb = np.asarray(rgb, dtype=np.float32)
    if rgb.ndim == 1:
        rgb = np.stack([rgb, np.zeros(n, np.float32), np.zeros(n, np.float32)], axis=1)
    c = np.concatenate([np.clip(rgb, 0, 1), np.ones((n, 1), np.float32)], axis=1)
    a = me.attributes.get(name) or me.attributes.new(name, 'FLOAT_COLOR', 'POINT')
    a.data.foreach_set("color", c.astype(np.float32).ravel())


def check_outward(ob, ref_fn):
    """法线朝向自检：ref_fn(面中心) -> 该点「里面」的参考点；大多数面朝里就整体翻转。"""
    me = ob.data
    bad = 0
    tot = 0
    step = max(1, len(me.polygons) // 400)
    for i in range(0, len(me.polygons), step):
        p = me.polygons[i]
        c = p.center
        if (c - ref_fn(c)).dot(p.normal) < 0:
            bad += 1
        tot += 1
    if bad > tot // 2:
        me.flip_normals()
        return True
    return False


# ---------------------------------------------------------------------------- 路径
class Path:
    """稠密折线（1 毫米一段）+ 平行传输标架；用弧长 d 取点和标架。"""

    def __init__(self, pts, step=0.001, up=None):
        pts = np.asarray(pts, dtype=np.float64)
        seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
        acc = np.concatenate([[0.0], np.cumsum(seg)])
        self.length = float(acc[-1])
        n = max(2, int(self.length / step) + 1)
        ds = np.linspace(0.0, self.length, n)
        P = np.stack([np.interp(ds, acc, pts[:, k]) for k in range(3)], axis=1)
        T = np.gradient(P, axis=0)
        T /= np.linalg.norm(T, axis=1)[:, None] + 1e-12
        N = np.zeros_like(P)
        up = np.array(up if up is not None else (0.0, 0.0, 1.0))
        n0 = np.cross(up, T[0])
        if np.linalg.norm(n0) < 1e-4:
            n0 = np.cross((1.0, 0.0, 0.0), T[0])
        N[0] = n0 / np.linalg.norm(n0)
        for k in range(1, n):
            v = N[k - 1] - T[k] * np.dot(N[k - 1], T[k])
            N[k] = v / (np.linalg.norm(v) + 1e-12)
        self.d = ds
        self.P, self.T, self.N = P, T, N
        self.B = np.cross(T, N)

    def at(self, d):
        d = np.clip(np.asarray(d, dtype=np.float64), 0.0, self.length)
        k = np.clip(np.round(d / self.length * (len(self.d) - 1)).astype(int), 0, len(self.d) - 1)
        return self.P[k], self.T[k], self.N[k], self.B[k]


def catmull_np(points, samples=24):
    pts = [np.asarray(p, dtype=np.float64) for p in points]
    out = []
    n = len(pts)
    for i in range(n - 1):
        p0 = pts[i - 1] if i > 0 else 2 * pts[0] - pts[1]
        p1, p2 = pts[i], pts[i + 1]
        p3 = pts[i + 2] if i + 2 < n else 2 * pts[-1] - pts[-2]
        for s in range(samples):
            t = s / samples
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                              + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    out.append(pts[-1])
    return np.array(out)


def tube_low(name, coll, mat, path, ds, radius_fn, sides, pole_start=True, pole_end=True, flat=1.0, phase=0.0,
             pole_k=0.6):
    """低模扫管：在弧长 ds 处各放一圈（sides 个点），首尾极点封口。UV0 按米展开：v = 弧长，u = 该圈周长上的位置
    （每圈各自按周长，岛是一条两头尖的带子，等密度），接缝在 a = phase 处。"""
    ds = np.asarray(ds, dtype=np.float64)
    P, T, N, B = path.at(ds)
    r = np.asarray([radius_fn(d) for d in ds])
    a = phase + 2 * np.pi * np.arange(sides) / sides
    ring = (P[:, None, :] + r[:, None, None] * (N[:, None, :] * np.cos(a)[None, :, None]
                                               + B[:, None, :] * flat * np.sin(a)[None, :, None]))
    R = len(ds)
    verts = list(ring.reshape(-1, 3))
    faces, uvs = [], []
    circ = 2 * np.pi * r * (1 + flat) / 2

    def uv(i, j):
        return ((j / sides - 0.5) * circ[i], ds[i])
    for i in range(R - 1):
        for j in range(sides):
            j1 = (j + 1) % sides
            faces.append((i * sides + j, i * sides + j1, (i + 1) * sides + j1, (i + 1) * sides + j))
            uvs.append((uv(i, j), uv(i, j + 1), uv(i + 1, j + 1), uv(i + 1, j)))
    if pole_start:
        k = len(verts)
        d0 = ds[0] - r[0] * pole_k
        verts.append(P[0] - T[0] * r[0] * pole_k)
        for j in range(sides):
            faces.append((k, (j + 1) % sides, j))
            uvs.append(((0.0, d0), uv(0, j + 1), uv(0, j)))
    if pole_end:
        k = len(verts)
        d1 = ds[-1] + r[-1] * pole_k
        verts.append(P[-1] + T[-1] * r[-1] * pole_k)
        base = (R - 1) * sides
        for j in range(sides):
            faces.append((base + j, base + (j + 1) % sides, k))
            uvs.append((uv(R - 1, j), uv(R - 1, j + 1), (0.0, d1)))
    return mesh_object(name, coll, np.array(verts), faces, uvs, mat)


def tube_high_points(path, ds, radius_fn, sides, flat=1.0, phase=0.0, disp_fn=None):
    """高模扫管的点阵 (R,C,3) 和每点的 (d, a, 法线)：disp_fn(d, a, P, n) -> 沿法线的位移（米）。"""
    ds = np.asarray(ds, dtype=np.float64)
    P, T, N, B = path.at(ds)
    r = np.asarray([radius_fn(d) for d in ds])
    a = phase + 2 * np.pi * np.arange(sides) / sides
    ca, sa = np.cos(a)[None, :, None], np.sin(a)[None, :, None]
    off = N[:, None, :] * ca + B[:, None, :] * flat * sa
    pts = P[:, None, :] + r[:, None, None] * off
    nrm = N[:, None, :] * ca * flat + B[:, None, :] * sa
    nrm /= np.linalg.norm(nrm, axis=2)[:, :, None]
    D = np.broadcast_to(ds[:, None], pts.shape[:2])
    A = np.broadcast_to(a[None, :], pts.shape[:2])
    if disp_fn is not None:
        h = disp_fn(D, A, pts, nrm)
        pts = pts + nrm * h[:, :, None]
    return pts, D, A, P, T
