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
// 流痕只出现在一部分竖条区域里（上面有焊缝、法兰、螺栓漏水的地方），不是满墙一个样。1 = 不分区
uniform float streak_cover : hint_range(0.0, 1.0) = 1.0;

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
// 水珠成片：大尺度（一两米一块）的湿区和干区，再加上焊缝、肋骨根部这些凹处集中挂水
uniform float cond_patch_scale = 0.55;
uniform float cond_patch_cover : hint_range(0.0, 1.0) = 0.35;  // 大约多少面积是湿区
uniform float cond_cavity = 1.0;

// 棱边磨出来的底材是不是金属（漆木家具磨出来的是木头，不是金属）
uniform float wear_metallic : hint_range(0.0, 1.0) = 0.85;

// ---- 厚漆钢件（军船那种一层层刷上去的漆）。默认全关，不影响别的材质。
// 掉漆分层：漆面磕掉先露出红丹底漆，再往里才是钢；primer_amount 是底漆那一圈有多宽
uniform float primer_amount : hint_range(0.0, 1.0) = 0.0;
uniform vec4 primer_color : source_color = vec4(0.32, 0.11, 0.065, 1.0);
// 大平面上成片的磕碰掉漆、划痕（不只在棱边）；chip_cover 是大约多少面积有，越靠近地板越多（脚踢的）
uniform sampler2D chip_tex : hint_default_black, filter_linear_mipmap, repeat_enable;
uniform float chip_amount : hint_range(0.0, 1.0) = 0.0;
uniform float chip_scale = 2.0;
uniform float chip_cover : hint_range(0.0, 1.0) = 0.5;
// 露出来的钢放久了发锈发暗（手常磨的棱边除外，那里是亮的）
uniform float bare_rust : hint_range(0.0, 1.0) = 0.0;
// 漆层厚度（米，夸大一些）：掉漆的边上有一道台阶，侧光下看得出来
uniform float paint_depth = 0.0;
// 大面的起伏（焊接变形、敲过的凹坑），反光跟着扭，不像冲压出来的平板
uniform float warp_amount : hint_range(0.0, 2.0) = 0.0;
uniform float warp_scale = 2.5;

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

float hash31(vec3 p) {
	p = fract(p * 0.1031);
	p += dot(p, p.zyx + 31.32);
	return fract((p.x + p.y) * p.z);
}

