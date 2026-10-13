"""船员的头（捏脸用）：Vitruvian——CharMorph 的写实角色（CC0，Sean Buckley 在 Antonia Polygon 上改出来的，
https://github.com/seenbuklee/CharMorph-Vitruvian），男女同一套拓扑、可以连续渐变。

先跑 python tools/fetch_vitruvian.py（下到 blender/cache/charmorph/vitruvian/，不进 git），再：
    Blender -b -Y --factory-startup --python blender/scripts/gen_head_vitruvian.py [-- --preview 目录]
gen_crew.py 发现头没生成、或者这个脚本改过，会自己调一遍。
产出 blender/cache/charmorph/crew_head.blend（gen_crew 追加到身体上）和 assets/textures/crew/ 下的贴图：

- 网格：全身网格里只留头和脖子（皮肤 UDIM 1001 那一块）、眼球（眼白连角膜、虹膜、瞳孔、角膜外面那层泪膜）；
  口腔（牙、牙龈、舌头）单独一块 Crew_Mouth；外加眼部遮蔽（Eyeshadow，盖在眼球上的一层软阴影，眼睛不再像贴上去的）、
  泪线（Tearline，眼睑和眼球交界处那条湿的高光）、睫毛（粒子毛发转成的细条）；
  头发：长发每个发型一块发片网格 Crew_Hair_xxx（Vitruvian 的发型引导线，不够密的插值出子发丝，每根一片，贴发丝贴图），
  另外每个发型一块层壳 Crew_Shell_xxx（头皮往外复制好几层，着色器里撒发丝：短发全靠它，长发拿它打底）
- 形态键：捏脸的 ID_xxx（脸型、眼、鼻、嘴、下巴、耳朵、性别……，Vitruvian 的 L2 形态，值域见 ID；
  Vitruvian 的形态是微调用的，另按五官位置造了几个大范围的 ID_Macro_xxx：脸宽、V 脸、瘦颊、眼睛大小、眼角、鼻子窄……）、
  表情的 EX_xxx（眨眼、看左右上下、瞳孔缩放、眉毛、笑、口型……，L3 形态）。睫毛、泪线、遮蔽按最近的皮肤三角形绑定，
  每个形态算一遍跟着走；只动不到的形态键删掉
- 贴图（assets/textures/crew/）：皮肤浅色 / 深色两张反照率（肤色在两张之间插值）、法线（由置换图求）、
  凹度 / 粗糙度 / 油光（R G B）、遮罩（R 嘴唇、G 胡茬、B 头皮、A 透光厚度）、化妆遮罩（R 眼线、G 眼影、B 腮红）、
  眉毛（14 种，按发丝画到 UV 上，一张竖着排的 Texture2DArray）、眼白、虹膜、口腔
"""
import json
import math
import os
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Vector as V
from mathutils.bvhtree import BVHTree

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
VIT = os.path.join(ROOT, "blender", "cache", "charmorph", "vitruvian")
OUT = os.path.join(ROOT, "blender", "cache", "charmorph", "crew_head.blend")
TEX = os.path.join(ROOT, "assets", "textures", "crew")
SIZE = 4096          # 皮肤贴图边长（头那一块 UDIM 原图就是 4K，原样用：捏脸拉近看脸时毛孔、雀斑都在）
MASK_SIZE = 2048     # 遮罩、化妆遮罩（都是软的过渡，2K 够了）
BROW_W, BROW_H = 2048, 1024  # 每种眉毛的贴图（只盖两道眉毛那一片 UV，一个像素约 0.07 毫米，一根眉毛一两个像素宽）

# 捏脸用的形态（L2）：脸、头、脖子上的；全身的（体型、肌肉）、奇幻的（猫眼、尖牙）不要
ID = [
    "Gender_FemaleHeadOnly", "Gender_MaleHeadOnly", "Age_Old",
    "Face_Puffy", "Fat_Face", "Fat_DoubleChin", "Face_Maxilla", "Face_Zygomatic_Bone", "Face_FrontalBone",
    "Face_FrontalBone_BrowRidge", "Face_FrontalBone_FrontalEminence", "Face_BrowRidge_Raise", "Face_BrowRidge_Droop",
    "Face_BrowRidge_CurvedRaise", "Face_BrowRidge_CurvedDroop", "Face_EyeSocket_Protrusion",
    "Cheeks_BoneDefinition", "Cheeks_BuccalFat", "Cheeks_CheeksBonePositionZ", "Cheeks_UpperCheek_Bone",
    "Jaw_Definition", "Jaw_Mandible", "Jaw_Mandible_GonialAngle", "Jaw_Ramus_Extrusion", "Jaw_Ramus_LocY", "Jaw_Width",
    "Chin_ChinCleft", "Chin_Height", "Chin_Portrusion", "Chin_PosZ", "Chin_SecondaryWidth", "Chin_Tilt", "Chin_Width",
    "Eyes_Size", "Eyes_Distance", "Eyes_VerticalShift", "Eyes_EyelidsAngle", "Eyes_EyelidsAngle2", "Eyes_Eyelid_Monolid",
    "Eyes_Eyelid_Hooded", "Eyes_EyelidsCrease", "Eyes_UpperLidOpenness", "Eyes_LowerLidOpenness", "Eyes_EyeBagsSize",
    "Eyes_EyeBagsProminence", "Eyes_EyebrowsAngle", "Eyes_EyebrowsDroop", "Eyes_LacrimalCaruncle_Sharpness",
    "Nose_BridgeProminence", "Nose_Flatness", "Nose_NasalAngle", "Nose_NasalBone", "Nose_NasalBone_AnteriorNasalAperature",
    "Nose_NasalBone_AnteriorNasalSpine", "Nose_NoseHeight", "Nose_NostrilSize", "Nose_Protrusion", "Nose_Tip_Protrusion",
    "Nose_Tip_Z", "Nose_Width", "Nose_BottomFlatness", "Nose_TipCrease",
    "Mouth_Lips_Height", "Mouth_Lips_Length", "Mouth_Lips_UpperLipArch", "Mouth_Lips_UpperAngle", "Mouth_Lips_LowerAngle",
    "Mouth_Lips_UpperLipDepth", "Mouth_Lips_BottomLipDepth", "Mouth_PhiltrumHeight", "Mouth_PhiltrumDepth",
    "Ears_Height", "Ears_Length", "Ears_Protrusion", "Ears_Round", "Ears_Lobe",
    "Head_ParietalFlatness", "Head_BackScalp_Protrusion", "Head_TopScalpPotrusion", "Head_SideScalp_Protrusion",
    "Head_FrontalBoneFlatness", "Neck_AdamsApple", "Neck_ChinConnection", "Generic_Assymetry",
]
# 表情（L3）：眨眼、视线、瞳孔、眉毛、笑、张嘴、口型（14 个，够 Oculus 那套 15 个口型用：sil 就是全 0）
EX = [
    "Eyes_Closed_Left", "Eyes_Closed_Right", "Eyes_Squint",
    "Look_Up_Left", "Look_Up_Right", "Look_Dwn_Left", "Look_Dwn_Right", "Look_In_Left", "Look_In_Right",
    "Look_Out_Left", "Look_Out_Right",
    "Pupil_Dilation_Left", "Pupil_Dilation_Right", "Pupil_Constriction_Left", "Pupil_Constriction_Right",
    "Eyebrows_Raised_Left", "Eyebrows_Raised_Right", "Eyebrows_Frown_Left", "Eyebrows_Frown_Right",
    "Eyebrows_InnerBrow_Raised_Left", "Eyebrows_InnerBrow_Raised_Right",
    "Smile_Lips_Closed", "Smile_Lips_Closed_Left", "Smile_Lips_Closed_Right", "Happy", "Sad", "Angry", "Scared",
    "Frown_Left", "Frown_Right", "Jaw_Lower", "Mouth_Large_Opened",
    "p_b_m_21", "f_v_18", "th_dh_17", "d_t_n_19", "k_g_ng_20", "sh_ch_jh_zh_16", "s_z_15", "l_14", "r_13",
    "aa_02", "ey_eh_uh_04", "y_iy_ih_ix_06", "ow_08", "w_uw_07",
]
# 原网格的材质槽：EyeHair, UDIM.Skin, censor, AqueosLayer, Pupil, Sclera_Cornea, Iris, Mouth
SKIN, AQUEOUS, PUPIL, SCLERA, IRIS, MOUTH = 1, 3, 4, 5, 6, 7
SLOTS = {SKIN: "Crew_Skin", AQUEOUS: "Crew_Aqueous", PUPIL: "Crew_Pupil", SCLERA: "Crew_Sclera", IRIS: "Crew_Iris",
         MOUTH: "Crew_Mouth"}
