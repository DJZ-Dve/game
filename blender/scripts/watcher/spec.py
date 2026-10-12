"""巨物「大眼」的共享规格：所有部件按这里的尺寸、曲面、骨骼、挂点、贴图组、材质名来做，合在一起才对得上。
这个文件由总装（gen_watcher.py）维护，部件作者只读不改；需要改的地方写进各自的报告里提。

外形（照潜渊症 Watcher 的思路原创）：一个直径十六七米、略扁的球形生物，比镇海号（14 米）还大一圈。
  - 外骨骼：漆黑的几丁质甲壳一片压一片裹住全身（参考鲎、大王具足虫、甲虫鞘翅那种真实的甲壳：
    有厚度、有棱、边缘往外卷、甲片之间是关节膜），甲的棱和边缘上长着往后倒的尖刺，背上的刺最长；
  - 甲片之间、眼睛周围露出暗红褐色的软肉（关节膜），湿、有褶；
  - 正面一只直径近 9 米的红色大眼：湿亮的角膜、有纹理的虹膜、会收缩的竖瞳（瞳孔大小由材质控制），
    上下两片肉质眼睑能闭上（闭眼时它的凝视就停了），眼睛能在眼窝里转、盯着你；
  - 两侧三对苍白的桨状附肢（参考海龟鳍肢、海蝎游泳足）：有关节、扁平、边缘薄，慢慢划水；这是它的弱点；
  - 腹面正中一个小小的虹吸口 / 滤食口（它靠滤食活着，不攻击）。
真实感：解剖统一（它是一只节肢动物式的生物：外骨骼 + 关节膜 + 附肢），大面干净、少数几处重点，
细节靠高模烘焙进贴图；不要满身噪声、不要对称得像机器做的。写实 PBR。

坐标（Blender）：+Y 朝前（眼睛），+Z 朝上，+X 朝右；原点在身体中心。单位米。
静止姿态（rest pose）：睁眼、眼睛朝正前、桨自然张开；动作全靠 Godot 里驱动骨骼（scripts/watcher_motion.gd）。

流程：高模烘焙低模（和鲨鱼那套一样）。每个部件出：
  - 低模（进游戏）：面数见 TRI_BUDGET；UV0 = 所在贴图组的图集（0～1，等密度，见 TEXSETS）；顶点组 = 骨骼权重；
  - 高模（只烘焙）：几毫米到几厘米的细节；点色属性 "Curv"（R 凹槽、G 凸棱）、"Area"（R 区域图，含义见 TEXSETS）。
  烘焙用 watcher/bakeutil.py：bake_set(组名, lows, highs, ...)，输出 assets/textures/watcher/<组>_normal.png、<组>_mask.png
  （R AO、G 凹槽、B 凸棱、A 区域图）和 <组>.json（1 个 UV 单位多少米）。
"""
import math
import zlib

import numpy as np
from mathutils import Vector, Matrix

V = Vector

# ---------------------------------------------------------------------------- 身体：略扁的椭球
AX, AY, AZ = 8.0, 8.6, 7.2      # 半轴（左右、前后、上下）


def surface(d):
    """方向 d（从中心出发）上的身体理想表面点（甲片底下那层肉的表面）。"""
    d = V(d).normalized()
    k = 1.0 / math.sqrt((d.x / AX) ** 2 + (d.y / AY) ** 2 + (d.z / AZ) ** 2)
    return d * k


def normal(p):
    """椭球表面某点的朝外法线。"""
    return V((p.x / AX ** 2, p.y / AY ** 2, p.z / AZ ** 2)).normalized()


def frame(d, offset=0.0, up=V((0, 0, 1))):
    """表面一点的局部坐标系：原点在表面（沿法线再往外 offset 米），Z = 朝外法线，Y 尽量朝 up 在切平面上的投影。"""
    p = surface(d)
    n = normal(p)
    y = up - n * up.dot(n)
    if y.length < 1e-6:
        y = V((0, 1, 0)) - n * n.y
    y.normalize()
    x = y.cross(n)
    m = Matrix.Identity(4)
    m.col[0][:3] = x
    m.col[1][:3] = y
    m.col[2][:3] = n
    m.col[3][:3] = p + n * offset
    return m


