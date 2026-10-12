// 冰井里崩开的加热管喷出来、在那一片积起来的一团水汽（体积雾，椭球 FogVolume 用）：
// 中间浓、边上散，整团在慢慢翻滚、往上浮；amount 由脚本按时间推（0 = 还没崩）。
// 噪声是一张可平铺的 3D 噪声（NoiseTexture3D），用世界坐标采样。
// 喷出来的那股汽本身、加热管平时冒的汽是粒子（几十米外体积雾的格子有一米来宽，细的东西会被抹平）。
shader_type fog;

uniform float density = 0.5;
uniform float amount = 1.0;
uniform sampler3D noise : repeat_enable, filter_linear;
uniform vec3 albedo : source_color = vec3(0.9, 0.93, 0.96);

void fog() {
	vec3 q = WORLD_POSITION * 0.22 + vec3(0.0, -TIME * 0.05, TIME * 0.03);
	float n = texture(noise, q).r * 0.65 + texture(noise, q * 2.3 + vec3(0.6)).r * 0.35;
	// SDF：椭球里面是负的，越往中间越负
	float shape = smoothstep(0.0, -1.2, SDF);
	DENSITY = density * amount * shape * smoothstep(0.3, 0.75, n);
	ALBEDO = albedo;
}
