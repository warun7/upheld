import sys
import threading
import time
import types

import pytest


class FakeLlama:
    """Stands in for llama_cpp.Llama with no model. Like the real one, it fails when two threads decode at once."""

    YES, NO = 1, 2
    DECODE_SECONDS = 0.05  # long enough that two unguarded audits overlap

    def __init__(self):
        self.input_ids: list[int] = []
        self.n_tokens = 0
        self.ctx = None
        self.decodes: list[tuple[float, float, int]] = []  # start, end and tokens read, for each eval
        self.fail_next = False
        self._busy = threading.Lock()

    def tokenize(self, text: bytes, add_bos: bool = True, special: bool = False) -> list[int]:
        return {b" yes": [self.YES], b" no": [self.NO]}.get(text) or [3 + b for b in text]

    def eval(self, tokens: list[int]) -> None:
        if not self._busy.acquire(blocking=False):
            raise RuntimeError("llama_decode returned -3")
        try:
            start = time.monotonic()
            time.sleep(self.DECODE_SECONDS)
            if self.fail_next:
                self.fail_next = False
                raise RuntimeError("llama_decode returned -3")
            self.input_ids[self.n_tokens :] = tokens
            self.n_tokens += len(tokens)
            self.decodes.append((start, time.monotonic(), len(tokens)))
        finally:
            self._busy.release()

    def reset(self) -> None:
        self.n_tokens = 0


class FakeGuardianTokenizer:
    def apply_chat_template(self, messages, documents, **kwargs) -> str:
        return f"<document>{documents[0]['text']}</document><claim>{messages[0]['content']}</claim>"


@pytest.fixture
def fake_llama(monkeypatch) -> FakeLlama:
    """Lets GraniteJudgeVerifier load without llama.cpp or the model, and returns the model it gets."""
    model = FakeLlama()
    logits = {FakeLlama.YES: 0.0, FakeLlama.NO: 4.0}  # "not ungrounded", so every claim reads as supported
    monkeypatch.setitem(
        sys.modules, "llama_cpp", types.SimpleNamespace(Llama=lambda *a, **kw: model, llama_get_logits_ith=lambda ctx, i: logits)
    )
    monkeypatch.setitem(sys.modules, "huggingface_hub", types.SimpleNamespace(hf_hub_download=lambda repo, file: "granite.gguf"))
    tokenizers = types.SimpleNamespace(from_pretrained=lambda name: FakeGuardianTokenizer())
    monkeypatch.setitem(sys.modules, "transformers", types.SimpleNamespace(AutoTokenizer=tokenizers))
    return model
