"""块面（blockout）工具：按 spec 的曲面放样出粗的网格，给各部件的占位版用，也给精修时当底子参考。"""
import math

import bmesh
import bpy

from giant import spec


def grid(name, coll, mat, rows, closed=False):
    """rows：一排排点（每排点数相同），相邻两排连成四边形；closed 时每排首尾相连。UV0 按米：u 沿排、v 跨排。"""
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new(spec.UV_MAIN)
    vs = [[bm.verts.new(p) for p in r] for r in rows]
    n = len(rows[0])
    us = []
    for r in rows:
        acc = [0.0]
        for j in range(1, n):
            acc.append(acc[-1] + (r[j] - r[j - 1]).length)
        if closed:
            acc.append(acc[-1] + (r[0] - r[-1]).length)
        us.append(acc)
    vv = [0.0]
    for i in range(1, len(rows)):
        vv.append(vv[-1] + (rows[i][n // 2] - rows[i - 1][n // 2]).length)
    cols = n if closed else n - 1
    for i in range(len(rows) - 1):
        for j in range(cols):
            j1 = (j + 1) % n
            quad = (vs[i][j], vs[i][j1], vs[i + 1][j1], vs[i + 1][j])
            if len(set(quad)) < 4:
                continue
            f = bm.faces.new(quad)
            for lp, (ii, jj) in zip(f.loops, ((i, j), (i, j + 1), (i + 1, j + 1), (i + 1, j))):
                lp[uvl].uv = (us[ii][jj], vv[ii])
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    me.materials.append(bpy.data.materials[mat])
    me.shade_smooth()
    return ob


def fix_normals(ob, outward_from=None):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bm.to_mesh(ob.data)
    bm.free()


def frange(a, b, n):
    return [a + (b - a) * i / (n - 1) for i in range(n)]
