// 海雪 / 悬浮颗粒：一张网格里放几万个四边形，每个是一粒颗粒。位置在顶点着色器里算：
// 按随机种子撒在一个盒子里，跟着洋流慢慢漂、上下晃，再绕着相机取模——相机走到哪，周围总有一盒颗粒，
// 而颗粒本身钉在世界里不动（艇开起来就从舷窗外往后划过去）。
// 相对相机有速度时拉成一道短线（人眼 / 摄像机的拖影），亮度摊到整条线上。
// 只有被灯照到才看得见：光照是前向散射（迎着灯看最亮），耐压舱里不显示。
shader_type spatial;
render_mode blend_add, depth_draw_never, cull_disabled, skip_vertex_transform, shadows_disabled;

uniform vec4 color : source_color = vec4(0.85, 0.88, 0.85, 1.0);
uniform float brightness = 1.0;
uniform vec3 box = vec3(24.0, 16.0, 24.0);  // 颗粒场的大小（以相机为中心）
uniform vec2 size_range = vec2(0.004, 0.02);  // 颗粒直径（米），大部分偏小
uniform float size_bias = 3.0;  // 越大小颗粒越多
uniform vec3 current = vec3(0.05, -0.012, 0.02);  // 洋流 + 下沉（米/秒）
uniform float wobble = 0.12;  // 随水晃动的幅度（米）
uniform vec3 cam_velocity = vec3(0.0);  // 相机的世界速度，拖影用
uniform float exposure = 0.06;  // 拖影的"快门"（秒）
uniform float fade_near = 0.25;  // 贴着眼睛的颗粒淡掉
uniform vec3 absorption = vec3(0.09, 0.032, 0.026);  // 和 underwater.gdshader 一致

uniform vec3 cabin_a = vec3(0.0);
uniform vec3 cabin_b = vec3(0.0, 0.0, 1.0);
uniform float cabin_radius = 1.38;

varying float v_alpha;
varying float v_dist;

vec3 hash3(vec3 p) {
	p = fract(p * vec3(0.1031, 0.1030, 0.0973));
	p += dot(p, p.yxz + 33.33);
	return fract((p.xxy + p.yxx) * p.zyx);
}

void vertex() {
	vec4 r = COLOR;
	vec3 r2 = hash3(r.xyz * 917.0 + r.w * 31.0);
	vec2 corner = UV * 2.0 - 1.0;

	// 世界位置：撒点 + 洋流（每粒快慢不一）+ 晃动，再绕相机取模
	vec3 p = r.xyz * box + current * TIME * (0.6 + r.w * 0.8);
	p += wobble * sin(TIME * (0.15 + r2 * 0.35) + r2 * 6.2831 + r.yzx * 20.0);
	vec3 cam = CAMERA_POSITION_WORLD;
	p -= box * floor((p - cam) / box + 0.5);

	float size = mix(size_range.x, size_range.y, pow(r.w, size_bias));
	vec3 c = (VIEW_MATRIX * vec4(p, 1.0)).xyz;
	float dist = length(c);

	// 不足一个像素的颗粒放大到一个像素宽、按面积降低亮度，免得闪烁
	float px = 2.0 * max(-c.z, 0.05) / (PROJECTION_MATRIX[1][1] * VIEWPORT_SIZE.y);
	float w = max(size, px * 1.6);
	float a = (size / w) * (size / w) * (0.35 + 0.65 * r2.x);  // 每粒反光强弱不一

	// 拖影：这一粒在"快门时间"里相对相机走过的线段
	vec3 vel = mat3(VIEW_MATRIX) * (current - cam_velocity);
	vec3 c0 = c - vel * exposure;
	vec2 s1 = c.xy / max(-c.z, 0.05);
	vec2 s0 = c0.xy / max(-c0.z, 0.05);
	vec2 sd = s1 - s0;
	float slen = length(sd) * max(-c.z, 0.05);  // 拖影长度换算回米
	vec2 along = slen > 1e-5 ? normalize(sd) : vec2(1.0, 0.0);
	vec2 perp = vec2(-along.y, along.x);
	vec3 end = corner.x > 0.0 ? c : c0;
	VERTEX = end + vec3(along * corner.x + perp * corner.y, 0.0) * w * 0.5;
	a *= w / (w + slen);

	// 耐压舱里不显示；场的边缘、贴着眼睛的都淡掉
	vec3 ab = cabin_b - cabin_a;
	float t = clamp(dot(p - cabin_a, ab) / dot(ab, ab), 0.0, 1.0);
	if (distance(p, cabin_a + ab * t) < cabin_radius + w) {
		a = 0.0;
		VERTEX = vec3(0.0);
	}
	vec3 rel = abs(p - cam) / (box * 0.5);
	a *= 1.0 - smoothstep(0.7, 1.0, max(rel.x, max(rel.y, rel.z)));
	a *= smoothstep(fade_near, fade_near * 2.0, dist);

	v_alpha = a;
	v_dist = dist;
	NORMAL = vec3(0.0, 0.0, 1.0);
}

void fragment() {
	vec2 q = UV * 2.0 - 1.0;
	float m = 1.0 - smoothstep(0.2, 1.0, length(q));
	ALBEDO = color.rgb * brightness * exp(-absorption * v_dist);  // 回到眼睛的这一段的吸收
	ALPHA = m * v_alpha * color.a;
}

void light() {
	// 悬浮颗粒强烈前向散射：灯在颗粒后面（迎着光看）最亮，灯在背后时暗得多
	float mu = dot(-LIGHT, VIEW);
	float g = 0.65;
	float hg = (1.0 - g * g) / pow(1.0 + g * g - 2.0 * g * mu, 1.5);
	float phase = 0.25 + 0.35 * hg;
	DIFFUSE_LIGHT += LIGHT_COLOR * ATTENUATION * phase;
}
