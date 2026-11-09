import { resolve } from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const ROOT = import.meta.dirname;

// The single-file report that `upheld audit --html` writes. Everything is inlined, fonts included, so the page opens
// from disk with no network; scripts/inline-report.mjs then folds the script and stylesheet into the HTML.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    outDir: "node_modules/.report",
    emptyOutDir: true,
    assetsInlineLimit: () => true,
    cssCodeSplit: false,
    modulePreload: false,
    rollupOptions: { input: resolve(ROOT, "report.html") },
  },
});
