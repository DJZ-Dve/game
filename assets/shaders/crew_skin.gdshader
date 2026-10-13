// 船员的脸（scripts/crew_look.gd 设参数，贴图见 blender/scripts/gen_head_vitruvian.py）：
// 两张反照率（浅、深肤色）按 melanin 插值，冷暖、红润调色；凹度 / 粗糙度 / 油光（T 区粗糙度低一点）；扫描的法线上再叠一层平铺的毛孔；
// 胡茬、头皮发茬（头发底下的头皮压成发色）、发际线下的暗部；眉毛按款式从 Texture2DArray 里取（按发丝画的）；
// 化妆一层层叠：眼影、眼线、腮红、口红（口红顺带让嘴唇润一点）；次表面散射按厚度遮罩（耳朵、鼻翼、眼皮透光多）
shader_type spatial;
render_mode sss_mode_skin, diffuse_burley, specular_schlick_ggx;

uniform sampler2D skin_light : source_color, filter_linear_mipmap_anisotropic;
uniform sampler2D skin_dark : source_color, filter_linear_mipmap_anisotropic;
uniform sampler2D skin_crc : hint_default_white, filter_linear_mipmap_anisotropic;   // R 凹度 G 粗糙度 B 油光
uniform sampler2D skin_normal : hint_normal, filter_linear_mipmap_anisotropic;
uniform sampler2D skin_mask : hint_default_black, filter_linear_mipmap;             // R 嘴唇 G 胡子 B 头皮 A 厚度
uniform sampler2D skin_makeup : hint_default_black, filter_linear_mipmap;           // R 眼线 G 眼影 B 腮红 A 发际线暗部
uniform sampler2D pore_normal : hint_normal, repeat_enable, filter_linear_mipmap_anisotropic;
uniform sampler2DArray brows : hint_default_black, filter_linear_mipmap_anisotropic;
uniform vec4 brow_rect = vec4(0.328, 0.597, 0.672, 0.669);   // 眉毛那一片 UV（Blender 的 UV：v 朝上）

uniform float melanin : hint_range(0.0, 1.0) = 0.2;
uniform float warmth : hint_range(-1.0, 1.0) = 0.0;      // 偏黄（+）还是偏粉（-）
uniform float flush : hint_range(0.0, 1.0) = 0.3;        // 两颊、鼻头的红润
uniform float age_detail : hint_range(0.0, 1.0) = 0.0;
uniform vec3 hair_color : source_color = vec3(0.05, 0.04, 0.035);
uniform float beard : hint_range(0.0, 1.0) = 0.0;        // 胡茬
uniform float scalp_hair : hint_range(0.0, 1.0) = 0.0;   // 头皮发茬（短发、寸头）
uniform float hairline_ao : hint_range(0.0, 1.0) = 0.0;  // 有头发时发际线下压暗
uniform float brow_style = 10.0;
uniform float brow_density : hint_range(0.0, 1.5) = 1.0;
uniform vec3 brow_color : source_color = vec3(0.05, 0.04, 0.035);
uniform float liner : hint_range(0.0, 1.0) = 0.0;
uniform vec3 liner_color : source_color = vec3(0.02, 0.018, 0.018);
uniform float shadow : hint_range(0.0, 1.0) = 0.0;
uniform vec3 shadow_color : source_color = vec3(0.45, 0.3, 0.25);
uniform float blush : hint_range(0.0, 1.0) = 0.0;
uniform vec3 blush_color : source_color = vec3(0.85, 0.42, 0.4);
uniform float lip : hint_range(0.0, 1.0) = 0.0;
uniform vec3 lip_color : source_color = vec3(0.6, 0.2, 0.22);
uniform float roughness_mul : hint_range(0.5, 1.5) = 1.0;
uniform float pore_scale = 90.0;
uniform float pore_strength : hint_range(0.0, 1.0) = 0.35;
uniform float sss : hint_range(0.0, 1.0) = 0.4;

float hash(vec2 p) {
	return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}

// 发茬：很细的格子里随机撒点，每点一根发根（UV 空间，脸上约 0.2 毫米一格）
float stubble(vec2 uv) {
	vec2 g = uv * 3200.0;
	vec2 c = floor(g);
	vec2 f = fract(g) - 0.5;
	float r = hash(c);
	vec2 o = vec2(hash(c + 17.0), hash(c + 31.0)) - 0.5;
	float d = length(f - o * 0.6);
	return step(0.45, r) * smoothstep(0.32, 0.12, d);
}

vec3 blend_normals(vec3 a, vec3 b) {
	// whiteout：两层切线空间法线叠起来
	return normalize(vec3(a.xy + b.xy, a.z * b.z));
}

