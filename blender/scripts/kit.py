"""驾驶舱「设备拼装」零件库。

- Parts：按材质分桶收集几何体，最后每种材质只生成一个对象（几千个小零件不会变成几千个对象）。
- 面板零件（螺丝、拨动开关、旋钮、按钮、指示灯、表头、数码管、报警灯牌、接插件、把手、散热孔……）
  都在面板坐标系 P 里摆放：P 的 XY 平面是面板正面，+Z 朝外（朝操作的人），+Y 朝上。
- Cables：单根的线缆，和桥架上平铺的扁平线束（成排拐弯不拧麻花，扎带连横档一起捆），最后统一扫掠成管子。
"""
import math
import os
import random

import bpy
import bmesh
from mathutils import Vector as V, Matrix

from lib import (T, R, S, frame, sph, cylinder, box, uvsphere, lathe, torus, catmull, circle_profile,
                 sweep, to_object, text_mesh, empty)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FONT_SANS = os.path.join(ROOT, "blender", "fonts", "NotoSansSC-VF.ttf")
FONT_SERIF = os.path.join(ROOT, "blender", "fonts", "NotoSerifSC-VF.ttf")
FONT_HAND = os.path.join(ROOT, "blender", "fonts", "LongCang-Regular.ttf")  # 只在建模时用，不进游戏
FONT_BRUSH = os.path.join(ROOT, "blender", "fonts", "MaShanZheng-Regular.ttf")



# ============================================================================ 分桶收集
class Parts:
    """K["Steel"] 拿到 Steel 材质的 bmesh；flush() 时每个材质生成一个对象。"""

    # 这些材质的零件是软的/圆的，不做加权法线
    SOFT = {"Foam", "Vinyl", "Cloth", "CableBlack", "CableGray", "CableOrange", "CableYellow", "CableBlue",
            "CableWhite", "Zip", "ZipBlack", "Paper", "Talisman", "Tape", "MaskTape", "ClothRed", "Ash",
            "Lagging", "Towel", "Jacket", "Net", "Orange", "Blanket", "Curtain"}

    def __init__(self, coll, M, prefix="Int"):
        self.coll, self.M, self.prefix = coll, M, prefix
        self.bms = {}
        self.n = 0

    def __getitem__(self, key):
        if key not in self.bms:
            if key not in self.M:
                raise KeyError(f"材质 {key} 没有定义")
            self.bms[key] = bmesh.new()
        return self.bms[key]

    def uid(self, base):
        self.n += 1
        return f"{base}_{self.n:04d}"

    def separate(self, name, key, fn, smooth=True, sharp=35.0, recalc=True):
        """不进桶、单独成对象（指针、指示灯这类运行时要单独控制的）。"""
        bm = bmesh.new()
        fn(bm)
        return to_object(bm, name, self.coll, self.M[key], smooth=smooth, sharp_angle=sharp, recalc=recalc)

    def text(self, s, M, size, key="Silk", font=FONT_SANS, align='CENTER'):
        """平面文字贴在 M 的 XY 平面上（M 的原点 = 文字中心，略微抬高避免和面板打架）。
        小字不挤出厚度、曲线不细分，否则几百行字就是几十万个顶点。"""
        return text_mesh(s, self.uid("Int_Txt"), self.coll, self.M[key], M @ T(0, 0, 0.00012),
                         size=size, extrude=0.0, font_path=font, align=align, resolution=1)

    def flush(self, recalc=True):
        """recalc=False：面的朝向已经排好了（房间的墙、地、顶朝屋里，自动重算会全翻到外面去）。"""
        out = []
        for key, bm in self.bms.items():
            if not bm.verts:
                bm.free()
                continue
            ob = to_object(bm, f"{self.prefix}_{key}", self.coll, self.M[key], sharp_angle=40.0, recalc=recalc)
            if key not in self.SOFT:
                wn = ob.modifiers.new("WeightedNormal", 'WEIGHTED_NORMAL')
                wn.keep_sharp = True
                wn.mode = 'FACE_AREA'
                wn.weight = 50
            out.append(ob)
        self.bms = {}
        return out


# ============================================================================ 基础形体
def bev_layer(bm):
    """面属性 bev：0 = 普通几何（磨损按曲率算），1 = 倒角盒子的平面，2 = 倒角盒子的倒角面。"""
    return bm.faces.layers.int.get("bev") or bm.faces.layers.int.new("bev")


