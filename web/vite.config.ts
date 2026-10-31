import { resolve } from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Two pages: the landing page at / and the playground at /app/.
// In dev, API calls are proxied to `upheld serve` (port 8000 unless UPHELD_API_DEV says otherwise).
const api = process.env.UPHELD_API_DEV ?? "http://127.0.0.1:8000";
export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    rollupOptions: {
      input: {
        main: resolve(import.meta.dirname, "index.html"),
        app: resolve(import.meta.dirname, "app/index.html"),
      },
    },
  },
  server: {
    proxy: {
      "/audit": api,
      "/health": api,
    },
  },
});
