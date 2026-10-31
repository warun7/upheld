import {
  ArrowCounterClockwiseIcon,
  CaretDownIcon,
  CheckIcon,
  CopyIcon,
  DownloadSimpleIcon,
  PlusIcon,
  TrashIcon,
  WarningCircleIcon,
} from "@phosphor-icons/react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { StrictMode, useEffect, useRef, useState, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { AnswerText, ClaimDetail, SourceRows, VerdictCounts } from "./components/AuditView";
import { Footer, Nav } from "./components/Chrome";
import { Roll } from "./components/ui";
import glp1Json from "./data/examples/glp1.json";
import towerJson from "./data/examples/tower.json";
import { API_BASE, getHealth, runAudit, type AuditReport, type AuditRequest, type Example, type Health } from "./lib/api";
import { VERDICTS } from "./lib/verdicts";
import "./styles.css";

const EXAMPLES = [towerJson, glp1Json] as Example[];
const MAX_ANSWER = 50_000;

interface SourceRow {
  key: number;
  id: string;
  title: string;
  text: string;
}

type ApiState = { kind: "checking" } | { kind: "live"; health: Health } | { kind: "offline" };
type Result =
  | { kind: "empty" }
  | { kind: "loading"; started: number }
  | { kind: "error"; message: string; offline: boolean }
  | { kind: "done"; report: AuditReport; answer: string; saved: boolean; seconds?: number };

let rowKey = 0;
const toRows = (ex: Example): SourceRow[] =>
  ex.sources.map((s) => ({ key: ++rowKey, id: s.id, title: s.title ?? "", text: s.text ?? "" }));

function sameInput(ex: Example, question: string, answer: string, rows: SourceRow[]) {
  return (
    ex.question === question &&
    ex.answer === answer &&
    ex.sources.length === rows.length &&
    ex.sources.every((s, i) => s.id === rows[i].id && (s.text ?? "") === rows[i].text)
  );
}

function Field({ label, hint, htmlFor, children }: { label: string; hint?: string; htmlFor: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-1 gap-2">
      <label htmlFor={htmlFor} className="text-sm font-medium text-ink">
        {label}
      </label>
      {children}
      {hint && <p className="text-xs leading-relaxed text-ink-3">{hint}</p>}
    </div>
  );
}

const inputCls =
  "w-full bg-cell px-3.5 py-2.5 text-[0.95rem] text-ink shadow-[inset_0_0_0_1px_var(--line-strong)] outline-none transition-shadow placeholder:text-ink-3 hover:shadow-[inset_0_0_0_1px_var(--ink-3)] focus:shadow-[inset_0_0_0_1.5px_var(--accent)]";

function ApiStatus({ api }: { api: ApiState }) {
  if (api.kind === "checking") return <p className="text-sm text-ink-3">Checking the API...</p>;
  if (api.kind === "live")
    return (
      <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-ink-2">
        <span className="relative flex size-2">
          <span className="absolute inline-flex size-full animate-ping bg-accent opacity-60 motion-reduce:hidden" />
          <span className="relative inline-flex size-2 bg-accent" />
        </span>
        Live API
        <span className="font-mono text-xs text-ink-3">{api.health.verifier}</span>
      </p>
    );
  return (
    <p className="text-sm leading-relaxed text-ink-2">
      <span className="font-medium text-ink">The live API isn't reachable.</span> The examples still show their saved results. To check your own answers, run{" "}
      <code className="bg-cell-2 px-1.5 py-0.5 font-mono text-xs text-ink">uv run upheld serve</code> and open localhost:8000/app/.
    </p>
  );
}

