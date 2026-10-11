"""Microsoft Rocketbox（MIT 许可）角色的共用处理：导入 FBX、把动画重定向到角色骨骼上、量骨骼位置；
眼睛（眼球单独一个材质、眼球贴图上画眼睑的影子、沿上眼睑缘长一排睫毛）。

gen_crew.py（第一人称的身体）和 gen_npc.py（沈渡这些剧情角色）都用它。
原始文件由 tools/fetch_rocketbox.sh 下到 blender/cache/rocketbox/（不进 git）。
"""
import os

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector as V

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


# ============================================================================ 眼睛
# Rocketbox 的头不带睫毛，眼球和脸共用一张贴图、一个材质，眼白上下一样亮——眼睛像贴上去的。这里：
# - 眼球（两只眼共用贴图左下角的同一块 UV）分到单独的材质槽，Godot 里给它开清漆（湿的角膜）
# - 眼球贴图上靠上眼睑那一截压暗（假的眼睑 AO）
# - 沿上眼睑缘（眼眶那一圈边界边里，眨眼时往下走的那半圈）长一条往前上方翘的睫毛片，贴 lash_image 的透明贴图；
#   每个睫毛顶点跟着它根部那个眼睑顶点走：骨骼权重照抄，每个形态键（眨眼、眯眼……）的位移照搬，眨眼时睫毛跟着眼皮下来
EYE_UV_BOX = (0.15, 0.0, 0.38, 0.2)      # 眼球那一块 UV 所在的框（u0, v0, u1, v1）


def _islands(bm):
    """网格的连通块（面的列表）。"""
    seen = set()
    out = []
    for f in bm.faces:
        if f.index in seen:
            continue
        seen.add(f.index)
        stack, isl = [f], []
        while stack:
            g = stack.pop()
            isl.append(g)
            for e in g.edges:
                for h in e.link_faces:
                    if h.index not in seen:
                        seen.add(h.index)
                        stack.append(h)
        out.append(isl)
    return out


def _lash_profile(t):
    """睫毛沿眼睑的长短：内眼角短，往外越来越长，到外眼角前面最长、尾巴收一点（t：0 内眼角 ~ 1 外眼角）。"""
    def ss(a, b, x):
        x = min(max((x - a) / (b - a), 0.0), 1.0)
        return x * x * (3 - 2 * x)
    return 0.45 + 0.55 * ss(0.0, 0.65, t) - 0.25 * ss(0.8, 1.0, t)


