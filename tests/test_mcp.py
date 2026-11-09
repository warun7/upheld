import asyncio
import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("mcp")

from mcp import Client, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

from upheld import mcp_server, pipeline  # noqa: E402
from upheld.mcp_server import excerpt, make_server  # noqa: E402
from upheld.models import LinkStatus  # noqa: E402
from upheld.sources import FetchedSource  # noqa: E402

EIFFEL = "The Eiffel Tower in Paris is 330 metres tall and was completed in 1889. It was designed by the engineering firm of Gustave Eiffel."
ANSWER = (
    "The Eiffel Tower is 330 metres tall [1]. It was completed in 1925 [1]. Its lift system was designed by Otis [2]. "
    "Gustave Eiffel was born in Dijon in 1832."
)


def server(**kwargs):
    return make_server("lexical", retrieval="bm25", **kwargs)


async def calls(srv, *requests, **kwargs):
    async with Client(srv) as client:
        return [await client.call_tool(tool, args, **kwargs) for tool, args in requests]


def call(srv, tool, args, **kwargs):
    [result] = asyncio.run(calls(srv, (tool, args), **kwargs))
    return result


def unreachable(monkeypatch, seen=None):
    async def fetch_all(sources, allow_private=False):
        if seen is not None:
            seen.append(allow_private)
        return {s.id: FetchedSource(s, LinkStatus.UNREACHABLE, note="not fetched in tests") for s in sources}

    monkeypatch.setattr(pipeline, "fetch_all", fetch_all)


def test_lists_two_read_only_tools():
    async def tools():
        async with Client(server()) as client:
            return (await client.list_tools()).tools

    listed = {t.name: t for t in asyncio.run(tools())}
    assert set(listed) == {"audit_citations", "check_claim"}
    for tool in listed.values():
        assert tool.annotations.read_only_hint and tool.description


def test_audit_citations_reports_what_isnt_supported():
    result = call(server(), "audit_citations", {"answer": ANSWER, "sources": [{"id": "1", "text": EIFFEL}]})
    assert not result.is_error
    out = result.structured_content
    assert out["summary"] == "1 of 3 cited claims supported, 1 uncited"
    assert out["verdicts"] == {"supported": 1, "unsupported": 1, "source_missing": 1, "uncited": 1}
    assert out["verifier"] == "lexical@0.56" and out["retrieval"] == "bm25"
    unsupported, missing, uncited = out["problems"]
    assert unsupported["claim"] == "It was completed in 1925."
    [citation] = unsupported["citations"]
    assert citation["source"] == "1" and citation["verdict"] == "unsupported"
    assert citation["flagged"] == ["1925"] and "1889" in citation["closest_passage"]
    assert missing["citations"] == [{"source": "2", "verdict": "source_missing", "note": "no source listed for [2]"}]
    assert uncited == {"claim": "Gustave Eiffel was born in Dijon in 1832.", "verdict": "uncited"}
    assert "report" not in out
    assert json.loads(result.content[0].text) == out


def test_audit_citations_full_report():
    out = call(server(), "audit_citations", {"answer": ANSWER, "sources": [EIFFEL], "full_report": True}).structured_content
    assert [c["verdict"] for c in out["report"]["claims"]] == ["supported", "unsupported", "source_missing", "uncited"]
    assert out["report"]["sources"][0]["status"] == "provided"


def test_sources_take_ids_by_position_or_as_numbers():
    answer = "The Eiffel Tower is 330 metres tall [1]. It was completed in 1889 [2]."
    out = call(server(), "audit_citations", {"answer": answer, "sources": ["Unrelated text.", {"id": 2, "text": EIFFEL}]}).structured_content
    assert out["verdicts"] == {"misattributed": 1, "supported": 1}  # [2] backs the claim cited to [1]
    assert out["problems"][0]["citations"][0]["source"] == "1"
    assert out["problems"][0]["supported_by"][0]["source"] == "2"


def test_audit_citations_reads_a_provider_response(monkeypatch):
    unreachable(monkeypatch)
    gemini = json.loads((Path(__file__).parent / "fixtures" / "gemini.json").read_text())
    for response in (gemini, json.dumps(gemini)):
        out = call(server(), "audit_citations", {"response": response, "question": "Tell me about the Eiffel Tower"}).structured_content
        assert out["verdicts"] == {"unverifiable": 3}
        assert all(p["citations"][0]["note"] == "not fetched in tests" for p in out["problems"])


@pytest.mark.parametrize(
    "args, message",
    [
        ({}, "give either answer"),
        ({"answer": "x [1].", "response": {"answer": "x"}}, "give either answer"),
        ({"response": "{not json"}, "Expecting property name"),
        ({"response": {"output": []}, "provider": "openai"}, "no answer text in this openai response"),
        ({"response": {"answer": "x [1]."}, "sources": ["text"]}, "sources go with an answer's text"),
        ({"answer": "x" * 50_001}, "at most 50000 characters"),
    ],
)
def test_audit_citations_rejects_bad_input(args, message):
    result = call(server(), "audit_citations", args)
    assert result.is_error and message in result.content[0].text


