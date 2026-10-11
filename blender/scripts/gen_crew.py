"""第一人称的身体：Microsoft Rocketbox 的 Construction_Male_05（MIT 许可），改成潜艇兵。

先跑 tools/fetch_rocketbox.sh 把角色和动画下到 blender/cache/rocketbox/，再：
    Blender -b --factory-startup --python blender/scripts/gen_crew.py
导出 assets/models/crew_body.glb（骨骼 + 身体、头、头发三块网格 + walk / run / idle / sit 四段原地动画）
和 assets/models/crew_body_gait.json（走、跑动画里左右脚落地在循环里的位置，Godot 拿它把动画和步伐对齐）。

- 动画：按世界空间朝向重定向到角色骨骼上（见 rocketbox.py 的 retarget）
- 贴图：蓝色工装压成深海军蓝的作业服，磨旧、蹭脏一点；浅黄色劳保鞋改成黑皮靴；手不动
- 头换成 MPFB2 生成的（blender/scripts/gen_head_mpfb.py：东亚、三十出头到三十五、偏瘦、晒黑、胡茬、短发——
  主角周海生的脸，见 docs/story.md），带眉毛、睫毛、眼球和眨眼、微笑这些形态键；按两只眼睛对位、按瞳距缩放，
  改绑到工装身体的骨架上，脖子往下留到领口里面。头和头发各一块网格，Godot 里只有镜子看得见（第一人称看不见自己的脸），
  手的肤色往这张脸上靠。（以前用过 Rocketbox 的 Police_Male_05——和沈渡是同一张扫描脸——和 Male_Adult_10，
  后者看着二十出头、偏清秀，不像 32 岁的退伍潜艇兵）
- 缩放到眼睛离地 1.62 米（和 cockpit_camera.gd 的 eye_height 一致），脸朝 Blender +Y（Godot 的 -Z）
"""
import json
import math
import os
import subprocess
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector as V

sys.path.insert(0, os.path.dirname(__file__))
from rocketbox import ROOT, SRC, import_fbx, bone_world, retarget, push_nla, rest_pose, trim_shapes  # noqa: E402
OUT = os.path.join(ROOT, "assets", "models", "crew_body.glb")
GAIT = os.path.join(ROOT, "assets", "models", "crew_body_gait.json")
EYE = 1.62
HEAD_SCRIPT = os.path.join(os.path.dirname(__file__), "gen_head_mpfb.py")
HEAD_BLEND = os.path.join(ROOT, "blender", "cache", "mpfb", "zhou_head.blend")
# 头的网格往下留到哪（Rocketbox 导进来的原尺寸，世界高度，米）：工装领口顶在 1.575，前襟开口低到 1.48；
# 再往下、离脖子中线 NECK 以外的（MPFB 的肩膀起得高，是斜方肌）也裁掉，免得顶出衣领
COLLAR = 1.47
NECK = 0.085
FACE_SHAPES = {"AK_09_EyeBlinkLeft", "AK_10_EyeBlinkRight", "AK_19_EyeSquintLeft", "AK_20_EyeSquintRight",
               "AK_21_EyeWideLeft", "AK_22_EyeWideRight", "AK_25_JawOpen", "AK_44_MouthSmileLeft",
               "AK_45_MouthSmileRight", "AK_03_BrowInnerUp", "AK_30_MouthFrownLeft", "AK_31_MouthFrownRight"}
ANIMS = {
    "walk": "m_walk_neutral_01.max.fbx",
    "run": "m_run_neutral.max.fbx",
    "idle": "m_idle_neutral_01.max.fbx",
    "sit": "m_sit_chair_idle_neutral_01.max.fbx",
}


def contacts(arm, act, f0, f1):
    """左右脚跟落地在循环里的位置（0~1）：脚的高度从高处降到接近最低点的那一帧。"""
    arm.animation_data.action = act
    sc = bpy.context.scene
    h = {"L": [], "R": []}
    for f in range(f0, f1 + 1):
        sc.frame_set(f)
        for s in h:
            h[s].append(bone_world(arm, f"Bip01 {s} Foot").z)
    out = {}
    n = f1 - f0   # 首尾两帧是同一个姿势
    for s, z in h.items():
        z = np.array(z[:n])
        lo, hi = z.min(), z.max()
        near = z < lo + 0.15 * (hi - lo)
        # 循环里从「不着地」变成「着地」的那一帧
        idx = [i for i in range(n) if near[i] and not near[i - 1]]
        out[s] = (idx[0] / n) if idx else 0.0
    sc.frame_set(f0)
    return out


