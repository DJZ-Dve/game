// 巨物「闷雷」体表的大尺度颜色（皮和鳍共用，鳍和皮同色）：格陵兰睡鲨那种暗灰褐，背略深腹略浅，大块的斑驳、零星深色斑点。
// 全按 BodyST（换算成米）铺，全身连续。要先 include giant_baked.gdshaderinc；着色器的 vertex() 里写 G_BODY_VERTEX，fragment() 里调 g_body_color。

group_uniforms body_color;
uniform vec4 dorsal_color : source_color = vec4(0.195, 0.183, 0.172, 1.0);
uniform vec4 flank_color : source_color = vec4(0.26, 0.243, 0.226, 1.0);
uniform vec4 belly_color : source_color = vec4(0.335, 0.318, 0.3, 1.0);
// 背 → 体侧、体侧 → 腹的过渡（|θ/π|）
uniform vec2 dorsal_to_flank = vec2(0.05, 0.55);
uniform vec2 flank_to_belly = vec2(0.6, 0.92);
// 大块斑驳（明暗 ±、冷暖）：两层，平铺尺寸（米）
uniform float mottle_amount : hint_range(0.0, 1.0) = 0.25;
uniform float mottle_tile = 26.0;
uniform float warmth_amount : hint_range(0.0, 1.0) = 0.25;
// 斑点：深色小圆斑（平铺尺寸、浓度、颜色）；腹面少
uniform vec4 spot_color : source_color = vec4(0.11, 0.095, 0.09, 1.0);
uniform float spot_amount : hint_range(0.0, 1.0) = 0.55;
uniform float spot_tile = 7.0;
// 细颗粒的明暗起伏
uniform float grain_amount : hint_range(0.0, 1.0) = 0.25;
// 每个物体（顶点色 B）一点明暗差
uniform float object_tint : hint_range(0.0, 0.3) = 0.05;
group_uniforms;

// 大尺度的部分（背深腹浅、大块斑驳、冷暖、每物体的明暗）只随 BodyST 慢慢变，放在顶点里算（一个顶点一次采样，
// 低模顶点间距三十厘米上下，几米大的斑驳插值足够），片元里只剩一次斑点层的采样。
varying vec3 g_base_col;   // 顶点算好的底色（还没加斑点、细颗粒）
varying vec2 g_pm;         // BodyST 换算成的米（片元里铺斑点用）
varying vec2 g_spot_ctl;   // x = 斑点成片的遮罩，y = 斑点颜色的深浅

// vertex() 里调用（Godot 不许在函数里写 varying，所以用 out 参数，见 G_BODY_VERTEX）
void g_body_vertex(vec2 uv2, float obj_rand, out vec3 base_col, out vec2 pm, out vec2 spot_ctl) {
	vec2 st = g_body(uv2);
	pm = g_body_m(st);
	vec4 n2 = textureLod(noise_tex, vec2(pm.x * 0.8 - pm.y * 0.6, pm.x * 0.6 + pm.y * 0.8) / mottle_tile + 0.37, 0.0);
	float ds = abs(st.y);
	vec3 col = mix(dorsal_color.rgb, flank_color.rgb, smoothstep(dorsal_to_flank.x, dorsal_to_flank.y, ds));
	col = mix(col, belly_color.rgb, smoothstep(flank_to_belly.x, flank_to_belly.y, ds));
	col *= 1.0 + (n2.r - 0.5) * 1.6 * mottle_amount * 2.0;
	// 冷暖：偏褐的块和偏灰青的块
	float w = (n2.g - 0.5) * 2.0 * warmth_amount * 3.0;
	col *= vec3(1.0 + w * 0.12, 1.0, 1.0 - w * 0.12);
	col *= 1.0 + (obj_rand - 0.5) * object_tint * 2.0;
	base_col = col;
	// 零星深色斑点：成片出现（n2.a 决定哪里有，约三成面积），背上、体侧多，腹面淡
	spot_ctl = vec2(smoothstep(0.45, 0.6, n2.a) * spot_amount * (1.0 - smoothstep(0.55, 0.85, ds) * 0.8), 0.85 + 0.3 * n2.r);
}

#define G_BODY_VERTEX { vec3 _bc; vec2 _pm; vec2 _sc; g_body_vertex(UV2, COLOR.b, _bc, _pm, _sc); g_base_col = _bc; g_pm = _pm; g_spot_ctl = _sc; }

// fragment() 里调用：返回反照率（线性）。noise_out = 斑点那一层的噪声采样（R 斑驳 G 另一张斑驳 B 斑点 A 颗粒，
// 别处想要随机就拿它，不用再采样）
vec3 g_body_color(out vec4 noise_out) {
	vec4 n1 = texture(noise_tex, g_pm / spot_tile);
	noise_out = n1;
	vec3 col = g_base_col * (1.0 + (n1.r - 0.5) * 0.9 * mottle_amount * 2.0);
	col *= 1.0 + (n1.a - 0.5) * grain_amount * 2.0;
	float sp = smoothstep(0.1, 0.5, n1.b) * g_spot_ctl.x;
	col = mix(col, spot_color.rgb * g_spot_ctl.y, clamp(sp, 0.0, 1.0));
	return max(col, vec3(0.0));
}