def test_check_claim():
    srv = server()
    supported, unsupported = asyncio.run(
        calls(
            srv,
            ("check_claim", {"claim": "The Eiffel Tower was completed in 1889.", "text": EIFFEL}),
            ("check_claim", {"claim": "The Eiffel Tower was completed in 1925. It is 330 metres tall.", "text": EIFFEL}),
        )
    )
    assert supported.structured_content == {
        "verdict": "supported",
        "score": 1.0,
        "closest_passage": EIFFEL,
        "verifier": "lexical@0.56",
    }
    # Both sentences are checked as one claim.
    assert unsupported.structured_content["verdict"] == "unsupported"
    assert unsupported.structured_content["flagged"] == ["1925"]
    assert call(srv, "check_claim", {"claim": "The tower is tall."}).is_error


def test_private_addresses_stay_blocked():
    out = call(server(), "check_claim", {"claim": "The admin page lists every user.", "url": "http://127.0.0.1:9/admin"}).structured_content
    assert out["verdict"] == "unverifiable" and "non-public address" in out["note"]
    assert out["url"] == "http://127.0.0.1:9/admin"


def test_allow_private_reaches_the_fetch(monkeypatch):
    seen: list[bool] = []
    unreachable(monkeypatch, seen)
    call(server(), "check_claim", {"claim": "The admin page lists every user.", "url": "http://127.0.0.1:9/admin"})
    call(server(allow_private=True), "check_claim", {"claim": "The admin page lists every user.", "url": "http://127.0.0.1:9/admin"})
    assert seen == [False, True]


def test_reports_progress():
    updates = []

    async def progress(value, total, message):
        updates.append(message)

    call(server(), "check_claim", {"claim": "The Eiffel Tower was completed in 1889.", "text": EIFFEL}, progress_callback=progress)
    assert updates and updates[0].startswith("loading the lexical models")


def test_time_budget(monkeypatch):
    async def slow(sources, allow_private=False):
        await asyncio.sleep(1)
        return {}

    monkeypatch.setattr(pipeline, "fetch_all", slow)
    result = call(server(timeout=0.2), "check_claim", {"claim": "The Eiffel Tower was completed in 1889.", "url": "https://example.com"})
    assert result.is_error and "stopped after 0 s" in result.content[0].text


def test_loads_the_models_once_and_retries_a_failed_load(monkeypatch):
    built = []

    class Auditor(mcp_server.Auditor):
        def __init__(self, verifier, **kwargs):
            built.append(verifier)
            if len(built) == 1:
                raise ImportError('MiniCheckVerifier needs the optional extra: pip install "upheld[minicheck]"')
            super().__init__("lexical", retrieval="bm25")

    monkeypatch.setattr(mcp_server, "Auditor", Auditor)
    monkeypatch.setattr(mcp_server, "default_verifier", lambda: "ensemble")  # what auto means without the judge
    args = {"claim": "The Eiffel Tower was completed in 1889.", "text": EIFFEL}
    failed, first, second = asyncio.run(calls(make_server(), ("check_claim", args), ("check_claim", args), ("check_claim", args)))
    assert failed.is_error
    assert 'uvx --from "upheld[models,mcp]" upheld mcp' in failed.content[0].text
    assert "--verifier lexical --retrieval bm25" in failed.content[0].text
    assert first.structured_content["verdict"] == second.structured_content["verdict"] == "supported"
    assert built == ["auto", "auto"]


def test_excerpt_keeps_the_closest_sentences():
    filler = " ".join(f"Sentence {n} is about something else entirely." for n in range(20))
    passage = f"{filler} The tower was completed in 1889 for the World's Fair. {filler}"
    text = excerpt(passage, "The tower was completed in 1889.", limit=200)
    assert "completed in 1889" in text
    assert text.startswith("…") and text.endswith("…") and len(text) <= 202
    assert excerpt("Short passage.", "anything") == "Short passage."


# A stray print() during an audit, as a model library might make, mustn't reach the protocol stream.
STDIO_SERVER = """
from upheld import auditor
from upheld.cli import app

real = auditor.run_audit

async def noisy(*args, **kwargs):
    print("stray print")
    return await real(*args, **kwargs)

auditor.run_audit = noisy
app()
"""


def test_runs_over_stdio(tmp_path):
    params = StdioServerParameters(
        command=sys.executable, args=["-c", STDIO_SERVER, "mcp", "--verifier", "lexical", "--retrieval", "bm25"]
    )

    async def run(errlog):
        async with Client(stdio_client(params, errlog=errlog)) as client:
            tools = (await client.list_tools()).tools
            result = await client.call_tool("audit_citations", {"answer": ANSWER, "sources": [EIFFEL]})
            return tools, result

    with open(tmp_path / "stderr.log", "w") as errlog:
        tools, result = asyncio.run(run(errlog))
    assert {t.name for t in tools} == {"audit_citations", "check_claim"}
    assert result.structured_content["summary"] == "1 of 3 cited claims supported, 1 uncited"
    stderr = (tmp_path / "stderr.log").read_text()
    assert "stray print" in stderr and "upheld.mcp INFO audited 4 claims" in stderr
