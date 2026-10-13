// 水下的气泡（breach.gd 的 Bubbles、Breath 粒子）：面朝相机的小方片。
// 水里的气泡因为全反射看上去是银白色的一圈亮边、中间透、上面一个高光点，不吃某一盏灯的颜色
// （之前跟着光照走，舱里只剩红色夜灯时整串气泡发红），亮度只跟舱里还剩多少灯走（glow，breach.gd 每帧给）。
// 冒出水面就破了（不画）；按浑水衰减。
shader_type spatial;
render_mode unshaded, blend_mix, depth_draw_never, cull_disabled, fog_disabled;

#include "res://assets/shaders/flood_common.gdshaderinc"

uniform float glow = 0.6;

void vertex() {
	mat4 m = mat4(INV_VIEW_MATRIX[0], INV_VIEW_MATRIX[1], INV_VIEW_MATRIX[2], MODEL_MATRIX[3]);
	MODELVIEW_MATRIX = VIEW_MATRIX * m * mat4(vec4(length(MODEL_MATRIX[0].xyz), 0, 0, 0),
			vec4(0, length(MODEL_MATRIX[1].xyz), 0, 0), vec4(0, 0, length(MODEL_MATRIX[2].xyz), 0), vec4(0, 0, 0, 1));
}

void fragment() {
	vec2 c = UV * 2.0 - 1.0;
	float r = length(c);
	float rim = smoothstep(1.0, 0.85, r) * smoothstep(0.55, 0.92, r);
	float spec = smoothstep(0.28, 0.0, distance(c, vec2(-0.32, 0.38)));
	float a = rim * 0.7 + spec * 0.9 + smoothstep(1.0, 0.0, r) * 0.08;
	vec3 wpos = (INV_VIEW_MATRIX * vec4(VERTEX, 1.0)).xyz;
	if (!flood_under(wpos)) {
		a = 0.0;
	}
	a *= COLOR.a * flood_trans(CAMERA_POSITION_WORLD, wpos);
	ALBEDO = vec3(0.82, 0.88, 0.9) * glow;
	ALPHA = clamp(a, 0.0, 1.0);
}
