"""主角周海生的头：MPFB2（MakeHuman 的 Blender 扩展，生成的人和素材 CC0）生成，换掉 Rocketbox 的 Male_Adult_10
（m024 看着二十出头、偏清秀，不像剧本里 32 岁的退伍潜艇兵、修船工，见 docs/story.md）。

先跑 tools/fetch_mpfb.sh（扩展和素材包装到 blender/cache/mpfb/，不动自己的 Blender 配置），再：
    BLENDER_USER_RESOURCES=blender/cache/mpfb/blender Blender -b --factory-startup --python blender/scripts/gen_head_mpfb.py [-- --preview 目录]
gen_crew.py 发现头没生成、或者这个脚本改过，会自己这样调一遍。
产出 blender/cache/mpfb/zhou_head.blend（Zhou_Head、Zhou_Hair 两块网格，gen_crew.swap_head 接到工装身体上）和几张贴图：

- 人：男、东亚 0.9、MakeHuman 年龄 0.6（约 38 岁的骨相，配上晒黑、胡茬的皮肤看着三十出头到三十五）、偏瘦、肌肉偏多；
  再微调几项：颧骨高、腮帮瘦、下颌方、眉压低、眼袋、额头矮一点，脖子拉长、加粗（MPFB 的肩膀比 Rocketbox 的身体起得高，
  不拉长会顶出衣领；干体力活的脖子粗）
- 带眉毛、睫毛、眼球、平头几个代理网格；加载 visemes02（15 个口型）和 faceunits01（52 个 ARKit 表情）两个形态键包，
  建模用的形态键（宏、微调）合进基础形状，表情和口型按 Rocketbox 的名字改名（AA_VI_xx、AK_xx，眨眼是 AK_09/AK_10）
- 只留头和脖子（往下多留一截，gen_crew 按领口裁）；眼球去掉透明的角膜壳；眉毛、睫毛、眼球并进头，一块网格多个材质槽：
  Crew_Head（皮肤）、Crew_Eyes、Crew_Lashes、Crew_Brows；头发单独一块 Crew_Hair
- 骨骼：用 MPFB 的 game_engine 骨架只为了拿蒙皮权重，顶点组按 BONES 改成 Rocketbox 的 Bip01 名字，骨架本身不要
- 皮肤贴图：MakeHuman 的 middleage_asian_male（2048，全身一张），把头上的每个像素对应的三维位置光栅化出来，
  按三维位置画：晒黑、鼻头颧骨耳朵晒红、下巴两腮上唇一层胡茬、眼下发暗；法线贴图（毛孔、法令纹、抬头纹）和粗糙度也一样画。
  MakeHuman 的贴图没有烘进去的暗部（Rocketbox 的有），日光灯下脸是平的：用 Cycles 烘一张近处的环境光遮蔽（8 厘米内），
  乘进皮肤和眼球的颜色——眼窝、鼻底、嘴角、耳朵里、发际线暗下去，眼球靠上眼皮那一截也压暗了
- 眼球：虹膜压成深棕、眼白压暗一点；头发压成黑的
"""
import os
import sys

import addon_utils
import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector as V

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CACHE = os.path.join(ROOT, "blender", "cache", "mpfb")
OUT = os.path.join(CACHE, "zhou_head.blend")
EXT = "bl_ext.user_default.mpfb"
HAIR = "short01"        # 贴着头皮的平头（short02 那种蓬起来的在镜子里像扣了个头套）
BROW = "eyebrow008"

HUMAN = {
    "name": "zhou",
    "phenotype": {"gender": 1.0, "age": 0.6, "muscle": 0.62, "weight": 0.36, "proportions": 0.5, "height": 0.5,
                  "cupsize": 0.5, "firmness": 0.5, "race": {"asian": 0.9, "caucasian": 0.1, "african": 0.0}},
    "targets": [{"target": t, "value": v} for t, v in (
        ("head-square", 0.3),
        ("l-cheek-bones-incr", 0.35), ("r-cheek-bones-incr", 0.35),
        ("l-cheek-volume-decr", 0.4), ("r-cheek-volume-decr", 0.4),
        ("chin-prominent-incr", 0.2), ("chin-width-incr", 0.25),
        ("eyebrows-trans-down", 0.25),
        ("l-eye-bag-incr", 0.3), ("r-eye-bag-incr", 0.3),
        ("forehead-scale-vert-decr", 0.35),
        ("measure-neck-height-incr", 0.6), ("measure-neck-circ-incr", 0.6),
    )],
    "rig": "game_engine",
    "eyes": "high-poly/high-poly.mhclo",
    "eyebrows": f"{BROW}/{BROW}.mhclo",
    "eyelashes": "eyelashes01/eyelashes01.mhclo",
    "hair": f"{HAIR}/{HAIR}.mhclo",
    "skin_mhmat": "middleage_asian_male/middleage_asian_male.mhmat",
    "skin_material_type": "MAKESKIN",
    "eyes_material_type": "MAKESKIN",
}
# MPFB game_engine 骨架 → Rocketbox（头、脖子以外的只在脖根那一圈有一点权重）
BONES = {"head": "Bip01 Head", "neck_01": "Bip01 Neck", "spine_03": "Bip01 Spine2", "spine_02": "Bip01 Spine1",
         "clavicle_l": "Bip01 L Clavicle", "clavicle_r": "Bip01 R Clavicle",
         "upperarm_l": "Bip01 L UpperArm", "upperarm_r": "Bip01 R UpperArm"}
