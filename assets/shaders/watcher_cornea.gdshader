// 巨物「大眼」的角膜（M_WatcherCornea）：眼球外面一层透明的鼓包（低模单独的面，UV 和虹膜岛重合，不用 eye 的贴图）。
// 正面几乎透明，掠射角上按菲涅尔变不透明一些（湿亮的一层膜），高光很锐。轻微发浑：一层很淡的乳红（巨物老了）。
// 透明物体：预乘 alpha（高光不跟着 alpha 变淡，正面也有锐利的反光点），不写深度（不挡后面的虹膜），单面。
shader_type spatial;
render_mode blend_premul_alpha, depth_draw_never, cull_back, diffuse_burley, specular_schlick_ggx;

uniform vec4 tint : source_color = vec4(0.5, 0.2, 0.17, 1.0);
uniform float haze : hint_range(0.0, 1.0) = 0.03;
uniform float fresnel_alpha : hint_range(0.0, 1.0) = 0.22;
uniform float roughness : hint_range(0.0, 1.0) = 0.03;
uniform float specular : hint_range(0.0, 1.0) = 0.7;

void fragment() {
	float fr = pow(1.0 - clamp(dot(NORMAL, VIEW), 0.0, 1.0), 5.0);
	float a = clamp(haze + fr * fresnel_alpha, 0.0, 1.0);
	ALBEDO = tint.rgb * 0.3 * a;
	ALPHA = a;
	ROUGHNESS = roughness;
	SPECULAR = specular;
	METALLIC = 0.0;
}
