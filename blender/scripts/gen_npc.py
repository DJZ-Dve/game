"""剧情角色沈渡（东溟海洋工程的代表）：Microsoft Rocketbox 的 Business_Male_02（MIT 许可）带表情的 _facial 版。

先跑 tools/fetch_rocketbox.sh，再：
    Blender -b --factory-startup --python blender/scripts/gen_npc.py [-- --preview DIR]
导出 assets/models/npc_shen.glb（骨骼 + 身体、头、头发三块网格 + 原地动画 + 口型、眨眼、微笑的形态键）
和 assets/models/npc_shen.json（坐姿下手、臀、眼睛的位置，office 场景按它摆桌椅）。

外观（见 docs/story.md 的人物设定）：
- 西装压成旧款的炭灰色，白衬衫洗得发黄、领口发暗，领带换成素色的深酒红
- 脸和手褪一点血色、发冷，眼窝发青（不夸张，第一眼只觉得“这人脸色不太好”）
- 皮鞋是湿的（ORM 贴图里鞋面的粗糙度很低），配一副民国式的圆框眼镜（Poly Haven round_spectacles，CC0）
- 眨眼的形态键留着，但 Godot 里故意不用：他不眨眼

缩放到眼睛离地 1.62 米（身高约 1.71 米），脸朝 Blender +Y（Godot 的 -Z）。
"""
import json
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Matrix, Vector as V

sys.path.insert(0, os.path.dirname(__file__))
from rocketbox import ROOT, SRC, import_fbx, bone_world, retarget, push_nla, rest_pose, trim_shapes  # noqa: E402

AVATAR = "Business_Male_02_facial.fbx"
TEX = "m008"
OUT = os.path.join(ROOT, "assets", "models", "npc_shen.glb")
META = os.path.join(ROOT, "assets", "models", "npc_shen.json")
GLASSES = os.path.join(ROOT, "assets", "third_party", "polyhaven", "models", "round_spectacles",
                       "round_spectacles_2k.gltf")
EYE = 1.62
ANIMS = {
    "sit": "m_sit_table_idle_neutral_01.max.fbx",
    "sit_breathe": "m_sit_table_breathe_01.max.fbx",
    "sit_think": "m_sit_table_gestic_thoughtful.max.fbx",
    "sit_shrug": "m_sit_table_gestic_shrug_01.max.fbx",
    "sit_touch_face": "m_sit_table_idle_touch_face.max.fbx",
    "sit_wait": "m_sit_table_idle_waiting_01.max.fbx",
    "stand": "m_idle_neutral_02.max.fbx",
    "stand_talk": "m_gestic_talk_neutral_01.max.fbx",
}
# 只留用得上的形态键（全留 190 个，glb 要大好几倍）：口型（visemes）、眨眼、张嘴、抿嘴、微笑、皱眉、眯眼
KEEP_SHAPES = [
    "AA_VI_00_Sil", "AA_VI_01_PP", "AA_VI_02_FF", "AA_VI_03_TH", "AA_VI_04_DD", "AA_VI_05_KK", "AA_VI_06_CH",
    "AA_VI_07_SS", "AA_VI_08_nn", "AA_VI_09_RR", "AA_VI_10_aa", "AA_VI_11_E", "AA_VI_12_I", "AA_VI_13_O",
    "AA_VI_14_U",
    "AK_01_BrowDownLeft", "AK_02_BrowDownRight", "AK_03_BrowInnerUp", "AK_09_EyeBlinkLeft", "AK_10_EyeBlinkRight",
    "AK_19_EyeSquintLeft", "AK_20_EyeSquintRight", "AK_21_EyeWideLeft", "AK_22_EyeWideRight", "AK_25_JawOpen",
    "AK_27_MouthClose", "AK_30_MouthFrownLeft", "AK_31_MouthFrownRight", "AK_36_MouthPressLeft",
    "AK_37_MouthPressRight", "AK_44_MouthSmileLeft", "AK_45_MouthSmileRight",
]


# ============================================================================ 贴图
def load_px(name):
    img = bpy.data.images.load(os.path.join(SRC, name))
    w, h = img.size
    px = np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4)
    return img, px


