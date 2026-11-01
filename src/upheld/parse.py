"""Split an answer into claims and work out which sources each claim cites.

Handles the citation styles AI search tools commonly emit:
  - numeric markers: [1], [1, 2], [1][2], [^1], 【1】
  - inline markdown links: [text](https://...)
  - a trailing reference list: "[1] Title - https://..." or "1. https://..."
"""

import re
from dataclasses import dataclass, field

from upheld.models import Source

_MARKER = re.compile(r"\[\^?(\d+(?:\s*,\s*\d+)*)\]|【(\d+)】")
_MD_LINK = re.compile(r"(?<!!)\[([^\]]+)\]\((https?://[^)\s]+)\)")
_REF_LINE = re.compile(r"^\s*(?:\[\^?(\d+)\]:?|(\d+)[.)])\s*(.*?)(https?://\S+)\s*$")
_REF_HEADER = re.compile(r"^\s*(?:#+\s*)?\**(sources|references|citations|links)\**:?\s*$", re.I)

# Split after sentence punctuation (optionally followed by citation markers),
# before whitespace and the start of the next sentence. A "[" can start a
# sentence (a markdown link) but not when it's a marker: "Finn. [1]" is one sentence.
_SENT_END = re.compile(
    r"(?<=[.!?])((?:\s*(?:\[\^?\d+(?:\s*,\s*\d+)*\]|【\d+】))*)\s+(?=[A-Z0-9\"“(*]|\[(?!\^?\d+(?:\s*,\s*\d+)*\]))"
)
_ABBREV = re.compile(r"\b(?:e\.g|i\.e|etc|vs|Dr|Mr|Mrs|Ms|Prof|St|Inc|Ltd|Co|U\.S|U\.K|No|Fig|al)\.$")


@dataclass
class Claim:
    index: int
    text: str  # cleaned: markers removed, link syntax reduced to its text
    start: int
    end: int
    cited: list[str] = field(default_factory=list)


def extract_reference_list(answer: str) -> tuple[str, list[Source]]:
    """Pull a trailing reference list out of the answer body.

    Only lines at the end of the answer are treated as references, so numbered
    lists in the body of the answer are left alone.
    """
    lines = answer.splitlines()
    sources: list[Source] = []
    cut = len(lines)
    for i in range(len(lines) - 1, -1, -1):
        line = lines[i]
        if not line.strip():
            continue
        m = _REF_LINE.match(line)
        if m:
            ref_id = m.group(1) or m.group(2)
            title = m.group(3).strip(" -–—:|") or None
            sources.append(Source(id=ref_id, url=m.group(4).rstrip(".,;"), title=title))
            cut = i
            continue
        if _REF_HEADER.match(line) and sources:
            cut = i
        break
    sources.reverse()
    return "\n".join(lines[:cut]), sources


def _clean(text: str) -> str:
    text = _MD_LINK.sub(r"\1", text)
    text = _MARKER.sub("", text)
    text = re.sub(r"[*_`]+", "", text)
    text = re.sub(r"^\s*(?:[-•]|\d+[.)])\s+", "", text)
    text = re.sub(r"\s+([.,;:!?])", r"\1", text)
    return re.sub(r"\s{2,}", " ", text).strip()


def _cited_ids(raw: str, link_ids: dict[str, str]) -> list[str]:
    ids: list[str] = []
    for m in _MARKER.finditer(raw):
        group = m.group(1) or m.group(2)
        ids.extend(part.strip() for part in group.split(","))
    for m in _MD_LINK.finditer(raw):
        ids.append(link_ids.setdefault(m.group(2), m.group(2)))
    return list(dict.fromkeys(ids))


def _sentences(line: str, offset: int) -> list[tuple[str, int, int]]:
    pieces: list[tuple[str, int, int]] = []
    start = 0
    for m in _SENT_END.finditer(line):
        head = line[start : m.start()]
        if _ABBREV.search(head):
            continue
        end = m.end(1)  # keep trailing citation markers with their sentence
        pieces.append((line[start:end], offset + start, offset + end))
        start = m.end()
    if start < len(line):
        pieces.append((line[start:], offset + start, offset + len(line)))
    return pieces


def is_claim(text: str) -> bool:
    """Skip headings, lead-ins ("Here's what I found:") and questions."""
    words = text.split()
    return len(words) >= 4 and not text.endswith((":", "?"))


def _only_citations(raw: str) -> bool:
    return not re.sub(r"[\s()\[\],.;]+", "", _MARKER.sub("", _MD_LINK.sub("", raw)))


def split_claims(answer: str) -> tuple[list[Claim], list[Source]]:
    """Return claims and any sources discovered from inline markdown links."""
    link_ids: dict[str, str] = {}
    claims: list[Claim] = []
    pos = 0
    for line in answer.splitlines(keepends=True):
        stripped = line.rstrip("\n")
        if stripped.strip() and not stripped.lstrip().startswith("#"):
            pieces: list[list] = []  # [raw, start, end, cited]
            for raw, s, e in _sentences(stripped, pos):
                cited = _cited_ids(raw, link_ids)
                if pieces and _only_citations(raw):
                    # Citations after their sentence's full stop, like ChatGPT's "... dose. ([nejm.org](https://...))"
                    pieces[-1][2] = e
                    pieces[-1][3] = list(dict.fromkeys(pieces[-1][3] + cited))
                    continue
                pieces.append([raw, s, e, cited])
            # A paragraph cited only at its end ("A. B. C. [1][2]") is cited as a whole.
            if len(pieces) > 1 and pieces[-1][3] and not any(p[3] for p in pieces[:-1]):
                for p in pieces[:-1]:
                    if is_claim(_clean(p[0])):
                        p[3] = pieces[-1][3]
            for raw, s, e, cited in pieces:
                text = _clean(raw)
                if text:
                    claims.append(Claim(len(claims), text, s, e, cited))
        pos += len(line)
    link_sources = [Source(id=url, url=url) for url in link_ids]
    return claims, link_sources
