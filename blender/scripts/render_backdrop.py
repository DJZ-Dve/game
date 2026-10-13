"""宿舍窗外的远景（150 米以外和天空）：Cycles 预渲染的全景条，Godot 里贴在一段半径 600 米的圆柱面上（scripts/story/dorm.gd）。

近处 150 米以内（院子、路灯、院墙、龙门吊、船台上的船壳）是 gen_dorm.py 的 3D 模型；这里只管更远的：
- 天：台风外围压得很低的雨云，两层（低空的碎积云底、上面一层整的），云底被城里的钠灯照成暗橙，离城越远越暗越灰
- 左边（西北）：白沙门县城——筒子楼、宿舍楼的剪影，十点五十了，零星几扇亮着的窗；几条街上的钠灯
- 正前方：船厂后半截——几座大车间、码头上的门座起重机（顶上红灯）、远一点的龙门吊，码头边的照明灯
- 右边（东北）：港湾、防波堤（头上一盏绿灯）、锚地里避风的几条船（甲板灯），对岸的山和山脚几点灯
- 雨雾：按距离加一层被灯光照亮的雾（后期在 numpy 里算：距离 → 透过率；雾的颜色取画面自己的大范围模糊——灯多的地方雾亮），
  灯、亮窗周围一圈光晕

相机在窗户中心的眼点，CENTRAL_CYLINDRICAL 全景：水平 ±U_DEG（以正北为中心，往东为正），竖直按 tan(仰角) 线性
（V_MIN ~ V_MAX，约 -5° ~ +40°）。改了这些要同步 scripts/story/dorm.gd 的 BACKDROP_*。

产出 assets/textures/backdrop/：
- dorm_night.exr   夜景（半精度 RGB，ZIP 压缩）6144 × 2048，约 38 像素/度
- dorm_flash.exr   闪电那一下（云里一大片冷白光）3072 × 1024：只亮一瞬，分辨率减半
- dorm_glow.png    发光的份额（8 位灰度）：每个像素里亮窗、灯和它们的光晕占夜景亮度的比例，Godot 里拿它让窗户偶尔灭、远处一盏灯闪

用法（慢，单独跑；不在 tools/rebuild_models.py 里）：
    Blender -b --factory-startup --python blender/scripts/render_backdrop.py [-- 参数]
      --scale 0.25        试渲：分辨率乘这个数（默认 1）
      --samples 64        采样数（默认 64，自适应 + OIDN 降噪）
      --only night|flash  只渲一张
      --preview DIR       顺带存一张简单色调映射过的 JPG 预览（看效果用）
      --no-save           不写 assets（试渲时配 --preview 用）
同样的参数每次渲出来一样（摆放用固定种子的随机数，Cycles 种子固定）。M4（10 核 GPU）上全分辨率：夜景约 2.5 分钟、
闪电版约 1 分钟，加上发光、距离两遍和后期，一共 4 分钟左右。渲完跑一遍 Godot --import。
"""
import math
import os
import random
import sys
import time

import bpy
import bmesh
import numpy as np
import OpenImageIO as oiio
from mathutils import Matrix, Vector as V

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "assets", "textures", "backdrop")

# ---------------------------------------------------------------------------- 和 dorm.gd / gen_dorm.py 同步
EYE = V((0.0, 2.34, 1.62))         # 窗户中心的眼点（Blender 坐标；gen_dorm.py 的窗 WIN 中心、玻璃那一层）
G = -3.65                          # 地面（宿舍在二楼，gen_dorm.py 的 GROUND）
U_DEG = 80.0                       # 水平：正北左右各 80°
W, H = 6144, 2048                  # 全分辨率（2 * U_DEG 度 → 每度 38.4 像素）
V_MIN = math.tan(math.radians(-5.0))
V_MAX = V_MIN + H / (W / math.radians(2 * U_DEG))   # 竖直和水平同样的像素密度（地平线附近）≈ tan(40.1°)
SODIUM = (1.0, 0.42, 0.12)
MIST = 20000.0                     # 天空算多远（米）
# 亮度：Cycles 里灯按常见的量级摆（钠灯几百瓦），成图整体乘 EXPOSE 落到游戏里的亮度（Godot 线性值，unshaded 直接输出）
EXPOSE = 0.1
HAZE_H = 8.0                       # 贴地雨雾层的厚度（米）
HAZE_L = 2500.0                    # 上面那层薄雾：e 倍衰减的距离（米）
# 雾的底色（Godot 线性值）：dorm_env.tres 的 fog_light_color (0.16, 0.1, 0.06) 转线性 × fog_light_energy 2 × 体积雾透过率约 0.8
HAZE_NIGHT = (0.030, 0.0136, 0.0068)
HAZE_FLASH = (0.20, 0.22, 0.27)
# 远处那盏快坏的钠灯（方位角、水平距离、灯杆高）：Godot 里它附近一圈跟着闪。改了同步 dorm.gd 的 BACKDROP_FLICKER
#（第三个数是灯头比眼睛高多少 = 灯杆高 + 0.3 + G - EYE.z）
FLICKER_LAMP = (-36.0, 230.0, 12.0)


def args():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []

    def get(k, d):
        return a[a.index(k) + 1] if k in a else d
    return {"scale": float(get("--scale", 1.0)), "samples": int(get("--samples", 64)), "only": get("--only", ""),
            "preview": get("--preview", ""), "save": "--no-save" not in a}


def polar(az, dist):
    """以眼点为原点：方位角（度，正北 0、往东为正）、水平距离 → (x, y)"""
    r = math.radians(az)
    return EYE.x + dist * math.sin(r), EYE.y + dist * math.cos(r)


