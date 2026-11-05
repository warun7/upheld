import { ArrowUpRightIcon } from "@phosphor-icons/react";
import { Fragment, type ReactNode } from "react";
import type { AuditReport, ClaimResult, SourceReport, Verdict } from "../lib/report";
import { LINK_STATUS, VERDICTS, VerdictLabel } from "../lib/verdicts";

const MARKER = /\[(\^?\d+(?:\s*,\s*\^?\d+)*)\]|\[([^\]]+)\]\((https?:[^)\s]+)\)/g;

/** Where a trailing "Sources:" block or `[1] https://...` reference list starts. */
export function referenceListStart(answer: string): number {
  const heading = /^\s*(sources|references|citations)\s*:?\s*$/im.exec(answer);
  const entry = /^\s*\[\^?\d+\]:?\s+\S/m.exec(answer);
  const hits = [heading?.index, entry?.index].filter((i): i is number => i !== undefined);
  return hits.length ? Math.min(...hits) : answer.length;
}

function Markers({ text }: { text: string }) {
  const out: ReactNode[] = [];
  let last = 0;
  for (const m of text.matchAll(MARKER)) {
    if (m.index > last) out.push(text.slice(last, m.index));
    if (m[1]) {
      for (const id of m[1].split(",").map((s) => s.trim().replace("^", ""))) {
        out.push(
          <sup
            key={`${m.index}-${id}`}
            className="mx-[1px] inline-grid h-[1.15rem] min-w-[1.15rem] -translate-y-[1px] place-items-center rounded-[2px] bg-cell-2 px-1 align-middle font-mono text-[0.68rem] font-medium text-ink-2 shadow-[inset_0_0_0_1px_var(--line)]"
          >
            {id}
          </sup>,
        );
      }
    } else {
      out.push(
        <span key={m.index} className="underline decoration-ink-3 underline-offset-2">
          {m[2]}
        </span>,
      );
    }
    last = m.index + m[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return <>{out}</>;
}

/** The answer as written, with every claim highlighted by its verdict. Claims in `dimmed` stay in place, faded. */
export function AnswerText({
  answer,
  claims,
  active,
  onSelect,
  revealed = Infinity,
  dimmed,
  className = "",
}: {
  answer: string;
  claims: ClaimResult[];
  active: number | null;
  onSelect: (index: number) => void;
  revealed?: number;
  dimmed?: Set<number>;
  className?: string;
}) {
  const end = referenceListStart(answer);
  const sorted = [...claims].sort((a, b) => a.start - b.start);
  const parts: ReactNode[] = [];
  let cursor = 0;
  sorted.forEach((c, i) => {
    if (c.start >= end) return;
    if (c.start > cursor) parts.push(<Markers key={`t${i}`} text={answer.slice(cursor, c.start)} />);
    const state: Verdict | "pending" = i < revealed ? c.verdict : "pending";
    parts.push(
      <span
        key={`c${c.index}`}
        role="button"
        tabIndex={0}
        data-verdict={state}
        data-active={active === c.index}
        className={`claim ${i === revealed ? "claim-scan" : ""}`}
        style={dimmed?.has(c.index) ? { opacity: 0.35 } : undefined}
        onClick={() => onSelect(c.index)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            onSelect(c.index);
          }
        }}
        aria-label={`Claim ${c.index + 1}: ${state === "pending" ? "checking" : VERDICTS[c.verdict].label}`}
      >
        <Markers text={answer.slice(c.start, Math.min(c.end, end))} />
      </span>,
    );
    cursor = Math.min(c.end, end);
  });
  if (cursor < end) parts.push(<Markers key="tail" text={answer.slice(cursor, end)} />);
  return <p className={`whitespace-pre-line ${className}`}>{parts}</p>;
}

/** Claim text with the verifier's flagged spans marked. Spans index into the claim text. */
function ClaimWithSpans({ claim }: { claim: ClaimResult }) {
  const spans = claim.checks.flatMap((c) => c.unsupported_spans).sort((a, b) => a.start - b.start);
  if (!spans.length) return <>{claim.text}</>;
  const out: ReactNode[] = [];
  let cursor = 0;
  for (const s of spans) {
    if (s.start < cursor) continue;
    out.push(claim.text.slice(cursor, s.start));
    out.push(
      <mark key={s.start} className="span-flag text-inherit">
        {claim.text.slice(s.start, s.end)}
      </mark>,
    );
    cursor = s.end;
  }
  out.push(claim.text.slice(cursor));
  return <>{out}</>;
}

export function thresholdOf(verifier: string): number {
  const m = /@([\d.]+)/.exec(verifier);
  return m ? Number(m[1]) : 0.5;
}

