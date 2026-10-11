#!/bin/zsh
# 下载 MPFB（MakeHuman Plugin For Blender，代码 GPL-3.0，生成的人和素材包 CC0）和它要的素材，
# 装进 blender/cache/mpfb/（不进 git），给 blender/scripts/gen_head_mpfb.py（主角周海生的头）用。
# 不动自己的 Blender 配置：扩展和 MPFB 的用户数据都装在 BLENDER_USER_RESOURCES=blender/cache/mpfb/blender 下面，
# 跑生成脚本时同样带上这个环境变量（gen_crew.py 自己设好再调 Blender）。
#   - 扩展本体：Blender 官方扩展平台 extensions.blender.org 的 mpfb 2.0.18（要 Blender ≥ 4.2），按平台给的 sha256 校验
#   - makehuman_system_assets（MakeHuman 官方素材包，CC0）：整包 280 MB，官方镜像单连接只有三四十 KB/s，
#     所以只按 HTTP 分段把用得上的几样（眼睛、眉毛、睫毛、短发、皮肤、牙齿舌头，约 30 MB）从 zip 里并发抠出来
#   - visemes02（15 个 Meta 口型）、faceunits01（52 个 ARKit 表情，含眨眼）：形态键包，整包下
# 用法: tools/fetch_mpfb.sh
set -eu
root=${0:A:h:h}
dest=$root/blender/cache/mpfb
dl=$dest/dl
res=$dest/blender
blender=${BLENDER:-/Applications/Blender.app/Contents/MacOS/Blender}

ver=2.0.18
sha=c075b3e9b94b8e5556a5f03f4653602d02ea306de08126e8f55ed6dee28a2dad
ext=https://extensions.blender.org/download/sha256:$sha/add-on-mpfb-v$ver.zip
# 素材包两个镜像，前一个连不上换后一个
mirrors=(https://files.makehumancommunity.org https://files2.makehumancommunity.org)
packs=(functional/visemes02.zip functional/faceunits01.zip)
system=asset_packs/makehuman_system_assets/makehuman_system_assets_cc0.zip
# 系统素材包里要的部分（zip 里的路径前缀）
pick=(packs/ eyes/ eyebrows/ eyelashes/ hair/short skins/middleage_asian_male/ skins/young_asian_male/
  teeth/teeth_base/ tongue/)

# 先下到 .part，完整下完再改名；失败重试 3 次（每次把镜像轮一遍）
fetch() {   # fetch 输出文件 网址...
  local out=$1; shift
  [[ -s $out ]] && return
  mkdir -p ${out:h}
  local i u
  for i in 1 2 3; do
    for u in "$@"; do
      if curl -fsSL --max-time 900 -o "$out.part" "$u"; then
        mv -f "$out.part" "$out"
        return
      fi
      echo "retry $i $u"
    done
  done
  echo "下载失败: ${out:t}" >&2
  exit 1
}

fetch $dl/mpfb-$ver.zip $ext
[[ $(shasum -a 256 $dl/mpfb-$ver.zip | cut -d' ' -f1) == $sha ]] || { echo "mpfb-$ver.zip 校验不对" >&2; exit 1 }
for p in $packs; do
  fetch $dl/${p:t} ${^mirrors}/$p
done

# 装扩展（装到 $res/extensions/user_default/mpfb）
if [[ ! -f $res/extensions/user_default/mpfb/__init__.py ]]; then
  BLENDER_USER_RESOURCES=$res "$blender" -b --factory-startup \
    --command extension install-file -r user_default $dl/mpfb-$ver.zip
fi
# 素材解到 MPFB 的用户数据目录（MPFB 界面上「Load pack from zip」也就是解压到这里）
data=$res/extensions/.user/user_default/mpfb/data
mkdir -p $data
for p in $packs; do
  stamp=$data/.${p:t:r}.done
  [[ -f $stamp ]] && continue
  unzip -oq $dl/${p:t} -d $data
  touch $stamp
done
stamp=$data/.system_assets.done
if [[ ! -f $stamp || ${(j: :)pick} != "$(cat $stamp)" ]]; then
  python3 -I - $data ${^mirrors}/$system -- $pick <<'EOF'
# 按 HTTP Range 从远端 zip 里只取某些文件：先读结尾的中央目录，再每个文件取「本地文件头 + 压缩数据」解开
import concurrent.futures as cf, os, struct, sys, time, urllib.request, zlib
a = sys.argv[1:]
out, urls, pick = a[0], a[1:a.index("--")], tuple(a[a.index("--") + 1:])

def get(lo, hi):
    for i in range(12):
        u = urls[i // 3 % len(urls)]
        try:
            r = urllib.request.Request(u, headers={"Range": f"bytes={lo}-{hi}"})
            with urllib.request.urlopen(r, timeout=120) as f:
                d = f.read()
            if len(d) == hi - lo + 1:
                return d
        except OSError as e:
            print("retry", i, u, e, flush=True)
        time.sleep(2 + i)
    raise SystemExit(f"下载失败: bytes {lo}-{hi}")

with urllib.request.urlopen(urllib.request.Request(urls[0], method="HEAD"), timeout=60) as f:
    size = int(f.headers["Content-Length"])
tail = get(size - 131072, size - 1)
e = tail.rfind(b"PK\x05\x06")
n, cd_size, cd_off = struct.unpack("<HII", tail[e + 10:e + 20])
cd = tail[cd_off - (size - 131072):][:cd_size] if cd_off >= size - 131072 else get(cd_off, cd_off + cd_size - 1)
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
    head = get(off, off + 29)
    nl, xl = struct.unpack("<HH", head[26:30])
    raw = get(off + 30 + nl + xl, off + 30 + nl + xl + csize - 1) if csize else b""
    data = zlib.decompress(raw, -15) if meth == 8 else raw
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst + ".part", "wb") as f:
        f.write(data)
    os.replace(dst + ".part", dst)
    return csize

total = sum(t[2] for t in todo)
done = 0
with cf.ThreadPoolExecutor(8) as ex:
    for k in ex.map(one, sorted(todo, key=lambda t: -t[2])):
        done += k
print(f"system assets: {len(todo)} 个文件，{total / 1e6:.1f} MB")
EOF
  print -r -- ${(j: :)pick} > $stamp
fi
ls $data
