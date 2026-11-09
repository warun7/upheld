from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class Source(BaseModel):
    id: str
    url: str | None = None
    title: str | None = None
    text: str | None = Field(default=None, description="Source text. If omitted, it is fetched from `url`.")


class CitedSpan(BaseModel):
    start: int = Field(ge=0)
    end: int
    cited: list[str] = Field(min_length=1, description="Ids of the sources the span cites.")


MAX_SEEN = 100  # seen_sources kept from one response


class AuditRequest(BaseModel):
    question: str | None = Field(default=None, max_length=2_000)
    answer: str = Field(max_length=50_000)
    sources: list[Source] = Field(default_factory=list, max_length=50)
    cited_spans: list[CitedSpan] = Field(
        default_factory=list,
        max_length=500,
        description="Character ranges of the answer that a provider marked as cited. Each is checked as one claim, "
        "in place of the sentences it overlaps; the rest of the answer is split into sentences as usual.",
    )
    seen_sources: list[Source] = Field(
        default_factory=list,
        max_length=MAX_SEEN,
        description="Pages the answer's web search returned that it doesn't cite, in the search's order. When its "
        "citations don't back a claim, upheld reads the first 10 to see whether one does, and says so when none does.",
    )

    @model_validator(mode="after")
    def _spans_in_answer(self) -> "AuditRequest":
        for span in self.cited_spans:
            if not span.start < span.end <= len(self.answer):
                raise ValueError(f"cited span {span.start}-{span.end} is outside the answer ({len(self.answer)} characters)")
        return self


class LinkStatus(StrEnum):
    PROVIDED = "provided"  # text supplied by the caller, nothing fetched
    LIVE = "live"
    ARCHIVED = "archived"  # up, but couldn't be read (blocked, say), so the Wayback Machine's copy was read
    LINK_ROT = "link_rot"  # dead now, but the Wayback Machine has a copy; read when it's readable
    LIKELY_FABRICATED = "likely_fabricated"  # dead and never archived
    UNREACHABLE = "unreachable"  # unreadable live and no readable archived copy, or a file type upheld can't read
    MISSING = "missing"  # cited id has no matching source


class Verdict(StrEnum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    WRONG_ENTITY = "wrong_entity"  # evidence reads as supporting, but a named entity in the claim is absent from the source
    MISATTRIBUTED = "misattributed"  # what it cites doesn't back it, but another source the answer cites, or its search found, does
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
    link: str | None = Field(
        default=None,
        description="The source's URL with a text fragment (#:~:text=) that opens the page at this passage's sentence "
        "closest to the claim, highlighted. None for inline text and PDFs.",
    )


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
    supported_by: list[CitationCheck] = Field(
        default_factory=list,
        description="Other sources that back the claim when what it cites doesn't, best first: ones the answer cites "
        "elsewhere, or for a cited claim, pages its search returned that it doesn't cite.",
    )
    note: str | None = None


class SourceReport(BaseModel):
    id: str
    url: str | None
    resolved_url: str | None = Field(default=None, description="Where the URL redirected to, if it did.")
    status: LinkStatus
    http_status: int | None = None
    chars: int = 0
    note: str | None = None
    archived_at: datetime | None = Field(default=None, description="When the archived copy the text came from was captured.")
    archive_url: str | None = Field(default=None, description="That copy in the Wayback Machine.")
    cited: bool = Field(
        default=True,
        description="False for a page the answer's search returned but the answer doesn't cite, listed because it backs a claim.",
    )


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
