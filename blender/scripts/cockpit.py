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
                 valve_wheel, unit, FONT_BRUSH, FONT_SERIF)

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
DOOR_HINGE = (-(0.32 + 0.075), Y_AFT + 0.135)  # 门轴 (x, y)：在左舷一侧、门扇正面外，门往控制舱里开
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
    # 生活舱
    add("Blanket", "M_Blanket", (0.32, 0.3, 0.27), 0.0, 0.95)
    add("Curtain", "M_Curtain", (0.36, 0.38, 0.3), 0.0, 0.9)
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
        sweep(K[key], [V((x, Y_AFT, DECK - 0.27)), V((x, y1, DECK - 0.27))], circle_profile(r, 20))
        for y in (-1.4, -0.2, 1.0):
            cylinder(K[key], r + 0.018, 0.022, 24, T(x, y, DECK - 0.27) @ R(-90, 'X'))
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
    Mb = T(0.1, -0.95, wz + 0.008) @ R(70, 'Z') @ R(90, 'Y') @ T(0, 0, -0.1)
    lathe(K["Bottle"], [(0.0, 0.0), (0.028, 0.002), (0.032, 0.012), (0.032, 0.13), (0.024, 0.16), (0.012, 0.175),
                        (0.012, 0.192), (0.0, 0.192)], 24, Mb)
    cylinder(K["BtnRed"], 0.0135, 0.014, 16, Mb @ T(0, 0, 0.19))
    # 烟头
    rng = random.Random(5)
    for x, y in ((-0.12, -0.6), (0.05, -0.55), (0.18, 0.2), (-0.2, 0.75), (0.0, -1.6), (-0.05, 1.1)):
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
    # 两根液压软管从面板下部穿出、弯进桌面下
    for k, x in enumerate((-0.15, -0.09)):
        connector(K, F, x, -0.2, r=0.011, plug="Steel")
    for k, x in enumerate((-0.15, -0.09)):
        s0 = F @ V((x, -0.2, 0.035))
        n = (F.to_3x3() @ V((0, 0, 1))).normalized()
        e = V((1.12, s0.y + 0.05 * k, DESK_Z - 0.01))
        Cab.add([s0, s0 + n * 0.06, (s0 + e) / 2 + n * 0.05 + V((0, 0, -0.08)), e], 0.008, "CableBlack")


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
DOOR_DOGS = (90, 32, 0, -32, -90)  # 门扇上压紧把手的位置（角度，0° 朝右舷、90° 朝上；门轴那一侧靠铰链压紧）