# visemes02（Meta/Oculus 的 15 个口型）→ Rocketbox 的 AA_VI_xx（同一套，顺序一样）
VISEMES = ["sil", "PP", "FF", "TH", "DD", "kk", "CH", "SS", "nn", "RR", "aa", "E", "I", "O", "U"]
VISEME_NAMES = {f"viseme_{v}": f"AA_VI_{i:02d}_{n}" for i, (v, n) in enumerate(zip(VISEMES, (
    "Sil", "PP", "FF", "TH", "DD", "KK", "CH", "SS", "nn", "RR", "aa", "E", "I", "O", "U")))}


def _arg(name, default=None):
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    return argv[argv.index(name) + 1] if name in argv else default


def _co(kb_or_verts, n):
    a = np.empty(n * 3, np.float32)
    kb_or_verts.foreach_get("co", a)
    return a.reshape(n, 3)


def bake_shapes(ob, rename):
    """建模用的形态键（$md- 宏、微调）按当前的值合进基础形状；rename 里有的（表情、口型）改名留下，相对新的基础形状。"""
    me = ob.data
    sk = me.shape_keys
    if sk is None:
        return
    n = len(me.vertices)
    basis = _co(sk.key_blocks[0].data, n)
    model = basis.copy()
    keep = {}
    for kb in list(sk.key_blocks)[1:]:
        d = _co(kb.data, n) - basis
        if kb.name in rename:
            if np.abs(d).max() > 1e-6:
                keep[rename[kb.name]] = d
        else:
            model += d * kb.value
    ob.shape_key_clear()
    me.vertices.foreach_set("co", model.ravel())
    if keep:
        ob.shape_key_add(name="Basis", from_mix=False)
        for name, d in keep.items():
            kb = ob.shape_key_add(name=name, from_mix=False)
            kb.data.foreach_set("co", (model + d).ravel())
            kb.value = 0.0          # Blender 5 新加的形态键默认值是 1
    me.update()


def keep_verts(ob, pred):
    """只留 pred(顶点) 为真的顶点（bmesh 删顶点时形态键、顶点组跟着走）。"""
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not pred(bm, v)], context='VERTS')
    bm.to_mesh(ob.data)
    bm.free()
    ob.data.update()


def map_groups(ob, bones):
    """顶点组只留骨头的（bones：MPFB 骨架的骨头名），改成 Rocketbox 的名字；BONES 里没有的骨头，权重并进头。"""
    for g in list(ob.vertex_groups):
        if g.name not in bones:
            ob.vertex_groups.remove(g)
        elif g.name in BONES:
            g.name = BONES[g.name]
    head = ob.vertex_groups.get("Bip01 Head") or ob.vertex_groups.new(name="Bip01 Head")
    names = set(BONES.values())
    for g in list(ob.vertex_groups):
        if g.name in names:
            continue
        for v in ob.data.vertices:
            for e in v.groups:
                if e.group == g.index and e.weight > 0:
                    head.add([v.index], e.weight, 'ADD')
        ob.vertex_groups.remove(g)


def landmark(ob, key, side=None):
    """形态键 key 位移最大的那个顶点（嘴角、下巴、鼻翼……）的位置。"""
    me = ob.data
    n = len(me.vertices)
    kb = me.shape_keys.key_blocks
    d = np.linalg.norm(_co(kb[key].data, n) - _co(kb[0].data, n), axis=1)
    co = _co(me.vertices, n)
    if side is not None:
        d = d * (co[:, 0] * side > 0)
    return V(co[int(np.argmax(d))])


