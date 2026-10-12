// 环形走台的钢格栅板（压焊格栅）：承载扁钢顺着走台的弧走（搭在径向托梁上），每 30 毫米一根；
// 横杆（扭绞方钢）沿径向，每 100 毫米一根。格子是镂空的：从上往下看，透过格栅看得见下面几圈的灯。
// 物体空间坐标，井轴是 Y 轴。镂空用 alpha scissor + MSAA 的 alpha to coverage 抗锯齿；
// 远了格子比像素还细的时候，镂空会闪成一片摩尔纹——改成不透明、颜色按“有多少是钢”压暗。
// 上下两个面都画（关掉背面剔除），斜着看时透过上面的格子看得见扁钢的下沿，显出 45 毫米的厚度。
// 侧面（走台内外沿的包边扁钢）是实心的。冷：靠近井壁那一侧的格栅上结着白霜，走的人多的中间一条被踩亮了。
// 热镀锌，旧了发灰发白（锌面上一层白锈），不刷漆。
// 斜着看时，看到的多半是扁钢、横杆竖着的侧面：法线往那边歪，灯从头顶照下来时不会像一整块平板那样亮。
// 远处几圈走台不挂真的灯光（太多了），扶手上那圈灯照在格栅上的一片片光斑在这里算（pool_power > 0 的圈）。
shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_disabled, diffuse_burley, specular_schlick_ggx, alpha_to_coverage;

uniform float radius = 11.0;
uniform float bar_pitch = 0.03;
uniform float bar_width = 0.005;
uniform float cross_pitch = 0.1;
uniform float cross_width = 0.007;
uniform vec4 paint_color : source_color = vec4(0.36, 0.36, 0.34, 1.0);   // 热镀锌，旧了发灰
uniform vec4 worn_color : source_color = vec4(0.5, 0.5, 0.48, 1.0);
uniform vec4 frost_color : source_color = vec4(0.78, 0.84, 0.88, 1.0);
uniform vec4 rust_color : source_color = vec4(0.22, 0.1, 0.04, 1.0);
// 远处几圈的灯光斑：灯（一圈 LAMPS 盏）挂在半径 lamp_r、走台面上方 lamp_h 处，第 j 盏在方位角 lamp_start + lamp_step * (j + 这圈的错位)
uniform float lamp_r = 9.38;
uniform float lamp_h = 1.22;
uniform float lamp_start = 0.14;
uniform float lamp_step = 0.25;
uniform float lamp_count = 24.0;
uniform vec4 lamp_color : source_color = vec4(1.0, 0.86, 0.68, 1.0);
instance uniform float pool_power = 0.0;   // 这一圈灯此刻的平均亮度 × 强度（近处几圈有真灯，是 0）
instance uniform float ring_phase = 0.0;   // 这一圈的灯整体错开了几盏（0~1）

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

// 周期为 1、每个周期开头 d 那一段是“杆”的方波，在 [x - w/2, x + w/2] 上的平均值（盒式滤波，远了自然变成 d）
float bar_cover(float x, float w, float d) {
	w = max(w, 1e-4);
	float x0 = x - 0.5 * w;
	float x1 = x + 0.5 * w;
	float i1 = floor(x1) * d + min(fract(x1), d);
	float i0 = floor(x0) * d + min(fract(x0), d);
	return clamp((i1 - i0) / w, 0.0, 1.0);
}

