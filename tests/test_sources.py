import asyncio
from datetime import UTC, datetime

import httpx
import pytest

from upheld import sources
from upheld.models import LinkStatus, Source
from upheld.sources import fetch_source

COOKIE_WALL = "<html><head><title>PubMed</title></head><body><p>Cookies must be enabled. Enable cookies for pubmed.ncbi.nlm.nih.gov and reload this page to continue.</p></body></html>"
ARTICLE = (
    "<html><head><title>Aspirin</title></head><body><article>"
    "<p>Daily low-dose aspirin did not lower the risk of cardiovascular disease in healthy older adults, "
    "and it raised the rate of major hemorrhage, the ASPREE investigators reported.</p>"
    "<p>The trial enrolled 19,114 people aged 70 or older in Australia and the United States, "
    "or 65 or older for Black and Hispanic participants in the United States.</p>"
    "<p>Participants took 100 mg of aspirin or a placebo every day and were followed for a median of 4.7 years.</p>"
    "</article></body></html>"
)
# The article as a typeset PDF would wrap it, with words broken across lines.
ARTICLE_LINES = [
    "Daily low-dose aspirin did not lower the risk of cardio-",
    "vascular disease in healthy older adults, and it raised the rate",
    "of major hemorrhage, the ASPREE investigators reported. The trial",
    "enrolled 19,114 people aged 70 or older in Australia and the United",
    "States, none of them with COVID-",
    "19. Participants took 100 mg of low-",
    "dose aspirin or a placebo every day and were followed for a median",
    "of 4.7 years.",
]


def make_pdf(lines: list[str]) -> bytes:
    """A one-page PDF with each string on its own line, and no page content at all if there are none."""
    stream = "BT /F1 10 Tf 12 TL 72 720 Td " + " ".join(f"({line}) Tj T*" for line in lines) + " ET" if lines else ""
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream",
    ]
    pdf, offsets = "%PDF-1.4\n", []
    for n, obj in enumerate(objects, 1):
        offsets.append(len(pdf))
        pdf += f"{n} 0 obj\n{obj}\nendobj\n"
    xref = len(pdf)
    pdf += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n" + "".join(f"{offset:010} 00000 n \n" for offset in offsets)
    pdf += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
    return pdf.encode("latin-1")


def fetch(body: str | bytes, content_type: str = "text/html"):
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=body, headers={"content-type": content_type}))

    async def run():
        async with httpx.AsyncClient(transport=transport) as client:
            return await fetch_source(client, Source(id="1", url="https://example.com/page"))

    return asyncio.run(run())


def test_block_page_is_unreadable_not_evidence():
    fetched = fetch(COOKIE_WALL)
    assert fetched.status == LinkStatus.UNREACHABLE
    assert fetched.text == ""
    assert "cookie wall" in fetched.note


def test_article_is_read():
    fetched = fetch(ARTICLE)
    assert fetched.status == LinkStatus.LIVE
    assert "ASPREE" in fetched.text


# Some servers send PDFs as a generic download, so the file's own header counts too.
@pytest.mark.parametrize("content_type", ["application/pdf", "application/octet-stream"])
def test_pdf_is_read_with_its_lines_joined(content_type):
    fetched = fetch(make_pdf(ARTICLE_LINES), content_type)
    assert fetched.status == LinkStatus.LIVE
    assert "risk of cardiovascular disease in healthy older adults" in fetched.text
    assert "with COVID-19." in fetched.text
    assert "100 mg of low-dose aspirin" in fetched.text  # the article hyphenates it on its first line
    assert "\n" not in fetched.text


def test_pdf_without_text_is_unreadable():
    fetched = fetch(make_pdf([]), "application/pdf")
    assert fetched.status == LinkStatus.UNREACHABLE
    assert fetched.text == ""
    assert "no text layer" in fetched.note