def mpfb_head():
    """周海生的头（gen_head_mpfb.py 生成的 Zhou_Head、Zhou_Hair）：没生成过、或者脚本比产出新，就另起一个 Blender
    （带上装 MPFB 的 BLENDER_USER_RESOURCES，见 tools/fetch_mpfb.sh）先生成一遍，再追加进来。"""
    if not os.path.exists(HEAD_BLEND) or os.path.getmtime(HEAD_BLEND) < os.path.getmtime(HEAD_SCRIPT):
        env = dict(os.environ, BLENDER_USER_RESOURCES=os.path.join(ROOT, "blender", "cache", "mpfb", "blender"))
        subprocess.run([bpy.app.binary_path, "-b", "--factory-startup", "--python", HEAD_SCRIPT], env=env, check=True)
    with bpy.data.libraries.load(HEAD_BLEND) as (src, dst):
        dst.objects = ["Zhou_Head", "Zhou_Hair"]
    for o in dst.objects:
        bpy.context.scene.collection.objects.link(o)
    return dst.objects


def swap_head(arm, old_head):
    """换脸：MPFB 的头和头发按两只眼睛对位（两眼中点对到 Bip01 LEye、REye 的中点，按瞳距缩放），
    绑到工装身体的骨架上（顶点组已经是 Bip01 的名字，绑定姿势下不变形），脖子按领口裁，替掉原来的头。
    返回 (新的头, 头发, 脸上皮肤的平均颜色)。"""
    head, hair = mpfb_head()
    eye_l, eye_r = bone_world(arm, "Bip01 LEye"), bone_world(arm, "Bip01 REye")
    k = (eye_l - eye_r).length / (V(head["eye_l"]) - V(head["eye_r"])).length
    m = Matrix.Translation((eye_l + eye_r) / 2) @ Matrix.Scale(k, 4) @ Matrix.Translation(-V(head["eye_mid"]))
    for o in (head, hair):
        o.data.transform(m, shape_keys=True)
        o.parent = arm
        o.matrix_parent_inverse = arm.matrix_world.inverted()
        o.modifiers.new("Armature", 'ARMATURE').object = arm
        trim_shapes(o, FACE_SHAPES)
    # 脖子：领口以下的、领口附近离中线远的（肩膀）不要
    bm = bmesh.new()
    bm.from_mesh(head.data)
    cut = [v for v in bm.verts if v.co.z < COLLAR or (v.co.z < COLLAR + 0.06 and abs(v.co.x) > NECK)]
    bmesh.ops.delete(bm, geom=cut, context='VERTS')
    bm.to_mesh(head.data)
    bm.free()
    bpy.data.objects.remove(old_head, do_unlink=True)
    head.name = head.data.name = "Crew_Head"
    hair.name = hair.data.name = "Crew_Hair"
    skin = np.array(head["skin"], np.float32)
    print("crew: 换脸 MPFB，缩放 %.3f，裁掉脖子 %d 个顶点，皮肤 %s，材质 %s" % (
        k, len(cut), skin.round(3), [mt.name for mt in head.data.materials]))
    return head, hair, skin


