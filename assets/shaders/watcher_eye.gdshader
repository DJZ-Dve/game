// 巨物「大眼」的眼球（M_WatcherEye，贴图组 eye）。外面还有一层透明角膜（M_WatcherCornea，单独的面），高光主要在那层。
// mask.A：1 虹膜 / 0 巩膜。
//   巩膜：暗红、湿，凹槽里（血管沟）更深；
//   虹膜：橙红，纤维（凸棱）发亮、隐窝（凹槽）发暗；瞳孔边往外一圈「领圈」偏金，根部到角膜缘一圈暗环；
//   竖瞳：按 assets/textures/watcher/eye_iris.json 的位置在 UV 里画（虹膜是一个圆岛，正投影，瞳孔竖直 = Godot 的 V 方向），
//     大小用 instance uniform `pupil`（0 一条缝 → 1 张成大椭圆），每只大眼自己控制（watcher.gd 里
//     set_instance_shader_parameter("pupil", …)）；模型上那道竖瞳凹槽是最窄时的样子。
shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_back, diffuse_burley, specular_schlick_ggx, sss_mode_skin;

#include "res://assets/shaders/giant_baked.gdshaderinc"

// 瞳孔张开程度（0 缝 → 1 大椭圆）；眼睛自己发一点光（凝视时用，0 = 不发光）
instance uniform float pupil : hint_range(0.0, 1.0) = 0.15;
instance uniform float glow : hint_range(0.0, 1.0) = 0.0;

group_uniforms iris_uv;
// eye_iris.json：center_uv_godot、r_root_uv、r_limbus_uv、pupil_groove_half_len_uv / half_width_uv
uniform vec2 iris_center = vec2(0.25756, 0.74228);
uniform float r_root = 0.23973;
uniform float r_limbus = 0.2571;
uniform vec2 slit_half = vec2(0.02524, 0.16403);
// 张到最大时瞳孔的半宽、半高（UV）
uniform vec2 open_half = vec2(0.12, 0.18);
uniform float collarette = 0.34;

group_uniforms color;
uniform vec4 sclera_color : source_color = vec4(0.24, 0.035, 0.03, 1.0);
uniform vec4 vessel_color : source_color = vec4(0.09, 0.008, 0.012, 1.0);
uniform vec4 iris_color : source_color = vec4(0.62, 0.11, 0.035, 1.0);
uniform vec4 fiber_color : source_color = vec4(0.85, 0.32, 0.09, 1.0);
uniform vec4 collar_color : source_color = vec4(0.8, 0.45, 0.12, 1.0);
uniform vec4 crypt_color : source_color = vec4(0.16, 0.025, 0.015, 1.0);
uniform vec4 limbus_color : source_color = vec4(0.06, 0.01, 0.01, 1.0);
uniform vec4 pupil_color : source_color = vec4(0.006, 0.003, 0.003, 1.0);
uniform vec4 glow_color : source_color = vec4(1.0, 0.25, 0.06, 1.0);
uniform float glow_energy = 2.0;

group_uniforms surface;
uniform float ao_albedo : hint_range(0.0, 1.0) = 0.6;
uniform float roughness_iris : hint_range(0.0, 1.0) = 0.5;
uniform float roughness_sclera : hint_range(0.0, 1.0) = 0.22;
uniform float specular : hint_range(0.0, 1.0) = 0.5;
uniform float sss : hint_range(0.0, 1.0) = 0.35;
group_uniforms;

void fragment() {
	vec4 m = texture(mask_tex, UV);
	vec3 nb = g_unpack(texture(normal_tex, UV).xy);
	nb.xy *= normal_strength;
	vec4 nz = texture(noise_tex, UV * atlas_meters / 1.5);
	float iris = smoothstep(0.3, 0.7, m.a);

	// ---- 虹膜岛里的坐标
	vec2 d = UV - iris_center;
	float r = length(d);
	vec2 ph = mix(slit_half, open_half, pupil);
	float pe = length(d / ph);                        // < 1 在瞳孔里
	float pu = 1.0 - smoothstep(0.9, 1.05, pe);
	// 从瞳孔边（0）到虹膜根（1）
	float t = clamp((r - ph.x * (1.0 - pupil * 0.3)) / max(r_root - ph.x, 1e-3), 0.0, 1.0);
	t = mix(t, clamp((pe - 1.0) / 3.0, 0.0, 1.0), 0.35);

	vec3 ic = iris_color.rgb * (0.85 + 0.3 * nz.r);
	ic = mix(ic, collar_color.rgb, smoothstep(0.08, 0.0, abs(t - collarette)) * 0.55);
	ic = mix(ic, fiber_color.rgb, m.b * 0.8);
	ic = mix(ic, crypt_color.rgb, smoothstep(0.1, 0.6, m.g));
	ic = mix(ic, limbus_color.rgb, smoothstep(r_root * 0.88, r_limbus, r) * 0.85);
	// 瞳孔边一圈更深的缘
	ic *= 1.0 - smoothstep(1.6, 1.0, pe) * 0.45;
	ic = mix(ic, pupil_color.rgb, pu);

	vec3 sc = mix(sclera_color.rgb * (0.85 + 0.3 * nz.r), vessel_color.rgb, smoothstep(0.15, 0.7, m.g));
	sc = mix(sc, sclera_color.rgb * 1.4, m.b * 0.3);

	vec3 col = mix(sc, ic, iris);
	col *= mix(1.0, m.r, ao_albedo);

	vec3 dbg;
	if (g_debug(m, nb, col, pe * 0.25, dbg)) {
		ALBEDO = vec3(0.0);
		EMISSION = dbg;
	} else {
		ALBEDO = col;
		// 凝视时：虹膜从里往外微微发光（瞳孔不亮），纤维亮、隐窝暗
		EMISSION = glow_color.rgb * glow * glow_energy * iris * (1.0 - pu) * (0.4 + 0.8 * m.b) * (1.0 - m.g * 0.8)
			* (1.0 - smoothstep(r_root * 0.8, r_root, r));
	}
	NORMAL_MAP = g_pack(nb);
	ROUGHNESS = mix(roughness_sclera, roughness_iris, iris * (1.0 - pu));
	SPECULAR = specular;
	AO = m.r;
	AO_LIGHT_AFFECT = 0.0;
	SSS_STRENGTH = sss * (1.0 - pu);
}
