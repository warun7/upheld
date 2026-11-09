"""Audit an answer's citations: fetch sources, then check every claim against what it cites."""

import asyncio
from collections import Counter

from upheld.entities import missing_entities
from upheld.evidence import Embedder, SourceIndex, retrieval_name, tokenize
from upheld.models import (
    AuditReport,
    AuditRequest,
    CitationCheck,
    ClaimResult,
    Evidence,
    LinkStatus,
    Source,
    SourceReport,
    Span,
    Summary,
    Verdict,
)
from upheld.parse import Claim, extract_reference_list, is_claim, split_claims, with_cited_spans
from upheld.quantities import unit_mismatches
from upheld.sources import FetchedSource, fetch_all
from upheld.verify import SupportResult, Verifier

# ~1,000 words of evidence per verifier call, well inside LettuceDetect's 4,096 tokens. A claim that
# retrieves more on its own (the judge ensemble takes 10) is checked by itself.
MAX_PASSAGES = 8
# A claim its citations don't back is checked against at most this many of the answer's other sources: those whose
# closest passages hold at least this share of the claim's words.
OTHER_SOURCES = 2
OTHER_SOURCE_COVERAGE = 0.5


async def run_audit(
    req: AuditRequest,
    verifier: Verifier,
    *,
    embedder: Embedder | None = None,
    fetch: bool = True,
    allow_private: bool = False,
    top_k: int | None = None,
) -> AuditReport:
    """top_k (evidence passages per claim) defaults to what the verifier was tuned with."""
    body, listed = extract_reference_list(req.answer)
    parsed, linked = split_claims(body)
    if req.cited_spans:
        parsed = with_cited_spans(req.answer, parsed, req.cited_spans)
    claims = [c for c in parsed if c.cited or is_claim(c.text)]

    sources: dict[str, Source] = {}
    for s in [*req.sources, *listed, *linked]:
        sources.setdefault(s.id, s)

    cited_ids = list(dict.fromkeys(i for c in claims for i in c.cited))
    to_load = [sources[i] for i in cited_ids if i in sources]
    if fetch:
        loaded = await fetch_all(to_load, allow_private)
    else:
        loaded = {s.id: _without_fetch(s) for s in to_load}

    results = await asyncio.to_thread(_check_claims, claims, loaded, verifier, embedder, req.question, top_k or verifier.top_k)
    reports = [_source_report(loaded[i]) if i in loaded else _missing_report(i) for i in cited_ids]
    return AuditReport(
        verifier=verifier.name, retrieval=retrieval_name(embedder), summary=_summarize(results), claims=results, sources=reports
    )


def _without_fetch(source: Source) -> FetchedSource:
    if source.text:
        return FetchedSource(source, LinkStatus.PROVIDED, source.text)
    return FetchedSource(source, LinkStatus.UNREACHABLE, note="fetching disabled and no text given")


def _check_claims(
    claims: list[Claim],
    loaded: dict[str, FetchedSource],
    verifier: Verifier,
    embedder: Embedder | None,
    question: str | None,
    top_k: int,
) -> list[ClaimResult]:
    # The verifier reads the whole answer (markers stripped), so each claim is a range within it.
    answer, ranges = _join_claims(claims)

    checks: dict[tuple[int, str], CitationCheck] = {}
    claims_by_source: dict[str, list[int]] = {}
    for i, claim in enumerate(claims):
        for source_id in claim.cited:
            early = _precheck(loaded.get(source_id), source_id)
            if early:
                checks[i, source_id] = early
            else:
                claims_by_source.setdefault(source_id, []).append(i)

    # One verifier call per source (in batches that fit the model's context), covering every claim that cites it.
    indexes = {source_id: SourceIndex(loaded[source_id].text, embedder) for source_id in claims_by_source}
    for source_id, claim_ids in claims_by_source.items():
        source = loaded[source_id]
        evidence = {i: indexes[source_id].search(claims[i].text, top_k) for i in claim_ids}
        for batch, passages in _batches(claim_ids, evidence):
            scored = verifier.check(answer, [ranges[i] for i in batch], passages, question)
            for i, result in zip(batch, scored):
                checks[i, source_id] = _citation_check(source_id, claims[i].text, source, result, evidence[i], verifier)

    results: list[ClaimResult] = []
    for i, claim in enumerate(claims):
        base = dict(index=i, text=claim.text, start=claim.start, end=claim.end, cited=claim.cited)
        if not claim.cited:
            results.append(ClaimResult(**base, verdict=Verdict.UNCITED))
            continue
        claim_checks = [checks[i, s] for s in claim.cited]
        verdict, note = _claim_verdict(answer, ranges[i], claim.text, claim_checks, loaded, indexes, verifier, question)
        results.append(ClaimResult(**base, verdict=verdict, checks=claim_checks, note=note))

    _find_other_support(claims, results, answer, ranges, loaded, indexes, verifier, question, top_k)
    return results


