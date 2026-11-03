# upheld website

The landing page (`/`), the docs (`/docs/`) and the playground (`/app/`). Vite, React, Tailwind v4 and Motion; it builds to static files in `web/dist`.

The demos on the landing page are real `upheld audit --json` output, saved in `src/data/examples/`, so the page works without a backend. The docs are static too. Only the playground calls the API.

## Develop

```bash
uv run upheld serve --port 8000     # the API, from the repo root
cd web && npm ci && npm run dev     # http://localhost:5173, proxies /audit and /health to :8000
```

Set `UPHELD_API_DEV=http://127.0.0.1:8001` if the API runs on another port.

## Build

```bash
cd web && npm run build             # typecheck, then write web/dist
uv run upheld serve                 # now serves the site at / and the playground at /app/
```

Benchmark numbers live in `src/data/benchmarks.ts`. Update them with the README when the evals change. To refresh an example, rerun `upheld audit <file> --json` and replace its `report` field. The docs are in `src/docs/content.tsx`; update them when a CLI option, API field or default changes.

`VITE_UPHELD_PLAYGROUND=off npm run build` builds the site without the playground: `/app/` isn't built, the "Open playground" buttons become "Read the docs", and the docs stop mentioning it.

## Deploy

### The site alone, no backend

The landing page and the docs need no server, so this costs nothing to host.

**Cloudflare Pages** (or any static host):

1. In the Cloudflare dashboard, create a Pages project connected to the GitHub repo.
2. Root directory `web`, build command `npm ci && npm run build`, output directory `dist`.
3. Environment variables: `VITE_UPHELD_PLAYGROUND` = `off`, and `NODE_VERSION` = `24` (Vite needs Node 20.19 or newer).
4. Under Custom domains, add the subdomain, e.g. `upheld.varunsg.com`. If `varunsg.com`'s DNS is on Cloudflare, the record is created for you. Otherwise, add a CNAME from `upheld` to `<project>.pages.dev` at your DNS provider.

Every push to `main` redeploys it.

### With the playground

Two pieces: the static site, and the API that the playground calls.

**API: a Hugging Face Docker Space** (free CPU tier, 16 GB RAM). The `Dockerfile` in the repo root builds the site too, so the Space alone is a working demo.

1. Create a Space with the Docker SDK and push this repo to it.
2. The Space's `README.md` needs this header at the top (Spaces read their config from it):
   ```yaml
   ---
   title: upheld
   sdk: docker
   app_port: 7860
   ---
   ```
3. Set the variable `UPHELD_CORS_ORIGINS` to the site's origin, e.g. `https://upheld.varunsg.com`.

The image bakes in about 4 GB of models so cold starts don't download them. On the free CPU tier expect a few seconds per claim. `UPHELD_MAX_CONCURRENT=1` queues requests instead of running them side by side.

**Site: Cloudflare Pages**, set up as above, except:

- Remove `VITE_UPHELD_PLAYGROUND`.
- Set `VITE_UPHELD_API` = the Space URL, e.g. `https://<user>-upheld.hf.space`.

The public API fetches any URL a visitor cites. Private and local addresses are already refused; there is no rate limit yet.
