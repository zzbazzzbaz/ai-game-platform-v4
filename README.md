# AI 游戏平台 v4

在原有全栈 Agent 应用（认证、会话、SSE 对话、HITL、文件/预览）基础上，合并 v3 的按 game 沙盒生命周期：600 秒续签、暂停后归档到阿里云 OSS、下次从 OSS 恢复。

## 技术栈

| 层 | 技术 |
| --- | --- |
| 前端 | React 19 + Vite + Vercel AI SDK `useChat` |
| 后端 | FastAPI + Pydantic AI 2.68 + pydantic-ai-harness |
| 数据库 | PostgreSQL 17.11 + SQLAlchemy async + Alembic |
| 沙盒 | 阿里云 Agent Sandbox（E2B 协议，二代 runtime） |
| 快照 | 阿里云 OSS |
| 模型 | DeepSeek `deepseek:deepseek-flash` |

## 目录

```text
backend/                 FastAPI、Agent、沙盒注册表、OSS 快照、APScheduler
frontend/                React 聊天界面、文件树、预览、审批
sandbox/                 沙盒镜像、游戏模板、Phaser 技能库
.github/workflows/       Docker Hub 镜像构建
docs/                    架构、数据库、沙盒生命周期
```

## 沙盒模型

- 一个 game 对应一个工作区和一个沙盒。
- 会话通过 `conversations.game_id` 关联 game；默认创建会话时自动新建 game。
- 沙盒内工作区：`/home/user/workspace`。
- 600 秒无 envd 操作自动暂停；`ensure/touch/connect` 续签 600 秒。
- Agent run 和预览页各有 240 秒心跳。
- 暂停满 2 小时后归档到：

```text
ai-game-platform/games/<game_id>/workspace/<timestamp>.tar.gz
```

- 归档后 kill 沙盒；下次打开新建沙盒并从 OSS 解包。
- 归档排除 `node_modules`、`.runtime`、`dist`、`input`、`.git`、`.env` 等。

## 本地启动

```bash
cp .env.example .env
# 填写 DEEPSEEK_API_KEY、E2B_API_KEY、OSS 凭证
make up
make install
make migrate
make dev
```

- 后端：`http://127.0.0.1:8000`
- 前端：`http://127.0.0.1:5173`

## 沙盒模板

阿里云二代 runtime 的自定义模板只接受官方公共镜像或 ACR EE，不能直接使用 Docker Hub 镜像。Docker Hub 镜像仍由 GitHub Actions 构建并公开：

```text
docker.io/<DOCKERHUB_USERNAME>/ai-game-platform-sandbox:sandbox-v4
```

阿里云模板使用官方 `runtime-v2/base:v0.0.53` + 构建步骤安装 Playwright、noVNC 和游戏模板：

```bash
make template
```

需要：

- 阿里云 CLI 已登录
- `.env` 中 `FCSANDBOX_TEAM_ID`、`ALIYUN_REGION`
- OSS 可写

模板构建完成后把输出的 `TEMPLATE_ID` 写入 `.env` 的 `E2B_TEMPLATE`。

## 验证

```bash
make smoke        # 真实沙盒：创建 → 写文件 → 归档 OSS → 恢复 → 校验
make agent-smoke  # 真实模型 + 真实沙盒聊天
```

## OSS 凭证

当前 `.env` 可以直接使用阿里云 CLI OAuth 的临时 STS 凭证：

```bash
cd backend
uv run python scripts/refresh_oss_token.py
```

过期后重新执行并重启后端，或改用永久 AK/SK 并清空 `OSS_SECURITY_TOKEN`。本机访问 OSS 需要代理时设置 `OSS_PROXY`。

## 说明

- 旧会话在迁移 `0003` 中各自生成一个 game，game ID 等于原会话 ID。
- 旧 `sandbox_sessions` 映射在迁移时清空；下一次对话按新 game 模板重建沙盒。
- 删除会话不会删除 game/沙盒；删除 game 会 kill 沙盒并删除 OSS 前缀。
