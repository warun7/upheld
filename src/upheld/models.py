from enum import StrEnum

from pydantic import BaseModel, Field


class Source(BaseModel):
    id: str
    url: str | None = None
    title: str | None = None
    text: str | None = Field(default=None, description="Source text. If omitted, it is fetched from `url`.")


class AuditRequest(BaseModel):
    question: str | None = Field(default=None, max_length=2_000)
    answer: str = Field(max_length=50_000)
    sources: list[Source] = Field(default_factory=list, max_length=50)


class LinkStatus(StrEnum):
    PROVIDED = "provided"  # text supplied by the caller, nothing fetched
    LIVE = "live"
    LINK_ROT = "link_rot"  # dead now, but the Wayback Machine has a copy
    LIKELY_FABRICATED = "likely_fabricated"  # dead and never archived
    UNREACHABLE = "unreachable"  # network error, blocked, or unsupported content
    MISSING = "missing"  # cited id has no matching source


class Verdict(StrEnum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    WRONG_ENTITY = "wrong_entity"  # evidence reads as supporting, but a named entity in the claim is absent from the source
    SOURCE_MISSING = "source_missing"  # cited source doesn't exist or isn't listed
    UNVERIFIABLE = "unverifiable"  # source exists but its text couldn't be read
    UNCITED = "uncited"


class Span(BaseModel):
    start: int
    end: int
    text: str
    confidence: float


class Evidence(BaseModel):
    source_id: str
    passage: str
    score: float


class CitationCheck(BaseModel):
    source_id: str
    verdict: Verdict
    support_score: float | None = Field(default=None, description="Verifier's estimate that the claim is supported, 0-1.")
    unsupported_spans: list[Span] = Field(default_factory=list, description="Character spans within the claim text.")
    missing_entities: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    note: str | None = None


class ClaimResult(BaseModel):
    index: int
    text: str
    start: int = Field(description="Offset of the claim's sentence in the original answer.")
    end: int
    cited: list[str]
    verdict: Verdict
    checks: list[CitationCheck] = Field(default_factory=list)
    note: str | None = None


class SourceReport(BaseModel):
    id: str
    url: str | None
    status: LinkStatus
    http_status: int | None = None
    chars: int = 0
    note: str | None = None


class Summary(BaseModel):
    claims: int
    cited_claims: int
    supported_claims: int
    citations_checked: int
    citation_verdicts: dict[str, int]
    claim_verdicts: dict[str, int]


class AuditReport(BaseModel):
    verifier: str = Field(description="Verifier name and threshold. Every number in this report depends on it.")
    retrieval: str = Field(description="How evidence passages were found within each source.")
    summary: Summary
    claims: list[ClaimResult]
    sources: list[SourceReport]
