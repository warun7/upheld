"""An MCP server, so AI agents can check the citations in an answer they've drafted before they show it.

`upheld mcp` runs it over stdio. The models load on the first call and stay
loaded, and audits run one at a time, since they share them.
"""

import asyncio
import json
import logging
import re
import time
from importlib.metadata import version
from typing import Annotated, Any, Literal

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field

from upheld.auditor import Auditor, to_request
from upheld.evidence import tokenize
from upheld.models import AuditReport, AuditRequest, CitationCheck, CitedSpan, ClaimResult, Source, SourceReport, Verdict
from upheld.verify import default_verifier

log = logging.getLogger("upheld.mcp")

PASSAGE_CHARS = 400  # of the closest passage, per citation
HEARTBEAT_SECONDS = 5.0

INSTRUCTIONS = """\
upheld checks whether the sources an answer cites actually say what the answer claims. Before you show the user an \
answer that cites web pages or documents, call audit_citations on it, then fix each claim it reports: reword it to \
match the source, cite a source that backs it, or drop it. While researching, check_claim tests one statement against \
one page. Each call fetches the cited pages and runs local models, so it takes seconds to a few minutes; the first \
call also loads the models."""

READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=True)


class SourceArg(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True)

    id: str | None = Field(default=None, description="What the answer cites it as: 1 for [1]. Defaults to its position in the list, from 1.")
    url: str | None = Field(default=None, description="Fetched, unless text is given.")
    title: str | None = None
    text: str | None = Field(default=None, description="The source's text, if you have it. It's used as is and nothing is fetched.")


class Checker:
    """Loads the auditor on the first call, then runs audits one at a time within a time budget."""

    def __init__(self, verifier: str, *, threshold: float | None, retrieval: str, timeout: float, allow_private: bool):
        self.verifier = verifier
        self.threshold = threshold
        self.retrieval = retrieval
        self.timeout = timeout
        self.allow_private = allow_private
        self._loading: asyncio.Future[Auditor] | None = None
        self._lock = asyncio.Lock()

    async def audit(self, req: AuditRequest, ctx: Context) -> AuditReport:
        start = time.monotonic()
        # Shielded, so an audit that runs out of time finishes in the background and holds the
        # lock until it does: the models it's using can't take a second audit at once.
        work = asyncio.ensure_future(self._audit(req))
        work.add_done_callback(_retrieve)
        beat = asyncio.ensure_future(self._heartbeat(ctx, start))
        try:
            async with asyncio.timeout(self.timeout):
                return await asyncio.shield(work)
        except TimeoutError:
            if self._loading is None or not self._loading.done():
                raise ToolError(
                    f"stopped after {self.timeout:.0f} s: the {self.verifier} models are still loading (the first run downloads "
                    "about 4 GB). They keep loading in the background, so try again in a minute or two."
                ) from None
            raise ToolError(
                f"stopped after {self.timeout:.0f} s. Slow or blocked pages take longest: try again with fewer sources, or give "
                "the sources' text instead of their URLs."
            ) from None
        finally:
            beat.cancel()

    async def _audit(self, req: AuditRequest) -> AuditReport:
        auditor = await self._auditor()
        async with self._lock:
            start = time.monotonic()
            report = await auditor.audit_async(req, allow_private=self.allow_private)
            log.info("audited %d claims against %d sources in %.1f s", len(report.claims), len(report.sources), time.monotonic() - start)
            return report

    async def _auditor(self) -> Auditor:
        if self._loading is None:
            log.info("loading the %s verifier with %s retrieval", self.verifier, self.retrieval)
            self._loading = asyncio.ensure_future(
                asyncio.to_thread(Auditor, self.verifier, threshold=self.threshold, retrieval=self.retrieval)
            )
        loading = self._loading
        try:
            return await asyncio.shield(loading)
        except Exception as e:
            if self._loading is loading:
                self._loading = None  # the next call tries again
            if not isinstance(e, ImportError):
                raise
            missing = getattr(e.__cause__, "name", None) or e.name or "a model library"
            name = default_verifier() if self.verifier == "auto" else self.verifier
            extras = "models,judge,mcp" if "judge" in name else "models,mcp"
            message = (
                f"the {name} verifier with {self.retrieval} retrieval needs packages that aren't installed ({missing}). "
                f'Change the server\'s command in the MCP client config to uvx --from "upheld[{extras}]" upheld mcp, or '
                f'pip install "upheld[{extras}]". Or start it with --verifier lexical --retrieval bm25, which needs no models '
                "but is much weaker."
            )
            log.error(message)
            raise ToolError(message) from e

    async def _heartbeat(self, ctx: Context, start: float) -> None:
        try:
            while True:
                loading = self._loading is None or not self._loading.done()
                doing = f"loading the {self.verifier} models (first call only)" if loading else "fetching sources and checking claims"
                elapsed = time.monotonic() - start
                await ctx.report_progress(round(elapsed), None, f"{doing}, {elapsed:.0f} s")
                await asyncio.sleep(HEARTBEAT_SECONDS)
        except Exception:  # a client that has gone away, say; the audit carries on
            return


