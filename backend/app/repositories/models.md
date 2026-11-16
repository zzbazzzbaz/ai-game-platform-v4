# 数据库设计

SQLAlchemy 模型位于同目录的 `models.py`，全部继承同一个 `Base`，由 Alembic 读取 `Base.metadata` 生成迁移。

数据库为 PostgreSQL 17.11，Schema 为 `public`。建表 SQL 与 ER 图见 `docs/database-design.md`。

## 模型与表

| 模型 | 表 | 说明 |
| --- | --- | --- |
| `User` | `users` | 用户 |
| `Session` | `sessions` | 登录会话 |
| `Conversation` | `conversations` | 会话与 `ConversationStore` 记录 |
| `ConversationEntryRow` | `conversation_entries` | 消息链节点 |
| `SandboxSession` | `sandbox_sessions` | 会话与沙箱实例映射 |
| `Run` | `runs` | 单次 Agent 运行 |

## users

| 列 | 类型 | 约束 |
| --- | --- | --- |
| `id` | `uuid` | 主键，`gen_random_uuid()` |
| `email` | `citext` | 非空，唯一 |
| `password_hash` | `text` | 非空 |
| `created_at` | `timestamptz` | 非空，`now()` |

## sessions

| 列 | 类型 | 约束 |
| --- | --- | --- |
| `id` | `uuid` | 主键，`gen_random_uuid()` |
| `user_id` | `uuid` | 非空，外键 `users.id`，级联删除 |
| `token_hash` | `text` | 非空，唯一 |
| `expires_at` | `timestamptz` | 非空 |
| `created_at` | `timestamptz` | 非空，`now()` |

索引：

- `sessions_user_id_idx (user_id)`
- `sessions_expires_at_idx (expires_at)`

## conversations

| 列 | 类型 | 约束 |
| --- | --- | --- |
| `id` | `uuid` | 主键 |
| `user_id` | `uuid` | 非空，外键 `users.id`，级联删除 |
| `title` | `text` | 非空，默认 `新会话` |
| `head_id` | `uuid` | 可空，指向 `conversation_entries.id`，不建物理外键 |
| `usage` | `jsonb` | 非空，默认 `{}` |
| `deferred_tool_requests` | `jsonb` | 可空 |
| `created_at` | `timestamptz` | 非空，`now()` |
| `updated_at` | `timestamptz` | 非空，`now()` |

索引：

- `conversations_user_updated_idx (user_id, updated_at DESC)`

`usage` 保存累计 `RunUsage`。`deferred_tool_requests` 保存当前待处理审批请求，恢复后清空或覆盖。`revision` 不建列，使用 PostgreSQL 系统列 `xmin::text` 做乐观锁。

## conversation_entries

| 列 | 类型 | 约束 |
| --- | --- | --- |
| `id` | `uuid` | 主键 |
| `conversation_id` | `uuid` | 非空，外键 `conversations.id`，级联删除 |
| `parent_id` | `uuid` | 可空，外键 `conversation_entries.id`，级联删除 |
| `message` | `jsonb` | 非空 |
| `created_at` | `timestamptz` | 非空，`now()` |

索引：

- `conversation_entries_conversation_created_idx (conversation_id, created_at)`
- `conversation_entries_parent_idx (parent_id)`

`message` 是 `ModelMessagesTypeAdapter` 序列化后的单条 `ModelMessage`。历史从 `conversations.head_id` 沿 `parent_id` 链读取。

## sandbox_sessions

| 列 | 类型 | 约束 |
| --- | --- | --- |
| `id` | `uuid` | 主键，`gen_random_uuid()` |
| `user_id` | `uuid` | 非空，外键 `users.id`，级联删除 |
| `conversation_id` | `uuid` | 非空，外键 `conversations.id`，级联删除 |
| `provider` | `text` | 非空，默认 `e2b` |
| `sandbox_id` | `text` | 非空 |
| `template` | `text` | 非空 |
| `status` | `text` | 非空，默认 `active`，取值 `active` / `paused` / `dead` |
| `created_at` | `timestamptz` | 非空，`now()` |
| `last_used_at` | `timestamptz` | 非空，`now()` |
| `expires_at` | `timestamptz` | 可空 |

索引与约束：

- `sandbox_sessions_status_check`：`status IN ('active', 'paused', 'dead')`
- `sandbox_sessions_active_conversation_idx`：`(conversation_id)`，`WHERE status = 'active'`，唯一
- `sandbox_sessions_user_last_used_idx (user_id, last_used_at DESC)`

同一个 conversation 同时最多一条 `active` 记录。

## runs

| 列 | 类型 | 约束 |
| --- | --- | --- |
| `id` | `uuid` | 主键，`gen_random_uuid()` |
| `conversation_id` | `uuid` | 非空，外键 `conversations.id`，级联删除 |
| `user_id` | `uuid` | 非空，外键 `users.id`，级联删除 |
| `status` | `text` | 非空，取值 `running` / `waiting_approval` / `completed` / `cancelled` / `failed` |
| `model` | `text` | 非空 |
| `started_at` | `timestamptz` | 非空，`now()` |
| `finished_at` | `timestamptz` | 可空 |
| `usage` | `jsonb` | 非空，默认 `{}` |
| `error` | `jsonb` | 可空 |
| `parent_run_id` | `uuid` | 可空，外键 `runs.id`，置空删除 |

索引与约束：

- `runs_status_check`：`status IN ('running', 'waiting_approval', 'completed', 'cancelled', 'failed')`
- `runs_conversation_started_idx (conversation_id, started_at DESC)`
- `runs_user_status_idx (user_id, status)`

`usage` 保存单次 run 用量（`result.usage - usage_baseline`）。审批恢复产生新 run，`parent_run_id` 指向暂停的 run。

## ID 约定

- 业务表内部 ID 使用 `uuid`。
- `conversation_id`、`entry_id` 在 Pydantic AI 侧是字符串，读写时转换为 `uuid`。
- `tool_call_id`、`sandbox_id` 不是 UUID，保持 `text`。

## 外键删除规则

| 子表 | 外键 | 删除行为 |
| --- | --- | --- |
| `sessions` | `user_id` → `users.id` | `CASCADE` |
| `conversations` | `user_id` → `users.id` | `CASCADE` |
| `conversation_entries` | `conversation_id` → `conversations.id` | `CASCADE` |
| `conversation_entries` | `parent_id` → `conversation_entries.id` | `CASCADE` |
| `sandbox_sessions` | `user_id` → `users.id` | `CASCADE` |
| `sandbox_sessions` | `conversation_id` → `conversations.id` | `CASCADE` |
| `runs` | `conversation_id` → `conversations.id` | `CASCADE` |
| `runs` | `user_id` → `users.id` | `CASCADE` |
| `runs` | `parent_run_id` → `runs.id` | `SET NULL` |

删除 conversation 会级联删除其 entries、sandbox 记录与 runs。删除 user 会级联删除其 sessions、conversations 与 runs。
