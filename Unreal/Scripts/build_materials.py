# 材质：把 Godot 版的材质（assets/materials/*.tres）搬进 UE。
# 1. 母材质：着色器逻辑写在 Unreal/Shaders/*.ush（从 .gdshader 移植），这里建成 UE 材质——一个 Custom 节点 #include 那个文件，
#    参数按 .ush 开头的参数表（@tex / @color / @float / @bool / @vec）建成同名的材质参数，连进 Custom 节点
# 2. 贴图：.tres 引用的贴图导进 /Game/Textures（按用途设 sRGB、法线压缩；法线图保持 OpenGL 约定，着色器里自己处理）
# 3. 材质实例：每个用到的 Godot 材质建一个同名实例（/Game/Materials/M_xxx），.tres 里的值原样填进去（颜色 sRGB → 线性）
# 4. 按材质槽名把实例套到 /Game/Models 下的静态网格上（槽名就是 Blender 里的材质名）
# 用法：UnrealEditor-Cmd.exe Guixu.uproject -run=pythonscript -script=Scripts/build_materials.py
import json
import os
import re
import struct
import zlib

import unreal

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
SHADERS = os.path.join(REPO, "Unreal", "Shaders")
MASTER_DIR = "/Game/Materials/Master"
MI_DIR = "/Game/Materials"
TEX_DIR = "/Game/Textures"
MODEL_GLBS = ["submarine_exterior", "submarine_cockpit", "seabed"]

AT = unreal.AssetToolsHelpers.get_asset_tools()
MEL = unreal.MaterialEditingLibrary
EAL = unreal.EditorAssetLibrary
report = {"errors": [], "masters": {}, "instances": {}, "textures": 0, "slots": 0, "unmatched_slots": []}


def log(msg):
    unreal.log(f"[materials] {msg}")


def srgb_to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


# ---------------------------------------------------------------- .ush 参数表

def read_params(ush):
    params = []
    with open(os.path.join(SHADERS, ush), encoding="utf-8") as f:
        for line in f:
            m = re.match(r"//\s*@(tex|color|float|bool|vec)\s+(\w+)\s*(.*)", line)
            if m:
                kind, name, rest = m.group(1), m.group(2), m.group(3).split()
                params.append({"kind": kind, "name": name, "args": rest})
    return params


# ---------------------------------------------------------------- 贴图

def write_png(path, w, h, rgba):
    raw = b"".join(b"\x00" + bytes(rgba) * w for _ in range(h))
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    data = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)) \
        + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(data)


def import_texture(src, dest_dir, name, role):
    """role：color（sRGB 颜色）/ linear（灰度、打包图）/ normal（法线，OpenGL 约定原样保留）"""
    path = f"{dest_dir}/{name}"
    if not EAL.does_asset_exist(path):
        task = unreal.AssetImportTask()
        task.set_editor_property("filename", src)
        task.set_editor_property("destination_path", dest_dir)
        task.set_editor_property("destination_name", name)
        task.set_editor_property("automated", True)
        task.set_editor_property("replace_existing", True)
        task.set_editor_property("save", False)
        AT.import_asset_tasks([task])
    tex = unreal.load_asset(path)
    if tex is None:
        raise RuntimeError(f"贴图导入失败：{src}")
    if role == "normal":
        tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_NORMALMAP)
        tex.set_editor_property("srgb", False)
        tex.set_editor_property("flip_green_channel", False)
        tex.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_WORLD_NORMAL_MAP)
    elif role == "linear":
        tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_DEFAULT)
        tex.set_editor_property("srgb", False)
    else:
        tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_DEFAULT)
        tex.set_editor_property("srgb", True)
    EAL.save_loaded_asset(tex, only_if_is_dirty=False)
    report["textures"] += 1
    return tex


def default_textures():
    """参数没给贴图时用的默认图（对应 Godot 的 hint_default_white / black / hint_normal）"""
    d = os.path.join(REPO, ".tmp", "ue", "default_tex")
    os.makedirs(d, exist_ok=True)
    out = {}
    for key, rgba, role in [("white_color", (255, 255, 255, 255), "color"), ("white_linear", (255, 255, 255, 255), "linear"),
                            ("black_linear", (0, 0, 0, 255), "linear"), ("flat_normal", (128, 128, 255, 255), "normal")]:
        p = os.path.join(d, f"T_Default_{key}.png")
        write_png(p, 4, 4, rgba)
        out[key] = import_texture(p, f"{TEX_DIR}/Defaults", f"T_Default_{key}", role)
    return out


