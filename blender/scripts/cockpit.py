"""舱内（可以走动的耐压舱）。

一段横躺的圆柱形耐压壳 + 艏部半球，人能站直、走动：
- 结构：内壁刷漆，每 0.6 米一道 T 型肋骨；分前后两段，中间是带水密门的平隔壁（门能开关，见 Door_*）
- 前段是控制舱（本文件）；后段是生活舱（quarters.py），顶上有出入舱口和直梯
- 两舷：整排「嵌在舱壁里」的工作台——踢脚、柜门、桌面、斜面仪表板、灯罩，开间由肋骨分隔
- 艏部：驾驶台（主仪表板 + 左右翼板 + 顶板 + 操纵杆）和驾驶椅
- 舷窗：左右舷各一个，在驾驶台后面的观察位
- 头顶：管路（带法兰、阀门、吊架）、电缆桥架、顶灯；脚下：花纹钢地板，中间一条格栅，下面是舱底

坐标：Blender +Y 朝艏，+Z 朝上，+X 朝右舷。耐压壳轴线是 Y 轴。
"""
import math
import random

from mathutils import Vector as V, Matrix

from lib import (material, frame, T, R, S, cylinder, box, uvsphere, lathe, torus, catmull, circle_profile, text_mesh,
                 rect_profile, sweep, build, empty, _grid_faces)
from kit import (Parts, Cables, rbox, star_profile, extrude_profile, screw, socket_screw, toggle,
                 flip_cover, knob, pointer_knob, button, lamp, vent, handle, fuse, connector, label_plate, silk,
                 tape_label, sticky_note, meter_rect, gauge_round, seg_display, annunciator, rotameter,
                 valve_wheel, unit, FONT_BRUSH, FONT_SERIF, FONT_HAND)

# ---------------------------------------------------------------------------- 主尺寸（改这里要同步 Godot 的 crew.gd）
R_IN = 1.35                     # 耐压壳内壁半径
Y_AFT, Y_BOW = -2.6, 1.6        # 中间隔壁（水密门）位置；艏部半球的球心
Y_STERN = -6.4                  # 生活舱后端的隔壁（再往后是不进人的机舱）
DECK = -0.9                     # 地板面
FRAMES = (-2.3, -1.7, -1.1, -0.5, 0.1, 0.7, 1.3)   # 肋骨（控制舱）
AFT_FRAMES = (-2.9, -3.5, -4.1, -4.7, -5.3, -5.9)  # 肋骨（生活舱）
BAYS = [(FRAMES[i], FRAMES[i + 1]) for i in range(1, 6)]   # 工作台的五个开间（最前面一个是舷窗）
CON_Y0, CON_Y1 = -1.76, 1.85    # 两舷工作台的前后范围
DESK_Z = -0.12                  # 桌面高度（离地 78 厘米）
DESK_X = 0.775                  # 桌沿离中线
PANEL_B = (1.15, DESK_Z)        # 斜仪表板下沿 (|x|, z)
PANEL_T = (1.02, 0.62)          # 斜仪表板上沿
HOOD_Z = (0.60, 0.71)           # 灯罩上下沿
HATCH = (0.0, -3.35)            # 出入舱口中心 (x, y)，在生活舱顶上
HATCH_R = 0.30
HATCH_TOP = 1.55                # 舱盖底面高度（再往上就是艇外上层建筑的甲板）
DOOR = (0.0, 0.05, 0.32, 0.68)  # 水密门：中心 x、中心 z、半宽、半高（门槛离地 27 厘米，过门要低头）
DOOR_HINGE = (-0.43, Y_AFT + 0.13)  # 门轴 (x, y)：在左舷一侧、门扇正面外，门往控制舱里开
VP_Y = 1.0                      # 舷窗所在的 y
LADDER_Y = -3.57
OPEN_CAB = (-1, 2, 1, 55.0)     # 半开的柜门：舷、开间、第几扇、开的角度

SEAT = V((0, 1.48, DECK))
EYE_SEATED = V((0, 1.44, 0.34))


def vp_axis(s):
    """舷窗轴线：从舱内中线上方出发，朝 s 舷、略向下。"""
    return V((0, VP_Y, 0.42)), V((s * 0.985, 0, -0.17)).normalized()


def anchor_frame(pos, fwd, up=V((0, 0, 1))):
    """Blender 局部 +Y = fwd，+Z = up（导出到 Godot 后即 -Z 朝 fwd、+Y 朝上）。"""
    y = V(fwd).normalized()
    x = y.cross(V(up)).normalized()
    z = x.cross(y).normalized()
    return Matrix(((x.x, y.x, z.x, pos[0]), (x.y, y.y, z.y, pos[1]), (x.z, y.z, z.z, pos[2]), (0, 0, 0, 1)))


def wall_anchor(F, depth_offset=0.0):
    """面板坐标系 F（Z 朝外）转成道具挂点：道具正面（Godot +Z）朝外，+Y 朝上。"""
    p = F @ V((0, 0, depth_offset))
    return anchor_frame(p, -(F.to_3x3() @ V((0, 0, 1))), F.to_3x3() @ V((0, 1, 0)))


def abox(bm, x0, x1, y0, y1, z0, z1, r=0.0, seg=2):
    """按世界坐标范围放一个（倒角）盒子。"""
    rbox(bm, abs(x1 - x0), abs(y1 - y0), abs(z1 - z0), T((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2), r=r, seg=seg)


def sbox(bm, s, ax0, ax1, y0, y1, z0, z1, r=0.0, seg=2):
    """舷侧盒子：ax0/ax1 是离中线的距离，s=±1 选左右舷。"""
    abox(bm, s * ax0, s * ax1, y0, y1, z0, z1, r, seg)


def panel_frame(s, yc, t=0.5, dz=0.0):
    """s 舷斜仪表板上的面板坐标系：原点在 y=yc、斜面高度比例 t 处，Z 朝过道，Y 沿斜面向上，X 是人面对面板时的右手方向。"""
    (bx, bz), (tx, tz) = PANEL_B, PANEL_T
    p = V((s * (bx + (tx - bx) * t), yc, bz + (tz - bz) * t))
    u = V((s * (tx - bx), 0, tz - bz)).normalized()
    n = u.cross(V((0, 1, 0))) * s
    return frame(p + n * dz, n, u)


PANEL_LEN = math.hypot(PANEL_T[0] - PANEL_B[0], PANEL_T[1] - PANEL_B[1])


# ============================================================================ 材质
def materials(M):
    """只给预览用的基础色，正式外观由 Godot 的 setup_project.gd 生成同名材质替换。"""
    def add(key, name, color, metal=0.0, rough=0.6, emission=None, strength=1.0, alpha=1.0):
        M[key] = material(name, color, metal, rough, emission, strength, alpha)

    add("HullInner", "M_HullInner", (0.42, 0.46, 0.42), 0.2, 0.5)
    add("Console", "M_Console", (0.2, 0.24, 0.26), 0.3, 0.45)
    add("DeskTop", "M_DeskTop", (0.07, 0.08, 0.07), 0.0, 0.6)
    add("Rail", "M_Rail", (0.5, 0.51, 0.5), 0.8, 0.45)
    add("EquipGreen", "M_EquipGreen", (0.3, 0.37, 0.33), 0.2, 0.5)
    add("EquipGray", "M_EquipGray", (0.48, 0.49, 0.47), 0.2, 0.5)
    add("EquipBeige", "M_EquipBeige", (0.55, 0.51, 0.42), 0.2, 0.5)
    add("EquipBlue", "M_EquipBlue", (0.2, 0.26, 0.31), 0.2, 0.5)
    add("PanelDark", "M_PanelDark", (0.05, 0.05, 0.05), 0.2, 0.6)
    add("PanelGray", "M_PanelGray", (0.25, 0.26, 0.26), 0.2, 0.55)
    add("Bakelite", "M_Bakelite", (0.025, 0.022, 0.02), 0.0, 0.35)
    add("Chrome", "M_Chrome", (0.8, 0.8, 0.8), 1.0, 0.15)
    add("Steel", "M_Steel", (0.55, 0.55, 0.55), 1.0, 0.4)
    add("Alu", "M_Alu", (0.75, 0.75, 0.75), 1.0, 0.35)
    add("Dark", "M_Dark", (0.01, 0.01, 0.01), 0.0, 0.9)
    add("Knob", "M_Knob", (0.02, 0.02, 0.02), 0.0, 0.35)
    add("Silk", "M_Silk", (0.85, 0.84, 0.78), 0.0, 0.6)
    add("Ink", "M_GaugeInk", (0.02, 0.02, 0.02), 0.0, 0.5)
    add("InkRed", "M_InkRed", (0.7, 0.05, 0.03), 0.0, 0.5)
    add("LabelPlate", "M_LabelPlate", (0.02, 0.02, 0.02), 0.0, 0.3)
    add("LabelRed", "M_LabelRed", (0.45, 0.03, 0.02), 0.0, 0.35)
    add("MeterFace", "M_MeterFace", (0.86, 0.85, 0.78), 0.0, 0.5)
    add("GaugeFace", "M_GaugeFace", (0.85, 0.82, 0.7), 0.0, 0.5)
    add("Needle", "M_Needle", (0.8, 0.08, 0.04), 0.0, 0.4)
    add("NeedleBlack", "M_NeedleBlack", (0.02, 0.02, 0.02), 0.0, 0.4)
    add("Glass", "M_Glass", (0.55, 0.7, 0.68), 0.0, 0.05, alpha=0.12)
    add("GlassTube", "M_GlassTube", (0.8, 0.85, 0.85), 0.0, 0.05, alpha=0.2)
    add("FloatRed", "M_FloatRed", (0.8, 0.05, 0.03), 0.0, 0.4)
    add("LensRed", "M_IndicatorRed", (0.9, 0.05, 0.02), 0.0, 0.3, emission=(1, 0.05, 0.02), strength=2)
    add("LensAmber", "M_IndicatorAmber", (0.9, 0.5, 0.02), 0.0, 0.3, emission=(1, 0.5, 0.02), strength=2)
    add("LensGreen", "M_IndicatorGreen", (0.1, 0.9, 0.2), 0.0, 0.3, emission=(0.1, 1, 0.2), strength=2)
    add("LensWhite", "M_IndicatorWhite", (0.9, 0.88, 0.8), 0.0, 0.3, emission=(1, 0.95, 0.8), strength=1)
    add("LampGlass", "M_LampGlass", (0.95, 0.9, 0.8), 0.0, 0.2, emission=(1, 0.9, 0.7), strength=3)
    add("Warn", "M_Warn", (0.6, 0.35, 0.05), 0.0, 0.3)
    add("LedWindow", "M_LedWindow", (0.08, 0.0, 0.0), 0.0, 0.1)
    add("BtnRed", "M_BtnRed", (0.6, 0.04, 0.02), 0.0, 0.35)
    add("BtnBlack", "M_Knob", (0.02, 0.02, 0.02), 0.0, 0.35)
    add("BtnGreen", "M_BtnGreen", (0.05, 0.35, 0.1), 0.0, 0.35)
    add("BtnYellow", "M_BtnYellow", (0.75, 0.55, 0.05), 0.0, 0.35)
    add("Olive", "M_Olive", (0.2, 0.22, 0.12), 0.3, 0.5)
    add("CableBlack", "M_CableBlack", (0.025, 0.025, 0.025), 0.0, 0.55)
    add("CableGray", "M_CableGray", (0.3, 0.31, 0.3), 0.0, 0.55)
    add("CableOrange", "M_CableOrange", (0.7, 0.25, 0.05), 0.0, 0.5)
    add("CableYellow", "M_CableYellow", (0.7, 0.6, 0.1), 0.0, 0.5)
    add("CableBlue", "M_CableBlue", (0.1, 0.2, 0.45), 0.0, 0.5)
    add("CableWhite", "M_CableWhite", (0.75, 0.75, 0.72), 0.0, 0.5)
    add("Zip", "M_ZipWhite", (0.85, 0.85, 0.8), 0.0, 0.4)
    add("ZipBlack", "M_ZipBlack", (0.03, 0.03, 0.03), 0.0, 0.4)
    add("Brass", "M_Brass", (0.72, 0.52, 0.22), 1.0, 0.35)
    add("Copper", "M_Copper", (0.7, 0.35, 0.2), 1.0, 0.35)
    add("Vinyl", "M_Vinyl", (0.06, 0.045, 0.04), 0.0, 0.45)
    add("Cloth", "M_Cloth", (0.25, 0.27, 0.2), 0.0, 0.95)
    add("MaskTape", "M_MaskTape", (0.8, 0.74, 0.58), 0.0, 0.8)
    add("Marker", "M_Marker", (0.03, 0.03, 0.05), 0.0, 0.6)
    add("NoteYellow", "M_NoteYellow", (0.95, 0.85, 0.35), 0.0, 0.8)
    add("Deck", "M_Deck", (0.25, 0.25, 0.24), 0.8, 0.45)
    add("Grating", "M_Grating", (0.2, 0.2, 0.19), 0.7, 0.5)
    add("Bilge", "M_Bilge", (0.03, 0.035, 0.03), 0.0, 0.1)
    add("PipeRed", "M_PipeRed", (0.45, 0.06, 0.04), 0.2, 0.5)
    add("PipeBlue", "M_PipeBlue", (0.15, 0.25, 0.4), 0.2, 0.5)
    add("PipeGray", "M_PipeGray", (0.35, 0.36, 0.35), 0.3, 0.5)
    add("CRT", "M_CRT", (0.03, 0.15, 0.06), 0.0, 0.1, emission=(0.2, 1.0, 0.35), strength=0.5)
    add("O2", "M_O2Blue", (0.33, 0.58, 0.75), 0.1, 0.5)
    add("Rubber", "M_Rubber", (0.02, 0.02, 0.02), 0.0, 0.8)
    # 神龛
    add("Lacquer", "M_RedLacquer", (0.3, 0.03, 0.02), 0.0, 0.35)
    add("Gold", "M_Gold", (0.78, 0.56, 0.2), 1.0, 0.3)
    add("Statue", "M_StatueGilt", (0.55, 0.38, 0.12), 0.8, 0.45)
    add("ClothRed", "M_ClothRed", (0.5, 0.02, 0.02), 0.0, 0.9)
    add("Talisman", "M_Paper", (0.85, 0.7, 0.25), 0.0, 0.9)
    add("BrushRed", "M_BrushRed", (0.55, 0.02, 0.01), 0.0, 0.7)
    add("Incense", "M_Incense", (0.35, 0.12, 0.06), 0.0, 0.8)
    add("Ember", "M_Ember", (1.0, 0.3, 0.05), 0.0, 0.5, emission=(1, 0.3, 0.05), strength=4)
    add("Ash", "M_Ash", (0.35, 0.33, 0.3), 0.0, 0.95)
    add("Paper", "M_Paper", (0.85, 0.7, 0.25), 0.0, 0.9)
    add("Jade", "M_Jade", (0.3, 0.55, 0.4), 0.0, 0.25)
    # 生活痕迹
    add("Lagging", "M_Lagging", (0.55, 0.53, 0.47), 0.0, 0.95)
    add("Towel", "M_Towel", (0.7, 0.66, 0.56), 0.0, 0.95)
    add("Jacket", "M_Jacket", (0.12, 0.15, 0.22), 0.0, 0.9)
    add("Net", "M_Net", (0.8, 0.15, 0.05), 0.0, 0.7)
    add("Orange", "M_Orange", (0.85, 0.35, 0.04), 0.0, 0.5)
    add("Bottle", "M_Bottle", (0.55, 0.65, 0.7), 0.0, 0.25)
    add("Can", "M_Can", (0.6, 0.6, 0.58), 0.9, 0.3)
    add("CanLabel", "M_CanLabel", (0.55, 0.12, 0.05), 0.0, 0.5)
    add("Cardboard", "M_Cardboard", (0.5, 0.36, 0.2), 0.0, 0.9)
    add("PaintText", "M_PaintText", (0.82, 0.8, 0.7), 0.0, 0.6)
    add("Tea", "M_Tea", (0.12, 0.05, 0.015), 0.0, 0.05)
    add("TeaStain", "M_TeaStain", (0.4, 0.24, 0.1), 0.0, 0.7)
    # 生活舱
    add("Blanket", "M_Blanket", (0.32, 0.3, 0.27), 0.0, 0.95)
    add("Curtain", "M_Curtain", (0.36, 0.38, 0.3), 0.0, 0.9)
    add("Mattress", "M_Mattress", (0.55, 0.58, 0.62), 0.0, 0.9)
    add("Pillow", "M_Pillow", (0.72, 0.7, 0.62), 0.0, 0.9)
    add("Sheet", "M_Sheet", (0.75, 0.76, 0.73), 0.0, 0.9)
    add("Mirror", "M_Mirror", (0.8, 0.8, 0.78), 1.0, 0.08)
    return M


# ============================================================================ 耐压壳
def hull(c, M):
    """圆柱段 + 艏部半球的内壁（法线朝里）。在舷窗、舱口处开孔，地板以下不做。"""
    NU = 180

    def keep(cn):
        if cn.z < DECK - 0.12:
            return False
        if cn.z > 0 and math.hypot(cn.x - HATCH[0], cn.y - HATCH[1]) < HATCH_R + 0.03:
            return False
        for s in (-1, 1):
            o, d = vp_axis(s)
            v = cn - o
            along = v.dot(d)
            if along > 0.5 and (v - d * along).length < 0.2:
                return False
        return True

    def geo(bm):
        import bmesh
        stations = []
        ny = int(round((Y_BOW - Y_STERN) / 0.04))
        for j in range(ny + 1):
            stations.append((Y_STERN + (Y_BOW - Y_STERN) * j / ny, R_IN))
        for k in range(1, 37):
            th = math.radians(90 * k / 40)
            stations.append((Y_BOW + R_IN * math.sin(th), R_IN * math.cos(th)))
        rows = []
        for y, r in stations:
            rows.append([bm.verts.new(V((r * math.sin(2 * math.pi * i / NU), y, r * math.cos(2 * math.pi * i / NU))))
                         for i in range(NU)])
        for j in range(len(rows) - 1):
            for i in range(NU):
                k = (i + 1) % NU
                q = [rows[j][i], rows[j][k], rows[j + 1][k], rows[j + 1][i]]
                if keep(sum((v.co for v in q), V()) / 4):
                    bm.faces.new(q)
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context='VERTS')
        bm.normal_update()
        bm.faces.ensure_lookup_table()
        f = bm.faces[len(bm.faces) // 2]
        # 法线要朝向轴线（朝舱内）
        cc = f.calc_center_median()
        if f.normal.dot(V((cc.x, 0, cc.z))) > 0:
            bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
    build("Int_Hull", c, M["HullInner"], geo, recalc=False, sharp_angle=None)


def ring_sweep(bm, prof, y0, a0, a1, n):
    """绕 Y 轴扫一段剖面 prof=[(r, dy)]（闭合多边形），角度从 +Z 量起、朝 +X 为正。"""
    rings = []
    for i in range(n + 1):
        a = math.radians(a0 + (a1 - a0) * i / n)
        rings.append([bm.verts.new(V((r * math.sin(a), y0 + dy, r * math.cos(a)))) for r, dy in prof])
    _grid_faces(bm, rings)
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[-1])


T_FRAME = [(R_IN + 0.012, -0.011), (1.215, -0.011), (1.215, -0.046), (1.208, -0.05), (1.197, -0.05),
           (1.19, -0.044), (1.19, 0.044), (1.197, 0.05), (1.208, 0.05), (1.215, 0.046), (1.215, 0.011),
           (R_IN + 0.012, 0.011)]


def frames(K):
    """T 型肋骨：腹板焊在壳上，内缘一道翼板。舱口处断开（由舱口围板补强）。"""
    for y in FRAMES + AFT_FRAMES:
        # 工作台那一段，肋骨下端藏进柜体里；后部敞开的地方一直落到地板
        # 生活舱两舷都是铺位、柜子，肋骨下端藏在后面
        if CON_Y0 - 0.06 < y < CON_Y1:
            end = 132.0
        elif y < Y_AFT:
            end = 112.0
        else:
            end = math.degrees(math.acos(DECK / 1.19))
        dy = abs(y - HATCH[1])
        if dy < 0.43:
            cut = math.degrees(math.asin(math.sqrt(0.43 ** 2 - dy ** 2) / 1.2))
            segs = [(-end, -cut), (cut, end)]
        else:
            segs = [(-end, end)]
        for a0, a1 in segs:
            ring_sweep(K["HullInner"], T_FRAME, y, a0, a1, max(8, int((a1 - a0) / 1.5)))
        # 焊缝：腹板两侧和壳体相接处一道细焊道
        for side in (-1, 1):
            prof = [(R_IN + 0.004, side * 0.011), (R_IN - 0.006, side * 0.0115), (R_IN - 0.002, side * 0.019),
                    (R_IN + 0.004, side * 0.02)]
            if side < 0:
                prof.reverse()
            for a0, a1 in segs:
                ring_sweep(K["HullInner"], prof, y, a0, a1, max(8, int((a1 - a0) / 1.5)))


def weld_seams(K):
    """壳体环焊缝（两段筒体对接处）和筒体-半球连接处。"""
    for y in (-0.8, 0.4, Y_BOW, -4.4):
        prof = [(R_IN + 0.003, -0.012), (R_IN - 0.002, -0.009), (R_IN - 0.0035, 0.0), (R_IN - 0.002, 0.009),
                (R_IN + 0.003, 0.012)]
        ring_sweep(K["HullInner"], prof, y, -140, 140, 180)


