// 声呐 PPI 画面（画在 SonarDisplay 的离屏 SubViewport 里，再由 crt_sonar 贴到显像管上）。
// 艏向朝上：屏幕正上方是船头，方位顺时针增加。
// returns：极坐标回波图，横向 = 方位（0..1，顺时针），纵向 = 距离（0..1）。每一列在波束扫过时由脚本刷新，
// 屏幕上按「离上次扫过多久」算余辉：刚扫过的一列最亮，一圈以后剩一层暗的残影。
shader_type canvas_item;

uniform sampler2D returns : filter_linear, repeat_enable;
uniform float sweep = 0.0;             // 波束当前方位 0..1
uniform float gain = 1.0;
uniform float afterglow = 0.28;        // 余辉残留（一圈之后剩多少）
uniform float rings = 4.0;             // 距离环个数
uniform float cursor_brg = 0.117;      // 电子方位线（0..1）
uniform float cursor_rng = 0.375;      // 活动距离圈（0..1）
uniform float px = 0.004;              // 一个像素在屏幕坐标里的宽度（2 / 分辨率）


float line(float d, float w) {
	return smoothstep(w + px, w * 0.3, abs(d));
}

void fragment() {
	vec2 p = (UV - 0.5) * 2.0 * vec2(1.0, -1.0) / 0.96;
	float r = length(p);
	float brg = fract(atan(p.x, p.y) / TAU);
	float age = fract(sweep - brg);   // 0 = 波束刚扫过

	// 回波：刚扫过时是一层蓝白的闪光，衰减成黄绿色的长余辉
	// 波束有一定宽度：沿方位方向和相邻两列混一点，免得一列一列的楔形太硬
	float db = 1.0 / float(textureSize(returns, 0).x);
	float e = (texture(returns, vec2(brg, r)).r * 0.5 + texture(returns, vec2(brg - db, r)).r * 0.25
		+ texture(returns, vec2(brg + db, r)).r * 0.25) * gain;
	float flash = exp(-age * 28.0);
	float glow = mix(afterglow, 1.0, exp(-age * 2.2));
	vec3 col = vec3(0.55, 1.0, 0.3) * e * glow + vec3(0.6, 0.9, 1.0) * e * flash * 0.9;

	// 波束：一条亮线，后面拖一小片扇形余晖
	float beam = exp(-age * 260.0) * 0.9 + exp(-age * 18.0) * 0.07;
	col += vec3(0.5, 1.0, 0.55) * beam * smoothstep(1.0, 0.9, r);

	// 刻度：距离环、外圈方位刻度、艏向线、电子方位线和活动距离圈（都是虚线）
	float g = 0.0;
	for (float k = 1.0; k < rings + 0.5; k += 1.0) {
		g += line(r - k / rings, px * 0.6) * (k == rings ? 0.9 : 0.45);
	}
	// 外圈方位刻度：每 5° 一短线，10° 中线，30° 长线
	float deg = brg * 360.0;
	float n5 = floor(deg / 5.0 + 0.5);
	float arc = (deg - n5 * 5.0) / 57.29578 * r;
	float tl = mod(n5, 6.0) < 0.5 ? 0.08 : (mod(n5, 2.0) < 0.5 ? 0.045 : 0.022);
	g += line(arc, px * 0.6) * step(1.0 - tl, r) * step(r, 1.0) * 0.8;
	float head = line(p.x, px * 0.7) * step(0.0, p.y) * step(r, 1.0) * step(0.5, fract(r * 20.0));
	g += head * 0.6;
	vec2 cd = vec2(sin(cursor_brg * TAU), cos(cursor_brg * TAU));
	float along = dot(p, cd);
	float ebl = line(dot(p, vec2(cd.y, -cd.x)), px * 0.6) * step(0.0, along) * step(r, 1.0) * step(0.45, fract(along * 26.0));
	float vrm = line(r - cursor_rng, px * 0.6) * step(0.5, fract(brg * 90.0));
	g += (ebl + vrm) * 0.55;
	// 本艇：中心一个小十字
	g += (line(p.x, px * 0.6) + line(p.y, px * 0.6)) * step(max(abs(p.x), abs(p.y)), 0.035) * 0.8;
	col += vec3(0.45, 0.95, 0.5) * g * 0.55;

	// 屏幕外圈之外是黑的
	col *= step(r, 1.02);
	COLOR = vec4(col, 1.0);
}
