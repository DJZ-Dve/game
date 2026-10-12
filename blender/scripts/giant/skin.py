"""皮（第二版）：整张外皮——头、下颌外侧、唇、身体、尾柄连成一张；鳃裂、眼窝；高模烘焙细节（盾鳞、皱、
劳伦氏壶腹孔、侧线、旧疤、达摩鲨咬坑、一处新伤）。低模见 skin_low.py，高模见 skin_high.py。"""
import time

import bpy

import lib
from giant import spec, bakeutil
from giant import skin_low


def build(coll, bake=False):
    t0 = time.time()
    ob, m, ctx = skin_low.build(coll)
    bakeutil.atlas_uv([ob], "skin")
    print(f"skin low: {lib.stats([ob]):,} tris, {len(ob.data.vertices):,} verts ({time.time() - t0:.1f}s)")
    if bake:
        from giant import skin_high
        skin_high.bake(ob, m, ctx)
    return [ob]
