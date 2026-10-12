// 巨物「闷雷」的鳍（M_GiantFin，贴图组 fins）：和皮同色（同一套 BodyST 大尺度颜色），鳍缘略深，
// 薄处（mask.A = 1）被背光照时微微透光（BACKLIGHT，便宜：不用屏幕空间 SSS、不查阴影贴图）。
// 鳍是闭合的厚片（低模有厚度），单面渲染。撕口、鳍条起伏都在烘焙法线里，不再镂空。
shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_back, diffuse_burley, specular_schlick_ggx;

#include "res://assets/shaders/giant_baked.gdshaderinc"
#include "res://assets/shaders/giant_body_color.gdshaderinc"

group_uniforms curvature;
uniform float ao_albedo : hint_range(0.0, 1.0) = 0.7;
uniform float cavity_dark : hint_range(0.0, 1.0) = 0.6;
uniform float ridge_pale : hint_range(0.0, 1.0) = 0.3;
uniform vec4 pale_color : source_color = vec4(0.5, 0.48, 0.45, 1.0);

group_uniforms edge;
// 薄处（鳍缘）压暗多少、发一点点红（血色从薄膜里透出来）
uniform float edge_dark : hint_range(0.0, 1.0) = 0.35;
uniform vec4 edge_tint : source_color = vec4(0.9, 0.78, 0.76, 1.0);
// 背光透射：颜色、强度（只在薄处；厚的鳍根不透）
uniform vec4 transmit_color : source_color = vec4(0.8, 0.42, 0.3, 1.0);
uniform float transmit : hint_range(0.0, 2.0) = 0.35;
uniform float transmit_base : hint_range(0.0, 1.0) = 0.08;

group_uniforms detail;
uniform float denticle_tile = 0.6;
uniform float denticle_strength : hint_range(0.0, 2.0) = 0.45;

group_uniforms surface;
uniform float roughness : hint_range(0.0, 1.0) = 0.6;
uniform float specular : hint_range(0.0, 1.0) = 0.35;
// 很淡的水光：成片地把粗糙度往下压（和皮一样，不用清漆层）
uniform float wet_sheen : hint_range(0.0, 1.0) = 0.25;
group_uniforms;

void vertex() {
	G_BODY_VERTEX
}

void fragment() {
	vec4 m = texture(mask_tex, UV);
	vec3 nb = g_unpack(texture(normal_tex, UV).xy);
	nb.xy *= normal_strength;
	float mpp = g_mpp(VERTEX, PROJECTION_MATRIX[1][1], VIEWPORT_SIZE.y);
	float thin = m.a;

	vec4 nz;
	vec3 col = g_body_color(nz);
	col = mix(col, col + (pale_color.rgb - col) * 0.5, m.b * ridge_pale);
	col *= mix(vec3(1.0), edge_tint.rgb * (1.0 - edge_dark), smoothstep(0.2, 0.9, thin));
	col *= 1.0 - max(m.g, COLOR.g * 0.3) * cavity_dark;
	col *= mix(1.0, m.r, ao_albedo);

	float f_den = g_detail_fade(mpp, denticle_tile / 40.0) * (1.0 - thin * 0.5);
	vec3 dn = g_unpack(texture(detail_tex, UV * atlas_meters / denticle_tile).rg);
	dn.xy *= denticle_strength * f_den;
	col *= 1.0 - (1.0 - dn.z) * 0.6 * f_den;

	vec3 dbg;
	if (g_debug(m, nb, col, f_den, dbg)) {
		ALBEDO = vec3(0.0);
		EMISSION = dbg;
	} else {
		ALBEDO = col;
	}
	NORMAL_MAP = g_pack(g_blend(nb, dn));
	ROUGHNESS = mix(mix(roughness, roughness - 0.15, m.g), 0.3, smoothstep(0.4, 0.7, nz.g) * wet_sheen);
	SPECULAR = specular;
	AO = m.r;
	AO_LIGHT_AFFECT = 0.0;
	// 背光：引擎会把它乘上反照率（鳍很暗），这里除掉，透过来的颜色只由 transmit_color 定
	// 鳍条（凸棱）厚、凹槽里薄：透光跟着鳍条一条条的，不是一整片
	float tr = transmit * mix(transmit_base, 1.0, smoothstep(0.1, 0.9, thin)) * (1.0 - m.b * 0.6) * (0.75 + 0.5 * nz.r);
	BACKLIGHT = min(transmit_color.rgb * tr * 0.25 / max(col, vec3(0.02)), vec3(8.0));
}
