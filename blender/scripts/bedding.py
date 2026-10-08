"""铺位上的软东西：被子、枕头、床垫、布帘、叠好的毯子。

- 被子、枕头、布帘用 Blender 布料模拟摆出来：被子落在床垫（和底下蜷着的人形）上，枕头靠内压鼓起来，
  布帘挂在环上被重力拉直。模拟结果按输入算哈希缓存在 blender/cache/，参数不变就不重算。
- 床垫是带滚边、绗缝凹坑的软垫；叠好的毯子是一条折了几折的布。
- 每件东西单独成对象（带 UV，单位是米），面料纹理顺着布走；导出时再按材质合并。

坐标和 cockpit.py 一样：Blender +Y 朝艏，+Z 朝上，+X 朝右舷。
"""
import hashlib
import math
import os
import random

import bpy
import bmesh
import numpy as np
from mathutils import Vector as V

from lib import to_object, circle_profile, sweep

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CACHE_DIR = os.path.join(ROOT, "blender", "cache")
SIM_VERSION = 1  # 改了模拟流程（而不只是参数）时加一，旧缓存作废


# ============================================================================ 小工具
def _noise2(rng, n=6, fmin=1.5, fmax=6.0):
    """几组随机方向的正弦叠出来的平滑噪声 f(x, y)，幅值约 ±1。"""
    waves = []
    for _ in range(n):
        a = rng.uniform(0, math.tau)
        f = rng.uniform(fmin, fmax)
        waves.append((math.cos(a) * f, math.sin(a) * f, rng.uniform(0, math.tau), 1.0 / math.sqrt(f)))
    norm = sum(w[3] for w in waves)

    def f(x, y):
        return sum(w * math.sin(kx * x + ky * y + ph) for kx, ky, ph, w in waves) / norm * 1.6
    return f


def _mesh_arrays(bm):
    bm.verts.index_update()
    co = np.array([v.co[:] for v in bm.verts], dtype=np.float64)
    faces = [[v.index for v in f.verts] for f in bm.faces]
    return co, faces


def _hash(*parts):
    h = hashlib.sha1()
    for p in parts:
        if isinstance(p, np.ndarray):
            h.update(np.ascontiguousarray(np.round(p, 5)).tobytes())
        else:
            h.update(repr(p).encode())
    return h.hexdigest()[:16]


def _new_mesh_object(name, co, faces, coll):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(c) for c in co], [], faces)
    me.update()
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    return ob


# ============================================================================ 布料模拟
class Collider:
    """模拟时的碰撞体：一个 bmesh 和碰撞厚度。"""

    def __init__(self, bm, outer=0.004, friction=40.0):
        self.co, self.faces = _mesh_arrays(bm)
        bm.free()
        self.outer, self.friction = outer, friction

    def key(self):
        return (self.co, repr(self.faces[:50]), len(self.faces), self.outer, self.friction)


