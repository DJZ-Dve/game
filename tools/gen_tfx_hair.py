#!/usr/bin/env python3
"""船员的发型 → TressFX 的发丝（.tfx，addons/tressfx 的 TressFXHair 读），再给头生成一个碰撞用的凸包。
试 TressFX 发丝用（scripts/tools/tressfx_try.gd 的 --cc-tfx-style）。

发型从发片里来：发型的引导线（CharMorph Vitruvian 的 hairstyles/*.npz）在 blender/cache 里，不进仓库，换机器就没了；
而发片（assets/models/crew_body_f.glb、crew_body_m.glb 里的 Crew_Hair_*）是 blender/scripts/gen_head_vitruvian.py
沿着一根根发丝铺的带子——根到梢每一段左右两个顶点，UV 的 v 从根 0 到梢 1（glTF 里翻成 1 - v）。按连通块分出每一片、
按 v 排好、左右取中点，就是那根发丝，而且已经在最终模型的网格坐标里（和蒙皮的绑定姿势同一个坐标系）。

这一两千根只当引导线（梳的方向），整头头发照着它长（groom）。第一版每片发片直接当一根主发丝、插件再在旁边复制几根跟随的，
看着假：跟随的是主发丝原样平移的副本，一簇七八根完全平行，像又拼回了一片片发片；所有发丝贴着头皮那 1.5~4.5 毫米一层，
像画在头上的、没有蓬松度；发际线是层壳一刀切的硬边；发梢齐刷刷一样长。真头发是这样的，照着做：
- 发根在头皮上撒满（层壳最里层就是有头发的那块头皮，顶点色 G 是发量），发际线那一圈越往外越稀，不是一条线
- 每根的形状照附近的引导线插值（只混形状相近的几根：分缝两边、刘海和侧面的一混就混出横穿脸的发丝，
  见 gen_head_vitruvian.py 的 hair_children），按两处“从头中心往外”的方向的夹角转过去（头是圆的，照搬会扎进头皮或者飘起来；
  不用皮肤的法线，见 Scalp）
- 成绺：同一根引导线周围的发丝越往发梢越往它收（clump），一绺一起弯（lock）；每根自己再弯一点（wave）
- 有厚度：每绺头发在头发层里有深有浅，越往外的离头皮抬得越高（lift），着色器按深浅压暗里层（crew_hair_strand.gdshader）
- 发梢长短不齐（cut）；少数几根翘出来的乱发（fly），轮廓才不是一刀切的
- 发际线一圈细短的绒毛（baby）
每根发丝的粗细倍数、在头发层里的深浅写进 .tfx 的发丝 UV（x、y），crew_hair_strand.gdshader 的 strand_attrs 打开时这么读。
这里的每根都是主发丝（插件再在每根旁边加几根跟随的，见 tressfx_try.gd），顺序打乱（着色器按发丝序号分 LOD 组，
远了整组不画）。

用法: python tools/gen_tfx_hair.py [--out 目录] [--style 发型,...] [--seed 7]
产出（默认 .tmp/tfx/styles/）：<f|m>_<发型>.tfx；
     <f|m>_head.json：头的凸包（往里收 2.5 毫米，碰撞用）的顶点、三角形，头皮层壳包围盒的中心（着色器的 volume_center），都是网格坐标。
"""
import argparse
import json
import os
import struct
import sys

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import ConvexHull, cKDTree

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
# 每个发型怎么长：
#   n      头发根数（发际线的绒毛另算）          verts  每根几个点（插件要 4、8、16、32、64；长头发 32 才弯得圆）
#   clump  发梢往这一绺的引导线收多少（每绺在这个范围里随机）
#   lock   一绺整体的弯曲、wave 每根自己的弯曲：发梢处的幅度（米）
#   frizz  毛躁：细碎的弯，只在外层（最外层发梢处的幅度，米）
#   lift   头发层多厚：最外层比最里层离头皮多抬这么多（米）
#   cut    发梢长短不齐：最多短多少（占全长的比例）
#   fly    翘出来的乱发占多少                    baby   发际线的绒毛几根
#   edge   发际线从头皮这块的边往里多宽渐密（米，从多少到多少；梳到后面的发型发际线全露着，渐变要宽）
GROOM = {
    "crop": dict(n=14000, verts=16, clump=(0.2, 0.5), lock=0.0015, wave=0.001, frizz=0.0003, lift=0.002, cut=0.3, fly=0.0, baby=250),
    "slick": dict(n=16000, verts=16, clump=(0.15, 0.35), lock=0.002, wave=0.0015, frizz=0.0004, lift=0.004, cut=0.12, fly=0.006,
                  baby=300),
    "bob": dict(n=24000, verts=32, clump=(0.3, 0.6), lock=0.003, wave=0.002, frizz=0.0008, lift=0.01, cut=0.08, fly=0.015, baby=450),
    "long": dict(n=28000, verts=32, clump=(0.3, 0.6), lock=0.005, wave=0.003, frizz=0.001, lift=0.012, cut=0.2, fly=0.015, baby=450),
    "back": dict(n=24000, verts=32, clump=(0.2, 0.45), lock=0.004, wave=0.002, frizz=0.0008, lift=0.004, cut=0.15, fly=0.012,
                 baby=800, edge=(0.002, 0.02)),
}
WORK = 32          # 长的时候每根先重采样成几个点
GAP = 0.0015       # 发丝离皮肤至少这么远（发根除外）
COMP = {5126: np.float32, 5125: np.uint32, 5123: np.uint16, 5121: np.uint8}
WIDTH = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}


