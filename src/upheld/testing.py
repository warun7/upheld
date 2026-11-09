"""Fail a test when an answer's citations don't hold up.

    from upheld.testing import assert_supported

    def test_answer_cites_its_sources():
        response = client.responses.create(...)  # your app, with web search on
        assert_supported(response, verifier="ensemble")

`assert_supported` audits the answer (or checks a report you already have) and raises `CitationsNotSupported`, an
AssertionError, listing every claim whose verdict is in `fail_on`. The models load on the first call and stay loaded,
so a test session pays for them once. Pin `verifier` in tests: `auto` picks one for the machine, so a laptop with a GPU
and a CI runner would run different verifiers.
"""

from collections.abc import Iterable
from typing import Any

from upheld.auditor import Auditor, SourcesArg, audit
from upheld.models import AuditReport, ClaimResult, Verdict
from upheld.providers import Provider

# The claim is wrong, or its source is gone: the site's "Flagged" filter, and `--fail-on flagged`.
FLAGGED = frozenset({Verdict.UNSUPPORTED, Verdict.WRONG_ENTITY, Verdict.MISATTRIBUTED, Verdict.SOURCE_MISSING})
FAILABLE = [v.value for v in Verdict if v != Verdict.SUPPORTED]

FailOn = str | Verdict | Iterable[str | Verdict]


def fail_on_verdicts(fail_on: FailOn) -> frozenset[Verdict]:
    """Read `fail_on`: "flagged", verdict names separated by commas, or a list of names or Verdicts."""
    names = fail_on.split(",") if isinstance(fail_on, str) else [fail_on] if isinstance(fail_on, Verdict) else list(fail_on)
    verdicts: set[Verdict] = set()
    for raw in names:
        name = str(raw).strip().lower().replace("-", "_")
        if not name:
            continue
        if name == "flagged":
            verdicts |= FLAGGED
        elif name in FAILABLE:
            verdicts.add(Verdict(name))
        else:
            raise ValueError(f"{name!r} isn't a verdict to fail on; use {', '.join(FAILABLE)} or flagged")
    return frozenset(verdicts)


def failing_claims(report: AuditReport, fail_on: FailOn = "flagged") -> list[ClaimResult]:
    verdicts = fail_on_verdicts(fail_on)
    return [c for c in report.claims if c.verdict in verdicts]


def summarize(failing: list[ClaimResult], report: AuditReport) -> str:
    """'2 of 5 claims failed (1 unsupported, 1 source_missing)'."""
    counts: dict[Verdict, int] = {}
    for c in failing:
        counts[c.verdict] = counts.get(c.verdict, 0) + 1
    found = ", ".join(f"{n} {v.value}" for v, n in sorted(counts.items(), key=lambda kv: -kv[1]))
    return f"{len(failing)} of {len(report.claims)} claims failed ({found})"


def _shorten(text: str, limit: int = 110) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else f"{text[: limit - 3].rstrip()}..."


def _explain(claim: ClaimResult) -> str:
    lines = [f'  claim {claim.index + 1}, {claim.verdict.value}: "{_shorten(claim.text)}"']
    for check in claim.checks:
        parts = [f"[{check.source_id}] {check.verdict.value}"]
        if check.support_score is not None and check.verdict != Verdict.SOURCE_MISSING:
            parts.append(f"score {check.support_score:.2f}")
        if check.missing_entities:
            parts.append(f"not in source: {', '.join(check.missing_entities)}")
        if check.note:
            parts.append(check.note)
        lines.append(f"    {' · '.join(parts)}")
    if claim.note:
        lines.append(f"    {claim.note}")
    return "\n".join(lines)


class CitationsNotSupported(AssertionError):
    """Some claims got a verdict the test fails on. `report` is the full audit; `failing` the claims that failed."""

    def __init__(self, report: AuditReport, failing: list[ClaimResult]):
        self.report = report
        self.failing = failing
        details = "\n".join(_explain(c) for c in failing)
        super().__init__(f"{summarize(failing, report)}, verifier {report.verifier}\n{details}")


def assert_supported(
    answer: Any,
    sources: SourcesArg = None,
    *,
    fail_on: FailOn = "flagged",
    question: str | None = None,
    verifier: str = "auto",
    threshold: float | None = None,
    retrieval: str = "auto",
    provider: Provider | str = Provider.AUTO,
    fetch: bool = True,
    allow_private: bool = False,
    auditor: Auditor | None = None,
) -> AuditReport:
    """Audit an answer and raise CitationsNotSupported if any claim's verdict is in `fail_on`; return the report.

    `answer` and `sources` are what `upheld.audit` takes: text with its sources, an AuditRequest, or a provider's
    response. An AuditReport is checked as it is. `fail_on` defaults to "flagged": unsupported, wrong_entity,
    misattributed and source_missing. Pass an `auditor` to use one you've built; otherwise the models are loaded once
    for the given verifier, threshold and retrieval and reused.
    """
    __tracebackhide__ = True  # pytest shows the test's line, not this one
    verdicts = fail_on_verdicts(fail_on)  # a typo in fail_on fails before the models load
    if isinstance(answer, AuditReport):
        report = answer
    elif auditor is not None:
        report = auditor.audit(answer, sources, question=question, provider=provider, fetch=fetch, allow_private=allow_private)
    else:
        report = audit(
            answer,
            sources,
            question=question,
            verifier=verifier,
            threshold=threshold,
            retrieval=retrieval,
            provider=provider,
            fetch=fetch,
            allow_private=allow_private,
        )
    failing = [c for c in report.claims if c.verdict in verdicts]
    if failing:
        raise CitationsNotSupported(report, failing)
    return report
