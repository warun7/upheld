"""Collect cited answers for the fresh 2026 benchmark.

Each provider answers with its own web search, and every answer ends up in
upheld's input format: markdown with [n] markers after each cited span, plus a
numbered source list. That way the labeling step audits every provider through
the same parser.

OpenAI and Gemini answer through their command-line agents, which run on a
ChatGPT or Google subscription rather than a paid API. Each gets the
instructions Claude got, one question per call, and may use only web search:

    uv run python evals/fresh/collect.py openai gemini --limit 25

- openai: Codex CLI (`codex`), gpt-6-luna, with OpenAI's web search.
- gemini: Antigravity CLI (`agy`), Gemini 3.8 Flash, with its search_web tool.
- perplexity: Sonar Pro through OpenRouter, since Perplexity has no subscription
  CLI. Needs OPENROUTER_API_KEY and costs about a cent per question.

Claude's answers came from Claude Sonnet 5.5 subagents in Claude Code, using its
WebSearch tool with the same instructions in batches of five, and are in
answers/claude.jsonl.

Writes answers/<provider>.jsonl (one answer per question, resumable) and each
raw response to raw/. A response is saved before it is converted, so one that
fails to convert is converted again from raw/ on the next run without asking again.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

HERE = Path(__file__).parent
QUESTIONS = HERE / "questions.txt"
ANSWERS = HERE / "answers"
RAW = HERE / "raw"
TIMEOUT = 300

# Mid-tier or fast models, so the scoreboard compares search and citation rather than price tiers.
DEFAULT_MODELS = {
    "openai": "gpt-6-luna",
    "gemini": "gemini-3.8-flash-medium",
    "perplexity": "perplexity/sonar-pro",
}
VIA = {
    "openai": "Codex CLI, web search",
    "gemini": "Antigravity CLI, search_web tool",
    "perplexity": "OpenRouter, Sonar's own search",
}

# What Claude's subagents were told, for one question at a time.
PROMPT = """Answer the question below the way an AI search assistant answers a user: search the web, then write the answer with inline citations.

Rules:
- Use only your web search tool. Do not run shell commands, fetch pages any other way, or read or write files.
- Write the answer as you normally would for a user. Put citation markers like [1] or [1][2] right after the sentences that use information from a source, numbering the sources from 1. Do not add a references section inside the answer text.
- List the sources you cited, numbered to match, with the exact URL from the search results and its title.

Your final message must be only a JSON object (no prose before or after, no code fence):
{"answer": "<answer text with [n] markers>", "sources": [{"id": "1", "url": "https://...", "title": "..."}]}

Question: """

_SOURCE = {
    "type": "object",
    "additionalProperties": False,
    "required": ["id", "url", "title"],
    "properties": {"id": {"type": "string"}, "url": {"type": "string"}, "title": {"type": "string"}},
}
SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["answer", "sources"],
    "properties": {"answer": {"type": "string"}, "sources": {"type": "array", "items": _SOURCE}},
}
_MARKER = re.compile(r"\[(\d+)\]")


def clean(url: str) -> str:
    """Drop utm_ parameters. OpenAI tags links utm_source=openai, which would tell the labeler who cited the page."""
    parts = urlsplit(url)
    query = parse_qsl(parts.query, keep_blank_values=True)
    if not any(k.startswith("utm_") for k, _ in query):
        return url
    return urlunsplit(parts._replace(query=urlencode([(k, v) for k, v in query if not k.startswith("utm_")])))


def _parse(response: str) -> dict:
    """The JSON reply. agy sometimes repeats it, so repeated copies are accepted, but not two different replies."""
    decoder, text, pos, replies = json.JSONDecoder(), response.strip(), 0, []
    while pos < len(text):
        reply, pos = decoder.raw_decode(text, pos)
        replies.append(reply)
        pos = len(text) - len(text[pos:].lstrip())
    if not replies or any(r != replies[0] for r in replies):
        raise ValueError(f"expected one JSON reply, got {len(replies)} different ones")
    return replies[0]


def _reply(response: str, tools: list[str], search: str) -> dict:
    """The agent's JSON reply, provided it searched, used nothing else, and every marker has a source."""
    if others := sorted(set(tools) - {search}):
        raise RuntimeError(f"used {others} as well as search")
    if search not in tools:
        raise RuntimeError("answered without searching")
    reply = _parse(response)
    if missing := set(_MARKER.findall(reply["answer"])) - {s["id"] for s in reply["sources"]}:
        raise RuntimeError(f"markers {sorted(missing)} have no source")
    return reply


def ask_codex(question: str, model: str) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        schema, last, work = Path(tmp, "schema.json"), Path(tmp, "last.txt"), Path(tmp, "work")
        schema.write_text(json.dumps(SCHEMA))
        work.mkdir()
        # An empty read-only directory and no user config (so no MCP servers): web search is the only tool that reaches out.
        r = subprocess.run(
            ["codex", "--search", "exec", "--model", model, "-c", 'model_reasoning_effort="medium"',
             "--sandbox", "read-only", "--ignore-user-config", "--ignore-rules", "--ephemeral", "--skip-git-repo-check",
             "--cd", str(work), "--output-schema", str(schema), "--json", "--output-last-message", str(last), "-"],
            input=PROMPT + question, capture_output=True, text=True, timeout=TIMEOUT,
        )
        if r.returncode:
            raise RuntimeError(f"codex exited {r.returncode}: {r.stderr.strip()[-300:]}")
        events = [json.loads(line) for line in r.stdout.splitlines() if line.strip()]
        response = last.read_text()
    tools = [e["item"]["type"] for e in events if e.get("type") == "item.completed" and e["item"]["type"] not in ("agent_message", "reasoning")]
    _reply(response, tools, "web_search")
    return {"events": events, "response": response}


