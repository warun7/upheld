import { ArrowUpRightIcon, GithubLogoIcon, MoonIcon, SunIcon } from "@phosphor-icons/react";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useState } from "react";
import { AUTHOR, GITHUB_URL, PLAYGROUND_URL } from "../lib/site";
import { LinkButton } from "./ui";

// "upheld" outlined from Mona Sans at wght 600, so the beam can sit exactly on the ascenders.
const LETTERS =
  "M249.1 9.1Q188.6 9.1 145.6 -14.7Q102.6 -38.6 80.5 -86.1Q58.4 -133.6 58.4 -202.3V-532.4H183.4V-235Q183.4 -189.6 195.1 -158.1Q206.7 -126.6 231.9 -110Q257.1 -93.4 297.1 -93.4Q337.4 -93.4 366.8 -113Q396.1 -132.6 412.1 -166.2Q428.1 -199.9 428.1 -241.6V-532.4H553.1V0H433.4L428.1 -102.7H421.9Q402 -49.4 355.4 -20.1Q308.7 9.1 249.1 9.1ZM675.3 167V-532.4H793.9L798.7 -435.4H805.7Q822.9 -483.1 868.9 -512.4Q915 -541.6 977.7 -541.6Q1026.9 -541.6 1066.9 -522.8Q1106.9 -504 1135.9 -468.6Q1164.9 -433.3 1180.4 -382.1Q1195.9 -330.9 1195.9 -266Q1195.9 -179.6 1168.6 -117.6Q1141.4 -55.6 1092.4 -23Q1043.3 9.6 977.7 9.6Q936.1 9.6 901.2 -3.6Q866.3 -16.7 841.9 -40.9Q817.4 -65 805.7 -96.1H800.3V167H675.3ZM930.9 -92Q975.4 -92 1006 -112.9Q1036.6 -133.9 1052.4 -173.2Q1068.1 -212.6 1068.1 -266Q1068.1 -320 1052.9 -358.9Q1037.7 -397.7 1007.7 -418.6Q977.7 -439.6 933.7 -439.6Q890.3 -439.6 860.4 -420.1Q830.4 -400.7 815.4 -367.5Q800.3 -334.3 800.3 -294.1V-237.4Q800.3 -196.1 815.9 -163.4Q831.6 -130.7 860.9 -111.4Q890.3 -92 930.9 -92ZM1290.3 0V-729H1414.9V-431.4H1421.1Q1443.7 -486.6 1491.1 -514.1Q1538.4 -541.6 1595.9 -541.6Q1636.3 -541.6 1670.8 -529.4Q1705.3 -517.1 1730.9 -490.7Q1756.4 -464.3 1770.7 -421.8Q1785 -379.3 1785 -318.9V0H1660V-292.3Q1660 -342 1648.1 -374.6Q1636.3 -407.3 1611.8 -423.1Q1587.3 -439 1548 -439Q1506.4 -439 1476.6 -419Q1446.9 -399 1430.9 -366.2Q1414.9 -333.4 1414.9 -293.4V0H1290.3ZM2127 9.5Q2046.5 9.5 1989.5 -24.2Q1932.5 -58 1902.5 -119.5Q1872.5 -181 1872.5 -263Q1872.5 -348.5 1902.8 -411Q1933 -473.5 1989 -507.5Q2045 -541.5 2122.5 -541.5Q2210 -541.5 2266.5 -502.7Q2323 -464 2348 -396Q2373 -328 2365.5 -240H1995Q1995.5 -189 2011.7 -154.5Q2028 -120 2057.7 -102.7Q2087.5 -85.5 2127 -85.5Q2174 -85.5 2203.3 -105.5Q2232.5 -125.5 2242.5 -158.5H2361Q2353 -106.5 2321 -69Q2289 -31.5 2239.2 -11Q2189.5 9.5 2127 9.5ZM1995.5 -307 1984 -320.5H2255L2243 -306.5Q2244.5 -355 2229.5 -385.8Q2214.5 -416.5 2187 -431.8Q2159.5 -447 2122.5 -447Q2084.5 -447 2056.2 -430.8Q2028 -414.5 2012.2 -383.3Q1996.5 -352 1995.5 -307ZM2453.3 0V-729H2578.3V0H2453.3ZM2891.7 9.1Q2843.1 9.1 2802.9 -9.6Q2762.6 -28.4 2733.6 -63.8Q2704.6 -99.1 2689.1 -150.4Q2673.6 -201.6 2673.6 -266.4Q2673.6 -353.4 2701.1 -415.1Q2728.6 -476.9 2777.6 -509.4Q2826.6 -542 2891.7 -542Q2933.9 -542 2968.5 -528.9Q3003.1 -515.7 3027.8 -492.1Q3052.4 -468.4 3063.7 -436.3H3069.1V-729H3194.1V0H3075.6L3070.7 -97H3063.7Q3046.6 -49.3 3000.7 -20.1Q2954.9 9.1 2891.7 9.1ZM2935.7 -92.9Q2979.7 -92.9 3009.4 -112.5Q3039 -132.1 3054.1 -165.1Q3069.1 -198.1 3069.1 -238.3V-295Q3069.1 -336.3 3053.5 -369.2Q3037.9 -402.1 3008.5 -421.3Q2979.1 -440.4 2938.6 -440.4Q2894 -440.4 2863.4 -419.5Q2832.9 -398.6 2817.1 -359.7Q2801.3 -320.9 2801.3 -266.4Q2801.3 -213.4 2816.5 -174.1Q2831.7 -134.7 2861.7 -113.8Q2891.7 -92.9 2935.7 -92.9Z";

/** The wordmark: a beam held just above the h, l and d of "held". On hover it lifts a little higher. */
export function Logo({ className = "" }: { className?: string }) {
  return (
    <a href="/" className={`logo inline-flex items-center ${className}`} aria-label="upheld home">
      <svg viewBox="58.4 -914 3135.7 1081" className="h-[1.45rem] w-auto overflow-visible" aria-hidden fill="currentColor">
        <path d={LETTERS} />
        <rect className="logo-beam" x="1290.3" y="-904" width="1903.9" height="95" />
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
          {theme === "dark" ? <SunIcon size={17} weight="bold" /> : <MoonIcon size={17} weight="bold" />}
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

export function Nav({ page }: { page: "landing" | "app" }) {
  const active = useActiveSection(page === "landing");
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
        </nav>
        <div className="ml-auto flex items-center gap-1">
          <ThemeToggle />
          <a
            href={GITHUB_URL}
            className="hidden size-9 place-items-center text-ink-2 transition-colors hover:bg-cell-2 hover:text-ink sm:grid"
            aria-label="upheld on GitHub"
          >
            <GithubLogoIcon size={18} weight="bold" />
          </a>
          {page === "landing" ? (
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
            <a href={PLAYGROUND_URL} className="hover:text-ink">
              Playground
            </a>
          </li>
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