def bulkhead(K, anchors):
    """控制舱和生活舱之间的隔壁（两面都看得见）。门框、压紧块、铰链座焊在隔壁上；
    门扇和手轮单独导出（Door_Leaf_*、Door_Wheel_*），Godot 里绕 Door_Hinge 转（见 watertight_door.gd）。"""
    import bmesh
    dx, dz, da, db = DOOR
    y = Y_AFT
    t_plate = 0.012

    def inside_door(x, z, k=1.0):
        return ((x - dx) / (da * k)) ** 2 + ((z - dz) / (db * k)) ** 2 < 1.0

    def plate(bm, yy, back=False):
        """隔壁板（单面），门洞和外圈的锯齿由门框、角焊盖住（门洞挖得比门框内沿大一圈，锯齿才藏得住）。"""
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
    K.separate("Int_BulkheadAft", "HullInner", lambda bm: plate(bm, y - t_plate, back=True), recalc=False)
    bm = K["HullInner"]
    # 隔壁和壳体的连接处一圈角焊（两面）
    ring_sweep(bm, [(R_IN + 0.01, 0.0), (R_IN - 0.035, 0.0), (R_IN + 0.01, 0.045)][::-1], y, -140, 140, 180)
    ring_sweep(bm, [(R_IN + 0.01, 0.0), (R_IN - 0.035, 0.0), (R_IN + 0.01, -0.045)], y - t_plate, -140, 140, 180)
    # 加强筋：两面各一横两竖
    zt = 0.95
    xt = math.sqrt(R_IN ** 2 - zt ** 2) + 0.01
    for sgn, y0 in ((1, y), (-1, y - t_plate)):
        rbox(bm, 2 * xt, 0.11, 0.02, T(0, y0 + sgn * 0.055, zt), r=0.0, seg=1)
        rbox(bm, 2 * xt, 0.02, 0.08, T(0, y0 + sgn * 0.11, zt), r=0.004, seg=2)
        for xs in (-0.62, 0.62):
            rbox(bm, 0.02, 0.11, zt - DECK, T(xs, y0 + sgn * 0.055, (zt + DECK) / 2))
            rbox(bm, 0.08, 0.02, zt - DECK - 0.01, T(xs, y0 + sgn * 0.11, (zt + DECK) / 2 - 0.005), r=0.004, seg=2)

    # 门框（围板）：穿过隔壁，两面各凸出一截
    path = [V((dx + math.cos(t) * (da + 0.045), y + 0.005, dz + math.sin(t) * (db + 0.045)))
            for t in [2 * math.pi * k / 96 for k in range(96)]]
    sweep(K["HullInner"], path, rect_profile(0.09, 0.13, 0.012), closed=True, up_hint=V((0, 1, 0)))
    # 压紧块（门扇上的把手压在这上面）
    for deg in DOOR_DOGS:
        t = math.radians(deg)
        px, pz = dx + math.cos(t) * (da + 0.105), dz + math.sin(t) * (db + 0.105)
        rbox(K["Steel"], 0.05, 0.075, 0.035, T(px, y + 0.105, pz) @ R(-deg, 'Y'), r=0.004, seg=1)
    # 铰链座：门轴竖着，上下两个铰链
    hx, hy = DOOR_HINGE
    for zz in (-0.35, 0.35):
        for dz_ in (-0.105, 0.035):
            cylinder(K["Steel"], 0.024, 0.07, 16, T(hx, hy, dz + zz + dz_))
        rbox(K["Steel"], 0.05, hy - y, 0.15, T(hx - 0.02, (y + hy) / 2, dz + zz), r=0.004, seg=1)
        cylinder(K["Steel"], 0.009, 0.23, 12, T(hx, hy, dz + zz - 0.115))
    anchors.append(empty("Door_Hinge", K.coll, anchor_frame(V((hx, hy, dz)), V((0, 1, 0)))))

    # ---- 门扇（Door_Leaf_*）：椭圆厚板 + 两面各两道加强 + 压紧把手 + 铰链臂；手轮（Door_Wheel_*）两面各一个
    D = Parts(K.coll, K.M, "Door_Leaf")
    W = Parts(K.coll, K.M, "Door_Wheel")
    door_y = y + 0.07
    Md = T(dx, door_y, dz) @ R(-90, 'X')
    cylinder(D["Console"], 1.0, 0.05, 64, Md @ S(da + 0.065, db + 0.065, 1))
    lathe(D["Rubber"], [(1.0, 0.0), (1.0, 0.004)], 64, Md @ S(da + 0.066, db + 0.066, 1))
    torus(D["Rubber"], 1.0, 0.006, 64, 6, Md @ S(da + 0.03, db + 0.03, 1) @ T(0, 0, -0.002))
    for face_y, sgn in ((door_y + 0.05, 1), (door_y, -1)):
        for zz in (-0.25, 0.25):
            w = 2 * da * math.sqrt(max(0.0, 1 - (zz / db) ** 2))
            rbox(D["EquipGray"], w, 0.03, 0.04, T(dx, face_y + sgn * 0.015, dz + zz), r=0.006, seg=2)
    for deg in DOOR_DOGS:
        t = math.radians(deg)
        px, pz = dx + math.cos(t) * (da + 0.03), dz + math.sin(t) * (db + 0.03)
        Mp = T(px, door_y + 0.05, pz) @ R(-90, 'X')
        cylinder(D["Steel"], 0.018, 0.03, 16, Mp)
        Ml = Mp @ T(0, 0, 0.035) @ R(-deg, 'Z')
        rbox(D["Steel"], 0.12, 0.024, 0.018, Ml @ T(0.045, 0, 0), r=0.006, seg=2)
        uvsphere(D["Steel"], 0.014, 12, 8, Ml @ T(0.1, 0, 0))
    # 铰链臂：从门轴伸到门扇正面
    for zz in (-0.35, 0.35):
        ex = dx - (da + 0.065) * math.sqrt(max(0.0, 1 - (zz / (db + 0.065)) ** 2))
        rbox(D["Steel"], ex - hx + 0.08, 0.03, 0.06, T((hx + ex + 0.08) / 2, hy, dz + zz), r=0.004, seg=1)
        cylinder(D["Steel"], 0.026, 0.066, 16, T(hx, hy, dz + zz - 0.033))
    # 门扇两面刷的字
    for yy, n in ((door_y + 0.0502, V((0, 1, 0))), (door_y - 0.0002, V((0, -1, 0)))):
        text_mesh("随手关门", D.uid("Door_Leaf_Txt"), K.coll, K.M["InkRed"], frame(V((dx, yy, dz - 0.45)), n),
                  size=0.04, extrude=0.0, font_path=FONT_SERIF, resolution=2)
    # 手轮：阀杆穿过门扇，两面各一个，一起转
    valve_wheel(W, T(dx, door_y + 0.05, dz) @ R(-90, 'X'), 0.13, "BtnRed", 4)
    valve_wheel(W, T(dx, door_y, dz) @ R(90, 'X'), 0.11, "BtnRed", 4)
    anchors.append(empty("Door_WheelAxis", K.coll, anchor_frame(V((dx, door_y + 0.025, dz)), V((0, 1, 0)))))
    D.flush()
    W.flush()

    # ---- 控制舱一侧：门上方的铭牌和刷漆字、灯、氧气瓶、接线盒
    P = frame(V((dx, y + 0.1215, zt + 0.02)), V((0, 1, 0)))  # 铭牌钉在加强筋的翼板上
    label_plate(K, P, 0, 0, "2号水密门  通生活舱", 0.014)
    K.text("水密门 随手关闭", frame(V((dx, y + 0.001, DECK + 0.1)), V((0, 1, 0))), 0.035, key="InkRed")
    K.text("当心碰头", frame(V((0.0, y + 0.1205, zt - 0.022)), V((0, 1, 0))), 0.026, key="Ink")
    ceiling_lamp(K, anchors, T(0.85, y, 0.42) @ R(-90, 'X'), "CabinLight_Aft")
    # 两个氧气瓶 + 绑带 + 减压阀和压力表
    for i, x in enumerate((0.76, 0.92)):
        base = V((x, y + 0.1, DECK))
        lathe(K["O2"], [(0.0, 0.0), (0.065, 0.0), (0.075, 0.015), (0.075, 0.62), (0.065, 0.67), (0.03, 0.7),
                        (0.022, 0.72), (0.0, 0.72)], 48, T(*base))
        cylinder(K["Brass"], 0.018, 0.06, 16, T(*base) @ T(0, 0, 0.72))
        K.text("氧", frame(base + V((0, 0.076, 0.4)), V((0, 1, 0))), 0.07, key="Ink")
        for z in (0.2, 0.55):
            torus(K["Rail"], 0.078, 0.006, 48, 6, T(x, y + 0.1, DECK + z) @ S(1, 1, 3))
    rbox(K["Rail"], 0.3, 0.02, 0.6, T(0.84, y + 0.012, DECK + 0.35), r=0.003, seg=1)
    Mr = T(0.76, y + 0.1, DECK + 0.78)
    rbox(K["Brass"], 0.05, 0.04, 0.05, Mr @ T(0, 0, 0.04), r=0.004, seg=2)
    Pg = frame(V((0.76, y + 0.125, DECK + 0.82)), V((0, 1, 0)))
    gauge_round(K, Pg, 0, 0, 0.026, "O2Tank", hi=25, label="MPa", major=5, flange=False, red_from=None)
    Cab.add([V((0.785, y + 0.1, DECK + 0.82)), V((0.84, y + 0.15, DECK + 0.9)), V((1.0, y + 0.3, 0.3)),
             V((1.34, -2.0, 0.2))], 0.007, "CableBlack")
    # 接线盒
    P = frame(V((-1.0, y, 0.35)), V((0, 1, 0)))
    junction_box(K, P)
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
    ya = y - t_plate
    P = frame(V((dx, ya - 0.1215, zt + 0.02)), V((0, -1, 0)))
    label_plate(K, P, 0, 0, "2号水密门  通控制舱", 0.014)
    K.text("当心碰头", frame(V((0.0, ya - 0.1205, zt - 0.022)), V((0, -1, 0))), 0.026, key="InkRed")
    K.text("水密门 随手关闭", frame(V((dx, ya - 0.001, DECK + 0.1)), V((0, -1, 0))), 0.035, key="InkRed")


