// 巨物「大眼」的桨（M_WatcherPaddle，贴图组 paddle）：三对苍白的桨状附肢——它的弱点，一眼要看得出是软的。
// mask.A = 软组织（关节膜、根部肉褶、叶片鳍条之间的膜）：偏粉、湿、半透明，被背光照时透出血色（BACKLIGHT），
//          鳍条（硬）在透光里是一条条暗的；
//   硬甲（根节、中节、叶片的桨骨和鳍条）：苍白的骨白略带灰，哑，凸棱（甲唇、后缘）更白，几道旧划痕在凹槽里。
// 贴图里的 AO 是高模上算的（paddle_high.py），只有细节自己的遮蔽。片元 4 次采样：法线、mask、噪声、细沟。
shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_back, diffuse_burley, specular_schlick_ggx, sss_mode_skin;

#include "res://assets/shaders/giant_baked.gdshaderinc"

group_uniforms color;
uniform vec4 hard_color : source_color = vec4(0.66, 0.62, 0.57, 1.0);
uniform vec4 soft_color : source_color = vec4(0.7, 0.47, 0.43, 1.0);
uniform vec4 deep_color : source_color = vec4(0.36, 0.2, 0.18, 1.0);
uniform vec4 ridge_color : source_color = vec4(0.78, 0.76, 0.72, 1.0);
uniform float ridge_pale : hint_range(0.0, 1.0) = 0.4;
uniform float mottle_tile = 2.0;
uniform float mottle_amount : hint_range(0.0, 1.0) = 0.3;

group_uniforms curvature;
uniform float ao_albedo : hint_range(0.0, 1.0) = 0.7;
uniform float cavity_dark : hint_range(0.0, 1.0) = 0.55;

group_uniforms detail;
uniform float tissue_tile = 0.5;
uniform float tissue_strength : hint_range(0.0, 2.0) = 0.4;

group_uniforms translucency;
uniform vec4 transmit_color : source_color = vec4(0.85, 0.3, 0.2, 1.0);
uniform float transmit : hint_range(0.0, 2.0) = 0.6;
uniform float transmit_hard : hint_range(0.0, 1.0) = 0.06;

group_uniforms surface;
uniform float roughness : hint_range(0.0, 1.0) = 0.55;
uniform float roughness_soft : hint_range(0.0, 1.0) = 0.28;
uniform float specular : hint_range(0.0, 1.0) = 0.45;
uniform float sss : hint_range(0.0, 1.0) = 0.6;
group_uniforms;

void fragment() {
	vec4 m = texture(mask_tex, UV);
	vec3 nb = g_unpack(texture(normal_tex, UV).xy);
	nb.xy *= normal_strength;
	vec4 nz = texture(noise_tex, UV * atlas_meters / mottle_tile);
	float soft = smoothstep(0.15, 0.85, m.a);

	vec3 col = mix(hard_color.rgb, soft_color.rgb, soft);
	col *= 1.0 + (nz.r - 0.5) * 2.0 * mottle_amount;
	col = mix(col, ridge_color.rgb, m.b * ridge_pale * (1.0 - soft * 0.6));
	col = mix(col, deep_color.rgb, clamp(m.g * cavity_dark, 0.0, 1.0));
	col *= mix(1.0, m.r, ao_albedo);

	float mpp = g_mpp(VERTEX, PROJECTION_MATRIX[1][1], VIEWPORT_SIZE.y);
	float f = g_detail_fade(mpp, tissue_tile / 14.0) * soft;
	vec3 dn = g_unpack(texture(detail_tex, UV * atlas_meters / tissue_tile).rg);
	dn.xy *= tissue_strength * f;

	vec3 dbg;
	if (g_debug(m, nb, col, f, dbg)) {
		ALBEDO = vec3(0.0);
		EMISSION = dbg;
	} else {
		ALBEDO = col;
	}
	NORMAL_MAP = g_pack(g_blend(nb, dn));
	ROUGHNESS = clamp(mix(roughness + (nz.a - 0.5) * 0.1, roughness_soft, soft) - m.g * 0.1, 0.05, 1.0);
	SPECULAR = specular;
	AO = m.r;
	AO_LIGHT_AFFECT = 0.0;
	SSS_STRENGTH = sss * mix(0.3, 1.0, soft);
	// 背光：引擎会乘上反照率，这里除掉，透过来的颜色只由 transmit_color 定
	float tr = transmit * mix(transmit_hard, 1.0, soft) * (0.8 + 0.4 * nz.g);
	BACKLIGHT = min(transmit_color.rgb * tr * 0.25 / max(col, vec3(0.02)), vec3(8.0));
}
