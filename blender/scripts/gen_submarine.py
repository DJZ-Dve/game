"""生成潜艇「镇海号」：外壳 + 舱内，导出两个 glb，并渲染预览图。

一艘退役的老式军用小潜艇，艇长约 14 米：
- 单壳体：耐压壳（内径 2.7 米，分控制舱、生活舱两段）本身就是外壳，艏部是半椭球，艉部收成长锥
- 艇身刷黑漆，水线以下是红色防污漆；背上一道上层建筑（甲板），两侧开着一排流水孔
- 中前部一座高围壳（指挥台）：围壳舵、潜望镜、通气管、天线（天线上还系着一条红布）
- 艉部十字尾舵（舵面能动）+ 七叶大侧斜螺旋桨（会转）
- 探照灯装在艏部的灯座里；舷窗是改装时在耐压壳上开的

用法：
  blender -b --factory-startup --python blender/scripts/gen_submarine.py -- [--no-export] [--preview DIR]
"""
import sys
import os
import math

sys.path.insert(0, os.path.dirname(__file__))
import bpy  # noqa: E402
import bmesh  # noqa: E402
from mathutils import Vector as V  # noqa: E402
from lib import *  # noqa: E402,F401,F403
import lib  # noqa: E402
import cockpit  # noqa: E402
from kit import rbox  # noqa: E402
from cockpit import R_IN, Y_BOW, Y_STERN, HATCH, vp_axis, anchor_frame  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FONT_SANS = r"C:\Windows\Fonts\NotoSansSC-VF.ttf"
FONT_SERIF = r"C:\Windows\Fonts\NotoSerifSC-VF.ttf"

R_OUT = R_IN + 0.06       # 耐压壳外径（壳厚 6 厘米）= 艇身半径
Y_TIP = 3.3               # 艏尖
Y_TAIL = Y_STERN - 0.2    # 平行中体到这里结束，往后收锥
Y_HUB = -10.3             # 艉锥末端（接螺旋桨毂）
R_HUB = 0.3
WL = 0.25                 # 水线高度（以上黑漆，以下红色防污漆）
SAIL = (0.05, -2.75, 3.3)    # 围壳：前缘 y、后缘 y、顶面高度
PROP_Y = -10.45           # 螺旋桨盘面
Y_HINGE = -9.38           # 尾舵转轴


# ============================================================================ 材质
def make_materials():
    m = {}
    m["HullBlack"] = material("M_HullBlack", (0.035, 0.037, 0.04), 0.15, 0.7)
    m["Antifoul"] = material("M_Antifoul", (0.3, 0.07, 0.05), 0.05, 0.8)
    m["DeckNonSkid"] = material("M_DeckNonSkid", (0.06, 0.06, 0.06), 0.1, 0.9)
    m["Frame"] = material("M_FrameSteel", (0.09, 0.09, 0.095), 0.6, 0.5)
    m["Bare"] = material("M_BareMetal", (0.55, 0.55, 0.56), 1.0, 0.35)
    m["Rubber"] = material("M_Rubber", (0.02, 0.02, 0.02), 0.0, 0.8)
    m["Dark"] = material("M_Dark", (0.01, 0.01, 0.01), 0.0, 0.9)
    m["Glass"] = material("M_Glass", (0.55, 0.7, 0.68), 0.0, 0.05, alpha=0.12)
    m["Lens"] = material("M_LampLens", (1.0, 0.95, 0.85), 0.0, 0.1, emission=(1, 0.95, 0.85), strength=2)
    m["Bronze"] = material("M_Bronze", (0.55, 0.38, 0.2), 1.0, 0.45)
    m["Cloth"] = material("M_ClothRed", (0.5, 0.02, 0.02), 0.0, 0.9)
    m["Text"] = material("M_PaintText", (0.85, 0.82, 0.72), 0.0, 0.6)
    return m


def fix_normals(bm, outward):
    """outward(face_center) 给出该处朝外的大致方向；按多数面的朝向把整个网格翻过来。"""
    bm.normal_update()
    score = sum(1 if f.normal.dot(outward(f.calc_center_median())) > 0 else -1 for f in bm.faces)
    if score < 0:
        bmesh.ops.reverse_faces(bm, faces=bm.faces[:])


# ============================================================================ 艇身
def hull_r(y):
    """艇身（耐压壳外表面）在 y 处的半径。"""
    if y >= Y_BOW:
        t = (y - Y_BOW) / (Y_TIP - Y_BOW)
        return R_OUT * math.sqrt(max(0.0, 1 - t * t))
    if y >= Y_TAIL:
        return R_OUT
    t = min(1.0, (Y_TAIL - y) / (Y_TAIL - Y_HUB))
    return R_HUB + (R_OUT - R_HUB) * (1 - t ** 1.8)


def hull_point(y, ang_deg, lift=0.0):
    """艇身表面上的点和朝外法线；ang 从正上方量起、朝右舷为正。lift：沿法线抬高。"""
    a = math.radians(ang_deg)
    r = hull_r(y)
    p = V((r * math.sin(a), y, r * math.cos(a)))
    # 法线 = 半径方向 - 半径对 y 的导数（往艏/艉收的地方法线往前/后倒）
    dy = 0.01
    dr = (hull_r(y + dy) - hull_r(y - dy)) / (2 * dy)
    n = V((math.sin(a), -dr, math.cos(a))).normalized()
    return p + n * lift, n


