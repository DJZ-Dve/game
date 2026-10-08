"""生活舱（耐压壳后段，中间隔壁的水密门后面）。

从门往后：
- 门后一小段是过道：右舷是小厨房（水槽、电炉、电饭锅、吊柜），左舷是两个衣柜；头顶是出入舱口，直梯立在过道中间
- 中段两舷各一组上下铺（四个铺位，带布帘、床头灯）
- 最后面：右舷储物架，左舷洗手池和镜子；后隔壁上是封死的机舱检修门（贴着封条和符）

坐标和 cockpit.py 一样：Blender +Y 朝艏，+Z 朝上，+X 朝右舷。
"""
import math
import random

from mathutils import Vector as V

from lib import (frame, T, R, S, cylinder, box, uvsphere, lathe, torus, catmull, circle_profile, rect_profile,
                 sweep, empty)
from kit import (rbox, screw, socket_screw, handle, vent, knob, lamp, label_plate, tape_label, toggle, FONT_BRUSH,
                 FONT_SERIF, FONT_HAND)
import cockpit as C
from bedding import Bunk
from cockpit import (R_IN, DECK, Y_AFT, Y_STERN, AFT_FRAMES, HATCH, PIPES, abox, sbox, anchor_frame, ring_sweep,
                     ceiling_lamp, decal)

Y_FWD = Y_AFT - 0.012           # 中间隔壁的后表面
GALLEY = (-2.78, -3.9)          # 小厨房 / 衣柜的前后范围（y1 > y0 的顺序：前、后）
BUNK = (-3.95, -5.85)           # 铺位的前后范围
FACE = 0.72                     # 厨房台面、衣柜门离中线
COUNTER_Z = -0.06               # 台面高度（离地 84 厘米）
BUNK_IN = 0.62                  # 铺位内沿（挡板、布帘）离中线
LINING_X = 1.11                 # 铺位靠壳体一侧的衬板
LOWER_Z, UPPER_Z = -0.52, 0.155  # 下铺、上铺床板上表面
MATTRESS = 0.1


def wall_x(z):
    """高度 z 处壳体内壁离中线的距离。"""
    return math.sqrt(max(0.0, R_IN ** 2 - z * z))


def build(K, anchors):
    deck(K)
    overhead(K, anchors)
    galley(K, anchors)
    lockers(K)
    for s in (-1, 1):
        bunks(K, anchors, s)
    aft_end(K, anchors)
    stern_bulkhead(K, anchors)
    decals(anchors, K.coll)


# ============================================================================ 地板、舱底
def deck(K):
    gx = 0.3
    ys = [Y_STERN] + list(reversed(AFT_FRAMES)) + [Y_FWD]
    for i in range(len(ys) - 1):
        y0, y1 = ys[i] + 0.003, ys[i + 1] - 0.003
        for s in (-1, 1):
            x0, x1 = s * (gx + 0.03), s * 1.0
            abox(K["Deck"], x0, x1, y0, y1, DECK - 0.012, DECK, r=0.002, seg=1)
            for xx in (x0 + s * 0.03, x1 - s * 0.05):
                for yy in (y0 + 0.03, y1 - 0.03):
                    cylinder(K["Steel"], 0.006, 0.0008, 12, T(xx, yy, DECK - 0.0004))
                    box(K["Dark"], 0.008, 0.0015, 0.0006, T(xx, yy, DECK + 0.0003))
    y0, y1 = Y_STERN + 0.1, Y_FWD - 0.12
    for s in (-1, 1):
        abox(K["Grating"], s * gx, s * (gx + 0.03), y0, y1, DECK - 0.05, DECK, r=0.002, seg=1)
    n = int((y1 - y0) / 0.032)
    for i in range(n + 1):
        y = y0 + (y1 - y0) * i / n
        box(K["Grating"], 2 * gx, 0.004, 0.03, T(0, y, DECK - 0.015))
    for k in range(1, 6):
        x = -gx + 2 * gx * k / 6
        box(K["Grating"], 0.006, y1 - y0, 0.006, T(x, (y0 + y1) / 2, DECK - 0.003))
    # 格栅两头没盖住的地方补两块地板
    for a, b in ((Y_STERN, y0), (y1, Y_FWD)):
        abox(K["Deck"], -gx, gx, a + 0.003, b - 0.003, DECK - 0.012, DECK, r=0.002, seg=1)
    # 舱底：槽底、一根管子、积水
    abox(K["HullInner"], -gx - 0.05, gx + 0.05, Y_STERN, Y_FWD, DECK - 0.36, DECK - 0.33)
    for s in (-1, 1):
        abox(K["HullInner"], s * (gx + 0.03), s * (gx + 0.05), Y_STERN, Y_FWD, DECK - 0.36, DECK - 0.05)
    sweep(K["PipeGray"], [V((-0.15, Y_STERN, DECK - 0.27)), V((-0.15, Y_FWD, DECK - 0.27))], circle_profile(0.05, 20))
    for y in (-3.2, -4.4, -5.6):
        cylinder(K["PipeGray"], 0.068, 0.022, 24, T(-0.15, y, DECK - 0.27) @ R(-90, 'X'))
    abox(K["Bilge"], -gx - 0.03, gx + 0.03, Y_STERN, Y_FWD, DECK - 0.335, DECK - 0.3)


# ============================================================================ 头顶：管路、桥架、灯
def overhead(K, anchors):
    """控制舱的管子、电缆桥架穿过中间隔壁接着往后走，到后隔壁穿出去（进机舱）。"""
    y0, y1 = Y_STERN, Y_FWD
    for x, z, r, key in PIPES:
        bm = K[key]
        sweep(bm, [V((x, y0, z)), V((x, y1, z))], circle_profile(r, 24 if r > 0.03 else 16))
        fbm = K["PipeGray"] if key == "Lagging" else bm
        # 穿舱处的法兰（两头）+ 中间一对
        for yf in (y1 - 0.03, -4.4, y0 + 0.03):
            for k in (-1, 1):
                cylinder(fbm, r + 0.022, 0.014, 32, T(x, yf + k * 0.007, z) @ R(-90, 'X') @ T(0, 0, -0.007))
            for i in range(6):
                a = 2 * math.pi * (i + 0.5) / 6
                cylinder(K["Steel"], 0.0055, 0.04, 6, T(x + math.cos(a) * (r + 0.013), yf - 0.02,
                                                          z + math.sin(a) * (r + 0.013)) @ R(-90, 'X'))
        if key == "Lagging":
            for yb in [y0 + 0.3 + k * 0.4 for k in range(10)]:
                if yb < y1 - 0.15 and abs(yb + 4.4) > 0.08:
                    cylinder(K["Steel"], r + 0.002, 0.016, 32, T(x, yb, z) @ R(-90, 'X'), caps=False)
        for yf in AFT_FRAMES:
            hang = 1.2 if math.hypot(x, yf - HATCH[1]) < 0.43 else math.sqrt(1.19 ** 2 - x * x)
            yh = yf + 0.035
            ring_r = r + 0.006
            arc = [V((x + math.cos(math.radians(a)) * ring_r, yh, z + math.sin(math.radians(a)) * ring_r))
                   for a in range(-180, 1, 15)]
            sweep(K["Steel"], arc, [(-0.002, -0.012), (0.002, -0.012), (0.002, 0.012), (-0.002, 0.012)],
                  up_hint=V((0, 1, 0)))
            for sx in (-1, 1):
                cylinder(K["Steel"], 0.005, hang - z, 8, T(x + sx * ring_r, yh, z))
            box(K["Steel"], 2 * ring_r + 0.03, 0.03, 0.006, T(x, yh, hang - 0.003))
    # 通风口
    x, z, r, _ = PIPES[0]
    for yv in (-4.65, -5.75):
        rbox(K["PipeGray"], 0.14, 0.12, 0.06, T(x, yv, z - r - 0.01), r=0.008, seg=2)
        vent(K, T(x, yv, z - r - 0.041) @ R(180, 'X'), 0, 0, 0.11, 0.09, 8, 0.006)

    # 电缆桥架
    for s in (-1, 1):
        a = math.radians(38 * s)
        rc = 1.13
        cx, cz = math.sin(a) * rc, math.cos(a) * rc
        tang = V((math.cos(a), 0, -math.sin(a)))
        nrm = V((math.sin(a), 0, math.cos(a)))
        for side in (-1, 1):
            c = V((cx, 0, cz)) + tang * side * 0.08
            sweep(K["Rail"], [V((c.x, y0, c.z)), V((c.x, y1, c.z))],
                  [(-0.025, -0.003), (0.025, -0.003), (0.025, 0.003), (-0.025, 0.003)], up_hint=tang)
        yy = y0 + 0.1
        while yy < y1 - 0.05:
            p = V((cx, yy, cz)) - nrm * 0.02
            box(K["Rail"], 0.16, 0.02, 0.006, frame(p, nrm, V((0, 1, 0))))
            yy += 0.25
        for yf in AFT_FRAMES:
            p = V((cx, yf + 0.03, cz))
            q = nrm * 1.19
            sweep(K["Steel"], [p, V((q.x, yf + 0.03, q.z))], circle_profile(0.005, 8))
        specs = [(0.009, "CableBlack"), (0.007, "CableGray"), (0.008, "CableBlack"), (0.005, "CableOrange"),
                 (0.006, "CableBlack"), (0.005, "CableYellow"), (0.007, "CableGray")]
        base = nrm * 1.145
        n = int((y1 - y0) / 0.3)
        C.Cab.bundle([V((base.x + 0.004 * math.sin(k), y0 + (y1 - y0) * k / n, base.z)) for k in range(n + 1)],
                     specs, tie_every=0.4)
    # 顶灯：门后一盏（舱口前面），铺位上方两盏
    for i, yl in enumerate((-2.78, -4.4, -5.6)):
        ceiling_lamp(K, anchors, T(0.0, yl, R_IN - 0.01) @ R(180, 'X'), f"CabinLight_Dome_{3 + i}")


