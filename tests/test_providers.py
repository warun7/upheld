import asyncio
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

import upheld
from upheld import pipeline
from upheld.auditor import to_request
from upheld.cli import app
from upheld.models import LinkStatus, Verdict
from upheld.providers import Provider, _snake_keys, detect, from_response
from upheld.sources import FetchedSource

FIXTURES = Path(__file__).parent / "fixtures"
KEY = "https://www.toureiffel.paris/en/the-monument/key-figures"
WIKI = "https://en.wikipedia.org/wiki/Eiffel_Tower"
PAGES = {
    KEY: "The Eiffel Tower is 330 metres tall with its antennas, and weighs 10,100 tonnes in all.",
    WIKI: "The Eiffel Tower was completed in 1889 as the entrance to the 1889 World's Fair. It is named after the engineer Gustave Eiffel.",
}


def load(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text())


def claims(req) -> list[tuple[str, list[str]]]:
    """Each claim's text and the sources it cites, as an audit splits them (nothing fetched)."""
    report = upheld.audit(req, verifier="lexical", retrieval="bm25", fetch=False)
    return [(c.text, c.cited) for c in report.claims]


def spans(req) -> list[tuple[str, list[str]]]:
    return [(req.answer[s.start : s.end], s.cited) for s in req.cited_spans]


def test_openai_links_become_markers():
    req = upheld.from_openai(load("openai"))
    # Without OpenAI's utm_source tag, so the Wayback Machine can find the page.
    assert [(s.id, s.url, s.title) for s in req.sources] == [("1", KEY, "Key figures - Eiffel Tower"), ("2", WIKI, "Eiffel Tower - Wikipedia")]
    # OpenAI's ranges cover the link written after a claim, not the claim, so the answer is split into sentences.
    assert req.cited_spans == []
    assert req.answer.startswith("The Eiffel Tower is 330 metres tall, including its antennas. [1] It was completed")
    assert claims(req) == [
        ("The Eiffel Tower is 330 metres tall, including its antennas.", ["1"]),
        ("It was completed in 1889 as the entrance arch to the World's Fair.", ["2"]),
        ("The tower is repainted every seven years, using about 60 tonnes of paint.", ["1"]),
        ("Tickets can be bought online or at the tower itself.", []),
    ]


def test_openai_chat_completions_and_offsets_counted_in_bytes():
    url = "https://www.insee.fr/en/statistiques/2011101"
    text = f"Café prices in Paris rose 4% in 2026. ([insee.fr]({url}))"
    start = len(text[: text.index("([")].encode())  # one too many for the é
    annotation = {"type": "url_citation", "url_citation": {"start_index": start, "end_index": len(text.encode()), "url": url, "title": "Prices"}}
    response = {"object": "chat.completion", "model": "gpt-6-luna-search", "choices": [{"index": 0, "message": {"role": "assistant", "content": text, "annotations": [annotation]}}]}
    assert detect(response) == Provider.OPENAI
    req = from_response(response)
    assert req.answer == "Café prices in Paris rose 4% in 2026. [1]"
    assert [(s.id, s.url) for s in req.sources] == [("1", url)]


def test_anthropic_cited_blocks_are_claims():
    req = upheld.from_anthropic(load("anthropic"))
    # Claude's narration of its searches comes before the answer and is left out.
    assert req.answer.startswith("Based on the search results, the Eiffel Tower")
    assert [(s.id, s.url) for s in req.sources] == [("1", KEY), ("2", WIKI)]
    assert spans(req) == [
        ("the Eiffel Tower is 330 metres tall", ["1"]),
        ("it was completed in 1889 as the entrance to the World's Fair", ["2"]),
        ("Gustave Eiffel's company", ["2"]),
    ]
    assert claims(req) == [
        ("the Eiffel Tower is 330 metres tall", ["1"]),
        ("it was completed in 1889 as the entrance to the World's Fair", ["2"]),
        ("It is the most visited paid monument in the world.", []),
        # Too short to check on its own, so the sentence it is in is checked.
        ("Its design is credited to Gustave Eiffel's company.", ["2"]),
    ]