def simulate(tag, co, faces, colliders, frames=60, pin=None, mass=0.3, tension=15.0,
             bending=0.5, shrink=0.0, pressure=0.0, self_collide=False, quality=6, gravity=-9.81,
             air=1.0, distance=0.003, damping=5.0):
    """跑一次布料模拟，返回最后一帧的顶点坐标（世界坐标，和 co 一一对应）。
    co/faces：布的初始网格；pin：钉住不动的顶点下标；pressure>0 时布是封闭的，靠内压鼓起来。"""
    settings = dict(frames=frames, mass=mass, tension=tension, bending=bending, shrink=shrink,
                    pressure=pressure, self_collide=self_collide, quality=quality, gravity=gravity, air=air,
                    distance=distance, damping=damping, v=SIM_VERSION)
    pin = sorted(pin or [])
    key = _hash(tag, co, repr(faces[:50]), len(faces), pin, repr(sorted(settings.items())),
                *[k for c in colliders for k in c.key()])
    path = os.path.join(CACHE_DIR, f"{tag}_{key}.npy")
    if os.path.exists(path):
        out = np.load(path)
        if out.shape == co.shape:
            return out

    # 在当前场景里开一个临时集合跑（后台模式下别的场景拿不到 depsgraph）；布只和这个集合里的东西碰
    scn = bpy.context.scene
    old = (tuple(scn.gravity), scn.frame_start, scn.frame_end, scn.frame_current)
    scn.gravity = (0, 0, gravity)
    scn.frame_start, scn.frame_end = 1, frames
    coll = bpy.data.collections.new("ClothSim")
    scn.collection.children.link(coll)
    col_objs = []
    for i, c in enumerate(colliders):
        ob = _new_mesh_object(f"SimCol_{i}", c.co, c.faces, coll)
        ob.modifiers.new("Collision", 'COLLISION')
        ob.collision.thickness_outer = c.outer
        ob.collision.cloth_friction = c.friction
        ob.collision.use_culling = False
        if isinstance(c, Animated):
            ob.location.z = c.lift
            ob.keyframe_insert("location", index=2, frame=1)
            ob.location.z = 0.0
            ob.keyframe_insert("location", index=2, frame=c.until)
        col_objs.append(ob)
    cl = _new_mesh_object("SimCloth", co, faces, coll)
    if pin:
        vg = cl.vertex_groups.new(name="pin")
        vg.add(pin, 1.0, 'REPLACE')
    mod = cl.modifiers.new("Cloth", 'CLOTH')
    s = mod.settings
    s.quality = quality
    s.mass = mass
    s.air_damping = air
    s.tension_stiffness = s.compression_stiffness = tension
    s.shear_stiffness = tension * 0.3
    s.bending_stiffness = bending
    s.tension_damping = s.compression_damping = s.shear_damping = damping
    s.bending_damping = 0.5
    s.shrink_min = shrink
    if pin:
        s.vertex_group_mass = "pin"
        s.pin_stiffness = 1.0
    if pressure:
        s.use_pressure = True
        s.uniform_pressure_force = pressure
        s.pressure_factor = 1.0
    cs = mod.collision_settings
    cs.distance_min = distance
    cs.collision_quality = 4
    cs.use_self_collision = self_collide
    cs.self_distance_min = distance
    cs.self_friction = 10.0
    if hasattr(cs, "friction"):
        cs.friction = 20.0
    cs.collection = coll
    mod.point_cache.frame_start, mod.point_cache.frame_end = 1, frames

    for f in range(1, frames + 1):
        scn.frame_set(f)
    dg = bpy.context.evaluated_depsgraph_get()
    me = cl.evaluated_get(dg).to_mesh()
    out = np.empty(len(me.vertices) * 3, dtype=np.float64)
    me.vertices.foreach_get("co", out)
    out = out.reshape(-1, 3)
    cl.evaluated_get(dg).to_mesh_clear()

    for ob in col_objs + [cl]:
        me = ob.data
        bpy.data.objects.remove(ob)
        bpy.data.meshes.remove(me)
    bpy.data.collections.remove(coll)
    scn.gravity = old[0]
    scn.frame_start, scn.frame_end = old[1], old[2]
    scn.frame_set(old[3])

    os.makedirs(CACHE_DIR, exist_ok=True)
    np.save(path, out)
    print(f"cloth sim {tag}: {len(co)} verts, {frames} frames")
    return out


class Animated(Collider):
    """从 lift 米高的地方慢慢落到原位的碰撞体（往枕头上压出头的印子）。"""

    def __init__(self, bm, lift, until, outer=0.004, friction=8.0):
        super().__init__(bm, outer, friction)
        self.lift, self.until = lift, until

    def key(self):
        return super().key() + (self.lift, self.until)


# ============================================================================ 网格 → 对象
def grid(nu, nv, closed_u=False):
    """nu×nv 点阵的四边形面（下标 j*nu+i）。"""
    faces = []
    for j in range(nv - 1):
        for i in range(nu if closed_u else nu - 1):
            i1 = (i + 1) % nu
            faces.append([j * nu + i, j * nu + i1, (j + 1) * nu + i1, (j + 1) * nu + i])
    return faces


def cloth_object(name, coll, mat, co, faces, uv, thick=0.0, subsurf=1, uv2=None, recalc=True):
    """co: (n,3)；uv: 每个顶点一个 (n,2)，或每个面角一个（和 faces 同形状的列表）。
    uv2（每个顶点一个）：毯子用来画包边，(离最近布边的距离, 沿布边的坐标)，单位米。
    recalc=False：面的朝向已经排好了（模拟完的封闭网格可能自己穿插，自动重算会整个翻过来）。"""
    bm = bmesh.new()
    vs = [bm.verts.new(tuple(c)) for c in co]
    lay = bm.loops.layers.uv.new("UVMap")
    lay2 = bm.loops.layers.uv.new("UVMap2") if uv2 is not None else None
    per_vertex = isinstance(uv, np.ndarray) and len(uv) == len(co)
    for fi, f in enumerate(faces):
        try:
            face = bm.faces.new([vs[i] for i in f])
        except ValueError:
            continue
        for k, (loop, i) in enumerate(zip(face.loops, f)):
            loop[lay].uv = tuple(uv[i]) if per_vertex else tuple(uv[fi][k])
            if lay2 is not None:
                loop[lay2].uv = tuple(uv2[i])
    ob = to_object(bm, name, coll, mat, smooth=True, sharp_angle=None, recalc=recalc)
    if subsurf:
        m = ob.modifiers.new("Subsurf", 'SUBSURF')
        m.levels = m.render_levels = subsurf
        m.uv_smooth = 'PRESERVE_BOUNDARIES'
    if thick:
        m = ob.modifiers.new("Solidify", 'SOLIDIFY')
        m.thickness = thick
        m.offset = 0.0
        m.use_even_offset = False   # 布折得很尖的地方，均匀厚度会把顶点推出去老远
        m.use_rim = True
    return ob