def hull_stations():
    ys = [Y_BOW + (Y_TIP - Y_BOW) * math.cos(math.radians(90 * k / 40)) for k in range(1, 40)]
    y = Y_BOW
    while y > Y_TAIL + 1e-6:
        ys.append(y)
        y -= 0.05 if -0.2 < y <= Y_BOW + 1e-6 else 0.15
    for k in range(41):
        ys.append(Y_TAIL - (Y_TAIL - Y_HUB) * k / 40)
    return ys


NT, NB = 96, 112   # 一圈里水线以上 / 以下的分段数（水线正好落在一条网格线上，分色才齐）


def ring_angles(r):
    aw = math.acos(WL / r) if r > WL + 1e-4 else math.radians(1.0)
    return ([-aw + 2 * aw * i / NT for i in range(NT)] +
            [aw + (2 * math.pi - 2 * aw) * i / NB for i in range(NB)])


def ext_hull(c, M):
    """艇身：水线以上（黑）、以下（红）分成两个对象；两舷舷窗处开孔。"""
    def keep(cn):
        for s in (-1, 1):
            o, d = vp_axis(s)
            v = cn - o
            along = v.dot(d)
            if along > 0.5 and (v - d * along).length < 0.2:
                return False
        return True

    stations = hull_stations()

    def geo(bm, top):
        rows = []
        for y in stations:
            r = hull_r(y)
            rows.append([bm.verts.new(V((r * math.sin(a), y, r * math.cos(a)))) for a in ring_angles(r)])
        n = NT + NB
        cols = range(NT) if top else range(NT, n)
        for j in range(len(rows) - 1):
            for i in cols:
                k = (i + 1) % n
                q = [rows[j][i], rows[j][k], rows[j + 1][k], rows[j + 1][i]]
                if keep(sum((v.co for v in q), V()) / 4):
                    bm.faces.new(q)
        tip = bm.verts.new(V((0, Y_TIP, 0)))
        end = bm.verts.new(V((0, Y_HUB, 0)))
        for i in cols:
            bm.faces.new([rows[0][i], rows[0][(i + 1) % n], tip])
            bm.faces.new([rows[-1][i], rows[-1][(i + 1) % n], end])
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context='VERTS')
        fix_normals(bm, lambda p: V((p.x, 0, p.z)) + V((0, max(0.0, p.y - Y_BOW) - max(0.0, Y_TAIL - p.y) * 0.3, 0)))
    build("Ext_HullTop", c, M["HullBlack"], lambda bm: geo(bm, True), recalc=False, sharp_angle=None)
    build("Ext_HullBottom", c, M["Antifoul"], lambda bm: geo(bm, False), recalc=False, sharp_angle=None)

    # 环焊缝（耐压壳分段对接处）
    def seams(bm):
        for y in (Y_BOW, 0.4, -0.8, -2.6, -4.4, Y_STERN):
            r = hull_r(y)
            lathe(bm, [(r - 0.002, -0.014), (r + 0.004, -0.007), (r + 0.005, 0.0), (r + 0.004, 0.007),
                       (r - 0.002, 0.014)], 160, T(0, y, 0) @ R(-90, 'X'))
    build("Ext_HullSeam", c, M["HullBlack"], seams, sharp_angle=None)

    # 龙骨：艇底一道扁钢，坐底时垫着
    def keel(bm):
        path = [V((0, y, -hull_r(y) - 0.04)) for y in [2.2 - 0.25 * k for k in range(41)] if y > -8.2]
        sweep(bm, path, rect_profile(0.1, 0.1, 0.01), up_hint=V((0, 0, 1)))
    build("Ext_Keel", c, M["Antifoul"], keel, bevel=(0.004, 2))

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

    # 吃水标志（艏、艉两舷，白漆数字 + 刻线，单位分米）
    for y, tag in ((2.45, "F"), (-7.9, "A")):
        r = hull_r(y)
        for s in (-1, 1):
            for v in range(2, 17, 2):
                z = -R_OUT + 0.1 * v
                if abs(z) > r * 0.92:
                    continue
                x = math.sqrt(r * r - z * z)
                n = V((s * x, 0, z)).normalized()
                p = V((s * x, y, z)) + n * 0.003
                text_mesh(str(v), f"Ext_Draft_{tag}{'R' if s > 0 else 'L'}{v}", c, M["Text"],
                          frame(p, n, V((0, 0, 1))) @ T(s * 0.06, 0, 0), size=0.07, extrude=0.002)

                def tick(bm, p=p, n=n):
                    box(bm, 0.06, 0.012, 0.004, frame(p, n, V((0, 0, 1))) @ T(-s * 0.02, -0.045, 0))
                build(f"Ext_DraftTick_{tag}{'R' if s > 0 else 'L'}{v}", c, M["Text"], tick)
    for s in (-1, 1):
        p, n = hull_point(1.95, s * 62, 0.004)
        text_mesh("ZH-01", f"Ext_Code_{'R' if s > 0 else 'L'}", c, M["Text"], frame(p, n, V((0, 0, 1))),
                  size=0.16, extrude=0.003)

    # 右舷艏部的锚穴
    def anchor_well(bm):
        p, n = hull_point(2.15, 100, -0.01)
        F = frame(p, n, V((0, 1, 0)))
        cylinder(bm, 0.16, 0.03, 32, F @ S(1, 1.3, 1))
    build("Ext_AnchorWell", c, M["Dark"], anchor_well)

    def anchor(bm):
        p, n = hull_point(2.15, 100, 0.0)
        F = frame(p, n, V((0, 1, 0)))
        box(bm, 0.05, 0.3, 0.05, F @ T(0, 0.02, 0.0))
        for sx in (-1, 1):
            box(bm, 0.05, 0.16, 0.06, F @ T(sx * 0.07, -0.12, 0.0) @ R(sx * 35, 'Z'))
        torus(bm, 0.04, 0.012, 16, 6, F @ T(0, 0.19, 0.0))
    build("Ext_Anchor", c, M["Frame"], anchor, bevel=(0.004, 1))


