import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from upheld.auditor import to_request
from upheld.evals import load_examples, metrics_at, score_examples
from upheld.evidence import make_embedder
from upheld.htmlreport import render_html
from upheld.models import AuditReport, AuditRequest, Verdict
from upheld.pipeline import run_audit
from upheld.providers import Provider
from upheld.testing import fail_on_verdicts, summarize
from upheld.verify import make_verifier

app = typer.Typer(no_args_is_help=True, help="Check whether an AI answer's citations actually support its claims.")
console = Console()
err = Console(stderr=True)

VERDICT_STYLE = {
    Verdict.SUPPORTED: "green",
    Verdict.UNSUPPORTED: "red",
    Verdict.WRONG_ENTITY: "magenta",
    Verdict.MISATTRIBUTED: "magenta",
    Verdict.SOURCE_MISSING: "red bold",
    Verdict.UNVERIFIABLE: "yellow",
    Verdict.UNCITED: "dim",
}

VERIFIER_HELP = "auto (the default: judge when the judge extra is installed and llama.cpp can use a GPU, otherwise ensemble), ensemble (MiniCheck, word overlap and LettuceDetect combined), ensemble+judge (adds the Granite Guardian 3.3 8B judge: most accurate, about 3x slower than the judge alone, needs the judge extra), minicheck (MiniCheck-Flan-T5), lettuce (LettuceDetect), lexical (word overlap, no model), or judge (the Granite judge alone: half the ensemble's false alarms, needs the judge extra)."
THRESHOLD_HELP = "Support score below this counts as unsupported."
RETRIEVAL_HELP = "How to find evidence in each source: hybrid (BM25 + embeddings), bm25, or auto (hybrid if installed)."
ALLOW_PRIVATE_HELP = "Allow fetching localhost and private-network URLs."

FAIL_ON_HELP = (
    "Exit with status 1 if any claim gets one of these verdicts, comma-separated: unsupported, wrong_entity, misattributed, "
    "source_missing, unverifiable, uncited, or flagged for the first four. Without it, a finished audit exits 0. "
    "Errors exit 2."
)


def _fail_on(value: str | None) -> frozenset[Verdict]:
    try:
        return fail_on_verdicts(value or "")
    except ValueError as e:
        raise typer.BadParameter(str(e)) from e


VerifierOpt = Annotated[str, typer.Option(help=VERIFIER_HELP)]
ThresholdOpt = Annotated[float | None, typer.Option(help=THRESHOLD_HELP)]
RetrievalOpt = Annotated[str, typer.Option(help=RETRIEVAL_HELP)]


@app.command()
def audit(
    path: Annotated[
        Path,
        typer.Argument(help="Answer as .json (an AuditRequest, or a provider's response), or markdown/text with a reference list. Use - for stdin."),
    ],
    question: Annotated[str | None, typer.Option(help="The question the answer responds to.")] = None,
    provider: Annotated[
        Provider,
        typer.Option(
            "--from",
            help="Whose API response the JSON is: openai, anthropic, perplexity or gemini. auto tells them apart by shape, and reads JSON with an `answer` as an AuditRequest.",
        ),
    ] = Provider.AUTO,
    verifier: VerifierOpt = "auto",
    threshold: ThresholdOpt = None,
    retrieval: RetrievalOpt = "auto",
    fetch: Annotated[bool, typer.Option(help="Fetch cited URLs. Off means only inline source text is used.")] = True,
    allow_private: Annotated[bool, typer.Option(help=ALLOW_PRIVATE_HELP)] = False,
    as_json: Annotated[bool, typer.Option("--json", help="Print the full report as JSON.")] = False,
    html: Annotated[
        Path | None,
        typer.Option("--html", help="Also write the report as one self-contained HTML page to this path, to open in a browser or share."),
    ] = None,
    fail_on: Annotated[str | None, typer.Option("--fail-on", help=FAIL_ON_HELP)] = None,
) -> None:
    """Audit one answer."""
    failing_verdicts = _fail_on(fail_on)
    try:
        text = sys.stdin.read() if str(path) == "-" else path.read_text()
        if path.suffix == ".json" or provider != Provider.AUTO or (str(path) == "-" and text.lstrip().startswith("{")):
            req = to_request(json.loads(text), question=question, provider=provider)
        else:
            req = AuditRequest(answer=text, question=question)
    except (OSError, ValueError) as e:  # unreadable file, bad JSON, or not a response upheld can read
        err.print(f"[red]error:[/] {e}")
        raise typer.Exit(2) from e
    try:
        report = asyncio.run(
            run_audit(
                req, make_verifier(verifier, threshold), embedder=make_embedder(retrieval), fetch=fetch, allow_private=allow_private
            )
        )
    except (ImportError, ValueError) as e:  # a missing extra, or an unknown verifier or retrieval name
        err.print(f"[red]error:[/] {e}")
        raise typer.Exit(2) from e
    except Exception as e:
        # A crash must not exit 1, which --fail-on uses for "the audit found problems".
        err.print_exception()
        raise typer.Exit(2) from e
    if as_json:
        print(report.model_dump_json(indent=2))
    else:
        render(report)
    if html:
        try:
            html.write_text(render_html(req, report), encoding="utf-8")
        except OSError as e:
            err.print(f"[red]error:[/] couldn't write the HTML report: {e}")
            raise typer.Exit(2) from e
        err.print(f"wrote {html}", soft_wrap=True, highlight=False)
    failing = [c for c in report.claims if c.verdict in failing_verdicts]
    if failing:
        err.print(f"[red]--fail-on:[/] {summarize(failing, report)}")
        raise typer.Exit(1)


