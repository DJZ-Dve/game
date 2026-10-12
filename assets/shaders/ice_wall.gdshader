// 冰井的井壁：掘进机钻出来的冰（物体空间坐标，井轴就是物体的 Y 轴）。
// 冰之所以像冰，靠的是“看得进去”：
// - 冰里的东西用实拍的湖冰（ambientCG Ice002 / Ice004，CC0）：照片里白色的裂面、气泡串只取明暗，
//   在三个深度各贴一层（尺度、方向都错开），按折射后的视线往冰里错开采样——换个角度看，几层互相错动；
//   越深吸收越多（absorb：红远大于蓝），所以越深越蓝，最深处剩 deep_color。照片本身偏绿，不用它的颜色。
// - 表面：大部分是刀具啃过的毛面（白偏灰、凹处透蓝；对照冰岛 Into the Glacier 人工冰隧道的照片），
//   毛面越厚越看不进去；两成左右被融水、升华磨光的地方湿亮透明，才看得见冰里；
// - 开凿痕迹：螺旋切削纹（刀盘一边转一边往下掘，纹距、深浅都不规则）、每节之间一道接缝、偶尔一道深刮痕；
// - 加热管两边化了又冻：最透；crack 随冰震从 0 涨到 1：一道道新裂纹（白的断面）。
shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_back, diffuse_burley, specular_schlick_ggx;

uniform sampler2D ice_a : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D ice_b : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform float radius = 11.0;
uniform vec4 milk_color : source_color = vec4(0.68, 0.8, 0.88, 1.0);     // 刀具啃过的毛冰面
uniform vec4 cavity_color : source_color = vec4(0.3, 0.58, 0.74, 1.0);   // 切削纹凹处透出来的蓝
uniform vec4 scatter_color : source_color = vec4(0.82, 0.92, 1.0, 1.0);  // 冰里的裂面、气泡散射回来的光
uniform vec4 deep_color : source_color = vec4(0.03, 0.17, 0.3, 1.0);     // 看到最深处剩下的颜色
uniform vec3 absorb = vec3(2.6, 0.7, 0.22);    // 每米吸收（红、绿、蓝；按真实的冰放大了好几倍，几十厘米就看得出蓝）
uniform vec2 layer_contrast = vec2(0.4, 0.72);  // 照片明暗映射到“有多少东西”的区间（暗的湖底 → 0，白的裂面 → 1）
uniform float milk_amount : hint_range(0.0, 1.0) = 0.8;
uniform float groove_pitch = 0.45;
uniform float lift = 3.0;
uniform vec3 pipe_angles = vec3(1.05, 2.62, 5.06);
uniform float wet_width = 0.6;
uniform float crack : hint_range(0.0, 1.0) = 0.0;
uniform float bump_strength = 1.0;
uniform float sss = 0.25;

varying vec3 p_obj;

void vertex() {
	p_obj = VERTEX;
}

float hash11(float x) {
	return fract(sin(x * 127.1) * 43758.5453);
}

float hash13(vec3 p) {
	p = fract(p * 0.1031);
	p += dot(p, p.zyx + 31.32);
	return fract((p.x + p.y) * p.z);
}

vec2 hash22(vec2 p) {
	vec3 q = fract(vec3(p.xyx) * vec3(0.1031, 0.1030, 0.0973));
	q += dot(q, q.yzx + 33.33);
	return fract((q.xx + q.yz) * q.zy);
}

float vnoise(vec3 p) {
	vec3 i = floor(p);
	vec3 f = fract(p);
	f = f * f * (3.0 - 2.0 * f);
	float a = mix(mix(hash13(i), hash13(i + vec3(1, 0, 0)), f.x), mix(hash13(i + vec3(0, 1, 0)), hash13(i + vec3(1, 1, 0)), f.x), f.y);
	float b = mix(mix(hash13(i + vec3(0, 0, 1)), hash13(i + vec3(1, 0, 1)), f.x), mix(hash13(i + vec3(0, 1, 1)), hash13(i + vec3(1, 1, 1)), f.x), f.y);
	return mix(a, b, f.z);
}

float fbm(vec3 p) {
	float s = 0.0;
	float a = 0.5;
	for (int i = 0; i < 5; i++) {
		s += a * vnoise(p);
		p = p * 2.03 + vec3(17.1, 3.7, 9.2);
		a *= 0.5;
	}
	return s;
}

