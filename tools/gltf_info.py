#!/usr/bin/env python3
"""打印 glTF 的节点、网格包围盒（米）和材质名，摆道具时用来查尺寸。
用法: python tools/gltf_info.py power_box_01 television_02 ...
"""
import json
import math
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "third_party", "polyhaven", "models")
sys.stdout.reconfigure(encoding="utf-8")


def f3(x):
    v = int(math.copysign(math.floor(abs(x) * 1000 + 0.5), x))  # 四舍五入到毫米（半数远离零）
    return f"{'-' if v < 0 else ''}{abs(v) // 1000}.{abs(v) % 1000:03d}"


def vec(xs):
    return ",".join(f3(x) for x in xs)


for id in sys.argv[1:]:
    with open(os.path.join(ROOT, id, f"{id}_2k.gltf"), encoding="utf-8") as f:
        g = json.load(f)
    print(f"== {id}  materials: {', '.join(m.get('name', '') for m in g.get('materials', []))}")
    for i, n in enumerate(g["nodes"]):
        s = f"  node[{i}] {n.get('name', '')}"
        if "translation" in n:
            s += f"  t=({vec(n['translation'])})"
        if "scale" in n:
            s += f"  s=({vec(n['scale'])})"
        if "mesh" in n:
            acc = [g["accessors"][p["attributes"]["POSITION"]] for p in g["meshes"][n["mesh"]]["primitives"]]
            mn = [min(a["min"][k] for a in acc) for k in range(3)]
            mx = [max(a["max"][k] for a in acc) for k in range(3)]
            s += f"  size=({vec(mx[k] - mn[k] for k in range(3))})  min=({vec(mn)})"
        if "children" in n:
            s += f"  children={','.join(map(str, n['children']))}"
        print(s)
