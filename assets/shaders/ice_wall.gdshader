// 冰井的井壁：掘进机钻出来的冰（物体空间坐标，井轴就是物体的 Y 轴）。
// 冰之所以像冰，靠的是“看得进去”：
// - 冰里的东西用实拍的湖冰（ambientCG Ice002 / Ice004，CC0）：照片里白色的裂面、气泡串只取明暗，
//   在三个深度各贴一层（尺度、方向都错开），按折射后的视线往冰里错开采样——换个角度看，几层互相错动；
//   越深吸收越多（absorb：红远大于蓝），所以越深越蓝，最深处剩 deep_color。照片本身偏绿，不用它的颜色。
// - 表面：大部分是刀具啃过的毛面（白偏灰、凹处透蓝；对照冰岛 Into the Glacier 人工冰隧道的照片），
//   毛面越厚越看不进去；两成左右被融水、升华磨光的地方湿亮透明，才看得见冰里；
// - 开凿痕迹：螺旋切削纹（刀盘一边转一边往下掘，纹距、深浅都不规则）、每节之间一道接缝、偶尔一道深刮痕；
// - 加热管两边化了又冻：最透；crack 随冰震从 0 涨到 1：一道道新裂纹（白的断面）。
// - 冰层：冰壳是一层层冻上来的，气泡多的白层、气泡少的清亮层交替，层面略倾斜，绕井一圈在井壁上起伏。
// - 霜晶闪点：冰面上的冰晶、新鲜断口是一片片小平面，灯照过来，朝向刚好对上的那几片闪一下（light() 里按半向量算）。
// 细的东西（节缝、刮痕、切削纹、裂纹）都按一个像素有多宽来画：小于像素时变宽、变淡（总量不变），远处不闪成虚线。
// 灯照在身后的冰上：每段井壁（两圈走台中间切开）正好对应一圈灯，这圈 24 盏灯照在冰上的那一圈暖光在这里算
// （真的灯光只往下照走台；每盏都加一个照冰的光源太多了）。走台面以下被格栅、梁挡住，淡掉。
// 每圈的深度标记（「R07 / -84 m」）：模板喷漆直接喷在这圈走台面上方的冰上，绕井几处各一条。
// 圈号、深度按这段井壁的 ring_y 算（第 n 圈走台面在 y = -n × ring_step），字形是距离场（tools/gen_stencil_glyphs.py）。
// 旧了：字边被磨得深一块浅一块、一片片漆皮剥掉露出冰、冰里冻出来的霜盖住一块块；漆是不透光的，那里不往外透蓝光。
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
uniform float translucency = 0.7;   // 光钻进冰里再透出来的那部分（见 light()）
uniform vec4 glow_color : source_color = vec4(0.42, 0.72, 1.0, 1.0);
uniform float strata_amount : hint_range(0.0, 1.0) = 0.5;
uniform float glint_amount = 80.0;     // 闪点有多亮
uniform float glint_density = 0.8;     // 多少格子里有一颗朝向能闪的冰晶
uniform float glint_cell = 0.006;      // 最细一级的格子多大（米）；远处按像素放大（至少六个像素一格）
uniform float glint_sharp = 900.0;     // 冰晶面越平，闪点越尖、越少

// 这段井壁对应的那圈灯：灯挂在半径 lamp_r、走台面上方 lamp_h 处，第 j 盏在方位角 lamp_start + lamp_step * (j + ring_phase)
uniform float lamp_r = 9.38;
uniform float lamp_h = 1.24;
uniform float lamp_start = 0.14;
uniform float lamp_step = 0.25;
uniform float lamp_count = 24.0;
uniform vec4 lamp_color : source_color = vec4(1.0, 0.86, 0.68, 1.0);
instance uniform float ring_y = 0.0;       // 这圈走台面的高度（世界坐标）
instance uniform float ring_phase = 0.0;   // 这圈的灯整体错开了几盏（0~1）
instance uniform float ring_power = 0.0;   // 这圈灯此刻的平均亮度 × 强度