# ============================================================================ 小厨房（右舷）
def galley(K, anchors):
    s = 1
    yf, ya = GALLEY
    zt = COUNTER_Z
    # 底柜：踢脚、柜体、两扇门
    sbox(K["Dark"], s, FACE + 0.06, 1.0, ya, yf, DECK, DECK + 0.08)
    sbox(K["EquipGray"], s, FACE + 0.02, 1.0, ya, yf, DECK + 0.08, zt - 0.04, r=0.006)
    zc = (DECK + 0.08 + zt - 0.04) / 2
    hz = (zt - 0.04) - (DECK + 0.08) - 0.03
    edges = [yf, -3.25, -3.55, ya]
    for i in range(3):
        a, b = edges[i + 1] + 0.008, edges[i] - 0.008
        rbox(K["EquipGray"], 0.018, a - b, hz, T(FACE + 0.01, (a + b) / 2, zc), r=0.004, seg=2)
        P = frame(V((FACE, (a + b) / 2, zc)), V((-1, 0, 0)))
        handle(K, P, ((b - a) / 2 + 0.03) * (1 if i % 2 else -1), 0.1, 0.08, key="Steel", standoff=0.018)
        for sx in (-1, 1):
            for sy in (-1, 1):
                screw(K, P, sx * ((b - a) / 2 - 0.015), sy * (hz / 2 - 0.015), r=0.003)
    # 不锈钢台面（水槽处开洞）+ 挡水沿 + 防滑栏杆
    sy0, sy1 = -3.22, -2.9   # 水槽
    sx0, sx1 = 0.8, 1.06
    top = K["Steel"]
    for a, b, x0, x1 in ((ya, sy0, FACE, 1.3), (sy1, yf, FACE, 1.3), (sy0, sy1, FACE, sx0), (sy0, sy1, sx1, 1.3)):
        abox(top, x0, x1, a, b, zt - 0.03, zt, r=0.003, seg=1)
    abox(top, FACE - 0.012, FACE + 0.002, ya, yf, zt - 0.045, zt + 0.004, r=0.002, seg=1)
    # 水槽：四壁、底、下水口、水龙头
    d = 0.15
    abox(top, sx0, sx1, sy0, sy1, zt - d - 0.004, zt - d)
    for x0, x1, y0_, y1_ in ((sx0, sx0 + 0.004, sy0, sy1), (sx1 - 0.004, sx1, sy0, sy1),
                             (sx0, sx1, sy0, sy0 + 0.004), (sx0, sx1, sy1 - 0.004, sy1)):
        abox(top, x0, x1, y0_, y1_, zt - d, zt - 0.002)
    cylinder(K["Dark"], 0.022, 0.001, 20, T((sx0 + sx1) / 2, (sy0 + sy1) / 2, zt - d))
    abox(K["Bilge"], sx0 + 0.004, sx1 - 0.004, sy0 + 0.004, sy1 - 0.004, zt - d, zt - d + 0.006)
    tap = [V((1.27, -3.06, zt + 0.02)), V((1.24, -3.06, zt + 0.2)), V((1.1, -3.06, zt + 0.25)),
           V((1.0, -3.06, zt + 0.18))]
    sweep(K["Chrome"], catmull(tap, 8), circle_profile(0.011, 12))
    cylinder(K["Chrome"], 0.025, 0.03, 16, T(1.27, -3.06, zt))
    for yy, key in ((-3.0, "PipeBlue"), (-3.12, "BtnRed")):   # 冷水、热水
        cylinder(K["Chrome"], 0.008, 0.03, 8, T(1.24, yy, zt + 0.12) @ R(90, 'Y'))
        cylinder(K[key], 0.016, 0.018, 12, T(1.21, yy, zt + 0.12) @ R(90, 'Y'))
    # 挡水板、靠墙一根水管
    abox(K["Steel"], 1.28, 1.3, ya, yf, zt, zt + 0.3)
    sweep(K["PipeBlue"], [V((1.29, yf, zt + 0.02)), V((1.27, -3.06, zt + 0.02))], circle_profile(0.012, 10))
    # 栏杆：防止东西滑下台面
    for yy in (ya + 0.04, -3.3, -3.6, yf - 0.04):
        cylinder(K["Steel"], 0.006, 0.05, 8, T(FACE + 0.015, yy, zt))
    sweep(K["Steel"], [V((FACE + 0.015, ya + 0.04, zt + 0.05)), V((FACE + 0.015, yf - 0.04, zt + 0.05))],
          circle_profile(0.006, 8))

    # 电炉（两个盘）+ 水壶
    Mh = T(0.98, -3.45, zt)
    rbox(K["EquipBeige"], 0.26, 0.42, 0.07, Mh @ T(0, 0, 0.035), r=0.008, seg=2)
    for k, yy in enumerate((-0.1, 0.1)):
        cylinder(K["Dark"], 0.075, 0.004, 32, Mh @ T(0, yy, 0.07))
        for j in range(4):
            torus(K["Steel"], 0.02 + j * 0.016, 0.004, 32, 6, Mh @ T(0, yy, 0.076))
        knob(K, frame(Mh @ V((-0.13, yy, 0.035)), V((-1, 0, 0))), 0, 0, 0.012, 0.014, ticks=5)
    Mk = Mh @ T(0, 0.1, 0.08)
    lathe(K["Alu"], [(0.0, 0.0), (0.085, 0.0), (0.095, 0.02), (0.095, 0.1), (0.08, 0.15), (0.045, 0.175),
                     (0.04, 0.185), (0.0, 0.19)], 32, Mk)
    uvsphere(K["Knob"], 0.015, 12, 8, Mk @ T(0, 0, 0.195))
    spout = catmull([Mk @ V((0, -0.08, 0.05)), Mk @ V((0, -0.14, 0.12)), Mk @ V((0, -0.17, 0.17))], 6)
    sweep(K["Alu"], spout, circle_profile(0.016, 10),
          scales=[1.0 - 0.55 * i / (len(spout) - 1) for i in range(len(spout))])
    sweep(K["Knob"], catmull([Mk @ V((0, 0.07, 0.13)), Mk @ V((0, 0.08, 0.22)), Mk @ V((0, -0.02, 0.24)),
                              Mk @ V((0, -0.07, 0.16))], 6), circle_profile(0.008, 8))
    # 电饭锅
    Mr = T(0.97, -3.76, zt)
    lathe(K["EquipBeige"], [(0.0, 0.0), (0.12, 0.0), (0.13, 0.02), (0.135, 0.15), (0.13, 0.17), (0.0, 0.17)], 40, Mr)
    lathe(K["Alu"], [(0.13, 0.17), (0.125, 0.19), (0.09, 0.215), (0.03, 0.225), (0.0, 0.225)], 40, Mr)
    cylinder(K["Knob"], 0.02, 0.02, 16, Mr @ T(0, 0, 0.222))
    for sy in (-1, 1):
        rbox(K["Knob"], 0.05, 0.03, 0.02, Mr @ T(0, sy * 0.145, 0.15), r=0.006, seg=2)
    rbox(K["PanelDark"], 0.012, 0.06, 0.04, Mr @ T(-0.133, 0, 0.08) @ R(-4, 'Y'), r=0.003, seg=1)
    lamp(K, frame(Mr @ V((-0.14, 0, 0.09)), V((-1, 0, 0))), 0, 0, 0.004, "LensRed")
    C.Cab.add([Mr @ V((0.12, 0.05, 0.05)), Mr @ V((0.22, 0.1, 0.02)), V((1.28, -3.85, zt + 0.15)),
               V((1.29, -3.9, zt + 0.25))], 0.004, "CableWhite")
    # 搪瓷缸子（白底红口），一个在台面上，三个挂在吊柜下面
    enamel_mug(K, T(0.82, -3.58, zt) @ R(200, 'Z'))
    enamel_mug(K, T(0.84, -2.86, zt) @ R(150, 'Z'), words=False)
    # 吊柜（两道肋骨之间）+ 柜下的灯管 + 挂杯钩
    cy0, cy1 = -3.45, -2.96
    abox(K["EquipGray"], 0.84, 1.2, cy0, cy1, 0.3, 0.58, r=0.008, seg=2)
    for k in range(2):
        a = cy0 + (cy1 - cy0) * k / 2 + 0.006
        b = cy0 + (cy1 - cy0) * (k + 1) / 2 - 0.006
        rbox(K["EquipGray"], 0.012, b - a, 0.25, T(0.835, (a + b) / 2, 0.44), r=0.003, seg=2)
        P = frame(V((0.829, (a + b) / 2, 0.44)), V((-1, 0, 0)))
        handle(K, P, 0, -0.08, 0.06, axis='X', key="Steel", standoff=0.015)
    label_plate(K, frame(V((0.829, -3.2, 0.555)), V((-1, 0, 0))), 0, 0, "炊具", 0.01)
    for yy in (cy0 + 0.03, cy1 - 0.03):
        abox(K["Steel"], 1.2, 1.24, yy - 0.012, yy + 0.012, 0.32, 0.56)
    abox(K["Steel"], 0.9, 1.15, -3.42, -2.99, 0.288, 0.3)
    sweep(K["LampGlass"], [V((1.02, -3.4, 0.28)), V((1.02, -3.01, 0.28))], circle_profile(0.011, 12))
    p = V((1.02, -3.2, 0.27))
    anchors.append(empty("CabinLight_Galley", K.coll, anchor_frame(p, V((-0.25, 0, -1)), V((0, 1, 0)))))
    sweep(K["Steel"], [V((0.86, cy0 + 0.02, 0.295)), V((0.86, cy1 - 0.02, 0.295))], circle_profile(0.004, 8))
    for k, yy in enumerate((-3.36, -3.25, -3.14)):
        hook = [V((0.86, yy, 0.295)), V((0.86, yy, 0.265)), V((0.875, yy, 0.255)), V((0.885, yy, 0.27))]
        sweep(K["Steel"], catmull(hook, 4), circle_profile(0.0018, 6))
        # 把手挂在钩子上，杯身斜着垂在下面
        enamel_mug(K, T(0.885, yy, 0.262) @ R(-70, 'Y') @ T(-0.066, 0, -0.045), words=(k == 1))
    # 筷子筒
    Mc = T(1.2, -3.66, zt)
    lathe(K["Bakelite"], [(0.0, 0.0), (0.035, 0.0), (0.035, 0.13), (0.031, 0.13), (0.031, 0.006), (0.0, 0.006)], 20, Mc)
    rng = random.Random(21)
    for k in range(9):
        a = rng.uniform(0, 6.28)
        rr = rng.uniform(0, 0.02)
        base = Mc @ V((math.cos(a) * rr, math.sin(a) * rr, 0.01))
        tip = base + V((rng.uniform(-0.02, 0.02), rng.uniform(-0.02, 0.02), 0.22))
        cylinder(K["Cardboard"], 0.0035, (tip - base).length, 6, frame(base, tip - base), r2=0.0025)
    anchors.append(empty("Anchor_GalleyThermos", K.coll, anchor_frame(V((0.8, -3.85, zt)), V((-0.3, 1, 0)))))
    anchors.append(empty("Anchor_Notepads", K.coll, anchor_frame(V((1.12, -2.86, zt)), V((-1, 0.3, 0)))))
    # 墙上一张手写的值日表
    P = frame(V((1.278, -3.62, zt + 0.2)), V((-1, 0, 0)))
    rbox(K["MaskTape"], 0.16, 0.11, 0.0006, P, r=0.0, seg=1)
    K.text("值日\n周一 老周\n周三 阿明\n周五 林工", P @ T(0, 0, 0.0004), 0.08, key="Marker", font=FONT_HAND)


