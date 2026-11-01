"""Score verifiers against the fresh benchmark's labels.

Each item already has the passages upheld retrieved from the cited page, so this
reruns only the verification step: no fetching. Scores are cached per verifier
in scores/, keyed by item id, so combinations can be compared without rerunning
the models.

    uv run python evals/fresh/verifiers.py score judge        # also minicheck, lettuce, lexical
    uv run python evals/fresh/verifiers.py report

Partial counts as unsupported, as in the scoreboard. Items labeled can't judge,
and items with no readable passages, are left out. Thresholds come from the
AttributionBench dev split (evals/results/attributionbench.json), never from
these labels.
"""

import argparse
import json
import math
from pathlib import Path

from upheld.verify import EnsembleVerifier, make_verifier

HERE = Path(__file__).parent
SCORES = HERE / "scores"
AB_RESULTS = HERE.parent / "results" / "attributionbench.json"


def _labels() -> dict[str, str]:
    rows = {r["id"]: r["label"] for r in map(json.loads, (HERE / "labels-claude.jsonl").read_text().splitlines())}
    rows |= {r["id"]: r["label"] for r in map(json.loads, (HERE / "labels.jsonl").read_text().splitlines())}
    return rows


def _items() -> list[dict]:
    labels = _labels()
    items = [i for i in map(json.loads, (HERE / "items.jsonl").read_text().splitlines()) if i["passages"]]
    return [i | {"label": labels[i["id"]]} for i in items if labels.get(i["id"], "cant_judge") != "cant_judge"]


def score(name: str, device: str | None) -> None:
    verifier = make_verifier(name, device=device)
    SCORES.mkdir(exist_ok=True)
    out = SCORES / f"{name}.json"
    done = json.loads(out.read_text()) if out.exists() else {}
    for n, item in enumerate(_items(), 1):
        if item["id"] in done:
            continue
        [result] = verifier.check(item["claim"], [(0, len(item["claim"]))], item["passages"], item["question"])
        done[item["id"]] = result.score
        if n % 50 == 0:
            out.write_text(json.dumps(done))
            print(f"{n} scored", flush=True)
    out.write_text(json.dumps(done))
    print(f"{len(done)} scores in {out}")


def report() -> None:
    items = _items()
    thresholds = {name: r["dev_threshold"] for name, r in json.loads(AB_RESULTS.read_text())["systems"].items()}
    scores = {p.stem: json.loads(p.read_text()) for p in sorted(SCORES.glob("*.json"))}
    ensembles = {
        "ensemble": (EnsembleVerifier.WEIGHTS, EnsembleVerifier.BIAS),
        "ensemble+judge": (EnsembleVerifier.JUDGE_WEIGHTS, EnsembleVerifier.JUDGE_BIAS),
    }
    for name, (weights, bias) in ensembles.items():
        if all(m in scores for m in weights):
            ids = set.intersection(*(set(scores[m]) for m in weights))
            scores[name] = {i: 1 / (1 + math.exp(-(bias + sum(w * scores[m][i] for m, w in weights.items())))) for i in ids}
    print(f"{len(items)} labeled items with passages; unsupported = partial or unsupported\n")
    print(f"{'verifier':12} {'thr':>5} {'agree':>6} {'macroF1':>8} {'prec':>5} {'recall':>6}")
    for name, by_id in scores.items():
        threshold = thresholds.get(name, 0.5)
        rows = [(by_id[i["id"]] < threshold, i["label"] != "supported") for i in items if i["id"] in by_id]
        print(f"{name:12} {threshold:>5} " + _metrics(rows))


def _metrics(rows: list[tuple[bool, bool]]) -> str:
    """rows: (flagged, actually unsupported)."""
    tp = sum(f and u for f, u in rows)
    fp = sum(f and not u for f, u in rows)
    fn = sum(u and not f for f, u in rows)
    tn = len(rows) - tp - fp - fn
    f1 = lambda p, r: 2 * p * r / (p + r) if p + r else 0.0  # noqa: E731
    p_bad, r_bad = tp / (tp + fp) if tp + fp else 0.0, tp / (tp + fn) if tp + fn else 0.0
    p_ok, r_ok = tn / (tn + fn) if tn + fn else 0.0, tn / (tn + fp) if tn + fp else 0.0
    macro = (f1(p_bad, r_bad) + f1(p_ok, r_ok)) / 2
    return f"{(tp + tn) / len(rows):>6.0%} {100 * macro:>8.1f} {p_bad:>5.2f} {r_bad:>6.2f}"


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("score")
    p.add_argument("verifier", choices=["lexical", "lettuce", "minicheck", "judge"])
    p.add_argument("--device", default=None)
    sub.add_parser("report")
    args = parser.parse_args()
    if args.command == "score":
        score(args.verifier, args.device)
    else:
        report()


if __name__ == "__main__":
    main()
