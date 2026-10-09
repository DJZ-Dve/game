#!/usr/bin/env python3
"""潜艇的音效全部在这里程序化合成，写到 assets/audio/（48 kHz、16 bit WAV）。只用 numpy。
用法: python3 tools/gen_sfx.py [名字前缀...]      （不给参数就全部重新生成）

- 循环音（环境声）在频域里造：噪声按频谱形状给幅度、随机相位，再反变换，天然首尾相接；
  音调成分都取整数个周期，调制、脉冲串也按循环长度绕回去摆，所以循环点没有接缝。
  循环点写进 WAV 的 smpl 块，Godot 导入时自动识别成循环（导入设置 loop_mode 默认「从 WAV 检测」）；
  循环音的导入设置改成不压缩（见 import_pcm），一次性的声音保持默认的 QOA 压缩。
- 一次性的声音（碰撞、门、脚步、吱嘎）用模态合成：激励（冲击脉冲、摩擦的粘滑脉冲串）卷积上一组
  指数衰减的正弦（结构的共振模态）。钢板、门扇、艇壳的差别就是模态频率范围和衰减时间。
- 这里只做归一化（循环音按 RMS -20 dBFS、一次性的按峰值 -3 dBFS），混音比例在 scripts/sub_audio.gd 里调。
- 随机数按声音名字定种子，同一个脚本重跑结果不变。
"""
import re
import struct
import sys
import zlib
from pathlib import Path

import numpy as np

SR = 48000
OUT = Path(__file__).resolve().parent.parent / "assets" / "audio"


# ---------------------------------------------------------------------------- 基本工具
def db(x):
    return 10.0 ** (x / 20.0)


def taxis(n):
    return np.arange(n) / SR


def rms(x):
    return float(np.sqrt(np.mean(np.square(x))) + 1e-12)


def bp(f, lo=None, hi=None, order=2):
    """平滑的带通幅度响应（巴特沃斯形状，order 阶）。"""
    g = np.ones_like(f)
    if lo:
        g = g / np.sqrt(1.0 + (lo / np.maximum(f, 1e-6)) ** (2 * order))
    if hi:
        g = g / np.sqrt(1.0 + (f / hi) ** (2 * order))
    return g


def tilt(f, db_per_oct, ref=1000.0):
    """频谱倾斜：每倍频程升降多少 dB（-3 就是粉红噪声）。"""
    return (np.maximum(f, 1.0) / ref) ** (db_per_oct / 6.0206)


def noise(n, shape, rng):
    """周期性的有色噪声（首尾无缝），单位 RMS。shape(f) 给出幅度谱。"""
    f = np.fft.rfftfreq(n, 1 / SR)
    spec = shape(f) * np.exp(2j * np.pi * rng.random(len(f)))
    spec[0] = 0
    x = np.fft.irfft(spec, n)
    return x / rms(x)


def wobble(n, lo, hi, rng):
    """慢速随机起伏（周期性），单位 RMS，用来做调制。"""
    return noise(n, lambda f: bp(f, lo, hi, 2), rng)


def loopf(f, n):
    """把频率凑成在 n 个采样里正好整数个周期。"""
    return max(1, round(f * n / SR)) * SR / n


def filt(x, shape):
    """零相位静态滤波（一次性的声音用，补零后做，不绕回）。"""
    m = 1 << (2 * len(x) - 1).bit_length()
    f = np.fft.rfftfreq(m, 1 / SR)
    return np.fft.irfft(np.fft.rfft(x, m) * shape(f), m)[: len(x)]


def fftconv(a, b):
    n = len(a) + len(b) - 1
    m = 1 << (n - 1).bit_length()
    return np.fft.irfft(np.fft.rfft(a, m) * np.fft.rfft(b, m), m)[:n]