# ============================================================================ 衣柜（左舷）
def lockers(K):
    s = -1
    yf, ya = GALLEY
    top = 0.45
    sbox(K["Dark"], s, FACE + 0.05, 1.0, ya, yf, DECK, DECK + 0.07)
    sbox(K["EquipGreen"], s, FACE + 0.02, 1.0, ya, yf, DECK + 0.07, top, r=0.006)
    sbox(K["EquipGreen"], s, FACE, 1.02, ya - 0.01, yf + 0.01, top, top + 0.02, r=0.006)
    mid = (ya + yf) / 2
    names = (("老周", 1), ("阿明", 2))
    for k, (a, b) in enumerate(((mid + 0.006, yf - 0.006), (ya + 0.006, mid - 0.006))):
        zc = (DECK + 0.07 + top) / 2
        hz = top - DECK - 0.1
        rbox(K["EquipGreen"], 0.018, b - a, hz, T(-FACE - 0.01, (a + b) / 2, zc), r=0.004, seg=2)
        P = frame(V((-FACE, (a + b) / 2, zc)), V((1, 0, 0)))
        vent(K, P, 0, hz / 2 - 0.12, (b - a) * 0.55, 0.12, 8, 0.005)
        vent(K, P, 0, -hz / 2 + 0.1, (b - a) * 0.55, 0.08, 6, 0.005)
        handle(K, P, (b - a) / 2 - 0.05, 0.05, 0.1, key="Steel", standoff=0.02)
        # 名牌框
        rbox(K["Steel"], 0.1, 0.045, 0.004, P @ T(0, 0.2, 0.002), r=0.002, seg=1)
        rbox(K["MeterFace"], 0.088, 0.035, 0.001, P @ T(0, 0.2, 0.0045), r=0.0, seg=1)
        nm, num = names[k]
        K.text(nm, P @ T(0, 0.2, 0.0052), 0.022, key="Ink", font=FONT_HAND)
        K.text(f"0{num}", P @ T(0, 0.29, 0.0005), 0.04, key="PaintText", font=FONT_SERIF)
        for sx in (-1, 1):
            for sy in (-1, 1):
                screw(K, P, sx * ((b - a) / 2 - 0.015), sy * (hz / 2 - 0.015), r=0.003)
    # 第二个衣柜的门缝上贴了一张符（门被封住了）
    P = frame(V((-FACE - 0.0205, mid - 0.006, 0.0)), V((1, 0, 0)))
    Mt = P @ R(4, 'Z')
    rbox(K["Talisman"], 0.06, 0.22, 0.0008, Mt, r=0.0, seg=1)
    K.text("敕令\n封", Mt @ T(0, 0, 0.0006), 0.13, key="BrushRed", font=FONT_BRUSH)
    for dy in (-0.1, 0.1):
        rbox(K["MaskTape"], 0.075, 0.025, 0.0006, Mt @ T(0, dy, 0.0008) @ R(8 * dy * 10, 'Z'), r=0.0, seg=1)
    # 衣柜顶上：一顶安全帽、一卷绳子
    Mh = T(-0.86, -3.05, top + 0.02)
    lathe(K["BtnYellow"], [(0.0, 0.0), (0.15, 0.0), (0.15, 0.006), (0.11, 0.012), (0.105, 0.06), (0.085, 0.11),
                           (0.05, 0.135), (0.0, 0.14)], 32, Mh @ S(1, 1.15, 1))
    torus(K["Cardboard"], 0.09, 0.025, 32, 10, T(-0.86, -3.55, top + 0.045) @ S(1, 1, 0.7))
    torus(K["Cardboard"], 0.08, 0.022, 32, 10, T(-0.86, -3.56, top + 0.085) @ S(1, 1, 0.7))


