#!/usr/bin/env python3
"""潜艇的音效全部在这里程序化合成，写到 assets/audio/（48 kHz、16 bit WAV）。只用 numpy。
用法: python tools/gen_sfx.py [名字前缀...]      （不给参数就全部重新生成）

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
    """转手轮时减速箱里的声音（运行时音量、音高跟着手轮转速）：铸铁壳里一对蜗轮蜗杆在干涩的黄油里啮合——
    齿一个一个咬过去（每秒四十来下），每一下敲在减速箱壳和门扇的低频模态上，闷闷的“咯咯咯”；
    底下一层齿面摩擦的沙沙声，再垫一点门扇被带着嗡的低频。"""
    n = 2 * SR
    rate = 42 + 6 * wobble(n, 0.3, 2, rng)
    amp = np.clip(1 + 0.35 * wobble(n, 1, 8, rng), 0.2, 2)
    x = np.convolve(stick_slip(n, rate, amp, rng, circular=True), pulse(0.8))[:n]
    f = logu(rng, 140, 1300, 16)
    ir = modes(0.5, f, rng.uniform(0.02, 0.07, 16) * (300 / f) ** 0.3, rng.uniform(0.4, 1, 16) * (f / 300) ** -0.5)
    mesh = cconv(x, ir)
    leaf = cconv(x, modes(0.6, plate_modes(rng, 62, 8), rng.uniform(0.08, 0.2, 8), np.ones(8)))
    rasp = noise(n, lambda f: bp(f, 180, 1400, 1) * tilt(f, -3), rng) * np.clip(amp, 0.3, None)
    return unit(mesh) + unit(leaf) * db(-6) + unit(rasp) * db(-14)


def hinge_creak(rng):
    """门扇荡开时铰链的声音：几十公斤的门扇压在一根粗销子上转，干摩擦一顿一顿（每秒二三十下），
    每一下敲在门扇和铰链座的低频模态上——低沉的“嘎——”，不是小门那种尖的吱呀；上面浮一点点尖音
    （运行时音量、音高跟着门扇角速度）。"""
    n = 3 * SR
    rate = 30 + 8 * wobble(n, 0.3, 1.5, rng)
    amp = np.clip(1 + 0.5 * wobble(n, 0.5, 5, rng), 0.15, 2.2)
    x = stick_slip(n, rate, amp, rng, circular=True)
    x = np.convolve(x, pulse(0.9))[:n]
    f = plate_modes(rng, rng.uniform(58, 68), 18)
    leaf = cconv(x, modes(0.6, f, rng.uniform(0.6, 1.2, 18) * 0.12 * (f[0] / f) ** 0.4, rng.uniform(0.4, 1, 18) * (f / f[0]) ** -0.3))
    fh = logu(rng, 500, 2200, 8)
    pin = cconv(x, modes(0.3, fh, rng.uniform(0.02, 0.06, 8), rng.uniform(0.4, 1, 8)))
    return unit(leaf) + unit(pin) * db(-9) + noise(n, lambda f: bp(f, 1200, 3500, 2), rng) * amp * db(-34)


def door_wedge(rng):
    """拧紧时把手骑上楔块：锻钢把手压着楔块的斜面硬往上蹭，压力越大顿得越狠（每秒五六十下的粘滑），
    一下一下敲在把手、楔块这些小钢件（中高频）和整扇门（低频）上，夹着刮铁的沙沙声
    （运行时音量跟着吃劲程度乘手轮转速）。"""
    n = 2 * SR
    rate = 55 + 12 * wobble(n, 0.5, 3, rng)
    amp = np.clip(1 + 0.6 * wobble(n, 2, 15, rng), 0.1, 2.5)
    x = np.convolve(stick_slip(n, rate, amp, rng, circular=True), pulse(0.25))[:n]
    f = logu(rng, 450, 3200, 12)
    small = cconv(x, modes(0.3, f, rng.uniform(0.01, 0.05, 12), rng.uniform(0.4, 1, 12)))
    leaf = cconv(x, modes(0.6, plate_modes(rng, 64, 10), rng.uniform(0.05, 0.15, 10), np.ones(10)))
    scrape = noise(n, lambda f: bp(f, 400, 3500, 2), rng) * amp
    return unit(small) + unit(leaf) * db(-4) + unit(scrape) * db(-12)


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
    """手轮减速箱的齿轮咔哒（运行时手轮每转过一个齿响一下）：粗齿咬过去的一下，带铸铁壳的闷响。"""
    f = logu(rng, 900, 3500, 6)
    y = fftconv(pulse(0.25), modes(0.08, f, rng.uniform(0.006, 0.025, 6), rng.uniform(0.4, 1, 6)))
    body = fftconv(pulse(1.2), modes(0.12, rng.uniform(220, 520, 3), [0.03, 0.022, 0.015], [1, 0.7, 0.5]))
    return mix(unit(y) * 0.6, unit(body))


def leaf_ir(rng, dur=2.0, f11=None, k=16, decay=0.4):
    """门扇本身：二十毫米钢板加包边，八九十公斤，最低一阶六十赫兹上下（简支板的模态）。"""
    f = plate_modes(rng, f11 or rng.uniform(56, 68), k)
    d = rng.uniform(0.6, 1.3, k) * decay * (f[0] / f) ** 0.5
    a = rng.uniform(0.5, 1.0, k) * (f / f[0]) ** -0.45
    return modes(dur, f, d, a)


def rattle(rng, n, count, t0, t1, level_db, f_lo=700, f_hi=3200):
    """把手、连杆、销子在间隙里被震得叮当几下：一串越来越轻、越来越密的小金属磕碰。"""
    y = np.zeros(n)
    for k, at in enumerate(np.sort(rng.uniform(t0, t1, count))):
        f = logu(rng, f_lo, f_hi, 6)
        c = fftconv(pulse(rng.uniform(0.1, 0.3)), modes(0.15, f, rng.uniform(0.008, 0.04, 6), rng.uniform(0.4, 1, 6)))
        place(y, unit(c) * db(level_db - 2.5 * k + rng.uniform(-3, 2)), int(at * SR))
    return y


def _clunks(rng, count, spread, f_lo, f_hi, dull, n=None):
    """几个压紧把手一起撞到（或离开）楔块：每个是一下发闷的金属响，带一点门扇的低频，时间上错开一点。"""
    n = n or int(1.2 * SR)
    y = np.zeros(n)
    for k, at in enumerate(np.sort(rng.uniform(0, spread, count))):
        f = logu(rng, f_lo, f_hi, 8)
        c = mix(unit(fftconv(pulse(dull), modes(0.4, f, rng.uniform(0.03, 0.12, 8), rng.uniform(0.3, 1, 8)))),
                unit(fftconv(pulse(3.0), modes(0.3, rng.uniform(110, 230, 2), [0.06, 0.05], [1, 0.7]))) * db(-2))
        place(y, c * rng.uniform(0.55, 1.0) * (1.4 if k == 0 else 1.0), int(at * SR))
    return y


def door_strain(rng):
    """开门第一下掰手轮：把手还咬在楔块上，手轮只挪几度——整套机构绷紧了“嘎——”地闷哼一声
    （慢速粘滑敲在门扇低频上，越绷越紧、越顿越密），减速箱里嘎吱一下。"""
    dur = 0.42
    n = int(dur * SR)
    t = taxis(n)
    rate = 16 + 26 * (t / dur) ** 1.5
    env = np.sin(np.pi * np.clip(t / dur, 0, 1)) ** 0.6 * np.clip(1 + 0.3 * wobble(n, 3, 20, rng), 0.2, 2)
    x = np.convolve(stick_slip(n, rate, env, rng), pulse(1.0))[:n]
    groan = fftconv(x, leaf_ir(rng, 0.8, decay=0.15))
    f = logu(rng, 300, 1600, 10)
    box_ = fftconv(x, modes(0.3, f, rng.uniform(0.02, 0.06, 10), rng.uniform(0.4, 1, 10)))
    y = np.zeros(int(1.0 * SR))
    place(y, unit(groan), 0)
    place(y, unit(box_) * db(-7), 0)
    return fade(y, 0.0, 0.25)


def door_unlatch(rng):
    """掰动了：绷着的劲一下松开，六个把手同时从楔块上蹦开——沉的一声“哐”（门扇被带着一震），
    跟着连杆、把手在间隙里叮当几下。"""
    n = int(1.6 * SR)
    y = _clunks(rng, 6, 0.035, 160, 1400, 1.0, n)
    y = unit(y)
    place(y, unit(fftconv(pulse(3.5), leaf_ir(rng, 1.4, decay=0.3))) * db(-3), 0)
    y += rattle(rng, n, 5, 0.04, 0.22, -14)
    return fade(y, 0.0, 0.4)


def door_seal(rng):
    """胶条从门框刀口上松开：橡胶粘着撕开一串细小的噼啪，两舱一点点压差“噗”地泄掉——
    一下很低的气压闷响，后面拖一口短短的嘶气。"""
    n = int(0.9 * SR)
    t = taxis(n)
    y = np.zeros(n)
    # 气压：一个周期左右的低频“噗”（门扇像活塞一样被吸住又松开）
    f0 = rng.uniform(55, 75)
    puff = np.sin(2 * np.pi * f0 * t) * np.exp(-t / 0.025) * np.clip(t / 0.004, 0, 1)
    place(y, unit(puff), int(0.01 * SR))
    # 橡胶撕开：几十个细碎的粘滑脉冲，敲在胶条和门扇边上
    m = int(0.12 * SR)
    rate = np.full(m, rng.uniform(250, 400))
    peel = stick_slip(m, rate, np.hanning(m), rng)
    peel = fftconv(np.convolve(peel, pulse(0.15))[:m], modes(0.1, logu(rng, 800, 4000, 6), rng.uniform(0.003, 0.01, 6), np.ones(6)))
    place(y, unit(peel) * db(-10), 0)
    # 嘶：压差泄掉的气流声，很快没了
    h = int(0.45 * SR)
    th = taxis(h)
    hiss = filt(rng.standard_normal(h), lambda f: bp(f, 900, 6000, 1)) * np.exp(-th / 0.09) * np.clip(th / 0.01, 0, 1)
    place(y, unit(hiss) * db(-16), int(0.012 * SR))
    place(y, unit(fftconv(pulse(4.0), leaf_ir(rng, 0.6, decay=0.15))) * db(-9), int(0.01 * SR))
    return fade(y, 0.0, 0.2)


def door_air(rng):
    """门扇快关上时，像一块大板子把空气推着往门洞里挤：低沉的“呼”越来越急，到撞上那一下戛然而止
    （门扇离门框还有十几度时触发，大约 0.15 秒后撞上）。"""
    n = int(0.3 * SR)
    t = taxis(n)
    hit = 0.16
    env = np.clip(t / hit, 0, 1) ** 2.2 * np.where(t < hit, 1.0, np.exp(-(t - hit) / 0.015))
    gust = filt(rng.standard_normal(n), lambda f: bp(f, 60, 700, 1) * tilt(f, -2)) * env
    whis = filt(rng.standard_normal(n), lambda f: bp(f, 500, 1600, 2)) * env ** 2
    return unit(gust) + unit(whis) * db(-12)


def door_slam(rng):
    """门扇撞上门框：胶条先垫一下、紧跟着钢包边磕上刀口，八九十公斤的门扇整个“咚”地一沉（最低六十赫兹上下），
    隔壁和耐压壳被带着“轰”地嗡起来（更低、更长），门框、补强板的金属余音拖很久；
    门扇像活塞一样把舱里的空气一压，耳朵里一下超低频的闷压；把手、连杆被震得在间隙里叮当几下。"""
    n = int(4.0 * SR)
    y = np.zeros(n)
    soft = pulse(5.0)                    # 胶条
    hard = pulse(0.4)                    # 钢磕钢
    # 门扇本体
    leaf = leaf_ir(rng, 2.5, decay=0.5)
    place(y, unit(fftconv(soft, leaf)), 0)
    place(y, unit(fftconv(hard, leaf)) * db(-8), int(0.002 * SR))
    # 隔壁、耐压壳：几个很低的大板模态，慢慢衰减
    fb = rng.uniform(36, 90, 6)
    bulk = modes(4.0, fb, rng.uniform(0.5, 1.2, 6), rng.uniform(0.5, 1, 6))
    place(y, unit(fftconv(pulse(8.0), bulk)) * db(-3), int(0.004 * SR))
    # 金属余音：门框、补强板、隔壁的中高阶模态（很弱，但拖得长）
    f = logu(rng, 250, 2600, 30)
    ring = modes(4.0, f, rng.uniform(0.3, 1.2, 30) * (300 / f) ** 0.35, rng.uniform(0.3, 1, 30) * (f / 300) ** -0.5)
    place(y, unit(fftconv(hard, ring)) * db(-10), int(0.002 * SR))
    # 气压：二三十赫兹半个周期的一下
    w = int(0.06 * SR)
    place(y, unit(np.sin(np.pi * np.arange(w) / w) ** 2) * db(-4), 0)
    # 钢磕钢的那一下脆响（几毫秒的宽频）
    place(y, unit(burst(3, lambda f: bp(f, 1200, 7000, 1), rng)) * db(-12), int(0.002 * SR))
    # 把手、连杆叮当
    y += rattle(rng, n, 7, 0.03, 0.32, -17, 600, 2600)
    return fade(y, 0.0, 1.0)


def door_knock(rng):
    """门扇撞上门框弹回来一点，又被拉回去贴上：轻一些、闷一些的“咚”，没有那么多余音。"""
    n = int(1.2 * SR)
    y = np.zeros(n)
    place(y, unit(fftconv(pulse(6.0), leaf_ir(rng, 1.0, decay=0.25))), 0)
    place(y, unit(fftconv(pulse(0.5), modes(0.3, logu(rng, 400, 2000, 10), rng.uniform(0.02, 0.08, 10), np.ones(10)))) * db(-14), 0)
    y += rattle(rng, n, 3, 0.02, 0.12, -20)
    return fade(y, 0.0, 0.4)


def door_latch(rng):
    """拧到底、上锁：六个把手几乎同时压死在楔块上（一串很密的闷响，“咔嚓”），减速箱顶到头——
    最沉的一下“哐”，整扇门、隔壁跟着低沉地嗡一下；隔一下是棘爪落进卡槽的“咔哒”，锁住了。"""
    n = int(1.8 * SR)
    y = np.zeros(n)
    # 把手压死：六下闷响挤在 30 毫秒里
    place(y, unit(_clunks(rng, 6, 0.03, 160, 1200, 1.2)) * db(-4), 0)
    # 顶到头：门扇和隔壁的低频（钝的激励，很沉）+ 齿顶死的一下中高频
    t0 = int(0.028 * SR)
    place(y, unit(fftconv(pulse(4.0), leaf_ir(rng, 1.2, decay=0.22))), t0)
    fb = rng.uniform(45, 95, 4)
    place(y, unit(fftconv(pulse(8.0), modes(1.2, fb, rng.uniform(0.12, 0.28, 4), np.ones(4)))) * db(-6), t0)
    f = logu(rng, 1200, 4500, 8)
    place(y, unit(fftconv(pulse(0.2), modes(0.1, f, rng.uniform(0.005, 0.02, 8), rng.uniform(0.4, 1, 8)))) * db(-12), t0)
    # 棘爪落下：咔—哒，两下，带一点减速箱壳的闷响
    t1 = int(rng.uniform(0.13, 0.17) * SR)
    for at, s in ((0, 0.0), (rng.uniform(0.008, 0.014), -5.0)):
        f = logu(rng, 1500, 5500, 6)
        c = mix(unit(fftconv(pulse(0.12), modes(0.06, f, rng.uniform(0.004, 0.015, 6), np.ones(6)))),
                unit(fftconv(pulse(0.8), modes(0.1, rng.uniform(350, 700, 2), [0.025, 0.018], [1, 0.6]))) * db(-3))
        place(y, unit(c) * db(-8 + s), t1 + int(at * SR))
    y += rattle(rng, n, 3, 0.05, 0.12, -22)
    return fade(y, 0.0, 0.5)


def plate_modes(rng, f11, k):
    """四边搭在龙骨上的矩形钢板（简支板）的前 k 个模态频率：f_mn ∝ (m/a)² + (n/b)²，f11 是最低的那个。"""
    ar = rng.uniform(1.3, 1.8)  # 长宽比
    f = sorted(f11 * (m * m + n * n * ar * ar) / (1 + ar * ar) for m in range(1, 8) for n in range(1, 8))
    return np.array(f[:k]) * rng.uniform(0.98, 1.02, k)


def cloth(rng, ms, level_db):
    """工装的裤腿、袖子跟着迈步擦一下：宽频的沙沙，起落都缓，中间一两下布料绷紧的“噗”。"""
    m = int(ms * SR / 1000)
    t = taxis(m)
    env = np.sin(np.pi * t / (m / SR)) ** 2 * np.clip(1 + 0.5 * rng.standard_normal(m // 480 + 1).repeat(480)[:m], 0.2, 2)
    x = filt(rng.standard_normal(m), lambda f: bp(f, 700, 7000, 1) * tilt(f, -2)) * env
    return unit(x) * db(level_db)


def scuff(rng, ms, level_db, lo=1200):
    """鞋底在地上蹭一下（起步蹬地、停下收脚）。"""
    return unit(burst(ms, lambda f: bp(f, lo, 8000, 2), rng)) * db(level_db)


def footstep(rng, surface="plate", gait="walk"):
    """军靴踩在地上。gait：walk 脚跟先着地、脚掌跟着落下；run 更硬更快，脚跟脚掌几乎一起，最后蹬地蹭一下；
    settle 停下时把后脚收过来轻轻一放。surface：
    plate  6 mm 花纹钢板（约 60×40 cm）搭在龙骨上，底下是空的舱底——板的模态（最低约 130 Hz，靴子压着很快止住）、
           舱底空腔的嗡声、没压实的钢板在龙骨上磕一下（金属撞金属，又亮又脆）
    grate  扁钢格栅：靴底同时压上好几根扁钢，一串很密的亮“嚓”（扁钢的高频模态），格栅板在角钢框上颠一两下“咔嗒”，
           底下舱底的空腔直接露着
    sill   门框的厚钢门槛：实心的，闷而短的一声“咚”，带一点隔壁的低频"""
    n = int(0.45 * SR)
    y = np.zeros(n)
    run, settle = gait == "run", gait == "settle"
    heel = pulse(rng.uniform(0.45, 0.7) if run else rng.uniform(2.0, 3.0) if settle else rng.uniform(0.8, 1.3))
    fore_at = rng.uniform(0.022, 0.04) if run else rng.uniform(0.07, 0.11)
    fore_amp = rng.uniform(0.55, 0.75) if run else rng.uniform(0.3, 0.45)
    damp = 1.6 if run else 0.7 if settle else 1.0     # 跑的时候脚一下就抬起来，板子响得久一点
    if surface == "plate":
        f = plate_modes(rng, rng.uniform(115, 150), 22)
        d = rng.uniform(0.6, 1.4, 22) * 0.055 * damp * (f[0] / f) ** 0.3
        body = modes(0.35, f, d, rng.uniform(0.4, 1.0, 22) * (f / f[0]) ** -0.15)
        cav = modes(0.25, rng.uniform(75, 100, 2), [0.04 * damp, 0.03 * damp], [1.0, 0.6])
        cav_db = -7
        fr = logu(rng, 900, 5500, 10)
        tick = modes(0.15, fr, rng.uniform(0.01, 0.04, 10), rng.uniform(0.5, 1, 10))
        knocks = 0 if settle else rng.integers(1, 4) if run else rng.choice([0, 1, 1, 2])
    elif surface == "grate":
        f = logu(rng, 650, 5200, 18)
        body = modes(0.25, f, rng.uniform(0.015, 0.07, 18) * damp, rng.uniform(0.4, 1.0, 18) * (f / 650) ** -0.3)
        panel = modes(0.2, plate_modes(rng, rng.uniform(190, 250), 8), rng.uniform(0.02, 0.05, 8) * damp, np.ones(8))
        body = mix(unit(body), unit(panel) * db(-5))
        cav = modes(0.3, rng.uniform(70, 105, 2), [0.06 * damp, 0.045 * damp], [1.0, 0.7])
        cav_db = -9
        fr = logu(rng, 1500, 6500, 8)
        tick = modes(0.1, fr, rng.uniform(0.006, 0.025, 8), rng.uniform(0.5, 1, 8))
        knocks = 0 if settle else rng.integers(2, 4) if run else rng.integers(1, 3)
    else:   # sill
        f = logu(rng, 280, 1800, 12)
        body = modes(0.2, f, rng.uniform(0.008, 0.035, 12), rng.uniform(0.5, 1, 12) * (f / 280) ** -0.4)
        cav = modes(0.4, rng.uniform(60, 140, 3), [0.15, 0.1, 0.08], [1.0, 0.6, 0.4])
        cav_db = -6
        tick = None
        knocks = 0
    # 靴底压上去：格栅上同时压上好几根扁钢，就是一串挤在两三毫秒里的小冲击
    exc = heel
    if surface == "grate":
        exc = np.zeros(int(0.005 * SR) + len(heel))
        for at in rng.uniform(0, 0.004, rng.integers(3, 6)):
            place(exc, heel * rng.uniform(0.4, 1.0), int(at * SR))
    place(y, unit(fftconv(exc, body)), 0)
    place(y, unit(fftconv(pulse(3.0), cav)) * db(cav_db), 0)
    # 磕一下 / 颠一下（金属撞金属，冲击极短）
    t0 = rng.uniform(0.006, 0.02)
    for k in range(int(knocks)):
        hit = mix(unit(fftconv(pulse(0.08), tick)), unit(fftconv(pulse(0.08), body)) * db(-6))
        place(y, unit(hit) * db(-5 - 5 * k + (3 if run else 0)), int(t0 * SR))
        t0 += rng.uniform(0.01, 0.03)
    # 脚掌落下
    if not settle:
        place(y, unit(fftconv(pulse(2.0), body)) * fore_amp, int(fore_at * SR))
    # 鞋底砂粒的擦声；跑步最后蹬地一下；停下收脚是一下拖蹭
    place(y, scuff(rng, rng.uniform(20, 40), -16), 0)
    if run:
        place(y, scuff(rng, rng.uniform(40, 70), -15, 900), int(rng.uniform(0.11, 0.16) * SR))
    if settle:
        place(y, scuff(rng, rng.uniform(70, 120), -15, 600), 0)
    # 衣服
    place(y, cloth(rng, rng.uniform(140, 220) if not run else rng.uniform(90, 140), -21 if run else -25), 0)
    return fade(y, 0.0, 0.06)


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


# ---------------------------------------------------------------------------- 巨物（scripts/giant.gd）
def giant_moan(rng):
    """巨物的叫声：二三十赫兹的基频慢慢滑下去，泛音很密，一个共振峰在一二百赫兹之间游走（像一整条沉船在呻吟，
    但是活的）；中间带一段粗糙的颤动，底下垫一层次声的涌动。在舱里隔着艇壳只剩低频，所以主要能量放在 200 Hz 以下。"""
    dur = rng.uniform(6.5, 9.5)
    n = int(dur * SR)
    t = taxis(n)
    f_a, f_b = rng.uniform(26, 38), rng.uniform(16, 22)
    bend = np.clip(t / dur, 0, 1) ** rng.uniform(0.6, 1.4)
    f0 = (f_a + (f_b - f_a) * bend) * (1 + 0.02 * wobble(n, 0.3, 2, rng))
    ph = 2 * np.pi * np.cumsum(f0) / SR
    form = rng.uniform(70, 110) + rng.uniform(40, 110) * np.sin(np.pi * t / dur) ** 2 * (1 + 0.15 * wobble(n, 0.2, 1, rng))
    bw = 45.0
    x = np.zeros(n)
    for k in range(1, 30):
        fk = k * f0
        a = (k ** -0.7) * (0.25 + np.exp(-((fk - form) / bw) ** 2)) * bp(fk, None, 320, 3)
        x += a * np.sin(k * ph + rng.uniform(0, 6.3))
    # 中段粗糙的颤动（声带一样的不规则抖动），两头平滑
    rough = np.clip(1 + 0.55 * wobble(n, 7, 16, rng) * np.sin(np.pi * t / dur) ** 3, 0.05, 2.0)
    x = x / rms(x) * rough
    env = np.clip(t / rng.uniform(1.2, 2.0), 0, 1) ** 2 * np.clip((dur - t) / rng.uniform(2.0, 3.0), 0, 1) ** 1.5
    env *= np.clip(1 + 0.25 * wobble(n, 0.3, 1.5, rng), 0.3, 2)
    swell = noise(n, lambda f: bp(f, 10, 60, 2), rng) * db(-8)
    grit = noise(n, lambda f: bp(f, 150, 700, 2), rng) * np.clip(wobble(n, 3, 12, rng), 0, None) * db(-22)
    return fade((x + swell + grit) * env, 0.0, 0.5)


def giant_swim(rng):
    """巨物游动时排开的水：极低频的涌动，跟着身体摆动（约 0.25 Hz）一下一下地推过来，夹一点甲片摩擦的沙沙声。
    运行时音量跟着距离和速度走。"""
    n = 16 * SR
    t = taxis(n)
    beat = 1 + 0.6 * np.sin(2 * np.pi * loopf(0.25, n) * t) + 0.2 * np.sin(2 * np.pi * loopf(0.5, n) * t + 1.0)
    m = np.clip(1 + 0.3 * wobble(n, 0.1, 1, rng), 0.3, 2)
    sh = lambda f: bp(f, 12, 90, 2) * tilt(f, -4, 30)
    c, l, r = (noise(n, sh, rng) * beat * m for _ in range(3))
    rub = lambda: noise(n, lambda f: bp(f, 200, 900, 2), rng) * np.clip(beat - 0.8, 0, None) * db(-24)
    return stereo(c, l + rub(), r + rub(), 0.6)


def giant_ram(rng):
    """巨物撞上艇身：比撞礁沉得多的一下，整个耐压壳被打得嗡嗡响很久；接着甲片贴着艇壳刮过去的长长一阵摩擦，
    钢板受力的吱嘎，最后几声壳体回弹的“嘣”。"""
    n = int(7.0 * SR)
    y = np.zeros(n)
    w = int(rng.uniform(0.06, 0.1) * SR)
    exc = filt(rng.standard_normal(w), lambda f: bp(f, None, 250, 2)) * np.hanning(w)
    f = logu(rng, 22, 500, 36)
    hull = modes(6.0, f, rng.uniform(0.8, 3.5, 36) * (60 / f) ** 0.3, rng.uniform(0.4, 1, 36) * (f / 60) ** -0.6)
    place(y, fftconv(exc, hull), 0)
    # 刮擦：慢速粘滑敲在钢板模态上，先猛后弱
    m = int(rng.uniform(2.5, 3.5) * SR)
    tt = taxis(m)
    rate = rng.uniform(10, 16) + rng.uniform(15, 30) * np.exp(-tt / 0.8) * (1 + 0.2 * wobble(m, 1, 4, rng))
    amp = np.exp(-tt / 1.2) * np.clip(1 + 0.5 * wobble(m, 1, 6, rng), 0.1, 2)
    fr = logu(rng, 60, 900, 24)
    ir = modes(1.0, fr, rng.uniform(0.1, 0.5, 24) * (200 / fr) ** 0.3, rng.uniform(0.3, 1, 24) * fr ** -0.3)
    scrape = fftconv(np.convolve(stick_slip(m, rate, amp, rng), pulse(0.8))[:m], ir)
    place(y, unit(scrape) * np.abs(y).max() * 0.5, int(0.15 * SR))
    for _ in range(3):
        fp = logu(rng, 200, 2500, 14)
        ring = modes(1.5, fp, rng.uniform(0.2, 0.9, 14) * (500 / fp) ** 0.5, rng.uniform(0.3, 1, 14) * (fp / 500) ** -0.3)
        place(y, unit(fftconv(pulse(0.2), ring)) * np.abs(y).max() * rng.uniform(0.12, 0.25),
              int(rng.uniform(1.2, 5.0) * SR))
    return fade(y, 0.0, 1.0)


# ---------------------------------------------------------------------------- 岸上的房间（宿舍、办事处）
def reverb_ir(rng, rt60, lo=150, hi=6000, pre=0.008):
    """简单的房间混响冲激响应：指数衰减的有色噪声（高频衰减得快一点）。"""
    n = int(rt60 * SR)
    t = taxis(n)
    x = filt(rng.standard_normal(n), lambda f: bp(f, lo, hi, 1)) * np.exp(-6.9 * t / rt60)
    x[: int(pre * SR)] = 0.0
    return x / (np.abs(x).sum() + 1e-9) * 40


def rain_window(rng, steel=False):
    """窗外的雨（循环）：外面一片哗哗的雨声（有一阵一阵的风），雨点一颗颗打在玻璃上「嗒」（玻璃的高频小模态，很短），
    打在铁防盗窗 / 钢窗框上「叮」（细铁条的模态，余音长一点），窗台上积水往下滴，排水管里哗哗流。
    steel：办事处的大钢窗——玻璃多、雨更密，没有防盗窗。"""
    n = 20 * SR
    gust = np.clip(1 + 0.35 * wobble(n, 0.04, 0.25, rng), 0.4, 1.8)
    hiss = lambda: noise(n, lambda f: bp(f, 250, 9000, 1) * tilt(f, -2.5, 1500), rng) * gust
    far_c, far_l, far_r = hiss(), hiss(), hiss()
    # 打在玻璃上：每秒几十颗，每颗一下极短的冲击
    rate = 70 if steel else 45
    k = int(rate * n / SR)
    glass = np.zeros(n)
    fg = logu(rng, 1800, 7500, 8)
    tick = modes(0.03, fg, rng.uniform(0.002, 0.008, 8), rng.uniform(0.4, 1, 8))
    for at in rng.integers(0, n, k):
        place(glass, tick * rng.uniform(0.15, 1.0) ** 2 * gust[at], int(at), circular=True)
    # 打在铁条 / 钢框上
    metal = np.zeros(n)
    fm = logu(rng, 1300, 4800, 6)
    tink = modes(0.25, fm, rng.uniform(0.03, 0.09, 6), rng.uniform(0.4, 1, 6))
    for at in rng.integers(0, n, int((6 if steel else 9) * n / SR)):
        place(metal, tink * rng.uniform(0.2, 1.0) ** 2, int(at), circular=True)
    # 窗台积水滴下去（几秒一滴，落在下面的铁皮托板上）
    drips = np.zeros(n)
    fd = logu(rng, 600, 2600, 6)
    plink = modes(0.35, fd, rng.uniform(0.04, 0.12, 6), rng.uniform(0.4, 1, 6))
    for at in np.arange(rng.uniform(0, 1.5), n / SR, rng.uniform(1.1, 1.9)):
        place(drips, plink * rng.uniform(0.5, 1.0), int(at * SR), circular=True)
    # 排水管：一股水流的咕嘟声
    gutter = noise(n, lambda f: bp(f, 180, 1400, 2), rng) * np.clip(1 + 0.6 * wobble(n, 1.5, 6, rng), 0.1, 2.5)
    c = unit(far_c) + unit(glass) * db(-6) + unit(metal) * db(-16 if steel else -11) + unit(drips) * db(-15)
    return stereo(c, unit(far_l) * db(-3) + unit(gutter) * db(-14), unit(far_r) * db(-3), 0.6)


def fan_whir(rng):
    """三叶吊扇（低速档，一秒转一圈多）：电机 100 Hz 的嗡声，叶片切过空气一下一下的「呼——」（每秒三四下），
    一片叶子有点松，每转一圈在叶柄上磕一下「嗒」。"""
    n = 6 * SR
    t = taxis(n)
    rev = loopf(1.1, n)
    hum = sum(k ** -1.3 * np.sin(2 * np.pi * 100 * k * t + rng.uniform(0, 6.3)) for k in range(1, 6))
    swish = noise(n, lambda f: bp(f, 150, 2500, 1) * tilt(f, -3, 300), rng)
    swish *= 0.45 + 0.55 * (0.5 + 0.5 * np.cos(2 * np.pi * 3 * rev * t)) ** 2
    ticks = np.zeros(n)
    f = logu(rng, 900, 4000, 5)
    click = modes(0.06, f, rng.uniform(0.005, 0.02, 5), np.ones(5))
    for k in range(int(rev * n / SR)):
        place(ticks, click * rng.uniform(0.6, 1.0), int((k / rev + 0.03) * SR), circular=True)
    return unit(hum) * db(-14) + unit(swish) + unit(ticks) * db(-20)


def radio_static(rng):
    """中波收音机没对准台：带通的沙沙声，一下一下的噼啪（远处在打雷），一个慢慢漂着的口哨音（差拍）。"""
    n = 8 * SR
    t = taxis(n)
    hiss = noise(n, lambda f: bp(f, 250, 4500, 2), rng) * np.clip(1 + 0.3 * wobble(n, 0.5, 4, rng), 0.3, 2)
    crack = np.zeros(n)
    for at in rng.integers(0, n, 40):
        place(crack, burst(rng.uniform(2, 12), lambda f: bp(f, 300, 4000, 1), rng) * rng.uniform(0.3, 1.0), int(at),
              circular=True)
    whistle_f = 1200 + 300 * wobble(n, 0.05, 0.2, rng)
    whistle = np.sin(2 * np.pi * np.cumsum(whistle_f) / SR)
    whistle *= np.clip(0.5 + 0.5 * wobble(n, 0.1, 0.4, rng), 0, 1)
    return unit(hiss) + unit(crack) * db(-6) + whistle * db(-22)


def pager_beep(rng):
    """汉显 BP 机来传呼：小喇叭「哔哔哔」三声（两千多赫兹的方波，喇叭小、低频全没了），
    同时机子在木桌上震——震动马达的嗡嗡传到桌板上，桌子跟着共鸣。"""
    n = int(1.3 * SR)
    t = taxis(n)
    y = np.zeros(n)
    f0 = 2730.0
    sq = np.sign(np.sin(2 * np.pi * f0 * t)) * 0.7 + 0.3 * np.sin(2 * np.pi * f0 * t)
    sq = filt(sq, lambda f: bp(f, 1500, 9000, 2))
    for k in range(3):
        a, b = int((0.0 + 0.2 * k) * SR), int((0.12 + 0.2 * k) * SR)
        seg = sq[a:b] * np.hanning(b - a) ** 0.2
        place(y, seg, a)
    buzz = np.sign(np.sin(2 * np.pi * 155 * t)) * np.clip(np.sin(np.pi * t / 1.2), 0, 1) ** 0.3
    f = logu(rng, 120, 900, 10)
    desk = fftconv(buzz * 0.02, modes(0.4, f, rng.uniform(0.02, 0.06, 10), np.ones(10)))[:n]
    return unit(y) + unit(desk) * db(-8)


def knock(rng):
    """有人用指节敲木门「咚、咚、咚」：门板（四块门芯板的三合板）的低频模态 + 指节磕上去的一点脆响，三下间隔差不多、越来越轻。"""
    n = int(1.6 * SR)
    y = np.zeros(n)
    f = plate_modes(rng, rng.uniform(95, 120), 16)
    door = modes(0.4, f, rng.uniform(0.03, 0.09, 16) * (f[0] / f) ** 0.3, rng.uniform(0.4, 1, 16) * (f / f[0]) ** -0.4)
    fk = logu(rng, 1200, 3500, 5)
    knuckle = modes(0.05, fk, rng.uniform(0.004, 0.012, 5), np.ones(5))
    at = 0.0
    for k in range(3):
        hit = mix(unit(fftconv(pulse(rng.uniform(1.0, 1.6)), door)), unit(fftconv(pulse(0.3), knuckle)) * db(-12))
        place(y, unit(hit) * db(-2.5 * k), int(at * SR))
        at += rng.uniform(0.36, 0.44)
    return y


def concrete_step(rng, level_db=0.0, gait="walk"):
    """皮鞋踩水泥地（宿舍、走廊）：实心地面没有共鸣，就是一下闷的「嗒」，鞋跟磕一下、鞋底压着细砂蹭一下。"""
    n = int(0.3 * SR)
    y = np.zeros(n)
    f = logu(rng, 150, 2200, 10)
    body = modes(0.15, f, rng.uniform(0.004, 0.02, 10), rng.uniform(0.5, 1, 10) * (f / 150) ** -0.2)
    heel = pulse(rng.uniform(0.5, 0.9) if gait == "run" else rng.uniform(0.8, 1.4))
    place(y, unit(fftconv(heel, body)), 0)
    if gait != "settle":
        place(y, unit(fftconv(pulse(1.8), body)) * rng.uniform(0.25, 0.4), int(rng.uniform(0.05, 0.09) * SR))
    place(y, scuff(rng, rng.uniform(25, 50), -14, 1500), 0)
    if gait == "run":
        place(y, scuff(rng, rng.uniform(40, 70), -13, 900), int(rng.uniform(0.09, 0.13) * SR))
    place(y, cloth(rng, rng.uniform(120, 200), -24), 0)
    return unit(y) * db(level_db)


def terrazzo_step(rng, gait="walk"):
    """皮鞋踩水磨石（办事处）：比水泥更硬更亮，鞋跟「咔」的一声清脆，大屋子里有一点回声。"""
    y = concrete_step(rng, 0.0, gait)
    f = logu(rng, 1800, 6000, 6)
    click = fftconv(pulse(0.12), modes(0.04, f, rng.uniform(0.002, 0.008, 6), np.ones(6)))
    y = mix(y, unit(click) * db(-7))
    return mix(y, fftconv(y, reverb_ir(rng, 0.7, 300, 5000)) * db(-14))


def steps_away(rng):
    """门外的脚步声走远：七八步，水泥走廊里回声很重，越走越轻、越闷，最后一下在楼梯口。"""
    n = int(5.0 * SR)
    y = np.zeros(n)
    ir = reverb_ir(rng, 1.4, 120, 4000)
    at = 0.35
    for k in range(8):
        s = concrete_step(rng, -2.5 * k)
        s = filt(s, lambda f, k=k: bp(f, None, 6000 / (1 + 0.5 * k), 1))
        place(y, s, int(at * SR))
        at += rng.uniform(0.5, 0.6)
    wet = fftconv(y, ir)[:n]
    return fade(y * 0.6 + wet * 1.2, 0.0, 0.5)


def envelope(rng):
    """信从门缝底下塞进来：纸贴着水泥地滑过去的沙沙声（越滑越慢），最后纸角一顿。"""
    n = int(1.2 * SR)
    t = taxis(n)
    env = np.clip(np.sin(np.pi * t / 0.95), 0, 1) ** 0.7 * (t < 0.95) * (1 - 0.5 * t)
    x = noise(n, lambda f: bp(f, 1200, 9000, 1) * tilt(f, -1.5, 3000), rng) * env
    x *= np.clip(1 + 0.6 * wobble(n, 5, 30, rng), 0.2, 2.0)
    stop = burst(25, lambda f: bp(f, 600, 5000, 1), rng)
    y = unit(x)
    place(y, unit(stop) * db(-6), int(0.92 * SR))
    return y


def wood_door(rng, opening=True):
    """木门：开——球形锁的锁舌「咔」地缩回去，合页「吱——」（细销子干摩擦，比水密门尖得多）；
    关——合页短短一声，门扇拍上门框「嘭」（木板的低频），锁舌弹进锁扣「咔嗒」。"""
    n = int(1.6 * SR)
    y = np.zeros(n)
    fl = logu(rng, 1500, 6000, 6)
    latch = fftconv(pulse(0.15), modes(0.06, fl, rng.uniform(0.004, 0.015, 6), np.ones(6)))
    m = int((0.9 if opening else 0.35) * SR)
    rate = 45 + 20 * wobble(m, 0.5, 3, rng)
    amp = np.clip(np.sin(np.pi * taxis(m) / (m / SR)), 0, 1) * np.clip(1 + 0.5 * wobble(m, 2, 10, rng), 0.2, 2)
    ss = np.convolve(stick_slip(m, rate, amp, rng), pulse(0.4))[:m]
    fh = logu(rng, 700, 3200, 8)
    creak = fftconv(ss, modes(0.2, fh, rng.uniform(0.01, 0.04, 8), rng.uniform(0.4, 1, 8)))[:m]
    fdoor = plate_modes(rng, rng.uniform(85, 110), 14)
    thud = fftconv(pulse(4.0), modes(0.5, fdoor, rng.uniform(0.04, 0.12, 14), np.ones(14)))
    if opening:
        place(y, unit(latch), 0)
        place(y, unit(creak) * db(-6), int(0.12 * SR))
    else:
        place(y, unit(creak) * db(-10), 0)
        place(y, unit(thud), int(0.35 * SR))
        place(y, unit(latch) * db(-4), int(0.37 * SR))
    return y


def tube_start(rng):
    """日光灯启动：启辉器里的双金属片「叮、叮」碰几下（每下伴一声镇流器的「嗡」），最后灯管亮起来，嗡声稳住。"""
    n = int(2.2 * SR)
    t = taxis(n)
    y = np.zeros(n)
    f = logu(rng, 3000, 9000, 5)
    ping = modes(0.08, f, rng.uniform(0.01, 0.03, 5), np.ones(5))
    for at in (0.0, 0.3, 0.42, 0.85, 1.05):
        place(y, unit(fftconv(pulse(0.08), ping)) * rng.uniform(0.5, 1.0), int(at * SR))
        m = int(0.12 * SR)
        hum = sum(k ** -1 * np.sin(2 * np.pi * 100 * k * taxis(m)) for k in range(1, 8)) * np.hanning(m)
        place(y, unit(hum) * db(-10), int(at * SR))
    steady = sum(k ** -1 * np.sin(2 * np.pi * 100 * k * t) for k in range(1, 8)) * np.clip((t - 1.15) / 0.2, 0, 1)
    return unit(y) + unit(steady) * db(-16)


def paper(rng):
    """拿起一张纸：纸面一抖的哗啦声（一串很密的小噼啪），起落都快。"""
    n = int(0.6 * SR)
    t = taxis(n)
    env = np.clip(np.sin(np.pi * t / 0.5), 0, 1) * (t < 0.5)
    x = noise(n, lambda f: bp(f, 800, 10000, 1), rng) * env * np.clip(1 + 1.2 * wobble(n, 20, 120, rng), 0, 3)
    return unit(x)


def pen_write(rng):
    """钢笔在纸上写字（垫着玻璃板）：一笔一笔的沙沙声，笔画之间抬笔停一下；每一笔落下时笔尖在玻璃上磕一下。"""
    n = int(4.5 * SR)
    y = np.zeros(n)
    at = 0.05
    f = logu(rng, 2500, 8000, 5)
    tap = modes(0.03, f, rng.uniform(0.002, 0.006, 5), np.ones(5))
    while at < 4.3:
        L = rng.uniform(0.06, 0.22)
        m = int(L * SR)
        tt = taxis(m)
        stroke = noise(m, lambda f: bp(f, 2500, 11000, 2), rng) * np.sin(np.pi * tt / L) ** 0.5
        place(y, unit(stroke) * rng.uniform(0.4, 1.0), int(at * SR))
        place(y, unit(fftconv(pulse(0.1), tap)) * db(-14), int(at * SR))
        at += L + rng.uniform(0.03, 0.15)
    return y


def soft_press(rng, sticky=False):
    """手指按下去：指肚压在纸上（底下是玻璃板）一声闷闷的「噗」；sticky：按进印泥，抬起来带一点黏的「嘁」。"""
    n = int(0.5 * SR)
    y = np.zeros(n)
    f = logu(rng, 200, 1500, 8)
    place(y, unit(fftconv(pulse(6.0), modes(0.15, f, rng.uniform(0.01, 0.03, 8), np.ones(8)))), 0)
    if sticky:
        place(y, unit(burst(40, lambda f: bp(f, 1500, 8000, 1), rng)) * db(-10), int(0.25 * SR))
    return y


def clock_tick(rng, tock=False):
    """摆钟走一下：擒纵叉打在擒纵轮上一声脆的「嘀」（tock 低一点），木壳子跟着「嗒」地共鸣。"""
    n = int(0.25 * SR)
    y = np.zeros(n)
    f = logu(rng, 2200 if not tock else 1700, 7000, 6)
    place(y, unit(fftconv(pulse(0.06), modes(0.05, f, rng.uniform(0.003, 0.01, 6), np.ones(6)))), 0)
    fc = plate_modes(rng, rng.uniform(260, 320) * (0.85 if tock else 1.0), 10)
    place(y, unit(fftconv(pulse(0.3), modes(0.2, fc, rng.uniform(0.01, 0.04, 10), np.ones(10)))) * db(-6), 0)
    return y


def clock_stop(rng):
    """钟停了：最后一下比平时沉（擒纵卡住了），钟摆磕在壳子上一声闷响。"""
    y = clock_tick(rng, True)
    f = plate_modes(rng, 180, 12)
    thump = fftconv(pulse(2.0), modes(0.5, f, rng.uniform(0.03, 0.1, 12), np.ones(12)))
    return mix(unit(y) * db(-4), unit(thump))


def thunder(rng):
    """远处打雷：先一阵噼噼啪啪的爆裂（高频，很快没了），接着低沉的隆隆声滚好几秒，一阵一阵的。"""
    n = int(rng.uniform(5, 8) * SR)
    t = taxis(n)
    crack = noise(n, lambda f: bp(f, 200, 3000, 1), rng) * np.exp(-t / 0.25) * np.clip(t / 0.02, 0, 1)
    roll_env = np.clip(t / 0.3, 0, 1) * np.exp(-t / (n / SR / 2.5))
    roll_env *= np.clip(1 + 0.8 * wobble(n, 0.6, 3.0, rng), 0.1, 2.5)
    roll = noise(n, lambda f: bp(f, 20, 260, 2) * tilt(f, -4, 40), rng) * roll_env
    return unit(crack) * db(-8) + unit(roll)


def chair_creak(rng):
    """坐到木椅子上：榫头松了，「嘎吱」一声（木头的粘滑，比铰链低、比门扇高）。"""
    m = int(rng.uniform(0.25, 0.45) * SR)
    rate = 60 + 25 * wobble(m, 0.5, 3, rng)
    amp = np.clip(np.sin(np.pi * taxis(m) / (m / SR)), 0, 1)
    ss = np.convolve(stick_slip(m, rate, amp, rng), pulse(0.6))[:m]
    f = logu(rng, 300, 1800, 10)
    return unit(fftconv(ss, modes(0.2, f, rng.uniform(0.01, 0.05, 10), np.ones(10))))


def wall_switch(rng):
    """墙上的胶木扳把开关「咔」：弹簧过死点一下，没有接触器。"""
    n = int(0.12 * SR)
    y = np.zeros(n)
    f = logu(rng, 1500, 6000, 6)
    place(y, fftconv(pulse(0.1), modes(0.05, f, rng.uniform(0.003, 0.012, 6), np.ones(6))), 0)
    place(y, fftconv(pulse(0.6), modes(0.08, logu(rng, 250, 900, 4), [0.01, 0.015, 0.01, 0.02], np.ones(4))) * 0.5, 0)
    return y


def ship_horn(rng):
    """远处船的汽笛：一声低沉的长鸣（一百多赫兹带一串谐波），隔着雨和港湾，后面拖着回声。"""
    n = int(6.0 * SR)
    t = taxis(n)
    f0 = rng.uniform(110, 140)
    env = np.clip(t / 0.3, 0, 1) * np.clip((3.2 - t) / 0.5, 0, 1)
    x = sum(k ** -0.9 * np.sin(2 * np.pi * f0 * k * t + rng.uniform(0, 6.3)) for k in range(1, 10)) * env
    x = filt(x, lambda f: bp(f, 80, 1500, 2))
    return fade(x + fftconv(x, reverb_ir(rng, 2.5, 80, 1200))[:n] * 2.0, 0.0, 1.0)


def harbor(rng):
    """港湾的水声（循环，办事处窗外）：码头墙脚的水一下一下拍着（十来秒一个浪），远处一片模糊的水声。"""
    n = 24 * SR
    t = taxis(n)
    waves = 0.5 + 0.5 * np.cos(2 * np.pi * loopf(0.11, n) * t) + 0.3 * wobble(n, 0.05, 0.2, rng)
    lap = noise(n, lambda f: bp(f, 120, 1500, 2), rng) * np.clip(waves, 0, None) ** 2
    far = noise(n, lambda f: bp(f, 60, 600, 1) * tilt(f, -3, 100), rng)
    return unit(lap) + unit(far) * db(-6)


# ---------------------------------------------------------------------------- 冰井（开场：冰震、一圈圈灯灭掉）
def shaft_air(rng):
    """二十公里深的冰井里的空气：竖井像一根巨大的管子，低频的气流涌动里带着几个很宽的共鸣峰（管子里的驻波），
    极慢地涨落；再加一层很淡的、左右各自不同的高处嘶声，让井显得又高又空。"""
    n = 16 * SR

    def shape(f):
        g = bp(f, 22, 500, 2) * tilt(f, -4.5, 60)
        for k, f0 in enumerate([31.0, 47.0, 63.0, 94.0, 141.0]):
            g = g + 1.6 / (k + 1) * np.exp(-0.5 * ((f - f0) / (f0 * 0.05)) ** 2)
        return g

    c = noise(n, shape, rng) * np.clip(1 + 0.4 * wobble(n, 0.03, 0.25, rng), 0.25, None)
    hiss = lambda f: bp(f, 1500, 9000, 2)
    return stereo(unit(c), unit(noise(n, hiss, rng)) * db(-30), unit(noise(n, hiss, rng)) * db(-30), 1.0)


def shaft_hum(rng):
    """一圈圈灯的镇流器嗡声：十几个 100 Hz 的嗡声叠在一起，频率各差一点点，互相拍出很慢的起伏；
    再带一点跟着电网半周期一下一下的“滋”。运行时音量跟着还亮着的灯走。"""
    n = 8 * SR
    t = taxis(n)
    y = np.zeros(n)
    for _ in range(12):
        f0 = loopf(100.0 + rng.uniform(-0.6, 0.6), n)
        ph = rng.uniform(0, 2 * np.pi)
        for h, a in [(1, 1.0), (2, 0.35), (3, 0.5), (5, 0.22), (7, 0.12)]:
            y += a * np.sin(2 * np.pi * loopf(f0 * h, n) * t + ph * h)
    gate = (0.5 + 0.5 * np.sin(2 * np.pi * loopf(100.0, n) * t)) ** 8
    buzz = noise(n, lambda f: bp(f, 2000, 7000, 2), rng) * gate
    return unit(y) + unit(buzz) * db(-26)


def ice_boom(rng):
    """冰震：几公里外的冰壳在断裂，经过冰和钢架传进井里——先是越来越响的次声轰鸣，中间夹着远处冰层
    噼噼啪啪的碎裂（隔得远，只剩闷的），最后一声低吼往下滑着沉下去。"""
    dur = 10.0
    n = int(dur * SR)
    t = taxis(n)
    env = (1 - np.exp(-t / 1.6)) * np.exp(-np.maximum(t - 2.8, 0) / 2.6)
    slow = unit(filt(rng.standard_normal(n), lambda f: bp(f, 0.5, 4, 2)))
    rumble = unit(filt(rng.standard_normal(n), lambda f: bp(f, 20, 90, 3) * tilt(f, -6, 30)))
    rumble = rumble * env * (1 + 0.5 * slow)
    f_inst = 30 + 24 * np.exp(-t / 5.0)
    ph = 2 * np.pi * np.cumsum(f_inst) / SR
    groan = (np.sin(ph) + 0.5 * np.sin(2 * ph + 0.3) + 0.3 * np.sin(3 * ph + 1.1)) * env ** 1.5
    crk = np.zeros(n)
    for tt in np.sort(rng.uniform(0.5, 7.0, 70)):
        b = burst(rng.uniform(2, 12), lambda f: bp(f, 150, 2500, 2), rng)
        place(crk, b * rng.uniform(0.2, 1.0) * env[int(tt * SR)], int(tt * SR))
    crk = filt(crk, lambda f: bp(f, None, 1800, 2))
    return unit(rumble) + unit(groan) * db(-8) + unit(crk) * db(-14)


BREAKER_WAV = OUT.parent / "third_party" / "freesound" / "131599__echocinematics__kill-switch-large-breaker-switch.wav"


def load_recording(path):
    """读一段外部录音（用 ffmpeg 解码，什么格式都行），转成 48 kHz 浮点、按声道排的数组。"""
    import subprocess
    ch = int(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=channels", "-of", "csv=p=0", str(path)],
                            capture_output=True, text=True, check=True).stdout.split()[0])
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ar", str(SR), "-f", "f32le", "-acodec", "pcm_f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, "<f4").astype(np.float64).reshape(-1, ch)


def relay_drop(rng):
    """一圈灯的电闸断开：用实录的大电闸（Freesound 131599，EchoCinematics，CC0；5.1 声道的文件，只有左右两声道有声音），
    从“咔嚓”前 10 毫秒剪起，连着它自己两秒的余响。三个变体音调各差一点（变慢 / 原样 / 变快），游戏里再随机变一点调。"""
    x = load_recording(BREAKER_WAV)[:, :2]
    on = int(np.argmax(np.abs(x).max(axis=1) > 0.05 * np.abs(x).max()))
    x = x[max(0, on - int(0.01 * SR)):]
    ratio = [0.93, 1.0, 1.06][_VARIANT % 3]
    n = int(len(x) / ratio)
    src = np.arange(n) * ratio
    y = np.stack([np.interp(src, np.arange(len(x)), x[:, c]) for c in range(2)], axis=1)
    return fade(y, 0.002, 0.0)


def steel_groan(rng):
    """井壁上一整圈钢架被冰挤着扭：很慢的粘滑（每秒十来下到二十几下）敲在大结构的低频模态上，又低又长的“嘎——”。"""
    dur = rng.uniform(2.5, 3.5)
    n = int(dur * SR)
    t = taxis(n)
    arch = np.sin(np.pi * t / dur)
    rate = 9 + 16 * arch ** 1.5 * np.clip(1 + 0.25 * wobble(n, 0.5, 3, rng), 0.3, None)
    exc = stick_slip(n, rate, arch ** 0.8, rng)
    ir = modes(1.5, logu(rng, 55, 700, 14), rng.uniform(0.08, 0.5, 14), rng.uniform(0.3, 1, 14))
    return fftconv(exc, ir)


def spark_crackle(rng):
    """断开的电缆头打火：一串越来越稀的“噼啪”，每一下是零点几毫秒的高频爆。"""
    n = int(1.4 * SR)
    y = np.zeros(n)
    tt = 0.0
    while tt < 1.2:
        place(y, burst(rng.uniform(0.2, 1.0), lambda f: bp(f, 1800, 14000, 2), rng) * rng.uniform(0.2, 1)
              * np.exp(-tt / 0.5), int(tt * SR))
        tt += rng.exponential(0.008 + tt * 0.05)
    return y



def steam_burst(rng):
    """冰裂扯开的加热管往外喷汽：开头一下猛的（管里的压力一口气冲出来），然后一直嘶嘶地喷，压力慢慢掉，
    和画面上的喷汽同一条包络（0.35 + 0.65·e^(-t/2.5)）。喷口的湍流让嘶声一直在抖，低处带一层闷的“轰”，
    偶尔夹着几下凝结水被冲出来的“噗嗤”。"""
    dur = 22.0
    n = int(dur * SR)
    t = taxis(n)
    env = (0.35 + 0.65 * np.exp(-t / 2.5)) * np.clip(t / 0.015, 0, 1) * np.clip((dur - t) / 4.0, 0, 1)
    # 嘶声：峰在三四千赫，压力高的时候亮一点（高频多一点）
    hiss_hi = noise(n, lambda f: bp(f, 2500, 11000, 2), rng)
    hiss_mid = noise(n, lambda f: bp(f, 700, 5000, 2) * tilt(f, 1.5, 2000), rng)
    bright = 0.35 + 0.65 * np.exp(-t / 2.5)
    hiss = hiss_mid + hiss_hi * bright * 0.8
    # 湍流：几赫兹到二十几赫兹的乱抖
    hiss *= np.clip(1 + 0.25 * wobble(n, 4, 25, rng) + 0.15 * wobble(n, 0.3, 2, rng), 0.2, None)
    roar = noise(n, lambda f: bp(f, 60, 600, 2) * tilt(f, -3, 150), rng)
    roar *= np.clip(1 + 0.3 * wobble(n, 1, 8, rng), 0.2, None)
    y = unit(hiss) + unit(roar) * db(-9)
    y = y * env
    # 刚崩开那一下：一口宽频的“噗”
    place(y, unit(burst(160, lambda f: bp(f, 150, 8000, 2), rng)) * 1.2, 0)
    # 凝结水“噗嗤”
    tt = rng.uniform(0.6, 1.2)
    while tt < dur - 5:
        place(y, unit(burst(rng.uniform(15, 50), lambda f: bp(f, 800, 9000, 2), rng)) * rng.uniform(0.4, 1.0)
              * (0.35 + 0.65 * np.exp(-tt / 2.5)), int(tt * SR))
        tt += rng.exponential(1.4)
    return y

# ---------------------------------------------------------------------------- 破舱（scripts/breach.gd）
# 都是合成的占位：真东西（钢板撕裂、高压水）以后换成实录更好，见 docs/design.md「破舱」。
def breach_strain(rng):
    """艇壳被从外面往里压、快撑不住了（2.6 秒，和 breach.gd 的 STRAIN 对齐）：低沉的吱嘎越来越密、越来越紧，
    中间几声“嘣”，最后半秒一条裂缝先滋出一股细水（嘶声从无到有、越来越尖）。"""
    dur = 2.6
    n = int(dur * SR)
    t = taxis(n)
    k = t / dur
    rate = 7 + 70 * k ** 2.2 * np.clip(1 + 0.2 * wobble(n, 2, 9, rng), 0.3, None)
    env = (0.25 + 0.75 * k ** 1.3) * np.clip(1 + 0.35 * wobble(n, 2, 8, rng), 0.1, None)
    x = np.convolve(stick_slip(n, rate, env, rng), pulse(0.5))[:n]
    f = logu(rng, 45, 1200, 28)
    ir = modes(1.2, f, rng.uniform(0.1, 0.6, 28) * (150 / f) ** 0.3, rng.uniform(0.3, 1, 28) * f ** -0.25)
    y = fftconv(x, ir)[:n]
    y = unit(y)
    for tt in sorted(rng.uniform(0.4, 2.3, 4)):
        f2 = logu(rng, 250, 3200, 14)
        ring = modes(1.2, f2, rng.uniform(0.15, 0.8, 14) * (500 / f2) ** 0.5, rng.uniform(0.3, 1, 14))
        place(y, unit(fftconv(pulse(0.2), ring)) * (0.35 + 0.5 * tt / dur), int(tt * SR))
    # 裂缝滋水
    hs = int(2.05 * SR)
    m = n - hs
    tm = taxis(m)
    hiss = noise(m, lambda f: bp(f, 1800, 12000, 2), rng) * np.clip(1 + 0.4 * wobble(m, 10, 40, rng), 0, None)
    place(y, unit(hiss) * (tm / tm[-1]) ** 1.5 * 0.5, hs)
    return fade(y, 0.0, 0.05)


def breach_burst(rng):
    """崩开的那一下：整个艇壳被砸响的一声巨响（低频长嗡），同时钢板撕裂的尖啸（高速粘滑敲在高频模态上，零点三秒），
    一口宽频的水爆。水柱的持续轰鸣是另一个循环音（breach_jet），同时开始。"""
    n = int(5.0 * SR)
    y = np.zeros(n)
    w = int(0.012 * SR)
    exc = filt(rng.standard_normal(w), lambda f: bp(f, None, 1500, 2)) * np.hanning(w)
    f = logu(rng, 28, 1100, 36)
    hull = modes(5.0, f, rng.uniform(0.5, 3.0, 36) * (60 / f) ** 0.35, rng.uniform(0.4, 1, 36) * (f / 60) ** -0.45)
    place(y, unit(fftconv(exc, hull)), 0)
    # 撕裂：粘滑从每秒几百下扫到上千下，敲在高频的板模态上
    m = int(0.38 * SR)
    tm = taxis(m)
    rate = 380 + 900 * (tm / tm[-1]) ** 0.6 * np.clip(1 + 0.3 * wobble(m, 20, 80, rng), 0.2, None)
    tear = stick_slip(m, rate, np.exp(-tm / 0.2), rng)
    f2 = logu(rng, 900, 9000, 30)
    tear = fftconv(tear, modes(0.4, f2, rng.uniform(0.01, 0.06, 30), rng.uniform(0.3, 1, 30)))
    place(y, unit(tear) * 0.7, int(0.005 * SR))
    # 低频的“咚”
    place(y, unit(modes(1.5, [32, 47, 61], [0.35, 0.25, 0.2], [1, 0.7, 0.5])) * 0.9, 0)
    # 水爆
    bl = int(1.2 * SR)
    tb = taxis(bl)
    blast = noise(bl, lambda f: bp(f, 120, 9000, 1) * tilt(f, -1.5, 1000), rng) * np.exp(-tb / 0.35)
    place(y, unit(blast) * 0.8, int(0.01 * SR))
    return fade(y, 0.0, 1.0)


def _bubbles(n, rng, rate, r_lo, r_hi, circular=True):
    """一串气泡声（Minnaert 共振：半径 r 米的气泡约 3.26/r 赫兹；破的时候音调往上滑一点，几毫秒到几十毫秒衰减完）。"""
    y = np.zeros(n)
    count = int(rate * n / SR)
    for _ in range(count):
        r = np.exp(rng.uniform(np.log(r_lo), np.log(r_hi)))
        f0 = 3.26 / r
        tau = 0.0006 + 0.012 * (r / r_hi) ** 0.8
        L = int(min(tau * 6, 0.08) * SR)
        tt = taxis(L)
        b = np.sin(2 * np.pi * f0 * tt * (1 + rng.uniform(0.05, 0.25) * tt / tau / 6)) * np.exp(-tt / tau)
        b *= np.clip(tt / 0.0004, 0, 1)
        place(y, b * rng.uniform(0.2, 1.0) * (r / r_hi) ** 0.3, int(rng.uniform(0, n)), circular)
    return y


def breach_jet(rng):
    """高压水柱横穿过舱、砸在对面柜门上（循环）：像高压水枪、消防水龙对着铁皮柜子猛冲——
    宽频的“哗——”（峰在一两千赫，湍流一直在抖），底下是水砸钢板的密集鼓点和柜子的低频轰鸣。"""
    n = 12 * SR
    sh = lambda f: bp(f, 250, 7000, 2) * tilt(f, -1.0, 1500)
    roar_l, roar_r = noise(n, sh, rng), noise(n, sh, rng)
    mod = np.clip(1 + 0.25 * wobble(n, 3, 18, rng) + 0.12 * wobble(n, 0.3, 2, rng), 0.2, None)
    hiss = noise(n, lambda f: bp(f, 3000, 14000, 2), rng) * db(-8)
    # 水砸铁皮：每秒几百下的密集冲击（循环脉冲串）卷柜门、艇壳的模态
    rate = 520 * np.clip(1 + 0.3 * wobble(n, 2, 12, rng), 0.3, None)
    hits = stick_slip(n, rate, np.ones(n), rng, circular=True)
    f = logu(rng, 60, 900, 22)
    drum = cconv(hits, modes(0.6, f, rng.uniform(0.03, 0.2, 22), rng.uniform(0.3, 1, 22) * (f / 100) ** -0.4))
    low = noise(n, lambda f: bp(f, 30, 160, 2), rng) * np.clip(1 + 0.4 * wobble(n, 1, 6, rng), 0.1, None)
    c = unit(drum) * db(-6) + unit(low) * db(-8)
    l = (unit(roar_l) + unit(hiss) * db(-6)) * mod
    r = (unit(roar_r) + unit(np.roll(hiss, n // 3)) * db(-6)) * np.roll(mod, n // 5)
    return stereo(c, l, r, 1.0)


def flood_churn(rng):
    """舱里的水被搅得翻天（循环）：一大片气泡的咕嘟、哗啦，水撞来撞去的低沉晃荡。"""
    n = 10 * SR
    bub = _bubbles(n, rng, 260, 0.0025, 0.03)
    bub2 = _bubbles(n, rng, 260, 0.0025, 0.03)
    slosh = noise(n, lambda f: bp(f, 35, 260, 2), rng) * np.clip(1 + 0.6 * wobble(n, 0.4, 3, rng), 0.05, None)
    splash = noise(n, lambda f: bp(f, 400, 6000, 1) * tilt(f, -2, 800), rng) * np.clip(0.6 + 0.5 * wobble(n, 1, 7, rng), 0, None)
    c = unit(slosh) * db(-4)
    return stereo(c, unit(bub) + unit(splash) * db(-12), unit(bub2) + unit(np.roll(splash, n // 2)) * db(-12), 1.0)


def underwater_roar(rng):
    """头没进水里听到的（循环）：水柱在水里冲出来的低沉轰鸣盖住一切，夹着闷掉的气泡咕嘟，压着耳朵的一层低频脉动。"""
    n = 10 * SR
    roar = noise(n, lambda f: bp(f, 25, 420, 2) * tilt(f, -2.5, 80), rng)
    roar *= np.clip(1 + 0.3 * wobble(n, 0.5, 4, rng), 0.2, None)
    bub = filt(_bubbles(n, rng, 180, 0.004, 0.04), lambda f: bp(f, None, 1100, 2))
    bub2 = filt(_bubbles(n, rng, 180, 0.004, 0.04), lambda f: bp(f, None, 1100, 2))
    throb = noise(n, lambda f: bp(f, 12, 45, 2), rng)
    c = unit(roar) + unit(throb) * db(-6)
    return stereo(c, unit(bub) * db(-8), unit(bub2) * db(-8), 1.0)


# ---------------------------------------------------------------------------- 破舱：ElevenLabs 生成的版本
# 原始文件由 tools/gen_sfx_el.py 生成（assets/third_party/elevenlabs/，描述和套餐记在 prompts.json）；这里挑版本、裁剪、
# 做模型做不出来的部分（渐强、接上合成的裂缝滋水），统一成 48 kHz 立体声。上面合成的版本留着对比（*_synth）。
EL = Path(__file__).resolve().parent.parent / "assets" / "third_party" / "elevenlabs"


def _el(name):
    x = load_recording(EL / f"{name}.mp3")
    return x if x.shape[1] == 2 else np.repeat(x, 2, axis=1)


def _cfilt(x, shape):
    """循环滤波（整段当一个周期做 FFT，首尾照样接得上），循环音用。"""
    n = len(x)
    f = np.fft.rfftfreq(n, 1 / SR)
    return np.stack([np.fft.irfft(np.fft.rfft(x[:, c]) * shape(f), n) for c in range(x.shape[1])], axis=1)


def breach_strain_el(rng):
    """挤压：取 hull_groan_v0（一段强度平稳的连续吱嘎）中间 3.8 秒，回放速度从 1 倍慢慢加到 1.45 倍（越绷越紧、音调往上走），
    音量从 -12 dB 推到 0；最后半秒叠上合成的裂缝滋水（breach_strain 的那一层）。2.65 秒，和 breach.gd 的 STRAIN 对齐。"""
    src = _el("hull_groan_v0")[int(0.4 * SR):int(4.2 * SR)]
    dur = 2.65
    n = int(dur * SR)
    t = taxis(n)
    k = t / dur
    rate = 1.0 + 0.45 * k ** 1.6
    pos = np.cumsum(rate) - rate[0]
    pos = np.minimum(pos, len(src) - 2)
    y = np.stack([np.interp(pos, np.arange(len(src)), src[:, c]) for c in range(2)], axis=1)
    y *= db(-12 + 12 * k ** 1.3)[:, None]
    y = unit(y)
    hs = int(2.05 * SR)
    m = n - hs
    tm = taxis(m)
    hiss = noise(m, lambda f: bp(f, 1800, 12000, 2), rng) * np.clip(1 + 0.4 * wobble(m, 10, 40, rng), 0, None)
    hiss = unit(hiss) * (tm / tm[-1]) ** 1.5 * 0.35
    y[hs:] += hiss[:, None]
    return fade(y, 0.002, 0.05)


def creature_ram_el(rng):
    """外面那东西撞艇：creature_ram_v0（闷重的一下，整条艇嗡）、v1（更低更沉）两个变体，轮流用。"""
    return fade(_el(f"creature_ram_v{_VARIANT}"), 0.0, 0.4)


def claw_scrape_el(rng):
    """爪子从外面刮过艇壳：claw_scrape_v1（起得快的那条）。"""
    return fade(_el("claw_scrape_v1"), 0.01, 0.3)


def claw_pierce_el(rng):
    """骨刺扎穿、顺着艇壳锯开：claw_pierce_v2（一开头就是扎穿的那一下，对得上画面）。"""
    return fade(_el("claw_pierce_v2"), 0.0, 0.5)


def breach_burst_el(rng):
    """崩开：breach_burst_v2（一串从低频直冲到七八千赫的金属冲击，后面拖着长长的低频余震）。"""
    return fade(_el("breach_burst_v2"), 0.0, 0.8)


def breach_jet_el(rng):
    """水柱（循环）：breach_jet_v1。原始的太亮（七成能量在 4 kHz 以上，像喷雾），压掉一点高频、补一点低频的轰。"""
    x = _el("breach_jet_v1")
    return _cfilt(x, lambda f: tilt(f, -2.0, 2000) * (1 + 1.5 * bp(f, 40, 300, 2)))


def flood_churn_el(rng):
    """翻腾的水（循环）：flood_churn_v0，最平稳、频带最宽的一条。"""
    return _el("flood_churn_v0")


def underwater_roar_el(rng):
    """头在水里听到的（循环）：underwater_roar_v2，三条里最平稳的。"""
    return _el("underwater_roar_v2")


# ---------------------------------------------------------------------------- 冰井的声学（给上面这些冰井的声音烘焙回声）
# 一口直径 22 米、几百米深的竖井，井壁是冰（几乎全反射），和普通大厅的混响很不一样：
# - 颤动回声：声音在两边井壁之间来回弹。镜头站在走台上、离井壁不到两米，所以先是贴身那面墙 10 毫秒的回声，
#   然后对面那面墙每 128 毫秒（来回 44 米）一簇：118、128、138 毫秒（一维的镜像声源），一簇比一簇糊、一簇比一簇闷；
#   圆形的井壁还会把声音往井轴上聚（焦散），中间夹着一串 64 毫秒的弱一点的回声。
#   上下每 12 米一圈走台，格栅、托梁又散射回来一串 70 毫秒的回声。几串周期差一点点，叠起来是冰井特有的金属“嗡嗡”声
# - 低频的尾巴很长（几秒），高频散得快（冰面的细碎起伏、格栅散射、空气吸收）
# 烘焙出来的“_wet”文件只有回声（干声由游戏里的 3D 播放器放；RMS 和干声一样，比例在游戏里配）。
# 每一圈灯的电闸声更讲究：按 tools/bake_shaft_rir.py（pyroomacoustics）算的 RIR 一圈一圈卷出来，见 relay_ring。
SHAFT_R = 11.0
C_AIR = 343.0
_VARIANT = 0


def _shift(x, sec):
    """把一段声音往后挪 sec 秒（亚采样精度，频域相移）。"""
    n = len(x)
    f = np.fft.rfftfreq(n, 1 / SR)
    return np.fft.irfft(np.fft.rfft(x) * np.exp(-2j * np.pi * f * sec), n)


def _bands_decay(n, rng, rt_lo, rt_mid, rt_hi, onset=0.03):
    """三段频带各自按 RT60 衰减的噪声尾巴（低 < 250 Hz < 中 < 2.5 kHz < 高）。"""
    t = taxis(n)
    ramp = 1 - np.exp(-t / onset)
    y = np.zeros(n)
    for lo, hi, rt in [(None, 250, rt_lo), (250, 2500, rt_mid), (2500, None, rt_hi)]:
        y += filt(rng.standard_normal(n), lambda f, lo=lo, hi=hi: bp(f, lo, hi, 3)) * np.exp(-6.9 * t / rt)
    return y * ramp


def shaft_ir(rng, dur=5.0, listener=1.75):
    """镜头那个位置（离井壁 listener 米）的冰井冲激响应，立体声，不含直达声。"""
    n = int(dur * SR)
    out = []
    for ch in range(2):
        y = np.zeros(n)
        def tap(at, amp, blur_ms, lp):
            # 一次反射：一小段按 blur_ms 摊开的脉冲（能量归一：amp² 就是这次反射的能量占比）
            w = max(4, int(blur_ms * SR / 1000))
            h = filt(np.hanning(w) * (1 + 0.6 * rng.standard_normal(w)), lambda f: bp(f, 60, lp, 2))
            place(y, amp * h / np.sqrt(np.sum(h ** 2)), int(at * SR))
        # 贴身那面墙
        tap(2 * listener / C_AIR + rng.uniform(-3e-4, 3e-4), 0.55, 1.5, 9000)
        L = 2 * SHAFT_R
        for k in range(1, 40):
            loss = db(-1.6 * k)           # 每来回一趟：冰面散射、格栅、托梁、栏杆挡掉一些
            lp = 9000 / (1 + 0.45 * k)     # 一趟比一趟闷
            blur = 1.5 + 2.2 * k           # 一簇比一簇糊（井壁不是正圆、表面有起伏）
            for img, a in [(2 * k * L - 2 * listener, 0.8), (2 * k * L, 1.0), (2 * k * L + 2 * listener, 0.7)]:
                at = img / C_AIR + rng.uniform(-6e-4, 6e-4) * k
                if at < dur - 0.1:
                    tap(at, 0.5 * a * loss, blur, lp)
            # 往井轴聚的那一串（每 64 毫秒，弱一点）
            at = (2 * k - 1) * L / C_AIR + rng.uniform(-8e-4, 8e-4) * k
            if at < dur - 0.1:
                tap(at, 0.22 * loss, blur * 1.3, lp * 0.8)
        # 上下一圈圈走台散射回来的（每 70 毫秒，越远越弱，糊）
        for k in range(1, 30):
            at = 2 * 12.0 * k / C_AIR * rng.uniform(0.98, 1.02)
            if at < dur - 0.1:
                tap(at, 0.18 * db(-2.2 * k), 6 + 3 * k, 5000 / (1 + 0.3 * k))
        tail = _bands_decay(n, rng, 6.0, 3.2, 1.1, onset=0.12)
        y += tail / np.sqrt(np.sum(tail ** 2)) * 0.8   # 扩散的尾巴，能量和前面那串回声差不多
        out.append(y)
    return np.stack(out, axis=1)


def _dry(fn, base):
    """按 base 的名字重新合成一遍干声（和 assets/audio/ 里那个文件一模一样，归一到 -3 dBFS）。"""
    name = f"{base}_{_VARIANT}"
    return finish(fn(np.random.default_rng(zlib.crc32(name.encode()))), False)


def wet_of(fn, base, gain_db=0.0):
    """base 的第 _VARIANT 个变体在冰井里的回声（不含干声）。"""
    def make(rng):
        x = _dry(fn, base)
        if x.ndim == 2:
            x = x.mean(axis=1)
        ir = shaft_ir(rng)
        y = np.stack([fftconv(x, ir[:, c]) for c in range(2)], axis=1)
        # 回声的电平：RMS 和干声一样（只算干声那么长的一段），游戏里再按距离配比
        return y * (rms(x) / rms(y[: len(x)])) * db(gain_db)
    return make


# ---------------------------------------------------------------------------- 每一圈的电闸声（按 pyroomacoustics 算的 RIR）
SHAFT_RIR = OUT.parent.parent / ".tmp" / "shaft_rir.npz"
_RING_GAIN = None


def _ring_raw(k):
    """第 k 圈的电闸声传到镜头：原声（三个变体轮着用）卷上这一圈到镜头的 RIR，去掉直达声之前的传播时间（游戏里另外延迟）。"""
    d = np.load(SHAFT_RIR)
    rir = d[f"rir_{k}"].astype(np.float64)
    dist = float(d[f"dist_{k}"])
    global _VARIANT
    keep = _VARIANT
    _VARIANT = k % 3
    x = _dry(relay_drop, "relay_drop").mean(axis=1)
    _VARIANT = keep
    y = np.stack([fftconv(x, rir[c]) for c in range(2)], axis=1)
    y = y[max(0, int((dist / C_AIR - 0.006) * SR)):]
    return fade(y[: int(7.0 * SR)], 0.0, 1.5)


def relay_ring(rng):
    """第 _VARIANT 圈（0 = 头顶那圈）的电闸声，从近到远同一套算法（tools/bake_shaft_rir.py）。
    各圈之间的响度差是算出来的（不各自归一化）：整套乘同一个增益，最响的那圈峰值 -3 dB。"""
    global _RING_GAIN
    if _RING_GAIN is None:
        n = len([k for k in np.load(SHAFT_RIR).files if k.startswith("rir_") and k[4:].isdigit()])
        _RING_GAIN = db(-3) / max(np.abs(_ring_raw(k)).max() for k in range(n))
    return _ring_raw(_VARIANT) * _RING_GAIN


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
    "door_wedge": (door_wedge, True, 1),
    "creak": (creak, False, 5),
    "pop": (pop, False, 3),
    "sonar_ping": (sonar_ping, False, 1),
    "drip": (drip, False, 6),
    "gear_tick": (gear_tick, False, 5),
    "door_strain": (door_strain, False, 2),
    "door_unlatch": (door_unlatch, False, 2),
    "door_seal": (door_seal, False, 2),
    "door_air": (door_air, False, 2),
    "door_slam": (door_slam, False, 2),
    "door_knock": (door_knock, False, 2),
    "door_latch": (door_latch, False, 2),
    "footstep_plate": (lambda r: footstep(r, "plate", "walk"), False, 10),
    "footstep_grate": (lambda r: footstep(r, "grate", "walk"), False, 10),
    "footstep_sill": (lambda r: footstep(r, "sill", "walk"), False, 4),
    "run_plate": (lambda r: footstep(r, "plate", "run"), False, 8),
    "run_grate": (lambda r: footstep(r, "grate", "run"), False, 8),
    "step_settle": (lambda r: footstep(r, "grate", "settle"), False, 4),
    "switch": (switch, False, 3),
    "hull_impact": (hull_impact, False, 3),
    # 巨物
    "giant_moan": (giant_moan, False, 4),
    "giant_swim": (giant_swim, True, 1),
    "giant_ram": (giant_ram, False, 2),
    # 岸上的房间
    "rain_window": (rain_window, True, 1),
    "rain_steel": (lambda r: rain_window(r, steel=True), True, 1),
    "fan_whir": (fan_whir, True, 1),
    "radio_static": (radio_static, True, 1),
    "harbor": (harbor, True, 1),
    "pager_beep": (pager_beep, False, 1),
    "knock": (knock, False, 2),
    "steps_away": (steps_away, False, 1),
    "envelope": (envelope, False, 1),
    "door_open": (lambda r: wood_door(r, True), False, 2),
    "door_close": (lambda r: wood_door(r, False), False, 2),
    "tube_start": (tube_start, False, 1),
    "paper": (paper, False, 4),
    "pen_write": (pen_write, False, 1),
    "ink_press": (lambda r: soft_press(r, True), False, 1),
    "thumb_press": (soft_press, False, 1),
    "clock_tick": (clock_tick, False, 2),
    "clock_tock": (lambda r: clock_tick(r, True), False, 2),
    "clock_stop": (clock_stop, False, 1),
    "thunder": (thunder, False, 3),
    "chair_creak": (chair_creak, False, 3),
    "wall_switch": (wall_switch, False, 2),
    "ship_horn": (ship_horn, False, 1),
    "step_concrete": (lambda r: concrete_step(r), False, 8),
    "run_concrete": (lambda r: concrete_step(r, gait="run"), False, 6),
    "settle_concrete": (lambda r: concrete_step(r, gait="settle"), False, 4),
    "step_terrazzo": (lambda r: terrazzo_step(r), False, 8),
    "run_terrazzo": (lambda r: terrazzo_step(r, "run"), False, 6),
    # 冰井（开场）
    "shaft_air": (shaft_air, True, 1),
    "shaft_hum": (shaft_hum, True, 1),
    "ice_boom": (ice_boom, False, 2),
    "relay_drop": (relay_drop, False, 3),
    "steel_groan": (steel_groan, False, 3),
    "spark_crackle": (spark_crackle, False, 2),
    "steam_burst": (steam_burst, False, 1),
    # 破舱（ElevenLabs 生成，见上面的 *_el；_synth 是原来合成的，对比用）
    "creature_ram": (creature_ram_el, False, 2),
    "claw_scrape": (claw_scrape_el, False, 1),
    "claw_pierce": (claw_pierce_el, False, 1),
    "breach_strain": (breach_strain_el, False, 1),
    "breach_burst": (breach_burst_el, False, 1),
    "breach_jet": (breach_jet_el, True, 1),
    "flood_churn": (flood_churn_el, True, 1),
    "underwater_roar": (underwater_roar_el, True, 1),
    "breach_strain_synth": (breach_strain, False, 1),
    "breach_burst_synth": (breach_burst, False, 1),
    "breach_jet_synth": (breach_jet, True, 1),
    "flood_churn_synth": (flood_churn, True, 1),
    "underwater_roar_synth": (underwater_roar, True, 1),
    # 冰井里的回声（KEEP_LEVEL：不归一化，保留和干声的比例）
    "ice_boom_wet": (wet_of(ice_boom, "ice_boom"), False, 2),
    "steel_groan_wet": (wet_of(steel_groan, "steel_groan"), False, 3),
    "spark_crackle_wet": (wet_of(spark_crackle, "spark_crackle"), False, 2),
    "steam_burst_wet": (wet_of(steam_burst, "steam_burst"), False, 1),
    # 每一圈的电闸声（要先跑 tools/bake_shaft_rir.py 算 RIR）
    "relay_ring": (relay_ring, False, 51),
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
    （tools/record.py 录出来、audio_report.py 查得到）。把导入设置改成不压缩的 PCM；还没导入过就写一个只有参数的
    .import，Godot 导入时会补全其余字段。"""
    imp = path.with_name(path.name + ".import")
    if imp.exists():
        text = imp.read_text(encoding="utf-8")
        new = re.sub(r"compress/mode=\d+", "compress/mode=0", text)
        if new != text:
            imp.write_text(new, encoding="utf-8", newline="\n")
    else:
        imp.write_text('[remap]\n\nimporter="wav"\ntype="AudioStreamWAV"\n\n[params]\n\ncompress/mode=0\n', encoding="utf-8", newline="\n")


