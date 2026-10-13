// 船员的头发（TressFX 发丝，addons/tressfx 插件画）：几何照抄插件的 addons/tressfx/shaders/tressfx_strand.gdshader
// （vertex() 一样：一根发丝一条对着相机的面片，宽度按像素算），打光换掉。插件那份的 Kajiya-Kay 高光绕着发丝一圈都一样亮、
// 又宽，黑发整头照成银灰；压窄压暗以后红棕、金发又没了光泽——毛病在模型本身，调参数顾此失彼。
// 这里换成 Marschner 的三条光路（Karis 2016《Physically Based Hair Shading in Unreal》，UE 的 HairBsdf）：
//   R   发丝表面直接反射：白色，和发色无关；纵向一条窄高斯（顺着发丝方向只在镜面角附近亮），方位上朝光源那边亮、
//       绕到背光那边没有——所以只在头上一条带子里亮，不会整头发灰。角质层是斜着叠的，高光往发根偏一点
//   TT  穿过发丝从另一边出来：逆光时轮廓透光，颜色是发丝吸收以后剩下的
//   TRT 钻进去在里面反射一次再出来：带发色的第二道高光，比 R 宽、往发梢偏
// 再加一层“多次散射”：光在一团头发里来回散射以后透出来的颜色。金发、红发的颜色主要靠它，黑发几乎没有。
// 发色先换算成发丝的吸收系数（Chiang 2016 的拟合，UE 的 HairColorToAbsorption 同一个），所以一套参数从黑发到金发都能用：
// 黑发吸收强，TT、TRT、多次散射都弱，剩下白色的 R 一条窄亮带；金发吸收弱，多次散射撑起颜色，R、TRT 叠在上面。
// 能量守恒：三条光路的纵向（高斯在 sinθi+sinθo 上归一，再按瓣中心的出射角修正）、方位（∫N dφ ≤ 1）都归一，
// 再乘菲涅尔、吸收；数值积分（对出射方向积 S·cosθo，除以 cosθi）：白发 R+TT+TRT 最多 0.998（30° 入射），
// 黑 0.18、红棕 0.84 / 0.45 / 0.25、金 0.97 / 0.93 / 0.80。多次散射只拿直接出去以后剩下的能量。
// 头发是一团，不是一根：没有阴影的灯（捏脸的补光、轮廓光）会穿过脑袋照到另一边的头发上。用“头发团”的法线
// （从头的中心指向这一点，volume_center）挡一下：背着光的那半边不进光，透光只在逆光的轮廓上。
// 开销：varying 压进 4 个槽位（插件那份 6 个；Godot 每个 varying 占一整个槽位，细发丝的三角形又小又多，槽位越少越省；
// 吸收系数在 fragment() 里算一次传给 light()，不占槽位），背着光、在阴影里的像素整段跳过，R、TT、TRT 只在各自那一瓣有值的地方算
shader_type spatial;
render_mode world_vertex_coords, cull_disabled, depth_prepass_alpha;

// —— TressFXHair 节点按名字设的，名字不能改 ——
// 模拟好的顶点：xyz 世界坐标，w 压缩的切线（发根指向发梢）
uniform sampler2D positions : filter_nearest;
// 每根发丝一个像素：发根在身体贴图上的坐标（strand_attrs 打开时是这根发丝的粗细倍数、在头发层里的深浅）
uniform sampler2D strand_uvs : filter_nearest;
uniform int verts_per_strand = 8;
// 每个网格实例一个：发丝发到 LOD_BUCKETS 个网格里，第 b 个网格的第 k 根是全局第 b + k * LOD_BUCKETS 根
instance uniform int lod_bucket = 0;
const int LOD_BUCKETS = 4;
// 远了发丝变宽，补上丢掉的那些
uniform float lod_start = 1.0;
uniform float lod_end = 5.0;
uniform float lod_width_multiplier = 1.0;