# ============================================================================ 上下铺
def bunks(K, anchors, s):
    yf, ya = BUNK
    xin, xw = BUNK_IN, LINING_X
    tag = "R" if s > 0 else "L"
    # 床尾 / 床头挡板（方管框里嵌一块压了筋的薄板）+ 过道一侧的立柱（立柱上挂布帘杆）
    for yy in (yf, ya):
        end_panel(K, s, yy)
        post(K, s, yy)
    # 靠壳体的衬板：三块拼起来，拼缝上压铝条
    lining(K, s, ya, yf)
    # 下铺：抽屉底座 + 床板 + 床垫
    sbox(K["Dark"], s, xin + 0.08, 1.0, ya + 0.012, yf - 0.012, DECK, DECK + 0.07)
    sbox(K["EquipBeige"], s, xin + 0.04, 1.0, ya + 0.012, yf - 0.012, DECK + 0.07, LOWER_Z - 0.03, r=0.004)
    for k in range(2):
        a = ya + 0.02 + (yf - ya - 0.04) * k / 2 + 0.006
        b = ya + 0.02 + (yf - ya - 0.04) * (k + 1) / 2 - 0.006
        zc = (DECK + 0.07 + LOWER_Z - 0.03) / 2
        h = LOWER_Z - 0.03 - DECK - 0.1
        sbox(K["EquipBeige"], s, xin + 0.02, xin + 0.04, a, b, zc - h / 2, zc + h / 2, r=0.004)
        P = frame(V((s * (xin + 0.02), (a + b) / 2, zc)), V((-s, 0, 0)))
        handle(K, P, 0, 0.03, 0.12, axis='X', key="Steel", standoff=0.016)
        card_holder(K, P @ T(0, 0.1, 0.0), ("被服", "杂物")[k] if s < 0 else ("鞋袜", "")[k], seed=k + (s > 0) * 2)
        for sx in (-1, 1):
            for sy in (-1, 1):
                rivet(K["EquipBeige"], P, sx * ((b - a) / 2 - 0.02), sy * (h / 2 - 0.02))
    sbox(K["EquipBeige"], s, xin, xw, ya + 0.012, yf - 0.012, LOWER_Z - 0.03, LOWER_Z, r=0.003)
    rail_edge(K, s, ya, yf, LOWER_Z)
    # 上铺：床板 + 挡板
    sbox(K["EquipBeige"], s, xin, xw, ya + 0.012, yf - 0.012, UPPER_Z - 0.035, UPPER_Z, r=0.003)
    rail_edge(K, s, ya, yf, UPPER_Z)
    guard(K, s, ya, yf)
    # 铺位编号、名牌：上铺的挂在护栏上，下铺的挂在上铺床板边上（帘子杆上面）
    names = {"L0": "李海生", "L1": "陈卫东", "R0": "", "R1": "王建国"}
    nums = {"L0": "03", "L1": "04", "R0": "01", "R1": "02"}
    for k, (z, dz) in enumerate(((UPPER_Z - 0.025, 0.0), (UPPER_Z + 0.09, 0.015))):
        P = frame(V((s * (xin - 0.004 + dz), yf - 0.3, z)), V((-s, 0, 0)))
        label_plate(K, P, 0, 0, nums[f"{tag}{k}"], 0.013, plate="Alu", ink="Ink")
        card_holder(K, P @ T(0.11, 0, 0), names[f"{tag}{k}"], seed=5 + k + (s > 0) * 2, w=0.1)
    # 上铺的脚蹬（焊在床尾挡板上）
    for z in (-0.12, 0.3):
        sbox(K["Steel"], s, xin + 0.05, xin + 0.2, ya + 0.0125, ya + 0.035, z - 0.012, z + 0.012, r=0.004)
    # 布帘杆
    for z in (0.8, UPPER_Z - 0.05):
        sweep(K["Steel"], [V((s * (xin + 0.01), ya, z)), V((s * (xin + 0.01), yf, z))], circle_profile(0.007, 10))
    # 床头灯（在床头那一头，靠衬板）
    lit = {(-1, 0), (1, 1)}   # 左舷下铺（帘子拉着）、右舷上铺亮着
    for k, z0 in enumerate((LOWER_Z, UPPER_Z)):
        zl = z0 + MATTRESS + 0.17
        yl = yf - 0.16
        F = frame(V((s * xw, yl, zl)), V((-s, 0, 0)))
        rbox(K["EquipGray"], 0.07, 0.05, 0.03, F @ T(0, 0, 0.015), r=0.006, seg=2)
        Fs = F @ T(0, -0.01, 0.03) @ R(-35, 'X')
        lathe(K["EquipGray"], [(0.0, 0.0), (0.02, 0.0), (0.035, 0.03), (0.045, 0.06), (0.043, 0.062),
                               (0.033, 0.032), (0.018, 0.004)], 24, Fs)
        uvsphere(K["LampGlass" if (s, k) in lit else "Silk"], 0.014, 12, 8, Fs @ T(0, 0, 0.03))
        toggle(K, F @ T(0, 0, 0.03), 0, 0.012, up=(s, k) in lit, s=0.7)
        if (s, k) in lit:
            anchors.append(empty(f"CabinLight_Bunk_{tag}{k}", K.coll, Fs @ T(0, 0, 0.05)))
        C.Cab.add([F @ V((0, -0.025, 0.01)), F @ V((0, -0.06, 0.0)), V((s * (xw - 0.005), yl - 0.1, zl - 0.15)),
                   V((s * (xw - 0.005), yl - 0.2, LOWER_Z - 0.04))], 0.003, "CableWhite")
    # 床垫、被褥、枕头、帘子（布料模拟，见 bedding.py）。先摆底下的，摆好的东西是后面几件的碰撞体
    lower = Bunk(K, s, LOWER_Z, xin, xw, ya, yf, DECK, False, tag + "0")
    upper = Bunk(K, s, UPPER_Z, xin, xw, ya, yf, DECK, True, tag + "1")
    for b in (lower, upper):
        b.mattress(MATTRESS, seed=2 + b.upper + (s > 0) * 2)
    if s < 0:
        # 下铺：帘子拉着，被子底下蜷着一个人，连头都蒙住了
        lower.sheet(seed=2)
        lower.body()
        lower.pillow(seed=2)
        lower.blanket(seed=3, over=0.15, y1=yf - 0.04)
        bunk_curtain(K, lower, UPPER_Z - 0.05, LOWER_Z + MATTRESS + 0.02, ya + 0.02, yf - 0.02, folds=15, seed=4)
        upper.sheet(seed=5)
        upper.pillow(seed=5, dy=-0.02, tilt=10)
        upper.blanket(seed=8, over=0.0, fold=(0.4, -20), crumple=0.04, shrink=-0.04)
        bunk_curtain(K, upper, 0.8, UPPER_Z + 0.18, yf - 0.26, yf - 0.02, folds=8, seed=5)
        # 下铺衬板上的搁板：搪瓷缸、眼镜（人蒙在被子里，眼镜摘下来放在这儿）
        bunk_shelf(K, anchors, s, -5.25, -4.85, -0.06, [("mug", -4.95, 30), ("Anchor_BunkSpectacles", -5.14, 0)])
        # 帘子底下一双胶靴
        for k, (dx, dy, yaw) in enumerate(((0.0, 0.0, 4), (0.05, 0.16, -10))):
            boot(K, T(s * (0.5 - dx), -4.62 + dy, DECK) @ R(yaw + 180, 'Z'))
    else:
        lower.folded_blanket(ya + 0.3, seed=6)
        bunk_shelf(K, anchors, s, -5.2, -4.8, -0.06, [("mug_plain", -5.08, 200), ("can", -4.9, 0)])
        lower.pillow(seed=7)
        bunk_curtain(K, lower, UPPER_Z - 0.05, LOWER_Z + MATTRESS + 0.02, ya + 0.02, ya + 0.4, folds=10, seed=6)
        upper.sheet(seed=9)
        upper.pillow(seed=9, dy=0.02)
        # 上铺的被子蹬到了床尾，堆成一团
        upper.blanket(seed=11, over=0.0, y0=ya + 0.05, y1=ya + 0.75, crumple=0.03, bunch=0.4)
        bunk_curtain(K, upper, 0.8, UPPER_Z + 0.18, ya + 0.02, ya + 0.3, folds=8, seed=7)
        anchors.append(empty("Anchor_PocketWatch", K.coll,
                             anchor_frame(V((s * 0.88, yf - 0.5, lower.surface_z(s * 0.88, yf - 0.5, 0.02))),
                                          V((0.3, 1, 0)))))
        anchors.append(empty("Anchor_BunkBook", K.coll,
                             anchor_frame(V((s * 0.85, -4.9, upper.surface_z(s * 0.85, -4.9) + 0.005)), V((1, 0.4, 0)))))
        # 上铺挡板上搭着一条毛巾；衬板上贴着照片
        upper.towel(-5.2, -4.86, seed=13)
        for k, (yy, zz, ang, cap) in enumerate(((-4.32, 0.37, -4, "九二年 青岛"), (-4.5, 0.385, 6, ""),
                                                (-4.44, 0.32, -2, "囡囡 五岁"))):
            photo(K, frame(V((s * (xw - 0.001), yy, zz)), V((-s, 0, 0))), ang, cap, seed=k)


