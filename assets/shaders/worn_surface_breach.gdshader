// 破舱用的 worn_surface：多一个撕开的口子（口子里的像素丢掉）和口子外面一圈崩掉的漆。
// 只在出事那一刻给那一块艇壳的材质换上（breach.gd），平时的材质不带 discard，不影响深度预渲染。
shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_back, diffuse_burley, specular_schlick_ggx;

#define BREACH
#include "res://assets/shaders/worn_surface.gdshaderinc"
