// 尼龙网兜：在旋转体网格上按「绕轴角度 ± 高度」画两组斜线，线以外的地方镂空。
// 网格没有 UV，用物体空间坐标 + 网兜中心（center，由 cockpit_props.gd 设置）来算。
shader_type spatial;
render_mode cull_disabled, diffuse_burley;

uniform vec4 color : source_color = vec4(0.75, 0.12, 0.04, 1.0);
uniform vec3 center = vec3(0.0);
uniform float strands = 14.0;      // 一圈多少根
uniform float pitch = 22.0;        // 每米高度上斜线走过多少圈
uniform float thread = 0.12;       // 线宽（占一格的比例）

varying vec3 obj_pos;

void vertex() {
	obj_pos = VERTEX;
}

void fragment() {
	vec3 q = obj_pos - center;
	float a = atan(q.z, q.x) / 6.2831853 * strands;
	float h = q.y * pitch;
	float u = fract(a + h);
	float v = fract(a - h);
	float line = min(min(u, 1.0 - u), min(v, 1.0 - v));
	// 网兜收口处线挤在一起：直接画实
	float neck = smoothstep(0.17, 0.2, q.y);
	if (line > thread && neck < 0.5) {
		discard;
	}
	ALBEDO = color.rgb;
	ROUGHNESS = 0.65;
	SPECULAR = 0.3;
}
