"""巨物「闷雷」的共享规格（第二版）：所有部件按这里的尺寸、曲面、骨骼、挂点、贴图组、材质名来做，合在一起才对得上。
这个文件由总装（gen_giant.py）维护，部件作者只读不改；需要改的地方写进各自的报告里提。

外形（第二版）：**一条真实可信的深海鲨鱼**，身体照格陵兰睡鲨，嘴照尖牙鱼，四十二米长、活了几百年。
真实感来自统一的解剖和克制的细节——每个部位都要能用同一套鲨鱼解剖解释，大面平滑、少数几处重点：
  - 身体：粗壮的圆筒，钝圆短吻，最粗处在身体前中段，往后收成尾柄；皮是细密的盾鳞（粗糙、哑光、略带湿光），
    暗灰褐色、背略深腹略浅、零星深色斑；大动物的尺度靠少量大东西体现：几道很长的发白旧疤、
    几个圆形的达摩鲨咬坑、一两处新伤，**不要满身噪声起伏、不要一排排钻孔**；
  - 鳃：头后、胸鳍前上方，五道**小**鳃裂（低、短、往后斜），随呼吸微微开合；
  - 鳍：一对胸鳍（中等、圆钝，能打舵）、一对腹鳍、两片**小**背鳍（靠后，第二背鳍更小）、歪尾（上叶长、下叶也不小，格陵兰睡鲨那种）；
    没有臀鳍。鳍边缘有旧的撕口，不要破成布条；
  - 眼睛：很小、浑浊的乳白色（瞎的），每只眼睛上挂着一只寄生桡足类（发白的身体 + 两条拖在水里的长卵带），
    这是格陵兰睡鲨真实的样子；
  - 嘴（恐怖点）：嘴在吻下、往前开得很大，地包天；**牙少而巨大**（尖牙鱼）：上下各一二十颗长短不一的獠牙，
    半透明发白，下颌前端两根最长的獠牙闭嘴时插进上颚的两个牙槽里（尖牙鱼真实的结构）；嘴里是黑紫色，衬得牙特别显眼；
    张嘴 JAW_OPEN_MAX 度能吞下 14 米的潜艇。不要喉咙里一圈圈的小牙、不要骨板、不要长须；
  - 吻下有鲨鱼的感觉孔（劳伦氏壶腹）：细小、深色、成片分布在吻部下面和前面，近看才看得见。

坐标（Blender）：+Y 朝前（头），+Z 朝上，+X 朝右；原点在 s = 0.5 的中轴线上。导出后在 Godot 里 -Z 朝前。单位米。
静止姿态（rest pose）：身体是直的、嘴闭着、鳃闭着、胸鳍自然张开；动作全靠 Godot 里驱动骨骼（scripts/giant_motion.gd）。

身体坐标 (s, θ)：
  s ∈ [0, 1]：0 = 上吻端，1 = 尾尖（尾柄末端，尾鳍再往后伸出）；y = HALF - LENGTH * s；下颌往前多伸出到 s = JAW_FRONT_S < 0
  θ（弧度）：截面上的角度，0 = 背中线（正上），+π/2 = 右侧（+X），±π = 腹中线（正下），-π/2 = 左侧

流程（第二版）：高模烘焙低模。每个部件出两份网格：
  - 低模（进游戏）：面数见 TRI_BUDGET；UV0 = 所在贴图组的图集（0～1，**等密度**：1 个 UV 单位 = TEXSETS[组]["meters"] 米），
    UV1 = "BodyST"（set_body_uv 算），顶点组 = 骨骼权重；
  - 高模（只用来烘焙）：雕刻级细节（盾鳞的大颗粒、皱、疤、咬坑、孔……几毫米到几厘米的都放这里），可以几百万面；
    点色属性 "Curv"（R 凹槽、G 凸棱，0～1，不给就自动算）、"Area"（R：区域图，比如疤和生肉，见 TEXSETS 说明）。
  同一贴图组的部件**共用一张图集**，UV 岛不能重叠：每个组的图集由该组的负责人统一排（见「分区」）。
  烘焙用 giant/bakeutil.py：bake_set(组名, lows, highs)，输出 assets/textures/giant/<组>_normal.png、<组>_mask.png。
"""
import math
import zlib
import numpy as np
from mathutils import Vector, Matrix

