"""岸上场景（宿舍 gen_dorm.py、办事处 gen_office.py）共用的建模零件和导出。

- Room：房间壳子。四面墙按开的洞（门、窗）切成格子：下半截墙裙、上半截白灰墙，踢脚线、墙裙上沿一道线，
  洞口四周的侧壁（窗台、门框里侧）和外墙皮；地面、天花板
- 门窗：老式木门（门框、门扇、插销、球形锁）、木窗（推拉的两扇 + 上亮子）和钢窗（细钢框分很多格）
- 九十年代老楼里的东西：明线（瓷夹板固定的花线）、拉线开关、扳把开关、两眼插座、日光灯（灯架 + 灯管 + 启辉器）、
  三叶吊扇（转子单独成对象 Spin_*，Godot 里转）、挂历、相框、暖水瓶、盖碗、搪瓷脸盆
- 挂点：Anchor_*（摆 Poly Haven 道具，道具正面朝 facing）、Light_*（灯）、Decal_*（贴花）、Use_*（能按 E 的东西）、
  Seat_* / SeatStand_*（坐的地方：坐着时眼睛的位置和朝向 / 站起来站哪）、Walk_*（能站的矩形）、Spawn（开场站哪）
- 导出：和 gen_submarine.py 一样烘焙曲率顶点色、按材质合并；名字以 KEEP 里的前缀开头的单独成对象

坐标：Blender +Y 朝北（从门口往里看大致的方向），+X 朝东，+Z 朝上，地面 z = 0。导出到 Godot 后 -Z 朝北。
"""
import math
import os
import random

import bpy
from mathutils import Vector as V, Matrix

from lib import (material, frame, T, R, S, cylinder, box, uvsphere, lathe, torus, catmull, circle_profile,
                 rect_profile, sweep, empty, bake_for_export, join, export_glb, stats, text_mesh)
from kit import Parts, rbox, extrude_profile, FONT_SANS, FONT_SERIF, FONT_HAND, FONT_BRUSH

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# 导出时不合并的对象（Godot 里要单独控制：转的、换贴图的、镜面、玻璃、门）
KEEP = ("Spin_", "Paper_", "Mirror_", "Glass_", "Door_", "Lamp_", "Hide_", "Tube_")


# ============================================================================ 材质（只给预览用，正式外观见 setup_project.gd）
def materials(M):
    def add(key, name, color, metal=0.0, rough=0.6, emission=None, strength=1.0, alpha=1.0):
        if key not in M:
            M[key] = material(name, color, metal, rough, emission, strength, alpha)
    # 墙、地、顶
    add("Plaster", "M_Plaster", (0.82, 0.8, 0.74), 0.0, 0.9)
    add("Ceiling", "M_Ceiling", (0.84, 0.83, 0.78), 0.0, 0.95)
    add("Facade", "M_Facade", (0.55, 0.54, 0.5), 0.0, 0.95)
    add("DadoGreen", "M_DadoGreen", (0.3, 0.45, 0.38), 0.0, 0.4)
    add("DadoLine", "M_DadoLine", (0.12, 0.2, 0.16), 0.0, 0.4)
    add("Skirt", "M_Skirt", (0.25, 0.25, 0.24), 0.0, 0.7)
    add("FloorPaint", "M_FloorPaint", (0.33, 0.12, 0.09), 0.0, 0.5)
    add("Terrazzo", "M_Terrazzo", (0.6, 0.6, 0.58), 0.0, 0.3)
    add("Wainscot", "M_Wainscot", (0.22, 0.12, 0.07), 0.0, 0.4)
    # 木头
    add("WoodDark", "M_WoodDark", (0.2, 0.1, 0.05), 0.0, 0.35)
    add("WoodLight", "M_WoodLight", (0.55, 0.38, 0.2), 0.0, 0.45)
    add("WoodRaw", "M_WoodRaw", (0.5, 0.38, 0.25), 0.0, 0.8)
    add("DoorBlue", "M_DoorBlue", (0.45, 0.6, 0.6), 0.0, 0.45)
    add("WindowWood", "M_WindowWood", (0.62, 0.66, 0.6), 0.0, 0.5)
    add("WindowSteel", "M_WindowSteel", (0.28, 0.34, 0.3), 0.4, 0.5)
    add("IronBar", "M_IronBar", (0.1, 0.1, 0.1), 0.6, 0.6)
    add("Bamboo", "M_Bamboo", (0.6, 0.5, 0.3), 0.0, 0.6)
    # 小东西
    add("Porcelain", "M_Porcelain", (0.9, 0.89, 0.85), 0.0, 0.15)
    add("Enamel", "M_Enamel", (0.88, 0.88, 0.84), 0.0, 0.2)
    add("Bakelite", "M_Bakelite", (0.03, 0.025, 0.022), 0.0, 0.35)
    add("BakeliteBrown", "M_BakeliteBrown", (0.18, 0.08, 0.04), 0.0, 0.35)
    add("Steel", "M_Steel", (0.55, 0.55, 0.55), 1.0, 0.4)
    add("Chrome", "M_Chrome", (0.8, 0.8, 0.8), 1.0, 0.15)
    add("Brass", "M_Brass", (0.72, 0.52, 0.22), 1.0, 0.35)
    add("FixtureWhite", "M_FixtureWhite", (0.8, 0.8, 0.76), 0.2, 0.5)
    add("FanCream", "M_FanCream", (0.75, 0.72, 0.62), 0.2, 0.45)
    add("Tube", "M_Tube", (0.95, 0.97, 0.95), 0.0, 0.3, emission=(0.9, 1.0, 0.95), strength=3)
    add("Wire", "M_Wire", (0.6, 0.55, 0.45), 0.0, 0.6)
    add("WireBlack", "M_CableBlack", (0.025, 0.025, 0.025), 0.0, 0.55)
    add("Dark", "M_Dark", (0.01, 0.01, 0.01), 0.0, 0.9)
    add("Glass", "M_Glass", (0.55, 0.7, 0.68), 0.0, 0.05, alpha=0.12)
    add("WinGlass", "M_WindowGlass", (0.6, 0.65, 0.65), 0.0, 0.05, alpha=0.2)
    add("Mirror", "M_Mirror", (0.8, 0.8, 0.78), 1.0, 0.08)
    add("PaperWhite", "M_PaperWhite", (0.86, 0.84, 0.78), 0.0, 0.9)
    add("Paper", "M_Paper", (0.85, 0.7, 0.25), 0.0, 0.9)
    add("Newspaper", "M_Newspaper", (0.72, 0.68, 0.58), 0.0, 0.9)
    add("Ink", "M_GaugeInk", (0.02, 0.02, 0.02), 0.0, 0.5)
    add("InkRed", "M_InkRed", (0.7, 0.05, 0.03), 0.0, 0.5)
    add("Silk", "M_Silk", (0.85, 0.84, 0.78), 0.0, 0.6)
    add("RedLacquer", "M_RedLacquer", (0.3, 0.03, 0.02), 0.0, 0.35)
    add("ThermosRed", "M_ThermosRed", (0.5, 0.06, 0.05), 0.2, 0.45)
    add("Cork", "M_Cork", (0.5, 0.36, 0.22), 0.0, 0.9)
    add("Rubber", "M_Rubber", (0.02, 0.02, 0.02), 0.0, 0.8)
    add("Rope", "M_Rope", (0.6, 0.55, 0.45), 0.0, 0.9)
    add("ClothRed", "M_ClothRed", (0.5, 0.02, 0.02), 0.0, 0.9)
    add("Tea", "M_Tea", (0.12, 0.05, 0.015), 0.0, 0.05)
    add("TeaStain", "M_TeaStain", (0.4, 0.24, 0.1), 0.0, 0.7)
    add("Ash", "M_Ash", (0.35, 0.33, 0.3), 0.0, 0.95)
    add("Incense", "M_Incense", (0.35, 0.12, 0.06), 0.0, 0.8)
    add("Ember", "M_Ember", (1.0, 0.3, 0.05), 0.0, 0.5, emission=(1, 0.3, 0.05), strength=4)
    add("Gold", "M_Gold", (0.78, 0.56, 0.2), 1.0, 0.3)
    add("BrushRed", "M_BrushRed", (0.55, 0.02, 0.01), 0.0, 0.7)
    add("Candle", "M_Candle", (0.6, 0.05, 0.03), 0.0, 0.5)
    add("Pewter", "M_Pewter", (0.5, 0.5, 0.48), 0.9, 0.45)
    add("Cardboard", "M_Cardboard", (0.5, 0.36, 0.2), 0.0, 0.9)
    add("BtnRed", "M_BtnRed", (0.6, 0.04, 0.02), 0.0, 0.35)
    add("LampGlass", "M_LampGlass", (0.95, 0.9, 0.8), 0.0, 0.2, emission=(1, 0.9, 0.7), strength=3)
    return M


