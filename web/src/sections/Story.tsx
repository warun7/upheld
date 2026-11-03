import { ArrowUpRightIcon } from "@phosphor-icons/react";
import { useInView } from "motion/react";
import { useRef, type ReactNode } from "react";
import { Reveal } from "../components/Reveal";
import { ScrollLit, Section, Ticker } from "../components/ui";
import { PROBLEM_STATS } from "../data/benchmarks";
import type { Verdict } from "../lib/api";
import { VERDICTS } from "../lib/verdicts";

export function Problem() {
  return (
    <Section>
      <div className="px-5 py-20 sm:px-8 md:py-28 lg:px-12">
        <p className="label">The problem</p>
        <ScrollLit
          className="display mt-6 max-w-[24ch] text-[2rem] leading-[1.12] sm:text-[2.6rem] lg:text-[3.3rem]"
          text="AI search now mostly cites real, working pages. The trouble is what the answer says those pages say, and a link checker can't see it."
        />
      </div>
      <div className="ruled grid-cols-1 border-t border-line md:grid-cols-3">
        {PROBLEM_STATS.map((s) => (
          <div key={s.value} className="ticks flex flex-col px-5 py-9 sm:px-8 lg:px-10">
            <p className="display text-5xl leading-none text-ink md:text-6xl">
              <Ticker value={s.value} />
            </p>
            <p className="mt-5 max-w-[36ch] leading-relaxed text-ink-2">{s.text}</p>
            <a href={s.href} className="mt-auto inline-flex items-center gap-1 pt-6 font-mono text-xs text-ink-3 transition-colors hover:text-accent-ink">
              {s.cite}
              <ArrowUpRightIcon size={11} weight="bold" aria-hidden />
            </a>
          </div>
        ))}
      </div>
    </Section>
  );
}

const PASSES = [
  {
    verb: "Parse",
    body: "Splits the answer into sentences and maps [1], [1, 2], [^1] and inline links to their sources. Questions and lead-ins aren't claims.",
    artifact: [
      ["claim 2", "It stands 384 metres tall.", "[1]"],
      ["claim 5", "repainted every three years", "[2]"],
      ["claim 6", "most visited paid monument", "none"],
    ],
  },
  {
    verb: "Fetch",
    body: "Downloads each cited page or PDF and pulls out its main text. A dead link goes to the Wayback Machine: archived means link rot, never archived means likely made up. A dead or blocked page is read from its archived copy.",
    artifact: [
      ["GET [1]", "Eiffel_Tower", "200"],
      ["GET [2]", "..._repainting_schedule", "404"],
      ["Wayback", "no snapshot, ever", "fabricated"],
    ],
  },
  {
    verb: "Retrieve",
    body: "Cuts each source into ~120-word windows and ranks them with BM25 and bge-small embeddings, merged by reciprocal rank fusion.",
    artifact: [
      ["claim 2", "384 metres tall", ""],
      ["best", "The tower is 330 metres ...", "0.99"],
    ],
  },
  {
    verb: "Verify",
    body: "MiniCheck, word overlap with exact number matching and LettuceDetect, combined by a logistic regression with four fitted numbers.",
    artifact: [
      ["score", "0.24 < 0.50", ""],
      ["verdict", "unsupported", ""],
      ["flagged", "384 metres", ""],
    ],
  },
];

const BAD = new Set(["404", "fabricated", "unsupported", "none"]);

