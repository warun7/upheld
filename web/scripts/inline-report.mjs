// Folds the report build (vite.report.config.ts) into one HTML file, the template `upheld audit --html` fills in,
// and writes it into the Python package. Fails if the page would still load anything from elsewhere.
import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

const ROOT = resolve(import.meta.dirname, "..");
const BUILD = resolve(ROOT, "node_modules/.report");
const TARGET = resolve(ROOT, "../src/upheld/report.html");

// Nothing may be fetched: the fonts are data: URIs, and the report's own data sits in the page.
const CSP = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; font-src data:; img-src data:; base-uri 'none'; form-action 'none'";

const fail = (message) => {
  console.error(`inline-report: ${message}`);
  process.exit(1);
};
const asset = (path) => readFileSync(resolve(BUILD, `.${path}`), "utf8");

let html = readFileSync(resolve(BUILD, "report.html"), "utf8");
let scripts = 0;
let styles = 0;
html = html.replace(/<script type="module" crossorigin src="([^"]+)"><\/script>/g, (_, src) => {
  scripts++;
  const js = asset(src);
  if (js.includes("<!--")) fail(`${src} contains "<!--", which would change how the inline script parses`);
  return `<script type="module">${js.replaceAll("</script", "<\\/script")}</script>`;
});
html = html.replace(/<link rel="stylesheet" crossorigin href="([^"]+)">/g, (_, href) => {
  styles++;
  const css = asset(href);
  if (/url\(\s*(?!["']?data:)/.test(css)) fail(`${href} still references a file`);
  return `<style>${css.replaceAll("</style", "<\\/style")}</style>`;
});
if (scripts !== 1 || styles !== 1) fail(`expected one script and one stylesheet, inlined ${scripts} and ${styles}`);
if (/<(script|link|img)\b[^>]*\b(src|href)=/i.test(html)) fail("the page still references a file");
if (!html.includes('<script id="upheld-data" type="application/json">{}</script>')) fail("the data slot is missing");

html = html.replace('<meta charset="UTF-8" />', `<meta charset="UTF-8" />\n    <meta http-equiv="Content-Security-Policy" content="${CSP}" />`);
writeFileSync(TARGET, html);
console.log(`inline-report: wrote ${TARGET} (${Math.round(html.length / 1024)} KB)`);
