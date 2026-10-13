// 舱里灌进来的水（全屏后处理，breach.gd 挂）：视线穿过水的那一段按浑水衰减、往水的颜色上混。
// 人站在水面以上往下看，水下的地板、柜门越深越看不清；头没进水里时整个画面都在水里：
// 不戴面罩的眼睛在水里对不上焦（整片发虚）、被水流搅得一晃一晃，再叠上浑水。
// 只盖不透明的东西（深度图里的）；水面、水柱、水花这些透明的东西画在它后面，自己按 flood_common 算衰减。
shader_type spatial;
render_mode unshaded, blend_mix, depth_draw_never, depth_test_disabled, cull_disabled, fog_disabled, shadows_disabled;

#include "res://assets/shaders/flood_common.gdshaderinc"

uniform sampler2D screen_tex : hint_screen_texture, filter_linear_mipmap, repeat_disable;
uniform sampler2D depth_tex : hint_depth_texture, filter_nearest, repeat_disable;

// 头在水里的程度（0 / 1，breach.gd 按眼睛和水面的高度给，过水面那一下有几厘米的过渡）
uniform float submerged = 0.0;
// 水流的搅动（0~1）：口子还在往里喷的时候大
uniform float churn = 1.0;
// 背景（没有几何体的像素，比如从口子望出去的海）按这么远算
uniform float bg_distance = 6.0;

void vertex() {
	POSITION = vec4(VERTEX.xy * 2.0, 1.0, 1.0);
}

vec2 wobble(vec2 uv, float t) {
	// 两层慢慢游走的正弦，模拟浑水里折射率的起伏
	vec2 a = vec2(sin(uv.y * 23.0 + t * 2.1) + sin(uv.y * 41.0 - t * 3.3 + uv.x * 9.0) * 0.5,
			cos(uv.x * 19.0 - t * 1.7) + cos(uv.x * 37.0 + t * 2.9 + uv.y * 7.0) * 0.5);
	return a * 0.0035 * (0.4 + churn);
}

void fragment() {
	vec2 uv = SCREEN_UV;
	if (submerged > 0.0) {
		uv += wobble(uv, TIME) * submerged;
	}
	float depth = textureLod(depth_tex, uv, 0.0).r;
	vec4 v = INV_PROJECTION_MATRIX * vec4(uv * 2.0 - 1.0, depth, 1.0);
	vec3 view_pos = v.xyz / v.w;
	if (depth <= 0.0) {
		view_pos = normalize(view_pos) * bg_distance;
	}
	vec3 wpos = (INV_VIEW_MATRIX * vec4(view_pos, 1.0)).xyz;
	float T = flood_trans(CAMERA_POSITION_WORLD, wpos);

	if (submerged > 0.0) {
		// 眼睛泡在水里：远处、近处一样糊（不是景深），再叠一层更糊的光晕
		float lod = mix(0.0, 2.6, submerged);
		vec3 c = textureLod(screen_tex, uv, lod).rgb * 0.7 + textureLod(screen_tex, uv, lod + 1.5).rgb * 0.3;
		ALBEDO = c * T + flood_color * (1.0 - T);
		ALPHA = 1.0;
	} else {
		ALBEDO = flood_color;
		ALPHA = 1.0 - T;
	}
}
