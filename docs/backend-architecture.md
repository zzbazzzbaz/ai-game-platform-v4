# 后端架构

## 1. 运行环境

| 项 | 值 |
| --- | --- |
| 语言 | Python 3.14 |
| 包管理 | uv |
| Web 框架 | FastAPI |
| ASGI Server | Uvicorn |
| Agent 框架 | Pydantic AI 2.68.0 |
| Agent 能力库 | pydantic-ai-harness 0.68.0 |
| 数据库 | PostgreSQL 17.11 |
| 数据库驱动 | asyncpg |
| ORM | SQLAlchemy 2.0（async） |
| 迁移 | Alembic |
| 沙箱 SDK | e2b 2.50.0 |
| 沙箱服务 | 阿里云 Agent Sandbox（E2B 协议） |
| 模型 | DeepSeek `deepseek:deepseek-flash` |
| 可观测性 | Logfire |

后端只有一个 Python 工程：`backend/pyproject.toml`。根目录不存放 `pyproject.toml`。

## 2. 目录结构

```text
pydantic-ai学习/
├── .env
├── .env.example
├── .python-version
├── .gitignore
├── Makefile
├── docker-compose.yml
├── docs/
│   ├── backend-architecture.md
│   ├── frontend-architecture.md
│   └── database-design.md
├── backend/
│   ├── pyproject.toml
│   ├── uv.lock
│   ├── alembic.ini
│   ├── migrations/
│   │   ├── env.py
│   │   └── versions/
│   │       ├── 0001_init.py
│   │       └── 0002_simplify_sandbox_sessions.py
│   ├── app/
│   │   ├── main.py
│   │   ├── lifespan.py
│   │   ├── dependencies.py
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── security.py
│   │   ├── errors.py
│   │   ├── dto/
│   │   │   ├── __init__.py
│   │   │   ├── auth.py
│   │   │   ├── chat.py
│   │   │   ├── conversation.py
│   │   │   ├── run.py
│   │   │   └── sandbox.py
│   │   ├── endpoints/
│   │   │   ├── __init__.py
│   │   │   ├── auth.py
│   │   │   ├── chat.py
│   │   │   ├── conversations.py
│   │   │   ├── runs.py
│   │   │   └── sandbox.py
│   │   ├── repositories/
│   │   │   ├── __init__.py
│   │   │   ├── models.py
│   │   │   ├── models.md
│   │   │   ├── conversation_store.py
│   │   │   ├── conversations.py
│   │   │   ├── runs.py
│   │   │   └── users.py
│   │   ├── runtime/
│   │   │   ├── __init__.py
│   │   │   ├── agent/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── factory.py
│   │   │   │   ├── model.py
│   │   │   │   ├── deps.py
│   │   │   │   ├── instructions.py
│   │   │   │   └── capabilities/
│   │   │   │       ├── permissions.py
│   │   │   │       └── planning.py
│   │   │   ├── runs/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── manager.py
│   │   │   │   ├── lifecycle.py
│   │   │   │   ├── hitl.py
│   │   │   │   └── stream.py
│   │   │   └── sandboxes/
│   │   │       ├── __init__.py
│   │   │       ├── registry.py
│   │   │       ├── files.py
│   │   │       ├── errors.py
│   │   │       └── reaper.py
│   │   └── services/
│   │       ├── __init__.py
│   │       ├── auth_service.py
│   │       ├── conversation_service.py
│   │       └── run_service.py
│   └── scripts/
│       ├── spike_local_agent.py
│       ├── spike_aliyun_sandbox.py
│       └── smoke_chat.py
└── frontend/
    └── src/
```

## 3. 分层职责

