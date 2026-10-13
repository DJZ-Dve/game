// 发丝（TressFX）底下的头皮：发型的层壳（Crew_Shell_xxx，见 crew_hair_shell.gdshader）只要最里一层（顶点色 R = 0，
// 贴着头皮 0.2 毫米），不画发丝，只把头皮染成发根的颜色——真头发的发根又密又细，分缝、发际线那里看过去是一层发根的暗色，
// 发丝粗、根数少，盖不满，露出的亮皮肤就成了一道道锯齿。发量 G 往发际线渐稀，染色跟着渐淡，没有硬边（层壳着色器那层是
// alpha 裁剪，边是一刀切的）
shader_type spatial;
render_mode blend_mix, depth_draw_never, cull_back, diffuse_burley;

uniform vec3 hair_color : source_color = vec3(0.03, 0.026, 0.024);
// 发量最密的地方盖住多少（1 整片发根色）
uniform float strength : hint_range(0.0, 1.0) = 0.8;
// 发量 G 从多少染到多少：分缝、发旋那里发量也低，染不到就露出一道亮皮肤；梳到后面的发型发际线全露着，
// 层壳的发量又比头发实际长到的地方大一圈，从低处染就在发际线下面多出一道染色带（tressfx_try.gd 按发型设）
uniform vec2 coverage = vec2(0.3, 0.9);

void fragment() {
	if (COLOR.r > 0.001) {
		discard;
	}
	// 发根色比发色暗一点（压在头发底下），带一点皮肤的暖色
	ALBEDO = mix(hair_color * 0.6, vec3(0.2, 0.13, 0.1), 0.15);
	ALPHA = smoothstep(coverage.x, coverage.y, COLOR.g) * strength;
	ROUGHNESS = 0.8;
	SPECULAR = 0.2;
}
