"""甲壳：眼窝以外全身一片压一片的厚甲（从眼睛往后像瓦片一样叠），甲的中棱、后缘长着往后倒的尖刺。
低模两个物体（ShellPlates 甲片、ShellSpikes 尖刺），材质 M_WatcherShell，权重全给 "Body"，UV0 是 "shell" 贴图组的图集。
高模（--bake 时现建、烘完删掉）：几丁质的细小凹坑和颗粒、沿生长方向的细纹和生长线、缘边磨损和小崩口、几道旧划痕、
两处愈合的裂纹、刺尖磨白（Area = 1）、甲缘磨白（Area 0.5～1）。

模块：shell_plate（排布 + 每片甲的解析外形）、shell_mesh（甲片低模 / 高模网格）、shell_spike（尖刺）、
shell_high（高模细节、Curv / Area、烘焙）、shell_np（numpy 工具）。"""
import time

import bpy
import numpy as np

from watcher import spec, bakeutil
from watcher import shell_np as snp
from watcher import shell_plate, shell_mesh, shell_spike


def _concat(parts):
    cos, tris, uvs = [], [], []
    off = 0
    for co, t, uv in parts:
        cos.append(co)
        tris.append(t + off)
        uvs.append(uv)
        off += len(co)
    return np.concatenate(cos), np.concatenate(tris), np.concatenate(uvs)


def layout():
    rng = spec.rng_for("shell")
    plates = shell_plate.layout(rng)
    spikes = shell_spike.plan(plates, rng)
    return plates, spikes


def build(coll, bake=False):
    t0 = time.time()
    mat = bpy.data.materials["M_WatcherShell"]
    plates, spikes = layout()
    co, tris, uv = _concat([shell_mesh.plate_low(p) for p in plates])
    ob_p = snp.make_mesh("ShellPlates", co, tris, coll, uv)
    from mathutils.bvhtree import BVHTree
    bvh = BVHTree.FromPolygons([tuple(v) for v in co], [tuple(t) for t in tris])
    co, tris, uv = _concat([shell_spike.spike_low(s, bvh) for s in spikes])
    ob_s = snp.make_mesh("ShellSpikes", co, tris, coll, uv)
    obs = [ob_p, ob_s]
    for o in obs:
        o.data.materials.append(mat)
        spec.assign_bone(o, "Body")
    print(f"shell: {len(plates)} plates ({len(ob_p.data.polygons):,} tris), {len(spikes)} spikes "
          f"({len(ob_s.data.polygons):,} tris), {time.time() - t0:.1f}s")
    bakeutil.atlas_uv(obs, "shell")
    if bake:
        from watcher import shell_high
        shell_high.bake(plates, spikes, obs)
    return obs
