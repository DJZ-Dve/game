#!/usr/bin/env python3
"""冰井每圈深度标记（「R07 / -84 m」）用的字形图集：工业上喷漆用的无衬线模板字。

字形用 Noto Sans SC（blender/fonts/，SIL OFL）字重 800，自动加模板的“桥”：每个封闭的字腔（0、4、6、8、9、R 里的洞）
在正中竖着切一道缝，从洞往上、往下切穿笔画——字模上那几块“岛”就是靠这几道桥连着的。
（试过 Stardos Stencil：衬线模板字的细笔画在主镜头里只有几个像素高时全丢了，剩一串黑点认不出是字。）

每个字形画成有符号距离场（0.5 是字的边，往里变大、往外变小），着色器拿它按像素宽度抗锯齿、
做喷漆的飞边（字边外一圈淡淡的雾点）、磨掉的边（阈值往里收），远近都清楚，图也小。
排成 4×4 格，每格 CELL 像素见方：笔的起点在格子左边 PEN_X、基线在 BASE_Y（从上往下数）；
1 em = EM 像素。字距（advance）、大写高按 em 打印出来，抄进 assets/shaders/ice_wall.gdshader 的 STENCIL_ADV、STENCIL_CAP_EM。

  python3 tools/gen_stencil_glyphs.py      # 输出 assets/textures/stencil_glyphs.png
之后让 Godot 导入一次：godot --headless --path . --import
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT = os.path.join(ROOT, "blender/fonts/NotoSansSC-VF.ttf")
WEIGHT = 800
OUT = os.path.join(ROOT, "assets/textures/stencil_glyphs.png")
GLYPHS = "0123456789R/-m+."   # 着色器按这个顺序取第几格
CELL = 128
EM = 100          # 1 em 多少像素
PEN_X = 16
BASE_Y = 100
SPREAD = 10.0     # 距离场覆盖字边内外各多少像素（再远就截到 0 / 1）
SS = 8            # 先按 SS 倍画、算距离，再缩下来
BRIDGE = 0.064    # 桥宽（em）


def load_font(size: int) -> ImageFont.FreeTypeFont:
    font = ImageFont.truetype(FONT, size)
    font.set_variation_by_axes([WEIGHT])
    return font


def stencilize(ink: np.ndarray, bw: int) -> np.ndarray:
    """每个封闭的字腔正中竖着切一道宽 bw 的缝：从洞的顶往上、从洞的底往下，切到出了笔画为止"""
    lab, n = ndimage.label(~ink)
    border = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]])).tolist())
    out = ink.copy()
    for h in range(1, n + 1):
        if h in border:
            continue
        ys, xs = np.nonzero(lab == h)
        cx = int(round(xs.mean()))
        x0, x1 = cx - bw // 2, cx + bw - bw // 2
        col = ys[xs == cx] if np.any(xs == cx) else ys
        y = col.min() - 1
        while y >= 0 and ink[y, x0:x1].any():
            out[y, x0:x1] = False
            y -= 1
        y = col.max() + 1
        while y < ink.shape[0] and ink[y, x0:x1].any():
            out[y, x0:x1] = False
            y += 1
    return out


def glyph_sdf(font: ImageFont.FreeTypeFont, ch: str) -> np.ndarray:
    big = CELL * SS
    im = Image.new("L", (big, big), 0)
    ImageDraw.Draw(im).text((PEN_X * SS, BASE_Y * SS), ch, font=font, fill=255, anchor="ls")
    inside = stencilize(np.asarray(im) >= 128, round(BRIDGE * EM * SS))
    # 有符号距离（大图像素）：字里正、字外负
    d = ndimage.distance_transform_edt(inside) - ndimage.distance_transform_edt(~inside)
    # 缩到 CELL：每个小像素取对应 SS×SS 块的平均距离，换成小图像素
    d = d.reshape(CELL, SS, CELL, SS).mean(axis=(1, 3)) / SS
    return np.clip(0.5 + d / (2.0 * SPREAD), 0.0, 1.0)


def main() -> None:
    font = load_font(EM * SS)
    atlas = np.zeros((CELL * 4, CELL * 4), np.float32)
    for i, ch in enumerate(GLYPHS):
        r, c = divmod(i, 4)
        atlas[r * CELL:(r + 1) * CELL, c * CELL:(c + 1) * CELL] = glyph_sdf(font, ch)
    Image.fromarray(np.round(atlas * 255.0).astype(np.uint8)).save(OUT)
    # 大写高：数字“0”的墨迹从基线往上多高（em）
    probe = Image.new("L", (EM * 4, EM * 4), 0)
    ImageDraw.Draw(probe).text((EM, EM * 3), "0", font=load_font(EM * 2), fill=255, anchor="ls")
    ys = np.nonzero(np.asarray(probe) >= 128)[0]
    cap = (EM * 3 - ys.min()) / (EM * 2)
    adv = ", ".join("%.3f" % (font.getlength(ch) / (EM * SS)) for ch in GLYPHS)
    print("wrote", os.path.relpath(OUT, ROOT))
    print("STENCIL_CAP_EM = %.3f" % cap)
    print("STENCIL_ADV = {%s}   // %s   space %.3f" % (adv, GLYPHS, font.getlength(" ") / (EM * SS)))


if __name__ == "__main__":
    sys.exit(main())
