import { ArrowLeftIcon, ArrowRightIcon } from "@phosphor-icons/react";
import { StrictMode, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { AnswerText, ClaimDetail, SourceRows, thresholdOf } from "./components/AuditView";
import { Logo } from "./components/Chrome";
import type { AuditReport } from "./lib/report";
import { FILTERS, VERDICT_ORDER, VerdictLabel, type Filter } from "./lib/verdicts";
import "./report-fonts.css";
import "./styles.css";

/** What `upheld audit --html` writes into the page's upheld-data script. */
interface Payload {
  question: string | null;
  answer: string;
  report: AuditReport;
  generated?: string;
  version?: string;
}

const SITE = "https://upheld.varunsg.com/";

function readPayload(): Payload | null {
  try {
    const data = JSON.parse(document.getElementById("upheld-data")?.textContent ?? "");
    return data && typeof data.answer === "string" && data.report ? data : null;
  } catch {
    return null;
  }
}

/** The claim a link like report.html#claim-3 points at (1-based in the URL). */
function claimFromHash(n: number): number | null {
  const m = /^#claim-(\d+)$/.exec(window.location.hash);
  const i = m ? Number(m[1]) - 1 : -1;
  return i >= 0 && i < n ? i : null;
}


function formatDate(iso: string | undefined) {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function ReportPage({ data }: { data: Payload }) {
  const { report, answer, question } = data;
  const claims = report.claims;
  const s = report.summary;
  const flagged = FILTERS.find((f) => f.id === "flagged")!;
  const [filter, setFilter] = useState<Filter>("all");
  const [active, setActive] = useState<number | null>(() => {
    const fromHash = claimFromHash(claims.length);
    if (fromHash !== null) return fromHash;
    const firstFlagged = claims.find((c) => flagged.match(c.verdict));
    return (firstFlagged ?? claims[0])?.index ?? null;
  });
  const detail = useRef<HTMLDivElement>(null);

  const current = FILTERS.find((f) => f.id === filter)!;
  const counts = FILTERS.map((f) => claims.filter((c) => f.match(c.verdict)).length);
  const visible = claims.filter((c) => current.match(c.verdict));
  const dimmed = new Set(claims.filter((c) => !current.match(c.verdict)).map((c) => c.index));
  const claim = active === null ? null : claims.find((c) => c.index === active) ?? null;
  const position = claim ? visible.findIndex((c) => c.index === claim.index) : -1;
  const uncited = s.claim_verdicts.uncited ?? 0;
  const unreadable = report.sources.filter((src) => src.status === "unreachable" || src.status === "missing" || src.status === "link_rot" || src.status === "likely_fabricated").length;

  const select = (index: number, scroll = false) => {
    setActive(index);
    try {
      history.replaceState(null, "", `#claim-${index + 1}`);
    } catch {
      // some browsers refuse history changes on file:// pages; the selection still works
    }
    // Stacked layout: the detail is below the answer, so bring it into view.
    if (scroll && window.matchMedia("(max-width: 1023px)").matches) detail.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const step = (by: number) => {
    if (!visible.length) return;
    const next = position === -1 ? (by > 0 ? 0 : visible.length - 1) : Math.min(Math.max(position + by, 0), visible.length - 1);
    select(visible[next].index);
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey || (e.target as HTMLElement)?.closest?.("input, textarea, select")) return;
      if (e.key === "ArrowRight" || e.key === "j") step(1);
      else if (e.key === "ArrowLeft" || e.key === "k") step(-1);
      else return;
      e.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  // A link to another claim in the same report changes only the hash.
  useEffect(() => {
    const onHash = () => {
      const i = claimFromHash(claims.length);
      if (i !== null) setActive(i);
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, [claims.length]);

  useEffect(() => {
    document.title = question ? `upheld report: ${question.length > 70 ? `${question.slice(0, 70)}...` : question}` : "upheld report";
  }, [question]);

  const generated = formatDate(data.generated);
  const verdictCounts = VERDICT_ORDER.filter((v) => s.claim_verdicts[v]);

  return (
    <>
      <header className="border-b border-line print:hidden">
        <div className="mx-auto flex h-14 max-w-[1200px] items-center justify-between gap-4 px-5 sm:px-8">
          <Logo href={SITE} />
          <p className="label">Citation report</p>
        </div>
      </header>

      <main className="mx-auto max-w-[1200px] px-5 pb-16 sm:px-8">
        <section className="grid grid-cols-1 gap-8 py-10 md:grid-cols-[minmax(0,1fr)_auto] md:items-end md:gap-12 md:py-12">
          <div>
            <p className="label">{question ? "Question" : "Audited answer"}</p>
            <h1 className="display mt-3 max-w-[38ch] text-2xl leading-[1.15] md:text-[2rem]">{question || "Which claims do the cited sources back?"}</h1>
          </div>
          <div className="md:text-right">
            <p className="display text-4xl leading-none md:text-5xl">
              {s.supported_claims}
              <span className="text-ink-3">/{s.cited_claims}</span>
            </p>
            <p className="mt-2 text-sm text-ink-2">cited claims supported</p>
          </div>
        </section>

        <div className="ruled grid-cols-2 border border-line sm:grid-cols-4">
          {[
            ["Claims", s.claims],
            ["Citations checked", s.citations_checked],
            ["Uncited claims", uncited],
            ["Sources not read", unreadable],
          ].map(([label, value]) => (
            <div key={label} className="px-4 py-3">
              <p className="label">{label}</p>
              <p className="mt-1 font-mono text-lg text-ink">{value}</p>
            </div>
          ))}
        </div>

        <ul className="mt-5 flex flex-wrap gap-x-5 gap-y-2" aria-label="Claims by verdict">
          {verdictCounts.map((v) => (
            <li key={v} className="flex items-center gap-2 text-sm">
              <VerdictLabel verdict={v} />
              <span className="font-mono text-xs text-ink-3">{s.claim_verdicts[v]}</span>
            </li>
          ))}
        </ul>

        <div className="ruled mt-10 grid-cols-1 border border-line lg:grid-cols-[minmax(0,1.12fr)_minmax(0,1fr)]">
          <div className="px-5 py-7 sm:px-8 lg:px-10 lg:py-9">
            <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-3">
              <p className="label">Answer</p>
              <div role="group" aria-label="Filter claims by verdict" className="flex flex-wrap gap-2 print:hidden">
                {FILTERS.map((f, i) => {
                  const on = filter === f.id;
                  return (
                    <button
                      key={f.id}
                      type="button"
                      aria-pressed={on}
                      disabled={counts[i] === 0}
                      onClick={() => setFilter(f.id)}
                      className={`inline-flex h-8 items-center gap-2 px-3 text-sm transition-colors disabled:opacity-40 ${
                        on ? "bg-ink text-bg" : "text-ink-2 shadow-[inset_0_0_0_1px_var(--line-strong)] hover:text-ink"
                      }`}
                    >
                      {f.label}
                      <span className="font-mono text-xs">{counts[i]}</span>
                    </button>
                  );
                })}
              </div>
            </div>
            <AnswerText
              answer={answer}
              claims={claims}
              active={active}
              onSelect={(i) => select(i, true)}
              dimmed={dimmed}
              className="mt-3 text-[1.06rem] leading-[1.95] text-ink sm:text-[1.12rem]"
            />
            <p className="mt-3 text-xs text-ink-3 print:hidden">Select a highlighted claim to see what upheld found. The arrow keys step through them.</p>
            <div className="mt-7 border-t border-line pt-4">
              <p className="label mb-3">Sources</p>
              <SourceRows sources={report.sources} />
            </div>
          </div>

          <div ref={detail} className="scroll-mt-4 bg-cell px-5 py-7 sm:px-8 lg:px-10 lg:py-9 print:hidden">
            <div className="lg:sticky lg:top-6">
              <div className="flex items-center justify-between gap-3">
                <p className="label">
                  {claim ? `Claim ${claim.index + 1} of ${claims.length}` : "Claim detail"}
                  <span className="ml-3 text-ink-3">threshold {thresholdOf(report.verifier).toFixed(2)}</span>
                </p>
                <div className="flex gap-1">
                  <button
                    type="button"
                    onClick={() => step(-1)}
                    disabled={position <= 0 && position !== -1}
                    aria-label="Previous claim"
                    className="grid size-8 place-items-center text-ink-2 shadow-[inset_0_0_0_1px_var(--line-strong)] transition-colors hover:text-ink disabled:opacity-40"
                  >
                    <ArrowLeftIcon size={14} weight="bold" aria-hidden />
                  </button>
                  <button
                    type="button"
                    onClick={() => step(1)}
                    disabled={position === visible.length - 1}
                    aria-label="Next claim"
                    className="grid size-8 place-items-center text-ink-2 shadow-[inset_0_0_0_1px_var(--line-strong)] transition-colors hover:text-ink disabled:opacity-40"
                  >
                    <ArrowRightIcon size={14} weight="bold" aria-hidden />
                  </button>
                </div>
              </div>
              <div className="mt-5" aria-live="polite">
                {claim ? <ClaimDetail claim={claim} report={report} /> : <p className="text-sm text-ink-2">This answer has no claims to check.</p>}
              </div>
            </div>
          </div>
        </div>

        {/* On paper there's nothing to click, so every claim is printed in full. */}
        <section className="hidden print:block">
          {claims.map((c) => (
            <div key={c.index} className="break-inside-avoid border-t border-line py-6">
              <p className="label mb-3">Claim {c.index + 1}</p>
              <ClaimDetail claim={c} report={report} />
            </div>
          ))}
        </section>

        <footer className="mt-10 flex flex-col gap-2 text-sm text-ink-3 sm:flex-row sm:justify-between">
          <p className="font-mono text-xs">
            verifier {report.verifier} · retrieval {report.retrieval}
          </p>
          <p className="font-mono text-xs">
            {[generated && `checked ${generated}`, data.version && `upheld ${data.version}`].filter(Boolean).join(" · ")}
          </p>
        </footer>
        <p className="mt-4 max-w-[70ch] text-sm leading-relaxed text-ink-2">
          Scores come from an automatic verifier and are wrong some of the time: see what upheld misses and how often it flags a good citation at{" "}
          <a href={`${SITE}#quality`} className="text-ink underline decoration-line-strong underline-offset-4 hover:decoration-accent" target="_blank" rel="noreferrer">
            upheld.varunsg.com
          </a>
          .
        </p>
      </main>
    </>
  );
}

function Empty() {
  return (
    <main className="mx-auto max-w-[60ch] px-5 py-16">
      <Logo href={SITE} />
      <p className="mt-8 text-ink-2">
        This report has no audit in it. <code className="font-mono text-[0.9em] text-ink">upheld audit answer.md --html report.html</code> writes one.
      </p>
    </main>
  );
}

async function start() {
  let data = readPayload();
  // `npm run dev` serves the bare template at /report.html; show a real report there.
  if (!data && import.meta.env.DEV) {
    const example = (await import("./data/examples/tower.json")).default;
    data = { question: example.question, answer: example.answer, report: example.report as AuditReport, generated: new Date().toISOString(), version: "dev" };
  }
  createRoot(document.getElementById("root")!).render(<StrictMode>{data ? <ReportPage data={data} /> : <Empty />}</StrictMode>);
}

void start();