def texture_asset_name(rel):
    base = os.path.splitext(os.path.basename(rel))[0]
    return "T_" + re.sub(r"[^A-Za-z0-9_]", "_", base)


def texture_dest_dir(rel):
    parts = rel.replace("\\", "/").split("/")
    # assets/third_party/ambientcg/DiamondPlate008A/xxx.jpg → /Game/Textures/ambientcg/DiamondPlate008A
    if parts[:2] == ["assets", "third_party"]:
        sub = parts[2:-1]
    else:
        sub = parts[1:-1]
    return TEX_DIR + "/" + "/".join(re.sub(r"[^A-Za-z0-9_]", "_", s) for s in sub)


_tex_cache = {}


def godot_texture(rel, role):
    if rel not in _tex_cache:
        _tex_cache[rel] = import_texture(os.path.join(REPO, rel), texture_dest_dir(rel), texture_asset_name(rel), role)
    return _tex_cache[rel]


# ---------------------------------------------------------------- 母材质

SAMPLER = {"color": unreal.MaterialSamplerType.SAMPLERTYPE_COLOR,
           "linear": unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR,
           "normal": unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL}
DEFAULT_TEX = {("color", "white"): "white_color", ("linear", "white"): "white_linear",
               ("linear", "black"): "black_linear", ("normal", "flat"): "flat_normal"}


def local_position_expr(mat, x, y):
    if hasattr(unreal, "MaterialExpressionLocalPosition"):
        return MEL.create_material_expression(mat, unreal.MaterialExpressionLocalPosition, x, y)
    wp = MEL.create_material_expression(mat, unreal.MaterialExpressionWorldPosition, x - 300, y)
    t = MEL.create_material_expression(mat, unreal.MaterialExpressionTransformPosition, x, y)
    t.set_editor_property("transform_source_type", unreal.MaterialPositionTransformSource.TRANSFORMPOSSOURCE_WORLD)
    t.set_editor_property("transform_type", unreal.MaterialPositionTransformSource.TRANSFORMPOSSOURCE_LOCAL)
    MEL.connect_material_expressions(wp, "", t, "")
    return t


ALL_OUTPUTS = ("base", "rough", "metal", "spec", "emis", "normal", "ao")