// 深度标记
uniform sampler2D stencil_glyphs : hint_default_black, filter_linear_mipmap, repeat_disable;
uniform vec4 stencil_paint : source_color = vec4(0.045, 0.045, 0.05, 1.0);   // 黑漆
uniform vec4 frost_color : source_color = vec4(0.8, 0.86, 0.9, 1.0);         // 盖在漆上的霜
uniform float stencil_cap = 0.42;         // 大写高（米）
uniform float stencil_base = 1.25;        // 基线在走台面上方多高
uniform vec4 stencil_angles = vec4(2.06, 3.14, 4.46, 5.62);   // 每圈喷在哪几个方位角（一条字的正中）
uniform float ring_step = 12.0;
// 字形图集（tools/gen_stencil_glyphs.py）：4×4 格、每格 128 像素，笔的起点在格子左边 16、基线在上边往下 100，
// 1 em = 100 像素，距离场覆盖字边内外各 10 像素（所以每 em 距离场变 5）。字宽按 em（那个脚本打印的），顺序 0123456789R/-m+.
const float STENCIL_ADV[16] = float[16](0.599, 0.599, 0.599, 0.599, 0.599, 0.599, 0.599, 0.599, 0.599, 0.599,
	0.695, 0.386, 0.376, 0.974, 0.599, 0.339);
const float STENCIL_SPACE = 0.228;
const float STENCIL_CAP_EM = 0.76;
const float STENCIL_TRACK = 0.07;         // 一块块字模拼着喷，字距比排版的松一点

varying vec3 p_obj;
// 霜晶闪点：两级格子（远近之间渐变）各一片冰晶面的法线（视图空间）和权重
varying vec3 g_n0;
varying vec3 g_n1;
varying vec2 g_w;
varying float paint_v;   // 这里有多少是漆（不透光：light() 里不加透出来的蓝光）

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

// 一条宽 w（和 x 同单位）的细线，像素宽 px：线比像素细时画成一个像素宽、按比例变淡（远看总量不变，不断成虚线）
float thin_line(float x, float w, float px) {
	float ww = max(w, px * 1.5);
	return (1.0 - smoothstep(0.0, ww, abs(x))) * (w / ww);
}

// 格子 cell 里那片冰晶面的法线：围着表面法线 n 随机歪 0~spread 弧度（n 和结果都在视图空间）
vec3 glint_facet(vec3 cell, vec3 n, float spread) {
	float h1 = hash13(cell + 17.31);
	float h2 = hash13(cell + 41.73);
	vec3 t = normalize(cross(n, abs(n.y) < 0.9 ? vec3(0.0, 1.0, 0.0) : vec3(1.0, 0.0, 0.0)));
	vec3 b = cross(n, t);
	float phi = TAU * h2;
	return normalize(n + (t * cos(phi) + b * sin(phi)) * tan(spread * sqrt(h1)));
}

// 第 n 圈深度标记「R07 / -84 m」的第 c 个字：图集里第几格；-1 = 空格，-2 = 写完了
int stencil_char(int n, int c) {
	if (c == 0) {
		return 10;
	}
	if (c == 1) {
		return (n / 10) % 10;
	}
	if (c == 2) {
		return n % 10;
	}
	if (c == 3 || c == 5) {
		return -1;
	}
	if (c == 4) {
		return 11;
	}
	int depth = n * int(ring_step + 0.5);
	int k = c - 6;
	if (depth > 0) {
		if (k == 0) {
			return 12;
		}
		k -= 1;
	}
	int nd = depth >= 100 ? 3 : (depth >= 10 ? 2 : 1);
	if (k < nd) {
		int div = k == nd - 1 ? 1 : (k == nd - 2 ? 10 : 100);
		return (depth / div) % 10;
	}
	if (k == nd) {
		return -1;
	}
	return k == nd + 1 ? 13 : -2;
}

float stencil_adv(int g) {
	return (g >= 0 ? STENCIL_ADV[g] : STENCIL_SPACE) + STENCIL_TRACK;
}

