import { CaretDownIcon } from "@phosphor-icons/react";
import { AnimatePresence, LayoutGroup, motion, useInView, useReducedMotion } from "motion/react";
import { useId, useRef, useState, type ReactNode } from "react";
import { Scramble, Section, Ticker } from "../components/ui";
import { EDITS, EDIT_TABLE, METRICS, SUBSETS, SUBSET_TABLE, SYSTEMS, type BenchSystem, type Metric } from "../data/benchmarks";

const DOMAIN: [number, number] = [50, 90];
const TICKS = [50, 60, 70, 80, 90];
const pct = (v: number) => ((v - DOMAIN[0]) / (DOMAIN[1] - DOMAIN[0])) * 100;

function Segmented({ value, onChange }: { value: Metric; onChange: (m: Metric) => void }) {
  return (
    <div role="tablist" aria-label="Benchmark subset" className="inline-flex flex-wrap shadow-[inset_0_0_0_1px_var(--line-strong)]">
      {METRICS.map((m) => (
        <button
          key={m.id}
          role="tab"
          aria-selected={value === m.id}
          onClick={() => onChange(m.id)}
          className={`relative px-3.5 py-2 text-sm transition-colors ${value === m.id ? "text-on-accent" : "text-ink-2 hover:text-ink"}`}
        >
          {value === m.id && (
            <motion.span layoutId="metric-pill" className="absolute inset-0 bg-accent" transition={{ type: "spring", stiffness: 460, damping: 36 }} />
          )}
          <span className="relative">{m.label}</span>
        </button>
      ))}
    </div>
  );
}

function Dot({ s }: { s: BenchSystem }) {
  if (s.isDefault) return <span className="block size-3 bg-accent ring-[3px] ring-bg" />;
  if (s.group === "upheld") return <span className="block size-2.5 bg-ink-2 ring-2 ring-bg" />;
  return <span className="block size-2.5 bg-bg ring-[1.5px] ring-ink-3" />;
}

