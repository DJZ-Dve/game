#!/usr/bin/env python3
"""巨物「闷雷」材质用的两张可平铺辅助贴图（第二版：主要细节在烘焙贴图里，这两张只补「大尺度颜色」和「近看的细颗粒」）。

1. assets/textures/giant_noise.png（512x512 RGBA，数据图，线性导入）——颜色变化用，着色器按 BodyST 换算成米来铺：
     R：大块斑驳（一张图 3 个起伏）            G：另一张独立的斑驳（一张图 5 个起伏）
     B：零星的深色斑点（软边小圆斑，0 = 没有、1 = 斑心；一张图约 70 个，大小不一）
     A：细的颜色颗粒（一张图 24 个起伏）
   R、G、A 均值 0.5、标准差约 0.11（和第一版一样，阈值好调）。
2. 两张 1024x1024 的可平铺细节法线（切线空间，OpenGL Y+，按法线贴图导入 = BC5 只存 XY，又小又快）：
     assets/textures/giant_denticle_n.png：盾鳞（一个个往同一方向搭着的小鳞片，每片三道纵棱；一张图 40×40 片左右），皮和鳍用
     assets/textures/giant_tissue_n.png：软组织的细沟和小孔（各向同性的脊状噪声），嘴里、眼球、寄生虫用

做法：都是在环面上（周期边界）生成，天然可平铺。固定种子，每次生成一样。
用法：python tools/gen_giant_noise.py            生成两张图（并同步下面的米数）
      python tools/gen_giant_noise.py --sync     只同步：把 assets/textures/giant/<组>.json 的 meters 写进
                                                  assets/materials/M_Giant*.tres 的 atlas_meters（重新排图集 / 烘焙以后跑一次）
"""
import json
import os
import re
import sys

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets", "textures")


def band_noise(rng, n, freqs, std=0.11):
    """频域滤波的周期噪声：每个主频一个高斯环（第二个往后振幅 ×0.45）。"""
    white = rng.standard_normal((n, n))
    f = np.fft.fft2(white)
    kx = np.fft.fftfreq(n) * n
    k = np.sqrt(kx[None, :] ** 2 + kx[:, None] ** 2)
    amp = np.zeros_like(k)
    for o, fc in enumerate(freqs):
        amp += 0.45 ** o * np.exp(-((k - fc) / (fc * 0.35)) ** 2)
    amp[0, 0] = 0.0
    img = np.real(np.fft.ifft2(f * amp))
    return (img - img.mean()) / img.std() * std + 0.5


def wrap_dist(n, cx, cy):
    """周期边界下每个像素到 (cx, cy)（像素）的 dx、dy。"""
    y, x = np.mgrid[0:n, 0:n].astype(np.float32)
    dx = (x - cx + n / 2) % n - n / 2
    dy = (y - cy + n / 2) % n - n / 2
    return dx, dy


def spots(rng, n, count):
    out = np.zeros((n, n), np.float32)
    warp = band_noise(rng, n, [24.0], std=1.0)
    for _ in range(count):
        cx, cy = rng.uniform(0, n, 2)
        r = rng.uniform(4.0, 10.0) * (1.8 if rng.uniform() < 0.15 else 1.0)
        dx, dy = wrap_dist(n, cx, cy)
        a = rng.uniform(0, np.pi)
        ax = dx * np.cos(a) + dy * np.sin(a)
        ay = -dx * np.sin(a) + dy * np.cos(a)
        d = np.sqrt((ax / 1.0) ** 2 + (ay / rng.uniform(0.6, 1.0)) ** 2) / r
        d = d + (warp - 0.0) * 0.12
        v = np.clip(1.0 - d, 0.0, 1.0)
        v = v * v * (3 - 2 * v)
        out = np.maximum(out, v * rng.uniform(0.6, 1.0))
    return out


def normal_xy(h, strength):
    """高度（像素单位）→ 切线空间法线 XY（OpenGL：Y+ 朝图像上方 = 行号减小的方向）。"""
    gx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * 0.5
    gy = (np.roll(h, 1, 0) - np.roll(h, -1, 0)) * 0.5   # 往上（行号减小）为正
    nx, ny, nz = -gx * strength, -gy * strength, np.ones_like(h)
    ln = np.sqrt(nx * nx + ny * ny + nz * nz)
    return nx / ln, ny / ln


