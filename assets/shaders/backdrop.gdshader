// 窗外 150 米以外和天空：Cycles 预渲染的全景条（blender/scripts/render_backdrop.py），贴在以窗户眼点为圆心、
// 半径 600 米的一段圆柱面上（dorm.gd 建的网格，UV 就是全景图的坐标）。雨雾、灯的光晕都已经烘在图里，
// 所以不吃雾（fog_disabled），也不受灯光（unshaded）。
// 颜色 = 夜景 × (1 - 发光份额 × 灭了多少) → 和闪电版按闪电亮度混合 → 越往上越淡到环境背景（圆柱上面露出来的夜空）
// → 闪电时再加上体积雾被闪电照亮的那层（圆柱外面的天和 3D 近景都有，圆柱不吃雾，自己补上）。
// 发光份额（dorm_glow.png）：每个像素里亮窗、灯和它们的光晕占夜景亮度的比例，拿它让几扇窗偶尔灭、远处一盏灯闪。
shader_type spatial;
render_mode unshaded, fog_disabled, cull_disabled, shadows_disabled, ambient_light_disabled, depth_draw_opaque;

uniform sampler2D night_tex : filter_linear_mipmap_anisotropic, repeat_disable;
uniform sampler2D flash_tex : filter_linear_mipmap, repeat_disable;
uniform sampler2D glow_tex : filter_linear_mipmap_anisotropic, repeat_disable;
uniform float gain = 0.8;                 // 夜景地平线以上再压一点：天边的雾别比 3D 的船壳、吊车亮（它们要成剪影）
// 地平线以下（150 米外的地面，和 3D 地面的深度雾在 150 米处接着）不压：图里的雾已经按 3D 雾的公式算过，
// 再乘 gain 会比紧挨着的 3D 地面暗三四成，出现一道直线接缝。仰角 tan 从 0 到 gain_ramp 慢慢压到 gain
uniform float gain_ramp = 0.05;
uniform float flash_gain = 2.6;           // 闪电版提亮：屋里看窗外那一下天要亮得晃眼，吊车、楼成剪影
uniform float flash_amt = 0.0;            // 闪电亮度（0~1），dorm.gd 每帧跟着 story_room 的闪电设
uniform vec2 tan_range = vec2(-0.0874887, 0.8433315);   // 全景图竖直范围：tan(仰角)，下沿、上沿
// 天：圆柱上沿外面的夜空（环境背景色 × 亮度，dorm.gd 每帧给）；从 sky_fade 的仰角（tan）开始往它淡，到上沿正好是它
uniform vec3 sky_top = vec3(0.0);
uniform float sky_dim = 0.8;              // 背景前面还隔着一层体积雾（18 米，透过率约 0.8）
uniform vec2 sky_fade = vec2(0.18, 0.8433315);
// 闪电照亮的体积雾：往闪电那边看最亮（Henyey-Greenstein，和 dorm_env 的 volumetric_fog_anisotropy 一样 0.4）
uniform vec3 flash_dir = vec3(0.0, 0.43, -0.9);   // 指向闪电（世界坐标）
uniform vec3 flash_fog = vec3(0.0);       // 闪电最亮那一下，雾往前散射的亮度（× 相位函数）
uniform float flash_fog_low = 0.35;       // 低处只补这么多（留住闪电版里云的纹理），越往上越接近圆柱外面的天
uniform float animate = 1.0;              // 0：窗户不灭、灯不闪（截图时，前后两次拍得一样）
uniform vec2 cells = vec2(256.0, 80.0);   // 亮窗按格子各自灭/亮（约 0.6° 一格）
uniform float off_ratio = 0.035;          // 任一时刻灭着的格子比例（有人关灯睡觉、停电的那几户）
uniform vec2 flicker_uv = vec2(-1.0);     // 远处那盏快坏的钠灯（全景图 UV），附近一圈跟着它闪
uniform vec2 flicker_size = vec2(0.004, 0.012);

float hash(vec2 p) {
	vec3 q = fract(vec3(p.xyx) * 0.1031);
	q += dot(q, q.yzx + 33.33);
	return fract((q.x + q.y) * q.z);
}

void fragment() {
	vec2 uv = UV;
	vec3 night = texture(night_tex, uv).rgb;
	float glow = texture(glow_tex, uv).r;
	// 亮窗偶尔灭、过一阵又亮：每格有自己的节奏（25~70 秒换一次），换的那一下是看不出过渡的开关
	vec2 cell = floor(uv * cells);
	float period = mix(25.0, 70.0, hash(cell + 7.1));
	float k = floor(TIME / period + hash(cell) * 13.0);
	float dim = step(hash(cell + k * 1.37), off_ratio);
	// 那盏钠灯：大部分时候亮着，隔一阵（约 9 秒一轮）抽一下，和院子里路灯的毛病一样但不同步
	vec2 dq = (uv - flicker_uv) / flicker_size;
	float near = 1.0 - smoothstep(0.6, 1.0, length(dq));
	float t = TIME * 0.11;
	float burst = smoothstep(0.82, 0.86, fract(t)) * (1.0 - smoothstep(0.93, 0.95, fract(t)));
	float sputter = 0.5 + 0.5 * sin(TIME * 23.0) * sin(TIME * 7.7);
	dim = max(dim, near * burst * (1.0 - sputter * 0.6));
	vec3 col = night * (1.0 - glow * dim * animate);
	float tan_el = mix(tan_range.y, tan_range.x, uv.y);
	col = mix(col * mix(1.0, gain, smoothstep(0.0, gain_ramp, tan_el)), texture(flash_tex, uv).rgb * flash_gain, flash_amt);
	// 越往上越淡到夜空：头顶的云离城里的灯远、照不着；上沿和圆柱外面的背景接上
	float up = smoothstep(sky_fade.x, sky_fade.y, tan_el);
	col = mix(col, sky_top * sky_dim, up);
	if (flash_amt > 0.0) {
		vec3 v = normalize(mat3(INV_VIEW_MATRIX) * -VIEW);
		float c = dot(v, normalize(flash_dir));
		float g = 0.4;
		float hg = (1.0 - g * g) / pow(1.0 + g * g - 2.0 * g * c, 1.5);
		col += flash_fog * flash_amt * hg * mix(flash_fog_low, 1.0, up);
	}
	ALBEDO = col;
}
