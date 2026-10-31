"""Label collected answers by hand and build the scoreboard.

    uv run python evals/fresh/label.py prepare                        # audit every answer (fetches cited pages)
    uv run python evals/fresh/label.py label                          # label citations one at a time; resumable
    uv run python evals/fresh/label.py scoreboard                     # per-provider results -> scoreboard.md

`prepare` turns every (claim, cited source) pair into an item with the
passages upheld retrieved. `label` shows items in random order with the
provider and upheld's verdict hidden, so neither biases the label. Open the
page ([o]) whenever the passages don't settle it: retrieval can miss.

Labels:
  s  supported    the cited page backs everything the claim says
  p  partial      it backs some of the claim; counted as unsupported, as in AttributionBench
  u  unsupported  it doesn't back the claim, or contradicts it
  x  can't judge  the page is unreadable, paywalled or gone
"""

import argparse
import asyncio
import hashlib
import json
import random
import webbrowser
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

from rich.console import Console
from rich.panel import Panel

from upheld.audit import run_audit
from upheld.evidence import make_embedder
from upheld.models import AuditRequest, Source, Verdict
from upheld.verify import make_verifier

HERE = Path(__file__).parent
ANSWERS = HERE / "answers"
ITEMS = HERE / "items.jsonl"
LABELS = HERE / "labels.jsonl"
SCOREBOARD = HERE / "scoreboard.md"
CHOICES = {"s": "supported", "p": "partial", "u": "unsupported", "x": "cant_judge"}
FLAGGED = {Verdict.UNSUPPORTED, Verdict.WRONG_ENTITY, Verdict.SOURCE_MISSING}

console = Console()


def prepare(verifier_name: str, threshold: float | None, device: str | None) -> None:
    verifier = make_verifier(verifier_name, threshold, device)
    embedder = make_embedder("auto")
    items = []
    for path in sorted(ANSWERS.glob("*.jsonl")):
        for line in path.read_text().splitlines():
            record = json.loads(line)
            req = AuditRequest(question=record["question"], answer=record["answer"], sources=[Source(**s) for s in record["sources"]])
            report = asyncio.run(run_audit(req, verifier, embedder=embedder))
            status = {s.id: s for s in report.sources}
            for claim in report.claims:
                for check in claim.checks:
                    source = status.get(check.source_id)
                    key = f"{record['provider']}|{record['question']}|{claim.text}|{check.source_id}"
                    items.append(
                        {
                            "id": hashlib.sha1(key.encode()).hexdigest()[:12],
                            "provider": record["provider"],
                            "model": record["model"],
                            "question": record["question"],
                            "claim": claim.text,
                            "source_id": check.source_id,
                            "url": source.url if source else None,
                            "source_status": source.status.value if source else "missing",
                            "passages": [e.passage for e in check.evidence],
                            "upheld_verdict": check.verdict.value,
                            "support_score": check.support_score,
                        }
                    )
            console.print(f"{record['provider']}: {len(report.claims)} claims · {record['question'][:60]}")
    ITEMS.write_text("".join(json.dumps(i) + "\n" for i in items))
    console.print(f"wrote {len(items)} items to {ITEMS} ({report.verifier}, {report.retrieval})")


def label() -> None:
    items = [json.loads(line) for line in ITEMS.read_text().splitlines()]
    done = {json.loads(line)["id"] for line in LABELS.read_text().splitlines()} if LABELS.exists() else set()
    todo = [i for i in items if i["id"] not in done]
    random.Random(0).shuffle(todo)
    console.print(f"{len(done)} labeled, {len(todo)} to go. Keys: s supported, p partial, u unsupported, x can't judge, o open page, q quit\n")
    for n, item in enumerate(todo, 1):
        passages = "\n\n".join(f"[dim]passage {k}[/] {p}" for k, p in enumerate(item["passages"], 1)) or "[dim](no readable text)[/]"
        console.print(
            Panel(
                f"[bold]Q:[/] {item['question']}\n\n[bold]Claim:[/] {item['claim']}\n\n"
                f"[bold]Source:[/] {item['url']} [dim]({item['source_status']})[/]\n\n{passages}",
                title=f"{n}/{len(todo)}",
            )
        )
        while True:
            key = console.input("label> ").strip().lower()
            if key == "o" and item["url"]:
                webbrowser.open(item["url"])
            elif key == "q":
                return
            elif key in CHOICES:
                with LABELS.open("a") as f:
                    f.write(json.dumps({"id": item["id"], "label": CHOICES[key], "at": datetime.now(UTC).isoformat(timespec="seconds")}) + "\n")
                break


def scoreboard() -> None:
    items = {i["id"]: i for i in map(json.loads, ITEMS.read_text().splitlines())}
    labels = {row["id"]: row["label"] for row in map(json.loads, LABELS.read_text().splitlines())} if LABELS.exists() else {}
    by_provider: dict[str, list[dict]] = defaultdict(list)
    for item in items.values():
        by_provider[item["provider"]].append(item)

    lines = [
        "# Fresh benchmark scoreboard",
        "",
        "How often each AI search tool's citations back the claim they're attached to, judged by hand.",
        "",
        "| Provider | Model | Citations labeled | Supported | Partial | Unsupported | Can't judge | Dead links (all citations) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for provider, rows in sorted(by_provider.items()):
        labeled = [labels[r["id"]] for r in rows if r["id"] in labels]
        counts = Counter(labeled)
        dead = sum(r["source_status"] in ("likely_fabricated", "link_rot") for r in rows)
        pct = lambda k: f"{counts[k] / len(labeled):.0%}" if labeled else "-"  # noqa: E731
        models = ", ".join(sorted({r["model"] for r in rows}))
        lines.append(
            f"| {provider} | {models} | {len(labeled)} | {pct('supported')} | {pct('partial')} | {pct('unsupported')} | {pct('cant_judge')} | {dead}/{len(rows)} |"
        )

    # How well upheld agrees with the human labels. Partial counts as unsupported.
    judged = [(items[i], label) for i, label in labels.items() if i in items and label != "cant_judge"]
    judged = [(item, label) for item, label in judged if item["upheld_verdict"] != "unverifiable"]
    if judged:
        human = [label != "supported" for _, label in judged]
        flagged = [item["upheld_verdict"] in FLAGGED for item, _ in judged]
        tp = sum(h and f for h, f in zip(human, flagged))
        precision = tp / sum(flagged) if sum(flagged) else 0.0
        recall = tp / sum(human) if sum(human) else 0.0
        agreement = sum(h == f for h, f in zip(human, flagged)) / len(judged)
        lines += [
            "",
            f"upheld vs these labels ({len(judged)} citations it could read): agreement {agreement:.0%}, "
            f"precision {precision:.2f} and recall {recall:.2f} on unsupported citations.",
        ]
    SCOREBOARD.write_text("\n".join(lines) + "\n")
    console.print("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--verifier", default="ensemble", choices=["ensemble", "minicheck", "lettuce", "lexical"])
    p.add_argument("--threshold", type=float, default=None)
    p.add_argument("--device", default=None)
    sub.add_parser("label")
    sub.add_parser("scoreboard")
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.verifier, args.threshold, args.device)
    elif args.command == "label":
        label()
    else:
        scoreboard()


if __name__ == "__main__":
    main()