function ResultSkeleton({ started }: { started: number }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 250);
    return () => window.clearInterval(t);
  }, []);
  return (
    <div className="space-y-5" aria-live="polite">
      <p className="font-mono text-xs text-ink-3">
        Fetching sources and checking claims, {((now - started) / 1000).toFixed(1)} s. Roughly 1 s per claim on CPU, more on a cold start.
      </p>
      <div className="flex gap-4">
        <div className="skeleton h-5 w-24" />
        <div className="skeleton h-5 w-28" />
        <div className="skeleton h-5 w-20" />
      </div>
      <div className="space-y-3 p-6 shadow-[inset_0_0_0_1px_var(--line)]">
        <div className="skeleton h-4 w-full" />
        <div className="skeleton h-4 w-11/12" />
        <div className="skeleton h-4 w-4/5" />
        <div className="skeleton h-4 w-2/3" />
      </div>
      {[0, 1, 2].map((i) => (
        <div key={i} className="skeleton h-14 w-full" />
      ))}
    </div>
  );
}

function EmptyState() {
  return (
    <div className="dots grid min-h-[28rem] place-items-center p-8 text-center shadow-[inset_0_0_0_1px_var(--line)]">
      <div className="max-w-sm">
        <p className="display text-2xl">Nothing checked yet</p>
        <p className="mt-2 leading-relaxed text-ink-2">
          Pick an example, or paste an answer with its citations and press Check citations. Each claim shows up here, highlighted by verdict.
        </p>
      </div>
    </div>
  );
}