V = Vector

LENGTH = 42.0
HALF = LENGTH / 2.0

# ---------------------------------------------------------------------------- 截面
# 沿身体的关键点：s、半宽、背高（中轴线以上）、腹深（中轴线以下）、中轴线高度、超椭圆指数（2 = 椭圆）
# 格陵兰睡鲨：粗圆筒，最粗在 s ≈ 0.36；头钝圆、略扁；尾柄细而侧扁
_PROFILE = np.array([
    # s     半宽  背高  腹深  中轴z  指数
    [0.00, 1.90, 1.10, 1.30, 0.30, 2.2],   # 钝圆短吻
    [0.04, 3.30, 2.10, 2.50, 0.30, 2.2],
    [0.10, 4.30, 3.00, 3.50, 0.30, 2.2],
    [0.18, 4.80, 3.60, 4.10, 0.30, 2.2],
    [0.26, 5.00, 4.00, 4.30, 0.35, 2.15],  # 鳃区
    [0.36, 5.10, 4.30, 4.30, 0.40, 2.1],   # 最粗
    [0.48, 4.70, 4.10, 3.90, 0.40, 2.1],
    [0.60, 3.90, 3.50, 3.10, 0.35, 2.05],
    [0.72, 2.70, 2.70, 2.20, 0.30, 2.0],
    [0.82, 1.60, 1.95, 1.45, 0.30, 2.0],
    [0.88, 1.00, 1.45, 1.00, 0.30, 2.0],   # 尾柄：细、侧扁
    [0.94, 0.80, 1.25, 0.90, 0.35, 2.0],
    [1.00, 0.30, 0.60, 0.40, 0.40, 2.0],
])


def _pchip_slopes(xs, ys):
    """保形三次插值（PCHIP）的斜率：关键点之间平滑过渡，不会一节一节鼓。"""
    h = np.diff(xs)
    d = np.diff(ys) / h
    m = np.zeros_like(ys)
    for k in range(1, len(xs) - 1):
        if d[k - 1] * d[k] > 0:
            w1, w2 = 2 * h[k] + h[k - 1], h[k] + 2 * h[k - 1]
            m[k] = (w1 + w2) / (w1 / d[k - 1] + w2 / d[k])
    m[0], m[-1] = d[0], d[-1]
    return m


_SLOPES = [_pchip_slopes(_PROFILE[:, 0], _PROFILE[:, c]) for c in range(_PROFILE.shape[1])]


def _smooth_interp(s, col):
    xs = _PROFILE[:, 0]
    ys = _PROFILE[:, col]
    m = _SLOPES[col]
    s = min(max(s, 0.0), 1.0)
    i = int(np.searchsorted(xs, s, side="right") - 1)
    i = min(max(i, 0), len(xs) - 2)
    h = xs[i + 1] - xs[i]
    t = (s - xs[i]) / h
    h00, h10, h01, h11 = 2 * t**3 - 3 * t**2 + 1, t**3 - 2 * t**2 + t, -2 * t**3 + 3 * t**2, t**3 - t**2
    return float(h00 * ys[i] + h10 * h * m[i] + h01 * ys[i + 1] + h11 * h * m[i + 1])


def section(s):
    """(半宽, 背高, 腹深, 中轴 z, 超椭圆指数)"""
    return tuple(_smooth_interp(s, c) for c in range(1, 6))


def y_of(s):
    return HALF - LENGTH * s


def s_of(y):
    return (HALF - y) / LENGTH


def center(s):
    """中轴线上的点（脊椎骨就沿着这条线）。"""
    return V((0.0, y_of(s), section(s)[3]))


def _se(c, e):
    return math.copysign(abs(c) ** (2.0 / e), c)


def surface(s, theta):
    """理想身体表面上的点（闭嘴时整个外轮廓；头部嘴线以下属于下颌）。"""
    hw, ht, hb, zc, e = section(s)
    c, sn = math.cos(theta), math.sin(theta)
    x = hw * _se(sn, e)
    z = (ht if c >= 0 else hb) * _se(c, e)
    return V((x, y_of(s), zc + z))