def cconv(a, b):
    """循环卷积（结果长度和 a 一样，尾巴绕回开头）——循环音里的脉冲串卷模态用。"""
    n = len(a)
    bb = np.zeros(((len(b) + n - 1) // n) * n)
    bb[: len(b)] = b
    bb = bb.reshape(-1, n).sum(axis=0)
    return np.fft.irfft(np.fft.rfft(a) * np.fft.rfft(bb), n)


def place(dst, src, at, circular=False):
    """把 src 叠到 dst 的 at 处（circular 时超出的部分绕回开头）。"""
    n = len(dst)
    if circular:
        idx = (at + np.arange(len(src))) % n
        np.add.at(dst, idx, src)
    else:
        k = max(0, min(len(src), n - at))
        dst[at:at + k] += src[:k]


def mix(*xs):
    """把长短不一的几段叠在一起（短的补零）。"""
    y = np.zeros(max(len(x) for x in xs))
    for x in xs:
        y[: len(x)] += x
    return y


def unit(x):
    """按峰值归一到 1（各成分先归一再按 dB 配比，免得互相牵连）。"""
    return x / (np.abs(x).max() + 1e-12)


def modes(dur, freqs, decays, amps):
    """模态冲激响应：一组从 0 开始的指数衰减正弦。最后 10% 渐弱到 0，截断处不留台阶。"""
    t = taxis(int(dur * SR))
    y = np.zeros_like(t)
    for f, d, a in zip(freqs, decays, amps):
        if f < SR * 0.45:
            y += a * np.exp(-t / d) * np.sin(2 * np.pi * f * t)
    return fade(y, 0.0, dur * 0.1)


def logu(rng, lo, hi, k):
    return np.exp(rng.uniform(np.log(lo), np.log(hi), k))


def pulse(ms):
    """宽 ms 毫秒的升余弦冲击（越宽越闷）。"""
    w = max(2, int(ms * SR / 1000))
    return np.hanning(w + 2)[1:-1]


def burst(ms, shape, rng):
    """短促的有色噪声爆发（擦、刮的颗粒感）。"""
    w = max(4, int(ms * SR / 1000))
    return filt(rng.standard_normal(w), shape) * np.hanning(w)


def stick_slip(n, rate, amp, rng, circular=False):
    """摩擦的粘滑：按瞬时速率 rate(采样数组, Hz) 打脉冲，每个脉冲幅度 amp(t) 再加随机起伏。
    circular 时把总相位凑成整数，脉冲串首尾相接。"""
    ph = np.cumsum(rate) / SR
    if circular:
        ph *= round(ph[-1]) / ph[-1]
    idx = np.nonzero(np.diff(np.floor(ph), prepend=np.floor(ph[0])) > 0)[0]
    x = np.zeros(n)
    x[idx] = amp[idx] * np.clip(1 + 0.45 * rng.standard_normal(len(idx)), 0.1, 2.5)
    return x


def fade(x, fin=0.0, fout=0.0):
    n = len(x)
    e = np.ones(n)
    a, b = int(fin * SR), int(fout * SR)
    if a:
        e[:a] = np.sin(np.linspace(0, np.pi / 2, a)) ** 2
    if b:
        e[n - b:] *= np.cos(np.linspace(0, np.pi / 2, b)) ** 2
    return x * (e if x.ndim == 1 else e[:, None])


def stereo(c, l, r, width):
    """共用成分 c + 左右各自独立的成分，width 越大越开。"""
    return np.stack([c + width * l, c + width * r], axis=1)


# ---------------------------------------------------------------------------- 环境声（循环）
def hull_bed(rng):
    """艇体低鸣：深水压在耐压壳上的低频轰鸣，慢慢起伏；再带一点壳体传进来的远处水流声。"""
    n = 24 * SR
    sh = lambda f: bp(f, 16, 85, 2) * tilt(f, -3, 40)
    c, l, r = (noise(n, sh, rng) for _ in range(3))
    m = np.clip(1 + 0.3 * wobble(n, 0.04, 0.25, rng), 0.35, 2.0)
    hiss = lambda: noise(n, lambda f: bp(f, 110, 480, 2), rng) * db(-26)
    return stereo(c * m, l * m + hiss(), r * m + hiss(), 0.7)


def vent(rng):
    """头顶球形风口的出风：喷口的宽带气流声 + 风管里的低频涌动 + 上游风机隐约的叶片音。"""
    n = 12 * SR
    t = taxis(n)
    air = noise(n, lambda f: bp(f, 260, 4200, 1) * tilt(f, -2.5, 1000), rng)
    air *= 1 + 0.12 * wobble(n, 0.3, 3.0, rng)
    duct = noise(n, lambda f: bp(f, 45, 220, 2), rng) * db(-7)
    duct *= 1 + 0.25 * wobble(n, 0.1, 0.8, rng)
    f0 = loopf(98.0, n)
    wow = 0.6 * wobble(n, 0.08, 0.4, rng)
    fan = sum(k ** -1.5 * np.sin(2 * np.pi * k * f0 * t + k * wow + rng.uniform(0, 6.3)) for k in range(1, 5))
    return air + duct + fan / rms(fan) * db(-24)


def power_hum(rng):
    """配电柜的变压器嗡声：100 Hz（两倍电网频率）带一串谐波，奇次谐波重一点，再削一点顶出“滋”的毛刺。"""
    n = 4 * SR
    t = taxis(n)
    h = sum((k ** -1.1) * (1.6 if k % 2 else 1.0) * np.sin(2 * np.pi * 100 * k * t + rng.uniform(0, 6.3))
            for k in range(1, 17))
    h /= rms(h)
    x = 0.7 * h + 0.3 * np.tanh(2.5 * h)
    x *= 1 + 0.04 * np.sin(2 * np.pi * 0.5 * t)
    x += noise(n, lambda f: bp(f, 6000, 9000, 3), rng) * db(-38)
    return x


def fluoro_buzz(rng):
    """老化日光灯管的电流声：100 Hz 的亮嗡声 + 每半个电网周期一次的放电“滋啦”（运行时音量跟着灯的闪烁走）。"""
    n = 2 * SR
    t = taxis(n)
    buzz = sum(k ** -0.8 * np.sin(2 * np.pi * 100 * k * t + rng.uniform(0, 6.3)) for k in range(1, 41))
    buzz /= rms(buzz)
    ph = np.mod(t, 0.01)
    gate = np.exp(-ph / 0.0008) * np.sin(np.pi / 2 * np.clip(ph / 0.0003, 0, 1)) ** 2  # 0.3 ms 起跳，不留硬边
    sizzle = noise(n, lambda f: bp(f, 3000, 10000, 2), rng) * gate
    sizzle /= rms(sizzle)
    # 放电声的起伏限制在 ±40% 以内：起伏太大时最响的那几下会单独跳出来，听着像接触不良的“嗒”
    return 0.75 * buzz + 0.25 * sizzle * np.clip(1 + 0.4 * wobble(n, 1, 6, rng), 0.6, 1.4)


def sea_flow(rng):
    """航行时艇身外的水流声（运行时音量、音高跟着航速走；在舱里听只剩低频）。"""
    n = 16 * SR
    sh = lambda f: bp(f, 30, 2500, 1) * tilt(f, -4, 200)
    m = lambda: np.clip(1 + 0.35 * wobble(n, 0.15, 1.5, rng), 0.2, 2.5)
    c, l, r = (noise(n, sh, rng) * m() for _ in range(3))
    gurgle = lambda: noise(n, lambda f: bp(f, 280, 900, 2), rng) * np.clip(wobble(n, 2, 8, rng), 0, None) * db(-10)
    return stereo(c, l + gurgle(), r + gurgle(), 0.8)


def sea_deep(rng):
    """一千八百米深的海：几乎听不见的极低频轰鸣，远处一层很淡的嘶声，极慢地涨落。"""
    n = 30 * SR
    m = np.clip(1 + 0.4 * wobble(n, 0.02, 0.15, rng), 0.25, 2.2)
    sh = lambda f: bp(f, 8, 45, 2) * tilt(f, -6, 20)
    c, l, r = (noise(n, sh, rng) * m for _ in range(3))
    hiss = lambda: noise(n, lambda f: bp(f, 150, 1200, 2), rng) * db(-30) * m
    return stereo(c, l + hiss(), r + hiss(), 0.8)


def motor_hum(rng):
    """推进电机（满速时）：转轴 25 Hz 的低频谐波、36 槽的电磁啸叫 900 Hz、齿轮啮合，叠上螺旋桨 8 Hz 的叶频起伏。
    运行时按转速改音高（整体变慢变低）和音量。"""
    n = 4 * SR
    t = taxis(n)
    low = sum(k ** -1.0 * np.sin(2 * np.pi * 25 * k * t + rng.uniform(0, 6.3)) for k in range(1, 9))
    blade = 1 + 0.22 * np.sin(2 * np.pi * 8 * t)
    whine = np.sin(2 * np.pi * 900 * t) + 0.3 * np.sin(2 * np.pi * 1800 * t + 1.0)
    mesh = np.sin(2 * np.pi * 325 * t) + 0.4 * np.sin(2 * np.pi * 300 * t) + 0.4 * np.sin(2 * np.pi * 350 * t)
    brush = noise(n, lambda f: bp(f, 2000, 6000, 2), rng)
    x = low / rms(low) * blade + whine / rms(whine) * db(-14) + mesh / rms(mesh) * db(-17) + brush * db(-30)
    return x


def prop_wash(rng):
    """螺旋桨搅水：七叶桨每转一圈拍七下水（满速约 8 Hz），沙沙的水声跟着叶频一下一下地涌。"""
    n = 4 * SR
    t = taxis(n)
    g = (0.5 + 0.5 * np.cos(2 * np.pi * 8 * t)) ** 3
    swish = noise(n, lambda f: bp(f, 60, 1800, 1) * tilt(f, -3, 200), rng) * (0.35 + 0.65 * g)
    thrum = sum(np.sin(2 * np.pi * 8 * k * t + rng.uniform(0, 6.3)) / k for k in range(2, 16))
    return swish + thrum / rms(thrum) * db(-8)


def pump(rng):
    """压载水泵（上浮、下潜时）：50 Hz 电机、7 叶叶轮的 350 Hz 叶频、一点齿轮啸叫和管子里的水流嘶声。"""
    n = 3 * SR
    t = taxis(n)
    motor = sum(k ** -1.2 * np.sin(2 * np.pi * 50 * k * t + rng.uniform(0, 6.3)) for k in range(1, 7))
    vane = np.sin(2 * np.pi * 350 * t) + 0.4 * np.sin(2 * np.pi * 700 * t + 2.0)
    whine = np.sin(2 * np.pi * 1450 * t)
    flow = noise(n, lambda f: bp(f, 400, 3000, 1), rng) * (1 + 0.2 * np.sin(2 * np.pi * 2 * t))
    return motor / rms(motor) + vane / rms(vane) * db(-9) + whine * db(-24) + flow * db(-12)


def door_grind(rng):
    """转手轮时减速箱里的摩擦声（运行时音量跟着手轮转速）。"""
    n = 2 * SR
    t = taxis(n)
    per = np.repeat(np.clip(1 + 0.6 * rng.standard_normal(80), 0.1, 3), n // 80)
    stick = (0.5 + 0.5 * np.cos(2 * np.pi * 40 * t)) ** 4 * per
    rasp = noise(n, lambda f: bp(f, 250, 2200, 1), rng) * (0.4 + 0.6 * stick)
    gear = noise(n, lambda f: bp(f, 60, 200, 2), rng) * db(-8)
    return rasp + gear


def hinge_creak(rng):
    """门扇荡开时铰链的吱嘎：45~75 次/秒的粘滑脉冲敲在门扇的模态上，速率慢慢游移
    （运行时音量、音高跟着门扇角速度）。"""
    n = 3 * SR
    rate = 60 + 15 * wobble(n, 0.3, 1.5, rng)
    amp = np.clip(1 + 0.4 * wobble(n, 0.5, 4, rng), 0.2, 2)
    x = stick_slip(n, rate, amp, rng, circular=True)
    ir = modes(0.4, logu(rng, 150, 1600, 14), rng.uniform(0.03, 0.15, 14), rng.uniform(0.3, 1, 14))
    x = cconv(np.convolve(x, pulse(0.5))[:n], ir)
    return x + noise(n, lambda f: bp(f, 900, 3500, 2), rng) * amp * db(-30) * rms(x)


# ---------------------------------------------------------------------------- 一次性的声音
def creak(rng):
    """艇壳受压的低沉吱嘎：慢速粘滑脉冲（8~45 次/秒）敲在大钢板的低频模态上，先紧后松。"""
    dur = rng.uniform(1.6, 3.2)
    n = int(dur * SR)
    t = taxis(n)
    r0, r1 = rng.uniform(8, 18), rng.uniform(22, 45)
    arc = np.sin(np.pi * t / dur) ** 0.7
    rate = r0 + (r1 - r0) * arc * (1 + 0.15 * wobble(n, 1, 5, rng))
    env = np.sin(np.pi * t / dur) ** 1.5 * np.clip(1 + 0.4 * wobble(n, 1, 6, rng), 0.1, 2)
    x = np.convolve(stick_slip(n, rate, env, rng), pulse(0.6))[:n]
    f = logu(rng, 70, 900, 24)
    ir = modes(1.0, f, rng.uniform(0.08, 0.5, 24) * (200 / f) ** 0.3, rng.uniform(0.3, 1, 24) * f ** -0.3)
    y = fftconv(x, ir)
    rub = np.zeros(len(y))
    rub[:n] = noise(n, lambda f: bp(f, 600, 3500, 2), rng) * env * db(-28) * rms(y)
    return fade(y + rub, 0.0, 0.3)


def pop(rng):
    """钢壳受压“嘣”的一声：一下尖冲击敲响一组非谐和的中高频模态，余音拖很长。"""
    f = logu(rng, 250, 3500, 18)
    ring = modes(2.0, f, rng.uniform(0.25, 1.2, 18) * (500 / f) ** 0.5, rng.uniform(0.3, 1, 18) * (f / 500) ** -0.3)
    thump = modes(2.0, rng.uniform(60, 150, 3), rng.uniform(0.08, 0.15, 3), [1.5, 1, 1])
    return fade(mix(fftconv(pulse(0.15), ring), fftconv(pulse(2.0), thump) * 0.4), 0.0, 0.2)


def sonar_ping(rng, f0=950.0, hold=0.25, ring=1.4, echo=2.0):
    """主动声呐的 ping：一声低沉的纯音（950 Hz，像潜渊症里那种），起音很尖；后面一长串微微颤动的余音——
    声波在海面、海底、温跃层之间来回反射，成百上千条路径前后脚回来（多径混响）；
    echo 秒后远处目标弹回来一声闷一点的回波（0 = 不要）。"""
    n = int(6.0 * SR)
    t = taxis(n)
    env = np.clip(t / 0.003, 0, 1) * np.where(t < hold, 1.0, np.exp(-(t - hold) / 0.05))
    ping = np.sin(2 * np.pi * f0 * t) * env
    # 换能器自己的余振：两个差一点点的频率，拍出慢慢的颤动
    shimmer = (np.sin(2 * np.pi * f0 * 1.0025 * t) + np.sin(2 * np.pi * f0 * 0.9975 * t + 1.0)) \
        * np.clip(t / 0.01, 0, 1) * np.exp(-t / (ring * 0.4)) * db(-14)
    # 多径混响：一千多条随机延迟、指数衰减的反射
    k = 1500
    taps = rng.uniform(0.02, 4.0, k) ** 1.3 / 4.0 ** 0.3
    ir = np.zeros(int(4.2 * SR))
    np.add.at(ir, (taps * SR).astype(int), rng.standard_normal(k) * np.exp(-taps / ring))
    rev = fftconv(ping, ir)[:n]
    rev = filt(rev, lambda f: bp(f, f0 * 0.6, f0 * 1.6, 2))
    y = unit(ping) + unit(shimmer + 1e-12) * db(-14) + unit(rev) * db(-9)
    if echo:
        e = fade(filt(ping, lambda f: bp(f, f0 * 0.85, f0 * 1.15, 3)), 0.003)   # 走了远路，频带变窄、发闷；
        # 零相位滤波截掉了起点前的那点余波，开头补个 3 ms 渐入，不然回波一来先咔一下
        e = mix(unit(e), unit(fftconv(e, ir[: int(1.5 * SR)])) * db(-6))
        place(y, unit(e) * db(-13), int(echo * SR))
    return fade(y, 0.0, 0.8)


def drip(rng, kind="metal"):
    """水珠从冷却水管的法兰上滴下来，落了 1.8 米砸到地板上。kind：
    film   铁地板上一层薄积水：一下很短很脆的拍水声“嗒”（宽频，几毫秒），没有气泡音；溅起的小水珠零星落回来
    puddle 滴进有点深的水洼：拍水声软一点，带一个短促、低沉的气泡音“噗”
    metal  滴在干铁板上：拍水声 + 钢板高频的“叮”"""
    n = int(0.35 * SR)
    t = taxis(n)
    y = np.zeros(n)
    # 拍水：几毫秒的宽频噪声，起音极快、衰减很快；越薄的水越脆（频带越高）
    lo = {"film": 1800, "puddle": 700, "metal": 2200}[kind]
    w = int(rng.uniform(4, 8) * SR / 1000)
    slap = filt(rng.standard_normal(w), lambda f: bp(f, lo, 11000, 1)) * np.exp(-np.arange(w) / (w / 4))
    place(y, unit(slap), 0)
    if kind == "puddle":
        f0 = rng.uniform(450, 800)
        tau = rng.uniform(0.012, 0.025)
        f = f0 * (1 + 0.25 * np.clip(t / (3 * tau), 0, 1))
        b = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / tau) * (1 - np.exp(-t / 0.001))
        place(y, unit(b) * db(-4), int(0.003 * SR))
    if kind == "metal":
        fm = logu(rng, 2500, 7500, 6)
        place(y, unit(fftconv(pulse(0.05), modes(0.12, fm, rng.uniform(0.01, 0.04, 6), np.ones(6)))) * db(-6), 0)
    # 溅起的小水珠落回来：零星几下更轻、更高的“嗒”
    for _ in range(rng.integers(2, 6)):
        m = int(rng.uniform(0.6, 1.5) * SR / 1000)
        d = filt(rng.standard_normal(m), lambda f: bp(f, 3000, 12000, 1)) * np.hanning(m)
        place(y, unit(d) * db(rng.uniform(-24, -14)), int(rng.uniform(0.02, 0.12) * SR))
    return y


def gear_tick(rng):
    """手轮减速箱的齿轮咔哒（运行时手轮每转过一个齿响一下）。"""
    f = logu(rng, 1800, 7000, 6)
    y = fftconv(pulse(0.12), modes(0.08, f, rng.uniform(0.006, 0.03, 6), rng.uniform(0.4, 1, 6)))
    body = fftconv(pulse(0.5), modes(0.08, rng.uniform(400, 900, 2), [0.015, 0.01], [1, 0.6]))
    return mix(y, body * 0.5)


def _clunks(rng, count, spread, f_lo, f_hi, dull):
    """几个压紧把手一起撞到楔块上：每个是一下金属闷响，时间上错开一点。"""
    n = int(1.2 * SR)
    y = np.zeros(n)
    for k, at in enumerate(np.sort(rng.uniform(0, spread, count))):
        f = logu(rng, f_lo, f_hi, 8)
        c = mix(fftconv(pulse(dull), modes(0.5, f, rng.uniform(0.05, 0.2, 8), rng.uniform(0.3, 1, 8))),
                fftconv(pulse(3.0), modes(0.3, rng.uniform(90, 200, 2), [0.08, 0.06], [1, 0.7])) * 2.0)
        place(y, c * rng.uniform(0.5, 1.0) * (1.4 if k == 0 else 1.0), int(at * SR))
    return y


def door_unlatch(rng):
    """开门：六个压紧把手从楔块上同时被拨开，第一下最响。"""
    return fade(_clunks(rng, 6, 0.05, 250, 2200, 0.6), 0.0, 0.3)


def door_latch(rng):
    """关门拧紧：把手压上楔块前一小声挤压的吱，再是一串发闷的咬合声。"""
    n = int(1.2 * SR)
    t = taxis(n)
    k = int(0.15 * SR)
    rate = np.zeros(n)
    rate[:k] = np.linspace(120, 300, k)
    squeak = np.convolve(stick_slip(n, rate, np.sin(np.pi * np.clip(t / 0.15, 0, 1)), rng), pulse(0.2))[:n]
    squeak = fftconv(squeak, modes(0.2, logu(rng, 800, 3000, 6), rng.uniform(0.01, 0.04, 6), np.ones(6)))[:n]
    y = _clunks(rng, 6, 0.08, 180, 1500, 1.0)
    place(y, squeak / (np.abs(squeak).max() + 1e-9) * 0.25, 0)
    return fade(y, 0.0, 0.3)


def door_slam(rng):
    """门扇甩回去撞上门框：低沉的一下重击，整扇钢门和隔壁嗡嗡地响很久，把手跟着叮当几下。"""
    n = int(3.5 * SR)
    y = np.zeros(n)
    exc = mix(pulse(3.0), burst(4, lambda f: bp(f, 500, 6000, 1), rng) * 0.15)
    thud = modes(1.2, rng.uniform(45, 160, 6), rng.uniform(0.12, 0.3, 6), rng.uniform(0.6, 1, 6))
    f = logu(rng, 160, 3200, 30)
    clang = modes(3.5, f, rng.uniform(0.25, 1.0, 30) * (300 / f) ** 0.4, rng.uniform(0.3, 1, 30) * (f / 300) ** -0.4)
    place(y, unit(fftconv(exc, thud)), 0)
    place(y, unit(fftconv(exc, clang)) * db(-5), 0)
    w = int(0.08 * SR)
    place(y, unit(filt(rng.standard_normal(w), lambda f: bp(f, 25, 80, 2)) * np.hanning(w)) * db(-6), 0)
    for at in np.sort(rng.uniform(0.06, 0.25, 4)):
        place(y, unit(gear_tick(rng)) * db(-20), int(at * SR))
    return fade(y, 0.0, 0.6)


def plate_modes(rng, f11, k):
    """四边搭在龙骨上的矩形钢板（简支板）的前 k 个模态频率：f_mn ∝ (m/a)² + (n/b)²，f11 是最低的那个。"""
    ar = rng.uniform(1.3, 1.8)  # 长宽比
    f = sorted(f11 * (m * m + n * n * ar * ar) / (1 + ar * ar) for m in range(1, 8) for n in range(1, 8))
    return np.array(f[:k]) * rng.uniform(0.98, 1.02, k)


def footstep(rng):
    """军靴踩在花纹钢地板上。地板是 6 mm 钢板（约 60×40 cm）搭在龙骨上，底下是空的舱底：
    - 靴跟踩下去：钢板“咚”一下（板的模态，最低约 130 Hz；靴子压在板上，很快止住），舱底空腔跟着嗡一声
    - 没压实的钢板在龙骨上磕一下（金属撞金属，冲击极短，又亮又脆）——踩铁的感觉主要靠这一下
    - 脚掌跟着落下，轻一点；鞋底砂粒的擦声"""
    n = int(0.35 * SR)
    y = np.zeros(n)
    f = plate_modes(rng, rng.uniform(115, 150), 22)
    d = rng.uniform(0.6, 1.4, 22) * 0.055 * (f[0] / f) ** 0.3       # 靴子一直压在板上，振动很快被压住；低的模态稍久
    a = rng.uniform(0.4, 1.0, 22) * (f / f[0]) ** -0.15
    plate = modes(0.3, f, d, a)
    cavity = modes(0.2, rng.uniform(75, 100, 2), [0.04, 0.03], [1.0, 0.6])
    fr = logu(rng, 900, 5500, 10)
    frame = modes(0.15, fr, rng.uniform(0.01, 0.04, 10), rng.uniform(0.5, 1, 10))
    heel = pulse(rng.uniform(0.8, 1.3))
    place(y, unit(fftconv(heel, plate)), 0)
    place(y, unit(fftconv(pulse(3.0), cavity)) * db(-7), 0)
    knock = mix(unit(fftconv(pulse(0.08), frame)), unit(fftconv(pulse(0.08), plate)) * db(-4))
    for k in range(rng.integers(1, 3)):     # 磕一两下
        place(y, unit(knock) * db(-5 - 5 * k), int(rng.uniform(0.006, 0.02) * SR) + int(k * rng.uniform(0.012, 0.025) * SR))
    place(y, unit(fftconv(pulse(2.0), plate)) * rng.uniform(0.3, 0.45), int(rng.uniform(0.06, 0.09) * SR))
    place(y, unit(burst(rng.uniform(20, 40), lambda f: bp(f, 1500, 8000, 2), rng)) * db(-16), 0)
    return y


def switch(rng):
    """探照灯拨杆开关：拨杆“咔嗒”两下（过死点、落到位），紧接着配电柜里接触器吸合的一声闷响。"""
    n = int(0.3 * SR)
    y = np.zeros(n)
    for at, s in ((0.0, 1.0), (rng.uniform(0.005, 0.01), 0.7)):
        f = logu(rng, 2500, 9000, 6)
        place(y, fftconv(pulse(0.08), modes(0.05, f, rng.uniform(0.004, 0.015, 6), np.ones(6))) * s, int(at * SR))
    place(y, fftconv(pulse(0.6), modes(0.1, rng.uniform(300, 900, 3), [0.02, 0.015, 0.02], [1, 0.7, 0.5])) * 0.6, 0)
    f = logu(rng, 180, 1200, 6)
    relay = fftconv(pulse(1.0), modes(0.15, f, rng.uniform(0.02, 0.05, 6), np.ones(6)))
    place(y, relay * 0.5, int(rng.uniform(0.035, 0.06) * SR))
    return y


def hull_impact(rng):
    """艇身撞上礁石：沉闷的一下撞击，整个艇壳低沉地嗡鸣好几秒，接着一阵刮擦。"""
    n = int(4.0 * SR)
    y = np.zeros(n)
    w = int(rng.uniform(0.02, 0.04) * SR)
    exc = filt(rng.standard_normal(w), lambda f: bp(f, None, 400, 2)) * np.hanning(w)
    f = logu(rng, 35, 700, 28)
    hull = modes(4.0, f, rng.uniform(0.4, 2.5, 28) * (80 / f) ** 0.3, rng.uniform(0.4, 1, 28) * (f / 80) ** -0.5)
    place(y, fftconv(exc, hull), 0)
    m = int(rng.uniform(0.3, 0.8) * SR)
    tt = taxis(m)
    scrape = noise(m, lambda f: bp(f, 250, 2500, 1), rng) * np.clip(1 + 0.8 * wobble(m, 8, 40, rng), 0, None)
    scrape *= np.exp(-tt / (m / SR / 3)) * np.clip(tt / 0.02, 0, 1)
    place(y, scrape * rms(y) * 1.5, int(0.01 * SR))
    return fade(y, 0.0, 0.8)


# 名字 -> (函数, 是否循环, 变体个数)
SOUNDS = {
    "hull_bed": (hull_bed, True, 1),
    "vent": (vent, True, 1),
    "power_hum": (power_hum, True, 1),
    "fluoro_buzz": (fluoro_buzz, True, 1),
    "sea_flow": (sea_flow, True, 1),
    "sea_deep": (sea_deep, True, 1),
    "motor_hum": (motor_hum, True, 1),
    "prop_wash": (prop_wash, True, 1),
    "pump": (pump, True, 1),
    "door_grind": (door_grind, True, 1),
    "hinge_creak": (hinge_creak, True, 1),
    "creak": (creak, False, 5),
    "pop": (pop, False, 3),
    "sonar_ping": (sonar_ping, False, 1),
    "drip": (drip, False, 6),
    "gear_tick": (gear_tick, False, 5),
    "door_unlatch": (door_unlatch, False, 2),
    "door_latch": (door_latch, False, 2),
    "door_slam": (door_slam, False, 2),
    "footstep": (footstep, False, 8),
    "switch": (switch, False, 3),
    "hull_impact": (hull_impact, False, 3),
}


# ---------------------------------------------------------------------------- 输出
def write_wav(path, x, loop):
    ch = 1 if x.ndim == 1 else 2
    pcm = np.clip(np.round(x * 32767), -32768, 32767).astype("<i2")
    frames = len(pcm)
    if loop:
        # 循环终点后面再接 16 个循环开头的采样：Godot 变调播放时在相邻采样之间插值，循环末尾会读到终点之后，
        # 那里本来是补的零，每圈接缝一个毛刺；接上开头，读过头读到的就是正确的延续（循环点不变）
        pcm = np.concatenate([pcm, pcm[:16]])
    data = pcm.tobytes()
    chunks = b"fmt " + struct.pack("<IHHIIHH", 16, 1, ch, SR, SR * ch * 2, ch * 2, 16)
    chunks += b"data" + struct.pack("<I", len(data)) + data
    if loop:
        # smpl 块：10 个 uint32 的头（最后一个是第一个循环的 cue id）+ 循环类型 0（正向）、起点、终点。
        # WAV 规范里终点是「含」的（应写 n-1），但 Godot 读进来直接当 AudioStreamWAV.loop_end 用，那是「不含」的，
        # 写 n-1 每圈会跳掉最后一个采样；这里按 Godot 的意思写循环长度
        body = struct.pack("<9I", 0, 0, 1000000000 // SR, 60, 0, 0, 0, 1, 0)
        body += struct.pack("<6I", 0, 0, 0, frames, 0, 0)
        chunks += b"smpl" + struct.pack("<I", len(body)) + body
    path.write_bytes(b"RIFF" + struct.pack("<I", 4 + len(chunks)) + b"WAVE" + chunks)


def import_pcm(path):
    """循环音在 Godot 里不能用默认的 QOA 压缩：QOA 绕回循环起点时解码器的预测状态接不上，每圈接缝处一个毛刺
    （tools/record.sh 录出来、audio_report.py 查得到）。把导入设置改成不压缩的 PCM；还没导入过就写一个只有参数的
    .import，Godot 导入时会补全其余字段。"""
    imp = path.with_name(path.name + ".import")
    if imp.exists():
        text = imp.read_text()
        new = re.sub(r"compress/mode=\d+", "compress/mode=0", text)
        if new != text:
            imp.write_text(new)
    else:
        imp.write_text('[remap]\n\nimporter="wav"\ntype="AudioStreamWAV"\n\n[params]\n\ncompress/mode=0\n')


def finish(x, loop):
    x = np.asarray(x, dtype=np.float64)
    assert np.all(np.isfinite(x))
    if loop:
        x = x * (db(-20) / rms(x))
        if np.abs(x).max() > db(-1):
            x *= db(-1) / np.abs(x).max()
    else:
        # 去掉直流和次声（零相位高通），开头 0.3 ms、结尾 5% 渐变，首尾都落在 0 上，播放器起停时不咔哒
        x = fade(filt(x, lambda f: bp(f, 18, None, 2)), 0.0003, len(x) / SR * 0.05)
        x = x * (db(-3) / np.abs(x).max())
        # 尾巴补 50 ms 的数字静音：播放器变调重采样时会读到数据末尾之后，别让它读到垃圾
        x = np.concatenate([x, np.zeros((int(0.05 * SR),) + x.shape[1:])])
    return x


def seam(x):
    """循环接缝处的跳变，和信号里正常的采样间跳变比（≈1 就是无缝）。"""
    m = x if x.ndim == 1 else x[:, 0]
    d = np.abs(np.diff(m))
    return abs(m[0] - m[-1]) / (np.percentile(d, 99) + 1e-12)


def main():
    want = sys.argv[1:]
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"{'名字':<18}{'时长':>6}{'声道':>4}{'峰值dB':>8}{'RMS dB':>8}  备注")
    for name, (fn, loop, count) in SOUNDS.items():
        if want and not any(name.startswith(w) for w in want):
            continue
        for k in range(count):
            fname = name if count == 1 else f"{name}_{k}"
            rng = np.random.default_rng(zlib.crc32(fname.encode()))
            x = finish(fn(rng), loop)
            write_wav(OUT / f"{fname}.wav", x, loop)
            if loop:
                import_pcm(OUT / f"{fname}.wav")
            note = f"循环，接缝 {seam(x):.2f}" if loop else ""
            print(f"{fname:<20}{len(x) / SR:6.2f}{x.ndim if x.ndim == 1 else x.shape[1]:>4}"
                  f"{20 * np.log10(np.abs(x).max()):8.1f}{20 * np.log10(rms(x)):8.1f}  {note}")


if __name__ == "__main__":
    main()
