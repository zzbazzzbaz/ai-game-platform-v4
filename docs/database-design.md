# 数据库设计

## 1. 实例

| 项 | 值 |
| --- | --- |
| 数据库 | PostgreSQL 17.11 |
| 数据库名 | `agent` |
| 用户 | `agent` |
| Schema | `public` |
| 驱动 | asyncpg |
| 连接串 | `postgresql+asyncpg://agent:agent@localhost:5432/agent` |
| 扩展 | `citext`、`pgcrypto` |

`docker-compose.yml` 中的数据库镜像为 `postgres:17.11`。

SQLAlchemy 模型与列的对应关系见 `backend/app/repositories/models.md`。

## 2. ER 图

```mermaid
erDiagram
  users ||--o{ sessions : "拥有"
  users ||--o{ games : "拥有"
  users ||--o{ conversations : "拥有"
  users ||--o{ runs : "发起"

  games ||--o{ conversations : "包含"
  games ||--o| sandbox_sessions : "使用"
  conversations ||--o{ conversation_entries : "包含"
  conversations ||--o{ runs : "产生"

  conversation_entries ||--o{ conversation_entries : "parent"
```

## 3. 表定义

### 3.1 users

```sql
CREATE TABLE users (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email         citext NOT NULL UNIQUE,
    password_hash text NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now()
);
```

| 字段 | 说明 |
| --- | --- |
| `id` | 用户 ID |
| `email` | 登录邮箱，大小写不敏感 |
| `password_hash` | Argon2 哈希 |
| `created_at` | 创建时间 |

### 3.2 sessions

```sql
CREATE TABLE sessions (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash text NOT NULL UNIQUE,
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX sessions_user_id_idx ON sessions (user_id);
CREATE INDEX sessions_expires_at_idx ON sessions (expires_at);
```

| 字段 | 说明 |
| --- | --- |
| `id` | 会话 ID |
| `user_id` | 所属用户 |
| `token_hash` | Cookie 令牌的哈希 |
| `expires_at` | 过期时间 |

### 3.3 conversations

```sql
CREATE TABLE conversations (
    id                     uuid PRIMARY KEY,
    user_id                uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    game_id                uuid NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    title                  text NOT NULL DEFAULT '新会话',
    head_id                uuid,
    usage                  jsonb NOT NULL DEFAULT '{}'::jsonb,
    deferred_tool_requests jsonb,
    created_at             timestamptz NOT NULL DEFAULT now(),
    updated_at             timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX conversations_user_updated_idx
    ON conversations (user_id, updated_at DESC);
CREATE INDEX conversations_game_idx ON conversations (game_id);
```

| 字段 | 说明 |
| --- | --- |
| `id` | UUIDv7；Pydantic AI 侧是字符串，入库时转为 `uuid` |
| `user_id` | 所属用户 |
| `game_id` | 所属游戏工作区 |
| `title` | 会话标题 |
| `head_id` | 最新一条 `conversation_entries.id`，UUID，逻辑外键 |
| `usage` | `RunUsage` 的 JSON 表示 |
| `deferred_tool_requests` | `DeferredToolRequests` 的 JSON 表示，可为空 |
| `created_at` | 创建时间 |
| `updated_at` | 最近保存时间 |

`head_id` 不建立物理外键，避免 `conversations` 与 `conversation_entries` 之间的循环引用。一致性由 `ConversationStore.save` 维护。

`ConversationStore` 需要的 `scope`、`format_version`、`revision` 不建业务列：`scope` 映射为 `user_id`，`format_version` 固定为 `1`，`revision` 使用 PostgreSQL 系统列 `xmin::text`。`write_record` 用 `xmin` 做乐观锁，并在写入后把新的 `xmin` 回写到 `ConversationRecord.revision`。不支持 branch / fork。

### 3.4 conversation_entries