class Glb:
    def __init__(self, path):
        with open(path, "rb") as f:
            data = f.read()
        n = struct.unpack_from("<I", data, 12)[0]
        self.g = json.loads(data[20:20 + n])
        m = struct.unpack_from("<I", data, 20 + n)[0]
        self.bin = data[28 + n:28 + n + m]

    def accessor(self, i):
        a = self.g["accessors"][i]
        v = self.g["bufferViews"][a["bufferView"]]
        dt = np.dtype(COMP[a["componentType"]])
        w = WIDTH[a["type"]]
        off = v.get("byteOffset", 0) + a.get("byteOffset", 0)
        stride = v.get("byteStride", dt.itemsize * w)
        raw = np.frombuffer(self.bin, np.uint8, count=stride * (a["count"] - 1) + dt.itemsize * w, offset=off)
        rows = np.lib.stride_tricks.as_strided(raw, (a["count"], dt.itemsize * w), (stride, 1))
        out = rows.copy().view(dt).reshape(a["count"], w).squeeze()
        if a.get("normalized"):          # 顶点色常存成归一化的整数
            out = out.astype(np.float32) / np.iinfo(dt).max
        return out

    def primitive(self, mesh, material=None):
        for m in self.g["meshes"]:
            if m["name"] != mesh:
                continue
            for p in m["primitives"]:
                if material and self.g["materials"][p["material"]]["name"] != material:
                    continue
                return {k: self.accessor(i) for k, i in p["attributes"].items()}, self.accessor(p["indices"]).reshape(-1, 3)
        raise SystemExit(f"glb 里没有网格 {mesh}（材质 {material}）")


def strands_from_cards(pos, uv, tris):
    """发片 → 发丝：每个连通块一片，按 v（glTF 里根 1、梢 0）排好，同一个 v 的左右两个顶点取中点。返回 (片数, 点数, 3)"""
    n = len(pos)
    edges = np.concatenate([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]])
    adj = coo_matrix((np.ones(len(edges)), (edges[:, 0], edges[:, 1])), shape=(n, n))
    count, label = connected_components(adj, directed=False)
    per = n // count
    if per * count != n or np.any(np.bincount(label) != per) or per % 2:
        raise SystemExit(f"发片顶点数不齐：{n} 个顶点、{count} 片")
    order = np.lexsort((-uv[:, 1], label))           # 先按片，片内从根（v 大）到梢
    p = pos[order].reshape(count, per // 2, 2, 3).mean(axis=2).astype(np.float64)
    return p


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def unit(v):
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-12)


def rotations(a, b):
    """把单位向量 a 转到 b 的旋转矩阵（逐行，Rodrigues）"""
    v = np.cross(a, b)
    c = np.einsum("ij,ij->i", a, b)
    k = np.zeros((len(a), 3, 3))
    k[:, 0, 1], k[:, 0, 2], k[:, 1, 2] = -v[:, 2], v[:, 1], -v[:, 0]
    k[:, 1, 0], k[:, 2, 0], k[:, 2, 1] = v[:, 2], -v[:, 1], v[:, 0]
    return np.eye(3) + k + k @ k / (1.0 + np.maximum(c, -0.99))[:, None, None]


