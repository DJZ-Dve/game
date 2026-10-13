// 硬表面通用材质：底漆颜色 + 三平面映射的细节贴图 + 曲率顶点色（R=棱边磨损，G=凹槽积垢）。
// 另外叠加：指纹/手摸的油污（改粗糙度）、朝上表面的积灰、竖直方向的水渍流痕。
// 不依赖 UV，适合脚本生成的模型。
shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_back, diffuse_burley, specular_schlick_ggx;

#include "res://assets/shaders/worn_surface.gdshaderinc"
