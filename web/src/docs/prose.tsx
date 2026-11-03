import { CheckIcon, CopyIcon, InfoIcon } from "@phosphor-icons/react";
import { useState, type ReactNode } from "react";

/** One docs page section. The id is its anchor and its sidebar entry. */
export function DocSection({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section id={id} className="border-b border-line px-5 py-12 last:border-b-0 sm:px-8 md:py-14 lg:px-12">
      <h2 className="display text-[1.85rem] leading-[1.08] md:text-[2.25rem]">
        <a href={`#${id}`} className="group">
          {title}
          <span className="ml-2 text-ink-3 opacity-0 transition-opacity group-hover:opacity-100" aria-hidden>
            #
          </span>
        </a>
      </h2>
      <div className="mt-6 max-w-[72ch] space-y-5 leading-relaxed text-ink-2">{children}</div>
    </section>
  );
}

export function H3({ children }: { children: ReactNode }) {
  return <h3 className="pt-3 font-semibold tracking-[-0.01em] text-ink">{children}</h3>;
}

/** Inline code. */
export function C({ children }: { children: ReactNode }) {
  return <code className="bg-cell-2 px-1 py-0.5 font-mono text-[0.84em] text-ink">{children}</code>;
}

export function A({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a href={href} className="text-ink underline decoration-line-strong underline-offset-[0.2em] transition-colors hover:decoration-accent">
      {children}
    </a>
  );
}

/** A code block with a copy button. Lines starting with # are dimmed as comments. */
export function Code({ children, label }: { children: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(children);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      // clipboard blocked; the text is selectable
    }
  };
  return (
    <div className="max-w-none bg-cell shadow-[inset_0_0_0_1px_var(--line)]">
      <div className="flex h-9 items-center border-b border-line pr-1.5 pl-4">
        <span className="label">{label ?? "shell"}</span>
        <button
          type="button"
          onClick={copy}
          className="ml-auto inline-flex h-7 items-center gap-1.5 px-2.5 text-xs text-ink-2 transition-colors hover:bg-cell-2 hover:text-ink"
        >
          {copied ? <CheckIcon size={13} weight="bold" className="text-accent-ink" /> : <CopyIcon size={13} weight="bold" />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre className="overflow-x-auto px-4 py-4 font-mono text-[0.8rem] leading-6">
        <code>
          {children.split("\n").map((l, i) => (
            <span key={i} className={`block ${l.trimStart().startsWith("#") ? "text-ink-3" : "text-ink"}`}>
              {l || " "}
            </span>
          ))}
        </code>
      </pre>
    </div>
  );
}

/** A simple ruled table. The first column is set in mono when `mono` is on. */
export function Table({ head, rows, mono = true }: { head: string[]; rows: ReactNode[][]; mono?: boolean }) {
  return (
    <div className="max-w-none overflow-x-auto shadow-[inset_0_0_0_1px_var(--line)]">
      <table className="w-full min-w-[34rem] border-collapse text-left text-sm">
        <thead>
          <tr className="border-b border-line">
            {head.map((h) => (
              <th key={h} scope="col" className="label px-4 py-3 font-normal">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-b border-line align-top last:border-b-0">
              {r.map((cell, j) => (
                <td key={j} className={`px-4 py-3 leading-relaxed ${j === 0 ? `text-ink ${mono ? "font-mono text-[0.8rem] whitespace-nowrap" : ""}` : "text-ink-2"}`}>
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Note({ children }: { children: ReactNode }) {
  return (
    <div className="flex gap-3 border-l-2 border-accent bg-cell px-4 py-3 text-sm leading-relaxed text-ink-2">
      <InfoIcon size={17} weight="bold" className="mt-0.5 shrink-0 text-accent-ink" aria-hidden />
      <div>{children}</div>
    </div>
  );
}