def bunk_curtain(K, bunk, ztop, zbot, ya, yb, folds=10, seed=1):
    """布帘（布料模拟）+ 杆上的一排挂环。"""
    bunk.curtain(ztop, zbot, ya, yb, folds, seed)
    for k in range(folds + 1):
        y = ya + (yb - ya) * k / folds
        torus(K["Steel"], 0.011, 0.002, 12, 4, T(bunk.x(BUNK_IN + 0.01), y, ztop) @ R(90, 'X'))


def boot(K, M):
    """一只半高筒胶靴（鞋尖朝 M 的 +Y）。"""
    rbox(K["Rubber"], 0.1, 0.29, 0.025, M @ T(0, 0.03, 0.0125), r=0.01, seg=2)
    rbox(K["Rubber"], 0.09, 0.2, 0.07, M @ T(0, 0.07, 0.06) @ R(-8, 'X'), r=0.035, seg=3)
    lathe(K["Rubber"], [(0.0, 0.02), (0.05, 0.02), (0.052, 0.12), (0.055, 0.3), (0.05, 0.3), (0.047, 0.12),
                        (0.0, 0.11)], 20, M @ T(0, -0.05, 0) @ S(1, 1.2, 1))


def rivet(bm, P, x, y, r=0.0034):
    """圆头铆钉（面板坐标系 P 里，Z 朝外）。"""
    lathe(bm, [(r, 0.0), (r * 0.95, r * 0.3), (r * 0.7, r * 0.6), (r * 0.35, r * 0.75), (0.0, r * 0.78)], 10,
          P @ T(x, y, 0))


def card_holder(K, P, text, seed=0, w=0.07):
    """铝皮插卡框，插着一张手写卡片（text 为空就是一张白卡）。P 的 XY 平面是贴的那个面。"""
    rng = random.Random(seed)
    h = w * 0.45
    rbox(K["Alu"], w + 0.008, h + 0.006, 0.0012, P @ T(0, 0, 0.0006), r=0.0006, seg=1)
    M = P @ T(rng.uniform(-0.002, 0.002), rng.uniform(-0.001, 0.001), 0.0013) @ R(rng.uniform(-1.5, 1.5), 'Z')
    rbox(K["MeterFace"], w, h, 0.0004, M, r=0.0, seg=1)
    for sx in (-1, 1):  # 框的两条竖边压住卡片
        rbox(K["Alu"], 0.004, h + 0.004, 0.0008, P @ T(sx * (w / 2 + 0.001), 0, 0.0018), r=0.0003, seg=1)
        rivet(K["Steel"], P @ T(sx * (w / 2 + 0.001), 0, 0.0022), 0, 0, 0.0012)
    if text:
        K.text(text, M @ T(0, -h * 0.05, 0.00025), h * 0.5, key="Marker", font=FONT_HAND)


def end_panel(K, s, y):
    """铺位两头的挡板：靠壳一侧一根竖方管、上下两根横方管，中间一块凹进去的薄钢板，
    板上横着压了几道加强筋；方管和板子之间一圈螺钉（两面都有）。"""
    xa, xb = BUNK_IN + 0.03, LINING_X
    t = 0.03
    z0, z1 = DECK, 0.43
    sbox(K["EquipBeige"], s, xa - 0.02, xb, y - 0.015, y + 0.015, z1 - t, z1, r=0.005)
    sbox(K["EquipBeige"], s, xa - 0.02, xb, y - 0.015, y + 0.015, z0, z0 + 0.05, r=0.005)
    sbox(K["EquipBeige"], s, xb - t, xb, y - 0.015, y + 0.015, z0, z1, r=0.005)
    sbox(K["EquipBeige"], s, xa - 0.02, xb - t, y - 0.004, y + 0.004, z0 + 0.04, z1 - t + 0.01, r=0.0015)
    for zb in (-0.74, -0.29, -0.06, 0.34):
        sweep(K["EquipBeige"], [V((s * (xa + 0.03), y, zb)), V((s * (xb - t - 0.03), y, zb))],
              circle_profile(0.0075, 10))
        for xx in (xa + 0.03, xb - t - 0.03):
            uvsphere(K["EquipBeige"], 0.0075, 10, 6, T(s * xx, y, zb))
    rng = random.Random(int(abs(y) * 100))
    for side in (-1, 1):
        P = frame(V((0, y + side * 0.004, 0)), V((0, side, 0)))
        for k in range(6):
            x = xa + (xb - t - xa) * (k + 0.5) / 6
            for z in (z1 - t - 0.012, z0 + 0.062):
                screw(K, T(s * x, 0, z) @ P, 0, 0, 0.0032, key="Steel", rng=rng)
        for z in (-0.6, -0.15, 0.2):
            screw(K, T(s * (xb - t - 0.012), 0, z) @ P, 0, 0, 0.0032, key="Steel", rng=rng)


def post(K, s, y):
    """过道一侧的立柱：方钢管，底下一块地脚板两颗螺栓，顶上一块盖板。"""
    x0, x1 = BUNK_IN - 0.01, BUNK_IN + 0.03
    sbox(K["Steel"], s, x0, x1, y - 0.02, y + 0.02, DECK, 0.86, r=0.004)
    sbox(K["Steel"], s, x0 - 0.018, x1 + 0.018, y - 0.035, y + 0.035, DECK, DECK + 0.007, r=0.002, seg=1)
    sbox(K["Steel"], s, x0 - 0.003, x1 + 0.003, y - 0.023, y + 0.023, 0.86, 0.866, r=0.002, seg=1)
    for k in (-1, 1):
        cylinder(K["Steel"], 0.0065, 0.006, 6, T(s * (x0 - 0.009 if k < 0 else x1 + 0.009), y, DECK + 0.007)
                 @ R(15, 'Z'))
    # 立柱和挡板之间的焊缝（一串小疙瘩）
    rng = random.Random(int(abs(y) * 77))
    for k in range(40):
        z = DECK + 0.06 + (0.4 - DECK - 0.06) * k / 39
        uvsphere(K["Steel"], 0.0032 + rng.uniform(-0.0006, 0.0006), 8, 4,
                 T(s * (x1 + 0.0005), y + rng.uniform(-0.0015, 0.0015), z) @ S(0.7, 1, 1.3))


