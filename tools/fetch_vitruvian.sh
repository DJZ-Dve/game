#!/bin/zsh
# 下载 Vitruvian（CharMorph 的写实角色，CC0，https://github.com/seenbuklee/CharMorph-Vitruvian）里捏脸要用的部分，
# 装进 blender/cache/charmorph/vitruvian/（不进 git），给 blender/scripts/gen_head_vitruvian.py 用：
#   - char.blend（全身网格，男女同一套拓扑）、morphs/（L1 基础形状、L2 捏脸形态、L3 表情）、hairstyles/（发型、眉毛的发丝）
#   - assets/ 里的 Eyeshadow（眼部遮蔽）、Tearline（泪线）；泪阜（Lacrimal_Caruncle）作者授权只写了 Free，不用
#   - textures/4K/ 里头（UDIM 1001）、眼白、虹膜、口腔的贴图（身体的几块不要，省 600 MB）
# 固定在 REV 这个提交上；GitHub 直连就够快（几 MB/s），不用代理。
# 用法: tools/fetch_vitruvian.sh
set -eu
root=${0:A:h:h}
dest=$root/blender/cache/charmorph/vitruvian
REV=db7736668dfbcb090019068c8aeab28105af36a0
mkdir -p $dest
tree=$dest/.tree_$REV.json
[[ -s $tree ]] || curl -fsSL --max-time 120 -o $tree \
  "https://api.github.com/repos/seenbuklee/CharMorph-Vitruvian/git/trees/$REV?recursive=1"
python3 -I - $tree $dest $REV <<'EOF'
# 按目录树挑文件并发下载：先下到 .part，大小对上了再改名；失败重试 3 次
import concurrent.futures as cf, json, os, sys, urllib.parse, urllib.request
tree, dest, rev = sys.argv[1:4]
want_tex = ("skin_light_col.1001", "skin_dark_col.1001", "skin_cavity_rough_coat.1001", "skin_disp.1001",
            "age_skin_disp.1001", "mouth_col.1006", "mouth_rough.1006", "sclera_col.1005", "sclera_rough.1005",
            "iris_col.1007", "iris_rough.1007", "iris_disp.1007")
def wanted(p):
    if p.startswith("textures/4K/"):
        return any(w in p for w in want_tex)
    if p.startswith("assets/"):
        return p.endswith(("Eyeshadow.blend", "Tearline.blend", "authors.yaml"))
    # 发型库（hair.blend，80 MB）和骨骼绑定数据用不上
    return p != "hair.blend" and not p.startswith(("weights/", "joints/"))
fs = [x for x in json.load(open(tree))["tree"] if x["type"] == "blob" and wanted(x["path"])]
base = "https://raw.githubusercontent.com/seenbuklee/CharMorph-Vitruvian/%s/" % rev
def one(x):
    p, dst = x["path"], os.path.join(dest, x["path"])
    if os.path.exists(dst) and os.path.getsize(dst) == x["size"]:
        return 0
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    for i in range(3):
        try:
            with urllib.request.urlopen(base + urllib.parse.quote(p), timeout=600) as r:
                d = r.read()
            if len(d) == x["size"]:
                with open(dst + ".part", "wb") as f:
                    f.write(d)
                os.replace(dst + ".part", dst)
                return len(d)
            print("大小不对，重试", p, len(d), x["size"])
        except OSError as e:
            print("重试", i, p, e)
    raise SystemExit("下载失败: " + p)
with cf.ThreadPoolExecutor(6) as ex:
    got = sum(ex.map(one, fs))
print("vitruvian: %d 个文件，新下载 %.1f MB" % (len(fs), got / 1e6))
EOF
