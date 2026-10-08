#!/bin/zsh
# 从 Poly Haven (CC0) 下载模型和贴图到 assets/third_party/polyhaven/
# 用法: tools/fetch_polyhaven.sh [--models a,b] [--textures c,d] [--res 2k]
set -eu
zparseopts -D -E -F -- -models:=o_models -textures:=o_textures -res:=o_res
models=(${(s:,:)${o_models[-1]:-}})
textures=(${(s:,:)${o_textures[-1]:-}})
res=${o_res[-1]:-2k}
root=${0:A:h:h}/assets/third_party/polyhaven

# 先下到 .part，完整下完再改名，断线不会留下半截文件；失败重试 3 次
get_file() {
  local url=$1 dest=$2 i
  [[ -e $dest ]] && return 0
  mkdir -p ${dest:h}
  for i in 1 2 3; do
    if curl -fsSL --max-time 300 -o "$dest.part" "$url"; then
      mv -f "$dest.part" "$dest"
      return 0
    fi
    (( i < 3 )) && echo "retry $i $url"
  done
  return 1
}

for id in $models; do
  dir=$root/models/$id
  # 第一行是 .gltf 本身，后面是它引用的 .bin 和贴图（相对路径 \t 链接）
  curl -fsSL "https://api.polyhaven.com/files/$id" |
    jq -r --arg res $res '.gltf[$res].gltf | "\(.url | split("/")[-1])\t\(.url)", ((.include // {}) | to_entries[] | "\(.key)\t\(.value.url)")' |
    while IFS=$'\t' read -r name url; do
      get_file $url $dir/$name
    done
  echo "model  $id"
done

# 贴图只取颜色、法线(OpenGL)、ARM(AO/粗糙度/金属度) 三张
for id in $textures; do
  dir=$root/textures/$id
  curl -fsSL "https://api.polyhaven.com/files/$id" |
    jq -r --arg res $res '.Diffuse, .nor_gl, .arm | .[$res].jpg.url // empty' |
    while read -r url; do
      get_file $url $dir/${url:t}
    done
  echo "texture $id"
done