def recolor(img_path, skin=None):
    """工装蓝 → 深海军蓝（按亮度保留褶皱明暗），浅黄劳保鞋 → 黑皮靴；整体叠一层低频的脏旧。"""
    img = bpy.data.images.load(img_path)
    w, h = img.size
    px = np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4)
    rgb = px[..., :3]
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    lum = 0.3 * r + 0.59 * g + 0.11 * b
    # 蓝色工装
    blue = np.clip((b - np.maximum(r, g) - 0.08) * 6.0, 0.0, 1.0)
    navy = np.array([0.09, 0.115, 0.18], np.float32)
    rgb[:] = rgb * (1 - blue[..., None]) + navy * np.clip(lum / 0.24, 0.3, 2.2)[..., None] * blue[..., None]
    # 鞋：贴图下方中间两块（UV 左下是原点）
    yy, xx = np.mgrid[0:h, 0:w] / np.array([h, w], np.float32)[:, None, None]
    region = (yy < 0.28) & (((xx > 0.21) & (xx < 0.42)) | ((xx > 0.58) & (xx < 0.755)))
    tan = region & (r > b + 0.12) & (r - g < 0.15)   # 浅黄的鞋面（皮肤偏红，r - g 更大，不动）
    boot = np.array([0.045, 0.04, 0.035], np.float32)
    rgb[tan] = boot * np.clip(lum[tan] / 0.55, 0.4, 2.0)[:, None]
    # 脏旧：低频起伏（油污、汗渍、洗得发白的地方）
    rng = np.random.default_rng(7)
    low = rng.random((h // 128, w // 128)).astype(np.float32)
    low = np.kron(low, np.ones((128, 128), np.float32))
    for _ in range(3):   # 简单模糊几遍，块变成团
        low = (low + np.roll(low, 37, 0) + np.roll(low, -53, 1) + np.roll(low, 71, (0, 1))) / 4
    cloth = blue > 0.5
    rgb[cloth] *= (0.82 + 0.3 * low[cloth])[:, None]
    # 手：肤色往换上的那张脸靠（不然手是白人的、脸是东亚人的）
    if skin is not None:
        hand = (r > g) & (g > b) & (r - b > 0.08) & (lum > 0.2) & ~cloth & ~tan & ~region
        ref = rgb[hand].mean(0)
        rgb[hand] *= (np.asarray(skin, np.float32) / np.maximum(ref, 1e-3))[None, :] * 0.6 + 0.4
    px[..., :3] = np.clip(rgb, 0, 1)
    img.pixels[:] = px.ravel()
    img.filepath_raw = os.path.join(SRC, "crew_body_color.png")
    img.file_format = 'PNG'
    img.save()
    return img


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.fps = 30
    objs = import_fbx("Construction_Male_05.fbx")
    arm = next(o for o in objs if o.type == 'ARMATURE')
    mesh = next(o for o in objs if o.type == 'MESH')
    for o in objs:
        if o.type == 'EMPTY':
            bpy.data.objects.remove(o, do_unlink=True)

    # 按材质拆开：身体、头；安全帽不要
    bpy.context.view_layer.objects.active = mesh
    mesh.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.separate(type='MATERIAL')
    bpy.ops.object.mode_set(mode='OBJECT')
    parts = [o for o in bpy.data.objects if o.type == 'MESH']
    for o in parts:
        m = o.data.materials[0].name
        if "helmet" in m:
            bpy.data.objects.remove(o, do_unlink=True)
        elif "head" in m:
            o.name = o.data.name = "Crew_Head"
        else:
            o.name = o.data.name = "Crew_Body"
    body = bpy.data.objects["Crew_Body"]
    head, hair, skin = swap_head(arm, bpy.data.objects["Crew_Head"])

    # 材质：贴图换成改过色的；布料很糙，不反光
    col = recolor(os.path.join(SRC, "m104_body_color.tga"), skin)
    nrm = bpy.data.images.load(os.path.join(SRC, "m104_body_normal.tga"))
    nrm.colorspace_settings.name = 'Non-Color'
    for ob, image, normal, name in ((body, col, nrm, "Crew_Body"),):
        mat = bpy.data.materials.new(name)
        nt = mat.node_tree
        bsdf = nt.nodes["Principled BSDF"]
        t = nt.nodes.new('ShaderNodeTexImage')
        t.image = image
        nt.links.new(t.outputs["Color"], bsdf.inputs["Base Color"])
        if normal:
            tn = nt.nodes.new('ShaderNodeTexImage')
            tn.image = normal
            nm = nt.nodes.new('ShaderNodeNormalMap')
            nt.links.new(tn.outputs["Color"], nm.inputs["Color"])
            nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
        bsdf.inputs["Roughness"].default_value = 0.85
        bsdf.inputs["Metallic"].default_value = 0.0
        ob.data.materials.clear()
        ob.data.materials.append(mat)

    # 动画
    sc.frame_set(0)
    gait = {}
    acts = {}
    for key, fname in ANIMS.items():
        act, f0, f1 = retarget(arm, key, fname)
        acts[key] = act
        gait[key] = {"frames": f1 - f0, "fps": sc.render.fps, "length": (f1 - f0) / sc.render.fps}
        if key in ("walk", "run"):
            gait[key].update(contacts(arm, act, f0, f1))
    arm.animation_data.action = None

    # 朝向和大小：静止姿势下脚尖朝 +Y，眼睛离地 EYE
    rest_pose(arm)
    # 脚是外八的，按左右髋的连线定朝向：面朝 f 时右髋在 f × 上 的方向
    right = bone_world(arm, "Bip01 R Thigh") - bone_world(arm, "Bip01 L Thigh")
    fwd = V((0, 0, 1)).cross(right)
    yaw = math.atan2(fwd.y, fwd.x) - math.pi / 2
    eye = (arm.matrix_world @ arm.data.bones["Bip01 REye"].head_local).z
    k = EYE / eye
    arm.matrix_world = Matrix.Rotation(-yaw, 4, 'Z') @ Matrix.Diagonal((k, k, k, 1.0)) @ arm.matrix_world
    gait["scale"] = k
    print("crew: 朝向修正 %.1f°，缩放 %.3f" % (math.degrees(-yaw), k))

    push_nla(arm, acts)

    bpy.ops.object.select_all(action='DESELECT')
    for o in (arm, body, head, hair):
        o.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.export_scene.gltf(
        filepath=OUT, export_format='GLB', use_selection=True, export_yup=True, export_apply=False,
        export_morph=True, export_morph_normal=False, export_animations=True, export_animation_mode='NLA_TRACKS', export_force_sampling=True,
        export_frame_range=False, export_anim_single_armature=True, export_def_bones=False,
        export_image_format='AUTO', export_materials='EXPORT', export_cameras=False, export_lights=False)
    with open(GAIT, "w") as f:
        json.dump(gait, f, indent=2, ensure_ascii=False)
    print("exported", OUT, json.dumps(gait, ensure_ascii=False))


main()
