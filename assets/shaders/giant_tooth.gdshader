// 巨物「闷雷」的牙（M_GiantTooth，贴图组 mouth，和嘴里共用一张图集）：尖牙鱼的獠牙——半透明发白，
// 牙尖更透（偏一点冷灰青），牙根发黄发褐；纵向细纹、裂纹在烘焙法线和凹槽里（凹槽染成褐色的污渍）。
// 牙根 / 牙尖怎么分：
//   牙根 = 烘焙 AO 低的地方（被牙床、唇包着）；
//   牙尖 = 低模曲率的棱边（顶点色 R，牙尖最尖），或者 mask.A 的渐变（tip_from_area：建模把牙的 A 从牙根 0.5 渐变到牙尖 1）。
// 透：屏幕空间 SSS（skin 模式，只有牙和眼睛用，屏幕上面积小）+ 背光透射（牙尖被灯从后面照时发亮）。
shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_back, diffuse_burley, specular_schlick_ggx, sss_mode_skin;

#include "res://assets/shaders/giant_baked.gdshaderinc"

group_uniforms color;
uniform vec4 enamel_color : source_color = vec4(0.86, 0.85, 0.8, 1.0);
uniform vec4 tip_color : source_color = vec4(0.66, 0.7, 0.72, 1.0);
uniform vec4 root_color : source_color = vec4(0.58, 0.45, 0.28, 1.0);
uniform vec4 stain_color : source_color = vec4(0.3, 0.2, 0.12, 1.0);
// 牙根按 AO 判断：AO 在这个区间里从「全是牙根」到「没有」
uniform vec2 root_ao = vec2(0.25, 0.75);
uniform bool tip_from_area = false;
uniform float ao_albedo : hint_range(0.0, 1.0) = 0.5;
uniform float variation : hint_range(0.0, 0.5) = 0.12;

group_uniforms translucency;
uniform float sss : hint_range(0.0, 1.0) = 0.5;
uniform vec4 transmit_color : source_color = vec4(0.95, 0.8, 0.6, 1.0);
uniform float transmit_depth = 0.6;
uniform float transmit_boost : hint_range(0.0, 1.0) = 0.15;
uniform float backlight : hint_range(0.0, 2.0) = 0.35;
uniform float edge_translucency : hint_range(0.0, 1.0) = 0.55;

group_uniforms surface;
uniform float roughness : hint_range(0.0, 1.0) = 0.3;
uniform float specular : hint_range(0.0, 1.0) = 0.55;
uniform float clearcoat : hint_range(0.0, 1.0) = 0.6;
uniform float clearcoat_roughness : hint_range(0.0, 1.0) = 0.1;
group_uniforms;

void fragment() {
	vec4 m = texture(mask_tex, UV);
	vec3 nb = g_unpack(texture(normal_tex, UV).xy);
	nb.xy *= normal_strength;
	vec4 nz = texture(noise_tex, UV * atlas_meters * 0.6);

	float root = 1.0 - smoothstep(root_ao.x, root_ao.y, m.r);
	float tip = tip_from_area ? smoothstep(0.65, 1.0, m.a) : smoothstep(0.15, 0.8, COLOR.r);
	tip *= 1.0 - root;

	vec3 col = enamel_color.rgb * (1.0 + (nz.r - 0.5) * variation * 2.0 + (COLOR.b - 0.5) * variation);
	col = mix(col, tip_color.rgb, tip);
	col = mix(col, root_color.rgb, root);
	// 裂纹、纵纹里的污渍
	col = mix(col, stain_color.rgb, clamp(m.g * 1.3, 0.0, 1.0) * (0.5 + 0.5 * root));
	col *= mix(1.0, m.r, ao_albedo);
	// 半透明的边：牙尖的轮廓附近光透过去了，反射回来的少，发灰发暗（看起来是「透」的）
	float nv = clamp(dot(NORMAL, VIEW), 0.0, 1.0);
	col *= 1.0 - edge_translucency * (0.35 + 0.65 * tip) * (1.0 - nv) * (1.0 - root);

	vec3 dbg;
	if (g_debug(m, nb, col, tip, dbg)) {
		ALBEDO = vec3(0.0);
		EMISSION = dbg;
	} else {
		ALBEDO = col;
	}
	NORMAL_MAP = g_pack(nb);
	ROUGHNESS = roughness + root * 0.2 + m.g * 0.2;
	SPECULAR = specular;
	AO = m.r;
	AO_LIGHT_AFFECT = 0.0;
	CLEARCOAT = clearcoat * (1.0 - root * 0.5);
	CLEARCOAT_ROUGHNESS = clearcoat_roughness;
	SSS_STRENGTH = sss * (0.4 + 0.6 * tip) * (1.0 - root * 0.7);
	SSS_TRANSMITTANCE_COLOR = vec4(transmit_color.rgb, 1.0);
	SSS_TRANSMITTANCE_DEPTH = transmit_depth * (0.5 + tip);
	SSS_TRANSMITTANCE_BOOST = transmit_boost;
	BACKLIGHT = transmit_color.rgb * backlight * (0.2 + 0.8 * tip) * (1.0 - root);
}