# ============================================================================ 挂点
def anchor(anchors, coll, name, pos, facing=(0, -1, 0), up=(0, 0, 1)):
    """道具挂点：Godot 里道具的正面（Poly Haven 模型的正面是 Godot +Z）朝 facing。"""
    y = -V(facing).normalized()
    x = y.cross(V(up)).normalized()
    z = x.cross(y).normalized()
    m = Matrix(((x.x, y.x, z.x, pos[0]), (x.y, y.y, z.y, pos[1]), (x.z, y.z, z.z, pos[2]), (0, 0, 0, 1)))
    anchors.append(empty(name, coll, m))
    return anchors[-1]


def look_frame(pos, look, up=(0, 0, 1)):
    """挂点的 Blender +Y 朝 look：导出后 Godot 的 -Z 朝 look（灯、坐着时的眼睛这类「朝向」挂点）。"""
    y = V(look).normalized()
    x = y.cross(V(up)).normalized()
    z = x.cross(y).normalized()
    return Matrix(((x.x, y.x, z.x, pos[0]), (x.y, y.y, z.y, pos[1]), (x.z, y.z, z.z, pos[2]), (0, 0, 0, 1)))


def light(anchors, coll, name, pos, look=(0, 0, -1)):
    anchors.append(empty(name, coll, look_frame(pos, look, (0, 1, 0) if abs(look[2]) > 0.9 else (0, 0, 1))))


def use(anchors, coll, name, pos):
    """能按 E 的东西（Godot 里在这里放 Interactable，参数在场景脚本里配）。"""
    anchors.append(empty(f"Use_{name}", coll, T(*pos)))


def seat(anchors, coll, name, eye, look, stand):
    """坐的地方：eye 是坐着时眼睛的位置，look 是面朝的方向；stand 是站起来以后站的位置（地面上）。"""
    anchors.append(empty(f"Seat_{name}", coll, look_frame(eye, (look[0], look[1], 0))))
    anchors.append(empty(f"SeatStand_{name}", coll, T(*stand)))


def walk(anchors, coll, x0, x1, y0, y1):
    """能站的一块矩形（Godot 里拼成 RoomWalker.walk_areas）：挂点在矩形中心，缩放就是长宽。"""
    n = sum(1 for a in anchors if a.name.startswith("Walk_"))
    anchors.append(empty(f"Walk_{n:02d}", coll, T((x0 + x1) / 2, (y0 + y1) / 2, 0) @ S(x1 - x0, y1 - y0, 1)))


def spawn(anchors, coll, pos, look):
    anchors.append(empty("Spawn", coll, look_frame(pos, look)))