def ask_agy(question: str, model: str) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        schema, work = Path(tmp, "schema.json"), Path(tmp, "work")
        schema.write_text(json.dumps(SCHEMA))
        work.mkdir()
        r = subprocess.run(
            ["agy", "--print", PROMPT + question, "--model", model, "--sandbox", "--output-format", "stream-json",
             "--json-schema", str(schema), "--print-timeout", f"{TIMEOUT}s"],
            cwd=work, capture_output=True, text=True, timeout=TIMEOUT + 60,
        )
    if r.returncode:
        raise RuntimeError(f"agy exited {r.returncode}: {r.stderr.strip()[-300:]}")
    events = [json.loads(line) for line in r.stdout.splitlines() if line.strip()]
    result = next((e["result"] for e in events if e.get("event") == "result"), {})
    if result.get("status") != "SUCCESS":
        raise RuntimeError(f"agy did not finish: {str(result)[:300]}")
    steps = [e["step_update"] for e in events if "step_update" in e]
    tools = [s["tool_name"] for s in steps if s.get("step_type") == "tool" and s.get("state") == "DONE"]
    reply = _reply(result["response"], tools, "search_web")
    # Gemini cites Google redirect links, which expire and would tell the labeler who
    # cited the page, so they are resolved now and the real URLs kept with the response.
    resolved = {}
    for s in reply["sources"]:
        if urlsplit(s["url"]).hostname == "vertexaisearch.cloud.google.com":
            r = httpx.get(s["url"], follow_redirects=False, timeout=30)
            if not r.headers.get("location"):
                raise RuntimeError(f"redirect for source {s['id']} did not resolve (HTTP {r.status_code})")
            resolved[s["url"]] = r.headers["location"]
    return {"events": events, "response": result["response"], "resolved": resolved}


def ask_openrouter(question: str, model: str) -> dict:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        sys.exit("OPENROUTER_API_KEY is not set (Perplexity goes through OpenRouter)")
    # Sonar searches on every call, so no web plugin is needed (asking for one got a 404).
    r = httpx.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={"model": model, "messages": [{"role": "user", "content": question}]},
        timeout=TIMEOUT,
    )
    if r.is_error:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:500]}")
    raw = r.json()
    if not raw["choices"][0]["message"].get("content"):
        raise RuntimeError(f"no answer text (finish_reason {raw['choices'][0].get('finish_reason')})")
    return raw


ASK = {"openai": ask_codex, "gemini": ask_agy, "perplexity": ask_openrouter}


def convert(raw: dict, provider: str) -> tuple[str, list[dict]]:
    """One saved response as an answer with [n] markers and the sources it cites."""
    if provider == "perplexity":
        # Sonar writes its own [n] markers into its list of search results, which
        # OpenRouter passes on as one annotation per result in the same order.
        message = raw["choices"][0]["message"]
        answer = message["content"]
        cites = [a["url_citation"] for a in message.get("annotations") or [] if a.get("type") == "url_citation"]
        sources = [{"id": str(i), "url": c["url"], "title": c.get("title")} for i, c in enumerate(cites, 1)]
    else:
        reply = _parse(raw["response"])
        answer = reply["answer"]
        sources = [{**s, "url": raw.get("resolved", {}).get(s["url"], s["url"])} for s in reply["sources"]]
    cited = set(_MARKER.findall(answer))
    return answer, [{**s, "url": clean(s["url"])} for s in sources if s["id"] in cited]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("providers", nargs="+", choices=list(DEFAULT_MODELS))
    parser.add_argument("--limit", type=int, default=None, help="questions per provider")
    parser.add_argument("--model", default=None, help="override the default model (only with a single provider)")
    args = parser.parse_args()
    if args.model and len(args.providers) > 1:
        parser.error("--model applies to one provider at a time")

    questions = [q.strip() for q in QUESTIONS.read_text().splitlines() if q.strip() and not q.startswith("#")][: args.limit]
    ANSWERS.mkdir(exist_ok=True)
    RAW.mkdir(exist_ok=True)
    for provider in args.providers:
        model = args.model or DEFAULT_MODELS[provider]
        out = ANSWERS / f"{provider}.jsonl"
        done = {json.loads(line)["question"] for line in out.read_text().splitlines()} if out.exists() else set()
        for n, question in enumerate(questions):
            if question in done:
                continue
            saved = RAW / f"{provider}-{n:03d}.json"
            try:
                if saved.exists():
                    raw = json.loads(saved.read_text())
                else:
                    raw = ASK[provider](question, model) | {"model_asked": model, "collected_at": datetime.now(UTC).isoformat(timespec="seconds")}
                    saved.write_text(json.dumps(raw))
                answer, sources = convert(raw, provider)
            except (httpx.HTTPError, subprocess.TimeoutExpired, KeyError, ValueError, RuntimeError) as e:
                print(f"{provider} q{n}: failed ({e})", flush=True)
                continue
            record = {
                "provider": provider,
                "model": f"{raw.get('model_asked', model)} ({VIA[provider]})",
                "question": question,
                "answer": answer,
                "sources": sources,
                "collected_at": raw.get("collected_at") or datetime.fromtimestamp(raw["created"], UTC).isoformat(timespec="seconds"),
            }
            with out.open("a") as f:
                f.write(json.dumps(record) + "\n")
            print(f"{provider} q{n}: {len(sources)} sources", flush=True)


if __name__ == "__main__":
    main()
