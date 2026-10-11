// 下雨天的窗玻璃（宿舍、办事处的窗户）：外面挂满雨点，一些雨点攒大了往下淌、身后拖一道断续的湿痕。
// 雨点当透镜：按球冠斜率（越靠边越陡）往反方向取屏幕，雨点里是背后画面缩小的倒像，边上一圈发暗（全反射）；
// 透镜取到的点要是比玻璃还近（屋里的窗台、窗帘），就退回原位，不然夜里雨点会采到亮着的东西，满窗都是“星星”。
// 玻璃上一层水膜：背后发虚（mip 模糊）、雨点清楚。玻璃本体几乎透明：预乘混合，反射（探针、天光）不被 ALPHA 压掉，
// 窗外的雨丝粒子照样透过来。light() 留空：灯不在玻璃上打出圆形高光（办事处窗上那个假“月亮”）。
// 雨点按世界坐标排（u 沿玻璃水平、v 竖直），不需要 UV。
shader_type spatial;
render_mode blend_premul_alpha, depth_draw_never, cull_back, diffuse_burley, specular_schlick_ggx;

uniform sampler2D screen_tex : hint_screen_texture, filter_linear_mipmap, repeat_disable;
uniform sampler2D grime_tex : hint_default_black, filter_linear_mipmap, repeat_enable;
uniform vec3 tint = vec3(0.97, 0.98, 0.97);
uniform float rain : hint_range(0.0, 1.0) = 1.0;
uniform float drop_size = 0.0035;
uniform float speed = 1.0;
uniform float lens = 0.06;         // 雨点透镜：斜率 1 时往外取多远（屏幕比例）
uniform float film = 0.3;          // 水膜 / 雾气：混进多少模糊的背景
uniform float film_lod = 2.5;
uniform float dirt = 0.35;
uniform float grime_scale = 1.4;
uniform float small_density = 0.55; // 细小水珠那层
uniform sampler2D depth_tex : hint_depth_texture, filter_nearest, repeat_disable;

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

// 一层静止的雨点：返回 (指向球冠中心的斜率 xy，覆盖 z)；w 是到中心的归一化距离
vec4 drops(vec2 uv, float cell, float density, float rmin, float rmax) {
	vec2 g = uv / cell;
	vec2 id = floor(g);
	vec2 f = fract(g);
	vec4 best = vec4(0.0, 0.0, 0.0, 1.0);
	for (int j = -1; j <= 1; j++) {
		for (int i = -1; i <= 1; i++) {
			vec2 o = vec2(float(i), float(j));
			vec3 h = hash3(id + o);
			if (h.z > density) {
				continue;
			}
			vec2 c = o + 0.15 + h.xy * 0.7;
			float s = fract(h.z * 17.3 + h.x);
			float r = mix(rmin, rmax, s * s);   // 小的多、大的少
			vec2 d = f - c;
			d.y *= d.y < 0.0 ? 0.8 : 1.15;     // 下半截更饱满
			float dist = length(d) / r;
			float m = 1.0 - smoothstep(0.82, 1.0, dist);
			if (m > best.z) {
				// 球冠：斜率 = d / sqrt(1 - d²)，越靠边越陡
				vec2 dn = d / r;
				best = vec4(-dn / sqrt(max(1.0 - dist * dist, 0.08)), m, dist);
			}
		}
	}
	return best;
}