def decal(anchors, coll, kind, pos, normal, up, w, h, depth=0.06):
    """贴花挂点（同 cockpit.py 的 decal）：缩放就是贴花的尺寸（X 宽、Y 高、Z 投射深度）。"""
    n = sum(1 for a in anchors if a.name.startswith(f"Decal_{kind}_"))
    anchors.append(empty(f"Decal_{kind}_{n:02d}", coll, frame(V(pos), V(normal), V(up)) @ S(w, h, depth)))


# ============================================================================ 房间壳子
class Room:
    """长方形房间：x0..x1、y0..y1、高 h，墙厚 t（洞口的侧壁有这么深）。
    墙的局部坐标：u 是站在屋里面朝这面墙时从左往右，v 是高度；opening() 在墙上开洞。"""

    SIDES = ("N", "E", "S", "W")

    def __init__(self, K, anchors, x0, x1, y0, y1, h, t=0.24):
        self.K, self.anchors = K, anchors
        self.x0, self.x1, self.y0, self.y1, self.h, self.t = x0, x1, y0, y1, h, t
        self.holes = {s: [] for s in self.SIDES}

    def wall(self, side):
        """返回 (原点（左下角）, u 方向, 朝屋里的法线, 墙长)。"""
        x0, x1, y0, y1 = self.x0, self.x1, self.y0, self.y1
        return {
            "N": (V((x0, y1, 0)), V((1, 0, 0)), V((0, -1, 0)), x1 - x0),
            "E": (V((x1, y1, 0)), V((0, -1, 0)), V((-1, 0, 0)), y1 - y0),
            "S": (V((x1, y0, 0)), V((-1, 0, 0)), V((0, 1, 0)), x1 - x0),
            "W": (V((x0, y0, 0)), V((0, 1, 0)), V((1, 0, 0)), y1 - y0),
        }[side]

    def at(self, side, u, v, d=0.0):
        """墙面上 (u, v) 处、离墙面 d 米（往屋里）的点。"""
        o, du, n, _ = self.wall(side)
        return o + du * u + V((0, 0, v)) + n * d

    def frame(self, side, u, v, d=0.0):
        """贴在墙面上的坐标系：Z 朝屋里，Y 朝上，X 朝 u 方向。"""
        o, du, n, _ = self.wall(side)
        return frame(self.at(side, u, v, d), n, V((0, 0, 1)))

    def opening(self, side, u0, u1, v0, v1, reveal="Plaster", sill=None, outer=True):
        self.holes[side].append((u0, u1, v0, v1, reveal, sill, outer))

    # ------------------------------------------------------------------ 墙面
    def walls(self, upper="Plaster", dado=None, dado_h=1.2, line=None, skirt=None, skirt_h=0.14, facade="Facade"):
        K = self.K
        for side in self.SIDES:
            o, du, n, L = self.wall(side)
            holes = self.holes[side]
            us = sorted({0.0, L, *[x for hh in holes for x in hh[:2]]})
            vs = sorted({0.0, self.h, *[x for hh in holes for x in hh[2:4]],
                         *([dado_h] if dado else []), *([skirt_h] if skirt else [])})
            for i in range(len(us) - 1):
                for j in range(len(vs) - 1):
                    uc, vc = (us[i] + us[i + 1]) / 2, (vs[j] + vs[j + 1]) / 2
                    if any(hh[0] < uc < hh[1] and hh[2] < vc < hh[3] for hh in holes):
                        continue
                    key = dado if (dado and vc < dado_h) else upper
                    self._quad(K[key], o, du, n, us[i], us[i + 1], vs[j], vs[j + 1])
            # 墙裙上沿一道线、踢脚线（凸出来一点），遇到门洞断开
            for key, z0, z1, d in ((line, dado_h - 0.012, dado_h + 0.012, 0.004),
                                   (skirt, 0.0, skirt_h, 0.012)):
                if not key or (key == line and not dado):
                    continue
                for a, b in self._spans(side, L, z0, z1):
                    M = frame(o + du * ((a + b) / 2) + V((0, 0, (z0 + z1) / 2)) + n * (d / 2), n, V((0, 0, 1)))
                    rbox(K[key], b - a, z1 - z0, d, M, r=min(0.003, d * 0.4), seg=1)
            # 洞口：四周的侧壁、窗台，外墙皮
            for (u0, u1, v0, v1, reveal, sill, outer) in holes:
                t = self.t
                P = lambda u, v, d: o + du * u + V((0, 0, v)) - n * d  # noqa: E731
                bm = K[reveal]
                hc = P((u0 + u1) / 2, (v0 + v1) / 2, t / 2)
                for (ua, va), (ub, vb) in (((u0, v0), (u0, v1)), ((u1, v1), (u1, v0)), ((u0, v1), (u1, v1)),
                                           ((u1, v0), (u0, v0))):
                    if v0 <= 0.001 and va == vb == v0:
                        continue   # 门洞没有下沿
                    vs_ = [bm.verts.new(P(ua, va, 0)), bm.verts.new(P(ub, vb, 0)), bm.verts.new(P(ub, vb, t)),
                           bm.verts.new(P(ua, va, t))]
                    f = bm.faces.new(vs_)
                    f.normal_update()
                    if f.normal.dot(hc - f.calc_center_median()) < 0:   # 侧壁朝洞口里面
                        f.normal_flip()
                if sill:
                    # 窗台：比墙面凸出来一点的一块板
                    M = frame(o + du * ((u0 + u1) / 2) + V((0, 0, v0 - 0.02)) - n * (t / 2 - 0.03), V((0, 0, 1)), n)
                    rbox(K[sill], u1 - u0 + 0.08, t + 0.06, 0.04, M, r=0.004, seg=2)
                if outer:
                    m = 1.2
                    for (a0, a1, b0, b1) in ((u0 - m, u0, v0 - m, v1 + m), (u1, u1 + m, v0 - m, v1 + m),
                                             (u0, u1, v1, v1 + m), (u0, u1, v0 - m, v0)):
                        if b1 <= 0.0:
                            continue
                        self._quad(K[facade], o - n * t, du, -n, a0, a1, max(b0, -0.5), b1)

    def _spans(self, side, L, z0, z1):
        """沿墙长 0..L，除掉和 [z0, z1] 重叠的洞口，剩下的几段。"""
        cuts = sorted((hh[0], hh[1]) for hh in self.holes[side] if hh[2] < z1 and hh[3] > z0)
        out, a = [], 0.0
        for c0, c1 in cuts:
            if c0 > a:
                out.append((a, c0))
            a = max(a, c1)
        if a < L:
            out.append((a, L))
        return out

    def _quad(self, bm, o, du, n, u0, u1, v0, v1, flip=False):
        """墙面上的一块：分成边长不超过 0.5 米的小格（顶点色、积灰、冷凝这些按顶点算，不能太稀）。"""
        nu = max(1, int(math.ceil((u1 - u0) / 0.5)))
        nv = max(1, int(math.ceil((v1 - v0) / 0.5)))
        grid = [[bm.verts.new(o + du * (u0 + (u1 - u0) * i / nu) + V((0, 0, v0 + (v1 - v0) * j / nv)))
                 for i in range(nu + 1)] for j in range(nv + 1)]
        for j in range(nv):
            for i in range(nu):
                f = [grid[j][i], grid[j][i + 1], grid[j + 1][i + 1], grid[j + 1][i]]
                if flip:
                    f.reverse()
                face = bm.faces.new(f)
                face.normal_update()
                if (face.normal.dot(n) < 0) != flip:
                    face.normal_flip()

    def floor(self, key, step=0.5):
        bm = self.K[key]
        nx = max(1, int(math.ceil((self.x1 - self.x0) / step)))
        ny = max(1, int(math.ceil((self.y1 - self.y0) / step)))
        g = [[bm.verts.new((self.x0 + (self.x1 - self.x0) * i / nx, self.y0 + (self.y1 - self.y0) * j / ny, 0.0))
              for i in range(nx + 1)] for j in range(ny + 1)]
        for j in range(ny):
            for i in range(nx):
                bm.faces.new([g[j][i], g[j][i + 1], g[j + 1][i + 1], g[j + 1][i]])

    def ceiling(self, key, step=0.5):
        bm = self.K[key]
        nx = max(1, int(math.ceil((self.x1 - self.x0) / step)))
        ny = max(1, int(math.ceil((self.y1 - self.y0) / step)))
        g = [[bm.verts.new((self.x0 + (self.x1 - self.x0) * i / nx, self.y0 + (self.y1 - self.y0) * j / ny, self.h))
              for i in range(nx + 1)] for j in range(ny + 1)]
        for j in range(ny):
            for i in range(nx):
                bm.faces.new([g[j][i], g[j + 1][i], g[j + 1][i + 1], g[j][i + 1]])


