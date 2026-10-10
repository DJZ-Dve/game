"""剧情里的几张老照片：用游戏自己的模型在 Blender 里拍，再做旧（黑白 / 发黄、颗粒、暗角、划痕、褪色的边）。
输出 assets/textures/story/：
- old_photo.png    办事处墙上：民国时候的照相馆合影——穿西装的沈家人站在小圆几旁边（就是沈渡那张脸，“我祖父”）
- desk_photo.png   办事处写字台玻璃板底下：一九五八年的镇海号，靠在码头上
- crew_photo.png   宿舍桌上：一九八六年冬天，周海生第一次跟艇出海回来，站在潜艇甲板上

先生成 npc_shen.glb、crew_body.glb、submarine_exterior.glb，再：
    Blender -b --factory-startup --python blender/scripts/render_photos.py
"""
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Vector as V

sys.path.insert(0, os.path.dirname(__file__))
from lib import frame  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "assets", "textures", "story")
MODELS = os.path.join(ROOT, "assets", "models")
PH = os.path.join(ROOT, "assets", "third_party", "polyhaven", "models")


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    try:
        sc.render.engine = 'BLENDER_EEVEE'
    except TypeError:
        sc.render.engine = 'BLENDER_EEVEE_NEXT'
    sc.render.film_transparent = False
    w = bpy.data.worlds.new("W")
    sc.world = w
    w.color = (0.3, 0.3, 0.3)
    return sc


def import_glb(path, action=None, frame_no=1):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    if action:
        arm = next((o for o in new if o.type == 'ARMATURE'), None)
        if arm and action in bpy.data.actions:
            arm.animation_data_create()
            arm.animation_data.action = bpy.data.actions[action]
            bpy.context.scene.frame_set(frame_no)
    return new


def plane(name, size, loc, rot, color, rough=0.9):
    bpy.ops.mesh.primitive_plane_add(size=1.0, location=loc, rotation=rot)
    ob = bpy.context.active_object
    ob.name = name
    ob.scale = (size[0], size[1], 1)
    m = bpy.data.materials.new(name)
    bsdf = m.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*color, 1)
    bsdf.inputs["Roughness"].default_value = rough
    ob.data.materials.append(m)
    return ob


def area_light(name, loc, target, energy, size, color=(1, 1, 1)):
    ld = bpy.data.lights.new(name, 'AREA')
    ld.energy, ld.size, ld.color = energy, size, color
    ob = bpy.data.objects.new(name, ld)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = loc
    ob.rotation_euler = (V(target) - V(loc)).to_track_quat('-Z', 'Y').to_euler()
    return ob


def camera(loc, target, lens):
    cd = bpy.data.cameras.new("Cam")
    cd.lens = lens
    cam = bpy.data.objects.new("Cam", cd)
    bpy.context.scene.collection.objects.link(cam)
    cam.location = loc
    cam.rotation_euler = (V(target) - V(loc)).to_track_quat('-Z', 'Y').to_euler()
    bpy.context.scene.camera = cam
    return cam


def render(name, res):
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = res
    path = os.path.join(OUT, f"_{name}_raw.png")
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    return path


def age(raw, name, tone=(1.08, 0.93, 0.74), seed=1, contrast=1.25, fade_amt=0.12, blur=1, scratches=3):
    """做旧：转黑白（或发黄）、提一点对比、轻微模糊（老镜头不锐）、颗粒、暗角、几道划痕、边上褪色发白。"""
    img = bpy.data.images.load(raw)
    w, h = img.size
    px = np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4)[..., :3]
    g = px @ np.array([0.3, 0.59, 0.11], np.float32)
    g = np.clip((g - 0.5) * contrast + 0.5, 0, 1)
    for _ in range(blur):
        g = (g + np.roll(g, 1, 0) + np.roll(g, -1, 0) + np.roll(g, 1, 1) + np.roll(g, -1, 1)) / 5
    rng = np.random.default_rng(seed)
    g = g + rng.normal(0, 0.035, g.shape).astype(np.float32)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    r = np.hypot((xx - w / 2) / (w / 2), (yy - h / 2) / (h / 2))
    g *= 1 - 0.45 * np.clip(r - 0.55, 0, 1) ** 1.5
    for _ in range(scratches):   # 划痕：细的亮线
        x0 = rng.uniform(0, w)
        ang = rng.uniform(-0.3, 0.3)
        y0, y1 = sorted(rng.uniform(0, h, 2))
        ys = np.arange(int(y0), int(y1))
        xs = (x0 + (ys - y0) * ang).astype(int)
        ok = (xs >= 0) & (xs < w)
        g[ys[ok], xs[ok]] = np.minimum(g[ys[ok], xs[ok]] + 0.12, 1.0)
    edge = np.clip((r - 0.85) * 3, 0, 1)
    g = g * (1 - fade_amt) + fade_amt * 0.9 + edge * 0.15
    rgb = np.clip(np.stack([g * tone[0], g * tone[1], g * tone[2]], -1), 0, 1)
    out = np.concatenate([rgb, np.ones((h, w, 1), np.float32)], -1)
    im = bpy.data.images.new(name, w, h, alpha=True)
    im.pixels[:] = out.ravel()
    im.filepath_raw = os.path.join(OUT, f"{name}.png")
    im.file_format = 'PNG'
    im.save()
    os.remove(raw)
    print("photo", im.filepath_raw)