def _retrieve(task: asyncio.Future) -> None:
    # Marks the exception of an audit nobody waited for as seen, so asyncio doesn't log it.
    if not task.cancelled():
        task.exception()


def make_server(
    verifier: str = "auto",
    *,
    threshold: float | None = None,
    retrieval: str = "auto",
    timeout: float = 300.0,
    allow_private: bool = False,
) -> MCPServer:
    checker = Checker(verifier, threshold=threshold, retrieval=retrieval, timeout=timeout, allow_private=allow_private)
    server = MCPServer("upheld", instructions=INSTRUCTIONS, version=version("upheld"), website_url="https://upheld.varunsg.com")

    @server.tool(annotations=READ_ONLY)
    async def audit_citations(
        ctx: Context,
        answer: Annotated[
            str | None,
            Field(
                description="The answer's text. Cite sources with [1], [2] or [1, 2] after each claim, or with inline markdown "
                "links. A reference list at the end ('[1] Title - https://...') works too, with no sources argument."
            ),
        ] = None,
        sources: Annotated[
            list[SourceArg | str] | None,
            Field(description="The sources the answer cites, in order: each a URL, the source's text, or an object. Numbered from 1."),
        ] = None,
        question: Annotated[str | None, Field(description="The question the answer responds to.")] = None,
        response: Annotated[
            dict[str, Any] | str | None,
            Field(
                description="Instead of answer and sources: an OpenAI, Anthropic, Perplexity or Gemini API response with web "
                "search, as JSON. upheld reads the citations from it."
            ),
        ] = None,
        provider: Annotated[
            Literal["auto", "openai", "anthropic", "perplexity", "gemini"],
            Field(description="Whose response it is. auto tells them apart."),
        ] = "auto",
        full_report: Annotated[
            bool, Field(description="Also return the full report: every claim, score, evidence passage and source.")
        ] = False,
    ) -> dict[str, Any]:
        """Check whether the sources an answer cites back its claims, before you show the answer.

        Returns counts of each verdict and, for each claim that isn't supported, the cited URL, the closest passage in the
        source and why, so you can fix or drop the claim. Verdicts: supported; unsupported (the source doesn't say it);
        wrong_entity (a name in the claim isn't in the source); misattributed (what it cites doesn't back it, but another
        source in the answer, or a page its search returned, does: supported_by says which); source_missing (no such source
        listed, or a dead URL that was never archived); unverifiable (the page couldn't be read, live or archived); uncited
        (a factual sentence with no citation). Pages that can't be read live are read from the Wayback Machine, and the
        note says so. passage_link opens the page at the closest passage, highlighted, to show the user.
        """
        if (answer is None) == (response is None):
            raise ToolError("give either answer (with its sources) or response")
        listed = [s if isinstance(s, str) else s.model_dump(exclude_none=True) for s in sources or []]
        try:
            given = answer if answer is not None else json.loads(response) if isinstance(response, str) else response
            req = to_request(given, listed, question=question, provider=provider)
        except ValueError as e:  # bad JSON, a response upheld can't read, or input over the limits
            raise ToolError(str(e)) from e
        return compact(await checker.audit(req, ctx), full_report)

    @server.tool(annotations=READ_ONLY)
    async def check_claim(
        ctx: Context,
        claim: Annotated[str, Field(description="One statement, as you'd write it in the answer, without citation markers.")],
        url: Annotated[str | None, Field(description="The page to check it against.")] = None,
        text: Annotated[str | None, Field(description="The source's text, if you have it, instead of a URL. Nothing is fetched.")] = None,
        question: Annotated[str | None, Field(description="The question the statement answers.")] = None,
    ) -> dict[str, Any]:
        """Check one statement against one source before you cite it.

        Give the source's url, or its text. Returns the verdict, a support score from 0 to 1 and the passage that came
        closest, whether or not it backs the statement. The verdicts are those of audit_citations.
        """
        if not claim.strip():
            raise ToolError("claim is empty")
        if not (url or text):
            raise ToolError("give the source's url or its text")
        try:
            req = AuditRequest(
                answer=claim,
                question=question,
                sources=[Source(id="1", url=url, text=text)],
                cited_spans=[CitedSpan(start=0, end=len(claim), cited=["1"])],
            )
        except ValueError as e:
            raise ToolError(str(e)) from e
        report = await checker.audit(req, ctx)
        result = next((c for c in report.claims if c.checks), None)
        if result is None:
            raise ToolError("claim has no text to check once citation markers are removed")
        citation = _citation(result.checks[0], report.sources[0], result.text)
        del citation["source"]
        return {"verdict": citation.pop("verdict"), **citation, "verifier": report.verifier}

    return server


