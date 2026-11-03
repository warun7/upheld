"""Targeted tests: does each check catch the failure it exists for?

AttributionBench measures overall agreement with human labels, but its errors
are mostly vague or partial support. These tests take ID-test claims that
humans labeled as supported, then edit them so the evidence no longer
supports them:

  wrong_number         a number that appears in the evidence is changed (14.9% -> 22.4%)
  wrong_entity_absent  a name in the claim is swapped for a name from another claim
                       that the evidence never mentions (the entity check's job)
  wrong_entity_swap    a name in the claim is swapped for another name that *does*
                       appear in the evidence: the claim pins a fact on the wrong
                       party, and only the verifier can catch it
  multi_source         two unrelated supported claims are joined into one sentence
                       and cited to both sources. Neither source supports it alone;
                       together they do. Runs through the full audit pipeline.

Catch rate is measured only on claims whose unedited version passes, so a
verifier that flags everything doesn't get credit for it. Thresholds come from
the dev-split calibration in evals/results/attributionbench.json when present.

    uv run python evals/perturbations.py lexical
    uv run python evals/perturbations.py minicheck --device mps
"""

import argparse
import asyncio
import json
import random
import re
from pathlib import Path

from attributionbench import RESULTS, load_split
from wordfreq import zipf_frequency

from upheld.pipeline import run_audit
from upheld.entities import COMMON_ZIPF, _present, missing_entities, named_entities
from upheld.models import AuditRequest, Source, Verdict
from upheld.parse import split_claims
from upheld.verify import Verifier, make_verifier

PER_TYPE = 150
MAX_EVIDENCE_WORDS = 400
_NUMBER = re.compile(r"(?<![\w.,])\d{1,3}(?:,\d{3})+(?:\.\d+)?(?![\w])|(?<![\w.,])\d+(?:\.\d+)?(?![\w])")
_MARKERS = re.compile(r"\s*\[\d+\]")


def edit_number(claim: str, evidence: str, rng: random.Random) -> str | None:
    evidence_numbers = {n.replace(",", "") for n in _NUMBER.findall(evidence)}
    in_names = [m.span() for m in re.finditer("|".join(map(re.escape, named_entities(claim))) or r"(?!)", claim)]
    candidates = [
        m
        for m in _NUMBER.finditer(claim)
        if m.group().replace(",", "") in evidence_numbers
        and claim[m.start() - 1 : m.start()] != "-"  # "SURMOUNT-1" is a name, not a quantity
        and not any(s <= m.start() < e for s, e in in_names)  # nor is "STEP 1"
    ]
    if not candidates:
        return None
    m = rng.choice(candidates)
    old = m.group()
    value = float(old.replace(",", ""))
    decimals = len(old.split(".")[1]) if "." in old else 0
    if decimals == 0 and len(old) == 4 and 1500 <= value <= 2100:
        new = str(int(value) + rng.choice([-5, -3, -2, 2, 3, 5]))  # a year
    elif decimals == 0 and value < 10:
        new = str(int(value) + rng.choice([2, 3, 4]))
    else:
        new_value = value * rng.choice([0.5, 0.6, 0.7, 1.4, 1.6, 2.0])
        new = f"{new_value:,.{decimals}f}" if "," in old else f"{new_value:.{decimals}f}"
    if new.replace(",", "") in evidence_numbers or new == old:
        return None
    return claim[: m.start()] + new + claim[m.end() :]


def _looks_like_name(entity: str) -> bool:
    return len(entity.split()) > 1 or bool(re.search(r"\d|[A-Z].*[A-Z]", entity)) or zipf_frequency(entity.lower(), "en") < COMMON_ZIPF


def edit_entity(claim: str, evidence: str, pool: list[str], rng: random.Random, *, in_evidence: bool) -> str | None:
    present = [e for e in named_entities(claim) if _present(e, evidence) and _looks_like_name(e)]
    if not present:
        return None
    old = rng.choice(present)
    if in_evidence:
        options = [e for e in named_entities(evidence) if e not in claim and _looks_like_name(e)]
    else:
        options = [e for e in pool if not _present(e, evidence)]
    options = [e for e in options if len(e.split()) == len(old.split()) and e.lower() not in old.lower() and old.lower() not in e.lower()]
    if not options:
        return None
    return claim.replace(old, rng.choice(options), 1)


def passes(verifier: Verifier, claim: str, evidence: list[str], question: str | None, *, entity_check: bool) -> bool:
    [result] = verifier.check(claim, [(0, len(claim))], evidence, question)
    if result.score < verifier.threshold:
        return False
    return not (entity_check and missing_entities(claim, "\n".join(evidence)))


