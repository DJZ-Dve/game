"""序章「二〇七」：白沙门船厂单身职工宿舍 3 号楼 207（剧情见 docs/story.md）。导出 assets/models/dorm.glb。

一间筒子楼里的单身宿舍，3.3 × 4.4 米，2.9 米高，1998 年夏天，台风前夜：
- 墙：下半截刷绿漆墙裙（油漆，有光，磕掉的地方露出白灰），上半截白灰墙；水泥踢脚线；水泥地刷紫红地板漆，走出了几条发白的路
- 南墙是门（木门刷浅蓝绿漆，球形锁、插销，门底下一道缝——信从这里塞进来），门外是筒子楼的公共走廊
- 北墙是窗（木窗，外面焊着铁防盗窗），窗外是停工的船厂：龙门吊、船台、一盏路灯
- 西墙：铁架床（Poly Haven old_bed_frame）挂着蚊帐，床上褥子、草席、枕头（枕巾）、毛巾被、叠成豆腐块的军被
- 窗下三屉桌：传呼机、催款单、存折、闹钟、收音机、暖水瓶、搪瓷缸、方便面、烟灰缸、台灯、合影；右边抽屉半开，里面是退伍证
- 东墙：铁管脸盆架（顶上一面小镜子——玩家在这里看见自己的脸）、帆布简易衣柜
- 西南角：刷白漆的旧碗柜，上面电炉、搪瓷锅；屋中间横着一根晾衣绳，挂着毛巾、汗衫、袜子
- 头顶：日光灯、三叶吊扇；明线从门边的开关沿墙爬上去

用法：Blender -b --factory-startup --python blender/scripts/gen_dorm.py [-- --preview DIR] [--no-export]
"""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(__file__))
import bpy  # noqa: E402
import bmesh  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Vector as V, Matrix  # noqa: E402

from lib import (reset_scene, collection, frame, T, R, S, cylinder, box, uvsphere, lathe, torus, catmull,  # noqa: E402
                 circle_profile, rect_profile, sweep, empty, text_mesh, render_preview)
from kit import Parts, rbox, extrude_profile, FONT_SANS, FONT_SERIF, FONT_HAND, FONT_BRUSH  # noqa: E402
import room_kit as RK  # noqa: E402
from room_kit import Room, anchor, light, use, seat, walk, spawn, decal  # noqa: E402
from bedding import Bunk, Collider, simulate, cloth_object, grid, _noise2  # noqa: E402
from quarters import enamel_mug  # noqa: E402

ROOT = RK.ROOT
OUT = os.path.join(ROOT, "assets", "models", "dorm.glb")

# ---------------------------------------------------------------------------- 主尺寸（改了要同步 scripts/story/dorm.gd）
X0, X1, Y0, Y1, H = -1.65, 1.65, -2.2, 2.2, 2.9
WT = 0.24                          # 墙厚
DOOR = (0.55, 1.45, 2.0)           # 门洞 x 范围、高度（南墙）
WIN = (-0.75, 0.75, 0.9, 2.35)     # 窗洞 x 范围、下沿、上沿（北墙）
DADO = 1.2                         # 墙裙高度
CY0, CY1 = Y0 - WT - 1.8, Y0 - WT  # 走廊（南北方向的范围）
CX0, CX1 = -5.0, 4.0               # 走廊（东西方向）
GROUND = -3.65                     # 窗外地面（二楼）
BED = (-1.17, 0.15)                # 床的中心（x, y），床头朝北
BED_Z = 0.496                      # 床绷子的高度
DESK = (-0.55, 0.55, 1.61, 2.17, 0.76)   # 三屉桌：x 范围、y 范围、桌面高度
WASH = (1.33, 1.05)                # 脸盆架
MIRROR_Z = 1.6                     # 镜子中心高度


def materials(M):
    RK.materials(M)
    from lib import material

    def add(key, name, color, metal=0.0, rough=0.6, emission=None, strength=1.0, alpha=1.0):
        if key not in M:
            M[key] = material(name, color, metal, rough, emission, strength, alpha)
    add("Concrete", "M_Concrete", (0.45, 0.45, 0.43), 0.0, 0.85)
    add("Mattress", "M_Mattress", (0.55, 0.58, 0.62), 0.0, 0.9)
    add("Sheet", "M_Sheet", (0.75, 0.76, 0.73), 0.0, 0.9)
    add("Pillow", "M_Pillow", (0.72, 0.7, 0.62), 0.0, 0.9)
    add("Blanket", "M_Blanket", (0.25, 0.27, 0.16), 0.0, 0.95)
    add("Towel", "M_Towel", (0.7, 0.66, 0.56), 0.0, 0.95)
    add("Mat", "M_StrawMat", (0.62, 0.52, 0.32), 0.0, 0.8)
    add("TowelBlanket", "M_TowelBlanket", (0.6, 0.45, 0.5), 0.0, 0.95)
    add("Net", "M_MosquitoNet", (0.9, 0.9, 0.88), 0.0, 0.9, alpha=0.3)
    add("Canvas", "M_Canvas", (0.3, 0.38, 0.42), 0.0, 0.85)
    add("Curtain", "M_CurtainCheck", (0.55, 0.62, 0.7), 0.0, 0.9)
    add("Undershirt", "M_Undershirt", (0.85, 0.84, 0.8), 0.0, 0.9)
    add("Sock", "M_Sock", (0.25, 0.25, 0.27), 0.0, 0.95)
    add("Jacket", "M_Jacket", (0.12, 0.15, 0.22), 0.0, 0.9)
    add("Plastic", "M_PlasticRed", (0.6, 0.08, 0.06), 0.0, 0.4)
    add("PlasticWhite", "M_PlasticWhite", (0.85, 0.84, 0.8), 0.0, 0.35)
    add("Booklet", "M_BookletRed", (0.4, 0.04, 0.03), 0.0, 0.6)
    add("BookletGreen", "M_BookletGreen", (0.14, 0.26, 0.18), 0.0, 0.6)
    add("Briquette", "M_Briquette", (0.06, 0.06, 0.06), 0.0, 0.95)
    add("Ground", "M_WetGround", (0.08, 0.08, 0.08), 0.0, 0.2)
    add("Brick", "M_Brick", (0.35, 0.2, 0.15), 0.0, 0.85)
    add("CraneRust", "M_CraneRust", (0.2, 0.12, 0.08), 0.5, 0.7)
    add("ShipHull", "M_ShipHull", (0.15, 0.15, 0.15), 0.3, 0.6)
    add("StreetLamp", "M_StreetLampGlass", (1.0, 0.6, 0.25), 0.0, 0.3, emission=(1.0, 0.55, 0.2), strength=3)
    add("NavLight", "M_NavLight", (1.0, 0.2, 0.1), 0.0, 0.3, emission=(1.0, 0.15, 0.08), strength=6)
    add("NeighborWindow", "M_NeighborWindow", (0.8, 0.6, 0.3), 0.0, 0.5, emission=(1.0, 0.65, 0.3), strength=1.5)
    add("Coil", "M_Coil", (0.5, 0.45, 0.4), 0.8, 0.5)
    add("Noodle", "M_Noodle", (0.85, 0.75, 0.5), 0.0, 0.6)
    add("Cigarette", "M_Cigarette", (0.85, 0.8, 0.7), 0.0, 0.8)
    add("Filter", "M_CigFilter", (0.75, 0.5, 0.25), 0.0, 0.8)
    add("Lcd", "M_PagerLcd", (0.45, 0.5, 0.4), 0.0, 0.3)
    add("Sweater", "M_Sweater", (0.45, 0.12, 0.1), 0.0, 0.95)
    add("Bottle", "M_Bottle", (0.3, 0.2, 0.1), 0.0, 0.25)
    return M


# ============================================================================ 壳子
def shell(S_, A, coll):
    """宿舍和走廊的墙、地、顶。S_：墙地顶专用的零件桶（朝向自己排好，导出时不重算法线）。"""
    room = Room(S_, A, X0, X1, Y0, Y1, H, WT)
    # 南墙 u 从东往西量（屋里面朝南看，右手是西）
    room.opening("S", X1 - DOOR[1], X1 - DOOR[0], 0.0, DOOR[2], outer=False)
    room.opening("N", WIN[0] - X0, WIN[1] - X0, WIN[2], WIN[3], sill="Skirt")
    room.walls(upper="Plaster", dado="DadoGreen", dado_h=DADO, line="DadoLine", skirt="Skirt", skirt_h=0.12)
    room.floor("FloorPaint")
    room.ceiling("Ceiling")
    # 走廊：北墙上和宿舍门对着开一个洞，西头是楼梯口（黑洞洞的），东头一扇小窗
    cor = Room(S_, A, CX0, CX1, CY0, CY1, H, WT)
    cor.opening("N", DOOR[0] - CX0, DOOR[1] - CX0, 0.0, DOOR[2], outer=False)
    cor.opening("W", 0.3, 1.5, 0.0, 2.2, outer=False)
    cor.opening("E", 0.5, 1.3, 1.1, 2.0, sill="Skirt")
    cor.walls(upper="Plaster", dado="DadoGreen", dado_h=DADO, line="DadoLine", skirt="Skirt", skirt_h=0.12)
    cor.floor("Concrete")
    cor.ceiling("Ceiling")
    # 门洞里的过门石（门槛）
    abox(S_["Skirt"], DOOR[0], DOOR[1], CY1, Y0, 0.0, 0.012)
    # 楼梯口里面：一段往下的黑台阶，几步就看不见了
    for k in range(6):
        abox(S_["Concrete"], CX0 - 0.3 - 0.28 * (k + 1), CX0 - 0.3 - 0.28 * k, CY0 + 0.3, CY0 + 1.5,
             -0.17 * (k + 1) - 0.1, -0.17 * (k + 1))
    return room, cor