def normal(s, theta, eps=1e-3):
    s0, s1 = max(s - eps, 0.0), min(s + eps, 1.0)
    ds = surface(s1, theta) - surface(s0, theta)
    dt = surface(s, theta + eps) - surface(s, theta - eps)
    n = dt.cross(ds)
    if n.length < 1e-9:
        p = surface(s, theta) - center(s)
        return p.normalized() if p.length > 1e-9 else V((0, 0, 1))
    n.normalize()
    if n.dot(surface(s, theta) - center(s)) < 0:
        n = -n
    return n


def frame(s, theta, offset=0.0):
    """表面上一点的局部坐标系：原点在表面（沿法线再往外 offset 米），Z = 朝外法线，Y = 朝头的切向，X = Y × Z。"""
    n = normal(s, theta)
    p = surface(s, theta) + n * offset
    fwd = surface(max(s - 1e-3, 0.0), theta) - surface(min(s + 1e-3, 1.0), theta)
    fwd = fwd - n * fwd.dot(n)
    if fwd.length < 1e-9:
        fwd = V((0, 1, 0))
    fwd.normalize()
    x = fwd.cross(n)
    m = Matrix.Identity(4)
    m.col[0][:3] = x
    m.col[1][:3] = fwd
    m.col[2][:3] = n
    m.col[3][:3] = p
    return m


def body_coords(p):
    """任意一点 → 最接近的 (s, θ)（按所在截面的超椭圆反算，UV1 和权重用）。"""
    s = min(max(s_of(p.y), 0.0), 1.0)
    hw, ht, hb, zc, e = section(s)
    dz = p.z - zc
    h = ht if dz >= 0 else hb
    u = p.x / max(hw, 1e-3)
    v = dz / max(h, 1e-3)
    uc = math.copysign(abs(u) ** (e / 2.0), u)
    vc = math.copysign(abs(v) ** (e / 2.0), v)
    return s, math.atan2(uc, vc)


# ---------------------------------------------------------------------------- 嘴
# 嘴线：上颌和下颌闭嘴时的分界（侧面看），从吻端到嘴角铰链。尖牙鱼式的大嘴：嘴在吻下往前开，嘴角在眼睛后下方。
JAW_HINGE_S = 0.20          # 嘴角 / 下颌铰链
JAW_FRONT_S = -0.02         # 下颌往前伸出上吻端这么多（地包天，约 0.8 米）
JAW_OPEN_MAX = 70.0         # 张嘴最大角度（度），绕铰链 X 轴往下


def mouth_k(s):
    """嘴线在截面上的位置：中轴以下 k·腹深（吻端靠下、往后抬到嘴角）。"""
    t = min(max(s / JAW_HINGE_S, 0.0), 1.0)
    return 0.62 - 0.40 * t


def mouth_z(s):
    hw, ht, hb, zc, e = section(s)
    return zc - mouth_k(s) * hb


def mouth_theta(s):
    """嘴线落在截面上的角度（右侧；左侧取负）：上头外皮 θ ∈ [-mouth_theta, +mouth_theta]，其余是下颌。"""
    e = section(s)[4]
    k = mouth_k(s)
    return math.acos(-(k ** (e / 2.0)))


def jaw_hinge():
    """下颌铰链（骨骼 Jaw 的根）：嘴角处中轴线上、嘴线高度。"""
    return V((0.0, y_of(JAW_HINGE_S), mouth_z(JAW_HINGE_S)))


def jaw_surface(s, theta):
    """下颌外表面（闭嘴状态）。s 可以小于 0（伸出上吻端的部分沿用 s = 0 的截面，往前略收、往上翘）。
    θ 在 [mouth_theta(s), 2π - mouth_theta(s)]（经过腹中线）。"""
    if s >= 0.0:
        return surface(s, theta)
    p = surface(0.0, theta)
    t = s / JAW_FRONT_S
    shrink = 1.0 - 0.3 * t
    zm = mouth_z(0.0)
    return V((p.x * shrink, y_of(s), (p.z - zm) * shrink + zm + 0.3 * t))


# 唇和牙床：外皮在唇缘（嘴线）往里卷到「牙床线」为止；牙床线往里是嘴里的东西。
GUM_INSET = 0.6      # 牙床线离唇缘往里多少米（水平）
GUM_DROP = 0.3       # 上牙床比上唇缘往上缩多少米（下牙床往下缩同样多），唇包住牙根