/** Support score on a 0-1 hairline, with the verifier's threshold marked. */
export function ScoreScale({ score, threshold }: { score: number; threshold: number }) {
  const pass = score >= threshold;
  return (
    <div className="flex items-center gap-3">
      <div className="relative h-4 flex-1" aria-hidden>
        <div className="absolute inset-x-0 top-1/2 h-px bg-line-strong" />
        <div className="absolute top-0 h-4 w-px bg-ink-3" style={{ left: `${threshold * 100}%` }} />
        <div
          className={`absolute top-1/2 size-2.5 -translate-x-1/2 -translate-y-1/2 ring-2 ring-cell ${pass ? "bg-accent" : "bg-bad"}`}
          style={{ left: `${Math.min(Math.max(score, 0), 1) * 100}%` }}
        />
      </div>
      <span className="shrink-0 font-mono text-xs text-ink-2">
        <span className="text-ink">{score.toFixed(2)}</span> / {threshold.toFixed(2)} needed
      </span>
    </div>
  );
}

function sourceLabel(s: SourceReport | undefined, id: string) {
  if (!s?.url) return `Source ${id}`;
  try {
    const u = new URL(s.url);
    return `${u.hostname.replace(/^www\./, "")}${decodeURIComponent(u.pathname)}`;
  } catch {
    return s.url;
  }
}

function trimPassage(text: string, max = 300) {
  const t = text.replace(/\s+/g, " ").trim();
  // Passages are fixed-size windows, so they often start mid-sentence.
  const lead = /^[a-z0-9(,]/.test(t) ? "..." : "";
  return lead + (t.length > max ? `${t.slice(0, max).replace(/\s\S*$/, "")}...` : t);
}

/** Everything upheld found for one claim: verdict, flagged words, score and evidence per citation. */
export function ClaimDetail({ claim, report }: { claim: ClaimResult; report: AuditReport }) {
  const threshold = thresholdOf(report.verifier);
  const byId = new Map(report.sources.map((s) => [s.id, s]));
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <VerdictLabel verdict={claim.verdict} />
        <span className="text-sm text-ink-3">{VERDICTS[claim.verdict].short}</span>
      </div>
      <p className="text-[0.95rem] leading-relaxed text-ink">
        <ClaimWithSpans claim={claim} />
      </p>
      {claim.checks.length === 0 && (
        <p className="text-sm text-ink-2">{claim.note ?? "No citation, so there's nothing to check it against."}</p>
      )}
      {claim.checks.map((check) => {
        const src = byId.get(check.source_id);
        const best = check.evidence[0];
        return (
          <div key={check.source_id} className="space-y-3 border-t border-line pt-4">
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
              <span className="font-mono text-xs text-ink-3">[{check.source_id}]</span>
              {src?.url ? (
                <a href={src.url} className="inline-flex min-w-0 items-center gap-1 truncate text-ink-2 hover:text-ink" target="_blank" rel="noreferrer">
                  <span className="truncate">{sourceLabel(src, check.source_id)}</span>
                  <ArrowUpRightIcon size={12} weight="bold" className="shrink-0" aria-hidden />
                </a>
              ) : (
                <span className="text-ink-2">{sourceLabel(src, check.source_id)}</span>
              )}
            </div>
            {src && (
              <p className={`font-mono text-xs ${LINK_STATUS[src.status].tone}`}>
                {src.status}
                {src.note && ` · ${src.note}`}
              </p>
            )}
            {check.support_score !== null && check.verdict !== "source_missing" && (
              <ScoreScale score={check.support_score} threshold={threshold} />
            )}
            {check.missing_entities.length > 0 && (
              <p className="text-sm text-ink-2">
                Not in the source:{" "}
                {check.missing_entities.map((e, i) => (
                  <Fragment key={e}>
                    {i > 0 && ", "}
                    <span className="font-medium text-warn">{e}</span>
                  </Fragment>
                ))}
              </p>
            )}
            {best && (
              <blockquote className="border-l-2 border-line-strong bg-bg px-4 py-3 text-sm leading-relaxed text-ink-2">
                <span className="mb-1 flex items-baseline justify-between gap-3 text-xs font-medium text-ink-3">
                  <span>Closest passage in the source</span>
                  <span className="font-mono">score {best.score.toFixed(2)}</span>
                </span>
                {trimPassage(best.passage)}
              </blockquote>
            )}
            {check.note && (
              <p className="text-sm text-ink-3">
                {check.note}
                {src?.archive_url && (
                  <>
                    {" · "}
                    <a href={src.archive_url} className="text-ink-2 underline hover:text-ink" target="_blank" rel="noreferrer">
                      open the copy
                    </a>
                  </>
                )}
              </p>
            )}
          </div>
        );
      })}
    </div>
  );
}

export function SourceRows({ sources }: { sources: SourceReport[] }) {
  return (
    <ul className="space-y-2 text-sm">
      {sources.map((s) => (
        <li key={s.id} className="flex min-w-0 items-center gap-3">
          <span className="font-mono text-xs text-ink-3">[{s.id}]</span>
          <span className="min-w-0 flex-1 truncate text-ink-2">{sourceLabel(s, s.id)}</span>
          <span className={`shrink-0 text-xs font-medium ${LINK_STATUS[s.status].tone}`}>{LINK_STATUS[s.status].label}</span>
        </li>
      ))}
    </ul>
  );
}
