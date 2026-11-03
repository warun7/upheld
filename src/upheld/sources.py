"""Fetch cited sources and decide whether each one exists.

A dead link (404/410, or a domain that doesn't resolve) is checked against
the Wayback Machine: an archived copy means link rot, no copy at all means the
URL most likely never existed. Other failures (401, 403, 429, 5xx, timeouts, a
block page) only say the page couldn't be read, not that it's fake. In both
cases the newest archived copy, if there is one, is read instead.
"""

import asyncio
import ipaddress
import os
import re
import socket
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from typing import Literal
from urllib.parse import urlparse

import httpx
import trafilatura
from pypdf import PdfReader

from upheld.models import LinkStatus, Source

# Some sites (Wikipedia included) reject generic agents, so deployments should
# set this to include a project URL or contact address.
USER_AGENT = os.environ.get("UPHELD_USER_AGENT", "upheld/0.1 (+https://github.com/warun7/upheld)")
MAX_BYTES = 5_000_000
TIMEOUT = 15.0
GONE = {404, 410}
# Less readable text than this means a stand-in was served instead of the page: in the fresh
# benchmark every such page was a cookie wall, a VPN or bot check, or a JavaScript app whose
# text only loads in a browser. The shortest real page there had 647 characters.
MIN_TEXT_CHARS = 300
# Archive lookups and fetches in flight at once per audit, to stay well inside the Wayback Machine's rate limits.
ARCHIVE_CONCURRENCY = 4
# Gemini cites pages through redirect links on this host, which expire after a while.
GEMINI_REDIRECT_HOST = "vertexaisearch.cloud.google.com"


@dataclass
class FetchedSource:
    source: Source
    status: LinkStatus
    text: str = ""
    http_status: int | None = None
    note: str | None = None
    archived_at: datetime | None = None  # set when the text comes from an archived copy
    archive_url: str | None = None
    resolved_url: str | None = None  # where the URL redirected to, if it did


class BlockedURL(ValueError):
    pass


class UnknownHost(BlockedURL):
    pass


