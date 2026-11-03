"""Cross-check the Claude labels with labelers from two other vendors.

The fresh benchmark was labeled by Claude subagents, and Claude also wrote a
third of the answers being labeled. So GPT (through the Codex CLI) and Gemini
(through the Antigravity CLI) label a sample of the same citations under the
same rules (labeling-guide.md), blind to the provider, to upheld's verdict and
to every other label. Both CLIs run on a subscription, not a paid API.

Neither labeler browses. Antigravity has no tool that opens a URL, so each
cited page is fetched once here and both labelers get the same text in the
prompt: the comparison is between judgments of one document, not between
browsers. A page that can't be fetched is read from the Wayback Machine, then
from the copy Claude read (an archive or the paper's abstract), else the
labelers get only the passages and may answer can't judge.

    uv run python evals/fresh/crosscheck.py sample           # 150 ids, stratified by provider and Claude's label
    uv run python evals/fresh/crosscheck.py pages            # fetch each sampled page once -> pages/ (not committed)
    uv run python evals/fresh/crosscheck.py label gpt        # or gemini; resumable
    uv run python evals/fresh/crosscheck.py report           # -> crosscheck.md

Labels go to labels-gpt.jsonl and labels-gemini.jsonl, in the format of
labels-claude.jsonl, and each raw response to raw/.
"""

import argparse
import asyncio
import hashlib
import json
import random
import re
import subprocess
import tempfile
from collections import Counter, defaultdict
from datetime import UTC, datetime
from io import BytesIO
from itertools import combinations
from pathlib import Path

import httpx

from upheld.sources import MIN_TEXT_CHARS, check_url_allowed, extract_text
from verifiers import load_scores, metrics

HERE = Path(__file__).parent
SAMPLE = HERE / "crosscheck-sample.json"
PAGES = HERE / "pages"
RAW = HERE / "raw"
REPORT = HERE / "crosscheck.md"
SAMPLE_SIZE = 150
# Pages are cut here, and a batch holds at most this many items and this much page text.
MAX_PAGE_CHARS = 160_000
BATCH_ITEMS = 8
BATCH_CHARS = 200_000
TIMEOUT = 900
BROWSER_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36"

# Labeler -> (model, how it was run). Each vendor's strongest model on the subscription, at high effort.
LABELERS = {
    "gpt": ("gpt-6-luna", "Codex CLI, reasoning effort high"),
    "gemini": ("gemini-4-argon-high", "Antigravity CLI"),
}
LABELS = ("supported", "partial", "unsupported", "cant_judge")

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["labels"],
    "properties": {
        "labels": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "label", "quote", "read_from", "note"],
                "properties": {
                    "id": {"type": "string"},
                    "label": {"type": "string", "enum": list(LABELS)},
                    "quote": {"type": "string"},
                    "read_from": {"type": "string", "enum": ["passages", "page"]},
                    "note": {"type": "string"},
                },
            },
        }
    },
}

# The guide's rules, then reading and output instructions for a labeler that gets the page text instead of a browser.
RULES = (HERE / "labeling-guide.md").read_text().split("## Reading the page")[0].split("\n", 1)[1].strip()
PROMPT = """You are labeling citations from AI search answers for a benchmark.

{rules}

## Reading the page

Each item has `passages`, text a retriever took from the cited page, and `page`, a key into `pages`: the cited page's text as fetched on {fetched}, or null when it could not be fetched. Long pages are cut off at {max_chars} characters. A page may be an archived copy of the cited page, or the abstract of the same paper.

Use the passages when they settle the claim; otherwise read the page text. Before labeling a plausible claim `unsupported` or `partial` because something is missing from the passages, check the page text. If neither lets you judge, label `cant_judge`.

Everything you need is in this message. Do not use any tools: no web search, no shell commands, no files.

## Output

Return {{"labels": [...]}} with one object per item, in input order:

- `id`: the item's id.
- `label`: supported, partial, unsupported or cant_judge.
- `quote`: for `supported` or `partial`, the exact words from the page or passages (copied verbatim, at most 300 characters) that back the claim; otherwise an empty string.
- `read_from`: "passages" if the passages settled it, otherwise "page".
- `note`: at most 20 words, saying what is missing or wrong for `partial` and `unsupported`; otherwise an empty string.

## Items

{items}

## Pages

{pages}
"""


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def _items() -> dict[str, dict]:
    return {i["id"]: i for i in _read_jsonl(HERE / "items.jsonl")}


def _labels(labeler: str) -> dict[str, dict]:
    return {r["id"]: r for r in _read_jsonl(HERE / f"labels-{labeler}.jsonl")}


