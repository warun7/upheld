import { ArrowRightIcon, ArrowUpRightIcon } from "@phosphor-icons/react";
import { motion, useInView, useReducedMotion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { Footer, Nav } from "./components/Chrome";
import { GlyphField } from "./components/GlyphField";
import { LinkButton, Rise, Section } from "./components/ui";
import { DOCS_URL, GITHUB_URL } from "./lib/site";
import { VerdictLabel } from "./lib/verdicts";
import { mount } from "./mount";
import "./styles.css";

/** The pages the build makes, as listed in public/sitemap.xml. */
const LISTED = ["/", "/docs/"];

type Target = { href: string; title: string; keys: string[] };

/** "CLI reference" and "cli_reference.html" both become "cli-reference". */
const slug = (s: string) =>
  s
    .toLowerCase()
    .replace(/\.html?$/, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");

// Where a mistyped or outdated address most likely meant to go. The docs ids are the anchors in src/docs/content.tsx;
// they're copied rather than imported so this page doesn't load the whole docs.
const SITE_TARGETS: Target[] = [
  { href: "/#report", title: "Real reports", keys: ["report", "reports", "example", "examples", "demo", "playground"] },
  { href: "/#how", title: "How it works", keys: ["how", "how-it-works"] },
  { href: "/#quality", title: "Quality", keys: ["quality", "benchmark", "benchmarks", "evals", "accuracy"] },
  { href: "/#limits", title: "Limitations", keys: ["limits", "limitations"] },
  { href: "/#install", title: "Install", keys: ["install", "download", "get-started"] },
  // The docs index is a real page and it is in the sitemap, so it has to be a candidate here too: /doc is one
  // character from it. Without this, a path a letter short of /docs/ was told there was no close match, one line
  // under a row listing /docs/.
  { href: DOCS_URL, title: "Docs", keys: ["docs", "doc", "documentation", "reference", "manual"] },
];
const DOC_TARGETS: Target[] = [
  ["overview", "Overview", "about", "intro"],
  ["install", "Install", "installation"],
  ["setup", "Set up and first run", "first-run", "models"],
  ["quickstart", "Quickstart", "quick-start", "getting-started", "start"],
  ["providers", "Audit a provider's response", "provider", "openai", "perplexity", "gemini"],
  ["audit-an-answer", "Audit an answer from an AI search tool", "audit"],
  ["python", "Check a RAG pipeline from Python", "library", "sdk", "rag"],
  ["http-api", "Gate answers over HTTP", "api", "http", "rest"],
  ["mcp", "Check answers from an AI agent", "mcp-server", "agent", "agents"],
  ["verifiers", "Pick a verifier", "verifier", "judge"],
  ["eval", "Measure it on your own labels", "evals", "evaluate", "labels"],
  ["self-host", "Self-host the API", "selfhost", "docker", "deploy"],
  ["input", "Input format", "input-format"],
  ["report", "Report format", "report-format", "json"],
  ["verdicts", "Verdicts and link statuses", "verdict", "statuses"],
  ["cli", "CLI reference", "command-line", "commands"],
  ["how-it-works", "How it works", "architecture"],
  ["troubleshooting", "Troubleshooting", "troubleshoot", "faq", "errors", "help"],
].map(([id, title, ...keys]) => ({ href: `${DOCS_URL}#${id}`, title, keys: [id, slug(title), ...keys] }));

function editDistance(a: string, b: string) {
  const row = Array.from({ length: b.length + 1 }, (_, j) => j);
  for (let i = 1; i <= a.length; i++) {
    let diag = row[0];
    row[0] = i;
    for (let j = 1; j <= b.length; j++) {
      const up = row[j];
      row[j] = Math.min(up + 1, row[j - 1] + 1, diag + (a[i - 1] === b[j - 1] ? 0 : 1));
      diag = up;
    }
  }
  return row[b.length];
}

/** The page a path most likely meant: the closest keyword to any of its segments, within a typo or two. */
function nearest(path: string): Target | null {
  const segments = path
    .split("/")
    .map(slug)
    .filter((s) => s && s !== "docs" && s !== "index")
    .reverse();
  const pool = path.startsWith("/docs") ? [...DOC_TARGETS, ...SITE_TARGETS] : [...SITE_TARGETS, ...DOC_TARGETS];
  let best: Target | null = null;
  let bestDistance = Infinity;
  for (const s of segments) {
    for (const t of pool) {
      for (const k of t.keys) {
        const d = editDistance(s, k);
        if (d <= Math.floor(k.length / 4) && d < bestDistance) {
          best = t;
          bestDistance = d;
        }
      }
    }
  }
  return best;
}

/** The address that was asked for. Unknown until the page runs in a browser: the same file answers every missing path. */
function useMissingPath() {
  const [path, setPath] = useState<string | null>(null);
  useEffect(() => {
    let p = location.pathname;
    try {
      p = decodeURIComponent(p);
    } catch {
      // malformed escapes: show it as sent
    }
    setPath(p);
  }, []);
  return path;
}

const STEPS = 4;

/** The address checked the way upheld checks a citation: fetch it, look for it, find the nearest real page, give a verdict. */
function Audit({ path }: { path: string | null }) {
  const reduce = useReducedMotion();
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, amount: 0.5 });
  const [step, setStep] = useState(reduce ? STEPS : 0);
  const match = path ? nearest(path) : null;

  useEffect(() => {
    if (!inView || step >= STEPS) return;
    const t = window.setTimeout(() => setStep((s) => s + 1), step === 0 ? 500 : 560);
    return () => window.clearTimeout(t);
  }, [inView, step]);

  const shown = (n: number) => ({
    initial: false as const,
    animate: step >= n ? { opacity: 1, y: 0 } : { opacity: 0, y: 6 },
    transition: { duration: 0.45, ease: [0.16, 1, 0.3, 1] as const },
  });
  const where = path ?? "this address";

  return (
    <div ref={ref} className="flex flex-col bg-cell! px-5 py-7 sm:px-8 lg:px-10 lg:py-9">
      <p className="label flex items-center justify-between gap-4">
        <span>This address, audited</span>
        <span className="hidden sm:inline">1 claim · 1 source</span>
      </p>
      <p className="mt-5 text-[1.06rem] leading-[1.95] text-ink sm:text-[1.12rem]">
        <span className={`claim cursor-default ${step > 0 && step < STEPS ? "claim-scan" : ""}`} data-verdict={step >= STEPS ? "source_missing" : "pending"}>
          There is a page at <span className="font-mono text-[0.86em] break-all">{where}</span>.
        </span>
        <sup className="mx-[1px] inline-grid h-[1.15rem] min-w-[1.15rem] -translate-y-[1px] place-items-center rounded-[2px] bg-cell-2 px-1 align-middle font-mono text-[0.68rem] font-medium text-ink-2 shadow-[inset_0_0_0_1px_var(--line)]">
          1
        </sup>
      </p>

      <div className="mt-6 space-y-2 border-t border-dashed border-line-strong pt-4 font-mono text-[0.75rem] leading-5">
        <motion.div {...shown(1)} className="grid grid-cols-[4.6rem_minmax(0,1fr)_auto] gap-3">
          <span className="text-ink-3">GET [1]</span>
          <span className="truncate text-ink">{where}</span>
          <span className="text-bad">404</span>
        </motion.div>
        <motion.div {...shown(2)} className="grid grid-cols-[4.6rem_minmax(0,1fr)_auto] gap-3">
          <span className="text-ink-3">sitemap</span>
          <span className="truncate text-ink">{LISTED.join(" · ")}</span>
          <span className="text-bad">not listed</span>
        </motion.div>
        <motion.div {...shown(3)} className="grid grid-cols-[4.6rem_minmax(0,1fr)_auto] gap-3">
          <span className="text-ink-3">nearest</span>
          {match ? (
            <a href={match.href} className="truncate text-accent-ink underline decoration-1 underline-offset-[3px] hover:decoration-2">
              {match.title}
            </a>
          ) : (
            <span className="truncate text-ink-2">no close match</span>
          )}
          <span className="text-ink-2">{match ? match.href : ""}</span>
        </motion.div>
      </div>

      <motion.div {...shown(STEPS)} className="mt-auto pt-7">
        <div className="border-l-2 border-bad bg-bg px-4 py-3">
          <VerdictLabel verdict="source_missing" />
          <p className="mt-1.5 text-sm leading-relaxed text-ink-2">
            Nothing is published at this address, so the claim that a page exists here has no source to back it.
          </p>
        </div>
      </motion.div>
    </div>
  );
}

