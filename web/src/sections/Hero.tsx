import { motion, useReducedMotion } from "motion/react";
import { GlyphField } from "../components/GlyphField";
import { CopyBar, LinkButton, Section, Ticker } from "../components/ui";
import { CTA, GITHUB_URL, SECONDARY_CTA } from "../lib/site";

const QUICKSTART = 'pip install "upheld[models]"';

/** Words rise out of a mask one after another. */
function Rise({ text, delay, className = "" }: { text: string; delay: number; className?: string }) {
  const reduce = useReducedMotion();
  return (
    <span className={`block ${className}`}>
      {text.split(" ").map((w, i) => (
        <span key={i} className="inline-block overflow-hidden pb-[0.08em] align-top">
          <motion.span
            className="inline-block"
            initial={reduce ? false : { y: "105%" }}
            animate={{ y: 0 }}
            transition={{ duration: 0.9, delay: delay + i * 0.06, ease: [0.16, 1, 0.3, 1] }}
          >
            {w}
            {" "}
          </motion.span>
        </span>
      ))}
    </span>
  );
}

const PROOF = [
  { value: "74.4", label: "macro-F1 on AttributionBench, in-distribution", note: "GPT-4 with chain of thought: 73.3" },
  { value: "83.1", label: "macro-F1 out-of-distribution", note: "Best fine-tuned model in the paper: 84.2" },
  { value: "100%", label: "of wrong numbers caught", note: "82 true claims, one number edited in each" },
  { value: "0", label: "API keys needed", note: "Runs on CPU, Apple silicon or NVIDIA" },
];

export function Hero() {
  const reduce = useReducedMotion();
  const fade = (delay: number) =>
    reduce
      ? {}
      : {
          initial: { opacity: 0, y: 12 },
          animate: { opacity: 1, y: 0 },
          transition: { duration: 0.8, delay, ease: [0.16, 1, 0.3, 1] as const },
        };

  return (
    <Section className="!border-t-0">
      <div className="px-5 pt-14 pb-12 sm:px-8 md:pt-20 lg:px-12 lg:pb-16">
        <motion.p {...fade(0)} className="label flex items-center gap-2.5">
          <span className="relative flex size-2">
            <span className="absolute inset-0 animate-ping bg-accent opacity-60" />
            <span className="relative size-2 bg-accent" />
          </span>
          Open source · Runs on your laptop
        </motion.p>
        <h1 className="display mt-7 text-[2.6rem] leading-[1.0] sm:text-6xl lg:text-[4.6rem] xl:text-[5.4rem]">
          <Rise text="AI cites its sources." delay={0.05} className="text-ink-h1" />
          <Rise text="upheld reads them." delay={0.3} />
        </h1>
        <div className="mt-10 grid grid-cols-1 gap-8 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end lg:gap-16">
          <motion.p {...fade(0.45)} className="max-w-[36rem] text-lg leading-relaxed text-ink-2">
            Point it at an answer from ChatGPT, Perplexity, Gemini or your own RAG pipeline. It splits the answer into claims, reads every page it cites, and
            tells you which claims the sources actually back. Runs locally: no API key, no account.
          </motion.p>
          <motion.div {...fade(0.55)} className="grid w-full max-w-[25rem] grid-cols-1 gap-5">
            <div className="flex flex-wrap items-center gap-x-4 gap-y-5">
              <LinkButton href={CTA.href} arrow>
                {CTA.label}
              </LinkButton>
              <LinkButton href={SECONDARY_CTA.href} variant="ghost">
                {SECONDARY_CTA.label}
              </LinkButton>
              <a href={GITHUB_URL} className="text-sm text-ink-2 underline decoration-line-strong underline-offset-4 hover:text-ink">
                GitHub
              </a>
            </div>
            <CopyBar label="Copy quickstart" text={QUICKSTART} />
          </motion.div>
        </div>
      </div>

      <div className="relative h-[24rem] overflow-hidden border-t border-line sm:h-[30rem] lg:h-[36rem]">
        <GlyphField
          mode="temple"
          cell={[6, 10]}
          className="absolute inset-0"
          label="A temple portico drawn in text characters, slowly turning. Eleven columns stand; one is broken, its drum lying on the steps."
        />
        <p className="label pointer-events-none absolute top-4 left-5 sm:left-8">Fig. 01 · Portico, in glyphs</p>
        <p className="label pointer-events-none absolute top-4 right-5 hidden sm:right-8 sm:block">Drag to turn</p>
        <p className="pointer-events-none absolute bottom-5 left-5 max-w-[22ch] text-sm text-ink-2 sm:left-8">
          Eleven columns hold. <span className="text-bad">One doesn't.</span>
        </p>
      </div>

      <div className="ruled grid-cols-2 border-t border-line lg:grid-cols-4">
        {PROOF.map((p) => (
          <div key={p.label} className="ticks px-5 py-7 sm:px-8 lg:px-10">
            <p className="display text-4xl leading-none text-ink sm:text-5xl">
              <Ticker value={p.value} />
            </p>
            <p className="mt-3 text-sm text-ink">{p.label}</p>
            <p className="mt-1 text-xs text-ink-3">{p.note}</p>
          </div>
        ))}
      </div>
    </Section>
  );
}
