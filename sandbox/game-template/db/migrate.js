// 数据库迁移：连接平台注入的 DATABASE_URL（每游戏独占数据库；禁止硬编码连接串）。
// 可按需扩展表结构；发布前执行一次 `npm run db:migrate`。
import pg from "pg";

const { Client } = pg;
const url = process.env.DATABASE_URL;

if (!url) {
  console.log("[db] 未注入 DATABASE_URL，跳过迁移");
  process.exit(0);
}

const client = new Client({ connectionString: url });

try {
  await client.connect();
  await client.query(`
    CREATE TABLE IF NOT EXISTS game_state (
      key text PRIMARY KEY,
      value jsonb NOT NULL DEFAULT '{}'::jsonb,
      updated_at timestamptz NOT NULL DEFAULT now()
    )
  `);
  console.log("[db] 迁移完成（game_state）");
} catch (error) {
  console.error(`[db] 迁移失败：${error.message}`);
  process.exitCode = 1;
} finally {
  await client.end();
}