# ============================================================================ 上层建筑（甲板）
CASING_KEYS = [  # y, 甲板面离艇身顶部的高度, 甲板半宽（两头收进艇身里）
    (3.12, 0.0, 0.0), (2.75, 0.11, 0.2), (2.25, 0.19, 0.36), (1.5, 0.21, 0.45), (-6.3, 0.21, 0.45),
    (-7.3, 0.19, 0.4), (-8.2, 0.1, 0.22), (-8.8, 0.0, 0.0)]
CASING_ALPHA = 40.0   # 甲板侧板落到艇身上的位置（离正上方的角度）


def casing_at(y):
    ks = CASING_KEYS
    if y >= ks[0][0] or y <= ks[-1][0]:
        return 0.0, 0.0
    for (y0, h0, w0), (y1, h1, w1) in zip(ks, ks[1:]):
        if y1 <= y <= y0:
            t = (y0 - y) / (y0 - y1)
            t = t * t * (3 - 2 * t)
            return h0 + (h1 - h0) * t, w0 + (w1 - w0) * t
    return 0.0, 0.0


def casing_section(y):
    """一个横截面：左侧板（从艇身到甲板边）、甲板、右侧板。返回 (left, deck, right) 三段点列。"""
    r = hull_r(y)
    h, w = casing_at(y)
    zt = r + h
    al = math.radians(CASING_ALPHA) * min(1.0, w / 0.45)
    rr = min(0.05, w * 0.3)
    side = []
    B = V(((r - 0.012) * math.sin(al), y, (r - 0.012) * math.cos(al)))
    E = V((w, y, zt))
    for t in (0.0, 0.35, 0.7):
        side.append(B + (E - B) * t)
    d = (B - E).normalized() if (B - E).length > 1e-6 else V((0, 0, -1))
    E1 = E + d * rr
    E2 = E + V((-rr, 0, 0))
    side += [E1, (E1 + E2) / 2 + (E - (E1 + E2) / 2) * 0.6, E2]
    deck = [V((-(w - rr) + 2 * (w - rr) * k / 6, y, zt)) for k in range(7)]
    right = side[:-1] + [deck[-1]]
    left = [V((-p.x, p.y, p.z)) for p in right]
    return left, deck, list(reversed(right))


def deck_z(y):
    return hull_r(y) + casing_at(y)[0]