vec4 running(vec2 uv, float t) {
	float col_w = 0.03;
	float cx = floor(uv.x / col_w);
	float fx = fract(uv.x / col_w) - 0.5;
	float seed = hash1(cx * 1.37 + 3.1);
	if (seed > 0.6 * rain) {
		return vec4(0.0, 0.0, 0.0, 1.0);
	}
	float sp = mix(0.05, 0.16, hash1(cx + 7.7)) * speed;
	float tt = t * sp + seed * 10.0;
	float stair = floor(tt) + smoothstep(0.0, 0.3, fract(tt));
	float period = 1.4;
	float y = period - mod(stair * 0.5, period);
	float vy = mod(uv.y, period);
	float wig = sin(uv.y * 37.0 + seed * 20.0) * 0.08 + sin(uv.y * 11.0 + seed * 5.0) * 0.12;
	vec2 d = vec2((fx + wig) * col_w, vy - y);
	float r = 0.0045 + seed * 0.0035;
	vec2 dd = d / r;
	dd.y *= d.y > 0.0 ? 0.65 : 1.2;
	float dist = length(dd);
	float m = 1.0 - smoothstep(0.82, 1.0, dist);
	vec4 res = vec4(-dd / sqrt(max(1.0 - dist * dist, 0.08)), m, dist);
	// 身后一道湿痕（细、断续），不是一串圆点
	float trail = step(0.0, d.y) * (1.0 - smoothstep(0.0, 0.3, d.y));
	float tw = 0.0012 + 0.0008 * sin(d.y * 90.0 + seed * 9.0);
	float tx = abs((fx + wig) * col_w);
	float tm = (1.0 - smoothstep(tw * 0.6, tw, tx)) * trail * step(0.25, hash1(floor(d.y / 0.012) + cx));
	if (tm > res.z) {
		res = vec4(vec2(-sign(fx + wig) * 0.6, 0.0), tm * 0.8, 0.5);
	}
	return res;
}

void fragment() {
	vec3 n = normalize(wnrm);
	vec3 tu = normalize(cross(vec3(0.0, 1.0, 0.0), n));
	vec2 uv = vec2(dot(wpos, tu), wpos.y);
	float t = TIME;
	vec4 a = drops(uv, drop_size * 4.0, 0.42 * rain, 0.18, 0.46);
	vec4 b = drops(uv * 1.9 + 3.7, drop_size * 4.0, 0.3 * rain, 0.12, 0.4);
	vec4 s = drops(uv * 4.3 + 9.1, drop_size * 4.0, small_density * rain, 0.1, 0.32);
	vec4 c = running(uv, t);
	vec4 d = a;
	if (b.z > d.z) d = b;
	if (s.z > d.z) d = s;
	if (c.z > d.z) d = c;
	float px = length(fwidth(uv)) / (drop_size * 2.0);
	float fade = 1.0 - smoothstep(0.35, 0.9, px);
	float m = d.z * fade;

	// 背后的画面：水膜让它发虚；雨点里是透镜倒像（清楚、缩小）
	vec3 blur = textureLod(screen_tex, SCREEN_UV, film_lod).rgb;
	vec2 off = clamp(d.xy * lens, vec2(-0.25), vec2(0.25));
	vec2 luv = SCREEN_UV + off * vec2(1.0, -1.0) * vec2(VIEWPORT_SIZE.y / VIEWPORT_SIZE.x, 1.0);
	// 透镜取样点在玻璃前面（屋里的东西）：退回原位
	float sd = textureLod(depth_tex, luv, 0.0).r;
	vec4 sv = INV_PROJECTION_MATRIX * vec4(luv * 2.0 - 1.0, sd, 1.0);
	if (-sv.z / sv.w < -VERTEX.z) {
		luv = SCREEN_UV;
	}
	vec3 lensed = textureLod(screen_tex, luv, 0.5).rgb;
	float rim = smoothstep(0.55, 1.0, d.w);
	lensed *= mix(1.04, 0.35, rim);

	// 脏：灰斑 + 干了的水渍（贴图），贴着窗框的地方更脏
	float g = texture(grime_tex, uv * grime_scale).r;
	float grime = clamp(dirt * (g * 1.2 - 0.15), 0.0, 1.0);

	// 预乘混合：结果 = EMISSION + 反射 + 背后 × (1 - ALPHA)。
	// 玻璃本体只盖住 film（水膜）那一部分，背后的透明东西（窗外的雨丝粒子）照样透过来；雨点处完全由透镜像接管
	float a_body = clamp(film + grime * 0.3, 0.0, 1.0);
	vec3 e_body = blur * film * tint;
	ALBEDO = vec3(0.0);
	EMISSION = mix(e_body, lensed, m);
	ROUGHNESS = mix(0.06 + grime * 0.4, 0.02, m);
	METALLIC = 0.0;
	SPECULAR = 0.5;
	ALPHA = mix(a_body, 1.0, m);
	PREMUL_ALPHA_FACTOR = ALPHA;
}

void light() {
}
