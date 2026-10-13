// 层壳头发（blender/scripts/gen_head_vitruvian.py 的 build_shells）：头皮那片往外复制了好几层，顶点色 R 是第几层（0 贴着头皮，1 发梢）、
// G 是发量（发际线处渐稀）、B A 是梳的方向在头皮 UV 里的方向（Blender 的 UV，v 朝上）。
// 顺着梳的方向画：横着一根一根（strands 根 / UV 单位），顺着一段一段（segment 倍发丝间距长，短发短、顺下来的头发长），
// 几根一束（clump），往外的层发丝越来越细、越来越少；最底层按发量铺满（发根，盖住头皮），发际线用低频噪声打散。
// 远了一根发丝不到一个像素时换成按发束的覆盖率（不闪、也不是一块平的颜色）；高光顺着梳的方向拉长
shader_type spatial;
render_mode cull_back, diffuse_burley, specular_schlick_ggx;

uniform vec3 hair_color : source_color = vec3(0.03, 0.026, 0.024);
uniform float strands = 2600.0;
uniform float segment = 8.0;
uniform float clump = 7.0;
uniform float flow_flip = 1.0;
uniform float roughness : hint_range(0.2, 0.9) = 0.45;
uniform float base_layer : hint_range(0.0, 1.0) = 1.0;   // 最底层铺不铺（寸头不铺：头皮上的发茬由皮肤着色器画）
uniform float cover : hint_range(0.0, 1.0) = 1.0;        // 远看时的覆盖率（寸头稀一点，只剩一层绒毛）

float hash(vec2 p) {
	return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}

float vnoise(vec2 p) {
	vec2 i = floor(p);
	vec2 f = fract(p);
	f = f * f * (3.0 - 2.0 * f);
	return mix(mix(hash(i), hash(i + vec2(1, 0)), f.x), mix(hash(i + vec2(0, 1)), hash(i + vec2(1, 1)), f.x), f.y);
}

void fragment() {
	float l = COLOR.r;
	// 发量：里面实心，只在发际线那一圈用噪声打散
	float dens = clamp(COLOR.g * 1.6 - 0.3 + (vnoise(UV * 90.0) - 0.5) * 0.5, 0.0, 1.0);
	vec2 dir = COLOR.ba * 2.0 - 1.0;
	dir.y = -dir.y * flow_flip;               // Godot 的 UV v 朝下
	dir = normalize(dir + vec2(1e-5, 0.0));
	vec2 perp = vec2(-dir.y, dir.x);
	float across = dot(UV, perp) * strands;
	float along = dot(UV, dir) * strands / segment;
	float sid = floor(across);
	float sf = fract(across) - 0.5;
	float bundle = hash(vec2(floor(across / clump), 1.7));
	float seg = floor(along + hash(vec2(sid, 5.1)) * 8.0);
	float h1 = hash(vec2(sid, seg));
	float slen = mix(0.4, 1.0, hash(vec2(sid, seg + 0.5))) * mix(0.75, 1.1, bundle);
	float exist = step(hash(vec2(sid, seg + 0.25)), dens);
	float rad = 0.42 * (1.0 - 0.75 * l / slen);
	float strand = exist * step(l, slen) * smoothstep(rad, rad * 0.4, abs(sf));
	// 远了：发丝不到一个像素，按发束覆盖率
	float far = smoothstep(0.45, 1.5, fwidth(across));
	float cf = fract(across / clump);
	float bundle_cov = dens * pow(clamp(1.0 - l / mix(0.7, 1.0, bundle), 0.0, 1.0), 0.6)
		* (0.85 + 0.15 * smoothstep(0.0, 0.35, cf) * smoothstep(1.0, 0.65, cf));
	float a = mix(strand, bundle_cov * cover, far);
	if (l < 0.001) {
		// 发根层往发际线里面收一点（外面那圈由皮肤上渐变的头皮压暗接上，不是一道硬边）
		a = (dens - 0.25) * 1.5 * base_layer;
	}
	float tone = mix(h1, bundle, far);
	ALBEDO = hair_color * mix(0.35, 1.0, l) * (0.8 + 0.4 * tone);
	ALPHA = a;
	ALPHA_SCISSOR_THRESHOLD = 0.5;
	ALPHA_ANTIALIASING_EDGE = 0.3;
	ROUGHNESS = roughness + 0.15 * (bundle - 0.5);
	SPECULAR = 0.4;
	ANISOTROPY = 0.7;
	ANISOTROPY_FLOW = dir;
	BACKLIGHT = hair_color * 0.4;
	AO = mix(0.5, 1.0, l);
	AO_LIGHT_AFFECT = 0.3;
}
