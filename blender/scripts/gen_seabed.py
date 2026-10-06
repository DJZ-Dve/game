"""生成海底地形：起伏的泥沙海床 + 礁岩带 + 一侧陡降的海沟（归墟）。

用法：blender -b --factory-startup --python blender/scripts/gen_seabed.py -- [--preview DIR]
地形 240m × 240m，0.5m 网格（约 46 万三角面），原点在场景中心，+Y 方向是海沟。
"""
import sys
import os
import math

sys.path.insert(0, os.path.dirname(__file__))
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import noise, Vector as V  # noqa: E402
from lib import *  # noqa: E402,F401,F403

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SIZE = 240.0
RES = 480


def height(x, y):
    p = V((x, y, 0.0))
    # 大尺度起伏
    h = noise.fractal(p * 0.012 + V((3.1, 7.7, 0)), 1.0, 2.0, 5, noise_basis='PERLIN_NEW') * 4.0
    # 中尺度沙丘
    h += noise.fractal(p * 0.05 + V((11.0, 2.0, 0)), 1.0, 2.1, 4, noise_basis='PERLIN_NEW') * 0.9
    # 礁岩脊：用低频噪声做遮罩
    mask = max(0.0, noise.noise(p * 0.018 + V((40.0, 5.0, 0)), noise_basis='PERLIN_NEW') * 1.8 - 0.15)
    ridge = noise.ridged_multi_fractal(p * 0.04 + V((5.0, 9.0, 0)), 1.0, 2.0, 5, 1.0, 2.0,
                                       noise_basis='PERLIN_NEW')
    h += mask * ridge * 2.6
    # 海沟：y > 55 之后陡降，边缘用噪声扰动
    edge = 55.0 + noise.noise(V((x * 0.03, 0.5, 0)), noise_basis='PERLIN_NEW') * 10.0
    t = (y - edge) / 22.0
    if t > 0:
        drop = min(t, 1.0)
        drop = drop * drop * (3 - 2 * drop)
        h -= drop * 85.0 + max(0.0, t - 1.0) * 30.0
        h += noise.fractal(p * 0.08, 1.0, 2.0, 3, noise_basis='PERLIN_NEW') * 2.0 * drop
    # 出生点附近压平一点
    d = math.hypot(x, y + 10.0)
    if d < 25:
        k = 1 - d / 25
        h = h * (1 - 0.6 * k * k)
    return h


def place(c, asset, idx, x, y, z_off=0.0, rot=(0.0, 0.0, 0.0), scale=1.0):
    """放置点：Godot 里按名字实例化对应素材（Place__素材名__编号）。"""
    from mathutils import Euler, Matrix
    z = height(x, y) + z_off
    m = Matrix.Translation((x, y, z)) @ Euler([math.radians(a) for a in rot], 'XYZ').to_matrix().to_4x4() \
        @ Matrix.Diagonal((scale, scale, scale, 1.0))
    e = bpy.data.objects.new(f"Place__{asset}__{idx:03d}", None)
    e.matrix_world = m
    c.objects.link(e)
    return e