```sql
CREATE TABLE conversation_entries (
    id              uuid PRIMARY KEY,
    conversation_id uuid NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    parent_id       uuid REFERENCES conversation_entries(id) ON DELETE CASCADE,
    message         jsonb NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX conversation_entries_conversation_created_idx
    ON conversation_entries (conversation_id, created_at);
CREATE INDEX conversation_entries_parent_idx
    ON conversation_entries (parent_id);
```

| 字段 | 说明 |
| --- | --- |
| `id` | UUIDv7；Pydantic AI 侧是字符串，入库时转为 `uuid` |
| `conversation_id` | 所属会话 |
| `parent_id` | 前一条 entry；首条为 `NULL` |
| `message` | `ModelMessage` 的 JSON 表示 |
| `created_at` | 写入时间 |

`message` 的序列化与反序列化使用 Pydantic AI 的 `ModelMessagesTypeAdapter`。历史按 `parent_id` 链读取，链头为 `conversations.head_id`。

`kind` 固定为 `message`，不存列。

### 3.5 games

```sql
CREATE TABLE games (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name       text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX games_user_updated_idx ON games (user_id, updated_at DESC);
```

一个 game 对应一个沙盒工作区；多个 conversation 可共享同一个 game。

### 3.6 sandbox_sessions

```sql
CREATE TABLE sandbox_sessions (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    game_id          uuid NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    sandbox_id       text,
    lifecycle_state  text NOT NULL DEFAULT 'active',
    snapshot_key     text,
    snapshot_at      timestamptz,
    snapshot_bytes   bigint,
    snapshot_sha256  text,
    last_used_at     timestamptz NOT NULL DEFAULT now(),
    archive_retry_at timestamptz,
    archive_attempts integer NOT NULL DEFAULT 0,
    last_error       text,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT sandbox_sessions_state_check
        CHECK (lifecycle_state IN ('active', 'archiving', 'archived', 'restoring'))
);

CREATE UNIQUE INDEX sandbox_sessions_game_idx ON sandbox_sessions (game_id);
CREATE INDEX sandbox_sessions_last_used_idx ON sandbox_sessions (last_used_at);
CREATE INDEX sandbox_sessions_retry_idx ON sandbox_sessions (archive_retry_at);
```

每个 game 最多一条记录。`sandbox_id` 在归档后置空；`snapshot_key` 指向 OSS 工作区 tar.gz。

### 3.7 runs

```sql
CREATE TABLE runs (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id uuid NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    user_id         uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status          text NOT NULL,
    model           text NOT NULL,
    started_at      timestamptz NOT NULL DEFAULT now(),
    finished_at     timestamptz,
    usage           jsonb NOT NULL DEFAULT '{}'::jsonb,
    error           jsonb,
    parent_run_id   uuid REFERENCES runs(id) ON DELETE SET NULL,
    CONSTRAINT runs_status_check
        CHECK (status IN ('running', 'waiting_approval', 'completed', 'cancelled', 'failed'))
);

CREATE INDEX runs_conversation_started_idx
    ON runs (conversation_id, started_at DESC);
CREATE INDEX runs_user_status_idx
    ON runs (user_id, status);
```

| 字段 | 说明 |
| --- | --- |
| `id` | run ID |
| `conversation_id` | 所属会话 |
| `user_id` | 发起用户 |
| `status` | `running` / `waiting_approval` / `completed` / `cancelled` / `failed` |
| `model` | 模型字符串 |
| `started_at` | 开始时间 |
| `finished_at` | 结束时间 |
| `usage` | `RunUsage` 的 JSON 表示 |
| `error` | 错误信息 JSON |
| `parent_run_id` | 审批恢复时指向暂停的 run |

每次 `POST /api/chat` 对应一条 `runs` 记录。审批恢复产生新的 run。

审批状态不单独建表。待处理的审批请求保存在 `conversations.deferred_tool_requests`；用户决定后，`DeferredToolResults` 随下一次 run 传入，调用和结果写入消息历史。

