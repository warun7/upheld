"""Score upheld's verifiers on AttributionBench (Li et al., 2024, arXiv:2402.15089).

AttributionBench pools human labels on whether cited evidence fully supports a
claim, from seven datasets. Stanford-GenSearch and AttrScore-GenSearch come
from real generative search engines (Bing Chat, NeevaAI, Perplexity, YouChat).
The paper reports macro-F1 over both classes on balanced test splits:

  in-distribution (ID):      ExpertQA, Stanford-GenSearch, AttributedQA, LFQA
  out-of-distribution (OOD): BEGIN, AttrScore-GenSearch, HAGRID

Two steps, so each verifier runs once and every comparison reuses its scores:

    uv run python evals/attributionbench.py score lexical
    uv run python evals/attributionbench.py score lettuce --device mps
    uv run python evals/attributionbench.py score minicheck --device mps
    uv run python evals/attributionbench.py report

`score` caches one score per example in evals/results/scores/. `report` picks
each verifier's threshold on the dev split (never the test splits), adds a
logistic-regression ensemble of every scored verifier trained on a sample of
the train split, prints macro-F1 per subset, and writes
evals/results/attributionbench.json.
"""

import argparse
import json
import random
import time
from collections import defaultdict
from pathlib import Path

import httpx

from upheld.entities import missing_entities
from upheld.evals import Example, Metrics, metrics_for
from upheld.verify import make_verifier

BASE = "https://huggingface.co/datasets/osunlp/AttributionBench/resolve/main"
# split -> (file, rows to sample or None for all)
SPLITS = {
    "train": ("train_all_subset_balanced.jsonl", 2000),
    "dev": ("dev_all_subset_balanced.jsonl", None),
    "id": ("test_all_subset_balanced.jsonl", None),
    "ood": ("test_ood_all_subset_balanced.jsonl", None),
}
CACHE = Path.home() / ".cache" / "upheld" / "attributionbench"
RESULTS = Path(__file__).parent / "results"
SCORES = RESULTS / "scores"
THRESHOLDS = [t / 100 for t in range(1, 100)]


def load_split(split: str) -> list[tuple[str, Example]]:
    filename, sample = SPLITS[split]
    path = CACHE / filename
    if not path.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        r = httpx.get(f"{BASE}/{filename}", follow_redirects=True, timeout=120)
        r.raise_for_status()
        path.write_bytes(r.content)
    rows = []
    for line in path.read_text().splitlines():
        row = json.loads(line)
        claim, response = row["claim"], row.get("response") or ""
        example = Example(
            claim=claim,
            evidence=row["references"] or [""],
            unsupported=row["attribution_label"] != "attributable",
            question=row.get("question"),
            answer=response if claim in response else None,
        )
        rows.append((row["src_dataset"], example))
    return random.Random(0).sample(rows, sample) if sample else rows


def score(name: str, device: str | None, splits: list[str], force: bool) -> None:
    verifier = make_verifier(name, device=device)
    SCORES.mkdir(parents=True, exist_ok=True)
    for split in splits:
        out = SCORES / f"{name}-{split}.json"
        if out.exists() and not force:
            print(f"{out.name} exists, skipping (--force to redo)")
            continue
        rows = load_split(split)
        started = time.time()
        scores = []
        for _, e in rows:
            answer = e.answer or e.claim
            start = answer.index(e.claim)
            [result] = verifier.check(answer, [(start, start + len(e.claim))], e.evidence, e.question)
            scores.append(result.score)
        per_example = (time.time() - started) / len(rows)
        out.write_text(json.dumps({"verifier": verifier.name, "threshold": verifier.threshold, "split": split, "seconds_per_example": round(per_example, 3), "scores": scores}))
        print(f"{split}: {len(rows)} rows, {per_example:.3f}s/example -> {out}")


