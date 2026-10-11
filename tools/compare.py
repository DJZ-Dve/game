#!/usr/bin/env python3
"""改画面前后对比：两个 tools/bench.sh 输出目录里同名的截图左右并排（左 before、右 after），再出总拼图。

用法: python3 tools/compare.py 前目录 后目录 输出目录 [--only 名字,名字] [--crop x,y,w,h] [--diff] [--labels before,after]
  例: python3 tools/compare.py .tmp/bench/baseline .tmp/bench/try1 .tmp/bench/cmp1
      python3 tools/compare.py .tmp/bench/baseline .tmp/bench/try1 .tmp/bench/cmp1 --only office_visitor --crop 600,250,500,350
  --only   只比这几张（文件名去掉 .png，或者只给场景名 office 比这个场景的全部）
  --crop   只比原图上这一块（像素，按 1600x900 的原图算），放大看细节：墙皮、漆面、布料
  --diff   右边再加一格差异图（前后差多少，放大 4 倍，越亮差得越多）
产出: 输出目录/<名字>.jpg（每对一张，原尺寸，看细节用这个）、<场景>_compare.jpg（每个场景一张总览，两对一行）、
      compare_sheet.jpg（全部）。
每格下面标着帧率、帧时间（读两边的 <场景>_shots.json）。
"""
import argparse
import glob
import json
import os

from PIL import Image, ImageChops, ImageDraw

from contact_sheet import BG, DIM, INK, font, stats_line

BEFORE = (120, 170, 230)
AFTER = (235, 170, 90)


def manifests(folder):
    """文件名 -> 清单里的记录（帧率、说明……）"""
    out = {}
    for path in glob.glob(os.path.join(folder, "*_shots.json")):
        for r in json.load(open(path, encoding="utf-8")).get("shots", []):
            out[r["file"]] = r
    return out


def order_key(name, recs):
    """按场景、再按清单里的顺序排（清单里没有的按名字排在后面）"""
    scene = name.split("_")[0]
    rank = {"dorm": 0, "office": 1, "cabin": 2}.get(scene, 9)
    idx = recs.get(name + ".png", {}).get("_i", 999)
    return (rank, scene, idx, name)


