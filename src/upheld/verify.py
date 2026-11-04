"""Verifiers decide whether evidence passages support claims in an answer.

They are swappable on purpose: measured citation accuracy depends heavily on
the verifier, so every report names the verifier and threshold it used, and
`upheld eval` compares them on the same labeled data.

Verifiers see the whole answer, not just one claim: LettuceDetect was trained
on full RAG responses and misjudges sentences scored in isolation.
"""

import math
import re
from dataclasses import dataclass, field
from typing import Protocol

from upheld.evidence import tokenize
from upheld.models import Span


@dataclass
class SupportResult:
    score: float  # estimated probability that the claim is supported, 0-1
    spans: list[Span] = field(default_factory=list)  # offsets relative to the claim


class Verifier(Protocol):
    name: str
    threshold: float  # a claim is supported when score >= threshold
    top_k: int  # evidence passages retrieved per claim from each source

    def check(
        self, answer: str, claims: list[tuple[int, int]], passages: list[str], question: str | None = None
    ) -> list[SupportResult]:
        """Score each claim (a start/end range within `answer`) against the passages."""
        ...


_NUMBER = re.compile(r"\d+(?:[.,]\d+)*%?")


def _normalize_number(n: str) -> str:
    return n.replace(",", "")


class LexicalVerifier:
    """Baseline: share of the claim's content words found in the evidence.

    Numbers must match exactly. This is deliberately simple; it exists so the
    learned verifiers have something to beat in evals, and so tests run
    without downloading a model.
    """

    top_k = 3

    def __init__(self, threshold: float = 0.7):
        self.threshold = threshold
        self.name = f"lexical@{threshold}"

    def check(
        self, answer: str, claims: list[tuple[int, int]], passages: list[str], question: str | None = None
    ) -> list[SupportResult]:
        evidence = " ".join(passages)
        evidence_words = set(tokenize(evidence))
        evidence_numbers = {_normalize_number(n) for n in _NUMBER.findall(evidence)}
        return [self._check_one(answer[s:e], evidence_words, evidence_numbers) for s, e in claims]

    def _check_one(self, claim: str, evidence_words: set[str], evidence_numbers: set[str]) -> SupportResult:
        words = tokenize(claim)
        if not words:
            return SupportResult(1.0)
        covered = sum(w in evidence_words for w in words) / len(words)
        spans = [
            Span(start=m.start(), end=m.end(), text=m.group(), confidence=1.0)
            for m in _NUMBER.finditer(claim)
            if _normalize_number(m.group()) not in evidence_numbers
        ]
        score = 0.0 if spans else covered
        return SupportResult(round(score, 3), spans)


class LettuceVerifier:
    """LettuceDetect token classifier (ModernBERT), run on CPU or GPU.

    One forward pass scores every answer token against the passages. A
    claim's score is 1 minus the highest hallucination probability among its
    tokens, which matches LettuceDetect's own decision rule at threshold 0.5.
    """

    top_k = 3
    DEFAULT_MODEL = "KRLabsOrg/lettucedect-base-modernbert-en-v1"

    def __init__(self, model_path: str = DEFAULT_MODEL, threshold: float = 0.5, device: str | None = None):
        try:
            from lettucedetect.models.inference import HallucinationDetector
        except ImportError as e:
            raise ImportError('LettuceVerifier needs the optional extra: pip install "upheld[lettuce]"') from e
        self.detector = HallucinationDetector(method="transformer", model_path=model_path, device=device)
        self.threshold = threshold
        self.name = f"lettuce:{model_path.rsplit('/', 1)[-1]}@{threshold}"

    def check(
        self, answer: str, claims: list[tuple[int, int]], passages: list[str], question: str | None = None
    ) -> list[SupportResult]:
        tokens = self.detector.predict(context=passages, answer=answer, question=question, output_format="tokens")
        located = _locate_tokens(answer, [t["token"] for t in tokens])
        # Punctuation-only tokens can't carry a false claim, but the model sometimes flags them.
        probs = [(span, t["prob"]) for span, t in zip(located, tokens) if span is not None and any(ch.isalnum() for ch in t["token"])]
        return [self._claim_result(answer, s, e, probs) for s, e in claims]

    def _claim_result(self, answer: str, start: int, end: int, probs: list[tuple[tuple[int, int], float]]) -> SupportResult:
        inside = [(span, p) for span, p in probs if start <= span[0] and span[1] <= end]
        worst = max((p for _, p in inside), default=0.0)
        score = round(1.0 - worst, 3)
        if score >= self.threshold:
            return SupportResult(score)

        # Merge consecutive flagged tokens into spans for display.
        flagged_above = 1.0 - self.threshold
        spans: list[Span] = []
        run: list[tuple[tuple[int, int], float]] = []
        for item in [*inside, None]:
            if item is not None and item[1] > flagged_above:
                run.append(item)
                continue
            if run:
                s, e = run[0][0][0], run[-1][0][1]
                spans.append(Span(start=s - start, end=e - start, text=answer[s:e], confidence=round(max(p for _, p in run), 3)))
                run = []
        return SupportResult(score, spans)


