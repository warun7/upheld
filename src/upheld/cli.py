import asyncio
import json
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from upheld.auditor import to_request
from upheld.evals import load_examples, metrics_at, score_examples
from upheld.evidence import make_embedder
from upheld.models import AuditReport, AuditRequest, Verdict
from upheld.pipeline import run_audit
from upheld.providers import Provider
from upheld.verify import make_verifier

app = typer.Typer(no_args_is_help=True, help="Check whether an AI answer's citations actually support its claims.")
console = Console()

VERDICT_STYLE = {
    Verdict.SUPPORTED: "green",
    Verdict.UNSUPPORTED: "red",
    Verdict.WRONG_ENTITY: "magenta",
    Verdict.SOURCE_MISSING: "red bold",
    Verdict.UNVERIFIABLE: "yellow",
    Verdict.UNCITED: "dim",
}

VerifierOpt = Annotated[
    str,
    typer.Option(
        help="ensemble (MiniCheck, word overlap and LettuceDetect combined), ensemble+judge (adds the Granite Guardian 3.3 8B judge: most accurate, slower, needs the judge extra), minicheck (MiniCheck-Flan-T5), lettuce (LettuceDetect), lexical (word overlap, no model), or judge (the Granite judge alone)."
    ),
]
ThresholdOpt = Annotated[float | None, typer.Option(help="Support score below this counts as unsupported.")]
RetrievalOpt = Annotated[
    str, typer.Option(help="How to find evidence in each source: hybrid (BM25 + embeddings), bm25, or auto (hybrid if installed).")
]


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
    verifier: VerifierOpt = "ensemble",
    threshold: ThresholdOpt = None,
    retrieval: RetrievalOpt = "auto",
    fetch: Annotated[bool, typer.Option(help="Fetch cited URLs. Off means only inline source text is used.")] = True,
    allow_private: Annotated[bool, typer.Option(help="Allow fetching localhost and private-network URLs.")] = False,
    as_json: Annotated[bool, typer.Option("--json", help="Print the full report as JSON.")] = False,
) -> None:
    """Audit one answer."""
    text = sys.stdin.read() if str(path) == "-" else path.read_text()
    try:
        if path.suffix == ".json" or provider != Provider.AUTO or (str(path) == "-" and text.lstrip().startswith("{")):
            req = to_request(json.loads(text), question=question, provider=provider)
        else:
            req = AuditRequest(answer=text, question=question)
    except ValueError as e:  # bad JSON, or not a response upheld can read
        console.print(f"[red]error:[/] {e}")
        raise typer.Exit(1) from e
    report = asyncio.run(
        run_audit(
            req, make_verifier(verifier, threshold), embedder=make_embedder(retrieval), fetch=fetch, allow_private=allow_private
        )
    )
    if as_json:
        print(report.model_dump_json(indent=2))
    else:
        render(report)


@app.command("eval")
def evaluate(
    path: Annotated[Path, typer.Argument(help="Labeled JSONL: claim, evidence, label (supported|unsupported).")],
    verifier: VerifierOpt = "ensemble",
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
    verifier: VerifierOpt = "ensemble",
    retrieval: RetrievalOpt = "auto",
) -> None:
    """Run the HTTP API, plus the website and playground when web/dist is built."""
    import os

    try:
        import fastapi  # noqa: F401
        import uvicorn
    except ImportError as e:
        console.print(f'[red]error:[/] upheld serve needs the api extra ({e.name} is missing): pip install "upheld\\[api]"')
        raise typer.Exit(1) from e

    os.environ["UPHELD_VERIFIER"] = verifier
    os.environ["UPHELD_RETRIEVAL"] = retrieval
    uvicorn.run("upheld.api:app", host=host, port=port)


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