| 层 | 目录 | 职责 |
| --- | --- | --- |
| 应用入口 | `app/main.py` | FastAPI 实例、CORS、路由挂载、健康检查 |
| 生命周期 | `app/lifespan.py` | Logfire、运行时实例、遗留 run、APScheduler 启动与关闭 |
| 依赖 | `app/dependencies.py` | 当前用户、运行时实例与 FastAPI 依赖别名 |
| 接入层 | `app/endpoints/` | HTTP 路由、SSE、请求解析、错误映射 |
| 业务层 | `app/services/` | 认证、会话元数据、run 查询 |
| 运行时 | `app/runtime/` | Agent 组装、run 生命周期、HITL、沙箱、流式执行、空闲回收 |
| 数据访问 | `app/repositories/` | SQLAlchemy 模型、查询、`ConversationStore` |
| 基础设施 | `app/database.py`、`app/security.py` | 数据库连接、密码与会话令牌 |
| 通用 | `app/config.py`、`app/errors.py`、`app/dto/` | 配置、HTTP 错误构造、DTO |

运行时边界：

- `app/runtime/` 不导入 `app/services/` 或 `app/endpoints/`。
- Agent 组装、run 生命周期、HITL、沙箱、流式执行、空闲回收都在 `app/runtime/`。
- `app/services/` 只保留认证、会话元数据、run 查询等业务逻辑。
- `app/repositories/` 只负责持久化，不感知 Agent 运行时。
- `PostgresConversationStore` 是持久化适配器，留在 `app/repositories/`。

## 4. 请求流程

```mermaid
sequenceDiagram
  autonumber
  participant W as Web
  participant A as FastAPI
  participant R as RunManager
  participant S as SandboxRegistry
  participant G as Agent
  participant P as PostgreSQL
  participant E as 阿里云沙箱

  W->>A: POST /api/chat（SSE）
  A->>A: current_user
  A->>R: acquire(conversation_id)
  R->>P: INSERT runs（running）
  R->>S: ensure(conversation_id)
  S->>P: SELECT sandbox_sessions
  alt 没有 active 沙箱
    S->>E: AsyncSandbox.create(template)
    S->>P: INSERT sandbox_sessions
  end
  A->>G: 构建 Agent 并执行 run_stream
  G->>E: shell / read_file / write_file / grep
  E-->>G: 工具结果
  G-->>A: 事件流
  A-->>W: SSE
  G-->>R: DeferredToolRequests 或最终结果
  R->>P: UPDATE runs
  A-->>W: done
```

流程说明：

1. `POST /api/chat` 的请求体包含 `id`（conversation_id）和本轮 `messages`。
2. `current_user` 从会话 Cookie 解析当前用户。
3. `conversation_service.get_owned` 校验该 conversation 的 `user_id` 与当前用户一致。
4. `RunManager`（`app/runtime/runs/manager.py`）以 `conversation_id` 获取 Postgres advisory lock，并写入一条 `runs` 记录，状态为 `running`。
5. `SandboxRegistry.ensure` 查找该 conversation 的沙箱记录；存在则复用，不存在则创建并写入 `sandbox_sessions`。
6. `AgentFactory.build` 使用当前 conversation 的依赖构建 Agent。模型实例在应用启动时创建，由所有 run 复用。
7. `VercelAIAdapter.from_request` 解析请求，`run_stream` 以 `conversation_store` 加载历史、执行 Agent，`streaming_response` 编码 SSE，并在结束后保存历史。
8. `on_complete` 更新 `runs` 的状态、用量和结束时间，并更新 `sandbox_sessions.last_used_at`。
9. run 以 `DeferredToolRequests` 结束时，`runs.status` 置为 `waiting_approval`，待处理请求保存在 `conversations.deferred_tool_requests`。
10. 取消时，`runs.status` 置为 `cancelled`，`RunCancelled` 携带的消息写回 `ConversationStore`。