# ============================================================================ 地板
def deck(K):
    """两侧花纹钢地板 + 中间一条格栅，格栅下面是舱底（管子、积水）。"""
    gx = 0.3  # 格栅半宽
    ys = [Y_AFT] + [y for y in FRAMES] + [1.95]
    for i in range(len(ys) - 1):
        y0, y1 = ys[i] + 0.003, ys[i + 1] - 0.003
        for s in (-1, 1):
            x0, x1 = s * (gx + 0.03), s * 1.02
            abox(K["Deck"], x0, x1, y0, y1, DECK - 0.012, DECK, r=0.002, seg=1)
            # 沉头螺丝
            for xx in (x0 + s * 0.03, x1 - s * 0.05):
                for yy in (y0 + 0.03, y1 - 0.03):
                    cylinder(K["Steel"], 0.006, 0.0008, 12, T(xx, yy, DECK - 0.0004))
                    box(K["Dark"], 0.008, 0.0015, 0.0006, T(xx, yy, DECK + 0.0003))
            # 起板孔
            rbox(K["Dark"], 0.07, 0.024, 0.001, T(s * 0.62, (y0 + y1) / 2, DECK + 0.0001), r=0.011, seg=3)
    # 格栅：外框角钢 + 承重扁钢 + 横杆
    y0, y1 = Y_AFT + 0.25, 1.55
    for s in (-1, 1):
        abox(K["Grating"], s * (gx + 0.0), s * (gx + 0.03), y0, y1, DECK - 0.05, DECK, r=0.002, seg=1)
    n = int((y1 - y0) / 0.032)
    for i in range(n + 1):
        y = y0 + (y1 - y0) * i / n
        box(K["Grating"], 2 * gx, 0.004, 0.03, T(0, y, DECK - 0.015))
    for k in range(1, 6):
        x = -gx + 2 * gx * k / 6
        box(K["Grating"], 0.006, y1 - y0, 0.006, T(x, (y0 + y1) / 2, DECK - 0.003))
    # 舱底：槽底、两根管子、一层积水
    abox(K["HullInner"], -gx - 0.05, gx + 0.05, Y_AFT, y1 + 0.05, DECK - 0.36, DECK - 0.33)
    for s in (-1, 1):
        abox(K["HullInner"], s * (gx + 0.03), s * (gx + 0.05), Y_AFT, y1 + 0.05, DECK - 0.36, DECK - 0.05)
    abox(K["HullInner"], -gx - 0.05, gx + 0.05, y1 + 0.03, y1 + 0.05, DECK - 0.36, DECK - 0.05)
    for x, r, key in ((-0.15, 0.05, "PipeGray"), (0.12, 0.032, "PipeBlue")):
        zp = DECK - 0.33 + r + 0.022   # 法兰下沿离槽底留一点
        sweep(K[key], [V((x, Y_AFT, zp)), V((x, y1, zp))], circle_profile(r, 20))
        for y in (-1.4, -0.2, 1.0):
            cylinder(K[key], r + 0.018, 0.022, 24, T(x, y, zp) @ R(-90, 'X'))
    abox(K["Bilge"], -gx - 0.03, gx + 0.03, Y_AFT, y1 + 0.03, DECK - 0.335, DECK - 0.31)


def bilge(K, anchors):
    """舱底：侧壁上三盏昏黄的防水灯（光从格栅缝里往上漏），积水里漂着垃圾和一张泡烂的符。"""
    gx = 0.33  # 舱底侧壁内表面
    for i, (s, y) in enumerate(((1, -1.65), (-1, -0.35), (1, 0.95))):
        F = frame(V((s * gx, y, DECK - 0.13)), V((-s, 0, 0)))
        rbox(K["EquipGray"], 0.1, 0.06, 0.03, F @ T(0, 0, 0.015), r=0.006, seg=2)
        for sx in (-1, 1):
            socket_screw(K, F @ T(0, 0, 0.03), sx * 0.04, 0, r=0.004)
        lathe(K["LensAmber"], [(0.02, 0.03), (0.02, 0.042), (0.014, 0.052), (0.0, 0.054)], 24, F)
        for k in range(3):
            a = math.radians(90 + 120 * k)
            sweep(K["Steel"], catmull([F @ V((math.cos(a) * 0.024, math.sin(a) * 0.024, 0.03)),
                                       F @ V((math.cos(a) * 0.024, math.sin(a) * 0.024, 0.05)),
                                       F @ V((0, 0, 0.062))], 5), circle_profile(0.0018, 6))
        anchors.append(empty(f"CabinLight_Bilge_{i}", K.coll, F @ T(0, 0, 0.07)))
    wz = DECK - 0.31  # 水面
    # 半沉的塑料瓶
    Mb = T(0.0, -0.95, wz + 0.008) @ R(70, 'Z') @ R(90, 'Y') @ T(0, 0, -0.1)   # 漂在两根管子中间
    lathe(K["Bottle"], [(0.0, 0.0), (0.028, 0.002), (0.032, 0.012), (0.032, 0.13), (0.024, 0.16), (0.012, 0.175),
                        (0.012, 0.192), (0.0, 0.192)], 24, Mb)
    cylinder(K["BtnRed"], 0.0135, 0.014, 16, Mb @ T(0, 0, 0.19))
    # 烟头
    rng = random.Random(5)
    for x, y in ((-0.03, -0.6), (0.05, -0.55), (0.03, 0.2), (-0.27, 0.75), (0.0, -1.6), (-0.05, 1.1)):
        M = T(x, y, wz + 0.002) @ R(rng.uniform(0, 180), 'Z') @ R(90, 'Y')
        cylinder(K["Silk"], 0.0042, 0.022, 10, M)
        cylinder(K["CableOrange"], 0.0044, 0.012, 10, M @ T(0, 0, 0.022))
    # 泡在水里的符纸（墨迹洇开了一半）
    Mt = T(-0.08, 0.38, wz + 0.0012) @ R(-28, 'Z')
    rbox(K["Talisman"], 0.05, 0.16, 0.0006, Mt, r=0.0, seg=1)
    K.text("敕令\n镇海", Mt @ T(0, 0, 0.0003), 0.11, key="BrushRed", font=FONT_BRUSH)


# ============================================================================ 两舷工作台
def consoles(K, anchors):
    """嵌在舱壁里的连续工作台：踢脚、柜体和柜门、桌面、斜仪表板、立柱、灯罩。"""
    rng = random.Random(3)
    cab_edges = [CON_Y0] + list(FRAMES[1:]) + [CON_Y1]
    zc = (DECK + 0.1 + DESK_Z - 0.045) / 2
    hz = (DESK_Z - 0.045) - (DECK + 0.1) - 0.03

    def door_span(i, k):
        a, b = cab_edges[i] + 0.012, cab_edges[i + 1] - 0.012
        return a + (b - a) * k / 2 + 0.006, a + (b - a) * (k + 1) / 2 - 0.006

    for s in (-1, 1):
        # 踢脚、柜体、桌面
        sbox(K["Dark"], s, 0.87, 1.2, CON_Y0 + 0.02, CON_Y1, DECK, DECK + 0.1)
        z_lo, z_hi = DECK + 0.1, DESK_Z - 0.045
        if s == OPEN_CAB[0]:
            # 有一扇柜门半开着：柜体在这里掏空，里面一层隔板，放着罐头和纸箱
            cy0, cy1 = door_span(OPEN_CAB[1], OPEN_CAB[2])
            cz0, cz1 = zc - hz / 2 + 0.01, zc + hz / 2 - 0.01
            sbox(K["Console"], s, 0.82, 1.42, CON_Y0, cy0, z_lo, z_hi, r=0.006)
            sbox(K["Console"], s, 0.82, 1.42, cy1, CON_Y1, z_lo, z_hi, r=0.006)
            sbox(K["Console"], s, 0.82, 1.42, cy0, cy1, z_lo, cz0, r=0.003)
            sbox(K["Console"], s, 0.82, 1.42, cy0, cy1, cz1, z_hi, r=0.003)
            sbox(K["Console"], s, 1.22, 1.42, cy0, cy1, cz0, cz1)
            cabinet_contents(K, s, cy0, cy1, cz0, cz1)
        else:
            sbox(K["Console"], s, 0.82, 1.42, CON_Y0, CON_Y1, z_lo, z_hi, r=0.006)
        sbox(K["Console"], s, DESK_X, 1.42, CON_Y0 - 0.015, CON_Y1, DESK_Z - 0.045, DESK_Z - 0.003, r=0.012, seg=3)
        sbox(K["DeskTop"], s, DESK_X + 0.018, 1.36, CON_Y0 + 0.004, CON_Y1, DESK_Z - 0.006, DESK_Z, r=0.002, seg=1)
        # 桌沿包一道钢条
        sbox(K["Steel"], s, DESK_X - 0.006, DESK_X + 0.004, CON_Y0 - 0.01, CON_Y1, DESK_Z - 0.04, DESK_Z - 0.006,
             r=0.002, seg=1)
        # 灯罩（上沿）
        sbox(K["Console"], s, 0.9, 1.4, CON_Y0, 1.33, HOOD_Z[0], HOOD_Z[1], r=0.012, seg=3)
        # 柜门：每个开间两扇，门上刷着编号
        for i in range(len(cab_edges) - 1):
            for k in range(2):
                y0, y1 = door_span(i, k)
                # 开着的那扇门绕铰链（远离把手的那一边）转出来
                Md = Matrix()
                if (s, i, k) == OPEN_CAB[:3]:
                    hy = y1 if k == 1 else y0
                    ang = (-s if k == 1 else s) * OPEN_CAB[3]
                    Md = T(s * 0.805, hy, 0) @ R(ang, "Z") @ T(-s * 0.805, -hy, 0)
                rbox(K["Console"], 0.02, y1 - y0, hz, Md @ T(s * 0.815, (y0 + y1) / 2, zc), r=0.005, seg=2)
                P = Md @ frame(V((s * 0.805, (y0 + y1) / 2, zc)), V((-s, 0, 0)))
                num = 2 * i + k + 1
                K.text(f"{'右' if s > 0 else '左'}{num:02d}", P @ T(0, hz / 2 - 0.06, 0), 0.026, key="PaintText",
                       font=FONT_SERIF)
                hx = (y1 - y0) / 2 - 0.035
                handle(K, P, hx if k == 0 else -hx, 0.12, 0.09, key="Steel", standoff=0.02)
                if rng.random() < 0.5:
                    vent(K, P, 0, -0.12, (y1 - y0) * 0.6, 0.1, 9, 0.004)
                for sx in (-1, 1):
                    for sy in (-1, 1):
                        screw(K, P, sx * ((y1 - y0) / 2 - 0.012), sy * (hz / 2 - 0.012), r=0.0032)
        # 立柱（肋骨位置）+ 斜面板底部的挡条
        for y in FRAMES[1:]:
            F = panel_frame(s, y)
            rbox(K["Console"], 0.07, PANEL_LEN + 0.02, 0.06, F @ T(0, 0, 0.012), r=0.01, seg=3)
            for t in (-0.3, -0.1, 0.1, 0.3):
                cylinder(K["Steel"], 0.0075, 0.006, 6, F @ T(0, t, 0.042))
                cylinder(K["Steel"], 0.009, 0.0015, 16, F @ T(0, t, 0.042))
        F = panel_frame(s, (CON_Y0 + 1.3) / 2, 0.0)
        rbox(K["Console"], 1.3 - CON_Y0, 0.05, 0.035, F @ T(0, 0.02, 0.0), r=0.008, seg=2)
        # 灯罩下的灯管（舷窗那个开间不装）
        for i, (a, b) in enumerate(BAYS[:4]):
            yc = (a + b) / 2
            sbox(K["Steel"], s, 0.93, 0.98, yc - 0.22, yc + 0.22, HOOD_Z[0] - 0.02, HOOD_Z[0], r=0.002, seg=1)
            sweep(K["LampGlass"], [V((s * 0.955, yc - 0.2, HOOD_Z[0] - 0.02)), V((s * 0.955, yc + 0.2, HOOD_Z[0] - 0.02))],
                  circle_profile(0.011, 12))
            target = V((s * 1.1, yc, 0.15))
            p = V((s * 0.955, yc, HOOD_Z[0] - 0.045))
            anchors.append(empty(f"CabinLight_Strip_{'R' if s > 0 else 'L'}{i}", K.coll,
                                 anchor_frame(p, target - p, V((0, 1, 0)))))
        # 驾驶台两边的高机柜
        sbox(K["Console"], s, 0.8, 1.45, 1.33, CON_Y1, DESK_Z, HOOD_Z[1], r=0.012, seg=3)
        P = frame(V((s * 0.8, (1.33 + CON_Y1) / 2, 0.3)), V((-s, 0, 0)))
        vent(K, P, 0, 0.25, 0.3, 0.12, 12, 0.005)
        for sx in (-1, 1):
            for sy in (-1, 1):
                socket_screw(K, P, sx * 0.24, sy * 0.38, r=0.006)
        Pa = frame(V((0.0 + s * 1.12, 1.33, 0.3)), V((0, -1, 0)))
        vent(K, Pa, 0, 0.2, 0.3, 0.1, 10, 0.005)


def bay_panel(K, s, a, b, key="PanelGray", screws=True, hole=None):
    """一个开间的斜仪表板：厚面板 + 一圈内六角螺钉。hole=(x, y, w, h) 给嵌进去的子面板留洞。
    返回面板坐标系（正面 z=0）。"""
    yc = (a + b) / 2
    F = panel_frame(s, yc)
    w = (b - a) - 0.065
    plate_with_hole(K[key], F, w, PANEL_LEN, 0.016, hole)
    if screws:
        for k in range(5):
            y = -PANEL_LEN / 2 + 0.06 + (PANEL_LEN - 0.12) * k / 4
            for sx in (-1, 1):
                socket_screw(K, F, sx * (w / 2 - 0.018), y, r=0.0045)
    return F


def sub_panel(K, F, x, y, w, h, key="PanelDark", inset=0.018):
    """嵌在大面板里的子面板：凹进去一截，四周一道倒角的框（外面的大面板要在这里留洞，
    见 SUBS）。返回子面板坐标系。"""
    P = F @ T(x, y, -inset)
    rbox(K[key], w + 0.01, h + 0.01, 0.01, P @ T(0, 0, -0.005), r=0.002, seg=1)
    # 凹槽四壁
    for xx, yy, bw, bh in ((0, h / 2, w, 0.002), (0, -h / 2, w, 0.002), (-w / 2, 0, 0.002, h), (w / 2, 0, 0.002, h)):
        box(K["Dark"], bw, bh, inset, P @ T(xx, yy, inset / 2))
    fw = 0.022
    for xx, yy, bw, bh in ((0, h / 2 + fw / 2, w + 2 * fw, fw), (0, -h / 2 - fw / 2, w + 2 * fw, fw),
                           (-w / 2 - fw / 2, 0, fw, h), (w / 2 + fw / 2, 0, fw, h)):
        rbox(K["Bakelite"], bw, bh, inset + 0.008, P @ T(xx, yy, (inset + 0.008) / 2 - 0.002), r=0.003, seg=2)
    for sx in (-1, 1):
        for sy in (-1, 1):
            screw(K, P @ T(0, 0, 0.006), sx * (w / 2 + fw / 2), sy * (h / 2 + fw / 2), r=0.003)
    return P


# ---------------------------------------------------------------------------- 右舷（s=+1）
LAMP_COLORS = ["LensRed", "LensAmber", "LensGreen", "LensGreen", "LensAmber", "LensGreen", "LensRed", "LensGreen"]


def bay_power(K):
    """右舷 1：配电。母线电压/电流表、三排带护杆的断路器、主开关。"""
    a, b = BAYS[0]
    F = bay_panel(K, 1, a, b, "PanelGray", hole=(0, -0.06, 0.4, 0.27))
    label_plate(K, F, 0, 0.32, "配电  PD-4", 0.009)
    meter_rect(K, F, -0.1, 0.21, 0.085, "BatV", hi=150, unit="V", label="母线电压", major=5)
    meter_rect(K, F, 0.1, 0.21, 0.085, "BatA", hi=200, unit="A", label="母线电流", major=4)
    P = sub_panel(K, F, 0, -0.06, 0.4, 0.27)
    names = [["推进左", "推进右", "垂推", "侧推", "液压"], ["照明", "声呐", "通信", "生保", "加热"],
             ["机械手", "摄像", "备用", "备用", "应急"]]
    for r_, row in enumerate(names):
        for c_, lb in enumerate(row):
            x, y = -0.16 + c_ * 0.08, 0.09 - r_ * 0.085
            toggle(K, P, x, y, up=not (r_ == 2 and c_ in (2, 3)), guard=True)
            silk(K, P, x, y + 0.03, lb, 0.0062)
            lamp(K, P, x + 0.022, y - 0.012, 0.0038, "LensGreen" if (r_, c_) != (1, 4) else "LensRed")
    pointer_knob(K, F, 0, -0.27, 0.022, angle=-35)
    for ang, lb in ((-60, "断"), (0, "电池"), (60, "岸电")):
        silk(K, F, math.cos(math.radians(90 - ang)) * 0.05, -0.27 + math.sin(math.radians(90 - ang)) * 0.05, lb,
             0.0075)
    silk(K, F, -0.15, -0.27, "主开关", 0.009)
    tape_label(K, F, 0.15, -0.3, "加热别开 跳闸", 0.009, -2)


def bay_life(K):
    """右舷 2：生命支持。两根供氧流量计、氧浓度/二氧化碳表、风机开关。"""
    a, b = BAYS[1]
    F = bay_panel(K, 1, a, b, "PanelGray", hole=(-0.12, 0.08, 0.17, 0.36))
    label_plate(K, F, 0, 0.32, "生命支持  SZ-2", 0.009)
    P = sub_panel(K, F, -0.12, 0.08, 0.17, 0.36, "EquipGreen")
    rotameter(K, P, -0.04, 0.0, 0.2, "O2a", label="供氧一")
    rotameter(K, P, 0.04, 0.0, 0.2, "O2b", label="供氧二")
    silk(K, P, 0, -0.16, "L/min", 0.0065)
    meter_rect(K, F, 0.1, 0.2, 0.09, "O2", hi=25, unit="% O₂", label="氧浓度")
    meter_rect(K, F, 0.1, 0.03, 0.09, "CO2", hi=5, unit="% CO₂", label="二氧化碳")
    for x, lb, up in ((-0.16, "风机", True), (-0.08, "加热", False), (0.0, "除湿", True)):
        toggle(K, F, x, -0.2, up=up, s=1.3)
        silk(K, F, x, -0.165, lb, 0.0075)
    lamp(K, F, 0.08, -0.2, 0.006, "LensAmber")
    lamp(K, F, 0.14, -0.2, 0.006, "LensGreen")
    tape_label(K, F, 0.0, -0.29, "吸收罐 6小时一换!", 0.0105, 1.5)


def bay_hydraulics(K):
    """右舷 3：液压站。液压/补偿器压力表、泄压阀手轮、泵开关。"""
    a, b = BAYS[2]
    F = bay_panel(K, 1, a, b, "EquipGreen")
    label_plate(K, F, 0, 0.32, "液压站  YY-1", 0.009)
    gauge_round(K, F, -0.1, 0.17, 0.065, "Hyd", hi=25, label="液压", unit="MPa", major=5, red_from=0.8)
    gauge_round(K, F, 0.11, 0.17, 0.05, "Comp", hi=1, label="补偿器", unit="", major=4,
                num_labels=["0", "¼", "½", "¾", "1"])
    for x, lb, up in ((-0.16, "液压泵", True), (-0.08, "机械手", False), (0.0, "备用泵", False)):
        toggle(K, F, x, -0.05, up=up, s=1.3)
        silk(K, F, x, -0.015, lb, 0.0075)
    Mv = F @ T(0.11, -0.12, 0)
    cylinder(K["Brass"], 0.025, 0.014, 6, Mv)
    valve_wheel(K, Mv @ T(0, 0, 0.006), 0.05, "BtnRed")
    silk(K, F, 0.11, -0.2, "泄压阀", 0.0085)
    # 两根液压软管从面板下部的接头出来，弯下去从桌面上的橡胶护圈钻进柜子里
    for k, x in enumerate((-0.15, -0.09)):
        connector(K, F, x, -0.2, r=0.011, plug="Steel")
    for k, x in enumerate((-0.15, -0.09)):
        s0 = F @ V((x, -0.2, 0.035))
        n = (F.to_3x3() @ V((0, 0, 1))).normalized()
        e = V((1.1, s0.y + 0.05 * k, DESK_Z))
        Cab.add([s0, s0 + n * 0.06, (s0 + e) / 2 + n * 0.05 + V((0, 0, -0.06)), e + V((0, 0, 0.04)),
                 e - V((0, 0, 0.03))], 0.008, "CableBlack")
        lathe(K["Rubber"], [(0.009, 0.0), (0.017, 0.0), (0.017, 0.004), (0.013, 0.007), (0.009, 0.007)], 20,
              T(e.x, e.y, DESK_Z))


def bay_env(K, anchors):
    """右舷 4：舱内环境 + 示波器（放在桌上）。"""
    a, b = BAYS[3]
    F = bay_panel(K, 1, a, b, "PanelGray", hole=(0, -0.18, 0.36, 0.1))
    label_plate(K, F, 0, 0.32, "舱内环境", 0.009)
    gauge_round(K, F, -0.1, 0.2, 0.05, "Temp", hi=50, label="舱温", unit="℃", major=5)
    gauge_round(K, F, 0.1, 0.2, 0.05, "Hum", hi=100, label="湿度", unit="%", major=5)
    gauge_round(K, F, 0.0, 0.05, 0.045, "Pressure", hi=2, label="舱压", unit="kgf/cm²", major=4)
    P = sub_panel(K, F, 0, -0.18, 0.36, 0.1)
    for k, a_ in enumerate(("2A", "5A", "5A", "10A", "2A", "1A")):
        fuse(K, P, -0.15 + k * 0.06, 0.01, a_)
    sticky_note(K, F, 0.15, 0.06, ["电话频道 3", "备用 7"], 0.0085, angle=4)
    # 桌上的示波器
    p = V((1.0, (a + b) / 2 + 0.05, DESK_Z))
    anchors.append(empty("Anchor_Scope", K.coll, anchor_frame(p, V((1, 0.15, 0)))))


# ---------------------------------------------------------------------------- 左舷（s=-1）
def bay_shrine(K, anchors):
    """左舷 1：船员把一个开间改成了神龛。面板上光秃秃的，贴满了符纸。"""
    a, b = BAYS[0]
    F = bay_panel(K, -1, a, b, "PanelDark")
    for x, y, ang, txt in ((-0.16, 0.18, -4, "敕令\n镇海"), (0.17, 0.2, 3, "出入\n平安"), (0.02, 0.27, -1, "镇\n海"),
                           (-0.13, -0.05, 6, "唵\n嘛呢"), (0.15, -0.02, -7, "敕\n令")):
        Mt = F @ T(x, y, 0.0004) @ R(ang, 'Z')
        rbox(K["Talisman"], 0.05, 0.16, 0.0006, Mt, r=0.0, seg=1)
        K.text(txt, Mt @ T(0, 0, 0.0003), 0.11, key="BrushRed", font=FONT_BRUSH)
    tape_label(K, F, 0.0, 0.33, "别动", 0.014, -3)
    G = frame(V((-1.0, (a + b) / 2, DESK_Z + 0.165)), V((1, 0, 0)))
    shrine(K, anchors, G)