def rbox(bm, sx, sy, sz, M=Matrix(), r=0.002, seg=3):
    """倒圆角的长方体（中心在原点）。r=0 就是普通盒子。
    平面和倒角面分别打上 bev=1/2，导出时据此只在倒角上画棱边磨损（平面上一点不磨）。"""
    res = bmesh.ops.create_cube(bm, size=1.0, matrix=M @ S(sx, sy, sz))
    lay = bev_layer(bm)
    verts = res["verts"]
    for f in {f for v in verts for f in v.link_faces}:
        f[lay] = 1
    if r <= 0:
        return
    r = min(r, sx * 0.45, sy * 0.45, sz * 0.45)
    edges = list({e for v in verts for e in v.link_edges})
    out = bmesh.ops.bevel(bm, geom=verts + edges, offset=r, offset_type='OFFSET', segments=seg, profile=0.5,
                          affect='EDGES', clamp_overlap=True)
    for f in out["faces"]:
        f[lay] = 2


def star_profile(r, n=24, depth=0.06):
    pts = []
    for i in range(n * 2):
        a = math.pi * i / n
        rr = r if i % 2 == 0 else r * (1 - depth)
        pts.append((math.cos(a) * rr, math.sin(a) * rr))
    return pts


def extrude_profile(bm, profile, M, h):
    """2D 剖面沿局部 Z 拉伸 h（带上下盖）。"""
    sweep(bm, [M @ V((0, 0, 0)), M @ V((0, 0, h))], profile, up_hint=(M.to_3x3() @ V((0, 1, 0))))


def path_length(points):
    return sum((V(points[i + 1]) - V(points[i])).length for i in range(len(points) - 1))


# ============================================================================ 面板零件
def screw(K, P, x, y, r=0.0028, key="Steel", rng=random):
    M = P @ T(x, y, 0)
    lathe(K[key], [(r, 0.0), (r, 0.0006), (r * 0.82, 0.0012), (r * 0.45, 0.00155), (0.0, 0.0016)], 12, M)
    a = rng.uniform(0, 180)
    for k in (0, 90):
        box(K["Dark"], r * 1.45, r * 0.26, 0.0005, M @ T(0, 0, 0.0014) @ R(a + k, 'Z'))


def socket_screw(K, P, x, y, r=0.0045, key="Steel"):
    M = P @ T(x, y, 0)
    cylinder(K[key], r, r * 0.9, 20, M)
    cylinder(K["Dark"], r * 0.42, 0.0004, 6, M @ T(0, 0, r * 0.9))


def toggle(K, P, x, y, up=True, guard=False, s=1.0):
    M = P @ T(x, y, 0)
    cylinder(K["Steel"], 0.0075 * s, 0.0008, 20, M)  # 垫圈
    cylinder(K["Steel"], 0.0066 * s, 0.0024, 6, M @ T(0, 0, 0.0008))  # 六角螺母
    cylinder(K["Chrome"], 0.0042 * s, 0.0075 * s, 16, M)  # 螺纹套
    Ml = M @ T(0, 0, 0.0072 * s) @ R(-24 if up else 24, 'X')
    cylinder(K["Chrome"], 0.0022 * s, 0.019 * s, 12, Ml, r2=0.0015 * s)
    uvsphere(K["Chrome"], 0.0024 * s, 12, 6, Ml @ T(0, 0, 0.019 * s))
    if guard:
        for sx in (-1, 1):
            pts = [M @ V((sx * 0.0095, -0.014, 0)), M @ V((sx * 0.0095, -0.012, 0.016)),
                   M @ V((sx * 0.0095, 0.0, 0.026)), M @ V((sx * 0.0095, 0.012, 0.016)),
                   M @ V((sx * 0.0095, 0.014, 0))]
            sweep(K["Chrome"], catmull(pts, 4), circle_profile(0.0012, 8))


def flip_cover(K, P, x, y, color="BtnRed", open_deg=105):
    """红色翻盖保护的关键开关（应急抛载之类）。翻盖在上方铰接、掀开。"""
    toggle(K, P, x, y, up=False)
    M = P @ T(x, y, 0)
    rbox(K["Bakelite"], 0.03, 0.044, 0.004, M @ T(0, 0, 0.002), r=0.0015, seg=2)
    hinge = M @ T(0, 0.022, 0.004) @ R(-open_deg, 'X')
    rbox(K[color], 0.028, 0.044, 0.016, hinge @ T(0, -0.022, 0.008), r=0.003, seg=2)
    cylinder(K["Steel"], 0.0025, 0.032, 12, M @ T(-0.016, 0.022, 0.0045) @ R(90, 'Y'))