class MiniCheckVerifier:
    """MiniCheck-Flan-T5-Large (Tang et al., 2024), run on CPU or GPU.

    Trained for the exact question upheld asks: is every part of this claim
    supported by this document? LettuceDetect instead looks for hallucinated
    spans in a whole answer. MiniCheck reads one claim at a time, so the rest
    of the answer is ignored. Long evidence is split into ~500-word chunks and
    a claim scores its best chunk, as in the reference implementation. It
    gives a score but no flagged spans.
    """

    top_k = 3
    DEFAULT_MODEL = "lytang/MiniCheck-Flan-T5-Large"
    CHUNK_WORDS = 500
    MAX_TOKENS = 2048
    LABEL_TOKENS = [3, 209]  # the tokens it was trained to emit for unsupported / supported

    def __init__(self, model_path: str = DEFAULT_MODEL, threshold: float = 0.5, device: str | None = None, batch_size: int = 8):
        try:
            import torch
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
        except ImportError as e:
            raise ImportError('MiniCheckVerifier needs the optional extra: pip install "upheld[minicheck]"') from e
        if device is None:
            device = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
        self.torch = torch
        self.device = device
        self.tokenizer = AutoTokenizer.from_pretrained(model_path)
        self.model = AutoModelForSeq2SeqLM.from_pretrained(model_path).to(device).eval()
        self.batch_size = batch_size
        self.threshold = threshold
        self.name = f"minicheck:{model_path.rsplit('/', 1)[-1]}@{threshold}"

    def check(
        self, answer: str, claims: list[tuple[int, int]], passages: list[str], question: str | None = None
    ) -> list[SupportResult]:
        chunks = _word_chunks(passages, self.CHUNK_WORDS)
        probs = self._support_probs([(chunk, answer[s:e]) for s, e in claims for chunk in chunks])
        n = len(chunks)
        return [SupportResult(round(max(probs[i * n : (i + 1) * n]), 3)) for i in range(len(claims))]

    def _support_probs(self, pairs: list[tuple[str, str]]) -> list[float]:
        eos = self.tokenizer.eos_token
        texts = [f"predict: {doc}{eos}{claim}" for doc, claim in pairs]
        probs: list[float] = []
        for i in range(0, len(texts), self.batch_size):
            batch = self.tokenizer(
                texts[i : i + self.batch_size], max_length=self.MAX_TOKENS, truncation=True, padding=True, return_tensors="pt"
            ).to(self.device)
            start = self.torch.zeros((batch["input_ids"].shape[0], 1), dtype=self.torch.long, device=self.device)
            with self.torch.no_grad():
                logits = self.model(**batch, decoder_input_ids=start).logits[:, 0, self.LABEL_TOKENS]
            probs.extend(logits.softmax(dim=-1)[:, 1].tolist())
        return probs


