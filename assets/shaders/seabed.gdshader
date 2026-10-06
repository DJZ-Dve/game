// 海床：泥沙/细砂按噪声混合，陡坡露出岩石，凹处积泥更暗。世界坐标三平面映射。
shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_back, diffuse_burley, specular_schlick_ggx;

uniform sampler2D sand_albedo : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D sand_normal : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D sand_arm : hint_default_white, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D mud_albedo : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D mud_normal : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D rock_albedo : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D rock_normal : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;

uniform float sand_scale = 0.35;
uniform float mud_scale = 0.22;
uniform float rock_scale = 0.12;
uniform vec4 tint : source_color = vec4(0.78, 0.8, 0.78, 1.0);
uniform float slope_rock_start : hint_range(0.0, 1.0) = 0.62;
uniform float slope_rock_end : hint_range(0.0, 1.0) = 0.42;
uniform float normal_strength = 0.8;

varying vec3 wpos;
varying vec3 wnrm;
varying vec4 wear;

void vertex() {
	wpos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	wnrm = normalize((MODEL_MATRIX * vec4(NORMAL, 0.0)).xyz);
	wear = COLOR;
}

vec3 weights(vec3 n) {
	vec3 w = pow(abs(n), vec3(6.0));
	return w / (w.x + w.y + w.z + 1e-5);
}

vec4 tri(sampler2D t, vec3 p, vec3 w) {
	return texture(t, p.zy) * w.x + texture(t, p.xz) * w.y + texture(t, p.xy) * w.z;
}

vec3 tri_n(sampler2D t, vec3 p, vec3 n, vec3 w, float s) {
	vec3 tx = texture(t, p.zy).xyz * 2.0 - 1.0;
	vec3 ty = texture(t, p.xz).xyz * 2.0 - 1.0;
	vec3 tz = texture(t, p.xy).xyz * 2.0 - 1.0;
	tx.xy *= s; ty.xy *= s; tz.xy *= s;
	tx = vec3(tx.xy + n.zy, abs(tx.z) * n.x);
	ty = vec3(ty.xy + n.xz, abs(ty.z) * n.y);
	tz = vec3(tz.xy + n.xy, abs(tz.z) * n.z);
	return normalize(tx.zyx * w.x + ty.xzy * w.y + tz.xyz * w.z);
}

void fragment() {
	vec3 n = normalize(wnrm);
	vec3 w = weights(n);
	vec4 sand = tri(sand_albedo, wpos * sand_scale, w);
	vec4 sarm = tri(sand_arm, wpos * sand_scale, w);
	vec4 mud = tri(mud_albedo, wpos * mud_scale, w);
	vec4 rock = tri(rock_albedo, wpos * rock_scale, w);

	// 大块泥斑：用低频的泥贴图亮度当噪声
	float blot = tri(mud_albedo, wpos * 0.017, w).r;
	float mud_mask = smoothstep(0.35, 0.6, blot + wear.g * 0.5);
	float rock_mask = 1.0 - smoothstep(slope_rock_end, slope_rock_start, n.y);
	rock_mask = clamp(rock_mask + wear.r * 0.8, 0.0, 1.0);

	vec3 col = mix(sand.rgb, mud.rgb * 0.9, mud_mask);
	col = mix(col, rock.rgb * 0.8, rock_mask);
	col *= tint.rgb * (1.0 - wear.g * 0.35);

	vec3 nn = tri_n(sand_normal, wpos * sand_scale, n, w, normal_strength);
	vec3 nm = tri_n(mud_normal, wpos * mud_scale, n, w, normal_strength);
	vec3 nr = tri_n(rock_normal, wpos * rock_scale, n, w, normal_strength * 1.3);
	nn = normalize(mix(mix(nn, nm, mud_mask), nr, rock_mask));

	ALBEDO = col;
	ROUGHNESS = mix(sarm.g, 0.9, mud_mask);
	METALLIC = 0.0;
	AO = sarm.r;
	NORMAL = normalize((VIEW_MATRIX * vec4(nn, 0.0)).xyz);
}
