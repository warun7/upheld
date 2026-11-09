"""Run by action.yml: audit every answer file with one set of loaded models, write an HTML and a JSON report for each,
annotate each failing claim on its line, and write a job summary. Exits 1 if a claim's verdict is in fail-on, 2 if a
file couldn't be audited, 0 otherwise -- the same codes as `upheld audit`."""

import glob
import json
import os
import re
import sys
from pathlib import Path

from upheld import Auditor, AuditRequest
from upheld.auditor import to_request
from upheld.htmlreport import render_html
from upheld.models import AuditReport, ClaimResult
from upheld.testing import fail_on_verdicts, summarize


def escape(value: str, *, prop: bool = False) -> str:
    """A workflow command's message, or one of its properties."""
    value = value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    return value.replace(":", "%3A").replace(",", "%2C") if prop else value


def annotate(path: str, text: str | None, claim: ClaimResult) -> None:
    where = f"file={escape(path, prop=True)}"
    if text is not None:  # a markdown or text answer: the claim's offset is a place in the file
        line = text.count("\n", 0, claim.start) + 1
        where += f",line={line}"
    reasons = [c.note or f"[{c.source_id}] {c.verdict.value}" for c in claim.checks] or [claim.note or claim.verdict.value]
    title = escape(f"upheld: claim {claim.index + 1} is {claim.verdict.value}", prop=True)
    print(f"::error {where},title={title}::{escape(claim.text.strip())} ({escape('; '.join(r for r in reasons if r))})")


def output(name: str, value: str) -> None:
    if path := os.environ.get("GITHUB_OUTPUT"):
        with open(path, "a") as f:
            f.write(f"{name}={value}\n")


def summary(rows: list[tuple[str, AuditReport | None, list[ClaimResult], str | None]], verifier: str) -> str:
    lines = ["## upheld citation check", "", "| Answer | Claims | Cited claims supported | Result |", "|---|---|---|---|"]
    for path, report, failing, error in rows:
        if report is None:
            lines.append(f"| `{path}` | | | couldn't audit: {error} |")
            continue
        s = report.summary
        result = summarize(failing, report) if failing else "passed"
        lines.append(f"| `{path}` | {s.claims} | {s.supported_claims}/{s.cited_claims} | {result} |")
    lines += ["", f"Verifier `{verifier}`. Each answer's HTML report is in the uploaded artifact."]
    for path, report, failing, _ in rows:
        if report and failing:
            lines += ["", f"<details><summary><code>{path}</code>: {len(failing)} failing</summary>", ""]
            lines += [f"- **claim {c.index + 1}, {c.verdict.value}**: {c.text.strip()}" + (f" ({c.note})" if c.note else "") for c in failing]
            lines += ["", "</details>"]
    return "\n".join(lines) + "\n"


def main() -> int:
    env = os.environ
    patterns = [p.strip() for p in env["UPHELD_FILES"].splitlines() if p.strip()]
    files = sorted({f for p in patterns for f in glob.glob(p, recursive=True) if Path(f).is_file()})
    if not files:
        print(f"::error title=upheld::no files match {', '.join(patterns) or 'the files input'}")
        return 2
    try:
        verdicts = fail_on_verdicts(env.get("UPHELD_FAIL_ON", ""))
    except ValueError as e:
        print(f"::error title=upheld::fail-on: {escape(str(e))}")
        return 2
    provider, fetch = env.get("UPHELD_FROM", "auto"), env.get("UPHELD_FETCH", "true").lower() != "false"
    out = Path(env["UPHELD_OUT"])
    out.mkdir(parents=True, exist_ok=True)
    output("report-dir", str(out))

    print(f"Loading the {env['UPHELD_VERIFIER']} verifier", flush=True)
    auditor = Auditor(env["UPHELD_VERIFIER"], retrieval=env.get("UPHELD_RETRIEVAL", "auto"))
    rows: list[tuple[str, AuditReport | None, list[ClaimResult], str | None]] = []
    for path in files:
        print(f"Auditing {path}", flush=True)
        try:
            text = Path(path).read_text(encoding="utf-8")
            if path.endswith(".json") or provider != "auto":
                req, answer_text = to_request(json.loads(text), provider=provider), None
            else:
                req, answer_text = AuditRequest(answer=text), text
            report = auditor.audit(req, fetch=fetch)
        except Exception as e:  # noqa: BLE001 -- one unreadable file shouldn't hide the others' results
            print(f"::error file={escape(path, prop=True)},title=upheld::couldn't audit this file: {escape(str(e))}")
            rows.append((path, None, [], str(e)))
            continue
        name = re.sub(r"[^\w.-]+", "_", path).strip("_")
        (out / f"{name}.html").write_text(render_html(req, report), encoding="utf-8")
        (out / f"{name}.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
        failing = [c for c in report.claims if c.verdict in verdicts]
        for claim in failing:
            annotate(path, answer_text, claim)
        print(f"  {summarize(failing, report) if failing else 'passed'}: {report.summary.supported_claims}/{report.summary.cited_claims} cited claims supported")
        rows.append((path, report, failing, None))

    if path := env.get("GITHUB_STEP_SUMMARY"):
        with open(path, "a", encoding="utf-8") as f:
            f.write(summary(rows, rows[0][1].verifier if rows and rows[0][1] else env["UPHELD_VERIFIER"]))
    failed = sum(1 for _, report, failing, _ in rows if failing)
    output("failed", str(failed))
    return 2 if any(report is None for _, report, _, _ in rows) else 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
