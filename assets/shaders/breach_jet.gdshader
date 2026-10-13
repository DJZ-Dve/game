// 从锯开的长缝里射进来的水幕（breach.gd 生成的一片网格：UV.x 沿缝 0~1，UV.y 从缝口 0 到落点 1）。
// 二百多个大气压的压差，水是以每秒两百米的速度冲进来的，出口就碎成白的：一整片乱抖的白色水幕，
// 沿着流向拉成一条条，越往前越散、越宽，砸到地板上炸开（炸开的水花是粒子，见 breach.gd）。
// 两面都画；缝还没锯到的那一段（UV.x > cut）没有水。
// 照明跟着舱里的灯走（不发光），透光（BACKLIGHT）；穿进水里的那一段淡一点、按浑水衰减。
shader_type spatial;
render_mode blend_mix, depth_draw_never, cull_disabled, diffuse_burley, specular_schlick_ggx;

#include "res://assets/shaders/flood_common.gdshaderinc"

uniform float intensity = 1.0;  // 0 没有 → 1 全开（刚裂开时只是一股细的）
uniform float reach = 1.0;      // 水柱头走到哪了（0~1，刚冲出来的那一下）
uniform float speed = 22.0;     // 纹理往前流的速度（画面上看着的，不是真的两百米每秒）
uniform float cut = 1.0;        // 缝锯到哪了（沿缝 0~1）

varying float along;

float hash12(vec2 p) {
	vec3 q = fract(vec3(p.xyx) * 0.1031);
	q += dot(q, q.yzx + 33.33);
	return fract((q.x + q.y) * q.z);
}

float vnoise(vec2 p) {
	vec2 i = floor(p);
	vec2 f = fract(p);
	f = f * f * (3.0 - 2.0 * f);
	return mix(mix(hash12(i), hash12(i + vec2(1, 0)), f.x), mix(hash12(i + vec2(0, 1)), hash12(i + vec2(1, 1)), f.x), f.y);
}

void vertex() {
	along = UV.y;
	// 水幕乱抖：沿缝的低频起伏随流向往前跑
	float n = vnoise(vec2(UV.x * 6.0 + 3.0, UV.y * 7.0 - TIME * speed * 0.35)) - 0.5;
	n += (vnoise(vec2(UV.x * 15.0, UV.y * 17.0 - TIME * speed * 0.6)) - 0.5) * 0.5;
	VERTEX += NORMAL * n * (0.01 + 0.07 * UV.y);
}

void fragment() {
	float ndv = clamp(abs(dot(NORMAL, VIEW)), 0.0, 1.0);
	// 沿流向拉长的纹理：一条条白的细丝 + 一团团更浓的
	vec2 q = vec2(UV.x * 16.0, along * 5.0 - TIME * speed * 0.25);
	float streak = vnoise(vec2(q.x, q.y * 0.35)) * 0.6 + vnoise(vec2(q.x * 2.3, q.y * 0.8 + 7.0)) * 0.4;
	float clump = vnoise(vec2(UV.x * 5.0, along * 3.0 - TIME * speed * 0.18));
	// 斜着看薄、正着看实；水幕两头（缝的两端）薄；一条条细丝之间是透的，越往前越散、越透
	float core = mix(0.35, 1.0, ndv) * smoothstep(0.0, 0.12, UV.x) * smoothstep(1.0, 0.88, UV.x);
	float fil = smoothstep(0.35 + along * 0.25, 0.75, streak);
	float a = core * mix(0.95, 0.35, along) * mix(fil, 1.0, (1.0 - along) * 0.6) * mix(0.7, 1.0, clump);
	// 头上散开、断成一团团
	a *= 1.0 - smoothstep(0.8, 1.0, along + (streak - 0.5) * 0.25);
	// 还没冲到的那一段没有
	a *= 1.0 - smoothstep(reach - 0.04, reach, along);
	// 沿缝分成几股：缝宽的地方喷得猛，窄的地方只是一层薄薄的水膜
	float lanes = vnoise(vec2(UV.x * 7.0, 3.7)) * 0.7 + vnoise(vec2(UV.x * 19.0, 9.1)) * 0.3;
	a *= smoothstep(0.25, 0.75, lanes) * 0.85 + 0.15;
	a *= intensity * 0.8;
	a *= 1.0 - smoothstep(cut - 0.06, cut, UV.x);

	vec3 wpos = (INV_VIEW_MATRIX * vec4(VERTEX, 1.0)).xyz;
	if (flood_under(wpos)) {
		a *= 0.3;  // 水下：一团团气泡和白水，没那么实
	}
	a *= flood_trans(CAMERA_POSITION_WORLD, wpos);

	ALBEDO = vec3(0.82, 0.86, 0.85) * mix(0.75, 1.0, streak);
	ROUGHNESS = 0.3;
	SPECULAR = 0.4;
	BACKLIGHT = vec3(0.45);
	ALPHA = clamp(a, 0.0, 1.0);
}
