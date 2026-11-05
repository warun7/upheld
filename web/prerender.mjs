// Injects each page's server-rendered HTML into its built file. Run after `vite build` and the SSR build (see package.json).
import { readFile, rm, writeFile } from "node:fs/promises";

const SSR_DIR = new URL("node_modules/.prerender/", import.meta.url);
const { pages } = await import(new URL("prerender.js", SSR_DIR));
const EMPTY = '<div id="root"></div>';

for (const [file, render] of Object.entries(pages)) {
  const path = new URL(`dist/${file}`, import.meta.url);
  const html = await readFile(path, "utf8");
  if (!html.includes(EMPTY)) throw new Error(`dist/${file}: no empty #root to fill`);
  await writeFile(path, html.replace(EMPTY, `<div id="root">${render()}</div>`));
  console.log(`prerendered dist/${file}`);
}
await rm(SSR_DIR, { recursive: true, force: true });
