import asyncio

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
    "19. Participants took 100 mg of aspirin or a placebo every day and",
    "were followed for a median of 4.7 years.",
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