def knob(K, P, x, y, r=0.011, h=0.014, skirt=True, ticks=11, sweep_deg=270, key="Knob", line=True):
    """滚花旋钮 + 白色指示线；可选铝裙边和面板刻度。"""
    M = P @ T(x, y, 0)
    if skirt:
        lathe(K["Alu"], [(r * 1.38, 0), (r * 1.38, 0.0018), (r * 1.2, 0.0026), (0, 0.0026)], 32, M)
    extrude_profile(K[key], star_profile(r, 18, 0.07), M, h * 0.8)
    lathe(K[key], [(r * 0.93, h * 0.8), (r * 0.9, h * 0.93), (r * 0.6, h), (0, h)], 36, M)
    if line:
        box(K["Silk"], r * 0.18, r * 0.95, 0.0004, M @ T(0, r * 0.45, h + 0.0001))
    for i in range(ticks):
        a = math.radians(90 + sweep_deg / 2 - sweep_deg * i / max(ticks - 1, 1))
        rr = r * 1.65
        box(K["Silk"], r * 0.35, 0.0007, 0.0003, M @ T(math.cos(a) * rr, math.sin(a) * rr, 0.00015)
            @ R(math.degrees(a), 'Z'))


def pointer_knob(K, P, x, y, r=0.012, angle=0.0, key="Knob"):
    """鸡头旋钮（档位选择开关常用）。angle：指针方向，0 = 朝上。"""
    M = P @ T(x, y, 0) @ R(angle, 'Z')
    lathe(K[key], [(r * 0.95, 0), (r * 0.95, 0.004), (r * 0.8, 0.006), (0, 0.006)], 32, M)
    pts = [(-r * 0.32, -r * 0.9), (r * 0.32, -r * 0.9), (r * 0.42, r * 0.4), (0.0, r * 1.45), (-r * 0.42, r * 0.4)]
    extrude_profile(K[key], pts, M @ T(0, 0, 0.004), 0.011)
    box(K["Silk"], r * 0.12, r * 1.1, 0.0004, M @ T(0, r * 0.65, 0.0152))


def button(K, P, x, y, r=0.0075, cap="BtnBlack", square=False):
    M = P @ T(x, y, 0)
    lathe(K["Chrome"], [(r * 1.45, 0), (r * 1.45, 0.0018), (r * 1.2, 0.0034), (r * 1.04, 0.0034),
                        (r * 1.04, 0.001)], 32, M)
    if square:
        rbox(K[cap], r * 1.8, r * 1.8, 0.008, M @ T(0, 0, 0.004), r=0.0012, seg=2)
    else:
        lathe(K[cap], [(r, 0.0), (r, 0.0065), (r * 0.9, 0.0078), (0, 0.008)], 28, M)


def lamp(K, P, x, y, r=0.0055, lens="LensRed", name=None):
    """指示灯：镀铬灯座 + 有色灯罩。name 不为空时灯罩单独成对象（运行时控制亮灭）。"""
    M = P @ T(x, y, 0)
    lathe(K["Chrome"], [(r * 1.65, 0), (r * 1.65, 0.0024), (r * 1.4, 0.0042), (r * 1.08, 0.0042),
                        (r * 1.08, 0.002)], 32, M)

    def geo(bm):
        lathe(bm, [(r, 0.0015), (r, 0.0055), (r * 0.82, 0.0082), (r * 0.42, 0.0096), (0, 0.0099)], 24, M)
    if name:
        K.separate(name, lens, geo)
    else:
        geo(K[lens])


def vent(K, P, x, y, w, h, n=None, slot=0.003):
    """一排长条散热孔（深色条 + 上沿冲压的一点凸起）。"""
    n = n or max(3, int(h / (slot * 2.6)))
    for i in range(n):
        yy = y - h / 2 + (i + 0.5) * h / n
        box(K["Dark"], w, slot, 0.0004, P @ T(x, yy, 0.0002))


def handle(K, P, x, y, L=0.09, axis='Y', key="Alu", standoff=0.022):
    """机柜把手：两个立柱 + 圆杆。"""
    d = V((0, 1, 0)) if axis == 'Y' else V((1, 0, 0))
    a = P @ (V((x, y, 0)) - d * L / 2)
    b = P @ (V((x, y, 0)) + d * L / 2)
    nz = (P.to_3x3() @ V((0, 0, 1))).normalized()
    pts = [a, a + nz * standoff * 0.8, a + nz * standoff + (b - a) * 0.12, b + nz * standoff - (b - a) * 0.12,
           b + nz * standoff * 0.8, b]
    sweep(K[key], catmull(pts, 5), circle_profile(0.0042, 12))
    for p in (a, b):
        cylinder(K[key], 0.0065, 0.003, 16, frame(p, nz))