def single_sentence(claim: str) -> bool:
    claims, _ = split_claims(claim)
    return len(claims) == 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("verifier", choices=["lexical", "lettuce", "minicheck", "judge", "ensemble", "ensemble+judge"])
    parser.add_argument("--device", default=None)
    args = parser.parse_args()

    calibration = RESULTS / "attributionbench.json"
    threshold = None
    if calibration.exists():
        threshold = json.loads(calibration.read_text())["systems"].get(args.verifier, {}).get("dev_threshold")
    verifier = make_verifier(args.verifier, threshold, args.device)
    print(f"{verifier.name} ({'dev-calibrated' if threshold else 'default'} threshold)")

    rng = random.Random(0)
    rows = [e for _, e in load_split("id") if not e.unsupported]
    rows = [e for e in rows if sum(len(r.split()) for r in e.evidence) <= MAX_EVIDENCE_WORDS]
    for e in rows:
        e.claim = _MARKERS.sub("", e.claim).strip()
    rng.shuffle(rows)
    pool = [n for e in rows for n in named_entities(e.claim) if _looks_like_name(n)]

    edits = {
        "wrong_number": lambda c, ev: edit_number(c, ev, rng),
        "wrong_entity_absent": lambda c, ev: edit_entity(c, ev, pool, rng, in_evidence=False),
        "wrong_entity_swap": lambda c, ev: edit_entity(c, ev, pool, rng, in_evidence=True),
    }
    results: dict = {"verifier": verifier.name}
    examples: dict = {}
    for kind, edit in edits.items():
        pairs = []
        for e in rows:
            edited = edit(e.claim, "\n".join(e.evidence))
            if edited:
                pairs.append((e, edited))
            if len(pairs) == PER_TYPE:
                break
        examples[kind] = [{"claim": e.claim, "edited": edited} for e, edited in pairs[:5]]
        for entity_check in (False, True):
            name = f"{kind}{' +entity' if entity_check else ''}"
            original = [passes(verifier, e.claim, e.evidence, e.question, entity_check=entity_check) for e, _ in pairs]
            edited = [passes(verifier, ed, e.evidence, e.question, entity_check=entity_check) for (e, ed), ok in zip(pairs, original) if ok]
            results[name] = {
                "n": len(pairs),
                "original_pass_rate": round(sum(original) / len(pairs), 3),
                "catch_rate": round(1 - sum(edited) / len(edited), 3) if edited else None,
            }
            print(f"  {name:28} n={len(pairs):<4} originals pass {results[name]['original_pass_rate']:.0%}, edits caught {results[name]['catch_rate']:.0%}")

    results["multi_source"] = asyncio.run(multi_source(verifier, [e for e in rows if single_sentence(e.claim)], rng))
    m = results["multi_source"]
    print(
        f"  {'multi_source':28} n={m['n']:<4} joined claim supported {m['joint_supported']:.0%} "
        f"(via combining: {m['via_combining']:.0%}), a single source wrongly passed it {m['single_source_passed']:.0%}"
    )

    out = RESULTS / f"perturbations-{args.verifier}.json"
    out.write_text(json.dumps({"results": results, "examples": examples}, indent=2))
    print(f"wrote {out}")


async def multi_source(verifier: Verifier, rows: list, rng: random.Random, n: int = 100) -> dict:
    """Join two supported claims, cite both sources, and audit through the full pipeline."""

    async def audit(answer: str, sources: list[Source]):
        report = await run_audit(AuditRequest(answer=answer, sources=sources), verifier, fetch=False)
        return report.claims[0]

    tried = joint_ok = via_combining = single_passed = 0
    for a, b in zip(rows[0::2], rows[1::2]):
        if tried == n:
            break
        src_a = Source(id="1", text="\n".join(a.evidence))
        src_b = Source(id="2", text="\n".join(b.evidence))
        # Only pairs where each half is supported on its own make a fair test.
        if (await audit(f"{a.claim} [1]", [src_a])).verdict != Verdict.SUPPORTED:
            continue
        if (await audit(f"{b.claim} [2]", [src_b])).verdict != Verdict.SUPPORTED:
            continue
        tried += 1
        joined = f"{a.claim.rstrip(' .')}; {b.claim.rstrip(' .')} [1][2]."
        claim = await audit(joined, [src_a, src_b])
        joint_ok += claim.verdict == Verdict.SUPPORTED
        via_combining += claim.note is not None and "combined" in claim.note
        single_passed += any(c.verdict == Verdict.SUPPORTED for c in claim.checks)
    return {
        "n": tried,
        "joint_supported": round(joint_ok / tried, 3),
        "via_combining": round(via_combining / tried, 3),
        "single_source_passed": round(single_passed / tried, 3),
    }


if __name__ == "__main__":
    main()
