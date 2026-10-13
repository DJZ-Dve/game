// 舱里涨起来的水面（breach.gd 挂的一张细分平面，节点的高度就是水位）。
// 平面比舱大，舱外的部分按耐压舱圆筒、艏部半球、隔壁丢掉。顶点按几层噪声起伏：口子还在往里灌的时候
// 整片水面被搅得乱晃，水柱扎进水里的地方往外一圈圈翻；表面的白沫是被搅出来的气泡，贴着柜子、
// 舱壁的一圈也有（按深度图找水面和东西相交的地方）。
// 从上面看：透过水面看到的东西按折射挪一下、按水深发浑（自己算，盖住 flood_post），反射交给光照；
// 从下面看（头在水里）：斜着看是全反射的一层亮膜，正着往上看透出上面的灯（斯涅尔窗）。
shader_type spatial;
render_mode blend_mix, depth_draw_never, cull_disabled, diffuse_burley, specular_schlick_ggx;

#include "res://assets/shaders/flood_common.gdshaderinc"

uniform sampler2D depth_tex : hint_depth_texture, filter_nearest, repeat_disable;
uniform sampler2D screen_tex : hint_screen_texture, filter_linear_mipmap, repeat_disable;

uniform float agitation = 1.0;   // 0 平静 → 1 被水柱搅得乱翻
uniform vec2 jet_xz = vec2(0.0); // 水柱扎进水面的位置（局部 x、z）；jet_on = 0 时没有
uniform float jet_on = 0.0;
uniform float bow_center = -1.6; // 艏部半球的球心（局部 z）
uniform float z_offset = 0.0;    // 平面节点的局部 z（顶点坐标 + 它 = 舱内局部 z）

varying vec3 lpos;
varying float foam_v;

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

// 水面高度（相对水位）：几层游走的噪声 + 水柱冲进来的一圈圈翻涌
float wave(vec2 p, float t) {
	// 舱里就两三米宽，起不了大浪：短而碎的乱波，被搅的时候更高更碎
	float a = 0.006 + 0.026 * agitation;
	float h = (vnoise(p * 3.7 + vec2(t * 1.1, -t * 0.8)) - 0.5) * 1.0
			+ (vnoise(p * 8.3 + vec2(-t * 2.3, t * 1.9)) - 0.5) * 0.55
			+ (vnoise(p * 19.0 + vec2(t * 4.1, t * 3.3)) - 0.5) * 0.3 * agitation;
	h *= a;
	if (jet_on > 0.0) {
		float r = distance(p, jet_xz);
		h += jet_on * (0.09 * exp(-r * r / 0.03) * (0.6 + 0.4 * sin(t * 23.0))
				+ 0.025 * sin(r * 26.0 - t * 14.0) * exp(-r * 1.2));
	}
	return h;
}

void vertex() {
	vec2 p = vec2(VERTEX.x, VERTEX.z + z_offset);
	float t = TIME;
	float h = wave(p, t);
	const float EPS = 0.02;
	float hx = wave(p + vec2(EPS, 0.0), t);
	float hz = wave(p + vec2(0.0, EPS), t);
	VERTEX.y += h;
	NORMAL = normalize(vec3(h - hx, EPS, h - hz));
	lpos = vec3(p.x, VERTEX.y, p.y);
	foam_v = h;
}

void fragment() {
	// 舱外的部分丢掉（按水位高度那一圈的圆筒截面、艏部半球、两头的隔壁）
	float lvl = flood_level;
	float rr = flood_radius * flood_radius - lvl * lvl;
	float x2 = lpos.x * lpos.x;
	if (x2 > rr || lpos.z < flood_z.x || lpos.z > flood_z.y) {
		discard;
	}
	if (lpos.z < bow_center && x2 + (lpos.z - bow_center) * (lpos.z - bow_center) > rr) {
		discard;
	}

	vec3 wpos = (INV_VIEW_MATRIX * vec4(VERTEX, 1.0)).xyz;
	// 白沫：搅动出来的一片片 + 浪尖 + 贴着东西的一圈
	float t = TIME;
	vec2 p = lpos.xz;
	float fn = vnoise(p * 7.0 + vec2(t * 1.3, -t * 0.8)) * 0.6 + vnoise(p * 19.0 - vec2(t * 2.0, t * 1.1)) * 0.4;
	float foam = smoothstep(0.88 - 0.12 * agitation, 0.99, fn) * (0.15 + 0.35 * agitation);
	foam += smoothstep(0.02, 0.05, foam_v) * agitation * 0.35;
	if (jet_on > 0.0) {
		float r = distance(p, jet_xz);
		foam += jet_on * smoothstep(0.5, 0.0, r) * (0.4 + 0.6 * fn);
	}
	float scene = textureLod(depth_tex, SCREEN_UV, 0.0).r;
	vec4 sv = INV_PROJECTION_MATRIX * vec4(SCREEN_UV * 2.0 - 1.0, scene, 1.0);
	float behind = -(sv.z / sv.w) - (-VERTEX.z);  // 水面后面的东西离水面多远（沿视线）
	foam += (1.0 - smoothstep(0.0, 0.05, behind)) * (0.35 + 0.65 * fn) * (0.4 + 0.6 * agitation);
	foam = clamp(foam, 0.0, 1.0);

	// 折射：按水面法线和平静水面法线的差把屏幕采样点挪一下；挪过去的地方要是在水面前面（挡在水面上方的东西），就不挪
	vec3 n0 = normalize((VIEW_MATRIX * vec4(flood_ay, 0.0)).xyz);
	vec2 ruv = SCREEN_UV + (NORMAL - n0).xy * (FRONT_FACING ? 0.035 : 0.06);
	float rd = textureLod(depth_tex, ruv, 0.0).r;
	vec4 rv = INV_PROJECTION_MATRIX * vec4(ruv * 2.0 - 1.0, rd, 1.0);
	rv.xyz /= rv.w;
	if (rv.z > VERTEX.z) {
		ruv = SCREEN_UV;
		rv = vec4(sv.xyz / sv.w, 1.0);
	}
	float ndv = clamp(abs(dot(NORMAL, VIEW)), 0.0, 1.0);
	vec3 col;
	if (FRONT_FACING) {
		// 从上面看：透过水面看到的东西（屏幕采样）按水面到它的那段水深发浑；反射交给光照（反射探针 + 灯的高光）
		vec3 bw = (INV_VIEW_MATRIX * vec4(rv.xyz, 1.0)).xyz;
		float Tw = flood_trans(wpos, bw);
		col = textureLod(screen_tex, ruv, 0.0).rgb * Tw + flood_color * (1.0 - Tw);
	} else {
		// 从下面看：斯涅尔窗（离法线 48.6° 以内）透出上面的舱，窗外是全反射：映着下面的浑水
		vec3 above = textureLod(screen_tex, ruv, 3.0).rgb;  // 眼睛在水里对不上焦，和 flood_post 一样糊
		float tir = smoothstep(0.6, 0.72, 1.0 - ndv);
		col = mix(above, flood_color * 1.6, tir);
		// 头在水里看水面：中间隔着一段水
		float T = flood_trans(CAMERA_POSITION_WORLD, wpos);
		col = col * T + flood_color * (1.0 - T);
	}
	ALBEDO = vec3(0.5, 0.53, 0.51) * foam;
	EMISSION = col * (1.0 - foam);
	ROUGHNESS = mix(0.07, 0.6, foam);
	SPECULAR = 0.25;  // F0 ≈ 0.02，水
	METALLIC = 0.0;
	ALPHA = 1.0;
}