def rail_edge(K, s, ya, yf, z):
    """床板靠过道一边包的角钢：竖边高出床板一点挡住床垫，一排圆头铆钉。"""
    xin = BUNK_IN
    sbox(K["EquipBeige"], s, xin - 0.004, xin + 0.001, ya + 0.02, yf - 0.02, z - 0.05, z + 0.012, r=0.0015)
    P = frame(V((s * (xin - 0.004), 0, 0)), V((-s, 0, 0)))
    n = int((yf - ya - 0.1) / 0.15)
    for k in range(n + 1):
        y = ya + 0.05 + (yf - ya - 0.1) * k / n
        rivet(K["EquipBeige"], T(0, y, z - 0.03) @ P, 0, 0)


def guard(K, s, ya, yf):
    """上铺护栏：一块钢板，上沿卷成圆管，过道一面压一道筋，背面三根竖加强条；下沿一排铆钉。"""
    xin = BUNK_IN
    z0, z1 = UPPER_Z, UPPER_Z + 0.16
    y0, y1 = ya + 0.012, yf - 0.012
    sbox(K["EquipBeige"], s, xin + 0.011, xin + 0.019, y0, y1, z0, z1 - 0.02, r=0.0015)
    sweep(K["EquipBeige"], [V((s * (xin + 0.015), y0, z1 - 0.014)), V((s * (xin + 0.015), y1, z1 - 0.014))],
          circle_profile(0.014, 16))
    for yy in (y0, y1):
        cylinder(K["EquipBeige"], 0.0142, 0.004, 16, T(s * (xin + 0.015), yy, z1 - 0.014) @ R(90, 'X')
                 @ T(0, 0, -0.002))
    zb = z0 + 0.04
    sweep(K["EquipBeige"], [V((s * (xin + 0.011), y0 + 0.05, zb)), V((s * (xin + 0.011), y1 - 0.05, zb))],
          circle_profile(0.0055, 10))
    for yy in (y0 + 0.4, (y0 + y1) / 2, y1 - 0.4):
        sbox(K["EquipBeige"], s, xin + 0.019, xin + 0.026, yy - 0.012, yy + 0.012, z0, z1 - 0.028, r=0.0015)
    P = frame(V((s * (xin + 0.011), 0, 0)), V((-s, 0, 0)))
    n = int((y1 - y0 - 0.1) / 0.15)
    for k in range(n + 1):
        y = y0 + 0.05 + (y1 - y0 - 0.1) * k / n
        rivet(K["EquipBeige"], T(0, y, z0 + 0.016) @ P, 0, 0)


def lining(K, s, ya, yf):
    """靠壳的衬板：三块板拼起来（板缝 3 毫米），拼缝上压一条铝压条，四角和压条上打螺钉。"""
    xw = LINING_X
    z0, z1 = LOWER_Z - 0.04, 0.45
    cuts = [ya, ya + (yf - ya) / 3, ya + 2 * (yf - ya) / 3, yf]
    rng = random.Random(3 + (s > 0))
    P = frame(V((s * xw, 0, 0)), V((-s, 0, 0)))
    for i in range(3):
        a, b = cuts[i] + (0.0015 if i else 0.0), cuts[i + 1] - (0.0015 if i < 2 else 0.0)
        sbox(K["EquipBeige"], s, xw, xw + 0.012, a, b, z0, z1, r=0.0015, seg=1)
        for yy in (a + 0.025, b - 0.025):
            for zz in (z0 + 0.025, z1 - 0.025):
                screw(K, T(0, yy, zz) @ P, 0, 0, 0.003, key="Steel", rng=rng)
    for yc in cuts[1:3]:
        sbox(K["Alu"], s, xw - 0.003, xw, yc - 0.014, yc + 0.014, z0 + 0.005, z1 - 0.005, r=0.001, seg=1)
        for k in range(6):
            zz = z0 + 0.04 + (z1 - z0 - 0.08) * k / 5
            screw(K, T(0, yc, zz) @ frame(V((s * (xw - 0.003), 0, 0)), V((-s, 0, 0))), 0, 0, 0.0026,
                  key="Steel", rng=rng)


def bunk_shelf(K, anchors, s, y0, y1, z, items):
    """下铺衬板上的小搁板（钢板折出前挡边，两个三角托架），上面摆着几样东西。"""
    xw = LINING_X
    d = 0.11
    sbox(K["EquipGray"], s, xw - d, xw, y0, y1, z - 0.004, z, r=0.0015, seg=1)
    sbox(K["EquipGray"], s, xw - d, xw - d + 0.004, y0, y1, z, z + 0.025, r=0.0015, seg=1)
    for yy in (y0 + 0.03, y1 - 0.03):
        bm = K["EquipGray"]
        tri = [V((s * xw, yy, z - 0.004)), V((s * (xw - d + 0.01), yy, z - 0.004)), V((s * xw, yy, z - 0.09))]
        for dy in (-0.002, 0.002):
            vs = [bm.verts.new(p + V((0, dy, 0))) for p in tri]
            bm.faces.new(vs)
        for i in range(3):
            a, b = tri[i], tri[(i + 1) % 3]
            vs = [bm.verts.new(p + V((0, dy, 0))) for p, dy in ((a, -0.002), (b, -0.002), (b, 0.002), (a, 0.002))]
            bm.faces.new(vs)
    for kind, y, ang in items:
        M = T(s * (xw - 0.055), y, z) @ R(ang, 'Z')
        if kind == "mug":
            enamel_mug(K, M)
        elif kind == "mug_plain":
            enamel_mug(K, M, words=False)
        elif kind == "can":
            lathe(K["Can"], [(0.0, 0.0), (0.032, 0.0), (0.033, 0.004), (0.033, 0.09), (0.03, 0.093),
                             (0.03, 0.006), (0.0, 0.006)], 24, M)
            lathe(K["CanLabel"], [(0.0335, 0.012), (0.0335, 0.08)], 24, M)
            for k, (dx, dy, ln) in enumerate(((0.008, 0.005, 0.15), (-0.01, 0.004, 0.14), (0.0, -0.01, 0.16))):
                sweep(K["Knob" if k else "BtnRed"], [M @ V((dx, dy, 0.006)), M @ V((dx * 3, dy * 3, ln))],
                      circle_profile(0.0035, 6))
        else:  # 挂点
            anchors.append(empty(kind, K.coll, anchor_frame(V((s * (xw - 0.055), y, z)), V((-s, 0.3, 0)))))


def enamel_mug(K, M, words=True):
    """搪瓷缸子（白底红口）。"""
    lathe(K["Silk"], [(0.0, 0.0), (0.038, 0.0), (0.04, 0.004), (0.04, 0.085), (0.036, 0.085), (0.036, 0.008),
                      (0.0, 0.008)], 24, M)
    torus(K["BtnRed"], 0.039, 0.003, 24, 6, M @ T(0, 0, 0.085))
    sweep(K["Silk"], catmull([M @ V((0.039, 0, 0.068)), M @ V((0.065, 0, 0.06)), M @ V((0.066, 0, 0.03)),
                              M @ V((0.039, 0, 0.022))], 5), circle_profile(0.005, 8))
    if words:
        K.text("先进", M @ T(-0.0402, 0, 0.045) @ R(-90, 'Y') @ R(-90, 'Z'), 0.014, key="InkRed", font=FONT_SERIF)


def photo(K, F, ang, caption, seed=0):
    """贴在墙上的照片：白边、画面、四角胶带，下边有手写字。"""
    rng = random.Random(seed)
    M = F @ R(ang, 'Z')
    rbox(K["MeterFace"], 0.09, 0.12, 0.0006, M @ T(0, 0, 0.0003), r=0.0, seg=1)
    rbox(K["EquipBlue" if seed % 2 else "PanelGray"], 0.078, 0.085, 0.0004, M @ T(0, 0.01, 0.0008), r=0.0, seg=1)
    for sx in (-1, 1):
        rbox(K["MaskTape"], 0.035, 0.014, 0.0004, M @ T(sx * 0.04, 0.056, 0.0011) @ R(sx * 35, 'Z'), r=0.0, seg=1)
    if caption:
        K.text(caption, M @ T(0, -0.048, 0.0009), 0.009, key="Marker", font=FONT_HAND)