# ============================================================================ 门
def wood_door(K, F, w, h, leaf="DoorBlue", jamb="DoorBlue", open_deg=0.0, hinge_right=True, name="Door_Leaf",
              knob=True, bolt=True, number=None):
    """老式木门：门框（贴脸）+ 门扇（四块凹进去的门芯板）+ 球形锁 + 插销。
    F：门洞底边中点的坐标系（Z 朝屋里、Y 朝上）。门扇单独成对象 name（原点在门轴上，Godot 里绕 Y 转）。"""
    # 门框贴脸：门洞三边一圈 6 厘米宽的木条，压在墙面上
    for (cx, cy, sx, sy) in ((-w / 2 - 0.03, h / 2 + 0.03, 0.06, h + 0.06), (w / 2 + 0.03, h / 2 + 0.03, 0.06, h + 0.06),
                             (0, h + 0.03, w + 0.12, 0.06)):
        rbox(K[jamb], sx, sy, 0.02, F @ T(cx, cy, 0.01), r=0.004, seg=2)
    # 门扇：放在门洞里，往屋里开（open_deg>0）
    hx = w / 2 - 0.005 if hinge_right else -w / 2 + 0.005
    sgn = -1 if hinge_right else 1
    th = 0.04
    lw, lh = w - 0.01, h - 0.01

    def leaf_geo(bm):
        L = T(sgn * lw / 2, lh / 2 + 0.005, -th / 2)   # 门扇局部：原点在门轴，门扇往 sgn 方向伸
        # 框（冒头、边梃）+ 四块门芯板（凹进去 1 厘米）
        for (cx, cy, sx, sy) in ((0, lh / 2 - 0.06, lw, 0.12), (0, -lh / 2 + 0.1, lw, 0.2), (0, 0.05, lw, 0.1),
                                 (-lw / 2 + 0.05, 0, 0.1, lh), (lw / 2 - 0.05, 0, 0.1, lh), (0, 0, 0.06, lh)):
            rbox(bm, sx, sy, th, L @ T(cx, cy, 0), r=0.003, seg=2)
        for cy, ph in ((0.05 + 0.05 + (lh / 2 - 0.12 - 0.1) / 2, lh / 2 - 0.12 - 0.1),
                       (-lh / 2 + 0.2 + (lh / 2 - 0.2 - 0.0) / 2, lh / 2 - 0.2)):
            for cx in (-(lw / 2 - 0.1 + 0.03) / 2 - 0.0, (lw / 2 - 0.1 + 0.03) / 2):
                pw = lw / 2 - 0.1 - 0.03
                rbox(bm, pw, ph, th - 0.02, L @ T(cx * 0.98, cy, 0), r=0.002, seg=1)
    door = K.separate(name, leaf, leaf_geo)
    door.matrix_world = F @ T(hx, 0, -0.02) @ R(sgn * -open_deg, 'Y')
    hw = []
    if knob:
        # 球形锁：屋里屋外各一个球，中间锁舌（门扇局部，离门边 6 厘米、高 1 米）
        def knob_geo(bm):
            # 门扇局部：屋里那面在 z=0，外面那面在 z=-th
            for d in (1, -1):
                Mk = T(sgn * (lw - 0.065), 1.0, 0.0 if d > 0 else -th) @ R(0 if d > 0 else 180, 'X')
                cylinder(bm, 0.032, 0.006, 24, Mk)
                lathe(bm, [(0.0, 0.0), (0.012, 0.0), (0.012, 0.02), (0.026, 0.035), (0.028, 0.05), (0.02, 0.065),
                           (0.0, 0.068)], 28, Mk)
        hw.append(K.separate(name + "_Knob", "Brass", knob_geo))
    if bolt:
        # 插销：门扇屋里那面上方一根铁插销
        def bolt_geo(bm):
            Mb = T(sgn * (lw - 0.07), lh - 0.25, 0.006)
            rbox(bm, 0.03, 0.14, 0.008, Mb, r=0.002, seg=1)
            cylinder(bm, 0.006, 0.16, 12, Mb @ T(0, -0.06, 0.008) @ R(-90, 'X'))
            cylinder(bm, 0.004, 0.02, 8, Mb @ T(0.012, 0.0, 0.01))
        hw.append(K.separate(name + "_Bolt", "Steel", bolt_geo))
    for o in hw:
        o.matrix_world = door.matrix_world   # Godot 里挂到门扇下面跟着转
    return door, hw