def labeled(im, title, sub, color):
    """图下面加一条标注：左边 before/after（彩色），后面帧率；字号跟着图宽走，缩小了也认得出"""
    size = max(15, im.width // 48)
    f = font(size)
    bar = size + 14
    out = Image.new("RGB", (im.width, im.height + bar), BG)
    out.paste(im, (0, 0))
    d = ImageDraw.Draw(out)
    d.text((8, im.height + 6), title, font=f, fill=color)
    x = 8 + d.textlength(title, font=f) + size
    d.text((x, im.height + 6), sub, font=f, fill=DIM)
    return out


def diff_image(a, b):
    d = ImageChops.difference(a.convert("RGB"), b.convert("RGB"))
    return d.point(lambda v: min(255, v * 4))


def pair(a_path, b_path, recs_a, recs_b, labels, crop=None, diff=False):
    a = Image.open(a_path).convert("RGB")
    b = Image.open(b_path).convert("RGB")
    if b.size != a.size:
        b = b.resize(a.size, Image.LANCZOS)
    if crop:
        x, y, w, h = crop
        a, b = a.crop((x, y, x + w, y + h)), b.crop((x, y, x + w, y + h))
        # 小块放大到大约原图宽度，看得清
        k = max(1.0, 1600 / max(w, 1))
        a = a.resize((round(w * k), round(h * k)), Image.LANCZOS)
        b = b.resize(a.size, Image.LANCZOS)
    panels = [a, b] + ([diff_image(a, b)] if diff else [])
    name = os.path.basename(a_path)
    tags = [(labels[0], stats_line(recs_a.get(name, {})), BEFORE), (labels[1], stats_line(recs_b.get(name, {})), AFTER)]
    if diff:
        tags.append(("diff ×4", "", DIM))
    cells = [labeled(p, t, sub, c) for p, (t, sub, c) in zip(panels, tags)]
    gap = 6
    W = sum(c.width for c in cells) + gap * (len(cells) - 1)
    out = Image.new("RGB", (W, cells[0].height), BG)
    x = 0
    for c in cells:
        out.paste(c, (x, 0))
        x += c.width + gap
    return out


def sheet(rows, path, title, cols=2):
    """总拼图：每格一对（已经缩好的），cols 对一行；上面一行标题"""
    if not rows:
        return
    f_head, f_name = font(22), font(17)
    head, name_h, gap = 40, 26, 12
    cw = max(r.width for _, _, r in rows)
    ch = max(r.height for _, _, r in rows) + name_h
    cols = min(cols, len(rows))
    nrows = (len(rows) + cols - 1) // cols
    img = Image.new("RGB", (8 + cols * (cw + gap), head + nrows * (ch + gap)), BG)
    d = ImageDraw.Draw(img)
    d.text((10, 9), title, font=f_head, fill=INK)
    for i, (name, desc, r) in enumerate(rows):
        x = 8 + (i % cols) * (cw + gap)
        y = head + (i // cols) * (ch + gap)
        d.text((x + 2, y + 2), name + ("　" + desc if desc else ""), font=f_name, fill=INK)
        img.paste(r, (x, y + name_h))
    img.save(path, quality=86)
    print("sheet", path)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("before")
    ap.add_argument("after")
    ap.add_argument("out")
    ap.add_argument("--only", default="")
    ap.add_argument("--crop", default="")
    ap.add_argument("--diff", action="store_true")
    ap.add_argument("--labels", default="before,after")
    a = ap.parse_args()
    labels = a.labels.split(",")
    crop = tuple(int(v) for v in a.crop.split(",")) if a.crop else None
    os.makedirs(a.out, exist_ok=True)
    recs_a, recs_b = manifests(a.before), manifests(a.after)
    for recs in (recs_a, recs_b):
        for i, r in enumerate(recs.values()):
            r.setdefault("_i", i)
    names_a = {os.path.basename(p)[:-4] for p in glob.glob(os.path.join(a.before, "*.png"))}
    names_b = {os.path.basename(p)[:-4] for p in glob.glob(os.path.join(a.after, "*.png"))}
    only = [n for n in a.only.split(",") if n]
    pick = lambda n: not only or n in only or n.split("_")[0] in only  # noqa: E731
    for n in sorted((names_a ^ names_b)):
        if pick(n):
            print(f"只有一边有: {n}.png（{'前' if n in names_a else '后'}）")
    names = sorted((n for n in names_a & names_b if pick(n)), key=lambda n: order_key(n, recs_a))
    if not names:
        print("没有同名的截图")
        return
    rows = {}
    for n in names:
        im = pair(os.path.join(a.before, n + ".png"), os.path.join(a.after, n + ".png"), recs_a, recs_b, labels,
                  crop, a.diff)
        im.save(os.path.join(a.out, n + ".jpg"), quality=90)
        # 总拼图里每对缩到 1280 宽（带差异图三格时 1500）
        w = 1500 if a.diff else 1280
        small = im.resize((w, round(im.height * w / im.width)), Image.LANCZOS)
        desc = (recs_b.get(n + ".png") or recs_a.get(n + ".png") or {}).get("desc", "")
        rows.setdefault(n.split("_")[0], []).append((n, desc, small))
    print(f"{len(names)} 对 -> {os.path.abspath(a.out)}")
    title = f"{labels[0]}: {os.path.abspath(a.before)}　{labels[1]}: {os.path.abspath(a.after)}" \
        + (f"　crop {a.crop}" if crop else "")
    cols = 1 if a.diff else 2
    for scene, r in rows.items():
        sheet(r, os.path.join(a.out, f"{scene}_compare.jpg"), f"{scene}　" + title, cols)
    sheet([x for r in rows.values() for x in r], os.path.join(a.out, "compare_sheet.jpg"), title, cols)


if __name__ == "__main__":
    main()
