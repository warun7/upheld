import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from upheld.audit import run_audit
from upheld.evidence import make_embedder, retrieval_name
from upheld.models import AuditReport, AuditRequest
from upheld.verify import make_verifier

_state: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load the models once at startup, not per request.
    _state["verifier"] = make_verifier(os.environ.get("UPHELD_VERIFIER", "ensemble"))
    _state["embedder"] = make_embedder(os.environ.get("UPHELD_RETRIEVAL", "auto"))
    yield
    _state.clear()


app = FastAPI(title="upheld", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "verifier": _state["verifier"].name, "retrieval": retrieval_name(_state["embedder"])}


@app.post("/audit")
async def audit(req: AuditRequest) -> AuditReport:
    return await run_audit(req, _state["verifier"], embedder=_state["embedder"])