void fragment() {
	vec3 p = p_obj;
	float r = length(p.xz);
	// 方位角取 0~2π：横杆、拼缝的接缝落在方位角 0，那里是电梯导轨的缺口，没有格栅
	float ang = atan(p.z, p.x);
	ang += ang < 0.0 ? TAU : 0.0;
	float u = r / bar_pitch;                    // 承载扁钢：沿半径一根根排
	float v = ang * radius / cross_pitch;       // 横杆：沿弧一根根排
	float wu = fwidth(u) * 1.4;
	float wv = fwidth(v) * 1.4;
	// 扁钢有 45 毫米高、横杆 20 毫米：斜着看，杆的侧面把缝挡住一大半，越斜越不透（掠射时就是一块实板）
	vec3 vw = normalize((INV_VIEW_MATRIX * vec4(VIEW, 0.0)).xyz);
	vec2 radial = normalize(p.xz);
	vec2 tangent = vec2(-radial.y, radial.x);
	float vy = max(abs(vw.y), 0.05);
	float tr = abs(dot(vw.xz, radial)) / vy;
	float tt = abs(dot(vw.xz, tangent)) / vy;
	float bu = bar_cover(u, wu, min((bar_width + 0.045 * tr) / bar_pitch, 1.0));
	float bv = bar_cover(v, wv, min((cross_width + 0.02 * tt) / cross_pitch, 1.0));
	float steel = 1.0 - (1.0 - bu) * (1.0 - bv);
	float side = 1.0 - step(0.5, abs(n_obj.y));
	// 格子小到一个像素装好几格时，镂空改成实心（颜色按钢的比例压暗，像看着一片半透的灰）
	float far = smoothstep(0.25, 0.6, max(wu, wv * 0.3));
	float alpha = max(mix(steel, 1.0, far), side);
	ALPHA = alpha;
	ALPHA_SCISSOR_THRESHOLD = 0.5;
	ALPHA_ANTIALIASING_EDGE = 0.25;

	// 锌面：一块块格栅板（每块约一米）深浅略有不同，板上很淡的起伏、零星发白的锌锈；锈从格子交叉点往外长
	float sv = ang * radius / 0.98;
	float panel = hash13(vec3(floor(sv), 3.0, 7.0));
	float big = vnoise(p * 1.7);
	float n2 = vnoise(p * 9.0 + 3.0);
	vec3 col = paint_color.rgb * (0.88 + 0.18 * panel + 0.08 * big);
	col = mix(col, vec3(0.6, 0.6, 0.58), smoothstep(0.72, 0.95, vnoise(p * 7.0 + 5.0)) * 0.2);
	float rust = smoothstep(0.62, 0.9, vnoise(p * 4.0 + 7.0) * 0.7 + bu * bv * 0.3);
	col = mix(col, rust_color.rgb, rust * 0.25);
	// 一块块格栅板之间的拼缝，远看也看得出走台是一块块拼起来的
	float sw = max(0.03, fwidth(sv) * 2.0);
	float top = step(0.5, n_obj.y);
	float seam = smoothstep(1.0 - sw, 1.0, abs(fract(sv) - 0.5) * 2.0) * min(0.06 / sw, 1.0);
	col *= 1.0 - 0.6 * seam * top;
	// 中间一条被踩亮（只在顶面的扁钢顶上）
	float mid = 1.0 - smoothstep(0.12, 0.42, abs(r - (radius - 0.8)));
	// 顺着走的方向一道道被鞋底磨亮的扁钢顶（顺着弧拉长的噪声，远看是一条略亮的带子，不是一块块斑）
	float path = vnoise(vec3(ang * radius * 0.6, r * 14.0, 0.0));
	float worn = top * mid * (0.35 + 0.65 * path) * (1.0 - far * 0.5);
	col = mix(col, worn_color.rgb, worn * 0.45);
	// 靠井壁那一侧结霜（顶面、包边上都有）
	float frost = smoothstep(radius - 0.45, radius - 0.08, r) * smoothstep(0.45, 0.8, vnoise(p * 6.0 + 11.0) * 0.7 + 0.4 * n2);
	col = mix(col, frost_color.rgb, frost * 0.6);
	col *= mix(1.0, 0.6, far * (1.0 - side));
	ALBEDO = col;
	METALLIC = mix(0.25, 0.7, worn) * (1.0 - frost);
	ROUGHNESS = mix(mix(0.6, 0.32, worn), 0.8, frost);
	SPECULAR = 0.5;

	// 法线：看到的钢里顶面占多少、扁钢侧面占多少、横杆侧面占多少，按比例把法线往朝着镜头的那个侧面歪
	if (side < 0.5) {
		float face = sign(n_obj.y);             // 顶面 +1，底面 -1
		float w_top = bar_width / bar_pitch + cross_width / cross_pitch;
		float w_u = min(0.045 * tr / bar_pitch, 1.0);
		float w_v = min(0.02 * tt / cross_pitch, 1.0) * 0.5;
		vec3 nu = vec3(radial.x, 0.0, radial.y) * sign(dot(vw.xz, radial));
		vec3 nv = vec3(tangent.x, 0.0, tangent.y) * sign(dot(vw.xz, tangent));
		vec3 nw = normalize(vec3(0.0, face, 0.0) * w_top + nu * w_u + nv * w_v);
		NORMAL = normalize(mix(NORMAL, (VIEW_MATRIX * vec4(nw, 0.0)).xyz, 0.7));
	}

	// 远处几圈：头顶扶手上那圈灯照在格栅上的光斑（点光源照水平面：E ∝ h / d³）
	if (pool_power > 0.0 && n_obj.y > 0.5) {
		float idx = (ang - lamp_start) / lamp_step - ring_phase;
		float j = clamp(floor(idx + 0.5), 0.0, lamp_count - 1.0);
		float la = lamp_start + lamp_step * (j + ring_phase);
		vec3 lp = vec3(lamp_r * cos(la), lamp_h, lamp_r * sin(la));
		vec3 d = lp - p;
		float dl = length(d);
		float e = lamp_h / (dl * dl * dl);
		// 两边相邻的两盏也照一点
		for (float s = -1.0; s <= 1.0; s += 2.0) {
			float lb = la + lamp_step * s;
			vec3 d2 = vec3(lamp_r * cos(lb), lamp_h, lamp_r * sin(lb)) - p;
			float l2 = length(d2);
			e += lamp_h / (l2 * l2 * l2);
		}
		EMISSION = col * lamp_color.rgb * pool_power * e;
	}
}