def _find_other_support(
    claims: list[Claim],
    results: list[ClaimResult],
    answer: str,
    ranges: list[tuple[int, int]],
    loaded: dict[str, FetchedSource],
    indexes: dict[str, SourceIndex],
    verifier: Verifier,
    question: str | None,
    top_k: int,
) -> None:
    """Check each claim that isn't supported against the answer's other sources most likely to back it.

    A claim cited to [1] that [2] backs is misattributed, which is a different fix from a claim nothing backs: move the
    marker. An uncited claim that a source backs says which marker to add. Only sources the answer cites somewhere are
    read, so this costs no extra fetches.
    """
    wanted: dict[str, list[int]] = {}
    evidence: dict[tuple[int, str], list[tuple[str, float]]] = {}
    for i, (claim, result) in enumerate(zip(claims, results)):
        words = set(tokenize(claim.text))
        if result.verdict == Verdict.SUPPORTED or not words:
            continue
        candidates = []
        for source_id, index in indexes.items():
            if source_id in claim.cited:
                continue
            found = index.search(claim.text, top_k)
            coverage = len(words & set(tokenize(" ".join(p for p, _ in found)))) / len(words)
            if coverage >= OTHER_SOURCE_COVERAGE:
                candidates.append((coverage, source_id, found))
        for _, source_id, found in sorted(candidates, key=lambda c: -c[0])[:OTHER_SOURCES]:
            wanted.setdefault(source_id, []).append(i)
            evidence[i, source_id] = found

    for source_id, claim_ids in wanted.items():
        found = {i: evidence[i, source_id] for i in claim_ids}
        for batch, passages in _batches(claim_ids, found):
            scored = verifier.check(answer, [ranges[i] for i in batch], passages, question)
            for i, score in zip(batch, scored):
                check = _citation_check(source_id, claims[i].text, loaded[source_id], score, found[i], verifier)
                if check.verdict == Verdict.SUPPORTED:
                    results[i].supported_by.append(check)

    for result in results:
        if not result.supported_by:
            continue
        result.supported_by.sort(key=lambda c: -(c.support_score or 0))
        markers = " and ".join(f"[{c.source_id}]" for c in result.supported_by)
        if result.verdict in (Verdict.UNSUPPORTED, Verdict.WRONG_ENTITY):
            result.verdict = Verdict.MISATTRIBUTED
            note = f"{markers} {'backs' if len(result.supported_by) == 1 else 'back'} it instead"
        elif result.verdict == Verdict.UNCITED:
            note = f"no citation, but {markers} {'backs' if len(result.supported_by) == 1 else 'back'} it"
        else:
            note = f"{markers} in the same answer {'backs' if len(result.supported_by) == 1 else 'back'} it"
        result.note = f"{result.note}; {note}" if result.note else note


def _join_claims(claims: list[Claim]) -> tuple[str, list[tuple[int, int]]]:
    parts: list[str] = []
    ranges: list[tuple[int, int]] = []
    pos = 0
    for claim in claims:
        ranges.append((pos, pos + len(claim.text)))
        parts.append(claim.text)
        pos += len(claim.text) + 1
    return " ".join(parts), ranges


def _batches(claim_ids: list[int], evidence: dict[int, list[tuple[str, float]]]) -> list[tuple[list[int], list[str]]]:
    batches: list[tuple[list[int], list[str]]] = []
    batch: list[int] = []
    passages: dict[str, None] = {}
    for i in claim_ids:
        new = [p for p, _ in evidence[i] if p not in passages]
        if batch and len(passages) + len(new) > MAX_PASSAGES:
            batches.append((batch, list(passages)))
            batch, passages = [], {}
            new = [p for p, _ in evidence[i]]
        batch.append(i)
        passages.update(dict.fromkeys(new))
    if batch:
        batches.append((batch, list(passages)))
    return batches