def fuse(K, P, x, y, label=None):
    M = P @ T(x, y, 0)
    lathe(K["Bakelite"], [(0.0085, 0), (0.0085, 0.003), (0.0065, 0.0035), (0.0065, 0.012), (0.0058, 0.0135),
                          (0, 0.0135)], 24, M)
    extrude_profile(K["Bakelite"], star_profile(0.0068, 12, 0.08), M @ T(0, 0, 0.006), 0.006)
    box(K["Silk"], 0.0015, 0.007, 0.0004, M @ T(0, 0, 0.0136))
    if label:
        K.text(label, P @ T(x, y - 0.015, 0), 0.0045)


def connector(K, P, x, y, r=0.008, out=(0, -1, 0), plug="Olive", tail=0.035):
    """航空插头：面板方座 + 插座 + 滚花锁紧环 + 尾套。返回线缆出口点和方向（世界坐标）。"""
    M = P @ T(x, y, 0)
    rbox(K["Steel"], r * 2.7, r * 2.7, 0.0025, M @ T(0, 0, 0.00125), r=0.001, seg=1)
    for sx in (-1, 1):
        for sy in (-1, 1):
            screw(K, M, sx * r * 1.05, sy * r * 1.05, r=0.0012)
    cylinder(K["Steel"], r * 0.95, 0.008, 20, M)
    o = V(out).normalized()
    # 插头从面板伸出，然后尾部转向 out 方向
    Mp = M @ T(0, 0, 0.006)
    extrude_profile(K[plug], star_profile(r * 1.18, 20, 0.05), Mp, 0.012)
    cylinder(K[plug], r * 1.02, 0.02, 20, Mp @ T(0, 0, 0.012), r2=r * 0.8)
    nz = (M.to_3x3() @ V((0, 0, 1))).normalized()
    start = Mp @ V((0, 0, 0.03))
    ow = (M.to_3x3() @ o).normalized()
    return start, nz, ow


def label_plate(K, P, x, y, text, size=0.008, plate="LabelPlate", ink="Silk", font=FONT_SANS, pad=0.6):
    """刻字铭牌：黑色塑料小牌 + 白字，两颗小铆钉。"""
    n = sum(1.0 if ord(ch) > 0x2e80 else 0.62 for ch in text)
    w = n * size + size * pad * 2 + 0.006
    h = size * 1.9
    M = P @ T(x, y, 0)
    rbox(K[plate], w, h, 0.0012, M @ T(0, 0, 0.0006), r=0.0005, seg=1)
    for sx in (-1, 1):
        cylinder(K["Steel"], 0.0011, 0.0016, 8, M @ T(sx * (w / 2 - 0.0025), 0, 0))
    K.text(text, M @ T(0, 0, 0.0012), size, key=ink, font=font)
    return w


def silk(K, P, x, y, text, size=0.0065, key="Silk", font=FONT_SANS, align='CENTER'):
    """丝印字（直接印在面板上）。"""
    return K.text(text, P @ T(x, y, 0), size, key=key, font=font, align=align)


def tape_label(K, P, x, y, text, size=0.011, angle=0.0, ink="Marker"):
    """美纹纸胶带 + 马克笔手写字。"""
    n = sum(1.0 if ord(ch) > 0x2e80 else 0.6 for ch in text)
    w = n * size * 1.05 + 0.014
    M = P @ T(x, y, 0) @ R(angle, 'Z')
    rbox(K["MaskTape"], w, size * 1.9, 0.0005, M @ T(0, 0, 0.00025), r=0.0, seg=1)
    K.text(text, M @ T(0, -size * 0.05, 0.0005), size, key=ink, font=FONT_HAND)


def sticky_note(K, P, x, y, lines, size=0.0085, angle=0.0, paper="NoteYellow"):
    """便利贴（7.6cm 方），手写几行字。"""
    M = P @ T(x, y, 0) @ R(angle, 'Z')
    s = 0.072
    rbox(K[paper], s, s, 0.0004, M @ T(0, 0, 0.0002), r=0.0, seg=1)
    for i, ln in enumerate(lines):
        K.text(ln, M @ T(0, s * 0.28 - i * size * 1.55, 0.0004), size, key="Marker", font=FONT_HAND)