# ============================================================================ 最后面：储物架、洗手池、镜子
def aft_end(K, anchors):
    y0, y1 = Y_STERN, BUNK[1]
    # 右舷：三层储物架（带挡条），堆着罐头、纸箱、扳手
    s = 1
    sbox(K["EquipGray"], s, FACE + 0.02, 1.0, y0 + 0.01, y1 - 0.02, DECK, DECK + 0.06)
    for yy in (y0 + 0.02, y1 - 0.03):
        sbox(K["EquipGray"], s, FACE, 1.08, yy - 0.01, yy + 0.01, DECK, 0.52)
    for z in (-0.45, 0.0, 0.45):
        x1 = min(1.0 if z < -0.3 else 1.08, wall_x(z) - 0.02)
        sbox(K["EquipGray"], s, FACE, x1, y0 + 0.03, y1 - 0.04, z - 0.015, z, r=0.003)
        sweep(K["Steel"], [V((s * (FACE + 0.01), y0 + 0.03, z + 0.06)), V((s * (FACE + 0.01), y1 - 0.04, z + 0.06))],
              circle_profile(0.005, 8))
    rng = random.Random(31)
    for k in range(5):
        M = T(s * (0.8 + 0.09 * (k % 2)), y0 + 0.1 + 0.075 * k, -0.45) @ R(rng.uniform(0, 360), 'Z')
        lathe(K["Can"], [(0.0, 0.0), (0.036, 0.0), (0.037, 0.004), (0.037, 0.106), (0.036, 0.11), (0.0, 0.11)], 24, M)
        lathe(K["CanLabel"], [(0.0375, 0.012), (0.0375, 0.098)], 24, M)
    for k, (w, d, h) in enumerate(((0.3, 0.24, 0.22), (0.26, 0.2, 0.16))):
        rbox(K["Cardboard"], w, d, h, T(s * (0.88 + 0.03 * k), (y0 + y1) / 2 + 0.02 * k, 0.0 + h / 2 + k * 0.22)
             @ R(4 - 9 * k, 'Z'), r=0.004, seg=1)
    tape_label(K, frame(V((s * 0.729, (y0 + y1) / 2, 0.11)), V((-1, 0, 0))), 0, 0, "压缩饼干", 0.016, 2)
    anchors.append(empty("Anchor_Wrench", K.coll, anchor_frame(V((s * 0.86, y1 - 0.15, 0.45)), V((0.2, -1, 0)))))
    anchors.append(empty("Anchor_Compass", K.coll, anchor_frame(V((s * 0.84, y0 + 0.16, 0.45)), V((-1, 0.4, 0)))))

    # 左舷：小洗手池 + 镜子 + 牙缸毛巾
    s = -1
    zt = -0.05
    sbox(K["Dark"], s, FACE + 0.05, 1.0, y0 + 0.01, y1 - 0.02, DECK, DECK + 0.07)
    sbox(K["EquipGreen"], s, FACE + 0.02, 1.0, y0 + 0.01, y1 - 0.02, DECK + 0.07, zt - 0.03, r=0.006)
    P = frame(V((s * FACE, (y0 + y1) / 2, (DECK + zt) / 2)), V((1, 0, 0)))
    handle(K, P, 0.12, 0.15, 0.09, key="Steel")
    sbox(K["Steel"], s, FACE - 0.01, 1.2, y0 + 0.01, y1 - 0.02, zt - 0.03, zt, r=0.003)
    Mb = T(s * 0.92, (y0 + y1) / 2, zt)
    lathe(K["Steel"], [(0.0, -0.1), (0.1, -0.1), (0.14, -0.04), (0.16, 0.0), (0.165, 0.004), (0.15, 0.004),
                       (0.13, -0.04), (0.09, -0.092), (0.0, -0.092)], 32, Mb @ T(0, 0, 0.004) @ S(1, 1.2, 1))
    cylinder(K["Dark"], 0.02, 0.001, 16, Mb @ T(0, 0, -0.091))
    tap = [V((s * 1.13, (y0 + y1) / 2, zt + 0.02)), V((s * 1.12, (y0 + y1) / 2, zt + 0.17)),
           V((s * 1.02, (y0 + y1) / 2, zt + 0.19)), V((s * 0.97, (y0 + y1) / 2, zt + 0.13))]
    sweep(K["Chrome"], catmull(tap, 8), circle_profile(0.01, 12))
    # 镜子：钉在两道肋骨之间的衬板上，水银斑驳
    ym = (y0 + y1) / 2 - 0.02
    xm = -1.08
    abox(K["EquipGreen"], xm - 0.02, xm, ym - 0.2, ym + 0.2, 0.18, 0.72)
    abox(K["Mirror"], xm, xm + 0.004, ym - 0.18, ym + 0.18, 0.2, 0.7)
    for yy in (ym - 0.19, ym + 0.19):
        for zz in (0.19, 0.71):
            socket_screw(K, frame(V((xm + 0.004, yy, zz)), V((1, 0, 0))), 0, 0, r=0.004)
    # 镜子下沿夹着一张照片（只看得见背面），写着字
    Mp = frame(V((xm + 0.006, ym + 0.1, 0.24)), V((1, 0, 0))) @ R(-8, 'Z')
    rbox(K["MeterFace"], 0.07, 0.1, 0.0006, Mp, r=0.0, seg=1)
    K.text("别回头", Mp @ T(0, 0.01, 0.0005), 0.014, key="Marker", font=FONT_HAND)
    # 牙缸、牙刷
    Mc = T(s * 1.1, y1 - 0.12, zt)
    lathe(K["Bottle"], [(0.0, 0.0), (0.033, 0.0), (0.035, 0.1), (0.031, 0.1), (0.03, 0.006), (0.0, 0.006)], 20, Mc)
    for k in range(2):
        a = Mc @ V((0.005 * (k * 2 - 1), 0.0, 0.01))
        b = a + V((0.02 * (k * 2 - 1), 0.015, 0.17))
        cylinder(K["BtnGreen" if k else "BtnRed"], 0.004, (b - a).length, 6, frame(a, b - a))
    # 柜门上的毛巾杆
    bx, bz = -(FACE - 0.03), -0.17
    sweep(K["Steel"], [V((bx, y0 + 0.08, bz)), V((bx, y1 - 0.12, bz))], circle_profile(0.006, 8))
    for yy in (y0 + 0.08, y1 - 0.12):
        sweep(K["Steel"], [V((bx, yy, bz)), V((-(FACE + 0.02), yy, bz))], circle_profile(0.006, 8))
    C.towel(K, (bx, bz + 0.006), y0 + 0.14, y1 - 0.2, 0.3, 0.16, seed=9)


