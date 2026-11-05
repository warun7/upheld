import { ArrowRightIcon, CheckIcon, CopyIcon } from "@phosphor-icons/react";
import { AnimatePresence, motion, useInView, useReducedMotion, useScroll, useTransform, type MotionValue } from "motion/react";
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";

/** A full-bleed rule with the framed column inside it, crosses where they meet. */
export function Section({
  id,
  children,
  className = "",
  frameClassName = "",
}: {
  id?: string;
  children: ReactNode;
  className?: string;
  frameClassName?: string;
}) {
  return (
    <section id={id} className={`border-t border-line ${className}`}>
      <div className={`frame ${frameClassName}`}>
        <span className="cross -left-[5px]" aria-hidden />
        <span className="cross -right-[5px]" aria-hidden />
        {children}
      </div>
    </section>
  );
}

/** Words rise out of a mask one after another. */
export function Rise({ text, delay, className = "" }: { text: string; delay: number; className?: string }) {
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

/** Text that rolls up to an identical copy on hover. */
export function Roll({ children }: { children: string }) {
  return (
    <span className="roll">
      <span data-text={children}>{children}</span>
    </span>
  );
}

export function LinkButton({
  href,
  children,
  variant = "primary",
  size,
  icon,
  arrow = false,
  className = "",
}: {
  href: string;
  children: string;
  variant?: "primary" | "ghost";
  size?: "sm";
  icon?: ReactNode;
  arrow?: boolean;
  className?: string;
}) {
  return (
    <a href={href} className={`btn btn-${variant} ${size === "sm" ? "btn-sm" : ""} ${className}`}>
      {icon}
      <Roll>{children}</Roll>
      {arrow && <ArrowRightIcon size={15} weight="bold" className="arrow" aria-hidden />}
    </a>
  );
}

/** A hatched bar that copies a command, with the label flipping to COPIED. */
export function CopyBar({ label, text, className = "" }: { label: string; text: string; className?: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      // clipboard blocked: nothing to undo
    }
  };
  return (
    <button
      type="button"
      onClick={copy}
      className={`group relative flex h-10 w-full items-center gap-3 overflow-hidden px-3.5 text-left shadow-[inset_0_0_0_1px_var(--line-strong)] transition-colors hover:shadow-[inset_0_0_0_1px_var(--ink-3)] ${className}`}
    >
      <span className="hatch absolute inset-0 opacity-70" aria-hidden />
      <motion.span
        className="absolute inset-y-0 left-0 bg-accent"
        initial={false}
        animate={{ width: copied ? "100%" : "0%" }}
        transition={{ duration: copied ? 0.45 : 0.3, ease: [0.16, 1, 0.3, 1] }}
        aria-hidden
      />
      <span className={`label relative transition-colors ${copied ? "!text-on-accent" : "!text-ink"}`}>
        <AnimatePresence mode="wait" initial={false}>
          <motion.span
            key={copied ? "y" : "n"}
            className="inline-block"
            initial={{ y: 10, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: -10, opacity: 0 }}
            transition={{ duration: 0.2 }}
          >
            {copied ? "Copied to clipboard" : label}
          </motion.span>
        </AnimatePresence>
      </span>
      <span className={`relative ml-auto transition-colors ${copied ? "text-on-accent" : "text-ink-2 group-hover:text-ink"}`}>
        <AnimatePresence mode="wait" initial={false}>
          <motion.span
            key={copied ? "y" : "n"}
            className="block"
            initial={{ scale: 0.4, rotate: -40, opacity: 0 }}
            animate={{ scale: 1, rotate: 0, opacity: 1 }}
            exit={{ scale: 0.4, opacity: 0 }}
            transition={{ type: "spring", stiffness: 500, damping: 28 }}
          >
            {copied ? <CheckIcon size={15} weight="bold" /> : <CopyIcon size={15} weight="bold" />}
          </motion.span>
        </AnimatePresence>
      </span>
    </button>
  );
}

const easeOut = (x: number) => 1 - Math.pow(1 - x, 4);

/**
 * Shows every number in a string. The final value is in the markup from the first render, so it reads without JS or under
 * reduced motion. The first time it scrolls into view, the numbers count up from zero.
 */
export function Ticker({ value, className = "", duration = 1400 }: { value: string; className?: string; duration?: number }) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true, amount: 0.6 });
  const reduce = useReducedMotion();
  const [k, setK] = useState(1);

  // A layout effect, so the count starts from zero before the browser paints anything else.
  useLayoutEffect(() => {
    if (!inView || reduce) return;
    setK(0);
    let raf = 0;
    const t0 = performance.now();
    const step = (now: number) => {
      const x = Math.min(1, (now - t0) / duration);
      setK(easeOut(x));
      if (x < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [inView, reduce, duration]);

  const out = value.replace(/\d+(?:[.,]\d+)?/g, (m) => {
    const decimals = m.includes(".") ? m.split(".")[1].length : 0;
    const n = Number(m.replace(",", ""));
    const v = n * k;
    const s = v.toFixed(decimals);
    return m.includes(",") ? Number(s).toLocaleString("en-US") : s;
  });
  return (
    <span ref={ref} className={`tabular-nums ${className}`} aria-label={value}>
      <span aria-hidden>{out}</span>
    </span>
  );
}

const NOISE = "!<>-_/[]{}=+*^?#%@01";

/** Decodes from `from` to `to` through random glyphs when `play` turns true. */
export function Scramble({ from, to, play, className = "" }: { from: string; to: string; play: boolean; className?: string }) {
  const reduce = useReducedMotion();
  const [text, setText] = useState(reduce ? to : from);
  useEffect(() => {
    if (reduce) {
      setText(to);
      return;
    }
    if (!play) return;
    let raf = 0;
    const t0 = performance.now();
    const len = Math.max(from.length, to.length);
    const step = (now: number) => {
      const e = (now - t0) / 900;
      let s = "";
      for (let i = 0; i < len; i++) {
        const settle = 0.25 + (i / len) * 0.6;
        if (e >= settle) s += to[i] ?? "";
        else if (e < 0.15) s += from[i] ?? "";
        else s += NOISE[Math.floor(Math.random() * NOISE.length)];
      }
      setText(s);
      if (e < 0.9) raf = requestAnimationFrame(step);
      else setText(to);
    };
    const delay = window.setTimeout(() => (raf = requestAnimationFrame(step)), 350);
    return () => {
      window.clearTimeout(delay);
      cancelAnimationFrame(raf);
    };
  }, [play, from, to, reduce]);
  return (
    <span className={className} aria-label={to}>
      <span aria-hidden>{text}</span>
    </span>
  );
}

function LitWord({ word, progress, range }: { word: string; progress: MotionValue<number>; range: [number, number] }) {
  const opacity = useTransform(progress, range, [0.16, 1]);
  return <motion.span style={{ opacity }}>{word} </motion.span>;
}

/** A statement whose words light up in reading order as it scrolls through the viewport. */
export function ScrollLit({ text, className = "" }: { text: string; className?: string }) {
  const ref = useRef<HTMLParagraphElement>(null);
  const reduce = useReducedMotion();
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start 85%", "end 45%"] });
  const words = text.split(" ");
  if (reduce) return <p className={className}>{text}</p>;
  return (
    <p ref={ref} className={className}>
      {words.map((w, i) => (
        <LitWord key={i} word={w} progress={scrollYProgress} range={[i / words.length, (i + 1) / words.length]} />
      ))}
    </p>
  );
}
