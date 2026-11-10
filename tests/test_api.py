import asyncio
import json
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from upheld import api, pipeline
from upheld.models import LinkStatus
from upheld.sources import FetchedSource


def client(monkeypatch, **env: str) -> TestClient:
    monkeypatch.setenv("UPHELD_VERIFIER", "lexical")
    monkeypatch.setenv("UPHELD_RETRIEVAL", "bm25")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return TestClient(api.app)


def test_health_and_audit(monkeypatch):
    with client(monkeypatch, UPHELD_MAX_CONCURRENT="1") as c:
        assert c.get("/health").json() == {"status": "ok", "verifier": "lexical@0.56", "retrieval": "bm25"}
        res = c.post(
            "/audit",
            json={
                "answer": "The Eiffel Tower is 330 metres tall [1]. It was completed in 1925 [1].",
                "sources": [{"id": "1", "text": "The Eiffel Tower in Paris is 330 metres tall and was completed in 1889."}],
            },
        )
        assert res.status_code == 200
        assert [c["verdict"] for c in res.json()["claims"]] == ["supported", "unsupported"]


def test_overlapping_audits_take_turns_with_the_judge(monkeypatch, fake_llama):
    # With no UPHELD_MAX_CONCURRENT, two audits at once used to decode on one llama.cpp model from two
    # threads: one got a 500, and three crashed the server.
    monkeypatch.setenv("UPHELD_VERIFIER", "judge")
    monkeypatch.setenv("UPHELD_RETRIEVAL", "bm25")
    monkeypatch.delenv("UPHELD_MAX_CONCURRENT", raising=False)
    request = {
        "answer": "The Eiffel Tower is 330 metres tall [1]. It was completed in 1889 [1].",
        "sources": [{"id": "1", "text": "The Eiffel Tower in Paris is 330 metres tall and was completed in 1889."}],
    }

    async def two_at_once() -> list[httpx.Response]:
        async with api.lifespan(api.app):
            transport = httpx.ASGITransport(app=api.app, raise_app_exceptions=False)
            async with httpx.AsyncClient(transport=transport, base_url="http://upheld") as c:
                return await asyncio.gather(c.post("/audit", json=request), c.post("/audit", json=request))

    responses = asyncio.run(two_at_once())
    assert [r.status_code for r in responses] == [200, 200]
    for r in responses:
        assert r.json()["verifier"].startswith("judge:")
        assert [c["verdict"] for c in r.json()["claims"]] == ["supported", "supported"]
    decodes = sorted(fake_llama.decodes)
    assert len(decodes) == 4  # two claims from each audit
    assert all(end <= next_start for (_, end, _), (next_start, _, _) in zip(decodes, decodes[1:]))


def test_rejects_oversized_answer(monkeypatch):
    with client(monkeypatch) as c:
        assert c.post("/audit", json={"answer": "x" * 50_001}).status_code == 422


def test_serves_built_site(monkeypatch):
    if not api.SITE_DIR.is_dir():
        return  # web/dist isn't built in this checkout
    with client(monkeypatch) as c:
        assert "<div id=\"root\">" in c.get("/").text
        assert c.get("/docs/").status_code == 200
        # The playground is gone: the site is static and has no /app/.
        assert c.get("/app/").status_code == 404


def test_audits_a_provider_response(monkeypatch):
    async def fetch_all(sources, allow_private=False):
        return {s.id: FetchedSource(s, LinkStatus.UNREACHABLE, note="not fetched in tests") for s in sources}

    monkeypatch.setattr(pipeline, "fetch_all", fetch_all)
    gemini = json.loads((Path(__file__).parent / "fixtures" / "gemini.json").read_text())
    with client(monkeypatch) as c:
        res = c.post("/audit/auto", params={"question": "Tell me about the Eiffel Tower"}, json=gemini)
        assert res.status_code == 200
        assert [claim["cited"] for claim in res.json()["claims"]] == [["1", "3"], ["2"], ["3"]]
        assert c.post("/audit/openai", json=gemini).status_code == 422
        assert c.post("/audit/auto", json={"answer": "The Eiffel Tower is 330 metres tall."}).status_code == 200
