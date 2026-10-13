#!/usr/bin/env python3
"""从 Poly Haven (CC0) 下载模型和贴图到 assets/third_party/polyhaven/
用法: python tools/fetch_polyhaven.py [--models a,b] [--textures c,d] [--res 2k] [--proxy URL]
"""
import argparse
import os

from fetch_util import download, get_json

DEST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "third_party", "polyhaven")


def fetch(models=(), textures=(), res="2k", proxy=None):
    ok = True
    for id in models:
        dest = os.path.join(DEST, "models", id)
        g = get_json(f"https://api.polyhaven.com/files/{id}", proxy)["gltf"][res]["gltf"]
        # .gltf 本身，加上它引用的 .bin 和贴图（相对路径 → 链接）
        files = {g["url"].split("/")[-1]: g["url"], **{k: v["url"] for k, v in g.get("include", {}).items()}}
        for name, url in files.items():
            ok &= download(url, os.path.join(dest, name), proxy)
        print(f"model  {id}")
    # 贴图只取颜色、法线(OpenGL)、ARM(AO/粗糙度/金属度) 三张
    for id in textures:
        dest = os.path.join(DEST, "textures", id)
        j = get_json(f"https://api.polyhaven.com/files/{id}", proxy)
        for kind in ("Diffuse", "nor_gl", "arm"):
            url = j.get(kind, {}).get(res, {}).get("jpg", {}).get("url")
            if url:
                ok &= download(url, os.path.join(dest, url.split("/")[-1]), proxy)
        print(f"texture {id}")
    return ok


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="从 Poly Haven 下载模型和贴图")
    ap.add_argument("--models", default="")
    ap.add_argument("--textures", default="")
    ap.add_argument("--res", default="2k")
    ap.add_argument("--proxy")
    a = ap.parse_args()
    models, textures = ([x for x in s.split(",") if x] for s in (a.models, a.textures))
    raise SystemExit(0 if fetch(models, textures, a.res, a.proxy) else 1)
