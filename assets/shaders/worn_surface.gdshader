// 硬表面通用材质：底漆颜色 + 三平面映射的细节贴图 + 曲率顶点色（R=棱边磨损，G=凹槽积垢）。
// 另外叠加：指纹/手摸的油污（改粗糙度）、朝上表面的积灰、竖直方向的水渍流痕。
// 不依赖 UV，适合脚本生成的模型。
shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_back, diffuse_burley, specular_schlick_ggx;

uniform vec4 paint_color : source_color = vec4(0.42, 0.06, 0.035, 1.0);
uniform float paint_roughness : hint_range(0.0, 1.0) = 0.55;
uniform float paint_metallic : hint_range(0.0, 1.0) = 0.1;
uniform float paint_variation : hint_range(0.0, 1.0) = 0.35;

uniform sampler2D grime_albedo : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D grime_normal : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D grime_arm : hint_default_white, filter_linear_mipmap_anisotropic, repeat_enable;
// true：grime_arm 是 Poly Haven 那种 AO/粗糙度/金属度打包图；false：只是一张粗糙度灰度图（ambientCG）
uniform bool arm_packed = true;
uniform float tex_scale = 1.0;
uniform float normal_strength : hint_range(0.0, 2.0) = 0.6;
// 细节贴图本身的粗糙度起伏，叠到底漆粗糙度上
uniform float rough_variation : hint_range(0.0, 1.0) = 0.0;

uniform float rust_amount : hint_range(0.0, 1.0) = 0.25;
uniform float cavity_dirt : hint_range(0.0, 2.0) = 1.0;
uniform float edge_wear : hint_range(0.0, 2.0) = 0.8;
uniform vec4 wear_color : source_color = vec4(0.42, 0.4, 0.37, 1.0);

// 指纹、手摸的油污：只改粗糙度和一点点颜色
uniform sampler2D smudge_tex : hint_default_black, filter_linear_mipmap, repeat_enable;
uniform float smudge_amount : hint_range(0.0, 1.0) = 0.0;
uniform float smudge_scale = 4.0;
// 朝上表面的积灰
uniform float dust_amount : hint_range(0.0, 1.0) = 0.0;
uniform vec4 dust_color : source_color = vec4(0.46, 0.44, 0.4, 1.0);
// 竖直流痕（冷凝水、锈水）
uniform sampler2D streak_tex : hint_default_black, filter_linear_mipmap, repeat_enable;
uniform float streak_amount : hint_range(0.0, 1.0) = 0.0;
uniform float streak_scale = 1.0;
uniform vec4 streak_color : source_color = vec4(0.3, 0.22, 0.14, 1.0);

// 大尺度的脏污起伏（几十厘米一块的明暗、粗糙度变化），打破大平面上「新刷的漆」那种均匀感
uniform float macro_amount : hint_range(0.0, 1.0) = 0.0;
uniform float macro_scale = 0.18;
// 越靠近地板越脏：鞋底蹭的、拖地水渍、积灰（物体空间高度，舱内模型原点就是艇的原点）
uniform float floor_dirt : hint_range(0.0, 1.0) = 0.0;
uniform float floor_height = -0.9;
uniform float floor_fade = 0.65;
uniform vec4 floor_color : source_color = vec4(0.2, 0.18, 0.15, 1.0);

// 冷凝水珠：深海水温只有两三度，耐压壳内壁和冷水管上结满水珠（越往上、越是朝下的面越密，朝上的面没有）。
// 程序生成（两层大小不同的 voronoi 水珠），不需要贴图。
uniform float condensation : hint_range(0.0, 1.0) = 0.0;
uniform float droplet_scale = 125.0;  // 每米多少格（大水珠那一层）
uniform float cond_height = 0.2;     // 物体空间高度：从这里往上水珠变密

// 棱边磨出来的底材是不是金属（漆木家具磨出来的是木头，不是金属）
uniform float wear_metallic : hint_range(0.0, 1.0) = 0.85;

uniform vec4 emission_color : source_color = vec4(0.0, 0.0, 0.0, 1.0);
uniform float emission_energy = 0.0;

varying vec3 obj_pos;
varying vec3 obj_nrm;
varying vec4 wear;

void vertex() {
	obj_pos = VERTEX;
	obj_nrm = NORMAL;
	wear = COLOR;
}

vec3 tri_weights(vec3 n) {
	vec3 w = pow(abs(n), vec3(4.0));
	return w / (w.x + w.y + w.z + 1e-5);
}

vec4 tri_sample(sampler2D t, vec3 p, vec3 w) {
	return texture(t, p.zy) * w.x + texture(t, p.xz) * w.y + texture(t, p.xy) * w.z;
}

