// 巨物「闷雷」第二版材质的公共部分（giant_skin / giant_fin / giant_mouth / giant_tooth / giant_eye 都 include 这个）。
//
// 第二版是「高模烘焙低模」：形状细节全在烘焙贴图里，着色器只采样、不逐像素算噪声，便宜。
// 每个贴图组（spec.TEXSETS：skin / fins / mouth / eyes）两张图（blender/scripts/giant/bakeutil.py）：
//   <组>_normal.png  切线空间法线（OpenGL Y+），按 UV0（图集）采样
//   <组>_mask.png    R = AO，G = 凹槽，B = 凸棱，A = 区域图（各组含义不同：skin 0 皮 / 0.5 旧疤 / 1 生肉；
//                    fins 1 = 鳍膜薄处；mouth 1 = 牙 / 0 = 肉；eyes 1 = 寄生虫 / 0 = 眼球）
// 两张辅助的可平铺图（tools/gen_giant_noise.py）：
//   giant_noise.png     R、G 大块斑驳，B 零星深色斑点，A 细颗粒——按 BodyST 换算成米铺（全身连续、不跟着图集的岛断开）
//   giant_denticle_n.png / giant_tissue_n.png  盾鳞 / 软组织细沟的细节法线——按 UV0 × 图集米数铺，只在近处显出来
//
// 坐标约定：
//   UV0  = 贴图组图集（0～1，等密度：1 个 UV 单位 = atlas_meters 米，见 <组>.json）
//   UV2  = BodyST（Blender 的 UV1）。glTF 导入翻了 V：s = UV2.x（0 吻端 → 1 尾尖），θ/π = 1 - UV2.y（0 背中线，±1 腹中线）
//   COLOR = 低模曲率（R 棱边、G 凹槽、B 每物体随机）
// 模型是蒙皮的，所有图案只按这三样算，不用物体 / 世界坐标，动起来不会「游」。
//
// 光：深海里只有探照灯，Godot 的 AO 输出只压环境光，所以烘焙的 AO 也按比例乘进反照率（不然灯光下看不出缝和褶）。

uniform sampler2D normal_tex : hint_normal, filter_linear_mipmap_anisotropic, repeat_disable;
uniform sampler2D mask_tex : hint_default_white, filter_linear_mipmap_anisotropic, repeat_disable;
// 1 个 UV0 单位多少米（<组>.json 的 meters）
uniform float atlas_meters = 40.0;
uniform float normal_strength : hint_range(0.0, 2.0) = 1.0;
// 细节法线（皮、鳍：giant_denticle_n 盾鳞；嘴、眼：giant_tissue_n 软组织细沟），BC5，只用 XY
uniform sampler2D detail_tex : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D noise_tex : filter_linear_mipmap, repeat_enable;
// 调试：0 正常；1 AO 2 凹槽 3 凸棱 4 区域图 5 烘焙法线 6 只看反照率 7 细节淡出（白 = 细节全显）
uniform int debug_view : hint_range(0, 7) = 0;

// 身体截面「半周长」（背中线绕到腹中线的弧长，米）随 s 的变化（按 spec._PROFILE 算、六次多项式拟合，误差 < 0.35 米）。
// 把 θ/π 换成米：同一块斑点在头上和尾柄上一样大，不会在细的地方被压扁拉长。（不用常量数组查表：动态下标在有些 GPU 上很慢）
const float G_LENGTH = 42.0;

// UV2 → (s, θ/π)
vec2 g_body(vec2 uv2) {
	return vec2(uv2.x, 1.0 - uv2.y);
}

float g_half_perim(float s) {
	float x = clamp(s, 0.0, 1.0);
	return ((((((-586.185 * x + 1933.992) * x - 2446.872) * x + 1528.994) * x - 542.599) * x + 108.962) * x + 5.143);
}

// BodyST → 体表的「米」坐标（x 沿身体，y 绕身体；接缝在腹中线）
vec2 g_body_m(vec2 st) {
	return vec2(st.x * G_LENGTH, st.y * g_half_perim(st.x));
}

// 切线空间法线（XY 在 0～1 里）→ 单位向量
vec3 g_unpack(vec2 t) {
	vec2 xy = t * 2.0 - 1.0;
	return vec3(xy, sqrt(max(1.0 - dot(xy, xy), 0.0)));
}

// 两层切线空间法线叠加（Whiteout）：细节的倾斜加在底层上
vec3 g_blend(vec3 base, vec3 det) {
	return normalize(vec3(base.xy + det.xy, base.z * det.z));
}

// 细节周期 period（米）在屏幕上够不够大：小于 2 像素时淡没（mpp = 每像素多少米）
float g_detail_fade(float mpp, float period) {
	return clamp((period / max(mpp, 1e-6) - 2.0) * 0.25, 0.0, 1.0);
}

// 每像素多少米：按到相机的距离和视野算（连续、平滑；用 UV 的屏幕导数会一个三角形一个值，细节一条条地断）。
// 掠射角上的压缩交给贴图的各向异性过滤和 mip。用法：g_mpp(VERTEX, PROJECTION_MATRIX[1][1], VIEWPORT_SIZE.y)
float g_mpp(vec3 vertex, float proj11, float vp_h) {
	return max(-vertex.z, 0.01) * 2.0 / (proj11 * vp_h);
}

// 最后写 NORMAL_MAP 的编码（Godot 自己从 XY 重建 Z）
vec3 g_pack(vec3 n) {
	return n * 0.5 + 0.5;
}

// 调试输出：返回 true 就直接用 dbg 当颜色
bool g_debug(vec4 m, vec3 nrm, vec3 albedo, float fade, out vec3 dbg) {
	dbg = vec3(0.0);
	if (debug_view == 0) {
		return false;
	}
	if (debug_view <= 4) {
		dbg = vec3(m[debug_view - 1]);
	} else if (debug_view == 5) {
		dbg = nrm * 0.5 + 0.5;
	} else if (debug_view == 6) {
		dbg = albedo;
	} else {
		dbg = vec3(fade);
	}
	return true;
}