def eye_setup(ob, arm, eye_mat, lash_mat, length=0.0048):
    """在头部网格 ob 上：眼球的面分到 eye_mat 槽，沿两只眼的上眼睑缘加睫毛片（lash_mat 槽，最长 length 米）。
    arm 是 ob 现在绑着的骨架（量眼球、头骨的位置）。返回 lid_shadow 要的眼球贴图坐标系。"""
    me = ob.data
    mw = ob.matrix_world
    inv = mw.inverted()
    # 调用方按 0 脸、1 眼球、2 睫毛换材质：头原来只能有脸一个槽
    assert len(me.materials) == 1, f"eye_setup: {ob.name} 原来有 {len(me.materials)} 个材质槽（应该只有脸一个）"
    me.materials.append(eye_mat)
    me.materials.append(lash_mat)
    i_eye, i_lash = len(me.materials) - 2, len(me.materials) - 1
    head = bone_world(arm, "Bip01 Head")
    eyes = {"L": bone_world(arm, "Bip01 LEye"), "R": bone_world(arm, "Bip01 REye")}
    mid = (eyes["L"] + eyes["R"]) / 2
    up = V((0, 0, 1))
    fwd = mid - head
    fwd.z = 0
    fwd.normalize()                                   # 脸朝的方向（水平）
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.verts.ensure_lookup_table()
    uvl = bm.loops.layers.uv.active
    shapes = bm.verts.layers.shape
    dl = bm.verts.layers.deform.active
    u0, v0, u1, v1 = EYE_UV_BOX
    # 眼球：整块 UV 都落在框里的小连通块
    eye_faces = []
    for isl in _islands(bm):
        uv = np.array([l[uvl].uv[:] for f in isl for l in f.loops])
        if len(isl) < 600 and (uv.min(0) > (u0, v0)).all() and (uv.max(0) < (u1, v1)).all():
            for f in isl:
                f.material_index = i_eye
            eye_faces.append(isl)
    assert eye_faces, f"eye_setup: {ob.name} 在 EYE_UV_BOX 里没找到眼球（换了别的头要重新量眼球在贴图上的位置）"
    # 眼球贴图的坐标系：UV 中心、哪个 UV 方向是朝上、UV 上下坐标和世界高度的比例
    isl = eye_faces[0]
    ctr = sum((mw @ v.co for f in isl for v in f.verts), V()) / sum(len(f.verts) for f in isl)
    uv = np.array([l[uvl].uv[:] for f in isl for l in f.loops])
    zr = np.array([(mw @ l.vert.co - ctr).dot(up) for f in isl for l in f.loops])
    c = uv.mean(0)
    up_uv = ((uv - c) * zr[:, None]).sum(0)
    up_uv /= np.linalg.norm(up_uv)
    k = float(((uv - c) @ up_uv * zr).sum() / (zr * zr).sum())   # UV 上下距离 / 世界高度差
    radius = float(np.linalg.norm(uv - c, axis=1).max())
    # 上眼睑缘：眨眼时往下走的皮肤顶点（上眼皮）里最下面那一排；睑缘有前后两排（眼皮的厚度），睫毛长在前排。
    # 眼睑周围的皮肤是封闭的（不是边界边），只能按眨眼形态键的位移找
    sk = me.shape_keys
    basis = np.array([v.co[:] for v in sk.key_blocks[0].data]) if sk else None
    top_s, bot_s = [], []
    lash_n = 0
    for side, blink in (("L", "AK_09_EyeBlinkLeft"), ("R", "AK_10_EyeBlinkRight")):
        eye = eyes[side]
        if sk is None or blink not in sk.key_blocks:
            continue
        d = np.array([v.co[:] for v in sk.key_blocks[blink].data]) - basis
        mag = np.linalg.norm(d, axis=1)
        near = [v for v in bm.verts if (mw @ v.co - eye).length < 0.03 and v.link_faces
                and v.link_faces[0].material_index != i_eye]
        top = max(mag[v.index] for v in near)
        moving = [v for v in near if mag[v.index] > 0.3 * top]
        rel = {v: mw @ v.co - eye for v in near}
        lat = (eye - mid).normalized()                 # 往外眼角的方向
        L_ = {v: rel[v].dot(lat) for v in moving}
        U_ = {v: rel[v].dot(up) for v in moving}
        F_ = {v: rel[v].dot(fwd) for v in moving}
        # 眼皮褶那一排：左右 2.4 毫米以内有低 0.8 毫米以上的点（睑缘前后两排之间只差半毫米上下）
        lid = [v for v in moving if not any(abs(L_[n] - L_[v]) < 0.0024 and U_[v] - U_[n] > 0.0008 for n in moving)]
        # 睑缘后排：旁边 2.5 毫米以内有更靠前 0.6 毫米以上的点；剩下挨得太近（1.2 毫米以内）的只留靠前的
        lid = [v for v in lid if not any((rel[n] - rel[v]).length < 0.0025 and F_[n] - F_[v] > 0.0006 for n in lid)]
        lid = [v for v in lid if not any(n is not v and (rel[n] - rel[v]).length < 0.0012 and F_[n] > F_[v] for n in lid)]
        # 下睑缘：眼球前面、眼睛中线以下离眼球最近的一排（只给眼球贴图的影子定个下限）
        low = [v for v in near if mag[v.index] <= 0.3 * top and rel[v].dot(up) < -0.002 and rel[v].dot(fwd) > 0.008]
        top_s += [rel[v].dot(up) * k for v in lid]
        bot_s += [max(rel[v].dot(up) for v in low) * k] if low else []
        # 从内眼角到外眼角排好
        lid.sort(key=lambda v: L_[v])
        print("eyes: %s 上睑缘 %d 个顶点 %s" % (side, len(lid), [(round(L_[v], 4), round(U_[v], 4)) for v in lid]))
        pts = [mw @ v.co for v in lid]
        acc = [0.0]
        for a, b in zip(pts, pts[1:]):
            acc.append(acc[-1] + (b - a).length)
        rows = []
        for v, p, s in zip(lid, pts, acc):
            t = s / acc[-1]
            L = length * _lash_profile(t)
            out = (p - eye)
            out = (out - up * out.dot(up)).normalized()     # 从眼球中心往外（水平）
            base = (fwd * 0.8 + out * 0.35 + up * 0.15).normalized()
            # 根、中间、梢：先往前、再往上卷；外眼角那几根往外撇
            row = []
            for f, (a, b) in ((0.0, (0.0, 0.0)), (0.5, (0.55, 0.2)), (1.0, (0.75, 0.75))):
                q = p + base * (L * a) + up * (L * b) + lat * (L * 0.25 * t * f) - fwd * 0.0003 * (1 - f)
                nv = bm.verts.new(inv @ q)
                off = nv.co - v.co
                for lay in shapes.values():
                    nv[lay] = v[lay] + off
                if dl is not None:
                    for g, w in v[dl].items():
                        nv[dl][g] = w
                row.append(nv)
            rows.append((row, t))
        for (ra, ta), (rb, tb) in zip(rows, rows[1:]):
            for j in range(2):
                f = bm.faces.new((ra[j], rb[j], rb[j + 1], ra[j + 1]))
                f.material_index = i_lash
                f.smooth = True
                for l, (uu, vv) in zip(f.loops, ((ta, j / 2), (tb, j / 2), (tb, (j + 1) / 2), (ta, (j + 1) / 2))):
                    l[uvl].uv = (uu, vv)
                lash_n += 1
    bm.to_mesh(me)
    bm.free()
    me.update()
    info = {"c": c, "up": up_uv, "r": radius,
            "top": float(np.median(top_s)) if top_s else 0.03, "bot": float(np.median(bot_s)) if bot_s else -0.03}
    print("eyes: 眼球 %d 块，睫毛 %d 片，上睑 %.3f 下睑 %.3f（UV）" % (len(eye_faces), lash_n, info["top"], info["bot"]))
    return info