@app.command("eval")
def evaluate(
    path: Annotated[Path, typer.Argument(help="Labeled JSONL: claim, evidence, label (supported|unsupported).")],
    verifier: VerifierOpt = "auto",
    threshold: ThresholdOpt = None,
) -> None:
    """Measure a verifier against human labels, with a threshold sweep."""
    examples = load_examples(path)
    v = make_verifier(verifier, threshold)
    scores = score_examples(examples, v)

    table = Table(title=f"{v.name} on {path.name} (n={len(examples)}, positive class = unsupported)")
    for col in ("threshold", "precision", "recall", "F1", "macro-F1", "accuracy", "flagged"):
        table.add_column(col, justify="right")
    for t in sorted({0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, v.threshold}):
        m = metrics_at(t, scores, examples)
        style = "bold" if t == v.threshold else None
        table.add_row(
            f"{t:.2f}",
            f"{m.precision:.3f}",
            f"{m.recall:.3f}",
            f"{m.f1:.3f}",
            f"{m.macro_f1:.3f}",
            f"{m.accuracy:.3f}",
            f"{m.flagged_rate:.1%}",
            style=style,
        )
    console.print(table)


@app.command()
def serve(
    host: str = "127.0.0.1",
    port: int = 8000,
    verifier: VerifierOpt = "auto",
    retrieval: RetrievalOpt = "auto",
) -> None:
    """Run the HTTP API, plus the website when web/dist is built."""
    try:
        import fastapi  # noqa: F401
        import uvicorn
    except ImportError as e:
        console.print(f'[red]error:[/] upheld serve needs the api extra ({e.name} is missing): pip install "upheld\\[api]"')
        raise typer.Exit(1) from e

    os.environ["UPHELD_VERIFIER"] = verifier
    os.environ["UPHELD_RETRIEVAL"] = retrieval
    uvicorn.run("upheld.api:app", host=host, port=port)


@app.command("mcp")
def mcp_server(
    verifier: Annotated[str, typer.Option(envvar="UPHELD_VERIFIER", help=VERIFIER_HELP)] = "auto",
    threshold: Annotated[float | None, typer.Option(envvar="UPHELD_THRESHOLD", help=THRESHOLD_HELP)] = None,
    retrieval: Annotated[str, typer.Option(envvar="UPHELD_RETRIEVAL", help=RETRIEVAL_HELP)] = "auto",
    timeout: Annotated[
        float, typer.Option(envvar="UPHELD_TIMEOUT", help="Seconds an audit may take, model loading included, before the call gives up.")
    ] = 300.0,
    allow_private: Annotated[bool, typer.Option(envvar="UPHELD_ALLOW_PRIVATE", help=ALLOW_PRIVATE_HELP)] = False,
) -> None:
    """Run an MCP server over stdio, so AI agents can check the citations in their answers."""
    try:
        from upheld.mcp_server import make_server
    except ImportError as e:
        Console(stderr=True).print(f'[red]error:[/] upheld mcp needs the mcp extra ({e.name} is missing): pip install "upheld\\[models,mcp]"')
        raise typer.Exit(1) from e

    # stdout carries the protocol, so logs go to stderr, one line each. httpx (and the httpx2 that newer
    # huggingface_hub uses) would log every request, model downloads included.
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s", stream=sys.stderr)
    for name in ("httpx", "httpx2"):
        logging.getLogger(name).setLevel(logging.WARNING)
    try:
        make_server(verifier, threshold=threshold, retrieval=retrieval, timeout=timeout, allow_private=allow_private).run("stdio")
    finally:
        # While serving, the SDK points fd 1 at stderr. Stray print()s still buffered when it hands fd 1 back
        # would reach the client as the process exits, so send those to stderr too.
        os.dup2(2, 1)


