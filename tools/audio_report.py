#!/usr/bin/env python3
"""检查一段音频（tools/record.sh 录的游戏声音，或 assets/audio/ 里的单个音效），不用耳朵也能发现的问题：
  - 响度：峰值、削波采样数、整体 RMS；ffmpeg ebur128 的综合响度（LUFS）和真峰值
  - 响度时间线：每 0.5 秒一格的 RMS（dBFS），看有没有突然炸响或者突然没声
  - 咔哒声：单个采样上的突变（循环接缝没接好、播放器突然开停、缓冲断了都会这样），列出时间
  - 事件对齐（给了 --log 时）：游戏里每触发一个音效打一行 `SFX <帧号> <名字>`，
    在录音里找它后面最近的起音，报告延迟；找不到起音的标出来
  - 频谱图（给了 --png 时）：ffmpeg showspectrumpic，对数频率轴
用法: tools/audio_report.py 录音.wav [--log 游戏输出.log] [--png 频谱.png] [--fps 60]
"""
import argparse
import re
import subprocess
import sys
import wave

import numpy as np


def load(path):
    with wave.open(path) as w:
        sr, ch, n = w.getframerate(), w.getnchannels(), w.getnframes()
        x = np.frombuffer(w.readframes(n), "<i2").astype(np.float64) / 32768.0
    return sr, x.reshape(-1, ch)


def dbfs(v):
    return 20 * np.log10(max(v, 1e-9))


def ebur128(path):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-af", "ebur128=peak=true",
                        "-f", "null", "-"], capture_output=True, text=True)
    tail = r.stderr[r.stderr.rfind("Summary:"):]
    get = lambda key: (re.search(key + r":\s+(-?[\d.]+|-inf)", tail) or [None, "nan"])[1]
    return get("I"), get("LRA"), get("Peak")


def timeline(mono, sr, step=0.5):
    k = int(step * sr)
    m = len(mono) // k
    return [dbfs(np.sqrt(np.mean(mono[i * k:(i + 1) * k] ** 2))) for i in range(m)]


def clicks(mono, sr, skip=()):
    """咔哒声：二阶差分突然比周围的局部能量大很多，而且是孤立的一下——前后 60 ms 里没有差不多大的尖峰
    （电流嗡声、齿轮连响这种本来就一下一下尖的声音，尖峰是成串重复的，不算）。
    skip 里的时间点（已知音效的起音）前后 30 ms 不算。"""
    e = np.abs(np.diff(mono, 2))
    w = 512
    local = np.sqrt(np.convolve(e ** 2, np.ones(w) / w, mode="same")) + 1e-6
    hits = np.nonzero((e > 10 * local) & (e > 2e-4))[0]
    near, far = int(0.003 * sr), int(0.06 * sr)
    out = []
    for i in hits:
        t = (i + 1) / sr
        if any(abs(t - s) < 0.03 for s in skip):
            continue
        around = np.concatenate([e[max(0, i - far):max(0, i - near)], e[i + near:i + far]])
        if around.size and around.max() >= 0.5 * e[i]:
            continue
        if not out or t - out[-1][0] > 0.05:
            out.append((t, dbfs(e[i])))
    return out


