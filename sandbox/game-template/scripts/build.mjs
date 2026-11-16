import { build } from "esbuild";

import { prodOptions } from "./esbuild.config.mjs";

await build(prodOptions);
console.log("[build] dist/game.js 已生成");
