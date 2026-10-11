// 港湾的水（办事处窗外）：雨天灰绿色的海面。两层慢慢走的噪声法线当浪，雨点打出来一圈圈小涟漪；
// 菲涅尔反射天光（远处发白、近处看得见水下发暗的绿），粗糙度不高，屏幕空间反射照得出码头和船。
// 雨打水面：两层很密的小坑（每米 12 格、30 格），每格按自己的节拍随机跳（这一下凹、下一下平），
// 小于一个像素时按 fwidth 淡掉（不闪）；远处看不清一个个雨点了，就靠粗糙度往上走（0.08 → 0.18，反射发虚），
// 再加上一阵阵雨扫过水面（顺着风走的大块噪声，雨大的地方更毛）。
shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_back, diffuse_burley, specular_schlick_ggx;

uniform vec4 deep : source_color = vec4(0.03, 0.055, 0.05, 1.0);
uniform vec4 shallow : source_color = vec4(0.08, 0.11, 0.1, 1.0);
uniform float wave_scale = 0.12;
uniform float wave_speed = 0.06;
uniform float rain = 1.0;
// 雨打水面的两层小坑：每米多少格、每秒跳几下、法线幅度
uniform vec2 pit_cells = vec2(12.0, 30.0);
uniform vec2 pit_rate = vec2(5.0, 9.0);
uniform vec2 pit_strength = vec2(0.22, 0.14);
// 粗糙度：近处 → 远处（米），雨扫过的地方再毛一点
uniform float rough_near = 0.08;
uniform float rough_far = 0.18;
uniform vec2 rough_dist = vec2(8.0, 90.0);
uniform float squall = 0.05;
uniform vec2 squall_wind = vec2(0.6, -1.0);   // 雨阵在水面上走的速度（米/秒，世界 x、z）
// 挨着船、码头的水面发暗：船壳、栈桥挡住了一大块天（反射里本该是船的倒影，屏幕空间反射在远处常常找不到它），
// 栈桥底下更是背光。几个圆角矩形（世界 x、z 的中心，半长、半宽），occ_par：圆角半径、往外淡出的距离、浓淡。
// 由 office.gd 按码头、母船、镇海号的位置设
uniform vec4 occ_box[4];
uniform vec4 occ_par[4];

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

// 一层雨打的小坑：每格按自己的节拍换一个随机位置、随机深浅（有的这一下没打着），坑是一个高斯凹，
// 返回水平方向的斜率。cells 小于一个像素时淡掉
vec2 rain_pits(vec2 p, float cells, float rate, float t) {
	vec2 g = p * cells;
	vec2 id = floor(g);
	vec2 f = fract(g) - 0.5;
	float r = hash(id + 0.37 * cells);
	float tick = floor(t * rate * (0.7 + 0.6 * r) + r * 17.0);
	float h = hash(id + vec2(tick * 1.37, tick * 0.71));
	vec2 c = (vec2(hash(id + tick * 2.11 + 5.3), hash(id + tick * 3.07 + 1.9)) - 0.5) * 0.6;
	vec2 d = f - c;
	// 打着的一刹那最深，同一拍里慢慢平下去
	float age = fract(t * rate * (0.7 + 0.6 * r) + r * 17.0);
	float k = exp(-dot(d, d) * 40.0) * step(0.45, h) * (1.0 - age);
	float px = length(fwidth(g));
	return d * k * (1.0 - smoothstep(0.3, 0.75, px));
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
	vec2 s = rain_pits(p, pit_cells.x, pit_rate.x, t) * pit_strength.x
			+ rain_pits(p + 3.7, pit_cells.y, pit_rate.y, t) * pit_strength.y;
	n = normalize(n + vec3(s.x, 0.0, s.y) * 4.0 * rain);
	NORMAL = normalize((VIEW_MATRIX * vec4(n, 0.0)).xyz);
	float occ = 0.0;
	for (int i = 0; i < 4; i++) {
		vec2 q = abs(p - occ_box[i].xy) - occ_box[i].zw + occ_par[i].x;
		float d = length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - occ_par[i].x;
		occ = max(occ, occ_par[i].z * (1.0 - smoothstep(0.0, max(occ_par[i].y, 0.01), d)));
	}
	ALBEDO = mix(deep.rgb, shallow.rgb, h0) * (1.0 - occ * 0.5);
	// 越远越毛：看不清一个个雨点的地方，雨把水面打毛了，反射发虚
	float dist = length(VERTEX);
	float rough = mix(rough_near, rough_far, smoothstep(rough_dist.x, rough_dist.y, dist) * rain);
	// 一阵阵雨扫过：大块噪声顺着风走
	float sq = noise((p - squall_wind * t) * 0.04) * 0.65 + noise((p - squall_wind * t * 1.3) * 0.11 + 7.3) * 0.35;
	rough += smoothstep(0.45, 0.8, sq) * squall * rain;
	ROUGHNESS = rough;
	METALLIC = 0.0;
	SPECULAR = 0.7 * (1.0 - occ * 0.85);
}
