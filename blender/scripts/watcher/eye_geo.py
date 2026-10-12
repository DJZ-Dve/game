"""眼的基础形体（低模、高模共用）：眼球局部坐标、虹膜的碟形剖面、竖瞳凹槽、虹膜用的椭圆坐标、角膜剖面。

眼球局部坐标（右手系）：ez = 眼轴（世界 +Y，朝前），ey = 上（世界 +Z），ex = 世界 -X
（也就是站在它正前方看它时的「右」——UV 的虹膜岛按这个平面投影，不是镜像）。
  平面坐标 (x, y)：垂直于眼轴的平面，原点在眼轴上；z：沿眼轴离眼球中心的距离。
  球面方向 (θ, φ)：θ 离眼轴的角度，φ 在 (ex, ey) 平面里从 ex 往 ey 量。

虹膜（ρ = √(x²+y²) ≤ RHO_L）：不是贴在球面上，而是往里收的一只浅碟——中心（瞳孔处）比球面顶点低 0.75 米，
  往外慢慢降到虹膜根部（RHO_ROOT），根部一圈沟（虹膜根和角膜缘之间的「房角」），再陡陡地爬回球面接上巩膜
  （角膜缘 = RHO_L，θ = 44°）。角膜罩在上面，前房（角膜和虹膜之间）中心深 1 米多——看进去是「深」的。
  瞳孔区（以眼轴为中心的竖长透镜形）再往下凹 0.10 米；瞳孔边缘以内到领圈（collarette）的瞳孔区略鼓。
虹膜椭圆坐标 (μ, ν)：焦点在 (0, ±FOC) 的共焦椭圆 / 双曲线。μ = 常数的椭圆一圈圈围着竖缝（越往外越圆），
  ν = 常数的双曲线从竖缝往外放射——虹膜纤维就顺着 ν 走，收缩沟顺着 μ 走。
  s = 0（瞳孔边缘，μ = MU_P）～ 1（虹膜根部的圆 RHO_ROOT）是归一化的径向位置。
"""
import math

import numpy as np

from watcher import spec
from watcher import eye_util as U

R = spec.EYE_R
C = np.array(spec.EYE_CENTER, dtype=np.float64)
EX = np.array((-1.0, 0.0, 0.0))
EY = np.array((0.0, 0.0, 1.0))
EZ = np.array((0.0, 1.0, 0.0))

TH_L = math.radians(44.0)          # 角膜缘（虹膜 / 巩膜分界）离眼轴的角度
RHO_L = R * math.sin(TH_L)         # 角膜缘在平面上的半径（3.06 米）
RHO_ROOT = 2.85                    # 虹膜根部（碟底外沿）的半径
Z_C = 3.65                         # 虹膜中心（瞳孔处）离眼球中心的轴向距离（球面顶点是 R = 4.4）
Z_ROOT = 3.0                       # 虹膜根部的轴向距离
DOME_A = (Z_C - Z_ROOT) / RHO_ROOT ** 2
SULCUS_D, SULCUS_W, SULCUS_AT = 0.06, 0.06, RHO_ROOT + 0.02   # 根部那圈沟

FOC = 1.85                         # 椭圆坐标的焦点（0, ±FOC）
PUPIL_HW = 0.30                    # 瞳孔边缘那个椭圆（μ = MU_P）的半宽
MU_P = math.asinh(PUPIL_HW / FOC)
PUPIL_A, PUPIL_B, PUPIL_D = 0.30, 1.95, 0.10   # 竖瞳凹槽：最宽处半宽、半长、深度
COLLARETTE_S = 0.34                # 领圈的位置（s）
PLATEAU = 0.025                    # 领圈以内的瞳孔区鼓起多少

CORNEA_B = 0.33                    # 角膜顶比眼球顶多鼓出多少（离眼球中心 R + 0.33 = 4.73）
TH_C = math.radians(50.0)          # 角膜边缘（贴回眼球、略埋进去）离眼轴的角度


