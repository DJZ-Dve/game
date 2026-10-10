// 港湾的水（办事处窗外）：雨天灰绿色的海面。两层慢慢走的噪声法线当浪，雨点打出来一圈圈小涟漪；
// 菲涅尔反射天光（远处发白、近处看得见水下发暗的绿），粗糙度不高，屏幕空间反射照得出码头和船。
shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_back, diffuse_burley, specular_schlick_ggx;

uniform vec4 deep : source_color = vec4(0.03, 0.055, 0.05, 1.0);
uniform vec4 shallow : source_color = vec4(0.08, 0.11, 0.1, 1.0);
uniform float wave_scale = 0.12;
uniform float wave_speed = 0.06;
uniform float rain = 1.0;

varying vec3 wpos;

void vertex() {
	wpos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

float hash(vec2 p) {
	return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}

float noise(vec2 p) {
	vec2 i = floor(p);
	vec2 f = fract(p);
	f = f * f * (3.0 - 2.0 * f);
	return mix(mix(hash(i), hash(i + vec2(1, 0)), f.x), mix(hash(i + vec2(0, 1)), hash(i + vec2(1, 1)), f.x), f.y);
}

float height(vec2 p, float t) {
	float h = noise(p * wave_scale + vec2(t * wave_speed, t * wave_speed * 0.6)) * 0.6;
	h += noise(p * wave_scale * 2.7 - vec2(t * wave_speed * 1.3, 0.0)) * 0.3;
	h += noise(p * wave_scale * 7.1 + vec2(0.0, t * wave_speed * 2.0)) * 0.1;
	return h;
}

// 雨点涟漪：每格一个雨点，按自己的节奏一圈一圈往外扩
float ripples(vec2 p, float t) {
	vec2 g = p * 2.5;
	vec2 id = floor(g);
	vec2 f = fract(g) - 0.5;
	float r = hash(id);
	float ph = fract(t * (0.8 + r) + r * 7.0);
	float d = length(f + (vec2(hash(id + 3.1), hash(id + 7.7)) - 0.5) * 0.6);
	float ring = sin((d - ph * 0.5) * 60.0) * (1.0 - ph) * smoothstep(0.5 * ph + 0.06, 0.5 * ph, d);
	return ring * step(0.35, r);
}

void fragment() {
	vec2 p = wpos.xz;
	float t = TIME;
	float e = 0.05;
	float h0 = height(p, t);
	float hx = height(p + vec2(e, 0.0), t);
	float hz = height(p + vec2(0.0, e), t);
	vec3 n = normalize(vec3(-(hx - h0) / e * 0.6, 1.0, -(hz - h0) / e * 0.6));
	float rp = ripples(p, t) * rain;
	n = normalize(n + vec3(rp * 0.15, 0.0, rp * 0.1));
	NORMAL = normalize((VIEW_MATRIX * vec4(n, 0.0)).xyz);
	ALBEDO = mix(deep.rgb, shallow.rgb, h0);
	ROUGHNESS = 0.08;
	METALLIC = 0.0;
	SPECULAR = 0.7;
}
