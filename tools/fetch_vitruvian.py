#!/usr/bin/env python3
"""下载 Vitruvian（CharMorph 的写实角色，CC0，https://github.com/seenbuklee/CharMorph-Vitruvian）里捏脸要用的部分，
装进 blender/cache/charmorph/vitruvian/（不进 git），给 blender/scripts/gen_head_vitruvian.py 用：
  - char.blend（全身网格，男女同一套拓扑）、morphs/（L1 基础形状、L2 捏脸形态、L3 表情）、hairstyles/（发型、眉毛的发丝）
  - assets/ 里的 Eyeshadow（眼部遮蔽）、Tearline（泪线）；泪阜（Lacrimal_Caruncle）作者授权只写了 Free，不用
  - textures/4K/ 里头（UDIM 1001）、眼白、虹膜、口腔的贴图（身体的几块不要，省 600 MB）
固定在 REV 这个提交上；GitHub 直连就够快（几 MB/s），不用代理。
用法: python tools/fetch_vitruvian.py
"""
import concurrent.futures as cf
import json
import os
import urllib.parse

from fetch_util import download, get_json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(ROOT, "blender", "cache", "charmorph", "vitruvian")
REV = "db7736668dfbcb090019068c8aeab28105af36a0"
WANT_TEX = ("skin_light_col.1001", "skin_dark_col.1001", "skin_cavity_rough_coat.1001", "skin_disp.1001",
            "age_skin_disp.1001", "mouth_col.1006", "mouth_rough.1006", "sclera_col.1005", "sclera_rough.1005",
            "iris_col.1007", "iris_rough.1007", "iris_disp.1007")


def wanted(p):
    if p.startswith("textures/4K/"):
        return any(w in p for w in WANT_TEX)
    if p.startswith("assets/"):
        return p.endswith(("Eyeshadow.blend", "Tearline.blend", "authors.yaml"))
    # 发型库（hair.blend，80 MB）和骨骼绑定数据用不上
    return p != "hair.blend" and not p.startswith(("weights/", "joints/"))


os.makedirs(DEST, exist_ok=True)
tree_path = os.path.join(DEST, f".tree_{REV}.json")
if not os.path.exists(tree_path):
    tree = get_json(f"https://api.github.com/repos/seenbuklee/CharMorph-Vitruvian/git/trees/{REV}?recursive=1")
    with open(tree_path, "w", encoding="utf-8") as f:
        json.dump(tree, f)
with open(tree_path, encoding="utf-8") as f:
    files = [x for x in json.load(f)["tree"] if x["type"] == "blob" and wanted(x["path"])]
base = f"https://raw.githubusercontent.com/seenbuklee/CharMorph-Vitruvian/{REV}/"


def one(x):
    """下好的文件大小和目录树里的对得上才算数（大小不对的删掉重下）"""
    dst = os.path.join(DEST, x["path"])
    if os.path.exists(dst):
        if os.path.getsize(dst) == x["size"]:
            return 0
        os.remove(dst)
    for _ in range(3):
        if not download(base + urllib.parse.quote(x["path"]), dst, timeout=600):
            break
        if os.path.getsize(dst) == x["size"]:
            return x["size"]
        print("大小不对，重试", x["path"], os.path.getsize(dst), x["size"])
        os.remove(dst)
    raise SystemExit("下载失败: " + x["path"])


with cf.ThreadPoolExecutor(6) as ex:
    got = sum(ex.map(one, files))
print("vitruvian: %d 个文件，新下载 %.1f MB" % (len(files), got / 1e6))