def junction_box(K, P, w=0.2, h=0.16, d=0.1):
    unit(K, P @ T(0, 0, d), w, h, d, body="EquipGray", face="EquipGray", handles=False)
    F = P @ T(0, 0, d)
    label_plate(K, F, 0, 0.055, "接线盒", 0.0075)
    tri = [(math.cos(math.radians(90 + 120 * k)) * 0.03, math.sin(math.radians(90 + 120 * k)) * 0.03 - 0.005)
           for k in range(3)]
    extrude_profile(K["Ink"], tri, F, 0.0004)
    extrude_profile(K["BtnYellow"], [(x * 0.8, y * 0.8 - 0.0008) for x, y in tri], F, 0.0007)
    K.text("当心触电", F @ T(0, -0.045, 0.0003), 0.009, key="Ink")
    Pb = F @ T(0, -h / 2, -d / 2) @ R(90, 'X')
    for k in range(3):
        x = -w / 2 + w * (k + 0.5) / 3
        start, nz, _ = connector(K, Pb, x, 0.0, r=0.008, plug="Olive" if k % 2 else "Steel")
        Cab.add([start, start + nz * 0.05, start + nz * 0.25 + V((-0.05 * (k + 1), 0.1, 0)),
                 V((-1.29, -2.25 + 0.04 * k, -0.45))], 0.005, ["CableBlack", "CableGray", "CableOrange"][k])