vec2 hash22(vec2 p) {
	vec3 q = fract(vec3(p.xyx) * vec3(0.1031, 0.1030, 0.0973));
	q += dot(q, q.yzx + 33.33);
	return fract((q.xx + q.yz) * q.zy);
}

// 一层水珠。返回 (表面斜率 xy, 覆盖 z)。竖直面上的水珠往下坠（下半截更圆更大）。
vec3 droplet_layer(vec2 uv, float density) {
	vec2 cell = floor(uv);
	vec2 f = fract(uv);
	vec3 best = vec3(0.0);
	for (int j = -1; j <= 1; j++) {
		for (int i = -1; i <= 1; i++) {
			vec2 g = vec2(float(i), float(j));
			vec2 h = hash22(cell + g);
			if (fract(h.x * 7.13 + h.y * 3.71) > density) {
				continue;
			}
			vec2 q = f - (g + 0.2 + h * 0.6);  // 从水珠中心指向当前像素
			float rad = mix(0.14, 0.4, fract(h.y * 13.7 + h.x));
			q.y *= q.y < 0.0 ? 0.8 : 1.3;
			float d = length(q) / rad;
			float m = 1.0 - smoothstep(0.8, 1.0, d);
			if (m > best.z) {
				best = vec3(q / rad * 0.9, m);
			}
		}
	}
	return best;
}

vec3 droplets2(vec2 uv, float density) {
	vec3 a = droplet_layer(uv, density);
	vec3 b = droplet_layer(uv * 2.3 + 17.1, min(density * 1.2, 1.0));
	return a.z >= b.z ? a : b;
}

vec3 tri_normal(vec3 p, vec3 n, vec3 w) {
	vec3 tx = texture(grime_normal, p.zy).xyz * 2.0 - 1.0;
	vec3 ty = texture(grime_normal, p.xz).xyz * 2.0 - 1.0;
	vec3 tz = texture(grime_normal, p.xy).xyz * 2.0 - 1.0;
	tx.xy *= normal_strength;
	ty.xy *= normal_strength;
	tz.xy *= normal_strength;
	// Whiteout 混合
	tx = vec3(tx.xy + n.zy, abs(tx.z) * n.x);
	ty = vec3(ty.xy + n.xz, abs(ty.z) * n.y);
	tz = vec3(tz.xy + n.xy, abs(tz.z) * n.z);
	return normalize(tx.zyx * w.x + ty.xzy * w.y + tz.xyz * w.z);
}