def arc(s):
    """每根各点的弧长 (n, m)"""
    seg = np.linalg.norm(np.diff(s, axis=1), axis=2)
    return np.concatenate([np.zeros((len(s), 1)), np.cumsum(seg, axis=1)], axis=1)


def resample(s, k, frac=None):
    """(n, m, 3) 每根按弧长重采样成 k 个点；frac 给了就只取每根从根起的这么一截（剪短）"""
    n, m, _ = s.shape
    d = arc(s)
    length = d[:, -1] if frac is None else d[:, -1] * frac
    t = np.linspace(0.0, 1.0, k)[None, :] * length[:, None]
    big = d[:, -1].max() + 1.0                        # 每行错开一大截，一次 searchsorted 查完所有行
    off = np.arange(n)[:, None] * big
    j = np.searchsorted((d + off).ravel(), (t + off).ravel(), side="right").reshape(n, k) - 1
    j = np.clip(j - np.arange(n)[:, None] * m, 0, m - 2)
    rows = np.arange(n)[:, None]
    d0, d1 = d[rows, j], d[rows, j + 1]
    w = np.clip((t - d0) / np.maximum(d1 - d0, 1e-12), 0.0, 1.0)[..., None]
    return s[rows, j] * (1 - w) + s[rows, j + 1] * w


def tangents(s):
    return unit(np.gradient(s, axis=1))


def wiggle(n, k, rng, cycles):
    """每根一条平滑的随机曲线（两个随机方向上各一个正弦，频率按全长算几个周期、相位随机），(n, k, 3)，最大约 1"""
    t = np.linspace(0.0, 1.0, k)[None, :, None]
    out = np.zeros((n, k, 3))
    for _ in range(2):
        f = rng.uniform(cycles[0], cycles[1], (n, 1, 1))
        ph = rng.uniform(0.0, 2 * np.pi, (n, 1, 1))
        out += np.sin(2 * np.pi * f * t + ph) * unit(rng.normal(size=(n, 1, 3)))
    return out * 0.7


def across(v, tan):
    """v 去掉顺着发丝的分量（只往两边弯，不改长短）"""
    return v - tan * np.einsum("nkj,nkj->nk", v, tan)[..., None]


def outward(p, center):
    """往外的方向：从头的中心指出来；头中心以下（垂下来的头发）只取水平方向，不往下推"""
    r = p - center
    r[..., 1] *= np.where(r[..., 1] < 0, 0.15, 1.0)
    return unit(r)


class Scalp:
    """皮肤（Crew_Skin）：最近的顶点 + 法线，把点压回头皮、推出皮肤。
    最近顶点的法线不全可信：耳朵、耳后那一圈最近的顶点可能在耳廓背面，法线和头皮差到一百多度。
    和“从头中心往外”的方向差太多（点积 < 0.3）的不用"""

    def __init__(self, sp, sn, center):
        self.sp, self.sn, self.center = sp, sn, center
        self.tree = cKDTree(sp)

    def _near(self, p):
        dist, i = self.tree.query(p)
        n = self.sn[i]
        ok = np.einsum("ij,ij->i", n, unit(p - self.center)) > 0.3
        return dist, i, n, ok

    def project(self, p):
        """落到最近顶点的切平面上（法线不可信的不动）"""
        _, i, n, ok = self._near(p)
        sd = np.einsum("ij,ij->i", p - self.sp[i], n) * ok
        return p - n * sd[:, None]

    def push_out(self, s, start=1):
        """每根从第 start 个点起，离皮肤不到 GAP 的推出去（离皮肤 3 厘米以外的不管：垂到肩上的头发最近的是脖子底下的开口）"""
        p = s[:, start:].reshape(-1, 3)
        dist, i, n, ok = self._near(p)
        sd = np.einsum("ij,ij->i", p - self.sp[i], n)
        fix = (sd < GAP) & (dist < 0.03) & ok
        p[fix] += n[fix] * (GAP - sd[fix])[:, None]
        s[:, start:] = p.reshape(len(s), -1, 3)
        return s