def bay_nav(K, anchors):
    """左舷 2：导航。罗经复示器、航速表、航程计、海图夹。"""
    a, b = BAYS[1]
    F = bay_panel(K, -1, a, b, "PanelGray")
    label_plate(K, F, 0, 0.32, "导航  DH-2", 0.009)
    gauge_round(K, F, -0.08, 0.15, 0.085, "Heading2", hi=360, label="罗经复示", major=8, sub=3, start=90,
                sweep_deg=360, num_labels=["北", "", "东", "", "南", "", "西", ""])
    gauge_round(K, F, 0.13, 0.2, 0.045, "Speed", hi=4, label="航速", unit="节", major=4)
    silk(K, F, 0.13, 0.09, "航程 km", 0.0075)
    seg_display(K, F, 0.13, 0.06, 0.1, 0.03, "Log")
    for x, lb in ((-0.15, "照度"), (-0.06, "复位"), (0.03, "校准")):
        knob(K, F, x, -0.12, 0.012, 0.015, ticks=7)
        silk(K, F, x, -0.085, lb, 0.0075)
    sticky_note(K, F, 0.13, -0.12, ["7月14", "老陈没回来"], 0.0095, angle=6)
    anchors.append(empty("Anchor_Logbook", K.coll, anchor_frame(V((-0.98, (a + b) / 2 - 0.05, DESK_Z)),
                                                                 V((-1, 0.3, 0)))))


def bay_powerbox(K, anchors):
    """左舷 3：配电箱（素材）装在面板上，门开着。"""
    a, b = BAYS[2]
    F = bay_panel(K, -1, a, b, "EquipGray")
    G = F @ T(0, 0.06, 0)
    anchors.append(empty("Anchor_PowerBox", K.coll, wall_anchor(G, 0.048)))
    label_plate(K, F, 0, -0.27, "照明配电", 0.0085)
    for k in range(4):
        toggle(K, F, -0.12 + k * 0.08, -0.32, up=k != 2)


def bay_comms(K, anchors):
    """左舷 4：水声电话。桌上一台老电台，面板上旋钮和耳机挂钩。"""
    a, b = BAYS[3]
    F = bay_panel(K, -1, a, b, "PanelGray")
    label_plate(K, F, 0, 0.32, "水声通信  UQC", 0.009)
    for x, lb in ((-0.15, "增益"), (-0.05, "量程"), (0.05, "音量"), (0.15, "静噪")):
        knob(K, F, x, 0.2, 0.015, 0.017, ticks=9)
        silk(K, F, x, 0.245, lb, 0.0075)
    meter_rect(K, F, -0.1, 0.03, 0.08, "Signal", hi=10, unit="dB", label="信号", major=5)
    for k in range(3):
        connector(K, F, 0.06 + k * 0.05, 0.03, r=0.01, plug="Olive" if k != 1 else "Steel")
    headset(K, F @ T(0.12, -0.12, 0))
    anchors.append(empty("Anchor_Radio", K.coll, anchor_frame(V((-1.0, (a + b) / 2 + 0.02, DESK_Z)), V((-1, 0, 0)))))
    anchors.append(empty("Anchor_Walkman", K.coll, anchor_frame(V((-0.86, (a + b) / 2 - 0.22, DESK_Z)),
                                                                 V((-0.4, -1, 0)))))


def headset(K, P):
    """挂在面板挂钩上的耳机。P 的原点是挂钩根部。"""
    sweep(K["Steel"], catmull([P @ V((0, 0, 0)), P @ V((0, 0, 0.035)), P @ V((0, 0.02, 0.05))], 6),
          circle_profile(0.003, 8))
    cylinder(K["Steel"], 0.008, 0.004, 12, P)
    F = P @ T(0, -0.005, 0.045)
    arc = [F @ V((math.cos(math.radians(a)) * 0.075, -0.075 + math.sin(math.radians(a)) * 0.075, 0))
           for a in range(10, 171, 8)]
    sweep(K["Knob"], arc, [(-0.0025, -0.012), (0.0025, -0.012), (0.0025, 0.012), (-0.0025, 0.012)])
    for sx in (-1, 1):
        Mc = F @ T(sx * 0.078, -0.1, 0) @ R(90 * sx, 'Y')
        cylinder(K["Knob"], 0.036, 0.022, 32, Mc @ T(0, 0, -0.022))
        torus(K["Vinyl"], 0.03, 0.009, 32, 10, Mc @ T(0, 0, 0.003))
    s = F @ V((-0.078, -0.12, 0))
    Cab.add([s, s + V((0, 0, -0.08)), s + V((0.0, 0.05, -0.2)), V((-1.1, s.y + 0.1, DESK_Z + 0.01))], 0.0025,
            "CableBlack")


# ============================================================================ 舷窗
def viewports(K, anchors):
    for s in (-1, 1):
        o, d = vp_axis(s)
        F = frame(o, d)
        # 加强座：深入舱内 15 厘米的厚钢圈，外圈一块覆板焊在壳上
        prof = [(0.15, 1.195), (0.225, 1.195), (0.245, 1.215), (0.245, 1.43),
                (0.165, 1.43), (0.165, 1.47), (0.15, 1.47)]
        lathe(K["HullInner"], prof + [prof[0]], 96, F)
        # 压环
        lathe(K["EquipGray"], [(0.147, 1.205), (0.147, 1.18), (0.153, 1.172), (0.228, 1.172), (0.235, 1.18),
                               (0.235, 1.205), (0.147, 1.205)], 96, F)
        Pr = F @ T(0, 0, 1.172) @ R(180, 'X')
        for i in range(12):
            ang = 2 * math.pi * (i + 0.5) / 12
            socket_screw(K, Pr, math.cos(ang) * 0.19, math.sin(ang) * 0.19, r=0.0075)
        torus(K["Rubber"], 0.151, 0.004, 64, 8, F @ T(0, 0, 1.2))
        # 窗玻璃本身在外壳模型里（Viewport_Glass），从舱内看到的就是它的内表面
        # 窗下一块橡胶垫肘的托板
        sbox(K["Vinyl"], s, DESK_X + 0.08, 1.2, VP_Y - 0.2, VP_Y + 0.2, DESK_Z, DESK_Z + 0.04, r=0.015, seg=3)
        anchors.append(empty(f"Anchor_Lean_{'R' if s > 0 else 'L'}", K.coll,
                             anchor_frame(o + d * 0.98, d)))
        # 窗边的小控制盒（摄像机 / 外部照明）
        P = frame(V((s * 0.96, VP_Y + 0.21, 0.36)), V((-s, -0.35, -0.2)).normalized())
        if s < 0:
            unit(K, P, 0.12, 0.16, 0.09, body="EquipBlue", face="PanelDark", handles=False)
            label_plate(K, P, 0, 0.062, "摄像", 0.0062)
            lathe(K["Rubber"], [(0.022, 0), (0.022, 0.004), (0.012, 0.016), (0.006, 0.02), (0, 0.02)], 24,
                  P @ T(0, 0.018, 0))
            cylinder(K["Knob"], 0.004, 0.03, 12, P @ T(0, 0.018, 0.015))
            uvsphere(K["Knob"], 0.007, 16, 8, P @ T(0, 0.018, 0.047))
            for x, cap, lb in ((-0.03, "BtnBlack", "变焦"), (0.0, "BtnBlack", "聚焦"), (0.03, "BtnRed", "录像")):
                button(K, P, x, -0.035, 0.006, cap)
                silk(K, P, x, -0.052, lb, 0.0052)
        else:
            unit(K, P, 0.12, 0.16, 0.09, body="EquipGray", face="PanelDark", handles=False)
            label_plate(K, P, 0, 0.062, "外部照明", 0.006)
            for y, lb in ((0.025, "左灯"), (-0.02, "右灯")):
                knob(K, P, -0.025, y, 0.011, 0.013, ticks=7)
                silk(K, P, 0.025, y + 0.008, lb, 0.0058)
                lamp(K, P, 0.025, y - 0.008, 0.004, "LensWhite")
            toggle(K, P, 0, -0.058, up=True)
        # 盒子背面一根支杆斜插到灯罩底下
        back = P @ V((0, 0, -0.09))
        sweep(K["Steel"], [back, V((s * 1.12, back.y, HOOD_Z[0]))], circle_profile(0.008, 10))