# ---------------------------------------------------------------------------- 表头
def meter_rect(K, P, x, y, s, name, hi=50, unit="V", label=None, major=5, sub=5, model="85C1"):
    """方形指针表（国产 85C1 型那种）：黑胶木外框，上部白色表盘窗口，下部黑色调零区。
    指针单独成对象 Needle_<name>，静止时指在刻度起点（左端），绕局部 Z 顺时针转 90° 到满量程。"""
    M0 = P @ T(x, y, 0)
    d = 0.013
    fw = s * 0.075
    win_h = s * 0.6
    low_h = s - win_h - fw
    rbox(K["Bakelite"], s, fw, d, M0 @ T(0, s / 2 - fw / 2, d / 2), r=0.0012, seg=2)
    for sx in (-1, 1):
        rbox(K["Bakelite"], fw, win_h, d, M0 @ T(sx * (s / 2 - fw / 2), s / 2 - fw - win_h / 2, d / 2), r=0.001,
             seg=1)
    rbox(K["Bakelite"], s, low_h, d, M0 @ T(0, -s / 2 + low_h / 2, d / 2), r=0.0012, seg=2)
    # 调零螺丝
    cylinder(K["Bakelite"], s * 0.06, 0.0012, 20, M0 @ T(0, -s / 2 + low_h * 0.45, d))
    box(K["Dark"], s * 0.09, s * 0.012, 0.0004, M0 @ T(0, -s / 2 + low_h * 0.45, d + 0.0012) @ R(30, 'Z'))
    face_w = s - 2 * fw
    cy = s / 2 - fw - win_h / 2
    box(K["MeterFace"], face_w + 0.001, win_h + 0.001, 0.001, M0 @ T(0, cy, 0.003))
    # 刻度弧：圆心在窗口下沿再往下一点（藏在黑色调零区后面）
    py = s / 2 - fw - win_h - s * 0.06
    ra = min(win_h * 0.86, face_w * 0.66)
    n = major * sub
    for i in range(n + 1):
        a = math.radians(135 - 90 * i / n)
        big = i % sub == 0
        L = s * (0.07 if big else 0.04)
        rr = ra + L / 2
        box(K["Ink"], L, s * (0.009 if big else 0.005), 0.0003,
            M0 @ T(math.cos(a) * rr, py + math.sin(a) * rr, 0.0036) @ R(math.degrees(a), 'Z'))
    # 弧线
    arc = [M0 @ V((math.cos(math.radians(a)) * ra, py + math.sin(math.radians(a)) * ra, 0.0036))
           for a in range(45, 136, 3)]
    sweep(K["Ink"], arc, [(-0.0002, -s * 0.003), (0.0002, -s * 0.003), (0.0002, s * 0.003), (-0.0002, s * 0.003)])
    for i in range(major + 1):
        a = math.radians(135 - 90 * i / major)
        rr = ra + s * 0.13
        v = hi * i / major
        txt = f"{v:g}"
        K.text(txt, M0 @ T(math.cos(a) * rr, py + math.sin(a) * rr, 0.0035), s * 0.07, key="Ink")
    K.text(unit, M0 @ T(0, py + ra * 0.55, 0.0035), s * 0.1, key="Ink")
    K.text(model, M0 @ T(-face_w * 0.3, cy - win_h * 0.36, 0.0035), s * 0.04, key="Ink")

    def needle(bm):
        L = ra + s * 0.05
        pts = [(-s * 0.04, -s * 0.012), (L, -s * 0.0025), (L, s * 0.0025), (-s * 0.04, s * 0.012)]
        extrude_profile(bm, pts, Matrix(), 0.0006)
        cylinder(bm, s * 0.025, 0.0012, 16, Matrix())
    nd = K.separate(f"Needle_{name}", "NeedleBlack", needle, sharp=30)
    nd.matrix_world = M0 @ T(0, py, 0.0046) @ R(135, 'Z')
    # 玻璃（单独一桶，导出时合成 GaugeGlass）
    box(K["Glass"], face_w + 0.002, win_h + 0.002, 0.0008, M0 @ T(0, cy, d - 0.0018))
    if label:
        label_plate(K, P, x, y - s / 2 - 0.012, label, size=s * 0.11)


