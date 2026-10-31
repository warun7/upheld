"""Collect cited answers from AI search APIs for the fresh 2026 benchmark.

Each provider's answer is converted to upheld's input format: markdown with
[n] markers after each cited span, plus a numbered source list. That way the
labeling step audits every provider through the same parser.

    uv sync --extra collect
    export PERPLEXITY_API_KEY=... OPENAI_API_KEY=... GEMINI_API_KEY=... ANTHROPIC_API_KEY=...
    uv run python evals/fresh/collect.py perplexity openai gemini claude --limit 25

Writes evals/fresh/answers/<provider>.jsonl (one answer per question, resumable)
and the raw API responses to evals/fresh/raw/. Every call costs money; --limit
caps how many questions each provider gets.

Default model names were current when this was written. Check each provider's
docs and pass --model if one has been retired.
"""

import argparse
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path

import httpx

HERE = Path(__file__).parent
QUESTIONS = HERE / "questions.txt"
ANSWERS = HERE / "answers"
RAW = HERE / "raw"
TIMEOUT = 300

DEFAULT_MODELS = {
    "perplexity": "sonar-pro",
    "openai": "gpt-5",
    "gemini": "gemini-2.5-flash",
    "claude": "claude-opus-5-5",
}


def with_markers(spans: list[tuple[str, list[tuple[str, str | None]]]]) -> tuple[str, list[dict]]:
    """Join (text, [(url, title), ...]) spans into markdown with [n] markers and a source list."""
    ids: dict[str, int] = {}
    sources: list[dict] = []
    out = []
    for text, cited in spans:
        markers = []
        for url, title in cited:
            if url not in ids:
                ids[url] = len(ids) + 1
                sources.append({"id": str(ids[url]), "url": url, "title": title})
            markers.append(f"[{ids[url]}]")
        out.append(_attach(text, "".join(dict.fromkeys(markers))))
    return "".join(out), sources


def _attach(text: str, markers: str) -> str:
    """Put markers before the span's trailing punctuation and whitespace: 'X is Y [1]. '"""
    if not markers:
        return text
    m = re.search(r"[\s.,;:!?]*$", text)
    return f"{text[: m.start()]} {markers}{text[m.start():]}"


def perplexity(question: str, model: str) -> tuple[dict, str, list[dict]]:
    r = httpx.post(
        "https://api.perplexity.ai/chat/completions",
        headers={"Authorization": f"Bearer {os.environ['PERPLEXITY_API_KEY']}"},
        json={"model": model, "messages": [{"role": "user", "content": question}]},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    raw = r.json()
    # Sonar already writes [n] markers that index into its 1-based citation list.
    answer = raw["choices"][0]["message"]["content"]
    results = raw.get("search_results") or [{"url": u} for u in raw.get("citations", [])]
    sources = [{"id": str(i), "url": s["url"], "title": s.get("title")} for i, s in enumerate(results, 1)]
    return raw, answer, sources


def openai(question: str, model: str) -> tuple[dict, str, list[dict]]:
    r = httpx.post(
        "https://api.openai.com/v1/responses",
        headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
        json={"model": model, "input": question, "tools": [{"type": "web_search"}]},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    raw = r.json()
    spans: list[tuple[str, list[tuple[str, str | None]]]] = []
    for item in raw["output"]:
        for part in item.get("content") or [] if item.get("type") == "message" else []:
            if part.get("type") != "output_text":
                continue
            text, pos = part["text"], 0
            for a in sorted((a for a in part.get("annotations", []) if a["type"] == "url_citation"), key=lambda a: a["end_index"]):
                spans.append((text[pos : a["end_index"]], [(a["url"], a.get("title"))]))
                pos = a["end_index"]
            spans.append((text[pos:], []))
    answer, sources = with_markers(spans)
    return raw, answer, sources


def gemini(question: str, model: str) -> tuple[dict, str, list[dict]]:
    r = httpx.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]},
        json={"contents": [{"parts": [{"text": question}]}], "tools": [{"google_search": {}}]},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    raw = r.json()
    candidate = raw["candidates"][0]
    text = "".join(p.get("text", "") for p in candidate["content"]["parts"])
    meta = candidate.get("groundingMetadata", {})
    chunks = [c.get("web", {}) for c in meta.get("groundingChunks", [])]
    # Segment offsets are UTF-8 byte offsets. Chunk URIs are Google redirect links;
    # upheld's fetcher follows them to the real page.
    data = text.encode()
    spans, pos = [], 0
    for support in sorted(meta.get("groundingSupports", []), key=lambda s: s["segment"].get("endIndex", 0)):
        end = support["segment"].get("endIndex", 0)
        if end <= pos:
            continue
        cited = [(chunks[i]["uri"], chunks[i].get("title")) for i in support.get("groundingChunkIndices", []) if chunks[i].get("uri")]
        spans.append((data[pos:end].decode(errors="ignore"), cited))
        pos = end
    spans.append((data[pos:].decode(errors="ignore"), []))
    answer, sources = with_markers(spans)
    return raw, answer, sources


