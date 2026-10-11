# 被 capture.sh / rebuild_models.sh 引用（source）。
# godot_window 参数...：运行一个要渲染画面的 Godot（截图、烘焙 GI），输出打到 stdout。
# 默认在后台运行：注入 tools/nofocus.m 编出来的动态库，Godot 不激活自己、不抢焦点、不出现在 Dock，
# 窗口完全透明且不接收鼠标，不会打断手上的工作；FOREGROUND=1 时照常在前台开窗口。
# 一律用 Dummy 音频驱动：后台跑的 Godot 绝不往扬声器/耳机出声（要听声音用 tools/record.sh 录成文件再放）。
# 环境变量 LIMIT=秒数：超时强行结束（编辑器卡在对话框、烘焙卡死时不会一直挂着），返回 124。
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
    "$godot" --audio-driver Dummy "$@" 2>&1
    return
  fi
  local lib
  if lib=$(_nofocus_lib); then
    if [[ -z ${LIMIT:-} ]]; then
      DYLD_INSERT_LIBRARIES=$lib "$godot" --audio-driver Dummy --position 20000,20000 "$@" 2>&1
      return
    fi
    # 超时看门狗（macOS 没有 timeout 命令；不能借 perl 的 alarm：系统自带的 perl 受 SIP 保护，会把 DYLD_INSERT_LIBRARIES 丢掉）
    DYLD_INSERT_LIBRARIES=$lib "$godot" --audio-driver Dummy --position 20000,20000 "$@" 2>&1 &
    local pid=$! flag=$(mktemp -t godot_bg_limit)
    rm -f $flag
    ( sleep $LIMIT </dev/null >/dev/null 2>&1; touch $flag; if kill $pid 2>/dev/null; then echo "godot_bg: 超过 ${LIMIT} 秒，强行结束" >&2; fi ) >/dev/null &
    local dog=$! rc=0
    wait $pid || rc=$?
    kill $dog 2>/dev/null || true
    if [[ -f $flag ]] && (( rc )); then
      rm -f $flag
      return 124
    fi
    rm -f $flag
    return $rc
  fi
  # 编不出注入库（比如没装 Xcode 命令行工具）：退回 open -g，窗口放屏幕外，但 Godot 启动时仍会抢一下焦点
  echo "godot_bg: 注入库编译失败，退回 open -g（可能会抢焦点）" >&2
  local app=${godot%/Contents/MacOS/*}
  local log=$(mktemp -t godot_bg)
  open -g -n -W -a "$app" --stdout "$log" --stderr "$log" --args --audio-driver Dummy --position 20000,20000 "$@"
  cat "$log"
  rm -f "$log"
}