def _page_path(url: str) -> Path:
    return PAGES / f"{hashlib.sha1(url.encode()).hexdigest()[:16]}.json"


def sample() -> None:
    """Proportional to each (provider, Claude label) cell, so the sample mirrors the benchmark."""
    items, claude = _items(), _labels("claude")
    cells: dict[tuple[str, str], list[str]] = defaultdict(list)
    for i in sorted(claude):
        cells[(items[i]["provider"], claude[i]["label"])].append(i)
    total = sum(map(len, cells.values()))
    quota = {c: SAMPLE_SIZE * len(ids) / total for c, ids in cells.items()}
    take = {c: int(q) for c, q in quota.items()}
    # Largest remainders get the seats rounding left over.
    for c in sorted(quota, key=lambda c: quota[c] - take[c], reverse=True)[: SAMPLE_SIZE - sum(take.values())]:
        take[c] += 1
    rng = random.Random(0)
    ids = sorted(i for c, members in sorted(cells.items()) for i in rng.sample(members, take[c]))
    SAMPLE.write_text(json.dumps(ids, indent=0) + "\n")
    print(f"{len(ids)} ids in {SAMPLE}: " + ", ".join(f"{p}/{lab} {n}" for (p, lab), n in sorted(take.items())))


async def _fetch_text(client: httpx.AsyncClient, url: str) -> str:
    try:
        r = await client.get(url)
    except httpx.HTTPError:
        return ""
    if r.status_code >= 400:
        return ""
    if "pdf" in r.headers.get("content-type", "") or r.content[:5] == b"%PDF-":
        from pypdf import PdfReader

        try:
            return "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(r.content)).pages)
        except Exception:  # pypdf raises many types on damaged files
            return ""
    return await asyncio.to_thread(extract_text, r.text, str(r.url))


async def _fetch_page(client: httpx.AsyncClient, url: str, claude_copies: list[str]) -> dict:
    for read_from in [url, f"https://web.archive.org/web/2026/{url}", *claude_copies]:
        if len(text := (await _fetch_text(client, read_from)).strip()) >= MIN_TEXT_CHARS:
            return {"url": url, "read_from": read_from, "chars": len(text), "text": text[:MAX_PAGE_CHARS]}
    return {"url": url, "read_from": None, "chars": 0, "text": ""}


async def _fetch_pages(urls: dict[str, list[str]]) -> None:
    async def guard(request: httpx.Request) -> None:
        await asyncio.to_thread(check_url_allowed, str(request.url))

    limit = asyncio.Semaphore(8)
    async with httpx.AsyncClient(
        follow_redirects=True, timeout=30, headers={"User-Agent": BROWSER_UA}, event_hooks={"request": [guard]}
    ) as client:

        async def one(url: str, copies: list[str]) -> None:
            async with limit:
                page = await _fetch_page(client, url, copies)
            page["fetched_at"] = datetime.now(UTC).isoformat(timespec="seconds")
            _page_path(url).write_text(json.dumps(page))
            print(f"{page['chars']:>8} chars  {url[:90]}" + (f"  (from {page['read_from'][:60]})" if page["read_from"] not in (url, None) else ""), flush=True)

        await asyncio.gather(*(one(u, c) for u, c in urls.items() if not _page_path(u).exists()))


def pages() -> None:
    items, claude = _items(), _labels("claude")
    urls: dict[str, list[str]] = {}
    for i in json.loads(SAMPLE.read_text()):
        if url := items[i]["url"]:
            # The copy Claude read is a last resort, used only when neither the page nor its Wayback copy can be read.
            read = claude[i]["read_from"]
            copies = urls.setdefault(url, [])
            if read not in ("passages", url) and read.startswith("http") and read not in copies:
                copies.append(read)
    PAGES.mkdir(exist_ok=True)
    asyncio.run(_fetch_pages(urls))
    fetched = [json.loads(_page_path(u).read_text()) for u in urls]
    print(f"{sum(bool(p['text']) for p in fetched)} of {len(fetched)} pages read; {sum(p['chars'] > MAX_PAGE_CHARS for p in fetched)} cut at {MAX_PAGE_CHARS} chars")


def _batches(todo: list[dict]) -> list[list[dict]]:
    """Items citing the same page stay together, so the page is sent once. Pages are ordered by hash, which mixes providers."""
    by_url: dict[str, list[dict]] = defaultdict(list)
    for item in todo:
        by_url[item["url"] or item["id"]].append(item)
    batches, current, chars = [], [], 0
    for key in sorted(by_url, key=lambda u: hashlib.sha1(u.encode()).hexdigest()):
        group = by_url[key]
        size = len(_page(group[0]["url"])["text"])
        if current and (len(current) + len(group) > BATCH_ITEMS or chars + size > BATCH_CHARS):
            batches.append(current)
            current, chars = [], 0
        current += group
        chars += size
    return batches + ([current] if current else [])