const PAGES = [
  { href: "/", path: "/", title: "Home", text: "What upheld does, with two real reports." },
  { href: DOCS_URL, path: DOCS_URL, title: "Docs", text: "Install it, audit an answer, read the report." },
  { href: "/#install", path: "/#install", title: "Install", text: "Runs on your laptop. No API key, no account." },
  { href: GITHUB_URL, path: "github", title: "Source", text: "The code, the evals and the labels. MIT licensed.", external: true },
];

function Pages() {
  return (
    <div className="flex flex-col">
      <p className="label px-5 pt-7 sm:px-8 lg:px-10 lg:pt-9">Pages that hold up</p>
      <ul className="mt-5 border-t border-line">
        {PAGES.map((p, i) => {
          const Arrow = p.external ? ArrowUpRightIcon : ArrowRightIcon;
          return (
            <li key={p.href} className="border-b border-line last:border-b-0">
              <a href={p.href} className="ticks group grid grid-cols-[2.25rem_minmax(0,1fr)_auto] items-baseline gap-y-1 px-5 py-5 sm:px-8 lg:px-10">
                <span className="font-mono text-xs text-ink-3">{String(i + 1).padStart(2, "0")}</span>
                <span className="min-w-0">
                  <span className="block font-semibold tracking-[-0.01em] text-ink">{p.title}</span>
                  <span className="mt-1 block text-sm leading-relaxed text-ink-2">{p.text}</span>
                </span>
                <span className="flex items-center gap-3 self-center pl-4">
                  <span className="hidden font-mono text-xs text-ink-3 sm:inline">{p.path}</span>
                  <Arrow
                    size={15}
                    weight="bold"
                    className="text-ink-3 transition-[color,transform] duration-300 ease-out-expo group-hover:translate-x-[3px] group-hover:text-accent-ink"
                    aria-hidden
                  />
                </span>
              </a>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export function NotFound() {
  const reduce = useReducedMotion();
  const path = useMissingPath();
  const fade = (delay: number) =>
    reduce
      ? {}
      : {
          initial: { opacity: 0, y: 12 },
          animate: { opacity: 1, y: 0 },
          transition: { duration: 0.8, delay, ease: [0.16, 1, 0.3, 1] as const },
        };

  return (
    <>
      <Nav page="404" />
      <main>
        <Section className="!border-t-0">
          <div className="px-5 pt-14 pb-12 sm:px-8 md:pt-20 lg:px-12 lg:pb-16">
            <motion.p {...fade(0)} className="label flex items-center gap-2.5">
              <span className="relative flex size-2">
                <span className="absolute inset-0 animate-ping bg-bad opacity-60" />
                <span className="relative size-2 bg-bad" />
              </span>
              Error 404 · Page not found
            </motion.p>
            <h1 className="display mt-7 text-[2.6rem] leading-[1.0] sm:text-6xl lg:text-[4.6rem] xl:text-[5.4rem]">
              <Rise text="Source missing." delay={0.05} className="text-ink-h1" />
              <Rise text="This page doesn't exist." delay={0.3} />
            </h1>
            <div className="mt-10 grid grid-cols-1 gap-8 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end lg:gap-16">
              <motion.p {...fade(0.45)} className="max-w-[36rem] text-lg leading-relaxed text-ink-2">
                The link you followed points at a page this site doesn't have. The address may have a typo, or the page may have moved. Everything upheld does is
                on the home page and in the docs.
              </motion.p>
              <motion.div {...fade(0.55)} className="flex max-w-[25rem] flex-wrap items-center gap-x-4 gap-y-5">
                <LinkButton href="/" arrow>
                  Back to the home page
                </LinkButton>
                <LinkButton href={DOCS_URL} variant="ghost">
                  Read the docs
                </LinkButton>
                <a href={`${GITHUB_URL}/issues`} className="text-sm text-ink-2 underline decoration-line-strong underline-offset-4 hover:text-ink">
                  Report a broken link
                </a>
              </motion.div>
            </div>
          </div>

          <div className="glyph-frame relative h-[15rem] overflow-hidden border-t border-line sm:h-[20rem] lg:h-[24rem]">
            <GlyphField
              mode="text"
              text="404"
              read="--bad"
              cell={[6, 10]}
              className="absolute inset-y-0 inset-x-6 sm:inset-x-0"
              label="The number 404 drawn in shimmering text characters."
            />
            <p className="label pointer-events-none absolute top-4 left-5 sm:left-8">Fig. 404 · Not found, in glyphs</p>
            <p className="label pointer-events-none absolute top-4 right-5 hidden sm:right-8 sm:block">HTTP 404</p>
            <p className="pointer-events-none absolute bottom-5 left-5 text-sm text-ink-2 sm:left-8">
              Two pages hold. <span className="text-bad">This one doesn't.</span>
            </p>
          </div>

          <div className="ruled grid-cols-1 border-t border-line lg:grid-cols-[minmax(0,1.12fr)_minmax(0,1fr)]">
            <Audit path={path} />
            <Pages />
          </div>
        </Section>
      </main>
      <Footer />
    </>
  );
}

mount(<NotFound />);
