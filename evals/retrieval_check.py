"""Does retrieval surface the passage that supports each claim?

Fetches the live Wikipedia article on the Eiffel Tower and, for 10 claims
paraphrased the way AI answers phrase them, reports the rank of the first
passage containing the supporting text under BM25 and hybrid retrieval.

    uv run python evals/retrieval_check.py

The claims were written by hand for this check, so treat it as a regression
test, not a benchmark. The article changes over time; if a gold snippet
disappears, the script says so.
"""

import asyncio

from upheld.evidence import SentenceEmbedder, SourceIndex
from upheld.models import Source
from upheld.sources import fetch_all

URL = "https://en.wikipedia.org/wiki/Eiffel_Tower"
DEPTH = 20

# (claim, text that appears in the supporting passage)
CASES = [
    ("It was originally intended to stand for only 20 years.", "slated for dismantling in 1909"),
    ("The tower's design is credited to two engineers at Eiffel's company, Maurice Koechlin and Émile Nouguier.", "attributed to Maurice Koechlin"),
    ("Prominent writers and artists signed a protest against its construction.", "protest with all our strength"),
    ("It drew almost 5.9 million visitors in 2022.", "5,889,000 visitors"),
    ("The iron structure alone weighs about 7,300 tonnes.", "weighs 7,300 tonnes"),
    ("It survived planned demolition because it proved useful for radio and scientific experiments.", "spared from scheduled demolition"),
    ("An antenna added in 1957 made it taller than the Chrysler Building.", "aerial at the top of the tower in 1957"),
    ("The company's head architect, Stephen Sauvestre, added decorative arches at the base.", "Sauvestre added decorative arches"),
    ("The top level is generally reachable only by elevator.", "usually accessible only by lift"),
    ("Before it was built, nobody had ever constructed something 300 metres high.", "constructed to a height of 300 m"),
]


def rank(index: SourceIndex, claim: str, gold: str) -> int | None:
    hits = index.search(claim, k=DEPTH)
    return next((r for r, (passage, _) in enumerate(hits, 1) if gold in passage), None)


def main() -> None:
    fetched = asyncio.run(fetch_all([Source(id="1", url=URL)]))["1"]
    if not fetched.text:
        raise SystemExit(f"could not fetch {URL}: {fetched.note}")

    indexes = {"bm25": SourceIndex(fetched.text), "hybrid": SourceIndex(fetched.text, SentenceEmbedder())}
    passages = indexes["bm25"].passages
    cases = [(c, g) for c, g in CASES if any(g in p for p in passages)]
    for claim, gold in CASES:
        if (claim, gold) not in cases:
            print(f"skipped, gold text no longer in article: {gold!r}")

    print(f"{len(passages)} passages, {len(cases)} claims\n")
    for name, index in indexes.items():
        ranks = [rank(index, c, g) for c, g in cases]
        hits = sum(r is not None and r <= 3 for r in ranks)
        shown = [r if r is not None else f">{DEPTH}" for r in ranks]
        print(f"{name:7} hit@3 = {hits}/{len(cases)}   ranks = {shown}")


if __name__ == "__main__":
    main()
