#!/bin/bash
# 预览浏览器守护：等游戏服务就绪后拉起 Chromium；退出后自动重启。
set -u

export DISPLAY="${DISPLAY:-:0}"
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-/opt/ms-playwright}"

CHROME_BIN=$(find "$PLAYWRIGHT_BROWSERS_PATH" -path '*/chrome-linux*/chrome' -type f 2>/dev/null | head -n1)
if [ -z "$CHROME_BIN" ]; then
  echo "[browser] 未找到 Chromium（$PLAYWRIGHT_BROWSERS_PATH），跳过预览浏览器"
  exit 0
fi

ready() {
  curl -sf -m 2 -o /dev/null http://127.0.0.1:3000/api/health \
    && curl -sf -m 2 -o /dev/null http://127.0.0.1:3000/dist/game.js
}

while true; do
  until ready; do sleep 2; done
  echo "[browser] 启动 Chromium：$CHROME_BIN"
  "$CHROME_BIN" \
    --no-sandbox --disable-setuid-sandbox --disable-dev-shm-usage \
    --no-first-run --no-default-browser-check \
    --autoplay-policy=no-user-gesture-required \
    --enable-unsafe-swiftshader \
    --remote-debugging-port=9222 --remote-debugging-address=127.0.0.1 \
    --user-data-dir=/tmp/chromium-profile \
    --disk-cache-dir=/tmp/chromium-cache \
    --window-position=0,0 --window-size=1280,720 \
    --app=http://127.0.0.1:3000
  echo "[browser] Chromium 退出，3s 后检查重启"
  sleep 3
done
