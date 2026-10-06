// 老式绿色荧光声呐屏：扫描线、距离环、余辉、回波点、屏幕弧度暗角。
shader_type spatial;
render_mode unshaded, cull_back;

uniform vec4 phosphor : source_color = vec4(0.25, 1.0, 0.4, 1.0);
uniform float brightness = 2.2;
uniform float sweep_speed = 0.6; // 每秒转数
uniform vec2 screen_size = vec2(0.22, 0.145); // 网格的 XY 尺寸（米）
uniform vec2 screen_center = vec2(0.0, 0.0175);
uniform float noise_amount = 0.08;
// 回波：xy=极坐标位置(角度 0..1, 半径 0..1)，z=强度
uniform vec4 echoes[8];

varying vec3 lpos;

void vertex() {
	lpos = VERTEX;
}

float hash(vec2 p) {
	return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453);
}

void fragment() {
	// 网格局部坐标 -> 屏幕坐标（Blender 导出后屏幕平面是局部 XZ，见 instruments.gd 传入的 uv）
	vec2 uv = UV;
	vec2 p = (uv - 0.5) * vec2(screen_size.x / screen_size.y, 1.0) * 2.0;
	float r = length(p);
	float ang = atan(p.y, p.x) / 6.2831853 + 0.5;

	float sweep = fract(TIME * sweep_speed);
	float d = fract(sweep - ang);
	float trail = exp(-d * 9.0);

	float rings = smoothstep(0.012, 0.0, abs(fract(r * 4.0) - 0.5) - 0.48) * 0.25;
	float cross_ = (smoothstep(0.006, 0.0, abs(p.x)) + smoothstep(0.006, 0.0, abs(p.y))) * 0.15;
	float scope = smoothstep(1.0, 0.97, r);

	float echo = 0.0;
	for (int i = 0; i < 8; i++) {
		vec4 e = echoes[i];
		if (e.z <= 0.0) continue;
		float ea = e.x * 6.2831853 - 3.1415926;
		vec2 ep = vec2(cos(ea), sin(ea)) * e.y;
		float age = fract(sweep - e.x);
		float fade = exp(-age * 2.5);
		echo += smoothstep(0.06, 0.0, length(p - ep)) * e.z * fade;
	}

	float grain = (hash(uv * 640.0 + TIME) - 0.5) * noise_amount;
	float scan = 0.85 + 0.15 * sin(uv.y * 900.0);
	float v = (trail * 0.65 + rings + cross_ + echo * 1.4) * scope + grain + 0.04;
	float vign = smoothstep(1.35, 0.4, length((uv - 0.5) * 2.0));
	ALBEDO = phosphor.rgb * v * scan * vign * brightness;
}
