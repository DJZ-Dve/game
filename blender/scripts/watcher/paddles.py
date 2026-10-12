"""桨（块面占位）：沿骨链扫一片扁平叶片，每节权重给对应的骨。正式版见 spec.py「分区」。"""
import math

import bmesh
import bpy

import lib
from lib import V
from watcher import spec, bakeutil, util


def build(coll, bake=False):
    mat = bpy.data.materials["M_WatcherPaddle"]
    obs = []
    for i, p in enumerate(spec.PADDLES):
        for side in (-1, 1):
            pts = spec.paddle_rest_points(i, side)
            path = []
            for k in range(spec.PADDLE_BONES):
                for q in range(4):
                    path.append(pts[k].lerp(pts[k + 1], q / 4))
            path.append(pts[-1])
            n = len(path)
            scales = [0.35 + 0.65 * math.sin(math.pi * min(1.2 * t / (n - 1), 1.0)) for t in range(n)]
            bm = bmesh.new()
            lib.sweep(bm, path, lib.rect_profile(p["width"], 0.4, 0.15), caps=True, scales=scales,
                      up_hint=V((0, 0, 1)))
            nm = "Paddle%s%d" % ("L" if side < 0 else "R", i)
            ob = lib.to_object(bm, nm, coll, mat)
            groups = [ob.vertex_groups.new(name=spec.paddle_bone(i, side, k)) for k in range(spec.PADDLE_BONES)]
            for v in ob.data.vertices:
                best, bk = 1e9, 0
                for k in range(spec.PADDLE_BONES):
                    a, b = pts[k], pts[k + 1]
                    ab = b - a
                    t = max(0.0, min(1.0, (v.co - a).dot(ab) / ab.length_squared))
                    d = (a + ab * t - v.co).length
                    if d < best:
                        best, bk = d, k
                groups[bk].add([v.index], 1.0, 'REPLACE')
            util.smart_uv(ob)
            obs.append(ob)
    bakeutil.atlas_uv(obs, "paddle")
    if bake:
        hs = util.placeholder_high(obs)
        bakeutil.bake_set("paddle", obs, hs)
        util.remove(hs)
    return obs
