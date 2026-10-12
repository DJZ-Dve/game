// 升降机轿厢的钢丝网片（焊接网：竖丝在里、横丝在外，每 50 毫米一根，丝径 3.5 毫米，刷黑漆）：透过它看得见整口井。
// 网片是平的，法线沿物体空间的 x 或 z：在网片的平面里量坐标，不要 UV。
// 镂空用 alpha scissor + MSAA 的 alpha to coverage；钢丝在一个像素里占多少按盒式滤波算。远了钢丝比像素还细时，
// 按“这个像素里有多少是钢丝”在屏幕上抖网点（4×4 有序抖动），看着是一层淡淡的网，不会整片消失。
// 圆钢丝：截面上法线从一边歪到另一边，灯光在丝上是一道亮线。
// 两面都画（关掉背面剔除）。冷：横丝朝上那一侧结一点霜，漆旧了磨出钢来。
shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_disabled, diffuse_burley, specular_schlick_ggx, alpha_to_coverage;

uniform vec4 paint_color : source_color = vec4(0.07, 0.07, 0.068, 1.0);
uniform vec4 bare_color : source_color = vec4(0.42, 0.42, 0.4, 1.0);
uniform vec4 frost_color : source_color = vec4(0.78, 0.84, 0.88, 1.0);
uniform float pitch = 0.05;
uniform float wire = 0.0035;
uniform float frost_amount : hint_range(0.0, 1.0) = 0.35;
uniform float wear_amount : hint_range(0.0, 1.0) = 0.3;

varying vec3 p_obj;
varying vec3 n_obj;

void vertex() {
	p_obj = VERTEX;
	n_obj = NORMAL;
}

float hash13(vec3 p) {
	p = fract(p * 0.1031);
	p += dot(p, p.zyx + 31.32);
	return fract((p.x + p.y) * p.z);
}

float vnoise(vec3 p) {
	vec3 i = floor(p);
	vec3 f = fract(p);
	f = f * f * (3.0 - 2.0 * f);
	float a = mix(mix(hash13(i), hash13(i + vec3(1, 0, 0)), f.x), mix(hash13(i + vec3(0, 1, 0)), hash13(i + vec3(1, 1, 0)), f.x), f.y);
	float b = mix(mix(hash13(i + vec3(0, 0, 1)), hash13(i + vec3(1, 0, 1)), f.x), mix(hash13(i + vec3(0, 1, 1)), hash13(i + vec3(1, 1, 1)), f.x), f.y);
	return mix(a, b, f.z);
}

// 周期为 1、每个周期开头 d 那一段是“丝”的方波，在 [x - w/2, x + w/2] 上的平均值（盒式滤波，远了自然变成 d）
// 4×4 有序抖动的阈值（0~1）
float bayer4(vec2 p) {
	ivec2 q = ivec2(mod(floor(p), 4.0));
	int i = q.x + q.y * 4;
	float m[16] = float[16](0.0, 8.0, 2.0, 10.0, 12.0, 4.0, 14.0, 6.0, 3.0, 11.0, 1.0, 9.0, 15.0, 7.0, 13.0, 5.0);
	return (m[i] + 0.5) / 16.0;
}

float bar_cover(float x, float w, float d) {
	w = max(w, 1e-4);
	float x0 = x - 0.5 * w;
	float x1 = x + 0.5 * w;
	float i1 = floor(x1) * d + min(fract(x1), d);
	float i0 = floor(x0) * d + min(fract(x0), d);
	return clamp((i1 - i0) / w, 0.0, 1.0);
}

void fragment() {
	// 网片平面里的坐标：u 横着（沿网片的水平方向）、v 竖着
	bool on_x = abs(n_obj.x) > abs(n_obj.z);
	vec2 q = on_x ? p_obj.zy : p_obj.xy;
	vec3 axis_u = on_x ? vec3(0.0, 0.0, 1.0) : vec3(1.0, 0.0, 0.0);
	vec2 g = q / pitch;
	vec2 wg = fwidth(g) * 1.2;
	float d = wire / pitch;
	float cu = bar_cover(g.x, wg.x, d);   // 竖丝（沿 u 一根根排）
	float cv = bar_cover(g.y, wg.y, d);   // 横丝
	float cover = 1.0 - (1.0 - cu) * (1.0 - cv);
	// 钢丝不到一个像素宽：抖网点（远看细网比几何上的占比显眼一点：丝上的高光、网格的摩尔纹）
	float sub = smoothstep(0.6, 1.2, max(wg.x, wg.y) / d);
	ALPHA = mix(cover, step(bayer4(FRAGCOORD.xy), cover * 1.5), sub);
	ALPHA_SCISSOR_THRESHOLD = 0.5;
	ALPHA_ANTIALIASING_EDGE = 0.3;

	// 近处（一根丝有一个像素以上宽）：圆钢丝的法线；横丝在外面，盖住竖丝
	float near = 1.0 - smoothstep(0.35, 0.9, max(wg.x, wg.y) / d);
	vec2 f = fract(g) / d;                 // 丝的截面上 0~1（< 1 在丝上）
	bool horiz = f.y < 1.0;
	float s = clamp((horiz ? f.y : f.x) * 2.0 - 1.0, -1.0, 1.0);
	vec3 across_obj = horiz ? vec3(0.0, 1.0, 0.0) : axis_u;
	vec3 across = normalize((VIEW_MATRIX * MODEL_MATRIX * vec4(across_obj, 0.0)).xyz);
	vec3 nrm = normalize(NORMAL * sqrt(max(1.0 - s * s, 0.0)) + across * s);
	NORMAL = normalize(mix(NORMAL, nrm, near));

	// 漆：大片的深浅、磨出钢来的点（横丝的朝外那面多一些）；横丝朝上那一侧结霜
	vec3 p = p_obj;
	float big = vnoise(p * 2.3);
	vec3 col = paint_color.rgb * (0.85 + 0.3 * big);
	float worn = smoothstep(0.62, 0.85, vnoise(p * 21.0 + 3.0)) * wear_amount * (horiz ? 1.0 : 0.6);
	col = mix(col, bare_color.rgb, worn * near);
	float up_side = horiz ? smoothstep(0.0, 0.8, s) : 0.0;
	float frost = frost_amount * smoothstep(0.35, 0.75, vnoise(p * 4.0 + 7.0) * 0.6 + 0.4 * vnoise(p * 17.0)) * mix(0.35, 1.0, up_side);
	col = mix(col, frost_color.rgb, frost * 0.7);
	ALBEDO = col;
	METALLIC = 0.6 * worn * near;
	ROUGHNESS = mix(mix(0.62, 0.35, worn), 0.85, frost);
	SPECULAR = 0.5;
}
