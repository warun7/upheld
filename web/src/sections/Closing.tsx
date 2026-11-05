import { ArrowRightIcon, CheckIcon, CopyIcon } from "@phosphor-icons/react";
import { AnimatePresence, motion } from "motion/react";
import { useState } from "react";
import { GlyphField } from "../components/GlyphField";
import { GithubMark } from "../components/icons";
import { Roll, Section } from "../components/ui";
import { FRESH_VERIFIED_CITATIONS, FRESH_VERIFIERS } from "../data/benchmarks";
import { BROKEN, PATHS, SNIPPETS, type SnippetTab } from "../data/install";
import { CTA, GITHUB_URL } from "../lib/site";

const REASONING = [
  {
    title: "Contradictions in the source's own words",
    example: "“The Great Wall of China is visible from the Moon with the naked eye” passes at 0.59. The page says it cannot be seen.",
    detail: "MiniCheck scores it 0.08, but word overlap and LettuceDetect both give 1.0 and outvote it. Found while building this site.",
  },
  {
    title: "One-step inferences",
    example: "Source: “mean change in body weight ... -14.9%”. Answer: “an average weight loss of 14.9%”.",
    detail: "MiniCheck scores that 0.08, so a true claim is flagged. Same for dates that need arithmetic.",
  },
  {
    title: "The wrong party",
    example: "A result credited to Stoicism when the page says Epicureanism, and mentions both.",
    detail: "Caught 35% of the time. Word overlap finds every word of the edited claim in the source.",
  },
  {
    title: "Same number, different unit",
    example: "“It stands 410 metres tall” passes, because the page gives the base as 410 ft.",
    detail: "The number check matches digits, not quantities. Also found while building this site.",
  },
];

const COVERAGE = [
  { title: "Expert content", detail: "57.8 macro-F1 on ExpertQA. Expect more mistakes on specialist claims." },
  { title: "Speed", detail: "0.3-1 s per claim per source on an Apple M5 Pro, several times slower on CPU." },
  { title: "No OCR", detail: "PDFs are read, but a scan with no text layer comes back unverifiable rather than guessed at." },
  { title: "Sentence-level claims", detail: "A sentence with two facts is judged as one unit." },
];

export function Limits() {
  return (
    <Section id="limits">
      <div className="grid grid-cols-1 gap-6 px-5 py-16 sm:px-8 md:py-20 lg:grid-cols-2 lg:items-end lg:px-12">
        <h2 className="display text-4xl leading-[1.02] md:text-[3.25rem]">Where it still misses</h2>
        <p className="max-w-[48ch] text-lg leading-relaxed text-ink-2 lg:justify-self-end">
          A checker you can't calibrate is worse than none. These are the known failure modes, each with the case that shows it.
        </p>
      </div>
      <div className="ruled grid-cols-1 border-t border-line lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <ol>
          {REASONING.map((r, i) => (
            <li key={r.title} className="ticks grid grid-cols-[2.25rem_minmax(0,1fr)] border-b border-line px-5 py-7 last:border-b-0 sm:px-8 lg:px-10">
              <span className="font-mono text-xs text-ink-3">{String(i + 1).padStart(2, "0")}</span>
              <div>
                <p className="font-semibold tracking-[-0.01em]">{r.title}</p>
                <p className="mt-3 border-l-2 border-bad bg-cell px-4 py-2.5 text-sm leading-relaxed text-ink">{r.example}</p>
                <p className="mt-3 text-sm leading-relaxed text-ink-2">{r.detail}</p>
              </div>
            </li>
          ))}
        </ol>
        <div className="px-5 py-7 sm:px-8 lg:px-10">
          <p className="label">Coverage gaps</p>
          <dl className="mt-6 space-y-7">
            {COVERAGE.map((c) => (
              <div key={c.title}>
                <dt className="font-semibold tracking-[-0.01em]">{c.title}</dt>
                <dd className="mt-1.5 text-sm leading-relaxed text-ink-2">{c.detail}</dd>
              </div>
            ))}
          </dl>
        </div>
      </div>
    </Section>
  );
}