def ext_casing(c, M):
    ys = [3.12 - 0.04 * k for k in range(14)] + [2.6 - 0.1 * k for k in range(110)]
    ys = [y for y in ys if y > -8.8] + [-8.8]

    def sides(bm):
        for part in (0, 2):
            rows = [[bm.verts.new(p) for p in casing_section(y)[part]] for y in ys]
            lib._grid_faces(bm, rows, closed_u=False)
        fix_normals(bm, lambda p: V((p.x, 0, 0.3)))
    build("Ext_Casing", c, M["HullBlack"], sides, recalc=False, sharp_angle=50)

    def deck(bm):
        rows = [[bm.verts.new(p) for p in casing_section(y)[1]] for y in ys]
        lib._grid_faces(bm, rows, closed_u=False)
        fix_normals(bm, lambda p: V((0, 0, 1)))
    build("Ext_CasingDeck", c, M["DeckNonSkid"], deck, recalc=False, sharp_angle=50)

    # 流水孔：甲板两侧一排长方形的孔（上层建筑里面是透水的）
    def holes(bm):
        y = 2.05
        while y > -7.7:
            _, w = casing_at(y)
            if w > 0.3:
                L, _, Rr = casing_section(y)
                for B, E in ((L[0], L[3]), (Rr[-1], Rr[-4])):
                    p = B + (E - B) * 0.42
                    up = (E - B).normalized()
                    n = V((math.copysign(1, p.x), 0, 0))
                    n = (n - up * n.dot(up)).normalized()
                    rbox_slot(bm, frame(p + n * 0.002, n, up), 0.24, 0.065)
            y -= 0.34
    build("Ext_LimberHoles", c, M["Dark"], holes)

    # 甲板：横向接缝、系缆桩、安全索导轨
    def seams(bm):
        for k in range(-7, 3):
            y = k * 1.0 + 0.5
            _, w = casing_at(y)
            if w > 0.2 and not (SAIL[1] - 0.05 < y < SAIL[0] + 0.05):
                box(bm, 2 * w - 0.08, 0.01, 0.002, T(0, y, deck_z(y) + 0.0005))
    build("Ext_DeckSeams", c, M["Dark"], seams)

    def fittings(bm):
        for y in (2.0, -4.6, -6.7):
            z = deck_z(y)
            for sx in (-1, 1):
                box(bm, 0.12, 0.3, 0.02, T(sx * 0.32, y, z + 0.01))
                for sy in (-1, 1):
                    cylinder(bm, 0.045, 0.12, 20, T(sx * 0.32, y + sy * 0.08, z + 0.02))
                    cylinder(bm, 0.06, 0.02, 20, T(sx * 0.32, y + sy * 0.08, z + 0.14))
        for y0, y1 in ((2.4, 1.95), (1.15, SAIL[0] + 0.05), (SAIL[1] - 0.15, HATCH[1] + 0.5),
                       (HATCH[1] - 0.5, -7.8)):
            n = max(2, int((y0 - y1) / 0.2))
            path = [V((0, y0 + (y1 - y0) * k / n, deck_z(y0 + (y1 - y0) * k / n) + 0.012)) for k in range(n + 1)]
            sweep(bm, path, rect_profile(0.03, 0.024, 0.004), up_hint=V((0, 0, 1)))
    build("Ext_DeckFittings", c, M["Frame"], fittings, bevel=(0.003, 1), sharp_angle=40)

    # 甲板上的舱口：后面一个是生活舱的出入舱口（正对舱内的舱口），前面一个是封死的装载口
    def hatches(bm):
        for (hx, hy), rr, live in (((HATCH[0], HATCH[1]), 0.4, True), ((0.0, 1.55), 0.33, False)):
            z = deck_z(hy)
            cylinder(bm, rr, 0.12, 64, T(hx, hy, z - 0.04))
            lathe(bm, [(0.0, 0.1), (rr * 0.45, 0.098), (rr * 0.85, 0.09), (rr - 0.005, 0.08), (rr - 0.01, 0.07),
                       (0.0, 0.07)], 64, T(hx, hy, z))
            box(bm, 0.24, 0.14, 0.09, T(hx, hy - rr - 0.02, z + 0.06))
            for i in range(6 if live else 10):
                a = 2 * math.pi * (i + 0.5) / (6 if live else 10)
                box(bm, 0.06, 0.035, 0.05, T(hx + math.cos(a) * (rr + 0.01), hy + math.sin(a) * (rr + 0.01), z + 0.06)
                    @ R(math.degrees(a), 'Z'))
            if live:
                torus(bm, 0.1, 0.018, 32, 8, T(hx, hy, z + 0.12))
                for k in range(4):
                    a = math.radians(45 + 90 * k)
                    sweep(bm, [V((hx, hy, z + 0.1)), V((hx + math.cos(a) * 0.1, hy + math.sin(a) * 0.1, z + 0.12))],
                          circle_profile(0.01, 8))
    build("Ext_DeckHatches", c, M["HullBlack"], hatches, bevel=(0.004, 2), sharp_angle=40)


def rbox_slot(bm, F, w, h):
    """流水孔：深色的长圆孔片（贴在侧板上，看上去像开的孔）。"""
    pts = []
    rr = h / 2
    for cx, a0 in ((w / 2 - rr, -90), (-(w / 2 - rr), 90)):
        for k in range(7):
            a = math.radians(a0 + 180 * k / 6)
            pts.append((cx + math.cos(a) * rr, math.sin(a) * rr))
    sweep(bm, [F @ V((0, 0, -0.01)), F @ V((0, 0, 0.004))], [(x, y) for x, y in pts], caps=True,
          up_hint=F.to_3x3() @ V((0, 1, 0)))


# ============================================================================ 围壳（指挥台）
def naca(x):
    """NACA 00xx 厚度分布（相对厚度 1 时的半厚，x∈[0,1]）。"""
    x = min(max(x, 0.0), 1.0)
    return 5 * (0.2969 * math.sqrt(x) - 0.126 * x - 0.3516 * x * x + 0.2843 * x ** 3 - 0.1036 * x ** 4)


def sail_chord(z):
    le0, te0, top = SAIL
    zb = deck_z(-1.3) - 0.05
    f = (z - zb) / (top - zb)
    le = le0 - 0.22 * f       # 前缘往后倾
    te = te0 + 0.05 * f
    return le, te


SAIL_T = 0.27  # 围壳相对厚度
SCOPES = ((-1.05, 0.06, 0.55), (-1.35, 0.08, 0.8))  # 潜望镜：y、半径、升出高度
SNORKEL_Y = -1.8
WHIP_Y = -2.45


def sail_half(y, z):
    le, te = sail_chord(z)
    c = le - te
    return naca((le - y) / c) * SAIL_T * c


