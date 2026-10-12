// 巨物「大眼」的甲壳（M_WatcherShell，贴图组 shell）：漆黑的几丁质，像鲎、大王具足虫的背甲——
// 大面是黑里透一点深琥珀褐（几丁质本身的颜色，成片深浅不一），外面一层很薄的蜡质表皮（弱清漆层，探照灯下一条柔的高光）；
// mask.A = 1 的刺尖、0.5～1 的甲缘是磨掉表皮露出来的灰白（哑、粗）；凸棱也略发白；缝里（凹槽）积一点灰褐的细泥。
// 形状全在烘焙贴图里（blender/scripts/watcher/shell_high.py），片元 3 次采样：法线、mask、噪声。
// 噪声按 UV0 × 图集米数铺：每片甲各自一块（甲片本来就是一片片的），蒙皮动起来不会游。
shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_back, diffuse_burley, specular_schlick_ggx;

#include "res://assets/shaders/giant_baked.gdshaderinc"

group_uniforms color;
uniform vec4 base_color : source_color = vec4(0.11, 0.1, 0.105, 1.0);
// 几丁质的琥珀褐底（成片地透出来，甲片中间多、缘边少）
uniform vec4 amber_color : source_color = vec4(0.22, 0.14, 0.085, 1.0);
uniform float amber_amount : hint_range(0.0, 1.0) = 0.55;
// 斑驳的尺度（米）
uniform float mottle_tile = 4.0;
// 磨掉表皮的灰白（刺尖、甲缘）
uniform vec4 worn_color : source_color = vec4(0.42, 0.4, 0.36, 1.0);
uniform float worn_amount : hint_range(0.0, 1.0) = 0.8;
uniform float ridge_pale : hint_range(0.0, 1.0) = 0.25;
// 缝里的细泥
uniform vec4 silt_color : source_color = vec4(0.36, 0.34, 0.3, 1.0);
uniform float silt_amount : hint_range(0.0, 1.0) = 0.45;

group_uniforms curvature;
uniform float ao_albedo : hint_range(0.0, 1.0) = 0.6;
uniform float cavity_dark : hint_range(0.0, 1.0) = 0.5;

group_uniforms surface;
uniform float roughness : hint_range(0.0, 1.0) = 0.45;
uniform float roughness_worn : hint_range(0.0, 1.0) = 0.75;
uniform float specular : hint_range(0.0, 1.0) = 0.5;
// 蜡质表皮：弱清漆层（磨掉的地方、泥里没有）
uniform float clearcoat : hint_range(0.0, 1.0) = 0.45;
uniform float clearcoat_roughness : hint_range(0.0, 1.0) = 0.3;
group_uniforms;

void fragment() {
	vec4 m = texture(mask_tex, UV);
	vec3 nb = g_unpack(texture(normal_tex, UV).xy);
	nb.xy *= normal_strength;
	vec4 nz = texture(noise_tex, UV * atlas_meters / mottle_tile);

	float worn = clamp(smoothstep(0.55, 0.95, m.a) * worn_amount + m.b * ridge_pale, 0.0, 1.0);
	float silt = smoothstep(0.25, 0.8, m.g) * silt_amount * (0.55 + 0.9 * nz.g);
	silt = clamp(silt, 0.0, 1.0) * (1.0 - worn);

	vec3 col = mix(base_color.rgb, amber_color.rgb, smoothstep(0.3, 0.75, nz.r) * amber_amount * (1.0 - m.b));
	col *= 0.85 + 0.3 * nz.a;
	col = mix(col, worn_color.rgb * (0.8 + 0.4 * nz.a), worn);
	col = mix(col, silt_color.rgb * (0.8 + 0.3 * nz.b), silt);
	col *= 1.0 - m.g * cavity_dark * (1.0 - silt * 0.6);
	col *= mix(1.0, m.r, ao_albedo);

	vec3 dbg;
	if (g_debug(m, nb, col, 1.0, dbg)) {
		ALBEDO = vec3(0.0);
		EMISSION = dbg;
	} else {
		ALBEDO = col;
	}
	NORMAL_MAP = g_pack(nb);
	ROUGHNESS = clamp(mix(roughness + (nz.a - 0.5) * 0.15, roughness_worn, max(worn, silt)), 0.0, 1.0);
	SPECULAR = specular;
	AO = m.r;
	AO_LIGHT_AFFECT = 0.0;
	CLEARCOAT = clearcoat * (1.0 - worn) * (1.0 - silt) * (0.7 + 0.6 * nz.g);
	CLEARCOAT_ROUGHNESS = clearcoat_roughness;
}
