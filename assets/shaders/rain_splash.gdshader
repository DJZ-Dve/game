// 雨点打在码头面、水面、甲板上溅起的小水花：和雨丝（rain_streaks.gdshader）一样，一张网格里放几千个四边形，
// 位置全在顶点着色器里算。每个四边形是一处落点：按自己的节拍（period 秒一次）在矩形区域里换一个随机位置，
// 落下的一刹那溅起一小撮水（往上蹦、往外散，0.2 秒左右落回去），其余时间不画。
// 朝着镜头的竖立小片；远处不足一个像素时放宽到一个像素、按面积降低亮度，不闪。
// 自己不发光：衬着天光（ambient）、被灯（闪电）照到才看得见，和雨丝一个路数。
shader_type spatial;
render_mode blend_add, depth_draw_never, cull_disabled, skip_vertex_transform, shadows_disabled;

uniform vec2 area_min = vec2(-5.0, -20.0);   // 落点区域（节点局部 x、z）
uniform vec2 area_max = vec2(5.0, -10.0);
uniform float surface_y = 0.0;               // 落点的高度（节点局部 y）
uniform float period = 0.6;                  // 每个四边形多少秒落一次（各自再随机快慢）
uniform float life = 0.22;                   // 一下水花持续多久（秒）
uniform float size = 0.12;                   // 水花多高多宽（米）
uniform float brightness = 1.0;
uniform vec3 ambient = vec3(0.05, 0.055, 0.06);
uniform float fade_near = 1.5;
uniform float seed = 0.0;                    // 每块区域换一个：网格是同一套随机数，不换的话各块的落点节拍、相对位置一模一样
uniform float deck_crown = 0.0;              // 区域正中（沿 x）比两边高多少：甲板中拱

varying float v_alpha;
varying float v_age;

vec3 hash3(vec3 p) {
	p = fract(p * vec3(0.1031, 0.1030, 0.0973));
	p += dot(p, p.yxz + 33.33);
	return fract((p.xxy + p.yxx) * p.zyx);
}

void vertex() {
	vec4 r = COLOR;
	float per = period * (0.7 + 0.6 * r.w);
	float t = TIME / per + r.x * 13.7 + seed * 0.37;
	float cycle = floor(t);
	float age = fract(t) * per / life;          // 0 → 1 这一下水花的一生，>1 就不画
	vec3 h = hash3(vec3(cycle * 0.173 + r.y * 91.0 + seed * 7.31, r.z * 37.0 + cycle * 0.311, r.w * 53.0 + seed * 3.17));
	vec2 xz = mix(area_min, area_max, h.xy);
	float cu = h.x * 2.0 - 1.0;
	vec3 p = vec3(xz.x, surface_y + deck_crown * (1.0 - cu * cu), xz.y);
	vec3 c = (VIEW_MATRIX * (MODEL_MATRIX * vec4(p, 1.0))).xyz;
	float dist = length(c);
	float px = 2.0 * max(-c.z, 0.05) / (PROJECTION_MATRIX[1][1] * VIEWPORT_SIZE.y);
	float s = size * (0.6 + 0.8 * h.z);
	float sw = max(s, px * 1.5);
	vec2 corner = UV * 2.0 - 1.0;
	// 竖立在落点上、朝着镜头（视空间里 x 朝右、y 朝上）
	vec3 up = mat3(VIEW_MATRIX) * (mat3(MODEL_MATRIX) * vec3(0.0, 1.0, 0.0));
	vec3 right = normalize(cross(up, vec3(0.0, 0.0, 1.0)));
	VERTEX = c + right * corner.x * sw * 0.5 + up * (corner.y * 0.5 + 0.5) * sw * 0.8;
	float a = (s / sw) * (s / sw);
	a *= step(age, 1.0);
	a *= smoothstep(fade_near, fade_near * 2.0, dist);
	v_alpha = a;
	v_age = clamp(age, 0.0, 1.0);
	NORMAL = vec3(0.0, 0.0, 1.0);
}

void fragment() {
	vec2 q = UV * 2.0 - 1.0;   // x：-1 左 → 1 右；y：-1 落点 → 1 顶
	float t = v_age;
	// 中间往上蹦的一柱（先长后落），两边往外散的一圈水珠（冠状）
	float jet_h = sin(t * 3.14159) * 1.2 - 1.0;
	float jet = (1.0 - smoothstep(0.08, 0.22, abs(q.x))) * step(-1.0, q.y) * (1.0 - smoothstep(jet_h - 0.15, jet_h + 0.05, q.y));
	float spread = 0.3 + t * 0.6;
	float crown_y = -1.0 + sin(t * 3.14159) * 0.7;
	float crown = 0.0;
	for (int i = -2; i <= 2; i++) {
		vec2 dp = q - vec2(float(i) * spread * 0.45, crown_y - abs(float(i)) * 0.12);
		crown += 1.0 - smoothstep(0.05, 0.12, length(dp * vec2(1.0, 0.8)));
	}
	float m = clamp(jet * 0.7 + crown, 0.0, 1.0) * (1.0 - t * t);
	ALBEDO = vec3(brightness);
	EMISSION = ambient * brightness;
	ALPHA = m * v_alpha;
}

void light() {
	// 水珠前向散射（同雨丝）
	float mu = dot(-LIGHT, VIEW);
	float g = 0.7;
	float hg = (1.0 - g * g) / pow(1.0 + g * g - 2.0 * g * mu, 1.5);
	DIFFUSE_LIGHT += LIGHT_COLOR * ATTENUATION * (0.15 + 0.3 * hg);
}