# ============================================================================ 头顶：管路、桥架、灯
PIPES = [  # x, z, 半径, 材质（中间留出 50 厘米给直梯和舱口）
    (-0.3, 1.02, 0.06, "Lagging"),      # 通风管（外包帆布保温层）
    (-0.43, 0.97, 0.026, "PipeBlue"),   # 冷却水
    (-0.51, 0.91, 0.026, "PipeRed"),    # 消防水
    (0.3, 1.06, 0.026, "PipeBlue"),     # 冷却水回水
    (0.38, 1.02, 0.016, "Copper"),      # 高压空气
]


def overhead(K, anchors):
    y0, y1 = Y_AFT, 1.5
    for x, z, r, key in PIPES:
        bm = K[key]
        path = [V((x, y0, z)), V((x, y1 - 0.15, z))]
        # 末端一个弯头穿进壳体
        bend = [V((x, y1 - 0.15 + 0.15 * math.sin(math.radians(a)), z + 0.15 * (1 - math.cos(math.radians(a)))))
                for a in range(0, 91, 10)]
        top = math.sqrt(R_IN ** 2 - x * x) + 0.05
        sweep(bm, path[:-1] + bend + [V((x, y1, top))], circle_profile(r, 24 if r > 0.03 else 16))
        # 包了保温层的管子：法兰露出铁皮，每隔一段一道钢带扎紧
        fbm = K["PipeGray"] if key == "Lagging" else bm
        if key == "Lagging":
            for yb in [Y_AFT + 0.25 + k * 0.4 for k in range(10)]:
                if yb < y1 - 0.2 and all(abs(yb - yf) > 0.08 for yf in (-1.4, -0.2, 0.95)):
                    cylinder(K["Steel"], r + 0.002, 0.016, 32, T(x, yb, z) @ R(-90, 'X'), caps=False)
        # 法兰（每隔两个肋骨一对）+ 螺栓
        for yf in (-1.4, -0.2, 0.95):
            for k in (-1, 1):
                cylinder(fbm, r + 0.022, 0.014, 32, T(x, yf + k * 0.007, z) @ R(-90, 'X') @ T(0, 0, -0.007))
            for i in range(6):
                a = 2 * math.pi * (i + 0.5) / 6
                cylinder(K["Steel"], 0.0055, 0.04, 6, T(x + math.cos(a) * (r + 0.013), yf - 0.02,
                                                          z + math.sin(a) * (r + 0.013)) @ R(-90, 'X'))
        # 吊架：每道肋骨一个，扁钢吊带抱住管子，螺杆吊到肋骨翼板上
        for yf in FRAMES:
            if yf > y1 - 0.2:
                continue
            # 吊到肋骨翼板上；肋骨在舱口处断开的地方吊到舱口围板底面
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
    for yv in (-1.4, -0.2, 0.95):
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

    # 电缆桥架（梯形桥架 + 里面的线束）
    for s in (-1, 1):
        a = math.radians(38 * s)
        rc = 1.13
        cx, cz = math.sin(a) * rc, math.cos(a) * rc
        tang = V((math.cos(a), 0, -math.sin(a)))    # 沿壳体切向
        nrm = V((math.sin(a), 0, math.cos(a)))      # 朝外（朝壳体）
        for side in (-1, 1):
            c = V((cx, 0, cz)) + tang * side * 0.08
            prof = [(-0.025, -0.003), (0.025, -0.003), (0.025, 0.003), (-0.025, 0.003)]
            sweep(K["Rail"], [V((c.x, Y_AFT, c.z)), V((c.x, 1.33, c.z))],
                  [(p[0], p[1]) for p in prof], up_hint=tang)
        for yy in [Y_AFT + 0.1 + k * 0.25 for k in range(16)]:
            if yy > 1.3:
                break
            p = V((cx, yy, cz)) - nrm * 0.02
            box(K["Rail"], 0.16, 0.02, 0.006, frame(p, nrm, V((0, 1, 0))))
        # 吊杆到肋骨
        for yf in FRAMES:
            p = V((cx, yf + 0.03, cz))
            q = nrm * 1.19
            sweep(K["Steel"], [p, V((q.x, yf + 0.03, q.z))], circle_profile(0.005, 8))
        specs = [(0.009, "CableBlack"), (0.007, "CableGray"), (0.008, "CableBlack"), (0.005, "CableOrange"),
                 (0.006, "CableBlack"), (0.005, "CableYellow"), (0.007, "CableGray"), (0.0045, "CableBlue"),
                 (0.006, "CableBlack")]
        base = nrm * 1.145
        Cab.bundle([V((base.x + 0.004 * math.sin(k), Y_AFT + k * 0.3, base.z)) for k in range(14)
                    if Y_AFT + k * 0.3 < 1.35], specs, tie_every=0.4)
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
    # 穿舱件：线从壳体外面引进来，落到桥架里
    for s, y in ((-1, 0.4), (1, 0.4), (1, -1.4)):
        a = math.radians(22 * s)
        d = V((math.sin(a), 0, math.cos(a)))
        F = frame(V((d.x * (R_IN - 0.004), y, d.z * (R_IN - 0.004))), -d)
        cylinder(K["EquipGray"], 0.1, 0.02, 48, F)
        for i in range(10):
            b = 2 * math.pi * i / 10
            cylinder(K["Steel"], 0.008, 0.009, 6, F @ T(math.cos(b) * 0.085, math.sin(b) * 0.085, 0.02))
        P = F @ T(0, 0, 0.02)
        keys = ["CableBlack", "CableGray", "CableOrange", "CableBlack", "CableBlue"]
        for k in range(5):
            ang = 2 * math.pi * k / 5
            start, nz, _ = connector(K, P, math.cos(ang) * 0.045, math.sin(ang) * 0.045, r=0.009,
                                     plug="Olive" if k % 2 else "Steel")
            ta = math.radians(38 * s)
            end = V((math.sin(ta) * 1.12, y + (k - 2) * 0.05 + 0.15, math.cos(ta) * 1.12))
            Cab.add([start, start + nz * 0.05, (start + end) / 2 - V((0, 0, 0.05)), end], 0.0055, keys[k])


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
    # ---- 中间隔壁：舱段号、严禁烟火、门框压紧块底下的锈水、门边一个手印
    d("TextC03", (-1.0, Y_AFT, 0.6), Z, UP, 0.26, 0.104, 0.05)
    d("TextFire", (0.5, Y_AFT, 0.12), Z, UP, 0.075, 0.3, 0.05)
    for x, z in ((0.43, 0.47), (0.43, -0.37), (0.06, 0.84)):
        d("Rust", (x, Y_AFT + 0.03, z - 0.17), Z, UP, 0.06, 0.28, 0.1)
    d("Rust", (-1.0, Y_AFT + 0.02, 0.1), Z, UP, 0.12, 0.32, 0.06)
    d("Hand", (-0.52, Y_AFT + 0.01, 0.22), Z, V((-0.2, 0, 0.98)), 0.12, 0.22, 0.04)
    # ---- 壳体：穿舱件下面的锈水
    for s, y in ((-1, 0.4), (1, 0.4), (1, -1.4)):
        a = math.radians(31)
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
    # ---- 舷窗：窗下的冷凝水顺着压环往下淌，滴到肘托上
    for s in (-1, 1):
        o, dd = vp_axis(s)
        F = frame(o, dd)
        d("Streak", F @ V((0, -0.2, 1.19)), -dd, F.to_3x3() @ V((0, 1, 0)), 0.07, 0.12, 0.05)
        d("Puddle", (s * 1.03, VP_Y, DESK_Z + 0.04), UP, Z, 0.2, 0.16, 0.03)
    # ---- 管子上刷的介质和流向
    for x, z, r, y, kind in ((-0.43, 0.97, 0.026, -0.75, "TextCool"), (-0.43, 0.97, 0.026, 0.62, "TextCool"),
                             (-0.51, 0.91, 0.026, -1.0, "TextFireWater"), (-0.51, 0.91, 0.026, 0.25, "TextFireWater"),
                             (0.3, 1.06, 0.026, -0.9, "TextReturn"), (-0.3, 1.02, 0.065, -0.6, "TextAir")):
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
