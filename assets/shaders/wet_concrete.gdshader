// 雨里泡透了的混凝土（办事处窗外的码头面板、桩、岸壁）。不依赖 UV（物体空间三平面映射）：
// - 混凝土贴图整体压暗、粗糙度降到 0.3 上下（湿了的水泥发黑发亮），凹处（曲率顶点色 G）更湿
// - 朝上的面上低洼处积着一洼洼水：几乎是镜面，雨点在水洼里打出一圈圈涟漪；水洼边上一圈半干半湿
// - 贴着水面那一截（潮差带）长着发黑发绿的青苔、滑溜溜的；码头面板底下、桩子顶上背光发暗（天光照不进去）
shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_back, diffuse_burley, specular_schlick_ggx;

uniform sampler2D albedo_tex : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D normal_tex : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D rough_tex : hint_default_white, filter_linear_mipmap_anisotropic, repeat_enable;
uniform vec4 tint : source_color = vec4(0.55, 0.55, 0.52, 1.0);
uniform float tex_scale = 0.7;
uniform float normal_strength = 0.8;
// 湿：0 干 → 1 泡透（反照率压暗到 wet_darken 倍、粗糙度降到 wet_roughness）
uniform float wetness : hint_range(0.0, 1.0) = 0.85;
uniform float wet_darken = 0.55;
uniform float wet_roughness = 0.3;
// 水洼：大约多少面积、多大一块（每米多少个噪声格）
uniform float puddle_amount : hint_range(0.0, 1.0) = 0.35;
uniform float puddle_scale = 0.45;
uniform float puddle_darken = 0.75;   // 水洼底下的混凝土透过水看更暗一点（主要靠反光和涟漪看出是水）
// 水洼里的雨点涟漪：每米多少格
uniform float ripple_cells = 3.0;
uniform float rain = 1.0;
// 潮差带：水面高度（物体空间 y）、往上多高长青苔
uniform float water_level = -8.6;
uniform float tide_band = 0.7;
uniform vec4 algae_color : source_color = vec4(0.05, 0.065, 0.045, 1.0);
// 背光：这个高度以下（码头面板底下）暗下去
uniform float under_top = -8.05;
uniform float under_dark : hint_range(0.0, 1.0) = 0.6;

varying vec3 obj_pos;
varying vec3 obj_nrm;
varying vec4 wear;

void vertex() {
	obj_pos = VERTEX;
	obj_nrm = NORMAL;
	wear = COLOR;
}

vec3 tri_weights(vec3 n) {
	vec3 w = pow(abs(n), vec3(4.0));
	return w / (w.x + w.y + w.z + 1e-5);
}

vec4 tri_sample(sampler2D t, vec3 p, vec3 w) {
	return texture(t, p.zy) * w.x + texture(t, p.xz) * w.y + texture(t, p.xy) * w.z;
}

vec3 tri_normal(vec3 p, vec3 n, vec3 w, float strength) {
	vec3 tx = texture(normal_tex, p.zy).xyz * 2.0 - 1.0;
	vec3 ty = texture(normal_tex, p.xz).xyz * 2.0 - 1.0;
	vec3 tz = texture(normal_tex, p.xy).xyz * 2.0 - 1.0;
	tx.xy *= strength;
	ty.xy *= strength;
	tz.xy *= strength;
	tx = vec3(tx.xy + n.zy, abs(tx.z) * n.x);
	ty = vec3(ty.xy + n.xz, abs(ty.z) * n.y);
	tz = vec3(tz.xy + n.xy, abs(tz.z) * n.z);
	return normalize(tx.zyx * w.x + ty.xzy * w.y + tz.xyz * w.z);
}

float hash(vec2 p) {
	return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}

float vnoise(vec2 p) {
	vec2 i = floor(p);
	vec2 f = fract(p);
	f = f * f * (3.0 - 2.0 * f);
	return mix(mix(hash(i), hash(i + vec2(1, 0)), f.x), mix(hash(i + vec2(0, 1)), hash(i + vec2(1, 1)), f.x), f.y);
}

