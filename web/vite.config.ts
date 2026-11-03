import { resolve } from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

// Three pages: the landing page at /, the docs at /docs/ and the playground at /app/.
// VITE_UPHELD_PLAYGROUND=off leaves the playground out, for a static deploy with no API.
// In dev, API calls are proxied to `upheld serve` (port 8000 unless UPHELD_API_DEV says otherwise).
const api = process.env.UPHELD_API_DEV ?? "http://127.0.0.1:8000";
export default defineConfig(({ mode }) => {
  const playground = loadEnv(mode, import.meta.dirname, "VITE_").VITE_UPHELD_PLAYGROUND !== "off";
  return {
    plugins: [react(), tailwindcss()],
    build: {
      rollupOptions: {
        input: {
          main: resolve(import.meta.dirname, "index.html"),
          docs: resolve(import.meta.dirname, "docs/index.html"),
          ...(playground && { app: resolve(import.meta.dirname, "app/index.html") }),
        },
      },
    },
    server: {
      proxy: {
        "/audit": api,
        "/health": api,
      },
    },
  };
});
