#!/usr/bin/env python3
"""下载 MPFB（MakeHuman Plugin For Blender，代码 GPL-3.0，生成的人和素材包 CC0）和它要的素材，
装进 blender/cache/mpfb/（不进 git），给 blender/scripts/gen_head_mpfb.py（主角周海生的头）用。
不动自己的 Blender 配置：扩展和 MPFB 的用户数据都装在 BLENDER_USER_RESOURCES=blender/cache/mpfb/blender 下面，
跑生成脚本时同样带上这个环境变量。
  - 扩展本体：Blender 官方扩展平台 extensions.blender.org 的 mpfb 2.0.18（要 Blender ≥ 4.2），按平台给的 sha256 校验
  - makehuman_system_assets（MakeHuman 官方素材包，CC0）：整包 280 MB，官方镜像单连接只有三四十 KB/s，
    所以只按 HTTP 分段把用得上的几样（眼睛、眉毛、睫毛、短发、皮肤、牙齿舌头，约 30 MB）从 zip 里并发抠出来
  - visemes02（15 个 Meta 口型）、faceunits01（52 个 ARKit 表情，含眨眼）：形态键包，整包下
用法: python tools/fetch_mpfb.py
"""
import concurrent.futures as cf
import hashlib
import os
import struct
import sys
import time
import urllib.request
import zipfile
import zlib

import godot_bg
from fetch_util import UA, download

ROOT = godot_bg.ROOT
dest = os.path.join(ROOT, "blender", "cache", "mpfb")
dl = os.path.join(dest, "dl")
res = os.path.join(dest, "blender")

VER = "2.0.18"
SHA = "c075b3e9b94b8e5556a5f03f4653602d02ea306de08126e8f55ed6dee28a2dad"
EXT = f"https://extensions.blender.org/download/sha256:{SHA}/add-on-mpfb-v{VER}.zip"
# 素材包两个镜像，前一个连不上换后一个
MIRRORS = ["https://files.makehumancommunity.org", "https://files2.makehumancommunity.org"]
PACKS = ["functional/visemes02.zip", "functional/faceunits01.zip"]
SYSTEM = "asset_packs/makehuman_system_assets/makehuman_system_assets_cc0.zip"
# 系统素材包里要的部分（zip 里的路径前缀）
PICK = ("packs/", "eyes/", "eyebrows/", "eyelashes/", "hair/short", "skins/middleage_asian_male/",
        "skins/young_asian_male/", "teeth/teeth_base/", "tongue/")


def fetch(out, urls):
    """失败重试 3 次，每次把镜像轮一遍"""
    for i in range(3):
        for u in urls:
            if download(u, out, tries=1, timeout=900):
                return
            print(f"retry {i + 1} {u}")
    sys.exit(f"下载失败: {os.path.basename(out)}")


def range_get(urls, lo, hi):
    for i in range(12):
        u = urls[i // 3 % len(urls)]
        try:
            r = urllib.request.Request(u, headers={"Range": f"bytes={lo}-{hi}", "User-Agent": UA})
            with urllib.request.urlopen(r, timeout=120) as f:
                d = f.read()
            if len(d) == hi - lo + 1:
                return d
        except OSError as e:
            print("retry", i, u, e, flush=True)
        time.sleep(2 + i)
    raise SystemExit(f"下载失败: bytes {lo}-{hi}")


def extract_remote(urls, out, pick):
    """按 HTTP Range 从远端 zip 里只取某些文件：先读结尾的中央目录，再每个文件取「本地文件头 + 压缩数据」解开"""
    req = urllib.request.Request(urls[0], method="HEAD", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as f:
        size = int(f.headers["Content-Length"])
    tail = range_get(urls, size - 131072, size - 1)
    e = tail.rfind(b"PK\x05\x06")
    n, cd_size, cd_off = struct.unpack("<HII", tail[e + 10:e + 20])
    cd = tail[cd_off - (size - 131072):][:cd_size] if cd_off >= size - 131072 else range_get(urls, cd_off, cd_off + cd_size - 1)
    todo, p = [], 0
    for _ in range(n):
        meth, csize, nl, xl, cl = struct.unpack("<10xH8xI4xHHH", cd[p:p + 34])
        off = struct.unpack("<I", cd[p + 42:p + 46])[0]
        name = cd[p + 46:p + 46 + nl].decode("utf-8")
        p += 46 + nl + xl + cl
        if name.startswith(pick) and not name.endswith("/"):
            todo.append((name, meth, csize, off))

    def one(t):
        name, meth, csize, off = t
        dst = os.path.join(out, name)
        if os.path.exists(dst):
            return 0
        head = range_get(urls, off, off + 29)
        nl, xl = struct.unpack("<HH", head[26:30])
        raw = range_get(urls, off + 30 + nl + xl, off + 30 + nl + xl + csize - 1) if csize else b""
        data = zlib.decompress(raw, -15) if meth == 8 else raw
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst + ".part", "wb") as f:
            f.write(data)
        os.replace(dst + ".part", dst)
        return csize

    total = sum(t[2] for t in todo)
    with cf.ThreadPoolExecutor(8) as ex:
        list(ex.map(one, sorted(todo, key=lambda t: -t[2])))
    print(f"system assets: {len(todo)} 个文件，{total / 1e6:.1f} MB")


zpath = os.path.join(dl, f"mpfb-{VER}.zip")
fetch(zpath, [EXT])
with open(zpath, "rb") as f:
    if hashlib.sha256(f.read()).hexdigest() != SHA:
        sys.exit(f"mpfb-{VER}.zip 校验不对")
for p in PACKS:
    fetch(os.path.join(dl, os.path.basename(p)), [f"{m}/{p}" for m in MIRRORS])

# 装扩展（装到 res/extensions/user_default/mpfb）
if not os.path.exists(os.path.join(res, "extensions", "user_default", "mpfb", "__init__.py")):
    rc, log = godot_bg.run([godot_bg.blender(), "-b", "--factory-startup", "--command", "extension", "install-file",
                            "-r", "user_default", zpath], env={**os.environ, "BLENDER_USER_RESOURCES": res})
    if rc:
        sys.exit(log)
# 素材解到 MPFB 的用户数据目录（MPFB 界面上「Load pack from zip」也就是解压到这里）
data = os.path.join(res, "extensions", ".user", "user_default", "mpfb", "data")
os.makedirs(data, exist_ok=True)
for p in PACKS:
    stamp = os.path.join(data, f".{os.path.splitext(os.path.basename(p))[0]}.done")
    if os.path.exists(stamp):
        continue
    with zipfile.ZipFile(os.path.join(dl, os.path.basename(p))) as z:
        z.extractall(data)
    open(stamp, "w").close()
stamp = os.path.join(data, ".system_assets.done")
want = " ".join(PICK)
if not os.path.exists(stamp) or open(stamp, encoding="utf-8").read().strip() != want:
    extract_remote([f"{m}/{SYSTEM}" for m in MIRRORS], data, PICK)
    with open(stamp, "w", encoding="utf-8") as f:
        f.write(want + "\n")
print("\n".join(sorted(os.listdir(data))))