def scatter(c):
    import random
    rnd = random.Random(1852)
    out = []
    ship = (6.0, 26.0)
    spawn = (0.0, -12.0)

    def free(x, y, r):
        if math.hypot(x - spawn[0], y - spawn[1]) < 12 + r:
            return False
        if abs(x - ship[0]) < 8 + r and abs(y - ship[1]) < 16 + r:
            return False
        return y < 62

    # 沉船（先用 Poly Haven 的帆船占位，之后换成中式帆船）
    out.append(place(c, "dutch_ship_medium", 0, *ship, z_off=-2.2, rot=(0, 22, 35)))
    # 打捞物
    for i, (asset, x, y, s) in enumerate((("treasure_chest", -2.5, 20.0, 1.0), ("antique_ceramic_vase_01", 12.0, 19.5, 1.0),
                                          ("antique_ceramic_vase_01", 2.5, 35.0, 1.0), ("ceramic_pot", 14.0, 31.0, 1.0),
                                          ("brass_vase_03", 8.5, 17.5, 1.4))):
        out.append(place(c, asset, i, x, y, z_off=-0.12 * s, rot=(rnd.uniform(-25, 25), rnd.uniform(-60, 60),
                                                                   rnd.uniform(0, 360)), scale=s))
    # 沉木
    for i in range(5):
        x, y = rnd.uniform(-25, 30), rnd.uniform(8, 45)
        if free(x, y, 2):
            out.append(place(c, "tree_stump_02", i, x, y, z_off=-0.3, rot=(rnd.uniform(-70, 70), 0, rnd.uniform(0, 360)),
                             scale=rnd.uniform(0.8, 1.6)))
    # 海沟边缘的悬崖岩体
    for i, x in enumerate((-58.0, 2.0, 62.0)):
        out.append(place(c, "coastal_cliff_04", i, x, 54.0, z_off=-5.5, rot=(0, 0, rnd.uniform(-12, 12)),
                         scale=rnd.uniform(0.55, 0.7)))
    # 大礁石
    n = 0
    while n < 16:
        x, y = rnd.uniform(-100, 100), rnd.uniform(-100, 58)
        if free(x, y, 4):
            out.append(place(c, "namaqualand_boulder_02", n, x, y, z_off=-0.35, rot=(0, 0, rnd.uniform(0, 360)),
                             scale=rnd.uniform(1.2, 3.0)))
            n += 1
    # 玄武岩群：成簇分布
    rocks = ("moon_rock_01", "moon_rock_03", "moon_rock_05")
    n = 0
    for _ in range(16):
        cx, cy = rnd.uniform(-95, 95), rnd.uniform(-95, 56)
        for _ in range(rnd.randint(5, 13)):
            x, y = cx + rnd.gauss(0, 6), cy + rnd.gauss(0, 6)
            s = rnd.uniform(8, 42)
            if free(x, y, s * 0.08):
                out.append(place(c, rnd.choice(rocks), n, x, y, z_off=-s * 0.02,
                                 rot=(rnd.uniform(-15, 15), rnd.uniform(-15, 15), rnd.uniform(0, 360)), scale=s))
                n += 1
    for _ in range(40):
        x, y = rnd.uniform(-110, 110), rnd.uniform(-110, 58)
        s = rnd.uniform(4, 16)
        if free(x, y, 1):
            out.append(place(c, rnd.choice(rocks), n, x, y, z_off=-s * 0.015,
                             rot=(rnd.uniform(-20, 20), rnd.uniform(-20, 20), rnd.uniform(0, 360)), scale=s))
            n += 1
    # 潜艇出生点：在海床上方 7 米，朝 +Y（沉船方向）
    e = bpy.data.objects.new("Spawn", None)
    from mathutils import Matrix
    e.matrix_world = Matrix.Translation((spawn[0], spawn[1], height(*spawn) + 4.5))
    c.objects.link(e)
    out.append(e)
    print("placements:", len(out))
    return out


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    preview_dir = argv[argv.index("--preview") + 1] if "--preview" in argv else None
    reset_scene()
    c = collection("Seabed")
    mat = material("M_Seabed", (0.32, 0.29, 0.24), 0.0, 0.95)

    n = RES + 1
    xs = np.linspace(-SIZE / 2, SIZE / 2, n)
    verts = []
    for j in range(n):
        y = xs[j]
        for i in range(n):
            x = xs[i]
            verts.append((x, y, height(x, y)))
    faces = []
    for j in range(RES):
        for i in range(RES):
            a = j * n + i
            faces.append((a, a + 1, a + n + 1, a + n))
    me = bpy.data.meshes.new("Seabed")
    me.from_pydata(verts, [], faces)
    me.materials.append(mat)
    me.shade_smooth()
    ob = bpy.data.objects.new("Seabed", me)
    c.objects.link(ob)

    placements = scatter(c)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(ROOT, "blender", "source", "seabed.blend"))

    if preview_dir:
        os.makedirs(preview_dir, exist_ok=True)
        render_preview(os.path.join(preview_dir, "seabed.png"), (-90, -120, 60), (0, 20, -10), 30)

    objs = bake_for_export([ob])
    # -col 后缀：Godot 导入时自动生成三角网格碰撞体
    objs[0].name = "Seabed-col"
    path = os.path.join(ROOT, "assets", "models", "seabed.glb")
    export_glb(path, objs + placements)
    print(f"exported seabed.glb: {stats(objs):,} tris, {os.path.getsize(path) / 1e6:.1f} MB")


main()
