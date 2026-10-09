# 被 capture.sh / rebuild_models.sh 引用（source）。
# godot_window 参数...：运行一个要渲染画面的 Godot（截图、烘焙 GI），输出打到 stdout。
# 默认用 open -g 在后台启动，窗口放到屏幕外，不抢焦点、不打断手上的工作；FOREGROUND=1 时照常在前台开窗口。
# Godot 不在 /Applications 下时用环境变量 GODOT 指定可执行文件。
godot=${GODOT:-/Applications/Godot.app/Contents/MacOS/Godot}

godot_window() {
  if [[ -n ${FOREGROUND:-} ]]; then
    "$godot" "$@" 2>&1
    return
  fi
  local app=${godot%/Contents/MacOS/*}
  local log=$(mktemp -t godot_bg)
  open -g -n -W -a "$app" --stdout "$log" --stderr "$log" --args --position 20000,20000 "$@"
  cat "$log"
  rm -f "$log"
}
