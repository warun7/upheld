import { readFileSync, statSync } from "node:fs";
import { resolve } from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, type Connect, type Plugin } from "vite";

const ROOT = import.meta.dirname;

const isFile = (path: string) => {
  try {
    return statSync(path).isFile();
  } catch {
    return false;
  }
};

/** A browser navigating to a page, as opposed to loading a script, style or image. */
const wantsPage = (req: Connect.IncomingMessage) => req.method === "GET" && !!req.headers.accept?.includes("text/html");

/**
 * Answers a page that doesn't exist with 404.html and a 404 status, in `vite` and `vite preview`, as Cloudflare Pages
 * does once the build has a 404.html. Without it, both would serve the home page for any path.
 */
function notFoundPage(): Plugin {
  // By the time this runs, Vite has served static files and rewritten known pages to their .html file.
  const middleware =
    (dir: string, render: () => string | Promise<string>): Connect.NextHandleFunction =>
    async (req, res, next) => {
      const path = new URL(req.url ?? "/", "http://localhost").pathname;
      if (!wantsPage(req) || isFile(resolve(dir, `.${path}`))) return next();
      if (isFile(resolve(dir, `.${path}/index.html`))) {
        res.writeHead(308, { Location: `${path}/` }).end();
        return;
      }
      res.statusCode = 404;
      res.setHeader("Content-Type", "text/html");
      res.end(await render());
    };
  return {
    name: "upheld-404",
    // Both hooks return a function, so the middleware goes after Vite's own.
    configureServer(server) {
      const render = () => server.transformIndexHtml("/404.html", readFileSync(resolve(ROOT, "404.html"), "utf8"));
      return () => server.middlewares.use(middleware(ROOT, render));
    },
    configurePreviewServer(server) {
      const dist = resolve(ROOT, server.config.build.outDir);
      return () => server.middlewares.use(middleware(dist, () => readFileSync(resolve(dist, "404.html"), "utf8")));
    },
  };
}

// Three static pages: the landing page at /, the docs at /docs/, and 404.html for every other path.
// There is no API behind the site.
export default defineConfig({
  appType: "mpa",
  plugins: [react(), tailwindcss(), notFoundPage()],
  build: {
    rollupOptions: {
      input: {
        main: resolve(ROOT, "index.html"),
        docs: resolve(ROOT, "docs/index.html"),
        notfound: resolve(ROOT, "404.html"),
      },
    },
  },
});
