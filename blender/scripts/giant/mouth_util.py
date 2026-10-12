"""嘴（mouth.py）用的小工具：numpy 网格构建器（顶点、面、骨骼权重、面区域、面角 UV、点色）和 numpy 噪声。
高模动辄上百万顶点，全用 numpy + foreach_set，不走 bmesh。"""
import math
import zlib

import bpy
import numpy as np


# ---------------------------------------------------------------------------- 噪声
def _hash(ix, iy, iz, seed):
    h = (ix.astype(np.int64) * 73856093) ^ (iy.astype(np.int64) * 19349663) ^ (iz.astype(np.int64) * 83492791)
    h = (h ^ (seed * 2654435761)) & 0xFFFFFFFF
    h = (h ^ (h >> 13)) * 1274126177 & 0xFFFFFFFF
    h = h ^ (h >> 16)
    return (h & 0xFFFF).astype(np.float64) / 32767.5 - 1.0


def vnoise(p, seed=0):
    """三维值噪声，p: (N, 3)，返回 (N,) ∈ [-1, 1]。"""
    p = np.asarray(p, dtype=np.float64)
    i = np.floor(p)
    f = p - i
    w = f * f * f * (f * (f * 6 - 15) + 10)
    i = i.astype(np.int64)
    out = np.zeros(len(p))
    for dx in (0, 1):
        wx = w[:, 0] if dx else 1 - w[:, 0]
        for dy in (0, 1):
            wy = w[:, 1] if dy else 1 - w[:, 1]
            for dz in (0, 1):
                wz = w[:, 2] if dz else 1 - w[:, 2]
                out += wx * wy * wz * _hash(i[:, 0] + dx, i[:, 1] + dy, i[:, 2] + dz, seed)
    return out


def fbm(p, octaves=4, seed=0, lac=2.03, gain=0.5):
    p = np.asarray(p, dtype=np.float64)
    out = np.zeros(len(p))
    a, tot = 1.0, 0.0
    for o in range(octaves):
        out += a * vnoise(p, seed + o * 101)
        tot += a
        p = p * lac + 17.3
        a *= gain
    return out / tot


def ridged(p, octaves=3, seed=0):
    """脊状噪声（皱褶）：0 平，1 棱。"""
    p = np.asarray(p, dtype=np.float64)
    out = np.zeros(len(p))
    a, tot = 1.0, 0.0
    for o in range(octaves):
        out += a * (1.0 - np.abs(vnoise(p, seed + o * 37)))
        tot += a
        p = p * 2.1 + 5.1
        a *= 0.5
    return out / tot