def lat_lon(p):
    """点 → (纬度, 经度)：纬度 -90°（腹）～ +90°（背），经度 0 = 正前（+Y）、+90° = 右（+X）、±180° = 正后。弧度。"""
    d = V(p).normalized()
    return math.asin(max(-1.0, min(1.0, d.z))), math.atan2(d.x, d.y)


def from_lat_lon(lat, lon):
    return V((math.cos(lat) * math.sin(lon), math.cos(lat) * math.cos(lon), math.sin(lat)))


# ---------------------------------------------------------------------------- 眼睛
EYE_CENTER = V((0.0, AY * 0.62, 0.3))   # 眼球往前鼓出身体约 1.3 米
EYE_R = 4.4                      # 眼球半径
SOCKET_ANGLE = math.radians(56)  # 从身体中心看，离 +Y 方向这个角度以内是眼窝（不长甲；肉质眼窝 + 眼睑）
EYE_TURN_MAX = math.radians(25)  # 眼球在眼窝里最多转多少（动作用；眼窝要留够空隙）
LID_CLOSE = math.radians(75)     # 眼睑从睁开到闭合转多少（上眼睑往下、下眼睑往上，绕过眼球中心的 X 轴）


def in_socket(d):
    """方向 d 是不是落在眼窝里（不长甲）。"""
    return V(d).normalized().angle(V((0, 1, 0))) < SOCKET_ANGLE


# ---------------------------------------------------------------------------- 桨
# 三对：(纬度, 经度) 是根部方向（右侧；左侧经度取负），length、width 是叶片尺寸（米），
# sweep：静止时往后掠的角度，droop：往下垂的角度
PADDLES = [
    dict(lat=math.radians(-18), lon=math.radians(70), length=9.0, width=3.2, sweep=math.radians(25), droop=math.radians(12)),
    dict(lat=math.radians(-24), lon=math.radians(95), length=10.5, width=3.6, sweep=math.radians(38), droop=math.radians(16)),
    dict(lat=math.radians(-18), lon=math.radians(122), length=8.5, width=3.0, sweep=math.radians(52), droop=math.radians(12)),
]
PADDLE_BONES = 3                 # 每支桨三节（根节、中节、叶片）


def paddle_root(i, side):
    p = PADDLES[i]
    return surface(from_lat_lon(p["lat"], side * p["lon"]))


def paddle_dir(i, side):
    """静止时桨伸出的方向：沿根部法线往外，再往后掠、往下垂。"""
    p = PADDLES[i]
    r = paddle_root(i, side)
    n = normal(r)
    out = V((n.x, 0.0, 0.0)).normalized() if abs(n.x) > 1e-3 else n
    back = V((0, -1, 0))
    d = out * math.cos(p["sweep"]) + back * math.sin(p["sweep"])
    d = d * math.cos(p["droop"]) + V((0, 0, -1)) * math.sin(p["droop"])
    return d.normalized()


def paddle_rest_points(i, side):
    """桨的骨链：PADDLE_BONES + 1 个点（根埋进身体 0.6 米，往外三节：根节 25%、中节 30%、叶片 45%）。"""
    r = paddle_root(i, side)
    d = paddle_dir(i, side)
    L = PADDLES[i]["length"]
    start = r - normal(r) * 0.6
    cuts = [0.0, 0.25, 0.55, 1.0]
    return [start + d * (0.6 + L * c) for c in cuts]


# ---------------------------------------------------------------------------- 腹面虹吸口
SIPHON_DIR = from_lat_lon(math.radians(-80), 0.0)   # 腹面正中略偏前
SIPHON_R = 1.1

# ---------------------------------------------------------------------------- 分区（谁负责哪一块）
# 甲壳（shell.py）：全身的外骨骼甲片（眼窝以外），甲片边缘、棱上的尖刺；每片甲是刚性的，权重全给 "Body"。
#   贴图组 "shell"。
# 肉（flesh.py）：甲片底下那层身体（甲片之间的关节膜露出来的部分要好看，完全被盖住的地方可以省面）、眼窝（眼球周围的肉）、
#   上下眼睑（权重 LidUp / LidLo，闭眼时盖住眼球、不穿模）、腹面虹吸口。桨根部的肉褶不归你（桨的人做）。贴图组 "flesh"。
# 桨（paddles.py）：三对桨，每支三节（权重 Paddle<L/R><i>_<k>，关节处混合），根部的肉褶盖住和身体的接缝。贴图组 "paddle"。
# 眼（eye.py）：眼球（巩膜、虹膜的起伏、瞳孔区域）+ 外面一层透明的角膜（单独物体，材质 M_WatcherCornea）；
#   权重全给 "Eye"。贴图组 "eye"。

