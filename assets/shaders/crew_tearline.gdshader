// 泪线（Vitruvian 的 Tearline 网格）：眼睑和眼球交界处那条湿的、带点粉的细带子，按顶点 alpha 淡出
shader_type spatial;
render_mode blend_mix, depth_draw_never, cull_back, specular_schlick_ggx;

uniform vec3 tint : source_color = vec3(0.72, 0.52, 0.5);
uniform float opacity : hint_range(0.0, 1.0) = 0.55;

void fragment() {
	ALBEDO = tint;
	ALPHA = clamp(COLOR.a * opacity, 0.0, 1.0);
	ROUGHNESS = 0.06;
	SPECULAR = 0.6;
}
