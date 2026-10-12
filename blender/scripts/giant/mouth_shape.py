"""嘴腔形状（闭嘴静止姿态）：上颚 / 口底的截面、牙床脊（牙从这里长出来）、外皮限高（嘴里的东西不能穿出头皮和下颌皮）。

截面都在 y = 常数 的平面里（每个 s 一排）。半截面从牙床线（spec.gum_point，皮在这里结束）往中线走：
  牙床线 → 唇侧牙龈坡 → 牙床脊（往嘴缝方向鼓一点，牙长在这条脊上）→ 舌侧牙龈坡 → 陡壁 → 上颚穹顶 / 口底（中间是基舌骨垫）。
h(d) = 离开嘴缝往颌里的深度（上颚往上、口底往下为正），d = 离牙床线往里的水平距离。"""
import math

import numpy as np
from mathutils import Vector as V

from giant import spec

HINGE_S = spec.JAW_HINGE_S


class Curve:
    """一维保形三次插值（关键点之间平滑，不过冲）。"""

    def __init__(self, keys):
        k = np.array(keys, dtype=np.float64)
        self.x, self.y = k[:, 0], k[:, 1]
        h = np.diff(self.x)
        d = np.diff(self.y) / h
        m = np.zeros_like(self.y)
        for i in range(1, len(self.x) - 1):
            if d[i - 1] * d[i] > 0:
                w1, w2 = 2 * h[i] + h[i - 1], h[i] + 2 * h[i - 1]
                m[i] = (w1 + w2) / (w1 / d[i - 1] + w2 / d[i])
        m[0], m[-1] = d[0], d[-1]
        self.m = m

    def __call__(self, s):
        x, y, m = self.x, self.y, self.m
        s = min(max(s, x[0]), x[-1])
        i = int(np.searchsorted(x, s, side="right") - 1)
        i = min(max(i, 0), len(x) - 2)
        h = x[i + 1] - x[i]
        t = (s - x[i]) / h
        h00, h10, h01, h11 = 2 * t**3 - 3 * t**2 + 1, t**3 - 2 * t**2 + t, -2 * t**3 + 3 * t**2, t**3 - t**2
        return float(h00 * y[i] + h10 * h * m[i] + h01 * y[i + 1] + h11 * h * m[i + 1])


def _ss(a, b, x):
    t = min(max((x - a) / (b - a), 0.0), 1.0)
    return t * t * (3 - 2 * t)


# ---------------------------------------------------------------------------- 外皮限高
def outer_z(s, x, upper):
    """外皮在 (s, x) 处的高度：upper 取头的背侧（上颚往上不能超过它），否则取下颌腹侧（口底往下不能低于它）。
    s < 0 只对下颌有意义（spec.jaw_surface 的伸出部分）。"""
    if s < 0 and not upper:
        t = s / spec.JAW_FRONT_S
        shrink = 1.0 - 0.3 * t
        zm = spec.mouth_z(0.0)
        z0 = outer_z(0.0, x / shrink, False)
        return (z0 - zm) * shrink + zm + 0.3 * t
    hw, ht, hb, zc, e = spec.section(max(s, 0.0))
    ax = min(abs(x) / hw, 0.999)
    f = (1.0 - ax ** e) ** (1.0 / e)
    return zc + ht * f if upper else zc - hb * f


# ---------------------------------------------------------------------------- 截面参数
# 上颚穹顶高度（牙床线以上，米）
PAL_H = Curve([(0.0, 0.0), (0.006, 0.30), (0.02, 0.80), (0.05, 1.20), (0.10, 1.55), (0.15, 1.70), (0.20, 1.55)])
# 口底深度（下牙床线以下，米）
FLO_H = Curve([(-0.02, 0.0), (-0.012, 0.10), (0.0, 0.20), (0.02, 0.32), (0.05, 0.75), (0.08, 1.15),
               (0.12, 1.45), (0.155, 1.30), (0.20, 0.65)])
# 基舌骨垫（口底中间隆起的软骨垫）高度、半宽
TONGUE_H = Curve([(-0.02, 0.0), (0.06, 0.0), (0.10, 0.08), (0.14, 0.14), (0.18, 0.16), (0.20, 0.14)])
TONGUE_W = 0.8
# 牙床脊内侧的沟（对面牙尖的落脚处）有多深
GUT_P = Curve([(0.0, 0.0), (0.05, 0.0), (0.075, 0.35), (0.12, 0.45), (0.17, 0.35), (0.20, 0.15)])
GUT_F = Curve([(-0.02, 0.0), (0.04, 0.0), (0.07, 0.25), (0.11, 0.3), (0.16, 0.2), (0.20, 0.0)])
# 牙床脊：离牙床线 CREST_D 米，往嘴缝方向鼓 CREST_C 米
CREST_D = 0.26
CREST_C = 0.11
# 上颚牙槽附近（s 0.012～0.065）没有上牙，脊放平成一块搁板，穹顶往中线退，好开牙槽
SOCKET_ZONE = (0.008, 0.02, 0.055, 0.075)


def _socket_w(s):
    a, b, c, d = SOCKET_ZONE
    return _ss(a, b, s) * (1.0 - _ss(c, d, s))


def gum_x(s, upper=True):
    return spec.gum_point(s, 1, upper).x


def gum_z(s, upper=True):
    return spec.gum_point(s, 1, upper).z


