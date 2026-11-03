import asyncio

from upheld.audit import run_audit
from upheld.models import AuditRequest, LinkStatus, Source, Verdict
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
    assert report.verifier == "lexical@0.7"
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
