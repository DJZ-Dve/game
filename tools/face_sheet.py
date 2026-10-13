#!/usr/bin/env python3
"""把捏脸预设的批量截图（捏脸界面 --cc-shots 拍的 <预设号>_face.png、<预设号>_side.png）拼成一张对比图。

用法: python3 tools/face_sheet.py 目录 [--out 路径] [--crop 0.3,0.12,0.7,0.8]
  每个预设一列：上面正脸、下面侧脸，底下写预设号和名字（从 scripts/crew_look.gd 的 PRESETS 里读）。
  --crop 按画面比例裁中间那块（左、上、右、下），默认裁出脸
"""
import argparse
import glob
import os
import re

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FONTS = ["/System/Library/Fonts/STHeiti Medium.ttc", "/System/Library/Fonts/PingFang.ttc",
         os.path.join(ROOT, "assets/fonts/NotoSerifSC-VF.ttf"), "C:/Windows/Fonts/msyh.ttc"]


def font(size):
    for f in FONTS:
        if os.path.exists(f):
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()


def preset_names():
    src = open(os.path.join(ROOT, "scripts/crew_look.gd"), encoding="utf-8").read()
    body = src[src.index("const PRESETS"):]
    return re.findall(r'\{"name": "([^"]+)", "sex": "([mf])"', body)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("--out")
    ap.add_argument("--crop", default="0.3,0.1,0.7,0.82")
    ap.add_argument("--tile", type=int, default=360)
    a = ap.parse_args()
    crop = [float(x) for x in a.crop.split(",")]
    names = preset_names()
    ids = sorted({int(os.path.basename(f)[:2]) for f in glob.glob(os.path.join(a.dir, "*_face.png"))})
    t = a.tile
    sheet = Image.new("RGB", (t * len(ids), t * 2 + 44), (24, 24, 26))
    d = ImageDraw.Draw(sheet)
    f = font(22)
    for col, i in enumerate(ids):
        for row, v in enumerate(("face", "side")):
            p = os.path.join(a.dir, "%02d_%s.png" % (i, v))
            if not os.path.exists(p):
                continue
            im = Image.open(p).convert("RGB")
            w, h = im.size
            im = im.crop((int(crop[0] * w), int(crop[1] * h), int(crop[2] * w), int(crop[3] * h)))
            im.thumbnail((t, t))
            sheet.paste(im, (col * t + (t - im.width) // 2, row * t))
        name, sex = names[i] if i < len(names) else ("?", "?")
        d.text((col * t + 12, t * 2 + 8), "%d %s（%s）" % (i, name, "男" if sex == "m" else "女"), font=f, fill=(226, 222, 212))
    out = a.out or os.path.join(a.dir, "sheet.jpg")
    sheet.save(out, quality=90)
    print(out)


main()
