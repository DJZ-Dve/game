// 巨物「大眼」的肉（M_WatcherFlesh，贴图组 flesh）：甲片之间露出来的关节膜、眼窝、上下眼睑、腹面虹吸口。
// 暗红褐、湿；mask.A = 1 是最湿的肉（眼睑内侧、结膜、眼窝口袋、虹吸口的喉）：更红、更亮、几乎镜面。
// 褶沟里更深更暗（凹槽 + AO），褶脊略发粉（凸棱）。皮下透一点红（SSS，皮肤模式），被背光照时薄处透光。
// 近处叠一层软组织细沟（giant_tissue_n），按每像素多少米淡出。片元 4 次采样：法线、mask、噪声、细沟。
shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_back, diffuse_burley, specular_schlick_ggx, sss_mode_skin;

#include "res://assets/shaders/giant_baked.gdshaderinc"

group_uniforms color;
uniform vec4 flesh_color : source_color = vec4(0.36, 0.15, 0.13, 1.0);
uniform vec4 deep_color : source_color = vec4(0.16, 0.04, 0.04, 1.0);
uniform vec4 wet_color : source_color = vec4(0.48, 0.1, 0.08, 1.0);
uniform vec4 ridge_color : source_color = vec4(0.55, 0.33, 0.3, 1.0);
uniform float ridge_pale : hint_range(0.0, 1.0) = 0.35;
uniform float mottle_tile = 2.5;
uniform float mottle_amount : hint_range(0.0, 1.0) = 0.35;

group_uniforms curvature;
uniform float ao_albedo : hint_range(0.0, 1.0) = 0.7;
uniform float cavity_dark : hint_range(0.0, 1.0) = 0.6;

group_uniforms detail;
uniform float tissue_tile = 0.6;
uniform float tissue_strength : hint_range(0.0, 2.0) = 0.5;

group_uniforms surface;
uniform float roughness : hint_range(0.0, 1.0) = 0.4;
uniform float roughness_wet : hint_range(0.0, 1.0) = 0.12;
uniform float specular : hint_range(0.0, 1.0) = 0.5;
uniform float sss : hint_range(0.0, 1.0) = 0.5;
uniform vec4 transmit_color : source_color = vec4(0.7, 0.12, 0.08, 1.0);
uniform float backlight : hint_range(0.0, 2.0) = 0.25;
group_uniforms;

void fragment() {
	vec4 m = texture(mask_tex, UV);
	vec3 nb = g_unpack(texture(normal_tex, UV).xy);
	nb.xy *= normal_strength;
	vec4 nz = texture(noise_tex, UV * atlas_meters / mottle_tile);
	float wet = smoothstep(0.3, 0.9, m.a);

	vec3 col = flesh_color.rgb * (1.0 + (nz.r - 0.5) * 2.0 * mottle_amount);
	col = mix(col, wet_color.rgb, wet);
	col = mix(col, ridge_color.rgb, m.b * ridge_pale * (1.0 - wet * 0.7));
	col = mix(col, deep_color.rgb, clamp(m.g * cavity_dark + (1.0 - m.r) * 0.4, 0.0, 1.0));
	col *= mix(1.0, m.r, ao_albedo);

	float mpp = g_mpp(VERTEX, PROJECTION_MATRIX[1][1], VIEWPORT_SIZE.y);
	float f = g_detail_fade(mpp, tissue_tile / 14.0);
	vec3 dn = g_unpack(texture(detail_tex, UV * atlas_meters / tissue_tile).rg);
	dn.xy *= tissue_strength * f * (1.0 - wet * 0.6);

	vec3 dbg;
	if (g_debug(m, nb, col, f, dbg)) {
		ALBEDO = vec3(0.0);
		EMISSION = dbg;
	} else {
		ALBEDO = col;
	}
	NORMAL_MAP = g_pack(g_blend(nb, dn));
	// 凹处更湿；成片地有水光
	float r = mix(roughness, roughness * 0.6, m.g) - smoothstep(0.55, 0.8, nz.g) * 0.12;
	ROUGHNESS = clamp(mix(r, roughness_wet, wet), 0.04, 1.0);
	SPECULAR = specular;
	AO = m.r;
	AO_LIGHT_AFFECT = 0.0;
	SSS_STRENGTH = sss;
	BACKLIGHT = min(transmit_color.rgb * backlight * 0.25 / max(col, vec3(0.02)), vec3(6.0)) * (0.4 + 0.6 * wet);
}