# ============================================================================ 舱口和直梯（生活舱顶上）
def hatch(K):
    """出入舱口：围板 + 舱口筒（顶到艇外上层建筑的甲板）+ 舱盖 + 直梯。"""
    hx, hy = HATCH
    M0 = T(hx, hy, 0)
    # 围板（补强座）+ 舱口筒
    lathe(K["HullInner"], [(HATCH_R, 1.2), (0.4, 1.2), (0.43, 1.23), (0.43, 1.42), (HATCH_R, 1.42), (HATCH_R, 1.2)],
          96, M0)
    K.separate("Int_HatchTrunk", "HullInner",
               lambda bm: lathe(bm, [(HATCH_R, 1.42), (HATCH_R, HATCH_TOP + 0.03)], 64, M0, flip=True), recalc=False)
    for i in range(16):
        a = 2 * math.pi * i / 16
        cylinder(K["Steel"], 0.011, 0.014, 6, M0 @ T(math.cos(a) * 0.365, math.sin(a) * 0.365, 1.186))
    # 舱盖：底面、密封圈、手轮、四个压紧块
    cylinder(K["EquipGray"], HATCH_R, 0.03, 64, M0 @ T(0, 0, HATCH_TOP))
    torus(K["Rubber"], HATCH_R - 0.008, 0.007, 64, 8, M0 @ T(0, 0, HATCH_TOP - 0.002))
    cylinder(K["Steel"], 0.035, 0.12, 24, M0 @ T(0, 0, HATCH_TOP - 0.12))
    valve_wheel(K, M0 @ T(0, 0, HATCH_TOP) @ R(180, 'X'), 0.15, "BtnRed", 5)
    for i in range(4):
        a = math.radians(45 + 90 * i)
        Md = M0 @ T(math.cos(a) * 0.24, math.sin(a) * 0.24, HATCH_TOP - 0.02) @ R(math.degrees(a), 'Z')
        rbox(K["Steel"], 0.08, 0.035, 0.03, Md, r=0.004, seg=2)
    # 直梯：扁钢立柱 + 防滑圆钢踏棍，脚板用螺栓固定在地板上，上端焊在舱口筒壁上
    top = HATCH_TOP - 0.1
    for sx in (-1, 1):
        x = sx * 0.18
        rbox(K["Steel"], 0.012, 0.06, top - DECK, T(x, LADDER_Y, (top + DECK) / 2), r=0.003, seg=1)
        rbox(K["Steel"], 0.06, 0.12, 0.008, T(x, LADDER_Y, DECK + 0.004), r=0.002, seg=1)
        rbox(K["Steel"], 0.01, 0.05, 0.14, T(x, LADDER_Y - 0.035, 1.3), r=0.002, seg=1)
        for k in range(4):
            cylinder(K["Steel"], 0.006, 0.004, 6,
                     T(x + (k // 2 - 0.5) * 0.04, LADDER_Y + (k % 2 - 0.5) * 0.08, DECK + 0.008))
    for k in range(8):
        z = DECK + 0.25 + k * 0.28
        cylinder(K["Steel"], 0.013, 0.36, 12, T(-0.18, LADDER_Y, z) @ R(90, 'Y'))
        for j in range(8):
            torus(K["Steel"], 0.0128, 0.0018, 12, 4, T(-0.12 + j * 0.034, LADDER_Y, z) @ R(90, 'Y'))


# ============================================================================ 中间隔壁和水密门
# 快速水密门：中间一个手轮，经过减速箱带动曲柄盘，六根连杆同时拨动门扇四周的六个压紧把手（门轴那一侧在两个
# 铰链中间也有一个）。把手压在门框外圈焊的楔块上，把门扇连同密封胶条压到门框的刀口上。
DOOR_DOGS = (90, 25, 0, -25, -90, 180)  # 压紧把手的位置（门洞椭圆的参数角，0° 朝右舷、90° 朝上）
DOOR_SPINDLE_K = -0.02  # 把手转轴离门洞边（负数 = 在门洞里面一点，背面的螺母从门洞里看得见）
DOOR_CRANK_B = 0.06     # 曲柄盘上连杆销的半径
DOOR_ARM_A = 0.055      # 把手曲臂长
DOOR_LEAF_K = 0.07      # 门扇外沿离门洞边
DOOR_FRAME_K = 0.085    # 门框外圈离门洞边
DOOR_DOUBLER_K = 0.13   # 门框外面焊的补强板外沿离门洞边
DOOR_HINGE_Z = 0.35     # 两个铰链离门中心的高度


def door_ring(t_deg, k):
    """门洞椭圆沿法线往外偏 k 的那一圈上、参数角 t 处的点（世界 x、z，y=0）和外法线。"""
    dx, dz, da, db = DOOR
    t = math.radians(t_deg)
    n = V((db * math.cos(t), 0, da * math.sin(t))).normalized()
    return V((dx + da * math.cos(t), 0, dz + db * math.sin(t))) + n * k, n


def door_loop(k, y, n=96):
    return [door_ring(360 * i / n, k)[0] + V((0, y, 0)) for i in range(n)]


def door_dog_layout():
    """每个压紧把手的转轴 S、把手朝外的方向、曲柄盘上的销 A0、曲臂上的销 B0（门平面里 (x, z)，关门状态）。
    连杆基本上沿「门中心→转轴」方向，两头的销都偏到同一侧（逆时针转 90°），曲柄盘逆时针一转，
    所有连杆一起往里拉，把手跟着逆时针转开、离开楔块。"""
    dx, dz = DOOR[0], DOOR[1]
    C = V((dx, 0, dz))
    out = []
    for deg in DOOR_DOGS:
        S, n = door_ring(deg, DOOR_SPINDLE_K)
        d = (S - C).normalized()
        p = V((-d.z, 0, d.x))
        out.append((S, n, C + p * DOOR_CRANK_B, S + p * DOOR_ARM_A))
    return out


def plate_xz(bm, pts, y0, h):
    """门平面里的板：pts 是 (x, z) 多边形，从 y0 往 +Y 拉伸 h（h 为负就往 -Y）。"""
    if h < 0:
        y0, h = y0 + h, -h
    extrude_profile(bm, [(x, -z) for x, z in pts], T(0, y0, 0) @ R(-90, 'X'), h)


def bulkhead(K, anchors):
    """控制舱和生活舱之间的隔壁（两面都看得见）。
    - 门洞四周一圈厚门框穿过隔壁，控制舱一面有一道刀口；门框外面两面各焊一圈补强板，补强板上焊着楔块和铰链座
    - 竖向加强筋只在生活舱一面（门两边各一根，到桥架下面削斜收头）；管子、电缆桥架从门上方穿过去
      （套管和穿舱框在 overhead 里做，见 pipe_sleeve、cable_transit）
    - 门扇往控制舱一侧开，门轴在左舷。门扇、手轮、曲柄盘、压紧把手、连杆都单独导出（Door_*），
      Godot 里由 watertight_door.gd 带着转：手轮转一圈多 → 曲柄盘转 50° → 连杆拉着六个把手一起转开。"""
    dx, dz, da, db = DOOR
    y = Y_AFT
    t_plate = 0.012
    ya = y - t_plate

    def inside_door(x, z, k=1.0):
        return ((x - dx) / (da * k)) ** 2 + ((z - dz) / (db * k)) ** 2 < 1.0

    def plate(bm, yy, back=False):
        """隔壁板（单面），门洞和外圈的锯齿由门框、角焊盖住（门洞挖得比门框内沿大一圈，锯齿才藏得住）。"""
        import bmesh
        step = 0.03
        nx = int(2 * R_IN / step) + 3
        nz = int((R_IN - DECK) / step) + 3
        verts = {}

        def vtx(i, j):
            if (i, j) not in verts:
                verts[(i, j)] = bm.verts.new(V((-R_IN - step + i * step, yy, DECK - 0.03 + j * step)))
            return verts[(i, j)]
        for i in range(nx):
            for j in range(nz):
                cx = -R_IN - step + (i + 0.5) * step
                cz = DECK - 0.03 + (j + 0.5) * step
                if math.hypot(cx, cz) > R_IN + 0.02 or inside_door(cx, cz, 1.08):
                    continue
                bm.faces.new([vtx(i, j), vtx(i, j + 1), vtx(i + 1, j + 1), vtx(i + 1, j)])
        if back:
            bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
    K.separate("Int_Bulkhead", "HullInner", lambda bm: plate(bm, y), recalc=False)
    K.separate("Int_BulkheadAft", "HullInner", lambda bm: plate(bm, ya, back=True), recalc=False)
    bm = K["HullInner"]
    # 隔壁和壳体的连接处一圈角焊（两面）
    ring_sweep(bm, [(R_IN + 0.01, 0.0), (R_IN - 0.035, 0.0), (R_IN + 0.01, 0.045)][::-1], y, -140, 140, 180)
    ring_sweep(bm, [(R_IN + 0.01, 0.0), (R_IN - 0.035, 0.0), (R_IN + 0.01, -0.045)], ya, -140, 140, 180)
    # 生活舱一面的竖向加强筋（T 型材）：腹板上端削斜，翼板比腹板短一截
    for xs in (-0.66, 0.66):
        web = [(0.0, DECK), (-0.08, DECK), (-0.08, 0.64), (-0.025, 0.72), (0.0, 0.72)]
        extrude_profile(bm, web, frame(V((xs - 0.006, ya, 0)), V((1, 0, 0))), 0.012)
        rbox(bm, 0.06, 0.012, 0.64 - DECK, T(xs, ya - 0.074, (0.64 + DECK) / 2), r=0.003, seg=1)
        for sx in (-1, 1):  # 腹板两边的角焊
            sweep(bm, [V((xs + sx * 0.006, ya, DECK)), V((xs + sx * 0.006, ya, 0.7))],
                  [(0, 0), (sx * 0.007, 0), (0, -0.007)], up_hint=V((0, 1, 0)))

    # ---- 门框：一圈厚扁钢穿过隔壁（控制舱一面凸出 5 厘米，生活舱一面 6 厘米），里沿倒圆；
    # 控制舱一面有一道刀口，关门时门扇背面的胶条压在上面
    up = V((0, 1, 0))
    prof = [(0.008, -0.07), (DOOR_FRAME_K, -0.07), (DOOR_FRAME_K, 0.05), (0.042, 0.05), (0.042, 0.06),
            (0.039, 0.064), (0.033, 0.064), (0.03, 0.06), (0.03, 0.05), (0.008, 0.05), (0.0, 0.042),
            (0.0, -0.062)]
    sweep(bm, door_loop(0.0, y), prof, closed=True, up_hint=up)
    for yy, sg in ((y, 1), (ya, -1)):
        k0, k1 = DOOR_FRAME_K, DOOR_DOUBLER_K
        for pr in ([(k0, 0.0), (k1, 0.0), (k1, 0.006), (k1 - 0.004, 0.01), (k0, 0.01)],   # 补强板
                   [(k0, 0.0098), (k0 + 0.008, 0.0098), (k0, 0.018)],                    # 门框和补强板之间的角焊
                   [(k1 - 0.001, 0.0), (k1 + 0.006, 0.0), (k1 - 0.001, 0.007)]):          # 补强板外沿的角焊
            sweep(bm, door_loop(0.0, yy), [(u, sg * v) for u, v in pr], closed=True, up_hint=up)
    # 楔块：焊在门框外圈和补强板上，顶面一头有个斜坡（把手从那边转回来压上去）
    for deg in DOOR_DOGS:
        q, n = door_ring(deg, DOOR_FRAME_K - 0.004)
        F = frame(q + V((0, y, 0)), n, up)
        extrude_profile(K["Steel"], [(-0.026, 0.006), (0.026, 0.006), (0.026, 0.124), (-0.006, 0.124),
                                     (-0.026, 0.108)], F, 0.05)
    # 铰链座：门轴竖着，上下两个。每个是一块底板焊在补强板上，两块耳板夹住门扇上的铰链臂，一根销子穿过去
    hx, hy = DOOR_HINGE
    lug = ([(hx - 0.045, y + 0.022), (hx + 0.04, y + 0.022), (hx + 0.036, hy - 0.012)]
           + [(hx + math.cos(math.radians(a)) * 0.036, hy + math.sin(math.radians(a)) * 0.036)
              for a in range(0, 181, 20)] + [(hx - 0.045, hy - 0.01)])
    for zz in (dz - DOOR_HINGE_Z, dz + DOOR_HINGE_Z):
        rbox(K["Steel"], 0.1, 0.022, 0.16, T(hx - 0.005, y + 0.011, zz), r=0.003, seg=1)
        for zl in (zz + 0.037, zz - 0.053):
            extrude_profile(K["Steel"], lug, T(0, 0, zl), 0.016)
        cylinder(K["Steel"], 0.012, 0.13, 16, T(hx, hy, zz - 0.068))
        lathe(K["Steel"], [(0.0, 0.0), (0.02, 0.0), (0.02, 0.005), (0.015, 0.011), (0.0, 0.012)], 20,
              T(hx, hy, zz + 0.053))
        cylinder(K["Steel"], 0.019, 0.011, 6, T(hx, hy, zz - 0.064))
        sweep(K["Steel"], catmull([V((hx - 0.016, hy, zz - 0.07)), V((hx, hy, zz - 0.07)),
                                   V((hx + 0.016, hy, zz - 0.07)), V((hx + 0.022, hy + 0.006, zz - 0.074))], 3),
              circle_profile(0.0018, 6))   # 开口销
        for sx in (-1, 1):
            cylinder(K["Steel"], 0.007, 0.006, 6, T(hx - 0.005 + sx * 0.035, y + 0.022, zz) @ R(-90, 'X'))
    anchors.append(empty("Door_Hinge", K.coll, anchor_frame(V((hx, hy, dz)), up)))
    # 门两边的扶手（低头钻门时抓的），两面都有
    for yy, sg in ((y, 1), (ya, -1)):
        for x in (-0.52, 0.52):
            P = frame(V((x, yy, 0.18)), V((0, sg, 0)))
            handle(K, P, 0, 0, 0.36, axis='Y', key="Steel", standoff=0.055)
            for zz in (-0.18, 0.18):
                rbox(K["Steel"], 0.04, 0.04, 0.006, P @ T(0, zz, 0.003), r=0.002, seg=1)

    door_leaf(K, anchors)

    # ---- 控制舱一侧：门上方的铭牌和刷漆字、灯、氧气瓶、接线盒
    P = frame(V((dx, y, dz + db + DOOR_DOUBLER_K + 0.075)), up)
    label_plate(K, P, 0, 0, "2号水密门  通生活舱", 0.014)
    K.text("当心碰头", frame(V((dx, y, dz + db + DOOR_DOUBLER_K + 0.115)), up), 0.026, key="Ink")
    K.text("水密门 随手关闭", frame(V((dx, y + 0.001, DECK + 0.1)), up), 0.035, key="InkRed")
    ceiling_lamp(K, anchors, T(0.85, y, 0.42) @ R(-90, 'X'), "CabinLight_Aft")
    # 两个氧气瓶 + 绑带 + 减压阀和压力表；出来一根紫铜管顺着隔壁爬上去，沿舱顶往前接到生命支持柜
    for i, x in enumerate((0.76, 0.92)):
        base = V((x, y + 0.1, DECK))
        lathe(K["O2"], [(0.0, 0.0), (0.065, 0.0), (0.075, 0.015), (0.075, 0.62), (0.065, 0.67), (0.03, 0.7),
                        (0.022, 0.72), (0.0, 0.72)], 48, T(*base))
        cylinder(K["Brass"], 0.018, 0.06, 16, T(*base) @ T(0, 0, 0.72))
        K.text("氧", frame(base + V((0, 0.076, 0.4)), up), 0.07, key="Ink")
        for z in (0.2, 0.55):
            torus(K["Rail"], 0.078, 0.006, 48, 6, T(x, y + 0.1, DECK + z) @ S(1, 1, 3))
    rbox(K["Rail"], 0.3, 0.02, 0.6, T(0.84, y + 0.012, DECK + 0.35), r=0.003, seg=1)
    Mr = T(0.76, y + 0.1, DECK + 0.78)
    rbox(K["Brass"], 0.05, 0.04, 0.05, Mr @ T(0, 0, 0.04), r=0.004, seg=2)
    Pg = frame(V((0.76, y + 0.125, DECK + 0.82)), up)
    gauge_round(K, Pg, 0, 0, 0.026, "O2Tank", hi=25, label="MPa", major=5, flange=False, red_from=None)
    o2_line(K)
    # 接线盒：线从盒顶出来，顺着隔壁往上，并进左舷的电缆桥架（见 overhead）
    junction_box(K, frame(V((-0.92, y, 0.35)), up))
    anchors.append(empty("Anchor_Extinguisher", K.coll, anchor_frame(V((-0.9, -1.98, DECK)), V((-1, 0, 0)))))
    # 防毒面具挂在后部左舷壳体的钩子上
    hook = V((-math.sqrt(R_IN ** 2 - 0.55 ** 2) + 0.005, -2.3, 0.55))
    inn = -V((hook.x, 0, hook.z)).normalized()
    sweep(K["Steel"], catmull([hook, hook + inn * 0.04, hook + inn * 0.055 + V((0, 0, 0.025))], 6),
          circle_profile(0.004, 8))
    cylinder(K["Steel"], 0.014, 0.006, 16, frame(hook, inn))
    anchors.append(empty("Anchor_GasMask", K.coll, anchor_frame(hook + inn * 0.05, -inn)))
    anchors.append(empty("Anchor_Medical", K.coll, anchor_frame(V((0.72, -2.08, DECK)), V((1, 0.1, 0)))))

    # ---- 生活舱一侧：门上方的铭牌、刷漆字
    P = frame(V((dx, ya, dz + db + DOOR_DOUBLER_K + 0.075)), -up)
    label_plate(K, P, 0, 0, "2号水密门  通控制舱", 0.014)
    K.text("当心碰头", frame(V((dx, ya, dz + db + DOOR_DOUBLER_K + 0.115)), -up), 0.026, key="InkRed")
    K.text("水密门 随手关闭", frame(V((dx, ya - 0.001, DECK + 0.1)), -up), 0.035, key="InkRed")


def door_leaf(K, anchors):
    """门扇和上面的机构。
    门扇：12 毫米钢板，正面（控制舱）一圈包边扁钢，背面一圈胶条槽（胶条压在门框刀口上）和两道横加强筋。
    正面中间是减速箱，上面的曲柄盘（Door_Crank_*）带六根连杆（Door_Rod_k），拉动四周的压紧把手（Door_Dog{k}_*）；
    手轮两面各一个（Door_Wheel_*），一根轴穿过门扇。"""
    dx, dz, da, db = DOOR
    y = Y_AFT
    hx, hy = DOOR_HINGE
    yb, yf = y + 0.085, y + 0.097      # 门板背面、正面
    up = V((0, 1, 0))
    D = Parts(K.coll, K.M, "Door_Leaf")
    W = Parts(K.coll, K.M, "Door_Wheel")
    Cr = Parts(K.coll, K.M, "Door_Crank")
    plate_xz(D["Console"], [(p.x, p.z) for p in door_loop(DOOR_LEAF_K, 0.0)], yb, yf - yb)
    ring0 = door_loop(0.0, y)
    # 正面包边扁钢；背面胶条槽（两道槽壁夹着胶条，胶条面比槽壁高出一毫米）
    sweep(D["Console"], ring0, [(0.052, 0.0965), (DOOR_LEAF_K, 0.0965), (DOOR_LEAF_K, 0.119), (0.067, 0.122),
                                (0.052, 0.122)], closed=True, up_hint=up)
    for k0, k1 in ((0.018, 0.023), (0.049, 0.054)):
        sweep(D["Steel"], ring0, [(k0, 0.066), (k1, 0.066), (k1, 0.0855), (k0, 0.0855)], closed=True, up_hint=up)
    sweep(D["Rubber"], ring0, [(0.023, 0.065), (0.049, 0.065), (0.049, 0.0855), (0.023, 0.0855)], closed=True,
          up_hint=up)
    # 背面两道横加强筋（扁钢立着焊，两头削斜），都在门洞里面，开关门时不碰门框
    for zz in (-0.3, 0.3):
        L = da * math.sqrt(1 - (zz / db) ** 2) - 0.05
        extrude_profile(D["Console"], [(-L, yb + 0.0005), (L, yb + 0.0005), (L - 0.025, yb - 0.045),
                                       (-L + 0.025, yb - 0.045)], T(0, 0, dz + zz - 0.006), 0.012)
    # 背面中间：手轮轴的填料函（压盖 + 两颗螺栓）
    lathe(D["Console"], [(0.0, yb), (0.04, yb), (0.04, yb - 0.012), (0.032, yb - 0.02), (0.0, yb - 0.02)], 32,
          T(dx, 0, dz) @ R(-90, 'X'))
    Mg = T(dx, yb - 0.02, dz)
    rbox(D["Steel"], 0.1, 0.008, 0.03, Mg @ T(0, -0.004, 0), r=0.004, seg=2)
    for sx in (-1, 1):
        cylinder(D["Steel"], 0.0065, 0.012, 6, Mg @ T(sx * 0.04, -0.008, 0) @ R(90, 'X'))
    # 正面中间：减速箱（铸铁圆壳，盖子一圈螺栓）
    Mb = T(dx, yf, dz) @ R(-90, 'X')
    lathe(D["Console"], [(0.0, 0.0), (0.076, 0.0), (0.076, 0.03), (0.07, 0.036), (0.07, 0.04), (0.0, 0.04)], 40, Mb)
    for i in range(8):
        a = 2 * math.pi * (i + 0.5) / 8
        cylinder(D["Steel"], 0.0055, 0.004, 6, Mb @ T(math.cos(a) * 0.063, math.sin(a) * 0.063, 0.04))
    # 铰链臂：一头套在销子上，一头用四颗螺栓压在门扇正面的垫块上
    for zz in (dz - DOOR_HINGE_Z, dz + DOOR_HINGE_Z):
        cylinder(D["Steel"], 0.03, 0.068, 24, T(hx, hy, zz - 0.034))
        rbox(D["Steel"], -0.22 - hx - 0.02, 0.026, 0.064, T((hx + 0.02 - 0.22) / 2, hy + 0.007, zz), r=0.004, seg=2)
        rbox(D["Steel"], 0.11, 0.027, 0.08, T(-0.27, yf + 0.0135, zz), r=0.003, seg=1)
        for bx in (-0.3, -0.24):
            for bz in (-0.022, 0.022):
                cylinder(D["Steel"], 0.007, 0.006, 6, T(bx, hy + 0.02, zz + bz) @ R(-90, 'X'))
    # 压紧把手的轴套（门扇的一部分）；把手、曲臂、轴（Door_Dog{k}_*）绕轴套转
    layout = door_dog_layout()
    for S, n, A0, B0 in layout:
        lathe(D["Console"], [(0.0, 0.0), (0.021, 0.0), (0.021, 0.024), (0.017, 0.027), (0.0, 0.027)], 24,
              T(S.x, yf - 0.001, S.z) @ R(-90, 'X'))
        lathe(D["Console"], [(0.0, 0.0), (0.019, 0.0), (0.019, 0.008), (0.0, 0.008)], 24,
              T(S.x, yb, S.z) @ R(90, 'X'))
    yc = y + 0.1465                    # 曲柄盘中面
    # 连杆中面：相邻两根错开一层，转动时从彼此上面交叉过去
    yrs = [y + 0.158 + (0.0125 if k % 2 else 0.0) for k in range(len(layout))]
    for k, (S, n, A0, B0) in enumerate(layout):
        yr = yrs[k]
        G = Parts(K.coll, K.M, f"Door_Dog{k}")
        pn = V((-n.z, 0, n.x))

        def P2(u, v, S=S, n=n, pn=pn):
            q = S + n * u + pn * v
            return q.x, q.z
        # 把手：锻钢扁条，底面贴着楔块顶面滑上去
        plate_xz(G["Steel"], [P2(0.0, -0.015), P2(0.12, -0.011), P2(0.15, -0.007), P2(0.156, 0.0),
                              P2(0.15, 0.007), P2(0.12, 0.011), P2(0.0, 0.015)], y + 0.1255, 0.0155)
        cylinder(G["Steel"], 0.02, 0.0155, 24, T(S.x, y + 0.1255, S.z) @ R(-90, 'X'))
        # 轴：穿过门扇，背面一颗螺母
        cylinder(G["Steel"], 0.011, y + 0.147 - (yb - 0.02), 16, T(S.x, yb - 0.02, S.z) @ R(-90, 'X'))
        cylinder(G["Steel"], 0.014, 0.009, 6, T(S.x, yb - 0.008, S.z) @ R(90, 'X'))
        # 曲臂 + 销子，轴顶一颗螺母
        d = (B0 - S).normalized()
        dn = V((-d.z, 0, d.x))
        arm = [S + dn * 0.016, B0 + dn * 0.011, B0 - dn * 0.011, S - dn * 0.016]
        plate_xz(G["Steel"], [(q.x, q.z) for q in arm], y + 0.1425, 0.008)
        for q, r_ in ((S, 0.016), (B0, 0.011)):
            cylinder(G["Steel"], r_, 0.008, 20, T(q.x, y + 0.1425, q.z) @ R(-90, 'X'))
        cylinder(G["Steel"], 0.0062, yr + 0.0105 - (y + 0.15), 12, T(B0.x, y + 0.15, B0.z) @ R(-90, 'X'))
        cylinder(G["Steel"], 0.0085, 0.003, 12, T(B0.x, yr + 0.0075, B0.z) @ R(-90, 'X'))
        cylinder(G["Steel"], 0.014, 0.008, 6, T(S.x, y + 0.1505, S.z) @ R(-90, 'X'))
        G.flush()
        anchors.append(empty(f"Door_DogAxis_{k}", K.coll, anchor_frame(S + V((0, y + 0.13, 0)), up)))
        anchors.append(empty(f"Door_DogPin_{k}", K.coll, anchor_frame(B0 + V((0, yr, 0)), up)))
        # 连杆：两头叉耳套在销子上，中间一个花篮螺母（调长度用）
        u = (B0 - A0)
        L = u.length
        u.normalize()
        z_ = u.cross(up)
        Mrod = Matrix(((u.x, 0, z_.x, A0.x), (u.y, 1, z_.y, yr), (u.z, 0, z_.z, A0.z), (0, 0, 0, 1)))

        def rod(bm, L=L):
            cylinder(bm, 0.0052, L - 0.02, 12, T(0.01, 0, 0) @ R(90, 'Y'))
            for x in (0.0, L):
                lathe(bm, [(0.0, -0.0062), (0.0115, -0.0062), (0.0125, -0.005), (0.0125, 0.005),
                           (0.0115, 0.0062), (0.0, 0.0062)], 16, T(x, 0, 0) @ R(-90, 'X'))
            cylinder(bm, 0.0085, 0.045, 6, T(L * 0.5 - 0.0225, 0, 0) @ R(90, 'Y'))
        K.separate(f"Door_Rod_{k}", "Steel", rod).matrix_world = Mrod
    # 曲柄盘：减速箱输出轴上的一块圆盘，六个连杆销
    cylinder(Cr["Steel"], 0.08, 0.009, 48, T(dx, yc - 0.0045, dz) @ R(-90, 'X'))
    lathe(Cr["Steel"], [(0.0, 0.0), (0.03, 0.0), (0.03, 0.006), (0.0, 0.006)], 24, T(dx, yc + 0.0045, dz) @ R(-90, 'X'))
    for (S, n, A0, B0), yr in zip(layout, yrs):
        cylinder(Cr["Steel"], 0.0062, yr + 0.0105 - (yc + 0.0045), 12, T(A0.x, yc + 0.0045, A0.z) @ R(-90, 'X'))
        cylinder(Cr["Steel"], 0.0085, 0.003, 12, T(A0.x, yr + 0.0075, A0.z) @ R(-90, 'X'))
    anchors.append(empty("Door_CrankAxis", K.coll, anchor_frame(V((dx, yc, dz)), up)))
    # 手轮：两面各一个，同一根轴
    door_wheel(W, T(dx, y + 0.168, dz) @ R(-90, 'X'), 0.13)   # 抬高一点，辐条从上层连杆的销子头上面转过去
    door_wheel(W, T(dx, yb - 0.045, dz) @ R(90, 'X'), 0.11)
    cylinder(W["Steel"], 0.012, 0.03, 16, T(dx, y + 0.138, dz) @ R(-90, 'X'))
    cylinder(W["Steel"], 0.012, 0.03, 16, T(dx, yb - 0.048, dz) @ R(-90, 'X'))
    anchors.append(empty("Door_WheelAxis", K.coll, anchor_frame(V((dx, y + 0.12, dz)), up)))

    # 门扇两面刷的字（避开连杆）
    for yy, n, x2, z2, x1, z1 in ((yf + 0.0002, up, dx + 0.13, dz + 0.42, dx - 0.09, dz - 0.45),
                                  (yb - 0.0002, -up, dx, dz + 0.45, dx, dz - 0.19)):
        text_mesh("随手关门", D.uid("Door_Leaf_Txt"), K.coll, K.M["InkRed"], frame(V((x1, yy, z1)), n),
                  size=0.04, extrude=0.0, font_path=FONT_SERIF, resolution=2)
        text_mesh("2", D.uid("Door_Leaf_Txt"), K.coll, K.M["PaintText"], frame(V((x2, yy, z2)), n),
                  size=0.12, extrude=0.0, font_path=FONT_SERIF, resolution=2)
    # 控制舱一面：左上角一块黄铜检验铭牌（四颗铆钉）
    Pb = frame(V((dx - 0.19, yf + 0.0002, dz + 0.18)), up)
    rbox(D["Brass"], 0.105, 0.062, 0.0015, Pb @ T(0, 0, 0.00075), r=0.001, seg=1)
    for sx in (-1, 1):
        for sy in (-1, 1):
            lathe(D["Brass"], [(0.0022, 0.0), (0.0018, 0.0012), (0.0, 0.0016)], 10,
                  Pb @ T(sx * 0.045, sy * 0.024, 0.0015))
    text_mesh("水密门  2 号\n试验压力 0.6 MPa\n1987 年 6 月  合格", D.uid("Door_Leaf_Txt"), K.coll, K.M["Ink"],
              Pb @ T(0, 0, 0.0017), size=0.03, extrude=0.0, font_path=FONT_SERIF, resolution=1)
    # 右下包边上焊的一个吊环，拴着一张检修牌：铁丝圈、一截细绳、马粪纸卡片，手写字
    q, n = door_ring(-58, 0.061)
    eye = q + V((0, y + 0.122, 0))
    torus(D["Steel"], 0.009, 0.0022, 16, 6, frame(eye + V((0, 0.006, 0)), V((n.x, 0, n.z))) @ R(90, 'X'))
    hook = eye + V((0, 0.009, -0.006))
    torus(D["Steel"], 0.014, 0.0011, 16, 4, frame(hook + V((0, 0, -0.012)), V((1, 0, 0))))
    knot = hook + V((0.0, 0.006, -0.05))
    tag_top = hook + V((-0.006, 0.01, -0.09))
    sweep(D["Cardboard"], catmull([hook + V((0, 0, -0.026)), knot, tag_top], 4), circle_profile(0.0008, 4))
    Mt = frame(tag_top + V((0, 0.001, -0.05)), V((-0.1, 1, 0.05)).normalized()) @ R(6, 'Z')
    rbox(D["MaskTape"], 0.064, 0.1, 0.0008, Mt, r=0.0, seg=1)
    torus(D["Steel"], 0.0035, 0.0009, 12, 4, Mt @ T(0, 0.041, 0.0004))
    text_mesh("检修\n密封圈渗水\n待换\n—林", D.uid("Door_Leaf_Txt"), K.coll, K.M["Marker"],
              Mt @ T(0, -0.006, 0.0006), size=0.064, extrude=0.0, font_path=FONT_HAND, resolution=1)
    D.flush()
    W.flush()
    Cr.flush()


def door_wheel(K, M, r):
    """门上的手轮：碟形（三根辐条从轮毂往外翘）、轮缘上一个转柄。M 的 Z 朝外，原点在轮毂底面。"""
    lathe(K["Steel"], [(0.0, 0.0), (0.028, 0.0), (0.028, 0.03), (0.022, 0.036), (0.0, 0.036)], 24, M)
    cylinder(K["Steel"], 0.012, 0.006, 6, M @ T(0, 0, 0.036))
    zr = 0.044
    torus(K["BtnRed"], r, r * 0.11, 64, 12, M @ T(0, 0, zr))
    for i in range(3):
        a = 2 * math.pi * i / 3 + math.pi / 2
        c, s_ = math.cos(a), math.sin(a)
        pts = [M @ V((c * 0.02, s_ * 0.02, 0.018)), M @ V((c * r * 0.5, s_ * r * 0.5, zr - 0.006)),
               M @ V((c * r, s_ * r, zr))]
        sweep(K["BtnRed"], catmull(pts, 5), [(x * 1.3, y_) for x, y_ in circle_profile(r * 0.065, 10)])
    Mk = M @ T(r * math.cos(math.radians(-35)), r * math.sin(math.radians(-35)), zr)
    cylinder(K["Steel"], 0.0055, 0.024, 10, Mk)
    lathe(K["Knob"], [(0.0, 0.016), (0.011, 0.018), (0.0125, 0.05), (0.009, 0.06), (0.0, 0.062)], 16, Mk)


def junction_box(K, P, w=0.2, h=0.16, d=0.1):
    """接线盒：三根线从盒顶的接插件出来（往上并进桥架，见 overhead 里的 JBOX_LEADS）。"""
    unit(K, P @ T(0, 0, d), w, h, d, body="EquipGray", face="EquipGray", handles=False)
    F = P @ T(0, 0, d)
    label_plate(K, F, 0, 0.055, "接线盒", 0.0075)
    tri = [(math.cos(math.radians(90 + 120 * k)) * 0.03, math.sin(math.radians(90 + 120 * k)) * 0.03 - 0.005)
           for k in range(3)]
    extrude_profile(K["Ink"], tri, F, 0.0004)
    extrude_profile(K["BtnYellow"], [(x * 0.8, y * 0.8 - 0.0008) for x, y in tri], F, 0.0007)
    K.text("当心触电", F @ T(0, -0.045, 0.0003), 0.009, key="Ink")
    Pt = F @ T(0, h / 2, -d / 2) @ R(-90, 'X')
    JBOX_LEADS.clear()
    for k in range(3):
        x = -w / 2 + w * (k + 0.5) / 3
        start, nz, _ = connector(K, Pt, x, 0.0, r=0.008, plug="Olive" if k % 2 else "Steel")
        JBOX_LEADS.append((start, nz, ["CableBlack", "CableGray", "CableOrange"][k]))


JBOX_LEADS = []   # 接线盒出线：(出口点, 方向, 颜色)，overhead 里把它们并进左舷桥架


def o2_line(K):
    """氧气减压阀出来的紫铜管：沿隔壁爬到舱顶，从肋骨翼板底下穿过，往前接到右舷生命支持柜的灯罩顶上。
    每道肋骨处一个小吊卡，隔壁上两个管卡。"""
    y = Y_AFT
    xr, zr = 0.87, 0.78          # 沿舱顶走的那一段
    ye = (BAYS[1][0] + BAYS[1][1]) / 2 + 0.05
    pts = [V((0.787, y + 0.1, DECK + 0.82)), V((0.83, y + 0.075, DECK + 0.83)), V((0.98, y + 0.04, DECK + 0.87)),
           V((1.06, y + 0.035, DECK + 1.0)), V((1.06, y + 0.035, 0.45)), V((1.04, y + 0.06, 0.66)),
           V((0.92, y + 0.14, 0.77)), V((xr, y + 0.32, zr)), V((xr, y + 0.6, zr)), V((xr, ye - 0.3, zr)),
           V((xr, ye - 0.12, zr)), V((xr + 0.035, ye - 0.04, zr - 0.02)), V((0.93, ye, HOOD_Z[1] + 0.03)),
           V((0.93, ye, HOOD_Z[1] - 0.01))]
    sweep(K["Copper"], catmull(pts, 8), circle_profile(0.006, 10))
    # 灯罩顶上的穿板接头
    cylinder(K["Brass"], 0.013, 0.012, 6, T(0.93, ye, HOOD_Z[1]))
    cylinder(K["Brass"], 0.01, 0.008, 16, T(0.93, ye, HOOD_Z[1] + 0.012))
    # 隔壁上的管卡
    for z in (0.0, 0.3):
        P = frame(V((1.06, y, z)), V((0, 1, 0)))
        arc = [P @ V((math.cos(math.radians(a)) * 0.0085, 0, 0.035 + math.sin(math.radians(a)) * 0.0085))
               for a in range(0, 181, 15)]
        arc = [P @ V((0.0085, 0, 0.0))] + arc + [P @ V((-0.0085, 0, 0.0))]
        sweep(K["Steel"], arc, [(-0.0008, -0.006), (0.0008, -0.006), (0.0008, 0.006), (-0.0008, 0.006)],
              up_hint=V((0, 0, 1)))
        for sx in (-1, 1):
            rbox(K["Steel"], 0.012, 0.012, 0.0016, P @ T(sx * 0.016, 0, 0.0008), r=0.0, seg=1)
            cylinder(K["Steel"], 0.0035, 0.002, 6, P @ T(sx * 0.016, 0, 0.0016))
    # 肋骨翼板上的吊卡：一截扁钢从翼板往下，末端一个抱箍
    for yf in FRAMES:
        if not (y + 0.25 < yf < ye - 0.2):
            continue
        top = math.sqrt(1.19 ** 2 - xr ** 2)
        rbox(K["Steel"], 0.004, 0.02, top - zr - 0.004, T(xr + 0.0105, yf + 0.03, (top + zr) / 2), r=0.0, seg=1)
        torus(K["Steel"], 0.0085, 0.0018, 16, 4, T(xr, yf + 0.03, zr) @ R(90, 'X'))


# ============================================================================ 头顶：管路、桥架、灯
PIPES = [  # x, z, 半径, 材质（中间留出 50 厘米给直梯和舱口）
    (-0.3, 1.02, 0.06, "Lagging"),      # 通风管（外包帆布保温层）
    (-0.43, 0.97, 0.026, "PipeBlue"),   # 冷却水
    (-0.51, 0.91, 0.026, "PipeRed"),    # 消防水
    (0.3, 1.06, 0.026, "PipeBlue"),     # 冷却水回水
    (0.38, 1.02, 0.016, "Copper"),      # 高压空气
]
PIPE_FLANGES = (-1.4, -0.2, 0.95)   # 控制舱里管子中间的对接法兰
SLEEVE = 0.084                      # 穿隔壁套管两头的法兰接合面离隔壁表面
PIPE_BOW = (None, 1.4, 1.52, 1.4, 1.52)   # 每根管子在这个 y 往上弯、穿出耐压壳（通风管除外）；相邻两根前后错开，
                                          # 不然穿壳件的法兰、补强垫板会挤到一起

TRAY_ANG = 38.0     # 电缆桥架在舱顶两侧的位置（离正上方的角度）
TRAY_RUNG = 1.111   # 横档上表面离轴线（电缆就铺在横档上）
TRAY_HW = 0.08      # 两根边梁离桥架中线
TRAY_END = 1.3      # 控制舱这头桥架到这里为止，再往前电缆垂进驾驶台两边的高机柜
TRAY_RUNGS = {-1: [], 1: []}    # 横档的 y（扎带捆在横档上），tray() 里记下来
TRAY_Y0 = Y_STERN - 0.004       # 电缆从后隔壁穿舱框里出来的地方（扁平线束的弧长从这里算起）
MCT_MID = (Y_AFT - 0.012 - 0.065, Y_AFT + 0.065)   # 中间隔壁上电缆穿舱框的前后两端
MCT_STERN = (Y_STERN - 0.01, Y_STERN + 0.065)
PENETRATORS = ((-1, 0.4), (1, -1.4), (1, -0.2))      # 壳体上的电缆穿舱件 (舷, y)：在桥架外侧，线翻过边梁铺进桥架
PEN_ANG = 52.0
TRAY_CABLES = [(0.009, "CableBlack"), (0.007, "CableGray"), (0.008, "CableBlack"), (0.005, "CableOrange"),
               (0.006, "CableBlack"), (0.005, "CableYellow"), (0.007, "CableGray"), (0.0045, "CableBlue"),
               (0.006, "CableBlack")]


def flange_pair(K, key, M, r, bolts=6):
    """一对对接法兰：两片背靠背夹一层垫片，一圈螺栓（两头六角螺母）。M 的 Z 是管子轴线，原点在接合面上。"""
    rf = r + (0.022 if r > 0.02 else 0.018)
    for z0 in (-0.0145, 0.0005):
        cylinder(K[key], rf, 0.014, 32, M @ T(0, 0, z0))
    cylinder(K["Rubber"], rf - 0.003, 0.001, 32, M @ T(0, 0, -0.0005))
    rb = (r + rf) / 2 + 0.002
    for i in range(bolts):
        a = 2 * math.pi * (i + 0.5) / bolts
        Mb = M @ T(math.cos(a) * rb, math.sin(a) * rb, 0) @ R(math.degrees(a), 'Z')
        cylinder(K["Steel"], 0.0026, 0.046, 8, Mb @ T(0, 0, -0.023))
        for z0 in (-0.0205, 0.0145):
            cylinder(K["Steel"], 0.0052, 0.006, 6, Mb @ T(0, 0, z0))


def pipe_sleeve(K, x, z, r, key, y_front=None, y_back=None):
    """管子穿隔壁：一截厚壁套管穿过隔壁板，和隔壁焊一圈，伸出来的头上带法兰，和两边的管子对接。
    y_front：隔壁朝 +Y（朝艏）的那一面；y_back：朝 -Y 的那一面；只给一个就只做那一面（另一面看不见）。"""
    fkey = "PipeGray" if key == "Lagging" else key
    rs = r + 0.006
    ya = y_back - SLEEVE if y_back is not None else y_front - 0.04
    yb = y_front + SLEEVE if y_front is not None else y_back + 0.04
    cylinder(K[fkey], rs, yb - ya, 24, T(x, ya, z) @ R(-90, 'X'))
    for yy, sg in ((y_front, 1), (y_back, -1)):
        if yy is None:
            continue
        flange_pair(K, fkey, T(x, yy + sg * SLEEVE, z) @ R(-90, 'X'), r)
        lathe(K["HullInner"], [(rs, 0.0), (rs + 0.009, 0.0), (rs, 0.009), (rs, 0.0)], 24,
              T(x, yy, z) @ R(-90 * sg, 'X'))


def pipe_hanger(K, x, z, r, yh, flat_top=None):
    """管子吊架：扁钢抱箍托住管子，两根螺杆吊到上面肋骨的翼板上（翼板是斜的，顶板贴着它斜放）。
    flat_top：舱口附近肋骨断开了，改吊到舱口围板的平底面上（给出底面高度）。"""
    ring_r = r + 0.006
    arc = [V((x + math.cos(math.radians(a)) * ring_r, yh, z + math.sin(math.radians(a)) * ring_r))
           for a in range(-180, 1, 15)]
    sweep(K["Steel"], arc, [(-0.002, -0.012), (0.002, -0.012), (0.002, 0.012), (-0.002, 0.012)],
          up_hint=V((0, 1, 0)))
    if flat_top is None:
        a = math.asin(x / 1.19)
        n, tg = V((math.sin(a), 0, math.cos(a))), V((math.cos(a), 0, -math.sin(a)))
        pc = V((n.x * 1.19, yh, n.z * 1.19))
    else:
        n, tg, pc = V((0, 0, 1)), V((1, 0, 0)), V((x, yh, flat_top))
    for sx in (-1, 1):
        xr = x + sx * ring_r
        top = pc.z - 0.006 * n.z - n.x * (xr - pc.x + 0.006 * n.x) / n.z   # 顶板下表面
        cylinder(K["Steel"], 0.005, top - z, 8, T(xr, yh, z))
        cylinder(K["Steel"], 0.0075, 0.007, 6, T(xr, yh, top - 0.007))
    c = pc - n * 0.003
    M = Matrix(((tg.x, 0, n.x, c.x), (tg.y, 1, n.y, c.y), (tg.z, 0, n.z, c.z), (0, 0, 0, 1)))
    rbox(K["Steel"], 2 * ring_r + 0.03, 0.03, 0.006, M, r=0.001, seg=1)


def hull_fitting(K, key, x, y, r, zf):
    """竖管穿出耐压壳：壳上焊一个厚壁接管座，根部一块补强垫板；下端法兰和管子对接（zf 是接合面高度）。"""
    zh = math.sqrt(R_IN ** 2 - x * x)
    flange_pair(K, key, T(x, y, zf), r)
    cylinder(K[key], r + 0.008, zh + 0.02 - zf, 24, T(x, y, zf))
    n = V((x, 0, zh)) / R_IN
    cylinder(K["HullInner"], r + 0.045, 0.02, 32, frame(V((x, y, zh)) - n * 0.012, n))
    lathe(K["HullInner"], [(r + 0.008, 0.0), (r + 0.016, 0.0), (r + 0.008, 0.008), (r + 0.008, 0.0)], 24,
          T(x, y, zh - 0.012 - 0.04 * abs(x)))


def tray_frame(s):
    """s 舷桥架的局部坐标系：X 沿横档（+X 在右舷朝外下方、在左舷朝里上方），Y 沿艇长，Z 是半径方向（朝壳体）。"""
    a = math.radians(TRAY_ANG * s)
    w = V((math.cos(a), 0, -math.sin(a)))
    n = V((math.sin(a), 0, math.cos(a)))
    return Matrix(((w.x, 0, n.x, 0), (w.y, 1, n.y, 0), (w.z, 0, n.z, 0), (0, 0, 0, 1)))


def tray(K, s, y0, y1, frame_ys):
    """梯式电缆桥架：两根边梁、每 25 厘米一根横档；每道肋骨处一个 U 形托架兜着，两条腿用螺栓吊在肋骨翼板上。"""
    L = tray_frame(s)
    for u in (-TRAY_HW, TRAY_HW):
        rbox(K["Rail"], 0.006, y1 - y0, 0.055, L @ T(u, (y0 + y1) / 2, 1.1275), r=0.0015, seg=1)
    yy = y0 + 0.1
    while yy < y1 - 0.05:
        rbox(K["Rail"], 2 * TRAY_HW - 0.006, 0.02, 0.006, L @ T(0, yy, TRAY_RUNG - 0.003), r=0.001, seg=1)
        TRAY_RUNGS[s].append(yy)
        yy += 0.25
    for yf in frame_ys:
        yc = yf + 0.03
        if y1 - 0.03 < yc < y1 + 0.05:
            yc = y1 - 0.015    # 肋骨正好在桥架头上：托架往回挪一点，兜住桥架的头
        if not (y0 + 0.03 < yc < y1):
            continue
        for u in (-1, 1):
            uu = u * (TRAY_HW + 0.006)
            rbox(K["Steel"], 0.006, 0.03, 0.097, L @ T(uu, yc, 1.1415), r=0.001, seg=1)
            rbox(K["Steel"], 0.04, 0.05, 0.005, L @ T(uu, yc, 1.1875), r=0.001, seg=1)
            cylinder(K["Steel"], 0.007, 0.006, 6, L @ T(uu + u * 0.011, yc, 1.185) @ R(180, 'X'))
        rbox(K["Steel"], 2 * (TRAY_HW + 0.009), 0.03, 0.006, L @ T(0, yc, 1.096), r=0.001, seg=1)


def cable_transit(K, s, y0, y1):
    """桥架穿隔壁处的多电缆穿舱框（MCT）：焊在隔壁上的方钢框，里面塞满一格一格的橡胶密封块，
    电缆从块中间穿过；最上面一条压紧板，两根顶紧螺栓。y0..y1 是框的前后两端。"""
    L = tray_frame(s)
    u0, r0, r1, t = 0.1, 1.055, 1.18, 0.012
    ym, ln = (y0 + y1) / 2, y1 - y0
    for rr in (r0 + t / 2, r1 - t / 2):
        rbox(K["HullInner"], 2 * u0, ln, t, L @ T(0, ym, rr), r=0.002, seg=1)
    for u in (-1, 1):
        rbox(K["HullInner"], t, ln, r1 - r0, L @ T(u * (u0 - t / 2), ym, (r0 + r1) / 2), r=0.002, seg=1)
    ri0, ri1 = r0 + t, r1 - t - 0.016
    rbox(K["Rubber"], 2 * (u0 - t), ln - 0.016, ri1 - ri0, L @ T(0, ym, (ri0 + ri1) / 2), r=0.0, seg=1)
    rbox(K["Steel"], 2 * (u0 - t), ln - 0.01, 0.014, L @ T(0, ym, ri1 + 0.008), r=0.001, seg=1)
    for yy, sg in ((y0 + 0.0076, -1), (y1 - 0.0076, 1)):
        for u in (-0.06, -0.02, 0.02, 0.06):   # 密封块之间的格缝
            box(K["Dark"], 0.0015, 0.001, ri1 - ri0, L @ T(u, yy, (ri0 + ri1) / 2))
        for rr in (ri0 + (ri1 - ri0) / 3, ri0 + 2 * (ri1 - ri0) / 3):
            box(K["Dark"], 2 * (u0 - t), 0.001, 0.0015, L @ T(0, yy, rr))
        for u in (-0.05, 0.05):
            cylinder(K["Steel"], 0.0065, 0.012, 6, L @ T(u, yy - sg * 0.002, ri1 + 0.008) @ R(-90 * sg, 'X'))


def penetrator(K, s, y):
    """壳体上的电缆穿舱件：法兰盘压在壳上，一圈螺栓，五个航空插头朝舱里。返回 [(出口点, 方向)]。"""
    a = math.radians(PEN_ANG * s)
    d = V((math.sin(a), 0, math.cos(a)))
    F = frame(V((d.x * (R_IN - 0.004), y, d.z * (R_IN - 0.004))), -d)
    cylinder(K["EquipGray"], 0.1, 0.02, 48, F)
    for i in range(10):
        b = 2 * math.pi * i / 10
        cylinder(K["Steel"], 0.008, 0.009, 6, F @ T(math.cos(b) * 0.085, math.sin(b) * 0.085, 0.02))
    P = F @ T(0, 0, 0.02)
    out = []
    for k in range(5):
        ang = 2 * math.pi * k / 5
        start, nz, _ = connector(K, P, math.cos(ang) * 0.045, math.sin(ang) * 0.045, r=0.009,
                                 plug="Olive" if k % 2 else "Steel")
        out.append((start, nz))
    return out


def join_leads(s, y_j, outs, via=()):
    """中途并进桥架的一组线：从出口点出来，经过 via（出口点 → 途经点的函数），在 y_j 处翻过桥架外侧的边梁，
    铺到上面一层。返回 (y_j, [(r, 颜色, 并进处弧长, 走线点), ...])。"""
    over = tray_frame(s) @ V((s * (TRAY_HW + 0.025), y_j + 0.04, 1.2))
    return (y_j, [(0.0055, key, y_j + 0.16 - TRAY_Y0, [start, start + nz * 0.035] + [f(start, nz) for f in via] + [over])
                  for start, nz, key in outs])


def tray_cables(K, s, joins):
    """一舷的电缆：从后隔壁的穿舱框出来，沿桥架一路往前，穿过中间隔壁，到控制舱前头整排垂进高机柜顶上的过线板。
    joins：join_leads() 的结果，铺在上面一层（后并进来的放在靠外那一侧，不用从先铺好的线上面翻过去）。"""
    L = tray_frame(s)
    y_start = TRAY_Y0

    def on(y, dr=0.0):
        return L @ V((0, y, TRAY_RUNG + dr))
    xg = s * 0.93
    # 在桥架里一直是直的，过了边梁的头才往外、往下拐
    path = ([on(y_start)] + [on(yy) for yy in [Y_STERN + 0.3 + 0.3 * k for k in range(30)] if yy < TRAY_END - 0.2]
            + [on(TRAY_END - 0.1), on(TRAY_END + 0.02), V((s * 0.79, 1.4, 0.835)), V((s * 0.89, 1.445, 0.77)),
               V((xg, 1.455, 0.7)), V((xg, 1.455, HOOD_Z[1] - 0.025))])
    top = []
    for y_j, group in sorted(joins, key=lambda j: j[0]):
        top = (top + group) if s > 0 else (group + top)
    layers = [TRAY_CABLES] + ([top] if top else [])
    cradles = [yf + 0.03 for yf in FRAMES + AFT_FRAMES]
    ties = [yy - y_start for i, yy in enumerate(TRAY_RUNGS[s])
            if i % 2 == 0 and all(abs(yy - c) > 0.08 for c in cradles)]
    rib = Cab.ribbon(path, L.to_3x3() @ V((0, 0, 1)), layers, ties=ties)
    # 机柜顶上的过线板：钢板压一块开了槽的橡胶垫，四颗螺钉
    for i, p in enumerate(rib["center"]):
        if p.z < HOOD_Z[1] + 0.002:
            break
    t, n, w = rib["frames"][i]
    c = p + n * rib["height"] / 2
    c.z = HOOD_Z[1]
    M = Matrix(((w.x, n.x, -t.x, c.x), (w.y, n.y, -t.y, c.y), (w.z, n.z, -t.z, c.z), (0, 0, 0, 1)))
    W, H = rib["width"], rib["height"]
    rbox(K["Steel"], W + 0.05, H + 0.05, 0.006, M @ T(0, 0, 0.003), r=0.002, seg=1)
    rbox(K["Rubber"], W + 0.014, H + 0.014, 0.01, M @ T(0, 0, 0.005), r=0.002, seg=1)
    for sx in (-1, 1):
        for sy in (-1, 1):
            cylinder(K["Steel"], 0.004, 0.002, 12, M @ T(sx * (W / 2 + 0.017), sy * (H / 2 + 0.017), 0.006))


def overhead(K, anchors):
    """控制舱头顶：管子从中间隔壁的套管出来往前走，到驾驶台上方往上弯、穿出耐压壳（通风管是往下弯，接个风口）；
    两舷的电缆桥架、穿舱件、顶灯。管子和桥架在生活舱那段见 quarters.overhead。"""
    y0 = Y_AFT + SLEEVE
    for i, (x, z, r, key) in enumerate(PIPES):
        bm = K[key]
        fkey = "PipeGray" if key == "Lagging" else key
        segs = 24 if r > 0.03 else 16
        pipe_sleeve(K, x, z, r, key, y_front=Y_AFT, y_back=Y_AFT - 0.012)
        y_end = 1.36
        if key == "Lagging":
            # 通风管：在驾驶台上方往下弯，一段短竖管，渐缩口接一个能转方向的球形风口，对着驾驶员的头顶
            yb, Rb = 1.36, 0.1
            bend = [V((x, yb + Rb * math.sin(math.radians(a)), z - Rb * (1 - math.cos(math.radians(a)))))
                    for a in range(0, 91, 10)]
            ze = z - Rb - 0.05
            sweep(bm, [V((x, y0, z))] + bend + [V((x, yb + Rb, ze))], circle_profile(r, segs))
            M = T(x, yb + Rb, ze)
            lathe(K["PipeGray"], [(0.0, 0.012), (r + 0.004, 0.012), (r + 0.004, -0.004), (r - 0.004, -0.012),
                                  (0.047, -0.04), (0.047, -0.05), (0.0, -0.05)], 32, M)
            torus(K["PipeGray"], 0.044, 0.006, 32, 8, M @ T(0, 0, -0.052))
            eye = EYE_SEATED + V((0, 0, 0.25))
            Ms = M @ T(0, 0, -0.058)
            look = (eye - Ms.translation).normalized()
            uvsphere(K["EquipGray"], 0.039, 24, 12, Ms)
            Mn = frame(Ms.translation, look)
            cylinder(K["EquipGray"], 0.02, 0.03, 20, Mn @ T(0, 0, 0.025))
            cylinder(K["Dark"], 0.016, 0.001, 16, Mn @ T(0, 0, 0.0551))
            for k in range(4):   # 喷口里的导流叶片
                box(K["EquipGray"], 0.032, 0.0015, 0.012, Mn @ T(0, -0.012 + k * 0.008, 0.049))
            for yb2 in [Y_AFT + 0.25 + k * 0.4 for k in range(10)]:
                if yb2 < 1.3 and all(abs(yb2 - yf) > 0.08 for yf in PIPE_FLANGES):
                    cylinder(K["Steel"], r + 0.002, 0.016, 32, T(x, yb2, z) @ R(-90, 'X'), caps=False)
        else:
            Rb = 0.1 if r < 0.02 else 0.12
            yb = PIPE_BOW[i]
            y_end = yb - Rb
            zf = math.sqrt(R_IN ** 2 - x * x) - 0.085
            bend = [V((x, yb - Rb + Rb * math.sin(math.radians(a)), z + Rb * (1 - math.cos(math.radians(a)))))
                    for a in range(0, 91, 10)]
            sweep(bm, [V((x, y0, z))] + bend + [V((x, yb, zf))], circle_profile(r, segs))
            hull_fitting(K, fkey, x, yb, r, zf)
        for yf in PIPE_FLANGES:
            flange_pair(K, fkey, T(x, yf, z) @ R(-90, 'X'), r)
        for yf in FRAMES:
            if yf + 0.035 < y_end - 0.02:
                pipe_hanger(K, x, z, r, yf + 0.035)
    # 通风口
    for yv in PIPE_FLANGES:
        x, z, r, _ = PIPES[0]
        rbox(K["PipeGray"], 0.14, 0.12, 0.06, T(x, yv + 0.25, z - r - 0.01), r=0.008, seg=2)
        P = T(x, yv + 0.25, z - r - 0.041) @ R(180, 'X')
        vent(K, P, 0, 0, 0.11, 0.09, 8, 0.006)
    # 冷却水管上的截止阀
    x, z, r, _ = PIPES[1]
    lathe(K["Brass"], [(0.0, -0.06), (0.04, -0.05), (0.045, 0.0), (0.04, 0.05), (0.0, 0.06)], 24,
          T(x, 0.4, z) @ R(-90, 'X'))
    cylinder(K["Brass"], 0.012, 0.12, 12, T(x, 0.4, z) @ R(180, 'X'))
    valve_wheel(K, T(x, 0.4, z - 0.1) @ R(180, 'X'), 0.07, "BtnRed", 4)
    tape_label(K, frame(V((x, 0.33, z - r - 0.003)), V((0, 0, -1)), V((0, 1, 0))), 0, 0, "常开", 0.012, 0)
    # 冷却水管的法兰漏水：底下挂着一颗水珠，隔一会儿滴一滴（Godot 里在 Anchor_Drip 处放粒子）
    drip = V((x, -0.2, z - r - 0.0235))
    uvsphere(K["Bilge"], 0.0042, 12, 8, T(*drip) @ S(1, 1, 1.25))
    anchors.append(empty("Anchor_Drip", K.coll, T(*(drip - V((0, 0, 0.004))))))

    # 电缆桥架：中间隔壁两面是穿舱框，往前到驾驶台两边的高机柜上方为止
    for s in (-1, 1):
        cable_transit(K, s, *MCT_MID)
        tray(K, s, MCT_MID[1], TRAY_END, FRAMES)
    # 壳体上的穿舱件：线从外侧翻过边梁铺进桥架
    joins = {-1: [], 1: []}
    keys = ["CableBlack", "CableGray", "CableOrange", "CableBlack", "CableBlue"]
    for s, y in PENETRATORS:
        outs = [(p, nz, keys[k]) for k, (p, nz) in enumerate(penetrator(K, s, y))]
        a = math.radians(PEN_ANG * s)
        tu = V((-math.cos(a) * s, 0, math.sin(a) * s))   # 沿壳体朝上（朝桥架）
        # 先直着出来，过了插头尾巴再拐弯，不从别的插头上面蹭过去
        joins[s].append(join_leads(s, y, outs, via=(lambda p, nz, tu=tu: p + nz * 0.07 + tu * 0.03,)))
    # 隔壁上接线盒的三根线：顺着隔壁往上爬（两道线卡压住），在门上方从外侧翻进左舷桥架
    if JBOX_LEADS:
        # 在 -2.3 那道肋骨前面翻进桥架（肋骨翼板挡着，不能在它那儿翻）
        joins[-1].append(join_leads(-1, Y_AFT + 0.12, JBOX_LEADS,
                                    via=(lambda p, nz: V((p.x, Y_AFT + 0.035, 0.53)),
                                         lambda p, nz: V((p.x, Y_AFT + 0.035, 0.65)),
                                         lambda p, nz: V((p.x + 0.03, Y_AFT + 0.09, 0.77)))))
        xs = [p.x for p, _, _ in JBOX_LEADS]
        for z in (0.57, 0.63):   # 线卡：一条扁钢压住三根线，两头折下来用螺钉固定在隔壁上
            rbox(K["Steel"], max(xs) - min(xs) + 0.03, 0.004, 0.012,
                 T((max(xs) + min(xs)) / 2, Y_AFT + 0.0435, z), r=0.001, seg=1)
            for xx in (min(xs) - 0.017, max(xs) + 0.017):
                rbox(K["Steel"], 0.004, 0.045, 0.012, T(xx, Y_AFT + 0.0225, z), r=0.001, seg=1)
                rbox(K["Steel"], 0.014, 0.003, 0.012, T(xx + (0.007 if xx > min(xs) else -0.007), Y_AFT + 0.0015, z),
                     r=0.0, seg=1)
    for s in (-1, 1):
        tray_cables(K, s, joins[s])
    # 顶灯
    for i, yl in enumerate((-1.4, -0.2, 1.0)):
        ceiling_lamp(K, anchors, T(0.0, yl, R_IN - 0.01) @ R(180, 'X'), f"CabinLight_Dome_{i}")
    # 驾驶台上方的红色夜灯（装在艏部半球壁上）
    dn = V((-0.55, 0.3, 1.0)).normalized()
    q = V((0, Y_BOW, 0)) + dn * (R_IN - 0.005)
    F = frame(q, -dn)
    cylinder(K["PanelDark"], 0.045, 0.02, 32, F)
    lathe(K["LensRed"], [(0.035, 0.02), (0.035, 0.035), (0.026, 0.05), (0.0, 0.055)], 32, F)
    for k in range(6):
        a = 2 * math.pi * k / 6
        sweep(K["Steel"], catmull([F @ V((math.cos(a) * 0.042, math.sin(a) * 0.042, 0.02)),
                                   F @ V((math.cos(a) * 0.04, math.sin(a) * 0.04, 0.045)),
                                   F @ V((0, 0, 0.062))], 5), circle_profile(0.0015, 6))
    anchors.append(empty("CabinLight_Night", K.coll, F @ T(0, 0, 0.07)))


def ceiling_lamp(K, anchors, M, name):
    """船用防水灯：铸铝灯座、磨砂玻璃罩、四根护笼。M 的 Z 是出光方向，原点在安装面上。"""
    lathe(K["EquipGray"], [(0.0, 0.0), (0.11, 0.0), (0.11, 0.02), (0.095, 0.035), (0.085, 0.05), (0.0, 0.05)],
          48, M)
    for i in range(4):
        a = math.radians(45 + 90 * i)
        socket_screw(K, M @ T(0, 0, 0.02), math.cos(a) * 0.1, math.sin(a) * 0.1, r=0.006)
    lathe(K["LampGlass"], [(0.075, 0.05), (0.075, 0.08), (0.062, 0.115), (0.03, 0.13), (0.0, 0.133)], 32, M)
    for i in range(4):
        a = 2 * math.pi * i / 4
        sweep(K["Steel"], catmull([M @ V((math.cos(a) * 0.084, math.sin(a) * 0.084, 0.05)),
                                   M @ V((math.cos(a) * 0.085, math.sin(a) * 0.085, 0.1)),
                                   M @ V((math.cos(a) * 0.04, math.sin(a) * 0.04, 0.142)),
                                   M @ V((0, 0, 0.145))], 6), circle_profile(0.004, 8))
    torus(K["Steel"], 0.085, 0.004, 32, 6, M @ T(0, 0, 0.09))
    anchors.append(empty(name, K.coll, M @ T(0, 0, 0.09)))


# ============================================================================ 驾驶台
def plate_with_hole(bm, F, w, h, t, hole=None):
    """面板（正面 z=0、厚 t），可以挖一个矩形孔 hole=(x, y, w, h)：拆成孔四周的四块。"""
    if hole is None:
        rbox(bm, w, h, t, F @ T(0, 0, -t / 2), r=0.002, seg=1)
        return
    hx, hy, hw, hh = hole
    x0, x1, y0, y1 = hx - hw / 2, hx + hw / 2, hy - hh / 2, hy + hh / 2
    for a, b, c, d in ((-w / 2, w / 2, y1, h / 2), (-w / 2, w / 2, -h / 2, y0), (-w / 2, x0, y0, y1),
                       (x1, w / 2, y0, y1)):
        if b - a > 1e-4 and d - c > 1e-4:
            rbox(bm, b - a, d - c, t, F @ T((a + b) / 2, (c + d) / 2, -t / 2), r=0.0, seg=1)


def helm_panel(K, F, w, h, depth=0.5, key="Console", face="PanelGray", hole=None):
    """驾驶台上的一块板：后面整块台体，正面一圈很深的厚边框，中间是面板（可以挖孔装显示器）。"""
    rbox(K[key], w + 0.06, h + 0.06, depth, F @ T(0, 0, -0.085 - depth / 2), r=0.015, seg=3)
    plate_with_hole(K[face], F, w, h, 0.012, hole)
    fw = 0.034
    for xx, yy, bw, bh in ((0, h / 2 + fw / 2, w + 2 * fw, fw), (0, -h / 2 - fw / 2, w + 2 * fw, fw),
                           (-w / 2 - fw / 2, 0, fw, h), (w / 2 + fw / 2, 0, fw, h)):
        rbox(K[key], bw, bh, 0.114, F @ T(xx, yy, -0.033), r=0.008, seg=3)
    for sx in (-1, 1):
        for sy in (-1, 1):
            socket_screw(K, F @ T(0, 0, 0.024), sx * (w / 2 + fw / 2), sy * (h / 2 + fw / 2), r=0.0065)
    return F


def helm(K, anchors):
    # ---- 主板（正对驾驶椅，上沿往后仰 15°）
    n_c = V((0, -math.cos(math.radians(15)), math.sin(math.radians(15))))
    u_c = V((0, math.sin(math.radians(15)), math.cos(math.radians(15))))
    Cm = V((0, 2.22, 0.18))
    cx, cy, sw, sh = 0.0, 0.11, 0.22, 0.165
    Fc = helm_panel(K, frame(Cm, n_c, u_c), 0.8, 0.62, hole=(cx, cy, sw, sh))
    label_plate(K, Fc, 0, 0.29, "镇海号  主操纵台", 0.011)
    gauge_round(K, Fc, -0.26, 0.12, 0.09, "Depth", hi=10, label="深度", unit="×1000 m", major=10, red_from=0.75)
    silk(K, Fc, -0.26, -0.005, "数字深度 m", 0.0085)
    seg_display(K, Fc, -0.26, -0.04, 0.15, 0.036, "Depth")
    # 声呐显示器：深凹进去的显像管，外面一圈厚遮光罩
    P = Fc @ T(cx, cy, 0)
    hw = 0.03
    for x, y, bw, bh in ((0, sh / 2 + hw / 2, sw + 2 * hw, hw), (0, -sh / 2 - hw / 2, sw + 2 * hw, hw),
                         (-sw / 2 - hw / 2, 0, hw, sh), (sw / 2 + hw / 2, 0, hw, sh)):
        rbox(K["Bakelite"], bw, bh, 0.05, P @ T(x, y, 0.01), r=0.006, seg=3)
    box(K["Dark"], sw, sh, 0.004, P @ T(0, 0, -0.07))
    for sx in (-1, 1):
        box(K["Dark"], 0.004, sh, 0.07, P @ T(sx * sw / 2, 0, -0.035))
    for sy in (-1, 1):
        box(K["Dark"], sw, 0.004, 0.07, P @ T(0, sy * sh / 2, -0.035))

    def screen(bm):
        nx, ny = 24, 18
        rows = []
        for j in range(ny + 1):
            y = -sh / 2 + sh * j / ny
            row = []
            for i in range(nx + 1):
                x = -sw / 2 + sw * i / nx
                bulge = 0.01 * (1 - (x / (sw * 0.6)) ** 2) * (1 - (y / (sh * 0.62)) ** 2)
                row.append(bm.verts.new(P @ V((x, y, -0.03 + bulge))))
            rows.append(row)
        faces = _grid_faces(bm, rows, closed_u=False)
        uvmap = {}
        for j, row in enumerate(rows):
            for i, v in enumerate(row):
                uvmap[v] = (i / nx, 1.0 - j / ny)
        uv = bm.loops.layers.uv.new("UVMap")
        for f in faces:
            for loop in f.loops:
                loop[uv].uv = uvmap[loop.vert]
    K.separate("Screen_Sonar", "CRT", screen, smooth=True, sharp=None, recalc=False)
    silk(K, Fc, 0.0, 0.245, "声呐  SONAR", 0.0085)
    for x, lb in ((-0.075, "亮度"), (-0.025, "对比"), (0.025, "增益"), (0.075, "量程")):
        knob(K, Fc, x, -0.03, 0.011, 0.013, ticks=7)
        silk(K, Fc, x, -0.0055, lb, 0.0065)
    gauge_round(K, Fc, 0.27, 0.15, 0.06, "Heading", hi=360, label="航向", major=8, sub=3, start=90,
                sweep_deg=360, num_labels=["北", "", "东", "", "南", "", "西", ""])
    gauge_round(K, Fc, 0.27, -0.01, 0.045, "Trim", hi=20, label="纵倾", unit="°", major=4,
                num_labels=["-10", "-5", "0", "5", "10"])
    # 下排：四块方表 + 八个开关和指示灯
    specs = [("Volt", 150, "V", "主电压", 5), ("Amp", 100, "A", "主电流", 5),
             ("ThrL", 3, "×1000 r/min", "左推转速", 3), ("ThrR", 3, "×1000 r/min", "右推转速", 3)]
    for x, (nm, hi, u_, lb, mj) in zip((-0.24, -0.08, 0.08, 0.24), specs):
        meter_rect(K, Fc, x, -0.13, 0.075, nm, hi=hi, unit=u_, label=lb, major=mj)
    labels = ["主推左", "主推右", "垂推", "侧推", "照明一", "照明二", "声呐", "摄像"]
    for i, lb in enumerate(labels):
        x = -0.28 + i * 0.08
        toggle(K, Fc, x, -0.255, up=(i in (0, 1, 2, 4, 6)), s=1.2)
        silk(K, Fc, x, -0.226, lb, 0.0072)
        lamp(K, Fc, x + 0.026, -0.27, 0.0052, LAMP_COLORS[i], name=f"Lamp_{i}")
    tape_label(K, Fc, 0.2, -0.3, "左推偶尔卡 多拨两下", 0.009, -1.5)

    # ---- 左右翼板
    wings = []
    for s in (-1, 1):
        # 翼板和主板在外框处相接，往驾驶椅方向折 45°
        yaw = math.radians(45)
        xdir = V((s * math.cos(yaw), -math.sin(yaw), 0))
        edge = V((s * (0.4 + 0.034), 2.22, 0.18))
        cen = edge + xdir * (0.23 + 0.034)
        n = (V((-s * math.sin(yaw), -math.cos(yaw), 0)) * math.cos(math.radians(15))
             + V((0, 0, math.sin(math.radians(15)))))
        Fw = helm_panel(K, frame(cen, n.normalized(), V((0, 0, 1))), 0.46, 0.62,
                        hole=(0, -0.19, 0.36, 0.14) if s < 0 else None)
        wings.append(Fw)
    Fl, Fr = wings
    # 左翼：压载、配平、应急抛载
    label_plate(K, Fl, 0, 0.29, "压载 / 配平", 0.0095)
    gauge_round(K, Fl, -0.1, 0.15, 0.06, "Ballast", hi=100, label="压载水舱", unit="%", major=5, red_from=0.85)
    gauge_round(K, Fl, 0.11, 0.15, 0.06, "Ballast2", hi=100, label="可调压载", unit="%", major=5)
    for x, cap, lb in ((-0.15, "BtnGreen", "注水"), (-0.09, "BtnRed", "排水"), (-0.03, "BtnBlack", "停泵")):
        button(K, Fl, x, 0.0, 0.011, cap)
        silk(K, Fl, x, 0.03, lb, 0.0075)
    pointer_knob(K, Fl, 0.11, -0.01, 0.016, angle=40)
    for a_, lb in ((50, "前"), (0, "中"), (-50, "后")):
        silk(K, Fl, 0.11 + math.cos(math.radians(90 + a_)) * 0.036, -0.01 + math.sin(math.radians(90 + a_)) * 0.036,
             lb, 0.0075)
    silk(K, Fl, 0.11, -0.065, "配平泵", 0.0075)
    P = sub_panel(K, Fl, 0, -0.19, 0.36, 0.14, "PanelDark")
    flip_cover(K, P, -0.09, 0.0)
    flip_cover(K, P, 0.0, 0.0)
    label_plate(K, P, 0.1, 0.0, "应急抛载", 0.011, plate="LabelRed")
    silk(K, P, -0.09, -0.05, "左压铁", 0.0068)
    silk(K, P, 0.0, -0.05, "右压铁", 0.0068)
    # 右翼：离底高度、外部照明、舱内照明调光
    label_plate(K, Fr, 0, 0.29, "高度计 / 照明", 0.0095)
    silk(K, Fr, 0, 0.215, "离底高度 m", 0.0085)
    seg_display(K, Fr, 0, 0.17, 0.15, 0.04, "Alt")
    silk(K, Fr, 0, 0.1, "潜航时间", 0.0085)
    seg_display(K, Fr, 0, 0.06, 0.15, 0.036, "Clock")
    for k, (lb, ang) in enumerate((("左探照", -40), ("右探照", -40), ("顶灯", 30), ("仪表", 60))):
        x = -0.15 + k * 0.1
        pointer_knob(K, Fr, x, -0.07, 0.014, angle=ang)
        silk(K, Fr, x, -0.035, lb, 0.0072)
    for k in range(5):
        fuse(K, Fr, -0.16 + k * 0.08, -0.2, ("5A", "5A", "2A", "1A", "10A")[k])
    sticky_note(K, Fr, 0.14, 0.17, ["下潜前", "检查 3号舱", "密封圈"], 0.0085, angle=-5)

    # ---- 顶板（报警灯牌 + 消音按钮）
    n_o = V((0, -0.6, -0.8))
    u_o = V((0, -0.8, 0.6))
    Fo = helm_panel(K, frame(V((0, 2.06, 0.74)), n_o, u_o), 0.66, 0.24, depth=0.35)
    annunciator(K, Fo, -0.07, 0.0, ["氧气低", "二氧化碳", "舱内漏水", "电池低", "绝缘故障", "超深", "液压低", "通信中断"],
                cols=4, tw=0.105, th=0.07)
    button(K, Fo, 0.27, 0.03, 0.012, "BtnYellow")
    silk(K, Fo, 0.27, -0.01, "消音", 0.008)
    vent(K, Fo, 0.27, -0.07, 0.07, 0.05, 6, 0.004)

    # 主板和顶板之间、台体顶上的盖板
    abox(K["Console"], -0.46, 0.46, 2.26, 2.8, 0.47, 0.7, r=0.012, seg=2)
    # ---- 下面的操纵桌和踢脚板
    abox(K["Console"], -0.78, 0.78, 1.8, 2.24, DESK_Z - 0.09, DESK_Z - 0.04, r=0.014, seg=3)
    abox(K["DeskTop"], -0.76, 0.76, 1.818, 2.2, DESK_Z - 0.045, DESK_Z - 0.039, r=0.002, seg=1)
    abox(K["Console"], -0.74, 0.74, 1.92, 2.7, DECK, DESK_Z - 0.09, r=0.01, seg=2)
    P = frame(V((0, 1.92, -0.5)), V((0, -1, 0)))
    vent(K, P, 0, 0.1, 0.5, 0.16, 14, 0.006)
    for sx in (-1, 1):
        for sy in (-1, 1):
            socket_screw(K, P, sx * 0.66, sy * 0.3, r=0.007)
    label_plate(K, P, 0, -0.15, "电池监控单元 内有高压", 0.012, plate="LabelRed")
    # 操纵杆（右手：推进/转向）、升降手柄（左手）
    top = DESK_Z - 0.039
    Pj = T(0.3, 1.98, top)
    rbox(K["PanelDark"], 0.14, 0.14, 0.03, Pj @ T(0, 0, 0.015), r=0.01, seg=3)
    for sx in (-1, 1):
        for sy in (-1, 1):
            socket_screw(K, Pj @ T(0, 0, 0.03), sx * 0.055, sy * 0.055, r=0.005)
    lathe(K["Rubber"], [(0.045, 0.03), (0.04, 0.045), (0.032, 0.05), (0.035, 0.058), (0.025, 0.063), (0.028, 0.07),
                        (0.016, 0.08), (0.012, 0.085)], 24, Pj)
    stick = Pj @ T(0, 0, 0.08) @ R(-8, 'X')
    cylinder(K["Chrome"], 0.01, 0.07, 16, stick)
    lathe(K["Knob"], [(0.0, 0.06), (0.018, 0.065), (0.022, 0.1), (0.021, 0.15), (0.017, 0.17), (0.0, 0.175)], 24,
          stick)
    button(K, stick @ T(0, 0, 0.17), 0, 0, 0.007, "BtnRed")
    silk(K, Pj @ T(0, -0.055, 0.0301), 0, 0, "推进 / 转向", 0.0075)
    Pl = T(-0.3, 1.98, top)
    rbox(K["PanelDark"], 0.08, 0.18, 0.05, Pl @ T(0, 0, 0.025), r=0.01, seg=3)
    box(K["Dark"], 0.012, 0.13, 0.002, Pl @ T(0, 0, 0.0505))
    for k in range(7):
        box(K["Silk"], 0.012 if k % 3 == 0 else 0.007, 0.0012, 0.0004, Pl @ T(0.022, -0.06 + k * 0.02, 0.0502))
    lev = Pl @ T(0, 0.02, 0.05) @ R(-15, 'X')
    cylinder(K["Chrome"], 0.007, 0.12, 12, lev)
    cylinder(K["Knob"], 0.014, 0.08, 16, lev @ T(-0.04, 0, 0.12) @ R(90, 'Y'))
    silk(K, Pl @ T(0, -0.1, 0.0002), 0, 0, "升 / 降", 0.0075)
    anchors.append(empty("Anchor_Spectacles", K.coll, anchor_frame(V((0.52, 1.95, top)), V((0.3, 1, 0)))))
    anchors.append(empty("Anchor_Clipboard", K.coll, anchor_frame(V((-0.55, 1.98, top)), V((-0.2, 1, 0)))))

    # 蛇管台灯：夹在主板上沿，灯罩朝下照着面板
    base = Fc @ V((0.36, 0.33, 0.02))
    shade = V((0.22, 1.98, 0.62))
    target = Fc @ V((0.0, -0.05, 0))
    fwd = (target - shade).normalized()
    rbox(K["Steel"], 0.05, 0.035, 0.04, T(*base) @ T(0, 0, 0.0), r=0.004, seg=2)
    up = V((0, 0, 1))
    path = catmull([base + up * 0.02, base + up * 0.18 + (shade - base) * 0.2, shade + up * 0.1 - fwd * 0.03,
                    shade - fwd * 0.036], 10)
    sweep(K["Chrome"], path, circle_profile(0.0045, 10), scales=[1.0 + 0.18 * (i % 2) for i in range(len(path))])
    Fs = frame(shade, fwd)
    lathe(K["PanelDark"], [(0.012, -0.036), (0.015, -0.032), (0.031, -0.004), (0.034, 0.0), (0.032, 0.0015),
                           (0.029, -0.0015), (0.0135, -0.029), (0.0105, -0.032), (0.012, -0.036)], 32, Fs)
    lathe(K["Silk"], [(0.0128, -0.0296), (0.0288, -0.003), (0.0284, -0.0016), (0.0122, -0.028)], 32, Fs)
    uvsphere(K["LensWhite"], 0.0105, 16, 8, Fs @ T(0, 0, -0.016))
    anchors.append(empty("CabinSpot_Console", K.coll, anchor_frame(shade + fwd * 0.005, fwd)))
    return Fc, Fo


def helm_desk(K, anchors, Fc):
    """驾驶台桌面上的日常：值班的人刚才还坐在这儿。
    茶缸（还冒着热气）、罐头盒改的烟灰缸、烟、火柴、写了一半的潜航记录和一截铅笔；
    主板上坏了的纵倾表拿胶布打了个叉；一根后来加装的线从面板底下拉出来，搭过桌沿垂到地上。"""
    import quarters
    top = DESK_Z - 0.039
    rng = random.Random(17)
    # 茶缸：字朝着驾驶椅，把手朝右后方
    Mm = T(0.15, 1.9, top) @ R(60, 'Z')
    quarters.enamel_mug(K, Mm, words="为人民服务", tea=0.45, seed=21)
    anchors.append(empty("Anchor_Steam", K.coll, T(0.15, 1.9, top + 0.075)))
    # 烟灰缸：压扁的罐头盒，卷边，里面一层烟灰，几个烟头
    Ma = T(-0.17, 1.9, top)
    lathe(K["Can"], [(0.0, 0.0), (0.043, 0.0), (0.045, 0.003), (0.046, 0.022), (0.048, 0.024), (0.0445, 0.0245),
                     (0.0435, 0.004), (0.0, 0.004)], 32, Ma)
    lathe(K["CanLabel"], [(0.0462, 0.006), (0.0462, 0.019)], 32, Ma)
    cylinder(K["Ash"], 0.042, 0.006, 24, Ma @ T(0, 0, 0.004))
    for k, (x, y, yaw, tilt, L) in enumerate(((0.012, -0.01, 30, 4, 0.024), (-0.015, 0.012, 140, 6, 0.018),
                                              (0.0, 0.025, 250, 3, 0.021))):
        M = Ma @ T(x, y, 0.012) @ R(yaw, 'Z') @ R(90 - tilt, 'Y')
        cylinder(K["CableOrange"], 0.0042, 0.012, 10, M)
        cylinder(K["Silk"], 0.0041, L - 0.012, 10, M @ T(0, 0, 0.012))
        cylinder(K["Ash"], 0.0039, 0.0015, 10, M @ T(0, 0, L))
    # 一支搭在缸沿上，烧了一半（烟灰还没掉）
    M = Ma @ T(0.03, -0.03, 0.026) @ R(-40, 'Z') @ R(80, 'Y')
    cylinder(K["CableOrange"], 0.0042, 0.02, 10, M @ T(0, 0, -0.02))
    cylinder(K["Silk"], 0.0041, 0.03, 10, M)
    cylinder(K["Ash"], 0.0043, 0.012, 10, M @ T(0, 0, 0.03), r2=0.0036)
    # 软包烟（拆开了，冒出一支）和火柴盒
    Mp = T(-0.05, 2.05, top) @ R(-18, 'Z')
    rbox(K["Silk"], 0.056, 0.088, 0.021, Mp @ T(0, 0, 0.0105), r=0.004, seg=2)
    rbox(K["BtnRed"], 0.0566, 0.034, 0.0214, Mp @ T(0, -0.022, 0.0105), r=0.004, seg=2)
    rbox(K["Alu"], 0.03, 0.006, 0.015, Mp @ T(-0.008, 0.043, 0.0105), r=0.002, seg=1)
    cylinder(K["Silk"], 0.004, 0.022, 10, Mp @ T(0.01, 0.04, 0.012) @ R(-90, 'X'))
    cylinder(K["CableOrange"], 0.0041, 0.006, 10, Mp @ T(0.01, 0.062, 0.012) @ R(-90, 'X'))
    Mx = T(-0.2, 2.07, top) @ R(12, 'Z')
    rbox(K["Cardboard"], 0.036, 0.053, 0.015, Mx @ T(0, 0, 0.0075), r=0.001, seg=1)
    rbox(K["BtnYellow"], 0.03, 0.044, 0.0006, Mx @ T(0, 0, 0.0152), r=0.0, seg=1)
    K.text("火柴", Mx @ T(0, 0, 0.0156) @ R(90, 'Z'), 0.008, key="InkRed", font=FONT_SERIF)
    for sx in (-1, 1):
        box(K["Dark"], 0.0012, 0.05, 0.012, Mx @ T(sx * 0.0182, 0, 0.0075))
    for k, (x, y, yaw) in enumerate(((-0.235, 1.83, 70), (-0.225, 1.845, 95))):
        M = T(x, y, top + 0.0012) @ R(yaw, 'Z') @ R(90, 'Y')
        cylinder(K["Cardboard"], 0.0012, 0.04, 6, M)
        uvsphere(K["Dark"], 0.0022, 8, 4, M @ T(0, 0, 0.04) @ S(1, 1, 1.4))
    # 潜航记录：A5 表格纸，印好的表头和格线，手写的几行；纸角卷起来一点
    Ml = T(0.0, 1.95, top) @ R(-7, 'Z')
    w, h = 0.148, 0.21
    rbox(K["MeterFace"], w, h, 0.0004, Ml @ T(0, 0, 0.0002), r=0.0, seg=1)
    rbox(K["MeterFace"], 0.03, 0.03, 0.0004, Ml @ T(w / 2 - 0.012, -h / 2 + 0.012, 0.004) @ R(45, 'Z')
         @ R(-22, 'X'), r=0.0, seg=1)
    K.text("潜 航 记 录", Ml @ T(0, h / 2 - 0.016, 0.0005), 0.009, key="Ink", font=FONT_SERIF)
    cols = (-0.05, -0.012, 0.03)
    for k, lb in enumerate(("时间", "深度 m", "航向")):
        K.text(lb, Ml @ T(cols[k] - 0.002, h / 2 - 0.034, 0.0005), 0.0055, key="Ink")
    for j in range(9):
        box(K["Ink"], w - 0.02, 0.0005, 0.0002, Ml @ T(0, h / 2 - 0.042 - j * 0.017, 0.0005))
    for xx in (-0.032, 0.008, 0.052):
        box(K["Ink"], 0.0005, 0.017 * 8, 0.0002, Ml @ T(xx, h / 2 - 0.042 - 0.017 * 4, 0.0005))
    rows = (("02:40", "1820", "265"), ("03:10", "1840", "270"), ("03:40", "1846", "270"), ("04:05", "1845", "？"))
    for j, row in enumerate(rows):
        for k, txt in enumerate(row):
            M = Ml @ T(cols[k] + rng.uniform(-0.002, 0.002), h / 2 - 0.05 - j * 0.017, 0.0005) @ R(rng.uniform(-3, 3), 'Z')
            K.text(txt, M, 0.0075, key="Marker", font=FONT_HAND)
    K.text("04:05 舱底有敲击声 三下", Ml @ T(0.0, h / 2 - 0.05 - 4 * 0.017, 0.0005) @ R(-1.5, 'Z'), 0.0072,
           key="Marker", font=FONT_HAND)
    # 铅笔头：六棱黄杆、削出来的木头尖、铅芯，另一头铁箍和橡皮
    Mq = Ml @ T(0.035, -0.04, 0.0038) @ R(28, 'Z') @ R(90, 'Y')
    cylinder(K["BtnYellow"], 0.0037, 0.07, 6, Mq @ T(0, 0, -0.035))
    cylinder(K["Cardboard"], 0.0034, 0.011, 12, Mq @ T(0, 0, 0.035), r2=0.0009)
    cylinder(K["Dark"], 0.0009, 0.0025, 8, Mq @ T(0, 0, 0.046), r2=0.0001)
    cylinder(K["Alu"], 0.0039, 0.008, 12, Mq @ T(0, 0, -0.043))
    cylinder(K["BtnRed"], 0.0035, 0.005, 12, Mq @ T(0, 0, -0.048))
    # 纵倾表坏了：玻璃上两条胶布打个叉，旁边手写「坏」
    for ang in (38, -38):
        rbox(K["MaskTape"], 0.09, 0.016, 0.0005, Fc @ T(0.27, -0.01, 0.0163) @ R(ang, 'Z'), r=0.0, seg=1)
    K.text("坏", Fc @ T(0.27, -0.01, 0.0172) @ R(4, 'Z'), 0.012, key="Marker", font=FONT_HAND)
    # 后来加装的一根线：从主板底下拉出来，贴着桌面，翻过桌沿垂到地上；中间一个接头缠着黑胶布
    pts = [V((0.4, 2.14, -0.125)), V((0.41, 2.09, top + 0.004)), V((0.402, 1.97, top + 0.005)),
           V((0.41, 1.84, top + 0.005)), V((0.418, 1.805, top - 0.01)), V((0.425, 1.785, top - 0.08)),
           V((0.43, 1.77, -0.45)), V((0.445, 1.745, DECK + 0.04)), V((0.47, 1.71, DECK + 0.009)), V((0.5, 1.68, DECK + 0.0065)),
           V((0.62, 1.62, DECK + 0.0065))]
    Cab.add(pts, 0.0048, "CableGray", samples=8)
    js = V((0.403, 1.98, top + 0.006))
    Mj = frame(js, V((0.01, -1, 0)))
    cylinder(K["ZipBlack"], 0.0078, 0.034, 12, Mj @ T(0, 0, -0.017))
    for z in (-0.017, 0.017):
        cylinder(K["ZipBlack"], 0.0072, 0.006, 12, Mj @ T(0, 0, z - 0.003), r2=0.0055)


def seat(K):
    """驾驶椅：落地底座 + 立柱 + 座垫 + 靠背（人造革）。"""
    x, y = SEAT.x, SEAT.y
    cylinder(K["Console"], 0.2, 0.025, 48, T(x, y, DECK))
    for i in range(6):
        a = 2 * math.pi * i / 6
        socket_screw(K, T(x, y, DECK + 0.025), math.cos(a) * 0.17, math.sin(a) * 0.17, r=0.008)
    cylinder(K["Chrome"], 0.045, 0.38, 24, T(x, y, DECK + 0.02))
    cylinder(K["Rubber"], 0.05, 0.08, 24, T(x, y, DECK + 0.14))
    rbox(K["Console"], 0.4, 0.38, 0.03, T(x, y, DECK + 0.4), r=0.006, seg=2)
    rbox(K["Vinyl"], 0.48, 0.46, 0.08, T(x, y + 0.02, DECK + 0.455), r=0.03, seg=4)
    Mb = T(x, y - 0.24, DECK + 0.75) @ R(-12, 'X')
    rbox(K["Console"], 0.04, 0.03, 0.5, T(x, y - 0.22, DECK + 0.62) @ R(-12, 'X'), r=0.006, seg=2)
    rbox(K["Vinyl"], 0.46, 0.08, 0.52, Mb, r=0.03, seg=4)
    # 坐垫上的补丁（电工胶布）
    rbox(K["Dark"], 0.07, 0.05, 0.001, T(x + 0.1, y + 0.06, DECK + 0.4955) @ R(20, 'Z'), r=0.0, seg=1)
    rbox(K["Dark"], 0.06, 0.05, 0.001, T(x + 0.1, y + 0.06, DECK + 0.4957) @ R(-25, 'Z'), r=0.0, seg=1)


# ============================================================================ 神龛
def shrine(K, anchors, F):
    """妈祖神龛：红漆木龛、金顶、红布蒙面的神像、香炉和三炷香、黄符。F：龛底中心往上 0.165 米，Z 朝外。"""
    rbox(K["Alu"], 0.36, 0.006, 0.22, F @ T(0, -0.16, 0.0), r=0.0015, seg=1)
    w, h, d = 0.26, 0.3, 0.15
    rbox(K["Lacquer"], w, h, 0.012, F @ T(0, 0.0, -0.07), r=0.002, seg=2)
    for sx in (-1, 1):
        rbox(K["Lacquer"], 0.012, h, d, F @ T(sx * w / 2, 0.0, 0.0), r=0.002, seg=2)
    rbox(K["Lacquer"], w + 0.012, 0.016, d, F @ T(0, -h / 2 + 0.008, 0.0), r=0.002, seg=2)
    rbox(K["Lacquer"], w + 0.04, 0.03, d + 0.03, F @ T(0, -h / 2, 0.0), r=0.003, seg=2)
    rbox(K["Lacquer"], w + 0.012, 0.016, d, F @ T(0, h / 2, 0.0), r=0.002, seg=2)
    for sx in (-1, 1):
        cylinder(K["Lacquer"], 0.011, h - 0.03, 16, F @ T(sx * (w / 2 - 0.02), -h / 2 + 0.015, d / 2 - 0.01)
                 @ R(-90, 'X'))
    # 扎带把龛身捆在托板上
    for sx in (-1, 1):
        torus(K["ZipBlack"], 0.02, 0.0018, 24, 4, F @ T(sx * 0.15, -0.16, 0.02) @ R(90, 'Y') @ S(1, 2.4, 1))
    # 金顶（两坡飞檐）
    for side in (-1, 1):
        path = []
        for k in range(13):
            t = k / 12
            x = -w / 2 - 0.05 + (w + 0.1) * t
            lift = 0.025 * (abs(2 * t - 1) ** 3)
            path.append(F @ V((x, h / 2 + 0.03 + lift, side * 0.03)))
        prof = [(0, -0.003), (0.045, -0.025), (0.045, -0.017), (0, 0.005)]
        sweep(K["Gold"], path, [(px, py * side) for px, py in prof] if side > 0 else list(reversed(prof)))
    rbox(K["Gold"], w + 0.06, 0.02, 0.02, F @ T(0, h / 2 + 0.045, 0), r=0.003, seg=2)
    for y in (-h / 2 + 0.02, h / 2 - 0.006):
        box(K["Gold"], w + 0.02, 0.006, 0.006, F @ T(0, y, 0.077))
    # 龛口挂的红布帘（褶皱）
    rows = []
    bm = K["ClothRed"]
    for j, yy in enumerate((h / 2 - 0.01, h / 2 - 0.035, h / 2 - 0.05)):
        row = []
        for i in range(41):
            t = i / 40
            x = -w / 2 + 0.01 + (w - 0.02) * t
            z = 0.079 + 0.004 * math.sin(t * 31) * (j + 1) / 3
            row.append(bm.verts.new(F @ V((x, yy, z))))
        rows.append(row)
    back_rows = [[bm.verts.new(v.co + (F.to_3x3() @ V((0, 0, -0.0015)))) for v in row] for row in rows]
    _grid_faces(bm, rows, closed_u=False)
    _grid_faces(bm, back_rows, closed_u=False, flip=True)
    for row, brow in ((rows[0], back_rows[0]), (rows[-1], back_rows[-1])):
        _grid_faces(bm, [row, brow], closed_u=False)
    _grid_faces(bm, [[rows[0][0], rows[1][0], rows[2][0]], [back_rows[0][0], back_rows[1][0], back_rows[2][0]]],
                closed_u=False)
    _grid_faces(bm, [[rows[0][-1], rows[1][-1], rows[2][-1]],
                     [back_rows[0][-1], back_rows[1][-1], back_rows[2][-1]]], closed_u=False)

    # 神像：莲台 + 坐姿袍身 + 头 + 冕冠，脸被红布蒙着
    S0 = F @ T(0, -0.135, -0.02) @ R(-90, 'X')
    bs = K["Statue"]
    lathe(bs, [(0.0, 0.0), (0.045, 0.0), (0.047, 0.008), (0.04, 0.012), (0.046, 0.02), (0.036, 0.024),
               (0.0, 0.024)], 48, S0)
    for k in range(12):
        a = 2 * math.pi * k / 12
        uvsphere(bs, 0.01, 12, 6, S0 @ T(math.cos(a) * 0.04, math.sin(a) * 0.04, 0.02) @ S(1, 1, 0.6))
    lathe(bs, [(0.0, 0.024), (0.034, 0.024), (0.036, 0.034), (0.031, 0.05), (0.024, 0.07), (0.025, 0.085),
               (0.03, 0.098), (0.027, 0.106), (0.012, 0.112), (0.0, 0.113)], 48, S0 @ S(1.15, 0.85, 1))
    box(bs, 0.012, 0.004, 0.045, S0 @ T(0, 0.024, 0.085) @ R(-12, 'X'))
    for sx in (-1, 1):
        uvsphere(bs, 0.007, 12, 8, S0 @ T(sx * 0.009, 0.022, 0.072))
        sweep(bs, catmull([S0 @ V((sx * 0.03, 0.0, 0.098)), S0 @ V((sx * 0.026, 0.016, 0.08)),
                           S0 @ V((sx * 0.01, 0.022, 0.072))], 4), circle_profile(0.007, 10))
    uvsphere(bs, 0.0145, 24, 12, S0 @ T(0, 0.0, 0.125))
    box(bs, 0.044, 0.03, 0.003, S0 @ T(0, 0, 0.145))
    for sx in (-1, 0, 1):
        for k in range(4):
            uvsphere(bs, 0.0018, 8, 4, S0 @ T(sx * 0.012, 0.016, 0.141 - k * 0.005))

    def veil(bm):
        rings = []
        for k in range(10):
            t = k / 9
            r, z = 0.004 + 0.026 * t ** 0.8, 0.143 - 0.045 * t
            ring = []
            for i in range(48):
                a = 2 * math.pi * i / 48
                wob = 1 + 0.08 * math.sin(a * 7) * (z < 0.13)
                ring.append(bm.verts.new(S0 @ V((math.cos(a) * r * wob, math.sin(a) * r * wob * 0.9, z))))
            rings.append(ring)
        S0i = S0.inverted()
        inner = [[bm.verts.new(S0 @ ((S0i @ v.co) * 0.97)) for v in ring] for ring in rings]
        _grid_faces(bm, rings)
        _grid_faces(bm, inner, flip=True)
        _grid_faces(bm, [rings[-1], inner[-1]])
    veil(K["ClothRed"])

    # 香炉（三足鼎，炉里是香灰）+ 三炷香
    P0 = F @ T(0, -0.15, 0.1) @ R(-90, 'X')
    lathe(K["Brass"], [(0.0, 0.012), (0.03, 0.013), (0.04, 0.025), (0.042, 0.045), (0.036, 0.05),
                       (0.034, 0.05), (0.03, 0.04), (0.0, 0.04)], 48, P0)
    cylinder(K["Ash"], 0.033, 0.006, 32, P0 @ T(0, 0, 0.04))
    for i in range(3):
        a = 2 * math.pi * i / 3
        cylinder(K["Brass"], 0.005, 0.016, 12, P0 @ T(math.cos(a) * 0.022, math.sin(a) * 0.022, 0.0), r2=0.004)
    for sx in (-1, 1):
        torus(K["Brass"], 0.009, 0.0025, 16, 6, P0 @ T(sx * 0.043, 0, 0.05) @ R(90, 'Y'))
    for i, (dx, tilt) in enumerate(((-0.012, -6), (0.0, 0), (0.012, 5))):
        base = P0 @ T(dx, 0, 0.044) @ R(tilt, 'Y')
        hgt = 0.085 - abs(dx) * 1.2
        K.separate(f"Incense_{i}", "Incense", lambda bm, base=base, hgt=hgt: cylinder(bm, 0.0013, hgt, 8, base),
                   smooth=True, sharp=None)
        K.separate(f"IncenseTip_{i}", "Ember",
                   lambda bm, base=base, hgt=hgt: uvsphere(bm, 0.0018, 8, 6, base @ T(0, 0, hgt)),
                   smooth=True, sharp=None)
    for sx, txt in ((-1, "敕令\n镇海"), (1, "出入\n平安")):
        Mt = F @ T(sx * 0.137, -0.01, 0.079) @ R(sx * 2, 'Z')
        rbox(K["Talisman"], 0.034, 0.12, 0.0006, Mt, r=0.0, seg=1)
        K.text(txt, Mt @ T(0, 0, 0.0003), 0.085, key="BrushRed", font=FONT_BRUSH)
    anchors.append(empty("Anchor_ShrineLamp", K.coll, F @ T(0.112, -0.14, 0.085) @ R(-90, 'X')))
    anchors.append(empty("Anchor_ShrineLight", K.coll, F @ T(0, -0.08, 0.06)))


# ============================================================================ 生活痕迹
def cloth(bm, rows, thick=0.004):
    """布料：rows 是二维点阵（一行行），沿点阵法线加厚成封闭的薄片。"""
    nr, nc = len(rows), len(rows[0])

    def nrm(j, i):
        a = rows[min(j + 1, nr - 1)][i] - rows[max(j - 1, 0)][i]
        b = rows[j][min(i + 1, nc - 1)] - rows[j][max(i - 1, 0)]
        n = a.cross(b)
        return n.normalized() if n.length > 1e-9 else V((0, 0, 1))
    front = [[bm.verts.new(rows[j][i] + nrm(j, i) * thick / 2) for i in range(nc)] for j in range(nr)]
    back = [[bm.verts.new(rows[j][i] - nrm(j, i) * thick / 2) for i in range(nc)] for j in range(nr)]
    _grid_faces(bm, front, closed_u=False)
    _grid_faces(bm, back, closed_u=False, flip=True)
    _grid_faces(bm, [front[0], back[0]], closed_u=False)
    _grid_faces(bm, [front[-1], back[-1]], closed_u=False)
    _grid_faces(bm, [[r[0] for r in front], [r[0] for r in back]], closed_u=False)
    _grid_faces(bm, [[r[-1] for r in front], [r[-1] for r in back]], closed_u=False)


def towel(K, bar, y0, y1, hang_in, hang_out, seed=1, key="Towel"):
    """搭在桥架边梁上的毛巾。bar=(x, z) 是梁的上沿，沿 Y 方向；两边各垂下 hang_in（朝舱内）、hang_out。"""
    rng = random.Random(seed)
    bx, bz = bar
    s = 1 if bx > 0 else -1
    r = 0.008
    ph = [rng.uniform(0, 6.28) for _ in range(4)]
    # 截面：舱内一侧从下往上 → 绕过梁顶 → 外侧往下（t 是离梁顶往下的距离，带正负号区分两边）
    prof = [(-s, hang_in * (1 - k / 7)) for k in range(7)]
    prof += [("arc", k / 6) for k in range(7)]
    prof += [(s, hang_out * k / 7) for k in range(1, 8)]
    rows = []
    for item in prof:
        row = []
        for i in range(15):
            u = i / 14
            y = y0 + (y1 - y0) * u
            if item[0] == "arc":
                # a=0 在舱内一侧，a=π 在外侧
                a = math.pi * item[1]
                p = V((bx - s * math.cos(a) * r, y, bz + math.sin(a) * r))
            else:
                side, d = item
                # 越往下褶皱越大，下摆参差
                d *= 1.0 + 0.07 * math.sin(u * 9 + ph[0]) + 0.04 * math.sin(u * 23 + ph[1])
                fold = 0.026 * min(d / 0.1, 1.0) * (math.sin(u * 11 + ph[2]) + 0.45 * math.sin(u * 27 + ph[3]))
                # 下摆往外卷一点
                curl = max(0.0, d - hang_in * 0.85) * 0.5
                p = V((bx + side * (r + d * 0.08 + curl) + fold, y, bz - d))
            row.append(p)
        rows.append(row)
    cloth(K[key], rows, 0.004)


def jacket(K):
    """搭在驾驶椅靠背上的工作服：前面耷拉一小截领子，后面垂到座垫以下，两只袖子挂在背后。"""
    Mb = T(SEAT.x, SEAT.y - 0.24, DECK + 0.75) @ R(-12, 'X')
    rng = random.Random(8)
    ph = [rng.uniform(0, 6.28) for _ in range(4)]
    r = 0.046
    prof = [("f", 0.13 * (1 - k / 5)) for k in range(5)]
    prof += [("arc", k / 8) for k in range(9)]
    prof += [("b", 0.56 * k / 10) for k in range(1, 11)]
    rows = []
    for item in prof:
        row = []
        for i in range(21):
            u = i / 20
            x = -0.27 + 0.54 * u
            edge = max(0.0, abs(x) - 0.2) / 0.07  # 两边超出靠背的部分往下耷拉
            if item[0] == "arc":
                a = math.pi * item[1]
                p = V((x, math.cos(a) * r, 0.26 + math.sin(a) * r - edge * 0.05))
            else:
                d = item[1]
                side = 1 if item[0] == "f" else -1
                d *= 1.0 + 0.05 * math.sin(u * 7 + ph[0])
                fold = 0.016 * min(d / 0.15, 1.0) * (math.sin(u * 17 + ph[1]) + 0.6 * math.sin(u * 31 + ph[2]))
                # 褶皱只往外鼓（往里就穿进靠背了）
                yy = side * (r + 0.028 + fold + max(0.0, d - 0.52) * 0.4)
                if side < 0 and d > 0.5:
                    yy -= (d - 0.5) * 0.6  # 下摆搭到座垫后沿以外，往后飘一点
                p = V((x * (1 + d * 0.15), yy, 0.26 - d - edge * 0.05))
            row.append(Mb @ p)
        rows.append(row)
    cloth(K["Jacket"], rows, 0.005)
    # 袖子：从背面两侧肩部垂下
    for sx in (-1, 1):
        pts = [Mb @ V((sx * 0.25, -0.07, 0.2)), Mb @ V((sx * 0.27, -0.1, 0.0)), Mb @ V((sx * 0.25, -0.1, -0.2)),
               Mb @ V((sx * 0.22, -0.13, -0.33))]
        path = catmull(pts, 6)
        sweep(K["Jacket"], path, circle_profile(0.042, 14),
              scales=[1.0 - 0.18 * i / (len(path) - 1) for i in range(len(path))])
        # 袖口罗纹
        e = path[-1]
        cylinder(K["Jacket"], 0.036, 0.03, 14, frame(e, (path[-1] - path[-2]).normalized()) @ T(0, 0, -0.01))


def net_bag(K, anchors, top, n_fruit=4):
    """桥架上挂着一网兜橘子。top：挂钩位置。"""
    x, y, z = top
    # S 钩
    hook = [V((x, y, z + 0.03)), V((x - 0.012, y, z + 0.02)), V((x - 0.012, y, z + 0.004)), V((x, y, z - 0.004)),
            V((x + 0.01, y, z - 0.02)), V((x, y, z - 0.034))]
    sweep(K["Steel"], catmull(hook, 4), circle_profile(0.0018, 6))
    zb = z - 0.3  # 网兜底
    prof = [(0.0, 0.0), (0.04, 0.004), (0.068, 0.025), (0.075, 0.05), (0.07, 0.085), (0.05, 0.12), (0.025, 0.16),
            (0.008, 0.22), (0.005, 0.266)]
    lathe(K["Net"], prof, 32, T(x, y, zb))
    torus(K["Net"], 0.006, 0.0025, 12, 6, T(x, y, zb + 0.255))
    for k in range(3):
        a = 2 * math.pi * k / 3 + 0.4
        uvsphere(K["Orange"], 0.034, 20, 12, T(x + math.cos(a) * 0.035, y + math.sin(a) * 0.035, zb + 0.037)
                 @ S(1, 1, 0.92))
    if n_fruit > 3:
        uvsphere(K["Orange"], 0.032, 20, 12, T(x + 0.005, y - 0.004, zb + 0.095) @ S(1, 1, 0.92))
    anchors.append(empty("Net_Center", K.coll, T(x, y, zb)))


def cabinet_contents(K, s, y0, y1, z0, z1):
    """开着的柜子里：一层隔板，下层一排罐头，上层纸箱和一卷胶布。"""
    zs = (z0 + z1) / 2 + 0.02
    sbox(K["Console"], s, 0.84, 1.22, y0 + 0.002, y1 - 0.002, zs - 0.012, zs, r=0.002, seg=1)
    rng = random.Random(4)
    for k, (ax, yy) in enumerate(((0.95, 0.25), (0.96, 0.5), (1.08, 0.3), (1.09, 0.6), (0.94, 0.78))):
        y = y0 + (y1 - y0) * yy
        M = T(s * ax, y, z0) @ R(rng.uniform(0, 360), 'Z')
        if k == 4:
            M = T(s * ax, y, z0 + 0.037) @ R(90, 'X') @ R(25, 'Y')  # 倒在一边
            M = M @ T(0, 0, -0.055)
        lathe(K["Can"], [(0.0, 0.0), (0.036, 0.0), (0.037, 0.004), (0.037, 0.106), (0.036, 0.11), (0.0, 0.11)], 24, M)
        lathe(K["CanLabel"], [(0.0375, 0.012), (0.0375, 0.098)], 24, M)
    # 上层：纸箱（开着口）、胶布
    M = T(s * 1.05, y0 + (y1 - y0) * 0.4, zs) @ R(8, 'Z')
    w, d, h = 0.2, 0.17, 0.16
    rbox(K["Cardboard"], w, d, 0.004, M @ T(0, 0, 0.002), r=0.0, seg=1)
    for sx in (-1, 1):
        rbox(K["Cardboard"], 0.004, d, h, M @ T(sx * w / 2, 0, h / 2), r=0.0, seg=1)
        rbox(K["Cardboard"], w, 0.004, h, M @ T(0, sx * d / 2, h / 2), r=0.0, seg=1)
        # 翻开的盖子
        rbox(K["Cardboard"], w, 0.004, d / 2, M @ T(0, sx * d / 2, h) @ R(-sx * 110, 'X') @ T(0, 0, d / 4), r=0.0, seg=1)
    rbox(K["MaskTape"], 0.05, d + 0.002, 0.001, M @ T(0, 0, h / 2) @ R(90, 'Y') @ T(-0.0, 0, w / 2 + 0.001), r=0.0, seg=1)
    torus(K["MaskTape"], 0.03, 0.012, 24, 8, T(s * 0.92, y0 + (y1 - y0) * 0.8, zs + 0.012) @ S(1, 1, 1.6))


# ============================================================================ 贴花挂点
def decal(anchors, coll, kind, pos, normal, up, w, h, depth=0.06):
    """在 Godot 里换成 Decal：挂点的缩放就是贴花的尺寸（X 宽、Y 高、Z 投射深度）。
    Godot 里 Decal 沿局部 -Y 投射，挂点 +Z（Blender）导出后正是 Godot 的 +Y。"""
    n = sum(1 for a in anchors if a.name.startswith(f"Decal_{kind}_"))
    anchors.append(empty(f"Decal_{kind}_{n:02d}", coll, frame(V(pos), V(normal), V(up)) @ S(w, h, depth)))


def decals(anchors, coll):
    def d(kind, pos, normal, up, w, h, depth=0.06):
        decal(anchors, coll, kind, pos, normal, up, w, h, depth)
    UP, Z = V((0, 0, 1)), V((0, 1, 0))
    # ---- 桌面：杯底水渍圈、烟头烫痕、撕掉胶布留下的残胶、胳膊肘常压的地方磨亮了
    for x, y, r in ((0.96, -0.2, 0.1), (1.08, -0.07, 0.085), (-0.9, 0.62, 0.1), (1.0, -1.05, 0.09)):
        d("Ring", (x, y, DESK_Z), UP, V((math.sin(x * 9), math.cos(x * 9), 0)), r, r, 0.03)
    d("Ring", (0.42, 1.9, DESK_Z - 0.039), UP, Z, 0.1, 0.1, 0.03)
    for x, y, r in ((0.87, -0.98, 0.035), (0.905, -0.925, 0.028), (-0.88, -1.25, 0.03), (-0.6, 1.88, 0.03)):
        z = DESK_Z if abs(y) < 1.8 else DESK_Z - 0.039
        d("Burn", (x, y, z), UP, V((x, 1, 0)), r, r, 0.03)
    d("Tape", (-0.97, -0.3, DESK_Z), UP, V((0.34, 0.94, 0)), 0.15, 0.05, 0.03)
    d("Tape", (1.12, 0.32, DESK_Z), UP, V((-0.2, 1, 0)), 0.11, 0.045, 0.03)
    d("Tape", (0.95, -1.6, DESK_Z), UP, V((0.1, 1, 0)), 0.12, 0.05, 0.03)
    for x, y, L in ((0.86, -1.35, 0.55), (-0.86, -0.75, 0.5), (0.86, 0.35, 0.45), (-0.86, 0.4, 0.45)):
        d("Polish", (x, y, DESK_Z), UP, Z, 0.16, L, 0.03)
    d("Polish", (0.0, 1.88, DESK_Z - 0.039), UP, Z, 0.75, 0.13, 0.03)
    # ---- 柜门：把手周围的手油，踢脚处鞋蹭的印子
    cab_edges = [CON_Y0] + list(FRAMES[1:]) + [CON_Y1]
    zc = (DECK + 0.1 + DESK_Z - 0.045) / 2
    for s, i, k in ((1, 1, 0), (1, 2, 1), (1, 4, 0), (-1, 1, 0), (-1, 3, 1), (-1, 4, 0), (1, 0, 1), (-1, 5, 0)):
        a, b = cab_edges[i] + 0.012, cab_edges[i + 1] - 0.012
        y0 = a + (b - a) * k / 2 + 0.006
        y1 = a + (b - a) * (k + 1) / 2 - 0.006
        hx = (y1 - y0) / 2 - 0.035
        # 柜门坐标系的 +X 是 -s 方向的 Y（见 consoles 里的 frame）
        yh = (y0 + y1) / 2 + (hx if k == 0 else -hx) * -s
        d("Grease", (s * 0.8, yh, zc + 0.12), V((-s, 0, 0)), UP, 0.13, 0.17, 0.05)
    for s in (-1, 1):
        for y in (-1.45, -0.75, -0.1, 0.5, 1.15):
            d("Scuff", (s * 0.8, y + 0.07 * s, DECK + 0.2), V((-s, 0, 0)), UP, 0.55, 0.17, 0.06)
    # ---- 地上：一串湿脚印从关着的水密门走出来，停在神龛前面
    steps = [(0.07, -2.4, 4, "L"), (-0.1, -2.14, 10, "R"), (-0.2, -1.88, 16, "L"), (-0.42, -1.64, 24, "R"),
             (-0.5, -1.38, 40, "L"), (-0.62, -1.27, 88, "R"), (-0.62, -1.45, 92, "L")]
    for x, y, yaw, foot in steps:
        a = math.radians(yaw)
        d("Boot" + foot, (x, y, DECK), UP, V((-math.sin(a), math.cos(a), 0)), 0.11, 0.29, 0.03)
    d("Puddle", (-0.43, -0.2, DECK), UP, V((0.3, 1, 0)), 0.32, 0.24, 0.03)
    d("Hazard", (DOOR[0], Y_AFT + 0.07, DECK), UP, Z, 0.66, 0.09, 0.03)
    d("Hazard", (DOOR[0], Y_AFT - 0.08, DECK), UP, Z, 0.66, 0.09, 0.03)
    # ---- 中间隔壁：舱段号、严禁烟火、门框楔块底下的锈水、接线盒底下的锈水、门边扶手旁一个手印
    d("TextC03", (0.6, Y_AFT, 0.62), Z, UP, 0.26, 0.104, 0.05)
    d("TextFire", (0.65, Y_AFT, 0.12), Z, UP, 0.075, 0.3, 0.05)
    for deg in (25, -25, 90):
        q, _ = door_ring(deg, DOOR_FRAME_K + 0.02)
        d("Rust", (q.x, Y_AFT + 0.03, q.z - 0.17), Z, UP, 0.06, 0.28, 0.1)
    d("Rust", (-0.92, Y_AFT + 0.02, 0.1), Z, UP, 0.12, 0.32, 0.06)
    d("Hand", (-0.62, Y_AFT + 0.01, 0.3), Z, V((-0.2, 0, 0.98)), 0.12, 0.22, 0.04)
    # ---- 壳体：穿舱件下面的锈水
    for s, y in PENETRATORS:
        a = math.radians(PEN_ANG + 9)
        p = V((s * math.sin(a) * R_IN, y, math.cos(a) * R_IN))
        d("Rust", p, V((-s * math.sin(a), 0, -math.cos(a))), V((-s * math.cos(a), 0, math.sin(a))), 0.1, 0.32, 0.12)
    # ---- 仪表板：老面板的螺钉下面挂着锈迹
    w = (0.6 - 0.065)
    ys = [-PANEL_LEN / 2 + 0.06 + (PANEL_LEN - 0.12) * k / 4 for k in range(5)]
    for s, bay, picks in ((1, 2, ((1, 3), (-1, 2), (1, 1))), (1, 3, ((-1, 3), (1, 0))), (-1, 0, ((1, 3), (-1, 1))),
                          (-1, 3, ((1, 2),))):
        F = panel_frame(s, (BAYS[bay][0] + BAYS[bay][1]) / 2)
        n = F.to_3x3() @ V((0, 0, 1))
        u = F.to_3x3() @ V((0, 1, 0))
        for sx, k in picks:
            d("Rust", F @ V((sx * (w / 2 - 0.018), ys[k] - 0.075, 0)), n, u, 0.045, 0.14, 0.04)
    # ---- 驾驶台主板：下排开关、声呐旋钮这些天天拨的地方，漆面被手油摸得发黑发亮
    n_c = V((0, -math.cos(math.radians(15)), math.sin(math.radians(15))))
    u_c = V((0, math.sin(math.radians(15)), math.cos(math.radians(15))))
    Fc = frame(V((0, 2.22, 0.18)), n_c, u_c)
    for x in (-0.24, -0.08, 0.08, 0.24):
        d("Grease", Fc @ V((x, -0.262, 0)), n_c, u_c, 0.16, 0.1, 0.04)
    d("Grease", Fc @ V((0.0, -0.03, 0)), n_c, u_c, 0.2, 0.08, 0.04)
    # ---- 舷窗：窗下的冷凝水顺着压环往下淌，滴到肘托上
    for s in (-1, 1):
        o, dd = vp_axis(s)
        F = frame(o, dd)
        d("Streak", F @ V((0, -0.2, 1.19)), -dd, F.to_3x3() @ V((0, 1, 0)), 0.07, 0.12, 0.05)
        d("Puddle", (s * 1.03, VP_Y, DESK_Z + 0.04), UP, Z, 0.2, 0.16, 0.03)
    # ---- 管子上刷的介质和流向
    for i, y, kind in ((1, -0.75, "TextCool"), (1, 0.62, "TextCool"), (2, -1.0, "TextFireWater"),
                       (2, 0.25, "TextFireWater"), (3, -0.9, "TextReturn"), (0, -0.6, "TextAir")):
        x, z, r, _ = PIPES[i]
        r = r + 0.005 if i == 0 else r
        d(kind, (x, y, z - r), V((0, 0, -1)), V((1, 0, 0)), 0.26 if r < 0.05 else 0.3, r * 1.7, r * 2)


# ============================================================================ 其它小东西
def charm(K, top):
    """驾驶台顶板下挂着的平安符：红绳 + 红布符袋 + 玉平安扣 + 黄穗子。
    单独成对象 Sway_Charm（原点在挂点），Godot 里随潜艇晃动。"""
    L = 0.13

    def geo(bm):
        sweep(bm, [V((0, 0, 0)), V((0, 0, -L))], circle_profile(0.0012, 6))
        rbox(bm, 0.03, 0.009, 0.042, T(0, 0, -L - 0.021), r=0.004, seg=2)
    ob = K.separate("Sway_Charm", "ClothRed", geo, smooth=True, sharp=None)

    def jade(bm):
        torus(bm, 0.011, 0.0055, 32, 12, T(0, 0, -L - 0.06) @ R(90, 'X'))
    jd = K.separate("Sway_Charm_Jade", "Jade", jade)

    def tassel(bm):
        for k in range(14):
            a = 2 * math.pi * k / 14
            x, y = math.cos(a) * 0.003, math.sin(a) * 0.003
            sweep(bm, [V((x, y, -L - 0.074)), V((x * 2.2, y * 2.2, -L - 0.11))], circle_profile(0.0007, 4))
        cylinder(bm, 0.0045, 0.008, 12, T(0, 0, -L - 0.08))
    ts = K.separate("Sway_Charm_Tassel", "Talisman", tassel)
    for o in (ob, jd, ts):
        o.matrix_world = T(*top)


def cabin_fan(K, p, look):
    """夹在机柜顶上的小电扇（舱里闷热潮湿，几乎每台老潜器里都有）。"""
    F = frame(p, (V(look) - p).normalized())
    base = V((p.x, p.y, HOOD_Z[1]))
    rbox(K["Steel"], 0.09, 0.09, 0.012, T(*base) @ T(0, 0, 0.006), r=0.003, seg=1)
    sweep(K["Steel"], catmull([base, (base + p) / 2 + V((0, 0, 0.02)), F @ V((0, -0.01, -0.07))], 6),
          circle_profile(0.006, 10))
    cylinder(K["EquipBeige"], 0.03, 0.06, 32, F @ T(0, 0, -0.085))
    lathe(K["EquipBeige"], [(0.03, -0.025), (0.026, -0.015), (0.012, -0.008), (0.0, -0.007)], 32, F)
    for k in range(4):
        a = 90 * k + 20
        Mb = F @ T(0, 0, -0.012) @ R(a, 'Z') @ T(0.045, 0, 0) @ R(25, 'X')
        rbox(K["EquipBeige"], 0.06, 0.032, 0.0015, Mb, r=0.0, seg=1)
    cylinder(K["EquipBeige"], 0.012, 0.01, 20, F @ T(0, 0, -0.018))
    for z, rr in ((0.0, 0.085), (-0.03, 0.085)):
        for k in range(4):
            torus(K["Chrome"], rr * (k + 1) / 4, 0.0012, 48, 4, F @ T(0, 0, z + (0.004 if z == 0 else 0)))
    for k in range(12):
        a = math.radians(30 * k)
        sweep(K["Chrome"], catmull([F @ V((0, 0, 0.006)), F @ V((math.cos(a) * 0.05, math.sin(a) * 0.05, 0.004)),
                                    F @ V((math.cos(a) * 0.085, math.sin(a) * 0.085, -0.012)),
                                    F @ V((math.cos(a) * 0.08, math.sin(a) * 0.08, -0.03))], 4),
              circle_profile(0.0011, 4))
    torus(K["Chrome"], 0.086, 0.002, 48, 6, F @ T(0, 0, -0.012))


def desk_props(anchors, coll):
    """桌面和地上随手放的东西（Godot 里按挂点摆 Poly Haven 道具）。"""
    def put(name, x, y, z, yaw):
        a = math.radians(yaw)
        anchors.append(empty(name, coll, anchor_frame(V((x, y, z)), V((math.sin(a), math.cos(a), 0)))))
    put("Anchor_Thermos", 0.88, -0.05, DESK_Z, 30)
    put("Anchor_Flashlight", 0.9, -0.38, DESK_Z, 70)
    put("Anchor_Multimeter", 0.95, -1.5, DESK_Z, 100)
    put("Anchor_Screwdriver", 0.86, -1.3, DESK_Z, 160)
    put("Anchor_Pliers", 0.92, -1.22, DESK_Z, 120)
    put("Anchor_Tape", 1.05, -1.25, DESK_Z, 0)
    put("Anchor_Watch", 0.9, -0.72, DESK_Z, 50)
    # 检查单夹板挂在驾驶台左边的机柜上
    anchors.append(empty("Anchor_Checklist", coll, anchor_frame(V((-0.795, 1.6, 0.3)), V((1, 0, 0)))))
    # 防毒面具挂在后部左舷舱壁的钩子上


# ============================================================================ 入口
Cab = None


def build_cockpit(coll, M, anchors):
    global Cab
    materials(M)
    K = Parts(coll, M, "Int")
    Cab = Cables(random.Random(11))

    hull(coll, M)
    frames(K)
    weld_seams(K)
    deck(K)
    bilge(K, anchors)
    consoles(K, anchors)
    bay_power(K)
    bay_life(K)
    bay_hydraulics(K)
    bay_env(K, anchors)
    bay_shrine(K, anchors)
    bay_nav(K, anchors)
    bay_powerbox(K, anchors)
    bay_comms(K, anchors)
    viewports(K, anchors)
    hatch(K)
    bulkhead(K, anchors)
    import quarters  # 生活舱（放在这里导入，避免和本模块循环导入）
    quarters.build(K, anchors)
    overhead(K, anchors)
    Fc, Fo = helm(K, anchors)
    helm_desk(K, anchors, Fc)
    seat(K)
    charm(K, Fo @ V((-0.3, -0.155, 0.0)))
    cabin_fan(K, V((0.9, 1.62, 0.84)), EYE_SEATED + V((0, 0.2, -0.1)))
    desk_props(anchors, coll)
    # 生活痕迹：桥架上搭的毛巾、椅背上的工作服、一网兜橘子
    towel(K, (-0.774, 0.864), -0.95, -0.67, 0.2, 0.15)
    jacket(K)
    net_bag(K, anchors, (0.776, 0.45, 0.85))
    decals(anchors, coll)

    # 舷窗外框上方的手写字
    tape_label(K, frame(V((-1.2, VP_Y, 0.55)), V((1, 0, -0.35)).normalized()), 0, 0, "别看太久", 0.014, 3)

    Cab.build(K)
    K.flush()
    anchors.append(empty("Anchor_Eye", coll, anchor_frame(EYE_SEATED, V((0, 1, -0.3)))))
    anchors.append(empty("Anchor_Stand", coll, anchor_frame(V((0, 1.0, DECK)), V((0, 1, 0)))))