BROWS = [f"mind_eyebrows_{i:02d}" for i in range(1, 15)]
BROWS[10] = "mind_eyebrows_11_Default"


def _arg(name, default=None):
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    return argv[argv.index(name) + 1] if name in argv else default


def _co(src, n):
    a = np.empty(n * 3, np.float32)
    src.foreach_get("co", a)
    return a.reshape(n, 3)


def morph(name):
    """形态 name 的位移（全身 39168 个顶点，米）：L2 / L3 里的 .npy 是全量、.npz 是 idx + delta。"""
    for lvl in ("L2", "L3"):
        p = os.path.join(VIT, "morphs", lvl, name)
        if os.path.exists(p + ".npy"):
            return np.load(p + ".npy")
        if os.path.exists(p + ".npz"):
            z = np.load(p + ".npz")
            d = np.zeros((N_FULL, 3))
            d[z["idx"]] = z["delta"]
            return d
    raise SystemExit("gen_head_vitruvian: 没有形态 " + name)


# ============================================================================ 大形态
# Vitruvian 的捏脸形态是微调用的（下颌宽窄拉满才 3 毫米）。这里按五官位置自己造几个大范围的（ID_Macro_xxx）：
# 在锚点附近一个椭球范围里按平滑衰减做缩放 / 平移 / 旋转，值 1 时的位移；跟原有形态一样带着睫毛、头发走
MACROS = ["FaceWidth", "VLine", "CheekSlim", "ChinLength", "MidfaceShort", "EyeScale", "EyeTilt", "NoseSlim",
          "NoseShort", "LipFull", "MouthSmall"]


def _falloff(p, c, r):
    """椭球（中心 c、三轴半径 r）里从 1 平滑降到边上的 0。"""
    d = np.linalg.norm((p - c) / r, axis=1)
    return _ss(1.0, 0.0, d)


def macro_morphs(base, lm):
    """lm：五官锚点（眼睛 eye_l / eye_r、鼻尖 nose、嘴 mouth、下巴 chin、下颌角 jaw_l / jaw_r，都在 Default 形状下）。
    返回 {名字: 全身 39168 个顶点的位移}。脸朝 -Y，x 是左右，z 朝上。"""
    p = base
    out = {}
    eye_z = (lm["eye_l"][2] + lm["eye_r"][2]) / 2
    front = _ss(lm["jaw_l"][1] + 0.03, lm["jaw_l"][1] - 0.01, p[:, 1])      # 下颌角往前的部分（耳朵、后脑不动）
    # 脸宽：颧骨到下颌一整片往两边推（±8%）
    w = front * _ss(eye_z + 0.04, eye_z, p[:, 2]) * _ss(lm["chin"][2] - 0.01, lm["chin"][2] + 0.03, p[:, 2])
    d = np.zeros_like(p)
    d[:, 0] = p[:, 0] * 0.08 * w
    out["FaceWidth"] = d
    # V 脸：嘴以下、离中线越远往里收得越多（下颌角收 9 毫米），下巴尖往前一点
    w = front * _ss(lm["mouth"][2] + 0.02, lm["chin"][2] + 0.005, p[:, 2])
    d = np.zeros_like(p)
    d[:, 0] = -p[:, 0] * 0.16 * w
    d[:, 1] = -0.003 * w * _ss(0.03, 0.0, np.abs(p[:, 0]))
    out["VLine"] = d
    # 瘦颊：颧骨下面、嘴两边那片往里凹
    d = np.zeros_like(p)
    for s, j in ((1, "jaw_l"), (-1, "jaw_r")):
        c = np.array([lm[j][0] * 0.8, (lm[j][1] + lm["mouth"][1]) / 2, (eye_z + lm["mouth"][2]) / 2 - 0.01])
        w = _falloff(p, c, np.array([0.035, 0.04, 0.035]))
        d[:, 0] += -np.sign(p[:, 0]) * 0.005 * w * (p[:, 0] * s > 0)
    out["CheekSlim"] = d
    # 下巴长短：嘴以下往下拉 8 毫米（越往下越多）
    w = front * _ss(lm["mouth"][2], lm["chin"][2] - 0.01, p[:, 2]) * _ss(0.07, 0.03, np.abs(p[:, 0]))
    d = np.zeros_like(p)
    d[:, 2] = -0.008 * w
    out["ChinLength"] = d
    # 中庭短：眼睛下面到嘴这一段往上提（嘴、下巴整体上移 6 毫米，眼睛不动）
    w = front * _ss(eye_z - 0.005, lm["nose"][2] - 0.01, p[:, 2])
    d = np.zeros_like(p)
    d[:, 2] = 0.006 * w
    out["MidfaceShort"] = d
    # 眼睛大小、眼角上扬：眼睛（连眼皮、眼球）绕眼睛中心放大 15%、外眼角往上转 8°
    d_scale = np.zeros_like(p)
    d_tilt = np.zeros_like(p)
    for s, e in ((1, "eye_l"), (-1, "eye_r")):
        c = np.array(lm[e])
        w = _falloff(p, c, np.array([0.03, 0.03, 0.022])) * (p[:, 0] * s > 0)
        d_scale += (p - c) * 0.15 * w[:, None]
        a = math.radians(8) * s
        rx = (p[:, 0] - c[0]) * math.cos(a) - (p[:, 2] - c[2]) * math.sin(a) + c[0]
        rz = (p[:, 0] - c[0]) * math.sin(a) + (p[:, 2] - c[2]) * math.cos(a) + c[2]
        d_tilt[:, 0] += (rx - p[:, 0]) * w
        d_tilt[:, 2] += (rz - p[:, 2]) * w
    out["EyeScale"] = d_scale
    out["EyeTilt"] = d_tilt
    # 鼻子窄、鼻子短：鼻子那片左右收 20%；鼻头往上提 4 毫米
    c = np.array(lm["nose"]) + np.array([0, 0.012, 0.008])
    w = _falloff(p, c, np.array([0.03, 0.035, 0.035]))
    d = np.zeros_like(p)
    d[:, 0] = -p[:, 0] * 0.2 * w
    out["NoseSlim"] = d
    w = _falloff(p, np.array(lm["nose"]), np.array([0.025, 0.03, 0.022]))
    d = np.zeros_like(p)
    d[:, 2] = 0.004 * w
    d[:, 1] = 0.001 * w
    out["NoseShort"] = d
    # 嘴唇厚、嘴小：嘴那片上下放大 25%；左右收 12%
    c = np.array(lm["mouth"])
    w = _falloff(p, c, np.array([0.035, 0.025, 0.018]))
    d = np.zeros_like(p)
    d[:, 2] = (p[:, 2] - c[2]) * 0.25 * w
    d[:, 1] = -0.0015 * w
    out["LipFull"] = d
    w = _falloff(p, c, np.array([0.04, 0.03, 0.025]))
    d = np.zeros_like(p)
    d[:, 0] = -(p[:, 0] - c[0]) * 0.12 * w
    out["MouthSmall"] = d
    return out


def landmarks(me, idx, base, eyes):
    """大形态的锚点：嘴（唇遮罩亮的那些顶点的中心）、鼻尖（中线上眼睛和嘴之间最靠前的点）、
    下巴（嘴以下中线上最低、最靠前那一截的最低点）、下颌角（嘴高度往下 2 厘米、左右最宽、偏后的点）。"""
    co = base[idx]
    lip = _attr(me, "ColLipMask")[:, 0]
    vi = np.empty(len(me.loops), np.int32)
    me.loops.foreach_get("vertex_index", vi)
    skin_loop = np.zeros(len(me.loops), bool)
    for pl in me.polygons:
        if pl.material_index == SKIN:
            skin_loop[pl.loop_start:pl.loop_start + pl.loop_total] = True
    lv = np.unique(vi[(lip > 0.5) & skin_loop])        # 只算皮肤上的（口腔里面也带着唇遮罩）
    mouth = co[lv].mean(0)
    mid = co[(np.abs(co[:, 0]) < 0.004)]
    nose = mid[(mid[:, 2] < eyes[1][2] - 0.01) & (mid[:, 2] > mouth[2] + 0.01)]
    nose = nose[np.argmin(nose[:, 1])]
    ch = mid[(mid[:, 2] < mouth[2] - 0.01) & (mid[:, 1] < mouth[1] + 0.03)]
    chin = ch[np.argmin(ch[:, 2])]
    band = co[(np.abs(co[:, 2] - (mouth[2] - 0.02)) < 0.006) & (co[:, 1] > mouth[1])]
    jaw = {s: band[np.argmax(band[:, 0] * s)] for s in (1, -1)}
    lm = {"eye_l": eyes[1], "eye_r": eyes[-1], "mouth": mouth, "nose": nose, "chin": chin, "jaw_l": jaw[1], "jaw_r": jaw[-1]}
    print("  landmarks", {k: [round(float(x), 3) for x in v] for k, v in lm.items()})
    return lm