// —— 发色、粗细，和插件那份同名同义 ——
uniform sampler2D base_albedo : source_color, hint_default_white, filter_linear_mipmap;
// 发色：一团头发看上去的颜色（不是一根发丝的颜色）。a 不用
uniform vec4 base_color : source_color = vec4(0.03, 0.026, 0.024, 1.0);
uniform vec4 tip_color : source_color = vec4(0.03, 0.026, 0.024, 1.0);
uniform float tip_percentage = 0.0;
uniform float fiber_radius = 0.0021;
uniform float fiber_ratio = 0.463; // 发梢半径 / 发根半径
uniform bool thin_tip = true;
uniform float expand_pixels = 0.71;
// 发根附近压暗（按发丝的长短比例，和下面按头发层厚度的那个一起乘）
uniform float root_shadow : hint_range(0.0, 1.0) = 0.3;
// 每根发丝的明暗、冷暖随机一点；发梢最后一段淡出
uniform float color_variation : hint_range(0.0, 1.0) = 0.3;
uniform float tip_fade : hint_range(0.0, 1.0) = 0.25;
// 发根淡入（占全长的比例）：发根从皮肤里慢慢露出来。不淡入的话发际线、分缝上每根发丝都从一个点突然以满粗细开始，
// 一排像刺；头发中间的发根被别的头发盖着，看不出来
uniform float root_fade : hint_range(0.0, 0.2) = 0.0;
// .tfx 的发丝 UV 不是贴图坐标，是每根发丝的 (粗细倍数, 在头发层里的深浅 0 最里 .. 1 最外)：tools/gen_tfx_hair.py 生成的发型这么存
// （发际线的绒毛细、乱发细；一绺一绺有深有浅）。深浅和下面按离头多远估的那个取小的（发根附近都贴着头皮）
uniform bool strand_attrs = false;

// —— 打光 ——
// 纵向粗糙度：R 的高斯宽 roughness²（在 sinθi+sinθo 上），TT 一半、TRT 两倍（Marschner 量的比例）。
// 0.4 时 R 的宽度约 ±5°（θh），Marschner 量的真人头发是 5°~10°
uniform float roughness : hint_range(0.15, 0.8) = 0.4;
// 角质层倾角：R 往发根偏这么多，TT 往发梢偏一半，TRT 往发梢偏 1.5 倍（人发约 3°）
uniform float cuticle_tilt_deg : hint_range(0.0, 8.0) = 3.0;
// 各条光路的倍数，1 是物理上的量
uniform float specular : hint_range(0.0, 2.0) = 1.0;     // R
uniform float transmission : hint_range(0.0, 2.0) = 1.0; // TT
uniform float secondary : hint_range(0.0, 2.0) = 1.0;    // TRT
uniform float scatter : hint_range(0.0, 1.0) = 1.0;      // 多次散射
// 每根发丝的高光位置、宽窄随机差一点：真发丝的倾角、粗细根根不同，高光碎成一根一根的，不是一整条
uniform float strand_jitter : hint_range(0.0, 1.0) = 0.5;
// 头发团的中心（本节点的坐标系里，一般是头的中心）：法线从这里指出去
uniform vec3 volume_center = vec3(0.0);
// 头发团明暗交界的软硬：越大背光那半边漏进的光越多（多次散射的包裹光照、R/TRT/TT 的进光都用它）
uniform float volume_wrap : hint_range(0.05, 1.0) = 0.5;
// 头发层有多厚（米）：发丝离头的中心比自己的发根远出这么多才算最外层。里层被外层挡着，接到的光少
// （TressFX 原本靠深度阴影图数中间隔了几根发丝；Godot 的阴影图只有挡没挡，还被柔光的半影糊掉）
uniform float volume_thickness = 0.03;
uniform float volume_occlusion : hint_range(0.0, 1.0) = 0.6; // 贴着头皮的最里层少接多少光

// 头发的折射率，菲涅尔 F0 = ((1-η)/(1+η))²
const float ETA = 1.55;
const float F0 = 0.0465;

varying vec4 v_tan_t;   // xyz 切线（视图空间），w 0 发根 .. 1 发梢
varying vec4 v_color;   // rgb 发色，a 每根发丝一个随机数
varying vec4 v_volume;  // xyz 头发团的法线（视图空间），w 在头发层里的深浅：0 贴着头皮 .. 1 最外层
varying vec2 v_ribbon;  // x 横跨面片 -1 .. 1，y 扩宽以后的半宽（像素）
varying vec3 v_sigma;   // fragment() 算好给 light()：吸收系数（每单位发丝半径）

// tressfx_sim.glsl 的 pack_tangent() 的逆（12+12 位八面体编码）
vec3 unpack_tangent(float p) {
	float x = floor(p / 4096.0);
	vec2 e = vec2(x, p - x * 4096.0) / 4095.0 * 2.0 - 1.0;
	vec3 n = vec3(e, 1.0 - abs(e.x) - abs(e.y));
	float t = max(-n.z, 0.0);
	n.xy += vec2(n.x >= 0.0 ? -t : t, n.y >= 0.0 ? -t : t);
	return normalize(n);
}

