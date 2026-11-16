#!/bin/bash
# 阿里云模板 ready_command：确认显示栈已经就绪。
set -e
[ -S /tmp/.X11-unix/X0 ]
pgrep -f "websockify.*9000" >/dev/null