def sample_scalp(shell, tris, m, rng):
    """层壳最里一层（顶点色 R = 0，就是这个发型有头发的那块头皮，离皮肤 0.2 毫米）上按面积均匀撒 m 个点，
    返回 (点, 发量 G, 离这块头皮的边多远)。边就是发际线（耳朵、后颈那一圈也是）；分缝在里面，发量也低，但离边远"""
    col, pos = shell["COLOR_0"], shell["POSITION"].astype(np.float64)
    base = col[:, 0] < 0.01
    t = tris[base[tris].all(axis=1)]
    # 边：只属于一个三角形的边，每条上撒几个点。glTF 在 UV 接缝处把顶点拆成了几个，先按位置焊回去，不然接缝也成了边
    _, weld = np.unique(np.round(pos / 1e-5).astype(np.int64), axis=0, return_inverse=True)
    weld = weld.ravel()
    e = np.sort(np.concatenate([weld[t[:, [0, 1]]], weld[t[:, [1, 2]]], weld[t[:, [2, 0]]]]), axis=1)
    uniq, cnt = np.unique(e, axis=0, return_counts=True)
    rim = uniq[cnt == 1]
    first = np.zeros(weld.max() + 1, np.int64)
    first[weld] = np.arange(len(weld))                 # 焊过的顶点 → 原来的某一个（位置一样）
    w = np.linspace(0.0, 1.0, 6)[None, :, None]
    rim_pts = (pos[first[rim[:, 0]]][:, None] * (1 - w) + pos[first[rim[:, 1]]][:, None] * w).reshape(-1, 3)
    a, b, c = pos[t[:, 0]], pos[t[:, 1]], pos[t[:, 2]]
    area = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)
    f = rng.choice(len(t), m, p=area / area.sum())
    u, v = rng.random(m), rng.random(m)
    flip = u + v > 1
    u[flip], v[flip] = 1 - u[flip], 1 - v[flip]
    p = a[f] + (b[f] - a[f]) * u[:, None] + (c[f] - a[f]) * v[:, None]
    g = col[:, 1]
    dens = g[t[f, 0]] * (1 - u - v) + g[t[f, 1]] * u + g[t[f, 2]] * v
    return p, dens, cKDTree(rim_pts).query(p)[0]


def grow(guides, roots, center):
    """新发根照附近的引导线长：最近的 3 根里和最近那根形状相近的按距离混（不相近的不混），每根按两处“从头中心往外”
    的方向的夹角转过去（头是圆的，照搬会扎进头皮或者飘起来；不用皮肤的法线：见 Scalp）。离得近的转得很少——
    一根 40 厘米的长发转 5° 发梢就偏出 3.5 厘米。返回 (发丝 (n, WORK, 3), 最近的引导线序号)"""
    gn, rn = unit(guides[:, 0] - center), unit(roots - center)
    rel = guides - guides[:, :1]
    length = arc(guides)[:, -1]
    _, gi = cKDTree(guides[:, 0]).query(roots, k=3)
    d = np.linalg.norm(roots[:, None] - guides[gi, 0], axis=2)
    shapes = np.stack([np.einsum("nij,nkj->nki", rotations(gn[gi[:, j]], rn), rel[gi[:, j]]) for j in range(3)], axis=1)
    diff = np.linalg.norm(shapes - shapes[:, :1], axis=3).mean(axis=2)          # 和最近那根差多少（平均每个点）
    ok = diff < np.maximum(0.004, 0.08 * length[gi[:, 0]])[:, None]
    w = ok / (d + 0.002) ** 2
    w /= w.sum(axis=1, keepdims=True)
    return roots[:, None] + np.einsum("nj,njkc->nkc", w, shapes), gi[:, 0]


