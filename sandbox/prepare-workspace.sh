#!/bin/bash
# 工作区准备（幂等）：
#   1. 工作区为空时从镜像模板播种
#   2. node_modules 软链到镜像内依赖，不进入 OSS 快照
set -u

TEMPLATE=/opt/game-template
WORK=/home/user/workspace

if [ ! -f "$WORK/package.json" ] && [ -d "$TEMPLATE" ]; then
  echo "[prepare] 播种工作区：$TEMPLATE → $WORK"
  mkdir -p "$WORK"
  (cd "$TEMPLATE" && tar --exclude=./node_modules --exclude=./.runtime --exclude=./dist -cf - .) \
    | (cd "$WORK" && tar -xf -)
fi

if [ ! -e "$WORK/node_modules" ]; then
  rm -f "$WORK/node_modules"
  ln -s "$TEMPLATE/node_modules" "$WORK/node_modules"
  echo "[prepare] node_modules → $TEMPLATE/node_modules"
fi

chown -R user:user "$WORK" 2>/dev/null || true
