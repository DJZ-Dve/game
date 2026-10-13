// 扎穿艇壳的那根骨刺（breach.gd 生成的弯锥：UV.y 从根 0 到尖 1，UV.x 绕一圈）。
// 外面那东西还没做，这只是一截占位：发黑、带油光的角质，顺着长度一道道细棱，越往尖越磨得发白发亮，尖上崩了几个小口。
shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_back, diffuse_burley, specular_schlick_ggx;

varying float along;

float hash12(vec2 p) {
	vec3 q = fract(vec3(p.xyx) * 0.1031);
	q += dot(q, q.yzx + 33.33);
	return fract((q.x + q.y) * q.z);
}

float vnoise(vec2 p) {
	vec2 i = floor(p);
	vec2 f = fract(p);
	f = f * f * (3.0 - 2.0 * f);
	return mix(mix(hash12(i), hash12(i + vec2(1, 0)), f.x), mix(hash12(i + vec2(0, 1)), hash12(i + vec2(1, 1)), f.x), f.y);
}

void vertex() {
	along = UV.y;
}

void fragment() {
	float ridge = vnoise(vec2(UV.x * 40.0, along * 3.0));
	float grain = vnoise(vec2(UV.x * 90.0, along * 60.0));
	vec3 base = mix(vec3(0.02, 0.017, 0.015), vec3(0.07, 0.05, 0.035), ridge * 0.6 + grain * 0.2);
	float worn = smoothstep(0.75, 0.99, along);
	ALBEDO = mix(base, vec3(0.42, 0.38, 0.32), worn * (0.6 + 0.4 * grain));
	ROUGHNESS = mix(0.22, 0.45, grain) + worn * 0.15;
	SPECULAR = 0.55;
}