# ============================================================================ 毛发
def strands_from_psys(ob, name):
    """粒子毛发 name 每一根的点（物体坐标，形状是当前的网格）。"""
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    mod = next(m for m in ev.modifiers if m.type == 'PARTICLE_SYSTEM' and m.particle_system.name == name)
    out = []
    for p in mod.particle_system.particles:
        out.append(np.array([k.co_object(ev, mod, p)[:] for k in p.hair_keys], np.float64))
    return out


def strands_from_npz(name):
    """hairstyles/name.npz：cnt 每根几段、data 去掉根的各点（Default 形状下的物体坐标）。"""
    z = np.load(os.path.join(VIT, "hairstyles", name + ".npz"))
    cnt, data = z["cnt"], z["data"].astype(np.float64)    # npz 每取一次数组都要重新解压，先取出来
    out, i = [], 0
    for c in cnt:
        out.append(data[i:i + int(c)])
        i += int(c)
    return out


class Binding:
    """把一堆点绑到皮肤三角形上：每个点找最近的三角形，记下重心坐标和（可选）在三角形局部坐标系里的偏移。
    形态改了皮肤以后按新的三角形把点摆回去——rigid=True 时偏移跟着三角形转（睫毛跟着眼皮转下去），
    否则只平移（头发离头皮远，转的话力臂太长）。"""

    def __init__(self, pts, co, tris, rigid=False, anchor=None):
        bvh = BVHTree.FromPolygons([V(c) for c in co], tris.tolist())
        self.tris = tris
        self.rigid = rigid
        q = pts if anchor is None else anchor
        self.face = np.empty(len(q), np.int64)
        locs = np.empty((len(q), 3))
        for i, p in enumerate(q):
            loc, _, f, _ = bvh.find_nearest(V(p))
            self.face[i] = f
            locs[i] = loc
        t = tris[self.face]
        self.bary = _bary_many(locs, co[t[:, 0]], co[t[:, 1]], co[t[:, 2]])
        self.local = self._to_local(pts, co)

    def _frame(self, co):
        t = self.tris[self.face]
        a, b, c = co[t[:, 0]], co[t[:, 1]], co[t[:, 2]]
        o = a * self.bary[:, :1] + b * self.bary[:, 1:2] + c * self.bary[:, 2:]
        x = _unit(b - a)
        n = _unit(np.cross(b - a, c - a))
        y = np.cross(n, x)
        return o, x, y, n

    def _to_local(self, pts, co):
        o, x, y, n = self._frame(co)
        d = pts - o
        if not self.rigid:
            return d
        return np.stack([(d * x).sum(1), (d * y).sum(1), (d * n).sum(1)], 1)

    def place(self, co):
        o, x, y, n = self._frame(co)
        if not self.rigid:
            return o + self.local
        lx, ly, ln = self.local[:, :1], self.local[:, 1:2], self.local[:, 2:]
        return o + lx * x + ly * y + ln * n


def _unit(v):
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-12)


def _bary(p, a, b, c):
    v0, v1, v2 = b - a, c - a, p - a
    d00, d01, d11 = v0 @ v0, v0 @ v1, v1 @ v1
    d20, d21 = v2 @ v0, v2 @ v1
    den = d00 * d11 - d01 * d01
    if abs(den) < 1e-20:
        return np.array([1.0, 0.0, 0.0])
    v = (d11 * d20 - d01 * d21) / den
    w = (d00 * d21 - d01 * d20) / den
    return np.array([1 - v - w, v, w])


def _bary_many(p, a, b, c):
    """_bary 的批量版（每行一个点、一个三角形）。"""
    v0, v1, v2 = b - a, c - a, p - a
    d00, d01, d11 = (v0 * v0).sum(1), (v0 * v1).sum(1), (v1 * v1).sum(1)
    d20, d21 = (v2 * v0).sum(1), (v2 * v1).sum(1)
    den = d00 * d11 - d01 * d01
    ok = np.abs(den) > 1e-20
    den = np.where(ok, den, 1.0)
    v = np.where(ok, (d11 * d20 - d01 * d21) / den, 0.0)
    w = np.where(ok, (d00 * d21 - d01 * d20) / den, 0.0)
    return np.stack([1 - v - w, v, w], 1)


def resample(s, n):
    """把一根发丝按弧长重采样成 n 个点。"""
    seg = np.linalg.norm(np.diff(s, axis=0), axis=1)
    t = np.concatenate([[0], np.cumsum(seg)])
    if t[-1] <= 0:
        return np.repeat(s[:1], n, 0)
    u = np.linspace(0, t[-1], n)
    return np.stack([np.interp(u, t, s[:, k]) for k in range(3)], 1)


def lash_mesh(strands):
    """睫毛：每根一条细带子，宽度从根 0.22 毫米收到梢 0.06 毫米，面朝前（-Y）；UV 的 u 横跨带子、v 从根到梢。
    返回 (顶点, 面, 每个顶点的 UV, 每个顶点所在那根的根)。"""
    verts, faces, uvs, roots = [], [], [], []
    for s in strands:
        p = resample(s, 6)
        t = _unit(np.gradient(p, axis=0))
        w = _unit(np.cross(t, np.array([0.0, -1.0, 0.0])))
        for i, (c, d) in enumerate(zip(p, w)):
            k = i / (len(p) - 1)
            half = (0.11 - 0.08 * k) * 1e-3
            base = len(verts)
            verts += [c - d * half, c + d * half]
            uvs += [(0.0, k), (1.0, k)]
            roots += [s[0], s[0]]
            if i:
                faces.append((base - 2, base - 1, base + 1, base))
    return np.array(verts), faces, np.array(uvs), np.array(roots)


# ============================================================================ 头发
# 发型：[模型里的名字, Vitruvian 的发型, 几片, 发片宽（毫米，根部）, 段数]。光头、寸头不用发片（寸头是头皮上画发茬）
HAIRSTYLES = [
    ("crop", "Combover_zoro_d", 3800, 5.0, 4),
    ("slick", "SlickedBack", 1800, 9.0, 8),
    ("bob", "Bob", 1500, 16.0, 10),
    ("long", "Eve", 1700, 16.0, 14),
    ("back", "Back1", 1500, 15.0, 12),
]
# 层壳头发（头皮那片往外复制好几层，每层按梳的方向倒一点，着色器里按格子撒发丝）：
# [模型里的名字, 发际线（发量）按哪个发型的发根算, 梳的方向 / 长度按哪个发型算, 层数, 最长（米）, 倒伏（往梳的方向倒多少）]。
# 寸头只有层壳；别的发型层壳只是发根打底（发片之间不露头皮），头发靠发片。
# 短发后梳那套引导线前额缺根，发量借碎短发的（3 万根，长头发的地方都有）
SHELLS = [
    ("buzz", "Combover_zoro_d", "Combover_zoro_d", 8, 0.0035, 0.3),
    ("crop", "Combover_zoro_d", "Combover_zoro_d", 5, 0.004, 0.6),
    ("slick", "Combover_zoro_d", "SlickedBack", 5, 0.003, 1.2),
    ("bob", "Bob", "Bob", 6, 0.004, 1.0),
    ("long", "Eve", "Eve", 6, 0.004, 1.0),
    ("back", "Back1", "Back1", 6, 0.004, 1.2),
]
HAIR_COLS = 8          # 发丝贴图横着分几列（每列一种发束），发片随机挑一列


