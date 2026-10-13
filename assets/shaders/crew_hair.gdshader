// 船员的头发（发片，blender/scripts/gen_head_vitruvian.py 的 build_hair）：贴图 R 每根发丝的明暗、G 根部压暗、A 透明度；
// 顶点色 R 每片随机的明暗、B 离头皮多远（贴头皮的里层暗一点）；
// alpha 剪裁 + alpha 转覆盖（MSAA 下发丝边缘不锯齿），高光沿发丝方向拉长（各向异性），逆光时透一点
shader_type spatial;
render_mode cull_disabled, diffuse_burley, specular_schlick_ggx;

uniform sampler2D hair_tex : hint_default_black, filter_linear_mipmap_anisotropic, repeat_disable;
uniform vec3 hair_color : source_color = vec3(0.03, 0.026, 0.024);
uniform float scissor : hint_range(0.05, 0.9) = 0.3;

void fragment() {
	vec4 t = texture(hair_tex, UV);
	vec3 c = hair_color * mix(0.65, 1.3, t.r) * mix(0.45, 1.0, t.g) * mix(0.8, 1.2, COLOR.r) * mix(0.7, 1.0, COLOR.b);
	ALBEDO = c;
	ALPHA = t.a;
	ALPHA_SCISSOR_THRESHOLD = scissor;
	ALPHA_ANTIALIASING_EDGE = 0.25;
	ROUGHNESS = 0.52 + 0.1 * (COLOR.r - 0.5);
	SPECULAR = 0.35;
	ANISOTROPY = 0.75;
	ANISOTROPY_FLOW = vec2(0.0, 1.0);
	BACKLIGHT = c * 0.6;
	AO = mix(0.55, 1.0, t.g);
	AO_LIGHT_AFFECT = 0.4;
}
