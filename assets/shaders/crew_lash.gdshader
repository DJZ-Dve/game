// 睫毛：每根一条细带子（UV 的 u 横跨、v 从根到梢），中间实、两边虚，梢上更细更淡；alpha 剪裁 + alpha 转覆盖
shader_type spatial;
render_mode cull_disabled, diffuse_burley, specular_schlick_ggx, depth_prepass_alpha;

uniform vec3 lash_color : source_color = vec3(0.02, 0.016, 0.014);
uniform float density : hint_range(0.0, 1.5) = 1.0;

void fragment() {
	float across = abs(UV.x * 2.0 - 1.0);
	float a = (1.0 - across * across) * mix(1.0, 0.55, UV.y) * density;
	ALBEDO = lash_color;
	ALPHA = clamp(a * 1.4, 0.0, 1.0);
	ALPHA_SCISSOR_THRESHOLD = 0.35;
	ALPHA_ANTIALIASING_EDGE = 0.3;
	ROUGHNESS = 0.55;
	SPECULAR = 0.35;
}
