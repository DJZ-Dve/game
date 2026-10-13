// 船员的眼球（scripts/crew_look.gd）：一个不透明材质画完眼白和虹膜——角膜那片（眼白贴图中心的圆，alpha 为 0）
// 直接画虹膜，按视线方向往里错开一点（虹膜在角膜后面两三毫米，侧着看会“沉”进去，假的折射），外圈压暗一圈角膜缘环；
// 角膜很光滑，高光落在鼓起来的角膜上。不用透明层、不用清漆（Godot 里这两种做法都会在虹膜上蒙一层灰）
shader_type spatial;
render_mode diffuse_burley, specular_schlick_ggx;

uniform sampler2D sclera_tex : source_color, filter_linear_mipmap_anisotropic;
uniform sampler2D sclera_rough : hint_default_white, filter_linear_mipmap;
uniform sampler2D iris_tex : source_color, filter_linear_mipmap_anisotropic;
uniform vec3 iris_inner : source_color = vec3(0.35, 0.22, 0.1);
uniform vec3 iris_outer : source_color = vec3(0.16, 0.1, 0.06);
uniform float tint : hint_range(0.0, 1.0) = 0.85;
uniform float iris_radius = 0.1317;      // 角膜圆在眼白 UV 里的半径（gen_head_vitruvian.py 的眼白贴图）
uniform float iris_depth = 0.05;         // 虹膜在角膜后面多深（UV 单位，眼白 UV 一个单位约 44 毫米）
uniform float parallax_sign = 1.0;
uniform float whiteness : hint_range(0.5, 1.2) = 0.78;
uniform float redness : hint_range(0.0, 1.0) = 0.1;

void fragment() {
	vec2 d = UV - 0.5;
	float r = length(d) / iris_radius;
	vec3 sc = texture(sclera_tex, UV).rgb * whiteness;
	sc = mix(sc, sc * vec3(1.05, 0.85, 0.85), redness);
	// 视线在切线空间里的方向，往里错开
	vec3 v = vec3(dot(VIEW, TANGENT), dot(VIEW, BINORMAL), dot(VIEW, NORMAL));
	float depth = iris_depth * max(1.0 - r * r, 0.0);
	vec2 off = -v.xy / max(v.z, 0.35) * depth * parallax_sign;
	vec2 iuv = 0.5 + (d + off) / (2.0 * iris_radius);
	vec3 t = texture(iris_tex, iuv).rgb;
	float lum = dot(t, vec3(0.3, 0.59, 0.11));
	float ir = length(iuv - 0.5) * 2.0;
	vec3 col = mix(iris_inner, iris_outer, smoothstep(0.2, 0.85, ir));
	vec3 iris = mix(t, col * (0.35 + 1.6 * lum), tint);
	iris *= 1.0 - 0.7 * smoothstep(0.78, 1.0, ir);
	float m = 1.0 - smoothstep(0.93, 1.06, r);
	ALBEDO = mix(sc, iris, m);
	// 湿的眼球：角膜很光滑（主光在上面是一个清楚的眼神光），眼白稍糙一点。
	// 不用清漆：Godot 的清漆这么光滑时整片发灰，虹膜像蒙了一层雾
	ROUGHNESS = mix(clamp(texture(sclera_rough, UV).r * 0.6, 0.12, 0.4), 0.14, m);
	SPECULAR = 0.5;
	SSS_STRENGTH = 0.25 * (1.0 - m);
}
