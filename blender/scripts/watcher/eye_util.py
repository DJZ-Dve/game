"""眼（eye.py / eye_detail.py）用的小工具：numpy 值噪声（确定性）、整数哈希、用数组快速建网格。
噪声部分照 giant/eyes_util.py 抄过来（那边不动）。"""
import bpy
import numpy as np

from watcher import spec


# ---------------------------------------------------------------------------- 噪声
def _hash(ix, iy, iz, seed):
    h = (ix * 73856093) ^ (iy * 19349663) ^ (iz * 83492791) ^ (seed * 2654435761)
    h = h & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    h = h ^ (h >> 16)
    return (h & 0xFFFFFF).astype(np.float64) / float(0xFFFFFF)


def hash1(i, k=0, seed=0):
    """整数数组 i → [0,1) 的确定性随机数（k 区分同一个 i 的不同属性）。"""
    i = np.asarray(i, dtype=np.int64)
    return _hash(i, np.full_like(i, k), np.full_like(i, 7), seed)


def vnoise3(p, seed=0):
    """3D 值噪声，p: (N,3)，返回 [0,1]。五次插值。"""
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


def fbm2(x, y, octaves=4, seed=0, z=0.0):
    """二维坐标的分形噪声（任意形状数组），返回 -1～1 左右。"""
    x = np.asarray(x, dtype=np.float64)
    shp = x.shape
    p = np.stack([x.ravel(), np.asarray(y, dtype=np.float64).ravel(), np.full(x.size, z)], axis=1)
    return ((fbm3(p, octaves, seed) - 0.5) * 2).reshape(shp)


def noise1(x, seed=0):
    """1D 值噪声 [0,1]。"""
    x = np.asarray(x, dtype=np.float64)
    shp = x.shape
    x = x.ravel()
    z = np.zeros_like(x)
    return vnoise3(np.stack([x, z + 0.37, z + 0.71], axis=1), seed).reshape(shp)


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


# ---------------------------------------------------------------------------- 网格
def mesh_object(name, coll, verts, faces, uvs=None, mat=None, smooth=True):
    """verts: (N,3)；faces: 每个面一个顶点下标序列；uvs: 和 faces 同结构的每角 UV。"""
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
    uvl = me.uv_layers.new(name=spec.UV_MAIN)
    if uvs is not None:
        flat = np.array([uv for f in uvs for uv in f], dtype=np.float32)
        uvl.data.foreach_set("uv", flat.ravel())
    me.validate(clean_customdata=False)
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    if mat is not None:
        me.materials.append(mat)
    if smooth:
        me.shade_smooth()
    return ob


def grid_quads(keep2d):
    """二维点阵（行×列，keep2d 标出要的点）→ (顶点下标映射, 四个角都在的四边形 (F,4))。"""
    Rn, Cn = keep2d.shape
    idx = np.full(Rn * Cn, -1, dtype=np.int64)
    k = keep2d.ravel()
    idx[k] = np.arange(k.sum())
    i, j = np.meshgrid(np.arange(Rn - 1), np.arange(Cn - 1), indexing="ij")
    i, j = i.ravel(), j.ravel()
    q = np.stack([i * Cn + j, i * Cn + j + 1, (i + 1) * Cn + j + 1, (i + 1) * Cn + j], axis=1)
    q = idx[q]
    return q[(q >= 0).all(axis=1)]


def raw_mesh(name, verts, quads, coll=None):
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(verts))
    me.vertices.foreach_set("co", np.asarray(verts, dtype=np.float32).ravel())
    idx = quads.ravel().astype(np.int32)
    me.loops.add(len(idx))
    me.loops.foreach_set("vertex_index", idx)
    me.polygons.add(len(quads))
    me.polygons.foreach_set("loop_start", (np.arange(len(quads)) * quads.shape[1]).astype(np.int32))
    me.update(calc_edges=True)
    ob = bpy.data.objects.new(name, me)
    (coll or bpy.context.scene.collection).objects.link(ob)
    me.shade_smooth()
    return ob


def set_point_color(ob, name, rgb):
    """点域 FLOAT_COLOR 属性。rgb: (N,3) 或 (N,)（只写 R）。"""
    me = ob.data
    n = len(me.vertices)
    rgb = np.asarray(rgb, dtype=np.float32)
    if rgb.ndim == 1:
        rgb = np.stack([rgb, np.zeros(n, np.float32), np.zeros(n, np.float32)], axis=1)
    c = np.concatenate([np.clip(rgb, 0, 1), np.ones((n, 1), np.float32)], axis=1)
    a = me.attributes.get(name) or me.attributes.new(name, 'FLOAT_COLOR', 'POINT')
    a.data.foreach_set("color", c.astype(np.float32).ravel())


def face_normals(verts, faces):
    """每个面的（未归一）法线：按前三个角算。"""
    v = np.asarray(verts)
    f = np.array([fc[:3] for fc in faces])
    return np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]])