export function HowItWorks() {
  return (
    <Section id="how">
      <div className="grid grid-cols-1 gap-6 px-5 py-16 sm:px-8 md:py-20 lg:grid-cols-2 lg:items-end lg:px-12">
        <h2 className="display text-4xl leading-[1.02] md:text-[3.25rem]">Four passes over every answer</h2>
        <p className="max-w-[48ch] text-lg leading-relaxed text-ink-2 lg:justify-self-end">
          Each claim ends up with one verdict per citation, the passage it was checked against, and a score. This is the run behind the demo above.
        </p>
      </div>
      <ol className="ruled relative grid-cols-1 border-t border-line md:grid-cols-2 xl:grid-cols-4">
        <span className="pulse-x hidden xl:block" aria-hidden />
        {PASSES.map((p, i) => (
          <li key={p.verb} className="ticks flex flex-col px-5 py-8 sm:px-8 lg:px-8">
            <p className="label lit-step" style={{ animationDelay: `${(i * 0.85).toFixed(2)}s` }}>
              {String(i + 1).padStart(2, "0")} · {p.verb}
            </p>
            <h3 className="display mt-6 text-[1.7rem] leading-none">{p.verb}</h3>
            <p className="mt-4 text-[0.95rem] leading-relaxed text-ink-2">{p.body}</p>
            <div className="mt-auto pt-7">
              <div className="space-y-1.5 border-t border-dashed border-line-strong pt-4 font-mono text-[0.72rem] leading-5">
                {p.artifact.map(([k, v, r]) => (
                  <div key={k + v} className="grid grid-cols-[4.2rem_minmax(0,1fr)_auto] gap-3">
                    <span className="text-ink-3">{k}</span>
                    <span className={`truncate ${BAD.has(v) ? "text-bad" : "text-ink"}`}>{v}</span>
                    <span className={BAD.has(r) ? "text-bad" : "text-ink-2"}>{r}</span>
                  </div>
                ))}
              </div>
            </div>
          </li>
        ))}
      </ol>
    </Section>
  );
}

function Mark({ verdict, on, delay, children }: { verdict: Verdict; on: boolean; delay: number; children: ReactNode }) {
  return (
    <span className="claim cursor-default" data-verdict={on ? verdict : "pending"} style={{ transitionDelay: `${delay}s` }}>
      {children}
    </span>
  );
}

const CELLS: { verdict: Verdict; sample: ReactNode[]; note: string }[] = [
  {
    verdict: "supported",
    sample: ["It was the ", "tallest man-made structure in the world until 1930", "."],
    note: "Wikipedia, Eiffel Tower: support 0.84.",
  },
  {
    verdict: "unsupported",
    sample: ["It ", "stands 384 metres tall", "."],
    note: "The page says 330 metres. The flagged words are marked.",
  },
  {
    verdict: "wrong_entity",
    sample: ["A tirzepatide trial cited for ", "Ozempic", "."],
    note: "Reads as supported, but the name never appears in the source.",
  },
  {
    verdict: "source_missing",
    sample: ["", "Repainted every three years", " [2]"],
    note: "404, and the Wayback Machine never saw the page.",
  },
  {
    verdict: "unverifiable",
    sample: ["", "Trial data from the paywalled appendix", " [3]"],
    note: "Blocked with no readable archived copy, or a scan with no text. It says so instead of guessing.",
  },
  {
    verdict: "uncited",
    sample: ["", "The most visited paid monument in the world", "."],
    note: "A factual-looking sentence with no citation at all.",
  },
];

export function Verdicts() {
  const ref = useRef<HTMLDivElement>(null);
  const on = useInView(ref, { once: true, amount: 0.35 });
  return (
    <Section>
      <div className="grid grid-cols-1 gap-6 px-5 py-16 sm:px-8 md:py-20 lg:grid-cols-2 lg:items-end lg:px-12">
        <h2 className="display text-4xl leading-[1.02] md:text-[3.25rem]">Six verdicts, each one specific</h2>
        <p className="max-w-[48ch] text-lg leading-relaxed text-ink-2 lg:justify-self-end">
          Every citation gets one. A claim keeps the best verdict among its citations. Each mark reads without color too: fill, wave, strike or dashes.
        </p>
      </div>
      <div ref={ref} className="ruled grid-cols-1 border-t border-line sm:grid-cols-2 lg:grid-cols-3">
        {CELLS.map((c, i) => {
          const v = VERDICTS[c.verdict];
          const Glyph = v.icon;
          return (
            <Reveal key={c.verdict} delay={(i % 3) * 0.05}>
              <div className="ticks flex h-full flex-col px-5 py-8 sm:px-8">
                <p className={`flex items-center gap-2 font-mono text-[0.8rem] ${v.tone}`}>
                  <Glyph size={17} weight="bold" aria-hidden />
                  {c.verdict}
                </p>
                <p className="mt-6 text-[1.15rem] leading-relaxed">
                  {c.sample[0]}
                  <Mark verdict={c.verdict} on={on} delay={0.25 + i * 0.12}>
                    {c.sample[1]}
                  </Mark>
                  {c.sample[2]}
                </p>
                <p className="mt-auto pt-6 text-sm leading-relaxed text-ink-2">{c.note}</p>
              </div>
            </Reveal>
          );
        })}
      </div>
    </Section>
  );
}
