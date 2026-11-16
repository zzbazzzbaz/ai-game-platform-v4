# 游戏工程模板（sandbox/game-template）

「一游戏一服务」的工程骨架：Express + Socket.IO + Phaser + PostgreSQL，同源单服务，
发布到 CloudBase 云托管（容器型 + Dockerfile）。

## 文件边界（规格 R-AGT-1）

| 区域 | 文件 | 谁改 |
|---|---|---|
| **平台维护** | `package.json`、`index.html`、`server/index.js`、`db/migrate.js`、`scripts/`、`Dockerfile` | 平台（禁止生成器修改） |
| **生成区** | `src/**`（Phaser 客户端）、`shared/**`（前后端共用纯逻辑） | AI / 用户 |

## 脚本

| 命令 | 作用 |
|---|---|
| `npm run dev` | esbuild 监听 + `node --watch server/index.js`（开发态，沙盒内由平台保活） |
| `npm run build` | 打包客户端到 `dist/game.js`（发布前必须成功） |
| `npm run start` | 生产启动（NODE_ENV=production） |
| `npm run db:migrate` | 连接注入的 `DATABASE_URL` 执行迁移 |

## 约定

- 端口：`PORT`（默认 3000；云托管注入 3000）。
- 客户端一律用相对路径访问自身接口（同源）。
- 健康检查：`GET /api/health`。
- WebSocket：云托管 60s 空闲断开 → 客户端每 10s `socket.emit("ping")`（服务端回 `pong`）。
- 数据库：只读环境变量 `DATABASE_URL`（每游戏独占库）；禁止硬编码连接串。
- 依赖目录 `node_modules` 在沙盒里软链到 `/opt/deps`（不进 COS 挂载层）。
