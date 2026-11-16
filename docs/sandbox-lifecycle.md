# 沙盒生命周期

## 归属

一个 game 对应一个工作区和一个沙盒。`games.id` 是沙盒归属键，`sandbox_sessions.game_id` 唯一。

## 平台语义

- 沙盒由阿里云 Agent Sandbox 提供，通过 E2B 兼容协议调用。
- 模板基于官方 `runtime-v2/base`，在构建步骤中安装游戏运行环境；规格 1 vCPU / 1024 MB。
- 预览服务由后端在沙盒创建/恢复后执行 `/opt/sandbox/start-services.sh` 启动。
- 创建参数：`timeout=600`、`on_timeout=pause`、`auto_resume=true`。
- `connect(timeout=600)`、`files.*`、`commands.*` 会刷新空闲计时。
- `get_info`、`list` 是控制面查询，不唤醒、不续期。
- 预览 HTTP 流量会唤醒已暂停沙盒，但不会刷新 `end_at`。
- 因此续签统一走 `SandboxRegistry.ensure()` 的 `connect(timeout=600)`。

## 状态

```text
active      有 sandbox_id，运行或暂停
archiving   正在打包/上传，或已上传待 kill
archived    沙盒已 kill，snapshot_key 指向 OSS 对象
restoring   正在创建新沙盒并从 OSS 解包
```

## 续签

| 场景 | 行为 |
| --- | --- |
| Agent run | 每 240 秒 `touch()` 一次；工具调用本身的 envd 操作也会续期 |
| 预览页 | 前端每 240 秒调用 `POST /api/conversations/{id}/sandbox/touch` |
| 打开游戏 | `open` 先 `ensure()`，再 `connect(600)` |
| run 结束 | 停止心跳；600 秒后平台自动暂停 |

## 归档

- APScheduler 每 300 秒扫描一次。
- 扫描 `SandboxQuery(metadata={"app": "ai-game-platform-v4"}, state=[PAUSED])`。
- 满足 `now - end_at >= 7200` 的实例进入归档。
- 归档期间持有 `sandbox:<game_id>` advisory lock，`ensure` 会等待。
- 归档步骤：
  1. `connect(timeout=600)` 恢复
  2. 停止 `dev.mjs` 游戏服务
  3. 打包 `/home/user/workspace`
  4. 用 OSS 预签名 PUT 从沙盒内直接上传
  5. 先写 `snapshot_key`，再 kill
  6. 状态置 `archived`，`sandbox_id=NULL`
- 打包排除：`node_modules`、`.runtime`、`dist`、`input`、`.git`、`.env`、`.cache`、`__pycache__`、`.pydantic-ai-harness`。
- 失败时暂停沙盒，`archive_retry_at = now + 300`，最多记录 `archive_attempts` 和 `last_error`。

## 恢复

- `ensure()` 发现 `archived` 或 `sandbox_id` 不存在时执行恢复。
- 创建新沙盒，元数据带 `game_id`。
- 用 OSS 预签名 GET 在沙盒内下载，校验 `sha256`。
- 删除旧工作区，解包到 `/home/user/workspace`，执行 `prepare-workspace.sh`。
- 恢复失败时 kill 新沙盒，保留 `archived` 状态，接口返回 503；不静默创建空工作区。

## OSS

```text
<OSS_PREFIX>/games/<game_id>/workspace/<UTC timestamp>.tar.gz
```

快照字段落在 `sandbox_sessions`：

- `snapshot_key`
- `snapshot_at`
- `snapshot_bytes`
- `snapshot_sha256`

## 删除

删除 game 时持有工作区锁，kill 当前沙盒，删除该 game 的 OSS 前缀，再删除数据库记录。