def lid_shadow(px, info, amount=0.3, band=0.25):
    """眼球贴图上靠上眼睑那一截压暗（px：h×w×4，Blender 的像素顺序，v 朝上）：上睑缘处压暗 amount，
    往下到睁眼高度的 band 处淡没；上睑缘以上（平时盖在眼皮下、往上看时才露出来）也压着。"""
    h, w = px.shape[:2]
    vv, uu = np.mgrid[0:h, 0:w].astype(np.float32)
    uu = (uu + 0.5) / w - info["c"][0]
    vv = (vv + 0.5) / h - info["c"][1]
    s = uu * info["up"][0] + vv * info["up"][1]
    inside = (uu * uu + vv * vv) < (info["r"] * 1.05) ** 2
    lo = info["top"] - band * (info["top"] - info["bot"])
    x = np.clip((s - lo) / max(info["top"] - lo, 1e-4), 0, 1)
    dark = 1.0 - amount * x * x * (3 - 2 * x) * inside
    px[..., :3] *= dark[..., None]


def lower_lid_band(px, depth=0.009):
    """下眼睑缘那一条（0~1 遮罩，px 同 lid_shadow）：头部贴图上眼眶是两个暗红的洞，洞的下沿往下 depth（贴图高的比例）
    那一窄条就是下眼睑的睑缘。Rocketbox 的贴图在这里偏白，脸从下面被桌上的纸、台灯照着时成了一道刺眼的白边，
    眼睛像描了白圈——压暗、调糙要用这个遮罩。"""
    h, w = px.shape[:2]
    r0, r1, c0, c1 = int(0.69 * h), int(0.74 * h), int(0.33 * w), int(0.67 * w)
    sub = px[r0:r1, c0:c1, :3]
    lum = 0.3 * sub[..., 0] + 0.59 * sub[..., 1] + 0.11 * sub[..., 2]
    m = (sub[..., 0] > 1.3 * sub[..., 1]) & (lum < 0.4)
    # 两只眼各从洞的中心长出去，只要连成一片的（眼袋、眉毛上零星的暗红像素不算）
    hole = np.zeros_like(m)
    half = m.shape[1] // 2
    for a, b in ((0, half), (half, m.shape[1])):
        ys, xs = np.nonzero(m[:, a:b])
        if len(ys) == 0:
            continue
        cy, cx = ys.mean(), xs.mean()
        i = int(np.argmin((ys - cy) ** 2 + (xs - cx) ** 2))
        hole[ys[i], a + xs[i]] = True
    for _ in range(600):
        g = hole.copy()
        g[1:] |= hole[:-1]
        g[:-1] |= hole[1:]
        g[:, 1:] |= hole[:, :-1]
        g[:, :-1] |= hole[:, 1:]
        g &= m
        if (g == hole).all():
            break
        hole = g
    # 每一列洞的最低点（v 朝上，行号最小）往下 n 行，越往下越淡；洞里贴近下沿的 n 行（下眼睑朝上的那一圈内侧，
    # 正对着窗和日光灯，白边主要就是它反的光）整个算进去
    n = max(int(depth * h), 1)
    has = hole.any(0)
    lo = np.argmax(hole, axis=0)
    dist = lo[None, :] - np.arange(r1 - r0)[:, None]
    inner = hole & (dist < 0) & (dist >= -n)
    below = (dist >= 0) & (dist <= n)
    band = np.zeros((h, w), np.float32)
    band[r0:r1, c0:c1] = np.where(has[None, :] & below, 1 - dist / (n + 1), np.where(inner, 1.0, 0.0))
    return band


