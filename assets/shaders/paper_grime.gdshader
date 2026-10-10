// 纸上的脏（scripts/story/paper_doc.gd 用）：叠在字上面、乘法混合，字也跟着变脏。
// 发黄（越靠边越黄越暗）、霉点、水渍/茶渍圈、被水泡过的一大片水迹、折痕（一道细暗线，一边亮一边暗）。
shader_type canvas_item;
render_mode unshaded, blend_mul;

#include "res://assets/shaders/paper_common.gdshaderinc"

uniform float age : hint_range(0.0, 1.0) = 0.3;
uniform float stains : hint_range(0.0, 1.0) = 0.2;
uniform float wet : hint_range(0.0, 1.0) = 0.0;
uniform vec2 folds = vec2(0.0, 0.0);   // 竖着、横着各折了几道

// 一圈水渍：中间淡、边上一道深一点的干痕
float ring(vec2 uv, vec2 c, float r, float aspect) {
	vec2 d = (uv - c) * vec2(aspect, 1.0);
	float n = fbm(uv * 9.0 + c * 31.0) - 0.5;
	float dist = length(d) / r + n * 0.25;
	float inside = 1.0 - smoothstep(0.92, 1.0, dist);
	float edge = smoothstep(0.82, 0.97, dist) * (1.0 - smoothstep(0.97, 1.03, dist));
	return inside * 0.25 + edge * 0.9;
}

void fragment() {
	vec2 uv = UV;
	float aspect = px_size.x / px_size.y;
	vec2 p = uv * vec2(aspect, 1.0);
	vec3 m = vec3(1.0);
	vec2 e = min(uv, 1.0 - uv) * vec2(aspect, 1.0);
	float edge = 1.0 - smoothstep(0.0, 0.09, min(e.x, e.y) + (fbm(p * 7.0) - 0.5) * 0.03);
	m *= mix(vec3(1.0), vec3(0.9, 0.8, 0.6), age * (0.35 + 0.65 * edge));
	float spots = smoothstep(0.78, 0.86, fbm(p * 26.0 + 3.0)) * age;
	m *= mix(vec3(1.0), vec3(0.72, 0.6, 0.45), spots * 0.6);
	float st = 0.0;
	for (int i = 0; i < 3; i++) {
		vec2 c = vec2(hash(vec2(float(i), 1.0)), hash(vec2(float(i), 7.0))) * 0.9 + 0.05;
		float r = mix(0.06, 0.16, hash(vec2(float(i), 3.0)));
		st = max(st, ring(uv, c, r, aspect) * step(float(i), stains * 3.0 - 0.5));
	}
	m *= mix(vec3(1.0), vec3(0.78, 0.66, 0.48), st * stains);
	if (wet > 0.0) {
		// 从下面漫上来的一大片，边上一道起伏的深痕
		float w = fbm(p * 2.5 + 9.0) * 0.6 + (1.0 - uv.y) * 0.5 + uv.x * 0.2;
		float front = wet * 0.9;
		float inside = 1.0 - smoothstep(front - 0.02, front + 0.02, w);
		float tide = smoothstep(front - 0.05, front, w) * (1.0 - smoothstep(front, front + 0.012, w));
		m *= mix(vec3(1.0), vec3(0.8, 0.8, 0.76), inside * 0.6);
		m *= mix(vec3(1.0), vec3(0.62, 0.58, 0.5), tide);
	}
	for (int k = 0; k < 2; k++) {
		float n = k == 0 ? folds.x : folds.y;
		if (n < 0.5) {
			continue;
		}
		float x = (k == 0 ? uv.x : uv.y) * (n + 1.0);
		float j = floor(x + 0.5);
		if (j < 1.0 || j > n) {
			continue;
		}
		float d = (x - j) / (n + 1.0);
		float line = 1.0 - smoothstep(0.0, 0.0018, abs(d));
		float side = 1.0 - smoothstep(0.0, 0.012, abs(d));
		m *= 1.0 - line * 0.22;
		m *= 1.0 + sign(d) * side * 0.04;
	}
	COLOR = vec4(m, 1.0);
}
