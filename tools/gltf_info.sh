#!/bin/zsh
# 打印 glTF 的节点、网格包围盒（米）和材质名，摆道具时用来查尺寸。
# 用法: tools/gltf_info.sh power_box_01 television_02 ...
set -eu
root=${0:A:h:h}/assets/third_party/polyhaven/models
for id in "$@"; do
  jq -r --arg id "$id" '
    def f3: (. * 1000 | round) as $v | ($v | if . < 0 then -. else . end) as $a
      | (if $v < 0 then "-" else "" end) + ($a / 1000 | floor | tostring) + "."
        + (($a % 1000 + 1000) | tostring | .[1:]);
    def vec: map(f3) | join(",");
    . as $g
    | "== \($id)  materials: \([$g.materials[]?.name] | join(", "))",
      (range(0; $g.nodes | length) as $i | $g.nodes[$i] as $n
       | "  node[\($i)] \($n.name)"
         + (if $n.translation then "  t=(\($n.translation | vec))" else "" end)
         + (if $n.scale then "  s=(\($n.scale | vec))" else "" end)
         + (if $n.mesh != null then
              [$g.meshes[$n.mesh].primitives[] | $g.accessors[.attributes.POSITION]] as $acc
              | [range(3) as $k | [$acc[].min[$k]] | min] as $mn
              | [range(3) as $k | [$acc[].max[$k]] | max] as $mx
              | "  size=(\([range(3) as $k | $mx[$k] - $mn[$k]] | vec))  min=(\($mn | vec))"
            else "" end)
         + (if $n.children then "  children=\($n.children | map(tostring) | join(","))" else "" end))
  ' "$root/$id/${id}_2k.gltf"
done
