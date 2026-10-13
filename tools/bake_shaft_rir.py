#!/usr/bin/env python3
"""用 pyroomacoustics 算冰井里每一圈灯的接线箱到镜头的房间冲激响应（RIR），给 tools/gen_sfx.py 烘焙 relay_ring_*。

开场镜头（scripts/intro/shaft_blackout.gd）里灯一圈圈往下灭，每圈接线箱的电闸“咔嚓”一声。以前远近分成几档、
近处实时放原声、远处放另算的版本，档与档之间音色一跳一跳的。这里把整口井按真实尺寸建成一个房间，
给 51 圈每一圈都算一条到镜头耳朵的 RIR：近的、远的同一套算法，从近到远连续变化。
- 井：32 边形的柱子，半径 11 米，从镜头上方 40 米一直到下面 640 米（坐标和游戏里一样：井轴是 Y，镜头那圈走台 y = 0）
- 井壁：冰几乎全反射，但走台、栏杆、管子、桥架每 12 米一圈挡着，散射很强、高频损失大一点
- 上下两头：井其实还往上往下通很远，按几乎全吸收算（声音走掉了，不回来）
- 空气：零下十几度、湿度不高（高频吸收按 ISO 9613 算，pyroomacoustics 自带）
- 镜头：两个全向话筒，左右相距 0.3 米（立体声）
- 镜像声源法（低阶，算清楚头几次反射）+ 声线追踪（后面的混响），两者拼起来
结果存到 .tmp/shaft_rir.npz（不进 git；120 MB 左右）。要重算：
    python tools/bake_shaft_rir.py            （全部 51 圈，十几分钟）
    python tools/bake_shaft_rir.py --rings 0,1,10,40 --rays 2000   （试参数）
    python tools/bake_shaft_rir.py --at land:10.2,4.49,0.2         （另算一个点：冰块落在镜头对面的走台上）
"""
import argparse
import time
from pathlib import Path

import numpy as np
import pyroomacoustics as pra

SR = 48000
R = 11.0
RING_STEP = 12.0
RING_FIRST, RING_LAST = -1, 49
JBOX_ANGLE = 3.66
CAM_A = 1.35
CAM_R = 9.05           # 扶着栏杆往外探的位置（9.3 再往井里探一点）
CAM_Y = 1.45
RX = 1.0             # 声线追踪的接收球半径（大一点，远处来的声线才接得到足够多）
Y_TOP, Y_BOTTOM = 40.0, -640.0
OUT = Path(__file__).resolve().parent.parent / ".tmp" / "shaft_rir.npz"
BANDS = [125, 250, 500, 1000, 2000, 4000]


def to_room(p):
    """游戏坐标（Y 朝上）→ pyroomacoustics 坐标（Z 朝上、全为正）。"""
    x, y, z = p
    return [x + R + 1.0, z + R + 1.0, y - Y_BOTTOM]


def pol(r, a, y):
    return (r * np.cos(a), y, r * np.sin(a))


def build(rays):
    n = 32
    ang = np.arange(n) * 2 * np.pi / n
    corners = np.array([np.cos(ang) * R + R + 1.0, np.sin(ang) * R + R + 1.0])
    ice = pra.Material(energy_absorption={"coeffs": [0.04, 0.05, 0.06, 0.08, 0.11, 0.15], "center_freqs": BANDS},
                       scattering={"coeffs": [0.2, 0.3, 0.4, 0.5, 0.6, 0.6], "center_freqs": BANDS})
    gone = pra.Material(energy_absorption=0.97, scattering=0.1)
    room = pra.Room.from_corners(corners, fs=SR, materials=ice, max_order=3, ray_tracing=True,
                                 air_absorption=True, temperature=-15.0, humidity=50.0)
    room.extrude(Y_TOP - Y_BOTTOM, materials={"floor": gone, "ceiling": gone})
    room.set_ray_tracing(n_rays=rays, receiver_radius=RX, energy_thres=1e-12, time_thres=8.0, hist_bin_size=0.004)
    # 两个话筒：沿切向左右各 0.15 米（面朝井里看，左手边是方位角增大的方向）
    tang = np.array([-np.sin(CAM_A), 0.0, np.cos(CAM_A)])
    c = np.array(pol(CAM_R, CAM_A, CAM_Y))
    mics = np.array([to_room(c - tang * 0.15), to_room(c + tang * 0.15)]).T
    room.add_microphone_array(mics)
    return room


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rings", default="", help="只算这几圈（序号 0 = 头顶那圈），逗号分隔")
    ap.add_argument("--rays", type=int, default=50000)
    ap.add_argument("--at", action="append", default=[],
                    help="另外算一个点：名字:r,方位,y（游戏坐标的极坐标），存成 rir_<名字>；给了 --at 就不算各圈")
    a = ap.parse_args()
    ks = [int(k) for k in a.rings.split(",")] if a.rings else ([] if a.at else list(range(RING_LAST - RING_FIRST + 1)))
    points = {}
    for spec in a.at:
        name, v = spec.split(":")
        r, ang, y = (float(t) for t in v.split(","))
        points[name] = np.array(pol(r, ang, y))
    cam = np.array(pol(CAM_R, CAM_A, CAM_Y))
    rirs, dists = {}, {}
    todo = [(k, np.array(pol(R - 0.25, JBOX_ANGLE, -(k + RING_FIRST) * RING_STEP + 1.3))) for k in ks] + list(points.items())
    for k, src in todo:
        y = src[1]
        t0 = time.time()
        room = build(a.rays)
        room.add_source(to_room(src))
        room.compute_rir()
        h = [np.asarray(room.rir[m][0], dtype=np.float32) for m in range(2)]
        L = min(len(h[0]), len(h[1]))
        rirs[k] = np.stack([h[0][:L], h[1][:L]])
        dists[k] = float(np.linalg.norm(src - cam))
        print(f"{k!s:>8}  y={y:7.1f}  距离 {dists[k]:6.1f} 米  长 {L / SR:5.2f} 秒  峰值 {np.abs(rirs[k]).max():.4f}  "
              f"用时 {time.time() - t0:5.1f} 秒", flush=True)
    OUT.parent.mkdir(exist_ok=True)
    old = dict(np.load(OUT, allow_pickle=True)) if OUT.exists() and (a.rings or a.at) else {}
    for k, _ in todo:
        old[f"rir_{k}"] = rirs[k]
        old[f"dist_{k}"] = np.float32(dists[k])
    np.savez(OUT, **old)
    print(f"存到 {OUT}")


if __name__ == "__main__":
    main()
