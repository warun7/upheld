"""Read an AI provider's own response: its answer, the sources it cites, and where.

Each provider marks citations its own way:
  - OpenAI (Responses API, or Chat Completions with web search): url_citation
    annotations whose range covers the link the model wrote after the claim.
    The link becomes an [n] marker and the answer is split into sentences.
  - Anthropic (Messages with web search): text blocks whose citations hold
    web_search_result_location entries. Each cited block is a claim.
  - Perplexity (Sonar, or the Agent API): [n] or [web:n] markers in the text,
    numbered into search_results (or the older citations list).
  - Gemini (generateContent with Google Search): groundingSupports, each a
    byte range of the text with indices into groundingChunks. Each range is a
    claim. The chunks' URLs are redirects, which fetching follows. The
    Interactions API's url_citation annotations cover the cited text instead.

A response can be the provider SDK's object, its JSON as a dict, or a JSON string.
"""

import json
import re
from enum import StrEnum
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from upheld.models import AuditRequest, CitedSpan, Source
from upheld.parse import _MARKER, _MD_LINK


class Provider(StrEnum):
    AUTO = "auto"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    PERPLEXITY = "perplexity"
    GEMINI = "gemini"


def from_response(response: Any, provider: Provider | str = Provider.AUTO, *, question: str | None = None) -> AuditRequest:
    data = _as_dict(response)
    provider = Provider(provider)
    if provider == Provider.AUTO:
        provider = detect(data)
    return READERS[provider](data, question=question)


def detect(data: dict) -> Provider:
    """Which provider's API a response came from, by its shape."""
    if "candidates" in data or "steps" in data:
        return Provider.GEMINI
    if isinstance(data.get("output"), list):
        return Provider.PERPLEXITY if any(item.get("type") == "search_results" for item in data["output"]) else Provider.OPENAI
    if isinstance(data.get("choices"), list):
        model = str(data.get("model", "")).lower()
        if "search_results" in data or "citations" in data or "sonar" in model or "perplexity" in model:
            return Provider.PERPLEXITY
        return Provider.OPENAI
    if isinstance(data.get("content"), list) and data.get("role") == "assistant":
        return Provider.ANTHROPIC
    raise ValueError("can't tell which provider this response is from: name it (openai, anthropic, perplexity or gemini)")


def from_openai(response: Any, *, question: str | None = None) -> AuditRequest:
    data = _as_dict(response)
    parts: list[tuple[str, list[dict]]] = []
    if isinstance(data.get("output"), list):  # Responses API
        for item in data["output"]:
            if item.get("type") == "message":
                parts += [(p.get("text") or "", p.get("annotations") or []) for p in item.get("content") or [] if p.get("type") == "output_text"]
    elif isinstance(data.get("choices"), list):  # Chat Completions
        message = data["choices"][0]["message"]
        annotations = [a.get("url_citation") or {} for a in message.get("annotations") or [] if a.get("type") == "url_citation"]
        parts.append((message.get("content") or "", [{**a, "type": "url_citation"} for a in annotations]))
    else:
        raise ValueError("not an OpenAI response: expected `output` (Responses API) or `choices` (Chat Completions)")

    sources = _Numbering()
    texts = []
    for text, annotations in parts:
        cites = []
        for a in annotations:
            if a.get("type") == "url_citation" and a.get("url"):
                start, end = _link_at(text, a["url"], a.get("start_index") or 0, a.get("end_index") or 0)
                cites.append((start, end, sources.id(_without_utm(a["url"]), a.get("title"))))
        texts.append(_with_markers(text, cites))
    return _request("openai", "\n\n".join(texts), sources.list(), [], question)


def _without_utm(url: str) -> str:
    """OpenAI tags every link utm_source=openai, which keeps the Wayback Machine from finding the page."""
    parts = urlsplit(url)
    query = parse_qsl(parts.query, keep_blank_values=True)
    if not any(k.startswith("utm_") for k, _ in query):
        return url
    return urlunsplit(parts._replace(query=urlencode([(k, v) for k, v in query if not k.startswith("utm_")])))


def _link_at(text: str, url: str, start: int, end: int) -> tuple[int, int]:
    """The markdown link to the citation's URL nearest its range, else the range itself.

    The link is what the range should cover, and finding it still works if the
    offsets were counted in other units than Python's characters.
    """
    if not (links := [m for m in _MD_LINK.finditer(text) if m[2] == url]):
        return start, end
    nearest = min(links, key=lambda m: abs(m.start() - start))
    return nearest.start(), nearest.end()