// 一条标记的距离场（0.5 = 字边，往字里变大）。luv：从这条字的正中、基线量起（em，往右、往上）；
// gx、gy：luv 的屏幕导数（每个字只是平移，所以共用一组；由分支外面求好的 dFdx(p)、dFdy(p) 换算）
float stencil_sdf(int n, vec2 luv, vec2 gx, vec2 gy) {
	float w = -STENCIL_TRACK;
	for (int c = 0; c < 14; c++) {
		int g = stencil_char(n, c);
		if (g == -2) {
			break;
		}
		w += stencil_adv(g);
	}
	float pen = -0.5 * w;
	float sd = 0.0;
	for (int c = 0; c < 14; c++) {
		int g = stencil_char(n, c);
		if (g == -2) {
			break;
		}
		// 字格里的像素坐标；字的墨迹都在格子里，出了格子就是字外（不去采隔壁的格子）
		vec2 cp = vec2(16.0 + (luv.x - pen) * 100.0, 100.0 - luv.y * 100.0);
		if (g >= 0 && all(greaterThan(cp, vec2(1.0))) && all(lessThan(cp, vec2(127.0)))) {
			vec2 cell = vec2(float(g % 4), float(g / 4)) * 128.0;
			vec2 duv = vec2(100.0, -100.0) / 512.0;
			sd = max(sd, textureGrad(stencil_glyphs, (cell + cp) / 512.0, gx * duv, gy * duv).r);
		}
		pen += stencil_adv(g);
	}
	return sd;
}

