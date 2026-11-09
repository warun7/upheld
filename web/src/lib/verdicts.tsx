import {
  ArrowsLeftRightIcon,
  CheckCircleIcon,
  EyeSlashIcon,
  LinkBreakIcon,
  QuotesIcon,
  UserSwitchIcon,
  XCircleIcon,
  type Icon,
} from "@phosphor-icons/react";
import type { LinkStatus, Verdict } from "./report";

export const VERDICTS: Record<Verdict, { label: string; short: string; icon: Icon; tone: string }> = {
  supported: {
    label: "Supported",
    short: "The cited source backs the claim.",
    icon: CheckCircleIcon,
    tone: "text-accent-ink",
  },
  unsupported: {
    label: "Unsupported",
    short: "The source is real and readable, but doesn't back the claim.",
    icon: XCircleIcon,
    tone: "text-bad",
  },
  wrong_entity: {
    label: "Wrong entity",
    short: "Reads as supported, but a name in the claim is nowhere in the source.",
    icon: UserSwitchIcon,
    tone: "text-warn",
  },
  misattributed: {
    label: "Misattributed",
    short: "The cited source doesn't back the claim, but another source in the same answer does.",
    icon: ArrowsLeftRightIcon,
    tone: "text-warn",
  },
  source_missing: {
    label: "Source missing",
    short: "The cited source isn't listed, or its URL is dead and was never archived.",
    icon: LinkBreakIcon,
    tone: "text-bad",
  },
  unverifiable: {
    label: "Unverifiable",
    short: "The source exists but couldn't be read, and neither could an archived copy: blocked, or no readable text.",
    icon: EyeSlashIcon,
    tone: "text-ink-2",
  },
  uncited: {
    label: "Uncited",
    short: "A factual-looking sentence with no citation at all.",
    icon: QuotesIcon,
    tone: "text-ink-2",
  },
};

export type Filter = "all" | "supported" | "flagged" | "unreadable";

/** Claim filters. Flagged is what `upheld audit --fail-on flagged` fails on. */
export const FILTERS: { id: Filter; label: string; match: (v: Verdict) => boolean }[] = [
  { id: "all", label: "All", match: () => true },
  { id: "supported", label: "Supported", match: (v) => v === "supported" },
  { id: "flagged", label: "Flagged", match: (v) => v === "unsupported" || v === "wrong_entity" || v === "misattributed" || v === "source_missing" },
  { id: "unreadable", label: "Can't read", match: (v) => v === "unverifiable" },
];

export const VERDICT_ORDER: Verdict[] = [
  "supported",
  "unsupported",
  "wrong_entity",
  "misattributed",
  "source_missing",
  "unverifiable",
  "uncited",
];

export const LINK_STATUS: Record<LinkStatus, { label: string; tone: string }> = {
  provided: { label: "Text provided", tone: "text-ink-2" },
  live: { label: "Live", tone: "text-accent-ink" },
  archived: { label: "Read from an archived copy", tone: "text-ink-2" },
  link_rot: { label: "Dead, archived copy exists", tone: "text-warn" },
  likely_fabricated: { label: "Dead and never archived", tone: "text-bad" },
  unreachable: { label: "Couldn't read", tone: "text-ink-2" },
  missing: { label: "Not in the answer's sources", tone: "text-bad" },
};

export function VerdictLabel({ verdict, className = "" }: { verdict: Verdict; className?: string }) {
  const v = VERDICTS[verdict];
  const Glyph = v.icon;
  return (
    <span className={`inline-flex items-center gap-1.5 font-medium ${v.tone} ${className}`}>
      <Glyph size={16} weight="bold" aria-hidden />
      {v.label}
    </span>
  );
}
