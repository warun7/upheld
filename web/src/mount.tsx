import { StrictMode, type ReactNode } from "react";
import { createRoot, hydrateRoot } from "react-dom/client";

/**
 * Starts a page. The build prerenders each page into #root (see prerender.mjs), so normally React hydrates that markup.
 * Under reduced motion the first client render differs from the prerendered one (animations start settled), so it
 * renders fresh instead of hydrating. During the prerender itself there is no document, and this does nothing.
 */
export function mount(page: ReactNode) {
  if (typeof document === "undefined") return;
  const root = document.getElementById("root")!;
  const app = <StrictMode>{page}</StrictMode>;
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (root.hasChildNodes() && !reduce) {
    hydrateRoot(root, app);
  } else {
    root.replaceChildren();
    createRoot(root).render(app);
  }
}