def ext_sail(c, M, anchors):
    le0, te0, top = SAIL
    zb = deck_z(-1.3) - 0.05
    NX = 28
    xs = [(1 - math.cos(math.pi * k / NX)) / 2 for k in range(NX + 1)]

    def section(z, shrink=0.0, scale=1.0):
        le, te = sail_chord(z)
        le -= shrink
        te += shrink
        cc = le - te
        stb = [V((naca(x) * SAIL_T * cc * scale, le - x * cc, z)) for x in xs]
        port = [V((-p.x, p.y, z)) for p in reversed(stb[1:-1])]
        return stb + port

    def geo(bm):
        zs = [zb + (top - 0.05 - zb) * k / 10 for k in range(11)]
        secs = [section(z) for z in zs]
        secs.append(section(top - 0.02, 0.025, 0.9))
        secs.append(section(top, 0.06, 0.75))
        rows = [[bm.verts.new(p) for p in s] for s in secs]
        lib._grid_faces(bm, rows)
        bm.faces.new(rows[-1])
        fix_normals(bm, lambda p: V((p.x, 0, max(0.0, p.z - top + 0.1))))
    build("Ext_Sail", c, M["HullBlack"], geo, recalc=False, sharp_angle=None)

    # 围壳顶上前部的露天指挥位（黑洞洞的开口）、侧面的小窗
    def well(bm):
        rbox(bm, 0.34, 0.5, 0.01, T(0, le0 - 0.55, top + 0.001), r=0.04, seg=3)
        for s in (-1, 1):
            for k, yy in enumerate((le0 - 0.42, le0 - 0.66)):
                x = sail_half(yy, top - 0.22)
                n = V((s, 0.12 * (1 if k == 0 else 0.4), 0)).normalized()
                box(bm, 0.15, 0.09, 0.012, frame(V((s * (x + 0.002), yy, top - 0.22)), n, V((0, 0, 1))))
    build("Ext_SailWindows", c, M["Dark"], well)

    # 围壳舵
    def planes(bm):
        z = top - 0.55
        le_root = sail_chord(z)[0] - 0.12
        for s in (-1, 1):
            fin_loft(bm, lambda t: (le_root - 0.06 * t, le_root - 0.62 + 0.05 * t), 0.11,
                     lambda t: 0.15 + 1.05 * t, lambda p: V((s * p.z, p.y, z + p.x)))
    build("Ext_SailPlanes", c, M["HullBlack"], planes, sharp_angle=None)

    # 侧面的踏步（左舷后部，从甲板一直到顶）
    def steps(bm):
        yy = te0 + 0.35
        z = zb + 0.3
        while z < top - 0.15:
            x = sail_half(yy, z)
            p0, p1 = V((-x, yy + 0.09, z)), V((-x, yy - 0.09, z))
            sweep(bm, [p0, p0 + V((-0.07, 0, 0)), p1 + V((-0.07, 0, 0)), p1], circle_profile(0.011, 8))
            z += 0.3
    build("Ext_SailSteps", c, M["Bare"], steps, sharp_angle=50)

    # 升降桅杆：潜望镜两根、通气管、雷达、鞭状天线
    def masts(bm):
        for yy, r, h in SCOPES:
            cylinder(bm, r + 0.03, 0.04, 24, T(0, yy, top))
            cylinder(bm, r, h, 24, T(0, yy, top))
            cylinder(bm, r * 0.8, 0.14, 24, T(0, yy, top + h))
            uvsphere(bm, r * 0.8, 16, 8, T(0, yy, top + h + 0.14) @ S(1, 1, 0.6))
        rbox(bm, 0.12, 0.22, 0.75, T(0, SNORKEL_Y, top + 0.375), r=0.03, seg=2)
        rbox(bm, 0.2, 0.34, 0.2, T(0, SNORKEL_Y - 0.02, top + 0.82), r=0.03, seg=2)
        cylinder(bm, 0.045, 0.45, 16, T(0, SNORKEL_Y - 0.4, top))
        box(bm, 0.5, 0.05, 0.04, T(0, SNORKEL_Y - 0.4, top + 0.46))
        cylinder(bm, 0.03, 0.04, 12, T(0, WHIP_Y, top))
        cylinder(bm, 0.012, 1.35, 8, T(0, WHIP_Y, top), r2=0.005)
    build("Ext_Masts", c, M["Frame"], masts, bevel=(0.004, 2), sharp_angle=40)

    def mast_glass(bm):
        for yy, r, h in SCOPES:
            box(bm, 0.05, 0.02, 0.05, T(0, yy + r * 0.8, top + h + 0.08))
        for k in range(5):
            box(bm, 0.21, 0.004, 0.012, T(0, SNORKEL_Y - 0.02 + 0.171, top + 0.76 + k * 0.03))
    build("Ext_MastGlass", c, M["Dark"], mast_glass)

    # 鞭状天线上系的红布条
    def ribbon(bm):
        x0 = 0.0
        base = top + 1.2
        w = WHIP_Y
        path = [V((x0, w, base)), V((x0, w - 0.1, base - 0.07)), V((x0 + 0.01, w - 0.2, base - 0.23)),
                V((x0 - 0.01, w - 0.27, base - 0.4)), V((x0, w - 0.35, base - 0.55))]
        sweep(bm, catmull(path, 10), rect_profile(0.004, 0.07))
    build("Ext_RedRibbon", c, M["Cloth"], ribbon)

    # 舷号：围壳两侧刷「镇海」
    for s in (-1, 1):
        z = top - 1.0
        le, te = sail_chord(z)
        yy = le - 0.4 * (le - te)
        x = sail_half(yy, z)
        ob = text_mesh("镇海", f"Ext_Name_{'R' if s > 0 else 'L'}", c, M["Text"],
                       frame(V((s * x, yy, z)), V((s, 0, 0)), V((0, 0, 1))), size=0.36,
                       extrude=0.004, font_path=FONT_SERIF)
        # 字是平的，围壳侧面是弯的：把每个顶点按所在位置贴回到围壳表面上
        for v in ob.data.vertices:
            v.co.x = s * (sail_half(v.co.y, v.co.z) + 0.003) + (v.co.x - s * x)


