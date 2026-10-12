"""眼：巨物「大眼」的眼球 + 角膜。权重全给 "Eye"（眼球中心 spec.EYE_CENTER，半径 spec.EYE_R）。
形体（虹膜的碟、竖瞳凹槽、椭圆坐标、角膜剖面）见 eye_geo.py；高模细节见 eye_detail.py。

低模（进游戏，约 5.5k 三角）：
  EyeBall（M_WatcherEye，烘焙目标）：眼轴为中心一圈圈往外——
    虹膜：72 条辐条沿椭圆坐标的双曲线（从竖缝往外放射），环是 μ 常数的椭圆（越往外越圆，s = 1 时正好是根部的圆），
      瞳孔凹槽里面用一排「梯子」缝起来；根部往外三圈爬回球面到角膜缘（θ = 44°）。
    巩膜：θ = 44°～88°，八圈；辐条的角度从角膜缘处（跟着虹膜）慢慢过渡到均匀。
  EyeBack（M_WatcherEye，不烘焙）：θ = 88°～180° 的眼球后部（永远埋在眼窝里，转 25° 也露不出来），四圈 + 极点。
  Cornea（M_WatcherCornea，不烘焙）：θ ≤ 50° 的鼓包，顶点比眼球多鼓出 0.33 米，边缘埋回眼球。
UV0（贴图组 "eye"）：
  虹膜一个圆岛：平面正投影 (x, y)（站在正前方看到的样子，不镜像），atlas_uv 排完以后再转回「瞳孔竖直 = UV +V」
    （圆岛绕自己圆心转，占的地方不变）。
  巩膜四条：以眼轴为极的墨卡托展开（保角，越靠角膜缘密度越高 1.4 倍），按经度切成四段。
  眼球后部：不进图集，UV 贴在巩膜最外一圈带子上（来回镜像，反正看不到）。
  角膜：不进图集，和虹膜岛重合（同样的平面投影，按角膜边缘 = 虹膜岛边缘缩放）——角膜不要用 eye_normal。
  排完以后虹膜岛的位置写进 assets/textures/watcher/eye_iris.json（材质做竖瞳用）。
"""
import json
import math
import os
import time

import bpy
import numpy as np

import lib
from watcher import spec, bakeutil
from watcher import eye_util as U
from watcher import eye_geo as G

S = 72                                     # 一圈几条辐条
NU = 2 * np.pi * np.arange(S) / S          # 虹膜辐条的 ν（0 朝上，往 +x 转）
INNER_MU = [0.035, 0.09]                   # 瞳孔凹槽里面的两圈（μ）
IRIS_S = [0.0, 0.05, 0.13, 0.23, 0.33, 0.44, 0.56, 0.68, 0.79, 0.89, 1.0]
WALL_RHO = [2.92, 2.99]                    # 根部往外爬回球面（再往外是角膜缘 RHO_L）
SCLERA_TH = [44, 46, 49, 53, 58, 64, 71, 79, 88]
BACK_TH = [88, 100, 118, 140]
CORNEA_T = [0.1, 0.2, 0.31, 0.42, 0.53, 0.63, 0.72, 0.8, 0.87, 0.93, 0.97, 1.0]
STRIPS = 4                                 # 巩膜按经度切几条（试过 3、6、8、12 条，四条排得最满）


def _wrap(a):
    return (a + np.pi) % (2 * np.pi) - np.pi


def _phi_u(j):
    """均匀辐条的方位角（和虹膜辐条 ν 对上：ν = 0 朝上 → φ = 90°）。j 可以到 S（展开不跳）。"""
    return np.pi / 2 - 2 * np.pi * np.asarray(j) / S


def iris_rings():
    """虹膜各圈的平面坐标 (环数, S, 2)，最后一圈是角膜缘。"""
    rings = []
    for mu in INNER_MU:
        rings.append(np.stack(G.from_elliptic(np.full(S, mu), NU), axis=1))
    for s in IRIS_S:
        mu = G.MU_P + s * (G.mu_root(NU) - G.MU_P)
        rings.append(np.stack(G.from_elliptic(mu, NU), axis=1))
    phi = np.arctan2(rings[-1][:, 1], rings[-1][:, 0])
    for rho in WALL_RHO + [G.RHO_L]:
        rings.append(np.stack([rho * np.cos(phi), rho * np.sin(phi)], axis=1))
    return np.array(rings), phi


def _orient(verts, faces, uvs, want):
    """把法线和期望方向（want(面中心, 面法线) → 期望方向）反着的面翻过来；返回翻了几个。"""
    v = np.asarray(verts)
    n = U.face_normals(v, faces)
    flipped = 0
    for i, f in enumerate(faces):
        c = v[list(f)].mean(axis=0)
        if np.dot(n[i], want(c)) < 0:
            faces[i] = tuple(reversed(f))
            uvs[i] = tuple(reversed(uvs[i]))
            flipped += 1
    return flipped