# ============================================================================ 窗
def wood_window(K, F, w, h, frame_key="WindowWood", glass="WinGlass", transom=0.35, open_deg=(0, 0), name="Window"):
    """木窗：外框 + 上亮子（固定）+ 下面两扇对开的窗扇（往外推开，open_deg 是左右两扇开的角度）。
    F：窗洞中心的坐标系（Z 朝屋里，Y 朝上），窗框装在墙厚中间偏外。"""
    fw = 0.05
    for (cx, cy, sx, sy) in ((0, h / 2 - fw / 2, w, fw), (0, -h / 2 + fw / 2, w, fw), (-w / 2 + fw / 2, 0, fw, h),
                             (w / 2 - fw / 2, 0, fw, h), (0, h / 2 - transom, w, 0.05)):
        rbox(K[frame_key], sx, sy, 0.06, F @ T(cx, cy, 0), r=0.004, seg=2)
    # 上亮子：两块玻璃
    ty = h / 2 - transom / 2
    rbox(K[frame_key], 0.035, transom, 0.05, F @ T(0, ty, 0), r=0.003, seg=1)
    for sx in (-1, 1):
        box(K[glass], w / 2 - 0.06, transom - 0.08, 0.003, F @ T(sx * w / 4, ty, 0))
    # 两扇窗扇
    sh = h - transom - fw
    sw = w / 2 - fw
    leaves = []
    for k, sx in enumerate((-1, 1)):
        hinge = F @ T(sx * (w / 2 - fw), -h / 2 + fw + sh / 2, -0.01)

        def sash(bm, sx=sx):
            L = T(-sx * sw / 2, 0, 0)
            for (cx, cy, ssx, ssy) in ((0, sh / 2 - 0.025, sw, 0.05), (0, -sh / 2 + 0.03, sw, 0.06),
                                       (-sw / 2 + 0.025, 0, 0.05, sh), (sw / 2 - 0.025, 0, 0.05, sh),
                                       (0, 0, sw, 0.03)):
                rbox(bm, ssx, ssy, 0.04, L @ T(cx, cy, 0), r=0.003, seg=1)
        so = K.separate(f"{name}_Sash{k}", frame_key, sash)
        so.matrix_world = hinge @ R(-sx * open_deg[k], 'Y')

        def pane(bm, sx=sx):
            L = T(-sx * sw / 2, 0, 0)
            for cy in (sh / 4 + 0.005, -sh / 4 - 0.01):
                box(bm, sw - 0.09, sh / 2 - 0.06, 0.003, L @ T(0, cy, 0))
        go = K.separate(f"Glass_{name}{k}", glass, pane)
        go.matrix_world = so.matrix_world
        leaves.append((so, go))
    return leaves


