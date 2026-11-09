import asyncio
from datetime import UTC, datetime

from upheld import pipeline
from upheld.pipeline import run_audit
from upheld.models import AuditRequest, LinkStatus, Source, Verdict
from upheld.sources import FetchedSource
from upheld.verify import LexicalVerifier

SOURCES = [
    Source(id="1", text="The Eiffel Tower in Paris is 330 metres tall and was completed in 1889."),
    Source(id="2", text="Tirzepatide reduced body weight by 20.9% over 72 weeks in the SURMOUNT-1 trial."),
    Source(id="3", text="Marie Curie won the Nobel Prize in Physics in 1903."),
    Source(id="4", text="Marie Curie also won the Nobel Prize in Chemistry in 1911."),
]


def audit(answer: str):
    req = AuditRequest(answer=answer, sources=SOURCES)
    return asyncio.run(run_audit(req, LexicalVerifier(), fetch=False))


def test_verdicts_across_failure_modes():
    report = audit(
        "Here's what I found:\n"
        "The Eiffel Tower in Paris is 330 metres tall [1]. "
        "The Eiffel Tower was completed in 1925 [1]. "
        "Ozempic reduced body weight by 20.9% over 72 weeks [2]. "
        "The tower is repainted every seven years [9]. "
        "It is the most visited paid monument in the world."
    )
    verdicts = [c.verdict for c in report.claims]
    assert verdicts == [
        Verdict.SUPPORTED,
        Verdict.UNSUPPORTED,  # wrong year
        Verdict.WRONG_ENTITY,  # real numbers, wrong drug
        Verdict.SOURCE_MISSING,  # [9] isn't listed
        Verdict.UNCITED,
    ]
    assert report.claims[2].checks[0].missing_entities == ["Ozempic"]
    assert report.claims[1].checks[0].unsupported_spans[0].text == "1925"
    assert report.summary.supported_claims == 1 and report.summary.cited_claims == 4
    assert report.verifier == "lexical@0.56"
    assert report.retrieval == "bm25"
    assert {s.id: s.status for s in report.sources} == {"1": LinkStatus.PROVIDED, "2": LinkStatus.PROVIDED, "9": LinkStatus.MISSING}


def test_claim_supported_only_by_combining_sources():
    report = audit("Marie Curie won the Nobel Prize in Physics in 1903 and in Chemistry in 1911 [3][4].")
    claim = report.claims[0]
    assert [c.verdict for c in claim.checks] == [Verdict.UNSUPPORTED, Verdict.UNSUPPORTED]
    assert claim.verdict == Verdict.SUPPORTED
    assert claim.note == "supported only when the cited sources are combined"


def test_url_without_fetch_is_unverifiable():
    req = AuditRequest(answer="The Eiffel Tower is 330 metres tall [1].\n\n[1] https://example.com/eiffel")
    report = asyncio.run(run_audit(req, LexicalVerifier(), fetch=False))
    assert report.claims[0].verdict == Verdict.UNVERIFIABLE
    assert report.sources[0].url == "https://example.com/eiffel"


def test_retrieves_as_many_passages_as_the_verifier_wants():
    topics = ["the tower's paint", "the lifts", "the lighting", "the restaurants", "the visitor numbers"]
    page = " ".join(f"This section covers {t}. " + "It adds more detail about the history of the site. " * 15 for t in topics)
    verifier = LexicalVerifier()
    req = AuditRequest(answer="The Eiffel Tower has lifts [1].", sources=[Source(id="1", text=page)])
    for top_k in (1, 3):
        verifier.top_k = top_k
        report = asyncio.run(run_audit(req, verifier, fetch=False))
        assert len(report.claims[0].checks[0].evidence) == top_k


def test_archived_copy_is_checked_like_a_live_page(monkeypatch):
    async def fetch_all(sources, allow_private=False):
        [source] = sources
        copy = FetchedSource(
            source,
            LinkStatus.ARCHIVED,
            SOURCES[0].text,
            http_status=403,
            note="HTTP 403 (blocked or rate-limited); read from the Wayback Machine copy of 2026-10-11",
            archived_at=datetime(2026, 10, 11, 19, 44, 35, tzinfo=UTC),
            archive_url="https://web.archive.org/web/20261011194435/https://example.com/eiffel",
        )
        return {source.id: copy}

    monkeypatch.setattr(pipeline, "fetch_all", fetch_all)
    req = AuditRequest(answer="The Eiffel Tower in Paris is 330 metres tall [1].\n\n[1] https://example.com/eiffel")
    report = asyncio.run(run_audit(req, LexicalVerifier()))
    [check] = report.claims[0].checks
    assert check.verdict == Verdict.SUPPORTED
    assert check.note == "checked against the Wayback Machine copy of 2026-10-11"
    [source] = report.sources
    assert source.status == LinkStatus.ARCHIVED and source.archived_at.year == 2026
    assert source.archive_url.startswith("https://web.archive.org/web/20261011194435/")
    # The passage was read from the copy, so its link opens the copy.
    assert check.evidence[0].link == "https://web.archive.org/web/20261011194435/https://example.com/eiffel#:~:text=The%20Eiffel%20Tower%20in,was%20completed%20in%201889."


