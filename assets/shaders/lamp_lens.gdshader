// 舱壁灯的玻璃球：所有灯泡在一个 MultiMesh 里，亮度由脚本按每一盏单独控制（实例自定义数据：r = 亮度，g = 余辉）。
// 灯丝刚断电时还剩一点余辉，颜色往橙红偏（卤素灯冷下来就是这个颜色）。
shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_back;

uniform vec4 lit_color : source_color = vec4(1.0, 0.82, 0.6, 1.0);
uniform vec4 ember_color : source_color = vec4(1.0, 0.35, 0.08, 1.0);
uniform float energy = 14.0;

varying vec2 pe;

void vertex() {
	pe = INSTANCE_CUSTOM.rg;
}

void fragment() {
	ALBEDO = vec3(0.04);
	ROUGHNESS = 0.15;
	SPECULAR = 0.6;
	EMISSION = lit_color.rgb * energy * pe.x + ember_color.rgb * energy * 0.25 * pe.y;
}