def _page(url: str | None) -> dict:
    path = _page_path(url) if url else None
    return json.loads(path.read_text()) if path and path.exists() else {"text": "", "fetched_at": None}


def _prompt(batch: list[dict]) -> str:
    keys: dict[str, str] = {}
    pages: dict[str, str] = {}
    for item in batch:
        if item["url"] and item["url"] not in keys and (text := _page(item["url"])["text"]):
            keys[item["url"]] = f"p{len(keys) + 1}"
            pages[keys[item["url"]]] = text
    shown = [
        {
            "id": i["id"],
            "question": i["question"],
            "claim": i["claim"],
            "url": i["url"],
            "source_status": i["source_status"],
            "passages": i["passages"],
            "page": keys.get(i["url"]),
        }
        for i in batch
    ]
    fetched = max((p["fetched_at"] for p in map(_page, {i["url"] for i in batch}) if p["fetched_at"]), default="2026-11-02")[:10]
    return PROMPT.format(
        rules=RULES, fetched=fetched, max_chars=f"{MAX_PAGE_CHARS:,}", items=json.dumps(shown, indent=1), pages=json.dumps(pages, indent=1)
    )


def ask_codex(prompt: str, model: str) -> tuple[str, dict]:
    with tempfile.TemporaryDirectory() as tmp:
        schema, last, work = Path(tmp, "schema.json"), Path(tmp, "last.txt"), Path(tmp, "work")
        schema.write_text(json.dumps(SCHEMA))
        work.mkdir()
        # No --search, no user config (so no MCP servers), and an empty read-only directory: nothing to look at but the prompt.
        r = subprocess.run(
            ["codex", "exec", "--model", model, "-c", 'model_reasoning_effort="high"',
             "--sandbox", "read-only", "--ignore-user-config", "--ignore-rules", "--ephemeral", "--skip-git-repo-check",
             "--cd", str(work), "--output-schema", str(schema), "--json", "--output-last-message", str(last), "-"],
            input=prompt, capture_output=True, text=True, timeout=TIMEOUT,
        )  # fmt: skip
        if r.returncode:
            raise RuntimeError(f"codex exited {r.returncode}: {r.stderr.strip()[-300:]}")
        events = [json.loads(line) for line in r.stdout.splitlines() if line.strip()]
        response = last.read_text()
    if tools := [e["item"]["type"] for e in events if e.get("type") == "item.completed" and e["item"]["type"] not in ("agent_message", "reasoning")]:
        raise RuntimeError(f"used tools: {tools}")
    return response, {"events": events}


def ask_agy(prompt: str, model: str) -> tuple[str, dict]:
    with tempfile.TemporaryDirectory() as tmp:
        schema, work = Path(tmp, "schema.json"), Path(tmp, "work")
        schema.write_text(json.dumps(SCHEMA))
        work.mkdir()
        r = subprocess.run(
            ["agy", "--print", prompt, "--model", model, "--sandbox", "--output-format", "stream-json",
             "--json-schema", str(schema), "--print-timeout", f"{TIMEOUT}s"],
            cwd=work, capture_output=True, text=True, timeout=TIMEOUT + 60,
        )  # fmt: skip
    if r.returncode:
        raise RuntimeError(f"agy exited {r.returncode}: {r.stderr.strip()[-300:]}")
    events = [json.loads(line) for line in r.stdout.splitlines() if line.strip()]
    result = next((e["result"] for e in events if e.get("event") == "result"), {})
    if result.get("status") != "SUCCESS":
        raise RuntimeError(f"agy did not finish: {str(result)[:300]}")
    steps = [e["step_update"] for e in events if "step_update" in e]
    if tools := sorted({s["tool_name"] for s in steps if s.get("step_type") == "tool"} - {"finish"}):
        raise RuntimeError(f"used tools: {tools}")
    return result["response"], {"events": events}


ASK = {"gpt": ask_codex, "gemini": ask_agy}


def _parse(response: str, batch: list[dict]) -> list[dict]:
    """The labels, provided there is exactly one valid label per item in the batch."""
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", response.strip())
    rows = json.loads(text)["labels"]
    if sorted(r["id"] for r in rows) != sorted(i["id"] for i in batch):
        raise ValueError("labels don't match the batch's ids")
    if bad := [r["label"] for r in rows if r["label"] not in LABELS]:
        raise ValueError(f"unknown labels {bad}")
    return rows