def steel_window(K, F, w, h, cols=4, rows=4, frame_key="WindowSteel", glass="WinGlass", open_cells=(), name="Window",
                 cracked=()):
    """钢窗：细的 T 型钢框，分成 cols × rows 格；open_cells 里的格子是推开的小窗扇（列, 行, 角度）。
    F：窗洞中心的坐标系（Z 朝屋里，Y 朝上）。"""
    fw = 0.045
    for (cx, cy, sx, sy) in ((0, h / 2 - fw / 2, w, fw), (0, -h / 2 + fw / 2, w, fw), (-w / 2 + fw / 2, 0, fw, h),
                             (w / 2 - fw / 2, 0, fw, h)):
        rbox(K[frame_key], sx, sy, 0.05, F @ T(cx, cy, 0), r=0.003, seg=1)
    cw, ch = (w - 2 * fw) / cols, (h - 2 * fw) / rows
    for i in range(1, cols):
        x = -w / 2 + fw + cw * i
        rbox(K[frame_key], 0.022, h - 2 * fw, 0.04, F @ T(x, 0, 0), r=0.002, seg=1)
        rbox(K[frame_key], 0.006, h - 2 * fw, 0.05, F @ T(x, 0, -0.005), r=0.0, seg=1)
    for j in range(1, rows):
        y = -h / 2 + fw + ch * j
        rbox(K[frame_key], w - 2 * fw, 0.022, 0.04, F @ T(0, y, 0), r=0.002, seg=1)
    opened = {(c, r_): a for c, r_, a in open_cells}

    def panes(bm, which):
        for i in range(cols):
            for j in range(rows):
                if ((i, j) in opened) != which:
                    continue
                cx = -w / 2 + fw + cw * (i + 0.5)
                cy = -h / 2 + fw + ch * (j + 0.5)
                box(bm, cw - 0.03, ch - 0.03, 0.003, F @ T(cx, cy, -0.008))
    K.separate(f"Glass_{name}", glass, lambda bm: panes(bm, False))
    for (i, j), a in opened.items():
        # 推开的小窗扇：上边铰接，往外推开 a 度
        cx = -w / 2 + fw + cw * (i + 0.5)
        top = -h / 2 + fw + ch * (j + 1)
        H = F @ T(cx, top - 0.012, -0.03) @ R(-a, 'X')

        def sash(bm):
            for (sx_, sy_, ssx, ssy) in ((0, -0.012, cw - 0.02, 0.025), (0, -ch + 0.03, cw - 0.02, 0.025),
                                         (-cw / 2 + 0.02, -ch / 2, 0.025, ch - 0.03),
                                         (cw / 2 - 0.02, -ch / 2, 0.025, ch - 0.03)):
                rbox(bm, ssx, ssy, 0.03, T(sx_, sy_, 0), r=0.002, seg=1)
        so = K.separate(f"{name}_Vent{i}{j}", frame_key, sash)
        so.matrix_world = H
        go = K.separate(f"Glass_{name}_Vent{i}{j}", glass, lambda bm: box(bm, cw - 0.05, ch - 0.06, 0.003,
                                                                           T(0, -ch / 2, 0)))
        go.matrix_world = H
    # 裂了的玻璃：贴一个纸条十字（窗格中心）
    for (i, j) in cracked:
        cx = -w / 2 + fw + cw * (i + 0.5)
        cy = -h / 2 + fw + ch * (j + 0.5)
        for a in (38, -38):
            rbox(K["Newspaper"], math.hypot(cw, ch) * 0.8, 0.035, 0.0008, F @ T(cx, cy, 0.0) @ R(a, 'Z'), r=0.0, seg=1)


# ============================================================================ 电
def wire_run(K, pts, cleat_every=0.4, normal=None, pair=True, key="Wire"):
    """明线：两根花线并排（或一根），沿 pts 走，每隔 cleat_every 一个瓷夹板压在墙上。
    normal：墙面朝屋里的方向（夹板贴墙）；pts 是贴着墙面的点。"""
    path = [V(p) for p in pts]
    n = V(normal) if normal else V((0, 0, -1))
    off = 0.0045
    for k in ((-1, 1) if pair else (0,)):
        side = []
        for i, p in enumerate(path):
            d = (path[min(i + 1, len(path) - 1)] - path[max(i - 1, 0)]).normalized()
            b = d.cross(n).normalized()
            side.append(p + b * off * k + n * 0.006)
        sweep(K[key], side, circle_profile(0.0028, 8), caps=True)
    # 瓷夹板：沿线每隔一段一个（两半夹住线，一颗螺丝）
    total = sum((path[i + 1] - path[i]).length for i in range(len(path) - 1))
    s = cleat_every * 0.5
    while s < total:
        acc = 0.0
        for i in range(len(path) - 1):
            seg = (path[i + 1] - path[i]).length
            if acc + seg >= s:
                p = path[i] + (path[i + 1] - path[i]) * ((s - acc) / seg)
                d = (path[i + 1] - path[i]).normalized()
                M = frame(p, n, d)
                rbox(K["Porcelain"], 0.026, 0.034, 0.012, M @ T(0, 0, 0.006), r=0.004, seg=2)
                cylinder(K["Steel"], 0.0035, 0.002, 10, M @ T(0, 0, 0.012))
                break
            acc += seg
        s += cleat_every


def toggle_switch(K, F):
    """扳把开关（胶木圆座）：F 贴墙（Z 朝外）。"""
    lathe(K["BakeliteBrown"], [(0.0, 0.0), (0.035, 0.0), (0.036, 0.012), (0.03, 0.022), (0.0, 0.024)], 32, F)
    rbox(K["BakeliteBrown"], 0.008, 0.026, 0.01, F @ T(0, 0.005, 0.026) @ R(-20, 'X'), r=0.003, seg=2)


def socket(K, F):
    """两眼插座（胶木方座）。"""
    rbox(K["BakeliteBrown"], 0.07, 0.07, 0.016, F @ T(0, 0, 0.008), r=0.006, seg=2)
    for sx in (-1, 1):
        cylinder(K["Dark"], 0.003, 0.001, 10, F @ T(sx * 0.0095, 0, 0.0161))


def pull_switch(K, F, cord=0.9):
    """拉线开关：天花板/墙上一个圆胶木盒，垂下一根细绳，绳头一个小坠子。F 的 Z 朝外。"""
    lathe(K["Porcelain"], [(0.0, 0.0), (0.03, 0.0), (0.031, 0.02), (0.024, 0.03), (0.0, 0.031)], 28, F)
    top = F @ V((0, 0, 0.03))
    bot = top + V((0.01, 0.0, -cord))
    sweep(K["Rope"], catmull([top, (top + bot) / 2 + V((0.005, 0.004, 0)), bot], 6), circle_profile(0.0012, 6))
    lathe(K["Bakelite"], [(0.0, 0.0), (0.006, 0.004), (0.007, 0.018), (0.003, 0.026), (0.0, 0.027)], 12,
          T(*bot) @ R(180, 'X'))


