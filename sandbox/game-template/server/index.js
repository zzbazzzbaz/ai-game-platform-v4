// 平台维护文件：游戏服务（Express + Socket.IO + 静态托管 + 健康检查 + 优雅退出）。
// 生成区代码请放 src/、shared/，不要修改本文件。
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

import express from "express";
import { Server } from "socket.io";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const PORT = Number(process.env.PORT || 3000);

const app = express();
app.disable("x-powered-by");
app.use(express.json());

app.get("/api/health", (_req, res) => {
  res.json({ ok: true });
});

// 客户端构建产物 + public/ 额外素材（同源，相对路径访问）
app.use("/dist", express.static(path.join(ROOT, "dist")));
app.use(express.static(path.join(ROOT, "public")));

// 其余 GET 请求回壳页（单服务同源：静态 + API + WebSocket）
app.use((req, res, next) => {
  if (req.method !== "GET" || req.path.startsWith("/api/") || req.path.startsWith("/socket.io/")) {
    return next();
  }
  res.sendFile(path.join(ROOT, "index.html"));
});

const server = http.createServer(app);
const io = new Server(server);

io.on("connection", (socket) => {
  // 云托管网关 60s 空闲会断开 → 客户端建议每 10s 发一次 ping
  socket.on("ping", () => socket.emit("pong"));
});

server.listen(PORT, "0.0.0.0", () => {
  console.log(`[server] listening on http://0.0.0.0:${PORT}`);
});

function shutdown(signal) {
  console.log(`[server] ${signal} 收到，优雅退出`);
  io.close();
  server.close(() => process.exit(0));
  setTimeout(() => process.exit(0), 5000).unref();
}

process.on("SIGTERM", () => shutdown("SIGTERM"));
process.on("SIGINT", () => shutdown("SIGINT"));
