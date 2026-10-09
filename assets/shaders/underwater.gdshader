// 水体吸收（全屏后处理）：海水对红光吸收最快、绿次之、蓝最慢，东西离得越远越偏蓝绿、越暗。
// 灯都装在艇上 / 相机旁，光是"灯 → 物体 → 眼睛"走了一个来回，所以按相机距离的两倍算光程。
// 耐压舱（一段胶囊体）里面是空气，不衰减；背景（没有几何体的像素）只按 bg_distance 算，
// 免得探照灯光柱在黑背景前被吃掉——光柱本身是体积雾散射出来的，散射点离相机远不了多少。
shader_type spatial;
render_mode unshaded, blend_mix, depth_draw_never, depth_test_disabled, cull_disabled, fog_disabled, shadows_disabled;

uniform sampler2D screen_tex : hint_screen_texture, filter_linear_mipmap, repeat_disable;
uniform sampler2D depth_tex : hint_depth_texture, filter_nearest, repeat_disable;

// 每米光程的衰减系数（RGB）：比纯水轻一些（不然十米外的艇身就只剩一团青黑），红光二三十米光程就基本没了
uniform vec3 absorption = vec3(0.09, 0.032, 0.026);
// 再远的距离也只按这么远算，更远处交给环境的距离雾压黑
uniform float max_distance = 14.0;
uniform float bg_distance = 5.0;
// 前一米几乎不衰减：贴着舷窗看东西颜色还是对的
uniform float clear_distance = 1.0;

uniform vec3 cabin_a = vec3(0.0);  // 耐压舱轴线两端（世界坐标），由 water_fx.gd 每帧更新
uniform vec3 cabin_b = vec3(0.0, 0.0, 1.0);
uniform float cabin_radius = 1.38;

void vertex() {
	POSITION = vec4(VERTEX.xy * 2.0, 1.0, 1.0);
}

void fragment() {
	vec3 col = textureLod(screen_tex, SCREEN_UV, 0.0).rgb;
	float depth = textureLod(depth_tex, SCREEN_UV, 0.0).r;
	vec4 v = INV_PROJECTION_MATRIX * vec4(SCREEN_UV * 2.0 - 1.0, depth, 1.0);
	vec3 view_pos = v.xyz / v.w;
	vec3 wpos = (INV_VIEW_MATRIX * vec4(view_pos, 1.0)).xyz;
	float d = depth > 0.0 ? min(length(view_pos), max_distance) : bg_distance;

	// 落在耐压舱里的像素：舱内表面，不衰减
	vec3 ab = cabin_b - cabin_a;
	float t = clamp(dot(wpos - cabin_a, ab) / dot(ab, ab), 0.0, 1.0);
	float inside = 1.0 - smoothstep(cabin_radius - 0.015, cabin_radius + 0.015, distance(wpos, cabin_a + ab * t));
	// 相机在舱里时，视线先穿过一段空气，这段不算
	vec3 cam = CAMERA_POSITION_WORLD;
	float tc = clamp(dot(cam - cabin_a, ab) / dot(ab, ab), 0.0, 1.0);
	float cam_in = step(distance(cam, cabin_a + ab * tc), cabin_radius);
	d = max(d - cam_in * 1.3 - clear_distance, 0.0);

	vec3 trans = exp(-absorption * d * 2.0);
	ALBEDO = col * mix(trans, vec3(1.0), inside);
}