def ellipsoid(bm, c, axis, r, half_len, u=20, v=12):
    """沿 axis 方向半长 half_len、横截面半径 r 的椭球。"""
    from lib import frame, S, uvsphere
    uvsphere(bm, 1.0, u, v, frame(c, axis) @ S(r[0], r[1], half_len))


# ============================================================================ 床垫
def _axis_samples(h, r, step):
    """-h..h 的采样点：中间均匀，靠两头圆角的地方加密。"""
    n = max(2, int(math.ceil(2 * (h - r) / step)))
    mid = [-(h - r) + 2 * (h - r) * k / n for k in range(n + 1)]
    return [-h, -(h - r) - 0.7 * r, -(h - r) - 0.35 * r] + mid + [(h - r) + 0.35 * r, (h - r) + 0.7 * r, h]


def cushion(center, half, r, step=0.03, top=None, bottom=True):
    """圆角软垫：六个面各是一张网格，投到圆角盒子上（面与面的边上顶点重合，转对象时焊上）。
    bottom=False 不要底面（压在床板上看不见）。
    top(x, y) 给顶面加起伏（局部坐标）。返回 co, faces, 面角 UV（条纹沿 Y 方向走）。"""
    hx, hy, hz = half
    ax = [_axis_samples(h, r, step) for h in half]
    inner = np.array(half) - r
    co, faces, fuv = [], [], []

    def project(p):
        c = np.clip(p, -inner, inner)
        d = p - c
        n = np.linalg.norm(d)
        q = c + d / n * r if n > 1e-9 else p.copy()
        if top is not None and q[2] > hz - r * 1.01:
            w = min(1.0, (q[2] - (hz - r)) / r)
            q[2] += top(q[0], q[1]) * w
        return q

    # (法线轴, 正负, 面内两轴)；面内两轴的顺序让面朝外
    for axis, sign in ((2, 1), (2, -1), (0, 1), (0, -1), (1, 1), (1, -1)):
        if (axis, sign) == (2, -1) and not bottom:
            continue
        a, b = [k for k in range(3) if k != axis]
        if sign < 0:
            a, b = b, a
        base = len(co)
        na, nb = len(ax[a]), len(ax[b])
        for j in range(nb):
            for i in range(na):
                p = np.zeros(3)
                p[axis] = sign * half[axis]
                p[a], p[b] = ax[a][i], ax[b][j]
                co.append(project(p))
        for f in grid(na, nb):
            faces.append([base + k for k in f])
            uvs = []
            for k in f:
                q = co[k]
                if axis == 2:
                    uvs.append((q[1], q[0]))
                elif axis == 0:
                    uvs.append((q[1], q[2]))
                else:
                    uvs.append((q[0], q[2]))
            fuv.append(uvs)
    co = np.array(co) + np.array(center)
    return co, faces, fuv


def piping(center, half, r, tube=0.0055, z_sign=1):
    """床垫顶面（或底面）一圈滚边：圆角矩形路径，截面是小圆管。返回 co, faces, 面角 UV。"""
    hx, hy, hz = half
    c45 = math.cos(math.radians(45))
    rx, ry = hx - r + r * c45, hy - r + r * c45
    rc = r * c45 + 0.004
    z = center[2] + z_sign * (hz - r + r * c45)
    path = []
    for cx, cy, a0 in ((rx - rc, ry - rc, 0), (-(rx - rc), ry - rc, 90), (-(rx - rc), -(ry - rc), 180),
                       (rx - rc, -(ry - rc), 270)):
        for k in range(7):
            a = math.radians(a0 + 90 * k / 6)
            path.append(V((center[0] + cx + math.cos(a) * rc, center[1] + cy + math.sin(a) * rc, z)))
    return tube_mesh(path, tube, bias=True)


