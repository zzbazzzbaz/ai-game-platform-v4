export const common = {
  entryPoints: ["src/main.js"],
  bundle: true,
  outfile: "dist/game.js",
  format: "esm",
  target: ["es2020"],
  logLevel: "info",
};

export const devOptions = { ...common, minify: false, sourcemap: true };

export const prodOptions = { ...common, minify: true, sourcemap: false };