def smoothstep(a, b, x):
    t = np.clip((np.asarray(x, dtype=np.float64) - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def sstep(a, b, x):
    t = min(max((x - a) / (b - a), 0.0), 1.0)
    return t * t * (3 - 2 * t)


def rng(name):
    return np.random.default_rng(zlib.crc32(name.encode()))


# ---------------------------------------------------------------------------- 网格构建器
class MB:
    """攒顶点和面，最后一次性生成网格物体。
    - 权重：每个顶点一个 {骨名: 权重}（weights 列表），或者整块顶点共用一个字典；
    - 面：四边形 / 三角形，各带 区域号（region，用来标接缝）、材质号；可以带面角 UV（每个角一个 (u, v)）；
    - 点色属性：按顶点存（attrs[名字] = (N, 4) 数组）。"""

    def __init__(self):
        self.verts = []
        self.nv = 0
        self.faces = []        # (np int 数组 (k, n), region, mat, uv 或 None)
        self.wblocks = []      # (start, count, weights)；weights = dict（整块共用）或 list[dict]
        self.attrs = {}        # name -> list of (start, (count,4) array)

    def add_verts(self, pts, weights=None):
        pts = np.asarray(pts, dtype=np.float64).reshape(-1, 3)
        start = self.nv
        self.verts.append(pts)
        self.nv += len(pts)
        if weights is not None:
            self.wblocks.append((start, len(pts), weights))
        return start

    def set_weights(self, start, count, weights):
        self.wblocks.append((start, count, weights))

    def add_attr(self, name, start, cols):
        self.attrs.setdefault(name, []).append((start, np.asarray(cols, dtype=np.float32).reshape(-1, 4)))

    def add_faces(self, idx, region=0, mat=0, uv=None):
        idx = np.asarray(idx, dtype=np.int64)
        if idx.ndim == 1:
            idx = idx[None, :]
        if len(idx) == 0:
            return
        if uv is not None:
            uv = np.asarray(uv, dtype=np.float64).reshape(len(idx), idx.shape[1], 2)
        self.faces.append((idx, region, mat, uv))

    def grid(self, P, closed=False, region=0, mat=0, uv=None, mask=None, flip=False, weights=None):
        """P: (nr, nc, 3) 一排排点（排 = 截面，列 = 沿截面），相邻两排连四边形；closed 时每排首尾相连。
        uv: (nr, nc(+1 若 closed), 2) 每个网格点的 UV（closed 时最后一列是接缝那头）；mask: (nr-1, ncols) 哪些格子要面。
        返回顶点索引 (nr, nc)。"""
        P = np.asarray(P, dtype=np.float64)
        nr, nc = P.shape[:2]
        start = self.add_verts(P.reshape(-1, 3), weights)
        ids = start + np.arange(nr * nc).reshape(nr, nc)
        ncol = nc if closed else nc - 1
        quads, uvs = [], []
        for i in range(nr - 1):
            for j in range(ncol):
                if mask is not None and not mask[i, j]:
                    continue
                j1 = (j + 1) % nc
                q = [ids[i, j], ids[i, j1], ids[i + 1, j1], ids[i + 1, j]]
                if uv is not None:
                    u = [uv[i, j], uv[i, j + 1], uv[i + 1, j + 1], uv[i + 1, j]]
                if flip:
                    q = q[::-1]
                    if uv is not None:
                        u = u[::-1]
                quads.append(q)
                if uv is not None:
                    uvs.append(u)
        self.add_faces(np.array(quads, dtype=np.int64).reshape(-1, 4), region, mat, np.array(uvs) if uv is not None else None)
        return ids

    def all_verts(self):
        return np.concatenate(self.verts) if self.verts else np.zeros((0, 3))

    def to_object(self, name, coll, materials, smooth=True, regions_attr=False):
        V = self.all_verts()
        quads = [f for f in self.faces if f[0].shape[1] == 4]
        tris = [f for f in self.faces if f[0].shape[1] == 3]
        groups = quads + tris
        idx_list, reg, mat, sizes, uvl = [], [], [], [], []
        has_uv = any(g[3] is not None for g in groups)
        for idx, r, m, uv in groups:
            idx_list.append(idx.reshape(-1))
            reg.append(np.full(len(idx), r, dtype=np.int32))
            mat.append(np.full(len(idx), m, dtype=np.int32))
            sizes.append(np.full(len(idx), idx.shape[1], dtype=np.int32))
            if has_uv:
                uvl.append(uv.reshape(-1, 2) if uv is not None else np.zeros((idx.size, 2)))
        loops = np.concatenate(idx_list).astype(np.int32)
        sizes = np.concatenate(sizes)
        starts = np.concatenate([[0], np.cumsum(sizes)[:-1]]).astype(np.int32)
        me = bpy.data.meshes.new(name)
        me.vertices.add(len(V))
        me.vertices.foreach_set("co", V.astype(np.float32).reshape(-1))
        me.loops.add(len(loops))
        me.loops.foreach_set("vertex_index", loops)
        me.polygons.add(len(sizes))
        me.polygons.foreach_set("loop_start", starts)
        me.polygons.foreach_set("loop_total", sizes)
        me.polygons.foreach_set("material_index", np.concatenate(mat))
        me.update(calc_edges=True)
        if has_uv:
            uvlay = me.uv_layers.new(name="UVMap")
            uvlay.data.foreach_set("uv", np.concatenate(uvl).astype(np.float32).reshape(-1))
        if regions_attr:
            a = me.attributes.new("mregion", 'INT', 'FACE')
            a.data.foreach_set("value", np.concatenate(reg))
        for an, blocks in self.attrs.items():
            arr = np.zeros((len(V), 4), dtype=np.float32)
            arr[:, 3] = 1.0
            for st, c in blocks:
                arr[st:st + len(c)] = c
            a = me.attributes.new(an, 'FLOAT_COLOR', 'POINT')
            a.data.foreach_set("color", arr.reshape(-1))
        me.validate(clean_customdata=False)
        ob = bpy.data.objects.new(name, me)
        coll.objects.link(ob)
        for m in materials:
            me.materials.append(bpy.data.materials[m] if isinstance(m, str) else m)
        if smooth:
            me.shade_smooth()
        self._apply_weights(ob)
        return ob

    def _apply_weights(self, ob):
        per_bone = {}
        for start, count, w in self.wblocks:
            if isinstance(w, dict):
                for b, val in w.items():
                    per_bone.setdefault(b, []).append((np.arange(start, start + count), np.full(count, val)))
            else:
                for k, d in enumerate(w):
                    for b, val in d.items():
                        per_bone.setdefault(b, []).append((np.array([start + k]), np.array([val])))
        for b, lst in per_bone.items():
            ids = np.concatenate([a for a, _ in lst])
            ws = np.concatenate([c for _, c in lst])
            keep = ws > 1e-4
            ids, ws = ids[keep], ws[keep]
            if not len(ids):
                continue
            vg = ob.vertex_groups.get(b) or ob.vertex_groups.new(name=b)
            q = np.round(ws * 255).astype(np.int32)
            for qv in np.unique(q):
                sel = ids[q == qv]
                vg.add(sel.tolist(), float(qv) / 255.0, 'REPLACE')


def merge_weights(ws):
    """[(权重字典, 系数)] 线性混合，归一化。"""
    out = {}
    for d, k in ws:
        if k <= 0:
            continue
        for b, w in d.items():
            out[b] = out.get(b, 0.0) + w * k
    tot = sum(out.values())
    if tot > 0:
        out = {b: w / tot for b, w in out.items() if w / tot > 1e-3}
    return out


def mark_region_seams(ob):
    """面属性 mregion 不同的相邻面之间标接缝（展 UV 用）。"""
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    lay = bm.faces.layers.int.get("mregion")
    for e in bm.edges:
        fs = e.link_faces
        if len(fs) == 2 and fs[0][lay] != fs[1][lay]:
            e.seam = True
        elif len(fs) != 2:
            e.seam = True
    bm.to_mesh(ob.data)
    bm.free()


def unwrap(ob, method='ANGLE_BASED', keep_existing_regions=None):
    """按接缝展 UV0（用于肉的大片网格）。"""
    me = ob.data
    if "UVMap" not in me.uv_layers:
        me.uv_layers.new(name="UVMap")
    bpy.ops.object.select_all(action='DESELECT')
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.unwrap(method=method, margin=0.002)
    bpy.ops.object.mode_set(mode='OBJECT')
    ob.select_set(False)
