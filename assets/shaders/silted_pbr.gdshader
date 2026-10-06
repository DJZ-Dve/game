// 给外部素材（岩石、沉船、沉木……）用：保留原本的 PBR 贴图，朝上的面盖一层海雪沉积的细泥。
shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_back, diffuse_burley, specular_schlick_ggx;

uniform sampler2D albedo_tex : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D normal_tex : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D orm_tex : hint_default_white, filter_linear_mipmap_anisotropic, repeat_enable;
uniform vec4 albedo_tint : source_color = vec4(1.0);
uniform bool has_orm = false;
uniform float base_roughness = 0.8;

uniform sampler2D silt_albedo : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform float silt_scale = 0.4;
uniform float silt_amount : hint_range(0.0, 1.0) = 0.6;
uniform vec4 silt_tint : source_color = vec4(0.72, 0.72, 0.68, 1.0);
uniform vec4 darken : source_color = vec4(0.7, 0.72, 0.72, 1.0);

varying vec3 wpos;
varying vec3 wnrm;

void vertex() {
	wpos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	wnrm = normalize((MODEL_MATRIX * vec4(NORMAL, 0.0)).xyz);
}

void fragment() {
	vec4 a = texture(albedo_tex, UV) * albedo_tint;
	vec3 orm = has_orm ? texture(orm_tex, UV).rgb : vec3(1.0, base_roughness, 0.0);
	NORMAL_MAP = texture(normal_tex, UV).rgb;

	// 沉积：朝上 + 一点噪声，用细砂贴图做颜色
	vec4 s = texture(silt_albedo, wpos.xz * silt_scale);
	float up = smoothstep(0.35, 0.85, normalize(wnrm).y);
	float silt = clamp(up * silt_amount + (s.r - 0.5) * 0.6 * up, 0.0, 1.0);

	ALBEDO = mix(a.rgb * darken.rgb, s.rgb * silt_tint.rgb, silt);
	ROUGHNESS = mix(orm.g, 0.95, silt);
	METALLIC = orm.b * (1.0 - silt);
	AO = orm.r;
	if (a.a < 0.5) {
		discard;
	}
}