def fluorescent(K, anchors, coll, p, along, name, chain=0.0, tube_len=1.2):
    """日光灯：白漆铁皮灯架（瘦长的槽）+ 两头灯座 + 灯管（单独成对象 Tube_<name>，Godot 里亮/闪）+ 启辉器。
    p：灯架顶面中心（贴天花板或吊链下端），along：灯管方向。灯光挂点 Light_Tube_<name> 在灯管中心朝下。"""
    a = V(along).normalized()
    M = frame(V(p), V((0, 0, -1)), a)   # Z 朝下，Y 沿灯管
    L = tube_len + 0.08
    if chain:
        for s in (-1, 1):
            q = V(p) + a * s * L * 0.35
            for k in range(int(chain / 0.025)):
                torus(K["Steel"], 0.006, 0.0012, 10, 4, T(*(q + V((0, 0, k * 0.025 + 0.012)))) @ R(90 * (k % 2), 'Z')
                      @ R(90, 'X'))
            cylinder(K["FixtureWhite"], 0.03, 0.008, 20, T(*(q + V((0, 0, chain)))))
    rbox(K["FixtureWhite"], 0.06, L, 0.04, M @ T(0, 0, 0.02), r=0.004, seg=2)
    rbox(K["FixtureWhite"], 0.05, 0.22, 0.03, M @ T(0, 0.15, 0.055), r=0.004, seg=2)   # 镇流器那一截
    for s in (-1, 1):
        rbox(K["Bakelite"], 0.04, 0.025, 0.05, M @ T(0, s * (tube_len / 2 + 0.012), 0.065), r=0.004, seg=2)
    # 启辉器：灯架侧面一个小圆柱
    cylinder(K["FixtureWhite"], 0.011, 0.035, 16, M @ T(0.03, -0.25, 0.03) @ R(90, 'Y'))

    def tube(bm):
        cylinder(bm, 0.0135, tube_len - 0.02, 20, T(0, -(tube_len - 0.02) / 2, 0) @ R(-90, 'X'))
        for s in (-1, 1):
            cylinder(bm, 0.014, 0.012, 20, T(0, s * (tube_len / 2 - 0.004) - 0.006, 0) @ R(-90, 'X'))
    tb = K.separate(f"Tube_{name}", "Tube", tube)
    tb.matrix_world = M @ T(0, 0, 0.065)
    light(anchors, coll, f"Light_Tube_{name}", M @ V((0, 0, 0.09)), (0, 0, -1))
    return tb


def ceiling_fan(K, anchors, coll, p, rod=0.5, name="Fan", blade_len=0.6, seed=1):
    """三叶吊扇（米黄色漆，八十年代的样子）：天花板上的吊钩罩、吊杆、电机外壳、三片叶子。
    转的部分（电机下壳 + 叶子）单独成对象 Spin_<name>，原点在转轴上。"""
    rng = random.Random(seed)
    top = V(p)
    lathe(K["FanCream"], [(0.0, 0.0), (0.05, 0.0), (0.055, -0.02), (0.045, -0.07), (0.012, -0.075), (0.0, -0.075)], 32,
          T(*top))
    cylinder(K["FanCream"], 0.012, rod, 16, T(*(top - V((0, 0, rod + 0.07)))))
    hub = top - V((0, 0, rod + 0.07))
    lathe(K["FanCream"], [(0.0, 0.0), (0.03, 0.0), (0.09, -0.03), (0.115, -0.07), (0.11, -0.09), (0.0, -0.09)], 40,
          T(*hub))

    def rotor(bm):
        lathe(bm, [(0.0, 0.0), (0.105, 0.0), (0.1, -0.03), (0.07, -0.055), (0.025, -0.07), (0.0, -0.072)], 40, Matrix())
        for k in range(3):
            a = 120 * k + rng.uniform(-1, 1)
            Mb = R(a, 'Z')
            # 叶柄：一根扁铁从电机下壳伸出去，压着叶子根部
            rbox(bm, 0.2, 0.03, 0.006, Mb @ T(0.17, 0, -0.03) @ R(-6, 'Y'), r=0.002, seg=1)
            # 叶子：根部窄、外头宽，有一点扭角；叶尖往下垂一点（用久了）
            rbox(bm, blade_len, 0.13, 0.005, Mb @ T(0.25 + blade_len / 2, 0, -0.042 - blade_len * 0.02)
                 @ R(-2, 'Y') @ R(10, 'X'), r=0.02, seg=2)
    sp = K.separate(f"Spin_{name}", "FanCream", rotor)
    sp.matrix_world = T(*(hub - V((0, 0, 0.09))))
    return sp


# ============================================================================ 墙上的东西
def picture_frame(K, F, w, h, depth=0.02, frame_key="WoodDark", paper=None, glass=True, tilt=3.0):
    """挂在钉子上的相框 / 奖状框：木框、玻璃、里面一张纸（paper 是 Paper_<id> 名字，Godot 里换成那张纸的贴图）。
    F：钉子的位置（Z 朝屋里），相框往前倾 tilt 度挂着。"""
    M = F @ T(0, -0.03, 0) @ R(-tilt, 'X') @ T(0, -h / 2 + 0.03, depth / 2)
    fw = 0.025
    for (cx, cy, sx, sy) in ((0, h / 2 - fw / 2, w, fw), (0, -h / 2 + fw / 2, w, fw), (-w / 2 + fw / 2, 0, fw, h),
                             (w / 2 - fw / 2, 0, fw, h)):
        rbox(K[frame_key], sx, sy, depth, M @ T(cx, cy, 0), r=0.004, seg=2)
    box(K["Cardboard"], w - 0.01, h - 0.01, 0.003, M @ T(0, 0, -depth / 2 + 0.002))
    if paper:
        paper_quad(K, paper, M @ T(0, 0, -depth / 2 + 0.006), w - 2 * fw - 0.004, h - 2 * fw - 0.004)
    if glass:
        box(K["Glass"], w - 2 * fw + 0.004, h - 2 * fw + 0.004, 0.002, M @ T(0, 0, depth / 2 - 0.006))
    # 挂绳：钉子到相框背后两边的三角
    nail = F @ V((0, 0, 0.004))
    cylinder(K["Steel"], 0.002, 0.02, 8, F)
    for sx in (-1, 1):
        q = M @ V((sx * w * 0.35, h / 2 - 0.04, -depth / 2))
        sweep(K["Rope"], [nail, q], circle_profile(0.0012, 5))