def label(labeler: str, limit: int | None) -> None:
    items = _items()
    out = HERE / f"labels-{labeler}.jsonl"
    done = set(_labels(labeler))
    todo = [items[i] for i in json.loads(SAMPLE.read_text()) if i not in done]
    model, via = LABELERS[labeler]
    RAW.mkdir(exist_ok=True)
    batches = _batches(todo)[:limit]
    print(f"{len(done)} labeled, {len(todo)} to go in {len(_batches(todo))} batches", flush=True)
    for batch in batches:
        prompt = _prompt(batch)
        key = hashlib.sha1("".join(sorted(i["id"] for i in batch)).encode()).hexdigest()[:10]
        started = datetime.now(UTC)
        try:
            response, raw = ASK[labeler](prompt, model)
            (RAW / f"crosscheck-{labeler}-{key}.json").write_text(json.dumps(raw | {"response": response, "model": model}))
            rows = _parse(response, batch)
        except (subprocess.TimeoutExpired, RuntimeError, ValueError, KeyError) as e:
            print(f"batch {key} ({len(batch)} items): failed ({str(e)[:200]})", flush=True)
            continue
        at = datetime.now(UTC).isoformat(timespec="seconds")
        fields = ("id", "label", "quote", "read_from", "note")
        with out.open("a") as f:
            # The guide caps quotes at 300 characters; not every labeler keeps to it.
            f.write("".join(json.dumps({k: r[k] for k in fields} | {"quote": r["quote"][:300], "by": f"{model} ({via})", "at": at}) + "\n" for r in rows))
        seconds = (datetime.now(UTC) - started).total_seconds()
        print(f"batch {key}: {len(rows)} labeled in {seconds:.0f}s ({len(prompt):,} chars) " + str(dict(Counter(r["label"] for r in rows))), flush=True)


def _kappa(pairs: list[tuple[str, str]]) -> float:
    n = len(pairs)
    observed = sum(a == b for a, b in pairs) / n
    left, right = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    expected = sum(left[k] * right[k] for k in left) / n**2
    return (observed - expected) / (1 - expected) if expected < 1 else 1.0


def _binary(label: str) -> str | None:
    """Supported or not, as in the scoreboard: partial counts as unsupported, and can't judge drops out."""
    return None if label == "cant_judge" else "supported" if label == "supported" else "not supported"


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[‘’“”]", "'", text)).strip().lower()