void fragment() {
	vec2 uv = UV;
	vec3 light = texture(skin_light, uv).rgb;
	vec3 dark = texture(skin_dark, uv).rgb;
	vec3 c = mix(light, dark, melanin);
	vec4 mask = texture(skin_mask, uv);
	vec4 mk = texture(skin_makeup, uv);
	// 冷暖：偏黄是红绿多、蓝少；偏粉是红多、绿少
	c *= mix(vec3(1.0), warmth > 0.0 ? vec3(1.03, 1.0, 0.86) : vec3(1.04, 0.95, 1.0), abs(warmth));
	// 红润：腮红那片（两颊）和鼻头、嘴唇周围；肤色越深越不显
	float cheeks = mk.b;
	c = mix(c, c * vec3(1.08, 0.88, 0.86), flush * cheeks * 0.7 * (1.0 - melanin * 0.6));
	// 胡茬：胡子那片撒发根，发根是发色，整片再压一点青（剃过的胡子茬透出来）
	float bmask = mask.g * beard;
	float s = stubble(uv);
	c = mix(c, c * vec3(0.78, 0.82, 0.86), bmask * 0.55);
	c = mix(c, hair_color, bmask * s * 0.8);
	// 头皮：短发、寸头时头皮压成发色（发根），发际线下的暗部
	float scalp = mask.b * scalp_hair;
	c = mix(c, mix(c * 0.35, hair_color, 0.75), scalp * 0.92);
	c = mix(c, hair_color, scalp * stubble(uv * 0.8) * 0.9);
	c *= 1.0 - mk.a * hairline_ao * 0.35;
	// 化妆
	c = mix(c, c * shadow_color * 1.6, shadow * mk.g * 0.75);
	c = mix(c, mix(c, blush_color, 0.5), blush * mk.b * 0.55);
	c = mix(c, lip_color * (0.6 + 0.4 * c / max(dot(c, vec3(0.333)), 0.05)), lip * mask.r * 0.85);
	c = mix(c, liner_color, liner * mk.r);
	// 眉毛：眉毛那一片取当前款式；G 是眉毛底下的软影
	vec2 bv = vec2(uv.x, 1.0 - uv.y);
	vec2 buv = (bv - brow_rect.xy) / (brow_rect.zw - brow_rect.xy);
	float brow_a = 0.0;
	if (buv.x > 0.0 && buv.x < 1.0 && buv.y > 0.0 && buv.y < 1.0) {
		vec4 b = texture(brows, vec3(buv.x, 1.0 - buv.y, brow_style));
		brow_a = clamp(b.r * brow_density, 0.0, 1.0);
		c *= 1.0 - b.g * 0.25 * min(brow_density, 1.0);
		vec3 bc = mix(brow_color, brow_color * 1.6 + 0.02, b.b * 0.5);
		c = mix(c, bc, brow_a);
	}
	ALBEDO = c;

	vec3 crc = texture(skin_crc, uv).rgb;
	// 油光（B）不用清漆（Godot 的清漆粗糙度只在 0.001~0.1，一点点就是一层湿光），改成那片粗糙度低一点
	float rough = (0.14 + crc.g * 1.08 - crc.b * 0.25) * roughness_mul;
	rough = mix(rough, 0.32, lip * mask.r * 0.6);         // 口红：嘴唇润一点
	rough = mix(rough, 0.6, brow_a * 0.8 + bmask * s * 0.5);
	rough = mix(rough, 0.72, scalp);                       // 有发茬的头皮不反光
	ROUGHNESS = clamp(rough, 0.3, 0.9);
	SPECULAR = mix(0.2, 0.38, crc.r);

	// 法线贴图按 RGTC 压缩导入，只有 xy，z 自己补
	vec3 n = vec3(texture(skin_normal, uv).rg * 2.0 - 1.0, 0.0);
	n.z = sqrt(max(0.0, 1.0 - dot(n.xy, n.xy)));
	vec3 p = vec3(texture(pore_normal, uv * pore_scale).rg * 2.0 - 1.0, 0.0);
	p.xy *= pore_strength * (1.0 - mask.r) * (1.0 - brow_a);
	p.z = sqrt(max(0.0, 1.0 - dot(p.xy, p.xy)));
	NORMAL_MAP = blend_normals(n, p) * 0.5 + 0.5;

	// 透光：厚度遮罩亮的地方（耳朵、鼻翼、眼皮）薄
	SSS_STRENGTH = sss * (0.6 + 0.4 * (1.0 - mask.a));
	SSS_TRANSMITTANCE_COLOR = vec4(0.9, 0.3, 0.2, 1.0);
	SSS_TRANSMITTANCE_DEPTH = mix(0.1, 0.5, 1.0 - mask.a);
	SSS_TRANSMITTANCE_BOOST = 0.0;
}