def test_inline_text_has_no_passage_link():
    [check] = audit("The Eiffel Tower in Paris is 330 metres tall [1].").claims[0].checks
    assert check.evidence and all(e.link is None for e in check.evidence)


def test_claim_backed_by_another_source_in_the_answer_is_misattributed():
    report = audit(
        "Marie Curie won the Nobel Prize in Chemistry in 1911 [3]. "
        "Marie Curie won the Nobel Prize in Physics in 1903 [4]. "
        "The Eiffel Tower in Paris is 330 metres tall [1]. "
        "The Eiffel Tower was completed in 1889. "
        "Tirzepatide reduced body weight by 20.9% over 72 weeks."
    )
    chemistry, physics, height, completed, tirzepatide = report.claims
    assert chemistry.verdict == physics.verdict == Verdict.MISATTRIBUTED
    assert [c.source_id for c in chemistry.supported_by] == ["4"] and chemistry.note == "[4] backs it instead"
    assert [c.source_id for c in physics.supported_by] == ["3"]
    assert chemistry.checks[0].verdict == Verdict.UNSUPPORTED  # the citation itself is still wrong
    assert height.verdict == Verdict.SUPPORTED and height.supported_by == []
    # An uncited claim is told which marker to add.
    assert completed.verdict == Verdict.UNCITED and [c.source_id for c in completed.supported_by] == ["1"]
    assert completed.note == "no citation, but [1] backs it"
    # Only sources the answer cites are read, so [2], listed but never cited, backs nothing.
    assert tirzepatide.verdict == Verdict.UNCITED and tirzepatide.supported_by == []
    assert report.summary.claim_verdicts == {"misattributed": 2, "supported": 1, "uncited": 2}


def test_claim_backed_by_a_search_result_it_doesnt_cite():
    req = AuditRequest(
        answer="The Eiffel Tower in Paris is 330 metres tall [1]. "
        "Marie Curie won the Nobel Prize in Physics in 1903 [1]. "
        "The Eiffel Tower was completed in 1925 [1]. "
        "Marie Curie also won the Nobel Prize in Chemistry in 1911.",
        sources=[SOURCES[0]],
        seen_sources=[Source(id="2", text=SOURCES[2].text), Source(id="3", text=SOURCES[3].text)],
    )
    report = asyncio.run(run_audit(req, LexicalVerifier(), fetch=False))
    height, physics, completed, chemistry = report.claims
    assert height.verdict == Verdict.SUPPORTED
    assert physics.verdict == Verdict.MISATTRIBUTED and [c.source_id for c in physics.supported_by] == ["2"]
    assert physics.note == "[2] backs it instead; the answer's search returned [2] but it doesn't cite it"
    # Nothing it read says this, so the claim didn't come from its search.
    assert completed.verdict == Verdict.UNSUPPORTED
    assert completed.note == "nor do the 2 other pages the answer's search returned"
    # Uncited claims are checked only against the sources the answer cites.
    assert chemistry.verdict == Verdict.UNCITED and chemistry.supported_by == [] and chemistry.note is None
    # Only the search result that backs a claim is listed.
    assert [(s.id, s.cited) for s in report.sources] == [("1", True), ("2", False)]


def test_search_results_are_fetched_only_when_a_cited_claim_fails(monkeypatch):
    fetched: list[list[str]] = []

    async def fetch_all(sources, allow_private=False):
        fetched.append([s.id for s in sources])
        return {s.id: FetchedSource(s, LinkStatus.LIVE, SOURCES[0].text if s.id == "1" else "A page about something else.") for s in sources}

    monkeypatch.setattr(pipeline, "fetch_all", fetch_all)
    seen = [Source(id=str(n), url=f"https://example.com/{n}") for n in range(2, 14)]
    for answer in ("The Eiffel Tower in Paris is 330 metres tall [1].", "The Eiffel Tower was completed in 1925 [1]."):
        req = AuditRequest(answer=answer, sources=[Source(id="1", url="https://example.com/1")], seen_sources=seen)
        report = asyncio.run(run_audit(req, LexicalVerifier()))
    # The first answer's claim holds, so the search results aren't read. For the second, the first ten are.
    assert fetched == [["1"], ["1"], [str(n) for n in range(2, 12)]]
    assert report.claims[0].note == "nor do the 10 of the 12 other pages the answer's search returned that upheld read"
    assert [s.id for s in report.sources] == ["1"]


class AlwaysSupported:
    """A verifier that reads "410" in both and misses the unit, as models can."""

    name, threshold, top_k = "always", 0.5, 3

    def check(self, answer, claims, passages, question=None):
        from upheld.verify import SupportResult

        return [SupportResult(1.0) for _ in claims]


def test_same_number_in_another_unit_is_unsupported_for_any_verifier():
    page = "The tower is 330 m (1,083 ft) tall. Its base is 125 m (410 ft) on a side."
    req = AuditRequest(answer="The base is 410 metres wide [1]. The base is 125 metres wide [1].", sources=[Source(id="1", text=page)])
    wrong, right = asyncio.run(run_audit(req, AlwaysSupported(), fetch=False)).claims
    assert wrong.verdict == Verdict.UNSUPPORTED
    assert wrong.checks[0].note == "the source gives 410 ft, not 410 metres"
    assert [s.text for s in wrong.checks[0].unsupported_spans] == ["410 metres"]
    assert right.verdict == Verdict.SUPPORTED
