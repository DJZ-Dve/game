// 海雪颗粒：受光的柔和光点（只有被探照灯照到才看得见），耐压舱（一段胶囊体）里不显示。
shader_type spatial;
render_mode blend_mix, cull_disabled, depth_draw_never, diffuse_lambert, specular_disabled;

uniform vec4 color : source_color = vec4(0.85, 0.88, 0.85, 1.0);
uniform vec3 cabin_a = vec3(0.0);  // 耐压舱轴线的两端（世界坐标）
uniform vec3 cabin_b = vec3(0.0, 0.0, 1.0);
uniform float cabin_radius = 1.42;

void vertex() {
	// 粒子广告牌
	MODELVIEW_MATRIX = VIEW_MATRIX * mat4(INV_VIEW_MATRIX[0], INV_VIEW_MATRIX[1], INV_VIEW_MATRIX[2], MODEL_MATRIX[3]);
	MODELVIEW_MATRIX = MODELVIEW_MATRIX * mat4(
		vec4(length(MODEL_MATRIX[0].xyz), 0.0, 0.0, 0.0),
		vec4(0.0, length(MODEL_MATRIX[1].xyz), 0.0, 0.0),
		vec4(0.0, 0.0, length(MODEL_MATRIX[2].xyz), 0.0),
		vec4(0.0, 0.0, 0.0, 1.0));
	vec3 p = MODEL_MATRIX[3].xyz;
	vec3 ab = cabin_b - cabin_a;
	float t = clamp(dot(p - cabin_a, ab) / dot(ab, ab), 0.0, 1.0);
	if (distance(p, cabin_a + ab * t) < cabin_radius) {
		VERTEX = vec3(0.0);
	}
}

void fragment() {
	float d = length(UV - 0.5) * 2.0;
	float a = smoothstep(1.0, 0.2, d);
	ALBEDO = color.rgb * COLOR.rgb;
	ALPHA = a * color.a * COLOR.a;
}