def lip_point(s, side, upper=True):
    """唇缘（嘴线上）的点：side = -1 左 / +1 右。s 可以小于 0（只对下颌有效）。"""
    if upper:
        return surface(max(s, 0.0), side * mouth_theta(max(s, 0.0)))
    mt = mouth_theta(max(s, 0.0))
    return jaw_surface(s, math.pi - side * (math.pi - mt))


def gum_point(s, side, upper=True):
    """牙床线上的点：唇缘往里 GUM_INSET、往颌骨里缩 GUM_DROP。"""
    p = lip_point(s, side, upper)
    return p + V((-side * GUM_INSET, 0.0, GUM_DROP if upper else -GUM_DROP))


# 尖牙鱼的牙槽：下颌最前面那对最长獠牙闭嘴时插进上颚的这两个坑里（左右各一，在上牙床线往里）
FANG_SOCKET_S = 0.035
FANG_SOCKET_INSET = 1.1      # 从上唇缘往里多少米


def fang_socket(side):
    p = lip_point(FANG_SOCKET_S, side, True)
    return p + V((-side * FANG_SOCKET_INSET, 0.0, 0.0))


# ---------------------------------------------------------------------------- 眼睛、鳃、鳍
EYE_S = 0.075
EYE_THETA = math.radians(64)       # 右眼；左眼取负
EYE_RADIUS = 0.38                  # 眼球露出的半径（小，格陵兰睡鲨的眼睛本来就小）


def eye_center(side):
    return surface(EYE_S, side * EYE_THETA)


GILL_S = [0.236, 0.248, 0.260, 0.272, 0.284]   # 五道鳃裂的中心 s
GILL_THETA = math.radians(102)                  # 鳃裂中心的 θ（低，在侧面中线以下）
GILL_LENGTH = [2.4, 2.4, 2.3, 2.1, 1.8]        # 鳃裂长度（米），往后斜约 12°

# 鳍：根部中心 (s, θ)，根长（沿身体，米），伸出长度（米）。胸鳍、腹鳍左右各一（θ 取正负）
FINS = {
    "pectoral": dict(s=0.300, theta=math.radians(122), root=3.2, span=7.0),
    "pelvic": dict(s=0.585, theta=math.radians(150), root=2.0, span=3.4),
    "dorsal1": dict(s=0.500, theta=0.0, root=2.6, span=1.7),
    "dorsal2": dict(s=0.680, theta=0.0, root=1.8, span=1.2),
    # 尾鳍：从尾柄末端往后伸，上叶长、下叶也不小（格陵兰睡鲨）
    "caudal": dict(s=0.95, upper=8.5, lower=5.5),
}

# ---------------------------------------------------------------------------- 分区（谁负责哪一块）
# 皮（skin.py）：整张外皮——头、下颌外侧（权重给 Jaw）、唇（往里卷到牙床线）、身体、尾柄，连成一张（下颌是同一张皮上
#   沿嘴线切开的一块，铰链附近用权重过渡）；鳃裂（裂缝 + 后缘的皮瓣，皮瓣权重给 GillL/GillR，张开时往外翻）；眼窝（眼球不归你）；
#   劳伦氏壶腹孔；旧疤、咬坑、新伤（高模细节 + Area 区域图）。贴图组 "skin"，图集你来排。
# 鳍（fins.py）：FINS 里的全部鳍，根部融进皮里（在鳍根做 0.1～0.3 米的肉褶，盖住和皮的接缝）。贴图组 "fins"，图集你来排。
# 嘴（mouth.py）：牙床线往里的一切——牙床、上颚（含两个獠牙牙槽）、舌头 / 口底（权重给 Jaw）、喉咙（往里收成黑洞）、
#   嘴角颊膜（权重从脊椎骨渐变到 Jaw，张嘴不露空洞），以及**全部的牙**。贴图组 "mouth"，图集你来排。
# 眼（eyes.py）：两只眼球（浑浊乳白、表面有划痕和薄膜）、眼睑褶、挂在眼睛上的寄生桡足类（身体 + 两条长卵带，
#   卵带沿 ParasiteL/R 骨链）。贴图组 "eyes"，图集你来排。
SKULL_END = 0.30   # 头的「后脑」大约到这里（只用来估权重和碰撞；皮是一整张）