class GraniteJudgeVerifier:
    """Granite Guardian 3.3 8B (IBM, Apache 2.0) as an LLM judge, run with llama.cpp.

    For the claims the small models get wrong because they take reasoning: a
    fact pinned on another party the page also names, a claim the page
    contradicts in its own words, a step of inference. Granite Guardian's
    groundedness check reads the evidence and the claim and answers whether
    the claim is ungrounded; the score is the probability that it answers no.
    It runs IBM's 8-bit GGUF (8.7 GB, downloaded on first use) on Metal, CUDA
    or CPU. Long evidence is split into ~1,500-word chunks and a claim scores
    its best chunk. Claims checked against the same chunk reuse its cached
    prompt, so only the claim is read again.
    """

    top_k = 3
    GGUF_REPO = "ibm-granite/granite-guardian-3.3-8b-GGUF"
    GGUF_FILE = "granite-guardian-3.3-8b-Q8_0.gguf"
    TOKENIZER = "ibm-granite/granite-guardian-3.3-8b"  # its chat template, which llama.cpp can't render with documents
    VERDICT_PREFIX = "<think>\n</think>\n<score>"  # what it writes before " yes" (ungrounded) or " no" with thinking off
    CHUNK_WORDS = 1500
    N_CTX = 8192

    def __init__(self, threshold: float = 0.5, device: str | None = None, model_path: str | None = None):
        try:
            import llama_cpp
            from huggingface_hub import hf_hub_download
            from transformers import AutoTokenizer
        except ImportError as e:
            raise ImportError('GraniteJudgeVerifier needs the optional extra: pip install "upheld[judge]"') from e
        self.llama_cpp = llama_cpp
        self.tokenizer = AutoTokenizer.from_pretrained(self.TOKENIZER)
        path = model_path or hf_hub_download(self.GGUF_REPO, self.GGUF_FILE)
        self.llm = llama_cpp.Llama(path, n_ctx=self.N_CTX, n_gpu_layers=0 if device == "cpu" else -1, verbose=False)
        self.yes, self.no = (self.llm.tokenize(t.encode(), add_bos=False, special=False)[0] for t in (" yes", " no"))
        self.threshold = threshold
        self.name = f"judge:granite-guardian-3.3-8b@{threshold}"

    def check(
        self, answer: str, claims: list[tuple[int, int]], passages: list[str], question: str | None = None
    ) -> list[SupportResult]:
        # The question is left out on purpose: shown it, the judge also weighs whether the claim
        # answers it, which cut its AUC on 300 AttributionBench dev rows from 0.85 to 0.76.
        chunks = _word_chunks(passages, self.CHUNK_WORDS)
        return [SupportResult(round(max(self._grounded(chunk, answer[s:e]) for chunk in chunks), 3)) for s, e in claims]

    def _grounded(self, document: str, claim: str) -> float:
        prompt = self.tokenizer.apply_chat_template(
            [{"role": "assistant", "content": claim}],
            documents=[{"doc_id": "0", "text": document}],
            guardian_config={"criteria_id": "groundedness"},
            think=False,
            tokenize=False,
            add_generation_prompt=True,
        )
        tokens = self.llm.tokenize((prompt + self.VERDICT_PREFIX).encode(), add_bos=False, special=True)
        if len(tokens) >= self.N_CTX:
            return self._grounded(document[: len(document) * 3 // 4], claim)
        # Keep whatever prefix (the system prompt and document) the last call already read.
        cached = self.llm.input_ids[: self.llm.n_tokens]
        keep = 0
        while keep < min(len(cached), len(tokens) - 1) and cached[keep] == tokens[keep]:
            keep += 1
        self.llm.n_tokens = keep
        self.llm.eval(tokens[keep:])
        logits = self.llama_cpp.llama_get_logits_ith(self.llm.ctx, -1)
        yes, no = logits[self.yes], logits[self.no]
        return 1 / (1 + math.exp(yes - no))


class EnsembleVerifier:
    """Logistic regression over MiniCheck, word overlap and LettuceDetect.

    Each catches failures the others miss: MiniCheck judges entailment claim
    by claim, word overlap rewards evidence that repeats the claim's wording
    and numbers, and LettuceDetect reads the claim in the context of the whole
    answer and points at the unsupported span. The weights were fit on 2,000
    rows of AttributionBench's train split and the threshold checked on its
    dev split (evals/attributionbench.py report prints them).

    with_judge adds the Granite judge as a fourth member, with its own fit. It
    is the most accurate setup but needs the judge extra, a 9 GB model and,
    reading 10 passages per claim, about 2.5 seconds per claim, so it is opt-in.
    """

    WEIGHTS = {"minicheck": 1.61, "lexical": 1.33, "lettuce": 0.52}
    BIAS = -1.69
    THRESHOLD = 0.5
    JUDGE_WEIGHTS = {"judge": 1.57, "minicheck": 0.64, "lexical": 0.91, "lettuce": 0.28}
    JUDGE_BIAS = -1.56
    JUDGE_THRESHOLD = 0.48
    # With the judge, reading more of the page cuts false alarms: on the fresh benchmark, 10 passages
    # per claim instead of 3 lifted macro-F1 from 82.0 to 84.1 and flagged 18% of good citations instead
    # of 27% (evals/fresh/verifiers.py). The default ensemble gains nothing from more, so it keeps 3.
    TOP_K = 3
    JUDGE_TOP_K = 10

    def __init__(self, threshold: float | None = None, device: str | None = None, with_judge: bool = False):
        self.members: dict[str, Verifier] = {
            "minicheck": MiniCheckVerifier(device=device),
            "lexical": LexicalVerifier(),
            "lettuce": LettuceVerifier(device=device),
        }
        if with_judge:
            self.members["judge"] = GraniteJudgeVerifier(device=device)
        self.weights, self.bias = (self.JUDGE_WEIGHTS, self.JUDGE_BIAS) if with_judge else (self.WEIGHTS, self.BIAS)
        self.threshold = threshold if threshold is not None else self.JUDGE_THRESHOLD if with_judge else self.THRESHOLD
        self.top_k = self.JUDGE_TOP_K if with_judge else self.TOP_K
        self.name = f"ensemble:{'+'.join(self.members)}@{self.threshold}"

    def check(
        self, answer: str, claims: list[tuple[int, int]], passages: list[str], question: str | None = None
    ) -> list[SupportResult]:
        results = {name: m.check(answer, claims, passages, question) for name, m in self.members.items()}
        out = []
        for i in range(len(claims)):
            z = self.bias + sum(w * results[name][i].score for name, w in self.weights.items())
            score = round(1 / (1 + math.exp(-z)), 3)
            # Show where the claim goes wrong: LettuceDetect's spans, else word overlap's mismatched numbers.
            spans = (results["lettuce"][i].spans or results["lexical"][i].spans) if score < self.threshold else []
            out.append(SupportResult(score, spans))
        return out


_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+|\n+")


def _word_chunks(passages: list[str], max_words: int) -> list[str]:
    """Pack whole sentences into chunks of at most ~max_words words."""
    chunks: list[str] = []
    current: list[str] = []
    count = 0
    for sentence in (s for p in passages for s in _SENTENCE_BREAK.split(p) if s.strip()):
        words = len(sentence.split())
        if current and count + words > max_words:
            chunks.append(" ".join(current))
            current, count = [], 0
        current.append(sentence)
        count += words
    if current:
        chunks.append(" ".join(current))
    return chunks or [""]


def _locate_tokens(text: str, tokens: list[str]) -> list[tuple[int, int] | None]:
    """Map decoded tokens back to character ranges in `text`, in order."""
    located: list[tuple[int, int] | None] = []
    cursor = 0
    for token in tokens:
        piece = token.strip()
        i = text.find(piece, cursor) if piece else -1
        if i == -1 or i - cursor > 50:
            located.append(None)
            continue
        located.append((i, i + len(piece)))
        cursor = i + len(piece)
    return located


def make_verifier(name: str, threshold: float | None = None, device: str | None = None) -> Verifier:
    """Build a verifier by name. `device` (e.g. "mps", "cuda") applies to the model-based ones."""
    kwargs = {} if threshold is None else {"threshold": threshold}
    if name == "lexical":
        return LexicalVerifier(**kwargs)
    if name == "lettuce":
        return LettuceVerifier(device=device, **kwargs)
    if name == "minicheck":
        return MiniCheckVerifier(device=device, **kwargs)
    if name == "ensemble":
        return EnsembleVerifier(device=device, **kwargs)
    if name == "ensemble+judge":
        return EnsembleVerifier(device=device, with_judge=True, **kwargs)
    if name == "judge":
        return GraniteJudgeVerifier(device=device, **kwargs)
    raise ValueError(f"unknown verifier: {name} (choose ensemble, ensemble+judge, minicheck, lettuce, lexical or judge)")
