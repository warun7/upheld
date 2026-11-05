// Build-time only: renders each page to HTML so the numbers are in the static files for crawlers and link previews.
import { StrictMode } from "react";
import { renderToString } from "react-dom/server";
import { Docs } from "./docs";
import { Landing } from "./landing";
import { NotFound } from "./notfound";

export const pages: Record<string, () => string> = {
  "index.html": () => renderToString(<StrictMode><Landing /></StrictMode>),
  "docs/index.html": () => renderToString(<StrictMode><Docs /></StrictMode>),
  "404.html": () => renderToString(<StrictMode><NotFound /></StrictMode>),
};