def gauge_round(K, P, x, y, r, name, hi=10, label=None, unit=None, major=10, sub=5, start=225, sweep_deg=270,
                flange=True, numbers_every=1, red_from=None, face="GaugeFace", num_labels=None):
    """圆形仪表：镀铬压圈、表盘、刻度、数字、指针（单独对象）、玻璃。指针静止时指在刻度起点。"""
    M0 = P @ T(x, y, 0)
    if flange:
        cylinder(K["PanelDark"], r * 1.3, 0.003, 48, M0)
        for i in range(3):
            a = math.radians(90 + 120 * i)
            screw(K, M0 @ T(0, 0, 0.003), math.cos(a) * r * 1.18, math.sin(a) * r * 1.18, r=0.0022)
    lathe(K["Chrome"], [(r * 1.1, 0.0), (r * 1.12, 0.008), (r * 1.1, 0.016), (r * 1.06, 0.0185), (r * 1.0, 0.017),
                        (r * 0.99, 0.012)], 64, M0)
    lathe(K["PanelDark"], [(r * 1.0, 0.0), (r * 1.0, 0.004), (0.0, 0.004)], 48, M0)
    cylinder(K[face], r * 0.995, 0.0015, 64, M0 @ T(0, 0, 0.004))
    z = 0.0058
    n = major * sub
    for i in range(n + 1):
        a = math.radians(start - sweep_deg * i / n)
        big = i % sub == 0
        L = r * (0.15 if big else 0.08)
        w = r * (0.03 if big else 0.015)
        rr = r * 0.88 - L / 2
        box(K["Ink"], L, w, 0.0003, M0 @ T(math.cos(a) * rr, math.sin(a) * rr, z) @ R(math.degrees(a), 'Z'))
    if red_from is not None:
        a0, a1 = start - sweep_deg * red_from, start - sweep_deg
        arc = [M0 @ V((math.cos(math.radians(a)) * r * 0.9, math.sin(math.radians(a)) * r * 0.9, z))
               for a in [a0 + (a1 - a0) * k / 16 for k in range(17)]]
        sweep(K["InkRed"], arc, [(-0.0002, -r * 0.025), (0.0002, -r * 0.025), (0.0002, r * 0.025),
                                 (-0.0002, r * 0.025)])
    last = major if sweep_deg < 359 else major - 1  # 360° 表盘最后一个数字和 0 重合
    for i in range(0, last + 1, numbers_every):
        a = math.radians(start - sweep_deg * i / major)
        rr = r * 0.6
        s = num_labels[i] if num_labels else f"{hi * i / major:g}"
        K.text(s, M0 @ T(math.cos(a) * rr, math.sin(a) * rr, z), r * 0.16, key="Ink")
    if label:
        K.text(label, M0 @ T(0, -r * 0.32, z), r * 0.13, key="Ink")
    if unit:
        K.text(unit, M0 @ T(0, r * 0.3, z), r * 0.12, key="Ink")

    def needle(bm):
        pts = [(-r * 0.22, -r * 0.03), (r * 0.84, -r * 0.007), (r * 0.84, r * 0.007), (-r * 0.22, r * 0.03)]
        extrude_profile(bm, pts, Matrix(), 0.0008)
        lathe(bm, [(r * 0.075, 0), (r * 0.075, 0.0025), (r * 0.04, 0.0035), (0, 0.0036)], 20, Matrix())
    nd = K.separate(f"Needle_{name}", "Needle", needle, sharp=30)
    nd.matrix_world = M0 @ T(0, 0, z + 0.0006) @ R(start, 'Z')
    cylinder(K["Glass"], r * 1.0, 0.001, 64, M0 @ T(0, 0, 0.0145))


def seg_display(K, P, x, y, w, h, name):
    """数码管窗口：黑框 + 深红滤光片；Godot 里在 Display_<name> 挂 Label3D 显示数字。"""
    M = P @ T(x, y, 0)
    rbox(K["Bakelite"], w + 0.014, h + 0.014, 0.008, M @ T(0, 0, 0.004), r=0.0015, seg=2)
    box(K["LedWindow"], w, h, 0.0012, M @ T(0, 0, 0.0082))
    empty(f"Display_{name}", K.coll, M @ T(0, 0, 0.0092) @ R(-90, 'X'), 0.02)


def annunciator(K, P, x, y, labels, cols=4, tw=0.052, th=0.028, first=0):
    """报警灯牌：格子里是半透明灯片 + 黑字，灯片单独成对象 Warn_<n>。"""
    rows = (len(labels) + cols - 1) // cols
    W, H = cols * tw + 0.012, rows * th + 0.012
    M = P @ T(x, y, 0)
    rbox(K["Bakelite"], W, H, 0.014, M @ T(0, 0, 0.007), r=0.002, seg=2)
    for k, lb in enumerate(labels):
        r_, c_ = divmod(k, cols)
        cx = -W / 2 + 0.006 + tw * (c_ + 0.5)
        cy = H / 2 - 0.006 - th * (r_ + 0.5)
        Mt = M @ T(cx, cy, 0.0135)

        def tile(bm, Mt=Mt):
            rbox(bm, tw - 0.004, th - 0.004, 0.003, Mt, r=0.0006, seg=1)
        K.separate(f"Warn_{first + k}", "Warn", tile, smooth=False)
        K.text(lb, Mt @ T(0, 0, 0.0016), th * 0.36, key="Ink")
    return W, H