def h_profile(s, d, upper):
    """离牙床线往里 d 米处，往颌里的深度 h（只是形体，不含高模细节）。d 可以是数组。"""
    d = np.asarray(d, dtype=np.float64)
    D = max(gum_x(s, upper), 1e-3)
    ramp = _ss(0.0, 0.012, s) if upper else _ss(spec.JAW_FRONT_S, spec.JAW_FRONT_S + 0.012, s)
    C = CREST_C * ramp
    if upper:
        H = PAL_H(s)
        sw = _socket_w(s)
        C *= 1.0 - 0.8 * sw
        d0 = 0.42 + 0.55 * sw
        p = 3.4
    else:
        H = FLO_H(s)
        d0 = 0.42
        p = 4.2
    d0 = min(d0, 0.55 * D)
    dc = min(CREST_D, 0.3 * D)
    bump = np.where(d < 2 * dc, np.sin(np.pi * np.clip(d / (2 * dc), 0, 1)) ** 2, 0.0)
    t = np.clip((d - d0) / max(D - d0, 1e-3), 0.0, 1.0)
    vault = 1.0 - (1.0 - t) ** p
    h = -C * bump + H * vault
    # 牙床脊内侧一道深沟：闭嘴时对面的牙尖落在这里（上颚给下牙、口底给上牙）
    G = (GUT_P(s) if upper else GUT_F(s))
    h = h + G * np.exp(-((d - (d0 + 0.32)) / 0.30) ** 2)
    if upper:
        # 上颚几道纵向的褶（两侧各三道）+ 中缝一道浅沟，前后都淡出
        fold = _ss(0.02, 0.06, s) * (1.0 - 0.5 * _ss(0.17, 0.2, s))
        x = D - d
        r = np.zeros_like(d)
        for xc, a, w in ((0.55, 0.05, 0.20), (1.25, 0.08, 0.26), (2.05, 0.07, 0.28), (2.8, 0.05, 0.26)):
            r += a * np.exp(-((x - xc) / w) ** 2)
        r -= 0.06 * np.exp(-(x / 0.14) ** 2)
        h = h - r * fold * np.clip(t * 3, 0, 1)
    else:
        th = TONGUE_H(s)
        x = D - d
        pad = np.clip(1.0 - (x / TONGUE_W) ** 4, 0.0, 1.0) ** 0.8
        # 垫子两边各有一道沟（口底最深处）
        groove = 0.10 * np.exp(-((x - TONGUE_W * 1.05) / 0.3) ** 2) * _ss(0.06, 0.1, s)
        h = h - th * pad + groove
    return h


def depth_limit(s, x, upper):
    """嘴里的面离外皮至少留这么厚（颅骨 / 下颌骨）。下颌前端本来就薄（牙床线离下颌皮只有几十厘米），按可用厚度打折。"""
    avail = abs(outer_z(s, x, upper) - gum_z(s, upper))
    if upper:
        return min(0.50, 0.5 * avail)
    return max(0.05, min(0.24, 0.45 * avail))


def point(s, d, upper, side=1):
    """截面上的点（3D）：side 左右。d 可为标量。"""
    gx, gz = gum_x(s, upper), gum_z(s, upper)
    h = float(h_profile(s, np.array([d]), upper)[0])
    x = gx - d
    z = gz + h if upper else gz - h
    lim = outer_z(s, x, upper)
    m = depth_limit(s, x, upper)
    if upper:
        z = _smin(z, lim - m, 0.25)
    else:
        z = -_smin(-z, -(lim + m), 0.25)
    return V((side * x, spec.y_of(s), z))


def _smin(a, b, k):
    h = max(k - abs(a - b), 0.0) / k
    return min(a, b) - h * h * k * 0.25


def half_row(s, upper, n, n_gum=7, gum_arc=0.95):
    """半截面：从牙床线到中线 n 个点（3D，右侧），按弧长排：前 gum_arc 米给 n_gum 个点（牙床那段密），其余均匀。"""
    D = gum_x(s, upper)
    ds = np.linspace(0.0, D, 240)
    pts = [point(s, d, upper) for d in ds]
    arr = np.array([[p.x, p.z] for p in pts])
    seg = np.linalg.norm(np.diff(arr, axis=0), axis=1)
    acc = np.concatenate([[0.0], np.cumsum(seg)])
    total = acc[-1]
    ga = min(gum_arc, 0.45 * total)
    targ = np.concatenate([np.linspace(0, ga, n_gum)[:-1], np.linspace(ga, total, n - n_gum + 1)])
    dd = np.interp(targ, acc, ds)
    return [point(s, d, upper) for d in dd], dd


def full_row(s, upper, n_half, **kw):
    """整排：从右牙床线经过中线到左牙床线（2*n_half - 1 个点）。返回点表和每个点的 d（左右都是离牙床线的距离）。"""
    half, dd = half_row(s, upper, n_half, **kw)
    right = half
    left = [V((-p.x, p.y, p.z)) for p in reversed(half[:-1])]
    return right + left, np.concatenate([dd, dd[::-1][1:]])


def crest_point(s, upper, side=1):
    """牙床脊上的点（牙根中心从这里往颌里埋）和该处截面上的「往嘴缝」方向。"""
    dc = min(CREST_D, 0.3 * gum_x(s, upper))
    p = point(s, dc, upper, side)
    return p


def cavity_z(s, x, upper):
    """嘴腔表面在 (s, |x|) 处的高度（解析形体，不含牙槽、褶的高模细节）。"""
    d = gum_x(s, upper) - abs(x)
    if d < 0:
        return gum_z(s, upper)
    return point(s, d, upper).z
