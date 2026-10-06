"""生成潜艇「镇海号」：外壳 + 舱内，导出两个 glb，并渲染预览图。

艇长约 10 米。耐压壳是一段横躺的圆筒（内径 2.7 米，人能站直走动）+ 艏部半球，
艏部和两舷舷窗那一段露在外面（深灰漆），其余包在红白两色的玻璃钢整流罩里。

用法：
  blender -b --factory-startup --python blender/scripts/gen_submarine.py -- [--no-export] [--preview DIR]
"""
import sys
import os
import math
import random

sys.path.insert(0, os.path.dirname(__file__))
import bpy  # noqa: E402
import bmesh  # noqa: E402
from mathutils import Vector as V, Matrix  # noqa: E402
from lib import *  # noqa: E402,F401,F403
import lib  # noqa: E402
import cockpit  # noqa: E402
from cockpit import R_IN, Y_BOW, HATCH, vp_axis, anchor_frame  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FONT_SANS = r"C:\Windows\Fonts\NotoSansSC-VF.ttf"
FONT_SERIF = r"C:\Windows\Fonts\NotoSerifSC-VF.ttf"

R_OUT = R_IN + 0.06       # 耐压壳外径（壳厚 6 厘米）
Y_FAIR = 0.35             # 整流罩前沿：再往前是裸露的耐压壳
SAIL_Y = HATCH[1]

random.seed(7)


# ============================================================================ 材质
def make_materials():
    m = {}
    m["HullRed"] = material("M_HullRed", (0.42, 0.06, 0.035), 0.1, 0.55)
    m["HullWhite"] = material("M_HullWhite", (0.68, 0.66, 0.6), 0.1, 0.55)
    m["Sphere"] = material("M_SpherePaint", (0.16, 0.17, 0.17), 0.3, 0.5)
    m["Frame"] = material("M_FrameSteel", (0.09, 0.09, 0.095), 0.6, 0.5)
    m["Bare"] = material("M_BareMetal", (0.55, 0.55, 0.56), 1.0, 0.35)
    m["Rubber"] = material("M_Rubber", (0.02, 0.02, 0.02), 0.0, 0.8)
    m["Glass"] = material("M_Glass", (0.55, 0.7, 0.68), 0.0, 0.05, alpha=0.12)
    m["Lens"] = material("M_LampLens", (1.0, 0.95, 0.85), 0.0, 0.1, emission=(1, 0.95, 0.85), strength=2)
    m["Iron"] = material("M_Iron", (0.2, 0.12, 0.08), 0.6, 0.85)
    m["Brass"] = material("M_Brass", (0.72, 0.52, 0.22), 1.0, 0.35)
    m["Cloth"] = material("M_ClothRed", (0.5, 0.02, 0.02), 0.0, 0.9)
    m["Text"] = material("M_PaintText", (0.85, 0.82, 0.72), 0.0, 0.6)
    return m


