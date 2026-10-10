// 镜子（scripts/story/mirror.gd）：反射相机渲染的画面贴在镜面上（左右翻过来）；
// 老镜子水银发乌（整体暗一点、边上发黑一圈），擦过的手印、水渍让镜面一块块发雾。
shader_type spatial;
render_mode unshaded, cull_back;

uniform sampler2D reflection : source_color, filter_linear, repeat_disable;
uniform sampler2D smear : hint_default_black, filter_linear_mipmap, repeat_enable;
uniform float darken : hint_range(0.0, 1.0) = 0.18;
uniform float haze : hint_range(0.0, 1.0) = 0.35;
uniform vec4 haze_color : source_color = vec4(0.5, 0.5, 0.48, 1.0);

void fragment() {
	// 反射相机的右手是镜面的左手（左右反）；glTF 的 UV 原点在左上角，和视口贴图一样，上下不用翻
	vec2 uv = vec2(1.0 - UV.x, UV.y);
	vec3 r = texture(reflection, uv).rgb;
	float s = texture(smear, UV * 2.0).r;
	vec2 e = min(UV, 1.0 - UV);
	float edge = 1.0 - smoothstep(0.0, 0.06, min(e.x, e.y));
	vec3 col = r * (1.0 - darken) * (1.0 - edge * 0.7);
	col = mix(col, haze_color.rgb * max(dot(r, vec3(0.33)), 0.05) * 1.5, s * haze);
	ALBEDO = col;
}
