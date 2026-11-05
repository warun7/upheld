# upheld website

The landing page (`/`), the docs (`/docs/`) and a 404 page (`404.html`). Vite, React, Tailwind v4 and Motion; it builds to static files in `web/dist`.

Cloudflare Pages serves `404.html`, with a 404 status, for any path that isn't a file. `npm run dev` and `npm run preview` do the same, so a mistyped URL shows the 404 page locally too. The 404 page suggests the nearest real page for the path. Its list of targets is read from the pages that exist -- the nav's sections in
`src/components/Chrome.tsx` and the docs pages in `src/docs/content.tsx` -- by the `upheld-routes` plugin in `vite.config.ts`, which uses
`scripts/routes.mjs`. Adding a section or a docs page is enough; `src/notfound.tsx` only holds the search synonyms and the couple of names
it prefers to the nav's. If content.tsx stops looking like a list of pages, the build fails on a count instead of quietly suggesting less.

`npm run build` ends by running `scripts/check-links.mjs`, which fails when the nav links to a section the page doesn't render, when the docs
index links to a page the build didn't make, when an in-page anchor has no target, or when a sitemap URL has no file behind it.

The reports on the landing page are real `upheld audit --json` output, saved in `src/data/examples/`, so the page works without a backend. The docs are static too. Numbers come from `src/data/benchmarks.ts`, which is copied from the root README.

## Develop

```bash
cd web && npm ci && npm run dev     # http://localhost:5173
```

## Build

```bash
cd web && npm run build             # typecheck, then write web/dist
```

To refresh an example, rerun `upheld audit <file> --json` and replace its `report` field. Update `benchmarks.ts` with the README when the evals change. The docs are in `src/docs/content.tsx`; update them when a CLI option, API field or default changes.

## Deploy

The site is static, so it costs nothing to host.

**Cloudflare Pages** (or any static host):

1. In the Cloudflare dashboard, create a Pages project connected to the GitHub repo.
2. Root directory `web`, build command `npm ci && npm run build`, output directory `dist`.
3. Environment variable: `NODE_VERSION` = `24` (Vite needs Node 20.19 or newer).
4. Under Custom domains, add the subdomain, e.g. `upheld.varunsg.com`. If `varunsg.com`'s DNS is on Cloudflare, the record is created for you. Otherwise, add a CNAME from `upheld` to `<project>.pages.dev` at your DNS provider.

Every push to `main` redeploys it.

The site is static; a hosted playground would need a model server and isn't deployed.
