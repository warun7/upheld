// Types mirror src/upheld/models.py. Keep them in sync when the report changes.

export type Verdict =
  | "supported"
  | "unsupported"
  | "wrong_entity"
  | "misattributed"
  | "source_missing"
  | "unverifiable"
  | "uncited";
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
  /** Other sources in the answer that back the claim when what it cites doesn't, best first. */
  supported_by?: CitationCheck[];
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
  caption: string;
  question: string;
  answer: string;
  sources: Source[];
  report: AuditReport;
}
