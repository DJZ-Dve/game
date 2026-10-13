// 进水的舱：几个水相关的着色器共用（flood_post / flood_surface / breach_jet / flood_particle）。
// 坐标都换到舱内局部坐标（Body：x 右舷、y 上、-z 艏，耐压舱轴线在 y = 0、x = 0）算：
// 灌了水的部分 = 耐压舱圆筒（半径 flood_radius）里、这个舱的前后范围（flood_z）里、水位（flood_level）以下。
// 视线穿过这块水的那一段长度，按浑水的消光系数衰减、往水的颜色上混（被灯照着的浑水本身也发一点光）。
// 参数由 scripts/breach.gd 每帧更新。

uniform vec3 flood_origin = vec3(0.0);           // 舱内局部坐标原点（世界坐标）
uniform vec3 flood_ax = vec3(1.0, 0.0, 0.0);     // 局部 x、y、z 轴（世界坐标，单位长）
uniform vec3 flood_ay = vec3(0.0, 1.0, 0.0);
uniform vec3 flood_az = vec3(0.0, 0.0, 1.0);
uniform float flood_level = -10.0;               // 水面高度（局部 y）
uniform vec2 flood_z = vec2(-2.95, 2.6);         // 这个舱的前后范围（局部 z）
uniform float flood_radius = 1.35;
// 浑水：搅起来的舱底脏水、气泡、碎屑，一两米外就看不清了
uniform float flood_extinction = 1.1;            // 每米
uniform vec3 flood_color : source_color = vec3(0.035, 0.05, 0.045);  // 被舱里的灯照着的浑水（灯灭了 breach.gd 跟着压暗）

vec3 flood_local(vec3 world) {
	vec3 d = world - flood_origin;
	return vec3(dot(d, flood_ax), dot(d, flood_ay), dot(d, flood_az));
}

// 线段 a → b（局部坐标）落在水里的长度
float flood_path(vec3 a, vec3 b) {
	vec3 d = b - a;
	float t0 = 0.0;
	float t1 = 1.0;
	// 水位以下
	if (abs(d.y) < 1e-6) {
		if (a.y >= flood_level) {
			return 0.0;
		}
	} else {
		float th = (flood_level - a.y) / d.y;
		if (d.y > 0.0) {
			t1 = min(t1, th);
		} else {
			t0 = max(t0, th);
		}
	}
	// 舱的前后范围
	if (abs(d.z) < 1e-6) {
		if (a.z < flood_z.x || a.z > flood_z.y) {
			return 0.0;
		}
	} else {
		float za = (flood_z.x - a.z) / d.z;
		float zb = (flood_z.y - a.z) / d.z;
		t0 = max(t0, min(za, zb));
		t1 = min(t1, max(za, zb));
	}
	// 耐压舱圆筒里
	float A = dot(d.xy, d.xy);
	float C = dot(a.xy, a.xy) - flood_radius * flood_radius;
	if (A < 1e-8) {
		if (C > 0.0) {
			return 0.0;
		}
	} else {
		float B = dot(a.xy, d.xy);
		float disc = B * B - A * C;
		if (disc < 0.0) {
			return 0.0;
		}
		float s = sqrt(disc);
		t0 = max(t0, (-B - s) / A);
		t1 = min(t1, (-B + s) / A);
	}
	return max(t1 - t0, 0.0) * length(d);
}

// 透过率（1 没有水，0 完全看不见）
float flood_trans(vec3 cam_world, vec3 p_world) {
	float L = flood_path(flood_local(cam_world), flood_local(p_world));
	return exp(-flood_extinction * L);
}

bool flood_under(vec3 world) {
	vec3 p = flood_local(world);
	return p.y < flood_level && p.z > flood_z.x && p.z < flood_z.y && dot(p.xy, p.xy) < flood_radius * flood_radius;
}
