// 巨物「闷雷」嘴里的肉（M_GiantMouth，贴图组 mouth）：尖牙鱼的黑嘴——黑紫色、很湿，衬得牙特别显眼。
// 牙床、上颚、牙槽、口底、喉咙、颊膜都用它；mask.A = 1 的地方是牙（牙用 M_GiantTooth，这里只用来在牙根附近
// 让牙床发一点暗红）。凸棱（上颚的横褶、牙床的棱）是深紫灰，凹槽、喉咙（AO）往纯黑走。
// 湿：底层粗糙度低 + 整片清漆层（锐的高光），近处叠一层软组织细沟（giant_tissue_n）。
shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_back, diffuse_burley, specular_schlick_ggx;

#include "res://assets/shaders/giant_baked.gdshaderinc"

group_uniforms color;
uniform vec4 flesh_color : source_color = vec4(0.1, 0.06, 0.095, 1.0);
uniform vec4 ridge_color : source_color = vec4(0.19, 0.13, 0.18, 1.0);
uniform vec4 deep_color : source_color = vec4(0.03, 0.015, 0.03, 1.0);
// 牙根周围的牙床（mask.A 往外渗的一圈，靠贴图的过滤和 mip 自然出来）
uniform vec4 gum_color : source_color = vec4(0.27, 0.075, 0.1, 1.0);
uniform float gum_amount : hint_range(0.0, 1.0) = 0.6;
uniform float ao_albedo : hint_range(0.0, 1.0) = 0.85;
uniform float variation : hint_range(0.0, 1.0) = 0.35;

group_uniforms detail;
uniform float crease_tile = 1.4;
uniform float crease_strength : hint_range(0.0, 2.0) = 0.7;

group_uniforms surface;
uniform float roughness : hint_range(0.0, 1.0) = 0.38;
uniform float specular : hint_range(0.0, 1.0) = 0.5;
uniform float clearcoat : hint_range(0.0, 1.0) = 1.0;
uniform float clearcoat_roughness : hint_range(0.0, 1.0) = 0.12;
group_uniforms;

void fragment() {
	vec4 m = texture(mask_tex, UV);
	vec3 nb = g_unpack(texture(normal_tex, UV).xy);
	nb.xy *= normal_strength;
	float mpp = g_mpp(VERTEX, PROJECTION_MATRIX[1][1], VIEWPORT_SIZE.y);
	vec2 uvm = UV * atlas_meters;
	vec4 d = texture(detail_tex, uvm / crease_tile);
	vec4 nz = texture(noise_tex, g_body_m(g_body(UV2)) / 7.0);

	vec3 col = flesh_color.rgb * (1.0 + (nz.r - 0.5) * variation * 2.5);
	col = mix(col, ridge_color.rgb, smoothstep(0.1, 0.7, m.b));
	float gum = smoothstep(0.02, 0.4, m.a) * gum_amount;
	col = mix(col, gum_color.rgb, gum);
	float deep = clamp(m.g + (1.0 - m.r) * 0.6, 0.0, 1.0);
	col = mix(col, deep_color.rgb, deep);
	col *= mix(1.0, m.r * m.r, ao_albedo);

	float f = g_detail_fade(mpp, crease_tile / 14.0);
	vec3 cn = g_unpack(d.rg);
	cn.xy *= crease_strength * f;
	col *= 1.0 - (1.0 - cn.z) * 0.8;

	vec3 dbg;
	if (g_debug(m, nb, col, f, dbg)) {
		ALBEDO = vec3(0.0);
		EMISSION = dbg;
	} else {
		ALBEDO = col;
	}
	NORMAL_MAP = g_pack(g_blend(nb, cn));
	ROUGHNESS = roughness * mix(0.8, 1.2, nz.g) + m.b * 0.1;
	SPECULAR = specular;
	AO = m.r;
	AO_LIGHT_AFFECT = 0.0;
	CLEARCOAT = clearcoat;
	CLEARCOAT_ROUGHNESS = clearcoat_roughness;
}
