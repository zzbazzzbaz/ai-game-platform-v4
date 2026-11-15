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
│   │       └── 0001_init.py
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── db.py
│   │   ├── models.py
│   │   ├── auth/
│   │   │   ├── router.py
│   │   │   ├── deps.py
│   │   │   └── security.py
│   │   ├── api/
│   │   │   ├── chat.py
│   │   │   ├── conversations.py
│   │   │   ├── runs.py
│   │   │   └── sandbox.py
│   │   ├── agent/
│   │   │   ├── factory.py
│   │   │   ├── deps.py
│   │   │   ├── instructions.py
│   │   │   └── capabilities/
│   │   │       ├── workspace.py
│   │   │       ├── permissions.py
│   │   │       └── planning.py
│   │   ├── runtime/
│   │   │   ├── runs.py
│   │   │   ├── sandboxes.py
│   │   │   └── reaper.py
│   │   └── store/
│   │       └── conversations.py
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
| 接入层 | `app/api/` | HTTP 路由、SSE、请求参数校验 |
| 认证 | `app/auth/` | 登录、会话 Cookie、当前用户解析 |
| 运行时 | `app/runtime/` | 运行锁、运行记录、沙箱登记、审批记录、空闲回收 |
| Agent | `app/agent/` | 模型、指令、依赖、capability 组装 |
| 存储 | `app/store/` | `ConversationStore` 的 Postgres 实现 |
| 表映射 | `app/models.py` | SQLAlchemy 模型 |
| 数据库连接 | `app/db.py` | async engine、session factory |
| 配置 | `app/config.py` | 环境变量读取 |

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
3. `ChatService` 校验该 conversation 的 `user_id` 与当前用户一致。
4. `RunManager` 以 `conversation_id` 获取 Postgres advisory lock，并写入一条 `runs` 记录，状态为 `running`。
5. `SandboxRegistry.ensure` 查找该 conversation 的 `active` 沙箱；存在则复用，不存在则创建并写入 `sandbox_sessions`。
6. `AgentFactory.build` 使用当前 conversation 的依赖构建 Agent。模型实例在应用启动时创建，由所有 run 复用。
7. `VercelAIAdapter.dispatch_request` 以 `conversation_store` 加载历史、执行 Agent、编码 SSE，并在结束后保存历史。
8. `on_complete` 更新 `runs` 的状态、用量和结束时间，并更新 `sandbox_sessions.last_used_at`。
9. run 以 `DeferredToolRequests` 结束时，`runs.status` 置为 `waiting_approval`，待处理请求保存在 `conversations.deferred_tool_requests`。
10. 取消时，`runs.status` 置为 `cancelled`，`RunCancelled` 携带的消息写回 `ConversationStore`。

