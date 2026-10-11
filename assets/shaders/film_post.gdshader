// 岸上房间的“镜头”：很淡的胶片颗粒（每秒换 24 次）、暗角、四角一点点色差。画在界面下面（字幕不吃颗粒）。
// 第一人称是“眼睛”，都压得很克制，只是让画面不那么像干净的渲染图。
shader_type canvas_item;

uniform sampler2D screen_tex : hint_screen_texture, filter_linear, repeat_disable;
uniform float grain = 0.018;
uniform float grain_size = 1.3;        // 颗粒多大（像素）
uniform float vignette = 0.22;
uniform float vignette_start = 0.35;
uniform float aberration = 0.0012;     // 色差：四角 RGB 错开多少（屏幕比例）
uniform float time_seed = -1.0;        // >= 0 时颗粒固定（截图对比用）

float hash(vec2 p) {
	vec3 q = fract(vec3(p.xyx) * 0.1031);
	q += dot(q, q.yzx + 33.33);
	return fract((q.x + q.y) * q.z);
}

void fragment() {
	vec2 uv = SCREEN_UV;
	vec2 d = uv - 0.5;
	float r2 = dot(d, d);
	vec2 off = d * aberration * r2 * 4.0;
	vec3 c;
	c.r = texture(screen_tex, uv + off).r;
	c.g = texture(screen_tex, uv).g;
	c.b = texture(screen_tex, uv - off).b;
	// 暗角：从 vignette_start 往外慢慢压暗（按画面宽高比修正成圆的）
	vec2 dv = d * vec2(SCREEN_PIXEL_SIZE.y / SCREEN_PIXEL_SIZE.x, 1.0);
	float v = smoothstep(vignette_start, vignette_start + 0.55, length(dv) * 1.2);
	c *= 1.0 - vignette * v;
	// 颗粒：暗部、中间调明显，亮部几乎没有（胶片的样子）
	float t = time_seed >= 0.0 ? time_seed : floor(TIME * 24.0);
	vec2 px = floor(FRAGCOORD.xy / grain_size);
	float n = hash(px + t * 37.0) + hash(px * 1.7 + t * 11.0) - 1.0;
	float lum = dot(c, vec3(0.299, 0.587, 0.114));
	c += n * grain * (1.0 - smoothstep(0.2, 0.9, lum));
	COLOR = vec4(c, 1.0);
}
