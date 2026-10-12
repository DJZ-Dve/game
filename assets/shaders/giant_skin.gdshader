// 巨物「闷雷」的外皮（M_GiantSkin，贴图组 skin）：格陵兰睡鲨的盾鳞皮——暗灰褐、哑光、粗糙，湿处一层很淡的水光。
// 形状全靠烘焙贴图（法线 + AO / 凹槽 / 凸棱），mask.A 分区：0 正常皮，0.5 发白发灰的旧疤，1 暗红的生肉（新伤）。
// 叠两层便宜的东西：
//   近处：盾鳞细节法线（giant_denticle_n，疤和生肉上没有），按每像素多少米淡出；
//   远处：BodyST 上的背深腹浅、斑驳、零星深色斑点（giant_body_color）。
// 鳃裂里（BodyST 上鳃区的凹槽）透一点暗红。没有屏幕空间 SSS（盾鳞皮厚，不透光，也省掉整屏一次模糊）。
// 片元里 4 次采样：法线、mask、盾鳞、噪声（大尺度颜色在顶点里算，见 giant_body_color）。没有清漆层。
shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_back, diffuse_burley, specular_schlick_ggx;

#include "res://assets/shaders/giant_baked.gdshaderinc"
#include "res://assets/shaders/giant_body_color.gdshaderinc"

group_uniforms curvature;
// 烘焙 AO 乘进反照率多少（探照灯下也看得出褶和缝）
uniform float ao_albedo : hint_range(0.0, 1.0) = 0.7;
uniform float cavity_dark : hint_range(0.0, 1.0) = 0.65;
// 凸棱发白（盾鳞磨掉了尖、旧皮褶的棱）
uniform float ridge_pale : hint_range(0.0, 1.0) = 0.35;
// 低模曲率（顶点色）的补充：大的凹处再暗一点
uniform float vcol_cavity : hint_range(0.0, 1.0) = 0.3;

group_uniforms detail;
// 盾鳞：一张细节图的边长（米）；图里约 40×40 片
uniform float denticle_tile = 0.7;
uniform float denticle_strength : hint_range(0.0, 2.0) = 0.5;

group_uniforms scar;
uniform vec4 scar_color : source_color = vec4(0.43, 0.415, 0.395, 1.0);
uniform float scar_amount : hint_range(0.0, 1.0) = 0.85;
uniform vec4 flesh_color : source_color = vec4(0.3, 0.07, 0.06, 1.0);
uniform vec4 flesh_deep_color : source_color = vec4(0.12, 0.02, 0.025, 1.0);

group_uniforms gill;
// 鳃区（BodyST）：s 范围、|θ/π| 中心和半宽；鳃裂里的凹槽透出暗红
uniform vec2 gill_s = vec2(0.222, 0.298);
uniform vec2 gill_theta = vec2(0.567, 0.13);
uniform vec4 gill_color : source_color = vec4(0.28, 0.06, 0.06, 1.0);

group_uniforms surface;
uniform float roughness : hint_range(0.0, 1.0) = 0.62;
// 凹处更湿
uniform float roughness_cavity : hint_range(0.0, 1.0) = 0.42;
uniform float specular : hint_range(0.0, 1.0) = 0.35;
// 很淡的水光：不用清漆层（省一层高光），成片地把粗糙度往下压一点，凹处多一点
uniform float wet_sheen : hint_range(0.0, 1.0) = 0.25;
// 盾鳞的「砂纸」光泽：掠射角上一层柔的亮边（Godot 的 RIM，很便宜）
uniform float denticle_sheen : hint_range(0.0, 1.0) = 0.35;
uniform float sheen_tint : hint_range(0.0, 1.0) = 0.4;
group_uniforms;

varying float v_gill;

void vertex() {
	G_BODY_VERTEX
	// 鳃区（BodyST 上的一块）
	vec2 st = g_body(UV2);
	float g = smoothstep(gill_s.x - 0.01, gill_s.x + 0.01, st.x) * (1.0 - smoothstep(gill_s.y - 0.01, gill_s.y + 0.01, st.x));
	v_gill = g * (1.0 - smoothstep(gill_theta.y * 0.6, gill_theta.y, abs(abs(st.y) - gill_theta.x)));
}

void fragment() {
	vec4 m = texture(mask_tex, UV);
	vec3 nb = g_unpack(texture(normal_tex, UV).xy);
	nb.xy *= normal_strength;
	float mpp = g_mpp(VERTEX, PROJECTION_MATRIX[1][1], VIEWPORT_SIZE.y);

	float area = m.a;
	float scar = clamp(1.0 - abs(area - 0.5) * 2.5, 0.0, 1.0) * scar_amount;
	float flesh = smoothstep(0.72, 0.95, area);
	float skin = 1.0 - max(scar, flesh);

	// ---- 颜色
	vec4 nz;
	vec3 col = g_body_color(nz);
	float cav = max(m.g, COLOR.g * vcol_cavity);
	// 鳃裂
	float gill = v_gill;
	col = mix(col, scar_color.rgb * mix(0.85, 1.08, nz.a), scar);
	vec3 fl = mix(flesh_color.rgb, flesh_deep_color.rgb, clamp(m.g * 1.5 + (1.0 - m.r), 0.0, 1.0));
	col = mix(col, fl, flesh);
	col = mix(col, col + (scar_color.rgb - col) * 0.5, m.b * ridge_pale * skin);
	col = mix(col, gill_color.rgb * 0.6, gill * smoothstep(0.15, 0.6, m.g));
	col *= 1.0 - cav * cavity_dark * (1.0 - flesh * 0.5);
	col *= mix(1.0, m.r, ao_albedo);

	// ---- 法线：烘焙 + 盾鳞（疤和生肉上没有盾鳞——疤组织是光的，生肉的起伏在烘焙里）
	float f_det = g_detail_fade(mpp, denticle_tile / 40.0);
	vec2 d1 = texture(detail_tex, UV * atlas_meters / denticle_tile).rg;
	vec2 dxy = (d1 - 0.5) * (2.0 * denticle_strength * f_det * skin);
	vec3 n = normalize(vec3(nb.xy + dxy, nb.z));
	float f_den = f_det * skin;
	// 盾鳞的缝里一点暗（近处）
	col *= 1.0 - dot(dxy, dxy) * 0.5;

	vec3 dbg;
	if (g_debug(m, nb, col, f_den, dbg)) {
		ALBEDO = vec3(0.0);
		EMISSION = dbg;
	} else {
		ALBEDO = col;
	}
	NORMAL_MAP = g_pack(n);
	float wet = smoothstep(0.4, 0.7, nz.g) * wet_sheen;
	ROUGHNESS = mix(mix(roughness, roughness_cavity, cav), 0.3, max(max(flesh, scar * 0.3), wet));
	SPECULAR = specular;
	AO = m.r;
	AO_LIGHT_AFFECT = 0.0;
	RIM = denticle_sheen * skin;
	RIM_TINT = sheen_tint;
}