def build_master(name, ush, struct_name, fn, builtins, normal_code, defaults, translucent=False, description="",
                 outputs=ALL_OUTPUTS, domain=None, additive_unlit=False, unlit=False):
    """builtins：传给 HLSL 函数的内置输入（LocalPos / LocalNormal / VColor / UV0 / UV1），按函数参数顺序"""
    # 已经有了就清空节点重建（不删资产：材质实例、网格还引用着它）
    path = f"{MASTER_DIR}/{name}"
    if EAL.does_asset_exist(path):
        mat = unreal.load_asset(path)
        MEL.delete_all_material_expressions(mat)
    else:
        mat = AT.create_asset(name, MASTER_DIR, unreal.Material, unreal.MaterialFactoryNew())
    mat.set_editor_property("tangent_space_normal", False)
    if domain is not None:
        mat.set_editor_property("material_domain", domain)
        mat.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)  # 贴花只能用半透明 / 预乘 / 相乘
    else:
        # 用在 Nanite 网格上（不先标上，编辑器会边用边改、打一堆提示，打包时直接用不了）
        mat.set_editor_property("used_with_nanite", True)
    if additive_unlit:
        # 发光的东西（数码管）：不受光照、加色叠在后面的东西上
        mat.set_editor_property("blend_mode", unreal.BlendMode.BLEND_ADDITIVE)
        mat.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    elif unlit:
        # 自己发光的屏（声呐显像管）：不受光照
        mat.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    elif translucent and domain is None:
        mat.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
        mat.set_editor_property("translucency_lighting_mode", unreal.TranslucencyLightingMode.TLM_SURFACE)
    params = read_params(ush)
    texs = [p for p in params if p["kind"] == "tex"]
    vals = [p for p in params if p["kind"] != "tex"]

    lines = [f"{struct_name} P;"]
    for p in vals:
        rhs = p["name"] + (".rgb" if p["kind"] in ("color", "vec") else "")
        lines.append(f"P.{p['name']} = {rhs};")
    args = ["P"] + builtins + [a for p in texs for a in (p["name"], p["name"] + "Sampler")]
    lines.append(f"FGXSurface S = {fn}({', '.join(args)});")
    lines += ["Roughness = S.Roughness;", "Metallic = S.Metallic;", "Specular = S.Specular;", "Emissive = S.Emissive;",
              "AO = S.AO;", "Opacity = S.Opacity;", f"NormalWS = {normal_code};", "return S.BaseColor;"]
    code = "\n".join(lines)

    custom = MEL.create_material_expression(mat, unreal.MaterialExpressionCustom, 0, 0)
    custom.set_editor_property("code", code)
    custom.set_editor_property("description", description or fn)
    custom.set_editor_property("output_type", unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    custom.set_editor_property("include_file_paths", [f"/Guixu/{ush}"])
    inputs = []
    for n in [p["name"] for p in vals] + builtins + [p["name"] for p in texs]:
        ci = unreal.CustomInput()
        ci.set_editor_property("input_name", n)
        inputs.append(ci)
    custom.set_editor_property("inputs", inputs)
    outs = []
    for n, t in [("Roughness", "CMOT_FLOAT1"), ("Metallic", "CMOT_FLOAT1"), ("Specular", "CMOT_FLOAT1"), ("Emissive", "CMOT_FLOAT3"),
                 ("AO", "CMOT_FLOAT1"), ("Opacity", "CMOT_FLOAT1"), ("NormalWS", "CMOT_FLOAT3")]:
        co = unreal.CustomOutput()
        co.set_editor_property("output_name", n)
        co.set_editor_property("output_type", getattr(unreal.CustomMaterialOutputType, t))
        outs.append(co)
    custom.set_editor_property("additional_outputs", outs)

    y = -2000
    for p in vals:
        a = p["args"]
        if p["kind"] in ("float", "bool"):
            e = MEL.create_material_expression(mat, unreal.MaterialExpressionScalarParameter, -700, y)
            e.set_editor_property("default_value", float(a[0]))
        else:
            e = MEL.create_material_expression(mat, unreal.MaterialExpressionVectorParameter, -700, y)
            v = [float(x) for x in a[:3]]
            if p["kind"] == "color":
                v = [srgb_to_linear(c) for c in v]
            e.set_editor_property("default_value", unreal.LinearColor(v[0], v[1], v[2], 1.0))
        e.set_editor_property("parameter_name", p["name"])
        MEL.connect_material_expressions(e, "", custom, p["name"])
        y += 70
    for p in texs:
        role, dflt = p["args"][0], p["args"][1]
        e = MEL.create_material_expression(mat, unreal.MaterialExpressionTextureObjectParameter, -700, y)
        e.set_editor_property("parameter_name", p["name"])
        e.set_editor_property("texture", defaults[DEFAULT_TEX[(role, dflt)]])
        e.set_editor_property("sampler_type", SAMPLER[role])
        MEL.connect_material_expressions(e, "", custom, p["name"])
        y += 120

    by = 600
    for b in builtins:
        if b == "LocalPos":
            e = local_position_expr(mat, -400, by)
        elif b == "LocalNormal":
            vn = MEL.create_material_expression(mat, unreal.MaterialExpressionVertexNormalWS, -700, by)
            e = MEL.create_material_expression(mat, unreal.MaterialExpressionTransform, -400, by)
            e.set_editor_property("transform_source_type", unreal.MaterialVectorCoordTransformSource.TRANSFORMSOURCE_WORLD)
            e.set_editor_property("transform_type", unreal.MaterialVectorCoordTransform.TRANSFORM_LOCAL)
            MEL.connect_material_expressions(vn, "", e, "")
        elif b == "VColor":
            e = MEL.create_material_expression(mat, unreal.MaterialExpressionVertexColor, -400, by)
        elif b == "Time":
            e = MEL.create_material_expression(mat, unreal.MaterialExpressionTime, -400, by)
        elif b in ("UV0", "UV1"):
            e = MEL.create_material_expression(mat, unreal.MaterialExpressionTextureCoordinate, -400, by)
            e.set_editor_property("coordinate_index", int(b[-1]))
        else:
            raise RuntimeError(b)
        MEL.connect_material_expressions(e, "", custom, b)
        by += 120

    pins = {"base": ("", "MP_BASE_COLOR"), "rough": ("Roughness", "MP_ROUGHNESS"), "metal": ("Metallic", "MP_METALLIC"),
            "spec": ("Specular", "MP_SPECULAR"), "emis": ("Emissive", "MP_EMISSIVE_COLOR"), "normal": ("NormalWS", "MP_NORMAL"),
            "ao": ("AO", "MP_AMBIENT_OCCLUSION"), "opacity": ("Opacity", "MP_OPACITY")}
    outs_used = list(outputs) + (["opacity"] if (translucent or domain is not None) and not additive_unlit else [])
    if translucent and "ao" in outs_used:
        outs_used.remove("ao")
    for k in outs_used:
        pin, prop = pins[k]
        MEL.connect_material_property(custom, pin, getattr(unreal.MaterialProperty, prop))
    MEL.recompile_material(mat)
    EAL.save_loaded_asset(mat, only_if_is_dirty=False)
    report["masters"][name] = {"params": len(vals), "textures": len(texs)}
    log(f"母材质 {name}：{len(vals)} 个参数，{len(texs)} 张贴图")
    return mat, params


LOCAL_N = "normalize(TransformLocalVectorToWorld(Parameters, GX_DirFromGodot(S.Normal)))"
TANGENT_N = "normalize(mul(S.Normal, (MaterialFloat3x3)Parameters.TangentToWorld))"


# ---------------------------------------------------------------- .tres

def parse_value(v):
    v = v.strip()
    if v == "null":
        return None
    if v in ("true", "false"):
        return 1.0 if v == "true" else 0.0
    m = re.match(r"Color\(([^)]*)\)", v)
    if m:
        return ("color", [float(x) for x in m.group(1).split(",")])
    m = re.match(r"Vector3\(([^)]*)\)", v)
    if m:
        return ("vec", [float(x) for x in m.group(1).split(",")])
    m = re.match(r'ExtResource\("([^"]+)"\)', v)
    if m:
        return ("ext", m.group(1))
    try:
        return float(v)
    except ValueError:
        return ("raw", v)


def read_tres(name):
    with open(os.path.join(REPO, "assets", "materials", name + ".tres"), encoding="utf-8") as f:
        s = f.read()
    head = s.split("\n", 1)[0]
    kind = re.search(r'type="(\w+)"', head).group(1)
    ext = {m.group(3): (m.group(1), m.group(2)) for m in
           re.finditer(r'\[ext_resource type="(\w+)" path="res://([^"]+)" id="([^"]+)"\]', s)}
    props = {}
    for line in s.split("[resource]", 1)[1].splitlines():
        if " = " not in line:
            continue
        k, v = line.split(" = ", 1)
        props[k.strip().replace("shader_parameter/", "")] = parse_value(v)
    shader = None
    if kind == "ShaderMaterial":
        sid = props.get("shader")
        if isinstance(sid, tuple) and sid[0] == "ext":
            shader = os.path.basename(ext[sid[1]][1])
    return kind, shader, props, ext


def make_instance(name, master, params, values, ext):
    path = f"{MI_DIR}/{name}"
    if EAL.does_asset_exist(path):
        mi = unreal.load_asset(path)
        MEL.clear_all_material_instance_parameters(mi)
    else:
        mi = AT.create_asset(name, MI_DIR, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    MEL.set_material_instance_parent(mi, master)
    kinds = {p["name"]: p for p in params}
    for k, v in values.items():
        p = kinds.get(k)
        if p is None or v is None:
            continue
        if p["kind"] == "tex":
            if isinstance(v, tuple) and v[0] == "ext":
                rel = ext[v[1]][1]
                MEL.set_material_instance_texture_parameter_value(mi, k, godot_texture(rel, p["args"][0]))
        elif p["kind"] in ("float", "bool"):
            if isinstance(v, float):
                MEL.set_material_instance_scalar_parameter_value(mi, k, v)
        elif p["kind"] == "color" and isinstance(v, tuple) and v[0] == "color":
            c = [srgb_to_linear(x) for x in v[1][:3]]
            MEL.set_material_instance_vector_parameter_value(mi, k, unreal.LinearColor(c[0], c[1], c[2], 1.0))
        elif p["kind"] == "vec" and isinstance(v, tuple) and v[0] in ("vec", "color"):
            c = v[1]
            MEL.set_material_instance_vector_parameter_value(mi, k, unreal.LinearColor(c[0], c[1], c[2], 1.0))
    MEL.update_material_instance(mi)
    EAL.save_loaded_asset(mi, only_if_is_dirty=False)
    return mi


# 贴花（Godot 版 cockpit_props.gd 的 DECALS）：种类 → 贴图名、有没有 ORM、浓淡、是否改颜色（mix 0 = 只改粗糙度）
DECALS = {
    "Ring": {"tex": "ring", "alpha": 0.8}, "Burn": {"tex": "burn"}, "Tape": {"tex": "tape", "alpha": 0.85},
    "Polish": {"tex": "polish", "orm": True, "mix": 0.0}, "Grease": {"tex": "grease", "orm": True, "alpha": 0.8},
    "Scuff": {"tex": "scuff", "alpha": 0.8}, "BootL": {"tex": "boot_l", "orm": True, "alpha": 0.75},
    "BootR": {"tex": "boot_r", "orm": True, "alpha": 0.75}, "Puddle": {"tex": "puddle", "orm": True},
    "Hazard": {"tex": "hazard", "orm": True}, "Rust": {"tex": "rust", "alpha": 0.85}, "Streak": {"tex": "streak", "orm": True},
    "Hand": {"tex": "hand", "orm": True, "alpha": 0.85}, "TextC03": {"tex": "text_c03"}, "TextFire": {"tex": "text_fire"},
    "TextCool": {"tex": "text_cool"}, "TextFireWater": {"tex": "text_firewater"}, "TextReturn": {"tex": "text_return"},
    "TextAir": {"tex": "text_air", "alpha": 0.8},
}


def build_decals(defaults):
    dom = unreal.MaterialDomain.MD_DEFERRED_DECAL
    full = build_master("M_Decal", "Decal.ush", "FGXDecalParams", "GX_Decal", ["UV0"], "float3(0, 0, 1)", defaults,
                        description="贴花", outputs=("base", "rough", "metal"), domain=dom)
    rough = build_master("M_DecalRough", "Decal.ush", "FGXDecalParams", "GX_Decal", ["UV0"], "float3(0, 0, 1)", defaults,
                         description="贴花（只改粗糙度）", outputs=("rough", "metal"), domain=dom)
    for kind, c in DECALS.items():
        master, params = rough if c.get("mix", 1.0) < 0.5 else full
        name = f"MI_Decal_{kind}"
        path = f"/Game/Decals/{name}"
        if EAL.does_asset_exist(path):
            mi = unreal.load_asset(path)
            MEL.clear_all_material_instance_parameters(mi)
        else:
            mi = AT.create_asset(name, "/Game/Decals", unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
        MEL.set_material_instance_parent(mi, master)
        tex = import_texture(os.path.join(REPO, "assets", "textures", "decals", c["tex"] + ".png"), "/Game/Decals/Textures",
                             "T_Decal_" + c["tex"], "color")
        MEL.set_material_instance_texture_parameter_value(mi, "albedo", tex)
        if c.get("orm"):
            orm = import_texture(os.path.join(REPO, "assets", "textures", "decals", c["tex"] + "_orm.png"), "/Game/Decals/Textures",
                                 "T_Decal_" + c["tex"] + "_orm", "linear")
            MEL.set_material_instance_texture_parameter_value(mi, "orm", orm)
            MEL.set_material_instance_scalar_parameter_value(mi, "use_orm", 1.0)
        MEL.set_material_instance_scalar_parameter_value(mi, "modulate", c.get("alpha", 1.0))
        MEL.update_material_instance(mi)
        EAL.save_loaded_asset(mi, only_if_is_dirty=False)
    log(f"贴花材质 {len(DECALS)} 种")


def glb_material_names():
    names = set()
    for n in MODEL_GLBS:
        with open(os.path.join(REPO, "assets", "models", n + ".glb"), "rb") as f:
            f.read(12)
            clen, _ = struct.unpack("<II", f.read(8))
            g = json.loads(f.read(clen))
        names |= {m.get("name") for m in g.get("materials", [])}
    return sorted(names)


def main():
    defaults = default_textures()
    masters = {
        "worn_surface.gdshader": build_master("M_WornSurface", "WornSurface.ush", "FGXWornParams", "GX_WornSurface",
                                              ["LocalPos", "LocalNormal", "VColor"], LOCAL_N, defaults,
                                              description="worn_surface（Godot 版移植）"),
        "fabric.gdshader": build_master("M_Fabric", "Fabric.ush", "FGXFabricParams", "GX_Fabric",
                                        ["UV0", "UV1", "VColor"], TANGENT_N, defaults, description="布料"),
        "seabed.gdshader": build_master("M_Seabed", "Seabed.ush", "FGXSeabedParams", "GX_Seabed",
                                        ["LocalPos", "LocalNormal", "VColor"], LOCAL_N, defaults, description="海床"),
    }
    std_normal = f"P.uv1_triplanar > 0.5 ? {LOCAL_N} : {TANGENT_N}"
    std = build_master("M_Standard", "StandardSurface.ush", "FGXStandardParams", "GX_StandardSurface",
                       ["LocalPos", "LocalNormal", "UV0"], std_normal, defaults, description="Godot StandardMaterial3D")
    std_t = build_master("M_StandardTranslucent", "StandardSurface.ush", "FGXStandardParams", "GX_StandardSurface",
                         ["LocalPos", "LocalNormal", "UV0"], std_normal, defaults, translucent=True,
                         description="Godot StandardMaterial3D（透明）")

    instances = {}
    for name in glb_material_names():
        try:
            kind, shader, props, ext = read_tres(name)
            if kind == "StandardMaterial3D":
                vals = dict(props)
                col = props.get("albedo_color")
                if isinstance(col, tuple) and col[0] == "color" and len(col[1]) > 3:
                    vals["albedo_alpha"] = col[1][3]
                translucent = isinstance(props.get("transparency"), float) and props["transparency"] > 0
                master, params = std_t if translucent else std
            elif shader in masters:
                vals = props
                master, params = masters[shader]
            elif shader == "crt_sonar.gdshader":
                # 声呐屏先用一块发暗绿光的玻璃顶着，声呐画面以后搬（Godot 版 sonar_display.gd）
                vals = {"albedo_color": ("color", [0.02, 0.03, 0.025]), "roughness": 0.15, "emission_enabled": 1.0,
                        "emission": ("color", [0.035, 0.05, 0.04]), "emission_energy_multiplier": 2.4}
                master, params = std
            elif shader == "net_bag.gdshader":
                # 网兜先用实心的红色顶着，网眼以后搬
                vals = {"albedo_color": ("color", [0.75, 0.12, 0.04]), "roughness": 0.85}
                master, params = std
            else:
                raise RuntimeError(f"没有对应的母材质：{kind} {shader}")
            instances[name] = make_instance(name, master, params, vals, ext)
            report["instances"][name] = master.get_name()
        except Exception as e:
            report["errors"].append(f"{name}: {e}")
            unreal.log_error(f"[materials] {name}: {e}")
    log(f"材质实例 {len(instances)} 个，贴图 {report['textures']} 张")
    build_decals(defaults)
    build_master("M_SonarCRT", "Sonar.ush", "FGXSonarParams", "GX_Sonar", ["UV0", "Time"], "float3(0, 0, 1)", defaults,
                 description="声呐显像管", outputs=("emis",), unlit=True)
    build_master("M_SevenSeg", "SevenSeg.ush", "FGXSevenSegParams", "GX_SevenSeg", ["LocalPos"], "float3(0, 0, 1)", defaults,
                 description="数码管", outputs=("emis",), additive_unlit=True)

    for path in EAL.list_assets("/Game/Models", recursive=True, include_folder=False):
        sm = unreal.load_asset(path)
        if not isinstance(sm, unreal.StaticMesh):
            continue
        changed = False
        for i, slot in enumerate(sm.static_materials):
            sname = str(slot.material_slot_name)
            mi = instances.get(sname)
            if mi:
                sm.set_material(i, mi)
                changed = True
                report["slots"] += 1
            else:
                report["unmatched_slots"].append(f"{sm.get_name()}:{sname}")
        if changed:
            EAL.save_loaded_asset(sm, only_if_is_dirty=False)
    log(f"套上材质的槽 {report['slots']} 个，没对上的 {len(report['unmatched_slots'])} 个")

    out = os.path.join(REPO, ".tmp", "ue", "build_materials.json")
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    log(f"结果写到 {out}")


main()