# ---------------------------------------------------------------------------- 贴图组
# size：贴图边长（像素）；meters：1 个 UV 单位对应多少米（图集要等密度，排不下就告诉总装加大）
# mask.A（Area）各组的含义：skin = 疤和新伤（0 正常皮，0.5 发白的旧疤，1 生肉）；fins = 鳍膜薄处（1 最薄、透光）；
#   mouth = 牙（1）/ 肉（0）；eyes = 寄生虫（1）/ 眼球（0）
TEXSETS = {
    "skin": dict(size=4096, meters=44.0),
    "fins": dict(size=2048, meters=24.0),
    "mouth": dict(size=2048, meters=18.0),
    "eyes": dict(size=1024, meters=3.0),
}

# 材质：名字对应 assets/materials/ 下的同名 .tres（Godot 导入时替换），每个贴图组一种（嘴里的肉和牙同组不同材质）
MATERIALS = {
    "M_GiantSkin": ((0.20, 0.18, 0.16), 0.7),     # 暗灰褐的盾鳞皮
    "M_GiantFin": ((0.18, 0.16, 0.15), 0.7),
    "M_GiantMouth": ((0.10, 0.05, 0.08), 0.35),   # 嘴里：黑紫、湿
    "M_GiantTooth": ((0.82, 0.80, 0.74), 0.3),    # 牙：半透明发白
    "M_GiantEye": ((0.75, 0.75, 0.72), 0.25),     # 浑浊的乳白眼球、寄生虫
}
MATERIAL_TEXSET = {"M_GiantSkin": "skin", "M_GiantFin": "fins", "M_GiantMouth": "mouth", "M_GiantTooth": "mouth",
                   "M_GiantEye": "eyes"}

UV_MAIN = "UVMap"
UV_BODY = "BodyST"

# 低模三角面预算（合起来约八万；细节都在贴图里）
TRI_BUDGET = {"skin": 45000, "fins": 9000, "mouth": 18000, "eyes": 3000}

# ---------------------------------------------------------------------------- 骨骼
SPINE_BONES = 16
TAIL_FIN_BONES = 2
TAIL_FIN_SEG = 3.5
PARASITE_BONES = 4
PARASITE_LENGTH = 2.4        # 寄生虫卵带的长度（米）——真实的只有几厘米，按比例放大到看得见


def spine_bone_name(i):
    return "Spine_%02d" % i


def spine_bone_span(i):
    return i / SPINE_BONES, (i + 1) / SPINE_BONES


def bone_at(s):
    return spine_bone_name(min(max(int(s * SPINE_BONES), 0), SPINE_BONES - 1))


def fin_root(name, side=1):
    f = FINS[name]
    return surface(f["s"], side * f["theta"])


def parasite_rest_points(side):
    """寄生虫卵带静止时的骨链（从眼睛往后下方垂）。"""
    p = eye_center(side) + normal(EYE_S, side * EYE_THETA) * 0.3
    pts = [p.copy()]
    seg = PARASITE_LENGTH / PARASITE_BONES
    for k in range(PARASITE_BONES):
        t = (k + 0.5) / PARASITE_BONES
        d = V((side * 0.25, -0.6 - 0.3 * t, -0.75)).normalized()
        p = p + d * seg
        pts.append(p.copy())
    return pts


