from fastapi.testclient import TestClient

from upheld import api


def client(monkeypatch, **env: str) -> TestClient:
    monkeypatch.setenv("UPHELD_VERIFIER", "lexical")
    monkeypatch.setenv("UPHELD_RETRIEVAL", "bm25")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return TestClient(api.app)


def test_health_and_audit(monkeypatch):
    with client(monkeypatch, UPHELD_MAX_CONCURRENT="1") as c:
        assert c.get("/health").json() == {"status": "ok", "verifier": "lexical@0.7", "retrieval": "bm25"}
        res = c.post(
            "/audit",
            json={
                "answer": "The Eiffel Tower is 330 metres tall [1]. It was completed in 1925 [1].",
                "sources": [{"id": "1", "text": "The Eiffel Tower in Paris is 330 metres tall and was completed in 1889."}],
            },
        )
        assert res.status_code == 200
        assert [c["verdict"] for c in res.json()["claims"]] == ["supported", "unsupported"]


def test_rejects_oversized_answer(monkeypatch):
    with client(monkeypatch) as c:
        assert c.post("/audit", json={"answer": "x" * 50_001}).status_code == 422


def test_serves_built_site(monkeypatch):
    if not api.SITE_DIR.is_dir():
        return  # web/dist isn't built in this checkout
    with client(monkeypatch) as c:
        assert "<div id=\"root\">" in c.get("/").text
        assert c.get("/app/").status_code == 200
