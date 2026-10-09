"""第一人称的身体：Microsoft Rocketbox 的 Construction_Male_05（MIT 许可），改成潜艇兵。

先跑 tools/fetch_rocketbox.sh 把角色和动画下到 blender/cache/rocketbox/，再：
    Blender -b --factory-startup --python blender/scripts/gen_crew.py
导出 assets/models/crew_body.glb（骨骼 + 身体、头两块网格 + walk / run / idle / sit 四段原地动画）
和 assets/models/crew_body_gait.json（走、跑动画里左右脚落地在循环里的位置，Godot 拿它把动画和步伐对齐）。

- 动画：Rocketbox 的动画文件和角色是同一套 3ds Max Biped 骨骼，但动画文件的绑定姿势不一样，不能直接套。
  这里用世界空间的「复制旋转」约束把每根骨头的朝向抄过来（骨盆再抄位置，按腿长比例缩放），再烘焙成角色自己的动作
- 贴图：蓝色工装压成深海军蓝的作业服，磨旧、蹭脏一点；浅黄色劳保鞋改成黑皮靴；手不动
- 安全帽删掉；头单独一块网格（Godot 里只投影子不渲染，第一人称看不见自己的脸）
- 缩放到眼睛离地 1.62 米（和 cockpit_camera.gd 的 eye_height 一致），脸朝 Blender +Y（Godot 的 -Z）
"""
import json
import math
import os

import bpy
import numpy as np
from mathutils import Matrix, Vector as V

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC = os.path.join(ROOT, "blender", "cache", "rocketbox")
OUT = os.path.join(ROOT, "assets", "models", "crew_body.glb")
GAIT = os.path.join(ROOT, "assets", "models", "crew_body_gait.json")
EYE = 1.62
ANIMS = {
    "walk": "m_walk_neutral_01.max.fbx",
    "run": "m_run_neutral.max.fbx",
    "idle": "m_idle_neutral_01.max.fbx",
    "sit": "m_sit_chair_idle_neutral_01.max.fbx",
}


def import_fbx(name):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=os.path.join(SRC, name), automatic_bone_orientation=False)
    return [o for o in bpy.data.objects if o not in before]


def leg_length(arm):
    b = arm.data.bones
    pts = [arm.matrix_world @ b[n].head_local for n in ("Bip01 L Thigh", "Bip01 L Calf", "Bip01 L Foot")]
    return (pts[1] - pts[0]).length + (pts[2] - pts[1]).length


def bone_world(arm, name):
    return arm.matrix_world @ arm.pose.bones[name].head


def retarget(arm, key, fname):
    """把动画文件的动作按世界空间朝向抄到角色骨骼上，烘焙成名为 key 的动作。"""
    new = import_fbx(fname)
    src = next(o for o in new if o.type == 'ARMATURE')
    act = src.animation_data.action
    f0, f1 = (int(round(v)) for v in act.frame_range)
    # 骨盆位置按腿长比例缩放（两副骨架高矮不一样，不缩脚会悬空或者陷进地里）
    k = leg_length(arm) / leg_length(src)
    src.matrix_world = Matrix.Diagonal((k, k, k, 1.0)) @ src.matrix_world
    names = {b.name for b in src.data.bones}
    for pb in arm.pose.bones:
        if pb.name not in names:
            continue
        c = pb.constraints.new('COPY_ROTATION')
        c.target, c.subtarget = src, pb.name
        c.owner_space = c.target_space = 'WORLD'
        if pb.name == "Bip01 Pelvis":
            c = pb.constraints.new('COPY_LOCATION')
            c.target, c.subtarget = src, pb.name
            c.owner_space = c.target_space = 'WORLD'
    bpy.context.view_layer.objects.active = arm
    arm.select_set(True)
    bpy.ops.object.mode_set(mode='POSE')
    bpy.ops.pose.select_all(action='SELECT')
    bpy.ops.nla.bake(frame_start=f0, frame_end=f1, only_selected=False, visual_keying=True,
                     clear_constraints=True, use_current_action=False, bake_types={'POSE'})
    bpy.ops.object.mode_set(mode='OBJECT')
    baked = arm.animation_data.action
    baked.name = key
    baked.use_fake_user = True
    for o in new:
        bpy.data.objects.remove(o, do_unlink=True)
    bpy.data.actions.remove(act)
    return baked, f0, f1


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


def recolor(img_path):
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
    head = bpy.data.objects["Crew_Head"]

    # 材质：贴图换成改过色的；布料很糙，不反光
    col = recolor(os.path.join(SRC, "m104_body_color.tga"))
    nrm = bpy.data.images.load(os.path.join(SRC, "m104_body_normal.tga"))
    nrm.colorspace_settings.name = 'Non-Color'
    hcol = bpy.data.images.load(os.path.join(SRC, "m104_head_color.tga"))
    for ob, image, normal, name in ((body, col, nrm, "Crew_Body"), (head, hcol, None, "Crew_Head")):
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
    for pb in arm.pose.bones:
        pb.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()
    # 脚是外八的，按左右髋的连线定朝向：面朝 f 时右髋在 f × 上 的方向
    right = bone_world(arm, "Bip01 R Thigh") - bone_world(arm, "Bip01 L Thigh")
    fwd = V((0, 0, 1)).cross(right)
    yaw = math.atan2(fwd.y, fwd.x) - math.pi / 2
    eye = (arm.matrix_world @ arm.data.bones["Bip01 REye"].head_local).z
    k = EYE / eye
    arm.matrix_world = Matrix.Rotation(-yaw, 4, 'Z') @ Matrix.Diagonal((k, k, k, 1.0)) @ arm.matrix_world
    gait["scale"] = k
    print("crew: 朝向修正 %.1f°，缩放 %.3f" % (math.degrees(-yaw), k))

    # 每段动作放进一条 NLA 轨道，导出时一段一个动画
    ad = arm.animation_data
    for key, act in acts.items():
        tr = ad.nla_tracks.new()
        tr.name = key
        st = tr.strips.new(key, int(act.frame_range[0]), act)
        st.name = key
        tr.mute = True

    bpy.ops.object.select_all(action='DESELECT')
    for o in (arm, body, head):
        o.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.export_scene.gltf(
        filepath=OUT, export_format='GLB', use_selection=True, export_yup=True, export_apply=False,
        export_animations=True, export_animation_mode='NLA_TRACKS', export_force_sampling=True,
        export_frame_range=False, export_anim_single_armature=True, export_def_bones=False,
        export_image_format='AUTO', export_materials='EXPORT', export_cameras=False, export_lights=False)
    with open(GAIT, "w") as f:
        json.dump(gait, f, indent=2, ensure_ascii=False)
    print("exported", OUT, json.dumps(gait, ensure_ascii=False))


main()