def fin_loft(bm, chord, t_ratio, span, place, n_span=8, flap=None):
    """翼面：沿展向放样的 NACA 剖面。局部坐标里展向 = +Z、弦向 = Y（前缘在 +Y）、厚度 = X。
    chord(t) -> (前缘 y, 后缘 y)，span(t) -> 展向位置，place(p) 把局部点变到艇体坐标。
    flap=(hinge_y, part)：只做转轴前（part='fixed'）或转轴后（part='flap'）的那一截。"""
    NX = 16
    rows = []
    for j in range(n_span + 1):
        t = j / n_span
        le, te = chord(t)
        cc = le - te
        x0, x1 = 0.0, 1.0
        if flap:
            xh = (le - flap[0]) / cc
            if flap[1] == "fixed":
                x1 = xh - 0.006 / cc
            else:
                x0 = xh + 0.004 / cc
        xs = [x0 + (x1 - x0) * (1 - math.cos(math.pi * k / NX)) / 2 for k in range(NX + 1)]

        def half(x):
            h = naca(x) * t_ratio * cc
            if flap and flap[1] == "flap":
                h *= min(1.0, math.sqrt(max(0.0, (x - x0) * cc / 0.05)) + 0.15)
            return max(h, 0.002)
        z = span(t)
        stb = [V((half(x), le - x * cc, z)) for x in xs]
        port = [V((-p.x, p.y, z)) for p in reversed(stb[1:-1])]
        rows.append([bm.verts.new(place(p)) for p in stb + port])
    lib._grid_faces(bm, rows)
    bm.faces.new(list(reversed(rows[0])))
    bm.faces.new(rows[-1])


# ============================================================================ 艉部：十字尾舵、螺旋桨
FIN_LE = (-8.35, -8.85)   # 翼根、翼尖的前缘 y
FIN_TE = -9.8
FIN_SPAN = (0.35, 1.75)   # 离轴线的距离：翼根（埋在艇身里）、翼尖


def ext_stern(c, M, anchors):
    fins = (("RudderU", 0, "HullBlack"), ("PlaneR", 90, "HullBlack"), ("RudderD", 180, "Antifoul"),
            ("PlaneL", 270, "HullBlack"))

    def chord(t):
        return FIN_LE[0] + (FIN_LE[1] - FIN_LE[0]) * t, FIN_TE + 0.08 * t

    def span(t):
        return FIN_SPAN[0] + (FIN_SPAN[1] - FIN_SPAN[0]) * t

    for name, ang, mat in fins:
        Mr = R(ang, 'Y')

        def fixed(bm, Mr=Mr):
            fin_loft(bm, chord, 0.12, span, lambda p: Mr @ p, flap=(Y_HINGE, "fixed"))
        build(f"Ext_Fin{name}", c, M[mat], fixed, sharp_angle=50)

        def flap(bm, Mr=Mr):
            fin_loft(bm, chord, 0.12, span, lambda p: Mr @ p, flap=(Y_HINGE, "flap"))
        build(f"Fin_{name}", c, M[mat], flap, sharp_angle=50)
    anchors.append(empty("Pivot_Stern", c, anchor_frame(V((0, Y_HINGE, 0)), V((0, 1, 0)))))

    # 螺旋桨：七片大侧斜桨叶 + 桨毂 + 导流帽（整个一起转，Godot 里绕 Prop_Axis 转）
    def prop(bm):
        lathe(bm, [(0.0, Y_HUB + 0.02), (R_HUB - 0.01, Y_HUB + 0.02), (R_HUB - 0.01, PROP_Y - 0.15),
                   (R_HUB * 0.85, PROP_Y - 0.3), (R_HUB * 0.5, PROP_Y - 0.48), (0.05, PROP_Y - 0.58),
                   (0.0, PROP_Y - 0.6)], 48, R(-90, 'X'))
        n_bl = 7
        for k in range(n_bl):
            blade(bm, 2 * math.pi * k / n_bl)
    build("Prop_Main", c, M["Bronze"], prop, sharp_angle=40)
    anchors.append(empty("Prop_Axis", c, anchor_frame(V((0, PROP_Y, 0)), V((0, -1, 0)))))

    # 艉轴和桨毂之间一圈轴封
    def seal(bm):
        torus(bm, R_HUB - 0.005, 0.015, 48, 8, T(0, Y_HUB + 0.01, 0) @ R(-90, 'X'))
    build("Ext_ShaftSeal", c, M["Frame"], seal)