def uv_grid(h, w):
    """每个像素的 (u, v)，v 朝上（Blender 的像素从左下角开始存）。"""
    v, u = np.mgrid[0:h, 0:w].astype(np.float32)
    return (u + 0.5) / w, (v + 0.5) / h


def blob(u, v, cu, cv, ru, rv):
    return np.exp(-(((u - cu) / ru) ** 2 + ((v - cv) / rv) ** 2))


def save_png(px, name, colorspace='sRGB'):
    h, w = px.shape[:2]
    img = bpy.data.images.new(name, w, h, alpha=True)
    img.pixels[:] = np.clip(px, 0, 1).ravel()
    img.filepath_raw = os.path.join(SRC, name + ".png")
    img.file_format = 'PNG'
    img.save()
    img.colorspace_settings.name = colorspace
    return img


def low_noise(h, w, cell, seed):
    """低频起伏（0~1），几十个像素一团。"""
    rng = np.random.default_rng(seed)
    low = rng.random((h // cell + 1, w // cell + 1)).astype(np.float32)
    low = np.kron(low, np.ones((cell, cell), np.float32))[:h, :w]
    for _ in range(3):
        low = (low + np.roll(low, cell // 3, 0) + np.roll(low, -cell // 2, 1) + np.roll(low, cell // 2, (0, 1))) / 4
    return low


def pallor(rgb, amount):
    """褪血色：往亮度靠一点、偏冷一点。"""
    lum = (0.3 * rgb[..., 0] + 0.59 * rgb[..., 1] + 0.11 * rgb[..., 2])[..., None]
    out = rgb * (1 - amount) + lum * amount
    return out * np.array([0.97, 0.99, 1.0], np.float32)


def body_textures():
    """西装、衬衫、领带、手、鞋。返回 (颜色图, ORM 图)。ORM：R 不用、G 粗糙度、B 金属度。"""
    _, px = load_px(f"{TEX}_body_color.tga")
    h, w = px.shape[:2]
    u, v = uv_grid(h, w)
    rgb = px[..., :3].copy()
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    lum = 0.3 * r + 0.59 * g + 0.11 * b
    sat = rgb.max(-1) - rgb.min(-1)
    hands = ((u < 0.25) | (u > 0.75)) & (v < 0.18) & (r > b + 0.05)
    shoes = (v > 0.03) & (v < 0.31) & (((u > 0.21) & (u < 0.42)) | ((u > 0.63) & (u < 0.8))) & (lum < 0.12) & ~hands
    tie = (u > 0.355) & (u < 0.545) & (v < 0.135) & ~shoes
    shirt = (sat < 0.12) & (lum > 0.3) & ~hands & ~tie
    suit = ~(hands | shoes | tie | shirt)
    # 西装：藏青压成发旧的炭灰（微微偏暖），按原来的明暗保留褶子
    k = np.clip(lum / max(float(lum[suit].mean()), 1e-3), 0.25, 2.6)[..., None]
    wear = low_noise(h, w, 96, 3)[..., None]
    rgb[suit] = (np.array([0.072, 0.068, 0.062], np.float32) * k * (0.9 + 0.22 * wear))[suit]
    # 衬衫：洗得发黄，领口、袖口发暗
    ks = np.clip(lum / 0.82, 0.3, 1.2)[..., None]
    shirt_col = np.array([0.74, 0.71, 0.6], np.float32) * ks * (0.92 + 0.12 * wear)
    rgb[shirt] = shirt_col[shirt]
    # 领带：素色深酒红
    kt = np.clip(lum / max(float(lum[tie].mean()), 1e-3), 0.4, 1.8)[..., None]
    rgb[tie] = (np.array([0.1, 0.018, 0.022], np.float32) * kt)[tie]
    # 手：褪血色
    rgb[hands] = pallor(rgb, 0.2)[hands]
    # 鞋：更黑一点（湿的）
    rgb[shoes] *= 0.75
    px[..., :3] = np.clip(rgb, 0, 1)
    orm = np.zeros_like(px)
    orm[..., 3] = 1.0
    rough = np.full((h, w), 0.8, np.float32)
    rough[shirt] = 0.62
    rough[tie] = 0.5
    rough[hands] = 0.5
    rough[shoes] = 0.16
    rough[suit] = 0.78 + 0.08 * (wear[..., 0][suit] - 0.5)
    orm[..., 0] = 1.0
    orm[..., 1] = rough
    return save_png(px, "npc_shen_body_color"), save_png(orm, "npc_shen_body_orm", 'Non-Color')


def head_textures():
    """脸：褪血色、眼窝发青；眼球、嘴里湿润。"""
    _, px = load_px(f"{TEX}_head_color.tga")
    h, w = px.shape[:2]
    u, v = uv_grid(h, w)
    rgb = px[..., :3].copy()
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    lum = 0.3 * r + 0.59 * g + 0.11 * b
    atlas = (v < 0.42) & (u < 0.38)          # 左下角：眼球、牙齿、口腔
    hair = (lum < 0.12) & ~atlas
    skin = ~atlas & ~hair & (v > 0.3)
    rgb[skin] = pallor(rgb, 0.18)[skin]
    # 眼窝：两只眼睛周围（下眼睑多一点）压暗、偏青紫
    sock = np.zeros((h, w), np.float32)
    for cu in (0.42, 0.571):
        sock = np.maximum(sock, blob(u, v, cu, 0.712, 0.06, 0.035) * 0.8 + blob(u, v, cu, 0.69, 0.05, 0.025) * 0.5)
    sock = np.clip(sock, 0, 1) * skin
    tint = np.array([0.8, 0.78, 0.85], np.float32)
    rgb = rgb * (1 - sock[..., None] * 0.45) + rgb * tint * (sock[..., None] * 0.45)
    px[..., :3] = np.clip(rgb, 0, 1)
    orm = np.zeros_like(px)
    orm[..., 3] = 1.0
    orm[..., 0] = 1.0
    rough = np.full((h, w), 0.5, np.float32)
    # 额头、鼻子出点油
    rough -= 0.08 * (blob(u, v, 0.5, 0.82, 0.08, 0.06) + blob(u, v, 0.5, 0.66, 0.025, 0.05))
    rough[hair] = 0.65
    eye = blob(u, v, 0.264, 0.082, 0.07, 0.07) > 0.3
    rough[eye & atlas] = 0.04
    rough[atlas & ~eye] = 0.3
    orm[..., 1] = np.clip(rough, 0.03, 1)
    return save_png(px, "npc_shen_head_color"), save_png(orm, "npc_shen_head_orm", 'Non-Color')


def pbr(name, color, orm=None, normal=None, alpha=False):
    mat = bpy.data.materials.new(name)
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    t = nt.nodes.new('ShaderNodeTexImage')
    t.image = color
    nt.links.new(t.outputs["Color"], bsdf.inputs["Base Color"])
    if alpha:
        nt.links.new(t.outputs["Alpha"], bsdf.inputs["Alpha"])
    if orm is not None:
        to = nt.nodes.new('ShaderNodeTexImage')
        to.image = orm
        sep = nt.nodes.new('ShaderNodeSeparateColor')
        nt.links.new(to.outputs["Color"], sep.inputs["Color"])
        nt.links.new(sep.outputs["Green"], bsdf.inputs["Roughness"])
        nt.links.new(sep.outputs["Blue"], bsdf.inputs["Metallic"])
    else:
        bsdf.inputs["Roughness"].default_value = 0.7
        bsdf.inputs["Metallic"].default_value = 0.0
    if normal is not None:
        tn = nt.nodes.new('ShaderNodeTexImage')
        tn.image = normal
        normal.colorspace_settings.name = 'Non-Color'
        nm = nt.nodes.new('ShaderNodeNormalMap')
        nt.links.new(tn.outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


# ============================================================================ 网格
def glasses(arm, head_bone="Bip01 Head"):
    """圆框眼镜：镜片中心对准两只眼睛，镜片在眼球前 1.4 厘米；挂在头骨上。"""
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=GLASSES)
    new = [o for o in bpy.data.objects if o not in before]
    ob = next(o for o in new if o.type == 'MESH')
    for o in new:
        if o is not ob:
            bpy.data.objects.remove(o, do_unlink=True)
    ob.name = ob.data.name = "Shen_Glasses"
    me = ob.data
    # 镜片（玻璃材质）的两个中心
    gi = [i for i, m in enumerate(me.materials) if m and "glass" in m.name]
    pts = np.array([me.vertices[v].co[:] for p in me.polygons if p.material_index in gi for v in p.vertices])
    lc = pts[pts[:, 0] > 0].mean(0)
    rc = pts[pts[:, 0] < 0].mean(0)
    half = (lc[0] - rc[0]) / 2
    # 镜片换成项目里的玻璃材质（Poly Haven 的是透射材质，Godot 里不透明）
    for i in gi:
        me.materials[i] = bpy.data.materials.get("M_Glass") or bpy.data.materials.new("M_Glass")
    le, re_ = bone_world(arm, "Bip01 LEye"), bone_world(arm, "Bip01 REye")
    k = (le - re_).length / 2 / half * 0.9       # 民国式小圆片：镜片间距比瞳距略窄，镜片 4 厘米上下
    mid = (le + re_) / 2
    fwd = V((0, -1, 0))                          # 角色这时还面朝 -Y
    center = V(((lc + rc) / 2).tolist())
    ob.matrix_world = Matrix.Translation(mid + fwd * 0.026 + V((0, 0, -0.004))) @ Matrix.Diagonal((k, k, k, 1)) \
        @ Matrix.Translation(-center)
    # 挂到头骨上（保持现在的世界位置）
    mw = ob.matrix_world.copy()
    ob.parent = arm
    ob.parent_type = 'BONE'
    ob.parent_bone = head_bone
    ob.matrix_world = mw
    return ob


# ============================================================================ 预览
def preview(arm, out_dir, acts):
    sc = bpy.context.scene
    try:
        sc.render.engine = 'BLENDER_EEVEE'
    except TypeError:
        sc.render.engine = 'BLENDER_EEVEE_NEXT'
    sc.render.resolution_x, sc.render.resolution_y = 900, 900
    world = bpy.data.worlds.new("W")
    world.color = (0.03, 0.03, 0.035)
    sc.world = world
    for name, loc, energy, col in (("Key", (0.9, 1.6, 1.8), 220, (1.0, 0.92, 0.8)),
                                   ("Fill", (-1.3, 1.0, 1.3), 60, (0.75, 0.85, 1.0)),
                                   ("Rim", (0.2, -1.4, 1.9), 120, (1.0, 1.0, 1.0))):
        ld = bpy.data.lights.new(name, 'AREA')
        ld.energy, ld.color, ld.size = energy, col, 0.6
        lo = bpy.data.objects.new(name, ld)
        sc.collection.objects.link(lo)
        lo.location = loc
        lo.rotation_euler = (V((0, 0, 1.1)) - V(loc)).to_track_quat('-Z', 'Y').to_euler()
    cam_d = bpy.data.cameras.new("Cam")
    cam = bpy.data.objects.new("Cam", cam_d)
    sc.collection.objects.link(cam)
    sc.camera = cam
    arm.animation_data.action = acts["sit"]
    sc.frame_set(60)
    head = bone_world(arm, "Bip01 Head")
    for nm, pos, look, lens in (("face", head + V((0.12, 0.62, 0.06)), head + V((0, 0, 0.06)), 70),
                                ("body", V((0.9, 2.1, 1.25)), V((0, 0, 0.75)), 40),
                                ("side", V((2.0, 0.2, 1.0)), V((0, 0, 0.7)), 45)):
        cam_d.lens = lens
        cam.location = pos
        cam.rotation_euler = (V(look) - V(pos)).to_track_quat('-Z', 'Y').to_euler()
        sc.render.filepath = os.path.join(out_dir, f"npc_{nm}.png")
        bpy.ops.render.render(write_still=True)
    arm.animation_data.action = None


# ============================================================================ 入口
def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    preview_dir = argv[argv.index("--preview") + 1] if "--preview" in argv else None
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.fps = 30
    objs = import_fbx(AVATAR)
    arm = next(o for o in objs if o.type == 'ARMATURE')
    mesh = next(o for o in objs if o.type == 'MESH')
    for o in objs:
        if o.type == 'EMPTY':
            bpy.data.objects.remove(o, do_unlink=True)

    # 按材质拆成身体、头、头发（发片带透明度）
    bpy.context.view_layer.objects.active = mesh
    mesh.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.separate(type='MATERIAL')
    bpy.ops.object.mode_set(mode='OBJECT')
    parts = {}
    for o in [o for o in bpy.data.objects if o.type == 'MESH']:
        m = o.data.materials[0].name
        key = "Head" if "head" in m else "Hair" if "opacity" in m else "Body"
        o.name = o.data.name = f"Shen_{key}"
        parts[key] = o
    parts["Body"].shape_key_clear()
    for key in ("Head", "Hair"):
        trim_shapes(parts[key], set(KEEP_SHAPES))
        sk = parts[key].data.shape_keys
        print(f"shen: {key} 形态键 {len(sk.key_blocks) - 1 if sk else 0} 个")

    # 材质
    bc, bo = body_textures()
    hc, ho = head_textures()
    bn = bpy.data.images.load(os.path.join(SRC, f"{TEX}_body_normal.tga"))
    hn = bpy.data.images.load(os.path.join(SRC, f"{TEX}_head_normal.tga"))
    hair = bpy.data.images.load(os.path.join(SRC, f"{TEX}_opacity_color.tga"))
    for key, mat in (("Body", pbr("Shen_Body", bc, bo, bn)), ("Head", pbr("Shen_Head", hc, ho, hn)),
                     ("Hair", pbr("Shen_Hair", hair, alpha=True))):
        parts[key].data.materials.clear()
        parts[key].data.materials.append(mat)

    # 动画
    gl = glasses(arm)
    acts = {}
    for key, fname in ANIMS.items():
        act, f0, f1 = retarget(arm, key, fname)
        acts[key] = act
    arm.animation_data.action = None

    # 朝向和大小：静止姿势下脸朝 +Y，眼睛离地 EYE
    rest_pose(arm)
    right = bone_world(arm, "Bip01 R Thigh") - bone_world(arm, "Bip01 L Thigh")
    fwd = V((0, 0, 1)).cross(right)
    yaw = math.atan2(fwd.y, fwd.x) - math.pi / 2
    eye = bone_world(arm, "Bip01 LEye").z
    k = EYE / eye
    arm.matrix_world = Matrix.Rotation(-yaw, 4, 'Z') @ Matrix.Diagonal((k, k, k, 1.0)) @ arm.matrix_world
    bpy.context.view_layer.update()
    print("shen: 朝向修正 %.1f°，缩放 %.3f" % (math.degrees(-yaw), k))

    # 坐姿（sit 第一帧）下的关键位置，office 场景按它摆椅子、桌子
    arm.animation_data.action = acts["sit"]
    sc.frame_set(int(acts["sit"].frame_range[0]))
    pel = bone_world(arm, "Bip01 Pelvis")
    meta = {"scale": k}
    for nm, b in (("pelvis", "Bip01 Pelvis"), ("hand_l", "Bip01 L Hand"), ("hand_r", "Bip01 R Hand"),
                  ("eye", "Bip01 LEye"), ("foot_l", "Bip01 L Foot"), ("thigh_l", "Bip01 L Thigh")):
        p = bone_world(arm, b) - V((pel.x, pel.y, 0))
        meta[nm] = [round(p.x, 4), round(p.y, 4), round(p.z, 4)]   # Blender 坐标：+Y 朝前，+Z 朝上
    arm.animation_data.action = None
    print("shen: 坐姿", json.dumps(meta, ensure_ascii=False))

    if preview_dir:
        os.makedirs(preview_dir, exist_ok=True)
        preview(arm, preview_dir, acts)

    push_nla(arm, acts)
    bpy.ops.object.select_all(action='DESELECT')
    for o in (arm, *parts.values(), gl):
        o.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.export_scene.gltf(
        filepath=OUT, export_format='GLB', use_selection=True, export_yup=True, export_apply=False,
        export_animations=True, export_animation_mode='NLA_TRACKS', export_force_sampling=True,
        export_frame_range=False, export_anim_single_armature=True, export_def_bones=False,
        export_morph=True, export_morph_normal=False, export_image_format='AUTO', export_materials='EXPORT',
        export_cameras=False, export_lights=False)
    with open(META, "w") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    print("exported", OUT, f"{os.path.getsize(OUT) / 1e6:.1f} MB")


main()