void fragment() {
	vec3 p = p_obj;
	// 方位角取 0~2π：展开图的接缝落在方位角 0，正好藏在电梯导轨的安装底板后面
	float ang = atan(p.z, p.x);
	ang += ang < 0.0 ? TAU : 0.0;
	float s = ang * radius;   // 沿井壁的弧长
	vec2 uv = vec2(s, p.y);
	float big = fbm(p * 0.3);
	// 一个像素在井壁上有多宽（米）
	vec3 dpx = dFdx(p);
	vec3 dpy = dFdy(p);
	float px = max(length(dpx), length(dpy));

	// ---- 开凿痕迹（只在表面）
	// 螺旋切削纹：沿着螺旋线量高度，纹距被噪声扭得不太规整，每道深浅不一
	float helix = p.y + ang / TAU * groove_pitch * 3.0 + (vnoise(vec3(p.x * 0.15, p.y * 0.4, p.z * 0.15)) - 0.5) * 0.25;
	float gpos = helix / groove_pitch;
	float gid = floor(gpos);
	float gph = fract(gpos);
	float gdepth = 0.2 + 0.8 * hash11(gid + floor(s / 7.0) * 13.0);
	// 纹距小到两三个像素时换成平均值（不然远处起摩尔纹）
	float gfar = smoothstep(0.15, 0.4, px / groove_pitch);
	float groove = mix(1.0 - pow(abs(2.0 * gph - 1.0), 1.4), 0.58, gfar);
	// 刀齿刮出的细纹（顺着切削方向，一段一段，很淡）
	float scratch = mix(pow(0.5 + 0.5 * sin(helix * TAU / 0.045 + vnoise(p * vec3(1.5, 12.0, 1.5)) * 5.0), 6.0), 0.23,
		smoothstep(0.006, 0.02, px)) * smoothstep(0.45, 0.75, vnoise(vec3(s * 0.6, gid * 3.1, 0.0)));
	// 偶尔一道深的刮痕（刀齿崩了一颗）
	float gouge = thin_line(gph - 0.5, 0.05, px / groove_pitch) * step(0.93, hash11(gid * 3.7 + floor(s / 3.0))) * (1.0 - gfar);
	// 节缝
	float lph = fract(p.y / lift);
	float seam = thin_line(min(lph, 1.0 - lph) * lift, 0.015, px);

	// ---- 表面：毛面还是镜面
	// 大部分是刀具啃过的毛面；一部分被融水、升华磨光了，透亮、看得进去
	// 磨光透亮的地方顺着融水往下流的方向长：竖着的一道道，上宽下窄、断断续续
	float melt = fbm(vec3(s * 1.1, p.y * 0.07, 0.0) + vec3(0.0, 0.0, 3.0)) + (vnoise(p * vec3(0.4, 0.9, 0.4)) - 0.5) * 0.25;
	float milk = (1.0 - smoothstep(0.58, 0.8, melt) * 0.75) * milk_amount;
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
	// 冰层：层面朝一边倾斜几度、带点起伏（绕井一圈在井壁上是一道道起伏的带子）；气泡多的层白、散射多，
	// 气泡少的层清亮、看得更深、更蓝
	float sy = p.y + dot(p.xz, vec2(0.11, -0.06)) + (fbm(p * vec3(0.12, 0.05, 0.12)) - 0.5) * 2.0;
	float strata = vnoise(vec3(sy * 0.8, 3.7, 1.3)) * 0.65 + vnoise(vec3(sy * 2.9, 8.1, 5.2)) * 0.35;
	float bubbly = mix(0.5, smoothstep(0.3, 0.72, strata), strata_amount);
	vec3 inside = scatter_color.rgb * (l1 * t1 * 1.1 + l2 * t2 * 0.85 * (1.0 - l1 * 0.6) + l3 * t3 * 0.7 * (1.0 - l2 * 0.5))
		* mix(0.55, 1.35, bubbly)
		+ deep_color.rgb * exp(-absorb * 0.8) * mix(5.0, 3.0, bubbly);

	// ---- 冰震的新裂纹：白的断面
	vec2 cuv = uv * vec2(0.22, 0.13) + vec2(fbm(p * 1.3), fbm(p * 1.3 + 11.0)) * 0.9;
	vec2 ce = voronoi(cuv);
	float line = thin_line(ce.x, 0.012 + 0.012 * vnoise(p * 30.0), px * 0.2);
	float cracked = line * step(ce.y, crack * 0.4 - 0.02);

	// 毛面：乳白，大尺度上借一点照片的明暗打破均匀；切削纹的凹处透蓝
	float lbig = ice_layer(ice_b, uv, 6.0, 0.6);
	// 冰晶的晶界在毛面上也看得出来（钻开的冰壁上，一颗颗冰晶的边界会被刮得更白）
	float grain = ice_layer(ice_a, uv, 0.7, 0.4);
	vec3 milky = milk_color.rgb * (0.78 + 0.12 * big + 0.1 * lbig + 0.22 * grain + 0.04 * scratch) * mix(0.93, 1.06, bubbly);
	milky = mix(milky, cavity_color.rgb, clamp((1.0 - groove) * gdepth * 0.45 + seam * 0.5, 0.0, 1.0));
	vec3 col = mix(inside * 1.4, milky, milk);
	col = mix(col, vec3(0.95, 0.98, 1.0), cracked * 0.9);

	// ---- 这圈的深度标记：先按高度筛（绝大多数像素到这里就跳过），再找离哪条字最近（按方位角），
	// 量到那条字的正中、基线（em）。分支里不能求导（各像素走的路不一样），字形用 textureGrad 采，
	// 导数按分支外面求好的 dFdx(p)、dFdy(p) 换算（方位角 atan(z, x) 的微分是 (x dz - z dx) / (x² + z²)）
	float rel = p.y - ring_y;
	float em = stencil_cap / STENCIL_CAP_EM;
	float paint = 0.0;
	float pfrost = 0.0;
	int ring_no = int(round(-ring_y / ring_step));
	float lv = (rel - stencil_base) / em;
	if (lv > -0.3 && lv < 1.0 && ring_no >= 0) {
		float da = 10.0;
		for (int i = 0; i < 4; i++) {
			float d = mod(ang - stencil_angles[i] + PI, TAU) - PI;
			da = abs(d) < abs(da) ? d : da;
		}
		vec2 luv = vec2(da * radius / em, lv);
		float rr = dot(p.xz, p.xz);
		vec2 lgx = vec2((p.x * dpx.z - p.z * dpx.x) / rr * radius, dpx.y) / em;
		vec2 lgy = vec2((p.x * dpy.z - p.z * dpy.x) / rr * radius, dpy.y) / em;
		float sd = abs(luv.x) < 3.8 ? stencil_sdf(ring_no, luv, lgx, lgy) : 0.0;
		if (sd > 0.2) {   // 字上、字边上（飞边伸到字外 0.06 em）
			// 抗锯齿：距离场每 em 变 5，一个像素宽是多少（字小到几个像素时边自然变虚）
			float aa = 3.8 * max(length(lgx), length(lgy)) + 0.01;
			// 字边深一块浅一块：喷得不匀，边上的漆磨掉一些
			float wob = vnoise(p * 26.0) * 0.6 + vnoise(p * 70.0) * 0.4;
			float edge = 0.5 + (wob - 0.5) * 0.16;
			float cov = smoothstep(edge - aa, edge + aa, sd);
			// 飞边：字模边上漏出去的雾点。冰面不平，字模贴不严，有的地方漏得多、漏得远（远了看不出一粒粒，就是一圈淡灰）
			float leak = smoothstep(0.35, 0.75, vnoise(p * 5.0 + 40.0));
			float speck = mix(step(0.62, hash13(floor(p * 500.0))), 0.38, smoothstep(0.0015, 0.004, px));
			float over = smoothstep(0.42 - 0.2 * leak, 0.5, sd) * (1.0 - cov) * speck * (0.25 + 0.45 * leak);
			// 一片片漆皮翘起来剥掉，露出底下的冰（越靠字边剥得越多；剥口的边是碎的）
			float peel = vnoise(p * vec3(9.0, 13.0, 9.0) + 5.0) * 0.6 + vnoise(p * 33.0 + 9.0) * 0.28 + vnoise(p * 95.0) * 0.12;
			cov *= 1.0 - smoothstep(0.6, 0.64, peel + (0.6 - sd) * 0.3);
			paint = clamp(cov + over, 0.0, 1.0);
			// 漆褪色发灰；冰里冻出来的霜从冰面往外长：整片罩一层薄的，一块块厚的（切削纹凹处先长）
			float fr = vnoise(p * vec3(4.0, 6.0, 4.0) + 21.0) * 0.6 + vnoise(p * 19.0 + 3.0) * 0.4;
			pfrost = smoothstep(0.5, 0.78, fr + (1.0 - groove) * gdepth * 0.12);
			vec3 pc = mix(stencil_paint.rgb, vec3(0.16, 0.16, 0.17), smoothstep(0.3, 0.9, big) * 0.6);
			pc = mix(pc, frost_color.rgb, pfrost * 0.8 + 0.12);
			col = mix(col, pc, paint);
		}
	}
	paint_v = paint;

	ALBEDO = col;
	ROUGHNESS = mix(mix(0.05, 0.48, milk) - scratch * 0.08 * milk + gouge * 0.2, mix(0.6, 0.85, pfrost), paint);
	SPECULAR = 0.5;
	METALLIC = 0.0;
	SSS_STRENGTH = sss * (0.5 + 0.5 * milk) * (1.0 - paint);

	// 凹凸是按 2×2 像素块求导的：只有几个像素宽的细线（节缝、深刮痕、裂纹、刀纹）会被导数切成一段段，离远了不进凹凸，只留颜色
	float thin = 1.0 - smoothstep(0.004, 0.012, px);
	float h = groove * gdepth * 0.15 * (1.0 - gfar) + grain * 0.12 + big * 0.6 - (seam * 0.8 + gouge * 0.6 + cracked * 0.3) * thin
		+ scratch * 0.04 * thin + l1 * 0.05 * (1.0 - milk);
	NORMAL = bump_normal(NORMAL, VERTEX, h * 0.022 * bump_strength);

	// ---- 霜晶闪点：格子按像素大小分级（至少六个像素一格），相邻两级按距离渐变；每格里一颗冰晶，
	// 在格子里随机的一点、一两个像素大的圆点（不是整格亮，不然是一个个小方块）。
	// 毛面上（刮开的冰晶、结的霜）和新裂开的断口上才有；离远了一格比一颗冰晶大得多，淡掉
	float lod = log2(max(px * 6.0, glint_cell) / glint_cell);
	float l0 = floor(lod);
	float c0 = glint_cell * exp2(l0);
	vec3 id0 = floor(p / c0);
	vec3 id1 = floor(p / (c0 * 2.0)) + 1000.0;
	vec3 s0 = (id0 + 0.25 + 0.5 * vec3(hash13(id0 + 1.3), hash13(id0 + 2.9), hash13(id0 + 4.1))) * c0;
	vec3 s1 = (id1 - 1000.0 + 0.25 + 0.5 * vec3(hash13(id1 + 1.3), hash13(id1 + 2.9), hash13(id1 + 4.1))) * c0 * 2.0;
	float dot0 = 1.0 - smoothstep(0.08, 0.2, length(p - s0) / c0);
	float dot1 = 1.0 - smoothstep(0.08, 0.2, length(p - s1) / (c0 * 2.0));
	g_n0 = glint_facet(id0, NORMAL, 0.7);
	g_n1 = glint_facet(id1, NORMAL, 0.7);
	float gm = (milk * 0.85 + cracked + 0.1) * (1.0 - smoothstep(0.004, 0.012, px)) * (1.0 - paint * (1.0 - pfrost));
	g_w = vec2(step(hash13(id0 + 5.17), glint_density) * dot0 * (1.0 - fract(lod)),
		step(hash13(id1 + 5.17), glint_density) * dot1 * fract(lod)) * gm;

	// ---- 这圈灯照在冰上：最近的三盏，点光源照一个面（按凹凸以后的法线算 cos / d²，切削纹、台阶都显得出来）；
	// 冰会把光吃进去再散出来，稍微背光的地方也亮一点点
	if (ring_power > 0.0 && abs(rel) < 6.0) {
		float idx = (ang - lamp_start) / lamp_step - ring_phase;
		float j0 = clamp(floor(idx + 0.5), 0.0, lamp_count - 1.0);
		float e = 0.0;
		float gl = 0.0;   // 灯照过来的霜晶闪点
		for (float dj = -1.0; dj <= 1.0; dj += 1.0) {
			float j = j0 + dj;
			if (j < 0.0 || j > lamp_count - 1.0) {
				continue;
			}
			float la = lamp_start + lamp_step * (j + ring_phase);
			vec3 d = vec3(lamp_r * cos(la), ring_y + lamp_h, lamp_r * sin(la)) - p;
			float dl2 = dot(d, d);
			vec3 dv = normalize((VIEW_MATRIX * vec4(d, 0.0)).xyz);
			float c = dot(NORMAL, dv);
			e += (max(c, 0.0) + 0.08 * clamp(c + 0.5, 0.0, 1.0)) / dl2;
			vec3 hv = normalize(dv + VIEW);
			gl += (g_w.x * pow(max(dot(g_n0, hv), 0.0), glint_sharp) + g_w.y * pow(max(dot(g_n1, hv), 0.0), glint_sharp))
				* max(c, 0.0) / dl2;
		}
		// 走台面以下被格栅、梁挡住；离开这段井壁的两头淡掉（和上下两段接上，没有缝）
		float fade = smoothstep(-0.5, 0.05, rel) * (1.0 - smoothstep(2.5, 4.5, abs(rel)));
		EMISSION = (ALBEDO * (lamp_color.rgb + glow_color.rgb * translucency * 0.25 * (1.0 - paint)) * e + lamp_color.rgb * gl * glint_amount)
			* ring_power * fade;
	}
}