def _uv_signed_area(faces_uv):
    s = 0.0
    for uv in faces_uv:
        for k in range(len(uv)):
            x0, y0 = uv[k]
            x1, y1 = uv[(k + 1) % len(uv)]
            s += x0 * y1 - x1 * y0
    return s


# ---------------------------------------------------------------------------- 眼球（前部，烘焙目标）
def build_ball(coll, mat):
    rings, phi_l = iris_rings()
    ni = len(rings)
    verts, plane = [], []
    for r in rings:
        z = G.iris_z(r[:, 0], r[:, 1])
        verts += list(G.plane_to_world(r[:, 0], r[:, 1], z))
        plane += list(r)
    # 巩膜：第 0 圈就是虹膜的角膜缘那圈（共用顶点）
    delta = _wrap(phi_l - _phi_u(np.arange(S)))
    delta = np.append(delta, delta[0])
    sth = [math.radians(t) for t in SCLERA_TH]
    sphi = []                                  # 每圈每条辐条展开后的 φ（S + 1 个，最后一个 = 第 0 个转一圈）
    for k, th in enumerate(sth):
        w = float(U.smoothstep(0.0, 4.0, k))
        ph = _phi_u(np.arange(S + 1)) + delta * (1 - w)
        sphi.append(ph)
        if k > 0:
            verts += list(G.C + G.R * G.sphere_dir(np.full(S, th), ph[:S]))
    vid_iris = lambda i, j: i * S + (j % S)
    vid_scl = lambda k, j: (ni - 1) * S + k * S + (j % S) if k > 0 else vid_iris(ni - 1, j)

    faces, uvs, kinds = [], [], []
    # 瞳孔凹槽里的梯子：j 和 S - j 是左右对称的一对
    pl = lambda i, j: tuple(plane[vid_iris(i, j)])
    for j in range(S // 2):
        a, b, c, d = j, j + 1, (S - j - 1) % S, (S - j) % S
        f = [a, b, c, d]
        if d == a:
            f = [a, b, c]
        elif c == b:
            f = [a, b, d]
        faces.append(tuple(vid_iris(0, q) for q in f))
        uvs.append(tuple(pl(0, q) for q in f))
        kinds.append("iris")
    for i in range(ni - 1):
        for j in range(S):
            f = (vid_iris(i, j), vid_iris(i, j + 1), vid_iris(i + 1, j + 1), vid_iris(i + 1, j))
            faces.append(f)
            uvs.append((pl(i, j), pl(i, j + 1), pl(i + 1, j + 1), pl(i + 1, j)))
            kinds.append("iris")
    n_iris = len(faces)
    # 巩膜：墨卡托，按经度切 STRIPS 条
    per = S // STRIPS
    merc = lambda k, j: (-G.R * sphi[k][j], G.R * math.log(math.tan(sth[k] / 2)))
    last_band = {}
    for k in range(len(sth) - 1):
        for j in range(S):
            f = (vid_scl(k, j), vid_scl(k, j + 1), vid_scl(k + 1, j + 1), vid_scl(k + 1, j))
            faces.append(f)
            off = (j // per) * 5.0          # 各条先错开放（pack 会重排）
            uvs.append(tuple((u + off, v) for (u, v) in
                             (merc(k, j), merc(k, j + 1), merc(k + 1, j + 1), merc(k + 1, j))))
            kinds.append("sclera")
            if k == len(sth) - 2:
                last_band[j] = len(faces) - 1
    verts = np.array(verts)
    want = lambda c: G.EZ if np.dot(c - G.C, G.EZ) > 0 and np.linalg.norm(
        np.cross(c - G.C, G.EZ)) < G.RHO_L - 1e-3 else (c - G.C)
    fl = _orient(verts, faces, uvs, lambda c: want(c))
    if fl:
        print(f"eye: flipped {fl} ball faces")
    # UV 别镜像：每个岛的有向面积要是正的（法线朝外时逆时针）
    if _uv_signed_area(uvs[:n_iris]) < 0:
        print("WARNING eye: 虹膜 UV 镜像了")
    if _uv_signed_area(uvs[n_iris:]) < 0:
        uvs[n_iris:] = [tuple((-u, v) for (u, v) in f) for f in uvs[n_iris:]]
    ob = U.mesh_object("EyeBall", coll, verts, faces, uvs, mat)
    info = dict(n_iris=n_iris, plane=np.array(plane), faces=faces, last_band=last_band, sphi=sphi)
    return ob, info


# ---------------------------------------------------------------------------- 眼球后部（不烘焙）
def build_back(coll, mat):
    ths = [math.radians(t) for t in BACK_TH]
    verts = []
    for th in ths:
        verts += list(G.C + G.R * G.sphere_dir(np.full(S, th), _phi_u(np.arange(S))))
    pole = len(verts)
    verts.append(G.C - G.EZ * G.R)
    faces = []
    for k in range(len(ths) - 1):
        for j in range(S):
            j1 = (j + 1) % S
            faces.append((k * S + j, k * S + j1, (k + 1) * S + j1, (k + 1) * S + j))
    base = (len(ths) - 1) * S
    for j in range(S):
        faces.append((base + j, base + (j + 1) % S, pole))
    uvs = [tuple((0.0, 0.0) for _ in f) for f in faces]
    verts = np.array(verts)
    _orient(verts, faces, uvs, lambda c: c - G.C)
    return U.mesh_object("EyeBack", coll, verts, faces, uvs, mat)


# ---------------------------------------------------------------------------- 角膜（不烘焙）
def build_cornea(coll, mat):
    ph = _phi_u(np.arange(S))
    verts, plane = [], []
    for t in CORNEA_T:
        th = t * G.TH_C
        r = float(G.cornea_r(t))
        verts += list(G.C + r * G.sphere_dir(np.full(S, th), ph))
        plane += list(np.stack([r * math.sin(th) * np.cos(ph), r * math.sin(th) * np.sin(ph)], axis=1))
    pole = len(verts)
    verts.append(G.C + G.EZ * float(G.cornea_r(0.0)))
    plane.append((0.0, 0.0))
    faces = []
    for j in range(S):
        faces.append((pole, j, (j + 1) % S))
    for k in range(len(CORNEA_T) - 1):
        for j in range(S):
            j1 = (j + 1) % S
            faces.append((k * S + j, k * S + j1, (k + 1) * S + j1, (k + 1) * S + j))
    plane = np.array(plane)
    uvs = [tuple(tuple(plane[i]) for i in f) for f in faces]
    verts = np.array(verts)
    _orient(verts, faces, uvs, lambda c: c - G.C)
    ob = U.mesh_object("Cornea", coll, verts, faces, uvs, mat)
    rim = plane[(len(CORNEA_T) - 1) * S:(len(CORNEA_T)) * S]
    return ob, plane, float(np.linalg.norm(rim, axis=1).max())


# ---------------------------------------------------------------------------- 图集排完以后
def _loop_uvs(ob):
    me = ob.data
    uv = np.empty(len(me.loops) * 2, dtype=np.float64)
    me.uv_layers[spec.UV_MAIN].data.foreach_get("uv", uv)
    return uv.reshape(-1, 2)


def _set_loop_uvs(ob, uv):
    ob.data.uv_layers[spec.UV_MAIN].data.foreach_set("uv", np.asarray(uv, dtype=np.float32).ravel())


def fix_uvs(ball, info, back, cornea, cplane, crim):
    """虹膜岛转正（瞳孔竖直 = +V）；眼球后部、角膜的 UV 跟着图集定。返回虹膜岛的 (中心, 每米多少 UV)。"""
    me = ball.data
    uv = _loop_uvs(ball)
    starts = np.empty(len(me.polygons), dtype=np.int64)
    me.polygons.foreach_get("loop_start", starts)
    lv = np.empty(len(me.loops), dtype=np.int64)
    me.loops.foreach_get("vertex_index", lv)
    n_iris = info["n_iris"]
    iris_loops = np.arange(starts[n_iris]) if n_iris < len(starts) else np.arange(len(lv))
    p = info["plane"][lv[iris_loops]]
    q = uv[iris_loops]
    pc = p[:, 0] + 1j * p[:, 1]
    qc = q[:, 0] + 1j * q[:, 1]
    pm, qm = pc.mean(), qc.mean()
    a = np.sum(np.conj(pc - pm) * (qc - qm)) / np.sum(np.abs(pc - pm) ** 2)
    b = qm - a * pm                       # 平面原点（眼轴 = 瞳孔中心）在 UV 里的位置
    k = abs(a)
    print(f"eye: iris island rotated {math.degrees(np.angle(a)):.1f} deg by packing -> upright")
    new = b + k * pc
    uv[iris_loops, 0] = new.real
    uv[iris_loops, 1] = new.imag
    _set_loop_uvs(ball, uv)
    # 眼球后部：贴在巩膜最外一圈带子（θ 79°～88°）上
    loop_of = {}
    for j, f in info["last_band"].items():
        st = starts[f]
        loop_of[j] = {int(lv[st + c]): uv[st + c] for c in range(len(info["faces"][f]))}
    ni = (len(INNER_MU) + len(IRIS_S) + len(WALL_RHO) + 1)
    k79 = len(SCLERA_TH) - 2
    vid = lambda kk, j: (ni - 1) * S + kk * S + (j % S)

    def band_uv(j, jj, t):
        d = loop_of[j]
        return (1 - t) * d[vid(k79 + 1, jj)] + t * d[vid(k79, jj)]
    bme = back.data
    buv = _loop_uvs(back)
    bst = np.empty(len(bme.polygons), dtype=np.int64)
    bme.polygons.foreach_get("loop_start", bst)
    blv = np.empty(len(bme.loops), dtype=np.int64)
    bme.loops.foreach_get("vertex_index", blv)
    tring = [0.0, 0.25, 0.5, 0.75]
    pole = len(BACK_TH) * S
    for fi, poly in enumerate(bme.polygons):
        vs = [int(blv[bst[fi] + c]) for c in range(poly.loop_total)]
        ring_vs = [v for v in vs if v != pole]
        js = sorted({v % S for v in ring_vs})
        j0 = js[0] if not (0 in js and S - 1 in js) else S - 1     # 这个面所在的那一列（j0, j0+1）
        for c, v in enumerate(vs):
            if v == pole:
                val = 0.5 * (band_uv(j0, j0, 1.0) + band_uv(j0, j0 + 1, 1.0))
            else:
                jj = j0 if v % S == j0 else j0 + 1
                val = band_uv(j0, jj, tring[v // S])
            buv[bst[fi] + c] = val
    _set_loop_uvs(back, buv)
    # 角膜：同一个平面投影，按角膜边缘 = 虹膜岛的角膜缘缩放
    cme = cornea.data
    clv = np.empty(len(cme.loops), dtype=np.int64)
    cme.loops.foreach_get("vertex_index", clv)
    cp = cplane[clv]
    sc = k * G.RHO_L * 0.98 / crim
    cc = b + sc * (cp[:, 0] + 1j * cp[:, 1])
    _set_loop_uvs(cornea, np.stack([cc.real, cc.imag], axis=1))
    return b, k


def _write_iris_json(b, k):
    """材质做竖瞳用：虹膜岛在 UV 里的位置（Blender 的 UV，V 朝上；Godot 里 v' = 1 - v）。"""
    d = dict(
        note="Blender UV (v up). In Godot/glTF use v' = 1 - v; pupil 'up' is +v here, i.e. -v' in Godot.",
        center_uv=[round(b.real, 5), round(b.imag, 5)],
        center_uv_godot=[round(b.real, 5), round(1 - b.imag, 5)],
        uv_per_meter=round(k, 6),
        r_limbus_uv=round(k * G.RHO_L, 5),
        r_root_uv=round(k * G.RHO_ROOT, 5),
        pupil_groove_half_len_uv=round(k * G.PUPIL_B, 5),
        pupil_groove_half_width_uv=round(k * G.PUPIL_A, 5),
        pupil_margin_ellipse_uv=[round(k * G.PUPIL_HW, 5), round(k * G.FOC * math.cosh(G.MU_P), 5)],
        focus_uv=round(k * G.FOC, 5),
        collarette_s=G.COLLARETTE_S,
    )
    path = os.path.join(bakeutil.OUT_DIR, "eye_iris.json")
    os.makedirs(bakeutil.OUT_DIR, exist_ok=True)
    with open(path, "w") as f:
        json.dump(d, f, indent=1)
    print("eye iris uv:", d)


def build(coll, bake=False):
    t0 = time.time()
    m_eye = bpy.data.materials["M_WatcherEye"]
    m_cor = bpy.data.materials["M_WatcherCornea"]
    ball, info = build_ball(coll, m_eye)
    back = build_back(coll, m_eye)
    cornea, cplane, crim = build_cornea(coll, m_cor)
    obs = [ball, back, cornea]
    for o in obs:
        spec.assign_bone(o, "Eye")
    bakeutil.atlas_uv([ball], "eye")
    b, k = fix_uvs(ball, info, back, cornea, cplane, crim)
    _write_iris_json(b, k)
    print(f"eye low: ball {lib.stats([ball])}, back {lib.stats([back])}, cornea {lib.stats([cornea])} tris "
          f"({time.time() - t0:.1f}s)")
    if bake:
        from watcher import eye_detail
        t1 = time.time()
        highs = eye_detail.build_highs()
        print(f"eye high: {lib.stats(highs):,} tris ({time.time() - t1:.1f}s)")
        bakeutil.bake_set("eye", [ball], highs, extrusion=0.12, max_ray=0.35, ao_distance=0.6)
        for h in highs:
            bpy.data.objects.remove(h)
        print(f"eye bake: {time.time() - t1:.1f}s")
    return obs
