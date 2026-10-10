"""Microsoft Rocketbox（MIT 许可）角色的共用处理：导入 FBX、把动画重定向到角色骨骼上、量骨骼位置。

gen_crew.py（第一人称的身体）和 gen_npc.py（沈渡这些剧情角色）都用它。
原始文件由 tools/fetch_rocketbox.sh 下到 blender/cache/rocketbox/（不进 git）。
"""
import os

import bpy
import numpy as np
from mathutils import Matrix

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC = os.path.join(ROOT, "blender", "cache", "rocketbox")


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
    """把动画文件的动作按世界空间朝向抄到角色骨骼上，烘焙成名为 key 的动作。

    Rocketbox 的动画文件和角色是同一套 3ds Max Biped 骨骼，但动画文件的绑定姿势不一样，不能直接套：
    这里用世界空间的「复制旋转」约束把每根骨头的朝向抄过来（骨盆再抄位置，按腿长比例缩放），再烘焙成角色自己的动作。
    脸上的骨头（下巴、眼皮……）动画文件里没有，保持绑定姿势，表情交给形态键。"""
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


def push_nla(arm, acts):
    """每段动作放进一条 NLA 轨道，导出 glTF 时一段一个动画。"""
    arm.animation_data.action = None
    ad = arm.animation_data
    for key, act in acts.items():
        tr = ad.nla_tracks.new()
        tr.name = key
        st = tr.strips.new(key, int(act.frame_range[0]), act)
        st.name = key
        tr.mute = True


def rest_pose(arm):
    for pb in arm.pose.bones:
        pb.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()


def trim_shapes(ob, keep):
    """只留 keep 里、而且在这块网格上真的有位移的形态键（全留的话 glb 要大好几倍）。"""
    sk = ob.data.shape_keys
    if sk is None:
        return
    basis = np.empty(len(ob.data.vertices) * 3, np.float32)
    sk.key_blocks[0].data.foreach_get("co", basis)
    for kb in list(sk.key_blocks)[1:]:
        co = np.empty_like(basis)
        kb.data.foreach_get("co", co)
        if kb.name not in keep or np.abs(co - basis).max() < 1e-5:
            ob.shape_key_remove(kb)
    if len(sk.key_blocks) == 1:
        ob.shape_key_clear()