/** Dot plot: macro-F1 doesn't start at zero, so position (not bar length) carries the value. */
function DotPlot({ metric }: { metric: Metric }) {
  const reduce = useReducedMotion();
  const [hover, setHover] = useState<string | null>(null);
  const rows = SYSTEMS.filter((s) => s.scores[metric] !== undefined).sort((a, b) => b.scores[metric]! - a.scores[metric]!);

  return (
    <div className="relative">
      <div className="grid grid-cols-[minmax(0,1fr)_3.2rem] gap-x-4 sm:grid-cols-[minmax(0,14rem)_1fr_3.5rem]">
        <div className="hidden sm:block" />
        <div className="relative mb-2 h-5 font-mono text-[0.68rem] text-ink-3" aria-hidden>
          {TICKS.map((t) => (
            <span key={t} className="absolute -translate-x-1/2" style={{ left: `${pct(t)}%` }}>
              {t}
            </span>
          ))}
        </div>
        <div />
      </div>
      <LayoutGroup>
        <ul className="relative">
          {rows.map((s) => {
            const v = s.scores[metric]!;
            return (
              <motion.li
                layout={reduce ? false : "position"}
                transition={{ type: "spring", stiffness: 260, damping: 32 }}
                key={s.name}
                className="group grid grid-cols-[minmax(0,1fr)_3.2rem] items-center gap-x-4 border-t border-line py-2 first:border-t-0 sm:grid-cols-[minmax(0,14rem)_1fr_3.5rem]"
                onMouseEnter={() => setHover(s.name)}
                onMouseLeave={() => setHover(null)}
              >
                <div className="col-span-2 min-w-0 sm:col-span-1">
                  <p className={`truncate text-sm transition-colors ${s.isDefault ? "font-semibold text-ink" : "text-ink-2 group-hover:text-ink"}`}>{s.name}</p>
                  <p className="hidden truncate text-xs text-ink-3 sm:block">{s.detail}</p>
                </div>
                <div className="relative h-8">
                  <div className="absolute inset-0 overflow-x-clip">
                    {TICKS.map((t) => (
                      <span key={t} className="absolute inset-y-0 w-px bg-line" style={{ left: `${pct(t)}%` }} aria-hidden />
                    ))}
                    <span
                      className="absolute top-1/2 left-0 h-px bg-line-strong opacity-0 transition-opacity group-hover:opacity-100"
                      style={{ width: `${pct(v)}%` }}
                      aria-hidden
                    />
                    {/* A full-width layer slid by the value, so the move animates as a transform. */}
                    <div
                      className="absolute inset-y-0 left-0 w-full transition-transform duration-700 ease-out-expo"
                      style={{ transform: `translateX(${pct(v)}%)` }}
                    >
                      <span className="absolute top-1/2 left-0 -translate-x-1/2 -translate-y-1/2 transition-transform duration-300 group-hover:scale-125">
                        <Dot s={s} />
                      </span>
                    </div>
                  </div>
                  <AnimatePresence>
                    {hover === s.name && (
                      <motion.div
                        initial={{ opacity: 0, y: 4 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: 4 }}
                        transition={{ duration: 0.15 }}
                        className="pointer-events-none absolute bottom-full z-10 mb-1 w-56 -translate-x-1/2 bg-cell p-3 text-xs shadow-[inset_0_0_0_1px_var(--line-strong),var(--shadow)]"
                        style={{ left: `${Math.min(Math.max(pct(v), 22), 78)}%` }}
                      >
                        <p className="font-medium text-ink">{s.name}</p>
                        <p className="mt-0.5 text-ink-2">{s.detail}</p>
                        <p className="mt-2 font-mono text-ink">
                          {v.toFixed(1)} <span className="text-ink-3">macro-F1</span>
                        </p>
                        <p className="mt-1 text-ink-3">Fit to the benchmark: {s.fit}</p>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
                <p className={`text-right font-mono text-sm ${s.isDefault ? "font-semibold text-accent" : "text-ink-2"}`}>{v.toFixed(1)}</p>
              </motion.li>
            );
          })}
        </ul>
      </LayoutGroup>
      <ul className="mt-5 flex flex-wrap gap-x-5 gap-y-2 text-xs text-ink-2">
        <li className="inline-flex items-center gap-2">
          <span className="block size-3 bg-accent" /> upheld default
        </li>
        <li className="inline-flex items-center gap-2">
          <span className="block size-2.5 bg-ink-2" /> other upheld verifiers
        </li>
        <li className="inline-flex items-center gap-2">
          <span className="block size-2.5 ring-[1.5px] ring-ink-3 ring-inset" /> from the AttributionBench paper
        </li>
      </ul>
    </div>
  );
}

function Disclosure({ label, children }: { label: string; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  return (
    <div className="px-5 py-5 sm:px-8 lg:px-12">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((o) => !o)}
        className="group inline-flex items-center gap-2.5 text-sm font-medium text-ink-2 hover:text-ink"
      >
        <span className="grid size-5 place-items-center shadow-[inset_0_0_0_1px_var(--line-strong)] transition-colors group-hover:shadow-[inset_0_0_0_1px_var(--ink-3)]">
          <CaretDownIcon size={11} weight="bold" className={`transition-transform duration-300 ${open ? "rotate-180" : ""}`} aria-hidden />
        </span>
        {label}
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            id={id}
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
            className="overflow-hidden"
          >
            <div className="overflow-x-auto pt-5">{children}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function SubsetTable() {
  const cols = [...SUBSETS.id, "ID avg", ...SUBSETS.ood, "OOD avg"];
  return (
    <table className="w-full min-w-[56rem] text-left text-sm">
      <thead className="text-xs text-ink-3">
        <tr>
          <th className="py-2 pr-4 font-medium">Verifier</th>
          <th className="py-2 pr-4 font-medium">Threshold</th>
          {cols.map((c) => (
            <th key={c} className="py-2 pr-4 text-right font-medium">
              {c}
            </th>
          ))}
        </tr>
      </thead>
      <tbody className="font-mono text-ink-2">
        {SUBSET_TABLE.map((r) => (
          <tr key={r.name} className={`border-t border-line transition-colors hover:bg-cell ${r.name === "ensemble" ? "text-ink" : ""}`}>
            <td className="py-2 pr-4 font-sans">{r.name}</td>
            <td className="py-2 pr-4">{r.threshold}</td>
            {SUBSETS.id.map((c) => (
              <td key={c} className="py-2 pr-4 text-right">
                {r.id[c].toFixed(1)}
              </td>
            ))}
            <td className="py-2 pr-4 text-right font-semibold">{r.id.avg.toFixed(1)}</td>
            {SUBSETS.ood.map((c) => (
              <td key={c} className="py-2 pr-4 text-right">
                {r.ood[c].toFixed(1)}
              </td>
            ))}
            <td className="py-2 pr-4 text-right font-semibold">{r.ood.avg.toFixed(1)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

const NOTES = [
  {
    title: "Lightly supervised, not zero-shot",
    body: "The ensemble's four numbers were fit on 2,000 train rows. The clean zero-shot comparison is MiniCheck alone at 0.5: 73.3 in-distribution, level with GPT-4.",
  },
  {
    title: "Most of the gain is out-of-distribution",
    body: "+3.8 over MiniCheck where answers copy their evidence and word overlap is a strong signal. In-distribution it adds 0.5, within noise.",
  },
  {
    title: "ExpertQA is still hard",
    body: "Long, expert-written claims score 57.8, below GPT-4's 59.2. Every model in the paper stays under 62.",
  },
  {
    title: "The entity check costs 2 points",
    body: "It false-alarms on 6% of supported claims, mostly names written differently. It stays on because it catches 98% of names the source never mentions.",
  },
];

export function Benchmarks() {
  const [metric, setMetric] = useState<Metric>("id");
  const note = METRICS.find((m) => m.id === metric)!.note;
  return (
    <Section id="benchmarks">
      <div className="ruled grid-cols-1 lg:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)]">
        <div className="flex flex-col px-5 py-16 sm:px-8 md:py-20 lg:px-12">
          <p className="label">AttributionBench</p>
          <h2 className="display mt-5 text-4xl leading-[1.02] md:text-[3.25rem]">Graded against 3,296 human labels</h2>
          <p className="mt-5 max-w-[46ch] text-lg leading-relaxed text-ink-2">
            Claims from seven datasets, each with the evidence it cited and a human verdict. Thresholds were picked on the dev split, never on test.
          </p>
          <div className="mt-auto grid grid-cols-2 gap-8 pt-12">
            <div>
              <p className="text-sm text-ink-2">In-distribution</p>
              <p className="display mt-2 text-5xl leading-none text-accent md:text-6xl">
                <Ticker value="74.4" />
              </p>
              <p className="mt-2 text-xs text-ink-3">macro-F1. GPT-4 + CoT: 73.3</p>
            </div>
            <div>
              <p className="text-sm text-ink-2">Out-of-distribution</p>
              <p className="display mt-2 text-5xl leading-none text-ink md:text-6xl">
                <Ticker value="83.1" />
              </p>
              <p className="mt-2 text-xs text-ink-3">Best fine-tuned: 84.2</p>
            </div>
          </div>
        </div>

        <div className="bg-cell! px-5 py-8 sm:px-8 lg:px-10 lg:py-12">
          <Segmented value={metric} onChange={setMetric} />
          <AnimatePresence mode="wait" initial={false}>
            <motion.p
              key={metric}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={{ duration: 0.18 }}
              className="mt-4 min-h-10 text-sm text-ink-3"
            >
              {note}. Macro-F1, test split.
            </motion.p>
          </AnimatePresence>
          <div className="mt-4">
            <DotPlot metric={metric} />
          </div>
        </div>
      </div>

      <div className="ruled grid-cols-1 border-t border-line sm:grid-cols-2 lg:grid-cols-4">
        {NOTES.map((n) => (
          <div key={n.title} className="ticks px-5 py-8 sm:px-8">
            <h3 className="font-semibold tracking-[-0.01em]">{n.title}</h3>
            <p className="mt-2 text-sm leading-relaxed text-ink-2">{n.body}</p>
          </div>
        ))}
      </div>

      <div className="border-t border-line">
        <Disclosure label="Every subset, every verifier">
          <SubsetTable />
          <p className="mt-3 text-xs text-ink-3">
            Runtime per example on an Apple M5 Pro: MiniCheck 0.14-0.91 s, LettuceDetect 0.12-0.22 s, word overlap under 1 ms.
          </p>
        </Disclosure>
      </div>
    </Section>
  );
}

function Edited({ text, swap, play, tone }: { text: string; swap: string[]; play: boolean; tone: "old" | "new" }) {
  const [from, to] = swap;
  const word = tone === "old" ? from : to;
  if (!word || !text.includes(word)) return <>{text}</>;
  const [a, b] = text.split(word, 2);
  return (
    <>
      {a}
      {tone === "new" ? (
        <span className="span-flag font-medium text-ink">
          <Scramble from={from} to={to} play={play} />
        </span>
      ) : (
        <span className="font-medium text-ink">{word}</span>
      )}
      {b}
    </>
  );
}

function EditTile({ e }: { e: (typeof EDITS)[number] }) {
  const ref = useRef<HTMLElement>(null);
  const play = useInView(ref, { once: true, amount: 0.5 });
  const rate = Number.parseFloat(e.headline);
  const weak = e.tone === "weak";
  return (
    <article ref={ref} className="ticks flex h-full flex-col px-5 py-8 sm:px-8 lg:px-10 lg:py-10">
      <div className="flex items-start justify-between gap-6">
        <h3 className="max-w-[24ch] text-lg font-semibold tracking-[-0.02em]">{e.title}</h3>
        <span className="label shrink-0">{e.n} edits</span>
      </div>
      <p className={`display mt-8 text-6xl leading-none md:text-7xl ${weak ? "text-warn" : "text-ink"}`}>
        <Ticker value={e.headline} />
      </p>
      <div className="relative mt-5 h-1 bg-cell-2" aria-hidden>
        <motion.div
          className={`absolute inset-y-0 left-0 ${weak ? "bg-warn" : "bg-accent"}`}
          initial={{ width: 0 }}
          animate={{ width: play ? `${rate}%` : 0 }}
          transition={{ duration: 1.4, ease: [0.16, 1, 0.3, 1] }}
        />
      </div>
      <p className="mt-4 text-ink-2">
        {e.caption}. {e.sub}
      </p>
      <div className="mt-auto space-y-2 pt-8 text-sm leading-relaxed">
        <p className="text-ink-3">
          <span className="label mr-2 inline-block w-11">Before</span>
          <Edited text={e.before} swap={e.changed} play={play} tone="old" />
        </p>
        <p className="text-ink-2">
          <span className="label mr-2 inline-block w-11">After</span>
          <Edited text={e.after} swap={e.changed} play={play} tone="new" />
        </p>
      </div>
    </article>
  );
}

export function EditedClaims() {
  return (
    <Section>
      <div className="grid grid-cols-1 gap-6 px-5 py-16 sm:px-8 md:py-20 lg:grid-cols-2 lg:items-end lg:px-12">
        <h2 className="display text-4xl leading-[1.02] md:text-[3.25rem]">Then we broke true claims on purpose</h2>
        <p className="max-w-[50ch] text-lg leading-relaxed text-ink-2 lg:justify-self-end">
          Take a claim humans marked supported, edit it so the evidence no longer backs it, and see if upheld notices. A catch only counts if the unedited claim
          passed first.
        </p>
      </div>
      <div className="ruled grid-cols-1 border-t border-line md:grid-cols-2">
        {EDITS.map((e) => (
          <EditTile key={e.id} e={e} />
        ))}
      </div>
      <div className="border-t border-line">
        <Disclosure label="All four verifiers">
          <table className="w-full min-w-[48rem] text-left text-sm">
            <thead className="text-xs text-ink-3">
              <tr>
                {["Verifier", "Unedited pass", "Wrong number", "Name not in source", "with entity check", "Name in source", "Joined claims"].map((h) => (
                  <th key={h} className="py-2 pr-4 font-medium">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="font-mono text-ink-2">
              {EDIT_TABLE.map((r) => (
                <tr key={r.verifier} className={`border-t border-line transition-colors hover:bg-cell ${r.verifier === "ensemble" ? "text-ink" : ""}`}>
                  <td className="py-2 pr-4 font-sans">{r.verifier}</td>
                  <td className="py-2 pr-4">{r.pass}</td>
                  <td className="py-2 pr-4">{r.wrongNumber}</td>
                  <td className="py-2 pr-4">{r.absent}</td>
                  <td className="py-2 pr-4">{r.absentEntity}</td>
                  <td className="py-2 pr-4">{r.swap}</td>
                  <td className="py-2 pr-4">{r.multi}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-3 text-xs text-ink-3">
            Edits are synthetic and the claims come from AttributionBench, so these say whether each check works, not how often each failure happens in the wild.
          </p>
        </Disclosure>
      </div>
    </Section>
  );
}
