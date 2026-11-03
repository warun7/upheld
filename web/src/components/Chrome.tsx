import { ArrowUpRightIcon } from "@phosphor-icons/react";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useState } from "react";
import { AUTHOR, DOCS_URL, GITHUB_URL, HAS_PLAYGROUND, PLAYGROUND_URL, PRIMARY_CTA } from "../lib/site";
import { GithubMark, MoonGlyph, SunGlyph } from "./icons";
import { LinkButton } from "./ui";

// "upheld" outlined from Mona Sans at wght 600, each letter moved 28 units closer to the last,
// so the beam can rest exactly on the ascenders of h, l and d.
const LETTERS =
  "M249.1 9.1 Q188.6 9.1 145.6 -14.7 Q102.6 -38.6 80.5 -86.1 Q58.4 -133.6 58.4 -202.3 V-532.4 H183.4 V-235 Q183.4 -189.6 195.1 -158.1 Q206.7 -126.6 231.9 -110 Q257.1 -93.4 297.1 -93.4 Q337.4 -93.4 366.8 -113 Q396.1 -132.6 412.1 -166.2 Q428.1 -199.9 428.1 -241.6 V-532.4 H553.1 V0 H433.4 L428.1 -102.7 H421.9 Q402 -49.4 355.4 -20.1 Q308.7 9.1 249.1 9.1ZM647.3 167 V-532.4 H765.9 L770.7 -435.4 H777.7 Q794.9 -483.1 840.9 -512.4 Q887 -541.6 949.7 -541.6 Q998.9 -541.6 1038.9 -522.8 Q1078.9 -504 1107.9 -468.6 Q1136.9 -433.3 1152.4 -382.1 Q1167.9 -330.9 1167.9 -266 Q1167.9 -179.6 1140.6 -117.6 Q1113.4 -55.6 1064.4 -23 Q1015.3 9.6 949.7 9.6 Q908.1 9.6 873.2 -3.6 Q838.3 -16.7 813.9 -40.9 Q789.4 -65 777.7 -96.1 H772.3 V167 H647.3ZM902.9 -92 Q947.4 -92 978 -112.9 Q1008.6 -133.9 1024.4 -173.2 Q1040.1 -212.6 1040.1 -266 Q1040.1 -320 1024.9 -358.9 Q1009.7 -397.7 979.7 -418.6 Q949.7 -439.6 905.7 -439.6 Q862.3 -439.6 832.4 -420.1 Q802.4 -400.7 787.4 -367.5 Q772.3 -334.3 772.3 -294.1 V-237.4 Q772.3 -196.1 787.9 -163.4 Q803.6 -130.7 832.9 -111.4 Q862.3 -92 902.9 -92ZM1234.3 0 V-729 H1358.9 V-431.4 H1365.1 Q1387.7 -486.6 1435.1 -514.1 Q1482.4 -541.6 1539.9 -541.6 Q1580.3 -541.6 1614.8 -529.4 Q1649.3 -517.1 1674.9 -490.7 Q1700.4 -464.3 1714.7 -421.8 Q1729 -379.3 1729 -318.9 V0 H1604 V-292.3 Q1604 -342 1592.1 -374.6 Q1580.3 -407.3 1555.8 -423.1 Q1531.3 -439 1492 -439 Q1450.4 -439 1420.6 -419 Q1390.9 -399 1374.9 -366.2 Q1358.9 -333.4 1358.9 -293.4 V0 H1234.3ZM2043 9.5 Q1962.5 9.5 1905.5 -24.2 Q1848.5 -58 1818.5 -119.5 Q1788.5 -181 1788.5 -263 Q1788.5 -348.5 1818.8 -411 Q1849 -473.5 1905 -507.5 Q1961 -541.5 2038.5 -541.5 Q2126 -541.5 2182.5 -502.7 Q2239 -464 2264 -396 Q2289 -328 2281.5 -240 H1911 Q1911.5 -189 1927.7 -154.5 Q1944 -120 1973.7 -102.7 Q2003.5 -85.5 2043 -85.5 Q2090 -85.5 2119.3 -105.5 Q2148.5 -125.5 2158.5 -158.5 H2277 Q2269 -106.5 2237 -69 Q2205 -31.5 2155.2 -11 Q2105.5 9.5 2043 9.5ZM1911.5 -307 1900 -320.5 H2171 L2159 -306.5 Q2160.5 -355 2145.5 -385.8 Q2130.5 -416.5 2103 -431.8 Q2075.5 -447 2038.5 -447 Q2000.5 -447 1972.2 -430.8 Q1944 -414.5 1928.2 -383.3 Q1912.5 -352 1911.5 -307ZM2341.3 0 V-729 H2466.3 V0 H2341.3ZM2751.7 9.1 Q2703.1 9.1 2662.9 -9.6 Q2622.6 -28.4 2593.6 -63.8 Q2564.6 -99.1 2549.1 -150.4 Q2533.6 -201.6 2533.6 -266.4 Q2533.6 -353.4 2561.1 -415.1 Q2588.6 -476.9 2637.6 -509.4 Q2686.6 -542 2751.7 -542 Q2793.9 -542 2828.5 -528.9 Q2863.1 -515.7 2887.8 -492.1 Q2912.4 -468.4 2923.7 -436.3 H2929.1 V-729 H3054.1 V0 H2935.6 L2930.7 -97 H2923.7 Q2906.6 -49.3 2860.7 -20.1 Q2814.9 9.1 2751.7 9.1ZM2795.7 -92.9 Q2839.7 -92.9 2869.4 -112.5 Q2899 -132.1 2914.1 -165.1 Q2929.1 -198.1 2929.1 -238.3 V-295 Q2929.1 -336.3 2913.5 -369.2 Q2897.9 -402.1 2868.5 -421.3 Q2839.1 -440.4 2798.6 -440.4 Q2754 -440.4 2723.4 -419.5 Q2692.9 -398.6 2677.1 -359.7 Q2661.3 -320.9 2661.3 -266.4 Q2661.3 -213.4 2676.5 -174.1 Q2691.7 -134.7 2721.7 -113.8 Q2751.7 -92.9 2795.7 -92.9Z";