@app.command()
def doctor() -> None:
    """Show what's installed, which verifier and retrieval `auto` picks on this machine and why, and which models are downloaded."""
    from upheld.doctor import diagnose

    d = diagnose()
    ok, no = "[green]✓[/]", "[red]✗[/]"
    console.print(f"[bold]upheld {d.upheld}[/] · Python {d.python} · {d.system} · {d.memory_gib:.0f} GB memory\n")

    console.print("[bold]extras[/]")
    for e in d.extras:
        detail = ", ".join(e.versions) if e.installed else f'[dim]pip install "upheld\\[{e.name}]"[/]'
        console.print(f"  {ok if e.installed else no} {e.name:<10} {detail}")

    devices = {"cuda": "cuda (NVIDIA GPU)", "mps": "mps (Apple GPU)", "cpu": "cpu (no GPU found by torch)", None: "[dim]unknown: torch isn't installed[/]"}
    console.print(f"\n[bold]device[/]     {devices[d.device]}")
    console.print(f"[bold]verifier[/]   auto picks [bold]{d.verifier}[/]: {escape(d.reason)}")
    if not d.runnable:
        console.print(
            f'           [red]{d.verifier} needs extras that aren\'t installed[/], so audits fail unless you pass --verifier lexical, '
            'which is much weaker: pip install "upheld\\[models]"'
        )
    retrieval = "hybrid (BM25 + embeddings)" if d.retrieval == "hybrid" else 'bm25 (keywords only; hybrid needs pip install "upheld\\[dense]")'
    console.print(f"[bold]retrieval[/]  auto picks {retrieval}")

    if d.models:
        console.print("\n[bold]models[/] for these choices")
        width = max(len(m.repo) for m in d.models)
        for m in d.models:
            if m.downloaded is None:
                state = f"[dim]can't tell: huggingface_hub isn't installed ({m.size})[/]"
            elif m.downloaded:
                state = "downloaded"
            else:
                state = f"[yellow]downloads {m.size} on first use[/]"
            mark = "[dim]?[/]" if m.downloaded is None else ok if m.downloaded else no
            console.print(f"  {mark} {m.repo:<{width}}  {state}")


def render(report: AuditReport) -> None:
    s = report.summary
    console.print(f"[bold]verifier[/] {report.verifier} · [bold]retrieval[/] {report.retrieval}")
    console.print(
        f"[bold]{s.supported_claims}/{s.cited_claims}[/] cited claims supported · "
        f"{s.citations_checked} citations checked · {s.claim_verdicts.get('uncited', 0)} uncited claims\n"
    )

    claims = Table(show_lines=True, expand=True)
    claims.add_column("#", justify="right", width=3)
    claims.add_column("verdict", width=14)
    claims.add_column("claim", ratio=3)
    claims.add_column("details", ratio=2)
    for c in report.claims:
        details = []
        for check in c.checks:
            score = f" {check.support_score:.2f}" if check.support_score is not None else ""
            line = f"[{check.source_id}] [{VERDICT_STYLE[check.verdict]}]{check.verdict.value}[/]{score}"
            if check.missing_entities:
                line += f" · not in source: {', '.join(check.missing_entities)}"
            if check.unsupported_spans:
                line += " · flagged: " + "; ".join(f'"{sp.text.strip()}"' for sp in check.unsupported_spans)
            if check.note:
                line += f" · {check.note}"
            details.append(line)
        if c.note:
            details.append(f"[dim]{c.note}[/]")
        claims.add_row(str(c.index), f"[{VERDICT_STYLE[c.verdict]}]{c.verdict.value}[/]", c.text, "\n".join(details))
    console.print(claims)

    sources = Table(title="sources", expand=True)
    for col in ("id", "status", "url / note"):
        sources.add_column(col)
    for src in report.sources:
        resolved = f"→ {src.resolved_url}" if src.resolved_url else None
        sources.add_row(src.id, src.status.value, " · ".join(x for x in (src.url, resolved, src.note) if x))
    console.print(sources)