def from_anthropic(response: Any, *, question: str | None = None) -> AuditRequest:
    data = _as_dict(response)
    blocks = data.get("content")
    if not isinstance(blocks, list):
        raise ValueError("not an Anthropic message: expected a `content` list of blocks")

    # Text before the first cited passage narrates the searches ("I'll search for ..."), so the answer
    # starts with the run of text blocks that holds the first citation.
    first_cited = next((i for i, b in enumerate(blocks) if b.get("type") == "text" and b.get("citations")), len(blocks))
    start = max((i + 1 for i, b in enumerate(blocks[:first_cited]) if b.get("type") != "text"), default=0)

    sources = _Numbering()
    answer, spans, after_text = "", [], True
    for block in blocks[start:]:
        if block.get("type") != "text":
            after_text = False
            continue
        if not after_text and answer:
            answer += "\n\n"
        after_text = True
        text = block.get("text") or ""
        ids = [
            sources.id(c["url"], c.get("title"))
            for c in block.get("citations") or []
            if c.get("type") == "web_search_result_location" and c.get("url")
        ]
        if ids and text.strip():
            spans.append(CitedSpan(start=len(answer), end=len(answer) + len(text), cited=list(dict.fromkeys(ids))))
        answer += text
    return _request("anthropic", answer, sources.list(), spans, question)


_TYPED_MARKER = re.compile(r"\[([a-z_]+):(\d+)\]")


def from_perplexity(response: Any, *, question: str | None = None) -> AuditRequest:
    data = _as_dict(response)
    if isinstance(data.get("output"), list):  # Agent API
        items = data["output"]
        text = "\n\n".join(
            p.get("text") or ""
            for item in items
            if item.get("type") == "message"
            for p in item.get("content") or []
            if p.get("type") == "output_text"
        )
        results: dict[str, dict] = {}
        for r in (r for item in items if item.get("type") == "search_results" for r in item.get("results") or []):
            results.setdefault(str(r.get("id", len(results) + 1)), r)
    elif isinstance(data.get("choices"), list):  # Sonar Chat Completions
        message = data["choices"][0]["message"]
        text = message.get("content") or ""
        listed = data.get("search_results") or [{"url": url} for url in data.get("citations") or []]
        if not listed:  # through OpenRouter: one url_citation per search result, in order
            listed = [a.get("url_citation") or {} for a in message.get("annotations") or [] if a.get("type") == "url_citation"]
        results = {str(n): r for n, r in enumerate(listed, 1)}
    else:
        raise ValueError("not a Perplexity response: expected `choices` (Sonar) or `output` (Agent API)")

    # The Agent API's presets cite web results as [web:1]; other kinds of marker point at no page.
    text = _TYPED_MARKER.sub(lambda m: f"[{m[2]}]" if m[1] == "web" else "", text)
    cited = {i.strip() for m in _MARKER.finditer(text) for i in (m[1] or m[2]).split(",")}
    sources = [Source(id=i, url=r["url"], title=r.get("title") or None) for i, r in results.items() if i in cited and r.get("url")]
    return _request("perplexity", text, sources, [], question)


def from_gemini(response: Any, *, question: str | None = None) -> AuditRequest:
    data = _as_dict(response)
    if isinstance(data.get("steps"), list):
        return _from_gemini_interaction(data, question)
    candidates = data.get("candidates")
    if not candidates:
        raise ValueError("not a Gemini response: expected `candidates` (generateContent) or `steps` (Interactions API)")
    candidate = candidates[0]
    parts = (candidate.get("content") or {}).get("parts") or []

    # The answer is the text parts, minus thought summaries. Segments index into one part, in UTF-8 bytes.
    answer, part_start = "", {}
    for i, part in enumerate(parts):
        if part.get("text") and not part.get("thought"):
            part_start[i] = len(answer)
            answer += part["text"]

    metadata = candidate.get("grounding_metadata") or {}
    chunks = [(c.get("web") or {}) for c in metadata.get("grounding_chunks") or []]
    sources: dict[str, Source] = {}
    ids_by_url: dict[str, str] = {}
    spans = []
    for support in metadata.get("grounding_supports") or []:
        segment = support.get("segment") or {}
        part = segment.get("part_index") or 0
        if part not in part_start:
            continue
        start, end = _segment_range(parts[part]["text"], segment)
        ids = []
        for index in support.get("grounding_chunk_indices") or []:
            web = chunks[index] if 0 <= index < len(chunks) else {}
            if not web.get("uri"):
                continue  # a map or image chunk, not a page
            source_id = ids_by_url.setdefault(web["uri"], str(index + 1))
            sources.setdefault(source_id, Source(id=source_id, url=web["uri"], title=web.get("title") or None))
            ids.append(source_id)
        if ids and start < end:
            spans.append(CitedSpan(start=part_start[part] + start, end=part_start[part] + end, cited=list(dict.fromkeys(ids))))
    return _request("gemini", answer, sorted(sources.values(), key=lambda s: int(s.id)), spans, question)