const EXPECTATIONS = [
  "No API key and no account. Nothing leaves your machine except the requests for the cited pages.",
  "The first run downloads about 4 GB of models into ~/.cache/huggingface, which takes minutes. After that, loading them takes about half a minute, and each audit takes seconds.",
  "The default verifier takes 0.3–1 s per claim per source on an Apple M5 Pro, and several times longer on CPU.",
  "The judge is opt-in. Its install builds llama.cpp, downloads 8.7 GB, and needs about 9 GB of free memory.",
  "Every report names its verifier and threshold.",
];

function VerifierChooser() {
  return (
    <div className="border-t border-line px-5 py-10 sm:px-8 lg:px-12">
      <p className="label">Choosing a verifier</p>
      <p className="mt-3 max-w-[70ch] text-sm text-ink-3">
        Agreement and flags are from the {FRESH_VERIFIED_CITATIONS} labeled 2026 citations, with the verifier alone. Bad means partial or unsupported. See Quality
        above.
      </p>
      <div className="mt-5 overflow-x-auto">
        <table className="w-full min-w-[56rem] text-left text-sm">
          <thead className="text-xs text-ink-3">
            <tr>
              {["Verifier", "Passages per claim", "Agreement", "Bad citations flagged", "Good citations flagged", "Time per claim", "Memory"].map((h) => (
                <th key={h} className="py-2 pr-4 font-medium">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="text-ink-2">
            {FRESH_VERIFIERS.map((v) => (
              <tr key={v.verifier} className="border-t border-line align-top">
                <td className="py-3 pr-4 font-mono text-ink">{v.verifier}</td>
                <td className="py-3 pr-4 font-mono">{v.passages}</td>
                <td className="py-3 pr-4 font-mono">{v.agreement}%</td>
                <td className="py-3 pr-4 font-mono">{v.badFlagged}%</td>
                <td className="py-3 pr-4 font-mono">{v.goodFlagged}%</td>
                <td className="py-3 pr-4">{v.time}</td>
                <td className="py-3 pr-4">{v.memory}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-4 text-sm text-ink">
        Pick <span className="font-mono">ensemble</span> for speed, <span className="font-mono">ensemble+judge</span> if you'll act on the flags.
      </p>
    </div>
  );
}

function Broken() {
  return (
    <div className="border-t border-line px-5 py-10 sm:px-8 lg:px-12">
      <p className="label">When it looks broken</p>
      <div className="mt-5 overflow-x-auto">
        <table className="w-full min-w-[40rem] text-left text-sm">
          <thead className="text-xs text-ink-3">
            <tr>
              <th className="py-2 pr-6 font-medium">What you see</th>
              <th className="py-2 font-medium">What's going on</th>
            </tr>
          </thead>
          <tbody>
            {BROKEN.map(([problem, fix]) => (
              <tr key={problem} className="border-t border-line align-top">
                <td className="py-3 pr-6 font-medium text-ink">{problem}</td>
                <td className="py-3 text-ink-2">{fix}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function Install() {
  const [tab, setTab] = useState<SnippetTab>("CLI");
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(SNIPPETS[tab]);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      // clipboard blocked; the text is selectable
    }
  };
  const lines = SNIPPETS[tab].split("\n");
  const path = PATHS.find((p) => p.tab === tab)!;

  return (
    <Section id="install">
      <div className="ruled grid-cols-1 lg:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)]">
        <div className="px-5 py-16 sm:px-8 md:py-20 lg:px-12">
          <h2 className="display text-4xl leading-[1.02] md:text-[3.25rem]">One engine, four ways in</h2>
          <p className="mt-5 max-w-[44ch] text-lg leading-relaxed text-ink-2">
            A CLI for spot checks, a Python library for your eval suite, an HTTP API to gate a RAG pipeline, and an MCP server so your agent checks its own
            citations. The first run is the slow one.
          </p>
          <ul className="mt-10 space-y-4 text-ink-2">
            {EXPECTATIONS.map((t) => (
              <li key={t} className="flex gap-3">
                <span className="mt-[0.4rem] grid size-3.5 shrink-0 place-items-center bg-accent text-on-accent">
                  <CheckIcon size={9} weight="bold" aria-hidden />
                </span>
                <span>{t}</span>
              </li>
            ))}
          </ul>
        </div>
        <div className="flex min-w-0 flex-col bg-cell!">
          <div className="flex items-center border-b border-line">
            {(Object.keys(SNIPPETS) as SnippetTab[]).map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => setTab(t)}
                className={`relative h-12 border-r border-line px-3.5 text-sm transition-colors sm:px-5 ${tab === t ? "text-ink" : "text-ink-3 hover:text-ink"}`}
              >
                {tab === t && <motion.span layoutId="code-tab" className="absolute inset-x-0 -bottom-px h-0.5 bg-accent" transition={{ type: "spring", stiffness: 460, damping: 36 }} />}
                {t}
              </button>
            ))}
            <button
              type="button"
              onClick={copy}
              className="ml-auto mr-3 inline-flex h-8 items-center gap-1.5 px-3 text-xs text-ink-2 transition-colors hover:bg-cell-2 hover:text-ink"
            >
              <AnimatePresence mode="wait" initial={false}>
                <motion.span
                  key={copied ? "y" : "n"}
                  initial={{ scale: 0.5, opacity: 0 }}
                  animate={{ scale: 1, opacity: 1 }}
                  exit={{ scale: 0.5, opacity: 0 }}
                  transition={{ type: "spring", stiffness: 500, damping: 26 }}
                  className="block"
                >
                  {copied ? <CheckIcon size={14} weight="bold" className="text-accent-ink" /> : <CopyIcon size={14} weight="bold" />}
                </motion.span>
              </AnimatePresence>
              {copied ? "Copied" : "Copy"}
            </button>
          </div>
          <div className="border-b border-line px-5 py-5 sm:px-6">
            <p className="label text-accent-ink">{path.name}</p>
            <div className="mt-3 space-y-3 text-sm leading-relaxed text-ink-2">
              {path.text.map((t) => (
                <p key={t}>{t}</p>
              ))}
            </div>
          </div>
          <AnimatePresence mode="wait" initial={false}>
            <motion.pre
              key={tab}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.2 }}
              className="flex-1 overflow-x-auto py-6 font-mono text-[0.8rem] leading-6"
            >
              <code className="grid grid-cols-[3rem_auto]">
                {lines.map((l, i) => (
                  <span key={i} className="contents">
                    <span className="pr-4 text-right text-ink-3 select-none">{i + 1}</span>
                    <span className={`pr-6 ${l.trimStart().startsWith("#") ? "text-ink-3" : "text-ink"} ${i === lines.length - 1 ? "caret" : ""}`}>
                      {l || " "}
                    </span>
                  </span>
                ))}
              </code>
            </motion.pre>
          </AnimatePresence>
        </div>
      </div>
      <VerifierChooser />
      <Broken />
    </Section>
  );
}

export function FinalCta() {
  return (
    <section className="bg-accent text-on-accent">
      <div className="frame !border-on-accent/25">
        <div className="px-5 pt-20 pb-6 sm:px-8 md:pt-28 lg:px-12">
          <h2 className="display max-w-[16ch] text-5xl leading-[0.98] md:text-7xl">Check your own answer. See what holds up.</h2>
          <div className="mt-10 flex flex-wrap gap-x-4 gap-y-5">
            <a href={CTA.href} className="btn btn-invert">
              <Roll>{CTA.label}</Roll>
              <ArrowRightIcon size={15} weight="bold" className="arrow" aria-hidden />
            </a>
            <a href={GITHUB_URL} className="btn btn-outline-invert">
              <GithubMark />
              <Roll>View on GitHub</Roll>
            </a>
          </div>
        </div>
        <GlyphField
          mode="text"
          text="upheld"
          ink="--on-accent"
          read="--on-accent"
          cell={[8, 14]}
          className="relative h-48 sm:h-64 md:h-80"
          label="The word upheld drawn in shimmering text characters."
        />
      </div>
    </section>
  );
}
