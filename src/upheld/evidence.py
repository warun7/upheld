"""Find the passages in a source that are most relevant to a claim.

Keyword search (BM25) misses paraphrases: an answer says "intended to stand
for only 20 years" where the source says "slated for dismantling in 1909".
Hybrid mode adds a small embedding model and merges the two rankings with
reciprocal rank fusion, so a passage either method ranks highly makes the cut.
"""

import re
from typing import Protocol

import numpy as np
from rank_bm25 import BM25Okapi

STOPWORDS = frozenset(
    "a an and are as at be been but by for from has have in is it its of on or that the this to was were will with "
    "which who what when where how than then there their they them these those not no can could would should".split()
)
_WORD = re.compile(r"[a-z0-9]+(?:[.,'][a-z0-9]+)*")


def tokenize(text: str) -> list[str]:
    return [w for w in _WORD.findall(text.lower()) if w not in STOPWORDS]


def chunk(text: str, size: int = 120, overlap: int = 30) -> list[str]:
    """Split text into overlapping word windows, starting each window at a sentence boundary where possible."""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    chunks: list[str] = []
    current: list[str] = []
    for sentence in sentences:
        words = sentence.split()
        if current and len(current) + len(words) > size:
            chunks.append(" ".join(current))
            current = current[-overlap:] if overlap else []
        current.extend(words)
    if current:
        chunks.append(" ".join(current))
    return chunks


class Embedder(Protocol):
    name: str

    def embed(self, texts: list[str], *, query: bool = False) -> np.ndarray:
        """Return one L2-normalized vector per text."""
        ...


class SentenceEmbedder:
    DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"
    # bge v1.5 recommends this prefix on short retrieval queries.
    BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

    def __init__(self, model_name: str = DEFAULT_MODEL):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            raise ImportError('hybrid retrieval needs the optional extra: pip install "upheld[dense]"') from e
        self.model = SentenceTransformer(model_name)
        self.name = model_name.rsplit("/", 1)[-1]
        self.query_prefix = self.BGE_QUERY_PREFIX if "bge" in model_name.lower() else ""

    def embed(self, texts: list[str], *, query: bool = False) -> np.ndarray:
        if query:
            texts = [self.query_prefix + t for t in texts]
        return self.model.encode(texts, normalize_embeddings=True, batch_size=32, show_progress_bar=False)


def make_embedder(retrieval: str) -> Embedder | None:
    """`bm25` -> None, `hybrid` -> embedding model, `auto` -> hybrid if the dense extra is installed."""
    if retrieval == "bm25":
        return None
    if retrieval == "hybrid":
        return SentenceEmbedder()
    if retrieval == "auto":
        try:
            return SentenceEmbedder()
        except ImportError:
            return None
    raise ValueError(f"unknown retrieval: {retrieval} (choose auto, bm25 or hybrid)")


def retrieval_name(embedder: Embedder | None) -> str:
    return "bm25" if embedder is None else f"hybrid:bm25+{embedder.name}"


def rrf(rankings: list[list[int]], k: int = 60) -> list[tuple[int, float]]:
    """Reciprocal rank fusion: score each item by the sum of 1 / (k + rank) across rankings."""
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, 1):
            scores[item] = scores.get(item, 0.0) + 1 / (k + rank)
    return sorted(scores.items(), key=lambda pair: pair[1], reverse=True)


class SourceIndex:
    """One source's passages, indexed once and searched once per claim."""

    def __init__(self, text: str, embedder: Embedder | None = None):
        self.passages = chunk(text)
        self.embedder = embedder
        self._bm25 = BM25Okapi([tokenize(p) for p in self.passages]) if self.passages else None
        self._vectors: np.ndarray | None = None

    def search(self, query: str, k: int = 3) -> list[tuple[str, float]]:
        """Top-k passages with scores scaled so the best is 1.0."""
        if len(self.passages) <= k:
            return [(p, 1.0) for p in self.passages]
        scores = self._bm25.get_scores(tokenize(query))
        order = [int(i) for i in np.argsort(-scores)]
        if self.embedder is None:
            ranked = [(i, float(scores[i])) for i in order[:k]]
        else:
            if self._vectors is None:
                self._vectors = self.embedder.embed(self.passages)
            query_vector = self.embedder.embed([query], query=True)[0]
            dense = [int(i) for i in np.argsort(-(self._vectors @ query_vector))]
            # Passages with no keyword overlap don't get a BM25 rank.
            keyword = [i for i in order if scores[i] > 0]
            ranked = rrf([keyword, dense])[:k]
        best = ranked[0][1] or 1.0
        return [(self.passages[i], round(s / best, 3)) for i, s in ranked]
