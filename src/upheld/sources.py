"""Fetch cited sources and decide whether each one exists.

A dead link (404/410, or a domain that doesn't resolve) is checked against
the Wayback Machine: an archived copy means link rot, no copy at all means the
URL most likely never existed. Other failures (403, 429, 5xx, timeouts) only
say the page couldn't be read, not that it's fake.
"""

import asyncio
import ipaddress
import os
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
import trafilatura

from upheld.models import LinkStatus, Source

# Some sites (Wikipedia included) reject generic agents, so deployments should
# set this to include a project URL or contact address.
USER_AGENT = os.environ.get("UPHELD_USER_AGENT", "upheld/0.1 (+https://github.com/warun7/upheld)")
MAX_BYTES = 5_000_000
TIMEOUT = 15.0
GONE = {404, 410}


@dataclass
class FetchedSource:
    source: Source
    status: LinkStatus
    text: str = ""
    http_status: int | None = None
    note: str | None = None


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


async def _wayback_has_copy(client: httpx.AsyncClient, url: str) -> bool | None:
    # The CDX API is less aggressively rate-limited than /wayback/available.
    try:
        r = await client.get("https://web.archive.org/cdx/search/cdx", params={"url": url, "limit": 1, "output": "json"})
        r.raise_for_status()
        rows = r.json()  # [] when nothing is archived, else a header row plus results
        return len(rows) > 1
    except (httpx.HTTPError, ValueError):
        return None


async def _get_capped(client: httpx.AsyncClient, url: str) -> tuple[httpx.Response, bytes]:
    async with client.stream("GET", url) as r:
        body = bytearray()
        async for chunk in r.aiter_bytes():
            body.extend(chunk)
            if len(body) > MAX_BYTES:
                break
        return r, bytes(body)


async def fetch_source(client: httpx.AsyncClient, source: Source, allow_private: bool = False) -> FetchedSource:
    if source.text:
        return FetchedSource(source, LinkStatus.PROVIDED, source.text)
    if not source.url:
        return FetchedSource(source, LinkStatus.UNREACHABLE, note="no URL or text given")

    try:
        response, body = await _get_capped(client, source.url)
    except UnknownHost as e:
        archived = await _wayback_has_copy(client, source.url)
        return _dead(source, None, archived, str(e))
    except BlockedURL as e:
        return FetchedSource(source, LinkStatus.UNREACHABLE, note=str(e))
    except httpx.HTTPError as e:
        return FetchedSource(source, LinkStatus.UNREACHABLE, note=f"request failed: {type(e).__name__}")

    if response.status_code in GONE:
        archived = await _wayback_has_copy(client, source.url)
        return _dead(source, response.status_code, archived, f"HTTP {response.status_code}")
    if response.status_code >= 400:
        reason = "blocked or rate-limited" if response.status_code in (401, 403, 429) else "server error"
        return FetchedSource(source, LinkStatus.UNREACHABLE, http_status=response.status_code, note=f"HTTP {response.status_code} ({reason})")

    content_type = response.headers.get("content-type", "")
    if "html" not in content_type and "text" not in content_type:
        return FetchedSource(
            source, LinkStatus.UNREACHABLE, http_status=response.status_code, note=f"unsupported content type: {content_type or 'unknown'}"
        )
    html = body.decode(response.encoding or "utf-8", errors="replace")
    text = await asyncio.to_thread(extract_text, html, str(response.url))
    if not text.strip():
        return FetchedSource(source, LinkStatus.UNREACHABLE, http_status=response.status_code, note="page had no extractable text")
    return FetchedSource(source, LinkStatus.LIVE, text, http_status=response.status_code)


def _dead(source: Source, http_status: int | None, archived: bool | None, reason: str) -> FetchedSource:
    if archived is True:
        return FetchedSource(source, LinkStatus.LINK_ROT, http_status=http_status, note=f"{reason}; archived copy exists")
    if archived is False:
        return FetchedSource(source, LinkStatus.LIKELY_FABRICATED, http_status=http_status, note=f"{reason}; never archived")
    return FetchedSource(source, LinkStatus.UNREACHABLE, http_status=http_status, note=f"{reason}; archive check failed")


async def fetch_all(sources: list[Source], allow_private: bool = False) -> dict[str, FetchedSource]:
    async def guard(request: httpx.Request) -> None:
        # Runs on every request, redirects included. DNS rebinding between this
        # check and the connection is not covered.
        await asyncio.to_thread(check_url_allowed, str(request.url), allow_private)

    headers = {"User-Agent": USER_AGENT}
    hooks = {"request": [guard]}
    async with httpx.AsyncClient(follow_redirects=True, timeout=TIMEOUT, headers=headers, event_hooks=hooks) as client:
        results = await asyncio.gather(*(fetch_source(client, s, allow_private) for s in sources))
    return {r.source.id: r for r in results}
