// 破舱的粒子（breach.gd）：口子边上的喷雾、水柱打到柜门上炸开的水花、飘满半个舱的水雾、水下的气泡。
// 面朝相机的方片，形状是一团带噪声边缘的软斑（气泡是一圈亮边、中间透）；亮度跟舱里的灯走（受光照），透光。
// 颜色、透明度来自粒子的颜色渐变（COLOR）。按浑水衰减。
shader_type spatial;
render_mode blend_mix, depth_draw_never, cull_disabled, diffuse_burley, specular_schlick_ggx;

#include "res://assets/shaders/flood_common.gdshaderinc"

uniform sampler2D depth_tex : hint_depth_texture, filter_nearest, repeat_disable;
uniform int kind = 0;           // 0 水雾 / 一团团的水花，1 气泡，2 飞溅的水滴（顺着速度拉长）
uniform float stretch = 6.0;    // 水滴拉多长（倍）
uniform float softness = 0.15;  // 贴着东西的地方淡掉（米），免得方片插进墙里露出直边
uniform float density = 1.0;

varying float seed;

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
	seed = fract(MODEL_MATRIX[3].x * 13.7 + MODEL_MATRIX[3].y * 7.3 + MODEL_MATRIX[3].z * 3.1);
	if (kind == 2) {
		// 飞溅的水滴：粒子的 Y 轴已经对着速度（particle_flag_align_y），绕这根轴转过来对着相机，沿轴拉长
		vec3 axis = normalize(MODEL_MATRIX[1].xyz);
		vec3 pos = MODEL_MATRIX[3].xyz;
		vec3 to_cam = normalize(CAMERA_POSITION_WORLD - pos);
		vec3 side = normalize(cross(axis, to_cam));
		float sc = length(MODEL_MATRIX[0].xyz);
		MODELVIEW_MATRIX = VIEW_MATRIX * mat4(vec4(side * sc, 0.0), vec4(axis * sc * stretch, 0.0),
				vec4(cross(side, axis) * sc, 0.0), vec4(pos, 1.0));
		MODELVIEW_NORMAL_MATRIX = mat3(MODELVIEW_MATRIX);
	} else {
	// 粒子方片面朝相机（保留粒子自己的缩放），绕视线转一个随机角度
	mat4 m = mat4(INV_VIEW_MATRIX[0], INV_VIEW_MATRIX[1], INV_VIEW_MATRIX[2], MODEL_MATRIX[3]);
	float rot = INSTANCE_CUSTOM.x;
	mat4 r = mat4(vec4(cos(rot), -sin(rot), 0.0, 0.0), vec4(sin(rot), cos(rot), 0.0, 0.0), vec4(0, 0, 1, 0), vec4(0, 0, 0, 1));
	MODELVIEW_MATRIX = VIEW_MATRIX * m * r * mat4(vec4(length(MODEL_MATRIX[0].xyz), 0, 0, 0),
			vec4(0, length(MODEL_MATRIX[1].xyz), 0, 0), vec4(0, 0, length(MODEL_MATRIX[2].xyz), 0), vec4(0, 0, 0, 1));
	MODELVIEW_NORMAL_MATRIX = mat3(MODELVIEW_MATRIX);
	}
}

void fragment() {
	vec2 c = UV * 2.0 - 1.0;
	float r = length(c);
	float a;
	if (kind == 1) {
		// 气泡：亮边、透明的中心，上面一个高光点
		a = smoothstep(1.0, 0.82, r) * (0.25 + 0.75 * smoothstep(0.55, 0.9, r));
		a += smoothstep(0.3, 0.0, distance(c, vec2(-0.35, 0.4))) * 0.8;
		ALBEDO = vec3(0.8, 0.86, 0.85);
		ROUGHNESS = 0.1;
	} else if (kind == 2) {
		// 细长的一道，中间实、两头尖
		a = smoothstep(1.0, 0.3, length(c * vec2(1.0, 0.9))) * smoothstep(1.0, 0.0, abs(c.x) * 2.2);
		ALBEDO = vec3(0.82, 0.86, 0.85);
		ROUGHNESS = 0.2;
		BACKLIGHT = vec3(0.6);
	} else {
		float n = vnoise(c * 2.2 + seed * 37.0) * 0.6 + vnoise(c * 5.0 + seed * 91.0) * 0.4;
		a = smoothstep(1.0, 0.2, r + (n - 0.5) * 0.7);
		ALBEDO = vec3(0.8, 0.84, 0.83);
		ROUGHNESS = 0.45;
		BACKLIGHT = vec3(0.5);
	}
	a *= COLOR.a * density;

	// 贴着东西淡掉
	float scene = textureLod(depth_tex, SCREEN_UV, 0.0).r;
	vec4 sv = INV_PROJECTION_MATRIX * vec4(SCREEN_UV * 2.0 - 1.0, scene, 1.0);
	float gap = (VERTEX.z) - (sv.z / sv.w);
	a *= smoothstep(0.0, softness, gap);

	vec3 wpos = (INV_VIEW_MATRIX * vec4(VERTEX, 1.0)).xyz;
	bool under = flood_under(wpos);
	if (kind != 1 && under) {
		a *= 0.3;  // 水花落进水里就没了
	}
	if (kind == 1 && !under) {
		a = 0.0;  // 气泡冒出水面就破了
	}
	a *= flood_trans(CAMERA_POSITION_WORLD, wpos);
	ALBEDO *= COLOR.rgb;
	ALPHA = clamp(a, 0.0, 1.0);
}