# ============================================================================ 贴图
def _ss(a, b, x):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def raster(ob, size):
    """头的每个贴图像素对应的三维位置（size×size×3，Blender 的像素顺序：行是 v、从下往上）和覆盖遮罩。"""
    me = ob.data
    me.calc_loop_triangles()
    tris = np.array([t.loops[:] for t in me.loop_triangles if me.materials[t.material_index].name == "_Crew_Head"])
    uv = np.empty(len(me.loops) * 2, np.float32)
    me.uv_layers.active.data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2) * size - 0.5
    vi = np.empty(len(me.loops), np.int64)
    me.loops.foreach_get("vertex_index", vi)
    co = _co(me.vertices, len(me.vertices))
    pos = np.zeros((size, size, 3), np.float32)
    cover = np.zeros((size, size), bool)
    for t in tris:
        p = uv[t]
        x0, y0 = np.maximum(np.floor(p.min(0)).astype(int), 0)
        x1, y1 = np.minimum(np.ceil(p.max(0)).astype(int) + 1, size)
        if x0 >= x1 or y0 >= y1:
            continue
        ys, xs = np.mgrid[y0:y1, x0:x1].astype(np.float32)
        (ax, ay), (bx, by), (cx, cy) = p
        den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(den) < 1e-9:
            continue
        l0 = ((by - cy) * (xs - cx) + (cx - bx) * (ys - cy)) / den
        l1 = ((cy - ay) * (xs - cx) + (ax - cx) * (ys - cy)) / den
        l2 = 1 - l0 - l1
        m = (l0 > -0.02) & (l1 > -0.02) & (l2 > -0.02)
        c = co[vi[t]]
        pos[y0:y1, x0:x1][m] = l0[m, None] * c[0] + l1[m, None] * c[1] + l2[m, None] * c[2]
        cover[y0:y1, x0:x1] |= m
    # 往外扩几个像素（贴图过滤、MIP 时岛边不发黑）
    for _ in range(4):
        g = cover.copy()
        for ax_, sh in ((0, 1), (0, -1), (1, 1), (1, -1)):
            src = np.roll(cover, sh, ax_) & ~g
            pos[src] = np.roll(pos, sh, ax_)[src]
            g |= src
        cover = g
    return pos, cover


def _blur(a, n=1):
    for _ in range(n):
        a = (a * 4 + np.roll(a, 1, 0) + np.roll(a, -1, 0) + np.roll(a, 1, 1) + np.roll(a, -1, 1)) / 8
    return a


def _load(path):
    img = bpy.data.images.load(path)
    w, h = img.size
    return img, np.array(img.pixels[:], np.float32).reshape(h, w, 4)


def _save(name, px, colorspace='sRGB'):
    h, w = px.shape[:2]
    img = bpy.data.images.new(name, w, h, alpha=True)
    img.pixels[:] = np.ascontiguousarray(px, np.float32).ravel()
    path = os.path.join(CACHE, name + ".png")
    img.filepath_raw = path
    img.file_format = 'PNG'
    img.save()
    bpy.data.images.remove(img)
    return _img(path, colorspace)


def _img(path, colorspace='sRGB'):
    """从磁盘载入的贴图（生成的图存进 .blend 再追加出来是空的，所以存完都重新载入）。"""
    img = bpy.data.images.load(path)
    img.colorspace_settings.name = colorspace
    return img


def bake_ao(obs, hide, size, dist=0.08):
    """用 Cycles 给 obs 里每块网格烘一张环境光遮蔽（只算 dist 米以内的遮挡），hide 里的不参与（睫毛、眉毛是透明贴图的
    薄片，当实心的算会在眼睛上压出黑块）。返回 {网格: size×size 的遮蔽（1 不挡、0 全挡），Blender 的像素顺序}。"""
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.cycles.device = 'CPU'
    sc.cycles.samples = 64
    if sc.world is None:
        sc.world = bpy.data.worlds.new("W")
    sc.world.light_settings.distance = dist
    for o in hide:
        o.hide_render = True
    out = {}
    for o in obs:
        img = bpy.data.images.new("ao_" + o.name, size, size, float_buffer=True)
        nodes = []
        for m in o.data.materials:
            n = m.node_tree.nodes.new('ShaderNodeTexImage')
            n.image = img
            m.node_tree.nodes.active = n
            nodes.append((m, n))
        bpy.ops.object.select_all(action='DESELECT')
        o.select_set(True)
        bpy.context.view_layer.objects.active = o
        bpy.ops.object.bake(type='AO', margin=8, use_clear=True)
        a = np.array(img.pixels[:], np.float32).reshape(size, size, 4)[..., 0]
        out[o] = _blur(a, 2)
        for m, n in nodes:
            m.node_tree.nodes.remove(n)
        bpy.data.images.remove(img)
    for o in hide:
        o.hide_render = False
    return out


