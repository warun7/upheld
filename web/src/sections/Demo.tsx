import { animate, AnimatePresence, motion, useInView, useMotionValue, useReducedMotion, useTransform } from "motion/react";
import { useEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import { AnswerText, ClaimDetail, SourceRows } from "../components/AuditView";
import { LinkButton, Section } from "../components/ui";
import towerJson from "../data/examples/tower.json";
import type { ClaimResult, Example } from "../lib/api";
import { PLAYGROUND_URL } from "../lib/site";
import { VERDICTS } from "../lib/verdicts";

const tower = towerJson as Example;
const STEP_MS = 1050;

const DOT: Record<ClaimResult["verdict"], string> = {
  supported: "bg-accent",
  unsupported: "bg-bad",
  wrong_entity: "bg-warn",
  source_missing: "bg-bad",
  unverifiable: "bg-ink-3",
  uncited: "bg-ink-3",
};

const pad = (n: number) => String(n).padStart(2, "0");

/**
 * A stepped slider in the spirit of a timeline scrubber: drag anywhere on the track,
 * the thumb follows the pointer and springs to the nearest claim on release.
 */
function Scrubber({
  value,
  claims,
  revealed,
  onChange,
}: {
  value: number;
  claims: ClaimResult[];
  revealed: number;
  onChange: (v: number) => void;
}) {
  const count = claims.length;
  const track = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);
  const [grabbed, setGrabbed] = useState(false);
  const frac = useMotionValue(0);
  const left = useTransform(frac, (f) => `${f * 100}%`);
  const target = (Math.max(value, 1) - 1) / (count - 1);

  useEffect(() => {
    if (dragging.current) return;
    const ctl = animate(frac, target, { type: "spring", stiffness: 380, damping: 34 });
    return () => ctl.stop();
  }, [target, frac]);

  const fromPointer = (e: PointerEvent) => {
    const r = track.current!.getBoundingClientRect();
    const f = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width));
    frac.set(f);
    onChange(Math.round(f * (count - 1)) + 1);
  };

  const onKey = (e: KeyboardEvent) => {
    const next =
      e.key === "ArrowRight" || e.key === "ArrowUp"
        ? Math.min(count, value + 1)
        : e.key === "ArrowLeft" || e.key === "ArrowDown"
          ? Math.max(1, value - 1)
          : e.key === "Home"
            ? 1
            : e.key === "End"
              ? count
              : null;
    if (next !== null) {
      e.preventDefault();
      onChange(next);
    }
  };

  const minor = Array.from({ length: (count - 1) * 4 + 1 }, (_, i) => i / ((count - 1) * 4));

  return (
    <div
      ref={track}
      className="relative h-16 cursor-pointer touch-none select-none"
      onPointerDown={(e) => {
        dragging.current = true;
        setGrabbed(true);
        e.currentTarget.setPointerCapture(e.pointerId);
        fromPointer(e);
      }}
      onPointerMove={(e) => dragging.current && fromPointer(e)}
      onPointerUp={() => {
        dragging.current = false;
        setGrabbed(false);
        animate(frac, (value - 1) / (count - 1), { type: "spring", stiffness: 380, damping: 34 });
      }}
    >
      <div className="absolute inset-x-0 top-1/2 h-px bg-line-strong" />
      {minor.map((f, i) => (
        <span
          key={i}
          className={`absolute top-1/2 w-px -translate-y-1/2 ${i % 4 === 0 ? "h-3.5 bg-ink-3" : "h-1.5 bg-line-strong"}`}
          style={{ left: `${f * 100}%` }}
          aria-hidden
        />
      ))}
      {claims.map((c, i) => (
        <span key={c.index} className="absolute top-0 -translate-x-1/2" style={{ left: `${(i / (count - 1)) * 100}%` }} aria-hidden>
          <motion.span
            className={`block size-1.5 ${DOT[c.verdict]}`}
            initial={false}
            animate={{ scale: i < revealed ? 1 : 0, opacity: i < revealed ? 1 : 0 }}
            transition={{ type: "spring", stiffness: 500, damping: 22 }}
          />
        </span>
      ))}
      {claims.map((c, i) => (
        <span
          key={c.index}
          className={`absolute bottom-0 -translate-x-1/2 font-mono text-[0.68rem] transition-colors ${i + 1 === value ? "text-ink" : "text-ink-3"}`}
          style={{ left: `${(i / (count - 1)) * 100}%` }}
          aria-hidden
        >
          {pad(i + 1)}
        </span>
      ))}
      <motion.div
        role="slider"
        tabIndex={0}
        aria-label="Claim"
        aria-valuemin={1}
        aria-valuemax={count}
        aria-valuenow={Math.max(value, 1)}
        aria-valuetext={`Claim ${Math.max(value, 1)} of ${count}`}
        onKeyDown={onKey}
        className="absolute top-1/2 -translate-x-1/2 -translate-y-1/2"
        style={{ left }}
      >
        <motion.span
          className="grid h-7 w-5 place-items-center bg-cell shadow-[inset_0_0_0_1px_var(--ink),var(--shadow)]"
          animate={{ scale: grabbed ? 1.15 : 1 }}
          transition={{ type: "spring", stiffness: 600, damping: 28 }}
        >
          <span className="flex gap-[2px]" aria-hidden>
            <span className="h-2.5 w-px bg-ink-2" />
            <span className="h-2.5 w-px bg-ink-2" />
          </span>
        </motion.span>
      </motion.div>
    </div>
  );
}

