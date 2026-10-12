"""桨：三对，每支三节（根节、中节、叶片），根部一圈肉褶贴进身体。形体见 paddle_geo.py（参数化，低模高模共用），
高模细节和烘焙见 paddle_high.py。

低模：每支一根扁管（沿长度一圈圈采样，截面 NV 个点），叶尖收成一点，根部第一圈埋在体表下（不封口）；
UV0 自己展：u = 沿长度的距离，v = 绕截面的弧长（从前缘量起，上表面为正），接缝在后缘（只拆 UV、不拆顶点）。
权重：根部肉褶 Body → Paddle?_0，两处关节在关节膜上过渡（spec.paddle_bone）。材质 M_WatcherPaddle，贴图组 "paddle"。
"""
import math
import time

import bpy
import numpy as np

from watcher import spec, bakeutil
from watcher import shell_np as snp
from watcher import paddle_geo as pg
from watcher import flesh_mesh as fm

NV = 20     # 截面点数（偶数：v = 0 前缘、±π 后缘都正好有点）


def vcols(nv):
    return -math.pi + 2 * math.pi * np.arange(nv) / nv


def tube(pd, xs, nv):
    """返回 co (n,3)、tris (m,3)、逐角 uv (m*3,2)、网格参数 G（不含叶尖点）。顶点顺序：第 i 圈第 j 个 = i*nv + j，最后一个是叶尖。"""
    vs = vcols(nv)
    G = pd.grid(xs, vs)
    P = G["P"]
    ni = len(xs)
    tip = pd.tip()
    co = np.concatenate([P.reshape(-1, 3), tip[None]], 0)
    # UV：u 沿长度（相邻两圈的平均距离累加），v 绕截面的弧长（列 nv/2 是前缘 v = 0）
    du = np.linalg.norm(P[1:] - P[:-1], axis=-1).mean(1)
    U = np.concatenate([[0.0], np.cumsum(du)])
    ring = np.concatenate([P, P[:, :1]], 1)
    seg = np.linalg.norm(ring[:, 1:] - ring[:, :-1], axis=-1)
    s = np.concatenate([np.zeros((ni, 1)), np.cumsum(seg, 1)], 1)       # (ni, nv+1)
    V = s - s[:, nv // 2][:, None]
    u_tip = U[-1] + np.linalg.norm(P[-1] - tip, axis=-1).mean()
    # 面：圈 i、i+1 之间的四边形（列 j、j+1，j+1 = nv 时顶点回到 0，UV 用第 nv 列）
    i, j = np.meshgrid(np.arange(ni - 1), np.arange(nv), indexing="ij")
    i, j = i.ravel(), j.ravel()
    j1 = j + 1
    vid = lambda a, b: a * nv + (b % nv)
    q = [(i, j), (i, j1), (i + 1, j1), (i + 1, j)]
    tri_v, tri_uv = [], []
    for t in ((0, 1, 2), (0, 2, 3)):
        tri_v.append(np.stack([vid(*q[k]) for k in t], 1))
        tri_uv.append(np.stack([np.stack([U[q[k][0]], V[q[k][0], q[k][1]]], -1) for k in t], 1))
    # 叶尖扇
    jj = np.arange(nv)
    tip_i = ni * nv
    tri_v.append(np.stack([vid(ni - 1, jj), np.full(nv, tip_i), vid(ni - 1, jj + 1)], 1))
    tri_uv.append(np.stack([np.stack([np.full(nv, U[-1]), V[-1, jj]], -1),
                            np.stack([np.full(nv, u_tip), np.zeros(nv)], -1),
                            np.stack([np.full(nv, U[-1]), V[-1, jj + 1]], -1)], 1))
    tris = np.concatenate(tri_v, 0)
    uv = np.concatenate(tri_uv, 0)
    # 朝外：中节那一圈的面法线应该背离桨轴
    n = np.cross(co[tris[:, 1]] - co[tris[:, 0]], co[tris[:, 2]] - co[tris[:, 0]])
    cen = co[tris].mean(1)
    xm = (cen - pd.o) @ pd.d
    axis = pd.o + np.outer(xm, pd.d)
    sel = (xm > pd.xj[0] + 0.5) & (xm < pd.xj[1] - 0.5)
    if (np.einsum("ij,ij->i", n[sel], (cen - axis)[sel]) < 0).mean() > 0.5:
        tris = tris[:, ::-1].copy()
        uv = uv[:, ::-1].copy()
    return co, tris, uv.reshape(-1, 2), G


def build(coll, bake=False):
    t0 = time.time()
    mat = bpy.data.materials["M_WatcherPaddle"]
    obs, pads = [], []
    for pd in pg.all_paddles():
        xs = pg.stations(pd)
        co, tris, uv, G = tube(pd, xs, NV)
        ob = snp.make_mesh(pd.name, co, tris, coll, uv)
        ob.data.materials.append(mat)
        xv = np.concatenate([G["x"].ravel(), [pd.L]])
        wb, ws = pg.bone_weights(pd, xv)
        groups = {"Body": wb}
        for k, w in enumerate(ws):
            groups[spec.paddle_bone(pd.i, pd.side, k)] = w
        fm.set_weights(ob, groups)
        obs.append(ob)
        pads.append(pd)
    print(f"paddles low: {sum(len(o.data.polygons) for o in obs):,} tris, {time.time() - t0:.1f}s")
    bakeutil.atlas_uv(obs, "paddle")
    if bake:
        from watcher import paddle_high
        paddle_high.bake(pads, obs)
    return obs