def rotameter(K, P, x, y, h, name, hi=10, label=None):
    """氧气流量计：竖直玻璃管 + 红色浮子（单独对象 Float_<name>，在 Godot 里上下浮动）+ 刻度。"""
    M = P @ T(x, y, 0)
    rbox(K["Alu"], 0.034, h + 0.04, 0.004, M @ T(0, 0, 0.002), r=0.001, seg=1)
    up = R(-90, 'X')  # 局部 Z 转成沿面板 +Y
    for sy in (-1, 1):
        # 上下两个黄铜接头，再各有一根小管弯进面板
        cylinder(K["Brass"], 0.011, 0.016, 16, M @ T(0, sy * (h / 2 + 0.008), 0.004))
        cylinder(K["Brass"], 0.0095, 0.012, 6, M @ T(0, sy * (h / 2 + 0.008), 0.004) @ up @ T(0, 0, -0.006))
    lathe(K["GlassTube"], [(0.0075, 0), (0.0075, h)], 24, M @ T(0, -h / 2, 0.012) @ up)
    for i in range(hi + 1):
        yy = -h / 2 + h * 0.08 + h * 0.84 * i / hi
        big = i % 2 == 0
        box(K["Silk"], 0.006 if big else 0.0035, 0.0007, 0.0003, M @ T(0.0115 - (0.0 if big else 0.001), yy, 0.0041))
        if big:
            K.text(str(i), M @ T(-0.0125, yy, 0.0041), 0.004)

    def flt(bm):
        lathe(bm, [(0.0, -0.004), (0.0055, 0.0), (0.0055, 0.002), (0.0, 0.0035)], 16, Matrix())
    f = K.separate(f"Float_{name}", "FloatRed", flt)
    # 浮子的局部 Z 沿玻璃管向上（Godot 里是局部 Y）
    f.matrix_world = M @ T(0, -h / 2 + h * 0.08, 0.012) @ up
    # 底部针阀旋钮
    knob(K, P, x, y - h / 2 - 0.03, r=0.009, h=0.012, skirt=False, ticks=0)
    if label:
        silk(K, P, x, y + h / 2 + 0.026, label, 0.006)


def valve_wheel(K, M, r=0.035, key="BtnRed", spokes=4):
    """手轮阀：轮缘、辐条、轮毂、阀杆。M 的 Z 是阀杆方向。"""
    cylinder(K["Brass"], 0.007, 0.04, 16, M)
    torus(K[key], r, r * 0.12, 40, 10, M @ T(0, 0, 0.04))
    cylinder(K[key], r * 0.25, 0.014, 20, M @ T(0, 0, 0.033))
    for i in range(spokes):
        a = 2 * math.pi * (i + 0.5) / spokes
        sweep(K[key], [M @ V((0, 0, 0.04)), M @ V((math.cos(a) * r, math.sin(a) * r, 0.04))],
              circle_profile(r * 0.07, 8))


# ============================================================================ 设备箱
def unit(K, F, w, h, d, body="EquipGreen", face="PanelDark", handles=True, screws=True, lip=0.004):
    """标准设备箱：箱体 + 稍大一圈的前面板（四角螺丝）+ 两侧把手。返回前面板坐标系（面板正面 z=0）。"""
    rbox(K[body], w, h, d - 0.004, F @ T(0, 0, -d / 2 - 0.002), r=0.004, seg=3)
    rbox(K[face], w + lip * 2, h + lip * 2, 0.004, F @ T(0, 0, -0.002), r=0.0012, seg=2)
    if screws:
        for sx in (-1, 1):
            for sy in (-1, 1):
                screw(K, F, sx * (w / 2 - 0.006), sy * (h / 2 - 0.006))
    if handles:
        L = min(0.1, h * 0.6)
        for sx in (-1, 1):
            handle(K, F, sx * (w / 2 - 0.018), 0, L)
    return F