def report() -> None:
    from sklearn.linear_model import LogisticRegression

    rows = {split: load_split(split) for split in SPLITS}
    entity = {
        split: [bool(missing_entities(e.claim, "\n".join(e.evidence))) for _, e in split_rows] for split, split_rows in rows.items()
    }
    names = sorted({p.stem.rsplit("-", 1)[0] for p in SCORES.glob("*.json")})
    scored = {}  # name -> split -> list of support scores (higher = supported)
    defaults = {}  # name -> the verifier's own default threshold
    for name in names:
        files = {split: SCORES / f"{name}-{split}.json" for split in SPLITS}
        if all(f.exists() for f in files.values()):
            scored[name] = {split: json.loads(f.read_text())["scores"] for split, f in files.items()}
            defaults[name] = json.loads(files["dev"].read_text())["threshold"]
        else:
            print(f"skipping {name}: not scored on every split")

    # Every system is a support score per example plus a threshold picked on dev.
    systems: dict[str, dict[str, list[float]]] = {}
    for name, by_split in scored.items():
        systems[name] = by_split
        systems[f"{name}+entity"] = {s: [0.0 if entity[s][i] else x for i, x in enumerate(v)] for s, v in by_split.items()}
    if len(scored) > 1:
        # Same features as upheld's EnsembleVerifier: each verifier's raw score, nothing else.
        features = {s: [[scored[n][s][i] for n in scored] for i in range(len(rows[s]))] for s in SPLITS}
        labels = [not e.unsupported for _, e in rows["train"]]
        model = LogisticRegression(max_iter=1000).fit(features["train"], labels)
        systems["ensemble"] = {s: model.predict_proba(features[s])[:, 1].tolist() for s in SPLITS}
        systems["ensemble+entity"] = {s: [0.0 if entity[s][i] else x for i, x in enumerate(v)] for s, v in systems["ensemble"].items()}
        weights = dict(zip(scored, model.coef_[0].round(2).tolist()))
        print(f"ensemble weights (for EnsembleVerifier): WEIGHTS = {weights}, BIAS = {model.intercept_[0]:.2f}")

    results: dict = {}
    for name, by_split in systems.items():
        dev_examples = [e for _, e in rows["dev"]]
        dev_best = max(THRESHOLDS, key=lambda t: _metrics(by_split["dev"], dev_examples, t).macro_f1)
        results[name] = {"dev_threshold": dev_best}
        for split in ("id", "ood"):
            results[name][split] = _split_scores(by_split[split], rows[split], dev_best)
            if name in scored:
                results[name][split]["avg_at_default"] = _split_scores(by_split[split], rows[split], defaults[name])["avg"]

    for split in ("id", "ood"):
        subsets = sorted({subset for subset, _ in rows[split]})
        print(f"\n{split.upper()} macro-F1, threshold picked on dev")
        print(f"  {'system':18} {'thr':>5} " + " ".join(f"{s[:12]:>12}" for s in subsets) + f" {'avg':>6} {'@dflt':>6}")
        for name, r in results.items():
            m = r[split]
            default = f"{m['avg_at_default']:>6}" if "avg_at_default" in m else f"{'':>6}"
            print(f"  {name:18} {r['dev_threshold']:>5} " + " ".join(f"{m[s]:>12}" for s in subsets) + f" {m['avg']:>6} {default}")

    timing = {n: {s: json.loads((SCORES / f"{n}-{s}.json").read_text())["seconds_per_example"] for s in SPLITS} for n in scored}
    (RESULTS / "attributionbench.json").write_text(json.dumps({"systems": results, "seconds_per_example": timing}, indent=2))
    print(f"\nwrote {RESULTS / 'attributionbench.json'}")


def _metrics(scores: list[float], examples: list[Example], threshold: float) -> Metrics:
    return metrics_for([s < threshold for s in scores], examples, threshold)


def _split_scores(scores: list[float], rows: list[tuple[str, Example]], threshold: float) -> dict:
    """Macro-F1 per subset, plus the paper's average: the mean over subsets, not pooled."""
    by_subset: dict[str, list[int]] = defaultdict(list)
    for i, (subset, _) in enumerate(rows):
        by_subset[subset].append(i)
    out = {
        subset: round(100 * _metrics([scores[i] for i in idx], [rows[i][1] for i in idx], threshold).macro_f1, 1)
        for subset, idx in sorted(by_subset.items())
    }
    out["avg"] = round(sum(out.values()) / len(out), 1)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("score", help="run one verifier and cache its scores")
    p.add_argument("verifier", choices=["lexical", "lettuce", "minicheck"])
    p.add_argument("--device", default=None, help="torch device, e.g. mps or cuda")
    p.add_argument("--splits", nargs="+", default=list(SPLITS), choices=list(SPLITS))
    p.add_argument("--force", action="store_true")
    sub.add_parser("report", help="compare every cached verifier")
    args = parser.parse_args()
    if args.command == "score":
        score(args.verifier, args.device, args.splits, args.force)
    else:
        report()


if __name__ == "__main__":
    main()