def sphere_dir(th, ph):
    th, ph = np.asarray(th, dtype=np.float64), np.asarray(ph, dtype=np.float64)
    st = np.sin(th)[..., None]
    return st * (np.cos(ph)[..., None] * EX + np.sin(ph)[..., None] * EY) + np.cos(th)[..., None] * EZ


def plane_to_world(x, y, z):
    x, y, z = (np.asarray(a, dtype=np.float64)[..., None] for a in (x, y, z))
    return C + x * EX + y * EY + z * EZ


# ---------------------------------------------------------------------------- 虹膜的椭圆坐标
def elliptic(x, y):
    """平面 (x, y) → (μ ≥ 0, ν ∈ [-π, π])：x = FOC·sinhμ·sinν，y = FOC·coshμ·cosν（ν = 0 朝上）。"""
    w = np.arccosh((np.asarray(y) + 1j * np.asarray(x)) / FOC)
    return w.real, w.imag


def from_elliptic(mu, nu):
    return FOC * np.sinh(mu) * np.sin(nu), FOC * np.cosh(mu) * np.cos(nu)


def mu_root(nu):
    """沿 ν 这条双曲线走到虹膜根部圆（RHO_ROOT）时的 μ。"""
    return np.arcsinh(np.sqrt(np.maximum((RHO_ROOT / FOC) ** 2 - np.cos(nu) ** 2, 1e-9)))


def iris_s(mu, nu):
    return (mu - MU_P) / (mu_root(nu) - MU_P)


def fiber_len(nu):
    """沿纤维从瞳孔边缘到虹膜根部大约多少米（把 s 换成米用）。"""
    rp = FOC * np.sqrt(np.sinh(MU_P) ** 2 + np.cos(nu) ** 2)
    return RHO_ROOT - rp


# ---------------------------------------------------------------------------- 基础剖面
def pupil_groove(x, y):
    """竖瞳凹槽的深度（≥0）：透镜形（两头尖），中间最宽 PUPIL_A。"""
    ay = np.abs(y) / PUPIL_B
    w = PUPIL_A * np.clip(1 - ay ** 2, 1e-4, None) ** 0.6
    g1 = 1 - U.smoothstep(0.45, 1.35, np.abs(x) / w)
    g2 = 1 - U.smoothstep(0.7, 1.0, ay)
    return PUPIL_D * g1 * g2


def iris_z(x, y):
    """虹膜区（含根部的沟和爬回球面的那段）的轴向高度；ρ ≥ RHO_L 处就是球面。"""
    x, y = np.asarray(x, dtype=np.float64), np.asarray(y, dtype=np.float64)
    rho = np.hypot(x, y)
    mu, nu = elliptic(x, y)
    s = iris_s(mu, nu)
    zd = Z_C - DOME_A * rho ** 2
    valley = SULCUS_D * np.exp(-((rho - SULCUS_AT) / SULCUS_W) ** 2)
    plateau = PLATEAU * (1 - U.smoothstep(COLLARETTE_S - 0.06, COLLARETTE_S + 0.06, s))
    inner = zd - valley + plateau - pupil_groove(x, y)
    w = U.smoothstep(RHO_ROOT, RHO_L, rho)
    zs = np.sqrt(np.maximum(R * R - rho * rho, 0.0))
    return inner * (1 - w) + zs * w


def iris_area(rho):
    """mask.A：虹膜 1，往外过了根部的沟沿着那段坡降到角膜缘处的 0。"""
    return 1 - U.smoothstep(RHO_ROOT, RHO_L, rho)


# ---------------------------------------------------------------------------- 角膜
def cornea_r(t):
    """角膜离眼球中心的距离，t = θ / TH_C（0 顶点，1 边缘）。边缘略埋进眼球（−2.5 厘米）。"""
    t = np.asarray(t, dtype=np.float64)
    return R + CORNEA_B * np.clip(1 - t * t, 0, None) ** 1.25 - 0.025 * t ** 6
