"""肉：甲片底下的身体（关节膜）+ 眼窝（同一张网格）、上下眼睑、腹面虹吸口。

形体是参数化的（flesh_geo.py，结构说明见那里的文件头）：低模、高模用同一套函数，高模只是采样密 ×k 再加细节
（flesh_high.py）。低模（flesh_mesh.py）自己展好 UV0（接缝放在甲壳下、口袋里、眼睑根部这些看不见的地方），
再由 bakeutil.atlas_uv 排进 "flesh" 图集。

权重：身体、眼窝、虹吸口 = Body；结膜前缘带一点 Eye（≤0.3，转眼时这圈湿肉跟着被牵动）；
眼睑刚性部分 = LidUp / LidLo，根部 8° 过渡到 Body（根部一直藏在眼眶唇下的口袋里）。
"""
import time

import bpy

from watcher import bakeutil
from watcher import flesh_mesh as fm


def build(coll, bake=False):
    t0 = time.time()
    mat = bpy.data.materials["M_WatcherFlesh"]
    body, bi = fm.body_low(coll, mat)
    up, ui = fm.lid_low(coll, mat, False)
    lo, li = fm.lid_low(coll, mat, True)
    sip, si = fm.siphon_low(coll, mat)
    obs = [body, up, lo, sip]
    bakeutil.atlas_uv(obs, "flesh")
    print(f"flesh low: {time.time() - t0:.1f}s")
    if bake:
        from watcher import flesh_high
        flesh_high.bake(obs)
    return obs