KEEP_LEVEL = ("_wet", "relay_ring")


def finish(x, loop, keep=False):
    x = np.asarray(x, dtype=np.float64)
    assert np.all(np.isfinite(x))
    if keep:
        x = fade(filt(x, lambda f: bp(f, 18, None, 2)) if x.ndim == 1 else
                 np.stack([filt(x[:, c], lambda f: bp(f, 18, None, 2)) for c in range(x.shape[1])], axis=1),
                 0.0003, len(x) / SR * 0.05)
        peak = np.abs(x).max()
        if peak > db(-1):
            print(f"  （电平太高 {20 * np.log10(peak):.1f} dB，压到 -1 dB；和干声的比例变了）")
            x *= db(-1) / peak
        return np.concatenate([x, np.zeros((int(0.05 * SR),) + x.shape[1:])])
    if loop:
        x = x * (db(-20) / rms(x))
        if np.abs(x).max() > db(-1):
            x *= db(-1) / np.abs(x).max()
    else:
        # 去掉直流和次声（零相位高通），开头 0.3 ms、结尾 5% 渐变，首尾都落在 0 上，播放器起停时不咔哒
        hp = lambda v: filt(v, lambda f: bp(f, 18, None, 2))
        x = hp(x) if x.ndim == 1 else np.stack([hp(x[:, c]) for c in range(x.shape[1])], axis=1)
        x = fade(x, 0.0003, len(x) / SR * 0.05)
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
            global _VARIANT
            _VARIANT = k
            fname = name if count == 1 else f"{name}_{k}"
            rng = np.random.default_rng(zlib.crc32(fname.encode()))
            x = finish(fn(rng), loop, any(m in name for m in KEEP_LEVEL))
            write_wav(OUT / f"{fname}.wav", x, loop)
            if loop:
                import_pcm(OUT / f"{fname}.wav")
            note = f"循环，接缝 {seam(x):.2f}" if loop else ""
            print(f"{fname:<20}{len(x) / SR:6.2f}{x.ndim if x.ndim == 1 else x.shape[1]:>4}"
                  f"{20 * np.log10(np.abs(x).max()):8.1f}{20 * np.log10(rms(x)):8.1f}  {note}")


if __name__ == "__main__":
    main()