/** The wordmark: a beam resting on the h, l and d of "held", like a lintel on columns. On hover it lifts a little. */
export function Logo({ className = "" }: { className?: string }) {
  return (
    <a href="/" className={`logo inline-flex items-center ${className}`} aria-label="upheld home">
      <svg viewBox="58.4 -834 2995.7 1001" className="h-[1.34rem] w-auto overflow-visible" aria-hidden fill="currentColor">
        <path d={LETTERS} />
        <rect className="logo-beam" x="1234.3" y="-834" width="1819.8" height="110" />
      </svg>
    </a>
  );
}

type Theme = "light" | "dark";

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("light");
  useEffect(() => setTheme(document.documentElement.dataset.theme === "dark" ? "dark" : "light"), []);

  const flip = () => {
    const next: Theme = theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem("upheld-theme", next);
    } catch {
      // private mode: the choice lasts for this page view
    }
    setTheme(next);
  };

  return (
    <button
      type="button"
      onClick={flip}
      className="grid size-9 place-items-center text-ink-2 transition-colors hover:bg-cell-2 hover:text-ink"
      aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
    >
      <AnimatePresence mode="wait" initial={false}>
        <motion.span
          key={theme}
          initial={{ rotate: -90, scale: 0.5, opacity: 0 }}
          animate={{ rotate: 0, scale: 1, opacity: 1 }}
          exit={{ rotate: 90, scale: 0.5, opacity: 0 }}
          transition={{ type: "spring", stiffness: 420, damping: 26 }}
          className="block"
        >
          {theme === "dark" ? <SunGlyph /> : <MoonGlyph />}
        </motion.span>
      </AnimatePresence>
    </button>
  );
}

const LINKS = [
  { id: "demo", label: "Demo" },
  { id: "how", label: "How it works" },
  { id: "benchmarks", label: "Benchmarks" },
  { id: "limits", label: "Limitations" },
  { id: "install", label: "Install" },
];