### 接口清单

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/auth/login` | 登录并写入会话 Cookie |
| `POST` | `/api/auth/register` | 注册并写入会话 Cookie |
| `POST` | `/api/auth/logout` | 退出登录 |
| `GET` | `/api/health` | 健康检查 |
| `GET` | `/api/me` | 当前用户 |
| `GET` | `/api/conversations` | 会话列表 |
| `POST` | `/api/conversations` | 新建会话 |
| `GET` | `/api/conversations/{id}` | 会话详情与消息 |
| `DELETE` | `/api/conversations/{id}` | 删除会话 |
| `POST` | `/api/chat` | 发送消息，返回 SSE |
| `POST` | `/api/conversations/{id}/cancel` | 取消当前 run |
| `GET` | `/api/runs/{id}` | run 状态与用量 |
| `GET` | `/api/conversations/{id}/sandbox/files?path=` | 沙箱目录 |
| `GET` | `/api/conversations/{id}/sandbox/file?path=` | 沙箱文件内容 |
| `GET` | `/api/conversations/{id}/sandbox/preview/{port}` | 沙箱端口预览地址 |
| `POST` | `/api/conversations/{id}/files` | 上传文件到沙箱 |

## 5. Agent 组装

`AgentFactory` 在每次 run 前构建 Agent，使用进程级模型实例和当前 conversation 的依赖。模型由 `app/runtime/agent/model.py` 的 `build_model()` 构建：`ConfiguredDeepSeekProvider` 显式传入 `DEEPSEEK_API_KEY` 和 `DEEPSEEK_BASE_URL`，不再依赖进程环境变量。

| Capability | 作用 |
| --- | --- |
| `E2BSandbox` | harness 内置的 E2B 工作区 capability；run 时通过 `workspace=WorkspaceRef(...)` 附着到 `SandboxRegistry` 登记的沙箱 |
| `Coder` | 文件读写、编辑、列目录、grep、shell、子任务委派、上下文清理与工具结果截断 |
| `Permissions` | 依据 `AgentDeps.approval_mode` 生成审批请求 |
| `Planning` | 计划工具；按 conversation 使用进程内存储 |

`AgentDeps` 字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `user_id` | `UUID` | 当前用户 |
| `conversation_id` | `str` | 当前会话 |
| `approval_mode` | `Literal['full', 'auto', 'read-only']` | 审批模式 |

组装代码位于 `app/runtime/agent/factory.py`：

```python
agent = Agent(
    model,
    deps_type=AgentDeps,
    capabilities=[
        E2BSandbox(client=..., template=..., sandbox_timeout=...),
        Coder(),
        Permissions(lambda ctx: ctx.deps.approval_mode),
        Planning(),
    ],
)
```

`Planning` 按 conversation 使用进程内存储，计划不落库，进程重启后清空。

`Coder` 自带的能力集合：

| 能力 | 作用 |
| --- | --- |
| `FileSystem` | `read_file`、`write_file`、`edit_file`、`list_files`、`grep` |
| `Shell` | `shell` 工具，命令在沙箱内执行 |
| `RepoContext` | 读取工作区中的 `AGENTS.md` / `CLAUDE.md` |
| `SubAgents` | `delegate_task`，把子任务交给同一 Agent 的新 run |
| `ClearToolResults` | 清理旧工具结果 |
| `ToolOutputLimits` | 截断超长工具结果 |
| `RepairToolArguments` | 修复格式错误的工具参数 |
| `Caching` | 提示词缓存 |

## 6. 会话与沙箱

### 会话

会话由 `ConversationStore` 管理，实现在 `app/repositories/conversation_store.py`。存储内容包含：

- 消息日志（`conversation_entries`）
- 累计用量（`conversations.usage`）
- 待审批请求（`conversations.deferred_tool_requests`）

会话归属由 `conversations.user_id` 维护。`conversation_scope` 传当前用户 ID 字符串；`ConversationStore` 读取时与 `user_id` 比对，写入时把 `scope` 映射为 `user_id`，数据库不单独存 scope 列。

### 沙箱

`sandbox_sessions` 保存 conversation 与沙箱实例的映射：

| 字段 | 说明 |
| --- | --- |
| `id` | 记录 ID |
| `conversation_id` | 所属会话，唯一 |
| `sandbox_id` | 阿里云沙箱 ID |
| `last_used_at` | 最近一次使用时间 |

`SandboxRegistry` 实现在 `app/runtime/sandboxes/registry.py`。行为：

1. 查询 `sandbox_sessions` 中该 conversation 的记录。
2. 存在时更新 `last_used_at`，返回 `WorkspaceRef(provider='e2b', id=sandbox_id)`。
3. 不存在时通过 `e2b.E2B` 客户端创建沙箱，写入 `sandbox_sessions`，再返回引用。
4. 运行结束或复用时更新 `last_used_at`。
5. 沙箱不可用时删除映射，下一次 run 重新创建。

`e2b.E2B` 客户端的连接参数来自环境变量：

| 参数 | 环境变量 |
| --- | --- |
| API Key | `E2B_API_KEY` |
| API URL | `E2B_API_URL` |
| Domain | `E2B_DOMAIN` |
| Template | `E2B_TEMPLATE` |

`E2B_TEMPLATE` 为空时使用阿里云默认模板。默认模板包含 Python 3.13、git、Node 20，不包含 `rg`；`Coder` 在缺少 `rg` 时使用 POSIX 搜索。

回收器实现在 `app/runtime/sandboxes/reaper.py`，由 `app/lifespan.py` 注册到 APScheduler，每 5 分钟执行一次。任务开始前先获取 PostgreSQL advisory lock，只有拿到锁的进程才扫描 `sandbox_sessions`；对 `last_used_at` 超过 30 分钟且没有运行中 run 的沙箱执行 `kill`，并删除记录。

预览与文件接口：

| 接口 | 行为 |
| --- | --- |
| `GET /api/conversations/{id}/sandbox/preview/{port}` | 调用沙箱 `get_host(port)`，返回可访问地址 |
| `POST /api/conversations/{id}/files` | 将上传内容写入沙箱工作目录 |

## 7. 流式输出与历史

### SSE

`POST /api/chat` 返回 `text/event-stream`。响应由 `VercelAIAdapter` 编码，前端使用 `useChat` 消费。

适配器参数：

| 参数 | 值 |
| --- | --- |
| `agent` | 当前 conversation 构建的 Agent |
| `conversation_store` | `PostgresConversationStore` |
| `conversation_scope` | 当前用户 ID 字符串 |
| `sdk_version` | `6`，启用工具审批流 |
| `on_complete` | 更新 `runs` 与 `sandbox_sessions` |
| `on_cancel` | 保存取消时的消息 |

流式生命周期由 `app/runtime/runs/stream.py` 的 `AgentRunStream` 管理：`on_complete` / `on_cancel` 回调、客户端断开时的取消与消息保存、沙箱不可用标记、响应后台收尾都在该类中完成。

传入 `conversation_store` 后，历史由服务端持有。前端每次只提交本轮新消息，适配器按 conversation id 加载完整历史并保存新增消息。

### 刷新与恢复

- `GET /api/conversations/{id}` 返回会话消息与最近一次 run 的状态。
- `GET /api/runs/{id}` 返回 run 的状态、时间与用量。
- 页面刷新后前端不接管未结束的 SSE 流；客户端断开后 run 记为 `cancelled`，并保存已产生的消息。
- 已结束的 run 从 `conversation_entries` 重建消息列表。

### 取消

`POST /api/conversations/{id}/cancel` 对 active run 触发 `CancellationToken`，适配器返回 `RunCancelled`，后端将其中的消息保存到 `ConversationStore`，并把 `runs.status` 置为 `cancelled`。若只有 `waiting_approval` 的 run，则直接把该 run 置为 `cancelled` 并清空 `conversations.deferred_tool_requests`。

## 8. 审批

审批由 `Permissions` 产生。模式与行为：

| 模式 | 文件写入 | 命令 |
| --- | --- | --- |
| `full` | 直接执行 | 直接执行 |
| `auto` | 直接执行 | 匹配 `ask_commands` 时请求审批 |
| `read-only` | 请求审批 | 请求审批 |

审批链路：

1. `Permissions` 对需要审批的调用抛出 `ApprovalRequired`。
2. run 以 `DeferredToolRequests` 结束。
3. `VercelAIAdapter` 在 `sdk_version=6` 下把待审批调用编码为 `tool-approval-request`，前端渲染 `ApprovalDialog`。
4. 用户批准或拒绝后，前端在下一次 `/api/chat` 请求中提交决定。
5. 适配器把决定转换为 `deferred_tool_results`，恢复 run。
6. 待审批状态由 `conversations.deferred_tool_requests` 保存；恢复后由 `DeferredToolResults` 和消息历史记录决定。

审批不单独建表。`conversations.deferred_tool_requests` 只保存当前待处理请求，恢复后会被下一次保存覆盖。

每次审批恢复产生一条新的 `runs` 记录，`parent_run_id` 指向暂停的 run。

自定义 HITL 参数：

- `ApprovalRequired(metadata={...})` 的 metadata 写入 `DeferredToolRequests.metadata[tool_call_id]`，随 `conversations.deferred_tool_requests` 落库。
- 恢复时 `DeferredToolResults.metadata[tool_call_id]` 传回，工具通过 `ctx.tool_call_metadata` 读取。
- `DeferredToolResults.answered_by[tool_call_id]` 记录决策人；不单独落库。

## 9. 异常与状态

HTTP 错误统一由 `app/errors.py` 的无参工厂函数生成。响应只包含固定提示，具体原因和上下文只写入后端日志。

`runs.status` 取值：

| 状态 | 含义 |
| --- | --- |
| `running` | 正在执行 |
| `waiting_approval` | 等待用户审批 |
| `completed` | 正常结束 |
| `cancelled` | 用户取消 |
| `failed` | 执行失败 |

`WorkspaceUnavailableError`：沙箱不可用。后端删除 `sandbox_sessions` 中的映射，下一次 run 重新创建沙箱。

`ConversationConflict`：同一 conversation 被并发保存。适配器把冲突转成 SSE error 事件，`runs.status` 记为 `failed`。

## 10. 配置

配置由 `app/config.py` 读取，只使用根目录 `.env`。`Settings` 不提供默认值，缺少任一配置键时启动失败。

| 环境变量 | 说明 |
| --- | --- |
| `MODEL` | 模型字符串，值为 `deepseek:deepseek-flash` |
| `DEEPSEEK_API_KEY` | DeepSeek API Key |
| `DEEPSEEK_BASE_URL` | DeepSeek API Base URL，`https://api.deepseek.com` |
| `DATABASE_URL` | `postgresql+asyncpg://agent:agent@localhost:5432/agent` |
| `SESSION_SECRET` | 会话 Cookie 签名密钥 |
| `SESSION_COOKIE` | 会话 Cookie 名称，`.env` 中为 `agent_session` |
| `SESSION_TTL_SECONDS` | 会话有效期，`.env` 中为 `2592000` |
| `E2B_API_KEY` | 阿里云 Agent Sandbox API Key |
| `E2B_API_URL` | `https://api.<region>.sandbox.aliyuncs.com` |
| `E2B_DOMAIN` | `<region>.sandbox.aliyuncs.com` |
| `E2B_TEMPLATE` | 沙箱模板名称；为空时使用默认模板 |
| `LOGFIRE_TOKEN` | Logfire 写入 Token，可为空 |
| `LOGFIRE_ENVIRONMENT` | Logfire 环境名，`.env` 中为 `development` |
| `SANDBOX_TIMEOUT` | 沙箱生命周期秒数，`.env` 中为 `3600` |
| `SANDBOX_IDLE_SECONDS` | 空闲回收阈值秒数，`.env` 中为 `1800` |

## 11. 启动

项目根目录提供 `Makefile`。

首次准备：

```bash
make up
make install
make migrate
```

开发模式：

```bash
make dev
```

后端监听 `:8000`，前端监听 `:5173`。也可以分别启动：

```bash
make run-api
make run-ui
```

其他命令：

```bash
make build   # 前端生产构建
make check   # ruff、ty、前端类型检查
make smoke   # 真实模型 + 沙箱 smoke，需先启动后端
```

沙箱回收任务由应用 lifespan 内的 APScheduler 启动，不需要单独进程。

`uv` 使用根目录的 `.python-version`（3.14），虚拟环境位于 `backend/.venv`。
