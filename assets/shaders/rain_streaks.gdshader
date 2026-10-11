// 窗外的雨丝：一张网格里放几万个四边形，每个是一滴雨。位置在顶点着色器里算：按随机种子撒在一个盒子里
// （节点局部坐标的 box_min ~ box_max，岸上房间放在窗外），往下落、被风吹斜，出了盒子从另一头绕回来。
// 每滴拉成一道短线（快门时间里落过的那一段），太细不足一个像素时放宽到一个像素、按宽度降低亮度，远处不闪。
// 雨滴本身不发光：只有被灯照到（路灯、高杆灯，强烈的前向散射，迎着灯看最亮）或者衬着天光（ambient）才看得见。
shader_type spatial;
render_mode blend_add, depth_draw_never, cull_disabled, skip_vertex_transform, shadows_disabled;

uniform vec3 box_min = vec3(-10.0, -5.0, -20.0);
uniform vec3 box_max = vec3(10.0, 10.0, -2.0);
uniform float fall_speed = 8.0;           // 米/秒
uniform vec2 wind = vec2(0.0, 0.0);       // 水平风速（节点局部 x、z，米/秒）
uniform float gust = 0.3;                 // 阵风：风速时大时小（比例）
uniform float exposure = 0.035;           // 拖影的“快门”（秒）：8 m/s 时一道约 0.28 米
uniform float width = 0.0015;             // 雨丝粗细（米）
uniform float brightness = 1.0;
uniform vec3 ambient = vec3(0.0);         // 天光（白天衬着亮天也看得见；夜里 0，只靠灯）
uniform float fade_near = 0.8;            // 贴着眼睛的淡掉

varying float v_alpha;

vec3 hash3(vec3 p) {
	p = fract(p * vec3(0.1031, 0.1030, 0.0973));
	p += dot(p, p.yxz + 33.33);
	return fract((p.xxy + p.yxx) * p.zyx);
}

void vertex() {
	vec4 r = COLOR;
	vec3 r2 = hash3(r.xyz * 613.0 + r.w * 17.0);
	vec2 corner = UV * 2.0 - 1.0;
	vec3 size = box_max - box_min;
	float g = 1.0 + gust * sin(TIME * 0.7 + r.x * 1.3) * sin(TIME * 0.23 + 1.7);
	vec3 vel = vec3(wind.x * g, -fall_speed * (0.85 + 0.3 * r.w), wind.y * g);
	vec3 p = box_min + mod(r.xyz * size + vel * TIME, size);

	vec3 c = (VIEW_MATRIX * (MODEL_MATRIX * vec4(p, 1.0))).xyz;
	vec3 c0 = c - mat3(VIEW_MATRIX) * (mat3(MODEL_MATRIX) * vel) * exposure;
	float dist = length(c);
	float px = 2.0 * max(-c.z, 0.05) / (PROJECTION_MATRIX[1][1] * VIEWPORT_SIZE.y);
	float w = max(width, px * 1.2);
	float a = (width / w) * (0.5 + 0.5 * r2.x);

	vec2 s1 = c.xy / max(-c.z, 0.05);
	vec2 s0 = c0.xy / max(-c0.z, 0.05);
	vec2 sd = s1 - s0;
	vec2 along = length(sd) > 1e-6 ? normalize(sd) : vec2(0.0, 1.0);
	vec2 perp = vec2(-along.y, along.x);
	vec3 end = corner.x > 0.0 ? c : c0;
	VERTEX = end + vec3(perp * corner.y, 0.0) * w * 0.5;

	// 盒子边上淡掉（绕回来的那一下看不出来），贴着眼睛的淡掉
	vec3 rel = abs(p - (box_min + box_max) * 0.5) / (size * 0.5);
	a *= 1.0 - smoothstep(0.8, 1.0, max(rel.x, max(rel.y, rel.z)));
	a *= smoothstep(fade_near, fade_near * 2.0, dist);
	v_alpha = a;
	NORMAL = vec3(0.0, 0.0, 1.0);
}

void fragment() {
	float q = abs(UV.y * 2.0 - 1.0);
	float m = 1.0 - smoothstep(0.3, 1.0, q);
	// 两头细一点
	m *= smoothstep(0.0, 0.25, UV.x) * smoothstep(1.0, 0.75, UV.x);
	ALBEDO = vec3(brightness);
	EMISSION = ambient * brightness;
	ALPHA = m * v_alpha;
}

void light() {
	// 水滴强烈前向散射：灯在雨后面（迎着光看）最亮
	float mu = dot(-LIGHT, VIEW);
	float g = 0.7;
	float hg = (1.0 - g * g) / pow(1.0 + g * g - 2.0 * g * mu, 1.5);
	DIFFUSE_LIGHT += LIGHT_COLOR * ATTENUATION * (0.15 + 0.3 * hg);
}