void fragment() {
	vec3 n = normalize(obj_nrm);
	vec3 w = tri_weights(n);
	vec3 p = obj_pos * tex_scale;
	vec4 g = tri_sample(grime_albedo, p, w);
	vec4 arm = tri_sample(grime_arm, p, w);
	if (!arm_packed) {
		arm = vec4(1.0, arm.r, 0.0, 1.0);
	}
	float lum = dot(g.rgb, vec3(0.299, 0.587, 0.114));

	float edge = wear.r;
	float cav = wear.g;
	float noise = tri_sample(grime_albedo, p * 0.37 + 0.13, w).g;

	vec3 col = paint_color.rgb * mix(1.0, 0.6 + lum * 1.4, paint_variation);
	float rough = clamp(paint_roughness + (arm.g - 0.5) * rough_variation, 0.04, 1.0);
	float metal = paint_metallic;

	if (macro_amount > 0.0) {
		vec3 mp = obj_pos * macro_scale;
		float m = tri_sample(grime_albedo, mp + 0.31, w).r * 0.6 + tri_sample(grime_albedo, mp * 0.37 + 0.71, w).g * 0.4;
		m = (m - 0.5) * 2.0;
		col *= 1.0 + m * macro_amount * 0.35;
		rough = clamp(rough + m * macro_amount * 0.18, 0.05, 1.0);
	}

	// 锈蚀：凹槽里先长，再按噪声扩散
	float rust = smoothstep(0.55, 0.8, rust_amount + cav * cavity_dirt * 0.6 + (noise - 0.5) * 0.8);
	col = mix(col, g.rgb, rust);
	rough = mix(rough, arm.g, rust);
	metal = mix(metal, arm.b, rust);

	// 棱边磨出底下的金属
	// 阈值偏高：只有真正的棱边（倒角面、曲率大的地方）才掉漆，大平面上不会出现成片的斑
	float e = smoothstep(0.55, 0.9, edge * edge_wear + (noise - 0.5) * 0.5);
	col = mix(col, wear_color.rgb, e * (1.0 - rust));
	metal = mix(metal, wear_metallic, e * (1.0 - rust));
	rough = mix(rough, 0.35, e * (1.0 - rust));

	// 凹槽积垢
	col *= 1.0 - cav * cavity_dirt * 0.35;

	if (floor_dirt > 0.0) {
		float f = 1.0 - smoothstep(floor_height, floor_height + floor_fade, obj_pos.y);
		f = clamp(f * (0.55 + noise * 0.9), 0.0, 1.0) * floor_dirt;
		col = mix(col, col * floor_color.rgb * 2.2, f);
		rough = mix(rough, 0.8, f * 0.6);
		metal = mix(metal, 0.0, f * 0.5);
	}

	// 指纹/油污：手常碰的地方更亮（油）或更哑（灰），这里统一成「更光滑 + 略暗」
	if (smudge_amount > 0.0) {
		vec3 sp = obj_pos * smudge_scale;
		float s = (texture(smudge_tex, sp.zy).r * w.x + texture(smudge_tex, sp.xz).r * w.y
				+ texture(smudge_tex, sp.xy).r * w.z) * smudge_amount;
		rough = mix(rough, rough * 0.55 + 0.08, s);
		col *= 1.0 - s * 0.12;
	}

	// 水渍流痕：只在侧面（竖直面）出现，颜色发褐，表面发亮（湿）
	if (streak_amount > 0.0) {
		vec3 sp = obj_pos * streak_scale;
		float side = 1.0 - w.y;
		float st = (texture(streak_tex, sp.zy).r * w.x + texture(streak_tex, sp.xy).r * w.z) / max(w.x + w.z, 1e-4);
		st = smoothstep(0.2, 0.9, st) * streak_amount * side;
		col = mix(col, col * streak_color.rgb * 1.6, st);
		rough = mix(rough, 0.25, st * 0.7);
	}

	// 积灰：只落在朝上的面，凹槽里多一点
	if (dust_amount > 0.0) {
		float up = smoothstep(0.35, 0.9, n.y);
		float d = clamp(up * dust_amount * (0.6 + noise * 0.8) + cav * dust_amount * 0.4, 0.0, 1.0);
		col = mix(col, dust_color.rgb, d * 0.75);
		rough = mix(rough, 0.95, d);
		metal = mix(metal, 0.0, d);
	}

	vec3 nn = tri_normal(p, n, w);

	if (condensation > 0.0) {
		float hgt = smoothstep(cond_height - 0.6, cond_height + 0.7, obj_pos.y);
		float up = smoothstep(0.25, 0.7, n.y);
		// 水珠一片一片地结，不是均匀铺满
		float dens = condensation * (0.1 + 0.4 * hgt) * (1.0 - up) * clamp(noise * 1.6 - 0.2, 0.0, 1.0);
		// 整面潮湿：越密的地方越亮
		rough = mix(rough, rough * 0.55, dens * 0.6);
		vec3 dp = obj_pos * droplet_scale;
		vec3 slope = vec3(0.0);
		float cover = 0.0;
		// 侧面（x、z 投影）水珠拉长，朝下的面（y 投影）是圆的
		if (w.x > 0.02) {
			vec3 d = droplets2(vec2(dp.z, dp.y * 0.75), dens);
			slope += (vec3(0.0, 0.0, 1.0) * d.x + vec3(0.0, 1.0, 0.0) * d.y) * d.z * w.x;
			cover += d.z * w.x;
		}
		if (w.y > 0.02) {
			vec3 d = droplets2(dp.xz, dens);
			slope += (vec3(1.0, 0.0, 0.0) * d.x + vec3(0.0, 0.0, 1.0) * d.y) * d.z * w.y;
			cover += d.z * w.y;
		}
		if (w.z > 0.02) {
			vec3 d = droplets2(vec2(dp.x, dp.y * 0.75), dens);
			slope += (vec3(1.0, 0.0, 0.0) * d.x + vec3(0.0, 1.0, 0.0) * d.y) * d.z * w.z;
			cover += d.z * w.z;
		}
		// 远处水珠小于一个像素时淡掉，免得闪
		float px = length(fwidth(dp));
		float fade = 1.0 - smoothstep(0.25, 0.6, px);
		cover *= fade;
		slope *= fade;
		nn = normalize(nn + slope);
		col *= 1.0 - cover * 0.12;
		rough = mix(rough, 0.03, cover);
		metal = mix(metal, 0.0, cover);
	}

	ALBEDO = col;
	ROUGHNESS = rough;
	METALLIC = metal;
	AO = mix(1.0, arm.r, 0.6) * (1.0 - cav * 0.4);
	AO_LIGHT_AFFECT = 0.4;
	NORMAL = normalize((VIEW_MATRIX * MODEL_MATRIX * vec4(nn, 0.0)).xyz);
	EMISSION = emission_color.rgb * emission_energy;
}