def tube_mesh(path, tube, bias=False, spacing=0.03):
    """沿闭合路径扫一根细圆管（滚边、缝边）。返回 co, faces, 面角 UV（沿管子量，单位米）。
    bias=True：滚边布是斜裁的，条纹斜着绕在管子上。"""
    path = [V(p) for p in path]
    # 直边上加点，免得长边只有两头两个点
    dense = []
    for i in range(len(path)):
        p, q = path[i], path[(i + 1) % len(path)]
        n = max(1, int((q - p).length / spacing))
        dense += [p.lerp(q, t / n) for t in range(n)]
    bm = bmesh.new()
    prof = circle_profile(tube, 8)
    rings = sweep(bm, dense, prof, closed=True)
    bm.verts.index_update()
    co = np.array([v.co[:] for v in bm.verts])
    pos = {}
    s = 0.0
    for i, ring in enumerate(rings[:-1]):
        if i:
            s += (dense[i] - dense[i - 1]).length
        for k, v in enumerate(ring):
            pos[v.index] = (s, tube * math.tau * k / len(ring))
    total = s + (dense[0] - dense[-1]).length
    faces, fuv = [], []
    for f in bm.faces:
        idx = [v.index for v in f.verts]
        faces.append(idx)
        uvs = [pos[i] for i in idx]
        # 首尾接缝那一圈：沿路径的坐标从 total 绕回 0
        if max(u for u, _ in uvs) - min(u for u, _ in uvs) > total / 2:
            uvs = [(u + total if u < total / 2 else u, w) for u, w in uvs]
        fuv.append([(u * 0.7 + w * 0.7, -u * 0.7 + w * 0.7) for u, w in uvs] if bias else uvs)
    bm.free()
    return co, faces, fuv


