"""Links that open a cited page scrolled to the sentence upheld checked the claim against, with it highlighted.

They use URL text fragments (`#:~:text=start,end`), which Chrome, Edge, Safari and Firefox 131+ support. A fragment
names the first and last few words of the sentence rather than all of it, so it still matches when the page's
rendering differs from upheld's extracted text in between. A browser that can't find the words opens the page at
the top, as a plain link would.
"""

import re
from urllib.parse import quote

from upheld.evidence import tokenize

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
EDGE_WORDS = 4


def best_sentence(passage: str, claim: str) -> str:
    """The sentence of the passage that shares the most words with the claim."""
    sentences = [s for s in _SENTENCE_END.split(" ".join(passage.split())) if s]
    if not sentences:
        return ""
    words = set(tokenize(claim))
    return max(sentences, key=lambda s: len(words & set(tokenize(s))))


def _encode(text: str) -> str:
    # quote() leaves "-" alone, but in a text fragment it marks a prefix or suffix.
    return quote(text, safe="").replace("-", "%2D")


def text_fragment(sentence: str) -> str | None:
    """`:~:text=` for the sentence: all of it when short, otherwise its first and last few words."""
    words = sentence.split()  # as extracted: browsers match the page's text with its whitespace collapsed, as here
    if len(words) < 3:  # too little to find the right place
        return None
    if len(words) <= 2 * EDGE_WORDS:
        return f":~:text={_encode(' '.join(words))}"
    return f":~:text={_encode(' '.join(words[:EDGE_WORDS]))},{_encode(' '.join(words[-EDGE_WORDS:]))}"


def passage_link(url: str | None, passage: str, claim: str) -> str | None:
    """The URL with a text fragment for the passage's sentence closest to the claim. None without an http(s) URL,
    and for PDFs, whose viewers ignore text fragments."""
    if not url or not url.startswith(("http://", "https://")):
        return None
    base, _, fragment = url.partition("#")
    if base.split("?", 1)[0].lower().endswith(".pdf"):
        return None
    directive = text_fragment(best_sentence(passage, claim))
    return f"{base}#{fragment}{directive}" if directive else None