# ============================================================================ 噪声（摆放、云底起伏、山脊线）
class Noise:
    def __init__(self, seed, n=256):
        self.g = np.random.RandomState(seed).rand(n, n)
        self.n = n

    def value(self, x, y):
        n = self.n
        x, y = np.asarray(x, float), np.asarray(y, float)
        xi, yi = np.floor(x).astype(int), np.floor(y).astype(int)
        fx, fy = x - xi, y - yi
        fx, fy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
        a, b = self.g[xi % n, yi % n], self.g[(xi + 1) % n, yi % n]
        c, d = self.g[xi % n, (yi + 1) % n], self.g[(xi + 1) % n, (yi + 1) % n]
        return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy

    def fbm(self, x, y, octaves=5, gain=0.5):
        s, amp, tot = 0.0, 1.0, 0.0
        for k in range(octaves):
            s = s + amp * self.value(x * 2 ** k + 17 * k, y * 2 ** k + 31 * k)
            tot += amp
            amp *= gain
        return s / tot


# ============================================================================ 材质
def _nodes(name):
    m = bpy.data.materials.new(name)
    if m.node_tree is None:          # Blender 5 起材质总是节点的，use_nodes 要废掉了
        m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    return m, nt, out


def mat_surface(name, color, rough=0.8, bump=0.0, bump_scale=1.0, rough_var=0.0):
    """哑光（或湿的）表面；bump、rough_var 用噪声做起伏、积水"""
    m, nt, out = _nodes(name)
    b = nt.nodes.new("ShaderNodeBsdfPrincipled")
    b.inputs["Base Color"].default_value = (*color, 1.0)
    b.inputs["Roughness"].default_value = rough
    if bump or rough_var:
        tc = nt.nodes.new("ShaderNodeTexCoord")
        nz = nt.nodes.new("ShaderNodeTexNoise")
        nz.inputs["Scale"].default_value = bump_scale
        nz.inputs["Detail"].default_value = 6.0
        nt.links.new(tc.outputs["Object"], nz.inputs["Vector"])
        if rough_var:
            mr = nt.nodes.new("ShaderNodeMapRange")
            mr.inputs["From Min"].default_value = 0.4
            mr.inputs["From Max"].default_value = 0.6
            mr.inputs["To Min"].default_value = rough
            mr.inputs["To Max"].default_value = rough + rough_var
            nt.links.new(nz.outputs["Fac"], mr.inputs["Value"])
            nt.links.new(mr.outputs["Result"], b.inputs["Roughness"])
        if bump:
            bp = nt.nodes.new("ShaderNodeBump")
            bp.inputs["Strength"].default_value = bump
            nt.links.new(nz.outputs["Fac"], bp.inputs["Height"])
            nt.links.new(bp.outputs["Normal"], b.inputs["Normal"])
    nt.links.new(b.outputs[0], out.inputs["Surface"])
    return m


def mat_emit():
    """发光：颜色和亮度都在顶点色（浮点）Col 里，一个材质管所有的窗、灯"""
    m, nt, out = _nodes("Emit")
    at = nt.nodes.new("ShaderNodeAttribute")
    at.attribute_name = "Col"
    e = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(at.outputs["Color"], e.inputs["Color"])
    e.inputs["Strength"].default_value = 1.0
    nt.links.new(e.outputs[0], out.inputs["Surface"])
    return m