// 发色 → 吸收系数：Chiang 2016 拟合的反函数（方位粗糙度 0.3），一大团这个吸收系数的头发多次散射以后看上去就是这个颜色。
// 颜色越深吸收越强、增长得越快：黑（线性 0.002）约 1.1，红棕约 0.09 / 0.45 / 0.82，金约 0.012 / 0.038 / 0.13
vec3 color_to_absorption(vec3 c) {
	vec3 l = log(clamp(c, vec3(1e-4), vec3(1.0))) / 5.888;
	return l * l;
}

float hair_fresnel(float c) {
	float m = 1.0 - clamp(c, 0.0, 1.0);
	float m2 = m * m;
	return F0 + (1.0 - F0) * m2 * m2 * m;
}

// 归一的高斯（积分为 1）
float gauss(float b, float x) {
	return exp(-0.5 * x * x / (b * b)) * 0.39894228 / b;
}

// 纵向的高斯在 sinθi+sinθo 上归一，瓣偏了以后掠射时出射那边的 cosθo 比 cosθi 大，能量会多出来（白发 60° 入射时
// R+TT+TRT 积出来 1.11）：按瓣中心（sinθo = 偏移 − sinθi）的出射角乘回 cosθi / cosθo，只往小了改
float lobe_norm(float shift, float sin_i, float cos_i) {
	float so = shift - sin_i;
	return min(cos_i / max(sqrt(max(1.0 - so * so, 0.0)), 0.05), 1.0);
}

void vertex() {
	int hair_vertex = VERTEX_ID >> 1;
	int strand = lod_bucket + (hair_vertex / verts_per_strand) * LOD_BUCKETS;
	int gi = strand * verts_per_strand + hair_vertex % verts_per_strand;
	float side = float(VERTEX_ID & 1) * 2.0 - 1.0;
	int w = textureSize(positions, 0).x;
	vec4 d = texelFetch(positions, ivec2(gi % w, gi / w), 0);
	vec3 p = d.xyz;
	vec3 t = unpack_tangent(d.w);

	int wu = textureSize(strand_uvs, 0).x;
	vec2 strand_uv = texelFetch(strand_uvs, ivec2(strand % wu, strand / wu), 0).xy;

	float vt = float(gi % verts_per_strand) / float(verts_per_strand - 1);
	float ratio = thin_tip ? mix(1.0, fiber_ratio, vt) : 1.0;
	vec3 eye = INV_VIEW_MATRIX[3].xyz;
	float lod = smoothstep(lod_start, lod_end, distance(eye, p));
	float r = fiber_radius * (strand_attrs ? strand_uv.x : 1.0) * ratio * mix(1.0, lod_width_multiplier, lod);

	vec3 right = normalize(cross(t, normalize(p - eye)));
	// 两条真实的边投到屏幕上量发丝有几个像素宽（不管投影矩阵是哪种约定）
	mat4 vp = PROJECTION_MATRIX * VIEW_MATRIX;
	vec4 c0 = vp * vec4(p - right * r, 1.0);
	vec4 c1 = vp * vec4(p + right * r, 1.0);
	vec2 s0 = c0.xy / max(c0.w, 1e-4) * VIEWPORT_SIZE * 0.5;
	vec2 s1 = c1.xy / max(c1.w, 1e-4) * VIEWPORT_SIZE * 0.5;
	float half_width = max(0.5 * length(s1 - s0), 1e-4);
	float px = r / half_width; // 这里一个像素在世界里多大
	float expanded = half_width + expand_pixels;
	v_ribbon = vec2(side, expanded);
	VERTEX = p + right * side * expanded * px;
	NORMAL = normalize(cross(right, t));
	v_tan_t = vec4((VIEW_MATRIX * vec4(t, 0.0)).xyz, vt);

	// 发根在身体贴图上的颜色乘发色，发梢可以换颜色
	vec3 root_color = (strand_attrs ? vec3(1.0) : textureLod(base_albedo, strand_uv, 0.0).rgb) * base_color.rgb;
	vec3 col = vt > 1.0 - tip_percentage ? mix(root_color, tip_color.rgb, vt) : root_color;
	float h1 = fract(sin(float(strand) * 12.9898) * 43758.5453);
	float h2 = fract(sin(float(strand) * 78.233) * 43758.5453);
	col *= 1.0 + color_variation * (h1 - 0.5) * 1.4;
	col *= mix(vec3(1.0), vec3(1.0 + (h2 - 0.5) * 0.3, 1.0, 1.0 - (h2 - 0.5) * 0.3), color_variation);
	v_color = vec4(col, fract(sin(float(strand) * 39.3468) * 43758.5453));

	// 头发团：法线从头的中心指出来；发根在头皮上，这一点比发根离头的中心远出多少，就是压在多少头发上面
	vec3 center = (MODEL_MATRIX * vec4(volume_center, 1.0)).xyz;
	int gr = strand * verts_per_strand;
	vec3 p0 = texelFetch(positions, ivec2(gr % w, gr / w), 0).xyz;
	float depth = clamp((distance(p, center) - distance(p0, center)) / max(volume_thickness, 1e-4), 0.0, 1.0);
	if (strand_attrs) {
		depth = min(depth, strand_uv.y);
	}
	v_volume = vec4((VIEW_MATRIX * vec4(normalize(p - center), 0.0)).xyz, depth);
}