def blade(bm, theta0):
    """一片大侧斜桨叶：沿半径放样，弦线绕轴扭（螺距角），叶梢往旋转反方向弯（侧斜）。"""
    r0, r1 = R_HUB - 0.03, 0.95
    pitch = 1.5
    NS, NX = 12, 10
    rows = []
    for j in range(NS + 1):
        t = j / NS
        rho = r0 + (r1 - r0) * t
        chord_len = 0.3 + 0.42 * math.sin(math.pi * min(1.0, t * 0.85 + 0.1)) * (1 - 0.75 * t ** 3)
        if j == NS:
            chord_len = 0.06
        skew = math.radians(38) * t ** 1.6
        beta = math.atan(pitch / (2 * math.pi * rho))
        thick = 0.045 * (1 - t) + 0.006
        ring = []
        pts = []
        for k in range(NX + 1):
            u = -0.5 + k / NX
            pts.append((u, 1))
        for k in range(NX - 1, 0, -1):
            u = -0.5 + k / NX
            pts.append((u, -1))
        for u, side in pts:
            ht = thick * 0.5 * math.sqrt(max(0.0, 1 - (2 * u) ** 2)) * side
            s_t = u * chord_len * math.cos(beta) - ht * math.sin(beta)   # 切向（弧长）
            s_a = u * chord_len * math.sin(beta) + ht * math.cos(beta)   # 轴向
            th = theta0 + skew + s_t / rho
            ring.append(bm.verts.new(V((rho * math.sin(th), PROP_Y + s_a, rho * math.cos(th)))))
        rows.append(ring)
    lib._grid_faces(bm, rows)
    bm.faces.new(rows[-1])


# ============================================================================ 探照灯
def floodlight(bm, M):
    """沿局部 Z 发光的探照灯（灯头在 z=0）。"""
    lathe(bm, [(0.0, -0.24), (0.06, -0.24), (0.07, -0.22), (0.075, -0.2), (0.085, -0.17),
               (0.085, -0.02), (0.095, -0.01), (0.095, 0.015), (0.08, 0.02)], 48, M, cap_start=True, cap_end=True)
    for k in range(5):
        torus(bm, 0.087, 0.008, 48, 8, M @ T(0, 0, -0.15 + k * 0.025))


def light_mounts():
    """名字 -> (灯头位置, 光照方向, 灯座在艇身上的位置, 艇身法线)。"""
    out = {}
    for s, side in ((-1, "L"), (1, "R")):
        for key, y, ang, d, lift in (("F", 2.45, 52, V((s * 0.12, 1, -0.3)), 0.1),
                                     ("B", 2.3, 132, V((s * 0.08, 1, -0.4)), 0.1),
                                     ("S", 0.55, 107, V((s * 1, 0.3, -0.35)), 0.12)):
            base, n = hull_point(y, s * ang)
            out[key + side] = (base + n * lift, d.normalized(), base, n)
    return out


def ext_lights(c, M, anchors):
    mounts = light_mounts()

    def geo(bm):
        for name, (p, d, base, n) in mounts.items():
            floodlight(bm, frame(p, d))
            # 灯座：从艇身上焊出来的一截短筒 + 托架，把灯抱住
            cylinder(bm, 0.11, 0.06, 32, frame(base - n * 0.02, n))
            pipe(bm, [base + n * 0.03, p - d * 0.12], 0.04, 16, 2)
            torus(bm, 0.1, 0.012, 32, 8, frame(p - d * 0.01, d))
            # 护栏：三根弯钢条罩在灯前面
            F = frame(p, d)
            for k in range(3):
                a = 2 * math.pi * k / 3 + math.pi / 6
                q0 = F @ V((math.cos(a) * 0.1, math.sin(a) * 0.1, -0.02))
                q1 = F @ V((math.cos(a) * 0.09, math.sin(a) * 0.09, 0.1))
                q2 = F @ V((0, 0, 0.13))
                pipe(bm, [q0, q1, q2], 0.008, 8, 4)
    build("Ext_Floodlights", c, M["Frame"], geo, sharp_angle=40)

    def lens(bm):
        for name, (p, d, base, n) in mounts.items():
            cylinder(bm, 0.078, 0.006, 32, frame(p, d) @ T(0, 0, 0.008))
    build("Lens_Floodlights", c, M["Lens"], lens, sharp_angle=60)

    for name, (p, d, base, n) in mounts.items():
        anchors.append(empty(f"Light_{name}", c, anchor_frame(p + d * 0.03, d)))


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

    ext_hull(ext, M)
    ext_casing(ext, M)
    ext_sail(ext, M, anchors_ext)
    ext_stern(ext, M, anchors_ext)
    ext_lights(ext, M, anchors_ext)

    cockpit.build_cockpit(cock, M, anchors_int)

    out_blend = os.path.join(ROOT, "blender", "source", "submarine.blend")
    bpy.ops.wm.save_as_mainfile(filepath=out_blend)
    print("saved", out_blend)

    if preview_dir:
        os.makedirs(preview_dir, exist_ok=True)
        cock_objs = list(cock.objects)
        for nm, pos, look, lens in (("ext_front", (8.5, 7.5, 3.2), (0, -3.2, 0.6), 30),
                                    ("ext_side", (-18.0, -3.6, 1.2), (0, -3.6, 0.6), 30),
                                    ("ext_back", (7.0, -18.0, 3.5), (0, -5.5, 0.6), 30),
                                    ("ext_stern", (3.2, -12.8, 1.2), (0, -9.4, 0.0), 30),
                                    ("ext_top", (5.0, -1.0, 7.5), (0, -2.5, 1.6), 30)):
            render_preview(os.path.join(preview_dir, nm + ".png"), pos, look, lens, hide=cock_objs)
        ext_hide = [o for o in ext.objects if o.name not in ("Viewport_Glass",)]
        stand = V((0, -1.4, -0.9 + 1.62))
        for nm, pos, look, lens in (
                ("int_helm", cockpit.EYE_SEATED, V((0, 1, -0.3)), 16),
                ("int_fwd", stand, V((0, 1, -0.15)), 14),
                ("int_aft", V((0, 0.9, 0.72)), V((0, -1, -0.12)), 14),
                ("int_door", V((0.15, -1.5, 0.72)), V((-0.1, -1, -0.1)), 16),
                ("int_quarters", V((0, -3.0, 0.62)), V((0, -1, -0.12)), 14),
                ("int_galley", V((-0.3, -3.9, 0.6)), V((0.8, 0.6, -0.35)), 14),
                ("int_back", V((0, -5.6, 0.62)), V((0, 1, -0.1)), 14),
                ("int_port", V((0.2, -0.6, 0.72)), V((-1, 0.15, -0.3)), 14),
                ("int_up", V((0, -0.8, 0.5)), V((0, 0.3, 1)), 14),
                ("int_vp", V((0.4, 1.0, 0.55)), V((1, 0, -0.35)), 18)):
            render_preview(os.path.join(preview_dir, nm + ".png"), pos, pos + look, lens, hide=ext_hide)

    if do_export:
        # 运行时要单独控制的对象（指针、指示灯、报警灯片、浮子、屏幕、门、舵面、螺旋桨……）不合并
        special = ("Needle_", "Screen_", "Lamp_", "Warn_", "Float_", "Sway_", "Incense", "Lens_",
                   "Viewport_Glass", "Door_", "Fin_", "Prop_")
        for coll, fname in ((ext, "submarine_exterior.glb"), (cock, "submarine_cockpit.glb")):
            objs = bake_for_export([o for o in coll.objects])
            if coll is cock:
                clamp_into_hull(objs)
            empties = [o for o in objs if o.type == 'EMPTY']
            meshes = [o for o in objs if o.type == 'MESH']
            keep = [o for o in meshes if o.name.startswith(special)]
            others = [o for o in meshes if not o.name.startswith(special)]
            # 透明的玻璃单独合成一个对象，免得和不透明的东西一起排序
            glass = [o for o in others if o.data.materials and o.data.materials[0].name.startswith("M_Glass")]
            rest = [o for o in others if o not in glass]
            # 门扇上刷的字是单独生成的对象：门扇、手轮的零件按（前缀, 材质）合并，每种材质一个
            keep = merge_by_prefix(keep, ("Door_Leaf_", "Door_Wheel_"))
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


