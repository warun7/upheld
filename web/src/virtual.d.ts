/** Provided by the "upheld-routes" plugin in vite.config.ts, which reads these from the source that renders them. */
declare module "virtual:upheld-routes" {
  /** The nav's sections on the landing page: the ids the page is built with, in nav order. */
  export const SECTIONS: { id: string; title: string }[];
  /** Every docs page, in the order content.tsx declares them. */
  export const DOC_PAGES: { id: string; title: string }[];
}