def mat_cloud(name, albedo, scale, holes, flash_center, flash_r):
    """云底：漫反射（被城里的钠灯从下面照亮），噪声决定薄厚；holes > 0 时薄的地方透出上一层。
    闪电版：FlashAmt（值节点）× 离闪电中心的高斯 × 噪声 = 云里透出来的冷白光"""
    m, nt, out = _nodes(name)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1.0 / scale, 1.6 / scale, 2.0 / scale)   # 顺着东北风拉长
    mp.inputs["Rotation"].default_value = (0.0, 0.0, math.radians(35))
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 1.0
    nz.inputs["Detail"].default_value = 10.0
    nz.inputs["Roughness"].default_value = 0.62
    nz.inputs["Distortion"].default_value = 0.35
    nt.links.new(mp.outputs["Vector"], nz.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.3
    ramp.color_ramp.elements[0].color = (albedo * 0.12, albedo * 0.12, albedo * 0.12, 1)
    ramp.color_ramp.elements[1].position = 0.7
    ramp.color_ramp.elements[1].color = (albedo, albedo * 0.98, albedo * 0.96, 1)
    nt.links.new(nz.outputs["Fac"], ramp.inputs["Fac"])
    d = nt.nodes.new("ShaderNodeBsdfDiffuse")
    nt.links.new(ramp.outputs["Color"], d.inputs["Color"])
    shader = d.outputs[0]
    # 闪电：云里透出来的光
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    dist = nt.nodes.new("ShaderNodeVectorMath")
    dist.operation = 'DISTANCE'
    dist.inputs[1].default_value = flash_center
    nt.links.new(geo.outputs["Position"], dist.inputs[0])
    sq = nt.nodes.new("ShaderNodeMath")
    sq.operation = 'MULTIPLY'
    sq.inputs[1].default_value = -1.0 / (flash_r * flash_r)
    pw = nt.nodes.new("ShaderNodeMath")
    pw.operation = 'POWER'
    pw.inputs[1].default_value = 2.0
    nt.links.new(dist.outputs["Value"], pw.inputs[0])
    nt.links.new(pw.outputs[0], sq.inputs[0])
    ex = nt.nodes.new("ShaderNodeMath")
    ex.operation = 'EXPONENT'
    nt.links.new(sq.outputs[0], ex.inputs[0])
    fl = nt.nodes.new("ShaderNodeValue")
    fl.name = "FlashAmt"
    fl.outputs[0].default_value = 0.0
    k = nt.nodes.new("ShaderNodeMath")
    k.operation = 'MULTIPLY'
    nt.links.new(ex.outputs[0], k.inputs[0])
    nt.links.new(fl.outputs[0], k.inputs[1])
    cub = nt.nodes.new("ShaderNodeMath")
    cub.operation = 'POWER'
    cub.inputs[1].default_value = 3.0          # 噪声三次方：亮斑集中在云厚的地方，中间夹着暗缝
    nt.links.new(nz.outputs["Fac"], cub.inputs[0])
    k2 = nt.nodes.new("ShaderNodeMath")
    k2.operation = 'MULTIPLY'
    nt.links.new(k.outputs[0], k2.inputs[0])
    nt.links.new(cub.outputs[0], k2.inputs[1])
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (0.78, 0.85, 1.0, 1.0)
    nt.links.new(k2.outputs[0], em.inputs["Strength"])
    add = nt.nodes.new("ShaderNodeAddShader")
    nt.links.new(shader, add.inputs[0])
    nt.links.new(em.outputs[0], add.inputs[1])
    shader = add.outputs[0]
    if holes > 0:
        # 薄的地方是窟窿（边上是软的）：透明，露出上一层云
        cut = nt.nodes.new("ShaderNodeMapRange")
        cut.inputs["From Min"].default_value = holes - 0.05
        cut.inputs["From Max"].default_value = holes + 0.05
        nt.links.new(nz.outputs["Fac"], cut.inputs["Value"])
        tr = nt.nodes.new("ShaderNodeBsdfTransparent")
        mix = nt.nodes.new("ShaderNodeMixShader")
        nt.links.new(cut.outputs["Result"], mix.inputs["Fac"])
        nt.links.new(tr.outputs[0], mix.inputs[1])
        nt.links.new(shader, mix.inputs[2])
        shader = mix.outputs[0]
    nt.links.new(shader, out.inputs["Surface"])
    return m


# ============================================================================ 几何：按材质分桶的 bmesh
class Kit:
    def __init__(self):
        self.bm = {}
        self.mats = {}
        self.col = {}

    def __getitem__(self, k):
        if k not in self.bm:
            self.bm[k] = bmesh.new()
            self.col[k] = self.bm[k].loops.layers.float_color.new("Col")
        return self.bm[k]

    def box(self, key, cx, cy, z0, sx, sy, sz, rot=0.0):
        """底面中心 (cx, cy, z0)，绕 Z 转 rot 度"""
        M = Matrix.Translation((cx, cy, z0 + sz / 2)) @ Matrix.Rotation(math.radians(rot), 4, 'Z') @ \
            Matrix.Diagonal((sx, sy, sz, 1.0))
        bmesh.ops.create_cube(self[key], size=1.0, matrix=M)

    def quad(self, key, pts, color=(1, 1, 1)):
        bm = self[key]
        f = bm.faces.new([bm.verts.new(p) for p in pts])
        for lp in f.loops:
            lp[self.col[key]] = (*color, 1.0)
        return f

    def light_dot(self, p, r, color):
        """一个小发光球（灯头、亮窗太远时就是一个点）"""
        bm = self["Emit"]
        ret = bmesh.ops.create_icosphere(bm, subdivisions=1, radius=r, matrix=Matrix.Translation(p))
        for v in ret["verts"]:
            for lp in v.link_loops:
                lp[self.col["Emit"]] = (*color, 1.0)

    def beam(self, key, a, b, w):
        """一根方截面的杆（吊车的腿、臂架）"""
        a, b = V(a), V(b)
        d = b - a
        L = d.length
        z = d.normalized()
        x = z.cross(V((0, 0, 1)))
        if x.length < 1e-4:
            x = V((1, 0, 0))
        x.normalize()
        y = z.cross(x)
        M = Matrix((x, y, z)).transposed().to_4x4()
        M.translation = (a + b) / 2
        bmesh.ops.create_cube(self[key], size=1.0, matrix=M @ Matrix.Diagonal((w, w, L, 1.0)))

    def flush(self, coll):
        out = {}
        for k, bm in self.bm.items():
            me = bpy.data.meshes.new(k)
            bm.to_mesh(me)
            bm.free()
            ob = bpy.data.objects.new(k, me)
            coll.objects.link(ob)
            me.materials.append(self.mats[k])
            for p in me.polygons:
                p.use_smooth = k in ("Cloud", "CloudHigh", "Hills", "HillsFar")
            out[k] = ob
        return out


def lamp(K, p, power, color=SODIUM, head=0.35, glow=24.0, name="Lamp"):
    """一盏点光源（照地面、墙，水里有倒影）+ 发光的灯头"""
    li = bpy.data.lights.new(name, 'POINT')
    li.energy = power
    li.color = color
    li.shadow_soft_size = 0.3
    ob = bpy.data.objects.new(name, li)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = p
    ob.visible_camera = False
    ob.visible_glossy = False
    K.light_dot(V(p) + V((0, 0, 0.3)), head, tuple(c * glow for c in color))
    return ob


def area_up(name, p, size, radiance, color=SODIUM):
    """朝上的大面光：城里、船厂的灯照在低云底上（光污染）。相机和倒影里看不见它本身"""
    li = bpy.data.lights.new(name, 'AREA')
    li.shape = 'DISK'
    li.size = size
    li.color = color
    li.energy = radiance * math.pi * math.pi * (size / 2) ** 2   # 辐亮度 → 功率（单面朗伯）
    ob = bpy.data.objects.new(name, li)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = p
    ob.rotation_euler = (math.pi, 0, 0)     # 面光默认朝 -Z，翻过来朝上
    ob.visible_camera = False
    ob.visible_glossy = False
    return ob


# ============================================================================ 场景
def town(K, rng):
    """左边（西北）的县城：筒子楼、宿舍楼的盒子，朝南那面（和东面）开窗，十点五十了，零星几扇亮着"""
    blds = []
    for _ in range(170):
        az = rng.uniform(-84.0, -24.0)
        dist = 260.0 + 1500.0 * rng.random() ** 1.6
        x, y = polar(az, dist)
        if y > 420 and x > -250:          # 那边是水
            continue
        floors = rng.choice((3, 4, 4, 5, 5, 6, 6, 7, 8)) + (6 if rng.random() < 0.05 else 0)
        sx, sy = rng.uniform(16, 48), rng.uniform(10, 14)
        rot = rng.uniform(-12, 12) + (90 if rng.random() < 0.18 else 0)
        blds.append((x, y, floors, sx, sy, rot))
    blds.sort(key=lambda b: -math.hypot(b[0] - EYE.x, b[1] - EYE.y))
    lit = 0
    for (x, y, floors, sx, sy, rot) in blds:
        h = floors * 3.0 + 0.6
        K.box("Facade" if rng.random() < 0.6 else "Facade2", x, y, G, sx, sy, h, rot)
        # 屋顶上的水箱、楼梯间
        if rng.random() < 0.5:
            K.box("Roof", x + rng.uniform(-sx / 3, sx / 3), y, G + h, 4.0, 4.0, 3.0, rot)
        r = math.radians(rot)
        ex, ey = V((math.cos(r), math.sin(r), 0)), V((-math.sin(r), math.cos(r), 0))
        c = V((x, y, G))
        # 朝相机的两个面：南面（-ey）、东面或西面
        to_eye = (EYE - c).normalized()
        faces = [(-ey if to_eye.dot(-ey) > 0 else ey, ex, sx, sy)]
        faces.append((ex if to_eye.dot(ex) > 0 else -ex, ey, sy, sx))
        for (n, t, wlen, depth) in faces:
            nwin = max(1, int(wlen / 3.4))
            for fl in range(floors):
                for k in range(nwin):
                    if rng.random() > 0.04:
                        continue
                    u = (k + 0.5) / nwin * wlen - wlen / 2
                    zc = G + fl * 3.0 + 1.7
                    p = c + n * (depth / 2 + 0.06) + t * u
                    kind = rng.random()
                    if kind < 0.7:     # 白炽灯：暖黄，隔着窗帘
                        col = (1.0, 0.62, 0.3)
                    elif kind < 0.92:  # 日光灯：发青
                        col = (0.75, 0.95, 0.85)
                    else:              # 电视：发蓝
                        col = (0.45, 0.6, 1.0)
                    s = rng.uniform(0.6, 3.0)
                    col = tuple(ch * s for ch in col)
                    hw, hh = 0.7, 0.6
                    K.quad("Emit", [p - t * hw + V((0, 0, -hh)) + V((0, 0, zc - G)),
                                    p + t * hw + V((0, 0, -hh)) + V((0, 0, zc - G)),
                                    p + t * hw + V((0, 0, hh)) + V((0, 0, zc - G)),
                                    p - t * hw + V((0, 0, hh)) + V((0, 0, zc - G))], col)
                    lit += 1
    # 一栋十二层的宾馆（县城最高的楼），楼顶两盏红灯
    hx, hy = polar(-46.0, 900.0)
    K.box("Facade2", hx, hy, G, 30, 16, 40, -8)
    for dx in (-13, 13):
        K.light_dot(V((hx + dx, hy, G + 40.8)), 0.6, (6.0, 0.25, 0.1))
    # 水塔、烧锅炉的烟囱
    wx, wy = polar(-64.0, 520.0)
    for a in range(4):
        K.beam("Steel", (wx + 4 * math.cos(a * 1.57), wy + 4 * math.sin(a * 1.57), G), (wx, wy, G + 26), 0.6)
    K.box("Roof", wx, wy, G + 26, 9, 9, 7)
    cx, cy = polar(-31.0, 1250.0)
    K.box("Facade", cx, cy, G, 5, 5, 45)
    K.light_dot(V((cx, cy, G + 45.5)), 0.7, (6.0, 0.25, 0.1))
    # 街上的钠灯：沿几条路，35 米一盏
    lamps = []
    for (a, b) in (((-1600, 420), (-250, 400)), ((-260, 380), (-1300, 1500)), ((-500, 700), (-2000, 620)),
                   ((-700, 1100), (-1600, 1900))):
        a, b = V((a[0], a[1], 0)), V((b[0], b[1], 0))
        n = int((b - a).length / 38)
        for k in range(n):
            p = a + (b - a) * (k + rng.random() * 0.3) / n
            if rng.random() < 0.2:      # 坏了几盏
                continue
            lamps.append(lamp(K, (p.x, p.y, G + 8.0), 700.0, head=0.4))
    print(f"town: {len(blds)} buildings, {lit} lit windows, {len(lamps)} street lamps")


def shipyard(K, rng):
    """正前方：船厂后半截。大车间、码头上的门座起重机、远处一台龙门吊、船台上一条造了一半的船、码头照明灯"""
    for (x, y, sx, sy, h, rot) in ((-60, 235, 90, 42, 22, 0), (70, 265, 66, 38, 27, 3), (215, 215, 75, 40, 20, -4),
                                   (-170, 300, 50, 30, 16, 8)):
        K.box("Shed", x, y, G, sx, sy, h, rot)
        # 人字屋顶
        r = math.radians(rot)
        ex = V((math.cos(r), math.sin(r), 0))
        ey = V((-math.sin(r), math.cos(r), 0))
        c = V((x, y, G + h))
        K.quad("Roof", [c - ex * sx / 2 - ey * sy / 2, c + ex * sx / 2 - ey * sy / 2, c + ex * sx / 2 + V((0, 0, 7)),
                        c - ex * sx / 2 + V((0, 0, 7))])
        K.quad("Roof", [c - ex * sx / 2 + V((0, 0, 7)), c + ex * sx / 2 + V((0, 0, 7)), c + ex * sx / 2 + ey * sy / 2,
                        c - ex * sx / 2 + ey * sy / 2])
        # 车间山墙上一盏照明灯（门口）
        lamp(K, tuple(V((x, y, G)) - ey * (sy / 2 + 1.5) + V((rng.uniform(-sx / 3, sx / 3), 0, 9.0))), 1600.0,
             head=0.5)
    # 码头：岸线 y≈420，岸边一排高杆灯
    for x in range(-230, 470, 70):
        K.beam("Steel", (x, 412, G), (x, 412, G + 16), 0.5)
        lamp(K, (x, 411, G + 16.3), 2600.0, head=0.7)
    # 门座起重机：门架、转台、塔身、斜着的臂架；臂架头上一盏红灯
    for (x, y, az, lift) in ((25, 405, -30, 52), (130, 400, 20, 45), (285, 395, 75, 58)):
        for (dx, dy) in ((-5, -5), (5, -5), (-5, 5), (5, 5)):
            K.beam("Steel", (x + dx, y + dy, G), (x + dx * 0.4, y + dy * 0.4, G + 11), 1.0)
        K.box("Steel", x, y, G + 11, 9, 9, 4)
        K.beam("Steel", (x, y, G + 15), (x, y, G + 33), 2.6)
        K.box("Steel", x, y, G + 30, 8, 11, 6, az)
        a, l = math.radians(az), math.radians(lift)
        tip = V((x + 38 * math.cos(l) * math.sin(a), y + 38 * math.cos(l) * math.cos(a), G + 34 + 38 * math.sin(l)))
        K.beam("Steel", (x, y, G + 34), tip, 1.4)
        K.beam("Steel", (x, y, G + 41), tip, 0.35)
        K.light_dot(tip + V((0, 0, 0.8)), 0.6, (5.0, 0.2, 0.08))
    # 远处另一台龙门吊（比 3D 的那台远、矮一点）
    for x in (160, 236):
        for dy in (-4, 4):
            K.beam("Steel", (x, 330 + dy, G), (x, 330 + dy * 0.3, G + 36), 1.2)
    K.box("Steel", 198, 330, G + 36, 88, 3.2, 3.6)
    K.light_dot(V((198, 330, G + 40.5)), 0.6, (5.0, 0.2, 0.08))
    # 县城边上一盏高杆钠灯（快坏了，Godot 里时不时抽几下；放在县城的楼前面，别被挡住）
    x, y = polar(FLICKER_LAMP[0], FLICKER_LAMP[1])
    K.beam("Steel", (x, y, G), (x, y, G + FLICKER_LAMP[2]), 0.35)
    lamp(K, (x, y, G + FLICKER_LAMP[2]), 900.0, head=0.5)
    # 船台上一条造了一半的船（东边）
    K.box("Hull", 330, 300, G, 22, 120, 16, 8)
    K.box("Hull", 332, 352, G + 16, 18, 16, 9, 8)


def harbour(K, rng):
    """右边：港湾、防波堤、锚地里避台风的船、对岸的山"""
    # 防波堤，头上一盏绿灯
    a, b = V((260, 1350, 0)), V((1700, 1560, 0))
    n = 24
    for k in range(n):
        p = a + (b - a) * (k + 0.5) / n
        K.box("Pier", p.x, p.y, G - 3.0, (b - a).length / n + 1, 10, 5.2, math.degrees(math.atan2(b.y - a.y, b.x - a.x)))
    K.light_dot(V((a.x, a.y, G + 6)), 0.9, (0.3, 3.0, 0.8))
    K.beam("Steel", (a.x, a.y, G + 2), (a.x, a.y, G + 6), 0.6)
    # 锚地里的船：黑船壳、船尾楼，甲板灯和桅灯
    for (az, dist, rot) in ((-6.0, 2600.0, 20.0), (17.0, 3300.0, -30.0), (38.0, 2300.0, 60.0), (55.0, 3800.0, 5.0)):
        x, y = polar(az, dist)
        K.box("Hull", x, y, G - 3, 95, 15, 9, rot)
        r = math.radians(rot)
        ex = V((math.cos(r), math.sin(r), 0))
        st = V((x, y, G)) - ex * 38
        K.box("Hull", st.x, st.y, G + 6, 14, 13, 11, rot)
        K.light_dot(st + V((0, 0, 21)), 0.8, (5.0, 4.6, 3.8))
        K.light_dot(V((x, y, G)) + ex * 30 + V((0, 0, 16)), 0.7, (5.0, 4.6, 3.8))
        for k in range(rng.randint(2, 4)):
            p = V((x, y, G)) + ex * rng.uniform(-30, 35) + V((0, 0, 7.5))
            K.light_dot(p, 0.6, (4.0, 3.0, 1.6))


def hills(K, noise):
    """对岸和县城后面的山：两层山脊线（近的低、远的高），黑的；山脚几点人家的灯"""
    for key, dist, base, amp, seed in (("Hills", 3600.0, 60.0, 260.0, 0.0), ("HillsFar", 6500.0, 180.0, 420.0, 50.0)):
        bm = K[key]
        top, bot = [], []
        for i in range(181):
            az = -88.0 + 176.0 * i / 180
            d = dist * (1.0 + 0.25 * math.sin(math.radians(az) * 2.3 + seed))
            h = base + amp * float(noise.fbm(az / 22.0 + seed, 3.7 + seed, 5, 0.55)) ** 1.6
            x, y = polar(az, d)
            top.append(bm.verts.new((x, y, G + h)))
            bot.append(bm.verts.new((x, y, G - 6)))
        for i in range(180):
            bm.faces.new((bot[i], bot[i + 1], top[i + 1], top[i]))
    rng = random.Random(4)
    for _ in range(14):
        az = rng.uniform(5, 80)
        x, y = polar(az, 3500.0 * rng.uniform(0.95, 1.05))
        K.light_dot(V((x, y, G + rng.uniform(2, 20))), 1.4, (3.0, 2.0, 1.0))


def ground_water(K):
    """地（县城、船厂，湿的）和海（港湾）。岸线：船厂码头 y=420，往西北拐到县城外面"""
    coast = [(-9000, 3200), (-1700, 2600), (-900, 1500), (-420, 700), (-250, 420), (470, 420), (470, 300),
             (9000, 300), (9000, -200), (-9000, -200)]
    bm = K["Ground"]
    bm.faces.new([bm.verts.new((x, y, G)) for (x, y) in reversed(coast)])
    K.quad("Water", [(-9000, -200, G - 2.5), (9000, -200, G - 2.5), (9000, 16000, G - 2.5), (-9000, 16000, G - 2.5)])


def clouds(K, noise):
    """两层云：低空的云底（起伏大、有窟窿）220 米，上面整的一层 520 米"""
    for key, z, amp, res, cell in (("Cloud", 230.0, 55.0, 220, 1400.0), ("CloudHigh", 560.0, 30.0, 120, 3000.0)):
        bm = K[key]
        ext = (-14000.0, 14000.0, -3000.0, 22000.0)
        nx, ny = res, res
        xs = np.linspace(ext[0], ext[1], nx)
        # 离相机越近格子越密（近处的起伏看得清）
        ys = ext[2] + (ext[3] - ext[2]) * np.linspace(0, 1, ny) ** 1.8
        X, Y = np.meshgrid(xs, ys)
        Z = G + z + amp * (noise.fbm(X / cell, Y / cell + 11, 5, 0.55) - 0.5) * 2
        verts = [[bm.verts.new((float(X[j, i]), float(Y[j, i]), float(Z[j, i]))) for i in range(nx)] for j in range(ny)]
        for j in range(ny - 1):
            for i in range(nx - 1):
                # 法线朝下（从下面看）
                bm.faces.new((verts[j][i], verts[j + 1][i], verts[j + 1][i + 1], verts[j][i + 1]))


# 闪电在正北偏西（和 story_room.setup_lightning 的方向一致）的云里
FLASH_AZ, FLASH_DIST, FLASH_Z = -14.0, 1500.0, 500.0
FLASH_CLOUD = 60.0                 # 云里透出来的光（× 高斯 × 噪声³）
FLASH_RADIANCE = 15.0              # 云上面那片面光的辐亮度：照亮地上的楼、吊车、水面


def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    coll = sc.collection
    K = Kit()
    fx, fy = polar(FLASH_AZ, FLASH_DIST)
    fc = (fx, fy, G + FLASH_Z)
    K.mats = {
        "Facade": mat_surface("Facade", (0.13, 0.12, 0.11), 0.85, 0.3, 0.2),
        "Facade2": mat_surface("Facade2", (0.18, 0.17, 0.15), 0.85, 0.3, 0.2),
        "Roof": mat_surface("Roof", (0.06, 0.06, 0.06), 0.7),
        "Shed": mat_surface("Shed", (0.12, 0.12, 0.12), 0.6, 0.2, 0.1),
        "Steel": mat_surface("Steel", (0.07, 0.06, 0.055), 0.6),
        "Hull": mat_surface("Hull", (0.05, 0.05, 0.05), 0.5),
        "Pier": mat_surface("Pier", (0.2, 0.2, 0.19), 0.9),
        "Hills": mat_surface("Hills", (0.03, 0.035, 0.03), 0.95),
        "HillsFar": mat_surface("HillsFar", (0.03, 0.035, 0.03), 0.95),
        "Ground": mat_surface("Ground", (0.06, 0.06, 0.06), 0.18, 0.15, 0.05, rough_var=0.5),
        "Water": mat_surface("Water", (0.02, 0.022, 0.025), 0.06, 0.25, 0.12),
        "Emit": mat_emit(),
        "Cloud": mat_cloud("Cloud", 0.6, 1100.0, 0.42, fc, 1300.0),
        "CloudHigh": mat_cloud("CloudHigh", 0.3, 3500.0, 0.0, fc, 2200.0),
    }
    rng = random.Random(1998)
    noise = Noise(7)
    ground_water(K)
    town(K, rng)
    shipyard(K, rng)
    harbour(K, rng)
    hills(K, noise)
    clouds(K, noise)
    obs = K.flush(coll)
    for k in ("Cloud", "CloudHigh"):
        obs[k].visible_shadow = False     # 云不挡光：闪电的面光在云上面，照得到地上
    # 光污染：城里、船厂的灯照亮云底
    for (az, dist, size, rad) in ((-55.0, 900.0, 1400.0, 0.7), (-35.0, 1700.0, 1600.0, 0.35),
                                  (5.0, 330.0, 500.0, 0.35), (-75.0, 1300.0, 1200.0, 0.35), (40.0, 1100.0, 1500.0, 0.12)):
        x, y = polar(az, dist)
        area_up(f"Glow{az:+.0f}", (x, y, G + 45), size, rad)
    # 夜空本身（云上面、地平线外面）：很暗的灰
    w = bpy.data.worlds.new("Night")
    sc.world = w
    if w.node_tree is None:
        w.use_nodes = True
    bg = w.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (0.012, 0.011, 0.012, 1)
    bg.inputs["Strength"].default_value = 1.0
    # 闪电：云上面一大片冷白面光（渲闪电版时才开）
    li = bpy.data.lights.new("Flash", 'AREA')
    li.shape = 'DISK'
    li.size = 2400.0
    li.color = (0.78, 0.85, 1.0)
    li.energy = 0.0
    ob = bpy.data.objects.new("Flash", li)
    coll.objects.link(ob)
    ob.location = (fx, fy, G + 900.0)
    ob.visible_camera = False
    # 相机
    cam = bpy.data.cameras.new("Eye")
    cam.type = 'PANO'
    cam.panorama_type = 'CENTRAL_CYLINDRICAL'
    cam.central_cylindrical_range_u_min = math.radians(-U_DEG)
    cam.central_cylindrical_range_u_max = math.radians(U_DEG)
    cam.central_cylindrical_range_v_min = V_MIN
    cam.central_cylindrical_range_v_max = V_MAX
    cam.clip_start = 1.0
    cam.clip_end = 30000.0
    co = bpy.data.objects.new("Eye", cam)
    coll.objects.link(co)
    co.location = EYE
    co.rotation_euler = (math.radians(90), 0, 0)    # 朝 +Y（北）
    sc.camera = co
    return sc


def setup_render(sc, w, h, samples, denoise=True):
    sc.render.engine = 'CYCLES'
    prefs = bpy.context.preferences.addons['cycles'].preferences
    prefs.compute_device_type = 'METAL'
    prefs.get_devices()
    for d in prefs.devices:
        d.use = d.type == 'METAL'
    sc.cycles.device = 'GPU'
    sc.cycles.samples = samples
    sc.cycles.use_adaptive_sampling = denoise
    sc.cycles.adaptive_threshold = 0.02
    sc.cycles.seed = 7
    sc.cycles.use_denoising = denoise
    sc.cycles.denoiser = 'OPENIMAGEDENOISE'
    sc.cycles.max_bounces = 4
    sc.cycles.diffuse_bounces = 2
    sc.cycles.glossy_bounces = 2
    sc.cycles.transmission_bounces = 1
    sc.cycles.volume_bounces = 0
    sc.cycles.transparent_max_bounces = 8
    sc.cycles.sample_clamp_indirect = 4.0
    sc.render.resolution_x, sc.render.resolution_y = w, h
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = False
    sc.render.use_compositing = False
    sc.render.use_sequencer = False
    sc.view_settings.view_transform = 'Standard'
    s = sc.render.image_settings
    if hasattr(s, "media_type"):
        s.media_type = 'IMAGE'
    s.file_format = 'OPEN_EXR'
    s.color_mode = 'RGB'
    s.color_depth = '32'
    s.exr_codec = 'ZIP'


def render_exr(sc, name):
    """渲一张、读回 numpy（H × W × 3，第 0 行在上面，和贴图一样）"""
    path = os.path.join(bpy.app.tempdir or "/tmp", f"backdrop_{name}.exr")
    sc.render.filepath = path
    t0 = time.time()
    bpy.ops.render.render(write_still=True)
    inp = oiio.ImageInput.open(path)
    spec = inp.spec()
    px = inp.read_image(0, 0, 0, 3, "float")
    inp.close()
    os.remove(path)
    print(f"render {name} {spec.width}x{spec.height}: {time.time() - t0:.0f}s")
    return px


def render_depth(sc, w, h):
    """距离：所有东西换成「发光 = 相机光线长度」的材质（天空 = MIST），几个采样就够。这个 Blender 存多层 EXR 时
    不带 Mist、Emit 这些通道，所以距离和发光都单独渲一遍"""
    m, nt, out = _nodes("Depth")
    lp = nt.nodes.new("ShaderNodeLightPath")
    e = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(lp.outputs["Ray Length"], e.inputs["Strength"])
    nt.links.new(e.outputs[0], out.inputs["Surface"])
    vl = sc.view_layers[0]
    vl.material_override = m
    bg = sc.world.node_tree.nodes["Background"]
    keep = tuple(bg.inputs["Color"].default_value), bg.inputs["Strength"].default_value
    bg.inputs["Color"].default_value = (1, 1, 1, 1)
    bg.inputs["Strength"].default_value = MIST
    setup_render(sc, w, h, 4, denoise=False)
    d = render_exr(sc, "depth")[:, :, 0]
    vl.material_override = None
    bg.inputs["Color"].default_value = keep[0]
    bg.inputs["Strength"].default_value = keep[1]
    bpy.data.materials.remove(m)
    return d


def render_emission(sc, w, h):
    """只看得见直接发光的东西（亮窗、灯头、红灯）：别的全换成纯黑（挡在前面的照样挡），不打光、天是黑的"""
    m, nt, out = _nodes("Black")
    e = nt.nodes.new("ShaderNodeEmission")
    e.inputs["Strength"].default_value = 0.0
    nt.links.new(e.outputs[0], out.inputs["Surface"])
    swapped = []
    for ob in bpy.data.objects:
        if ob.type == 'MESH' and ob.name != "Emit":
            swapped.append((ob, ob.material_slots[0].material))
            ob.material_slots[0].material = m
    bg = sc.world.node_tree.nodes["Background"]
    keep = bg.inputs["Strength"].default_value
    bg.inputs["Strength"].default_value = 0.0
    setup_render(sc, w, h, 8, denoise=False)
    e_img = render_exr(sc, "emit")
    for ob, mat in swapped:
        ob.material_slots[0].material = mat
    bg.inputs["Strength"].default_value = keep
    bpy.data.materials.remove(m)
    return e_img


# ============================================================================ 后期（numpy）：雨雾、光晕、发光份额
def blur(a, sigma):
    """大半径高斯模糊：缩小 → 小核卷积 → 放大（边上按边缘像素延伸，不往里吃黑）"""
    h, w, c = a.shape
    f = max(1, int(sigma / 3.0))
    sw, sh = max(4, w // f), max(4, h // f)
    small = oiio.ImageBufAlgo.resize(oiio.ImageBuf(np.ascontiguousarray(a, np.float32)),
                                     roi=oiio.ROI(0, sw, 0, sh, 0, 1, 0, c)).get_pixels(oiio.FLOAT)
    s = sigma / f
    p = int(math.ceil(3 * s)) + 1
    small = np.pad(small, ((p, p), (p, p), (0, 0)), mode='edge')
    x = np.arange(-p, p + 1)
    k = np.exp(-0.5 * (x / s) ** 2)
    k /= k.sum()
    tmp = sum(k[i] * small[:, i:i + small.shape[1] - 2 * p] for i in range(2 * p + 1))
    small = sum(k[i] * tmp[i:i + tmp.shape[0] - 2 * p] for i in range(2 * p + 1))
    return oiio.ImageBufAlgo.resize(oiio.ImageBuf(np.ascontiguousarray(small, np.float32)),
                                    roi=oiio.ROI(0, w, 0, h, 0, 1, 0, c)).get_pixels(oiio.FLOAT)


def lum(a):
    return a[..., 0] * 0.2126 + a[..., 1] * 0.7152 + a[..., 2] * 0.0722


def post(comb, emit, dist, flash):
    """落到游戏里的亮度（× EXPOSE），再加雨雾和光晕。返回成图和发光份额。
    雨雾分两层：
    - 贴地的一层雨雾（厚 HAZE_H 米）：和 Godot 里 3D 近景的深度雾同一个公式（dorm_env.tres：density 0.85、6~140 米
      smoothstep），所以 150 米处 3D 地面和全景条接得上；往上看的光线很快穿出这一层，云底的纹理还看得见
    - 上面一层薄的：按整段距离 exp(-d / HAZE_L)
    雾的颜色 = 地平线上和 3D 雾一样的暗橙（HAZE_NIGHT）+ 画面大范围模糊（城里灯多的地方雾亮）。
    灯、亮窗穿雾按 sqrt(T) 衰减（往前散射的光还留在灯的周围，变成光晕），再加三层光晕"""
    h, w = comb.shape[:2]
    scale = w / W                               # 试渲时像素半径跟着缩
    comb = comb * EXPOSE
    emit = emit * EXPOSE
    d = np.clip(dist, 0.0, MIST)
    tan_el = V_MIN + (1.0 - (np.arange(h) + 0.5) / h) * (V_MAX - V_MIN)
    sin_el = (tan_el / np.sqrt(1.0 + tan_el ** 2))[:, None]
    d_low = np.where(sin_el > 1e-3, np.minimum(d, HAZE_H / np.maximum(sin_el, 1e-3)), d)
    t = np.clip((d_low - 6.0) / 134.0, 0.0, 1.0)
    T = (1.0 - 0.85 * t * t * (3.0 - 2.0 * t)) * np.exp(-d / HAZE_L)
    T = T[..., None]
    if flash:
        base = np.array(HAZE_FLASH)
        amb = blur(comb, 260 * scale) * 0.8
    else:
        base = np.array(HAZE_NIGHT)
        amb = blur(comb, 220 * scale) * 0.6
    haze = base + amb
    img = comb * T + haze * (1.0 - T)
    et = emit * np.sqrt(T)
    glow = blur(et, 3 * scale) * 0.45 + blur(et, 14 * scale) * 0.22 + blur(et, 60 * scale) * 0.10
    img = img + et - emit * T + glow
    share = np.clip(lum(et + glow) / np.maximum(lum(img), 1e-6), 0.0, 1.0)
    return img.astype(np.float32), share.astype(np.float32)


def write_exr(path, img):
    spec = oiio.ImageSpec(img.shape[1], img.shape[0], 3, oiio.HALF)
    spec.attribute("compression", "zip")     # Godot 的 tinyexr 不认 DWA
    out = oiio.ImageOutput.create(path)
    out.open(path, spec)
    out.write_image(np.ascontiguousarray(img[:, :, :3], np.float32))
    out.close()


def write_png8(path, a):
    spec = oiio.ImageSpec(a.shape[1], a.shape[0], 1, oiio.UINT8)
    out = oiio.ImageOutput.create(path)
    out.open(path, spec)
    out.write_image(np.ascontiguousarray((np.clip(a, 0, 1) * 255 + 0.5).astype(np.uint8)[..., None]))
    out.close()


def write_preview(path, img, exposure=30.0):
    """看效果用：提亮 30 倍（游戏里的值很暗）+ 简单的色调映射（x/(1+x)）+ sRGB，存 JPG"""
    x = img * exposure
    x = x / (1.0 + x)
    x = np.where(x <= 0.0031308, 12.92 * x, 1.055 * np.power(np.maximum(x, 1e-8), 1 / 2.4) - 0.055)
    spec = oiio.ImageSpec(img.shape[1], img.shape[0], 3, oiio.UINT8)
    out = oiio.ImageOutput.create(path)
    out.open(path, spec)
    out.write_image(np.ascontiguousarray((np.clip(x, 0, 1) * 255 + 0.5).astype(np.uint8)))
    out.close()


def render_one(sc, a, kind):
    flash = kind == "flash"
    s = a["scale"] * (0.5 if flash else 1.0)
    w, h = int(W * s), int(H * s)
    for m in ("Cloud", "CloudHigh"):
        bpy.data.materials[m].node_tree.nodes["FlashAmt"].outputs[0].default_value = FLASH_CLOUD if flash else 0.0
    li = bpy.data.lights["Flash"]
    li.energy = FLASH_RADIANCE * math.pi * math.pi * (li.size / 2) ** 2 if flash else 0.0
    setup_render(sc, w, h, a["samples"])
    comb = render_exr(sc, kind)
    emit = render_emission(sc, w, h) if not flash else np.zeros_like(comb)
    dist = render_depth(sc, w, h)
    return post(comb, emit, dist, flash)


def main():
    a = args()
    sc = build()
    kinds = [a["only"]] if a["only"] else ["night", "flash"]
    os.makedirs(OUT, exist_ok=True)
    for kind in kinds:
        img, share = render_one(sc, a, kind)
        if a["save"]:
            write_exr(os.path.join(OUT, f"dorm_{kind}.exr"), img)
            if kind == "night":
                write_png8(os.path.join(OUT, "dorm_glow.png"), share)
        if a["preview"]:
            os.makedirs(a["preview"], exist_ok=True)
            write_preview(os.path.join(a["preview"], f"{kind}.jpg"), img)
            if kind == "night":
                write_png8(os.path.join(a["preview"], "glow.png"), share)
        print("max", img.max(), "mean", img.mean(axis=(0, 1)))


main()
