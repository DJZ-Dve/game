#!/bin/zsh
# 从 ambientCG (CC0) 下载材质到 assets/third_party/ambientcg/<id>/
# 用法: tools/fetch_ambientcg.sh --ids DiamondPlate008A,Metal016 [--res 2K] [--proxy http://127.0.0.1:7900]
# 只保留 Color / NormalGL / Roughness / Metalness / AmbientOcclusion / Opacity。
set -eu
zparseopts -D -E -F -- -ids:=o_ids -res:=o_res -proxy:=o_proxy
ids=(${(s:,:)${o_ids[-1]:-}})
if (( ! $#ids )); then
  echo "用法: $0 --ids a,b [--res 2K] [--proxy URL]" >&2
  exit 1
fi
res=${o_res[-1]:-2K}
curl_opts=(-fsSL --max-time 300)
[[ -n ${o_proxy[-1]:-} ]] && curl_opts+=(--proxy ${o_proxy[-1]})
root=${0:A:h:h}/assets/third_party/ambientcg
mkdir -p $root
keep='_(Color|NormalGL|Roughness|Metalness|AmbientOcclusion|Opacity)\.(jpg|png)$'

for id in $ids; do
  dir=$root/$id
  have=($dir/*_Color.*(N))
  if (( $#have )); then echo "skip   $id"; continue; fi
  mkdir -p $dir
  tmp=$(mktemp -d)
  zip=$tmp/$id.zip
  for i in 1 2 3; do
    curl $curl_opts -o $zip "https://ambientcg.com/get?file=${id}_$res-JPG.zip" && break
    if (( i == 3 )); then rm -rf $tmp; exit 1; fi
    echo "retry $i $id"
  done
  names=(${(f)"$(unzip -Z1 $zip | grep -E $keep)"})
  unzip -o -j -q $zip $names -d $dir
  rm -rf $tmp
  echo "texture $id"
done