def _segment_range(text: str, segment: dict) -> tuple[int, int]:
    """A segment's byte range as a character range, checked against the text it quotes."""
    raw = text.encode()
    start = len(raw[: segment.get("start_index") or 0].decode(errors="ignore"))
    end = len(raw[: segment.get("end_index") or len(raw)].decode(errors="ignore"))
    quoted = segment.get("text")
    if quoted and text[start:end] != quoted and (found := text.find(quoted)) >= 0:
        start, end = found, found + len(quoted)
    return start, end


def _from_gemini_interaction(data: dict, question: str | None) -> AuditRequest:
    sources = _Numbering()
    answer, spans = "", []
    for step in data["steps"]:
        if step.get("type") != "model_output":
            continue
        if answer:
            answer += "\n\n"
        for block in step.get("content") or []:
            if block.get("type") != "text":
                continue
            text = block.get("text") or ""
            for a in block.get("annotations") or []:
                start, end = a.get("start_index") or 0, a.get("end_index") or 0
                if a.get("type") == "url_citation" and a.get("url") and 0 <= start < end <= len(text):
                    spans.append(CitedSpan(start=len(answer) + start, end=len(answer) + end, cited=[sources.id(a["url"], a.get("title"))]))
            answer += text
    return _request("gemini", answer, sources.list(), spans, question)


READERS = {
    Provider.OPENAI: from_openai,
    Provider.ANTHROPIC: from_anthropic,
    Provider.PERPLEXITY: from_perplexity,
    Provider.GEMINI: from_gemini,
}


class _Numbering:
    """Number sources 1, 2, ... in the order their URLs are first cited."""

    def __init__(self) -> None:
        self._sources: dict[str, Source] = {}

    def id(self, url: str, title: str | None = None) -> str:
        if url not in self._sources:
            self._sources[url] = Source(id=str(len(self._sources) + 1), url=url, title=title or None)
        return self._sources[url].id

    def list(self) -> list[Source]:
        return list(self._sources.values())


_URL = re.compile(r"https?://\S+")


def _with_markers(text: str, cites: list[tuple[int, int, str]]) -> str:
    """Put an [n] marker where each citation is. A link the model wrote there is replaced by its marker."""
    by_range: dict[tuple[int, int], list[str]] = {}
    for start, end, source_id in cites:
        start, end = max(0, min(start, len(text))), max(0, min(end, len(text)))
        ids = by_range.setdefault((start, max(start, end)), [])
        if source_id not in ids:
            ids.append(source_id)

    out, pos = [], 0
    for (start, end), ids in sorted(by_range.items()):
        markers = "".join(f"[{i}]" for i in ids)
        if start < pos:  # overlaps the previous citation's link: add to it
            out.append(markers)
            continue
        link = text[start:end]
        if not re.sub(r"[\s()\[\],.;]+", "", _URL.sub("", _MD_LINK.sub("", link))):
            if text[start - 1 : start] == "(" and text[end : end + 1] == ")":
                start, end = start - 1, end + 1
            out += [text[pos:start], markers]
        else:
            out += [text[pos:end], markers]
        pos = end
    out.append(text[pos:])
    return "".join(out)


def _request(provider: str, answer: str, sources: list[Source], spans: list[CitedSpan], question: str | None) -> AuditRequest:
    if not answer.strip():
        raise ValueError(f"no answer text in this {provider} response")
    return AuditRequest(question=question, answer=answer, sources=sources, cited_spans=spans)


def _as_dict(response: Any) -> dict:
    if isinstance(response, (str, bytes)):
        response = json.loads(response)
    elif hasattr(response, "model_dump"):  # the OpenAI, Anthropic, Perplexity and Google SDKs' objects are pydantic models
        response = response.model_dump(mode="json")
    elif hasattr(response, "to_dict"):
        response = response.to_dict()
    if not isinstance(response, dict):
        raise ValueError(f"expected a provider response or its JSON object, got {type(response).__name__}")
    return _snake_keys(response)


def _snake_keys(value: Any) -> Any:
    """Gemini's REST JSON is camelCase and its SDK's objects snake_case; read both as snake_case."""
    if isinstance(value, dict):
        return {re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", k).lower(): _snake_keys(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_snake_keys(v) for v in value]
    return value
