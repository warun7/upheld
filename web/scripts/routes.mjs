// The site's real routes, read from the source that renders them. Two callers: the "upheld-routes" plugin in
// vite.config.ts, which hands them to the 404 page, and scripts/check-links.mjs, which checks the built pages against
// them. Adding a section or a docs page here is enough for both.
//
// The reads are strict on purpose. If content.tsx stops looking like the list of pages it is, the build fails with a
// count rather than quietly offering fewer suggestions.

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const read = (root, path) => readFileSync(resolve(root, path), "utf8");

/** The nav's sections, from Chrome.tsx: the ids the landing page is built with, in nav order. */
export function readSections(root) {
  const nav = read(root, "src/components/Chrome.tsx").match(/const LINKS = \[([\s\S]*?)\n\];/)?.[1];
  if (!nav) throw new Error("routes: no LINKS array in Chrome.tsx");
  const sections = [...nav.matchAll(/\{ id: "([^"]+)", label: "([^"]+)" \}/g)].map(([, id, label]) => ({ id, title: label }));
  if (!sections.length) throw new Error("routes: LINKS has no entries");
  return sections;
}

/** Every docs page, from content.tsx, where each is declared as `id:` then `title:`. */
export function readDocs(root) {
  const content = read(root, "src/docs/content.tsx");
  const pages = [...content.matchAll(/^ {2}id: "([^"]+)",\n {2}title: "((?:[^"\\]|\\.)*)",/gm)].map(([, id, title]) => ({
    id,
    title: JSON.parse(`"${title}"`),
  }));
  if (!pages.length) throw new Error("routes: no doc pages read from content.tsx");

  // Every page is declared once and listed once in DOCS. If those counts disagree, a page exists that the 404 page
  // cannot suggest, or a page is listed that isn't declared; either way the build should stop here.
  const index = content.match(/export const DOCS[\s\S]*?\n\];/)?.[0] ?? "";
  const listed = [...index.matchAll(/pages: \[([^\]]*)\]/g)].flatMap(([, names]) => names.split(",").map((n) => n.trim()).filter(Boolean));
  if (pages.length !== listed.length) {
    throw new Error(`routes: content.tsx declares ${pages.length} doc pages but DOCS lists ${listed.length}`);
  }
  return pages;
}

export function readRoutes(root) {
  return { sections: readSections(root), docs: readDocs(root) };
}