### 3.8 ID 类型约定

| 字段 | 类型 | 生成方 |
| --- | --- | --- |
| `users.id` | `uuid` | `gen_random_uuid()` |
| `sessions.id` | `uuid` | `gen_random_uuid()` |
| `conversations.id` | `uuid` | Pydantic AI `uuid7()`，入库时转 `uuid` |
| `conversations.head_id` | `uuid` | `conversation_entries.id` |
| `conversation_entries.id` | `uuid` | Pydantic AI `uuid7()`，入库时转 `uuid` |
| `conversation_entries.parent_id` | `uuid` | 上一条 entry 的 id |
| `conversation_entries.conversation_id` | `uuid` | `conversations.id` |
| `games.id` | `uuid` | `gen_random_uuid()` |
| `sandbox_sessions.id` | `uuid` | `gen_random_uuid()` |
| `sandbox_sessions.game_id` | `uuid` | `games.id` |
| `runs.id` | `uuid` | `gen_random_uuid()` |
| `runs.conversation_id` | `uuid` | `conversations.id` |
| `runs.parent_run_id` | `uuid` | 暂停的 run id |
| `tool_call_id` | `text` | 模型/服务商生成，可能是 `call_...` |
| `sandbox_id` | `text` | 阿里云生成，形如 `sbx-...` |

`conversation_id`、`entry_id` 在 Pydantic AI 侧是 `str`，Store 在读写时做 `str` ↔ `uuid` 转换。`tool_call_id` 和 `sandbox_id` 不是 UUID，保持 `text`。

## 4. 外键与删除规则

| 子表 | 外键 | 删除行为 |
| --- | --- | --- |
| `sessions` | `user_id` → `users.id` | `CASCADE` |
| `conversations` | `user_id` → `users.id` | `CASCADE` |
| `conversation_entries` | `conversation_id` → `conversations.id` | `CASCADE` |
| `conversation_entries` | `parent_id` → `conversation_entries.id` | `CASCADE` |
| `games` | `user_id` → `users.id` | `CASCADE` |
| `conversations` | `game_id` → `games.id` | `CASCADE` |
| `sandbox_sessions` | `game_id` → `games.id` | `CASCADE` |
| `runs` | `conversation_id` → `conversations.id` | `CASCADE` |
| `runs` | `user_id` → `users.id` | `CASCADE` |
| `runs` | `parent_run_id` → `runs.id` | `SET NULL` |

删除 conversation 会删除其 entries、sandbox 记录与 runs。删除用户会删除其 sessions、conversations 与 runs。

## 5. JSON 字段

| 表.字段 | 内容 | 序列化 |
| --- | --- | --- |
| `conversations.usage` | 累计 `RunUsage` | Pydantic `RunUsage` JSON |
| `conversations.deferred_tool_requests` | 待处理的 deferred 请求 | `DeferredToolRequests` JSON |
| `conversation_entries.message` | 单条消息 | `ModelMessagesTypeAdapter` |
| `runs.usage` | 单次 run 用量 | Pydantic `RunUsage` JSON |
| `runs.error` | 错误信息 | JSON 对象 |

## 6. 时间与排序

- 所有时间字段使用 `timestamptz`，写入 UTC。
- 会话列表按 `conversations.updated_at DESC` 排序。
- 运行记录按 `runs.started_at DESC` 排序。
- 消息顺序由 `conversation_entries` 的 `parent_id` 链决定，`created_at` 仅用于调试与索引。

## 7. 迁移

- 初始迁移：`backend/migrations/versions/0001_init.py`。
- `sandbox_sessions` 精简迁移：`backend/migrations/versions/0002_simplify_sandbox_sessions.py`。
- 迁移命令：在 `backend/` 下执行 `uv run alembic upgrade head`。
- `users`、`sessions`、`conversations`、`conversation_entries`、`sandbox_sessions`、`runs` 由 Alembic 创建。