def abox(bm, x0, x1, y0, y1, z0, z1, r=0.0, seg=2):
    rbox(bm, abs(x1 - x0), abs(y1 - y0), abs(z1 - z0), T((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2), r=r, seg=seg)


# ============================================================================ 门、窗
def door(K, A, coll, room):
    uc = X1 - (DOOR[0] + DOOR[1]) / 2
    F = room.frame("S", uc, 0.0)
    w = DOOR[1] - DOOR[0]
    leaf, hw = RK.wood_door(K, F, w, DOOR[2], leaf="DoorBlue", jamb="DoorBlue", hinge_right=False, name="Door_Leaf")
    # 走廊那一面也有一圈门框贴脸
    Fo = frame(V(((DOOR[0] + DOOR[1]) / 2, Y0 - WT, 0)), V((0, -1, 0)), V((0, 0, 1)))
    for (cx, cy, sx, sy) in ((-w / 2 - 0.03, DOOR[2] / 2 + 0.03, 0.06, DOOR[2] + 0.06),
                             (w / 2 + 0.03, DOOR[2] / 2 + 0.03, 0.06, DOOR[2] + 0.06), (0, DOOR[2] + 0.03, w + 0.12, 0.06)):
        rbox(K["DoorBlue"], sx, sy, 0.02, Fo @ T(cx, cy, 0.01), r=0.004, seg=2)
    # 门外面刷的房号「207」，和门扇一起转
    num = text_mesh("207", "Door_Leaf_Num", coll, K.M["Silk"], Matrix(), size=0.06, extrude=0.0005,
                    font_path=FONT_SANS)
    num.matrix_world = leaf.matrix_world @ T((w - 0.01) / 2, 1.62, -0.0405) @ R(180, 'Y')
    # 门后两个挂钩（门扇局部坐标，和门扇一起转）
    def hooks(bm):
        for dx in (0.25, 0.55):
            Mh = T(dx, DOOR[2] - 0.25, 0.0)
            cylinder(bm, 0.004, 0.04, 8, Mh)
            cylinder(bm, 0.004, 0.02, 8, Mh @ T(0, 0, 0.04) @ R(-70, 'X'))
    hk = K.separate("Door_Leaf_Hooks", "Steel", hooks)
    hk.matrix_world = leaf.matrix_world
    # 门边墙上：扳把开关、吊扇调速器（圆盒子 + 旋钮）、拉上去的明线
    sw = room.frame("S", X1 - 0.35, 1.38)
    RK.toggle_switch(K, sw)
    use(A, coll, "Switch", room.at("S", X1 - 0.35, 1.38, 0.03))
    reg = room.frame("S", X1 - 0.18, 1.38)
    lathe(K["BakeliteBrown"], [(0.0, 0.0), (0.045, 0.0), (0.046, 0.03), (0.04, 0.04), (0.0, 0.041)], 32, reg)
    lathe(K["Bakelite"], [(0.0, 0.04), (0.018, 0.04), (0.018, 0.058), (0.0, 0.06)], 20, reg)
    return leaf, hw


def window(K, A, coll, room):
    uc = (WIN[0] + WIN[1]) / 2 - X0
    vc = (WIN[2] + WIN[3]) / 2
    w, h = WIN[1] - WIN[0], WIN[3] - WIN[2]
    F = room.frame("N", uc, vc, -WT * 0.55)
    RK.wood_window(K, F, w - 0.01, h - 0.01, frame_key="WindowWood", glass="WinGlass", transom=0.38,
                   open_deg=(0, 0), name="Window")
    # 防盗窗：窗洞外面焊一个往外凸 30 厘米的铁笼子，竖条每 12 厘米一根
    yo = Y1 + WT
    xa, xb = WIN[0] - 0.05, WIN[1] + 0.05
    za, zb = WIN[2] - 0.05, WIN[3] + 0.05
    d = 0.3
    for (p0, p1) in (((xa, yo, za), (xa, yo + d, za)), ((xb, yo, za), (xb, yo + d, za)),
                     ((xa, yo, zb), (xa, yo + d, zb)), ((xb, yo, zb), (xb, yo + d, zb)),
                     ((xa, yo + d, za), (xb, yo + d, za)), ((xa, yo + d, zb), (xb, yo + d, zb)),
                     ((xa, yo + d, (za + zb) / 2), (xb, yo + d, (za + zb) / 2)),
                     ((xa, yo + d, za), (xa, yo + d, zb)), ((xb, yo + d, za), (xb, yo + d, zb))):
        sweep(K["IronBar"], [V(p0), V(p1)], rect_profile(0.025, 0.025, 0.002))
    n = int((xb - xa) / 0.12)
    for i in range(1, n):
        x = xa + (xb - xa) * i / n
        sweep(K["IronBar"], [V((x, yo + d, za)), V((x, yo + d, zb))], circle_profile(0.007, 8))
        # 底下一片铁皮托板，放花盆的（空的，积着锈水）
    abox(K["IronBar"], xa, xb, yo, yo + d, za - 0.004, za + 0.004)
    # 窗台上（屋里）：一个空罐头盒插着两支蔫了的花？太讲究——一卷卫生纸、一包火柴
    lathe(K["PlasticWhite"], [(0.0, 0.0), (0.055, 0.0), (0.055, 0.1), (0.02, 0.1), (0.02, 0.0)], 24,
          T(0.48, Y1 - 0.12, WIN[2] + 0.02))
    rbox(K["Paper"], 0.05, 0.035, 0.015, T(0.32, Y1 - 0.1, WIN[2] + 0.028) @ R(20, 'Z'), r=0.001, seg=1)
    # 窗帘：一根铁丝横在窗洞上方，蓝白格子布窗帘拉到东边，堆着
    wire_z = WIN[3] + 0.08
    sweep(K["Steel"], [V((WIN[0] - 0.2, Y1 - 0.06, wire_z)), V((WIN[1] + 0.2, Y1 - 0.06, wire_z))],
          circle_profile(0.0018, 6))
    for x in (WIN[0] - 0.2, WIN[1] + 0.2):
        RK.nail(K, frame(V((x, Y1, wire_z)), V((0, -1, 0))))
    curtain(K, (WIN[1] - 0.42, WIN[1] + 0.16), Y1 - 0.06, wire_z, WIN[2] - 0.05, folds=11, seed=3)
    curtain(K, (WIN[0] - 0.14, WIN[0] + 0.1), Y1 - 0.06, wire_z, WIN[2] - 0.08, folds=6, seed=5)
    # 一块碎了的玻璃用报纸糊着（左下那块）
    RK.paper_quad(K, "Newspaper", frame(V((WIN[0] + w * 0.27, Y1 + WT * 0.55 - 0.012, WIN[2] + 0.42)),
                                        V((0, -1, 0))), 0.3, 0.42)
    use(A, coll, "Window", (0.0, Y1 - 0.1, 1.6))


def curtain(K, xr, y, ztop, zbot, folds=10, seed=1):
    """挂在铁丝上的布帘：顶上一排夹子钉住，往下一道道褶子（拉到一边的堆得很密）。"""
    rng = random.Random(seed)
    span = xr[1] - xr[0]
    nu = folds * 12 + 1
    nv = max(8, int((ztop - zbot) / 0.025) + 1)
    per = [rng.uniform(0.6, 1.35) for _ in range(folds + 2)]
    ph = rng.uniform(0, 6.28)
    amp = min(0.05, 0.012 + 0.6 * 0.07 / span * 0.1 * folds)
    co, uv = [], []
    for j in range(nv):
        v = j / (nv - 1)
        for i in range(nu):
            u = i / (nu - 1)
            k = u * folds
            k0 = int(min(k, folds))
            t = k - k0
            a = amp * (per[k0] * (1 - t) + per[min(k0 + 1, folds + 1)] * t) * (1 + 0.5 * v)
            x = xr[0] + span * u
            yy = y + a * math.sin(u * folds * 2 * math.pi + ph)
            z = ztop - 0.01 - (ztop - 0.01 - zbot) * v
            co.append((x, yy, z))
            uv.append((span * u * 2.2, ztop - z))
    co = np.array(co)
    faces = grid(nu, nv)
    wall = bmesh.new()
    bmesh.ops.create_cube(wall, size=1.0, matrix=T((xr[0] + xr[1]) / 2, Y1 + 0.05, 1.5) @ S(3, 0.1, 3))
    sill = bmesh.new()
    bmesh.ops.create_cube(sill, size=1.0, matrix=T((xr[0] + xr[1]) / 2, Y1 - 0.02, WIN[2] - 0.02) @ S(3, 0.12, 0.04))
    out = simulate(f"dorm_curtain_{seed}", co, faces, [Collider(wall), Collider(sill)], frames=50,
                   pin=list(range(nu)), mass=0.12, tension=12.0, bending=0.06, quality=6, distance=0.003)
    cloth_object(K.uid("Cloth_Curtain"), K.coll, K.M["Curtain"], out, faces, np.array(uv), thick=0.002, subsurf=0)
    for k in range(folds // 2 + 1):
        x = xr[0] + span * k / (folds // 2)
        rbox(K["Steel"], 0.008, 0.012, 0.03, T(x, y, ztop - 0.008), r=0.001, seg=1)


# ============================================================================ 床
def bed(K, A, coll):
    bx, by = BED
    anchor(A, coll, "Anchor_Bed", (bx, by, 0.0), (0, -1, 0))
    # bedding.Bunk：床靠西墙（s=-1），xin 是靠屋里那条边离中线 0 的距离——这里中线就是 x=0，正好可以直接用
    xin, xw = -(bx + 0.45) + 0.01, -(bx - 0.45) - 0.03
    b = Bunk(K, -1, BED_Z, xin, xw, by - 0.97, by + 0.97, 0.0, False, "dorm")
    b.mattress(h=0.07, seed=4)
    b.sheet(seed=5, crumple=0.008)
    straw_mat(K, b)
    b.pillow(seed=7, size=(0.52, 0.3), tilt=4)
    pillow_towel(K, b)
    b.blanket(seed=9, over=0.12, y0=by - 0.55, y1=by + 0.45, crumple=0.04, res=0.024, bunch=0.6,
              frames=90)
    for o in K.coll.objects:
        if o.name == "Bed_Blanket_dorm" and o.data.materials:
            o.data.materials[0] = K.M["TowelBlanket"]
    b.folded_blanket(by - 0.72, layers=7, size=(0.46, 0.34), seed=11)
    # 铁床的床头、床尾栏杆也挡着蚊帐
    b._box(sorted((b.x(b.xin), b.x(b.xw))), (by + 0.93, by + 0.97), (0.0, 1.2))
    b._box(sorted((b.x(b.xin), b.x(b.xw))), (by - 0.97, by - 0.93), (0.0, 0.84))
    sweater(K, b)
    mosquito_net(K, b)
    # 床底下：两个纸箱、一只樟木箱、一个脸盆
    anchor(A, coll, "Anchor_BoxBed1", (bx + 0.05, by - 0.45, 0.0), (1, 0.15, 0))
    anchor(A, coll, "Anchor_BoxBed2", (bx - 0.05, by + 0.35, 0.0), (1, -0.1, 0))
    trunk(K, T(bx + 0.02, by + 0.85, 0.0) @ R(92, 'Z'))
    # 床前一双拖鞋
    slippers(K, T(bx + 0.62, by + 0.05, 0.0) @ R(-80, 'Z'))
    use(A, coll, "Bed", (bx + 0.25, by - 0.1, 0.62))
    use(A, coll, "Sweater", (bx + 0.1, by + 0.55, 0.62))
    seat(A, coll, "Bed", (bx + 0.3, by - 0.15, BED_Z + 0.07 + 0.72), (1, 0.15, 0), (bx + 0.85, by - 0.15, 0.0))
    return b


def straw_mat(K, b):
    """草席：一张硬一点的薄席子，铺在床单上，四边比褥子窄一点。"""
    rng = random.Random(6)
    noise = _noise2(rng, 5, 4.0, 12.0)
    res = 0.03
    d0, d1 = b.xin + 0.06, b.xw - 0.03
    y0, y1 = b.ya + 0.08, b.yf - 0.12
    nu, nv = int((d1 - d0) / res) + 1, int((y1 - y0) / res) + 1
    z0 = b._zmax(d0, d1, y0, y1) + 0.02
    co, uv = [], []
    for j in range(nv):
        for i in range(nu):
            x, y = d0 + i * res, y0 + j * res
            co.append((b.x(x), y, z0 + 0.004 * noise(x, y)))
            uv.append((i * res, j * res))
    co = np.array(co)
    faces = grid(nu, nv)
    out = simulate("dorm_mat", co, faces, b.cols, frames=40, mass=0.4, tension=40.0, bending=3.0, quality=6,
                   distance=0.003)
    cloth_object("Bed_Mat_dorm", K.coll, K.M["Mat"], out, faces, np.array(uv), thick=0.003, subsurf=0)
    b._add(out, faces, outer=0.002)
    b.top += 0.004


def pillow_towel(K, b):
    """枕巾：一条毛巾铺在枕头上，两头垂下去。"""
    rng = random.Random(8)
    noise = _noise2(rng, 5, 6.0, 16.0)
    res = 0.015
    cx = (b.xin + b.xw) / 2
    d0, d1 = cx - 0.3, cx + 0.3
    y0, y1 = b.yf - 0.38, b.yf - 0.03
    nu, nv = int((d1 - d0) / res) + 1, int((y1 - y0) / res) + 1
    z0 = b._zmax(d0, d1, y0, y1) + 0.025
    co, uv = [], []
    for j in range(nv):
        for i in range(nu):
            x, y = d0 + i * res, y0 + j * res
            co.append((b.x(x), y, z0 + 0.006 * noise(x, y)))
            uv.append((i * res, j * res))
    co = np.array(co)
    faces = grid(nu, nv)
    out = simulate("dorm_pillowtowel", co, faces, b.cols, frames=50, mass=0.25, tension=12.0, bending=0.4,
                   quality=6, distance=0.003)
    cloth_object("Bed_PillowTowel_dorm", K.coll, K.M["Towel"], out, faces, np.array(uv), thick=0.003, subsurf=1)
    b._add(out, faces)


def sweater(K, b):
    """妈织的毛衣：叠好放在床头那边的里侧（三伏天用不上）。一个软一点的方块，上面一道道针脚的棱。"""
    cx = b.x((b.xin + b.xw) / 2 + 0.25)
    y = b.yf - 0.62
    z = b.surface_z(cx, y, 0.15)
    M = T(cx, y, z) @ R(8, 'Z')
    rbox(K["Sweater"], 0.32, 0.26, 0.05, M @ T(0, 0, 0.025), r=0.02, seg=3)
    for k in range(9):
        rbox(K["Sweater"], 0.3, 0.006, 0.004, M @ T(0, -0.11 + 0.0275 * k, 0.051), r=0.002, seg=1)


def mosquito_net(K, b):
    """蚊帐：床四角绑四根竹竿，顶上一圈竹竿框；白纱从框上垂下来，靠屋里那面撩起来挂在两边的钩子上。"""
    x_in, x_w = b.x(b.xin - 0.005), b.x(b.xw)
    y_a, y_f = b.ya - 0.02, b.yf + 0.02
    top = 1.98
    for x in (x_in, x_w):
        for y in (y_a, y_f):
            sweep(K["Bamboo"], [V((x, y, 0.75 if y == y_a else 1.1)), V((x, y, top + 0.02))], circle_profile(0.011, 10))
            for z in (0.8 if y == y_a else 1.15, top - 0.05):
                torus(K["Rope"], 0.014, 0.003, 12, 4, T(x, y, z))
    for (p0, p1) in (((x_in, y_a), (x_in, y_f)), ((x_w, y_a), (x_w, y_f)), ((x_in, y_a), (x_w, y_a)),
                     ((x_in, y_f), (x_w, y_f))):
        sweep(K["Bamboo"], [V((p0[0], p0[1], top)), V((p1[0], p1[1], top))], circle_profile(0.009, 8))
    # 纱：靠墙那面、床头、床尾三面垂下来；屋里那面两头各撩起一束
    panels = [
        ("wall", [(x_w + 0.005, y_a), (x_w + 0.005, y_f)], 0.0),
        ("head", [(x_w, y_f + 0.005), (x_in, y_f + 0.005)], 0.0),
        ("foot", [(x_in, y_a - 0.005), (x_w, y_a - 0.005)], 0.0),
    ]
    zb = BED_Z + 0.02
    for tag, (p0, p1), _ in panels:
        L = math.dist(p0, p1)
        res = 0.04
        nu = int(L / res) + 1
        nv = int((top - zb) / res) + 1
        co, uv = [], []
        for j in range(nv):
            for i in range(nu):
                u = i / (nu - 1)
                x = p0[0] + (p1[0] - p0[0]) * u
                y = p0[1] + (p1[1] - p0[1]) * u
                z = top - (top - zb) * j / (nv - 1)
                wob = 0.01 * math.sin(u * 17 + j * 0.3)
                n = V((-(p1[1] - p0[1]), p1[0] - p0[0], 0)).normalized()
                co.append((x + n.x * wob, y + n.y * wob, z))
                uv.append((L * u, top - z))
        co = np.array(co)
        faces = grid(nu, nv)
        out = simulate(f"dorm_net_{tag}", co, faces, b.cols, frames=45, pin=list(range(nu)), mass=0.05,
                       tension=6.0, bending=0.02, quality=5, distance=0.004)
        cloth_object(f"Net_{tag}", K.coll, K.M["Net"], out, faces, np.array(uv), subsurf=0)
    for k, y in enumerate((y_a + 0.12, y_f - 0.14)):
        gathered_net(K, b, x_in, y, top, k)


def gathered_net(K, b, x, y, top, k):
    """撩起来的一束纱：一圈很密的褶子，中间被一根绳扎住，挂在竹竿上的钩子上。"""
    rng = random.Random(20 + k)
    rows = []
    for j in range(24):
        v = j / 23
        z = top - (top - 1.05) * v
        pinch = 1.0 - 0.6 * math.exp(-((z - 1.35) / 0.12) ** 2)
        r = (0.045 + 0.02 * v) * pinch
        ring = []
        for i in range(25):
            a = 2 * math.pi * i / 24
            rr = r * (1 + 0.25 * math.sin(a * 6 + rng.uniform(0, 1)))
            ring.append(V((x + 0.05 + math.cos(a) * rr * 0.6, y + math.sin(a) * rr, z)))
        rows.append(ring)
    def geo(bm):
        uvl = bm.loops.layers.uv.new("UVMap")
        vs = [[bm.verts.new(p) for p in ring] for ring in rows]
        for j in range(len(vs) - 1):
            for i in range(24):
                f = bm.faces.new([vs[j][i], vs[j][i + 1], vs[j + 1][i + 1], vs[j + 1][i]])
                for loop, (di, dj) in zip(f.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
                    loop[uvl].uv = ((i + di) * 0.03, (j + dj) * 0.04)
    K.separate(K.uid("Cloth_NetGather"), "Net", geo, recalc=False)
    torus(K["Rope"], 0.04, 0.004, 16, 4, T(x + 0.05, y, 1.35))


def trunk(K, M):
    """樟木箱：红褐色漆，四角包铜皮，正面一把小铜锁。"""
    w, d, h = 0.7, 0.42, 0.34
    rbox(K["WoodDark"], w, d, h - 0.12, M @ T(0, 0, (h - 0.12) / 2), r=0.006, seg=2)
    rbox(K["WoodDark"], w + 0.006, d + 0.006, 0.12, M @ T(0, 0, h - 0.06), r=0.01, seg=2)
    for sx in (-1, 1):
        for sy in (-1, 1):
            for z in (0.02, h - 0.02):
                rbox(K["Brass"], 0.05, 0.05, 0.05, M @ T(sx * (w / 2 - 0.02), sy * (d / 2 - 0.02), z), r=0.008, seg=2)
    rbox(K["Brass"], 0.06, 0.008, 0.07, M @ T(0, -d / 2 - 0.004, h - 0.12), r=0.003, seg=1)
    torus(K["Brass"], 0.012, 0.003, 12, 4, M @ T(0, -d / 2 - 0.012, h - 0.17) @ R(90, 'X'))


def slippers(K, M):
    """一双塑料拖鞋（蓝色）：鞋底 + 一条横带，一只摆正、一只歪着。"""
    for k, (dx, a) in enumerate(((-0.06, 4), (0.07, -15))):
        Ms = M @ T(dx, 0.02 * k, 0) @ R(a, 'Z')
        prof = [(math.cos(t) * 0.045 * (1.1 if math.sin(t) > 0 else 0.95), math.sin(t) * 0.13)
                for t in [2 * math.pi * i / 24 for i in range(24)]]
        extrude_profile(K["PlasticWhite"], prof, Ms, 0.018)
        sweep(K["Plastic"], catmull([Ms @ V((-0.045, 0.04, 0.016)), Ms @ V((-0.03, 0.045, 0.05)),
                                     Ms @ V((0.03, 0.045, 0.05)), Ms @ V((0.045, 0.04, 0.016))], 6),
              rect_profile(0.04, 0.004, 0.0015))


# ============================================================================ 三屉桌和桌上的东西
def desk(K, A, coll):
    x0, x1, y0, y1, z = DESK
    t = 0.03
    rbox(K["WoodLight"], x1 - x0 + 0.02, y1 - y0 + 0.02, t, T((x0 + x1) / 2, (y0 + y1) / 2, z - t / 2), r=0.006, seg=2)
    # 四条腿（往下略收）、腿之间的横撑、脚踏横档
    for sx, x in ((-1, x0 + 0.03), (1, x1 - 0.03)):
        for y in (y0 + 0.03, y1 - 0.03):
            sweep(K["WoodLight"], [V((x, y, z - t)), V((x - sx * 0.01, y, 0.0))], rect_profile(0.045, 0.045, 0.004))
        rbox(K["WoodLight"], 0.03, y1 - y0 - 0.06, 0.05, T(x, (y0 + y1) / 2, 0.12), r=0.003, seg=1)
    rbox(K["WoodLight"], x1 - x0 - 0.06, 0.03, 0.04, T((x0 + x1) / 2, y1 - 0.04, 0.12), r=0.003, seg=1)
    # 桌面底下三个抽屉（横着一排），右边那个拉开一截
    dh = 0.12
    rbox(K["WoodLight"], x1 - x0 - 0.04, y1 - y0 - 0.02, 0.012, T((x0 + x1) / 2, (y0 + y1) / 2, z - t - dh - 0.006),
         r=0.002, seg=1)
    rbox(K["WoodLight"], x1 - x0 - 0.04, 0.012, dh, T((x0 + x1) / 2, y1 - 0.02, z - t - dh / 2), r=0.002, seg=1)
    dw = (x1 - x0 - 0.06) / 3
    for k in range(3):
        cx = x0 + 0.03 + dw * (k + 0.5)
        pull = 0.17 if k == 2 else 0.0
        F = T(cx, y0 - pull + 0.012, z - t - dh / 2)
        rbox(K["WoodLight"], dw - 0.008, 0.02, dh - 0.01, F, r=0.003, seg=2)
        rbox(K["Brass"], 0.06, 0.012, 0.012, F @ T(0, -0.014, 0.01), r=0.003, seg=2)
        if pull:
            # 拉开的抽屉：屉帮、屉底，里面一个红皮小本（退伍证）、一叠信、一把钥匙
            for sx in (-1, 1):
                rbox(K["WoodLight"], 0.01, 0.4, dh - 0.03, F @ T(sx * (dw / 2 - 0.02), 0.2, -0.01), r=0.0, seg=1)
            rbox(K["WoodLight"], dw - 0.04, 0.4, 0.008, F @ T(0, 0.2, -dh / 2 + 0.012), r=0.0, seg=1)
            booklet(K, F @ T(-0.04, 0.09, -dh / 2 + 0.017) @ R(12, 'Z'), "Booklet", (0.075, 0.105, 0.008))
            rbox(K["PaperWhite"], 0.11, 0.16, 0.012, F @ T(0.05, 0.2, -dh / 2 + 0.02) @ R(-6, 'Z'), r=0.001, seg=1)
            use(A, coll, "Discharge", F @ V((-0.04, 0.09, -dh / 2 + 0.03)))
    # 桌上的东西
    zt = z
    anchor(A, coll, "Anchor_AlarmClock", (0.38, 2.02, zt), (-0.35, -1, 0))
    anchor(A, coll, "Anchor_Radio", (-0.4, 2.05, zt + 0.111), (0.3, -1, 0))
    anchor(A, coll, "Anchor_Pears", (-0.2, 2.06, zt + 0.012), (0, -1, 0))
    plate(K, T(-0.19, 2.08, zt))
    RK.thermos(K, T(0.47, 1.78, zt) @ R(30, 'Z'), seed=2)
    enamel_mug(K, T(0.26, 1.74, zt) @ R(-120, 'Z'), words="白沙门船厂", tea=0.4, seed=3)
    pager(K, T(-0.08, 1.8, zt) @ R(15, 'Z'))
    use(A, coll, "Pager", (-0.08, 1.8, zt + 0.03))
    # 催款单：摊在桌上，边上压着一个空方便面碗
    RK.paper_quad(K, "Bill", T(0.06, 1.88, zt + 0.0015) @ R(-7, 'Z'), 0.21, 0.3)
    use(A, coll, "Bill", (0.06, 1.88, zt + 0.01))
    noodle_bowl(K, T(0.2, 1.98, zt))
    use(A, coll, "Noodles", (0.2, 1.98, zt + 0.06))
    # 存折：绿皮小本，翻开扣着
    booklet(K, T(-0.26, 1.78, zt) @ R(-25, 'Z'), "BookletGreen", (0.09, 0.13, 0.006))
    use(A, coll, "Bankbook", (-0.26, 1.78, zt + 0.01))
    ashtray(K, T(-0.42, 1.8, zt))
    desk_lamp(K, A, coll, T(-0.45, 1.98, zt) @ R(-30, 'Z'))
    # 合影：立着的木相框（1986 年艇员合影）
    photo_stand(K, T(0.07, 2.08, zt) @ R(-4, 'Z'))
    use(A, coll, "Photo", (0.07, 2.08, zt + 0.1))
    use(A, coll, "Radio", (-0.4, 2.05, zt + 0.12))
    use(A, coll, "Thermos", (0.47, 1.78, zt + 0.2))
    use(A, coll, "Clock", (0.38, 2.02, zt + 0.09))
    # 插座在桌子右边墙上，台灯、收音机的电线拖过去
    sk = frame(V((0.72, Y1, 0.95)), V((0, -1, 0)))
    RK.socket(K, sk)
    sweep(K["WireBlack"], catmull([V((-0.45, 2.05, zt + 0.01)), V((-0.2, 2.14, zt + 0.005)), V((0.3, 2.15, zt + 0.003)),
                                   V((0.58, 2.16, zt + 0.002)), V((0.62, 2.18, zt - 0.1)), V((0.7, Y1 - 0.02, 0.9)),
                                   V((0.72, Y1 - 0.02, 0.95))], 6), circle_profile(0.003, 6))
    # 椅子
    anchor(A, coll, "Anchor_Chair", (0.0, 1.22, 0.0), (0.2, 1, 0))
    seat(A, coll, "Desk", (0.02, 1.15, 0.45 + 0.74), (0.0, 1, 0), (0.25, 0.75, 0.0))


def booklet(K, M, key, size):
    w, h, d = size
    rbox(K[key], w, h, d, M @ T(0, 0, d / 2), r=0.002, seg=2)
    rbox(K["PaperWhite"], w - 0.006, h - 0.006, d - 0.002, M @ T(0.002, 0, d / 2), r=0.0, seg=1)


def plate(K, M):
    lathe(K["Enamel"], [(0.0, 0.0), (0.06, 0.0), (0.1, 0.012), (0.105, 0.016), (0.1, 0.016), (0.058, 0.004),
                        (0.0, 0.004)], 40, M)


def pager(K, M):
    """传呼机（汉显 BP 机）：黑色塑料小盒子，顶上一块灰绿的液晶屏（Paper_Pager，Godot 里显示传呼内容），
    侧面两个按钮，背后皮带夹。整个单独成对象 Hide_Pager（Godot 里来传呼时在桌上震着挪动）。"""
    def geo(bm):
        rbox(bm, 0.052, 0.078, 0.02, T(0, 0, 0.01), r=0.006, seg=3)
        rbox(bm, 0.044, 0.02, 0.006, T(0, -0.03, 0.021), r=0.002, seg=1)
        for k in range(2):
            rbox(bm, 0.004, 0.012, 0.006, T(0.027, 0.015 - k * 0.018, 0.012), r=0.0015, seg=1)
    ob = K.separate("Hide_Pager", "Bakelite", geo)
    ob.matrix_world = M
    scr = RK.paper_quad(K, "Pager", M @ T(0, 0.012, 0.0201), 0.04, 0.025)
    return ob


def noodle_bowl(K, M):
    """吃完的方便面：白色泡沫碗、一把塑料叉子斜插着，碗底剩一点汤。"""
    lathe(K["PlasticWhite"], [(0.0, 0.0), (0.045, 0.0), (0.06, 0.07), (0.064, 0.075), (0.059, 0.075), (0.041, 0.006),
                              (0.0, 0.006)], 36, M)
    cylinder(K["Tea"], 0.046, 0.001, 24, M @ T(0, 0, 0.014))
    sweep(K["PlasticWhite"], [M @ V((-0.01, 0.0, 0.01)), M @ V((0.05, 0.02, 0.12))], rect_profile(0.008, 0.002, 0.0008))
    # 撕下来的碗盖揉成一团扔在边上
    uvsphere(K["Noodle"], 0.025, 10, 6, M @ T(0.09, -0.04, 0.018) @ S(1.2, 0.9, 0.7))


def ashtray(K, M):
    """烟灰缸：一个铁皮罐头盖子，里面七八个烟头、一层烟灰。"""
    rng = random.Random(4)
    lathe(K["Steel"], [(0.0, 0.0), (0.045, 0.0), (0.048, 0.012), (0.046, 0.012), (0.043, 0.002), (0.0, 0.002)], 32, M)
    cylinder(K["Ash"], 0.04, 0.003, 20, M @ T(0, 0, 0.002))
    for k in range(8):
        a = rng.uniform(0, 6.28)
        r = rng.uniform(0.0, 0.03)
        Mc = M @ T(math.cos(a) * r, math.sin(a) * r, 0.007) @ R(rng.uniform(0, 360), 'Z') @ R(rng.uniform(70, 95), 'Y')
        L = rng.uniform(0.012, 0.03)
        cylinder(K["Filter"], 0.0038, 0.02, 8, Mc)
        cylinder(K["Cigarette"], 0.0038, L, 8, Mc @ T(0, 0, 0.02))
        cylinder(K["Ash"], 0.0039, 0.002, 8, Mc @ T(0, 0, 0.02 + L))


def desk_lamp(K, A, coll, M):
    """台灯（八十年代的样子）：圆铁底座、一根弯过来的蛇管、绿漆的喇叭形灯罩。"""
    lathe(K["WindowSteel"], [(0.0, 0.0), (0.075, 0.0), (0.078, 0.012), (0.06, 0.03), (0.012, 0.035), (0.0, 0.035)],
          36, M)
    path = [M @ V((0.0, 0.0, 0.03)), M @ V((0.0, 0.0, 0.2)), M @ V((0.03, 0.04, 0.38)), M @ V((0.09, 0.1, 0.42)),
            M @ V((0.15, 0.13, 0.38))]
    sweep(K["Chrome"], catmull(path, 8), circle_profile(0.007, 10))
    tip = path[-1]
    d = (M.to_3x3() @ V((0.6, 0.4, -1.0))).normalized()
    Fs = frame(tip, d)
    lathe(K["WindowSteel"], [(0.012, -0.01), (0.02, 0.0), (0.03, 0.03), (0.07, 0.1), (0.072, 0.102)], 40, Fs)
    lathe(K["FixtureWhite"], [(0.07, 0.099), (0.03, 0.029), (0.019, -0.002)], 40, Fs)
    uvsphere(K["LampGlass"], 0.022, 16, 8, Fs @ T(0, 0, 0.05))
    light(A, coll, "Light_DeskLamp", Fs @ V((0, 0, 0.06)), d)


def photo_stand(K, M):
    """立在桌上的木相框（背后一根撑脚）。照片是 Paper_Photo。"""
    w, h = 0.15, 0.11
    F = M @ T(0, 0, 0.005) @ R(75, 'X')   # 往后仰 15 度立着，正面朝 -Y
    fw = 0.014
    for (cx, cy, sx, sy) in ((0, h / 2 - fw / 2, w, fw), (0, -h / 2 + fw / 2, w, fw), (-w / 2 + fw / 2, 0, fw, h),
                             (w / 2 - fw / 2, 0, fw, h)):
        rbox(K["WoodDark"], sx, sy, 0.012, F @ T(cx, h / 2 + cy, 0), r=0.002, seg=1)
    RK.paper_quad(K, "Photo", F @ T(0, h / 2, 0.002), w - 2 * fw, h - 2 * fw)
    box(K["Glass"], w - 2 * fw, h - 2 * fw, 0.0015, F @ T(0, h / 2, 0.005))
    rbox(K["Cardboard"], w - 0.01, h - 0.01, 0.003, F @ T(0, h / 2, -0.005), r=0.0, seg=1)
    sweep(K["Cardboard"], [F @ V((0, h * 0.6, -0.006)), M @ V((0, 0.07, 0.0))], rect_profile(0.03, 0.003, 0.0005))


# ============================================================================ 东墙：脸盆架、衣柜
def washstand(K, A, coll):
    """铁管脸盆架（刷淡绿漆）：三条腿撑着一个放脸盆的圈，后面两根立柱往上，一根毛巾杆，顶上一面小镜子。
    镜面单独成对象 Mirror_Glass（Godot 里换成真的镜面反射，玩家在这里看见自己的脸）。"""
    cx, cy = WASH
    xw = X1 - 0.04
    ring_z = 0.72
    r = 0.19
    tube = circle_profile(0.008, 10)
    key = "FixtureWhite"
    # 放盆的圈（圆心离墙 r + 4 厘米）
    c = V((xw - r - 0.05, cy, ring_z))
    torus(K[key], r, 0.008, 40, 8, T(*c))
    for k in range(3):
        a = math.radians(90 + 120 * k)
        top = c + V((math.cos(a) * r, math.sin(a) * r, 0))
        foot = c + V((math.cos(a) * (r + 0.08), math.sin(a) * (r + 0.08), -ring_z))
        sweep(K[key], [top + V((0, 0, 0.02)), foot], tube)
    # 两根立柱靠墙，往上 1.85 米
    for dy in (-0.16, 0.16):
        sweep(K[key], [V((xw - 0.03, cy + dy, 0.0)), V((xw - 0.03, cy + dy, 1.85))], tube)
        sweep(K[key], [V((xw - 0.03, cy + dy, ring_z)), c + V((0.12, dy * 0.6, 0))], tube)
    # 毛巾杆
    sweep(K[key], [V((xw - 0.03, cy - 0.2, 1.22)), V((xw - 0.03, cy + 0.2, 1.22))], circle_profile(0.006, 8))
    # 镜子：木框，镜面朝屋里（-X）
    mw, mh = 0.3, 0.38
    F = frame(V((xw - 0.045, cy, MIRROR_Z)), V((-1, 0, 0)))
    for (ox, oy, sx, sy) in ((0, mh / 2 - 0.0125, mw, 0.025), (0, -mh / 2 + 0.0125, mw, 0.025),
                             (-mw / 2 + 0.0125, 0, 0.025, mh), (mw / 2 - 0.0125, 0, 0.025, mh)):
        rbox(K["WoodDark"], sx, sy, 0.02, F @ T(ox, oy, 0), r=0.003, seg=2)
    rbox(K["Cardboard"], mw - 0.01, mh - 0.01, 0.006, F @ T(0, 0, -0.008), r=0.0, seg=1)

    def glass(bm):
        uv = bm.loops.layers.uv.new("UVMap")
        w2, h2 = (mw - 0.05) / 2, (mh - 0.05) / 2
        vs = [bm.verts.new(F @ V((x, y, 0.002))) for x, y in ((-w2, -h2), (w2, -h2), (w2, h2), (-w2, h2))]
        f = bm.faces.new(vs)
        for loop, uvc in zip(f.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
            loop[uv].uv = uvc
    K.separate("Mirror_Glass", "Mirror", glass, smooth=False, recalc=False)
    use(A, coll, "Mirror", F @ V((0, 0, 0.0)))
    # 盆、牙缸、肥皂盒
    RK.basin(K, T(*(c + V((0, 0, -0.07)))))
    cylinder(K["Tea"], 0.12, 0.001, 32, T(*(c + V((0, 0, -0.04)))))   # 盆里一点脏水
    enamel_mug(K, T(xw - 0.08, cy + 0.16, ring_z + 0.01) @ R(200, 'Z'), words=False, seed=9)
    sweep(K["PlasticWhite"], [V((xw - 0.08, cy + 0.16, ring_z + 0.05)), V((xw - 0.07, cy + 0.17, ring_z + 0.17))],
          rect_profile(0.008, 0.005, 0.002))
    # 毛巾搭在杆上
    towel_over(K, "wash_towel", V((xw - 0.03, cy - 0.18, 1.22)), V((xw - 0.03, cy + 0.18, 1.22)), 0.22, 0.2,
               key="Towel", seed=4)
    anchor(A, coll, "Anchor_Bucket", (xw - 0.25, cy - 0.38, 0.0), (-1, 0, 0))


def wardrobe(K, A, coll):
    """帆布简易衣柜：白色铁管架子，罩一层灰蓝帆布（中间一条拉链，布面绷得不平，下摆起皱）。"""
    x0, x1 = X1 - 0.47, X1 - 0.03
    y0, y1 = -1.12, -0.18
    h = 1.72
    tube = circle_profile(0.009, 8)
    for x in (x0, x1):
        for y in (y0, y1):
            sweep(K["FixtureWhite"], [V((x, y, 0.0)), V((x, y, h))], tube)
    # 帆布：四面和顶，面上起伏（朝向自己排好，单独成对象不重算法线）
    res = 0.04
    rng = random.Random(3)
    noise = _noise2(rng, 6, 3.0, 9.0)
    sides = [((x0, y0), (x0, y1), (-1, 0)), ((x1, y1), (x1, y0), (1, 0)), ((x0, y1), (x1, y1), (0, 1)),
             ((x1, y0), (x0, y0), (0, -1))]

    def canvas(bm):
        for (a, b, nrm) in sides:
            canvas_side(bm, a, b, nrm)

    def canvas_side(bm, a, b, nrm):
        L = math.dist(a, b)
        nu, nv = int(L / res) + 1, int(h / res) + 1
        uvl = bm.loops.layers.uv.get("UVMap") or bm.loops.layers.uv.new("UVMap")
        rows = []
        for j in range(nv):
            z = 0.02 + (h - 0.02) * j / (nv - 1)
            row = []
            for i in range(nu):
                u = i / (nu - 1)
                bulge = 0.02 * math.sin(math.pi * u) * math.sin(math.pi * (z / h)) + 0.006 * noise(u * L, z)
                sag = 0.012 * max(0.0, 0.2 - z) / 0.2 * math.sin(u * 23)
                row.append(bm.verts.new((a[0] + (b[0] - a[0]) * u + nrm[0] * (0.012 + bulge + sag),
                                         a[1] + (b[1] - a[1]) * u + nrm[1] * (0.012 + bulge + sag), z)))
            rows.append(row)
        for j in range(nv - 1):
            for i in range(nu - 1):
                f = bm.faces.new([rows[j][i], rows[j][i + 1], rows[j + 1][i + 1], rows[j + 1][i]])
                for loop, (di, dj) in zip(f.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
                    loop[uvl].uv = (L * (i + di) / (nu - 1), h * (j + dj) / (nv - 1))   # 布纹 UV 用米
                f.normal_update()
                if f.normal.dot(V((nrm[0], nrm[1], 0))) < 0:
                    f.normal_flip()
    K.separate("Cloth_Canvas", "Canvas", canvas, recalc=False)
    rbox(K["Canvas"], x1 - x0 + 0.03, y1 - y0 + 0.03, 0.02, T((x0 + x1) / 2, (y0 + y1) / 2, h + 0.01), r=0.01, seg=2)
    # 拉链：朝屋里那面（-X）中间一道
    sweep(K["Dark"], [V((x0 - 0.035, (y0 + y1) / 2, 0.08)), V((x0 - 0.035, (y0 + y1) / 2, h - 0.04))],
          rect_profile(0.004, 0.012, 0.001))
    rbox(K["Steel"], 0.006, 0.012, 0.03, T(x0 - 0.04, (y0 + y1) / 2, 1.1), r=0.002, seg=1)
    # 顶上：一只旧皮箱
    anchor(A, coll, "Anchor_Suitcase", ((x0 + x1) / 2, (y0 + y1) / 2, h + 0.02), (-1, 0, 0))
    use(A, coll, "Wardrobe", (x0 - 0.05, (y0 + y1) / 2, 1.2))


def towel_over(K, tag, p0, p1, hang_a, hang_b, key="Towel", seed=1, res=0.015, frames=110, mass=0.3, bending=0.08):
    """搭在一根横杆 / 晾衣绳（p0 → p1）上的一块布：两边各垂下 hang_a、hang_b。布料模拟。"""
    p0, p1 = V(p0), V(p1)
    along = (p1 - p0).normalized()
    across = along.cross(V((0, 0, 1))).normalized()
    rng = random.Random(seed)
    noise = _noise2(rng, 5, 6.0, 18.0)
    L = (p1 - p0).length
    nu, nv = int(L / res) + 1, int((hang_a + hang_b) / res) + 1
    co, uv = [], []
    for j in range(nv):
        for i in range(nu):
            s = -hang_a + (hang_a + hang_b) * j / (nv - 1)
            p = p0 + along * (L * i / (nu - 1)) + across * s + V((0, 0, 0.02 + 0.006 * noise(i * res, s)))
            co.append(tuple(p))
            uv.append((i * res, (j * res)))
    co = np.array(co)
    faces = grid(nu, nv)
    bar = bmesh.new()
    mid = (p0 + p1) / 2
    bmesh.ops.create_cube(bar, size=1.0, matrix=frame(mid, along) @ S(0.01, 0.01, L + 0.1))
    # 布要软（弯曲刚度低）、阻尼小，不然搭在绳上撑成一个帐篷，垂不下来
    out = simulate(f"dorm_{tag}", co, faces, [Collider(bar, outer=0.004, friction=80.0)], frames=frames,
                   mass=mass, tension=15.0, bending=bending, quality=7, distance=0.003, damping=1.0)
    cloth_object(K.uid(f"Cloth_{tag}"), K.coll, K.M[key], out, faces, np.array(uv), thick=0.004, subsurf=1)


# ============================================================================ 西南角：碗柜、电炉；晾衣绳
def kitchen(K, A, coll):
    anchor(A, coll, "Anchor_Cabinet", (-1.0, Y0 + 0.33, 0.0), (0, 1, 0))
    top = 1.181
    hot_plate(K, T(-1.25, Y0 + 0.3, top))
    anchor(A, coll, "Anchor_Pot", (-1.25, Y0 + 0.3, top + 0.06), (0.4, 1, 0))
    for k in range(3):
        lathe(K["Enamel"], [(0.0, 0.0), (0.035, 0.0), (0.06, 0.05), (0.062, 0.055), (0.058, 0.055), (0.033, 0.005),
                            (0.0, 0.005)], 32, T(-0.82, Y0 + 0.28, top + 0.018 * k))
    # 酱油瓶、一罐咸菜、两包方便面
    lathe(K["Bottle"], [(0.0, 0.0), (0.03, 0.0), (0.03, 0.16), (0.012, 0.2), (0.011, 0.24), (0.0, 0.24)], 20,
          T(-0.62, Y0 + 0.34, top))
    lathe(K["Glass"], [(0.0, 0.0), (0.05, 0.0), (0.05, 0.14), (0.04, 0.15), (0.0, 0.15)], 24, T(-0.68, Y0 + 0.2, top))
    cylinder(K["Plastic"], 0.042, 0.02, 24, T(-0.68, Y0 + 0.2, top + 0.15))
    for k in range(2):
        rbox(K["Plastic"], 0.14, 0.11, 0.035, T(-0.95, Y0 + 0.22, top + 0.018 + 0.036 * k) @ R(8 * k, 'Z'),
             r=0.012, seg=2)
    use(A, coll, "Stove", (-1.25, Y0 + 0.3, top + 0.1))
    # 晾衣绳：西墙到东墙一根铁丝，挂着毛巾、汗衫、两只袜子
    p0 = V((X0 + 0.01, -0.45, 2.18))
    p1 = V((X1 - 0.01, -0.55, 2.14))
    mid = (p0 + p1) / 2 - V((0, 0, 0.05))
    sweep(K["Steel"], catmull([p0, mid, p1], 10), circle_profile(0.0015, 6))
    for p in (p0, p1):
        RK.nail(K, frame(p, V((1 if p.x < 0 else -1, 0, 0))))
    line_at = lambda t: p0 + (p1 - p0) * t - V((0, 0, 0.05 * math.sin(math.pi * t)))  # noqa: E731
    towel_over(K, "line_towel", line_at(0.12), line_at(0.24), 0.3, 0.26, key="Towel", seed=7)
    towel_over(K, "line_shirt", line_at(0.42), line_at(0.6), 0.34, 0.3, key="Undershirt", seed=8, res=0.018)
    for k, t in enumerate((0.75, 0.8)):
        towel_over(K, f"line_sock{k}", line_at(t), line_at(t + 0.02), 0.22, 0.04, key="Sock", seed=9 + k,
                   res=0.008, mass=0.12)
        q = line_at(t + 0.01)
        rbox(K["PlasticWhite"], 0.012, 0.008, 0.05, T(*(q + V((0, 0, 0.01)))), r=0.002, seg=1)


def hot_plate(K, M):
    """电炉：铁皮圆座，上面一块耐火土的盘，盘上一圈圈槽里盘着电炉丝。"""
    lathe(K["Steel"], [(0.0, 0.0), (0.1, 0.0), (0.105, 0.04), (0.11, 0.045), (0.0, 0.045)], 36, M)
    cylinder(K["Concrete"], 0.095, 0.012, 36, M @ T(0, 0, 0.045))
    pts = [M @ V((math.cos(a) * (0.02 + 0.07 * a / (8 * math.pi)), math.sin(a) * (0.02 + 0.07 * a / (8 * math.pi)),
                  0.058)) for a in [8 * math.pi * k / 200 for k in range(201)]]
    sweep(K["Coil"], pts, circle_profile(0.002, 5))


# ============================================================================ 墙上、头顶
def walls_and_ceiling(K, A, coll, room):
    # 日光灯（靠窗这边）、吊扇（屋子中间）
    RK.fluorescent(K, A, coll, (0.2, 0.75, H), (1, 0, 0), "Main")
    RK.ceiling_fan(K, A, coll, (0.0, -0.45, H), rod=0.42, name="Fan", blade_len=0.55)
    # 明线：开关 → 沿南墙上去 → 顶上往北拐到日光灯、往吊扇分一路
    sw_x = X1 - 0.35
    RK.wire_run(K, [V((sw_x, Y0, 1.42)), V((sw_x, Y0, H - 0.04))], normal=(0, 1, 0))
    RK.wire_run(K, [V((sw_x, Y0 + 0.03, H)), V((sw_x, -0.45, H)), V((0.08, -0.45, H))], normal=(0, 0, -1))
    RK.wire_run(K, [V((sw_x, -0.45, H)), V((sw_x, 0.75, H)), V((0.85, 0.75, H))], normal=(0, 0, -1))
    RK.wire_run(K, [V((X1 - 0.18, Y0, 1.42)), V((X1 - 0.18, Y0, H - 0.04))], normal=(0, 1, 0), pair=False)
    # 墙上：挂历（北墙窗户右边）、奖状（南墙碗柜上面）
    RK.nail(K, frame(V((1.15, Y1, 1.92)), V((0, -1, 0))))
    RK.paper_quad(K, "Calendar", frame(V((1.15, Y1 - 0.012, 1.55)), V((0, -1, 0))) @ R(-1.5, 'Z'), 0.38, 0.55,
                  curl=0.02, segs=10)
    use(A, coll, "Calendar", (1.15, Y1 - 0.05, 1.55))
    RK.picture_frame(K, room.frame("S", X1 - (-1.0), 2.05), 0.5, 0.36, paper="Award", frame_key="WoodDark", tilt=4)
    use(A, coll, "Award", room.at("S", X1 + 1.0, 1.85, 0.06))
    # 西墙上：床头上方一块搁板（两个三角铁架），上面书、饼干铁盒、一个旧收音机盒子
    for y in (0.0, 0.9):
        sweep(K["Steel"], [V((X0 + 0.005, y, 1.6)), V((X0 + 0.005, y, 1.78)), V((X0 + 0.2, y, 1.78)),
                           V((X0 + 0.005, y, 1.6))], rect_profile(0.012, 0.025, 0.002))
    rbox(K["WoodLight"], 0.24, 1.25, 0.02, T(X0 + 0.12, 0.45, 1.79), r=0.003, seg=1)
    rng = random.Random(5)
    yb = -0.08
    for k in range(9):
        th = rng.uniform(0.018, 0.04)
        hh = rng.uniform(0.17, 0.23)
        col = ["BookletGreen", "Booklet", "PaperWhite", "Cardboard", "WoodDark"][k % 5]
        rbox(K[col], 0.15, th, hh, T(X0 + 0.1, yb + th / 2, 1.8 + hh / 2) @ R(rng.uniform(-2, 2), 'X'), r=0.002, seg=1)
        yb += th + 0.002
    cylinder(K["ThermosRed"], 0.09, 0.07, 32, T(X0 + 0.12, 0.62, 1.8))
    rbox(K["Cardboard"], 0.18, 0.25, 0.12, T(X0 + 0.11, 0.9, 1.86), r=0.004, seg=1)
    # 门边：一双胶靴、一把黑伞挂在钉子上、拖把靠墙
    anchor(A, coll, "Anchor_Boots", (0.2, Y0 + 0.25, 0.0), (1, 0.3, 0))
    RK.nail(K, frame(V((0.38, Y0, 1.65)), V((0, 1, 0))))
    umbrella(K, T(0.38, Y0 + 0.06, 1.66))
    mop(K, V((-0.25, Y0 + 0.08, 0.0)))
    anchor(A, coll, "Anchor_Trash", (0.15, -1.55, 0.0), (0, 1, 0))


def umbrella(K, M):
    """收起来的黑布伞，伞把挂在钉子上（还是湿的，伞尖底下一小滩水）。"""
    sweep(K["Bakelite"], catmull([M @ V((0.0, 0.0, 0.0)), M @ V((0.03, 0.0, -0.02)), M @ V((0.03, 0.0, -0.06)),
                                  M @ V((0.0, 0.0, -0.08))], 6), circle_profile(0.008, 10))
    lathe(K["Dark"], [(0.0, -0.08), (0.012, -0.1), (0.035, -0.25), (0.04, -0.45), (0.03, -0.7), (0.008, -0.86),
                      (0.0, -0.9)], 12, M @ T(0.0, 0.0, 0.0) @ S(1, 0.8, 1))


def mop(K, base):
    """拖把：木杆靠在墙上，底下一团布条。"""
    top = base + V((0.08, -0.06, 1.25))
    sweep(K["WoodRaw"], [base + V((0, 0.12, 0.08)), top], circle_profile(0.012, 10))
    rng = random.Random(2)
    for k in range(26):
        a = rng.uniform(0, 6.28)
        q = base + V((math.cos(a) * 0.05, 0.12 + math.sin(a) * 0.05, 0.0))
        sweep(K["Undershirt"], catmull([base + V((0, 0.12, 0.1)), base + V((math.cos(a) * 0.03, 0.12 + math.sin(a) * 0.03,
                                                                              0.05)), q], 4), circle_profile(0.006, 5))


# ============================================================================ 走廊
def corridor(K, A, coll):
    """筒子楼的公共走廊：两边一扇扇门，门口堆着蜂窝煤、鞋、水桶；顶上隔老远一个灯泡（坏了一个）。"""
    rng = random.Random(11)
    doors = [("N", -2.2, "205", "WoodDark"), ("S", -1.5, "206", "DoorBlue"), ("S", 1.6, "208", "WoodLight"),
             ("N", 3.0, "209", "DoorBlue")]
    for side, x, num, key in doors:
        y = CY1 if side == "N" else CY0
        n = V((0, -1, 0)) if side == "N" else V((0, 1, 0))
        F = frame(V((x, y, 0.0)), n, V((0, 0, 1)))
        RK.wood_door(K, F, 0.9, 2.0, leaf=key, jamb=key, hinge_right=True, name=K.uid("Cor_Door"), knob=True,
                     bolt=False)
        K.text(num, F @ T(0, 1.65, 0.03), 0.05, key="Silk", font=FONT_SANS)
        # 门口的东西
        stuff = rng.choice(["coal", "shoes", "bucket"])
        p = F @ V((-0.75, 0.0, 0.25))
        if stuff == "coal":
            briquettes(K, T(*p), rng)
        elif stuff == "shoes":
            for k in range(2):
                rbox(K["Rubber"], 0.1, 0.27, 0.06, T(*(p + V((0.12 * k, 0, 0.03)))) @ R(rng.uniform(-20, 20), 'Z'),
                     r=0.02, seg=2)
        else:
            lathe(K["Plastic"], [(0.0, 0.0), (0.12, 0.0), (0.15, 0.3), (0.142, 0.3), (0.112, 0.012), (0.0, 0.01)], 28,
                  T(*p))
    # 我们这扇门对面墙上：一个灯泡（吊在一根花线上）
    for x, ok in ((-1.0, True), (2.6, False)):
        top = V((x, (CY0 + CY1) / 2, H))
        bot = top - V((0, 0, 0.45))
        sweep(K["Wire"], [top, bot], circle_profile(0.003, 6))
        lathe(K["Bakelite"], [(0.0, 0.0), (0.018, 0.0), (0.02, 0.05), (0.0, 0.052)], 16, T(*bot) @ R(180, 'X'))
        anchor(A, coll, "Anchor_CorBulb" if ok else "Anchor_CorBulbDead", tuple(bot - V((0, 0, 0.05))), (0, -1, 0))
        if ok:
            light(A, coll, "Light_Corridor", bot - V((0, 0, 0.09)), (0, 0, -1))
    # 走廊东头窗外的路灯光
    light(A, coll, "Light_CorWindow", (CX1 - 0.2, CY0 + 0.9, 1.6), (-1, 0, -0.2))


def briquettes(K, M, rng):
    """一摞蜂窝煤（12 个孔的圆饼）。"""
    for k in range(rng.randint(4, 7)):
        Mk = M @ T(rng.uniform(-0.005, 0.005), rng.uniform(-0.005, 0.005), 0.08 * k) @ R(rng.uniform(0, 30), 'Z')
        cylinder(K["Briquette"], 0.06, 0.078, 20, Mk)
        for i in range(12):
            a = 2 * math.pi * i / 12
            r = 0.035 if i % 2 else 0.018
            cylinder(K["Dark"], 0.006, 0.0005, 6, Mk @ T(math.cos(a) * r, math.sin(a) * r, 0.0785))


# ============================================================================ 窗外
def outside(K, A, coll):
    """窗外：二楼底下的院子（湿地面、一滩滩水），院墙，一盏路灯；远处是停工的船厂：龙门吊、船台上一条半截的船壳。"""
    g = GROUND
    abox(K["Ground"], -40, 40, Y1 + WT, 90, g - 0.1, g)
    # 楼的外墙（往两边延伸），一楼几扇黑窗户、楼上几扇亮着灯的窗户
    abox(K["Facade"], -20, 20, Y1 + WT - 0.01, Y1 + WT, g, -0.0 + WIN[2] - 1.2)
    for x in (-6.0, -3.2, 3.2, 6.0):
        for z, lit in ((WIN[2] + 0.6, x in (-3.2, 6.0)), (g + 1.6, False), (WIN[2] + 3.8, x == 3.2)):
            abox(K["NeighborWindow" if lit else "Dark"], x - 0.7, x + 0.7, Y1 + WT + 0.01, Y1 + WT + 0.02, z - 0.7,
                 z + 0.7)
    # 院墙：离楼 14 米，2.4 米高，顶上插着碎玻璃
    wy = Y1 + 14.0
    abox(K["Brick"], -40, 40, wy, wy + 0.24, g, g + 2.4)
    # 路灯：院子里，窗户右前方
    lp = V((4.5, Y1 + 8.0, g))
    sweep(K["IronBar"], [lp, lp + V((0, 0, 6.5)), lp + V((-0.4, -0.3, 6.8)), lp + V((-1.1, -0.6, 6.85))],
          circle_profile(0.06, 10))
    head = lp + V((-1.2, -0.65, 6.78))
    rbox(K["IronBar"], 0.45, 0.22, 0.12, T(*head) @ R(30, 'Z'), r=0.03, seg=2)
    rbox(K["StreetLamp"], 0.36, 0.16, 0.02, T(*(head - V((0, 0, 0.065)))) @ R(30, 'Z'), r=0.01, seg=1)
    light(A, coll, "Light_Street", head - V((0, 0, 0.1)), (0, 0, -1))
    # 龙门吊：离窗户 80 米，两条门腿、顶上一根大梁、一个小车；大梁顶上一盏红色航空障碍灯
    cy = Y1 + 80.0
    for x in (-28.0, 30.0):
        for dy in (-4.0, 4.0):
            sweep(K["CraneRust"], [V((x, cy + dy, g)), V((x * 0.98, cy + dy * 0.3, g + 34))], rect_profile(1.0, 1.0, 0.05))
        for k in range(6):
            z0 = g + 5 * k
            sweep(K["CraneRust"], [V((x, cy - 4 + 2.6 * k / 6, z0)), V((x, cy + 4 - 2.6 * k / 6, z0 + 5))],
                  rect_profile(0.25, 0.25, 0.02))
    abox(K["CraneRust"], -34, 36, cy - 1.6, cy + 1.6, g + 34, g + 37.5)
    for k in range(28):
        x = -33 + 2.5 * k
        sweep(K["CraneRust"], [V((x, cy - 1.6, g + 34)), V((x + 1.25, cy - 1.6, g + 37.5))], rect_profile(0.2, 0.2, 0.02))
    abox(K["CraneRust"], 4, 9, cy - 2.2, cy + 2.2, g + 37.5, g + 40)
    light(A, coll, "Light_CraneRed", (0.0, cy, g + 38.0), (0, 0, -1))
    light(A, coll, "Light_CraneRed2", (30.0, cy, g + 38.0), (0, 0, -1))
    for x in (0.0, 30.0):
        uvsphere(K["NavLight"], 0.35, 12, 8, T(x, cy, g + 37.8))
    # 船台边上两盏照明灯（高杆，钠灯），照着船壳和吊车腿
    for x, y in ((-18.0, cy + 6.0), (14.0, cy - 4.0)):
        sweep(K["IronBar"], [V((x, y, g)), V((x, y, g + 18.0))], circle_profile(0.25, 8))
        rbox(K["StreetLamp"], 1.6, 0.6, 0.5, T(x, y - 0.5, g + 18.0), r=0.05, seg=1)
        light(A, coll, "Light_Yard", (x, y - 1.0, g + 17.6), (0.0, 0.6, -1.0))
    # 船台上的半截船壳
    hull = bmesh.new()
    bmesh.ops.create_cube(hull, size=1.0, matrix=T(-6, cy + 25, g + 7) @ S(60, 14, 14))
    for v in hull.verts:
        if v.co.z < g + 7:
            v.co.y += 0 if v.co.y > cy + 25 else 3.0
            v.co.x *= 0.85
    me = bpy.data.meshes.new("Ext_Ship")
    hull.to_mesh(me)
    hull.free()
    ob = bpy.data.objects.new("Ext_Ship", me)
    K.coll.objects.link(ob)
    me.materials.append(K.M["ShipHull"])
    # 远处城里零星的灯（一排小亮块）
    rng = random.Random(9)
    for k in range(40):
        x = rng.uniform(-150, 150)
        y = Y1 + rng.uniform(150, 260)
        z = g + rng.uniform(1, 22)
        abox(K["NeighborWindow"], x - 0.6, x + 0.6, y, y + 0.1, z - 0.5, z + 0.5)


# ============================================================================ 贴花
def decals(A, coll):
    def d(kind, pos, normal, up, w, h, depth=0.06):
        decal(A, coll, kind, pos, normal, up, w, h, depth)
    UP, NORTH = V((0, 0, 1)), V((0, 1, 0))
    # 地上：门口到床、床到桌子、桌子到脸盆架走出来的发白的路（地板漆磨掉了）
    for (x, y, a, L) in ((0.9, -1.6, 10, 1.2), (0.3, -0.5, 35, 1.6), (0.2, 0.8, 60, 1.1), (0.85, 0.9, -20, 0.9)):
        r = math.radians(a)
        d("FloorWear", (x, y, 0.0), UP, V((math.sin(r), math.cos(r), 0)), 0.7, L, 0.04)
    # 窗下的墙：雨水从窗框渗进来，一道道往下淌，墙裙上鼓起的漆皮
    for x in (-0.6, -0.2, 0.45):
        d("Streak", (x, Y1, 0.6), V((0, -1, 0)), UP, 0.28, 0.75, 0.05)
    d("Damp", (0.0, Y1, 0.5), V((0, -1, 0)), UP, 1.9, 1.0, 0.05)
    # 天花板：窗户上方一大块黄褐色的水渍圈；墙角发霉
    d("CeilStain", (0.2, Y1 - 0.5, H), V((0, 0, -1)), NORTH, 1.3, 0.9, 0.05)
    for (x, y) in ((X0, Y1), (X1, Y1), (X0, Y0)):
        d("Mold", (x * 0.98, y * 0.98, H - 0.15), V((-x, -y, 0)).normalized(), UP, 0.5, 0.45, 0.4)
    # 开关周围一圈手印的黑；门把手、门边被摸黑
    d("Grime", (X1 - 0.35, Y0, 1.4), V((0, 1, 0)), UP, 0.22, 0.3, 0.05)
    d("Grime", (X1 - 0.18, Y0, 1.38), V((0, 1, 0)), UP, 0.15, 0.2, 0.05)
    # 床边的墙裙上被床沿、人蹭出来的一道
    d("Scuff", (X0, 0.15, 0.55), V((1, 0, 0)), UP, 1.9, 0.3, 0.05)
    d("Scuff", (0.0, Y1, 0.75), V((0, -1, 0)), UP, 1.2, 0.18, 0.05)
    # 桌上：茶缸子印、烟头烫的印
    for x, y, rr in ((0.24, 1.72, 0.09), (-0.1, 1.95, 0.08), (0.42, 1.95, 0.085)):
        d("Ring", (x, y, DESK[4]), UP, V((math.sin(x * 9), math.cos(x * 9), 0)), rr, rr, 0.03)
    for x, y in ((-0.38, 1.72), (-0.47, 1.85)):
        d("Burn", (x, y, DESK[4]), UP, V((x, 1, 0)), 0.03, 0.03, 0.03)
    # 盆架底下的水渍
    d("Puddle", (WASH[0] - 0.25, WASH[1], 0.0), UP, NORTH, 0.6, 0.5, 0.03)
    # 伞底下一小滩水
    d("Puddle", (0.38, Y0 + 0.08, 0.0), UP, NORTH, 0.22, 0.18, 0.03)
    # 走廊：一串湿脚印，从楼梯口一直到我们门口，没有回去的
    steps = []
    x = CX0 + 0.2
    k = 0
    while x < (DOOR[0] + DOOR[1]) / 2 - 0.3:
        side = 0.11 if k % 2 else -0.11
        steps.append((x, (CY0 + CY1) / 2 + 0.25 + side, 90, "L" if k % 2 == 0 else "R"))
        x += 0.62
        k += 1
    xd = (DOOR[0] + DOOR[1]) / 2
    steps += [(xd - 0.12, CY1 - 0.55, 20, "L"), (xd + 0.1, CY1 - 0.25, 5, "R"), (xd - 0.08, CY1 - 0.1, 0, "L")]
    for (x, y, yaw, foot) in steps:
        a = math.radians(yaw)
        d("Boot" + foot, (x, y, 0.0), UP, V((-math.sin(a), math.cos(a), 0)), 0.11, 0.29, 0.03)
    d("Puddle", (xd, CY1 - 0.18, 0.0), UP, NORTH, 0.5, 0.35, 0.03)


# ============================================================================ 能站的地方、坐的地方
def layout(A, coll):
    walk(A, coll, -0.6, 1.12, -1.3, 0.85)       # 屋子中间（床和衣柜之间）
    walk(A, coll, 0.42, 1.0, 0.85, 1.45)        # 椅子右边、脸盆架前
    walk(A, coll, -0.62, -0.25, 0.85, 1.25)     # 椅子左边、床尾到桌角
    walk(A, coll, -0.35, 1.3, -1.95, -1.3)      # 门里
    # 门开着才能走：门洞、走廊
    for (x0, x1, y0, y1) in ((DOOR[0] + 0.12, DOOR[1] - 0.12, CY1 - 0.35, -1.9), (CX0 + 0.2, CX1 - 0.3, CY0 + 0.25,
                                                                                 CY1 - 0.25)):
        n = sum(1 for a in A if a.name.startswith("WalkDoor_"))
        A.append(empty(f"WalkDoor_{n:02d}", coll, T((x0 + x1) / 2, (y0 + y1) / 2, 0) @ S(x1 - x0, y1 - y0, 1)))
    spawn(A, coll, (-0.3, -0.2, 0.0), (0.5, 1, 0))
    use(A, coll, "Door", ((DOOR[0] + DOOR[1]) / 2, Y0 + 0.05, 1.05))
    use(A, coll, "Envelope", ((DOOR[0] + DOOR[1]) / 2 - 0.1, Y0 + 0.2, 0.02))
    anchor(A, coll, "Anchor_Envelope", ((DOOR[0] + DOOR[1]) / 2 - 0.1, Y0 + 0.18, 0.0), (0.3, 1, 0))


# ============================================================================ 入口
def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    preview_dir = argv[argv.index("--preview") + 1] if "--preview" in argv else None
    do_export = "--no-export" not in argv
    reset_scene()
    M = materials({})
    coll = collection("Dorm")
    A = []
    shell_k = Parts(coll, M, "Shell")
    K = Parts(coll, M, "Dorm")
    room, cor = shell(shell_k, A, coll)
    door(K, A, coll, room)
    window(K, A, coll, room)
    bed(K, A, coll)
    desk(K, A, coll)
    washstand(K, A, coll)
    wardrobe(K, A, coll)
    kitchen(K, A, coll)
    walls_and_ceiling(K, A, coll, room)
    corridor(K, A, coll)
    outside(K, A, coll)
    decals(A, coll)
    layout(A, coll)
    shell_k.flush(recalc=False)
    K.flush()
    os.makedirs(os.path.join(ROOT, "blender", "source"), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(ROOT, "blender", "source", "dorm.blend"))
    if preview_dir:
        os.makedirs(preview_dir, exist_ok=True)
        eye = 1.62
        for nm, pos, look, lens in (("dorm_desk", (0.3, -0.9, eye), (0.0, 2.2, 1.0), 20),
                                    ("dorm_bed", (0.9, 1.2, eye), (-1.3, -0.6, 0.6), 18),
                                    ("dorm_door", (-0.3, 1.0, eye), (1.0, -2.2, 1.1), 18),
                                    ("dorm_wash", (-0.2, 0.3, eye), (1.65, 1.05, 1.3), 22),
                                    ("dorm_up", (0.0, -1.2, 1.5), (0.0, 0.8, 2.9), 16),
                                    ("dorm_out", (0.0, 1.6, eye), (2.0, 60.0, 0.0), 30)):
            render_preview(os.path.join(preview_dir, nm + ".png"), V(pos), V(look), lens)
    if do_export:
        RK.export_room(coll, OUT, A)


main()
