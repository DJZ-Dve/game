// 下雨天的窗玻璃（宿舍、办事处的窗户）：外面挂满雨点，一些雨点攒大了往下淌、身后拖一串小水珠；
// 雨点处把背后的画面折射歪（取屏幕贴图），没雨点的地方几乎全透明（窗外的雨丝粒子照样看得见）。
// 玻璃上有一层薄薄的雾气（fog，看出去发虚），擦过的地方清楚一点（wipe）。
// 雨点按世界坐标排（u 沿玻璃水平、v 竖直），不需要 UV。
shader_type spatial;
render_mode blend_mix, depth_draw_never, cull_back, diffuse_burley, specular_schlick_ggx;

uniform sampler2D screen_tex : hint_screen_texture, filter_linear_mipmap, repeat_disable;
uniform vec4 tint : source_color = vec4(0.84, 0.9, 0.88, 1.0);
uniform float base_alpha : hint_range(0.0, 1.0) = 0.04;
uniform float rain : hint_range(0.0, 1.0) = 1.0;       // 雨点多少
uniform float drop_size = 0.0035;                       // 静止雨点的平均半径（米）
uniform float speed = 1.0;
uniform float refraction = 0.025;
uniform float fog : hint_range(0.0, 1.0) = 0.2;
uniform float dirt : hint_range(0.0, 1.0) = 0.08;      // 玻璃脏（灰、干了的水痕）

varying vec3 wpos;
varying vec3 wnrm;

void vertex() {
	wpos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	wnrm = normalize((MODEL_MATRIX * vec4(NORMAL, 0.0)).xyz);
}

vec3 hash3(vec2 p) {
	vec3 q = fract(vec3(p.xyx) * vec3(0.1031, 0.1030, 0.0973));
	q += dot(q, q.yxz + 33.33);
	return fract((q.xxy + q.yzz) * q.zyx);
}

float hash1(float n) {
	return fract(sin(n * 12.9898) * 43758.5453);
}

// 静止的雨点：每格一个（有的格子空着），返回 (表面斜率 xy, 覆盖 z)
vec3 static_drops(vec2 uv, float cell, float density) {
	vec2 g = uv / cell;
	vec2 id = floor(g);
	vec2 f = fract(g);
	vec3 best = vec3(0.0);
	for (int j = -1; j <= 1; j++) {
		for (int i = -1; i <= 1; i++) {
			vec2 o = vec2(float(i), float(j));
			vec3 h = hash3(id + o);
			if (h.z > density) {
				continue;
			}
			vec2 c = o + 0.15 + h.xy * 0.7;
			float r = mix(0.12, 0.42, fract(h.z * 17.3 + h.x));
			vec2 d = f - c;
			d.y *= d.y < 0.0 ? 0.85 : 1.15;   // 往下坠一点
			float dist = length(d) / r;
			float m = 1.0 - smoothstep(0.85, 1.0, dist);
			if (m > best.z) {
				best = vec3(d / r * sqrt(max(1.0 - dist * dist, 0.0)) * -0.9, m);
			}
		}
	}
	return best;
}

// 往下淌的雨点：竖着一条条，每条里一颗大雨点一顿一顿地往下走，身后留一串小水珠
vec3 running_drops(vec2 uv, float t) {
	float col_w = 0.035;
	float cx = floor(uv.x / col_w);
	float fx = fract(uv.x / col_w) - 0.5;
	float seed = hash1(cx * 1.37 + 3.1);
	if (seed > 0.55 * rain) {
		return vec3(0.0);
	}
	float sp = mix(0.04, 0.12, hash1(cx + 7.7)) * speed;
	// 一顿一顿：时间扭成台阶形
	float tt = t * sp + seed * 10.0;
	float stair = floor(tt) + smoothstep(0.0, 0.35, fract(tt));
	float period = 1.6;
	float y = period - mod(stair * 0.45, period);
	float vy = mod(uv.y, period);
	float wig = sin(uv.y * 40.0 + seed * 20.0) * 0.06;
	vec2 d = vec2((fx + wig) * col_w, vy - y);
	float r = 0.0045 + seed * 0.003;
	vec2 dd = d / r;
	dd.y *= d.y > 0.0 ? 0.7 : 1.2;
	float dist = length(dd);
	float m = 1.0 - smoothstep(0.8, 1.0, dist);
	vec3 res = vec3(dd * sqrt(max(1.0 - dist * dist, 0.0)) * -0.9, m);
	// 拖尾：大雨点上面一截，一串小水珠
	float trail = step(0.0, d.y) * (1.0 - smoothstep(0.0, 0.25, d.y));
	if (trail > 0.0 && abs(fx + wig) < 0.25) {
		float k = fract(d.y / 0.018);
		vec2 td = vec2((fx + wig) * col_w / 0.0018, (k - 0.5) * 0.018 / 0.0018);
		float tdist = length(td);
		float tm = (1.0 - smoothstep(0.7, 1.0, tdist)) * trail * step(0.3, hash1(floor(d.y / 0.018) + cx));
		if (tm > res.z) {
			res = vec3(td * sqrt(max(1.0 - tdist * tdist, 0.0)) * -0.5, tm);
		}
	}
	return res;
}

void fragment() {
	vec3 n = normalize(wnrm);
	vec3 up = vec3(0.0, 1.0, 0.0);
	vec3 tu = normalize(cross(up, n));
	vec2 uv = vec2(dot(wpos, tu), wpos.y);
	float t = TIME;
	vec3 a = static_drops(uv, drop_size * 4.0, 0.4 * rain);
	vec3 b = static_drops(uv * 1.7 + 3.7, drop_size * 4.0, 0.2 * rain);
	vec3 c = running_drops(uv, t);
	vec3 d = a;
	if (b.z > d.z) d = b;
	if (c.z > d.z) d = c;
	// 远处雨点小于一个像素时淡掉
	float px = length(fwidth(uv)) / (drop_size * 2.0);
	float fade = 1.0 - smoothstep(0.25, 0.7, px);
	float m = d.z * fade;
	vec2 off = d.xy * refraction * m;
	float lod = fog * 5.0 * (1.0 - m) + m * 1.5;
	vec3 bg = textureLod(screen_tex, SCREEN_UV + off, lod).rgb;
	// 脏：几厘米一块的灰斑（不是一格一格的噪点）
	vec2 gq = uv * 8.0;
	vec2 gi = floor(gq);
	vec2 gf = smoothstep(0.0, 1.0, fract(gq));
	float gn = mix(mix(hash3(gi).x, hash3(gi + vec2(1, 0)).x, gf.x), mix(hash3(gi + vec2(0, 1)).x, hash3(gi + vec2(1, 1)).x, gf.x), gf.y);
	float grime = dirt * gn * 0.3;
	ALBEDO = vec3(0.0);
	EMISSION = bg * tint.rgb * (1.0 - grime);
	ROUGHNESS = mix(0.12 + fog * 0.3, 0.02, m);
	METALLIC = 0.0;
	SPECULAR = 0.6;
	ALPHA = clamp(max(base_alpha + fog * 0.6 + grime, m), 0.0, 1.0);
}
