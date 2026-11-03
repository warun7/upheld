"""Score verifiers against the fresh benchmark's labels.

Each labeled citation's page is fetched once, the way upheld fetches it, and
evidence is retrieved from it the way upheld retrieves it, for 3, 6 and 10
passages per claim. Every verifier member is scored on each, and the scores
are cached per member and setting in scores/, keyed by item id, so the
ensembles and settings can be compared without rerunning the models.

    uv run python evals/fresh/verifiers.py pages              # fetch the labeled pages -> sources/ (not committed)
    uv run python evals/fresh/verifiers.py score judge        # also minicheck, lettuce, lexical; resumable
    uv run python evals/fresh/verifiers.py report

Partial counts as unsupported, as in the scoreboard. Citations labeled can't
judge, and pages upheld can't read, are left out. Thresholds come from the
AttributionBench dev split (evals/results/attributionbench.json), never from
these labels. The report gives each verifier as shipped, with the passages per
claim it uses, then every verifier at every setting.
"""

import argparse
import asyncio
import hashlib
import json
import math
from pathlib import Path

from upheld.evidence import SourceIndex, make_embedder
from upheld.models import Source
from upheld.sources import fetch_all
from upheld.verify import EnsembleVerifier, GraniteJudgeVerifier, LettuceVerifier, LexicalVerifier, MiniCheckVerifier, make_verifier

HERE = Path(__file__).parent
SOURCES = HERE / "sources"
SCORES = HERE / "scores"
AB_RESULTS = HERE.parent / "results" / "attributionbench.json"
TOP_K = (3, 6, 10)
ENSEMBLES = {
    "ensemble": (EnsembleVerifier.WEIGHTS, EnsembleVerifier.BIAS),
    "ensemble+judge": (EnsembleVerifier.JUDGE_WEIGHTS, EnsembleVerifier.JUDGE_BIAS),
}
# Passages per claim each verifier ships with.
SHIPPED = {
    "ensemble": EnsembleVerifier.TOP_K,
    "ensemble+judge": EnsembleVerifier.JUDGE_TOP_K,
    "judge": GraniteJudgeVerifier.top_k,
    "minicheck": MiniCheckVerifier.top_k,
    "lettuce": LettuceVerifier.top_k,
    "lexical": LexicalVerifier.top_k,
}


def _labels() -> dict[str, str]:
    rows = {r["id"]: r["label"] for r in map(json.loads, (HERE / "labels-claude.jsonl").read_text().splitlines())}
    rows |= {r["id"]: r["label"] for r in map(json.loads, (HERE / "labels.jsonl").read_text().splitlines())}
    return rows


def _source_path(url: str) -> Path:
    return SOURCES / f"{hashlib.sha1(url.encode()).hexdigest()[:16]}.json"


def _labeled() -> list[dict]:
    labels = _labels()
    items = [i for i in map(json.loads, (HERE / "items.jsonl").read_text().splitlines()) if i["url"]]
    return [i | {"label": labels[i["id"]]} for i in items if labels.get(i["id"], "cant_judge") != "cant_judge"]


def _items() -> list[dict]:
    """Labeled citations whose page upheld can read, with the page text."""
    out = []
    for item in _labeled():
        path = _source_path(item["url"])
        if path.exists() and (page := json.loads(path.read_text()))["text"]:  # live, or read from an archived copy
            out.append(item | {"page": page["text"]})
    return out


def pages() -> None:
    SOURCES.mkdir(exist_ok=True)
    urls = sorted({i["url"] for i in _labeled() if not _source_path(i["url"]).exists()})
    fetched = asyncio.run(fetch_all([Source(id=str(n), url=url) for n, url in enumerate(urls)]))
    for f in fetched.values():
        archived_at = f.archived_at.isoformat() if f.archived_at else None
        page = {"url": f.source.url, "status": f.status.value, "note": f.note, "archived_at": archived_at, "text": f.text}
        _source_path(f.source.url).write_text(json.dumps(page))
    archived = sum(bool(f.archived_at) for f in fetched.values())
    print(f"{sum(bool(f.text) for f in fetched.values())} of {len(urls)} new pages readable ({archived} from an archived copy), in {SOURCES}")


def _evidence(items: list[dict]) -> dict[str, dict[str, list[str]]]:
    path = SOURCES / "passages.json"  # page text, so it stays out of the repo with the pages
    evidence = json.loads(path.read_text()) if path.exists() else {}
    todo = [i for i in items if any(i["id"] not in evidence.get(str(k), {}) for k in TOP_K)]
    if todo:
        embedder = make_embedder("auto")
        indexes: dict[str, SourceIndex] = {}
        for item in todo:
            index = indexes.setdefault(item["url"], SourceIndex(item["page"], embedder))
            for k in TOP_K:
                evidence.setdefault(str(k), {})[item["id"]] = [p for p, _ in index.search(item["claim"], k)]
        path.write_text(json.dumps(evidence))
    return evidence