// 横跨面片的覆盖率：发丝真实的宽度以内是 1，往外 expand_pixels 个像素降到 0（不排序的软边，见插件那份的说明）
void fragment() {
	ALBEDO = v_color.rgb;
	float dist = abs(v_ribbon.x) * v_ribbon.y;
	ALPHA = clamp((v_ribbon.y - dist) / max(expand_pixels, 1e-3), 0.0, 1.0);
	if (tip_fade > 0.0) {
		ALPHA *= smoothstep(1.0, 1.0 - tip_fade, v_tan_t.w);
	}
	if (root_fade > 0.0) {
		ALPHA *= smoothstep(0.0, root_fade, v_tan_t.w);
	}
	AO = mix(1.0 - root_shadow, 1.0, v_tan_t.w) * mix(1.0 - volume_occlusion, 1.0, v_volume.w);
	AO_LIGHT_AFFECT = 1.0;
	// 每个像素算一次（三个对数），每盏灯的 light() 直接用
	v_sigma = color_to_absorption(v_color.rgb);
}

// θ 是和发丝法平面的夹角（往发梢为正），φ 是 L、V 投到法平面里的夹角；θd = (θo − θi) / 2。
// 出射亮度 = S · E，E = LIGHT_COLOR · ATTENUATION（代码里叫 irr；和引擎的 Lambert 同一个约定：白色漫反射正对着光亮度是 E/π）。
// R、TT、TRT 不随发色乘 ALBEDO，进 SPECULAR_LIGHT；多次散射的颜色就是发色，进 DIFFUSE_LIGHT 让引擎乘 ALBEDO
void light() {
	// 头发团挡光：背着光的那半边进不了光（有阴影的灯靠阴影图，没阴影的灯全靠这个）。这半边、阴影里什么都不加，整段跳过
	vec3 nv = normalize(v_volume.xyz);
	float nl = dot(nv, LIGHT);
	float w = max(volume_wrap, 0.05); // 0 的话下面 smoothstep 两头一样，没有定义
	if (nl > -w && ATTENUATION > 1e-4) {
		vec3 irr = LIGHT_COLOR * ATTENUATION;
		vec3 T = normalize(v_tan_t.xyz);
		float sin_i = clamp(dot(T, LIGHT), -1.0, 1.0);
		float sin_o = clamp(dot(T, VIEW), -1.0, 1.0);
		float cos_i = sqrt(1.0 - sin_i * sin_i);
		float cos_o = sqrt(1.0 - sin_o * sin_o);
		float cos_d = sqrt(max(0.5 + 0.5 * (cos_i * cos_o + sin_i * sin_o), 1e-4));
		vec3 lp = LIGHT - sin_i * T;
		vec3 vp = VIEW - sin_o * T;
		float cos_phi = dot(lp, vp) * inversesqrt(max(dot(lp, lp) * dot(vp, vp), 1e-8));
		float cos_half_phi = sqrt(clamp(0.5 + 0.5 * cos_phi, 0.0, 1.0));
		float x = sin_i + sin_o;
		float lit = smoothstep(-w, w, nl);
		// 透光要光擦着头发团的边进来（光的明暗交界），再擦着边出去到相机（相机看过去的轮廓）：迎着光的那面，
		// 穿过发丝的光往头发团里面走，变成多次散射；背着光的那面光进不来。两个交界重合的地方只有逆光时的轮廓
		float rim = (1.0 - smoothstep(0.0, w, abs(nl))) * (1.0 - smoothstep(0.0, w, abs(dot(nv, VIEW))));

		float jit = (v_color.a - 0.5) * 2.0 * strand_jitter;
		float tilt = radians(cuticle_tilt_deg) * (1.0 + 0.6 * jit);
		float b = roughness * roughness * (1.0 + 0.3 * jit);

		// R：纵向峰在 θh = −倾角（往发根偏），方位 cos(φ/2)/4（∫ dφ = 1），菲涅尔按 L、V 的半角。
		// 窄，偏出 4 倍宽度（不到峰值的 0.04%）就不算了
		vec3 spec = vec3(0.0);
		if (abs(x + 2.0 * tilt) < 4.0 * b) {
			float m = gauss(b, x + 2.0 * tilt) * lobe_norm(-2.0 * tilt, sin_i, cos_i);
			float f = hair_fresnel(sqrt(clamp(0.5 + 0.5 * dot(LIGHT, VIEW), 0.0, 1.0)));
			spec = vec3(specular * m * 0.25 * cos_half_phi * f);
		}

		// 投到法平面里的等效折射率（Bravais），光在发丝里走的路长 2cosγt / cosθt（单位发丝半径）：TT、TRT 才用
		float a = 0.0;
		float cos_t = 1.0;
		if (rim > 0.0 || cos_phi > 0.6) {
			a = cos_d / sqrt(ETA * ETA - 1.0 + cos_d * cos_d);
			cos_t = sqrt(1.0 - (1.0 - cos_d * cos_d) / (ETA * ETA));
		}

		// TT：出射点 h 用 Karis 的近似，方位是朝前（φ = π）的一瓣（∫ dφ ≈ 0.99；cosφ > 0.3 时不到峰值的 1%，不算）
		vec3 tt_out = vec3(0.0);
		if (rim > 0.0 && cos_phi < 0.3) {
			float h = cos_half_phi * (1.0 + a * (0.6 - 0.8 * cos_phi));
			float f = hair_fresnel(cos_d * sqrt(clamp(1.0 - h * h, 0.0, 1.0)));
			vec3 ab = exp(-v_sigma * 2.0 * sqrt(clamp(1.0 - h * h * a * a, 0.0, 1.0)) / cos_t);
			float m = gauss(0.5 * b, x - tilt) * lobe_norm(tilt, sin_i, cos_i);
			// 擦着头发团的边进出的光，一般还要先、后穿过别的发丝（正好在轮廓上约一根，往里越来越多），
			// 每穿一根乘一次一根发丝平均的透光率（积分约 0.88 × 平均路长 1.9 倍半径的透过率）：越透颜色越饱和，
			// 金发的逆光是金色不是白色（双重散射里前向散射衰减最简单的形式，Zinke 2008）
			vec3 pass = exp((log(0.88) - 1.9 * v_sigma) * (2.0 - rim));
			spec += transmission * rim * m * exp(-3.65 * cos_phi - 3.98) * (1.0 - f) * (1.0 - f) * ab * pass;
			// 这一路总共直接透出去多少，多次散射扣掉
			tt_out = transmission * rim * 0.88 * exp(-1.9 * v_sigma) * pass;
		}

		// TRT：取 h = √3/2，方位是朝回（φ = 0）的一瓣（∫ dφ ≈ 0.76；cosφ < 0.6 时不到峰值的 0.2%，不算）
		if (cos_phi > 0.6) {
			float f = hair_fresnel(0.5 * cos_d);
			vec3 ab = exp(-v_sigma * 4.0 * sqrt(1.0 - 0.75 * a * a) / cos_t);
			float m = gauss(2.0 * b, x - 3.0 * tilt) * lobe_norm(3.0 * tilt, sin_i, cos_i);
			spec += secondary * m * exp(17.0 * cos_phi - 16.78) * (1.0 - f) * (1.0 - f) * f * ab;
		}

		SPECULAR_LIGHT += spec * lit * irr * SPECULAR_AMOUNT;

		// 多次散射：头发团当成一个漫反射面（法线 nv，包裹光照、能量守恒的写法），颜色是发色（引擎乘 ALBEDO）；
		// 顺着光的发丝截面小、接的光少（Kajiya-Kay 的 sinθ）。它拿的是直接出去以后剩下的能量：
		// R 约 7%、TRT 约 5%（积分见开头），轮廓上透出去的 TT 有多少扣多少
		float ms = (nl + w) / ((1.0 + w) * (1.0 + w));
		vec3 left = max(1.0 - 0.07 * specular - 0.05 * secondary - tt_out * lit, 0.0);
		DIFFUSE_LIGHT += scatter * left * ms * mix(1.0, cos_i, 0.4) * irr / PI;
	}
}
