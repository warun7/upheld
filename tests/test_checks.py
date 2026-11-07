import numpy as np
import pytest

from upheld.entities import missing_entities, named_entities
from upheld.evidence import SourceIndex, chunk, rrf
from upheld.sources import BlockedURL, check_url_allowed
from upheld.verify import LexicalVerifier, _locate_tokens, _word_chunks, make_verifier


def test_named_entities():
    assert named_entities("In the STEP 1 trial, Ozempic cut weight by 15% at Novo Nordisk sites.") == [
        "STEP 1",
        "Ozempic",
        "Novo Nordisk",
    ]
    # A lone ordinary word at sentence start is not an entity; a name-like one is.
    assert named_entities("Researchers found a large effect.") == []
    assert named_entities("GPT-4o scored highest on the benchmark.") == ["GPT-4o"]
    assert named_entities("Ozempic reduced weight in adults.") == ["Ozempic"]


def test_named_entities_strip_quotes_possessives_and_bullets():
    assert named_entities("Without Charles II's return, Parliament ruled.") == ["Charles II", "Parliament"]
    assert named_entities("Cliff Richard sang 'Suddenly' in Xanadu.") == ["Cliff Richard", "Suddenly", "Xanadu"]
    # A bullet or opening quote doesn't stop the first word counting as sentence-initial.
    assert named_entities("• Be honest with the other person.") == []
    assert named_entities("'What's in a name?' asked Juliet.") == ["Juliet"]


def test_missing_entities_catches_wrong_drug():
    source = "Tirzepatide reduced body weight by 20.9% over 72 weeks in the SURMOUNT-1 trial."
    assert missing_entities("In a 72-week trial, Ozempic reduced body weight by 20.9%.", source) == ["Ozempic"]
    assert missing_entities("In a 72-week trial, Tirzepatide reduced body weight by 20.9%.", source) == []


FILLER = " ".join(f"Unrelated sentence number {i} about gardening." for i in range(60))


class ConceptEmbedder:
    """Stand-in for an embedding model: texts mentioning the same concept get the same direction."""

    name = "concepts"
    CONCEPTS = [("dismantl", "demolish", "temporary", "20 years"), ("garden",)]

    def embed(self, texts, *, query=False):
        vectors = np.array([[0.1] + [float(any(w in t.lower() for w in words)) for words in self.CONCEPTS] for t in texts])
        return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)


def test_bm25_finds_the_relevant_window():
    text = FILLER + " The Eiffel Tower is 330 metres tall. " + FILLER
    assert len(chunk(text)) > 3
    best, score = SourceIndex(text).search("How tall is the Eiffel Tower", k=3)[0]
    assert "330 metres" in best and score == 1.0


def test_hybrid_finds_a_paraphrase_bm25_misses():
    target = "The structure was slated for dismantling in 1909."
    text = FILLER + " " + target + " " + FILLER
    claim = "It was only ever meant to be temporary."
    assert not any(target in p for p, _ in SourceIndex(text).search(claim, k=3))
    assert any(target in p for p, _ in SourceIndex(text, ConceptEmbedder()).search(claim, k=3))


def test_rrf_rewards_items_ranked_well_by_either_list():
    fused = [item for item, _ in rrf([[1, 2, 3], [3, 4, 1]])]
    assert fused[:2] == [1, 3]  # in both lists
    assert set(fused) == {1, 2, 3, 4}


def test_lexical_verifier_requires_numbers_to_match():
    v = LexicalVerifier()
    evidence = ["The trial enrolled 1,961 adults and ran for 68 weeks."]
    answer = "The trial enrolled 1961 adults. The trial enrolled 2,500 adults."
    ok, bad = v.check(answer, [(0, 31), (32, 64)], evidence)
    assert ok.score >= v.threshold
    assert bad.score == 0.0 and bad.spans[0].text == "2,500" and bad.spans[0].start == 19


def test_locate_tokens_maps_decoded_tokens_to_offsets():
    text = "Ozempic cut weight by 15%."
    assert _locate_tokens(text, ["Oz", "emp", "ic", " cut", " weight", " by", " 15", "%", "."]) == [
        (0, 2), (2, 5), (5, 7), (8, 11), (12, 18), (19, 21), (22, 24), (24, 25), (25, 26)
    ]
    assert _locate_tokens(text, ["Oz", "<unk>", "emp"])[1] is None


@pytest.mark.parametrize(
    "url",
    ["http://localhost:8000/x", "http://127.0.0.1/", "http://169.254.169.254/latest/meta-data", "file:///etc/passwd", "ftp://example.com"],
)
def test_ssrf_guard_blocks_local_and_non_http(url):
    with pytest.raises(BlockedURL):
        check_url_allowed(url)


def test_ssrf_guard_can_be_disabled_for_local_use():
    check_url_allowed("http://localhost:8000/x", allow_private=True)


def test_word_chunks_keep_sentences_whole():
    passages = ["One two three. Four five six.", "Seven eight nine ten."]
    assert _word_chunks(passages, 6) == ["One two three. Four five six.", "Seven eight nine ten."]
    assert _word_chunks(passages, 100) == ["One two three. Four five six. Seven eight nine ten."]
    assert _word_chunks([], 10) == [""]


def test_make_verifier_ignores_device_for_lexical():
    v = make_verifier("lexical", 0.6, device="mps")
    assert v.name == "lexical@0.6"
    with pytest.raises(ValueError):
        make_verifier("nope")


def test_auto_picks_the_judge_only_when_it_can_run_well(monkeypatch):
    import importlib.util
    import sys
    import types

    from upheld import verify

    fake = types.SimpleNamespace(llama_supports_gpu_offload=lambda: True)
    monkeypatch.setitem(sys.modules, "llama_cpp", fake)
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: object())
    monkeypatch.setattr(verify, "_memory_gib", lambda: 24.0)
    assert verify.default_verifier() == "judge"
    assert verify.default_verifier(device="cpu") == "ensemble"

    monkeypatch.setattr(verify, "_memory_gib", lambda: 8.0)
    assert verify.default_verifier() == "ensemble"

    monkeypatch.setattr(verify, "_memory_gib", lambda: 24.0)
    fake.llama_supports_gpu_offload = lambda: False
    assert verify.default_verifier() == "ensemble"

    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None if name == "llama_cpp" else object())
    assert verify.default_verifier() == "ensemble"