def bones():
    """全部骨骼：[(名字, 头, 尾, 父骨名或 None)]。"""
    out = []
    prev = None
    for i in range(SPINE_BONES):
        a, b = spine_bone_span(i)
        out.append((spine_bone_name(i), center(a), center(b), prev))
        prev = spine_bone_name(i)
    tip = center(1.0)
    for k in range(TAIL_FIN_BONES):
        a = tip + V((0.0, -TAIL_FIN_SEG * k, 0.0))
        out.append(("TailFin_%d" % k, a, a + V((0.0, -TAIL_FIN_SEG, 0.0)), prev))
        prev = "TailFin_%d" % k
    h = jaw_hinge()
    out.append(("Jaw", h, V((0.0, y_of(JAW_FRONT_S), mouth_z(0.0) - 0.8)), bone_at(JAW_HINGE_S)))
    for side, tag in ((-1, "L"), (1, "R")):
        # 胸鳍两节：根 → 中段 → 梢（静止时往外、往下、往后张开）
        r = fin_root("pectoral", side)
        d = V((side * 0.75, -0.45, -0.5)).normalized()
        span = FINS["pectoral"]["span"]
        out.append(("Pec%s_0" % tag, r, r + d * span * 0.5, bone_at(FINS["pectoral"]["s"])))
        out.append(("Pec%s_1" % tag, r + d * span * 0.5, r + d * span, "Pec%s_0" % tag))
        r = fin_root("pelvic", side)
        d = V((side * 0.5, -0.7, -0.5)).normalized()
        out.append(("Pel%s" % tag, r, r + d * FINS["pelvic"]["span"], bone_at(FINS["pelvic"]["s"])))
        # 鳃：一根骨管一侧五道鳃裂的后缘皮瓣（绕身体纵轴往外翻）
        g = surface(GILL_S[2], side * GILL_THETA)
        out.append(("Gill%s" % tag, g, g + V((0.0, -1.0, 0.0)), bone_at(GILL_S[2])))
        # 寄生虫卵带
        pts = parasite_rest_points(side)
        parent = bone_at(EYE_S)
        for k in range(PARASITE_BONES):
            nm = "Parasite%s_%d" % (tag, k)
            out.append((nm, pts[k], pts[k + 1], parent))
            parent = nm
    return out


def tail_fin_weights(y):
    """尾柄末端和尾鳍上的点该分给尾鳍骨多少：[(骨名, 权重)]（总装在合并后统一分）。"""
    d = y_of(1.0) - y

    def sm(a, b, x):
        t = min(max((x - a) / (b - a), 0.0), 1.0)
        return t * t * (3 - 2 * t)
    if d < -1.0:
        return []
    w1 = sm(2.5, 4.5, d)
    w0 = sm(-1.0, 1.0, d) * (1.0 - w1)
    return [("TailFin_0", w0), ("TailFin_1", w1)]


# ---------------------------------------------------------------------------- 给部件用的工具
def set_body_uv(ob):
    me = ob.data
    uv = me.uv_layers.get(UV_BODY) or me.uv_layers.new(name=UV_BODY)
    mw = ob.matrix_world
    st = [body_coords(mw @ v.co) for v in me.vertices]
    for loop in me.loops:
        s, th = st[loop.vertex_index]
        uv.data[loop.index].uv = (s, th / math.pi)


def spine_weights(s):
    f = s * SPINE_BONES - 0.5
    i0 = int(math.floor(f))
    t = f - i0
    if i0 < 0:
        return [(spine_bone_name(0), 1.0)]
    if i0 >= SPINE_BONES - 1:
        return [(spine_bone_name(SPINE_BONES - 1), 1.0)]
    return [(spine_bone_name(i0), 1.0 - t), (spine_bone_name(i0 + 1), t)]


def assign_spine(ob, rigid=False, s=None):
    """按顶点所在的 s 给脊椎骨权重；rigid 时整个物体只跟一根骨。"""
    mw = ob.matrix_world
    groups = {}

    def g(name):
        if name not in groups:
            groups[name] = ob.vertex_groups.get(name) or ob.vertex_groups.new(name=name)
        return groups[name]

    if rigid:
        if s is None:
            ys = [(mw @ v.co).y for v in ob.data.vertices]
            s = s_of(0.5 * (min(ys) + max(ys)))
        g(bone_at(s)).add([v.index for v in ob.data.vertices], 1.0, 'REPLACE')
        return
    for v in ob.data.vertices:
        for name, w in spine_weights(s_of((mw @ v.co).y)):
            if w > 1e-4:
                g(name).add([v.index], w, 'REPLACE')


def assign_bone(ob, bone):
    vg = ob.vertex_groups.get(bone) or ob.vertex_groups.new(name=bone)
    vg.add([v.index for v in ob.data.vertices], 1.0, 'REPLACE')


def rng_for(name):
    return np.random.default_rng(zlib.crc32(name.encode()))