def clamp_into_hull(objs):
    """舱内的柜子、灯罩都是方盒子，靠壳体那一侧的角会戳到圆形艇身的外面（从艇外看得见）：
    把伸出耐压壳内壁 4.5 厘米以外的顶点沿半径收回到壳体夹层里（从舱内看它们本来就藏在内壁后面）。
    舱口筒、舷窗座这些本来就要穿过壳体的不动。"""
    import numpy as np
    lim = R_IN + 0.045
    axes = [tuple(np.array(v, dtype=np.float64) for v in vp_axis(s)) for s in (-1, 1)]
    for ob in objs:
        if ob.type != 'MESH' or not len(ob.data.vertices):
            continue
        me = ob.data
        n = len(me.vertices)
        co = np.empty(n * 3, np.float32)
        me.vertices.foreach_get("co", co)
        mw = np.array(ob.matrix_world, dtype=np.float64)
        p = co.reshape(-1, 3) @ mw[:3, :3].T + mw[:3, 3]
        x, y, z = p[:, 0], p[:, 1], p[:, 2]
        free = (z > 0.9) & (np.hypot(x - HATCH[0], y - HATCH[1]) < 0.5)
        for o, d in axes:
            w = p - o
            along = w @ d
            free |= (along > 0.9) & (np.linalg.norm(w - np.outer(along, d), axis=1) < 0.34)
        # 圆柱段收到轴线方向，艏部半球收向球心
        c = np.zeros_like(p)
        c[:, 1] = np.where(y > Y_BOW, Y_BOW, y)
        r = np.linalg.norm(p - c, axis=1)
        fix = (r > lim) & ~free
        if not fix.any():
            continue
        p[fix] = c[fix] + (p[fix] - c[fix]) * (lim / r[fix])[:, None]
        inv = np.linalg.inv(mw)
        me.vertices.foreach_set("co", (p @ inv[:3, :3].T + inv[:3, 3]).astype(np.float32).ravel())
        me.update()


def merge_by_prefix(objs, prefixes):
    """名字以 prefix 开头的对象按 (prefix, 材质) 合并：门扇的漆面、钢件各成一个对象。"""
    out = [o for o in objs if not o.name.startswith(prefixes)]
    # 先分好组再合并（合并会删掉对象，之后就不能再读它们的名字了）
    groups = {}
    for o in objs:
        for pre in prefixes:
            if o.name.startswith(pre):
                key = o.data.materials[0].name if o.data.materials else "none"
                groups.setdefault((pre, key), []).append(o)
    for (pre, key), objs_ in sorted(groups.items()):
        out.append(join(objs_, f"{pre}{key.removeprefix('M_')}"))
    return out


main()