# ============================================================================ 后隔壁：封死的机舱检修门
def stern_bulkhead(K, anchors):
    y = Y_STERN

    def plate(bm):
        step = 0.03
        nx = int(2 * R_IN / step) + 3
        nz = int((R_IN - DECK) / step) + 3
        verts = {}

        def vtx(i, j):
            if (i, j) not in verts:
                verts[(i, j)] = bm.verts.new(V((-R_IN - step + i * step, y, DECK - 0.03 + j * step)))
            return verts[(i, j)]
        for i in range(nx):
            for j in range(nz):
                cx = -R_IN - step + (i + 0.5) * step
                cz = DECK - 0.03 + (j + 0.5) * step
                if math.hypot(cx, cz) > R_IN + 0.02:
                    continue
                bm.faces.new([vtx(i, j), vtx(i, j + 1), vtx(i + 1, j + 1), vtx(i + 1, j)])
    K.separate("Int_SternBulkhead", "HullInner", plate, recalc=False)
    bm = K["HullInner"]
    ring_sweep(bm, [(R_IN + 0.01, 0.0), (R_IN - 0.035, 0.0), (R_IN + 0.01, 0.045)][::-1], y, -140, 140, 180)
    zt = 0.95
    xt = math.sqrt(R_IN ** 2 - zt ** 2) + 0.01
    rbox(bm, 2 * xt, 0.11, 0.02, T(0, y + 0.055, zt), r=0.0, seg=1)
    rbox(bm, 2 * xt, 0.02, 0.08, T(0, y + 0.11, zt), r=0.004, seg=2)

    # 检修门：椭圆围板 + 螺栓压住的盖板（不是门，是拿 20 颗螺栓封死的）
    hz, ha, hb = 0.0, 0.27, 0.42
    path = [V((math.cos(t) * (ha + 0.04), y + 0.03, hz + math.sin(t) * (hb + 0.04)))
            for t in [2 * math.pi * k / 72 for k in range(72)]]

    sweep(K["HullInner"], path, rect_profile(0.08, 0.06, 0.01), closed=True, up_hint=V((0, 1, 0)))
    Mc = T(0, y + 0.06, hz) @ R(-90, 'X')
    cylinder(K["EquipGray"], 1.0, 0.025, 64, Mc @ S(ha + 0.06, hb + 0.06, 1))
    for k in range(20):
        t = 2 * math.pi * k / 20
        Mb = T(math.cos(t) * (ha + 0.03), y + 0.085, hz + math.sin(t) * (hb + 0.03)) @ R(-90, 'X')
        cylinder(K["Steel"], 0.014, 0.012, 6, Mb)
        cylinder(K["Steel"], 0.007, 0.022, 8, Mb)
    for zz in (-0.2, 0.2):
        P = frame(V((0, y + 0.085, hz + zz)), V((0, 1, 0)))
        handle(K, P, 0, 0, 0.14, axis='X', key="Steel", standoff=0.03)
    # 封条：两条交叉的纸，盖着红章；正中一张符
    P = frame(V((0, y + 0.0862, hz)), V((0, 1, 0)))
    for k, ang in enumerate((28, -28)):
        Ms = P @ R(ang, 'Z') @ T(0, 0, 0.0004 * (k + 1))
        rbox(K["MeterFace"], 0.06, 1.0, 0.0006, Ms, r=0.0, seg=1)
        for yy in (-0.32, 0.32):
            K.text("封", Ms @ T(0, yy, 0.0004), 0.035, key="InkRed", font=FONT_SERIF)
            torus(K["InkRed"], 0.022, 0.0015, 24, 4, Ms @ T(0, yy, 0.0004))
        K.text("严禁开启", Ms @ T(0, 0.13 * (1 if k else -1), 0.0004) @ R(90, 'Z'), 0.018, key="Ink", font=FONT_SERIF)
    Mt = P @ T(0, 0.02, 0.002) @ R(-3, 'Z')
    rbox(K["Talisman"], 0.085, 0.3, 0.0008, Mt, r=0.0, seg=1)
    K.text("敕令\n镇海\n封", Mt @ T(0, 0, 0.0006), 0.24, key="BrushRed", font=FONT_BRUSH)
    label_plate(K, frame(V((0, y + 0.002, hz + hb + 0.17)), V((0, 1, 0))), 0, 0, "机舱  严禁入内", 0.016,
                plate="LabelRed")

    # 日历（右边）：十月，前几天画了叉
    P = frame(V((0.6, y + 0.003, 0.35)), V((0, 1, 0))) @ R(2, 'Z')
    rbox(K["MeterFace"], 0.24, 0.32, 0.0008, P, r=0.0, seg=1)
    rbox(K["InkRed"], 0.24, 0.05, 0.0004, P @ T(0, 0.135, 0.0006), r=0.0, seg=1)
    K.text("十月", P @ T(0, 0.135, 0.001), 0.026, key="Silk", font=FONT_SERIF)
    for r_ in range(5):
        for c_ in range(7):
            day = r_ * 7 + c_ + 1
            if day > 31:
                continue
            p = P @ T(-0.09 + c_ * 0.03, 0.08 - r_ * 0.045, 0.0006)
            K.text(str(day), p, 0.011, key="Ink")
            if day < 7:
                K.text("×", p @ T(0, 0, 0.0003), 0.022, key="InkRed", font=FONT_HAND)
            elif day == 7:
                torus(K["InkRed"], 0.012, 0.0012, 20, 4, p @ T(0, 0, 0.0003))
    socket_screw(K, P @ T(0, 0.155, 0.0), 0, 0, r=0.004)
    # 挂钟（左边）：停在三点十七分
    F = frame(V((-0.6, y, 0.4)), V((0, 1, 0)))
    cylinder(K["Bakelite"], 0.11, 0.035, 48, F)
    cylinder(K["GaugeFace"], 0.095, 0.036, 48, F)
    torus(K["Bakelite"], 0.1, 0.008, 48, 8, F @ T(0, 0, 0.036))
    for k in range(12):
        a = math.radians(90 - 30 * k)
        L = 0.014 if k % 3 == 0 else 0.007
        box(K["Ink"], 0.003, L, 0.0006, F @ T(math.cos(a) * 0.082, math.sin(a) * 0.082, 0.0362) @ R(-30 * k, 'Z'))
    for k, txt in ((0, "12"), (3, "3"), (6, "6"), (9, "9")):
        a = math.radians(90 - 30 * k)
        K.text(txt, F @ T(math.cos(a) * 0.062, math.sin(a) * 0.062, 0.0365), 0.016, key="Ink", font=FONT_SERIF)
    for ang, L, w in ((90 - (3 + 17 / 60) * 30, 0.05, 0.006), (90 - 17 * 6, 0.075, 0.004)):
        a = math.radians(ang)
        box(K["Ink"], w, L, 0.001, F @ T(math.cos(a) * L / 2, math.sin(a) * L / 2, 0.039) @ R(ang - 90, 'Z'))
    cylinder(K["Brass"], 0.006, 0.006, 12, F @ T(0, 0, 0.038))
    # 红色夜灯
    q = V((0.0, y, 0.72))
    Fl = frame(q, V((0, 1, 0)))
    cylinder(K["PanelDark"], 0.045, 0.02, 32, Fl)
    lathe(K["LensRed"], [(0.035, 0.02), (0.035, 0.035), (0.026, 0.05), (0.0, 0.055)], 32, Fl)
    anchors.append(empty("CabinLight_NightAft", K.coll, Fl @ T(0, 0, 0.07)))


# ============================================================================ 贴花
def decals(anchors, coll):
    def d(kind, pos, normal, up, w, h, depth=0.06):
        decal(anchors, coll, kind, pos, normal, up, w, h, depth)
    UP, Z = V((0, 0, 1)), V((0, 1, 0))
    # 一串湿脚印从封死的检修门那儿走出来，停在拉着帘子的下铺跟前
    steps = [(0.06, -6.22, 0, "R"), (-0.08, -5.95, -6, "L"), (0.02, -5.68, -4, "R"), (-0.14, -5.42, -14, "L"),
             (-0.08, -5.15, -30, "R"), (-0.3, -4.95, -60, "L"), (-0.28, -4.78, -88, "R"), (-0.3, -4.96, -92, "L")]
    for x, y, yaw, foot in steps:
        a = math.radians(yaw)
        d("Boot" + foot, (x, y, DECK), UP, V((-math.sin(a), math.cos(a), 0)), 0.11, 0.29, 0.03)
    d("Puddle", (0.0, Y_STERN + 0.18, DECK), UP, V((1, 0.2, 0)), 0.42, 0.3, 0.03)
    for x in (-0.12, 0.05, 0.16):
        d("Rust", (x, Y_STERN + 0.04, -0.62), Z, UP, 0.07, 0.36, 0.12)
    d("Streak", (0.0, Y_STERN + 0.07, -0.47), Z, UP, 0.5, 0.12, 0.08)
    # 台面上的水渍圈、烫痕；衣柜门把手周围的手油；铺位挡板磨亮的地方
    for x, y, r in ((0.84, -3.68, 0.09), (1.15, -3.3, 0.08), (0.8, -2.83, 0.09)):
        d("Ring", (x, y, COUNTER_Z), UP, V((math.sin(x * 9), math.cos(x * 9), 0)), r, r, 0.03)
    d("Burn", (0.86, -3.52, COUNTER_Z), UP, Z, 0.03, 0.03, 0.03)
    for y in (-3.12, -3.68):
        d("Grease", (-FACE - 0.02, y, -0.05), V((1, 0, 0)), UP, 0.13, 0.17, 0.05)
    for s in (-1, 1):
        d("Scuff", (s * (FACE + 0.02), -3.3, DECK + 0.12), V((-s, 0, 0)), UP, 0.55, 0.15, 0.06)
        d("Polish", (s * (BUNK_IN + 0.015), -4.9, UPPER_Z + 0.16), UP, Z, 0.04, 1.2, 0.03)
    d("Hazard", (0.0, HATCH[1] - 0.22, DECK), UP, Z, 0.5, 0.09, 0.03)
