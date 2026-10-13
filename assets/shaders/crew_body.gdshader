// 船员的身体（工装）：贴图的 alpha 是皮肤遮罩（露出来的手），手的颜色乘 skin_tint 跟脸的肤色对上（scripts/crew_look.gd）
shader_type spatial;
render_mode diffuse_burley, specular_schlick_ggx;

uniform sampler2D albedo_tex : source_color, filter_linear_mipmap_anisotropic;
uniform sampler2D normal_tex : hint_normal, filter_linear_mipmap_anisotropic;
uniform vec3 skin_tint = vec3(1.0);

void fragment() {
	vec4 t = texture(albedo_tex, UV);
	float skin = t.a;
	ALBEDO = mix(t.rgb, t.rgb * skin_tint, skin);
	NORMAL_MAP = texture(normal_tex, UV).rgb;
	ROUGHNESS = mix(0.85, 0.5, skin);
	SPECULAR = mix(0.3, 0.45, skin);
	SSS_STRENGTH = skin * 0.3;
}
