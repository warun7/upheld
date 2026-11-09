import pytest

from upheld import AuditRequest, Source, Verdict
from upheld.auditor import Auditor
from upheld.testing import CitationsNotSupported, assert_supported, fail_on_verdicts

SOURCES = [Source(id="1", text="The Eiffel Tower in Paris is 330 metres tall and was completed in 1889.")]
GOOD = "The Eiffel Tower in Paris is 330 metres tall [1]."
BAD = GOOD + " The Eiffel Tower was completed in 1925 [1]. It is repainted every seven years [9]."
LEXICAL = {"verifier": "lexical", "retrieval": "bm25", "fetch": False}


def test_passes_and_returns_the_report_when_every_claim_holds_up():
    report = assert_supported(GOOD, SOURCES, **LEXICAL)
    assert [c.verdict for c in report.claims] == [Verdict.SUPPORTED]


def test_fails_with_the_claims_that_broke_and_why():
    with pytest.raises(CitationsNotSupported) as e:
        assert_supported(BAD, SOURCES, **LEXICAL)
    assert isinstance(e.value, AssertionError)
    assert [c.verdict for c in e.value.failing] == [Verdict.UNSUPPORTED, Verdict.SOURCE_MISSING]
    message = str(e.value)
    assert message.startswith("2 of 3 claims failed (")
    assert 'claim 2, unsupported: "The Eiffel Tower was completed in 1925."' in message
    assert "[1] unsupported · score" in message
    assert "verifier lexical@" in message


def test_fail_on_picks_the_verdicts_that_count():
    assert_supported(BAD, SOURCES, fail_on="wrong_entity,misattributed", **LEXICAL)
    with pytest.raises(CitationsNotSupported) as e:
        assert_supported(BAD, SOURCES, fail_on=[Verdict.SOURCE_MISSING], **LEXICAL)
    assert len(e.value.failing) == 1
    assert fail_on_verdicts("flagged") == fail_on_verdicts(["unsupported", "wrong-entity", "MISATTRIBUTED", "source_missing"])
    with pytest.raises(ValueError, match="isn't a verdict to fail on"):
        assert_supported(GOOD, SOURCES, fail_on="supported", **LEXICAL)


def test_checks_a_report_or_uses_an_auditor_you_already_have():
    auditor = Auditor("lexical", retrieval="bm25")
    report = assert_supported(AuditRequest(answer=GOOD, sources=SOURCES), auditor=auditor, fetch=False)
    assert assert_supported(report) is report
    bad = auditor.audit(BAD, SOURCES, fetch=False)
    with pytest.raises(CitationsNotSupported):
        assert_supported(bad)