// 二维 voronoi：x = 到最近格子边界的距离，y = 这个格子的随机数
vec2 voronoi(vec2 x) {
	vec2 n = floor(x);
	vec2 f = fract(x);
	vec2 mg;
	vec2 mr;
	float md = 8.0;
	for (int j = -1; j <= 1; j++)
	for (int i = -1; i <= 1; i++) {
		vec2 g = vec2(float(i), float(j));
		vec2 r = g + hash22(n + g) - f;
		float d = dot(r, r);
		if (d < md) { md = d; mr = r; mg = g; }
	}
	md = 8.0;
	for (int j = -2; j <= 2; j++)
	for (int i = -2; i <= 2; i++) {
		vec2 g = mg + vec2(float(i), float(j));
		vec2 r = g + hash22(n + g) - f;
		if (dot(mr - r, mr - r) > 0.00001)
			md = min(md, dot(0.5 * (mr + r), normalize(r - mr)));
	}
	return vec2(md, hash22(n + mg).x);
}

// 屏幕空间的凹凸（Mikkelsen 2010）：按高度 h 的屏幕导数扭法线，不需要切线
vec3 bump_normal(vec3 n, vec3 pos, float h) {
	vec3 dpdx = dFdx(pos);
	vec3 dpdy = dFdy(pos);
	float dhdx = dFdx(h);
	float dhdy = dFdy(h);
	vec3 r1 = cross(dpdy, n);
	vec3 r2 = cross(n, dpdx);
	float det = dot(dpdx, r1);
	vec3 grad = sign(det) * (dhdx * r1 + dhdy * r2);
	return normalize(abs(det) * n - grad);
}

// 冰里某一层：照片的明暗 → 这一层有多少会把光散射回来的东西
float ice_layer(sampler2D tex, vec2 uv, float tile, float rot) {
	float c = cos(rot);
	float s = sin(rot);
	vec2 r = vec2(c * uv.x - s * uv.y, s * uv.x + c * uv.y) / tile;
	float l = dot(texture(tex, r).rgb, vec3(0.299, 0.587, 0.114));
	return smoothstep(layer_contrast.x, layer_contrast.y, l);
}

