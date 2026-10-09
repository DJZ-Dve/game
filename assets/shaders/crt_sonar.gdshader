// 声呐显像管：把 SonarDisplay 画好的 PPI 画面（screen_tex）贴到荧光屏上，加上显像管的质感——
// 光晕（亮的地方往外渗一圈）、荧光粉颗粒、没被打亮的荧光粉本身的灰绿底色、边缘暗角、轻微的亮度抖动。
shader_type spatial;
render_mode unshaded, cull_back;

uniform sampler2D screen_tex : source_color, filter_linear;
uniform float brightness = 2.4;
uniform float bloom = 0.55;
uniform float bloom_radius = 0.006;
uniform vec3 phosphor_base : source_color = vec3(0.035, 0.05, 0.04);
uniform float grain = 0.12;

float hash(vec2 p) {
	return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453);
}

void fragment() {
	vec2 uv = UV;
	vec3 c = texture(screen_tex, uv).rgb;
	// 光晕：两圈 8 个采样点
	vec3 b = vec3(0.0);
	for (int i = 0; i < 8; i++) {
		float a = float(i) * 0.785398;
		vec2 o = vec2(cos(a), sin(a));
		b += texture(screen_tex, uv + o * bloom_radius).rgb;
		b += texture(screen_tex, uv + o * bloom_radius * 2.6).rgb * 0.5;
	}
	c += b / 12.0 * bloom;
	// 荧光粉颗粒（固定不动）+ 一点点随时间跳的噪声
	float g = hash(floor(uv * 900.0)) - 0.5;
	float n = hash(uv * 517.0 + fract(TIME * 7.3)) - 0.5;
	c *= 1.0 + g * grain;
	c += phosphor_base * (1.0 + g * 0.6) + vec3(0.2, 0.5, 0.25) * n * 0.012;
	// 边缘暗角，整体亮度随电源轻微抖动
	float r = length(uv - 0.5) * 2.0;
	c *= mix(1.0, 0.55, smoothstep(0.55, 1.0, r));
	c *= 1.0 + sin(TIME * 47.0) * 0.008;
	ALBEDO = c * brightness;
}