/** The section currently under the nav, for the active-link marker. */
function useActiveSection(enabled: boolean) {
  const [active, setActive] = useState<string | null>(null);
  useEffect(() => {
    if (!enabled) return;
    const seen = new Map<string, boolean>();
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) seen.set(e.target.id, e.isIntersecting);
        setActive(LINKS.find((l) => seen.get(l.id))?.id ?? null);
      },
      { rootMargin: "-45% 0px -50% 0px" },
    );
    for (const l of LINKS) {
      const el = document.getElementById(l.id);
      if (el) io.observe(el);
    }
    return () => io.disconnect();
  }, [enabled]);
  return active;
}

export function Nav({ page }: { page: "landing" | "docs" | "app" }) {
  const active = useActiveSection(page === "landing");
  // The page renders after the browser's own jump to a #section link, so make the jump once it exists.
  useEffect(() => {
    if (location.hash) document.getElementById(decodeURIComponent(location.hash.slice(1)))?.scrollIntoView({ behavior: "instant" });
  }, []);
  return (
    <header className="sticky top-0 z-30 border-b border-line bg-bg/85 backdrop-blur-md">
      <div className="frame flex h-14 items-center gap-6 px-4 sm:px-5">
        <Logo />
        <nav className="hidden items-center text-sm text-ink-2 lg:flex" aria-label="Main">
          {LINKS.map((l) => (
            <a
              key={l.id}
              href={`/#${l.id}`}
              className={`relative flex items-center gap-2 px-3 py-1.5 transition-colors hover:text-ink ${active === l.id ? "text-ink" : ""}`}
            >
              {active === l.id && (
                <motion.span layoutId="nav-dot" className="absolute left-0 size-1.5 bg-accent" transition={{ type: "spring", stiffness: 500, damping: 36 }} />
              )}
              {l.label}
            </a>
          ))}
          <a href={DOCS_URL} className={`relative flex items-center gap-2 px-3 py-1.5 transition-colors hover:text-ink ${page === "docs" ? "text-ink" : ""}`}>
            {page === "docs" && <span className="absolute left-0 size-1.5 bg-accent" />}
            Docs
          </a>
        </nav>
        <div className="ml-auto flex items-center gap-1">
          <ThemeToggle />
          <a
            href={GITHUB_URL}
            className="hidden size-9 place-items-center text-ink-2 transition-colors hover:bg-cell-2 hover:text-ink sm:grid"
            aria-label="upheld on GitHub"
          >
            <GithubMark size={17} />
          </a>
          {page === "landing" ? (
            <LinkButton href={PRIMARY_CTA.href} size="sm" className="ml-2">
              {PRIMARY_CTA.label}
            </LinkButton>
          ) : page === "docs" && HAS_PLAYGROUND ? (
            <LinkButton href={PLAYGROUND_URL} size="sm" className="ml-2">
              Open playground
            </LinkButton>
          ) : (
            <LinkButton href="/" size="sm" variant="ghost" className="ml-2">
              About upheld
            </LinkButton>
          )}
        </div>
      </div>
    </header>
  );
}

export function Footer() {
  return (
    <footer className="border-t border-line">
      <div className="frame grid grid-cols-1 gap-10 px-5 py-12 sm:px-8 md:grid-cols-[minmax(0,1fr)_auto] md:items-end lg:px-12">
        <div>
          <Logo />
          <p className="mt-4 max-w-[40ch] text-sm leading-relaxed text-ink-2">
            Checks whether an AI answer's citations actually support its claims. Open source, MIT licensed.
          </p>
        </div>
        <ul className="flex flex-wrap gap-x-6 gap-y-3 text-sm text-ink-2">
          <li>
            <a href={DOCS_URL} className="hover:text-ink">
              Docs
            </a>
          </li>
          {HAS_PLAYGROUND && (
            <li>
              <a href={PLAYGROUND_URL} className="hover:text-ink">
                Playground
              </a>
            </li>
          )}
          <li>
            <a href={`${GITHUB_URL}#readme`} className="hover:text-ink">
              README
            </a>
          </li>
          <li>
            <a href={`${GITHUB_URL}/tree/main/evals`} className="hover:text-ink">
              Evals
            </a>
          </li>
          <li>
            <a href={AUTHOR.url} className="inline-flex items-center gap-1 hover:text-ink">
              Built by {AUTHOR.name}
              <ArrowUpRightIcon size={13} weight="bold" aria-hidden />
            </a>
          </li>
        </ul>
      </div>
    </footer>
  );
}