def score(name: str, device: str | None) -> None:
    items = {i["id"]: i for i in _items()}
    evidence = _evidence(list(items.values()))
    verifier = make_verifier(name, device=device)
    for k in TOP_K:
        out = SCORES / f"{name}-top{k}.json"
        done = json.loads(out.read_text()) if out.exists() else {}
        for n, item in enumerate(items.values(), 1):
            if item["id"] in done:
                continue
            [result] = verifier.check(item["claim"], [(0, len(item["claim"]))], evidence[str(k)][item["id"]], item["question"])
            done[item["id"]] = result.score
            if n % 50 == 0:
                out.write_text(json.dumps(done))
        out.write_text(json.dumps(done))
        print(f"{name} top {k}: {len(done)} scores", flush=True)


def _all_scores() -> dict[tuple[str, int], dict[str, float]]:
    """Cached scores by (verifier, passages per claim), with the shipped ensembles computed from their members."""
    scores = {}
    for path in SCORES.glob("*-top*.json"):
        name, k = path.stem.rsplit("-top", 1)
        scores[name, int(k)] = json.loads(path.read_text())
    for name, (weights, bias) in ENSEMBLES.items():
        for k in TOP_K:
            if all((m, k) in scores for m in weights):
                ids = set.intersection(*(set(scores[m, k]) for m in weights))
                scores[name, k] = {i: 1 / (1 + math.exp(-(bias + sum(w * scores[m, k][i] for m, w in weights.items())))) for i in ids}
    return scores


def load_scores() -> tuple[dict[str, dict[str, float]], dict[str, float]]:
    """Each verifier's scores as shipped, by item id, and each verifier's dev threshold."""
    thresholds = {name: r["dev_threshold"] for name, r in json.loads(AB_RESULTS.read_text())["systems"].items()}
    scores = _all_scores()
    return {name: scores[name, k] for name, k in SHIPPED.items() if (name, k) in scores}, thresholds


def report() -> None:
    labels = {i["id"]: i["label"] for i in _items()}
    thresholds = {name: r["dev_threshold"] for name, r in json.loads(AB_RESULTS.read_text())["systems"].items()}
    scores = _all_scores()

    def row(name: str, k: int) -> str:
        rows = [(s < thresholds.get(name, 0.5), labels[i] != "supported") for i, s in scores[name, k].items() if i in labels]
        m = metrics(rows)
        good = [flagged for flagged, bad in rows if not bad]
        return f"{name:15} {k:>8} {m['agree']:>6.0%} {100 * m['macro_f1']:>8.1f} {m['recall']:>12.0%} {sum(good) / len(good):>13.0%}"

    header = f"{'verifier':15} {'passages':>8} {'agree':>6} {'macroF1':>8} {'bad flagged':>12} {'good flagged':>13}"
    print(f"{len(labels)} labeled citations with a readable page; unsupported = partial or unsupported\n\nAs shipped:\n{header}")
    for name, k in SHIPPED.items():
        if (name, k) in scores:
            print(row(name, k))
    print(f"\nBy passages per claim:\n{header}")
    for name in SHIPPED:
        for k in TOP_K:
            if (name, k) in scores:
                print(row(name, k))


def metrics(rows: list[tuple[bool, bool]]) -> dict[str, float]:
    """rows: (flagged, actually unsupported)."""
    tp = sum(f and u for f, u in rows)
    fp = sum(f and not u for f, u in rows)
    fn = sum(u and not f for f, u in rows)
    tn = len(rows) - tp - fp - fn
    f1 = lambda p, r: 2 * p * r / (p + r) if p + r else 0.0  # noqa: E731
    p_bad, r_bad = tp / (tp + fp) if tp + fp else 0.0, tp / (tp + fn) if tp + fn else 0.0
    p_ok, r_ok = tn / (tn + fn) if tn + fn else 0.0, tn / (tn + fp) if tn + fp else 0.0
    return {"agree": (tp + tn) / len(rows), "macro_f1": (f1(p_bad, r_bad) + f1(p_ok, r_ok)) / 2, "precision": p_bad, "recall": r_bad}


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("pages")
    p = sub.add_parser("score")
    p.add_argument("verifier", choices=["lexical", "lettuce", "minicheck", "judge"])
    p.add_argument("--device", default=None)
    sub.add_parser("report")
    args = parser.parse_args()
    if args.command == "pages":
        pages()
    elif args.command == "score":
        score(args.verifier, args.device)
    else:
        report()


if __name__ == "__main__":
    main()