# ============================================================================ 线缆
class Cables:
    def __init__(self, rng):
        self.items = []  # (points, r, key)
        self.loops = []  # (闭合路径, 线束走向, key, 锁扣坐标系)：扁平线束上的扎带
        self.rng = rng

    def add(self, pts, r, key="CableBlack", samples=6):
        pts = catmull(pts, samples) if len(pts) > 2 else [V(p) for p in pts]
        self.items.append((pts, r, key))

    def run(self, start, direction, end, r=0.004, key="CableBlack", sag=0.05):
        """从接插件出口沿 direction 伸出一点，再垂下来接到 end。"""
        s = V(start)
        e = V(end)
        d = V(direction).normalized()
        p1 = s + d * 0.03
        mid = (p1 + e) / 2 - V((0, 0, sag))
        self.add([s, p1, mid, e], r, key)

    def ribbon(self, path, n0, layers, ties=(), samples=6, gap=0.0025, wobble=0.0008, under=0.0085,
               tie_key="Zip"):
        """扁平线束：电缆一根挨一根平铺在支承面（桥架横档）上，可以叠几层；拐弯时整排一起弯，不拧麻花。
        path：支承面上的中心线；n0：起点处支承面的法线（电缆铺在这一侧）。
        layers：[[电缆, ...], ...]，第 0 层贴着支承面。电缆是 (r, key)，或者 (r, key, s0, lead)——
          中途并进来的：s0 是并进来处的弧长，lead 是并进来之前的走线点（从接插件出来、翻过桥架边梁）。
        ties：扎带位置（弧长），扎带连横档一起捆（under 是横档厚度加一点余量）。
        返回 dict：center（中心线）、frames（每点的 (t, n, w)）、arc（弧长）、width、height。"""
        center = catmull(path, samples) if len(path) > 2 else [V(p) for p in path]
        fr = []
        n = V(n0)
        prev = None
        for i in range(len(center)):
            t = (center[min(i + 1, len(center) - 1)] - center[max(i - 1, 0)]).normalized()
            n = (n - t * n.dot(t)).normalized() if prev is None else (prev.rotation_difference(t) @ n).normalized()
            prev = t
            fr.append((t, n, t.cross(n)))
        arc = [0.0]
        for i in range(1, len(center)):
            arc.append(arc[-1] + (center[i] - center[i - 1]).length)

        def at(s):
            i = min(range(len(arc)), key=lambda j: abs(arc[j] - s))
            return center[i], fr[i]
        # 截面排布：每层从中线往两边摊开，上一层压在下一层最粗的那根上面
        slots = []
        base = width = 0.0
        for layer in layers:
            w = sum(2 * c[0] for c in layer) + gap * (len(layer) - 1)
            width = max(width, w)
            u = -w / 2
            for c in layer:
                slots.append((u + c[0], base + c[0], c))
                u += 2 * c[0] + gap
            base += 2 * max(c[0] for c in layer)
        for u0, h, c in slots:
            r, key = c[0], c[1]
            s0, lead = (c[2], c[3]) if len(c) > 2 else (-1.0, [])
            ph, fq = self.rng.uniform(0, 6.28), self.rng.uniform(5, 9)
            body = [p + w_ * (u0 + math.sin(arc[i] * fq + ph) * wobble) + n_ * h
                    for i, (p, (t, n_, w_)) in enumerate(zip(center, fr)) if arc[i] >= s0]
            if lead:
                # 先在高处横移到自己槽位的正上方，再竖着落下去（落的时候不再横移，不会蹭到边梁）
                p1, (t1, n1, w1) = at(s0 - 0.1)
                p2, (t2, n2, w2) = at(s0 - 0.05)
                k = min(3, len(body) - 1)
                pts = catmull([V(q) for q in lead] + [p1 + w1 * u0 + n1 * (h + 0.05), p2 + w2 * u0 + n2 * (h + 0.02),
                                                      body[0], body[k]], 6)[:-1] + body[k:]
            else:
                pts = body
            self.items.append((pts, r, key))
        for s in ties:
            p, (t, n_, w_) = at(s)
            hu, top, rc = width / 2 + 0.003, base + 0.0015, 0.003
            loop = []
            for cu, cn, a0 in ((hu - rc, top - rc, 0), (-hu + rc, top - rc, 90), (-hu + rc, -under + rc, 180),
                               (hu - rc, -under + rc, 270)):
                for k in range(4):
                    a = math.radians(a0 + 30 * k)
                    loop.append(p + w_ * (cu + math.cos(a) * rc) + n_ * (cn + math.sin(a) * rc))
            self.loops.append((loop, t, tie_key, frame(p + w_ * (hu + 0.0025) + n_ * (top * 0.5), w_)))
        return {"center": center, "frames": fr, "arc": arc, "width": width, "height": base}

    def build(self, K):
        for pts, r, key in self.items:
            segs = 8 if r < 0.004 else 10 if r < 0.008 else 14
            sweep(K[key], pts, circle_profile(r, segs))
        for loop, t, key, head in self.loops:
            sweep(K[key], loop, [(-0.0006, -0.0022), (0.0006, -0.0022), (0.0006, 0.0022), (-0.0006, 0.0022)],
                  closed=True, up_hint=t)
            rbox(K[key], 0.005, 0.006, 0.005, head, r=0.0, seg=1)