# ---------------------------------------------------------------------------- 贴图组
# size：贴图边长；meters：目标的 1 个 UV 单位 = 多少米（atlas_uv 会写实际值到 json）
# mask.A（Area）各组的含义：shell = 刺 / 甲缘磨出的白（1）；flesh = 眼睑内侧和眼窝最湿的肉（1）；
#   paddle = 叶片薄处透光（1）；eye = 虹膜（1）/ 巩膜（0）
TEXSETS = {
    "shell": dict(size=4096, meters=48.0),
    "flesh": dict(size=4096, meters=40.0),
    "paddle": dict(size=2048, meters=24.0),
    "eye": dict(size=2048, meters=12.0),
}

MATERIALS = {
    "M_WatcherShell": ((0.03, 0.03, 0.035), 0.6),   # 漆黑的几丁质
    "M_WatcherFlesh": ((0.22, 0.10, 0.09), 0.4),    # 暗红褐的关节膜、眼窝、眼睑
    "M_WatcherPaddle": ((0.50, 0.42, 0.40), 0.45),  # 苍白的桨
    "M_WatcherEye": ((0.70, 0.05, 0.03), 0.2),      # 红色眼球（虹膜、巩膜靠贴图和着色器）
    "M_WatcherCornea": ((0.9, 0.9, 0.9), 0.02),     # 透明角膜
}
MATERIAL_TEXSET = {"M_WatcherShell": "shell", "M_WatcherFlesh": "flesh", "M_WatcherPaddle": "paddle",
                   "M_WatcherEye": "eye", "M_WatcherCornea": "eye"}

UV_MAIN = "UVMap"
TRI_BUDGET = {"shell": 35000, "flesh": 25000, "paddles": 12000, "eye": 6000}

# ---------------------------------------------------------------------------- 骨骼
def paddle_bone(i, side, k):
    return "Paddle%s%d_%d" % ("L" if side < 0 else "R", i, k)


def bones():
    """全部骨骼：[(名字, 头, 尾, 父骨名或 None)]。"""
    out = [("Body", V((0, -2.0, 0)), V((0, 2.0, 0)), None)]
    out.append(("Eye", EYE_CENTER, EYE_CENTER + V((0, EYE_R, 0)), "Body"))
    out.append(("LidUp", EYE_CENTER, EYE_CENTER + V((0, EYE_R * 0.8, EYE_R * 0.8)), "Body"))
    out.append(("LidLo", EYE_CENTER, EYE_CENTER + V((0, EYE_R * 0.8, -EYE_R * 0.8)), "Body"))
    for i in range(len(PADDLES)):
        for side in (-1, 1):
            pts = paddle_rest_points(i, side)
            parent = "Body"
            for k in range(PADDLE_BONES):
                nm = paddle_bone(i, side, k)
                out.append((nm, pts[k], pts[k + 1], parent))
                parent = nm
    return out


# ---------------------------------------------------------------------------- 工具
def assign_bone(ob, bone):
    vg = ob.vertex_groups.get(bone) or ob.vertex_groups.new(name=bone)
    vg.add([v.index for v in ob.data.vertices], 1.0, 'REPLACE')


def rng_for(name):
    return np.random.default_rng(zlib.crc32(name.encode()))


def fib_sphere(n):
    """单位球面上 n 个均匀分布的方向（斐波那契螺旋）。"""
    pts = []
    g = math.pi * (3 - math.sqrt(5))
    for i in range(n):
        z = 1 - 2 * (i + 0.5) / n
        r = math.sqrt(1 - z * z)
        a = g * i
        pts.append(V((r * math.cos(a), r * math.sin(a), z)))
    return pts
