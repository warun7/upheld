"""Measure a verifier against human labels.

Input is JSONL, one labeled citation per line:
  {"claim": "...", "evidence": "..." | ["...", ...], "label": "supported" | "unsupported",
   "answer": "..."?, "question": "..."?}

`answer` is the full response the claim came from (the claim must appear in
it verbatim). Give it when you have it: verifiers trained on full responses
judge claims better in context.

"unsupported" is the positive class, since catching bad citations is the job.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from upheld.verify import Verifier


@dataclass
class Example:
    claim: str
    evidence: list[str]
    unsupported: bool
    question: str | None = None
    answer: str | None = None


@dataclass
class Metrics:
    threshold: float
    n: int
    precision: float  # precision, recall and f1 are for the unsupported class
    recall: float
    f1: float
    macro_f1: float  # mean F1 over both classes, as AttributionBench reports
    accuracy: float
    flagged_rate: float


def load_examples(path: Path) -> list[Example]:
    examples = []
    for line_no, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        if row["label"] not in ("supported", "unsupported"):
            raise ValueError(f"line {line_no}: label must be 'supported' or 'unsupported'")
        evidence = row["evidence"] if isinstance(row["evidence"], list) else [row["evidence"]]
        answer = row.get("answer")
        if answer is not None and row["claim"] not in answer:
            raise ValueError(f"line {line_no}: claim does not appear verbatim in answer")
        examples.append(Example(row["claim"], evidence, row["label"] == "unsupported", row.get("question"), answer))
    return examples


def score_examples(examples: list[Example], verifier: Verifier) -> list[float]:
    scores = []
    for e in examples:
        answer = e.answer or e.claim
        start = answer.index(e.claim)
        [result] = verifier.check(answer, [(start, start + len(e.claim))], e.evidence, e.question)
        scores.append(result.score)
    return scores


def metrics_at(threshold: float, scores: list[float], examples: list[Example]) -> Metrics:
    return metrics_for([s < threshold for s in scores], examples, threshold)


def metrics_for(flagged: list[bool], examples: list[Example], threshold: float) -> Metrics:
    """Metrics for a list of unsupported/supported decisions, one per example."""
    actual = [e.unsupported for e in examples]
    n = len(examples)
    f1, precision, recall = _f1([f and a for f, a in zip(flagged, actual)], flagged, actual)
    f1_supported, _, _ = _f1(
        [not f and not a for f, a in zip(flagged, actual)], [not f for f in flagged], [not a for a in actual]
    )
    correct = sum(f == a for f, a in zip(flagged, actual))
    return Metrics(
        threshold, n, precision, recall, f1, (f1 + f1_supported) / 2, correct / n if n else 0.0, sum(flagged) / n if n else 0.0
    )


def _f1(true_positive: list[bool], predicted: list[bool], actual: list[bool]) -> tuple[float, float, float]:
    tp = sum(true_positive)
    precision = tp / sum(predicted) if sum(predicted) else 0.0
    recall = tp / sum(actual) if sum(actual) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return f1, precision, recall
