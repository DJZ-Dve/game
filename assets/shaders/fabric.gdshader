// 布料（铺位上的被子、枕头、床垫、布帘）：模型带 UV（单位是米），面料纹理顺着布走、跟着褶子弯。
// 另外叠加：绒面的边缘光泽（rim）、褶子里积的灰（曲率顶点色 G）、一块块发黄的汗渍、
// 薄布背后有灯时透出来的光（backlight）。
shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_back, diffuse_burley, specular_schlick_ggx;

uniform vec4 tint : source_color = vec4(0.3, 0.32, 0.22, 1.0);
uniform sampler2D albedo_tex : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D normal_tex : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D rough_tex : hint_default_white, filter_linear_mipmap_anisotropic, repeat_enable;
uniform float tex_scale = 2.0;  // 每米重复几次
// 0：只取贴图的明暗、染成 tint（灰白面料染色）；1：贴图原来的颜色乘 tint（条纹布）
uniform float albedo_mix : hint_range(0.0, 1.0) = 0.0;
uniform float tex_mean = 0.35;   // 贴图的平均亮度（线性），染色时除掉
uniform float tex_contrast = 1.5;
uniform float normal_strength : hint_range(0.0, 3.0) = 1.0;
uniform float roughness : hint_range(0.0, 1.0) = 0.95;

uniform float sheen : hint_range(0.0, 1.0) = 0.4;
uniform float sheen_tint : hint_range(0.0, 1.0) = 0.6;
uniform float cavity_dirt : hint_range(0.0, 1.0) = 0.5;
uniform float variation : hint_range(0.0, 0.5) = 0.12;  // 每件东西颜色深浅不一（顶点色 B）

// 汗渍、水渍：几十厘米一块的黄斑，边缘颜色深一圈
uniform float stain_amount : hint_range(0.0, 1.0) = 0.0;
uniform float stain_scale = 3.0;
uniform vec4 stain_color : source_color = vec4(0.62, 0.48, 0.26, 1.0);

// 毯子的锁边（UV2.x = 离布边的距离，UV2.y = 沿布边的坐标，单位米）：布边一窄条颜色深、毛绒被压平，
// 内侧一道缝线。binding_width = 0 不画
uniform float binding_width = 0.0;
uniform vec4 binding_color : source_color = vec4(0.7, 0.7, 0.7, 1.0);
uniform vec4 thread_color : source_color = vec4(0.45, 0.4, 0.28, 1.0);

uniform vec4 backlight : source_color = vec4(0.0, 0.0, 0.0, 1.0);

varying vec4 wear;

void vertex() {
	wear = COLOR;
}

float hash12(vec2 p) {
	vec3 q = fract(vec3(p.xyx) * 0.1031);
	q += dot(q, q.yzx + 33.33);
	return fract((q.x + q.y) * q.z);
}

float vnoise(vec2 p) {
	vec2 i = floor(p);
	vec2 f = fract(p);
	vec2 u = f * f * (3.0 - 2.0 * f);
	return mix(mix(hash12(i), hash12(i + vec2(1, 0)), u.x), mix(hash12(i + vec2(0, 1)), hash12(i + vec2(1, 1)), u.x), u.y);
}

float fbm(vec2 p) {
	float v = 0.0;
	float a = 0.5;
	for (int k = 0; k < 4; k++) {
		v += a * vnoise(p);
		p = p * 2.03 + vec2(17.1, 9.4);
		a *= 0.5;
	}
	return v;
}

void fragment() {
	vec2 uv = UV * tex_scale;
	vec3 tex = texture(albedo_tex, uv).rgb;
	float lum = dot(tex, vec3(0.2126, 0.7152, 0.0722));
	vec3 dyed = tint.rgb * pow(max(lum / tex_mean, 0.0), tex_contrast);
	vec3 col = mix(dyed, tex * tint.rgb, albedo_mix);
	// 每件东西深浅不一
	float rnd = wear.b;
	col *= 1.0 + variation * (rnd * 2.0 - 1.0);
	// 汗渍：一块块黄斑，边上一圈更深的水线
	float rough_add = 0.0;
	if (stain_amount > 0.0) {
		vec2 sp = UV * stain_scale + vec2(rnd * 37.0, rnd * 11.0);
		float n = fbm(sp);
		float body = smoothstep(0.62 - 0.2 * stain_amount, 0.7 - 0.2 * stain_amount, n);
		float ring = smoothstep(0.02, 0.0, abs(n - (0.64 - 0.2 * stain_amount))) * 0.6;
		float m = clamp(body * 0.55 + ring, 0.0, 1.0) * stain_amount;
		col = mix(col, col * stain_color.rgb, m);
		rough_add -= 0.08 * m;
	}
	float bind = 0.0;
	if (binding_width > 0.0) {
		bind = 1.0 - smoothstep(binding_width - 0.0015, binding_width, UV2.x);
		col = mix(col, col * binding_color.rgb, bind);
		float line = 1.0 - smoothstep(0.0004, 0.0011, abs(UV2.x - binding_width - 0.003));
		float dash = smoothstep(0.1, 0.2, fract(UV2.y / 0.007)) * (1.0 - smoothstep(0.65, 0.75, fract(UV2.y / 0.007)));
		col = mix(col, thread_color.rgb, line * dash * 0.85);
		rough_add -= 0.15 * bind;
	}
	// 褶子、凹坑里积的灰，顺便当 AO 用
	float cav = wear.g;
	col *= 1.0 - cavity_dirt * 0.45 * cav;
	ALBEDO = col;
	ROUGHNESS = clamp(roughness * texture(rough_tex, uv).r + rough_add, 0.0, 1.0);
	SPECULAR = 0.35;
	NORMAL_MAP = texture(normal_tex, uv).rgb;
	NORMAL_MAP_DEPTH = normal_strength * (1.0 - 0.6 * bind);
	AO = 1.0 - 0.5 * cav;
	AO_LIGHT_AFFECT = 0.3;
	RIM = sheen;
	RIM_TINT = sheen_tint;
	BACKLIGHT = backlight.rgb;
}