# ============================================================================ 铺位
class Bunk:
    """一个铺位：床板、两头挡板、靠壳的衬板（还有上铺的护栏）当碰撞体，往上一件件摆床垫、枕头、被子、布帘。
    摆好的每件东西都会成为后面几件的碰撞体。"""

    def __init__(self, K, s, z0, xin, xw, ya, yf, deck, upper, tag):
        self.K, self.s, self.z0 = K, s, z0
        self.xin, self.xw, self.ya, self.yf = xin, xw, ya, yf
        self.deck, self.upper, self.tag = deck, upper, tag
        self.cols = []
        self.items = []   # (co, faces)：摆好的东西，用来查表面高度
        self.top = z0     # 床垫顶面
        x0, x1 = sorted((s * xin, s * (xw + 0.05)))
        self._box((x0, x1), (ya, yf), (z0 - 0.035, z0))                                # 床板
        if not upper:
            self._box(sorted((s * (xin + 0.02), s * xw)), (ya, yf), (deck, z0))        # 下铺的抽屉底座
            self._box((-1.5, 1.5), (ya - 0.5, yf + 0.5), (deck - 0.05, deck))          # 地板
        self._box(sorted((s * xw, s * (xw + 0.06))), (ya, yf), (z0 - 0.05, z0 + 0.6))  # 衬板
        for yy in (yf, ya):
            self._box(sorted((s * (xin - 0.01), s * xw)), (yy - 0.02, yy + 0.02), (deck, 0.43))
        if upper:
            self._box(sorted((s * xin, s * (xin + 0.03))), (ya, yf), (z0, z0 + 0.16))  # 护栏

    def x(self, d):
        """离中线 d 米（铺位那一舷）。"""
        return self.s * d

    def _box(self, xr, yr, zr, outer=0.003):
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0)
        for v in bm.verts:
            v.co = V(((xr[0] + xr[1]) / 2 + v.co.x * (xr[1] - xr[0]), (yr[0] + yr[1]) / 2 + v.co.y * (yr[1] - yr[0]),
                      (zr[0] + zr[1]) / 2 + v.co.z * (zr[1] - zr[0])))
        self.cols.append(Collider(bm, outer))

    def _add(self, co, faces, outer=0.004):
        bm = bmesh.new()
        vs = [bm.verts.new(tuple(c)) for c in co]
        for f in faces:
            try:
                bm.faces.new([vs[i] for i in f])
            except ValueError:
                pass
        self.cols.append(Collider(bm, outer))
        self.items.append((np.asarray(co), faces))

    def surface_z(self, x, y, r=0.04):
        """(x, y) 附近摆好的东西的最高点（放书、怀表用）。"""
        best = self.top
        for co, _ in self.items:
            d = np.hypot(co[:, 0] - x, co[:, 1] - y)
            m = d < r
            if m.any():
                best = max(best, float(co[m, 2].max()))
        return best

    # ------------------------------------------------------------------ 床垫
    def mattress(self, h=0.1, seed=1):
        """条纹床垫：顶面中间微微鼓起，一排排绗缝凹坑，上下两圈滚边。"""
        rng = random.Random(seed)
        x0, x1 = self.xin + 0.035, self.xw - 0.015
        y0, y1 = self.ya + 0.03, self.yf - 0.03
        half = ((x1 - x0) / 2, (y1 - y0) / 2, h / 2)
        center = (self.x((x0 + x1) / 2), (y0 + y1) / 2, self.z0 + h / 2)
        tufts = []
        nx, ny = 2, 8
        for i in range(nx):
            for j in range(ny):
                tufts.append(((i + 0.5) / nx * 2 * half[0] - half[0], (j + 0.5) / ny * 2 * half[1] - half[1]))
        sag = _noise2(rng, 4, 1.0, 3.0)
        hx, hy = half[0], half[1]

        def top(x, y):
            z = 0.012 * (1 - (x / hx) ** 4) * (1 - (y / hy) ** 4)       # 中间鼓
            z -= 0.006 * max(0.0, 1 - abs(y + hy * 0.2) / (hy * 0.6)) * (1 - (x / hx) ** 2)  # 睡塌了一块
            z += 0.002 * sag(x * 3, y * 3)
            for tx, ty in tufts:
                z -= 0.009 * math.exp(-((x - tx) ** 2 + (y - ty) ** 2) / (2 * 0.018 ** 2))
            return z
        co, faces, fuv = cushion(center, half, 0.022, 0.016, top, bottom=False)
        ob = cloth_object(f"Bed_Mattress_{self.tag}", self.K.coll, self.K.M["Mattress"], co, faces, fuv, subsurf=0)
        for zs in (1, -1):
            pc, pf, pu = piping(center, half, 0.022, z_sign=zs)
            cloth_object(f"Bed_MattressPiping_{self.tag}{zs}", self.K.coll, self.K.M["Mattress"], pc, pf, pu,
                         subsurf=0)
        self._add(co, faces)
        self.top = self.z0 + h + 0.008
        return ob

    # ------------------------------------------------------------------ 人形（只当碰撞体，不出模型）
    def body(self):
        """侧身蜷着睡的一个人（脸朝过道，膝盖往胸口收），头枕在枕头上。只用来把被子顶起来。"""
        z = self.top
        bm = bmesh.new()
        hd = V((self.x(0.87), self.yf - 0.2, z + 0.16))
        self.head = hd
        ellipsoid(bm, hd, V((0, 1, 0)), (0.08, 0.1), 0.11)
        ellipsoid(bm, V((self.x(0.88), self.yf - 0.36, z + 0.1)), V((0, 1, 0)), (0.07, 0.06), 0.08)   # 脖子、肩
        ellipsoid(bm, V((self.x(0.87), self.yf - 0.62, z + 0.15)), V((0, 1, 0)), (0.11, 0.17), 0.25)  # 上身
        hip = V((self.x(0.88), self.yf - 0.95, z + 0.14))
        ellipsoid(bm, hip, V((0, 1, 0)), (0.12, 0.15), 0.14)
        knee = V((self.x(0.72), self.yf - 0.8, z + 0.1))
        ellipsoid(bm, (hip + knee) / 2, knee - hip, (0.08, 0.08), (knee - hip).length / 2 + 0.06)       # 大腿
        foot = V((self.x(0.76), self.yf - 1.2, z + 0.07))
        ellipsoid(bm, (knee + foot) / 2, foot - knee, (0.06, 0.06), (foot - knee).length / 2 + 0.05)    # 小腿
        ellipsoid(bm, V((self.x(0.73), self.yf - 0.55, z + 0.12)), V((0, 1, -0.3)), (0.05, 0.05), 0.16)  # 搭在胸前的胳膊
        co, faces = _mesh_arrays(bm)
        bm.free()
        self._add(co, faces, outer=0.006)
        self.items.pop()  # 人不算「摆好的东西」

    # ------------------------------------------------------------------ 枕头
    def pillow(self, seed=1, dy=0.0, tilt=0.0, size=(0.4, 0.25), dent=True):
        """枕套里塞满棉花：上下两片布四边缝死，靠内压鼓起来，落在床垫上压扁一点；
        有人睡过的枕头中间压出一个头的印子。"""
        rng = random.Random(seed)
        lx, ly = size
        res = 0.012
        nu, nv = int(lx / res) + 1, int(ly / res) + 1
        cx = self.x((self.xin + self.xw) / 2 + rng.uniform(-0.02, 0.02))
        cy = self.yf - 0.19 + dy
        a = math.radians(tilt + rng.uniform(-6, 6))
        ca, sa = math.cos(a), math.sin(a)
        zc = self.top + 0.05
        co, top_idx, bot_idx = [], {}, {}
        for side, store in ((1, top_idx), (-1, bot_idx)):
            for j in range(nv):
                for i in range(nu):
                    u, v = i / (nu - 1), j / (nv - 1)
                    border = i in (0, nu - 1) or j in (0, nv - 1)
                    if side < 0 and border:
                        store[(i, j)] = top_idx[(i, j)]
                        continue
                    px, py = (u - 0.5) * lx, (v - 0.5) * ly
                    bump = 0.0 if border else math.sin(math.pi * u) ** 0.5 * math.sin(math.pi * v) ** 0.5
                    store[(i, j)] = len(co)
                    co.append((cx + px * ca - py * sa, cy + px * sa + py * ca, zc + side * 0.035 * bump))
        # 面角 UV：缝边上的顶点上下两片共用，UV 按面所在的那一片取（下面那片挪开 1 米，免得和上面完全一样）
        faces, fuv = [], []
        for side, store in ((1, top_idx), (-1, bot_idx)):
            for j in range(nv - 1):
                for i in range(nu - 1):
                    ij = [(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)]
                    if side < 0:
                        ij.reverse()
                    faces.append([store[k] for k in ij])
                    fuv.append([((a / (nu - 1) - 0.5) * lx + (0 if side > 0 else 1.0), (b / (nv - 1) - 0.5) * ly)
                                for a, b in ij])
        co = np.array(co)
        cols = list(self.cols)
        if dent:
            hb = bmesh.new()
            head = getattr(self, "head", None) or V((cx + rng.uniform(-0.03, 0.03), cy + 0.01, self.top + 0.16))
            ellipsoid(hb, head, V((0, 1, 0)), (0.075, 0.09), 0.1)
            cols.append(Animated(hb, 0.12, 30))
        out = simulate(f"pillow_{self.tag}", co, faces, cols, frames=45, mass=0.25, tension=10.0, bending=0.2,
                       pressure=45.0, shrink=0.02, quality=8, distance=0.002)
        ob = cloth_object(f"Bed_Pillow_{self.tag}", self.K.coll, self.K.M["Pillow"], out, faces, fuv,
                          subsurf=1, recalc=False)
        # 四边的缝边：沿上下两片缝在一起的那一圈扫一根细滚条
        ring = ([top_idx[(i, 0)] for i in range(nu)] + [top_idx[(nu - 1, j)] for j in range(1, nv)] +
                [top_idx[(i, nv - 1)] for i in range(nu - 2, -1, -1)] + [top_idx[(0, j)] for j in range(nv - 2, 0, -1)])
        pc, pf, pu = tube_mesh(out[ring], 0.0035, spacing=0.012)
        cloth_object(f"Bed_PillowSeam_{self.tag}", self.K.coll, self.K.M["Pillow"], pc, pf, pu, subsurf=0)
        self._add(out, faces, outer=0.003)
        return ob

    # ------------------------------------------------------------------ 床单
    def sheet(self, seed=1, crumple=0.012):
        """白床单：落下来盖住床垫，靠过道那边多出一截垂下去，掖在床垫和床板边之间；靠壳那边顶着衬板。"""
        rng = random.Random(seed)
        noise = _noise2(rng, 6, 5.0, 16.0)
        res = 0.02
        d0, d1 = self.xin + 0.035 - 0.07, self.xw - 0.005
        y0, y1 = self.ya + 0.035, self.yf - 0.035
        nu, nv = int((d1 - d0) / res) + 1, int((y1 - y0) / res) + 1
        z0 = self._zmax(d0, d1, y0, y1) + crumple + 0.02
        co, uv = [], []
        for j in range(nv):
            for i in range(nu):
                x, y = d0 + i * res, y0 + j * res
                co.append((self.x(x), y, z0 + crumple * noise(x, y)))
                uv.append((i * res, j * res))
        co = np.array(co)
        faces = grid(nu, nv)
        out = simulate(f"sheet_{self.tag}", co, faces, self.cols, frames=50, mass=0.2, tension=15.0, bending=0.1,
                       quality=6, distance=0.003)
        ob = cloth_object(f"Bed_Sheet_{self.tag}", self.K.coll, self.K.M["Sheet"], out, faces, np.array(uv),
                          thick=0.002, subsurf=0)
        self._add(out, faces, outer=0.002)
        self.top += 0.004
        return ob

    # ------------------------------------------------------------------ 毛巾
    def towel(self, y0, y1, seed=1, hang_out=0.26, hang_in=0.22):
        """搭在上铺护栏上的毛巾：一条平布落到护栏的卷边上，两边垂下去（里面那半截搭在被子上）。"""
        rng = random.Random(seed)
        noise = _noise2(rng, 5, 6.0, 18.0)
        res = 0.014
        xc = self.xin + 0.015
        d0, d1 = xc - hang_out, xc + hang_in
        nu, nv = int((d1 - d0) / res) + 1, int((y1 - y0) / res) + 1
        z0 = self._zmax(d0, d1, y0, y1, zcap=self.z0 + 0.6) + 0.03
        co, uv = [], []
        for j in range(nv):
            for i in range(nu):
                x, y = d0 + i * res, y0 + j * res
                co.append((self.x(x), y + 0.01 * noise(x * 2, y), z0 + 0.008 * noise(x, y)))
                uv.append((i * res, j * res))
        co = np.array(co)
        faces = grid(nu, nv)
        out = simulate(f"towel_{self.tag}", co, faces, self.cols, frames=70, mass=0.35, tension=15.0, bending=1.0,
                       quality=6, distance=0.003)
        ob = cloth_object(f"Bed_Towel_{self.tag}", self.K.coll, self.K.M["Towel"], out, faces, np.array(uv),
                          thick=0.005, subsurf=1)
        self._add(out, faces)
        return ob

    def _zmax(self, d0, d1, y0, y1, zcap=None):
        """d0..d1（离中线）、y0..y1 范围里所有碰撞体的最高点（布从这上面落下来）。"""
        lo, hi = sorted((self.x(d0), self.x(d1)))
        zcap = self.z0 + 0.5 if zcap is None else zcap
        zmax = self.top
        for c in self.cols:
            m = (c.co[:, 0] > lo) & (c.co[:, 0] < hi) & (c.co[:, 1] > y0) & (c.co[:, 1] < y1) & (c.co[:, 2] < zcap)
            if m.any():
                zmax = max(zmax, float(c.co[m, 2].max()))
        return zmax

    # ------------------------------------------------------------------ 被子
    def blanket(self, seed=1, over=0.25, y0=None, y1=None, fold=None, crumple=0.03, shrink=-0.02, frames=80,
                res=0.022, bunch=1.0):
        """军毯：一张平布从上面落下来，盖在床垫（和人、枕头）上。靠过道那边多出 over 米垂下去，
        靠壳那边顶着衬板拱起来；fold=(长度, 角度°) 是床头那一头掀开折回来的一截；
        bunch<1 时整条毯子沿长度方向挤成一堆（蹬到床尾的被子），y0..y1 是挤完以后占的范围。"""
        rng = random.Random(seed)
        noise = _noise2(rng, 7, 4.0, 14.0)
        d0, d1 = self.xin + 0.035 - over, self.xw - 0.005
        y0 = self.ya + 0.05 if y0 is None else y0
        y1 = self.yf - 0.05 if y1 is None else y1
        nu, nv = int((d1 - d0) / res) + 1, int((y1 - y0) / bunch / res) + 1
        lam = 0.13
        wave = lam / math.pi * math.sqrt(max(0.0, 1 / bunch - 1))   # 波浪的幅度：让布的长度对得上
        # 从所有碰撞体在这块布底下的最高点上方落下来
        z0 = self._zmax(d0, d1, y0, y1) + crumple + 0.025
        if fold:
            fl, fa = fold
            fa = math.radians(fa)
            p0 = np.array((0.0, y1 - y0 - fl))           # 折线上一点（布的局部坐标：横向、纵向）
            n = np.array((math.sin(fa), math.cos(fa)))   # 折线法向（朝床头）
        co, uv, uv2 = [], [], []
        for j in range(nv):
            for i in range(nu):
                du, dv = min(i, nu - 1 - i) * res, min(j, nv - 1 - j) * res
                uv2.append((du, j * res) if du < dv else (dv, i * res))
                p = np.array((i * res, j * res))
                lift = 0.0
                if fold:
                    sd = float((p - p0 - np.array(((d1 - d0) / 2, 0.0))) @ n)
                    if sd > 0:
                        p = p - 2 * sd * n
                        lift = 0.02
                x, y = d0 + p[0], y0 + p[1] * bunch
                zb = 0.0
                if bunch < 1:
                    ph = y / lam * math.tau + 2.5 * noise(x * 0.3, y * 0.3) + x * 6
                    zb = wave * (1 + math.sin(ph)) * (0.7 + 0.3 * noise(x, y + 3))
                co.append((self.x(x), y, z0 + lift + zb + crumple * noise(x, y)))
                uv.append((i * res, j * res))
        co = np.array(co)
        faces = grid(nu, nv)
        out = simulate(f"blanket_{self.tag}", co, faces, self.cols, frames=frames, mass=0.6, tension=20.0,
                       bending=0.6, shrink=shrink, self_collide=bool(fold) or bunch < 1, quality=6, distance=0.004)
        ob = cloth_object(f"Bed_Blanket_{self.tag}", self.K.coll, self.K.M["Blanket"], out, faces, np.array(uv),
                          thick=0.006, subsurf=1, uv2=np.array(uv2))
        self._add(out, faces)
        return ob

    # ------------------------------------------------------------------ 布帘
    def curtain(self, ztop, zbot, ya, yb, folds=10, seed=1):
        """挂在杆上的布帘：顶上一排环钉住，往下是一道道褶子（每道深浅不一，越往下越散开），
        被重力拉直，下摆搭在被子、床垫上。拉开的帘子堆在一头，褶子挤得很深。"""
        rng = random.Random(seed)
        span = yb - ya
        amp = min(0.045, 0.01 + 0.012 * folds * 0.07 / span)
        per = [rng.uniform(0.6, 1.35) for _ in range(folds + 2)]
        ph = [rng.uniform(0, 6.28) for _ in range(4)]
        nu = folds * 14 + 1
        nv = max(8, int((ztop - zbot) / 0.02) + 1)
        xr = self.xin - 0.005
        co, uv = [], []
        for j in range(nv):
            v = j / (nv - 1)
            for i in range(nu):
                u = i / (nu - 1)
                k = u * folds
                k0 = int(k)
                t = k - k0
                a = amp * (per[k0] * (1 - t) + per[k0 + 1] * t)    # 每道褶子深浅不一
                a *= 1 + 0.6 * v * (0.5 + 0.5 * math.sin(u * 7 + ph[1]))
                f = math.sin(u * folds * 2 * math.pi + ph[0])
                y = ya + span * u + 0.25 * a * math.cos(u * folds * 2 * math.pi + ph[0]) * v
                z = ztop - 0.02 - (ztop - 0.02 - zbot) * v
                x = xr + a * f + 0.012 * v * math.sin(u * 3 + ph[3])
                co.append((self.x(x), y, z))
                uv.append((span * u * 1.6, (ztop - z)))
        co = np.array(co)
        faces = grid(nu, nv)
        out = simulate(f"curtain_{self.tag}_{seed}", co, faces, self.cols, frames=50, pin=list(range(nu)),
                       mass=0.15, tension=12.0, bending=0.08, quality=6, distance=0.003)
        ob = cloth_object(f"Bed_Curtain_{self.tag}_{seed}", self.K.coll, self.K.M["Curtain"], out, faces,
                          np.array(uv), thick=0.0025, subsurf=0)
        self._add(out, faces)
        return ob

    # ------------------------------------------------------------------ 叠好的毯子
    def folded_blanket(self, y, layers=6, size=(0.4, 0.3), seed=1):
        """叠成方块的军毯：一条布来回折了几折，折边鼓成圆弧，有点歪、有点塌。"""
        rng = random.Random(seed)
        noise = _noise2(rng, 6, 6.0, 20.0)
        w, ln = size
        t = 0.0105                       # 每层的厚度（层与层贴着）
        # 截面路径（沿铺位方向 y, 高度 z）：一层往前、折过来一层往后……
        path = []
        for k in range(layers):
            zk = self.top + t * (k + 0.5)
            ys = [-ln / 2 + ln * q / 20 for q in range(21)]
            if k % 2:
                ys.reverse()
            path += [(yy, zk) for yy in ys[:-1]]
            if k < layers - 1:
                end = ys[-1]
                sgn = 1 if end > 0 else -1
                for q in range(7):
                    a = math.pi * q / 6
                    path.append((end + sgn * (t / 2) * math.sin(a) * 1.6, zk + t / 2 - (t / 2) * math.cos(a)))
        path.append((ys[-1], self.top + t * (layers - 0.5)))
        arc = [0.0]
        for i in range(1, len(path)):
            arc.append(arc[-1] + math.dist(path[i], path[i - 1]))
        nx = int(w / 0.015) + 1
        yaw = math.radians(rng.uniform(-5, 5))
        cx = (self.xin + self.xw) / 2
        co, uv, uv2 = [], [], []
        for j, (py, pz) in enumerate(path):
            for i in range(nx):
                px = -w / 2 + w * i / (nx - 1)
                e = abs(2 * px / w) ** 6                    # 两头的布边往下塌一点
                dz = 0.002 * noise(px, py) - 0.006 * e * (pz - self.top) / (t * layers)
                dy = 0.004 * math.sin(px * 9 + j * 0.3) * (abs(py) > ln / 2 - 0.002)
                lx, ly = px * math.cos(yaw) - (py + dy) * math.sin(yaw), px * math.sin(yaw) + (py + dy) * math.cos(yaw)
                co.append((self.x(cx + lx), y + ly, pz + dz))
                uv.append((px, arc[j]))
                e1, e2 = min(px + w / 2, w / 2 - px), min(arc[j], arc[-1] - arc[j])
                uv2.append((e1, arc[j]) if e1 < e2 else (e2, px))
        co = np.array(co)
        faces = grid(nx, len(path))
        ob = cloth_object(f"Bed_Folded_{self.tag}", self.K.coll, self.K.M["Blanket"], co, faces, np.array(uv),
                          thick=t * 0.9, subsurf=1, uv2=np.array(uv2))
        self._add(co, faces)
        return ob
