#!/bin/zsh
# 打印 .glb 里每个网格每个图元（材质）的顶点数和有哪些顶点属性。排查导出问题用。
# 用法: tools/glb_info.sh assets/models/submarine_cockpit.glb [网格名过滤]
set -eu
if (( $# < 1 )); then
  echo "用法: $0 文件.glb [网格名过滤]" >&2
  exit 1
fi
glb=$1
# glb 头 12 字节，接着是 JSON 块：4 字节长度（小端）+ 4 字节类型 + JSON
len=$(od -An -t u4 -j 12 -N 4 "$glb" | tr -d ' ')
tail -c +21 "$glb" | head -c "$len" |
  jq -r --arg f "${2:-}" '
    . as $g | $g.meshes[]
    | select($f == "" or (.name | ascii_downcase | contains($f | ascii_downcase))) as $m
    | $m.primitives[]
    | [$m.name,
       (if .material != null then $g.materials[.material].name else "-" end),
       $g.accessors[.attributes.POSITION].count,
       (.attributes | keys_unsorted | join(","))] | @tsv' |
  while IFS=$'\t' read -r mesh mat n attrs; do
    printf "%-14s %-22s %8s  %s\n" "$mesh" "$mat" "$n" "$attrs"
  done
