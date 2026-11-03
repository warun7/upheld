// Types mirror src/upheld/models.py. Keep them in sync when the report changes.

export type Verdict = "supported" | "unsupported" | "wrong_entity" | "source_missing" | "unverifiable" | "uncited";
export type LinkStatus = "provided" | "live" | "archived" | "link_rot" | "likely_fabricated" | "unreachable" | "missing";

export interface Source {
  id: string;
  url?: string | null;
  title?: string | null;
  text?: string | null;
}

export interface AuditRequest {
  question?: string | null;
  answer: string;
  sources: Source[];
}

export interface Span {
  start: number;
  end: number;
  text: string;
  confidence: number;
}

export interface Evidence {
  source_id: string;
  passage: string;
  score: number;
}

export interface CitationCheck {
  source_id: string;
  verdict: Verdict;
  support_score: number | null;
  unsupported_spans: Span[];
  missing_entities: string[];
  evidence: Evidence[];
  note: string | null;
}

export interface ClaimResult {
  index: number;
  text: string;
  start: number;
  end: number;
  cited: string[];
  verdict: Verdict;
  checks: CitationCheck[];
  note: string | null;
}

export interface SourceReport {
  id: string;
  url: string | null;
  status: LinkStatus;
  http_status: number | null;
  chars: number;
  note: string | null;
  archived_at?: string | null;
  archive_url?: string | null;
}

export interface AuditReport {
  verifier: string;
  retrieval: string;
  summary: {
    claims: number;
    cited_claims: number;
    supported_claims: number;
    citations_checked: number;
    citation_verdicts: Record<string, number>;
    claim_verdicts: Record<string, number>;
  };
  claims: ClaimResult[];
  sources: SourceReport[];
}

export interface Example {
  id: string;
  title: string;
  blurb: string;
  question: string;
  answer: string;
  sources: Source[];
  report: AuditReport;
}

export interface Health {
  status: string;
  verifier: string;
  retrieval: string;
}

// Same origin by default (`upheld serve` hosts the site and the API together).
// A static deploy points at a hosted API with VITE_UPHELD_API at build time.
export const API_BASE = (import.meta.env.VITE_UPHELD_API ?? "").replace(/\/$/, "");

export async function getHealth(signal?: AbortSignal): Promise<Health> {
  const res = await fetch(`${API_BASE}/health`, { signal });
  if (!res.ok) throw new Error(`health check returned ${res.status}`);
  return res.json();
}

export async function runAudit(req: AuditRequest, signal?: AbortSignal): Promise<AuditReport> {
  const res = await fetch(`${API_BASE}/audit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
    signal,
  });
  if (!res.ok) {
    let detail = `The API returned ${res.status}.`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") detail = body.detail;
      else if (Array.isArray(body.detail)) detail = body.detail.map((d: { msg: string }) => d.msg).join("; ");
    } catch {
      // keep the status-code message
    }
    throw new Error(detail);
  }
  return res.json();
}
