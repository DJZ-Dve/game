// 巨物「闷雷」的眼睛和寄生虫（M_GiantEye，贴图组 eyes），mask.A 分：
//   0 眼球：浑浊乳白、略带灰蓝（瞎的），隐约一圈虹膜和瞳孔的影子，很湿亮（清漆层锐高光）；
//     虹膜的位置按 BodyST 离眼睛中心（spec.EYE_S、EYE_THETA）多少米算，不依赖眼球的 UV 怎么展；
//   1 寄生桡足类（身体 + 两条卵带）：发白偏黄、半透明、黏糊糊——SSS 强、背光透、湿亮，近处叠软组织细沟。
shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_back, diffuse_burley, specular_schlick_ggx, sss_mode_skin;

#include "res://assets/shaders/giant_baked.gdshaderinc"

group_uniforms eye;
uniform vec4 eye_color : source_color = vec4(0.6, 0.64, 0.67, 1.0);
uniform vec4 iris_color : source_color = vec4(0.5, 0.56, 0.6, 1.0);
uniform vec4 pupil_color : source_color = vec4(0.36, 0.4, 0.43, 1.0);
uniform vec4 limbus_color : source_color = vec4(0.42, 0.42, 0.42, 1.0);
// 眼睛中心（BodyST：s、|θ/π|）、眼球露出的半径（米）、虹膜 / 瞳孔占半径的比例
uniform vec2 eye_center = vec2(0.075, 0.3556);
uniform float eye_radius = 0.38;
uniform vec2 iris_pupil = vec2(0.62, 0.24);
uniform float cloudiness : hint_range(0.0, 1.0) = 0.7;
uniform float eye_roughness : hint_range(0.0, 1.0) = 0.2;
uniform float eye_sss : hint_range(0.0, 1.0) = 0.25;

group_uniforms parasite;
uniform vec4 parasite_color : source_color = vec4(0.84, 0.8, 0.68, 1.0);
uniform vec4 parasite_deep : source_color = vec4(0.66, 0.6, 0.5, 1.0);
uniform float parasite_roughness : hint_range(0.0, 1.0) = 0.3;
uniform float parasite_sss : hint_range(0.0, 1.0) = 1.0;
uniform float crease_tile = 0.5;
uniform float crease_strength : hint_range(0.0, 2.0) = 0.6;

group_uniforms translucency;
uniform vec4 transmit_color : source_color = vec4(0.95, 0.75, 0.5, 1.0);
uniform float transmit_depth = 0.25;
uniform float transmit_boost : hint_range(0.0, 1.0) = 0.3;
uniform float backlight : hint_range(0.0, 2.0) = 0.6;

group_uniforms surface;
uniform float ao_albedo : hint_range(0.0, 1.0) = 0.6;
uniform float specular : hint_range(0.0, 1.0) = 0.55;
uniform float clearcoat_roughness : hint_range(0.0, 1.0) = 0.05;
group_uniforms;

void fragment() {
	vec4 m = texture(mask_tex, UV);
	vec3 nb = g_unpack(texture(normal_tex, UV).xy);
	nb.xy *= normal_strength;
	float par = smoothstep(0.3, 0.7, m.a);
	vec2 st = g_body(UV2);
	vec2 pm = g_body_m(st);
	vec4 nz = texture(noise_tex, UV * atlas_meters * 0.9);
	vec4 d = texture(detail_tex, UV * atlas_meters / crease_tile);

	// ---- 眼球：离眼睛中心的距离（半径归一）
	vec2 ec = g_body_m(vec2(eye_center.x, sign(st.y) * eye_center.y));
	float r = length(pm - ec) / eye_radius;
	float cloud = (nz.r - 0.5) * 0.4 + (nz.a - 0.5) * 0.3;
	vec3 eye = eye_color.rgb;
	float iris = 1.0 - smoothstep(iris_pupil.x - 0.15, iris_pupil.x + 0.1, r + cloud * 0.3);
	float pupil = 1.0 - smoothstep(iris_pupil.y - 0.1, iris_pupil.y + 0.08, r + cloud * 0.2);
	eye = mix(eye, iris_color.rgb, iris * (1.0 - cloudiness * 0.6));
	eye = mix(eye, pupil_color.rgb, pupil * (1.0 - cloudiness * 0.5));
	eye = mix(eye, limbus_color.rgb, smoothstep(0.75, 1.0, r) * 0.5);
	eye *= 1.0 + cloud * 0.35;

	// ---- 寄生虫
	vec3 pc = mix(parasite_color.rgb, parasite_deep.rgb, clamp(m.g + (1.0 - m.r) * 0.5, 0.0, 1.0));
	pc *= 1.0 + (nz.g - 0.5) * 0.3;

	vec3 col = mix(eye, pc, par);
	col *= mix(1.0, m.r, ao_albedo);

	float f = g_detail_fade(g_mpp(VERTEX, PROJECTION_MATRIX[1][1], VIEWPORT_SIZE.y), crease_tile / 14.0) * par;
	vec3 cn = g_unpack(d.rg);
	cn.xy *= crease_strength * f;

	vec3 dbg;
	if (g_debug(m, nb, col, r * 0.5, dbg)) {
		ALBEDO = vec3(0.0);
		EMISSION = dbg;
	} else {
		ALBEDO = col;
	}
	NORMAL_MAP = g_pack(g_blend(nb, cn));
	ROUGHNESS = mix(eye_roughness, parasite_roughness, par) + m.g * 0.15;
	SPECULAR = specular;
	AO = m.r;
	AO_LIGHT_AFFECT = 0.0;
	CLEARCOAT = 1.0;
	CLEARCOAT_ROUGHNESS = clearcoat_roughness + par * 0.1;
	SSS_STRENGTH = mix(eye_sss, parasite_sss, par);
	SSS_TRANSMITTANCE_COLOR = vec4(transmit_color.rgb, 1.0);
	SSS_TRANSMITTANCE_DEPTH = transmit_depth;
	SSS_TRANSMITTANCE_BOOST = transmit_boost * par;
	BACKLIGHT = transmit_color.rgb * backlight * par;
}
