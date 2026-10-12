// 舱壁灯的玻璃球：所有灯泡在一个 MultiMesh 里，亮度由脚本按每一盏单独控制（实例自定义数据：r = 亮度，g = 余辉，
// b = 色温：0 是老的卤素灯，1 是后来换上的冷白 LED）。
// 灯丝刚断电时还剩一点余辉，颜色往橙红偏（卤素灯冷下来就是这个颜色；LED 没有余辉）。
shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_back;

uniform vec4 lit_color : source_color = vec4(1.0, 0.82, 0.6, 1.0);
uniform vec4 cool_color : source_color = vec4(0.86, 0.93, 1.0, 1.0);
uniform vec4 ember_color : source_color = vec4(1.0, 0.35, 0.08, 1.0);
uniform float energy = 14.0;

varying vec3 pe;

void vertex() {
	pe = INSTANCE_CUSTOM.rgb;
}

void fragment() {
	// 磨砂玻璃：正对着看最亮，边上暗一点（球里的灯丝 / 灯珠在中间）
	float core = mix(0.55, 1.0, pow(clamp(dot(NORMAL, VIEW), 0.0, 1.0), 1.5));
	ALBEDO = vec3(0.04);
	ROUGHNESS = 0.15;
	SPECULAR = 0.6;
	EMISSION = mix(lit_color.rgb, cool_color.rgb, pe.z) * energy * pe.x * core
		+ ember_color.rgb * energy * 0.25 * pe.y * (1.0 - pe.z);
}
