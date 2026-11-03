import asyncio
import os
from contextlib import asynccontextmanager, nullcontext
from importlib.metadata import version
from pathlib import Path
from typing import Annotated, Any

from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from upheld.auditor import to_request
from upheld.evidence import make_embedder, retrieval_name
from upheld.models import AuditReport, AuditRequest
from upheld.pipeline import run_audit
from upheld.providers import Provider
from upheld.verify import make_verifier

_state: dict = {}

# The built website (web/dist). Served at / when present, so `upheld serve` hosts the
# landing page and the playground next to the API.
SITE_DIR = Path(os.environ.get("UPHELD_SITE_DIR", Path(__file__).resolve().parents[2] / "web" / "dist"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load the models once at startup, not per request.
    _state["verifier"] = make_verifier(os.environ.get("UPHELD_VERIFIER", "ensemble"))
    _state["embedder"] = make_embedder(os.environ.get("UPHELD_RETRIEVAL", "auto"))
    # A public deployment can cap concurrent audits so requests queue instead of
    # competing for one model on a small machine.
    limit = int(os.environ.get("UPHELD_MAX_CONCURRENT", "0"))
    _state["slots"] = asyncio.Semaphore(limit) if limit > 0 else None
    yield
    _state.clear()


app = FastAPI(title="upheld", version=version("upheld"), lifespan=lifespan)

# Origins allowed to call the API from a browser, comma-separated, e.g. a static
# deploy of the website on another domain.
if origins := [o.strip() for o in os.environ.get("UPHELD_CORS_ORIGINS", "").split(",") if o.strip()]:
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"], allow_headers=["Content-Type"])


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "verifier": _state["verifier"].name, "retrieval": retrieval_name(_state["embedder"])}


@app.post("/audit")
async def audit(req: AuditRequest) -> AuditReport:
    async with _state["slots"] or nullcontext():
        return await run_audit(req, _state["verifier"], embedder=_state["embedder"])


@app.post("/audit/{provider}")
async def audit_response(provider: Provider, response: Annotated[dict[str, Any], Body()], question: str | None = None) -> AuditReport:
    """Audit a provider's API response as it came back. auto tells the provider from the response's shape."""
    try:
        req = to_request(response, question=question, provider=provider)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return await audit(req)


if SITE_DIR.is_dir():
    app.mount("/", StaticFiles(directory=SITE_DIR, html=True), name="site")