// 三维值噪声（0~1），大致均匀分布，用来分湿区、干区
float value_noise(vec3 p) {
	vec3 i = floor(p);
	vec3 f = fract(p);
	f = f * f * (3.0 - 2.0 * f);
	return mix(mix(mix(hash31(i), hash31(i + vec3(1, 0, 0)), f.x),
				mix(hash31(i + vec3(0, 1, 0)), hash31(i + vec3(1, 1, 0)), f.x), f.y),
			mix(mix(hash31(i + vec3(0, 0, 1)), hash31(i + vec3(1, 0, 1)), f.x),
				mix(hash31(i + vec3(0, 1, 1)), hash31(i + vec3(1, 1, 1)), f.x), f.y), f.z);
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
	float er = edge * edge_wear + (noise - 0.5) * 0.5;
	float e = smoothstep(0.55, 0.9, er);
	float height = 1.0;  // 漆面 1，底漆 0.5，钢 0（给 paint_depth 算掉漆边上的台阶）
	vec3 bare = wear_color.rgb;
	float old = 0.0;
	if (primer_amount > 0.0 || chip_amount > 0.0) {
		float chip = 0.0;
		if (chip_amount > 0.0) {
			vec3 cp = obj_pos * chip_scale;
			float c = texture(chip_tex, cp.zy).r * w.x + texture(chip_tex, cp.xz).r * w.y
					+ texture(chip_tex, cp.xy).r * w.z;
			float zn = value_noise(obj_pos * 2.3 + 5.1) * 0.7 + value_noise(obj_pos * 6.1 + 1.7) * 0.3;
			float region = smoothstep(1.0 - chip_cover - 0.1, 1.0 - chip_cover + 0.15, zn);
			float low = 1.0 - smoothstep(floor_height, floor_height + 0.45, obj_pos.y);
			chip = smoothstep(0.08, 0.6, c) * chip_amount * clamp(region + low * 0.9, 0.0, 1.0);
		}
		// 棱边掉漆一段一段的：十几厘米一块的噪声把一圈棱边分成磕掉的、没磕掉的，掉漆的边缘形状跟着掉漆遮罩走。
		// 只往下减（大平面是长三角形，棱边的顶点色会插值进面里，放大会让整面起皮）
		float brk = value_noise(obj_pos * 7.0 + 2.9) * 0.65 + value_noise(obj_pos * 19.0 + 0.7) * 0.35;
		vec3 ep = obj_pos * chip_scale * 2.0;
		float etex = texture(chip_tex, ep.zy).r * w.x + texture(chip_tex, ep.xz).r * w.y + texture(chip_tex, ep.xy).r * w.z;
		float edge_r = smoothstep(0.5, 0.9, er) * smoothstep(0.35, 0.65, brk + etex * 0.6);
		float r = max(edge_r, chip);
		float t0 = 0.45 - primer_amount * 0.3;
		float aa = max(fwidth(r) * 1.5, 0.03);   // 掉漆边缘按像素宽度抗锯齿，远处不闪
		float pm = smoothstep(t0 - aa, t0 + aa, r) * (1.0 - rust);
		e = smoothstep(0.62 - aa, 0.62 + aa, r);
		col = mix(col, primer_color.rgb * (0.8 + noise * 0.4), pm);
		rough = mix(rough, 0.72, pm);
		metal = mix(metal, 0.0, pm);
		height = 1.0 - pm * 0.5 - e * 0.5;
		// 磕出来的钢（不是手磨亮的棱边）发锈发暗
		old = bare_rust * clamp(chip - edge_r * 0.6, 0.0, 1.0) * (0.6 + noise * 0.8);
		old = clamp(old, 0.0, 1.0);
		bare = mix(wear_color.rgb, g.rgb * 0.7, old);
	}
	col = mix(col, bare, e * (1.0 - rust));
	metal = mix(metal, wear_metallic, e * (1.0 - rust));
	rough = mix(rough, mix(0.35, 0.75, old), e * (1.0 - rust));
	metal = mix(metal, 0.45, e * old * (1.0 - rust));

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
		if (streak_cover < 1.0) {
			// 竖着拉长的噪声：流痕区是一条条竖带，上面的源头决定下面湿不湿
			vec3 zp = obj_pos * vec3(1.6, 0.35, 1.6);
			float zn = value_noise(zp + 3.1) * 0.75 + value_noise(zp * 3.1 + 8.7) * 0.25;
			st *= smoothstep(1.0 - streak_cover - 0.1, 1.0 - streak_cover + 0.15, zn);
		}
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

	if (warp_amount > 0.0) {
		// 两层值噪声当高度场，取切向梯度把法线拧歪一点
		vec3 wp = obj_pos * warp_scale;
		const float H = 0.04;
		float h0 = value_noise(wp) + value_noise(wp * 2.7 + 3.3) * 0.35;
		vec3 gr = vec3(value_noise(wp + vec3(H, 0, 0)) + value_noise((wp + vec3(H, 0, 0)) * 2.7 + 3.3) * 0.35,
				value_noise(wp + vec3(0, H, 0)) + value_noise((wp + vec3(0, H, 0)) * 2.7 + 3.3) * 0.35,
				value_noise(wp + vec3(0, 0, H)) + value_noise((wp + vec3(0, 0, H)) * 2.7 + 3.3) * 0.35) - h0;
		gr /= H;
		gr -= n * dot(gr, n);
		nn = normalize(nn - gr * warp_amount * 0.02);
	}

	if (condensation > 0.0) {
		float hgt = smoothstep(cond_height - 0.6, cond_height + 0.7, obj_pos.y);
		float up = smoothstep(0.25, 0.7, n.y);
		// 水珠一片一片地结，不是均匀铺满：大块的湿区 + 凹处（焊缝、肋骨根部、法兰底下）
		vec3 pp = obj_pos * cond_patch_scale;
		float pn = value_noise(pp + 7.3) * 0.7 + value_noise(pp * 2.7 + 1.9) * 0.3;
		float patch = smoothstep(1.0 - cond_patch_cover - 0.08, 1.0 - cond_patch_cover + 0.12, pn);
		float where = clamp(patch + cav * cond_cavity * 1.5, 0.0, 1.0);
		float dens = condensation * (0.12 + 0.45 * hgt) * (1.0 - up) * where * clamp(noise * 1.6 - 0.1, 0.0, 1.0);
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
	if (paint_depth > 0.0) {
		// 屏幕空间凹凸（Mikkelsen 2010）：漆层高度场的屏幕导数推出法线偏转
		vec3 dpdx = dFdx(VERTEX);
		vec3 dpdy = dFdy(VERTEX);
		vec3 r1 = cross(dpdy, NORMAL);
		vec3 r2 = cross(NORMAL, dpdx);
		float det = dot(dpdx, r1);
		vec3 grad = sign(det) * (dFdx(height) * r1 + dFdy(height) * r2) * paint_depth;
		NORMAL = normalize(abs(det) * NORMAL - grad);
	}
	EMISSION = emission_color.rgb * emission_energy;
}