void fragment() {
	vec3 p = p_obj;
	float ang = atan(p.z, p.x);
	float s = ang * radius;   // 沿井壁的弧长
	vec2 uv = vec2(s, p.y);
	float big = fbm(p * 0.3);

	// ---- 开凿痕迹（只在表面）
	// 螺旋切削纹：沿着螺旋线量高度，纹距被噪声扭得不太规整，每道深浅不一
	float helix = p.y + ang / TAU * groove_pitch * 3.0 + (vnoise(vec3(s * 0.15, p.y * 0.4, 0.0)) - 0.5) * 0.25;
	float gpos = helix / groove_pitch;
	float gid = floor(gpos);
	float gph = fract(gpos);
	float gdepth = 0.2 + 0.8 * hash11(gid + floor(s / 7.0) * 13.0);
	float groove = 1.0 - pow(abs(2.0 * gph - 1.0), 1.4);
	// 刀齿刮出的细纹（顺着切削方向，一段一段，很淡）
	float scratch = pow(0.5 + 0.5 * sin(helix * TAU / 0.045 + vnoise(p * vec3(1.5, 12.0, 1.5)) * 5.0), 6.0)
		* smoothstep(0.45, 0.75, vnoise(vec3(s * 0.6, gid * 3.1, 0.0)));
	// 偶尔一道深的刮痕（刀齿崩了一颗）
	float gouge = (1.0 - smoothstep(0.0, 0.05, abs(gph - 0.5))) * step(0.93, hash11(gid * 3.7 + floor(s / 3.0)));
	// 节缝
	float lph = fract(p.y / lift);
	float seam = 1.0 - smoothstep(0.0, 0.015, min(lph, 1.0 - lph) * lift);

	// ---- 表面：毛面还是镜面
	// 大部分是刀具啃过的毛面；一部分被融水、升华磨光了，透亮、看得进去
	// 磨光透亮的地方顺着融水往下流的方向长：竖着的一道道，上宽下窄、断断续续
	float melt = fbm(vec3(s * 1.1, p.y * 0.07, 0.0) + vec3(0.0, 0.0, 3.0)) + (vnoise(p * vec3(0.4, 0.9, 0.4)) - 0.5) * 0.25;
	float milk = (1.0 - smoothstep(0.62, 0.72, melt) * 0.85) * milk_amount;
	float dmin = 1e3;
	for (int i = 0; i < 3; i++) {
		float da = abs(mod(ang - pipe_angles[i] + PI, TAU) - PI);
		dmin = min(dmin, da * radius);
	}
	float wet = 1.0 - smoothstep(wet_width * 0.35, wet_width, dmin + (fbm(p * 2.1) - 0.5) * 0.3);
	milk *= 1.0 - wet;
	milk = clamp(milk + seam * 0.3 + gouge * 0.3, 0.0, 1.0);

	// ---- 往冰里看：沿折射后的视线，在三个深度各取一层
	vec3 vw = normalize((INV_VIEW_MATRIX * vec4(VIEW, 0.0)).xyz);
	vec3 nw = normalize((INV_VIEW_MATRIX * vec4(NORMAL, 0.0)).xyz);
	vec3 rd = refract(-vw, nw, 1.0 / 1.31);
	if (dot(rd, rd) < 0.01) {
		rd = -nw;
	}
	vec3 tang = vec3(-sin(ang), 0.0, cos(ang));
	vec2 dir = vec2(dot(rd, tang), rd.y);   // 往里走一米，在井壁展开图上挪多少
	float l1 = ice_layer(ice_a, uv + dir * 0.06, 0.9, 0.0);
	float l2 = ice_layer(ice_b, uv + dir * 0.22, 1.7, 1.1);
	float l3 = ice_layer(ice_a, uv + dir * 0.5, 3.1, 2.3);
	vec3 t1 = exp(-absorb * 0.06);
	vec3 t2 = exp(-absorb * 0.22);
	vec3 t3 = exp(-absorb * 0.5);
	vec3 inside = scatter_color.rgb * (l1 * t1 * 1.1 + l2 * t2 * 0.85 * (1.0 - l1 * 0.6) + l3 * t3 * 0.7 * (1.0 - l2 * 0.5))
		+ deep_color.rgb * exp(-absorb * 0.8) * 4.0;

	// ---- 冰震的新裂纹：白的断面
	vec2 cuv = uv * vec2(0.22, 0.13) + vec2(fbm(p * 1.3), fbm(p * 1.3 + 11.0)) * 0.9;
	vec2 ce = voronoi(cuv);
	float line = 1.0 - smoothstep(0.0, 0.012 + 0.012 * vnoise(p * 30.0), ce.x);
	float cracked = line * step(ce.y, crack * 0.4 - 0.02);

	// 毛面：乳白，大尺度上借一点照片的明暗打破均匀；切削纹的凹处透蓝
	float lbig = ice_layer(ice_b, uv, 6.0, 0.6);
	// 冰晶的晶界在毛面上也看得出来（钻开的冰壁上，一颗颗冰晶的边界会被刮得更白）
	float grain = ice_layer(ice_a, uv, 0.7, 0.4);
	vec3 milky = milk_color.rgb * (0.78 + 0.12 * big + 0.1 * lbig + 0.22 * grain + 0.04 * scratch);
	milky = mix(milky, cavity_color.rgb, clamp((1.0 - groove) * gdepth * 0.45 + seam * 0.5, 0.0, 1.0));
	vec3 col = mix(inside, milky, milk);
	col = mix(col, vec3(0.95, 0.98, 1.0), cracked * 0.9);
	ALBEDO = col;
	ROUGHNESS = mix(0.05, 0.48, milk) - scratch * 0.08 * milk + gouge * 0.2;
	SPECULAR = 0.5;
	METALLIC = 0.0;
	SSS_STRENGTH = sss * (0.5 + 0.5 * milk);

	float h = groove * gdepth * 0.15 + grain * 0.12 + big * 0.6 - seam * 0.8 - gouge * 0.6 - cracked * 0.3 + scratch * 0.04 + l1 * 0.05 * (1.0 - milk);
	NORMAL = bump_normal(NORMAL, VERTEX, h * 0.022 * bump_strength);
}