def hair_texture(w=2048, h=2048, seed=21):
    """发丝贴图：横着 HAIR_COLS 列，每列一束头发（几十根微微弯曲的发丝，越往梢越往中间收、有几根短的飞毛），
    v 从根（0）到梢（1）。R 每根发丝的明暗、G 根部压暗、A 透明度。"""
    rng = np.random.default_rng(seed)
    a = np.zeros((h, w))
    br = np.zeros((h, w))
    cw = w // HAIR_COLS
    vs = np.arange(h) / (h - 1)
    rows = np.arange(h)
    for c in range(HAIR_COLS):
        x0 = c * cw
        for _ in range(rng.integers(120, 170)):
            u = rng.uniform(0.08, 0.92)
            end = 1.0 if rng.random() > 0.3 else rng.uniform(0.55, 0.95)
            amp, ph, fr = rng.uniform(0.0, 0.04), rng.uniform(0, 6.3), rng.uniform(2, 6)
            width, alpha, bright = rng.uniform(1.4, 3.2), rng.uniform(0.55, 1.0), rng.uniform(0.0, 1.0)
            clump = rng.uniform(0.2, 0.6)
            # 每一行这根发丝的横坐标（像素）
            xs = u + amp * np.sin(vs * fr + ph)
            xs = x0 + (xs + (0.5 - xs) * clump * vs ** 2) * cw
            taper = np.clip((end - vs) / 0.12, 0, 1) * np.clip(vs / 0.02, 0, 1) * (vs <= end)
            for dx in range(-4, 5):
                xi = np.floor(xs).astype(int) + dx
                ok = (xi >= x0) & (xi < x0 + cw)
                cov = np.clip(width / 2 + 0.5 - np.abs(xi + 0.5 - xs), 0, 1) * alpha * taper * ok
                r, x = rows[ok], xi[ok]
                cv = cov[ok]
                br[r, x] = np.where(cv > a[r, x], bright, br[r, x])
                a[r, x] = 1 - (1 - a[r, x]) * (1 - cv)
    out = np.zeros((h, w, 4), np.float32)
    out[..., 0] = br
    out[..., 1] = np.clip(vs[:, None] / 0.3, 0, 1)
    out[..., 3] = a
    _save("hair", out)


def hair_children(strands, n, rng, bvh):
    """从引导线插值出 n 根子发丝：每根随机挑一根引导线，根在它旁边的头皮上随机挪一点，形状照抄离新根最近的那根引导线
    （几根按距离混起来的话，前面刘海和侧面的引导线一混就混出横穿脸的发丝）。返回 n 根（点数和引导线一样）。"""
    roots = np.array([s[0] for s in strands])
    rel = np.array([s - s[0] for s in strands])
    spacing = np.median([np.sort(np.linalg.norm(roots - r, axis=1))[1] for r in roots[:200]])
    out = []
    for _ in range(n):
        i = rng.integers(len(strands))
        r = roots[i] + rng.normal(0, spacing * 0.7, 3)
        loc, nrm, _, _ = bvh.find_nearest(V(r))
        if loc is not None:
            r = np.array(loc) + np.array(nrm) * 0.0005
        k = int(np.argmin(np.linalg.norm(roots - r, axis=1)))
        out.append(r + rel[k] * rng.uniform(0.92, 1.05))
    return out


def hair_cards(strands, n_cards, width_mm, segs, rng, head_co, head_tris, center):
    """发片：每根（插值出来的）发丝一片，宽度方向贴着头皮（发丝走向 × 往外的方向），根宽梢窄；
    整片往外推，离头皮至少 1.5 毫米（再随机加 0~3 毫米分出层次）。返回 (顶点, 面, UV)。"""
    bvh = BVHTree.FromPolygons([V(c) for c in head_co], head_tris.tolist())
    rs = [resample(s, segs + 1) for s in strands if len(s) > 1 and np.linalg.norm(s[-1] - s[0]) > 0.004]
    if len(rs) < n_cards:
        kids = hair_children(rs, n_cards - len(rs), rng, bvh)
        rs = rs + kids
    else:
        rs = [rs[i] for i in rng.choice(len(rs), n_cards, replace=False)]
    verts, faces, uvs, cols = [], [], [], []
    for s in rs:
        lift = 0.0015 + rng.uniform(0.0, 0.003)
        tone = rng.uniform(0.0, 1.0)
        p = s.copy()
        for j in range(len(p)):
            loc, nrm, _, _ = bvh.find_nearest(V(p[j]))
            if loc is None:
                continue
            loc, nrm = np.array(loc), np.array(nrm)
            sd = (p[j] - loc) @ nrm
            if sd < lift:
                p[j] += nrm * (lift - sd)
        t = _unit(np.gradient(p, axis=0))
        rel = p - center
        rel[:, 2] *= np.where(rel[:, 2] < 0, 0.2, 1.0)      # 垂到头下面的部分：往外取水平方向
        out = _unit(rel)
        side = _unit(np.cross(t, out))
        w0 = width_mm * 1e-3 * rng.uniform(0.75, 1.25)
        col = rng.integers(HAIR_COLS)
        u0, u1 = (col + 0.04) / HAIR_COLS, (col + 0.96) / HAIR_COLS
        base = len(verts)
        layer = (lift - 0.0015) / 0.003
        for j in range(len(p)):
            k = j / (len(p) - 1)
            half = w0 * (1 - 0.4 * k) / 2
            verts += [p[j] - side[j] * half, p[j] + side[j] * half]
            uvs += [(u0, k), (u1, k)]
            cols += [(tone, 1.0, layer, 1.0)] * 2
            if j:
                b = base + 2 * j
                faces.append((b - 2, b - 1, b + 1, b))
    return np.array(verts), faces, np.array(uvs), np.array(cols)


# 头发跟着这几个形态走（头型、性别、年纪、额头、耳朵、脸宽），表情里只跟眉毛的（抬眉时刘海跟着额头动）
HAIR_KEYS = ["Gender_FemaleHeadOnly", "Gender_MaleHeadOnly", "Age_Old", "Head_TopScalpPotrusion",
             "Head_BackScalp_Protrusion", "Head_SideScalp_Protrusion", "Head_ParietalFlatness", "Head_FrontalBoneFlatness",
             "Face_FrontalBone", "Face_FrontalBone_FrontalEminence", "Fat_Face", "Ears_Protrusion", "Ears_Height",
             "Face_Zygomatic_Bone", "Jaw_Width", "Macro_FaceWidth", "Macro_VLine", "Macro_ChinLength"]