def claude(question: str, model: str) -> tuple[dict, str, list[dict]]:
    import anthropic

    client = anthropic.Anthropic()
    messages: list = [{"role": "user", "content": question}]
    for _ in range(5):  # resume pause_turn a few times at most
        response = client.beta.messages.create(
            model=model,
            max_tokens=16000,
            messages=messages,
            tools=[{"type": "web_search_20260318", "name": "web_search"}],
            output_config={"effort": "medium"},
            # On a policy decline, re-run on a fallback model chosen by refusal category.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        if response.stop_reason != "pause_turn":
            break
        messages = [{"role": "user", "content": question}, {"role": "assistant", "content": response.content}]
    raw = response.to_dict()
    if response.stop_reason == "refusal":
        raise RuntimeError(f"refused: {response.stop_details}")

    # The final answer is the text after the last tool block; earlier text is narration ("I'll search...").
    blocks = list(response.content)
    last_tool = max((i for i, b in enumerate(blocks) if b.type not in ("text", "thinking", "fallback")), default=-1)
    spans = [
        (b.text, [(c.url, c.title) for c in b.citations or [] if c.type == "web_search_result_location"])
        for b in blocks[last_tool + 1 :]
        if b.type == "text"
    ]
    answer, sources = with_markers(spans)
    return raw, answer, sources


PROVIDERS = {"perplexity": perplexity, "openai": openai, "gemini": gemini, "claude": claude}
KEYS = {"perplexity": "PERPLEXITY_API_KEY", "openai": "OPENAI_API_KEY", "gemini": "GEMINI_API_KEY", "claude": "ANTHROPIC_API_KEY"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("providers", nargs="+", choices=list(PROVIDERS))
    parser.add_argument("--limit", type=int, default=None, help="questions per provider (each one costs money)")
    parser.add_argument("--model", default=None, help="override the default model (only with a single provider)")
    args = parser.parse_args()
    if args.model and len(args.providers) > 1:
        parser.error("--model applies to one provider at a time")

    questions = [q.strip() for q in QUESTIONS.read_text().splitlines() if q.strip() and not q.startswith("#")][: args.limit]
    ANSWERS.mkdir(exist_ok=True)
    RAW.mkdir(exist_ok=True)
    for provider in args.providers:
        if provider != "claude" and not os.environ.get(KEYS[provider]):
            print(f"{provider}: {KEYS[provider]} not set, skipping")
            continue
        model = args.model or DEFAULT_MODELS[provider]
        out = ANSWERS / f"{provider}.jsonl"
        done = {json.loads(line)["question"] for line in out.read_text().splitlines()} if out.exists() else set()
        for n, question in enumerate(questions):
            if question in done:
                continue
            try:
                raw, answer, sources = PROVIDERS[provider](question, model)
            except (httpx.HTTPError, KeyError, RuntimeError) as e:
                print(f"{provider} q{n}: failed ({e!r})")
                continue
            stamp = datetime.now(UTC).isoformat(timespec="seconds")
            (RAW / f"{provider}-{n:03d}.json").write_text(json.dumps(raw))
            record = {"provider": provider, "model": raw.get("model", model), "question": question, "answer": answer, "sources": sources, "collected_at": stamp}
            with out.open("a") as f:
                f.write(json.dumps(record) + "\n")
            print(f"{provider} q{n}: {len(sources)} sources")


if __name__ == "__main__":
    main()
