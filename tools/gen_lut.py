#!/usr/bin/env python3
"""岸上房间的调色 LUT（Environment.adjustment_color_correction 用的 3D 查找表），生成横条 PNG。

用法: python3 tools/gen_lut.py [名字 ...] [--size N] [--out 目录]
  例: python3 tools/gen_lut.py                      全部（identity、office、dorm）写到 assets/textures/lut/
      python3 tools/gen_lut.py identity --size 64   只出单位 LUT，64³（对比 LUT 管线有没有偏差用）
  名字: identity（单位 LUT：理论上和不挂 LUT 一模一样）、office、dorm，调色见下面的 GRADES
产出: <目录>/<名字>_lut.png：N 张 N×N 的切片从左往右排成一条（宽 N*N、高 N），第 k 张是蓝 = 第 k 格，
      切片里 x 是红、y 是绿。第一次生成后要写一份 .import（Texture3D，横切 N 片、无损、不要 mipmap），
      本脚本会顺手写好（已有的不覆盖）；然后跑一次 Godot --import。

Godot 4.7 怎么用这张表（tonemap 着色器，查过引擎源码）：
  - 色调映射（AgX）→ 转 sRGB → 亮度/对比/饱和度 → clamp 到 0~1 → textureLod(lut, color)。
    所以表的输入、输出都是 sRGB 编码后的显示值（就是截图里的 0~255 / 255）。
  - 采样不做半像素偏移：输入 c 落在第 c*N-0.5 格（格中心在 (i+0.5)/N），线性插值，出了两头就夹住。
    按常见做法 i/(N-1) 存的表会让中间调整体暗约 2 级（第一轮实测 -2.6）。
  所以第 i 格存 grade((i+0.5)/N)。两头特殊处理：
  - 第 0 格存 grade(0)（= 0）：纯黑还是 0，不被抬成灰/蓝；代价是 0.5/N 以下的最暗一点被压到 0
  - 第 N-1 格存 grade(1)：纯白还是白
  N=128 时两头最多差 0.5/128*255 ≈ 1 级；N=64 时最暗那几级会差到 2 级。实测（单位 LUT 对比不挂 LUT，同样机位）：
  128³ 差超过 1 级的像素只有 0.03~0.35%（是雨、体积雾每次运行的抖动），平均偏差 ±0.2 级；64³ 有 5~12%（暗部被压）。
  128³ 在显存里 8 MB（RGBA8），全屏只多一次 3D 采样，开销可以忽略。
"""
import argparse
import os

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets", "textures", "lut")


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def luma(c):
    """显示值的亮度（Rec.709 权重，在 sRGB 编码值上算：调色按人眼看到的明暗分段）"""
    return c[..., 0] * 0.2126 + c[..., 1] * 0.7152 + c[..., 2] * 0.0722


def saturation(c):
    mx = c.max(axis=-1)
    mn = c.min(axis=-1)
    return np.where(mx > 1e-5, (mx - mn) / np.maximum(mx, 1e-5), 0.0)


def split_tone(c, shadow, shadow_band, high, high_band, toe, keep_sat=0.0):
    """分离色调：暗部加 shadow（RGB 偏移），亮部加 high。
    shadow_band = (满, 开始退, 退完)：亮度到「满」时偏移加满，「开始退」到「退完」之间退掉。
    toe：从纯黑到 toe 这一段偏移从 0 慢慢加上去（纯黑保持 0，最暗的地方不突然变成蓝黑）。
    high_band = (开始, 满)。keep_sat：已经很饱和的颜色（钠灯的橙）少偏一点，0 不管、1 饱和的完全不偏。"""
    L = luma(c)[..., None]
    ws = smoothstep(0.0, toe, L) * (1.0 - smoothstep(shadow_band[1], shadow_band[2], L))
    wh = smoothstep(high_band[0], high_band[1], L)
    if keep_sat > 0.0:
        k = 1.0 - keep_sat * smoothstep(0.25, 0.7, saturation(c))[..., None]
        ws = ws * k
        wh = wh * k
    return c + ws * np.asarray(shadow) + wh * np.asarray(high)


def grade_identity(c):
    return c


def grade_office(c):
    """办事处（阴天下午、日光灯）：整屋灰绿一色。暗部（西装、墙裙、柜子阴影）往青里偏，
    亮部（窗、台灯照的纸、皮肤高光）往暖里偏，层次靠冷暖分出来；纯黑不动"""
    return split_tone(c, shadow=(-0.02, 0.004, 0.025), shadow_band=(0.03, 0.18, 0.38),
                      high=(0.02, 0.01, -0.02), high_band=(0.45, 0.65), toe=0.06, keep_sat=0.4)


def grade_dorm(c):
    """宿舍（夜里、台灯和窗外钠灯）：橙色的灯光原样留着；暗处轻轻偏一点蓝绿，
    让黑里不只是一片棕黑。亮部不动，开场要压抑"""
    return split_tone(c, shadow=(-0.006, 0.005, 0.015), shadow_band=(0.03, 0.15, 0.32),
                      high=(0.0, 0.0, 0.0), high_band=(0.5, 0.8), toe=0.05)


GRADES = {"identity": grade_identity, "office": grade_office, "dorm": grade_dorm}


def build(grade, n):
    """N×N×N 的表：[b][g][r] -> 输出 RGB（0~1）。格中心按 Godot 不做半像素偏移的采样方式放"""
    x = (np.arange(n) + 0.5) / n
    x[0] = 0.0          # 第 0 格：纯黑
    x[-1] = 1.0         # 最后一格：纯白
    b, g, r = np.meshgrid(x, x, x, indexing="ij")
    c = np.stack([r, g, b], axis=-1)
    return np.clip(grade(c), 0.0, 1.0)


def save(lut, path):
    n = lut.shape[0]
    # 横条：第 k 张切片（蓝 = k）放在 x ∈ [k*N, (k+1)*N)；切片里 x 是红、y 是绿
    strip = lut.transpose(1, 0, 2, 3).reshape(n, n * n, 3)
    Image.fromarray(np.round(strip * 255.0).astype(np.uint8)).save(path, optimize=True)


IMPORT = """[remap]

importer="3d_texture"
type="CompressedTexture3D"

[params]

compress/mode=0
compress/high_quality=false
compress/lossy_quality=0.7
compress/hdr_compression=1
compress/channel_pack=0
mipmaps/generate=false
mipmaps/limit=-1
slices/horizontal={n}
slices/vertical=1
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("names", nargs="*", default=list(GRADES))
    ap.add_argument("--size", type=int, default=128)
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    for nm in a.names:
        path = os.path.join(a.out, f"{nm}_lut.png")
        save(build(GRADES[nm], a.size), path)
        imp = path + ".import"
        if not os.path.exists(imp):
            with open(imp, "w") as f:
                f.write(IMPORT.format(n=a.size))
        print(f"{path}  {a.size}³")


if __name__ == "__main__":
    main()
