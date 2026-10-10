// 蚊帐纱（宿舍的床）：模型的 UV 是米，纱是一格一格的细线，线之间是空的。
// 离得近看得见格子，远了平均成一层半透明的白；线有一点点发黄发灰。双面、不投影。
shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_disabled, diffuse_burley, specular_disabled;

uniform vec4 color : source_color = vec4(0.82, 0.82, 0.78, 1.0);
uniform float mesh = 0.0018;       // 一格多宽（米）
uniform float thread = 0.22;       // 线占一格的比例
uniform float opacity = 0.75;      // 线本身的不透明度

void fragment() {
	vec2 g = UV / mesh;
	vec2 f = abs(fract(g) - 0.5) * 2.0;    // 0 在格子中间、1 在线上
	vec2 w = fwidth(g) * 1.2;
	vec2 l = smoothstep(1.0 - thread - w, 1.0 - thread + w, f);
	float line = max(l.x, l.y);
	// 远处格子比一个像素还小：直接用平均覆盖率
	float avg = 1.0 - (1.0 - thread) * (1.0 - thread);
	float far = smoothstep(0.35, 0.9, max(w.x, w.y));
	float cover = mix(line, avg, far);
	ALBEDO = color.rgb;
	ROUGHNESS = 1.0;
	ALPHA = cover * opacity;
	BACKLIGHT = color.rgb * 0.4;
}
