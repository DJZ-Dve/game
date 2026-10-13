#!/usr/bin/env python3
"""打印 .glb 里每个网格每个图元（材质）的顶点数和有哪些顶点属性。排查导出问题用。
用法: python tools/glb_info.py assets/models/submarine_cockpit.glb [网格名过滤]
"""
import json
import struct
import sys

if len(sys.argv) < 2:
    sys.exit(f"用法: python {sys.argv[0]} 文件.glb [网格名过滤]")
sys.stdout.reconfigure(encoding="utf-8")
want = sys.argv[2].lower() if len(sys.argv) > 2 else ""
with open(sys.argv[1], "rb") as f:
    # glb 头 12 字节，接着是 JSON 块：4 字节长度（小端）+ 4 字节类型 + JSON
    f.seek(12)
    n = struct.unpack("<I", f.read(4))[0]
    f.seek(20)
    g = json.loads(f.read(n))
for m in g["meshes"]:
    if want not in m.get("name", "").lower():
        continue
    for p in m["primitives"]:
        mat = g["materials"][p["material"]]["name"] if "material" in p else "-"
        count = g["accessors"][p["attributes"]["POSITION"]]["count"]
        print(f"{m.get('name', ''):<14} {mat:<22} {count:>8}  {','.join(p['attributes'])}")