def _precheck(fetched: FetchedSource | None, source_id: str) -> CitationCheck | None:
    if fetched is None:
        return CitationCheck(source_id=source_id, verdict=Verdict.SOURCE_MISSING, note=f"no source listed for [{source_id}]")
    if fetched.status == LinkStatus.LIKELY_FABRICATED:
        return CitationCheck(source_id=source_id, verdict=Verdict.SOURCE_MISSING, note=fetched.note)
    if not fetched.text:
        return CitationCheck(source_id=source_id, verdict=Verdict.UNVERIFIABLE, note=fetched.note)
    return None


def _citation_check(
    source_id: str, claim: str, source: FetchedSource, result: SupportResult, passages: list[tuple[str, float]], verifier: Verifier
) -> CitationCheck:
    missing = missing_entities(claim, source.text)
    # Same digits, other unit: "410 metres" where the passage says "410 ft" and the page never gives 410 metres.
    # Checked for every verifier, since a model reading "410" in both can miss the unit.
    mismatched = unit_mismatches(claim, "\n".join(p for p, _ in passages), source.text)
    if result.score < verifier.threshold or mismatched:
        verdict = Verdict.UNSUPPORTED
    elif missing:
        verdict = Verdict.WRONG_ENTITY
    else:
        verdict = Verdict.SUPPORTED
    spans = list(result.spans)
    for q, _ in mismatched:
        if not any(sp.start < q.end and q.start < sp.end for sp in spans):
            spans.append(Span(start=q.start, end=q.end, text=q.text, confidence=1.0))
    notes = [f"the source gives {said.text}, not {q.text}" for q, said in mismatched]
    if source.archived_at:
        notes.append(f"checked against the Wayback Machine copy of {source.archived_at:%Y-%m-%d}")
    return CitationCheck(
        source_id=source_id,
        verdict=verdict,
        support_score=result.score,
        unsupported_spans=sorted(spans, key=lambda sp: sp.start),
        missing_entities=missing,
        evidence=[Evidence(source_id=source_id, passage=p, score=s) for p, s in passages],
        note="; ".join(notes) or None,
    )


def _claim_verdict(
    answer: str,
    claim_range: tuple[int, int],
    claim: str,
    checks: list[CitationCheck],
    loaded: dict[str, FetchedSource],
    indexes: dict[str, SourceIndex],
    verifier: Verifier,
    question: str | None,
) -> tuple[Verdict, str | None]:
    verdicts = {c.verdict for c in checks}
    if Verdict.SUPPORTED in verdicts:
        return Verdict.SUPPORTED, None

    # Multi-hop claims can need two sources together even when neither supports them alone.
    readable = [c.source_id for c in checks if c.support_score is not None]
    if len(readable) > 1:
        passages = [p for source_id in readable for p, _ in indexes[source_id].search(claim, 2)]
        [joint] = verifier.check(answer, [claim_range], passages, question)
        combined_text = "\n".join(loaded[source_id].text for source_id in readable)
        if joint.score >= verifier.threshold and not missing_entities(claim, combined_text):
            return Verdict.SUPPORTED, "supported only when the cited sources are combined"

    for verdict in (Verdict.UNVERIFIABLE, Verdict.WRONG_ENTITY, Verdict.UNSUPPORTED, Verdict.SOURCE_MISSING):
        if verdict in verdicts:
            return verdict, None
    return Verdict.UNSUPPORTED, None


def _source_report(f: FetchedSource) -> SourceReport:
    return SourceReport(
        id=f.source.id,
        url=f.source.url,
        resolved_url=f.resolved_url,
        status=f.status,
        http_status=f.http_status,
        chars=len(f.text),
        note=f.note,
        archived_at=f.archived_at,
        archive_url=f.archive_url,
    )


def _missing_report(source_id: str) -> SourceReport:
    return SourceReport(id=source_id, url=None, status=LinkStatus.MISSING, note="cited but not listed")


def _summarize(results: list[ClaimResult]) -> Summary:
    checks = [c for r in results for c in r.checks]
    cited = [r for r in results if r.cited]
    return Summary(
        claims=len(results),
        cited_claims=len(cited),
        supported_claims=sum(r.verdict == Verdict.SUPPORTED for r in cited),
        citations_checked=len(checks),
        citation_verdicts=dict(Counter(c.verdict.value for c in checks)),
        claim_verdicts=dict(Counter(r.verdict.value for r in results)),
    )