### 接口清单

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/auth/login` | 登录并写入会话 Cookie |
| `POST` | `/api/auth/logout` | 退出登录 |
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

`AgentFactory` 在每次 run 前构建 Agent，使用进程级模型实例和当前 conversation 的依赖。

| Capability | 作用 |
| --- | --- |
| `ConversationWorkspace` | 从 `AgentDeps.sandbox_ref` 解析工作区；沙箱由 `SandboxRegistry` 在 run 前创建并登记 |
| `Coder` | 文件读写、编辑、列目录、grep、shell、子任务委派、上下文清理与工具结果截断 |
| `Permissions` | 依据 `AgentDeps.approval_mode` 生成审批请求 |
| `Planning` | 计划工具；使用默认内存存储 |

`AgentDeps` 字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `user_id` | `UUID` | 当前用户 |
| `conversation_id` | `str` | 当前会话 |
| `sandbox_ref` | `WorkspaceRef \| None` | 当前会话的沙箱引用 |
| `approval_mode` | `Literal['full', 'auto', 'read-only']` | 审批模式 |

组装代码位于 `app/agent/factory.py`：

```python
agent = Agent(
    model,
    deps_type=AgentDeps,
    capabilities=[
        ConversationWorkspace(),
        Coder(),
        Permissions(lambda ctx: ctx.deps.approval_mode),
        Planning(),
    ],
)
```

`Planning` 使用默认内存存储，计划只存在于当前 run 的工具结果中，不落库。

`Coder` 自带的能力集合：

| 能力 | 作用 |
| --- | --- |
| `FileSystem` | `read_file`、`write_file`、`edit_file`、`list_files`、`grep` |
| `Shell` | `shell` 工具，命令在沙箱内执行 |
| `RepoContext` | 读取工作区中的 `AGENTS.md` / `CLAUDE.md` |
| `SubAgents` | `delegate_task`，把子任务交给同一 Agent 的新 run |
| `ClearToolResults` | 清理旧工具结果 |
| `WarnNearLimits` | 接近上下文上限时提示 |
| `ToolOutputLimits` | 截断超长工具结果 |
| `RepairToolArguments` | 修复格式错误的工具参数 |
| `Caching` | 提示词缓存 |

## 6. 会话与沙箱

### 会话

会话由 `ConversationStore` 管理。存储内容包含：

- 消息日志（`conversation_entries`）
- 累计用量（`conversations.usage`）
- 待审批请求（`conversations.deferred_tool_requests`）

会话归属由 `conversations.user_id` 维护。`conversation_scope` 传当前用户 ID 字符串；`ConversationStore` 读取时与 `user_id` 比对，写入时把 `scope` 映射为 `user_id`，数据库不单独存 scope 列。

### 沙箱

`sandbox_sessions` 保存 conversation 与沙箱实例的映射：

| 字段 | 说明 |
| --- | --- |
| `provider` | 固定为 `e2b` |
| `sandbox_id` | 阿里云沙箱 ID |
| `template` | 创建时使用的模板 |
| `status` | `active` / `paused` / `dead` |
| `last_used_at` | 最近一次使用时间 |
| `expires_at` | 过期时间 |

`SandboxRegistry` 的行为：

1. 查询 `sandbox_sessions` 中该 conversation 的 `active` 记录。
2. 存在时返回 `WorkspaceRef(provider='e2b', id=sandbox_id)`。
3. 不存在时通过 `e2b.E2B` 客户端创建沙箱，写入 `sandbox_sessions`，再返回引用。
4. 运行结束更新 `last_used_at`。
5. 沙箱不可用时把记录标记为 `dead`，下一次 run 重新创建。

`e2b.E2B` 客户端的连接参数来自环境变量：

| 参数 | 环境变量 |
| --- | --- |
| API Key | `E2B_API_KEY` |
| API URL | `E2B_API_URL` |
| Domain | `E2B_DOMAIN` |
| Template | `E2B_TEMPLATE` |

`E2B_TEMPLATE` 为空时使用阿里云默认模板。默认模板包含 Python 3.13、git、Node 20，不包含 `rg`；`Coder` 在缺少 `rg` 时使用 POSIX 搜索。

`reaper` 每 5 分钟扫描一次 `sandbox_sessions`，对 `last_used_at` 超过 30 分钟的 `active` 沙箱执行 `pause` 或 `kill`，并更新状态。

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

传入 `conversation_store` 后，历史由服务端持有。前端每次只提交本轮新消息，适配器按 conversation id 加载完整历史并保存新增消息。

### 刷新与恢复

- `GET /api/conversations/{id}` 返回会话消息与最近一次 run 的状态。
- `GET /api/runs/{id}` 返回 run 的状态、时间与用量。
- 正在运行的 run 在页面刷新后显示为 `running`；前端不接管未结束的 SSE 流。
- 已结束的 run 从 `conversation_entries` 重建消息列表。

### 取消

`POST /api/conversations/{id}/cancel` 查找该 conversation 的 `running` 或 `waiting_approval` run，取消对应的 asyncio Task。适配器返回 `RunCancelled`，后端将其中的消息保存到 `ConversationStore`，并把 `runs.status` 置为 `cancelled`。

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

`runs.status` 取值：

| 状态 | 含义 |
| --- | --- |
| `running` | 正在执行 |
| `waiting_approval` | 等待用户审批 |
| `completed` | 正常结束 |
| `cancelled` | 用户取消 |
| `failed` | 执行失败 |

`WorkspaceUnavailableError`：沙箱不可用。后端把 `sandbox_sessions.status` 置为 `dead`，下一次 run 重新创建沙箱。

`ConversationConflict`：同一 conversation 被并发保存。后端返回 `409`，前端提示会话正在运行。

## 10. 配置

配置由 `app/config.py` 读取。加载顺序：根目录 `.env`，然后 `backend/.env`，后者覆盖前者。

| 环境变量 | 说明 |
| --- | --- |
| `MODEL` | 模型字符串，值为 `deepseek:deepseek-flash` |
| `DEEPSEEK_API_KEY` | DeepSeek API Key |
| `DATABASE_URL` | `postgresql+asyncpg://agent:agent@localhost:5432/agent` |
| `SESSION_SECRET` | 会话 Cookie 签名密钥 |
| `E2B_API_KEY` | 阿里云 Agent Sandbox API Key |
| `E2B_API_URL` | `https://api.<region>.sandbox.aliyuncs.com` |
| `E2B_DOMAIN` | `<region>.sandbox.aliyuncs.com` |
| `E2B_TEMPLATE` | 沙箱模板名称；为空时使用默认模板 |
| `LOGFIRE_TOKEN` | Logfire 写入 Token，可为空 |

## 11. 启动

```bash
docker compose up -d db

cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
```

`uv` 使用根目录的 `.python-version`（3.14），虚拟环境位于 `backend/.venv`。