def compact(report: AuditReport, full_report: bool = False) -> dict[str, Any]:
    """What an agent needs to fix an answer: verdict counts, and each claim that isn't supported with its closest passage."""
    s = report.summary
    uncited = s.claim_verdicts.get(Verdict.UNCITED, 0)
    sources = {src.id: src for src in report.sources}
    result: dict[str, Any] = {
        "summary": f"{s.supported_claims} of {s.cited_claims} cited claims supported" + (f", {uncited} uncited" if uncited else ""),
        "verdicts": s.claim_verdicts,
        "problems": [_problem(c, sources) for c in report.claims if c.verdict != Verdict.SUPPORTED],
        "verifier": report.verifier,
        "retrieval": report.retrieval,
    }
    if full_report:
        result["report"] = report.model_dump(mode="json")
    return result


def _problem(claim: ClaimResult, sources: dict[str, SourceReport]) -> dict[str, Any]:
    problem: dict[str, Any] = {"claim": claim.text, "verdict": claim.verdict.value}
    if claim.checks:
        problem["citations"] = [_citation(check, sources.get(check.source_id), claim.text) for check in claim.checks]
    if claim.supported_by:
        problem["supported_by"] = [_citation(check, sources.get(check.source_id), claim.text) for check in claim.supported_by]
    return problem


def _citation(check: CitationCheck, source: SourceReport | None, claim: str) -> dict[str, Any]:
    fields = {
        "source": check.source_id,
        "url": source and (source.resolved_url or source.url),
        "verdict": check.verdict.value,
        "score": check.support_score,
        "closest_passage": excerpt(check.evidence[0].passage, claim) if check.evidence else None,
        "passage_link": check.evidence[0].link if check.evidence else None,
        "not_in_source": check.missing_entities or None,
        "flagged": [span.text.strip() for span in check.unsupported_spans] or None,
        "note": check.note,
    }
    return {k: v for k, v in fields.items() if v is not None}


def excerpt(passage: str, claim: str, limit: int = PASSAGE_CHARS) -> str:
    """The sentences of a passage around the one sharing the most words with the claim, to about `limit` characters."""
    if len(passage) <= limit:
        return passage
    sentences = re.split(r"(?<=[.!?])\s+", passage)
    words = set(tokenize(claim))
    best = max(range(len(sentences)), key=lambda i: len(words & set(tokenize(sentences[i]))))
    start, end = best, best + 1
    grew = True
    while grew:
        grew = False
        if end < len(sentences) and len(" ".join(sentences[start : end + 1])) <= limit:
            end, grew = end + 1, True
        if start > 0 and len(" ".join(sentences[start - 1 : end])) <= limit:
            start, grew = start - 1, True
    text = " ".join(sentences[start:end])
    cut = len(text) > limit
    if cut:
        text = text[:limit].rsplit(" ", 1)[0]
    return ("…" if start else "") + text + ("…" if cut or end < len(sentences) else "")
