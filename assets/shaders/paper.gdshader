// 纸的底色（scripts/story/paper_doc.gd 用，画在字下面）：底色 + 很细的颗粒 + 拉长的纤维 + 大片的明暗起伏。
// 发黄、水渍、折痕这些画在字上面，见 paper_grime.gdshader。
shader_type canvas_item;
render_mode unshaded;

#include "res://assets/shaders/paper_common.gdshaderinc"

uniform vec4 tint : source_color = vec4(0.93, 0.9, 0.82, 1.0);

void fragment() {
	vec2 p = UV * vec2(px_size.x / px_size.y, 1.0);
	float grain = vnoise(UV * px_size * 0.5) - 0.5;
	float fiber = fbm(p * vec2(60.0, 9.0)) - 0.5;
	float cloud = fbm(p * 3.0) - 0.5;
	COLOR = vec4(tint.rgb * (1.0 + grain * 0.035 + fiber * 0.05 + cloud * 0.06), 1.0);
}