def test_perplexity_markers_number_its_search_results():
    req = upheld.from_perplexity(load("perplexity"))
    # The fourth search result is never cited, so it isn't fetched.
    assert [(s.id, s.url) for s in req.sources] == [("1", KEY), ("2", WIKI), ("3", "https://en.wikipedia.org/wiki/Exposition_Universelle_(1889)")]
    assert req.sources[0].title == "Key figures - Eiffel Tower"
    assert claims(req) == [
        ("The Eiffel Tower is 330 metres tall, including its antennas.", ["1", "2"]),
        ("It was completed in 1889 for the Exposition Universelle.", ["2", "3"]),
        ("The tower is repainted every seven years.", ["1"]),
        ("It is one of the most visited monuments in the world.", []),
    ]


def test_perplexity_agent_api_web_markers():
    response = {
        "object": "response",
        "model": "openai/gpt-6-luna",
        "status": "completed",
        "output": [
            {"type": "search_results", "queries": ["eiffel tower"], "results": [
                {"id": 1, "title": "Eiffel Tower - Wikipedia", "url": WIKI, "date": "2026-10-30", "source": "web"},
                {"id": 2, "title": "Key figures", "url": KEY, "date": "2026-03-02", "source": "web"},
            ]},
            {"type": "message", "role": "assistant", "status": "completed", "content": [
                {"type": "output_text", "text": "The Eiffel Tower is 330 metres tall.[web:2] It was completed in 1889.[web:1][file:1]", "annotations": []},
            ]},
        ],
    }
    assert detect(response) == Provider.PERPLEXITY
    req = from_response(response)
    assert req.answer == "The Eiffel Tower is 330 metres tall.[2] It was completed in 1889.[1]"
    assert [(s.id, s.url) for s in req.sources] == [("1", WIKI), ("2", KEY)]


def test_perplexity_through_openrouter():
    # OpenRouter passes Sonar's search results on as url_citation annotations, in order, without ranges.
    message = {"role": "assistant", "content": "The Eiffel Tower is 330 metres tall[2].", "annotations": [
        {"type": "url_citation", "url_citation": {"url": WIKI, "title": "Wikipedia", "start_index": 0, "end_index": 0}},
        {"type": "url_citation", "url_citation": {"url": KEY, "title": "Key figures", "start_index": 0, "end_index": 0}},
    ]}
    response = {"object": "chat.completion", "model": "perplexity/sonar-pro", "provider": "Perplexity", "choices": [{"message": message}]}
    assert detect(response) == Provider.PERPLEXITY
    assert [(s.id, s.url) for s in from_response(response).sources] == [("2", KEY)]


def test_gemini_byte_ranges_become_character_spans():
    req = upheld.from_gemini(load("gemini"))
    assert spans(req) == [
        ("The Eiffel Tower stands 330 metres tall on the Champ de Mars in Paris.", ["1", "3"]),
        ("It was designed by Gustave Eiffel’s engineering company and completed in 1889 for the Exposition Universelle.", ["2"]),
        ("is now a global icon of France", ["3"]),
    ]
    assert [(s.id, s.title) for s in req.sources] == [("1", "toureiffel.paris"), ("2", "wikipedia.org"), ("3", "britannica.com")]
    assert all(s.url.startswith("https://vertexaisearch.cloud.google.com/grounding-api-redirect/") for s in req.sources)


def test_gemini_sdk_object():
    class GenerateContentResponse:  # google-genai's response: a pydantic model whose fields are snake_case
        def model_dump(self, mode: str) -> dict:
            return _snake_keys(load("gemini"))

    req = upheld.from_gemini(GenerateContentResponse())
    assert spans(req) == spans(upheld.from_gemini(load("gemini")))


