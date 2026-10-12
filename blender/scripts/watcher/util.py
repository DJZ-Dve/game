"""部件共用的小工具（占位版用；精修的部件可以用也可以不用）。"""
import bpy
import bmesh

from watcher import spec


def smart_uv(ob, margin=0.02):
    """UV0 用 Blender 的智能投影先展一遍（之后 bakeutil.atlas_uv 会统一缩放、排进图集）。"""
    if spec.UV_MAIN not in ob.data.uv_layers:
        ob.data.uv_layers.new(name=spec.UV_MAIN)
    bpy.ops.object.select_all(action='DESELECT')
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(island_margin=margin)
    bpy.ops.object.mode_set(mode='OBJECT')
    ob.select_set(False)


def placeholder_high(lows, strength=0.04):
    """占位高模：低模细分 + 一层云噪声起伏（只为让烘焙流程跑通）。"""
    tex = bpy.data.textures.get("_w_noise") or bpy.data.textures.new("_w_noise", 'CLOUDS')
    tex.noise_scale = 0.5
    out = []
    for o in lows:
        h = o.copy()
        h.data = o.data.copy()
        h.name = o.name + "_high"
        bpy.context.scene.collection.objects.link(h)
        h.modifiers.new("sub", 'SUBSURF').levels = 1
        d = h.modifiers.new("disp", 'DISPLACE')
        d.texture = tex
        d.strength = strength
        out.append(h)
    return out


def remove(objs):
    for o in objs:
        bpy.data.objects.remove(o)
