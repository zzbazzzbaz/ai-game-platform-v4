// 前后端共用纯逻辑（生成区）。示例：数值裁剪。
export function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}