function ReportView({ result }: { result: Extract<Result, { kind: "done" }> }) {
  const { report, answer } = result;
  const reduce = useReducedMotion();
  const firstFlag = report.claims.find((c) => c.verdict !== "supported")?.index ?? report.claims[0]?.index ?? null;
  const [active, setActive] = useState<number | null>(firstFlag);
  const [copied, setCopied] = useState(false);
  const json = JSON.stringify(report, null, 2);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(json);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      // clipboard blocked
    }
  };
  const download = () => {
    const url = URL.createObjectURL(new Blob([json], { type: "application/json" }));
    const a = Object.assign(document.createElement("a"), { href: url, download: "upheld-report.json" });
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
        <VerdictCounts report={report} />
        <div className="ml-auto flex gap-2">
          <button type="button" onClick={copy} className="inline-flex h-8 items-center gap-1.5 px-3 text-xs text-ink-2 shadow-[inset_0_0_0_1px_var(--line-strong)] transition-colors hover:bg-cell-2 hover:text-ink">
            {copied ? <CheckIcon size={14} weight="bold" /> : <CopyIcon size={14} weight="bold" />}
            {copied ? "Copied" : "Copy JSON"}
          </button>
          <button type="button" onClick={download} className="inline-flex h-8 items-center gap-1.5 px-3 text-xs text-ink-2 shadow-[inset_0_0_0_1px_var(--line-strong)] transition-colors hover:bg-cell-2 hover:text-ink">
            <DownloadSimpleIcon size={14} weight="bold" />
            Download
          </button>
        </div>
      </div>

      <div className="bg-cell p-6 shadow-[inset_0_0_0_1px_var(--line)] sm:p-7">
        {report.claims.length ? (
          <AnswerText answer={answer} claims={report.claims} active={active} onSelect={setActive} className="text-[1.05rem] leading-[1.85]" />
        ) : (
          <p className="text-ink-2">No claims found. upheld treats cited sentences and factual-looking sentences as claims; questions and lead-ins are skipped.</p>
        )}
        <p className="mt-5 border-t border-line pt-4 font-mono text-[0.7rem] leading-5 text-ink-3">
          {report.verifier}
          <br />
          {report.retrieval}
          {result.saved ? <><br />Saved result from an earlier run of this engine</> : result.seconds !== undefined && <><br />Checked in {result.seconds.toFixed(1)} s</>}
        </p>
      </div>

      <div>
        <h2 className="label mb-3">Claims</h2>
        <ul className="divide-y divide-line shadow-[inset_0_0_0_1px_var(--line)]">
          {report.claims.map((c) => {
            const open = active === c.index;
            const meta = VERDICTS[c.verdict];
            const Glyph = meta.icon;
            return (
              <li key={c.index} className={`overflow-hidden transition-colors ${open ? "bg-cell shadow-[inset_2px_0_0_var(--accent)]" : "hover:bg-cell"}`}>
                <button
                  type="button"
                  aria-expanded={open}
                  onClick={() => setActive(open ? null : c.index)}
                  className="flex w-full items-center gap-3 px-5 py-3.5 text-left"
                >
                  <Glyph size={18} weight="bold" className={`shrink-0 ${meta.tone}`} aria-label={meta.label} />
                  <span className="min-w-0 flex-1 truncate text-[0.95rem]">{c.text}</span>
                  <span className="hidden shrink-0 font-mono text-xs text-ink-3 sm:block">{c.cited.length ? c.cited.map((i) => `[${i}]`).join("") : "uncited"}</span>
                  <CaretDownIcon size={14} weight="bold" className={`shrink-0 text-ink-3 transition-transform ${open ? "rotate-180" : ""}`} aria-hidden />
                </button>
                <AnimatePresence initial={false}>
                  {open && (
                    <motion.div
                      initial={reduce ? false : { height: 0, opacity: 0 }}
                      animate={{ height: "auto", opacity: 1 }}
                      exit={reduce ? undefined : { height: 0, opacity: 0 }}
                      transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
                    >
                      <div className="border-t border-line px-5 pt-4 pb-5">
                        <ClaimDetail claim={c} report={report} />
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </li>
            );
          })}
        </ul>
      </div>

      {report.sources.length > 0 && (
        <div>
          <h2 className="label mb-3">Sources</h2>
          <div className="bg-cell p-5 shadow-[inset_0_0_0_1px_var(--line)]">
            <SourceRows sources={report.sources} />
          </div>
        </div>
      )}
    </div>
  );
}

function Playground() {
  const [api, setApi] = useState<ApiState>({ kind: "checking" });
  const [exampleId, setExampleId] = useState<string | null>(EXAMPLES[0].id);
  const [question, setQuestion] = useState(EXAMPLES[0].question);
  const [answer, setAnswer] = useState(EXAMPLES[0].answer);
  const [rows, setRows] = useState<SourceRow[]>(toRows(EXAMPLES[0]));
  const [result, setResult] = useState<Result>({
    kind: "done",
    report: EXAMPLES[0].report,
    answer: EXAMPLES[0].answer,
    saved: true,
  });
  const [run, setRun] = useState(0);
  const abort = useRef<AbortController | null>(null);
  const resultsRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const ctl = new AbortController();
    const timeout = window.setTimeout(() => ctl.abort(), 8000);
    getHealth(ctl.signal)
      .then((health) => setApi({ kind: "live", health }))
      .catch(() => setApi({ kind: "offline" }))
      .finally(() => window.clearTimeout(timeout));
    return () => ctl.abort();
  }, []);

  const loadExample = (ex: Example) => {
    abort.current?.abort();
    setExampleId(ex.id);
    setQuestion(ex.question);
    setAnswer(ex.answer);
    setRows(toRows(ex));
    setResult({ kind: "done", report: ex.report, answer: ex.answer, saved: true });
    setRun((r) => r + 1);
  };

  const clear = () => {
    abort.current?.abort();
    setExampleId(null);
    setQuestion("");
    setAnswer("");
    setRows([]);
    setResult({ kind: "empty" });
  };

  const submit = async () => {
    if (!answer.trim()) {
      setResult({ kind: "error", message: "Paste an answer to check first.", offline: false });
      return;
    }
    const ex = EXAMPLES.find((e) => e.id === exampleId);
    if (api.kind !== "live" && ex && sameInput(ex, question, answer, rows)) {
      setResult({ kind: "done", report: ex.report, answer: ex.answer, saved: true });
      setRun((r) => r + 1);
      return;
    }
    const ids = rows.map((r) => r.id.trim());
    if (ids.some((id) => !id)) {
      setResult({ kind: "error", message: "Every pasted source needs an id that matches its marker, like 1 for [1].", offline: false });
      return;
    }
    const req: AuditRequest = {
      question: question.trim() || null,
      answer,
      sources: rows
        .filter((r) => r.text.trim())
        .map((r) => ({ id: r.id.trim(), title: r.title.trim() || null, text: r.text })),
    };
    abort.current?.abort();
    const ctl = new AbortController();
    abort.current = ctl;
    const started = Date.now();
    setResult({ kind: "loading", started });
    if (window.matchMedia("(max-width: 1023px)").matches) resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    try {
      const report = await runAudit(req, ctl.signal);
      setResult({ kind: "done", report, answer, saved: false, seconds: (Date.now() - started) / 1000 });
      setRun((r) => r + 1);
    } catch (err) {
      if (ctl.signal.aborted) return;
      const offline = err instanceof TypeError;
      setResult({
        kind: "error",
        offline,
        message: offline
          ? `Couldn't reach the API${API_BASE ? ` at ${API_BASE}` : ""}. Run uv run upheld serve locally, or try an example.`
          : (err as Error).message,
      });
    }
  };

  const updateRow = (key: number, patch: Partial<SourceRow>) => setRows((rs) => rs.map((r) => (r.key === key ? { ...r, ...patch } : r)));
  const nextId = () => String(Math.max(0, ...rows.map((r) => Number(r.id) || 0)) + 1);

  return (
    <>
      <Nav page="app" />
      <main className="frame">
        <div className="grid min-h-[calc(100dvh-3.5rem)] grid-cols-1 lg:grid-cols-[minmax(0,28rem)_minmax(0,1fr)]">
          <div className="px-5 pt-10 pb-12 sm:px-8 lg:sticky lg:top-14 lg:max-h-[calc(100dvh-3.5rem)] lg:self-start lg:overflow-y-auto lg:pt-12">
            <h1 className="display text-5xl leading-none">Playground</h1>
            <div className="mt-3">
              <ApiStatus api={api} />
            </div>

            <div className="mt-8 grid grid-cols-2 gap-3">
              {EXAMPLES.map((ex) => (
                <button
                  key={ex.id}
                  type="button"
                  onClick={() => loadExample(ex)}
                  aria-pressed={exampleId === ex.id}
                  className={`ticks p-4 text-left transition-colors ${
                    exampleId === ex.id ? "bg-cell shadow-[inset_0_0_0_1.5px_var(--accent)]" : "shadow-[inset_0_0_0_1px_var(--line-strong)] hover:bg-cell"
                  }`}
                >
                  <span className="flex items-center gap-2 text-sm font-semibold">
                    <span className={`size-1.5 shrink-0 transition-colors ${exampleId === ex.id ? "bg-accent" : "bg-line-strong"}`} aria-hidden />
                    {ex.title}
                  </span>
                  <span className="mt-1 block text-xs leading-relaxed text-ink-2">{ex.blurb}</span>
                </button>
              ))}
            </div>

            <form
              className="mt-8 grid grid-cols-1 gap-6"
              onSubmit={(e) => {
                e.preventDefault();
                submit();
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                  e.preventDefault();
                  submit();
                }
              }}
            >
              <Field label="Question" htmlFor="q" hint="Optional. Helps the verifier read short answers.">
                <input id="q" value={question} onChange={(e) => setQuestion(e.target.value)} className={inputCls} maxLength={2000} />
              </Field>

              <Field
                label="Answer with citations"
                htmlFor="answer"
                hint="Use [1]-style markers and end with a reference list like [1] https://..., or use inline [text](url) links. Cited URLs are fetched."
              >
                <textarea
                  id="answer"
                  value={answer}
                  onChange={(e) => setAnswer(e.target.value)}
                  rows={11}
                  maxLength={MAX_ANSWER}
                  className={`${inputCls} resize-y font-mono text-[0.82rem] leading-6`}
                />
              </Field>

              <div className="grid grid-cols-1 gap-3">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-medium">Pasted sources</p>
                  <button
                    type="button"
                    onClick={() => setRows((rs) => [...rs, { key: ++rowKey, id: nextId(), title: "", text: "" }])}
                    className="inline-flex h-8 items-center gap-1.5 px-3 text-xs font-medium text-ink-2 shadow-[inset_0_0_0_1px_var(--line-strong)] transition-colors hover:bg-cell hover:text-ink"
                    disabled={rows.length >= 50}
                  >
                    <PlusIcon size={13} weight="bold" />
                    Add source text
                  </button>
                </div>
                <p className="-mt-1 text-xs leading-relaxed text-ink-3">For sources that aren't public URLs. The id must match the marker, so 1 for [1].</p>
                {rows.map((r) => (
                  <div key={r.key} className="grid grid-cols-1 gap-2 p-3 shadow-[inset_0_0_0_1px_var(--line)]">
                    <div className="flex gap-2">
                      <label className="sr-only" htmlFor={`id-${r.key}`}>
                        Source id
                      </label>
                      <input id={`id-${r.key}`} value={r.id} onChange={(e) => updateRow(r.key, { id: e.target.value })} className={`${inputCls} w-16 text-center font-mono`} />
                      <label className="sr-only" htmlFor={`title-${r.key}`}>
                        Source title
                      </label>
                      <input
                        id={`title-${r.key}`}
                        value={r.title}
                        placeholder="Title (optional)"
                        onChange={(e) => updateRow(r.key, { title: e.target.value })}
                        className={inputCls}
                      />
                      <button
                        type="button"
                        onClick={() => setRows((rs) => rs.filter((x) => x.key !== r.key))}
                        className="grid size-11 shrink-0 place-items-center text-ink-3 transition-colors hover:bg-cell-2 hover:text-bad"
                        aria-label={`Remove source ${r.id}`}
                      >
                        <TrashIcon size={16} weight="bold" />
                      </button>
                    </div>
                    <label className="sr-only" htmlFor={`text-${r.key}`}>
                      Source text
                    </label>
                    <textarea
                      id={`text-${r.key}`}
                      value={r.text}
                      rows={4}
                      placeholder="Paste the source's text"
                      onChange={(e) => updateRow(r.key, { text: e.target.value })}
                      className={`${inputCls} resize-y text-sm leading-relaxed`}
                    />
                  </div>
                ))}
              </div>

              <div className="flex flex-wrap items-center gap-3">
                <button type="submit" className="btn btn-primary" disabled={result.kind === "loading"}>
                  <Roll>{result.kind === "loading" ? "Checking..." : "Check citations"}</Roll>
                </button>
                <button type="button" onClick={clear} className="btn btn-ghost btn-sm">
                  <ArrowCounterClockwiseIcon size={15} weight="bold" />
                  <Roll>Clear</Roll>
                </button>
                <span className="hidden font-mono text-xs text-ink-3 sm:inline">Cmd/Ctrl + Enter</span>
              </div>
            </form>
          </div>

          <div ref={resultsRef} className="min-w-0 scroll-mt-16 border-t border-line px-5 lg:border-t-0 lg:border-l py-10 sm:px-8 lg:px-10 lg:py-12">
            <AnimatePresence mode="wait">
              <motion.div
                key={`${result.kind}-${run}`}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
              >
                {result.kind === "empty" && <EmptyState />}
                {result.kind === "loading" && <ResultSkeleton started={result.started} />}
                {result.kind === "error" && (
                  <div role="alert" className="flex gap-3 border-l-2 border-bad bg-cell p-6 shadow-[inset_0_0_0_1px_var(--line)]">
                    <WarningCircleIcon size={22} weight="bold" className="shrink-0 text-bad" />
                    <div>
                      <p className="font-medium">{result.offline ? "The API isn't reachable" : "That didn't work"}</p>
                      <p className="mt-1 leading-relaxed text-ink-2">{result.message}</p>
                    </div>
                  </div>
                )}
                {result.kind === "done" && <ReportView result={result} />}
              </motion.div>
            </AnimatePresence>
          </div>
        </div>
      </main>
      <Footer />
    </>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Playground />
  </StrictMode>,
);
