// Fails if the built pages and the routes they claim disagree. Run after `npm run build`; CI runs it too.
//
// Three things worth catching before a deploy:
//   - a section the nav links to that the landing page doesn't render
//   - a docs page the docs index links to that isn't in the built docs
//   - an in-page anchor with no target, or a sitemap URL with no file behind it

import { existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import { readRoutes } from "./routes.mjs";

const problems = [];
const ids = (html) => new Set([...html.matchAll(/\sid="([^"]+)"/g)].map((m) => m[1]));
const anchors = (html, pattern) => [...html.matchAll(pattern)].map((m) => m[1]);

const home = await readFile("dist/index.html", "utf8");
const docs = await readFile("dist/docs/index.html", "utf8");
const homeIds = ids(home);
const docsIds = ids(docs);

// The plugin reads these out of the source; this checks the build actually rendered them.
const { sections, docs: pages } = readRoutes(process.cwd());
for (const { id } of sections) if (!homeIds.has(id)) problems.push(`the nav's #${id} is not rendered on the landing page`);
for (const { id } of pages) if (!docsIds.has(id)) problems.push(`the docs page "${id}" is not rendered at /docs/`);

// Every anchor pointing into the landing page, from either page.
for (const [page, html] of [
  ["/", home],
  ["/docs/", docs],
]) {
  for (const id of anchors(html, /href="\/#([^"]+)"/g)) if (!homeIds.has(id)) problems.push(`${page} links to /#${id}, which has no id on the landing page`);
  for (const id of anchors(html, /href="#([^"]+)"/g)) {
    const target = page === "/docs/" ? docsIds : homeIds;
    if (!target.has(id)) problems.push(`${page} links to #${id}, which has no id on that page`);
  }
}

// Every sitemap URL has a built file.
const sitemap = await readFile("dist/sitemap.xml", "utf8");
for (const [, url] of sitemap.matchAll(/<loc>([^<]+)<\/loc>/g)) {
  const path = new URL(url).pathname;
  const file = path.endsWith("/") ? `dist${path}index.html` : `dist${path}`;
  if (!existsSync(file)) problems.push(`sitemap lists ${url}, but ${file} does not exist`);
}
if (!existsSync("dist/404.html")) problems.push("dist/404.html is missing");

if (problems.length) {
  console.error(`check-links: ${problems.length} problem${problems.length === 1 ? "" : "s"}`);
  for (const problem of problems) console.error(`  - ${problem}`);
  process.exit(1);
}
console.log(`check-links: ${sections.length} sections, ${pages.length} docs pages, all anchors and sitemap URLs resolve`);
