# upheld website

The landing page (`/`) and the playground (`/app/`). Vite, React, Tailwind v4 and Motion; it builds to static files in `web/dist`.

The demos on the landing page are real `upheld audit --json` output, saved in `src/data/examples/`, so the page works without a backend. The playground calls the API for anything else.

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

Benchmark numbers live in `src/data/benchmarks.ts`. Update them with the README when the evals change. To refresh an example, rerun `upheld audit <file> --json` and replace its `report` field.

## Deploy

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

**Site: Cloudflare Pages** (or any static host).

- Root directory `web`, build command `npm ci && npm run build`, output directory `dist`.
- Environment variable `VITE_UPHELD_API` = the Space URL, e.g. `https://<user>-upheld.hf.space`.
- Add the custom domain (`upheld.varunsg.com`) in the Pages project. With the domain's DNS on Cloudflare, that creates the record for you.

The public API fetches any URL a visitor cites. Private and local addresses are already refused; there is no rate limit yet.