def test_pdf_over_the_size_cap_is_unreadable(monkeypatch):
    pdf = make_pdf(ARTICLE_LINES)
    monkeypatch.setattr(sources, "MAX_BYTES", len(pdf) // 2)
    fetched = fetch(pdf, "application/pdf")
    assert fetched.status == LinkStatus.UNREACHABLE
    assert fetched.note.startswith("PDF over")


URL = "https://example.com/page"
CDX = "https://web.archive.org/cdx/search/cdx"
COPY = f"https://web.archive.org/web/20261011194435id_/{URL}"


def fetch_with_archive(live: httpx.Response, copies: list[list[str]], copy: httpx.Response | None = None):
    """Fetch URL, which answers with live; the Wayback Machine lists copies and serves copy. Returns the result and every URL requested."""
    requested = []

    def handle(request: httpx.Request) -> httpx.Response:
        requested.append(request.url)
        if str(request.url).startswith(CDX):
            return httpx.Response(200, json=[["timestamp", "original"], *copies] if copies else [])
        if str(request.url) == COPY and copy is not None:
            return copy
        if str(request.url) == URL:
            return live
        return httpx.Response(404)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            return await fetch_source(client, Source(id="1", url=URL))

    return asyncio.run(run()), requested


def html(body: str) -> httpx.Response:
    return httpx.Response(200, text=body, headers={"content-type": "text/html; charset=utf-8"})


def test_blocked_page_is_read_from_its_archived_copy():
    fetched, requested = fetch_with_archive(httpx.Response(403), [["20261011194435", URL]], html(ARTICLE))
    assert fetched.status == LinkStatus.ARCHIVED
    assert "ASPREE" in fetched.text
    assert fetched.http_status == 403
    assert fetched.archived_at == datetime(2026, 10, 11, 19, 44, 35, tzinfo=UTC)
    assert fetched.archive_url == f"https://web.archive.org/web/20261011194435/{URL}"
    assert fetched.note == "HTTP 403 (blocked or rate-limited); read from the Wayback Machine copy of 2026-10-11"
    # One lookup for the newest copy archived with HTTP 200, and one fetch of it.
    [lookup] = [u for u in requested if str(u).startswith(CDX)]
    assert lookup.params["filter"] == "statuscode:200" and lookup.params["limit"] == "-1"
    assert len(requested) == 3


def test_dead_link_is_read_from_its_archived_copy():
    fetched, _ = fetch_with_archive(httpx.Response(404), [["20261011194435", URL]], html(ARTICLE))
    assert fetched.status == LinkStatus.LINK_ROT
    assert "ASPREE" in fetched.text
    assert fetched.archived_at is not None
    assert fetched.note == "HTTP 404; read from the Wayback Machine copy of 2026-10-11"


def test_block_page_live_is_read_from_its_archived_copy():
    fetched, _ = fetch_with_archive(html(COOKIE_WALL), [["20261011194435", URL]], html(ARTICLE))
    assert fetched.status == LinkStatus.ARCHIVED
    assert "ASPREE" in fetched.text
    assert fetched.note.startswith("page had only")


def test_without_an_archived_copy_a_blocked_page_stays_unreadable():
    fetched, _ = fetch_with_archive(httpx.Response(403), [])
    assert fetched.status == LinkStatus.UNREACHABLE
    assert fetched.text == "" and fetched.archived_at is None
    assert fetched.note == "HTTP 403 (blocked or rate-limited); never archived"


def test_without_an_archived_copy_a_dead_link_is_likely_fabricated():
    fetched, _ = fetch_with_archive(httpx.Response(404), [])
    assert fetched.status == LinkStatus.LIKELY_FABRICATED
    assert fetched.note == "HTTP 404; never archived"


def test_archived_block_page_is_still_unreadable():
    fetched, _ = fetch_with_archive(httpx.Response(403), [["20261011194435", URL]], html(COOKIE_WALL))
    assert fetched.status == LinkStatus.UNREACHABLE
    assert fetched.text == "" and fetched.archived_at is None
    assert "Wayback Machine copy of 2026-10-11 couldn't be read: page had only" in fetched.note
    fetched, _ = fetch_with_archive(html(COOKIE_WALL), [["20261011194435", URL]], html(COOKIE_WALL))
    assert fetched.note.endswith("; so did the Wayback Machine copy of 2026-10-11")


def test_dead_link_with_an_unreadable_copy_is_link_rot_without_text():
    fetched, _ = fetch_with_archive(httpx.Response(410), [["20261011194435", URL]], httpx.Response(503))
    assert fetched.status == LinkStatus.LINK_ROT
    assert fetched.text == ""
    assert fetched.note == "HTTP 410; Wayback Machine copy of 2026-10-11 couldn't be read: HTTP 503"


def test_unreadable_document_is_not_looked_up_in_the_archive():
    # A scan has no text layer in its archived copy either.
    scan = httpx.Response(200, content=make_pdf([]), headers={"content-type": "application/pdf"})
    fetched, requested = fetch_with_archive(scan, [["20261011194435", URL]], html(ARTICLE))
    assert fetched.status == LinkStatus.UNREACHABLE
    assert requested == [httpx.URL(URL)]


GEMINI = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGcTq8x2xZr9kF0bHkE4yL7mNw1"


def fetch_through_redirect(redirect: httpx.Response, live: httpx.Response):
    """Fetch Gemini's redirect link, which answers with redirect; URL answers with live, and was never archived."""
    requested = []

    def handle(request: httpx.Request) -> httpx.Response:
        requested.append(request.url)
        if str(request.url).startswith(CDX):
            return httpx.Response(200, json=[])
        if str(request.url) == GEMINI:
            return redirect
        return live if str(request.url) == URL else httpx.Response(404)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle), follow_redirects=True) as client:
            return await fetch_source(client, Source(id="1", url=GEMINI))

    return asyncio.run(run()), requested


def test_redirect_is_followed_and_reported():
    fetched, _ = fetch_through_redirect(httpx.Response(302, headers={"location": URL}), html(ARTICLE))
    assert fetched.status == LinkStatus.LIVE
    assert fetched.resolved_url == URL


def test_blocked_page_behind_a_gemini_redirect_is_looked_up_by_its_real_url():
    fetched, requested = fetch_through_redirect(httpx.Response(302, headers={"location": URL}), httpx.Response(403))
    [lookup] = [u for u in requested if str(u).startswith(CDX)]
    assert lookup.params["url"] == URL
    assert fetched.status == LinkStatus.UNREACHABLE and fetched.resolved_url == URL


def test_expired_gemini_redirect_is_unreadable_not_fabricated():
    fetched, requested = fetch_through_redirect(httpx.Response(404), html(ARTICLE))
    assert fetched.status == LinkStatus.UNREACHABLE
    assert "redirect link no longer resolves" in fetched.note
    assert requested == [httpx.URL(GEMINI)]
