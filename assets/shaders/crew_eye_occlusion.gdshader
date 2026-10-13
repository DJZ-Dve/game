// 眼部遮蔽（Vitruvian 的 Eyeshadow 网格）：盖在眼球上的一层，按顶点 alpha 把后面压暗——
// 眼皮底下、眼角的眼球暗下去，眼睛才“嵌”在眼眶里
shader_type spatial;
render_mode unshaded, blend_mix, depth_draw_never, cull_back;

uniform float strength : hint_range(0.0, 1.0) = 0.85;

void fragment() {
	ALBEDO = vec3(0.02, 0.012, 0.01);
	ALPHA = clamp(COLOR.a * strength, 0.0, 1.0);
}
