"""船员的身体（男女各一套）：Microsoft Rocketbox 的工装角色（MIT 许可），头换成 Vitruvian 的捏脸头。

先跑 tools/fetch_rocketbox.sh、tools/fetch_vitruvian.sh 把素材下到 blender/cache/，再：
    Blender -b --factory-startup --python blender/scripts/gen_crew.py [-- m|f]
导出 assets/models/crew_body_m.glb、crew_body_f.glb（骨骼 + 身体、头、口腔几块网格 + walk / run / idle / sit 四段原地动画）
和 crew_body_m_gait.json、crew_body_f_gait.json（走、跑动画里左右脚落地在循环里的位置，Godot 拿它把动画和步伐对齐）。

- 身体：男 Construction_Male_05（一身蓝色连体工装），女 Construction_Female_01（蓝工装、黄色反光马甲、劳保手套）；
  蓝色压成深海军蓝的作业服，马甲改成深色、反光条留着，浅黄劳保鞋改成黑皮靴，手套压成黑的，磨旧、蹭脏一点
- 动画：按世界空间朝向重定向到角色骨骼上（见 rocketbox.py 的 retarget）
- 头：blender/scripts/gen_head_vitruvian.py 生成的（Crew_Head：脸、眼睛、睫毛、泪线、眼部遮蔽；Crew_Mouth：口腔），
  带全部捏脸（ID_）、表情（EX_）形态键，Godot 里按船员的样子（scripts/crew_look.gd）设形态键的值、换贴图参数。
  按两只眼睛对位、按瞳距缩放，骨骼权重从原来的头上按最近的面插值过来（脸上那些小骨头的权重并进 Bip01 Head），
  脖子按原来的头最低处裁（往下多留 1.5 厘米塞进领口），领口附近离脖子中线太远的（肩膀）也裁掉
- 手的肤色在 Godot 里跟着脸调：身体贴图的 alpha 是皮肤遮罩（1 是露出来的手）
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
from mathutils.bvhtree import BVHTree

sys.path.insert(0, os.path.dirname(__file__))
from rocketbox import ROOT, SRC, import_fbx, bone_world, retarget, push_nla, rest_pose  # noqa: E402
EYE = 1.62
HEAD_SCRIPT = os.path.join(os.path.dirname(__file__), "gen_head_vitruvian.py")
HEAD_BLEND = os.path.join(ROOT, "blender", "cache", "charmorph", "crew_head.blend")
BODIES = {
    "m": ("Construction_Male_05.fbx", "m104"),
    "f": ("Construction_Female_01.fbx", "f101"),
}
# 脖子往领口里多留多少（米，Rocketbox 原尺寸）；领口附近离脖子中线超过 NECK 的裁掉
TUCK = 0.015
NECK = 0.075
# 骨骼权重只留这几根，脸上的小骨头（下巴、眼皮、眉毛……）并进头
KEEP_BONES = {"Bip01 Head", "Bip01 Neck", "Bip01 Spine2", "Bip01 Spine1", "Bip01 L Clavicle", "Bip01 R Clavicle"}
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


def crew_head():
    """捏脸的头（gen_head_vitruvian.py 生成的 Crew_Head、Crew_Mouth）：没生成过、或者脚本比产出新，就另起一个 Blender
    先生成一遍，再追加进来。"""
    if not os.path.exists(HEAD_BLEND) or os.path.getmtime(HEAD_BLEND) < os.path.getmtime(HEAD_SCRIPT):
        subprocess.run([bpy.app.binary_path, "-b", "-Y", "--factory-startup", "--python", HEAD_SCRIPT], check=True)
    with bpy.data.libraries.load(HEAD_BLEND) as (src, dst):
        dst.objects = sorted((n for n in src.objects if n.startswith("Crew_")), key=lambda n: n != "Crew_Head")
    for o in dst.objects:
        bpy.context.scene.collection.objects.link(o)
    return dst.objects


def _weights(ob):
    """网格 ob 每个顶点在各顶点组上的权重（n×组数）和组名。"""
    names = [g.name for g in ob.vertex_groups]
    w = np.zeros((len(ob.data.vertices), len(names)), np.float32)
    for v in ob.data.vertices:
        for e in v.groups:
            w[v.index, e.group] = e.weight
    return w, names


def transfer_weights(src, dst_objs):
    """骨骼权重：dst 每个顶点找 src（原来的头，世界坐标）上最近的面，按重心坐标插值那几个顶点的权重；
    KEEP_BONES 以外的并进 Bip01 Head，再归一化。"""
    me = src.data
    co = [src.matrix_world @ v.co for v in me.vertices]
    tris = []
    for p in me.polygons:
        vs = list(p.vertices)
        tris += [(vs[0], vs[i], vs[i + 1]) for i in range(1, len(vs) - 1)]
    bvh = BVHTree.FromPolygons(co, tris)
    w, names = _weights(src)
    head = names.index("Bip01 Head")
    for j, nm in enumerate(names):
        if nm not in KEEP_BONES:
            w[:, head] += w[:, j]
            w[:, j] = 0
    keep = [j for j, nm in enumerate(names) if w[:, j].max() > 0]
    for o in dst_objs:
        for g in list(o.vertex_groups):
            o.vertex_groups.remove(g)
        groups = {j: o.vertex_groups.new(name=names[j]) for j in keep}
        for v in o.data.vertices:
            loc, _, f, _ = bvh.find_nearest(o.matrix_world @ v.co)
            a, b, c = (co[i] for i in tris[f])
            bw = _bary(loc, a, b, c)
            ww = bw[0] * w[tris[f][0]] + bw[1] * w[tris[f][1]] + bw[2] * w[tris[f][2]]
            s = ww[keep].sum()
            for j in keep:
                if ww[j] > 1e-4:
                    groups[j].add([v.index], float(ww[j] / s), 'REPLACE')


def _bary(p, a, b, c):
    v0, v1, v2 = b - a, c - a, p - a
    d00, d01, d11, d20, d21 = v0.dot(v0), v0.dot(v1), v1.dot(v1), v2.dot(v0), v2.dot(v1)
    den = d00 * d11 - d01 * d01
    if abs(den) < 1e-20:
        return (1.0, 0.0, 0.0)
    v = (d11 * d20 - d01 * d21) / den
    w = (d00 * d21 - d01 * d20) / den
    return (1 - v - w, v, w)


def push_out(objs, bodies, gap=0.004):
    """头发（长发垂到肩上、背上）推出身体（工装）外面：每个顶点找身体上最近的点，在身体里面或者离得比 gap 近，
    就沿那点的法线推到 gap 外；所有形态键一起推（位移不变）。"""
    for body in bodies:
        me = body.data
        co = [body.matrix_world @ v.co for v in me.vertices]
        tris = []
        for p in me.polygons:
            vs = list(p.vertices)
            tris += [(vs[0], vs[i], vs[i + 1]) for i in range(1, len(vs) - 1)]
        bvh = BVHTree.FromPolygons(co, tris)
        for o in objs:
            if not o.name.startswith("Crew_Hair"):
                continue
            n = len(o.data.vertices)
            moved = 0
            push = np.zeros((n, 3), np.float32)
            for v in o.data.vertices:
                loc, nrm, _, _ = bvh.find_nearest(v.co)
                if loc is None:
                    continue
                sd = (v.co - loc).dot(nrm)
                if sd < gap and (v.co - loc).length < 0.05:
                    push[v.index] = nrm * (gap - sd)
                    moved += 1
            if not moved:
                continue
            for kb in o.data.shape_keys.key_blocks:
                c = np.empty(n * 3, np.float32)
                kb.data.foreach_get("co", c)
                c = (c.reshape(-1, 3) + push).ravel()
                kb.data.foreach_set("co", c)
                if kb.name == "Basis":
                    o.data.vertices.foreach_set("co", c)
            print("crew: %s 推出身体 %d 个顶点" % (o.name, moved))


def swap_head(arm, old_head):
    """换头：Crew_Head、Crew_Mouth 按两只眼睛对位（两眼中点对到 Bip01 LEye、REye 的中点，按瞳距缩放），
    权重从原来的头传过来，绑到身体的骨架上，脖子按原来的头最低处裁，替掉原来的头。"""
    objs = crew_head()
    head = objs[0]
    eye_l, eye_r = bone_world(arm, "Bip01 LEye"), bone_world(arm, "Bip01 REye")
    k = (eye_l - eye_r).length / (V(head["eye_l"]) - V(head["eye_r"])).length
    mid = (V(head["eye_l"]) + V(head["eye_r"])) / 2
    m = Matrix.Translation((eye_l + eye_r) / 2) @ Matrix.Scale(k, 4) @ Matrix.Translation(-mid)
    for o in objs:
        o.data.transform(m, shape_keys=True)
    head["eye_l"], head["eye_r"] = [list(m @ V(head[n])) for n in ("eye_l", "eye_r")]
    # 脖子：原来的头最低处往下 TUCK 以下的、领口附近离中线远的（肩膀）不要
    oco = np.array([old_head.matrix_world @ v.co for v in old_head.data.vertices])
    collar = oco[:, 2].min() - TUCK
    ny = np.median(oco[oco[:, 2] < collar + 0.06][:, 1])
    bm = bmesh.new()
    bm.from_mesh(head.data)
    cut = [v for v in bm.verts if v.co.z < collar or
           (v.co.z < collar + 0.07 and math.hypot(v.co.x, (v.co.y - ny) * 0.8) > NECK)]
    bmesh.ops.delete(bm, geom=cut, context='VERTS')
    bm.to_mesh(head.data)
    bm.free()
    push_out(objs[1:], [b for b in arm.children if b.type == 'MESH' and "body" in b.data.materials[0].name])
    transfer_weights(old_head, objs)
    for o in objs:
        o.parent = arm
        o.matrix_parent_inverse = arm.matrix_world.inverted()
        o.modifiers.new("Armature", 'ARMATURE').object = arm
    bpy.data.objects.remove(old_head, do_unlink=True)
    print("crew: 换头，缩放 %.3f，领口 %.3f，裁掉脖子 %d 个顶点，形态键 %d 个" % (
        k, collar, len(cut), len(head.data.shape_keys.key_blocks) - 1))
    return objs


# 劳保鞋在贴图上的位置（UV 左下是原点）：[(u0, u1, v1), ...]
BOOTS = {"m": [(0.21, 0.42, 0.28), (0.58, 0.755, 0.28)], "f": [(0.2, 0.8, 0.31)]}
# 露皮肤的地方只在这个框里（u0, v0, u1, v1）：男的是两只手（不限），女的戴手套，只有领口
SKIN_BOX = {"m": (0.0, 0.0, 1.0, 1.0), "f": (0.42, 0.42, 0.58, 0.66)}


def recolor(img_path, out_name, sex):
    """蓝工装 → 深海军蓝（按亮度保留褶皱明暗），黄色反光马甲 → 深色、反光条留着，浅黄劳保鞋 → 黑皮靴，
    劳保手套 → 黑的；整体叠一层低频的脏旧。alpha 换成皮肤遮罩（露出来的手 1，Godot 里按脸的肤色调）。"""
    img = bpy.data.images.load(img_path)
    w, h = img.size
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(h, w, 4)
    rgb = px[..., :3]
    r, g, b = rgb[..., 0].copy(), rgb[..., 1].copy(), rgb[..., 2].copy()
    lum = 0.3 * r + 0.59 * g + 0.11 * b
    # 蓝色布料
    blue = np.clip((b - np.maximum(r, g) - 0.08) * 6.0, 0.0, 1.0)
    navy = np.array([0.09, 0.115, 0.18], np.float32)
    rgb[:] = rgb * (1 - blue[..., None]) + navy * np.clip(lum / 0.24, 0.3, 2.2)[..., None] * blue[..., None]
    # 黄色（反光马甲、手套上的黄）：压成深炭灰，按亮度留褶皱
    yellow = np.clip((np.minimum(r, g) - b - 0.25) * 5.0, 0.0, 1.0) * (np.abs(r - g) < 0.25)
    char = np.array([0.075, 0.08, 0.09], np.float32)
    rgb[:] = rgb * (1 - yellow[..., None]) + char * np.clip(lum / 0.6, 0.4, 1.8)[..., None] * yellow[..., None]
    # 鞋：贴图下方中间（BOOTS），浅黄 / 浅棕的鞋面
    yy, xx = np.mgrid[0:h, 0:w] / np.array([h, w], np.float32)[:, None, None]
    region = np.zeros((h, w), bool)
    for u0, u1, v1 in BOOTS[sex]:
        region |= (yy < v1) & (xx > u0) & (xx < u1)
    tan = region & (r > b + 0.12) & (r - g < 0.2) & (yellow < 0.5)
    boot = np.array([0.045, 0.04, 0.035], np.float32)
    rgb[tan] = boot * np.clip(lum[tan] / 0.55, 0.4, 2.0)[:, None]
    # 脏旧：低频起伏（油污、汗渍、洗得发白的地方）
    rng = np.random.default_rng(7)
    low = rng.random((h // 128, w // 128)).astype(np.float32)
    low = np.kron(low, np.ones((128, 128), np.float32))
    for _ in range(3):   # 简单模糊几遍，块变成团
        low = (low + np.roll(low, 37, 0) + np.roll(low, -53, 1) + np.roll(low, 71, (0, 1))) / 4
    cloth = (blue > 0.5) | (yellow > 0.5)
    rgb[cloth] *= (0.82 + 0.3 * low[cloth])[:, None]
    # 皮肤遮罩：偏红的暖色（够饱和，马甲上灰白的反光条不算）、够亮、不是布料和鞋
    u0, v0, u1, v1 = SKIN_BOX[sex]
    skin = ((r > g) & (g > b) & (r - b > 0.25 * r) & (lum > 0.2) & ~cloth & ~tan & ~region
            & (xx > u0) & (xx < u1) & (yy > v0) & (yy < v1))
    px[..., 3] = skin.astype(np.float32)
    px[..., :3] = np.clip(rgb, 0, 1)
    bpy.data.images.remove(img)
    # 原图是 24 位的 TGA，存不下 alpha：另建一张带 alpha 的
    img = bpy.data.images.new(out_name, w, h, alpha=True)
    img.pixels.foreach_set(px.ravel())
    img.filepath_raw = os.path.join(SRC, out_name + ".png")
    img.file_format = 'PNG'
    img.save()
    img.alpha_mode = 'CHANNEL_PACKED'
    print("crew: 皮肤遮罩 %d 像素，手的平均色（线性）%s" % (skin.sum(), np.round(_srgb_to_lin(px[..., :3][skin]).mean(0), 4)))
    return img


def _srgb_to_lin(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def sparsify_targets(path, eps_pos=2e-5, eps_nrm=0.01):
    """导出的 glb 里形态键的位移改成稀疏存：Blender 给每个形态键重算法线，全网格都带着一点浮点误差，
    导出器只好按稠密存（130 个形态键 × 1.5 万顶点，光法线就 40 多 MB）。位置小于 eps_pos 米、法线小于 eps_nrm 的清零，
    剩下的写成 sparse 访问器（没有 bufferView，底子是 0），再把 BIN 重新紧凑地排一遍。"""
    import struct
    data = open(path, "rb").read()
    jl = struct.unpack("<I", data[12:16])[0]
    j = json.loads(data[20:20 + jl])
    bl = struct.unpack("<I", data[20 + jl:24 + jl])[0]
    binc = data[28 + jl:28 + jl + bl]
    bvs, accs = j["bufferViews"], j["accessors"]

    def raw(bv):
        v = bvs[bv]
        return binc[v.get("byteOffset", 0):v.get("byteOffset", 0) + v["byteLength"]]

    def dense(a):
        out = np.zeros((a["count"], 3), np.float32)
        if "bufferView" in a:
            out[:] = np.frombuffer(raw(a["bufferView"]), np.float32,
                                   a["count"] * 3, a.get("byteOffset", 0)).reshape(-1, 3)
        sp = a.get("sparse")
        if sp:
            it = {5121: np.uint8, 5123: np.uint16, 5125: np.uint32}[sp["indices"]["componentType"]]
            ii = np.frombuffer(raw(sp["indices"]["bufferView"]), it, sp["count"], sp["indices"].get("byteOffset", 0))
            vv = np.frombuffer(raw(sp["values"]["bufferView"]), np.float32, sp["count"] * 3,
                               sp["values"].get("byteOffset", 0)).reshape(-1, 3)
            out[ii.astype(np.int64)] = vv
        return out

    blobs = {}           # 新的 bufferView 下标 → 字节
    new_views = []

    def add(b):
        new_views.append({"buffer": 0, "byteLength": len(b)})
        blobs[len(bvs) + len(new_views) - 1] = b
        return len(bvs) + len(new_views) - 1

    before = after = 0
    for m in j["meshes"]:
        # 头发（发片、层壳）：位置 0.1 毫米以下的不要，法线增量全不要（法线变一点看不出来）
        hair = m.get("name", "").startswith(("Crew_Hair", "Crew_Shell"))
        ep, en = (1e-4, 1e9) if hair else (eps_pos, eps_nrm)
        for p in m["primitives"]:
            for t in p.get("targets", []):
                for k, ai in t.items():
                    a = accs[ai]
                    d = dense(a)
                    before += d.nbytes
                    keep = np.flatnonzero(np.abs(d).max(1) > (ep if k == "POSITION" else en))
                    a.pop("bufferView", None)
                    a.pop("byteOffset", None)
                    a.pop("sparse", None)
                    if k == "POSITION":
                        dd = d.copy()
                        mask = np.zeros(len(d), bool)
                        mask[keep] = True
                        dd[~mask] = 0
                        a["min"] = [float(x) for x in dd.min(0)]
                        a["max"] = [float(x) for x in dd.max(0)]
                    if len(keep) == 0:
                        continue
                    it, ct = (np.uint16, 5123) if a["count"] < 65536 else (np.uint32, 5125)
                    ib = keep.astype(it).tobytes()
                    vb = d[keep].astype(np.float32).tobytes()
                    after += len(ib) + len(vb)
                    a["sparse"] = {"count": int(len(keep)), "indices": {"bufferView": add(ib), "componentType": ct},
                                   "values": {"bufferView": add(vb)}}
    # 还在用的旧 bufferView（几何、贴图、动画）照抄，新的接在后面，重新排偏移
    used = set()
    for a in accs:
        if "bufferView" in a:
            used.add(a["bufferView"])
        if "sparse" in a:
            used.add(a["sparse"]["indices"]["bufferView"])
            used.add(a["sparse"]["values"]["bufferView"])
    for im in j.get("images", []):
        if "bufferView" in im:
            used.add(im["bufferView"])
    allv = bvs + new_views
    remap, out = {}, bytearray()
    views = []
    for i in sorted(used):
        b = blobs[i] if i in blobs else raw(i)
        while len(out) % 4:
            out.append(0)
        v = dict(allv[i])
        v["byteOffset"] = len(out)
        v["byteLength"] = len(b)
        remap[i] = len(views)
        views.append(v)
        out += b
    for a in accs:
        if "bufferView" in a:
            a["bufferView"] = remap[a["bufferView"]]
        if "sparse" in a:
            a["sparse"]["indices"]["bufferView"] = remap[a["sparse"]["indices"]["bufferView"]]
            a["sparse"]["values"]["bufferView"] = remap[a["sparse"]["values"]["bufferView"]]
    for im in j.get("images", []):
        if "bufferView" in im:
            im["bufferView"] = remap[im["bufferView"]]
    j["bufferViews"] = views
    while len(out) % 4:
        out.append(0)
    j["buffers"] = [{"byteLength": len(out)}]
    js = json.dumps(j, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    glb = struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(out))
    glb += struct.pack("<I4s", len(js), b"JSON") + js + struct.pack("<I4s", len(out), b"BIN\0") + bytes(out)
    open(path, "wb").write(glb)
    print("crew: 形态键位移 %.1f MB → %.1f MB，glb %.1f MB" % (before / 1e6, after / 1e6, len(glb) / 1e6))


def build(sex):
    fbx, tex = BODIES[sex]
    out = os.path.join(ROOT, "assets", "models", f"crew_body_{sex}.glb")
    gait_path = os.path.join(ROOT, "assets", "models", f"crew_body_{sex}_gait.json")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.fps = 30
    objs = import_fbx(fbx)
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
    old_head = None
    for o in [o for o in bpy.data.objects if o.type == 'MESH']:
        m = o.data.materials[0].name
        if "helmet" in m:
            bpy.data.objects.remove(o, do_unlink=True)
        elif "head" in m:
            old_head = o
        else:
            o.name = o.data.name = "Crew_Body"
    body = bpy.data.objects["Crew_Body"]
    heads = swap_head(arm, old_head)

    # 材质：贴图换成改过色的；布料很糙，不反光
    col = recolor(os.path.join(SRC, f"{tex}_body_color.tga"), f"crew_body_{sex}_color", sex)
    nrm = bpy.data.images.load(os.path.join(SRC, f"{tex}_body_normal.tga"))
    nrm.colorspace_settings.name = 'Non-Color'
    mat = bpy.data.materials.new("Crew_Body")
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    t = nt.nodes.new('ShaderNodeTexImage')
    t.image = col
    nt.links.new(t.outputs["Color"], bsdf.inputs["Base Color"])
    tn = nt.nodes.new('ShaderNodeTexImage')
    tn.image = nrm
    nm = nt.nodes.new('ShaderNodeNormalMap')
    nt.links.new(tn.outputs["Color"], nm.inputs["Color"])
    nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    bsdf.inputs["Roughness"].default_value = 0.85
    bsdf.inputs["Metallic"].default_value = 0.0
    body.data.materials.clear()
    body.data.materials.append(mat)

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
    print("crew %s: 朝向修正 %.1f°，缩放 %.3f" % (sex, math.degrees(-yaw), k))

    push_nla(arm, acts)

    bpy.ops.object.select_all(action='DESELECT')
    for o in [arm, body] + heads:
        o.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.export_scene.gltf(
        filepath=out, export_format='GLB', use_selection=True, export_yup=True, export_apply=False,
        export_morph=True, export_morph_normal=True, export_try_sparse_sk=True, export_animations=True,
        export_animation_mode='NLA_TRACKS', export_force_sampling=True, export_frame_range=False,
        export_anim_single_armature=True, export_def_bones=False, export_vertex_color='ACTIVE',
        export_image_format='AUTO', export_materials='EXPORT', export_cameras=False, export_lights=False)
    sparsify_targets(out)
    with open(gait_path, "w") as f:
        json.dump(gait, f, indent=2, ensure_ascii=False)
    print("exported", out, json.dumps(gait, ensure_ascii=False))


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    for sex in (argv or list(BODIES)):
        build(sex)


main()
