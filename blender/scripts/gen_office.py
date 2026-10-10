"""第一章「契」：渔业公司老楼三楼，东溟海洋工程有限公司的临时办事处（剧情见 docs/story.md）。导出 assets/models/office.glb。

一间五十年代办公楼的大办公室，5 × 6 米，3.3 米高，1998 年 8 月 29 日下午三点，阴雨：
- 水磨石地面（铜条分格），墙下半截木墙裙、上半截白灰墙；两盏吊链日光灯（一盏不亮），中间一台吊扇慢慢转
- 北墙一整面钢窗，正对码头：雨里能看见镇海号靠在码头上，后面是母船的 A 字吊架；远处防波堤、灯塔、山
- 沈渡坐在一张红木官帽椅里（和公家办公室格格不入），面前一张老式写字台：玻璃台面底下压着海图、老照片；
  桌上两份合同、印泥、钢笔墨水、两碗盖碗茶（他那碗一口没动）、拨盘电话、罗盘、绿罩台灯
- 西墙：一排玻璃门的书柜，西北角一扇屏风，屏风后面是供桌（香炉、蜡烛、蒙红布的牌位、发黑的供果）
- 东墙：大海图（归墟用红笔圈着）、一排卡片抽屉柜、拓片、民国老照片；东北角保险柜；北墙两边一幅「海不扬波」的条幅、一台摆钟
- 南墙：门（门边衣帽架上挂着黑伞，伞尖底下一滩水），东南角一张茶几两个方凳

用法：Blender -b --factory-startup --python blender/scripts/gen_office.py [-- --preview DIR] [--no-export]
"""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(__file__))
import bpy  # noqa: E402
import bmesh  # noqa: E402
from mathutils import Vector as V, Matrix  # noqa: E402

from lib import (reset_scene, collection, frame, T, R, S, cylinder, box, uvsphere, lathe, torus, catmull,  # noqa: E402
                 circle_profile, rect_profile, sweep, empty, text_mesh, render_preview, material)
from kit import Parts, rbox, extrude_profile, FONT_SANS, FONT_SERIF, FONT_HAND, FONT_BRUSH  # noqa: E402
import room_kit as RK  # noqa: E402
from room_kit import Room, anchor, light, use, seat, walk, spawn, decal  # noqa: E402

ROOT = RK.ROOT
OUT = os.path.join(ROOT, "assets", "models", "office.glb")

# ---------------------------------------------------------------------------- 主尺寸（改了要同步 scripts/story/office.gd）
X0, X1, Y0, Y1, H = -2.5, 2.5, -3.0, 3.0, 3.3
WT = 0.3
WIN = (-1.65, 1.65, 0.85, 2.85)        # 北墙钢窗：x 范围、下沿、上沿
DOOR = (-2.05, -1.15, 2.1)             # 南墙门：x 范围、高
DADO = 1.1                             # 木墙裙高
DESK = (0.3, 1.25, 1.6, 0.85)          # 写字台中心 x、y，宽、深
DESK_Z = 0.765                         # 桌面（含玻璃板）高度
SHEN = (0.3, 1.9)                      # 沈渡：臀部正下方的地面点，面朝南（坐姿下手在臀部前 0.35 米、0.76 米高，见 npc_shen.json）
SHEN_LIFT = 0.03                       # 官帽椅座面高，人抬高一点
CHAIR_SCALE = 0.78                     # 官帽椅（Poly Haven chinese_armchair 座面 0.65 米，太高）
VISITOR = (0.3, 0.3)                   # 来客椅
GROUND = -8.6                          # 楼下码头水面（三楼）
PIER_Z = -7.6                          # 码头面


def materials(M):
    RK.materials(M)

    def add(key, name, color, metal=0.0, rough=0.6, emission=None, strength=1.0, alpha=1.0):
        if key not in M:
            M[key] = material(name, color, metal, rough, emission, strength, alpha)
    add("WoodRed", "M_WoodRed", (0.35, 0.15, 0.08), 0.0, 0.3)
    add("Brass", "M_Brass", (0.72, 0.52, 0.22), 1.0, 0.35)
    add("GreenGlass", "M_LampGreen", (0.05, 0.25, 0.12), 0.0, 0.15)
    add("SafeGreen", "M_SafeGreen", (0.15, 0.22, 0.17), 0.3, 0.45)
    add("InkPad", "M_InkPaste", (0.5, 0.03, 0.02), 0.0, 0.7)
    add("Leather", "M_Vinyl", (0.06, 0.045, 0.04), 0.0, 0.45)
    add("Concrete", "M_Concrete", (0.45, 0.45, 0.43), 0.0, 0.85)
    add("Water", "M_HarborWater", (0.05, 0.07, 0.07), 0.0, 0.1)
    add("ShipHull", "M_ShipHull", (0.15, 0.15, 0.15), 0.3, 0.6)
    add("ShipWhite", "M_ShipWhite", (0.6, 0.6, 0.58), 0.1, 0.6)
    add("CraneRust", "M_CraneRust", (0.2, 0.12, 0.08), 0.5, 0.7)
    add("Hill", "M_Hill", (0.1, 0.12, 0.1), 0.0, 0.9)
    add("Tarp", "M_Tarp", (0.15, 0.22, 0.18), 0.0, 0.8)
    add("Tire", "M_Rubber", (0.02, 0.02, 0.02), 0.0, 0.8)
    add("NavLight", "M_NavLight", (1.0, 0.2, 0.1), 0.0, 0.3, emission=(1.0, 0.15, 0.08), strength=6)
    add("Silk", "M_Silk", (0.85, 0.84, 0.78), 0.0, 0.6)
    add("ScrollPaper", "M_ScrollPaper", (0.85, 0.82, 0.72), 0.0, 0.9)
    add("Fruit", "M_RottenFruit", (0.3, 0.2, 0.08), 0.0, 0.6)
    add("Bottle", "M_Bottle", (0.3, 0.2, 0.1), 0.0, 0.25)
    add("Plastic", "M_PlasticRed", (0.6, 0.08, 0.06), 0.0, 0.4)
    return M


