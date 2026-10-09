# 被 capture.sh / rebuild_models.sh 引用（source）。
# godot_window 参数...：运行一个要渲染画面的 Godot（截图、烘焙 GI），输出打到 stdout。
# 默认在后台运行：注入 tools/nofocus.m 编出来的动态库，Godot 不激活自己、不抢焦点、不出现在 Dock，
# 窗口完全透明且不接收鼠标，不会打断手上的工作；FOREGROUND=1 时照常在前台开窗口。
# Godot 不在 /Applications 下时用环境变量 GODOT 指定可执行文件。
godot=${GODOT:-/Applications/Godot.app/Contents/MacOS/Godot}

# 按需编译注入库（源文件更新过就重编），放在 .godot/ 下，不进 git
_nofocus_lib() {
  local src=${${(%):-%x}:A:h}/nofocus.m
  local lib=${src:h:h}/.godot/nofocus.dylib
  if [[ ! -f $lib || $src -nt $lib ]]; then
    mkdir -p ${lib:h}
    clang -dynamiclib -fobjc-arc -framework AppKit -o $lib $src >&2 || return 1
  fi
  echo $lib
}

godot_window() {
  if [[ -n ${FOREGROUND:-} ]]; then
    "$godot" "$@" 2>&1
    return
  fi
  local lib
  if lib=$(_nofocus_lib); then
    DYLD_INSERT_LIBRARIES=$lib "$godot" --position 20000,20000 "$@" 2>&1
    return
  fi
  # 编不出注入库（比如没装 Xcode 命令行工具）：退回 open -g，窗口放屏幕外，但 Godot 启动时仍会抢一下焦点
  echo "godot_bg: 注入库编译失败，退回 open -g（可能会抢焦点）" >&2
  local app=${godot%/Contents/MacOS/*}
  local log=$(mktemp -t godot_bg)
  open -g -n -W -a "$app" --stdout "$log" --stderr "$log" --args --position 20000,20000 "$@"
  cat "$log"
  rm -f "$log"
}