def skin_textures(head, lm, data, ao):
    """皮肤：颜色、ORM（G 粗糙度）、法线三张，按头上每个像素的三维位置（相对眼睛、嘴、鼻子这些位置）画；
    颜色再乘上环境光遮蔽 ao（bake_ao）。返回 (颜色, ORM, 法线, 脸颊的平均颜色)。"""
    src, px = _load(os.path.join(data, "skins", "middleage_asian_male", "middleage_lightskinned_male_diffuse2.png"))
    size = px.shape[0]
    pos, cover = raster(head, size)
    x, y, z = pos[..., 0], pos[..., 1], pos[..., 2]
    ax = np.abs(x)
    E, M, C, N = lm["eye"], lm["mouth"], lm["chin"], lm["nose"]
    ex, mx = lm["eye_x"], lm["mouth_x"]
    rgb = px[..., :3]
    # 晒黑：脸颊的平均颜色拉到晒黑的本地人肤色（按通道缩放，明暗、斑点都留着）
    cheek = cover & (np.abs(ax - ex) < 0.012) & (np.abs(z - (E.z - 0.03)) < 0.01) & (y < E.y + 0.02)
    ref = rgb[cheek].mean(0)
    tan = np.array([0.75, 0.535, 0.4], np.float32)      # 比 m024 那张（0.81, 0.59, 0.44）深一档、偏暖
    k = cover[..., None] * (tan / ref - 1) + 1
    rgb *= k
    # 鼻头、颧骨、耳朵、额头晒得更红更深
    sun = (np.exp(-(((ax - ex - 0.004) / 0.016) ** 2 + ((z - E.z + 0.028) / 0.012) ** 2))
           + np.exp(-((x / 0.012) ** 2 + ((z - N.z) / 0.012) ** 2 + ((y - N.y) / 0.02) ** 2))
           + 0.6 * np.exp(-((x / 0.04) ** 2 + ((z - E.z - 0.05) / 0.02) ** 2))
           + 0.8 * _ss(ex + 0.045, ex + 0.06, ax) * (z > C.z)) * cover
    sun = np.clip(sun, 0, 1)
    rgb *= (1 + sun[..., None] * np.array([0.02, -0.06, -0.1], np.float32))
    # 胡茬：上唇、下巴、两腮，往耳朵、往脖子渐淡，嘴唇空出来。上沿：鼻子底下 → 嘴角外上方 → 斜着上到鬓角
    SN, wx = lm["subnasale"], lm["wing_x"]
    line = np.interp(ax, [0.0, wx, mx + 0.006, ex + 0.02, ex + 0.05],
                     [SN.z - 0.002, SN.z - 0.004, M.z + 0.012, E.z - 0.05, E.z - 0.02])
    beard = (_ss(line + 0.003, line - 0.004, z) * _ss(C.z - 0.065, C.z - 0.03, z)
             * _ss(E.y + 0.085, E.y + 0.07, y))
    lips = np.exp(-((x / (mx + 0.003)) ** 4 + ((z - M.z + 0.002) / 0.009) ** 2 + ((y - M.y) / 0.03) ** 2))
    beard = np.clip(beard - 1.3 * lips, 0, 1) * cover
    rng = np.random.default_rng(3)
    dots = rng.random((size, size)).astype(np.float32)
    hair = (dots > 0.55) * _blur(rng.random((size, size)).astype(np.float32), 1)
    kb = beard * (0.55 + 0.9 * hair)
    rgb[:] = rgb * (1 - 0.5 * kb[..., None]) + rgb * np.array([0.62, 0.7, 0.8], np.float32) * (0.5 * kb[..., None])
    # 眼下发暗（熬夜、心事）
    under = np.exp(-(((ax - ex) / 0.015) ** 2 + ((z - E.z + 0.016) / 0.006) ** 2)) * (y < E.y + 0.01) * cover
    rgb *= (1 - 0.1 * under[..., None] * np.array([1.0, 1.15, 1.1], np.float32))
    sm = rgb[cheek].mean(0)          # 给手对肤色用（遮蔽乘进去之前的）
    # 环境光遮蔽：暗部稍微偏红（皮肤透光）
    occ = np.where(cover, ao, 1.0)
    rgb *= (1 - 0.6 * (1 - occ))[..., None] ** np.array([0.85, 1.0, 1.1], np.float32)
    px[..., :3] = np.clip(rgb, 0, 1)
    color = _save("zhou_skin_color", px)
    # 法线：毛孔（细噪声）+ 胡茬根 + 法令纹 + 抬头纹 + 眼角细纹
    pore = _blur(rng.random((size, size)).astype(np.float32), 1) - 0.5
    h = pore * 0.3 + kb * hair * 0.5
    for s in (1, -1):
        # 法令纹：鼻翼外侧到嘴角外下方的一道沟，外侧（脸颊那边）鼓一点
        a = np.array([s * (lm["wing_x"] + 0.004), N.z + 0.002])
        b = np.array([s * (mx + 0.008), M.z - 0.008])
        p = np.stack([x, z], -1)
        u = np.clip(((p - a) @ (b - a)) / ((b - a) @ (b - a)), 0, 1)
        d = np.linalg.norm(p - (a + u[..., None] * (b - a)), axis=-1)
        side = np.sign((p - a) @ np.array([-(b - a)[1], (b - a)[0]]) * s)
        fold = (np.exp(-(d / 0.0016) ** 2) * -1.0 + np.exp(-((d - 0.003) / 0.003) ** 2) * 0.35 * (side > 0)) * (y < M.y + 0.03)
        h += fold * _ss(-0.1, 0.25, u) * _ss(1.15, 0.85, u)
        # 眼角细纹：外眼角往外几道放射状的浅纹
        dx, dz = x * s - (ex + 0.017), z - E.z
        r = np.hypot(dx, dz)
        ang = np.arctan2(dz, dx)
        h -= (0.35 * np.clip(np.sin(ang * 9) - 0.3, 0, 1) * np.exp(-((r - 0.009) / 0.005) ** 2) * (dx > -0.002)
              * (y < E.y + 0.02))
    # 抬头纹：眉毛上面三道横纹，中间深两边浅、跟着额头往下弯
    zz = z - (E.z + 0.022) + 3.0 * x * x
    h -= (0.25 * np.clip(np.sin(zz / 0.0095 * 2 * np.pi), 0, 1) ** 2 * _ss(0.0, 0.004, zz) * _ss(0.032, 0.022, zz)
          * _ss(0.05, 0.02, ax) * (y < E.y))
    h *= cover
    gx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) / 2
    gy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) / 2
    strength = 1.2
    n = np.stack([-gx * strength, -gy * strength, np.ones_like(h)], -1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    nm = np.ones((size, size, 4), np.float32)
    nm[..., :3] = n * 0.5 + 0.5
    normal = _save("zhou_skin_normal", nm, 'Non-Color')
    # 粗糙度：皮肤 0.55，额头、鼻子出点油，嘴唇润一点，胡茬那片糙
    tz = np.exp(-((x / 0.03) ** 2 + ((z - E.z - 0.04) / 0.03) ** 2)) + np.exp(-((x / 0.012) ** 2 + ((z - N.z - 0.012) / 0.025) ** 2))
    rough = 0.56 - 0.1 * np.clip(tz, 0, 1) - 0.12 * np.clip(lips, 0, 1) + 0.06 * beard
    orm = np.ones((size, size, 4), np.float32)
    orm[..., 1] = np.clip(rough, 0.3, 0.8)
    orm[..., 2] = 0.0
    orm_img = _save("zhou_skin_orm", orm, 'Non-Color')
    bpy.data.images.remove(src)
    return color, orm_img, normal, sm


def eye_texture(data, ao):
    """眼球：虹膜（偏红的棕）压成深棕，眼白压暗一点、去掉点红（太白了在镜子里像贴上去的）；
    乘上环境光遮蔽 ao（眼皮盖着的那一截暗下去，眼睛不再像贴上去的）。"""
    src, px = _load(os.path.join(data, "eyes", "materials", "brown_eye.png"))
    rgb = px[..., :3]
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    lum = 0.3 * r + 0.59 * g + 0.11 * b
    # 虹膜：两个瞳孔（最暗的两团）周围一圈里偏红的像素（眼白上的血丝不算）
    hgt, wid = lum.shape
    yy, xx = np.mgrid[0:hgt, 0:wid] / np.float32(wid)
    dark = lum < 0.08
    ring = np.zeros_like(lum)
    for half in (xx < 0.5, xx >= 0.5):
        m = dark & half & (yy < 0.85)
        cy, cx = yy[m].mean(), xx[m].mean()
        ring = np.maximum(ring, _ss(0.125, 0.105, np.hypot(yy - cy, xx - cx)))
    iris = np.clip((r - g - 0.03) * 8, 0, 1) * ring
    deep = np.array([0.30, 0.19, 0.12], np.float32) * np.clip(lum / 0.3, 0.2, 1.6)[..., None]
    rgb[:] = rgb * (1 - iris[..., None]) + deep * iris[..., None]
    white = (1 - iris) * _ss(0.45, 0.65, lum)
    grey = lum[..., None] * np.array([1.0, 0.98, 0.95], np.float32)
    rgb[:] = rgb * (1 - white[..., None]) + (0.5 * rgb + 0.5 * grey) * 0.86 * white[..., None]
    if ao.shape != rgb.shape[:2]:
        n = rgb.shape[0] // ao.shape[0]
        ao = np.kron(ao, np.ones((n, n), np.float32))
    rgb *= (1 - 0.8 * (1 - ao))[..., None]
    px[..., 3] = 1.0
    bpy.data.images.remove(src)
    return _save("zhou_eye_color", px)


def hair_texture(data):
    """短发：灰黄的发色压成黑的（按亮度留住发丝的明暗），透明度不动。"""
    src, px = _load(os.path.join(data, "hair", HAIR, HAIR + "_diffuse.png"))
    rgb = px[..., :3]
    lum = 0.3 * rgb[..., 0] + 0.59 * rgb[..., 1] + 0.11 * rgb[..., 2]
    rgb[:] = np.array([0.05, 0.043, 0.038], np.float32) * np.clip(lum / 0.25, 0.3, 2.5)[..., None]
    bpy.data.images.remove(src)
    return _save("zhou_hair_color", px)


def brow_texture(data, name):
    """眉毛：原图是浅淡的棕色细眉，加密（透明度放大）、压成黑的。"""
    src, px = _load(os.path.join(data, "eyebrows", name, name + ".png"))
    px[..., :3] = np.array([0.03, 0.025, 0.022], np.float32)
    px[..., 3] = np.clip(px[..., 3] * 1.8, 0, 1)
    bpy.data.images.remove(src)
    return _save("zhou_brow_color", px)


def _mat(name, color, normal=None, rough=0.55, alpha=False, orm=None):
    """glTF 能导出的材质：颜色贴图（带透明）、法线、ORM（G 粗糙度、B 金属度）。"""
    mat = bpy.data.materials.new(name)
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    t = nt.nodes.new('ShaderNodeTexImage')
    t.image = color
    nt.links.new(t.outputs["Color"], bsdf.inputs["Base Color"])
    if alpha:
        nt.links.new(t.outputs["Alpha"], bsdf.inputs["Alpha"])
    if normal is not None:
        tn = nt.nodes.new('ShaderNodeTexImage')
        tn.image = normal
        nm = nt.nodes.new('ShaderNodeNormalMap')
        nt.links.new(tn.outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = 0.0
    if orm is not None:
        to = nt.nodes.new('ShaderNodeTexImage')
        to.image = orm
        sep = nt.nodes.new('ShaderNodeSeparateColor')
        nt.links.new(to.outputs["Color"], sep.inputs["Color"])
        nt.links.new(sep.outputs["Green"], bsdf.inputs["Roughness"])
        nt.links.new(sep.outputs["Blue"], bsdf.inputs["Metallic"])
    return mat


# ============================================================================ 预览
def preview(head, out_dir):
    """三点光渲正面、四分之三侧面、闭眼、眼睛特写（看眨眼时睫毛跟不跟、有没有黑块）。"""
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_EEVEE'
    sc.render.resolution_x, sc.render.resolution_y = 700, 800
    sc.view_settings.view_transform = 'AgX'
    w = bpy.data.worlds.new("W")
    w.color = (0.03, 0.03, 0.035)
    sc.world = w
    c = V(head["eye_mid"])
    for name, loc, energy, col in (("Key", (0.9, -1.6, 0.7), 220, (1.0, 0.92, 0.8)),
                                   ("Fill", (-1.3, -1.0, 0.2), 60, (0.75, 0.85, 1.0)),
                                   ("Rim", (0.2, 1.4, 0.8), 120, (1.0, 1.0, 1.0))):
        ld = bpy.data.lights.new(name, 'AREA')
        ld.energy, ld.color, ld.size = energy, col, 0.6
        lo = bpy.data.objects.new(name, ld)
        sc.collection.objects.link(lo)
        lo.location = c + V(loc)
        lo.rotation_euler = (c - lo.location).to_track_quat('-Z', 'Y').to_euler()
    cd = bpy.data.cameras.new("Cam")
    cam = bpy.data.objects.new("Cam", cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    kb = head.data.shape_keys.key_blocks
    for nm, off, look, lens, blink in (("front", (0, -0.6, -0.02), (0, 0, -0.04), 70, 0),
                                       ("three", (0.38, -0.48, 0.0), (0, 0, -0.04), 70, 0),
                                       ("blink", (0.08, -0.3, 0.02), (0, 0, -0.01), 70, 1),
                                       ("eyes", (0.05, -0.3, 0.01), (0, 0, 0.0), 160, 0)):
        kb["AK_09_EyeBlinkLeft"].value = kb["AK_10_EyeBlinkRight"].value = blink
        cd.lens = lens
        cam.location = c + V(off)
        cam.rotation_euler = ((c + V(look)) - cam.location).to_track_quat('-Z', 'Y').to_euler()
        sc.render.filepath = os.path.join(out_dir, f"zhou_{nm}.png")
        bpy.ops.render.render(write_still=True)
    kb["AK_09_EyeBlinkLeft"].value = kb["AK_10_EyeBlinkRight"].value = 0


# ============================================================================ 入口
def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if not addon_utils.enable(EXT, default_set=True):
        raise SystemExit("gen_head_mpfb: 没装 MPFB，先跑 tools/fetch_mpfb.sh，并带上 BLENDER_USER_RESOURCES=blender/cache/mpfb/blender")
    mpfb = sys.modules[EXT]
    from importlib import import_module
    HumanService = import_module(EXT + ".services.humanservice").HumanService
    fs = import_module(EXT + ".services.faceservice")
    data = import_module(EXT + ".services.locationservice").LocationService.get_user_data()
    print("mpfb", mpfb.__name__, "data", data)

    st = HumanService.get_default_deserialization_settings()
    st["subdiv_levels"] = 0
    body = HumanService.deserialize_from_dict(dict(HUMAN), st)
    fs.FaceService.load_targets(body, load_microsoft_visemes=False, load_meta_visemes=True, load_arkit_faceunits=True)
    fs.FaceService.interpolate_targets(body)
    rig = body.parent
    bones = {b.name for b in rig.data.bones}
    neck = rig.matrix_world @ rig.data.bones["neck_01"].head_local
    rename = dict(VISEME_NAMES)
    rename.update({u: f"AK_{i + 1:02d}_{u[0].upper()}{u[1:]}" for i, u in enumerate(fs.ARKIT_FACEUNITS)})

    parts = {}
    for o in list(bpy.data.objects):
        if o.type != 'MESH':
            continue
        for m in list(o.modifiers):
            o.modifiers.remove(m)
        mw = o.matrix_world.copy()
        o.parent = None
        o.data.transform(mw, shape_keys=True)
        o.matrix_world = Matrix.Identity(4)
        bake_shapes(o, rename)
        o.data.uv_layers.active.name = "UVMap"
        for u in list(o.data.uv_layers)[1:]:
            o.data.uv_layers.remove(u)
        o.data.materials.clear()
        parts[o.name.split(".", 1)[1]] = o
    print("parts", sorted(parts))
    body, eyes, brows, lashes, hair = (parts[k] for k in ("body", "high-poly", BROW, "eyelashes01", HAIR))
    bpy.data.objects.remove(rig, do_unlink=True)

    # 眼睛、嘴、鼻子、下巴的位置（形态键位移最大的顶点；眼睛取眼球的中心）
    co = _co(eyes.data.vertices, len(eyes.data.vertices))
    eye = {s: V((co[co[:, 0] * s > 0].min(0) + co[co[:, 0] * s > 0].max(0)) / 2) for s in (1, -1)}
    lm = {"eye": (eye[1] + eye[-1]) / 2, "eye_x": eye[1].x}
    ml, mr = landmark(body, rename["mouthSmileLeft"], 1), landmark(body, rename["mouthSmileRight"], -1)
    lm["mouth"], lm["mouth_x"] = (ml + mr) / 2, (ml.x - mr.x) / 2
    wl, wr = landmark(body, rename["noseSneerLeft"], 1), landmark(body, rename["noseSneerRight"], -1)
    lm["wing_x"] = (wl.x - wr.x) / 2
    # 鼻尖：鼻子那一段中线上最靠前的点；鼻底（人中上端）：鼻尖和嘴之间中线上最靠里的点
    bco = _co(body.data.vertices, len(body.data.vertices))
    mid = bco[(np.abs(bco[:, 0]) < 0.004) & (bco[:, 1] < lm["eye"].y + 0.03)]
    tip = mid[(mid[:, 2] < lm["eye"].z - 0.01) & (mid[:, 2] > lm["mouth"].z + 0.01)]
    lm["nose"] = V(tip[np.argmin(tip[:, 1])])
    sn = mid[(mid[:, 2] < lm["nose"].z) & (mid[:, 2] > lm["mouth"].z + 0.006)]
    lm["subnasale"] = V(sn[np.argmax(sn[:, 1])])
    # 下巴底：嘴下面、脸前面那一截中线上最低的点
    ch = mid[(mid[:, 2] < lm["mouth"].z) & (mid[:, 2] > lm["mouth"].z - 0.08) & (mid[:, 1] < lm["mouth"].y + 0.025)]
    lm["chin"] = V(ch[np.argmin(ch[:, 2])])
    print("landmarks", {k: tuple(round(c, 4) for c in v) if isinstance(v, V) else round(v, 4) for k, v in lm.items()})

    # 身体只留头和脖子（帮助几何体、肩膀以下都不要；往下多留一截，gen_crew 按领口裁）
    body_g = body.vertex_groups["body"].index
    bottom = neck.z - 0.07
    keep_verts(body, lambda bm, v: v.co.z > bottom and abs(v.co.x) < 0.14
               and any(g == body_g and w > 0.5 for g, w in v[bm.verts.layers.deform.active].items()))
    # 眼球：去掉透明的角膜壳（UV 在贴图右下角那个透明的圆里）
    uv = eyes.data.uv_layers.active.data
    cornea = {v for p in eyes.data.polygons for v in p.vertices
              if (lambda u: u[0] > 0.85 and u[1] < 0.15)(np.mean([uv[i].uv[:] for i in p.loop_indices], 0))}
    keep_verts(eyes, lambda bm, v: v.index not in cornea)

    # 贴图、材质
    # 先放占位材质（名字前加 _，换成正式材质后正式的才叫 Crew_xxx，不会变成 Crew_xxx.001）
    for o, name in ((body, "Crew_Head"), (eyes, "Crew_Eyes"), (lashes, "Crew_Lashes"), (brows, "Crew_Brows"),
                    (hair, "Crew_Hair")):
        o.data.materials.append(bpy.data.materials.new("_" + name))
    # 环境光遮蔽（皮肤 2048、眼球 1024，和各自的贴图一样大）：头发算在遮挡里，睫毛、眉毛不算
    ao = bake_ao([body], [lashes, brows], 2048)
    ao.update(bake_ao([eyes], [lashes, brows], 1024))
    ao_skin, ao_eye = ao[body], ao[eyes]
    # 眉毛、睫毛、眼球并进头（形态键、顶点组按名字合）
    bpy.ops.object.select_all(action='DESELECT')
    for o in (body, eyes, lashes, brows):
        o.select_set(True)
    bpy.context.view_layer.objects.active = body
    bpy.ops.object.join()
    head = body
    head.name = head.data.name = "Zhou_Head"
    hair.name = hair.data.name = "Zhou_Hair"
    color, orm, normal, skin = skin_textures(head, lm, data, ao_skin)
    tex = lambda f, cs='sRGB': _img(os.path.join(data, f), cs)
    hn = os.path.join(data, "hair", HAIR, HAIR + "_normal.png")
    hair_normal = _img(hn, 'Non-Color') if os.path.exists(hn) else None
    for o in (head, hair):
        for s in o.material_slots:
            old = s.material
            s.material = {
                "Crew_Head": lambda: _mat("Crew_Head", color, normal, orm=orm),
                "Crew_Eyes": lambda: _mat("Crew_Eyes", eye_texture(data, ao_eye), rough=0.3),
                "Crew_Lashes": lambda: _mat("Crew_Lashes", tex("eyelashes/eyelashes01/eyelashes01.png"), rough=0.6, alpha=True),
                "Crew_Brows": lambda: _mat("Crew_Brows", brow_texture(data, BROW), rough=0.6, alpha=True),
                "Crew_Hair": lambda: _mat("Crew_Hair", hair_texture(data), hair_normal, rough=0.65, alpha=True),
            }[old.name[1:]]()
            bpy.data.materials.remove(old)
        map_groups(o, bones)
    head["eye_l"], head["eye_r"], head["eye_mid"] = eye[1][:], eye[-1][:], lm["eye"][:]
    head["skin"] = [float(c) for c in skin]
    print("head: %d 顶点，形态键 %d 个，材质 %s，顶点组 %s；头发 %d 顶点，顶点组 %s；脸颊 %s" % (
        len(head.data.vertices), len(head.data.shape_keys.key_blocks) - 1, [m.name for m in head.data.materials],
        [g.name for g in head.vertex_groups], len(hair.data.vertices), [g.name for g in hair.vertex_groups],
        np.round(skin, 3)))
    bpy.data.libraries.write(OUT, {head, hair}, path_remap='ABSOLUTE')
    print("exported", OUT)
    pv = _arg("--preview")
    if pv:
        preview(head, pv)


main()