def test_gemini_interactions_api():
    text = "The Eiffel Tower is 330 metres tall. It was completed in 1889."
    response = {
        "id": "v1_ChdpbnRlcmFjdGlvbg",
        "steps": [
            {"type": "google_search_call", "arguments": {"queries": ["eiffel tower height"]}},
            {"type": "google_search_result", "call_id": "search_001", "result": [{"search_suggestions": "<div></div>"}]},
            {"type": "model_output", "content": [{"type": "text", "text": text, "annotations": [
                {"type": "url_citation", "url": KEY, "title": "toureiffel.paris", "start_index": 0, "end_index": 36},
                {"type": "url_citation", "url": WIKI, "title": "wikipedia.org", "start_index": 37, "end_index": 62},
            ]}]},
        ],
    }
    req = from_response(response)
    assert spans(req) == [("The Eiffel Tower is 330 metres tall.", ["1"]), ("It was completed in 1889.", ["2"])]


def test_unknown_shapes_and_empty_answers_are_refused():
    with pytest.raises(ValueError, match="can't tell which provider"):
        from_response({"text": "hello"})
    with pytest.raises(ValueError, match="no answer text"):
        upheld.from_openai({"output": [{"type": "web_search_call", "status": "completed"}]})
    with pytest.raises(ValueError, match="sources go with an answer's text"):
        to_request(load("openai"), ["https://example.com"])


def fake_fetch(monkeypatch):
    async def fetch_all(sources, allow_private=False):
        return {s.id: FetchedSource(s, LinkStatus.LIVE, PAGES[s.url]) if s.url in PAGES else FetchedSource(s, LinkStatus.UNREACHABLE) for s in sources}

    monkeypatch.setattr(pipeline, "fetch_all", fetch_all)


def test_audit_a_provider_response(monkeypatch):
    fake_fetch(monkeypatch)
    report = upheld.audit(load("anthropic"), question="How tall is the Eiffel Tower?", verifier="lexical", retrieval="bm25")
    assert [c.verdict for c in report.claims] == [Verdict.SUPPORTED, Verdict.SUPPORTED, Verdict.UNCITED, Verdict.UNSUPPORTED]
    assert [(s.id, s.status) for s in report.sources] == [("1", LinkStatus.LIVE), ("2", LinkStatus.LIVE)]


def test_audit_text_with_sources_and_reuse_an_auditor():
    answer = "The Eiffel Tower is 330 metres tall [1]. It was completed in 1925 [2]."
    report = upheld.audit(answer, [PAGES[KEY], {"text": PAGES[WIKI]}], verifier="lexical", retrieval="bm25")
    assert [c.verdict for c in report.claims] == [Verdict.SUPPORTED, Verdict.UNSUPPORTED]
    assert to_request("A claim [1].", ["https://example.com/a"]).sources[0].url == "https://example.com/a"

    auditor = upheld.Auditor("lexical", retrieval="bm25")

    async def from_a_running_loop():  # as in a notebook: audit blocks, audit_async awaits
        return auditor.audit(answer, [PAGES[KEY], PAGES[WIKI]]), await auditor.audit_async(answer, [PAGES[KEY], PAGES[WIKI]])

    blocking, awaited = asyncio.run(from_a_running_loop())
    assert blocking == awaited == report


def test_cli_reads_a_provider_response():
    result = CliRunner().invoke(
        app, ["audit", str(FIXTURES / "perplexity.json"), "--from", "perplexity", "--verifier", "lexical", "--retrieval", "bm25", "--no-fetch", "--json"]
    )
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert [c["cited"] for c in report["claims"]] == [["1", "2"], ["2", "3"], ["1"], []]

    result = CliRunner().invoke(app, ["audit", str(FIXTURES / "perplexity.json"), "--from", "anthropic", "--no-fetch"])
    assert result.exit_code == 2 and "not an Anthropic message" in result.output
