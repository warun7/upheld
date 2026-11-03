"""Audit from Python in one call: an answer with its sources, or a provider's whole response."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from typing import Any, Coroutine, TypeVar

from upheld.evidence import make_embedder
from upheld.models import AuditReport, AuditRequest, Source
from upheld.pipeline import run_audit
from upheld.providers import Provider, from_response
from upheld.verify import Verifier, make_verifier

T = TypeVar("T")

SourcesArg = list[Source | dict | str] | None


class Auditor:
    """A verifier and retrieval model, loaded once and reused for every audit.

    The default ensemble takes a few seconds and about 4 GB of memory to load,
    so make one Auditor and keep it. `audit` blocks; `audit_async` is for code
    that already runs an event loop, such as a web server.
    """

    def __init__(
        self,
        verifier: str | Verifier = "ensemble",
        *,
        threshold: float | None = None,
        retrieval: str = "auto",
        device: str | None = None,
    ):
        self.verifier = make_verifier(verifier, threshold, device) if isinstance(verifier, str) else verifier
        self.embedder = make_embedder(retrieval)

    def audit(
        self,
        answer: Any,
        sources: SourcesArg = None,
        *,
        question: str | None = None,
        provider: Provider | str = Provider.AUTO,
        fetch: bool = True,
        allow_private: bool = False,
    ) -> AuditReport:
        return _run(self.audit_async(answer, sources, question=question, provider=provider, fetch=fetch, allow_private=allow_private))

    async def audit_async(
        self,
        answer: Any,
        sources: SourcesArg = None,
        *,
        question: str | None = None,
        provider: Provider | str = Provider.AUTO,
        fetch: bool = True,
        allow_private: bool = False,
    ) -> AuditReport:
        req = to_request(answer, sources, question=question, provider=provider)
        return await run_audit(req, self.verifier, embedder=self.embedder, fetch=fetch, allow_private=allow_private)


def audit(
    answer: Any,
    sources: SourcesArg = None,
    *,
    question: str | None = None,
    verifier: str = "ensemble",
    threshold: float | None = None,
    retrieval: str = "auto",
    provider: Provider | str = Provider.AUTO,
    fetch: bool = True,
    allow_private: bool = False,
) -> AuditReport:
    """Audit one answer and return its report.

    `answer` is the answer's text with [1]-style markers or inline links, an
    AuditRequest, or a provider's response (see upheld.providers). `sources`
    go with text: each a Source, a dict, or a string, which is a URL if it
    starts with http:// or https:// and the source's text otherwise, numbered
    from 1. The models load on the first call and stay loaded for the next
    call with the same verifier, threshold and retrieval.
    """
    auditor = _auditor(verifier, threshold, retrieval)
    return auditor.audit(answer, sources, question=question, provider=provider, fetch=fetch, allow_private=allow_private)


@lru_cache(maxsize=1)
def _auditor(verifier: str, threshold: float | None, retrieval: str) -> Auditor:
    return Auditor(verifier, threshold=threshold, retrieval=retrieval)


def to_request(answer: Any, sources: SourcesArg = None, *, question: str | None = None, provider: Provider | str = Provider.AUTO) -> AuditRequest:
    """Turn what `audit` accepts into an AuditRequest."""
    if isinstance(answer, str):
        return AuditRequest(answer=answer, question=question, sources=[_source(s, n) for n, s in enumerate(sources or [], 1)])
    if sources:
        raise ValueError("sources go with an answer's text; a request or a provider response carries its own")
    if isinstance(answer, AuditRequest):
        answer = answer.model_dump()
    if isinstance(answer, dict) and "answer" in answer and provider == Provider.AUTO:
        return AuditRequest.model_validate({**answer, "question": question} if question else answer)
    return from_response(answer, provider, question=question)


def _source(source: Source | dict | str, n: int) -> Source:
    if isinstance(source, Source):
        return source
    if isinstance(source, dict):
        return Source.model_validate({"id": str(n), **source})
    if source.startswith(("http://", "https://")):
        return Source(id=str(n), url=source)
    return Source(id=str(n), text=source)


def _run(coro: Coroutine[Any, Any, T]) -> T:
    """Run a coroutine to completion, also from inside a running event loop (a Jupyter notebook, say)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()
