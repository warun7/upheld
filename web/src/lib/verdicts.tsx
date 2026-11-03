import {
  CheckCircleIcon,
  EyeSlashIcon,
  LinkBreakIcon,
  QuotesIcon,
  UserSwitchIcon,
  XCircleIcon,
  type Icon,
} from "@phosphor-icons/react";
import type { LinkStatus, Verdict } from "./api";

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
  source_missing: {
    label: "Source missing",
    short: "The cited source isn't listed, or its URL is dead and was never archived.",
    icon: LinkBreakIcon,
    tone: "text-bad",
  },
  unverifiable: {
    label: "Unverifiable",
    short: "The source exists but couldn't be read: blocked, no readable text, or link rot.",
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

export const VERDICT_ORDER: Verdict[] = [
  "supported",
  "unsupported",
  "wrong_entity",
  "source_missing",
  "unverifiable",
  "uncited",
];

export const LINK_STATUS: Record<LinkStatus, { label: string; tone: string }> = {
  provided: { label: "Text provided", tone: "text-ink-2" },
  live: { label: "Live", tone: "text-accent-ink" },
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
