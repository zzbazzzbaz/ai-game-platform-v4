#!/bin/bash
# 沙盒启动时由阿里云模板的 start_command 调用。
# 只负责拉起预览所需的常驻进程，必须快速返回；envd 已由平台入口启动。
set -u

export DISPLAY=:0
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-/opt/ms-playwright}"
LOG_DIR=/tmp
mkdir -p "$LOG_DIR" /tmp/.X11-unix

start_once() {
  local name=$1
  shift
  if ! pgrep -f "$name" >/dev/null 2>&1; then
    nohup "$@" >>"$LOG_DIR/${name}.log" 2>&1 &
  fi
}

# 虚拟显示
if ! pgrep -f "Xvfb :0" >/dev/null 2>&1; then
  rm -f /tmp/.X0-lock
  nohup Xvfb :0 -screen 0 1280x720x24 -nolisten tcp -ac >>"$LOG_DIR/xvfb.log" 2>&1 &
fi
for _ in $(seq 1 100); do
  [ -S /tmp/.X11-unix/X0 ] && break
  sleep 0.1
done

# VNC 只监听本机，9000 对外提供 noVNC 页面
if ! pgrep -f "x11vnc -display :0" >/dev/null 2>&1; then
  nohup x11vnc -display :0 -forever -shared -nopw -localhost -rfbport 5900 -quiet \
    >>"$LOG_DIR/x11vnc.log" 2>&1 &
fi
if ! pgrep -f "websockify.*9000" >/dev/null 2>&1; then
  nohup websockify --web=/usr/share/novnc 9000 127.0.0.1:5900 \
    >>"$LOG_DIR/websockify.log" 2>&1 &
fi

# 浏览器守护：等游戏服务就绪后打开 Chromium
if ! pgrep -f "browser-kiosk.sh" >/dev/null 2>&1; then
  nohup /opt/sandbox/browser-kiosk.sh >>"$LOG_DIR/browser.log" 2>&1 &
fi

exit 0