def report() -> None:
    items = _items()
    ids = json.loads(SAMPLE.read_text())
    names = ["claude", *LABELERS]
    labels = {n: {i: r["label"] for i, r in _labels(n).items() if i in ids} for n in names}
    full = [i for i in ids if all(i in labels[n] for n in names)]
    lines = [
        "# Cross-checking the fresh labels",
        "",
        f"{len(full)} of the {len(ids)} sampled citations (stratified by provider and Claude's label, out of {len(labels['claude'])} labeled) "
        "have labels from all three labelers. Each labeler followed labeling-guide.md, blind to the provider, upheld's verdict and the other labels.",
        "",
        "- claude: Claude Sonnet 5.5 subagents, reading the passages and fetching the page themselves.",
        *(f"- {n}: {m} ({v}), given the same passages plus the page text fetched once by crosscheck.py." for n, (m, v) in LABELERS.items()),
        "",
        "## Agreement",
        "",
        "Binary means supported against partial or unsupported, as in the scoreboard, over the citations both labelers could judge.",
        "",
        "| Labelers | Same label (4-way) | Cohen's κ (4-way) | Judged by both | Same verdict (binary) | Cohen's κ (binary) |",
        "|---|---|---|---|---|---|",
    ]
    for a, b in combinations(names, 2):
        four = [(labels[a][i], labels[b][i]) for i in full]
        two = [(x, y) for x, y in ((_binary(p), _binary(q)) for p, q in four) if x and y]
        lines.append(
            f"| {a} vs {b} | {sum(x == y for x, y in four) / len(four):.0%} | {_kappa(four):.2f} | {len(two)} "
            f"| {sum(x == y for x, y in two) / len(two):.0%} | {_kappa(two):.2f} |"
        )

    # Where the other two agree, does Claude?
    lines += ["", "Where GPT and Gemini give the same binary verdict, how often Claude agrees:", ""]
    settled = [(i, _binary(labels["gpt"][i])) for i in full if _binary(labels["gpt"][i]) and _binary(labels["gpt"][i]) == _binary(labels["gemini"][i])]
    for verdict in ("supported", "not supported"):
        rows = [i for i, v in settled if v == verdict]
        agree = sum(_binary(labels["claude"][i]) == verdict for i in rows)
        unjudged = sum(_binary(labels["claude"][i]) is None for i in rows)
        if rows:
            lines.append(f"- both say {verdict}{' (partial or unsupported)' if verdict != 'supported' else ''}: Claude agrees on {agree} of {len(rows)} ({agree / len(rows):.0%}); can't judge on {unjudged}")

    lines += ["", "## Confusion against Claude", ""]
    for other in LABELERS:
        lines += [f"Rows are Claude's label, columns {other}'s.", "", "| claude \\ " + other + " | " + " | ".join(LABELS) + " |", "|---" * (len(LABELS) + 1) + "|"]
        grid = Counter((labels["claude"][i], labels[other][i]) for i in full)
        lines += [f"| {a} | " + " | ".join(str(grid[(a, b)]) for b in LABELS) + " |" for a in LABELS] + [""]

    lines += [
        "## Scoreboard by labeler",
        "",
        "Share of each provider's sampled citations labeled supported. A labeler that favors answers from its own vendor would rank that vendor higher.",
        "",
        "| Provider | Citations | " + " | ".join(names) + " |",
        "|---" * (len(names) + 2) + "|",
    ]
    by_provider: dict[str, list[str]] = defaultdict(list)
    for i in full:
        by_provider[items[i]["provider"]].append(i)
    for provider, rows in sorted(by_provider.items()):
        lines.append(f"| {provider} | {len(rows)} | " + " | ".join(f"{sum(labels[n][i] == 'supported' for i in rows) / len(rows):.0%}" for n in names) + " |")

    # upheld against each labeler, and against the majority binary verdict.
    majority = {}
    for i in full:
        votes = Counter(v for v in (_binary(labels[n][i]) for n in names) if v)
        if votes and votes.most_common(1)[0][1] >= 2:
            majority[i] = votes.most_common(1)[0][0]
    scores, thresholds = load_scores()
    lines += [
        "",
        "## upheld against each labeler",
        "",
        "Agreement and macro-F1 of each verifier on the sampled citations whose page upheld can read, as shipped (its passages per claim "
        "and its AttributionBench dev threshold; see verifiers.py). "
        f"Majority is the binary verdict at least two labelers share ({len(majority)} citations).",
        "",
        "| Verifier | " + " | ".join(f"{n} agree | {n} macro-F1" for n in [*names, "majority"]) + " |",
        "|---" * (2 * len(names) + 3) + "|",
    ]
    truth = {n: {i: _binary(labels[n][i]) for i in full if _binary(labels[n][i])} for n in names} | {"majority": majority}
    for name in ("ensemble", "ensemble+judge", "judge", "minicheck", "lettuce", "lexical"):
        if name not in scores:
            continue
        cells = []
        for n, verdicts in truth.items():
            rows = [(scores[name][i] < thresholds.get(name, 0.5), v == "not supported") for i, v in verdicts.items() if i in scores[name]]
            m = metrics(rows)
            cells += [f"{m['agree']:.0%}", f"{100 * m['macro_f1']:.1f}"]
        lines.append(f"| {name} | " + " | ".join(cells) + " |")

    lines += [
        "",
        "## Quotes",
        "",
        "Share of supported and partial labels whose quote appears verbatim in the passages or the fetched page "
        "(ignoring case, spacing and curly quotes; an ellipsis may join verbatim fragments).",
        "",
    ]
    for n in names:
        rows = [r for i, r in _labels(n).items() if i in full and r["label"] in ("supported", "partial") and r["quote"]]
        found = 0
        for r in rows:
            item = items[r["id"]]
            haystack = _normalize(" ".join(item["passages"]) + " " + _page(item["url"])["text"])
            fragments = [f for f in (_normalize(f.strip(" .")) for f in re.split(r"\.\.\.|…", r["quote"])) if f]
            found += all(f in haystack for f in fragments)
        lines.append(f"- {n}: {found} of {len(rows)} ({found / len(rows):.0%})" if rows else f"- {n}: no quotes")
    lines.append("\nClaude read some pages through its own fetcher or another copy of the document, so a quote it found there can be missing from this fetch.")
    REPORT.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("sample")
    sub.add_parser("pages")
    p = sub.add_parser("label")
    p.add_argument("labeler", choices=list(LABELERS))
    p.add_argument("--limit", type=int, default=None, help="batches to run")
    sub.add_parser("report")
    args = parser.parse_args()
    if args.command == "sample":
        sample()
    elif args.command == "pages":
        pages()
    elif args.command == "label":
        label(args.labeler, args.limit)
    else:
        report()


if __name__ == "__main__":
    main()