def build_shells(me, idx, base, deltas):
    """层壳头发（Crew_Shell_xxx，见 SHELLS）：头皮那片（这个发型有头发的皮肤面）复制成好几层，第 l 层往外抬 h = 长度 × l/(层数-1)
    （一部分沿法线、一部分往梳的方向倒）。每个顶点：发量（离最近的发根多远：发际线处渐稀）、梳的方向（附近发丝最初 12 毫米的走向，
    投到切平面上）、长度（附近发丝的长度，不超过这个发型的最长），都从发型的引导线算。顶点色 R 是第几层（0~1）、G 是发量、
    B A 是梳的方向在头皮 UV 里的方向（× 0.5 + 0.5；Blender 的 UV，v 朝上）。
    形态键和头皮一样（每层同一份位移）。"""
    from mathutils.kdtree import KDTree
    co = base[idx]
    n = len(co)
    vn = np.empty(n * 3, np.float32)
    me.vertex_normals.foreach_get("vector", vn)
    vn = vn.reshape(-1, 3).astype(np.float64)
    uv = _uv(me)
    skin = [p for p in me.polygons if p.material_index == SKIN]
    keys = {k: d for k, d in deltas.items() if (k.startswith("ID_") and k[3:] in HAIR_KEYS)
            or k.startswith("EX_Eyebrows")}
    obs = []
    for key, dens_src, src, layers, max_len, lean in SHELLS:
        strands = [s for s in strands_from_npz(src) if len(s) > 1]
        roots = np.array([s[0] for s in strands])
        dirs, lens = [], []
        for st in strands:
            seg = np.linalg.norm(np.diff(st, axis=0), axis=1)
            cum = np.concatenate([[0], np.cumsum(seg)])
            k = min(int(np.searchsorted(cum, min(0.012, cum[-1]))), len(st) - 1)
            dirs.append(_unit(st[k] - st[0]))
            lens.append(cum[-1])
        dirs, lens = np.array(dirs), np.array(lens)
        kd = KDTree(len(roots))
        for i, r in enumerate(roots):
            kd.insert(r, i)
        kd.balance()
        droots = roots if dens_src == src else np.array([st[0] for st in strands_from_npz(dens_src) if len(st) > 1])
        kdd = KDTree(len(droots))
        for i, r in enumerate(droots):
            kdd.insert(r, i)
        kdd.balance()
        spacing = np.median([kd.find_n(r, 2)[1][2] for r in roots[::max(1, len(roots) // 300)]])
        dspacing = np.median([kdd.find_n(r, 2)[1][2] for r in droots[::max(1, len(droots) // 300)]])
        r_in = max(1.2 * dspacing, 0.003)
        r_out = r_in + 0.007
        dens = np.zeros(n)
        lean_dir = np.zeros((n, 3))
        length = np.zeros(n)
        for v in range(n):
            d0 = kdd.find(co[v])[2]
            if d0 > r_out:
                continue
            dens[v] = _ss(r_out, r_in, d0)
            near = kd.find_n(co[v], 6)
            ids = [i for _, i, _ in near]
            w = np.array([1 / (d + spacing) ** 2 for _, _, d in near])
            dv = (dirs[ids] * w[:, None]).sum(0)
            dv -= vn[v] * (dv @ vn[v])
            lean_dir[v] = _unit(dv)
            length[v] = min((lens[ids] * w).sum() / w.sum(), max_len)
        faces = [p for p in skin if dens[list(p.vertices)].max() > 0.02]
        # 梳的方向换算成头皮 UV 里的方向（着色器沿它画发束、拉长高光）：每个面求 UV → 三维的雅可比，
        # 最小二乘解出 UV 里的方向，顶点上取相邻面的平均
        uvdir = np.zeros((n, 2))
        for p in faces:
            vs, ls_ = list(p.vertices), list(p.loop_indices)
            P = np.array([co[vs[1]] - co[vs[0]], co[vs[2]] - co[vs[0]]]).T
            U = np.array([uv[ls_[1]] - uv[ls_[0]], uv[ls_[2]] - uv[ls_[0]]]).T
            if abs(np.linalg.det(U)) < 1e-12:
                continue
            J = P @ np.linalg.inv(U)
            for v in vs:
                w = np.linalg.lstsq(J, lean_dir[v], rcond=None)[0]
                uvdir[v] += w / max(np.linalg.norm(w), 1e-12)
        uvdir = uvdir / np.maximum(np.linalg.norm(uvdir, axis=1, keepdims=True), 1e-12)
        used = sorted({v for p in faces for v in p.vertices})
        remap = {v: i for i, v in enumerate(used)}
        u = np.array(used)
        verts, polys, loop_uv, col = [], [], [], []
        for l in range(layers):
            t = l / (layers - 1)
            h = length[u] * t
            lift = 0.0002 + h * (1 - 0.5 * min(lean, 1.0))
            verts.append(co[u] + vn[u] * lift[:, None] + lean_dir[u] * (h * lean)[:, None])
            c = np.ones((len(u), 4))
            c[:, 0] = t
            c[:, 1] = dens[u]
            c[:, 2:] = uvdir[u] * 0.5 + 0.5
            col.append(c)
            off = l * len(u)
            for p in faces:
                polys.append([off + remap[v] for v in p.vertices])
                loop_uv += [uv[li] for li in p.loop_indices]
        verts = np.concatenate(verts)
        col = np.concatenate(col)
        sme = bpy.data.meshes.new("Crew_Shell_" + key)
        sme.from_pydata(verts.tolist(), [], polys)
        sme.shade_smooth()
        sme.update()
        sme.uv_layers.new(name="UVMap").data.foreach_set("uv", np.array(loop_uv, np.float32).ravel())
        ca = sme.color_attributes.new("Col", 'FLOAT_COLOR', 'POINT')
        ca.data.foreach_set("color", col.astype(np.float32).ravel())
        sme.materials.append(bpy.data.materials.get("Crew_Shell") or bpy.data.materials.new("Crew_Shell"))
        ob = bpy.data.objects.new("Crew_Shell_" + key, sme)
        bpy.context.scene.collection.objects.link(ob)
        ob.shape_key_add(name="Basis", from_mix=False)
        src_idx = np.tile(idx[u], layers)
        for k, d in keys.items():
            kb = ob.shape_key_add(name=k, from_mix=False)
            kb.data.foreach_set("co", (verts + d[src_idx]).astype(np.float32).ravel())
            kb.value = 0.0
        drop_flat_keys(ob, 1e-4)
        print("  shell %s: %d 层，%d 面一层，%d 顶点，发际线 %.1f~%.1f 毫米，最长 %.1f 毫米" % (
            key, layers, len(faces), len(verts), r_in * 1000, r_out * 1000, length.max() * 1000))
        obs.append(ob)
    return obs


def build_hair(base, tris, deltas, head_center):
    """各个发型的发片网格（Crew_Hair_xxx），绑到头皮上（只平移），HAIR_KEYS 里的形态跟着走。"""
    rng = np.random.default_rng(5)
    obs = []
    keys = {k: d for k, d in deltas.items() if (k.startswith("ID_") and k[3:] in HAIR_KEYS)
            or k.startswith("EX_Eyebrows")}
    for key, src, n, width, segs in HAIRSTYLES:
        strands = strands_from_npz(src)
        v, f, uv, cols = hair_cards(strands, n, width, segs, rng, base, tris, head_center)
        bind = Binding(v, base, tris)
        ob = strand_object("Crew_Hair_" + key, v, f, uv, bind, base, keys, "Crew_Hair", cols)
        drop_flat_keys(ob, 1e-4)
        print("  hair %s: %d 片，%d 顶点，形态键 %d 个" % (key, len(f) // segs, len(v), len(ob.data.shape_keys.key_blocks) - 1))
        obs.append(ob)
    return obs


# ============================================================================ 贴图
def _load_exr(name):
    img = bpy.data.images.load(os.path.join(VIT, "textures", "4K", name))
    w, h = img.size
    a = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(a)
    bpy.data.images.remove(img)
    return a.reshape(h, w, 4)


def _half(a):
    """边长减半（2×2 平均）。"""
    return (a[0::2, 0::2] + a[1::2, 0::2] + a[0::2, 1::2] + a[1::2, 1::2]) * 0.25


def _to_srgb(x):
    x = np.clip(x, 0, 1)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def _save(name, px):
    """存 PNG（px 是 h×w×4 的 0~1，Blender 的像素顺序：第 0 行在最下面）。"""
    h, w = px.shape[:2]
    img = bpy.data.images.new(name, w, h, alpha=True)
    img.pixels.foreach_set(np.ascontiguousarray(px, np.float32).ravel())
    img.filepath_raw = os.path.join(TEX, name + ".png")
    img.file_format = 'PNG'
    img.save()
    bpy.data.images.remove(img)
    print("  tex", name, w, h)


def raster(uv, tris, attrs, size):
    """把每个三角形（tris：loop 下标）按 UV 光栅化，attrs 里每个 loop 上的量（n_loop×k）插值到像素上。
    返回 (size×size×k, 覆盖遮罩)，再往外扩几个像素（贴图过滤、MIP 时岛边不发黑）。"""
    p = uv * size - 0.5
    k = attrs.shape[1]
    out = np.zeros((size, size, k), np.float32)
    cover = np.zeros((size, size), bool)
    for t in tris:
        q = p[t]
        x0, y0 = np.maximum(np.floor(q.min(0)).astype(int), 0)
        x1, y1 = np.minimum(np.ceil(q.max(0)).astype(int) + 1, size)
        if x0 >= x1 or y0 >= y1:
            continue
        ys, xs = np.mgrid[y0:y1, x0:x1].astype(np.float32)
        (ax, ay), (bx, by), (cx, cy) = q
        den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(den) < 1e-12:
            continue
        l0 = ((by - cy) * (xs - cx) + (cx - bx) * (ys - cy)) / den
        l1 = ((cy - ay) * (xs - cx) + (ax - cx) * (ys - cy)) / den
        l2 = 1 - l0 - l1
        m = (l0 > -0.01) & (l1 > -0.01) & (l2 > -0.01)
        a = attrs[t]
        out[y0:y1, x0:x1][m] = l0[m, None] * a[0] + l1[m, None] * a[1] + l2[m, None] * a[2]
        cover[y0:y1, x0:x1] |= m
    for _ in range(6):
        g = cover.copy()
        for ax_, sh in ((0, 1), (0, -1), (1, 1), (1, -1)):
            src = np.roll(cover, sh, ax_) & ~g
            out[src] = np.roll(out, sh, ax_)[src]
            g |= src
        cover = g
    return out, cover


def _blur(a, n=1):
    for _ in range(n):
        a = (a * 4 + np.roll(a, 1, 0) + np.roll(a, -1, 0) + np.roll(a, 1, 1) + np.roll(a, -1, 1)) / 8
    return a


def skin_textures(me, skin_faces):
    """皮肤：两张反照率（sRGB）、凹度 / 粗糙度 / 油光、法线（4K 置换图求梯度再缩到 2K）。返回每米多少个贴图像素。"""
    # 贴图上一个像素多大：皮肤面的三维面积和 UV 面积之比
    uv = _uv(me)
    co = _co(me.vertices, len(me.vertices))
    a3 = a2 = 0.0
    for f in skin_faces:
        p = me.polygons[f]
        vs = [co[v] for v in p.vertices]
        us = [uv[l] for l in p.loop_indices]
        for i in range(1, len(vs) - 1):
            a3 += np.linalg.norm(np.cross(vs[i] - vs[0], vs[i + 1] - vs[0])) / 2
            e1, e2 = us[i] - us[0], us[i + 1] - us[0]
            a2 += abs(e1[0] * e2[1] - e1[1] * e2[0]) / 2
    m_per_uv = math.sqrt(a3 / a2)
    print("  skin: %.3f 米 / UV 单位，一个像素 %.3f 毫米" % (m_per_uv, m_per_uv / SIZE * 1000))
    for src, dst in (("skin_light_col.1001.exr", "skin_light"), ("skin_dark_col.1001.exr", "skin_dark")):
        a = _load_exr(src)
        a[..., :3] = _to_srgb(a[..., :3])
        a[..., 3] = 1
        _save(dst, a)
    a = _load_exr("skin_cavity_rough_coat.1001.exr")
    a[..., 3] = 1
    _save("skin_crc", np.clip(a, 0, 1))
    # 法线：Vitruvian 的置换是 (h - 0.5) × 1 毫米（Displacement 节点 Scale 0.001），在 4K 上求梯度
    h = _load_exr("skin_disp.1001.exr")[..., 0].astype(np.float64) * 1e-3
    px = m_per_uv / h.shape[0]
    gx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) / (2 * px)
    gy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) / (2 * px)
    n = np.stack([-gx, -gy, np.ones_like(gx)], -1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    out = np.ones(n.shape[:2] + (4,), np.float32)
    out[..., :3] = n * 0.5 + 0.5
    _save("skin_normal", out)
    return SIZE / m_per_uv


def _uv(me):
    uv = np.empty(len(me.loops) * 2, np.float32)
    me.uv_layers[0].data.foreach_get("uv", uv)
    return uv.reshape(-1, 2)


def eye_textures():
    """眼白（带角膜透明度）、虹膜、口腔：原图 4K，缩到 2K（捏脸拉近看眼睛时虹膜纹理还清楚）。"""
    for src, dst, srgb in (("sclera_col.1005.exr", "sclera", True), ("iris_col.1007.exr", "iris", True),
                           ("mouth_col.1006.exr", "mouth", True), ("sclera_rough.1005.exr", "sclera_rough", False),
                           ("mouth_rough.1006.exr", "mouth_rough", False)):
        a = _half(_load_exr(src))
        if srgb:
            a[..., :3] = _to_srgb(a[..., :3])
        if not dst == "sclera":
            a[..., 3] = 1
        _save(dst, np.clip(a, 0, 1))


def pore_texture(size=512, seed=11):
    """平铺的毛孔法线（皮肤着色器按 UV × 90 平铺，一块约 5 毫米见方）：随机撒 160 个小坑（毛孔），
    再叠两层很细的皮纹（斜着交叉的细沟）和一点细噪声；四边能接上。"""
    rng = np.random.default_rng(seed)
    h = np.zeros((size, size))
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float64)
    for _ in range(160):
        cx, cy = rng.random(2) * size
        r = rng.uniform(2.5, 5.5)
        dx = (xx - cx + size / 2) % size - size / 2
        dy = (yy - cy + size / 2) % size - size / 2
        h -= rng.uniform(0.5, 1.0) * np.exp(-(dx * dx + dy * dy) / (r * r))
    for ang, k, amp in ((0.6, 9, 0.18), (-0.9, 7, 0.14)):
        u = (xx * math.cos(ang) + yy * math.sin(ang)) / size * 2 * math.pi * k
        # 方向上取整数个周期才平铺得上：按格点重新算
        kx, ky = round(k * math.cos(ang)), round(k * math.sin(ang))
        u = (xx * kx + yy * ky) / size * 2 * math.pi
        h -= amp * np.clip(np.sin(u + 0.7 * np.sin(u * 0.37)), 0, 1) ** 4
    noise = rng.random((size, size))
    h += 0.12 * (_blur(noise, 2) - 0.5)
    gx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) / 2
    gy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) / 2
    n = np.stack([-gx * 1.6, -gy * 1.6, np.ones_like(h)], -1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    out = np.ones((size, size, 4), np.float32)
    out[..., :3] = n * 0.5 + 0.5
    _save("skin_pores", out)


def _attr(me, name, vi=None):
    """颜色属性 name 每个 loop 上的 RGBA（点上的按 loop 的顶点号展开）。"""
    a = me.color_attributes[name]
    c = np.empty(len(a.data) * 4, np.float32)
    a.data.foreach_get("color", c)
    c = c.reshape(-1, 4)
    return c if a.domain == 'CORNER' else c[vi]


def _skin_loop_tris(me):
    tris = []
    for p in me.polygons:
        if p.material_index == SKIN:
            ls_ = list(p.loop_indices)
            tris += [(ls_[0], ls_[i], ls_[i + 1]) for i in range(1, len(ls_) - 1)]
    return np.array(tris, np.int64)


def _polyline_dist(pts, line):
    """pts（n×3）到折线 line（m×3）的最近距离，和最近点在折线上的弧长位置（0~1）。"""
    a, b = line[:-1], line[1:]
    ab = b - a
    seg = np.linalg.norm(ab, axis=1)
    cum = np.concatenate([[0], np.cumsum(seg)])
    best = np.full(len(pts), np.inf)
    pos = np.zeros(len(pts))
    for i in range(len(a)):
        t = np.clip(((pts - a[i]) @ ab[i]) / max(ab[i] @ ab[i], 1e-12), 0, 1)
        d = np.linalg.norm(pts - (a[i] + t[:, None] * ab[i]), axis=1)
        m = d < best
        best[m] = d[m]
        pos[m] = (cum[i] + t[m] * seg[i]) / cum[-1]
    return best, pos


def _ss(a, b, x):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def scalp_density(co):
    """长头发的地方：每个顶点离碎短发（Combover，3 万根，长头发的地方都有）最近的发根多远，3 毫米以内 1，10 毫米外 0。"""
    from mathutils.kdtree import KDTree
    roots = np.array([st[0] for st in strands_from_npz("Combover_zoro_d") if len(st) > 1])
    kd = KDTree(len(roots))
    for i, r in enumerate(roots):
        kd.insert(r, i)
    kd.balance()
    return np.array([_ss(0.010, 0.003, kd.find(c)[2]) for c in co])


def mask_textures(me, co, lash_lines, eyes):
    """皮肤遮罩（R 嘴唇、G 胡茬、A 透光厚度：Vitruvian 自带的顶点色；B 长头发的地方：scalp_density）和化妆遮罩
    （R 眼线、G 眼影、B 腮红、A 发际线下的暗部：按每个像素的三维位置离上睫毛根那条线、颧骨多远画）。"""
    uv = _uv(me)
    vi = np.empty(len(me.loops), np.int32)
    me.loops.foreach_get("vertex_index", vi)
    tris = _skin_loop_tris(me)
    beard = _attr(me, "BeardShadowMask", vi)
    attrs = np.concatenate([_attr(me, "ColLipMask")[:, :1], beard[:, 2:3], scalp_density(co)[vi, None],
                            _attr(me, "SkinDensity", vi)[:, :1], _attr(me, "HairAO", vi)[:, :1], co[vi]], 1)
    out, cover = raster(uv, tris, attrs, MASK_SIZE)
    m = np.ones((MASK_SIZE, MASK_SIZE, 4), np.float32)
    m[..., :4] = np.clip(out[..., :4], 0, 1)
    _save("skin_mask", m)
    pos = out[..., 5:8].reshape(-1, 3).astype(np.float64)
    mk = np.zeros((MASK_SIZE * MASK_SIZE, 4), np.float32)
    mk[:, 3] = np.clip(out[..., 4], 0, 1).ravel()
    for s, line in lash_lines.items():
        e = np.array(eyes[s])
        near = np.flatnonzero(np.linalg.norm(pos - e, axis=1) < 0.04)
        p = pos[near]
        d, t = _polyline_dist(p, line)
        # 睫毛根这条线在像素那个 x 上的高度：像素在线上方（上眼皮）才画
        order = np.argsort(line[:, 0])
        zl = np.interp(p[:, 0], line[order, 0], line[order, 2])
        above = _ss(-0.0004, 0.0008, p[:, 2] - zl)
        outer = t if line[-1, 0] * s > line[0, 0] * s else 1 - t       # 0 内眼角 → 1 外眼角
        # 眼线：贴着睫毛根，往外眼角渐粗，过了外眼角再挑出去一小截
        width = 0.0006 + 0.0011 * outer ** 2
        liner = _ss(width, width * 0.4, d) * above
        tail = line[order[-1] if s > 0 else order[0]]
        dirv = np.array([s * 0.8, 0.0, 0.6])
        q = p - tail
        along = q @ dirv / np.linalg.norm(dirv)
        perp = np.linalg.norm(q - np.outer(along, dirv / np.linalg.norm(dirv)), axis=1)
        wing = _ss(0.0055, 0.0, along) * (along > 0) * _ss(0.0009 * (1 - along / 0.0055) + 0.0001, 0.0, perp)
        mk[near, 0] = np.maximum(liner, wing)
        # 眼影：上眼皮，离睫毛根 1 厘米以内，外眼角浓一点
        shadow = _ss(0.011, 0.002, d) * above * (0.55 + 0.45 * outer)
        mk[near, 1] = np.clip(shadow, 0, 1)
        # 腮红：眼睛外下方 2.5 厘米的颧骨上
        c = e + np.array([s * 0.012, -0.012, -0.03])
        r = (pos - c) / np.array([0.024, 0.03, 0.018])
        mk[:, 2] = np.maximum(mk[:, 2], np.exp(-(r * r).sum(1)))
    mk[~cover.ravel()] = 0
    _save("skin_makeup", mk.reshape(MASK_SIZE, MASK_SIZE, 4))


def brow_textures(me):
    """14 种眉毛：hairstyles/mind_eyebrows_xx.npz 的每根眉毛投到皮肤上取 UV，按 UV 画到两道眉毛那一片
    （每种 BROW_W×BROW_H，竖着排成一张图，Godot 当 Texture2DArray 用）。R 覆盖度、G 模糊过的覆盖度（眉毛底下的软影）、
    B 发梢程度（0 根 → 1 梢，按覆盖度加权），返回那一片的 UV 范围 (u0, v0, u1, v1)。"""
    uv = _uv(me)
    co = _co(me.vertices, len(me.vertices))
    tris, tri_uv = [], []
    for p in me.polygons:
        if p.material_index != SKIN:
            continue
        vs, ls_ = list(p.vertices), list(p.loop_indices)
        for i in range(1, len(vs) - 1):
            tris.append((vs[0], vs[i], vs[i + 1]))
            tri_uv.append((uv[ls_[0]], uv[ls_[i]], uv[ls_[i + 1]]))
    tris = np.array(tris)
    tri_uv = np.array(tri_uv)
    bvh = BVHTree.FromPolygons([V(c) for c in co], tris.tolist())
    styles = []
    for name in BROWS:
        out = []
        for s in strands_from_npz(name):
            if len(s) > 1:
                s = np.vstack([s[0] - (s[1] - s[0]), s])
            uvs = []
            for p in s:
                loc, _, f, _ = bvh.find_nearest(V(p))
                b = _bary(np.array(loc), *(co[j] for j in tris[f]))
                uvs.append(b @ tri_uv[f])
            out.append(np.array(uvs))
        styles.append(out)
    allp = np.concatenate([np.concatenate(s) for s in styles])
    u0, v0 = allp.min(0) - 0.006
    u1, v1 = allp.max(0) + 0.006
    print("  brows: UV %.3f~%.3f × %.3f~%.3f" % (u0, u1, v0, v1))
    sc = np.array([BROW_W / (u1 - u0), BROW_H / (v1 - v0)])
    slices = []
    for strands in styles:
        dens = np.zeros((BROW_H + 1, BROW_W + 1))
        tipw = np.zeros_like(dens)
        for s in strands:
            px = (s - [u0, v0]) * sc
            seg = np.linalg.norm(np.diff(px, axis=0), axis=1)
            L = seg.sum()
            if L <= 0:
                continue
            k = max(int(L / 0.3), 2)
            t = np.linspace(0, 1, k)
            cum = np.concatenate([[0], np.cumsum(seg)]) / L
            q = np.stack([np.interp(t, cum, px[:, 0]), np.interp(t, cum, px[:, 1])], 1)
            a = 0.55 * (1 - 0.7 * t ** 2) * _ss(0.0, 0.08, t)
            x0 = np.floor(q[:, 0]).astype(int)
            y0 = np.floor(q[:, 1]).astype(int)
            fx, fy = q[:, 0] - x0, q[:, 1] - y0
            ok = (x0 >= 0) & (y0 >= 0) & (x0 < BROW_W) & (y0 < BROW_H)
            for dx, dy, w in ((0, 0, (1 - fx) * (1 - fy)), (1, 0, fx * (1 - fy)), (0, 1, (1 - fx) * fy), (1, 1, fx * fy)):
                np.add.at(dens, (y0[ok] + dy, x0[ok] + dx), (a * w)[ok])
                np.add.at(tipw, (y0[ok] + dy, x0[ok] + dx), (a * w * t)[ok])
        dens, tipw = dens[:BROW_H, :BROW_W], tipw[:BROW_H, :BROW_W]
        alpha = 1 - np.exp(-dens * 1.15)
        img = np.ones((BROW_H, BROW_W, 4), np.float32)
        img[..., 0] = alpha
        img[..., 1] = np.clip(_blur(alpha, 12) * 1.6, 0, 1)
        img[..., 2] = np.clip(tipw / np.maximum(dens, 1e-6), 0, 1)
        slices.append(img)
    _save("brows", np.concatenate(slices[::-1], 0))
    return [float(u0), float(v0), float(u1), float(v1)]


def strand_object(name, verts, faces, uvs, bind, base, deltas, mat, alpha=None):
    """一块跟着脸走的网格（睫毛、泪线、遮蔽）：基础形状 verts，每个形态 bind.place 一遍得出跟着走的位置。"""
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts.tolist(), [], [tuple(f) for f in faces])
    me.shade_smooth()      # from_pydata 建的网格默认是平直着色，高光一块一块的
    me.update()
    uvl = me.uv_layers.new(name="UVMap")
    li = np.empty(len(me.loops), np.int32)
    me.loops.foreach_get("vertex_index", li)
    uvl.data.foreach_set("uv", uvs[li].astype(np.float32).ravel())
    if alpha is not None:
        ca = me.color_attributes.new("Col", 'FLOAT_COLOR', 'POINT')
        c = np.ones((len(verts), 4), np.float32)
        if alpha.ndim == 2:
            c[:] = alpha
        else:
            c[:, 3] = alpha
        ca.data.foreach_set("color", c.ravel())
    me.materials.append(bpy.data.materials.get(mat) or bpy.data.materials.new(mat))
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    ob.shape_key_add(name="Basis", from_mix=False)
    p0 = bind.place(base)
    for k, d in deltas.items():
        kb = ob.shape_key_add(name=k, from_mix=False)
        kb.data.foreach_set("co", (verts + bind.place(base + d) - p0).astype(np.float32).ravel())
        kb.value = 0.0
    return ob


def asset_object(name, base, tris, deltas, mat):
    """Vitruvian 自带的眼部小网格（Eyeshadow 眼部遮蔽、Tearline 泪线）：细分一级，按透明度遮罩（OpacityMask）做顶点 alpha。"""
    with bpy.data.libraries.load(os.path.join(VIT, "assets", name + ".blend")) as (src, dst):
        dst.objects = [n for n in src.objects if n == name]
    src_ob = dst.objects[0]
    bpy.context.scene.collection.objects.link(src_ob)
    for m in list(src_ob.modifiers):
        if m.type != 'SUBSURF':
            src_ob.modifiers.remove(m)
    if not src_ob.modifiers:
        src_ob.modifiers.new("sub", 'SUBSURF').levels = 1
    ev = src_ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
    me = bpy.data.meshes.new_from_object(ev)
    n = len(me.vertices)
    verts = _co(me.vertices, n).astype(np.float64)
    ca = me.color_attributes.get("OpacityMask") or me.attributes.get("OpacityMask")
    a = np.empty(n * 4, np.float32)
    ca.data.foreach_get("color", a)
    alpha = a.reshape(-1, 4)[:, 0]
    faces = [tuple(p.vertices) for p in me.polygons]
    uv = np.zeros((n, 2))
    li = np.empty(len(me.loops), np.int32)
    me.loops.foreach_get("vertex_index", li)
    if me.uv_layers:
        u = np.empty(len(me.loops) * 2, np.float32)
        me.uv_layers[0].data.foreach_get("uv", u)
        uv[li] = u.reshape(-1, 2) - np.floor(u.reshape(-1, 2))
    bpy.data.objects.remove(src_ob, do_unlink=True)
    bind = Binding(verts, base, tris)
    print("  %s: %d 顶点，透明度 %.2f~%.2f" % (name, n, alpha.min(), alpha.max()))
    return strand_object("_" + name, verts, faces, uv, bind, base, deltas, mat, alpha)


def drop_flat_keys(ob, eps=2e-5):
    """删掉这块网格上几乎不动的形态键（最大位移不到 eps 米）。"""
    sk = ob.data.shape_keys
    if sk is None:
        return
    n = len(ob.data.vertices)
    basis = _co(sk.key_blocks[0].data, n)
    for kb in list(sk.key_blocks)[1:]:
        if np.abs(_co(kb.data, n) - basis).max() < eps:
            ob.shape_key_remove(kb)


def split_material(ob, slot_name, new_name):
    """把材质槽 slot_name 的面拆成单独一块网格（形态键跟着走）。"""
    me2 = ob.data.copy()
    ob2 = bpy.data.objects.new(new_name, me2)
    bpy.context.scene.collection.objects.link(ob2)
    me2.name = new_name
    for o, keep_it in ((ob, False), (ob2, True)):
        bm = bmesh.new()
        bm.from_mesh(o.data)
        slot = [i for i, m in enumerate(o.data.materials) if m and m.name == slot_name][0]
        bmesh.ops.delete(bm, geom=[f for f in bm.faces if (f.material_index == slot) != keep_it], context='FACES')
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context='VERTS')
        bm.to_mesh(o.data)
        bm.free()
        o.data.update()
    return ob2


# ============================================================================ 入口
N_FULL = 0


def main():
    global N_FULL
    bpy.ops.wm.open_mainfile(filepath=os.path.join(VIT, "char.blend"), load_ui=False, use_scripts=False)
    os.makedirs(TEX, exist_ok=True)
    ob = bpy.data.objects["cm_vitruvian"]
    me = ob.data
    base = np.load(os.path.join(VIT, "morphs", "L1", "Default.npy")).astype(np.float64)
    N_FULL = len(base)
    me.vertices.foreach_set("co", base.astype(np.float32).ravel())
    me.update()

    # 睫毛：粒子毛发（Default 形状下）先取出来，再删粒子系统
    lashes = strands_from_psys(ob, "Eyelashes")
    for m in list(ob.modifiers):
        ob.modifiers.remove(m)
    print("lashes", len(lashes), "strands")

    # 只留头：皮肤里 UDIM 1001 那一块（头、脖子），加眼睛、口腔；记下原来的顶点号
    uv = _uv(me)
    mi = np.empty(len(me.polygons), np.int32)
    me.polygons.foreach_get("material_index", mi)
    ls = np.empty(len(me.polygons), np.int32)
    me.polygons.foreach_get("loop_start", ls)
    tile = (1001 + np.floor(uv[ls, 0]) + 10 * np.floor(uv[ls, 1])).astype(int)
    keep = ((mi == SKIN) & (tile == 1001)) | np.isin(mi, [AQUEOUS, PUPIL, SCLERA, IRIS, MOUTH])
    orig = me.attributes.new("orig", 'INT', 'POINT')
    orig.data.foreach_set("value", np.arange(N_FULL, dtype=np.int32))
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.faces.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if not keep[f.index]], context='FACES')
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context='VERTS')
    bm.to_mesh(me)
    bm.free()
    me.update()
    idx = np.empty(len(me.vertices), np.int32)
    me.attributes["orig"].data.foreach_get("value", idx)
    # UV 只留 UDIM 那套，各块挪回 0~1（每个材质一张贴图）
    for u in [u for u in me.uv_layers if u.name != "VitruvianUV_UDIM"]:
        me.uv_layers.remove(u)
    uv = _uv(me)
    uv -= np.floor(uv)
    me.uv_layers[0].data.foreach_set("uv", uv.ravel())
    me.uv_layers["VitruvianUV_UDIM"].name = "UVMap"
    for a in [a for a in me.attributes if a.name in ("orig", "rest_position", "Tension_AreaMask", "TeethMask", "MicroNormals")]:
        me.attributes.remove(a)
    print("head: %d 顶点 %d 面" % (len(me.vertices), len(me.polygons)))

    # 形态：Vitruvian 的捏脸、表情形态，加上按五官位置造的大形态（锚点要先找到眼睛）
    n = len(me.vertices)
    co = base[idx]
    mi = np.empty(len(me.polygons), np.int32)
    me.polygons.foreach_get("material_index", mi)
    iv = sorted({v for f in np.flatnonzero(mi == IRIS) for v in me.polygons[f].vertices})
    ic = co[iv]
    eyes = {s: ic[ic[:, 0] * s > 0].mean(0) for s in (1, -1)}
    deltas = {}
    for name in ID:
        deltas["ID_" + name] = morph(name)
    for name, d in macro_morphs(base, landmarks(me, idx, base, eyes)).items():
        deltas["ID_Macro_" + name] = d
    for name in EX:
        deltas["EX_" + name] = morph(name)
    ob.shape_key_add(name="Basis", from_mix=False)
    for k, d in deltas.items():
        kb = ob.shape_key_add(name=k, from_mix=False)
        kb.data.foreach_set("co", (co + d[idx]).astype(np.float32).ravel())
        kb.value = 0.0
        if k.startswith("ID_"):
            kb.slider_min = -1.0

    # 皮肤三角形（绑定睫毛、泪线、遮蔽、头发用）：全身原网格上头那一块的三角形，用原顶点号
    mi = np.empty(len(me.polygons), np.int32)
    me.polygons.foreach_get("material_index", mi)
    skin_faces = np.flatnonzero(mi == SKIN)
    tris = []
    for f in skin_faces:
        vs = [int(idx[v]) for v in me.polygons[f].vertices]
        tris += [(vs[0], vs[i], vs[i + 1]) for i in range(1, len(vs) - 1)]
    tris = np.array(tris, np.int64)
    # 上睫毛根连成的线（眼线、眼影顺着它画）
    lash_lines = {}
    for s in (1, -1):
        r = np.array([st[0] for st in lashes if st[0][0] * s > 0 and st[0][2] > eyes[s][2]])
        lash_lines[s] = r[np.argsort(r[:, 0])]
        print("  上睫毛 %s: %d 根" % ("左右"[s < 0], len(r)))

    print("textures")
    tex_per_m = skin_textures(me, skin_faces)
    eye_textures()
    pore_texture()
    hair_texture()
    mask_textures(me, co, lash_lines, eyes)
    brow_rect = brow_textures(me)

    print("shells")
    shells = build_shells(me, idx, base, deltas)

    # 材质槽改名
    for i, s in enumerate(me.materials):
        nm = SLOTS.get(i)
        me.materials[i] = bpy.data.materials.new(nm) if nm else None
    bpy.data.objects.remove(bpy.data.objects["Plane"], do_unlink=True)

    # 睫毛、眼部遮蔽、泪线：绑到皮肤上，每个形态算一遍，合进头
    print("strands")
    lv, lf, lu, lr = lash_mesh(lashes)
    lob = strand_object("_lashes", lv, lf, lu, Binding(lv, base, tris, rigid=True, anchor=lr), base, deltas,
                        "Crew_Lashes", np.ones(len(lv)))
    parts = [lob, asset_object("Eyeshadow", base, tris, deltas, "Crew_EyeOcclusion"),
             asset_object("Tearline", base, tris, deltas, "Crew_Tearline")]
    for a in [a for a in me.color_attributes if a.name != "Col"]:
        me.color_attributes.remove(a)
    ca = me.color_attributes.new("Col", 'FLOAT_COLOR', 'POINT')
    ca.data.foreach_set("color", np.ones(n * 4, np.float32))
    bpy.ops.object.select_all(action='DESELECT')
    for o in [ob] + parts:
        o.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.join()
    me = ob.data
    me.color_attributes.active_color = me.color_attributes["Col"]
    me.color_attributes.render_color_index = me.color_attributes.find("Col")

    head = ob
    head.name = head.data.name = "Crew_Head"
    mouth = split_material(head, "Crew_Mouth", "Crew_Mouth")
    for o in (head, mouth):
        drop_flat_keys(o)
        print("%s: %d 顶点，形态键 %d 个，材质 %s" % (o.name, len(o.data.vertices),
              len(o.data.shape_keys.key_blocks) - 1, [m.name if m else None for m in o.data.materials]))
    head["eye_l"], head["eye_r"] = [[float(x) for x in eyes[s]] for s in (1, -1)]
    head["tex_per_m"] = float(tex_per_m)
    head["brow_rect"] = brow_rect
    # 头发：头的中心取头皮那一片（眼睛以上的皮肤）的平均位置
    skin_v = np.unique(tris)
    scalp = base[skin_v][base[skin_v][:, 2] > eyes[1][2] + 0.02]
    print("hair, 头的中心", scalp.mean(0).round(3))
    hair = build_hair(base, tris, deltas, scalp.mean(0))
    bpy.data.libraries.write(OUT, {head, mouth, *hair, *shells}, path_remap='ABSOLUTE')
    print("exported", OUT)


main()