def check_url_allowed(url: str, allow_private: bool = False) -> None:
    """Reject non-http schemes and, unless allowed, private or local addresses.

    A hosted auditor fetches URLs taken from untrusted answer text, so this
    stops it from being pointed at internal services or cloud metadata.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise BlockedURL(f"unsupported URL: {url}")
    if allow_private:
        return
    try:
        infos = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror as e:
        raise UnknownHost(f"domain {parsed.hostname} does not resolve") from e
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise BlockedURL(f"{parsed.hostname} resolves to non-public address {ip}")


def extract_text(html: str, url: str) -> str:
    text = trafilatura.extract(html, url=url, include_tables=True, include_comments=False, favor_recall=True)
    return text or ""


def extract_pdf_text(data: bytes) -> str:
    try:
        pages = [page.extract_text() or "" for page in PdfReader(BytesIO(data)).pages]
    except Exception:  # pypdf raises many types on damaged files
        return ""
    compounds = {word.lower() for page in pages for word in _COMPOUND.findall(page)}
    return "\n\n".join(text for text in (unwrap(page, compounds) for page in pages) if text)


_COMPOUND = re.compile(r"(?<![A-Za-z])(?=([A-Za-z]+-[a-z]+))")  # each hyphenated pair, overlapping: non-small-cell gives non-small, small-cell
_BROKEN_WORD = re.compile(r"([A-Za-z]+)-[ \t]*\n\s*([a-z]+)")


def unwrap(text: str, compounds: set[str] | frozenset[str] = frozenset()) -> str:
    """Undo a PDF's line wrapping: join wrapped lines, and words broken across lines at a hyphen.

    A broken word is joined up (cardio-/vascular -> cardiovascular) unless the
    document writes it with a hyphen elsewhere (low-/dose -> low-dose); compounds
    holds those hyphenated words, lowercased.
    """
    rejoin = lambda m: f"{m[1]}-{m[2]}" if f"{m[1]}-{m[2]}".lower() in compounds else m[1] + m[2]  # noqa: E731
    text = _BROKEN_WORD.sub(rejoin, text)
    text = re.sub(r"(?<=\w)-[ \t]*\n\s*", "-", text)  # COVID-\n19 -> COVID-19
    return " ".join(text.split())


async def _wayback_snapshot(client: httpx.AsyncClient, url: str) -> tuple[str, str] | Literal[False] | None:
    """(timestamp, original URL) of the newest copy archived with HTTP 200, False if there is none, None if the lookup failed."""
    # The CDX API is less aggressively rate-limited than /wayback/available.
    params = {"url": url, "filter": "statuscode:200", "limit": -1, "fl": "timestamp,original", "output": "json"}
    try:
        r = await client.get("https://web.archive.org/cdx/search/cdx", params=params)
        r.raise_for_status()
        rows = r.json()  # [] when nothing is archived, else a header row plus results
        return (rows[1][0], rows[1][1]) if len(rows) > 1 else False
    except (httpx.HTTPError, ValueError, IndexError):
        return None


async def _get_capped(client: httpx.AsyncClient, url: str) -> tuple[httpx.Response, bytes]:
    async with client.stream("GET", url) as r:
        body = bytearray()
        async for chunk in r.aiter_bytes():
            body.extend(chunk)
            if len(body) > MAX_BYTES:
                break
        return r, bytes(body)


async def _extract(response: httpx.Response, body: bytes, url: str) -> tuple[str, str | None]:
    """The document's text, or why the document itself can't be read (so an archived copy of it couldn't be either)."""
    content_type = response.headers.get("content-type", "")
    if "pdf" in content_type or body.startswith(b"%PDF-"):
        # A PDF cut off at the cap has lost the index at its end and won't parse.
        if len(body) > MAX_BYTES:
            return "", f"PDF over {MAX_BYTES // 1_000_000} MB"
        text = await asyncio.to_thread(extract_pdf_text, body)
        if len(text) < MIN_TEXT_CHARS:
            return "", f"PDF had {len(text)} characters of text: likely a scan with no text layer, or a damaged file"
        return text, None
    if "html" not in content_type and "text" not in content_type:
        return "", f"unsupported content type: {content_type or 'unknown'}"
    html = body.decode(response.encoding or "utf-8", errors="replace")
    return await asyncio.to_thread(extract_text, html, url), None


def _stand_in(text: str) -> str | None:
    """Why the page looks like something served in place of the real one, if it does."""
    if not (chars := len(text.strip())):
        return "page had no extractable text"
    if chars < MIN_TEXT_CHARS:
        return f"page had only {chars} characters of text: likely a cookie wall, bot check or page that needs JavaScript"
    return None


async def fetch_source(
    client: httpx.AsyncClient, source: Source, allow_private: bool = False, archive_slots: asyncio.Semaphore | None = None
) -> FetchedSource:
    if source.text:
        return FetchedSource(source, LinkStatus.PROVIDED, source.text)
    if not source.url:
        return FetchedSource(source, LinkStatus.UNREACHABLE, note="no URL or text given")

    http_status, dead, resolved = None, False, None
    try:
        response, body = await _get_capped(client, source.url)
    except UnknownHost as e:
        reason, dead = str(e), True
    except BlockedURL as e:
        return FetchedSource(source, LinkStatus.UNREACHABLE, note=str(e))
    except httpx.HTTPError as e:
        reason = f"request failed: {type(e).__name__}"
    else:
        http_status = response.status_code
        if str(response.url) != str(httpx.URL(source.url)):
            resolved = str(response.url)
        if urlparse(str(response.url)).hostname == GEMINI_REDIRECT_HOST and http_status >= 400:
            note = f"HTTP {http_status}: Gemini's redirect link no longer resolves (they expire), so the cited page is unknown"
            return FetchedSource(source, LinkStatus.UNREACHABLE, http_status=http_status, note=note)
        if http_status in GONE:
            reason, dead = f"HTTP {http_status}", True
        elif http_status >= 400:
            reason = f"HTTP {http_status} ({'blocked or rate-limited' if http_status in (401, 403, 429) else 'server error'})"
        else:
            text, problem = await _extract(response, body, str(response.url))
            if problem:
                return FetchedSource(source, LinkStatus.UNREACHABLE, http_status=http_status, note=problem, resolved_url=resolved)
            if not (reason := _stand_in(text)):
                return FetchedSource(source, LinkStatus.LIVE, text, http_status=http_status, resolved_url=resolved)
    # The Wayback Machine has the page a Gemini redirect leads to, not the redirect.
    archived = resolved if resolved and urlparse(source.url).hostname == GEMINI_REDIRECT_HOST else source.url
    async with archive_slots or nullcontext():
        fetched = await _from_archive(client, source, archived, http_status, reason, dead)
    fetched.resolved_url = resolved
    return fetched


async def _from_archive(client: httpx.AsyncClient, source: Source, url: str, http_status: int | None, reason: str, dead: bool) -> FetchedSource:
    """Read the newest archived copy of a page that is dead or couldn't be read live."""
    snapshot = await _wayback_snapshot(client, url)
    if snapshot is None:
        return FetchedSource(source, LinkStatus.UNREACHABLE, http_status=http_status, note=f"{reason}; archive check failed")
    if snapshot is False:
        status = LinkStatus.LIKELY_FABRICATED if dead else LinkStatus.UNREACHABLE
        return FetchedSource(source, status, http_status=http_status, note=f"{reason}; never archived")

    timestamp, original = snapshot
    archived_at = datetime.strptime(timestamp, "%Y%m%d%H%M%S").replace(tzinfo=UTC)
    copy = f"Wayback Machine copy of {archived_at:%Y-%m-%d}"
    text, problem = "", None
    try:
        # id_ serves the page as archived, without the Wayback Machine's toolbar or rewritten links.
        response, body = await _get_capped(client, f"https://web.archive.org/web/{timestamp}id_/{original}")
    except (httpx.HTTPError, ValueError) as e:  # BlockedURL is a ValueError
        problem = f"request failed: {type(e).__name__}"
    else:
        if response.status_code >= 400:
            problem = f"HTTP {response.status_code}"
        else:
            text, problem = await _extract(response, body, original)
            problem = problem or _stand_in(text)
    if problem:
        status = LinkStatus.LINK_ROT if dead else LinkStatus.UNREACHABLE
        failed = f"so did the {copy}" if problem == reason else f"{copy} couldn't be read: {problem}"
        return FetchedSource(source, status, http_status=http_status, note=f"{reason}; {failed}")
    return FetchedSource(
        source,
        LinkStatus.LINK_ROT if dead else LinkStatus.ARCHIVED,
        text,
        http_status=http_status,
        note=f"{reason}; read from the {copy}",
        archived_at=archived_at,
        archive_url=f"https://web.archive.org/web/{timestamp}/{original}",
    )


async def fetch_all(sources: list[Source], allow_private: bool = False) -> dict[str, FetchedSource]:
    async def guard(request: httpx.Request) -> None:
        # Runs on every request, redirects included. DNS rebinding between this
        # check and the connection is not covered.
        await asyncio.to_thread(check_url_allowed, str(request.url), allow_private)

    headers = {"User-Agent": USER_AGENT}
    hooks = {"request": [guard]}
    archive_slots = asyncio.Semaphore(ARCHIVE_CONCURRENCY)
    async with httpx.AsyncClient(follow_redirects=True, timeout=TIMEOUT, headers=headers, event_hooks=hooks) as client:
        results = await asyncio.gather(*(fetch_source(client, s, allow_private, archive_slots) for s in sources))
    return {r.source.id: r for r in results}