def abox(bm, x0, x1, y0, y1, z0, z1, r=0.0, seg=2):
    rbox(bm, abs(x1 - x0), abs(y1 - y0), abs(z1 - z0), T((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2), r=r, seg=seg)


# ============================================================================ 壳子
def shell(S_, A, coll):
    room = Room(S_, A, X0, X1, Y0, Y1, H, WT)
    room.opening("N", WIN[0] - X0, WIN[1] - X0, WIN[2], WIN[3], sill="Terrazzo")
    room.opening("S", X1 - DOOR[1], X1 - DOOR[0], 0.0, DOOR[2], outer=False)
    # 门上方的玻璃亮子
    room.opening("S", X1 - DOOR[1] - 0.06, X1 - DOOR[0] + 0.06, DOOR[2] + 0.05, DOOR[2] + 0.45, outer=False)
    room.walls(upper="Plaster", dado="Wainscot", dado_h=DADO, line="WoodDark", skirt="WoodDark", skirt_h=0.12)
    room.floor("Terrazzo")
    room.ceiling("Ceiling")
    # 门外：一小段走廊（开着门时看得见），暗的
    abox(S_["Terrazzo"], DOOR[0] - 0.6, DOOR[1] + 0.6, Y0 - WT - 1.6, Y0 - WT, -0.02, 0.0)
    abox(S_["Plaster"], DOOR[0] - 0.6, DOOR[1] + 0.6, Y0 - WT - 1.62, Y0 - WT - 1.6, 0.0, H)
    abox(S_["Ceiling"], DOOR[0] - 0.6, DOOR[1] + 0.6, Y0 - WT - 1.6, Y0 - WT, H, H + 0.02)
    for x in (DOOR[0] - 0.6, DOOR[1] + 0.6):
        abox(S_["Plaster"], x - 0.01, x + 0.01, Y0 - WT - 1.6, Y0 - WT, 0.0, H)
    return room


def floor_strips(K):
    """水磨石地面的铜分格条：每 1 米一道，嵌在地里只露一条细线。"""
    for k in range(1, 5):
        x = X0 + k
        abox(K["Brass"], x - 0.0015, x + 0.0015, Y0 + 0.01, Y1 - 0.01, -0.002, 0.0006)
    for k in range(1, 6):
        y = Y0 + k
        abox(K["Brass"], X0 + 0.01, X1 - 0.01, y - 0.0015, y + 0.0015, -0.002, 0.0006)


def wainscot_panels(K, room):
    """木墙裙：一块块凸起的板（压条框起来），上沿一道压顶线（Room.walls 的 line 画了），遇到门窗断开。"""
    for side in Room.SIDES:
        o, du, n, L = room.wall(side)
        spans = room._spans(side, L, 0.15, DADO - 0.05)
        for a, b in spans:
            k = max(1, int((b - a) / 0.6))
            w = (b - a) / k
            for i in range(k):
                c = a + w * (i + 0.5)
                F = frame(o + du * c + V((0, 0, (0.15 + DADO) / 2)) + n * 0.006, n, V((0, 0, 1)))
                rbox(K["Wainscot"], w - 0.08, DADO - 0.33, 0.012, F, r=0.004, seg=2)
                for (cx, cy, sx, sy) in ((0, (DADO - 0.33) / 2, w - 0.06, 0.02), (0, -(DADO - 0.33) / 2, w - 0.06, 0.02),
                                         (-(w - 0.06) / 2, 0, 0.02, DADO - 0.31), ((w - 0.06) / 2, 0, 0.02, DADO - 0.31)):
                    rbox(K["WoodDark"], sx, sy, 0.02, F @ T(cx, cy, 0.004), r=0.004, seg=2)


# ============================================================================ 门、窗
def door(K, A, coll, room):
    uc = X1 - (DOOR[0] + DOOR[1]) / 2
    F = room.frame("S", uc, 0.0)
    w = DOOR[1] - DOOR[0]
    leaf, hw = RK.wood_door(K, F, w, DOOR[2], leaf="WoodDark", jamb="WoodDark", hinge_right=True, name="Door_Leaf",
                            bolt=False)
    # 门上方一块玻璃亮子
    Ft = room.frame("S", uc, DOOR[2] + 0.25, -WT * 0.5)
    rbox(K["WoodDark"], w + 0.12, 0.05, 0.06, Ft @ T(0, -0.2, 0), r=0.004, seg=1)
    rbox(K["WoodDark"], w + 0.12, 0.05, 0.06, Ft @ T(0, 0.2, 0), r=0.004, seg=1)
    box(K["WinGlass"], w + 0.1, 0.35, 0.004, Ft)
    # 门边：开关、衣帽架（挂着沈渡的黑伞、一件深色风衣）
    RK.toggle_switch(K, room.frame("S", uc + w / 2 + 0.2, 1.4))
    coat_rack(K, T(DOOR[1] + 0.45, Y0 + 0.35, 0.0))
    use(A, coll, "Umbrella", (DOOR[1] + 0.45, Y0 + 0.35, 1.0))
    use(A, coll, "Door", ((DOOR[0] + DOOR[1]) / 2, Y0 + 0.05, 1.05))
    return leaf


def coat_rack(K, M):
    """落地衣帽架（弯木的）：一根立柱、四只脚、顶上一圈挂钩；挂一把湿黑伞、一件深色风衣。"""
    sweep(K["WoodDark"], [M @ V((0, 0, 0.05)), M @ V((0, 0, 1.78))], circle_profile(0.022, 14))
    for k in range(4):
        a = math.radians(45 + 90 * k)
        sweep(K["WoodDark"], catmull([M @ V((0, 0, 0.25)), M @ V((math.cos(a) * 0.15, math.sin(a) * 0.15, 0.1)),
                                      M @ V((math.cos(a) * 0.27, math.sin(a) * 0.27, 0.01))], 6), circle_profile(0.016, 10))
    for k in range(6):
        a = math.radians(60 * k)
        sweep(K["WoodDark"], catmull([M @ V((0, 0, 1.68)), M @ V((math.cos(a) * 0.12, math.sin(a) * 0.12, 1.66)),
                                      M @ V((math.cos(a) * 0.17, math.sin(a) * 0.17, 1.74))], 6), circle_profile(0.011, 8))
    uvsphere(K["WoodDark"], 0.035, 14, 8, M @ T(0, 0, 1.8))
    # 黑伞：伞把挂在一只钩子上，伞身垂下来
    a = math.radians(60)
    hook = M @ V((math.cos(a) * 0.16, math.sin(a) * 0.16, 1.72))
    sweep(K["Leather"], catmull([hook, hook + V((0.03, 0.0, -0.03)), hook + V((0.0, 0.0, -0.08))], 6),
          circle_profile(0.008, 10))
    lathe(K["Dark"], [(0.0, -0.08), (0.012, -0.11), (0.042, -0.3), (0.046, -0.55), (0.03, -0.85), (0.006, -0.98),
                      (0.0, -1.0)], 14, T(*hook) @ S(1, 0.8, 1))
    # 风衣：一块垂着的厚布（另一只钩子上），下摆有褶
    a2 = math.radians(240)
    top = M @ V((math.cos(a2) * 0.16, math.sin(a2) * 0.16, 1.72))
    rows = []
    for j in range(16):
        v = j / 15
        z = -1.05 * v
        w = 0.08 + 0.18 * min(1.0, v * 3)
        row = []
        for i in range(13):
            u = i / 12 - 0.5
            fold = 0.025 * math.sin(u * 14 + v * 2) * v
            row.append(top + V((u * w * 2 * math.cos(a2 + 1.57), u * w * 2 * math.sin(a2 + 1.57), z))
                       + V((math.cos(a2), math.sin(a2), 0)) * (0.04 * math.sin(math.pi * (u + 0.5)) + fold))
        rows.append(row)
    from cockpit import cloth
    cloth(K["Jacket"] if "Jacket" in K.M else K["Dark"], rows, 0.006)


def window(K, A, coll, room):
    uc = (WIN[0] + WIN[1]) / 2 - X0
    vc = (WIN[2] + WIN[3]) / 2
    w, h = WIN[1] - WIN[0], WIN[3] - WIN[2]
    F = room.frame("N", uc, vc, -WT * 0.6)
    RK.steel_window(K, F, w - 0.01, h - 0.01, cols=6, rows=4, open_cells=((1, 3, 18),), name="Window",
                    cracked=((4, 1),))
    use(A, coll, "Window", (0.9, Y1 - 0.15, 1.7))


# ============================================================================ 写字台
def desk(K, A, coll):
    cx, cy, w, d = DESK
    z = DESK_Z
    glass_t = 0.008
    zt = z - glass_t
    # 桌面：厚木板，前沿一道线脚；上面一块玻璃板（四边磨了斜边）
    rbox(K["WoodRed"], w, d, 0.035, T(cx, cy, zt - 0.0175), r=0.008, seg=3)
    box(K["Glass"], w - 0.04, d - 0.04, glass_t, T(cx, cy, zt + glass_t / 2))
    # 两个抽屉柜（座子），中间留出放腿的地方；朝来客那面（南）一块挡板
    ped_w = 0.42
    for sx in (-1, 1):
        px = cx + sx * (w / 2 - ped_w / 2 - 0.01)
        rbox(K["WoodRed"], ped_w, d - 0.04, zt - 0.06, T(px, cy, (zt - 0.06) / 2 + 0.04), r=0.006, seg=2)
        rbox(K["WoodDark"], ped_w - 0.02, d - 0.06, 0.04, T(px, cy, 0.02), r=0.004, seg=1)   # 底座
        # 沈渡那面（北）三个抽屉
        for k in range(3):
            hz = 0.16 + k * 0.19
            F = frame(V((px, cy + d / 2 - 0.02, hz)), V((0, 1, 0)))
            rbox(K["WoodRed"], ped_w - 0.04, 0.16, 0.012, F @ T(0, 0, 0.006), r=0.003, seg=2)
            rbox(K["Brass"], 0.08, 0.012, 0.012, F @ T(0, 0.02, 0.016), r=0.004, seg=2)
            cylinder(K["Brass"], 0.007, 0.004, 12, F @ T(0, 0.055, 0.012))   # 锁眼
    # 中间的抽屉（桌面下面一长条）、挡板
    rbox(K["WoodRed"], w - 2 * ped_w - 0.02, d - 0.04, 0.1, T(cx, cy, zt - 0.035 - 0.05), r=0.004, seg=2)
    rbox(K["WoodRed"], w - 2 * ped_w - 0.02, 0.02, zt - 0.2, T(cx, cy - d / 2 + 0.04, (zt - 0.2) / 2 + 0.12), r=0.004,
         seg=2)
    # 玻璃板底下压着的东西：一张海图（归墟附近）、一张老照片、一张名片、一张船票
    RK.paper_quad(K, "DeskChart", T(cx - 0.35, cy + 0.12, zt + 0.0004) @ R(4, 'Z') @ R(180, 'Z'), 0.42, 0.3)
    RK.paper_quad(K, "DeskPhoto", T(cx + 0.55, cy + 0.2, zt + 0.0004) @ R(-8, 'Z') @ R(180, 'Z'), 0.12, 0.085)
    RK.paper_quad(K, "Card", T(cx + 0.42, cy - 0.22, zt + 0.0004) @ R(3, 'Z'), 0.09, 0.054)
    use(A, coll, "DeskGlass", (cx - 0.35, cy + 0.12, z + 0.01))
    # 合同：两页，摊在来客这边（字朝来客）
    RK.paper_quad(K, "Contract1", T(cx - 0.02, cy - 0.2, z + 0.0006) @ R(-3, 'Z'), 0.21, 0.297)
    RK.paper_quad(K, "Contract2", T(cx + 0.22, cy - 0.18, z + 0.0004) @ R(6, 'Z'), 0.21, 0.297)
    use(A, coll, "Contract", (cx + 0.05, cy - 0.2, z + 0.01))
    # 印泥（圆铁盒，盖子掀开放在边上）、钢笔、墨水瓶
    inkpad(K, T(cx - 0.3, cy - 0.28, z))
    use(A, coll, "InkPad", (cx - 0.3, cy - 0.28, z + 0.02))
    pen(K, T(cx + 0.12, cy - 0.35, z + 0.006) @ R(70, 'Z'))
    lathe(K["Glass"], [(0.0, 0.0), (0.028, 0.0), (0.03, 0.05), (0.014, 0.065), (0.014, 0.075), (0.0, 0.075)], 24,
          T(cx - 0.12, cy + 0.15, z))
    cylinder(K["Ink"], 0.026, 0.035, 20, T(cx - 0.12, cy + 0.15, z + 0.002))
    cylinder(K["Bakelite"], 0.016, 0.02, 20, T(cx - 0.12, cy + 0.15, z + 0.075))
    # 两碗盖碗茶：来客这碗冒着热气；沈渡那碗一口没动，没有热气
    RK.gaiwan(K, T(cx - 0.5, cy - 0.25, z), tea=0.75)
    RK.gaiwan(K, T(cx + 0.35, cy + 0.25, z), tea=0.9)
    use(A, coll, "TeaMine", (cx - 0.5, cy - 0.25, z + 0.06))
    use(A, coll, "TeaShen", (cx + 0.35, cy + 0.25, z + 0.06))
    light(A, coll, "Light_Steam", (cx - 0.5, cy - 0.25, z + 0.07), (0, 0, 1))
    # 拨盘电话、罗盘、绿罩台灯、一叠卷宗
    phone(K, T(cx + 0.62, cy + 0.12, z) @ R(-160, 'Z'))
    use(A, coll, "Phone", (cx + 0.62, cy + 0.12, z + 0.06))
    luopan(K, T(cx - 0.62, cy + 0.2, z) @ R(18, 'Z'))
    use(A, coll, "Luopan", (cx - 0.62, cy + 0.2, z + 0.03))
    banker_lamp(K, A, coll, T(cx + 0.55, cy + 0.32, z) @ R(170, 'Z'))
    for k in range(4):
        rbox(K["Cardboard"], 0.24, 0.32, 0.012, T(cx - 0.62, cy - 0.15, z + 0.006 + 0.013 * k) @ R(5 * k - 4, 'Z'),
             r=0.002, seg=1)
    # 平安符：红布小袋，签完合同以后沈渡推过来（Hide_Talisman，Godot 里先藏着）
    def talisman(bm):
        rbox(bm, 0.045, 0.012, 0.06, T(0, 0, 0.006) @ R(90, 'X') @ R(0, 'Y'), r=0.005, seg=2)
        sweep(bm, catmull([V((0, 0.03, 0.006)), V((0.03, 0.06, 0.004)), V((0.0, 0.1, 0.003))], 6),
              circle_profile(0.0015, 6))
    tl = K.separate("Hide_Talisman", "ClothRed", talisman)
    tl.matrix_world = T(cx + 0.1, cy + 0.05, z)
    anchor(A, coll, "Anchor_Shen", (SHEN[0], SHEN[1], SHEN_LIFT), (0, -1, 0))
    anchor(A, coll, "Anchor_ShenChair", (SHEN[0], SHEN[1] + 0.06, 0.0), (0, -1, 0))
    use(A, coll, "Shen", (SHEN[0], SHEN[1] - 0.15, 1.15))
    # 来客椅
    visitor_chair(K, T(VISITOR[0], VISITOR[1], 0.0))
    seat(A, coll, "Visitor", (VISITOR[0], VISITOR[1] - 0.04, 0.45 + 0.745), (0, 1, 0),
         (VISITOR[0] - 0.45, VISITOR[1] - 0.35, 0.0))


def inkpad(K, M):
    """印泥：圆铁盒（盒盖印着花，掀开放在旁边），里面一层红印泥，有几个指头按过的坑。"""
    lathe(K["Steel"], [(0.0, 0.0), (0.042, 0.0), (0.044, 0.02), (0.04, 0.02), (0.04, 0.004), (0.0, 0.004)], 32, M)
    lathe(K["InkPad"], [(0.0, 0.012), (0.039, 0.012), (0.039, 0.016), (0.0, 0.017)], 32, M)
    for k, (dx, dy) in enumerate(((0.01, 0.005), (-0.012, -0.008))):
        uvsphere(K["Dark"], 0.008, 10, 6, M @ T(dx, dy, 0.02) @ S(1.2, 1.5, 0.3))
    lathe(K["Steel"], [(0.0, 0.0), (0.045, 0.0), (0.047, 0.014), (0.0, 0.014)], 32, M @ T(0.075, 0.03, 0.0))
    cylinder(K["InkRed"], 0.03, 0.0005, 24, M @ T(0.075, 0.03, 0.0145))


def pen(K, M):
    """钢笔（黑色胶木笔杆、金色笔夹）。"""
    cylinder(K["Bakelite"], 0.0055, 0.13, 16, M @ R(90, 'Y') @ T(0, 0, -0.065))
    lathe(K["Gold"], [(0.0, 0.0), (0.004, 0.0), (0.001, 0.02), (0.0, 0.021)], 12, M @ R(90, 'Y') @ T(0, 0, 0.065))
    rbox(K["Gold"], 0.04, 0.002, 0.003, M @ T(-0.03, 0.0, 0.007), r=0.0, seg=1)


def phone(K, M):
    """黑色拨盘电话：梯形的机身、话筒架在上面、正面一个拨号盘，一根卷曲的电话线。"""
    prof = [(-0.11, 0.0), (0.11, 0.0), (0.09, 0.09), (-0.09, 0.09)]
    extrude_profile(K["Bakelite"], prof, M @ R(90, 'X') @ T(0, 0, -0.1), 0.2)
    cylinder(K["Bakelite"], 0.055, 0.02, 32, M @ T(0, -0.07, 0.05) @ R(-30, 'X'))
    Fd = M @ T(0, -0.07, 0.05) @ R(-30, 'X') @ T(0, 0, 0.02)
    cylinder(K["Silk"], 0.05, 0.002, 32, Fd)
    for k in range(10):
        a = math.radians(60 + 30 * k)
        cylinder(K["Dark"], 0.006, 0.003, 10, Fd @ T(math.cos(a) * 0.035, math.sin(a) * 0.035, 0.0))
    # 话筒
    hs = M @ T(0, 0.01, 0.12)
    sweep(K["Bakelite"], catmull([hs @ V((-0.11, 0, 0.0)), hs @ V((-0.06, 0, 0.03)), hs @ V((0.06, 0, 0.03)),
                                  hs @ V((0.11, 0, 0.0))], 6), rect_profile(0.03, 0.025, 0.008))
    for sx in (-1, 1):
        cylinder(K["Bakelite"], 0.026, 0.035, 20, hs @ T(sx * 0.11, 0, -0.03))
    # 卷线
    pts = [M @ V((0.12 - 0.005 * k, 0.04 + 0.012 * math.cos(k * 0.9), 0.02 + 0.012 * math.sin(k * 0.9))) for k in range(30)]
    sweep(K["Bakelite"], pts, circle_profile(0.003, 6))


def luopan(K, M):
    """罗盘：方木底座上一块圆盘，盘面一圈圈刻着字（这里刻线代替），中间天池里一根磁针。"""
    rbox(K["WoodRed"], 0.26, 0.26, 0.03, M @ T(0, 0, 0.015), r=0.004, seg=2)
    cylinder(K["Gold"], 0.115, 0.012, 64, M @ T(0, 0, 0.03))
    for k in range(7):
        torus(K["Dark"], 0.03 + 0.012 * k, 0.0006, 64, 4, M @ T(0, 0, 0.042))
    for k in range(24):
        a = 2 * math.pi * k / 24
        rbox(K["Dark"], 0.07, 0.0008, 0.0008, M @ T(math.cos(a) * 0.075, math.sin(a) * 0.075, 0.042) @ R(math.degrees(a), 'Z'),
             r=0.0, seg=1)
    cylinder(K["Glass"], 0.024, 0.004, 32, M @ T(0, 0, 0.042))
    rbox(K["InkRed"], 0.04, 0.003, 0.002, M @ T(0, 0, 0.043) @ R(31, 'Z'), r=0.0, seg=1)
    # 十字红线
    for a in (0, 90):
        rbox(K["InkRed"], 0.26, 0.0012, 0.0012, M @ T(0, 0, 0.046) @ R(a, 'Z'), r=0.0, seg=1)


def banker_lamp(K, A, coll, M):
    """台灯：铜座、铜杆，绿玻璃的灯罩（半个圆筒），灯罩底下一根拉链开关。"""
    rbox(K["Brass"], 0.16, 0.12, 0.03, M @ T(0, 0, 0.015), r=0.012, seg=3)
    cylinder(K["Brass"], 0.008, 0.33, 12, M @ T(0, 0.03, 0.03))
    Mh = M @ T(0, 0.0, 0.36) @ R(-12, 'X')
    cylinder(K["Brass"], 0.006, 0.08, 12, Mh @ T(0, 0.04, 0) @ R(90, 'X'))

    def shade(bm):
        prof = [(math.cos(t) * 0.075, math.sin(t) * 0.055) for t in [math.pi * k / 16 for k in range(17)]]
        prof += [(math.cos(t) * 0.07, math.sin(t) * 0.05) for t in [math.pi * (16 - k) / 16 for k in range(17)]]
        extrude_profile(bm, prof, Mh @ R(90, 'Y') @ T(0, 0, -0.13), 0.26)
    K.separate(K.uid("Lamp_Shade"), "GreenGlass", shade)
    sweep(K["Brass"], [Mh @ V((0.05, -0.02, -0.03)), Mh @ V((0.05, -0.02, -0.12))], circle_profile(0.0012, 5))
    uvsphere(K["Brass"], 0.004, 8, 6, Mh @ T(0.05, -0.02, -0.125))
    light(A, coll, "Light_DeskLamp", Mh @ V((0, 0, -0.02)), (0, -0.25, -1))


def visitor_chair(K, M):
    """来客坐的椅子：五十年代机关里的木椅（四条腿、横档、弯木靠背），漆面磨得发白。"""
    seat_z = 0.45
    rbox(K["WoodDark"], 0.44, 0.42, 0.025, M @ T(0, 0, seat_z - 0.0125), r=0.008, seg=2)
    for sx in (-1, 1):
        for sy in (-1, 1):
            top = seat_z - 0.025
            if sy < 0:
                sweep(K["WoodDark"], [M @ V((sx * 0.19, sy * 0.18, 0.0)), M @ V((sx * 0.19, sy * 0.18, top))],
                      rect_profile(0.035, 0.035, 0.004))
            else:
                # 后腿一直伸上去做靠背立柱，往后仰
                sweep(K["WoodDark"], catmull([M @ V((sx * 0.19, 0.2, 0.0)), M @ V((sx * 0.19, 0.18, top)),
                                              M @ V((sx * 0.19, 0.22, 0.65)), M @ V((sx * 0.185, 0.27, 0.92))], 6),
                      rect_profile(0.035, 0.035, 0.004))
        rbox(K["WoodDark"], 0.02, 0.36, 0.03, M @ T(sx * 0.19, 0, 0.15), r=0.003, seg=1)
    rbox(K["WoodDark"], 0.36, 0.02, 0.03, M @ T(0, -0.18, 0.15), r=0.003, seg=1)
    for z, hh in ((0.62, 0.09), (0.84, 0.07)):
        y = 0.22 + (z - 0.6) * 0.17
        rbox(K["WoodDark"], 0.37, 0.02, hh, M @ T(0, y, z) @ R(-12, 'X'), r=0.006, seg=2)


# ============================================================================ 墙边的家具和东西
def west_wall(K, A, coll, room):
    # 两只顶天立地的红木顶箱柜（沈家搬来的，Poly Haven chinese_cabinet），中间一张条案上摞着账本
    for k, y in enumerate((-1.55, 0.05)):
        anchor(A, coll, f"Anchor_Cabinet{k}", (X0 + 0.3, y, 0.0), (1, 0, 0))
    abox(K["WoodRed"], X0 + 0.05, X0 + 0.45, -0.9, -0.62, 0.0, 0.82, r=0.006)
    for k in range(5):
        rbox(K["Cardboard"], 0.26, 0.2, 0.035, T(X0 + 0.25, -0.76, 0.84 + 0.036 * k) @ R(4 * k - 6, 'Z'), r=0.003,
             seg=1)
    # 西北角：屏风（斜着挡住墙角），后面一张供桌
    anchor(A, coll, "Anchor_Screen", (X0 + 0.72, Y1 - 0.62, 0.0), (0.7, -0.7, 0))
    anchor(A, coll, "Anchor_Altar", (X0 + 0.42, Y1 - 0.25, 0.0), (0.0, -1, 0))
    altar(K, A, coll, T(X0 + 0.42, Y1 - 0.25, 0.632))
    use(A, coll, "Screen", (X0 + 0.75, Y1 - 0.65, 1.2))
    use(A, coll, "Altar", (X0 + 0.42, Y1 - 0.3, 0.85))
    # 北墙窗户左边：一幅「海不扬波」的条幅
    scroll(K, room.frame("N", 0.42, 2.55), "海不扬波")
    use(A, coll, "Scroll", room.at("N", 0.42, 1.8, 0.05))


def altar(K, A, coll, M):
    """供桌上：锡香炉（插着三根快烧完的香）、一对红蜡烛、一块蒙着红布的牌位、一盘发黑的供果。"""
    lathe(K["Pewter"], [(0.0, 0.0), (0.06, 0.0), (0.065, 0.01), (0.075, 0.06), (0.07, 0.08), (0.075, 0.09),
                        (0.07, 0.092), (0.065, 0.085), (0.0, 0.08)], 32, M @ T(0, -0.05, 0))
    cylinder(K["Ash"], 0.066, 0.004, 24, M @ T(0, -0.05, 0.08))
    for k, dx in enumerate((-0.02, 0.0, 0.02)):
        L = 0.05 + 0.02 * k
        cylinder(K["Incense"], 0.0018, L, 6, M @ T(dx, -0.05, 0.082) @ R(3 * (k - 1), 'Y'))
        uvsphere(K["Ember"], 0.0022, 6, 4, M @ T(dx + 0.003 * (k - 1), -0.05, 0.082 + L))
    light(A, coll, "Light_Incense", M @ V((0, -0.05, 0.16)), (0, 0, 1))
    for sx in (-1, 1):
        lathe(K["Pewter"], [(0.0, 0.0), (0.04, 0.0), (0.03, 0.02), (0.012, 0.03), (0.012, 0.1), (0.025, 0.11),
                            (0.0, 0.11)], 24, M @ T(sx * 0.25, -0.03, 0))
        cylinder(K["Candle"], 0.012, 0.09, 16, M @ T(sx * 0.25, -0.03, 0.11))
    # 牌位：底座 + 竖板，蒙着一块红布（布搭下来盖住正面）
    rbox(K["RedLacquer"], 0.16, 0.08, 0.04, M @ T(0, 0.06, 0.02), r=0.006, seg=2)
    rbox(K["RedLacquer"], 0.1, 0.025, 0.32, M @ T(0, 0.06, 0.2), r=0.008, seg=2)
    rows = []
    for j in range(12):
        v = j / 11
        row = []
        for i in range(9):
            u = i / 8 - 0.5
            z = 0.37 - 0.33 * v
            yy = 0.06 - 0.02 - 0.012 * math.sin(math.pi * v) - (0.03 if v > 0.85 else 0.0) * (v - 0.85) / 0.15
            row.append(M @ V((u * 0.17 * (1 + 0.2 * v), yy + 0.004 * math.sin(u * 20 + v * 5), z + 0.004 * math.cos(u * 9))))
        rows.append(row)
    from cockpit import cloth
    cloth(K["ClothRed"], rows, 0.002)
    # 供果：一盘五个苹果，烂得发黑
    lathe(K["Porcelain"], [(0.0, 0.0), (0.06, 0.0), (0.1, 0.015), (0.105, 0.018), (0.0, 0.006)], 32, M @ T(0.15, -0.06, 0))
    rng = random.Random(4)
    for k in range(5):
        a = 2 * math.pi * k / 4 if k < 4 else 0
        r = 0.035 if k < 4 else 0.0
        uvsphere(K["Fruit"], 0.03, 14, 8, M @ T(0.15 + math.cos(a) * r, -0.06 + math.sin(a) * r, 0.04 + (0.035 if k == 4 else 0))
                 @ S(1, 1, 0.85 + rng.uniform(-0.1, 0.05)))


def scroll(K, F, text):
    """一幅条幅（立轴）：上下两根木轴、绫子边、宣纸上四个毛笔大字。"""
    w, h = 0.42, 1.35
    M = F @ T(0, -h / 2, 0.012)
    rbox(K["ScrollPaper"], w, h, 0.002, M, r=0.0, seg=1)
    rbox(K["ClothRed"], w + 0.02, 0.12, 0.003, M @ T(0, h / 2 - 0.06, 0.001), r=0.0, seg=1)
    rbox(K["ClothRed"], w + 0.02, 0.18, 0.003, M @ T(0, -h / 2 + 0.09, 0.001), r=0.0, seg=1)
    for zz in (h / 2 + 0.01, -h / 2 - 0.01):
        cylinder(K["WoodDark"], 0.012, w + 0.08, 16, M @ T(-(w + 0.08) / 2, zz, 0.012) @ R(90, 'Y'))
    for k, ch in enumerate(text):
        K.text(ch, M @ T(0, 0.38 - k * 0.24, 0.0015), 0.16, key="Ink", font=FONT_BRUSH)
    RK.nail(K, F)
    sweep(K["Rope"], [F @ V((0, 0, 0.004)), M @ V((-w / 2 + 0.03, h / 2 + 0.01, 0.01))], circle_profile(0.0012, 5))
    sweep(K["Rope"], [F @ V((0, 0, 0.004)), M @ V((w / 2 - 0.03, h / 2 + 0.01, 0.01))], circle_profile(0.0012, 5))
    K.text("沈氏", M @ T(0.12, -0.45, 0.0015), 0.035, key="InkRed", font=FONT_SERIF)


def east_wall(K, A, coll, room):
    # 大海图：东墙中间，木框玻璃
    RK.picture_frame(K, room.frame("E", 2.35, 2.5), 1.5, 1.0, paper="Chart", frame_key="WoodDark", tilt=2)
    use(A, coll, "Chart", room.at("E", 2.35, 1.95, 0.06))
    # 下面两个卡片抽屉柜
    for y in (0.85, -0.05):
        anchor(A, coll, f"Anchor_Drawers{int(y * 10)}", (X1 - 0.24, y, 0.0), (-1, 0, 0))
    # 拓片（东墙偏南）、民国老照片（拓片下面）
    RK.picture_frame(K, room.frame("E", 4.2, 2.35), 0.5, 0.75, paper="Rubbing", frame_key="WoodDark", tilt=3)
    use(A, coll, "Rubbing", room.at("E", 4.2, 1.95, 0.06))
    RK.picture_frame(K, room.frame("E", 4.95, 1.75), 0.32, 0.24, paper="OldPhoto", frame_key="WoodDark", tilt=4)
    use(A, coll, "OldPhoto", room.at("E", 4.95, 1.6, 0.06))
    # 救生圈：挂在东墙靠门的地方
    anchor(A, coll, "Anchor_Lifebuoy", (X1 - 0.08, -2.2, 1.55), (-1, 0, 0))
    use(A, coll, "Lifebuoy", (X1 - 0.1, -2.2, 1.55))
    # 东北角：保险柜（墨绿漆，铜把手、密码盘）
    safe(K, T(X1 - 0.38, Y1 - 0.35, 0.0))
    use(A, coll, "Safe", (X1 - 0.38, Y1 - 0.6, 0.8))
    # 北墙窗户右边：摆钟
    wall_clock(K, room.frame("N", X1 - X0 - 0.42, 2.35))
    use(A, coll, "Clock", room.at("N", X1 - X0 - 0.42, 2.15, 0.08))


def safe(K, M):
    w, d, h = 0.6, 0.55, 1.05
    rbox(K["SafeGreen"], w, d, h, M @ T(0, 0, h / 2 + 0.04), r=0.015, seg=3)
    rbox(K["SafeGreen"], w - 0.08, 0.02, h - 0.1, M @ T(0, -d / 2 - 0.005, h / 2 + 0.04), r=0.008, seg=2)
    F = M @ T(0, -d / 2 - 0.016, 0.7)
    lathe(K["Chrome"], [(0.0, 0.0), (0.05, 0.0), (0.052, 0.015), (0.04, 0.025), (0.0, 0.026)], 40, F @ R(90, 'X'))
    for k in range(40):
        a = 2 * math.pi * k / 40
        rbox(K["Dark"], 0.002, 0.008 if k % 5 else 0.014, 0.001, F @ R(90, 'X') @ T(math.cos(a) * 0.045, math.sin(a) * 0.045, 0.02)
             @ R(math.degrees(a) + 90, 'Z'), r=0.0, seg=1)
    sweep(K["Brass"], [F @ V((0.12, 0, -0.1)), F @ V((0.12, -0.05, -0.1)), F @ V((0.2, -0.05, -0.1)),
                       F @ V((0.2, 0, -0.1))], circle_profile(0.009, 10))
    for sx in (-1, 1):
        for sy in (-1, 1):
            cylinder(K["Dark"], 0.03, 0.04, 16, M @ T(sx * (w / 2 - 0.05), sy * (d / 2 - 0.05), 0.0))
    K.text("上海　安全牌", M @ T(0, -d / 2 - 0.0162, 1.0) @ R(90, 'X'), 0.025, key="Gold", font=FONT_SERIF)


def wall_clock(K, F):
    """摆钟（木壳，上面圆钟面，下面玻璃门里一个铜钟摆）。指针、钟摆单独成对象（Spin_ClockHour 这些），Godot 里走。"""
    w, h, d = 0.36, 0.78, 0.14
    M = F @ T(0, -h / 2 + 0.12, d / 2)
    rbox(K["WoodRed"], w, h, d, M, r=0.012, seg=3)
    cylinder(K["WoodRed"], 0.17, 0.03, 48, M @ T(0, h / 2 - 0.12, d / 2))
    Fc = M @ T(0, h / 2 - 0.12, d / 2 + 0.03)
    cylinder(K["Silk"], 0.14, 0.004, 48, Fc)
    for k in range(60):
        a = math.radians(90 - 6 * k)
        big = k % 5 == 0
        L = 0.018 if big else 0.008
        rbox(K["Ink"], L, 0.0035 if big else 0.0015, 0.0005, Fc @ T(math.cos(a) * (0.125 - L / 2), math.sin(a) * (0.125 - L / 2),
                                                                     0.0045) @ R(math.degrees(a), 'Z'), r=0.0, seg=1)
    for k in range(12):
        a = math.radians(90 - 30 * (k + 1))
        K.text(str(k + 1), Fc @ T(math.cos(a) * 0.098, math.sin(a) * 0.098, 0.0045), 0.022, key="Ink", font=FONT_SERIF)
    K.text("北极星", Fc @ T(0, 0.045, 0.0045), 0.016, key="Ink", font=FONT_SERIF)
    cylinder(K["Glass"], 0.14, 0.003, 48, Fc @ T(0, 0, 0.02))
    # 指针（原点在钟面中心，Godot 里绕局部 Y 转——导出后 Blender 的 Z 变成 Godot 的 Y）
    for nm, L, wdt in (("Hour", 0.07, 0.008), ("Minute", 0.105, 0.005), ("Second", 0.11, 0.0015)):
        def hand(bm, L=L, wdt=wdt):
            rbox(bm, wdt, L + 0.02, 0.0015, T(0, L / 2 - 0.01, 0), r=0.0, seg=1)
        h_ = K.separate(f"Spin_Clock{nm}", "Ink" if nm != "Second" else "InkRed", hand)
        h_.matrix_world = Fc @ T(0, 0, 0.006 + 0.002 * ("HMS".index(nm[0])))
    # 钟摆：玻璃门后面，一根铜杆一个铜圆盘
    def pendulum(bm):
        sweep(bm, [V((0, 0, 0)), V((0, -0.4, 0))], rect_profile(0.008, 0.002, 0.0))
        cylinder(bm, 0.045, 0.006, 32, T(0, -0.4, -0.003))
    pd = K.separate("Spin_Pendulum", "Brass", pendulum)
    pd.matrix_world = M @ T(0, h / 2 - 0.25, d / 2 - 0.03)
    box(K["Glass"], w - 0.06, h - 0.32, 0.003, M @ T(0, -0.12, d / 2 + 0.002))


def tea_corner(K, A, coll):
    """东南角：一张茶几、两只方凳，茶几上一把茶壶、几个杯子、一个暖水瓶。"""
    cx, cy = X1 - 0.75, Y0 + 0.85
    anchor(A, coll, "Anchor_TeaTable", (cx, cy, 0.0), (0, 1, 0))
    anchor(A, coll, "Anchor_Stool1", (cx - 0.7, cy + 0.05, 0.0), (1, 0, 0))
    anchor(A, coll, "Anchor_Stool2", (cx + 0.05, cy + 0.68, 0.0), (0, -1, 0))
    z = 0.499
    lathe(K["Porcelain"], [(0.0, 0.0), (0.05, 0.0), (0.07, 0.04), (0.068, 0.08), (0.04, 0.1), (0.035, 0.11), (0.0, 0.11)],
          32, T(cx - 0.1, cy, z))
    sweep(K["Porcelain"], catmull([V((cx - 0.03, cy, z + 0.05)), V((cx + 0.01, cy, z + 0.07)), V((cx + 0.02, cy, z + 0.1))], 6),
          circle_profile(0.008, 8))
    for k in range(3):
        lathe(K["Porcelain"], [(0.0, 0.0), (0.02, 0.0), (0.03, 0.04), (0.028, 0.04), (0.018, 0.004), (0.0, 0.004)], 20,
              T(cx + 0.1 + 0.07 * (k % 2), cy - 0.08 + 0.07 * k, z))
    RK.thermos(K, T(cx - 0.25, cy + 0.2, z), seed=4)


# ============================================================================ 头顶
def overhead(K, A, coll):
    RK.fluorescent(K, A, coll, (-0.9, 0.3, H - 0.5), (0, 1, 0), "A", chain=0.5)
    RK.fluorescent(K, A, coll, (1.5, 0.3, H - 0.5), (0, 1, 0), "B", chain=0.5)
    RK.ceiling_fan(K, A, coll, (0.3, -0.9, H), rod=0.55, name="Fan", blade_len=0.6, seed=3)
    for x in (-0.9, 1.5):
        RK.wire_run(K, [V((x, 0.3, H)), V((x, -1.6, H)), V((-1.4, -1.6, H)), V((-1.4, Y0 + 0.02, H))],
                    normal=(0, 0, -1))
    RK.wire_run(K, [V((-1.4, Y0, H - 0.04)), V((-1.4, Y0, 1.43))], normal=(0, 1, 0))


# ============================================================================ 窗外：码头、母船、港湾
def outside(K, A, coll):
    g = GROUND
    # 港湾的水面（Godot 里换成水的材质）
    abox(K["Water"], -200, 200, Y1 + WT, 400, g - 0.2, g)
    # 楼前的码头：从楼脚往北伸出去 60 米，8 米宽；边上一排系缆桩、轮胎
    px0, px1 = -3.0, 5.0
    abox(K["Concrete"], px0, px1, Y1 + WT, Y1 + 62, g - 1.0, PIER_Z)
    abox(K["Concrete"], -30, 30, Y1 + WT - 2, Y1 + WT + 6, g - 1.0, PIER_Z)
    for y in range(8, 62, 6):
        cylinder(K["IronBar"], 0.18, 0.5, 16, T(px1 - 0.4, Y1 + y, PIER_Z))
        cylinder(K["IronBar"], 0.24, 0.06, 16, T(px1 - 0.4, Y1 + y, PIER_Z + 0.5))
        torus(K["Tire"], 0.45, 0.13, 20, 8, T(px1 + 0.15, Y1 + y + 3, PIER_Z - 0.8) @ R(90, 'Y'))
    # 镇海号：靠在码头东边（Godot 里在这个挂点上放 submarine_exterior.glb），盖着半截帆布
    # 艇身轴线在水线下 0.25 米（gen_submarine.py 的 WL），围壳顶离轴线 3.3 米、前后在 y ∈ [-2.75, 0.05]
    anchor(A, coll, "Anchor_Sub", (px1 + 2.0, Y1 + 30.0, g - 0.25), (0, -1, 0))
    tarp(K, V((px1 + 2.0, Y1 + 30.0 - 1.35, g - 0.25 + 3.35)))
    # 母船「东溟号」：码头头上，船尾一个 A 字吊架
    ship(K, A, coll, T(px0 - 5.5, Y1 + 58.0, g) @ R(180, 'Z'))
    # 远处：防波堤、灯塔、几条渔船、山
    abox(K["Concrete"], -120, -10, Y1 + 160, Y1 + 168, g - 1, g + 2.5)
    lp = V((-10, Y1 + 164, g + 2.5))
    cylinder(K["ShipWhite"], 1.2, 9.0, 24, T(*lp), r2=0.9)
    cylinder(K["InkRed"], 1.0, 1.4, 24, T(*(lp + V((0, 0, 9.0)))))
    light(A, coll, "Light_Lighthouse", lp + V((0, 0, 10.0)), (0, 0, -1))
    rng = random.Random(3)
    for k in range(7):
        x = rng.uniform(-60, 60)
        y = Y1 + rng.uniform(70, 140)
        fishing_boat(K, T(x, y, g) @ R(rng.uniform(0, 360), 'Z'), rng)
    hills(K)


def tarp(K, top):
    """盖在潜艇围壳上的半截帆布：一大块布从围壳顶上搭下来，四角绑着绳子拉到艇身上。"""
    rows = []
    for j in range(20):
        v = j / 19
        row = []
        for i in range(17):
            u = i / 16 - 0.5
            x = u * 3.0
            z = -2.2 * v
            y = 3.5 * (v - 0.5) * 0.5 + 0.12 * math.sin(u * 9 + v * 4)
            row.append(top + V((x * (1 + 0.6 * v), y * 2.0, z - 0.15 * abs(u) * v)))
        rows.append(row)
    from cockpit import cloth
    cloth(K["Tarp"], rows, 0.01)


def ship(K, A, coll, M):
    """母船（四十来米的工作船）：船体、驾驶楼、桅杆，后甲板一个 A 字吊架，吊着一根钢缆。"""
    L, B, D = 42.0, 9.0, 4.2
    hull = bmesh.new()
    rows = []
    for k in range(25):
        t = k / 24
        y = -L / 2 + L * t
        b = B / 2 * (1 - max(0.0, t - 0.75) ** 1.5 * 3.2)
        b = max(b, 0.2)
        ring = [hull.verts.new(M @ V((sx * b, y, z))) for sx, z in ((-1, D), (-1, -1.2), (1, -1.2), (1, D))]
        rows.append(ring)
    for k in range(24):
        for i in range(3):
            hull.faces.new([rows[k][i], rows[k][i + 1], rows[k + 1][i + 1], rows[k + 1][i]])
    hull.faces.new(list(reversed(rows[0])))
    hull.faces.new(rows[-1])
    bmesh.ops.recalc_face_normals(hull, faces=hull.faces[:])
    me = bpy.data.meshes.new("Ext_ShipHull")
    hull.to_mesh(me)
    hull.free()
    ob = bpy.data.objects.new("Ext_ShipHull", me)
    K.coll.objects.link(ob)
    me.materials.append(K.M["ShipHull"])
    rbox(K["ShipWhite"], 7.0, 9.0, 3.2, M @ T(0, 6.0, D + 1.6), r=0.1, seg=1)
    rbox(K["ShipWhite"], 5.5, 5.0, 2.4, M @ T(0, 6.5, D + 4.4), r=0.1, seg=1)
    sweep(K["ShipWhite"], [M @ V((0, 5.0, D + 5.6)), M @ V((0, 5.0, D + 13.0))], circle_profile(0.12, 10))
    for sx in (-1, 1):
        sweep(K["CraneRust"], [M @ V((sx * 3.8, -L / 2 + 2.0, D)), M @ V((sx * 1.2, -L / 2 - 1.5, D + 9.0))],
              rect_profile(0.5, 0.5, 0.05))
    sweep(K["CraneRust"], [M @ V((-1.4, -L / 2 - 1.5, D + 9.0)), M @ V((1.4, -L / 2 - 1.5, D + 9.0))],
          rect_profile(0.6, 0.6, 0.05))
    sweep(K["Steel"], [M @ V((0, -L / 2 - 1.5, D + 8.6)), M @ V((0, -L / 2 - 1.6, -0.5))], circle_profile(0.04, 6))
    K.text("东溟", M @ T(4.52, 10.0, D - 1.0) @ R(90, 'Z') @ R(90, 'X'), 1.2, key="Silk", font=FONT_SERIF)
    light(A, coll, "Light_ShipMast", M @ V((0, 5.0, D + 13.1)), (0, 0, -1))


def fishing_boat(K, M, rng):
    L = rng.uniform(10, 18)
    rbox(K["ShipHull"] if rng.random() < 0.5 else K["ShipWhite"], 3.2, L, 1.6, M @ T(0, 0, 0.5), r=0.4, seg=2)
    rbox(K["ShipWhite"], 2.4, 3.0, 2.0, M @ T(0, -L * 0.2, 2.2), r=0.1, seg=1)
    sweep(K["WoodDark"], [M @ V((0, L * 0.15, 1.3)), M @ V((0, L * 0.15, 7.0))], circle_profile(0.1, 8))


def hills(K):
    """远处的山：几座起伏的山包，雨雾里只剩一层灰影。"""
    rng = random.Random(7)
    bm = K["Hill"]
    for k in range(5):
        cx = rng.uniform(-320, 320)
        cy = Y1 + rng.uniform(650, 850)
        w = rng.uniform(260, 420)
        h = rng.uniform(18, 45)
        rows = []
        for j in range(9):
            row = []
            for i in range(33):
                u = i / 32 - 0.5
                v = j / 8
                bump = math.cos(math.pi * u) ** 2 * (0.85 + 0.15 * math.sin(u * 7 + k * 2.1))
                z = GROUND + h * bump * (1 - v * 0.3)
                row.append(bm.verts.new((cx + u * w, cy + v * 80, z)))
            rows.append(row)
        for j in range(8):
            for i in range(32):
                bm.faces.new([rows[j][i], rows[j][i + 1], rows[j + 1][i + 1], rows[j + 1][i]])


# ============================================================================ 贴花
def decals(A, coll):
    def d(kind, pos, normal, up, w, h, depth=0.06):
        decal(A, coll, kind, pos, normal, up, w, h, depth)
    UP, NORTH = V((0, 0, 1)), V((0, 1, 0))
    # 玩家自己从雨里进来：一串湿鞋印从门口到来客椅
    x, y = (DOOR[0] + DOOR[1]) / 2, Y0 + 0.3
    k = 0
    while y < VISITOR[1] - 0.4:
        side = 0.1 if k % 2 else -0.1
        tx = x + (VISITOR[0] - x) * (y - (Y0 + 0.3)) / (VISITOR[1] - 0.4 - (Y0 + 0.3))
        a = math.atan2(VISITOR[0] - x, VISITOR[1] - Y0)
        d("Boot" + ("L" if k % 2 == 0 else "R"), (tx + side * math.cos(a), y, 0.0), UP,
          V((math.sin(a), math.cos(a), 0)), 0.11, 0.29, 0.03)
        y += 0.6
        k += 1
    # 伞底下一滩水；沈渡的椅子底下也有一小滩（他说他一下午都在屋里）
    d("Puddle", (DOOR[1] + 0.45, Y0 + 0.35, 0.0), UP, NORTH, 0.38, 0.32, 0.03)
    d("Puddle", (SHEN[0] - 0.05, SHEN[1] - 0.25, 0.0), UP, NORTH, 0.32, 0.26, 0.03)
    # 窗下：雨从钢窗缝里渗进来，墙上一道道水痕；天花板角上的水渍
    for x in (-1.4, -0.3, 1.0):
        d("Streak", (x, Y1, 0.55), V((0, -1, 0)), UP, 0.3, 0.6, 0.06)
    d("CeilStain", (-1.6, 2.2, H), V((0, 0, -1)), NORTH, 1.1, 0.8, 0.05)
    d("Mold", (X1 * 0.99, Y1 * 0.99, H - 0.2), V((-1, -1, 0)).normalized(), UP, 0.6, 0.5, 0.4)
    # 门把手、开关周围的手印；桌沿被胳膊肘磨亮
    d("Grime", (DOOR[1] + 0.2, Y0, 1.4), V((0, 1, 0)), UP, 0.18, 0.25, 0.05)
    d("FloorWear", ((DOOR[0] + DOOR[1]) / 2, -1.6, 0.0), UP, V((0.3, 1, 0)).normalized(), 0.8, 2.2, 0.04)
    d("Ring", (DESK[0] + 0.35, DESK[1] + 0.25, DESK_Z), UP, NORTH, 0.09, 0.09, 0.03)


# ============================================================================ 能站的地方
def layout(A, coll):
    walk(A, coll, -1.75, 1.0, -2.7, 0.55)        # 屋子南半边
    walk(A, coll, 1.0, 2.1, -1.0, 0.55)          # 茶几北边
    walk(A, coll, -1.75, -0.6, 0.55, 2.0)        # 写字台西边
    walk(A, coll, -1.35, -0.6, 2.0, 2.6)         # 屏风旁边（探头能看见供桌）
    walk(A, coll, 1.25, 2.1, 0.55, 2.2)          # 写字台东边（看海图、钟）
    spawn(A, coll, ((DOOR[0] + DOOR[1]) / 2 + 0.1, Y0 + 0.45, 0.0), (0.45, 1, 0))


# ============================================================================ 入口
def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    preview_dir = argv[argv.index("--preview") + 1] if "--preview" in argv else None
    do_export = "--no-export" not in argv
    reset_scene()
    M = materials({})
    M["Jacket"] = material("M_Jacket", (0.12, 0.15, 0.22), 0.0, 0.9)
    coll = collection("Office")
    A = []
    shell_k = Parts(coll, M, "Shell")
    K = Parts(coll, M, "Office")
    room = shell(shell_k, A, coll)
    door(K, A, coll, room)
    window(K, A, coll, room)
    floor_strips(K)
    wainscot_panels(K, room)
    desk(K, A, coll)
    west_wall(K, A, coll, room)
    east_wall(K, A, coll, room)
    tea_corner(K, A, coll)
    overhead(K, A, coll)
    outside(K, A, coll)
    decals(A, coll)
    layout(A, coll)
    shell_k.flush(recalc=False)
    K.flush()
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(ROOT, "blender", "source", "office.blend"))
    if preview_dir:
        os.makedirs(preview_dir, exist_ok=True)
        for nm, pos, look, lens in (("office_door", (-1.5, -2.5, 1.62), (0.5, 2.0, 1.1), 18),
                                    ("office_seat", (0.3, 0.26, 1.195), (0.3, 3.0, 1.2), 24),
                                    ("office_west", (1.0, -0.5, 1.62), (-2.5, 1.5, 1.0), 18),
                                    ("office_east", (-1.2, 0.0, 1.62), (2.5, 0.5, 1.4), 18),
                                    ("office_out", (0.3, 2.4, 1.7), (3.0, 40.0, -6.0), 28)):
            render_preview(os.path.join(preview_dir, nm + ".png"), V(pos), V(look), lens)
    if do_export:
        RK.export_room(coll, OUT, A)


main()
