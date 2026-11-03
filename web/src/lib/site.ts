export const GITHUB_URL = "https://github.com/warun7/upheld";
export const PLAYGROUND_URL = "/app/";
export const DOCS_URL = "/docs/";
export const AUTHOR = { name: "Varun S G", url: "https://github.com/warun7" };

// A static deploy with no API behind it builds with VITE_UPHELD_PLAYGROUND=off: the /app/ page
// isn't built, and the links that would open it point at the docs instead.
export const HAS_PLAYGROUND = import.meta.env.VITE_UPHELD_PLAYGROUND !== "off";

/** The main call to action: try it in the playground, or read how to run it. */
export const PRIMARY_CTA = HAS_PLAYGROUND ? { href: PLAYGROUND_URL, label: "Open playground" } : { href: DOCS_URL, label: "Read the docs" };