# ============================================================================ 外壳
def ext_pressure_hull(c, M):
    """露在整流罩前面的耐压壳：一段圆筒 + 艏部半球，两舷舷窗处开孔。"""
    NU = 160

    def keep(cn):
        for s in (-1, 1):
            o, d = vp_axis(s)
            v = cn - o
            along = v.dot(d)
            if along > 0.5 and (v - d * along).length < 0.2:
                return False
        return True

    def geo(bm):
        stations = [(Y_FAIR - 0.1 + (Y_BOW - Y_FAIR + 0.1) * j / 30, R_OUT) for j in range(31)]
        for k in range(1, 40):
            th = math.radians(90 * k / 40)
            stations.append((Y_BOW + R_OUT * math.sin(th), R_OUT * math.cos(th)))
        rows = [[bm.verts.new(V((r * math.sin(2 * math.pi * i / NU), y, r * math.cos(2 * math.pi * i / NU))))
                 for i in range(NU)] for y, r in stations]
        for j in range(len(rows) - 1):
            for i in range(NU):
                k = (i + 1) % NU
                q = [rows[j][i], rows[j][k], rows[j + 1][k], rows[j + 1][i]]
                if keep(sum((v.co for v in q), V()) / 4):
                    bm.faces.new(q)
        tip = bm.verts.new(V((0, Y_BOW + R_OUT, 0)))
        for i in range(NU):
            bm.faces.new([rows[-1][i], rows[-1][(i + 1) % NU], tip])
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context='VERTS')
        bm.normal_update()
        bm.faces.ensure_lookup_table()
        f = bm.faces[len(bm.faces) // 3]
        cc = f.calc_center_median()
        if f.normal.dot(cc - V((0, min(cc.y, Y_BOW), 0))) < 0:
            bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
    build("Ext_PressureHull", c, M["Sphere"], geo, recalc=False, sharp_angle=None)

    # 筒体和半球之间的环焊缝、一圈加强箍
    def seams(bm):
        lathe(bm, [(R_OUT - 0.002, -0.015), (R_OUT + 0.004, -0.008), (R_OUT + 0.005, 0.0),
                   (R_OUT + 0.004, 0.008), (R_OUT - 0.002, 0.015)], 160, T(0, Y_BOW, 0) @ R(-90, 'X'))
    build("Ext_HullSeam", c, M["Sphere"], seams, sharp_angle=None)

    # 舷窗外侧的压环 + 螺栓 + 窗玻璃（从舱内看到的就是玻璃的内表面）
    def rings(bm):
        for s in (-1, 1):
            o, d = vp_axis(s)
            F = frame(o, d)
            prof = [(0.17, 1.4), (0.3, 1.4), (0.315, 1.44), (0.295, 1.49), (0.24, 1.505), (0.19, 1.505),
                    (0.17, 1.48), (0.17, 1.4)]
            lathe(bm, prof, 96, F)
            for i in range(16):
                a = 2 * math.pi * (i + 0.5) / 16
                cylinder(bm, 0.012, 0.016, 6, F @ T(math.cos(a) * 0.265, math.sin(a) * 0.265, 1.488))
    build("Ext_ViewportRing", c, M["Bare"], rings, bevel=(0.0015, 2))

    def glass(bm):
        for s in (-1, 1):
            o, d = vp_axis(s)
            cylinder(bm, 0.162, 0.038, 64, frame(o, d) @ T(0, 0, 1.462), r2=0.19)
    build("Viewport_Glass", c, M["Glass"], glass, sharp_angle=60)


def superellipse(hw, zc, hh, y, n=2.6, segs=72):
    pts = []
    for i in range(segs):
        a = 2 * math.pi * i / segs
        ca, sa = math.cos(a), math.sin(a)
        x = hw * math.copysign(abs(ca) ** (2 / n), ca)
        z = zc + hh * math.copysign(abs(sa) ** (2 / n), sa)
        pts.append(V((x, y, z)))
    return pts


FAIRING_KEYS = [  # y, 半宽, 顶, 底（要把外径 1.41 的耐压壳和后舱都包住）
    (Y_FAIR, 1.5, 1.5, -1.5), (0.0, 1.57, 1.58, -1.53), (-1.0, 1.61, 1.63, -1.56),
    (-2.6, 1.61, 1.63, -1.56), (-3.9, 1.52, 1.5, -1.46), (-5.0, 1.3, 1.22, -1.21),
    (-5.9, 0.98, 0.86, -0.87), (-6.6, 0.66, 0.55, -0.56), (-7.0, 0.48, 0.4, -0.41), (-7.2, 0.4, 0.33, -0.34),
]


def fairing_stations(samples=6):
    return lib.catmull([V(k) for k in FAIRING_KEYS], samples)


def fairing_at(y):
    st = fairing_stations(8)
    return min(st, key=lambda s: abs(s[0] - y))


def ext_fairing(c, M):
    stations = fairing_stations(6)

    def geo(bm):
        rings = []
        for y, hw, top, bot in stations:
            rings.append([bm.verts.new(p) for p in superellipse(hw, (top + bot) / 2, (top - bot) / 2, y)])
        lib._grid_faces(bm, rings)
    ob = build("Ext_Fairing", c, M["HullRed"], geo, sharp_angle=None)
    ob.data.materials.append(M["HullWhite"])
    # 按环上的角度分色（上红下白），分界线沿艇身平顺
    idx = []
    for p in ob.data.polygons:
        i = p.index % 72
        a = 2 * math.pi * (i + 0.5) / 72
        idx.append(0 if math.sin(a) > 0.1 else 1)
    ob.data.polygons.foreach_set("material_index", idx)
    add_solidify(ob, 0.04)
    add_subsurf(ob, 1)

    # 前隔板：外沿贴合整流罩，内圈套住耐压壳
    def bulk(bm):
        y, hw, top, bot = stations[0]
        outer = superellipse(hw, (top + bot) / 2, (top - bot) / 2, y)
        inner = []
        for i in range(len(outer)):
            a = 2 * math.pi * i / len(outer)
            inner.append(V((math.cos(a) * (R_OUT - 0.01), y, math.sin(a) * (R_OUT - 0.01))))
        lib._grid_faces(bm, [[bm.verts.new(p) for p in outer], [bm.verts.new(p) for p in inner]])
    ob = build("Ext_Bulkhead", c, M["Sphere"], bulk, sharp_angle=None)
    add_solidify(ob, 0.05, offset=1.0)
    add_bevel(ob, 0.008, 2)

    # 侧面护舷条 + 螺栓
    def strake(bm):
        for side in (-1, 1):
            path = []
            for s in fairing_stations(10):
                if -4.6 <= s[0] <= Y_FAIR:
                    path.append(V((side * (s[1] + 0.01), s[0], 0.05)))
            sweep(bm, path, rect_profile(0.06, 0.08, 0.012))
            for i, p in enumerate(path[::4]):
                cylinder(bm, 0.013, 0.014, 6, frame(p + V((side * 0.03, 0, 0.0)), V((side, 0, 0))))
    build("Ext_Strakes", c, M["Rubber"], strake, sharp_angle=40)


def ext_sail(c, M):
    """艇顶指挥台（正好罩在出入舱口上）：舱口、吊环、天线、频闪灯、前视声呐罩。"""
    zs = [1.45, 1.62, 1.85, 2.05, 2.15, 2.19]
    scale = [1.0, 1.0, 0.98, 0.94, 0.88, 0.8]
    sy = SAIL_Y

    def geo(bm):
        rings = []
        for z, s in zip(zs, scale):
            pts = []
            for i in range(64):
                a = 2 * math.pi * i / 64
                ca, sa = math.cos(a), math.sin(a)
                x = 0.5 * s * math.copysign(abs(ca) ** (2 / 2.4), ca)
                yy = sy + (0.95 if sa > 0 else 0.9) * s * math.copysign(abs(sa) ** (2 / 2.4), sa)
                pts.append(V((x, yy, z)))
            rings.append([bm.verts.new(p) for p in pts])
        lib._grid_faces(bm, rings)
        bm.faces.new(rings[-1])
    ob = build("Ext_Sail", c, M["HullRed"], geo, sharp_angle=None)
    add_subsurf(ob, 2)

    def hatch(bm):
        cylinder(bm, 0.36, 0.82, 64, T(0, sy, 1.42))
        lathe(bm, [(0.0, 2.27), (0.14, 2.265), (0.29, 2.25), (0.38, 2.23), (0.385, 2.21), (0.0, 2.21)], 64,
              T(0, sy, 0))
        box(bm, 0.2, 0.12, 0.09, T(0, sy - 0.42, 2.23))  # 铰链
        for i in range(6):
            a = 2 * math.pi * i / 6
            box(bm, 0.06, 0.035, 0.05, T(math.cos(a) * 0.38, sy + math.sin(a) * 0.38, 2.22) @ R(math.degrees(a), 'Z'))
    build("Ext_Hatch", c, M["Sphere"], hatch, bevel=(0.004, 2))

    def lifting(bm):
        torus(bm, 0.12, 0.028, 48, 12, T(0, sy - 0.98, 2.33) @ R(90, 'Y'))
        box(bm, 0.14, 0.34, 0.07, T(0, sy - 0.98, 2.2))
    build("Ext_LiftEye", c, M["Bare"], lifting, bevel=(0.004, 2))

    def mast(bm):
        cylinder(bm, 0.035, 0.06, 16, T(0.26, sy - 0.62, 2.16))
        cylinder(bm, 0.009, 1.1, 12, T(0.26, sy - 0.62, 2.2), r2=0.004)
        cylinder(bm, 0.05, 0.05, 24, T(-0.24, sy - 0.62, 2.16))
        uvsphere(bm, 0.045, 24, 12, T(-0.24, sy - 0.62, 2.23))
        uvsphere(bm, 0.15, 48, 24, T(0, sy + 0.68, 2.12) @ S(1, 1, 0.55))
        cylinder(bm, 0.155, 0.04, 48, T(0, sy + 0.68, 2.09))
    build("Ext_Mast", c, M["Frame"], mast, sharp_angle=40)

    def ribbon(bm):
        path = [V((0.26, sy - 0.62, 3.15)), V((0.26, sy - 0.72, 3.08)), V((0.27, sy - 0.82, 2.92)),
                V((0.25, sy - 0.89, 2.75)), V((0.26, sy - 0.97, 2.6))]
        sweep(bm, catmull(path, 10), rect_profile(0.004, 0.07))
    build("Ext_RedRibbon", c, M["Cloth"], ribbon)

    for side in (-1, 1):
        rot = frame(V((side * 0.505, sy, 1.85)), V((side, 0, 0)), V((0, 0, 1)))
        text_mesh("镇海", f"Ext_Name_{'R' if side > 0 else 'L'}", c, M["Text"], rot, size=0.26,
                  extrude=0.004, font_path=FONT_SERIF)
        y = -4.4
        text_mesh("ZH-01", f"Ext_Code_{'R' if side > 0 else 'L'}", c, M["Text"],
                  frame(V((side * (fairing_at(y)[1] + 0.012), y, 0.5)), V((side, 0, 0))),
                  size=0.2, extrude=0.004)


def floodlight(bm, M):
    """沿局部 Z 发光的探照灯（灯头在 z=0）。"""
    lathe(bm, [(0.0, -0.24), (0.06, -0.24), (0.07, -0.22), (0.075, -0.2), (0.085, -0.17),
               (0.085, -0.02), (0.095, -0.01), (0.095, 0.015), (0.08, 0.02)], 48, M, cap_start=True, cap_end=True)
    for k in range(5):
        torus(bm, 0.087, 0.008, 48, 8, M @ T(0, 0, -0.15 + k * 0.025))
    for sx in (-1, 1):
        box(bm, 0.015, 0.06, 0.16, M @ T(sx * 0.105, 0, -0.1))
        cylinder(bm, 0.02, 0.02, 16, M @ T(sx * 0.1, 0, -0.1) @ R(90, 'Y'))
    box(bm, 0.23, 0.06, 0.02, M @ T(0, -0.02, -0.18) @ R(90, 'X'))


LIGHTS = {  # 名字: (位置, 方向)
    "FL": (V((-1.12, 2.3, 0.8)), V((-0.12, 1, -0.35))),
    "FR": (V((1.12, 2.3, 0.8)), V((0.12, 1, -0.35))),
    "BL": (V((-1.15, 2.1, -0.82)), V((-0.08, 1, -0.4))),
    "BR": (V((1.15, 2.1, -0.82)), V((0.08, 1, -0.4))),
    # 舷窗斜下方的侧照灯：照亮从舷窗看出去的那片水和海底
    "SL": (V((-1.45, 0.55, -0.42)), V((-1, 0.3, -0.35))),
    "SR": (V((1.45, 0.55, -0.42)), V((1, 0.3, -0.35))),
}


def ext_lights(c, M, anchors):
    def geo(bm):
        for name, (p, d) in LIGHTS.items():
            floodlight(bm, frame(p, d))
        # 支臂：从整流罩前沿伸出来
        for sx in (-1, 1):
            for z0, z1 in ((0.95, 0.8), (-0.95, -0.82)):
                pipe(bm, [V((sx * 1.45, Y_FAIR + 0.05, z0)), V((sx * 1.4, 1.2, z0 * 0.95)),
                          V((sx * 1.25, 2.0, z1)), V((sx * 1.15, 2.15, z1))], 0.035)
            # 侧照灯的短支座焊在整流罩前隔板上
            pipe(bm, [V((sx * 1.47, Y_FAIR + 0.02, -0.5)), V((sx * 1.47, 0.42, -0.48)),
                      V((sx * 1.4, 0.5, -0.45))], 0.035)
    build("Ext_Floodlights", c, M["Frame"], geo, sharp_angle=40)

    def lens(bm):
        for name, (p, d) in LIGHTS.items():
            cylinder(bm, 0.078, 0.006, 32, frame(p, d) @ T(0, 0, 0.008))
    build("Lens_Floodlights", c, M["Lens"], lens, sharp_angle=60)

    for name, (p, d) in LIGHTS.items():
        anchors.append(empty(f"Light_{name}", c, anchor_frame(p + d.normalized() * 0.03, d)))


def ext_frame(c, M):
    """滑橇和下部框架。"""
    def geo(bm):
        for sx in (-1, 1):
            x = sx * 1.0
            pipe(bm, [V((x, 2.7, -1.0)), V((x, 2.45, -1.65)), V((x, 1.6, -1.88)), V((x, -4.6, -1.88)),
                      V((x, -5.6, -1.6))], 0.055)
            for y in (1.2, -0.6, -2.4, -4.2):
                pipe(bm, [V((x, y, -1.86)), V((sx * 0.9, y, -1.42))], 0.035)
            pipe(bm, [V((x, 2.7, -1.0)), V((sx * 1.2, 2.55, -0.8))], 0.04)
        pipe(bm, [V((-1.2, 1.0, -0.82)), V((-1.25, 1.9, -0.82)), V((-0.95, 2.65, -0.88)), V((0, 2.85, -0.9)),
                  V((0.95, 2.65, -0.88)), V((1.25, 1.9, -0.82)), V((1.2, 1.0, -0.82))], 0.045)
        for x in (-1.0, 1.0):
            pipe(bm, [V((x, -5.6, -1.6)), V((x * 0.6, -5.65, -1.0))], 0.035)
    build("Ext_Frame", c, M["Frame"], geo, sharp_angle=50)


def ext_basket(c, M):
    """艏部下方的采样篮。"""
    x0, x1, y0, y1, z0, z1 = -0.7, 0.4, 2.45, 3.15, -1.5, -1.17

    def tubes(bm):
        corners = [(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]
        for a in corners:
            for b in corners:
                diff = sum(1 for i in range(3) if abs(a[i] - b[i]) > 1e-6)
                if diff == 1 and a < b:
                    pipe(bm, [V(a), V(b)], 0.018, 12)
    build("Ext_BasketFrame", c, M["Frame"], tubes, sharp_angle=50)

    def bars(bm):
        n = 16
        for i in range(1, n):
            x = x0 + (x1 - x0) * i / n
            pipe(bm, [V((x, y0, z0)), V((x, y1, z0))], 0.005, 8)
            pipe(bm, [V((x, y1, z0)), V((x, y1, z1))], 0.005, 8)
            pipe(bm, [V((x, y0, z0)), V((x, y0, z1))], 0.005, 8)
        for j in range(1, 11):
            y = y0 + (y1 - y0) * j / 11
            pipe(bm, [V((x0, y, z0)), V((x1, y, z0))], 0.005, 8)
            for x in (x0, x1):
                pipe(bm, [V((x, y, z0)), V((x, y, z1))], 0.005, 8)
    build("Ext_BasketMesh", c, M["Bare"], bars, sharp_angle=60)


def ext_arm(c, M):
    """收起状态的机械臂（右前下方）。"""
    base = V((0.72, 2.0, -1.12))
    sh = base + V((0, 0.05, 0.18))
    el = sh + V((-0.02, 0.55, 0.12))
    wr = el + V((-0.12, 0.05, -0.4))

    def geo(bm):
        cylinder(bm, 0.11, 0.12, 32, T(*base))
        box(bm, 0.18, 0.18, 0.18, T(*(base + V((0, 0, 0.17)))))
        cylinder(bm, 0.075, 0.22, 32, T(*sh) @ T(-0.11, 0, 0) @ R(90, 'Y'))
        for a, b, w in ((sh, el, 0.09), (el, wr, 0.075)):
            d = b - a
            Mx = frame(a, d)
            box(bm, w, w, d.length, Mx @ T(0, 0, d.length / 2))
            off = V((0, 0, 0.075))
            cylinder(bm, 0.024, d.length * 0.55, 16, frame(a + off, d) @ T(0, 0, 0.05))
            cylinder(bm, 0.013, d.length * 0.45, 12, frame(a + off, d) @ T(0, 0, d.length * 0.5))
        cylinder(bm, 0.07, 0.17, 32, T(*el) @ T(-0.085, 0, 0) @ R(90, 'Y'))
        cylinder(bm, 0.055, 0.13, 24, frame(wr, V((0, 0.2, -1))))
        jaw = frame(wr + V((0, 0.02, -0.13)), V((0, 0.2, -1)))
        for s in (-1, 1):
            box(bm, 0.022, 0.065, 0.15, jaw @ T(s * 0.038, 0, 0.065) @ R(s * 12, 'Y'))
    build("Ext_Arm", c, M["Frame"], geo, bevel=(0.004, 2), sharp_angle=40)


def ext_thrusters(c, M):
    def thruster(bm, Mx, Rr=0.3, L=0.36, blades=5):
        prof = [(Rr, 0.0), (Rr, L), (Rr + 0.02, L), (Rr + 0.07, L * 0.55), (Rr + 0.065, L * 0.2),
                (Rr + 0.03, 0.0), (Rr, 0.0)]
        lathe(bm, prof, 72, Mx)
        lathe(bm, [(0.0, -0.06), (0.05, -0.04), (Rr * 0.28, 0.08), (Rr * 0.26, 0.24), (Rr * 0.12, 0.33),
                   (0.0, 0.34)], 32, Mx)
        for i in range(blades):
            a = 360 * i / blades
            for k in range(6):
                t = k / 6
                r = Rr * (0.3 + 0.62 * t)
                box(bm, Rr * 0.11, 0.012, 0.11 * (1 - 0.4 * t),
                    Mx @ T(0, 0, L * 0.45) @ R(a, 'Z') @ T(r, 0, 0) @ R(35 - 20 * t, 'X'))
        for i in range(4):
            a = 360 * i / 4 + 45
            box(bm, Rr * 0.75, 0.02, 0.06, Mx @ T(0, 0, L * 0.85) @ R(a, 'Z') @ T(Rr * 0.6, 0, 0))
        for k in range(1, 4):
            torus(bm, Rr * k / 4, 0.004, 48, 6, Mx @ T(0, 0, L + 0.01))
        for i in range(6):
            a = math.pi * i / 6
            p1 = Mx @ V((math.cos(a) * Rr, math.sin(a) * Rr, L + 0.01))
            p2 = Mx @ V((-math.cos(a) * Rr, -math.sin(a) * Rr, L + 0.01))
            pipe(bm, [p1, p2], 0.004, 6)

    def geo(bm):
        thruster(bm, frame(V((0, -7.2, 0)), V((0, -1, 0))), 0.38, 0.44, 5)
        for sx in (-1, 1):
            thruster(bm, frame(V((sx * 1.9, -4.5, 0.0)), V((0, -1, 0))), 0.2, 0.3, 4)
            box(bm, 0.36, 0.34, 0.06, T(sx * 1.6, -4.35, 0.0))
            thruster(bm, frame(V((sx * 1.3, -5.7, 0.35)), V((0, 0, -1))), 0.17, 0.26, 4)
            box(bm, 0.12, 0.28, 0.06, T(sx * 1.1, -5.7, 0.3))
    build("Ext_Thrusters", c, M["Frame"], geo, bevel=(0.002, 1, 40), sharp_angle=40)


def ext_ballast(c, M):
    """艇腹两侧的压载铁（应急时整块抛掉）。"""
    for sx, side in ((-1, "L"), (1, "R")):
        for i in range(5):
            def geo(bm, i=i, sx=sx):
                box(bm, 0.4, 1.3, 0.06, T(sx * 0.42, -1.6, -1.84 + i * 0.065))
            build(f"Ballast_{side}_{i}", c, M["Iron"], geo, bevel=(0.006, 2))

    def holder(bm):
        for sx in (-1, 1):
            for y in (-1.05, -2.15):
                box(bm, 0.48, 0.07, 0.045, T(sx * 0.42, y, -1.89))
                for s in (-1, 1):
                    box(bm, 0.035, 0.07, 0.42, T(sx * 0.42 + s * 0.23, y, -1.7))
            cylinder(bm, 0.035, 0.14, 16, T(sx * 0.42, -1.6, -1.55))
    build("Ext_BallastHolder", c, M["Frame"], holder, bevel=(0.004, 2))


# ============================================================================ 主流程
def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    preview_dir = None
    if "--preview" in argv:
        preview_dir = argv[argv.index("--preview") + 1]
    do_export = "--no-export" not in argv

    reset_scene()
    M = make_materials()
    ext = collection("Exterior")
    cock = collection("Cockpit")
    anchors_ext, anchors_int = [], []

    ext_pressure_hull(ext, M)
    ext_fairing(ext, M)
    ext_sail(ext, M)
    ext_lights(ext, M, anchors_ext)
    ext_frame(ext, M)
    ext_basket(ext, M)
    ext_arm(ext, M)
    ext_thrusters(ext, M)
    ext_ballast(ext, M)

    cockpit.build_cockpit(cock, M, anchors_int)

    out_blend = os.path.join(ROOT, "blender", "source", "submarine.blend")
    bpy.ops.wm.save_as_mainfile(filepath=out_blend)
    print("saved", out_blend)

    if preview_dir:
        os.makedirs(preview_dir, exist_ok=True)
        cock_objs = list(cock.objects)
        render_preview(os.path.join(preview_dir, "ext_front.png"), (6.5, 8.5, 2.8), (0, -1.8, 0), 35,
                       hide=cock_objs)
        render_preview(os.path.join(preview_dir, "ext_side.png"), (-13.0, -2.0, 1.2), (0, -2.0, 0), 35,
                       hide=cock_objs)
        render_preview(os.path.join(preview_dir, "ext_back.png"), (5.0, -14.0, 3.5), (0, -2.5, 0), 35,
                       hide=cock_objs)
        ext_hide = [o for o in ext.objects if o.name not in ("Viewport_Glass",)]
        stand = V((0, -1.4, -0.9 + 1.62))
        for nm, pos, look, lens in (
                ("int_helm", cockpit.EYE_SEATED, V((0, 1, -0.3)), 16),
                ("int_fwd", stand, V((0, 1, -0.15)), 14),
                ("int_aft", V((0, 0.9, 0.72)), V((0, -1, -0.12)), 14),
                ("int_port", V((0.2, -0.6, 0.72)), V((-1, 0.15, -0.3)), 14),
                ("int_stbd", V((-0.2, -0.6, 0.72)), V((1, 0.15, -0.3)), 14),
                ("int_up", V((0, -0.8, 0.5)), V((0, 0.3, 1)), 14),
                ("int_vp", V((0.4, 1.0, 0.55)), V((1, 0, -0.35)), 18)):
            render_preview(os.path.join(preview_dir, nm + ".png"), pos, pos + look, lens, hide=ext_hide)

    if do_export:
        # 运行时要单独控制的对象（指针、指示灯、报警灯片、浮子、屏幕……）不合并
        special = ("Needle_", "Screen_", "Lamp_", "Warn_", "Float_", "Sway_", "Incense", "Ballast_", "Lens_",
                   "Viewport_Glass")
        for coll, fname in ((ext, "submarine_exterior.glb"), (cock, "submarine_cockpit.glb")):
            objs = bake_for_export([o for o in coll.objects])
            empties = [o for o in objs if o.type == 'EMPTY']
            meshes = [o for o in objs if o.type == 'MESH']
            keep = [o for o in meshes if o.name.startswith(special)]
            # 透明的玻璃单独合成一个对象，免得和不透明的东西一起排序
            glass = [o for o in meshes if o not in keep and o.data.materials
                     and o.data.materials[0].name.startswith("M_Glass")]
            rest = [o for o in meshes if o not in keep and o not in glass]
            # 按材质合并：每个导出的网格只有一种材质。Blender 5.2 的 glTF 导出器在多材质网格上
            # 只给第一个材质的图元写顶点色（其余全是白色），曲率磨损就全乱了。
            groups = {}
            for o in rest:
                key = o.data.materials[0].name if o.data.materials else "none"
                groups.setdefault(key, []).append(o)
            bodies = [join(objs_, f"Body_{key.removeprefix('M_')}") for key, objs_ in sorted(groups.items())]
            gl = join(glass, "GaugeGlass") if glass else None
            final = bodies + keep + ([gl] if gl else []) + empties
            path = os.path.join(ROOT, "assets", "models", fname)
            export_glb(path, final)
            print(f"exported {fname}: {stats(final):,} tris, {os.path.getsize(path) / 1e6:.1f} MB")


main()