def denticles(rng, n, cells):
    """盾鳞：抖动网格上的小鳞片，往 +Y（图像上方）搭，后一片压着前一片（取最大），每片三道纵棱、后缘有个尖。"""
    h = np.zeros((n, n), np.float32)
    cs = n / cells
    y, x = np.mgrid[0:n, 0:n].astype(np.float32)
    # 按行从下往上画（图像下方先画），上面的鳞片压住下面的鳞尖
    for j in range(cells):
        for i in range(cells):
            # 不规则：位置抖得多、大小不一（排成整齐的行远看像织物）
            ox = (i + 0.5 * (j % 2) + rng.uniform(-0.45, 0.45)) * cs
            oy = n - (j + rng.uniform(-0.4, 0.4)) * cs
            sz = cs * rng.uniform(0.5, 0.85)
            x0, x1 = int(ox - sz * 1.4), int(ox + sz * 1.4) + 1
            y0, y1 = int(oy - sz * 1.8), int(oy + sz * 1.2) + 1
            xs = np.arange(x0, x1) % n
            ys = np.arange(y0, y1) % n
            lx = (np.arange(x0, x1)[None, :] - ox) / sz
            ly = (oy - np.arange(y0, y1)[:, None]) / sz     # 往上为正（朝鳞尖）
            # 泪滴形：前圆后尖
            w = 1.0 - np.clip(ly, -1.0, 1.4) * 0.35
            d = np.sqrt((lx / np.maximum(w, 0.2)) ** 2 + ((ly - 0.1) / 1.25) ** 2)
            dome = np.clip(1.0 - d * d, 0.0, 1.0)
            # 往鳞尖方向抬起（鳞片斜着搭）
            dome *= 0.55 + 0.45 * np.clip(ly * 0.6 + 0.5, 0.0, 1.0)
            ridges = 1.0 - 0.28 * np.abs(np.sin(lx * np.pi * 1.5)) * np.clip(ly + 0.6, 0.0, 1.0)
            hh = dome * ridges * rng.uniform(0.8, 1.0)
            sub = h[np.ix_(ys, xs)]
            h[np.ix_(ys, xs)] = np.maximum(sub, hh)
    h += (band_noise(rng, n, [96.0], std=1.0)) * 0.03
    return h


def wrinkles(rng, n):
    """软组织：脊状噪声的细沟（黏膜的褶）+ 小孔。"""
    h = np.zeros((n, n), np.float32)
    for fc, amp in ((7.0, 1.0), (16.0, 0.6), (36.0, 0.3)):
        w = band_noise(rng, n, [fc], std=1.0)
        h -= np.exp(-np.abs(w) * 3.0) * amp      # 噪声过零处是一道窄沟
    h += band_noise(rng, n, [60.0, 120.0], std=1.0) * 0.12
    # 小孔
    pores = np.zeros((n, n), np.float32)
    for _ in range(900):
        cx, cy = rng.uniform(0, n, 2)
        r = rng.uniform(1.5, 3.5)
        dx, dy = wrap_dist(n, cx, cy)
        sl = (np.abs(dx) < r * 2) & (np.abs(dy) < r * 2)
        d = np.sqrt(dx[sl] ** 2 + dy[sl] ** 2) / r
        pores[sl] = np.minimum(pores[sl], -np.clip(1.0 - d * d, 0, 1))
    h += pores * 1.2
    return h


# 材质 → 贴图组（同 blender/scripts/giant/spec.py 的 MATERIAL_TEXSET）
MATERIAL_TEXSET = {"M_GiantSkin": "skin", "M_GiantFin": "fins", "M_GiantMouth": "mouth", "M_GiantTooth": "mouth",
                   "M_GiantEye": "eyes"}


def sync_meters():
    for mat, grp in MATERIAL_TEXSET.items():
        js = os.path.join(OUT, "giant", grp + ".json")
        tres = os.path.join(ROOT, "assets", "materials", mat + ".tres")
        if not (os.path.exists(js) and os.path.exists(tres)):
            continue
        meters = json.load(open(js, encoding="utf-8"))["meters"]
        s = open(tres, encoding="utf-8").read()
        s2 = re.sub(r"shader_parameter/atlas_meters = [0-9.]+", "shader_parameter/atlas_meters = %s" % meters, s)
        if s2 != s:
            open(tres, "w", encoding="utf-8", newline="\n").write(s2)
            print("%s: atlas_meters = %s" % (mat, meters))


def main():
    if "--sync" in sys.argv:
        sync_meters()
        return
    rng = np.random.default_rng(1998)
    n = 512
    r = band_noise(rng, n, [3.0, 6.0])
    g = band_noise(rng, n, [5.0, 10.0])
    b = spots(rng, n, 70)
    a = band_noise(rng, n, [24.0, 48.0])
    arr = (np.clip(np.stack([r, g, b, a], -1), 0, 1) * 255 + 0.5).astype(np.uint8)
    Image.fromarray(arr).save(os.path.join(OUT, "giant_noise.png"))

    n = 1024
    hd = denticles(rng, n, 40)
    dx, dy = normal_xy(hd * 18.0, 1.0)
    hw = wrinkles(rng, n)
    wx, wy = normal_xy(hw * 3.0, 1.0)
    for name, (x, y) in (("giant_denticle_n.png", (dx, dy)), ("giant_tissue_n.png", (wx, wy))):
        z = np.sqrt(np.clip(1.0 - x * x - y * y, 0.0, 1.0))
        arr = (np.clip(np.stack([x, y, z], -1) * 0.5 + 0.5, 0, 1) * 255 + 0.5).astype(np.uint8)
        Image.fromarray(arr).save(os.path.join(OUT, name))
    sync_meters()
    print("ok")


if __name__ == "__main__":
    main()