def groom(guides, shell, shell_tris, scalp, center, cfg, rng):
    """整头头发（见文件头）。返回 (发丝 (n, verts, 3), 每根的 (粗细倍数, 深浅))"""
    k = WORK
    g = resample(guides, k)
    g[:, 0] = scalp.project(g[:, 0])
    ng = len(g)
    gt = tangents(g)
    t = np.linspace(0.0, 1.0, k)[None, :, None]
    # 一绺一起弯：引导线（每绺的中心）先弯，跟着它的发丝收过去的时候一起弯过去
    g = g + across(wiggle(ng, k, rng, (0.3, 1.2)), gt) * cfg["lock"] * t ** 1.3
    g = scalp.push_out(g)

    # 发根：撒多一点，按发量留下——发际线那圈（离头皮这块的边 1 厘米以内）越往外越稀；里面发量低的地方（分缝）照样密，
    # 不然缝宽得像秃了一道。离引导线太远的不要（这个发型那里本来没头发）
    p, dens, edge = sample_scalp(shell, shell_tris, int(cfg["n"] * 2.2), rng)
    # 头皮这块比发型实际的发际线大一圈（层壳的发量按发根 3~10 毫米算的），靠边 2 厘米以内只在引导线的发根附近长，
    # 不然额头上多出一圈稀稀拉拉的短毛
    e0, e1 = cfg.get("edge", (0.004, 0.012))
    gd = cKDTree(g[:, 0]).query(p)[0]
    near_guide = np.where(edge > 0.02, 1.0, smoothstep(0.012, 0.004, gd))
    keep = rng.random(len(p)) < np.minimum(np.maximum(smoothstep(0.3, 0.85, dens), smoothstep(e0, e1, edge)),
                                           smoothstep(0.0, e1, edge) ** 0.5) * near_guide
    roots = p[keep][: cfg["n"]]
    roots = roots[cKDTree(g[:, 0]).query(roots)[0] < 0.03]
    n = len(roots)
    s, gi = grow(g, roots, center)

    # 成绺：越往发梢越往这一绺的中心（最近的引导线）收
    amt = rng.uniform(cfg["clump"][0], cfg["clump"][1], ng)[gi] * rng.uniform(0.7, 1.0, n)
    s += (g[gi] - s) * (amt[:, None] * smoothstep(0.0, 1.0, t[..., 0]))[..., None]
    # 每根自己弯一点
    s += across(wiggle(n, k, rng, (0.5, 1.8)), tangents(s)) * cfg["wave"] * t ** 1.5
    # 头发层的深浅：一绺一个，绺里每根再差一点
    depth = np.clip(rng.random(ng)[gi] + rng.normal(0.0, 0.12, n), 0.0, 1.0)
    # 毛躁：外层的一半发丝细碎地弯（里层压着、梳顺了）
    fz = (rng.random(n) < 0.5) * depth ** 2
    s += across(wiggle(n, k, rng, (2.5, 6.0)), tangents(s)) * (cfg["frizz"] * fz)[:, None, None] * t
    # 发梢长短不齐：大多数差不多长，少数短一截
    frac = 1.0 - cfg["cut"] * rng.random(n) ** 2
    s = resample(s, k, frac)

    # 外层的离头皮抬高，从发根往外 3 厘米（短发按长度的三成）抬到位
    d = arc(s)
    ramp = smoothstep(0.0, np.minimum(0.03, 0.3 * d[:, -1:]), d)
    s += outward(s, center) * (cfg["lift"] * depth[:, None] * ramp)[..., None]

    width = rng.uniform(0.75, 1.25, n)
    # 乱发：从中段起往外翘、往两边飘，细一点，在最外层
    nf = int(n * cfg["fly"])
    if nf:
        f = rng.choice(n, nf, replace=False)
        t0 = rng.uniform(0.15, 0.6, nf)[:, None]
        env = smoothstep(t0, 1.0, t[0, :, 0][None, :]) ** 1.5
        amp = np.minimum(rng.uniform(0.02, 0.08, nf) * arc(s[f])[:, -1], 0.025)[:, None]   # 长头发飘得远
        push = outward(s[f], center) + 0.8 * across(wiggle(nf, k, rng, (0.3, 1.0)), tangents(s[f]))
        s[f] += push * (amp * env)[..., None]
        width[f] = rng.uniform(0.5, 0.75, nf)
        depth[f] = 1.0

    # 发际线的绒毛：发量渐稀的那一圈里，照最近的引导线长短短一截（0.5~2.5 厘米），细、弯得多
    nb = cfg["baby"]
    if nb:
        p, dens, edge = sample_scalp(shell, shell_tris, nb * 20, rng)
        gd = cKDTree(g[:, 0]).query(p)[0]
        band = rng.random(len(p)) < smoothstep(0.15, 0.35, dens) * smoothstep(0.75, 0.45, dens) * (edge < e1) * (gd < 0.008)
        b, _ = grow(g, p[band][:nb], center)
        blen = arc(b)[:, -1]
        b = resample(b, k, np.clip(rng.uniform(0.005, 0.025, len(b)) / np.maximum(blen, 1e-4), 0.02, 1.0))
        bl = arc(b)[:, -1:, None]
        b += across(wiggle(len(b), k, rng, (0.4, 1.0)), tangents(b)) * 0.25 * bl * t ** 1.2
        s = np.concatenate([s, b])
        width = np.concatenate([width, rng.uniform(0.35, 0.55, len(b))])
        depth = np.concatenate([depth, np.ones(len(b))])

    s = scalp.push_out(s)
    out = resample(s, cfg["verts"])
    order = rng.permutation(len(out))
    return out[order], np.stack([width, depth], axis=1)[order]