// 冰的光照：表面的漫反射 + 光钻进冰里散开再透出来的蓝光。洗墙灯几乎贴着冰面掠过去，只算表面的话
// 冰面大半是暗的（像石板）；冰会把照进去的光在里面散开，灯照到的那一片整片往外透蓝光，
// 掠射、甚至稍微背着光的地方也亮（包裹光照，颜色往蓝偏：红光在冰里走不远）。高光按 GGX 自己算
void light() {
	float ndl = dot(NORMAL, LIGHT);
	vec3 lc = LIGHT_COLOR * ATTENUATION / PI;
	DIFFUSE_LIGHT += lc * max(ndl, 0.0);
	float wrap = clamp((ndl + 0.7) / 1.7, 0.0, 1.0);
	DIFFUSE_LIGHT += lc * wrap * wrap * glow_color.rgb * translucency * (1.0 - paint_v);
	vec3 h = normalize(LIGHT + VIEW);
	float ndh = max(dot(NORMAL, h), 0.0);
	float a = max(ROUGHNESS * ROUGHNESS, 0.002);
	float a2 = a * a;
	float d = ndh * ndh * (a2 - 1.0) + 1.0;
	float dd = a2 / (PI * d * d);
	float ndv = max(dot(NORMAL, VIEW), 1e-3);
	float nl = max(ndl, 0.0);
	float k = a * 0.5;
	float vis = 0.25 / ((nl * (1.0 - k) + k) * (ndv * (1.0 - k) + k));
	float f = 0.02 + 0.98 * pow(1.0 - max(dot(VIEW, h), 0.0), 5.0);
	SPECULAR_LIGHT += LIGHT_COLOR * ATTENUATION * nl * dd * vis * f;
	// 霜晶闪点：半向量正好对上这一格冰晶面的法线时闪一下
	if (g_w.x + g_w.y > 0.0) {
		float g = g_w.x * pow(max(dot(g_n0, h), 0.0), glint_sharp) + g_w.y * pow(max(dot(g_n1, h), 0.0), glint_sharp);
		SPECULAR_LIGHT += LIGHT_COLOR * ATTENUATION * nl * g * glint_amount;
	}
}
