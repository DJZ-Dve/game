// 生物发光：零星几个会自己亮的小东西，在黑水里慢慢漂。大部分时间是暗的，隔一阵亮一下再慢慢熄掉
// （有的闪两下）。摆放方式和海雪一样（绕相机取模的颗粒场，见 marine_snow.gdshader），自发光不受灯影响。
shader_type spatial;
render_mode blend_add, unshaded, depth_draw_never, cull_disabled, skip_vertex_transform, shadows_disabled;

uniform vec4 color : source_color = vec4(0.25, 0.95, 0.85, 1.0);
uniform vec4 color_alt : source_color = vec4(0.35, 0.55, 1.0, 1.0);
uniform float energy = 8.0;
uniform vec3 box = vec3(60.0, 30.0, 60.0);
uniform float size = 0.045;
uniform vec3 current = vec3(0.05, -0.004, 0.02);
uniform float period_min = 8.0;  // 两次发光之间的间隔（秒）
uniform float period_max = 22.0;
uniform vec3 absorption = vec3(0.09, 0.032, 0.026);

uniform vec3 cabin_a = vec3(0.0);
uniform vec3 cabin_b = vec3(0.0, 0.0, 1.0);
uniform float cabin_radius = 1.38;

varying float v_glow;
varying vec3 v_col;

void vertex() {
	vec4 r = COLOR;
	vec2 corner = UV * 2.0 - 1.0;
	vec3 p = r.xyz * box + current * TIME * (0.5 + r.w);
	p += 0.4 * sin(TIME * vec3(0.07, 0.11, 0.05) * (1.0 + r.w) + r.zxy * 40.0);
	vec3 cam = CAMERA_POSITION_WORLD;
	p -= box * floor((p - cam) / box + 0.5);

	// 发光节律：每个周期里在随机时刻亮起，0.15 秒点亮、2~3 秒熄灭；一部分会紧跟着再闪一下
	float period = mix(period_min, period_max, fract(r.w * 7.31));
	float ph = TIME / period + fract(r.x * 13.7 + r.z * 5.1);
	float k = fract(ph) * period;
	float glow = smoothstep(0.0, 0.15, k) * exp(-k * 1.6);
	float k2 = k - 0.6;
	glow += step(0.5, fract(r.y * 9.3)) * smoothstep(0.0, 0.1, k2) * exp(-max(k2, 0.0) * 2.2) * 0.7;

	vec3 c = (VIEW_MATRIX * vec4(p, 1.0)).xyz;
	float px = 2.0 * max(-c.z, 0.05) / (PROJECTION_MATRIX[1][1] * VIEWPORT_SIZE.y);
	float s = size * (0.6 + r.y * 0.8);
	float w = max(s, px * 2.0);
	glow *= (s / w) * (s / w);
	// 光晕比本体大一圈
	w *= 3.0;
	VERTEX = c + vec3(corner, 0.0) * w * 0.5;

	vec3 ab = cabin_b - cabin_a;
	float t = clamp(dot(p - cabin_a, ab) / dot(ab, ab), 0.0, 1.0);
	if (distance(p, cabin_a + ab * t) < cabin_radius + w) {
		glow = 0.0;
		VERTEX = vec3(0.0);
	}
	vec3 rel = abs(p - cam) / (box * 0.5);
	glow *= 1.0 - smoothstep(0.6, 1.0, max(rel.x, max(rel.y, rel.z)));
	glow *= smoothstep(0.5, 1.5, length(c));

	v_glow = glow;
	v_col = mix(color.rgb, color_alt.rgb, step(0.75, fract(r.z * 17.0))) * exp(-absorption * length(c));
}

void fragment() {
	float d = length(UV * 2.0 - 1.0);
	// 亮核 + 柔和光晕
	float m = exp(-d * d * 30.0) + 0.25 * exp(-d * d * 5.0);
	ALBEDO = v_col * energy * v_glow * m;
}
