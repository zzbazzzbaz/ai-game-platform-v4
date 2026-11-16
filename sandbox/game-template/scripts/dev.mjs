import { spawn } from "node:child_process";

import { context } from "esbuild";

import { devOptions } from "./esbuild.config.mjs";

const ctx = await context(devOptions);
await ctx.watch();
console.log("[dev] esbuild 监听中…");

const server = spawn(process.execPath, ["--watch", "server/index.js"], {
  stdio: "inherit",
  env: process.env,
});

server.on("exit", (code) => process.exit(code ?? 0));

for (const signal of ["SIGTERM", "SIGINT"]) {
  process.on(signal, async () => {
    await ctx.dispose();
    server.kill(signal);
  });
}
