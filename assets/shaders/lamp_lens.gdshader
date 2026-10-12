// 舱壁灯的玻璃罩：所有灯罩在每圈一个 MultiMesh 里，亮度由脚本按每一盏单独控制（实例自定义数据：r = 亮度，g = 余辉，
// b = 色温：0 是老的卤素灯，1 是后来换上的冷白 LED）。
// 磨砂玻璃罩：灯泡拧在灯座上、在罩子中心偏下一点，离灯泡近的那片玻璃最亮，往上、往边上暗下去；
// 正对着看中间亮（光在磨砂层里走的路短），边上暗一点。LED 的灯珠是平的一片，罩子里亮得更匀。
// 灯丝刚断电时还剩一点余辉，颜色往橙红偏（卤素灯冷下来就是这个颜色；LED 没有余辉）。
shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_back;

uniform vec4 lit_color : source_color = vec4(1.0, 0.82, 0.6, 1.0);
uniform vec4 cool_color : source_color = vec4(0.86, 0.93, 1.0, 1.0);
uniform vec4 ember_color : source_color = vec4(1.0, 0.35, 0.08, 1.0);
uniform float energy = 18.0;
uniform float bulb_y = -0.015;    // 灯泡在罩子中心上方多高（局部坐标，米）
uniform float globe_r = 0.08;

varying vec3 pe;
varying vec3 lp;

void vertex() {
	pe = INSTANCE_CUSTOM.rgb;
	lp = VERTEX;
}

void fragment() {
	float core = mix(0.6, 1.0, pow(clamp(dot(NORMAL, VIEW), 0.0, 1.0), 1.5));
	// 离灯泡越近越亮（卤素灯是一个点；LED 是一片，亮得匀）
	float d = length(lp - vec3(0.0, bulb_y, 0.0)) / globe_r;
	float hot = mix(mix(1.3, 0.75, smoothstep(0.35, 1.25, d)), 1.0, pe.z * 0.7);
	ALBEDO = vec3(0.05);
	ROUGHNESS = 0.2;
	SPECULAR = 0.6;
	EMISSION = mix(lit_color.rgb, cool_color.rgb, pe.z) * energy * pe.x * core * hot
		+ ember_color.rgb * energy * 0.25 * pe.y * (1.0 - pe.z) * hot;
}