def lash_image(name, w=512, h=128, seed=5):
    """睫毛的透明贴图：u 沿眼睑、v 从根（0）到梢（1）；一百来根往外梢渐细的弯丝，根部连成一道深色的睑缘线。"""
    rng = np.random.default_rng(seed)
    a = np.zeros((h, w), np.float32)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    for _ in range(150):
        u0 = rng.uniform(0.0, 1.0) * w
        lean = rng.normal(0.0, 0.05) * w + 0.04 * w      # 整体往外眼角那边斜一点
        reach = rng.uniform(0.7, 1.0)
        for t in np.linspace(0.0, reach, 48):
            x = u0 + lean * t * t
            y = t * (h - 1)
            r = 2.2 * (1 - t / reach) + 0.6                # 根粗梢细（像素）
            x0, x1 = int(max(x - 4, 0)), int(min(x + 5, w))
            y0, y1 = int(max(y - 4, 0)), int(min(y + 5, h))
            if x0 >= x1 or y0 >= y1:
                continue
            g = np.exp(-(((xx[y0:y1, x0:x1] - x) ** 2 + (yy[y0:y1, x0:x1] - y) ** 2) / (r * r)))
            a[y0:y1, x0:x1] = np.maximum(a[y0:y1, x0:x1], g * (1.0 - 0.35 * t))
    a = np.maximum(a, np.clip(1.0 - yy / (0.16 * h), 0, 1) * 0.95)  # 根部的睑缘线
    px = np.zeros((h, w, 4), np.float32)
    px[..., 0], px[..., 1], px[..., 2] = 0.022, 0.018, 0.016
    px[..., 3] = np.clip(a, 0, 1)
    img = bpy.data.images.new(name, w, h, alpha=True)
    img.pixels[:] = px.ravel()
    img.filepath_raw = os.path.join(SRC, name + ".png")
    img.file_format = 'PNG'
    img.save()
    return img


def lash_material(name):
    """睫毛材质：透明贴图（glTF 里是 BLEND），不反光。"""
    mat = bpy.data.materials.new(name)
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    t = nt.nodes.new('ShaderNodeTexImage')
    t.image = lash_image(name.lower() + "_alpha")
    nt.links.new(t.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(t.outputs["Alpha"], bsdf.inputs["Alpha"])
    bsdf.inputs["Roughness"].default_value = 0.6
    return mat