def write_tfx(path, strands, attrs):
    """.tfx 4.0：160 字节的头（版本、根数、每根点数、坐标的偏移、发丝 UV 的偏移），每个点 xyz + w（0 钉住），再每根一个 UV。
    头两个点钉在头皮上（w = 0），其余能动；不到 3 厘米的（发际线的绒毛、寸把长的碎发）整根钉住：一两厘米分成几十段，
    模拟里撑不住形状，被重力一拉全耷拉下来，发际线像挂了一排刘海"""
    n, k, _ = strands.shape
    out = np.zeros((n, k, 4), np.float32)
    out[:, :, :3] = strands
    length = np.linalg.norm(np.diff(strands, axis=1), axis=2).sum(axis=1)
    out[length >= 0.03, 2:, 3] = 1.0
    pos = out.tobytes()
    with open(path, "wb") as f:
        head = struct.pack("<fIIII", 4.0, n, k, 160, 160 + len(pos))
        f.write(head + bytes(160 - len(head)))
        f.write(pos)
        f.write(attrs.astype(np.float32).tobytes())


def main():
    sys.stdout.reconfigure(encoding="utf-8")   # 中文 Windows 默认 GBK，输出给管道时乱码
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, ".tmp", "tfx", "styles"))
    ap.add_argument("--style", default=",".join(GROOM))
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    for sex in "fm":
        glb = Glb(os.path.join(ROOT, "assets", "models", f"crew_body_{sex}.glb"))
        # 头的中心：寸头的层壳（贴着头皮的那层也在里面）包围盒的中心
        shell, _ = glb.primitive("Crew_Shell_buzz")
        lo, hi = shell["POSITION"].min(axis=0), shell["POSITION"].max(axis=0)
        center = (lo + hi) / 2
        skin, _ = glb.primitive("Crew_Head", "Crew_Skin")
        sp, sn = skin["POSITION"].astype(np.float64), skin["NORMAL"].astype(np.float64)
        scalp = Scalp(sp, sn, center)
        for style in a.style.split(","):
            cfg = GROOM[style]
            rng = np.random.default_rng(a.seed)
            attr, tris = glb.primitive("Crew_Hair_" + style)
            guides = strands_from_cards(attr["POSITION"], attr["TEXCOORD_0"], tris)
            sh, sh_tris = glb.primitive("Crew_Shell_" + style)
            r, at = groom(guides, sh, sh_tris, scalp, center, cfg, rng)
            length = np.linalg.norm(np.diff(r, axis=1), axis=2).sum(axis=1)
            path = os.path.join(a.out, f"{sex}_{style}.tfx")
            write_tfx(path, r, at)
            print(f"{sex} {style:<6} {len(r):6d} 根（引导线 {len(guides)}，每根 {r.shape[1]} 个点），"
                  f"长度 中位 {np.median(length) * 100:.1f} 厘米、最长 {length.max() * 100:.1f} 厘米 → {os.path.relpath(path, ROOT)}")
        # 碰撞用的头：皮肤的凸包往里收 2.5 毫米（插件要求碰撞体是封闭网格、比看得见的表面略小）
        hull = ConvexHull(sp)
        hv = sp[hull.vertices]
        remap = {int(v): j for j, v in enumerate(hull.vertices)}
        ht = [[remap[int(x)] for x in t] for t in hull.simplices]
        c = hv.mean(axis=0)
        # 面的朝向统一成往外（ConvexHull 的 simplices 不保证绕向）
        for t in ht:
            p0, p1, p2 = hv[t[0]], hv[t[1]], hv[t[2]]
            if np.dot(np.cross(p1 - p0, p2 - p0), p0 - c) < 0:
                t[1], t[2] = t[2], t[1]
        d = hv - c
        hv = c + d * (1 - 0.0025 / np.linalg.norm(d, axis=1))[:, None]
        path = os.path.join(a.out, f"{sex}_head.json")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            json.dump({"verts": np.round(hv, 5).tolist(), "tris": ht, "volume_center": np.round(center, 5).tolist(),
                       "scalp_min": np.round(lo, 5).tolist(), "scalp_max": np.round(hi, 5).tolist()}, f)
        print(f"{sex} 头的凸包 {len(hv)} 个顶点、{len(ht)} 个三角形，头皮 {np.round(lo, 3)} ~ {np.round(hi, 3)} → {os.path.relpath(path, ROOT)}")


if __name__ == "__main__":
    main()