def onsets(mono, sr):
    """起音检测：每个频点和「窗口不重叠的前 4 帧」里的最大值比，突然高出多少 dB；取上升最多的 8 个频点平均
    （单看总能量的话，持续的噪声底子起伏会把一个纯音、一声水滴的起音淹没）。阈值按周围 2 秒自适应。
    返回 (时间, 强度：比阈值高几 dB)。"""
    n, hop = 1024, 256
    lag = n // hop  # 前这么多帧和当前帧的窗口有重叠，跳过
    frames = (len(mono) - n) // hop
    idx = np.arange(n)[None, :] + hop * np.arange(frames)[:, None]
    f = np.fft.rfftfreq(n, 1 / sr)
    band = (f > 150) & (f < 12000)
    S = 20 * np.log10(np.abs(np.fft.rfft(mono[idx] * np.hanning(n), axis=1))[:, band] + 1e-9)
    ref = np.full_like(S, 200.0)
    ref[lag + 4:] = -200.0
    for k in range(lag, lag + 4):
        ref[lag + 4:] = np.maximum(ref[lag + 4:], S[lag + 4 - k:len(S) - k])
    o = np.sort(np.clip(S - ref, 0, 60), axis=1)[:, -8:].mean(axis=1)
    w = int(2 * sr / hop)
    pad = np.pad(o, (w // 2, w - w // 2 - 1), mode="edge")
    win = np.lib.stride_tricks.sliding_window_view(pad, w)
    thr = np.percentile(win, 98, axis=1) + 2.0
    out = []
    for i in range(lag + 4, len(o) - lag):
        if o[i] > thr[i] and o[i] == o[i - lag:i + lag + 1].max():
            out.append((i * hop / sr + n / 2 / sr, o[i] - thr[i]))
    return out


def presence(mono, sr, t, dur=0.4, others=()):
    """显著度：事件后 dur 秒的频谱（窗口在事件后 0~2.4 秒里滑动取最大）和事件前 0.8 秒比，最突出的 8 个频点平均高出多少 dB（减掉整体的变化）。
    慢慢涨起来的声音（吱嘎）没有尖锐的起音，用这个判断它到底听不听得见。
    没有事件的时刻量出来是 3~4 dB（噪声底子自己的起伏），< 6 dB 基本就是被盖住了。"""
    def psd(a, b):
        seg = mono[max(0, int(a * sr)):int(b * sr)]
        n = 2048
        if len(seg) < n:
            return None
        k = (len(seg) - n) // 512 + 1
        idx = np.arange(n)[None, :] + 512 * np.arange(k)[:, None]
        return 10 * np.log10(np.mean(np.abs(np.fft.rfft(seg[idx] * np.hanning(n), axis=1)) ** 2, axis=0) + 1e-18)
    before = psd(t - 0.85, t - 0.05)
    if before is None:
        return float("nan")
    f = np.fft.rfftfreq(2048, 1 / sr)
    best = float("nan")
    # 慢慢涨起来的声音（吱嘎）要一两秒才到最响：事件后的窗口往后滑，取最显著的那一段
    # 碰到下一个事件就不再往后滑（不然量到的是别的声音）
    stop = min([o for o in others if o > t + 0.02], default=t + 99)
    for off in np.arange(0.0, 2.41, 0.4):
        if off > 0 and t + off + dur > stop:
            break
        after = psd(t + off, t + off + dur)
        if after is None:
            break
        d = (after - before)[(f > 60) & (f < 12000)]
        v = float(np.sort(d)[-8:].mean() - np.median(d))
        best = v if not best >= v else best
    return best


def read_log(path, fps):
    ev = []
    for line in open(path, errors="replace"):
        m = re.match(r"(SFX|LOOP) (\d+) (\S+)", line.strip())
        if m:
            ev.append((int(m[2]) / fps, m[3], m[1] == "LOOP"))
    return ev


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("wav")
    ap.add_argument("--log")
    ap.add_argument("--png")
    ap.add_argument("--fps", type=float, default=60.0)
    a = ap.parse_args()

    sr, x = load(a.wav)
    mono = x.mean(axis=1)
    peak = np.abs(x).max(axis=0)
    clip = int((np.abs(x) >= 0.999).sum())
    print(f"{a.wav}: {len(x) / sr:.2f} 秒, {x.shape[1]} 声道, {sr} Hz")
    print("峰值 dBFS: " + " / ".join(f"{dbfs(p):.1f}" for p in peak) + f"   削波采样: {clip}   RMS: {dbfs(np.sqrt(np.mean(x ** 2))):.1f} dBFS")
    if x.shape[1] == 2:
        l, r = (np.sqrt(np.mean(x[:, c] ** 2)) for c in (0, 1))
        corr = np.corrcoef(x[:, 0], x[:, 1])[0, 1] if l > 1e-6 and r > 1e-6 else float("nan")
        print(f"左右 RMS 差: {dbfs(l) - dbfs(r):+.1f} dB   左右相关: {corr:.2f}")
    i, lra, tp = ebur128(a.wav)
    print(f"综合响度: {i} LUFS   响度范围: {lra} LU   真峰值: {tp} dBFS")
    tl = timeline(mono, sr)
    print("每 0.5 秒 RMS (dBFS):")
    for k in range(0, len(tl), 20):
        print(f"  {k * 0.5:6.1f}s " + " ".join(f"{v:4.0f}" for v in tl[k:k + 20]))

    ons = onsets(mono, sr)
    log = read_log(a.log, a.fps) if a.log else []
    events = [(t, n) for t, n, loop in log if not loop]
    loops = [(t, n) for t, n, loop in log if loop]
    if events:
        print(f"事件对齐（{len(events)} 个事件；起音在事件后 -20~+150 ms 内算对上）:")
        # 同一种声音间隔不到 0.15 秒的连发（手轮齿轮咔哒）合成一串，只报第一下，显著度是整串和串前比
        trains, shown = {}, []
        for t, name in events:
            if shown and shown[-1][1] == name and t - trains[shown[-1]][-1] < 0.15:
                trains[shown[-1]].append(t)
            else:
                shown.append((t, name))
                trains[(t, name)] = [t]
        bad = 0
        for t, name in shown:
            k = trains[(t, name)]
            if len(k) > 1:
                pr = presence(mono, sr, t, dur=min(0.4, k[-1] - t + 0.05), others=[o for o, _ in shown])
                tag = "" if pr >= 6 else "  ** 几乎听不出来 **"
                print(f"  {t:7.2f}s {name:<16} 连发 {len(k)} 下，到 {k[-1]:.2f}s   显著度 {pr:5.1f} dB{tag}")
                continue
            cand = [(o - t, s) for o, s in ons if -0.02 <= o - t <= 0.15]
            pr = presence(mono, sr, t, others=[o for o, _ in shown])
            tag = "" if pr >= 6 else "  ** 几乎听不出来 **"
            if cand:
                lag, s = min(cand, key=lambda c: abs(c[0]))
                print(f"  {t:7.2f}s {name:<16} 起音 {lag * 1000:+5.0f} ms  显著度 {pr:5.1f} dB{tag}")
            else:
                bad += 1
                print(f"  {t:7.2f}s {name:<16} 没有尖锐起音   显著度 {pr:5.1f} dB{tag}")
        single = sum(1 for e in shown if len(trains[e]) == 1)
        print(f"  有尖锐起音的 {single - bad} / {single}（连发不算；起音时间精度约 ±15 ms）")
    # 日志里的音效事件附近本来就有冲击声，不算咔哒（没日志就全都算）
    cl = clicks(mono, sr, skip=[t + d for t, _ in events for d in (0.0, 0.05, 0.1)])
    print(f"疑似咔哒声: {len(cl)} 处" + ("" if not cl else "  " + ", ".join(f"{t:.3f}s" for t, _ in cl[:20])))
    for t, _ in cl:
        near = [f"{n} ({(t - lt) * 1000:+.0f} ms)" for lt, n in loops if -0.02 < t - lt < 0.1]
        if near:
            print(f"  {t:.3f}s 附近有循环音起停: " + ", ".join(near))
    if loops:
        print("循环音起停: " + ", ".join(f"{t:.2f}s {n}" for t, n in loops))

    if a.png:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", a.wav, "-lavfi",
                        "showspectrumpic=s=1400x480:legend=1:fscale=log:scale=log:color=intensity:mode=combined",
                        a.png], check=True)
        print("频谱图: " + a.png)


if __name__ == "__main__":
    sys.exit(main())