export function Demo() {
  const reduce = useReducedMotion();
  const claims = tower.report.claims;
  const n = claims.length;
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { amount: 0.4 });
  const [pos, setPos] = useState(reduce ? 2 : 0);
  const [done, setDone] = useState(!!reduce);

  // Plays through once while in view, then settles on claim 2, the interesting one.
  useEffect(() => {
    if (!inView || done) return;
    const timer =
      pos >= n
        ? window.setTimeout(() => {
            setDone(true);
            setPos(2);
          }, 1300)
        : window.setTimeout(() => setPos((p) => p + 1), pos === 0 ? 350 : STEP_MS);
    return () => window.clearTimeout(timer);
  }, [inView, done, pos, n]);

  const take = (v: number) => {
    setDone(true);
    setPos(v);
  };

  const revealed = done ? n : pos;
  const active = pos > 0 ? claims[pos - 1] : null;

  return (
    <Section id="demo">
      <div className="grid grid-cols-1 gap-6 px-5 py-16 sm:px-8 md:py-20 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end lg:px-12">
        <div>
          <h2 className="display text-4xl leading-[1.02] md:text-[3.25rem]">Watch it read the sources</h2>
          <p className="mt-5 max-w-[56ch] text-lg leading-relaxed text-ink-2">
            A real report, not a mockup. upheld audited this answer against live Wikipedia. Drag the slider to step through its six claims.
          </p>
        </div>
        <LinkButton href={PLAYGROUND_URL} variant="ghost" arrow className="justify-self-start">
          Try your own answer
        </LinkButton>
      </div>

      <div ref={ref} className="border-t border-line">
        <div className="ruled grid-cols-1 lg:grid-cols-[minmax(0,1.12fr)_minmax(0,1fr)]">
          <div className="px-5 py-7 sm:px-8 lg:px-10 lg:py-9">
            <p className="label">Question</p>
            <p className="mt-2 text-ink-2">{tower.question}</p>
            <p className="label mt-7">Answer</p>
            <AnswerText
              answer={tower.answer}
              claims={claims}
              active={active?.index ?? null}
              onSelect={(i) => take(i + 1)}
              revealed={revealed}
              className="mt-2 text-[1.06rem] leading-[1.95] text-ink sm:text-[1.12rem]"
            />
            <div className="mt-7 border-t border-line pt-4">
              <SourceRows sources={tower.report.sources} />
            </div>
          </div>
          <div className="relative min-h-[24rem] bg-cell px-5 py-7 sm:px-8 lg:px-10 lg:py-9">
            <p className="label flex items-center justify-between">
              <span>Claim detail</span>
              <span className="text-ink-3">{tower.report.verifier.split(":")[0]} · threshold 0.50</span>
            </p>
            <div className="mt-5">
              <AnimatePresence mode="wait" initial={false}>
                {active ? (
                  <motion.div
                    key={active.index}
                    initial={{ opacity: 0, y: 10, filter: "blur(4px)" }}
                    animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
                    exit={{ opacity: 0, y: -8, filter: "blur(4px)" }}
                    transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
                  >
                    <ClaimDetail claim={active} report={tower.report} />
                  </motion.div>
                ) : (
                  <motion.div key="idle" exit={{ opacity: 0 }} className="space-y-3" aria-hidden>
                    <div className="skeleton h-4 w-1/3" />
                    <div className="skeleton h-4 w-3/4" />
                    <div className="skeleton h-20 w-full" />
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 items-center gap-4 border-t border-line px-5 py-5 sm:px-8 md:grid-cols-[minmax(0,1fr)_11rem] md:gap-10 lg:px-10">
          <Scrubber value={pos} claims={claims} revealed={revealed} onChange={take} />
          <div className="flex items-baseline justify-between gap-3 md:block md:text-right">
            <p className="label">
              Claim{" "}
              <span className="relative inline-flex h-[1.1em] overflow-hidden align-bottom text-ink">
                <AnimatePresence mode="popLayout" initial={false}>
                  <motion.span
                    key={pos}
                    initial={{ y: "100%" }}
                    animate={{ y: 0 }}
                    exit={{ y: "-100%" }}
                    transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
                  >
                    {pad(Math.max(pos, 1))}
                  </motion.span>
                </AnimatePresence>
              </span>{" "}
              / {pad(n)}
            </p>
            <p className={`mt-1 text-sm font-medium transition-colors ${active ? VERDICTS[active.verdict].tone : "text-ink-3"}`}>
              {active ? VERDICTS[active.verdict].label : "Waiting"}
            </p>
          </div>
        </div>
      </div>
    </Section>
  );
}