// 水洼里的雨点涟漪（同 harbor_water 的做法）：返回水面斜率
vec2 ripples(vec2 p, float t) {
	vec2 g = p * ripple_cells;
	vec2 id = floor(g);
	vec2 f = fract(g) - 0.5;
	float r = hash(id);
	float ph = fract(t * (0.9 + r) + r * 7.0);
	vec2 d = f + (vec2(hash(id + 3.1), hash(id + 7.7)) - 0.5) * 0.6;
	float l = length(d);
	float ring = sin((l - ph * 0.5) * 50.0) * (1.0 - ph) * smoothstep(0.5 * ph + 0.06, 0.5 * ph, l);
	float px = length(fwidth(g));
	return d / max(l, 1e-3) * ring * step(0.3, r) * (1.0 - smoothstep(0.15, 0.4, px));
}

void fragment() {
	vec3 n = normalize(obj_nrm);
	vec3 w = tri_weights(n);
	vec3 p = obj_pos * tex_scale;
	vec3 col = tri_sample(albedo_tex, p, w).rgb * tint.rgb;
	float rough = tri_sample(rough_tex, p, w).r;
	float cav = wear.g;
	float edge = wear.r;
	// 棱边磕掉一层，露出发白的新茬（湿了也比面上浅）
	col = mix(col, col * 1.35 + 0.02, smoothstep(0.4, 0.9, edge) * 0.6);

	// 泡湿：凹处更湿；竖直面上的雨水往下流，比朝上的面稍干一点
	float wet = clamp(wetness * (0.85 + 0.15 * n.y) + cav * 0.3, 0.0, 1.0);
	col *= mix(1.0, wet_darken, wet);
	rough = mix(rough, wet_roughness + (rough - 0.5) * 0.15, wet);

	// 水洼：只在朝上的面上，两层噪声分出低洼处
	vec2 q = obj_pos.xz * puddle_scale;
	float pn = vnoise(q) * 0.65 + vnoise(q * 2.7 + 5.1) * 0.35;
	float up = smoothstep(0.85, 0.97, n.y);
	float th = 1.0 - puddle_amount;
	float aa = max(fwidth(pn) * 1.2, 0.025);
	float puddle = smoothstep(th - aa, th + aa, pn) * up;
	float damp = smoothstep(th - 0.08, th, pn) * up;   // 水洼边上一圈半干半湿
	rough = mix(rough, rough * 0.6, damp);
	col = mix(col, col * 0.85, damp);

	// 潮差带：贴着水面那一截长青苔，滑
	float tide = 1.0 - smoothstep(water_level + tide_band * 0.3, water_level + tide_band, obj_pos.y);
	tide *= 0.75 + 0.5 * vnoise(obj_pos.xz * 2.0 + obj_pos.y * 3.0);
	tide = clamp(tide, 0.0, 1.0);
	col = mix(col, algae_color.rgb, tide * 0.85);
	rough = mix(rough, 0.18, tide);

	// 背光：面板底下、朝下的面
	float under = (1.0 - smoothstep(under_top - 0.5, under_top + 0.02, obj_pos.y)) * step(obj_pos.y, under_top + 0.3);
	under = max(under, smoothstep(-0.3, -0.8, n.y));
	col *= 1.0 - under_dark * under;

	vec3 nn = tri_normal(p, n, w, normal_strength * (1.0 - 0.5 * wet));
	// 水洼：水面是平的（盖住混凝土的起伏），雨点打出涟漪
	if (puddle > 0.001) {
		vec2 s = ripples(obj_pos.xz, TIME) * rain;
		vec3 wn = normalize(n + vec3(s.x, 0.0, s.y) * 0.25);
		nn = normalize(mix(nn, wn, puddle));
		col = mix(col, col * puddle_darken, puddle);
		rough = mix(rough, 0.03, puddle);
	}
	ALBEDO = col;
	ROUGHNESS = clamp(rough, 0.03, 1.0);
	METALLIC = 0.0;
	SPECULAR = mix(0.5, 0.6, max(wet, puddle));
	NORMAL = normalize((VIEW_MATRIX * (MODEL_MATRIX * vec4(nn, 0.0))).xyz);
}