def paper_quad(K, name, M, w, h, curl=0.0, segs=8):
    """一张纸（带 0~1 的 UV，Godot 里换成 PaperDoc 的贴图）：M 是纸面中心的坐标系（Z 朝外），curl 是下边往外翘多少米。"""
    import bmesh as _bm

    def geo(bm):
        uv = bm.loops.layers.uv.new("UVMap")
        rows = []
        for j in range(segs + 1):
            v = j / segs
            z = curl * (1 - v) ** 2
            rows.append([bm.verts.new(M @ V(((u - 0.5) * w, (v - 0.5) * h, z))) for u in (0.0, 1.0)])
        for j in range(segs):
            f = bm.faces.new([rows[j][0], rows[j][1], rows[j + 1][1], rows[j + 1][0]])
            for loop, (u, v) in zip(f.loops, ((0, j / segs), (1, j / segs), (1, (j + 1) / segs), (0, (j + 1) / segs))):
                loop[uv].uv = (u, v)
    ob = K.separate(f"Paper_{name}", "PaperWhite", geo, smooth=True, sharp=None, recalc=False)
    return ob


def nail(K, F):
    cylinder(K["Steel"], 0.0025, 0.02, 8, F)
    cylinder(K["Steel"], 0.004, 0.0015, 10, F @ T(0, 0, 0.02))


# ============================================================================ 桌上的东西
def thermos(K, M, shell="ThermosRed", seed=1):
    """暖水瓶（九十年代的铁皮壳）：铁皮外壳上刷红漆印花、上下两道箍、提手、软木塞。高 38 厘米。"""
    lathe(K[shell], [(0.0, 0.004), (0.06, 0.004), (0.062, 0.02), (0.062, 0.26), (0.056, 0.285), (0.045, 0.3),
                     (0.034, 0.315), (0.0, 0.315)], 40, M)
    for z in (0.012, 0.262):
        torus(K["Chrome"], 0.0625, 0.004, 40, 8, M @ T(0, 0, z))
    cylinder(K["Chrome"], 0.06, 0.006, 40, M)
    lathe(K["Chrome"], [(0.034, 0.315), (0.036, 0.33), (0.03, 0.34), (0.022, 0.342)], 32, M)
    lathe(K["Cork"], [(0.0, 0.33), (0.02, 0.33), (0.022, 0.36), (0.019, 0.375), (0.0, 0.376)], 24, M)
    hp = [M @ V((0.062, 0, 0.24)), M @ V((0.085, 0, 0.22)), M @ V((0.087, 0, 0.12)), M @ V((0.062, 0, 0.1))]
    sweep(K["Bakelite"], catmull(hp, 6), rect_profile(0.012, 0.016, 0.004))


def gaiwan(K, M, tea=0.7, lid_off=False):
    """盖碗：托盘、碗、盖子（白瓷），碗里有茶。lid_off：盖子斜靠在托盘上。"""
    lathe(K["Porcelain"], [(0.0, 0.0), (0.05, 0.0), (0.062, 0.006), (0.064, 0.01), (0.058, 0.008), (0.03, 0.006),
                           (0.0, 0.006)], 40, M)
    lathe(K["Porcelain"], [(0.0, 0.006), (0.022, 0.006), (0.024, 0.012), (0.03, 0.016), (0.045, 0.04), (0.05, 0.062),
                           (0.053, 0.068), (0.05, 0.068), (0.046, 0.06), (0.04, 0.04), (0.02, 0.018), (0.0, 0.017)],
          40, M)
    cylinder(K["Tea"], 0.045 * (0.6 + 0.4 * tea), 0.001, 32, M @ T(0, 0, 0.018 + 0.044 * tea))
    Ml = M @ (T(0.075, 0.0, 0.03) @ R(70, 'Y') if lid_off else T(0, 0, 0.058))
    lathe(K["Porcelain"], [(0.0, 0.0), (0.044, 0.0), (0.046, 0.004), (0.04, 0.012), (0.012, 0.02), (0.012, 0.03),
                           (0.016, 0.032), (0.0, 0.033)], 40, Ml)


def basin(K, M, r=0.17, color="Enamel", rim="BtnRed"):
    """搪瓷脸盆：盆底、盆壁、卷边（红口）。盆底印一对红鸳鸯/双喜就太讲究了，印一圈红花。"""
    lathe(K[color], [(0.0, 0.0), (r * 0.62, 0.0), (r * 0.66, 0.006), (r * 0.98, 0.075), (r, 0.08), (r * 0.97, 0.078),
                     (r * 0.64, 0.01), (0.0, 0.009)], 48, M)
    torus(K[rim], r * 0.995, 0.004, 48, 8, M @ T(0, 0, 0.08))


# ============================================================================ 导出
def export_room(coll, path, anchors):
    objs = bake_for_export([o for o in coll.objects])
    empties = [o for o in objs if o.type == 'EMPTY']
    meshes = [o for o in objs if o.type == 'MESH']
    keep = [o for o in meshes if o.name.startswith(KEEP)]
    rest = [o for o in meshes if not o.name.startswith(KEEP)]
    glass = [o for o in rest if o.data.materials and o.data.materials[0].name == "M_Glass"]
    rest = [o for o in rest if o not in glass]
    groups = {}
    for o in rest:
        key = o.data.materials[0].name if o.data.materials else "none"
        groups.setdefault(key, []).append(o)
    bodies = [join(objs_, f"Body_{key.removeprefix('M_')}") for key, objs_ in sorted(groups.items())]
    gl = join(glass, "GaugeGlass") if glass else None
    final = bodies + keep + ([gl] if gl else []) + empties
    export_glb(path, final)
    print(f"exported {os.path.basename(path)}: {stats(final):,} tris, {os.path.getsize(path) / 1e6:.1f} MB")
