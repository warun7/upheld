import asyncio

import httpx

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


def fetch(html: str):
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text=html, headers={"content-type": "text/html"}))

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
