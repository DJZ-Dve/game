#!/usr/bin/env python3
"""把一个场景的基准截图拼成一张带标注的总览图（tools/bench.sh 拍完自动调用）。

用法: python3 tools/contact_sheet.py 目录 场景 [--cols 3] [--tile 640] [--out 路径]
  读 目录/<场景>_shots.json（DebugArgs --shots 写的清单：顺序、说明、帧率、GPU 时间），没有清单就按文件名排 <场景>_*.png
  产出 目录/<场景>_sheet.jpg：每格一张缩略图，下面一行机位名和说明、一行帧率 / 帧时间 / GPU 时间；
  最上面一行场景名、分辨率、拍摄时间、git 版本（工作区有改动的标 +改动）
"""
import argparse
import datetime
import glob
import json
import os
import subprocess

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
# 标注要写中文：系统黑体优先，没有就用项目里的思源宋体
FONTS = ["/System/Library/Fonts/STHeiti Medium.ttc", "/System/Library/Fonts/PingFang.ttc",
         "/System/Library/Fonts/Hiragino Sans GB.ttc", os.path.join(ROOT, "assets/fonts/NotoSerifSC-VF.ttf"),
         "C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf"]
BG = (24, 24, 26)
INK = (226, 222, 212)
DIM = (150, 148, 142)


def font(size):
    for f in FONTS:
        if os.path.exists(f):
            try:
                return ImageFont.truetype(f, size)
            except OSError:
                continue
    return ImageFont.load_default()


def load_shots(folder, scene):
    """[(png 路径, 记录)]：按清单的顺序；清单里没有的图按文件名排在后面。"""
    shots = []
    seen = set()
    path = os.path.join(folder, f"{scene}_shots.json")
    if os.path.exists(path):
        for r in json.load(open(path, encoding="utf-8")).get("shots", []):
            p = os.path.join(folder, r["file"])
            if os.path.exists(p):
                shots.append((p, r))
                seen.add(os.path.abspath(p))
    for p in sorted(glob.glob(os.path.join(folder, f"{scene}_*.png"))):
        if os.path.abspath(p) not in seen:
            name = os.path.basename(p)[len(scene) + 1:-4]
            shots.append((p, {"name": name, "file": os.path.basename(p)}))
    return shots


def stats_line(r):
    """帧率 / 帧时间 / GPU 时间（有哪个写哪个）"""
    parts = []
    if r.get("fps"):
        parts.append(f"{r['fps']:.0f} fps")
    if r.get("frame_ms"):
        parts.append(f"帧 {r['frame_ms']:.1f} ms")
    if r.get("gpu_ms"):
        parts.append(f"GPU {r['gpu_ms']:.1f} ms")
    return " · ".join(parts)


def git_version():
    try:
        head = subprocess.run(["git", "-C", ROOT, "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                              check=True).stdout.strip()
        dirty = subprocess.run(["git", "-C", ROOT, "status", "--porcelain", "--untracked-files=no"],
                               capture_output=True, text=True).stdout.strip()
        return head + (" +改动" if dirty else "")
    except (OSError, subprocess.CalledProcessError):
        return ""


def fit_text(draw, text, f, width):
    """太长就截断加省略号"""
    if draw.textlength(text, font=f) <= width:
        return text
    while text and draw.textlength(text + "…", font=f) > width:
        text = text[:-1]
    return text + "…"


def sheet(folder, scene, cols=3, tile=640, out=None):
    shots = load_shots(folder, scene)
    if not shots:
        print(f"contact_sheet: {folder} 里没有 {scene}_*.png")
        return None
    first = Image.open(shots[0][0])
    tw, th = tile, round(tile * first.height / first.width)
    pad, label_h, head_h = 8, 50, 40
    rows = (len(shots) + cols - 1) // cols
    W = pad + cols * (tw + pad)
    H = head_h + rows * (th + label_h + pad) + pad
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    f_head, f_name, f_small = font(22), font(17), font(14)
    when = datetime.datetime.fromtimestamp(max(os.path.getmtime(p) for p, _ in shots)).strftime("%Y-%m-%d %H:%M")
    meta = json.load(open(os.path.join(folder, f"{scene}_shots.json"), encoding="utf-8")) \
        if os.path.exists(os.path.join(folder, f"{scene}_shots.json")) else {}
    res = "x".join(str(v) for v in meta.get("resolution", [first.width, first.height]))
    d.text((pad + 2, 9), f"{scene}　{res}　{when}　{git_version()}　{os.path.abspath(folder)}", font=f_head, fill=INK)
    for i, (p, r) in enumerate(shots):
        x = pad + (i % cols) * (tw + pad)
        y = head_h + (i // cols) * (th + label_h + pad)
        im = Image.open(p).convert("RGB").resize((tw, th), Image.LANCZOS)
        img.paste(im, (x, y))
        title = r["name"] + ("　" + r["desc"] if r.get("desc") else "")
        d.text((x + 2, y + th + 5), fit_text(d, title, f_name, tw - 4), font=f_name, fill=INK)
        d.text((x + 2, y + th + 28), stats_line(r), font=f_small, fill=DIM)
    out = out or os.path.join(folder, f"{scene}_sheet.jpg")
    img.save(out, quality=88)
    print("sheet", out)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder")
    ap.add_argument("scene")
    ap.add_argument("--cols", type=int, default=3)
    ap.add_argument("--tile", type=int, default=640, help="每格宽多少像素")
    ap.add_argument("--out")
    a = ap.parse_args()
    sheet(a.folder, a.scene, a.cols, a.tile, a.out)


if __name__ == "__main__":
    main()
