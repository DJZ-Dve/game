#!/usr/bin/env python3
"""从 ambientCG (CC0) 下载材质到 assets/third_party/ambientcg/<id>/
用法: python tools/fetch_ambientcg.py --ids DiamondPlate008A,Metal016 [--res 2K] [--proxy http://127.0.0.1:7900]
只保留 Color / NormalGL / Roughness / Metalness / AmbientOcclusion / Opacity。
ambientCG 直连很慢（几十 KB/s）：下不完就再跑一遍，压缩包会接着下（见 fetch_util.py）。
"""
import argparse
import glob
import os
import re
import zipfile

from fetch_util import download

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(ROOT, "assets", "third_party", "ambientcg")
KEEP = re.compile(r"_(Color|NormalGL|Roughness|Metalness|AmbientOcclusion|Opacity)\.(jpg|png)$")


def fetch(ids, res="2K", proxy=None):
    # 压缩包下到 .tmp/（不进 git），解压完再删，没下完的 .part 留着下次接着下
    cache = os.path.join(ROOT, ".tmp", "ambientcg")
    ok = True
    for id in ids:
        dest = os.path.join(DEST, id)
        if glob.glob(os.path.join(dest, "*_Color.*")):
            print(f"skip   {id}")
            continue
        zpath = os.path.join(cache, f"{id}_{res}-JPG.zip")
        if not download(f"https://ambientcg.com/get?file={id}_{res}-JPG.zip", zpath, proxy):
            ok = False
            continue
        os.makedirs(dest, exist_ok=True)
        with zipfile.ZipFile(zpath) as z:
            for name in z.namelist():
                if KEEP.search(name):
                    with open(os.path.join(dest, os.path.basename(name)), "wb") as f:
                        f.write(z.read(name))
        os.remove(zpath)
        print(f"texture {id}")
    return ok


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="从 ambientCG 下载材质")
    ap.add_argument("--ids", required=True)
    ap.add_argument("--res", default="2K")
    ap.add_argument("--proxy")
    a = ap.parse_args()
    raise SystemExit(0 if fetch([x for x in a.ids.split(",") if x], a.res, a.proxy) else 1)