# ============================================================================ 三张照片
def old_photo():
    """照相馆里：画着亭台的布景（这里就是一块灰调子的背景布）、一只小圆几放着青花瓷瓶，沈家人穿着西装站在旁边。"""
    reset()
    import_glb(os.path.join(MODELS, "npc_shen.glb"), "stand", 40)
    # 角色面朝 +Y：背景布在 -Y，相机在 +Y
    plane("Backdrop", (4, 3), (0, -1.4, 1.4), (math.radians(90), 0, 0), (0.22, 0.21, 0.2))
    plane("Floor", (4, 4), (0, 0, 0), (0, 0, 0), (0.35, 0.32, 0.28))
    bpy.ops.mesh.primitive_cylinder_add(radius=0.28, depth=0.04, location=(0.62, -0.2, 0.78))
    bpy.ops.mesh.primitive_cylinder_add(radius=0.04, depth=0.76, location=(0.62, -0.2, 0.38))
    import_glb(os.path.join(PH, "antique_ceramic_vase_01", "antique_ceramic_vase_01_2k.gltf"))
    vase = [o for o in bpy.data.objects if o.name.startswith("antique_ceramic_vase")][0]
    vase.location = (0.62, -0.2, 0.8)
    vase.scale = (0.8, 0.8, 0.8)
    area_light("Key", (-1.8, 1.6, 2.6), (0, 0, 1.4), 500, 2.0, (1.0, 0.95, 0.88))
    area_light("Fill", (2.0, 2.0, 1.5), (0, 0, 1.2), 90, 3.0)
    camera((0.25, 3.0, 1.4), (0.25, 0, 1.2), 60)
    age(render("old_photo", (900, 1200)), "old_photo", seed=3)


def desk_photo():
    """一九五八年：镇海号靠在码头上，艇上站着几个人影（太远了，看不清脸）。"""
    reset()
    import_glb(os.path.join(MODELS, "submarine_exterior.glb"))
    plane("Sea", (200, 200), (0, 0, 0.25), (0, 0, 0), (0.2, 0.22, 0.22), 0.15)
    plane("Pier", (6, 30), (-4.5, -3, 0.6), (0, 0, 0), (0.3, 0.3, 0.29))
    bpy.context.scene.world.color = (0.75, 0.75, 0.73)
    area_light("Sky", (10, -10, 20), (0, -3, 0), 5000, 30, (1.0, 0.98, 0.95))
    camera((-14, 8, 4.0), (0, -3.0, 1.0), 40)
    age(render("desk_photo", (1200, 840)), "desk_photo", tone=(1.05, 0.97, 0.85), seed=5, fade_amt=0.18)


def crew_photo():
    """一九八六年冬：周海生（二十岁）穿着作业服站在潜艇甲板上，背后是围壳。"""
    reset()
    import_glb(os.path.join(MODELS, "submarine_exterior.glb"))
    plane("Sea", (200, 200), (0, 0, 0.25), (0, 0, 0), (0.2, 0.22, 0.22), 0.2)
    import_glb(os.path.join(MODELS, "crew_body.glb"), "idle", 50)
    arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
    arm.location = (0.0, 1.0, 1.62)
    arm.rotation_euler = (0, 0, math.radians(-20))
    bpy.context.scene.world.color = (0.7, 0.72, 0.74)
    area_light("Sky", (-6, 8, 14), (0, 0, 1), 7000, 25)
    camera((-1.6, 5.2, 3.0), (0.0, 0.5, 2.35), 45)
    age(render("crew_photo", (1000, 750)), "crew_photo", tone=(1.0, 1.0, 1.0), seed=7, contrast=1.35)


os.makedirs(OUT, exist_ok=True)
old_photo()
desk_photo()
crew_photo()
