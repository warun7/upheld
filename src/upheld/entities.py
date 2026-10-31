"""Catch "deceptive grounding": evidence that supports the claim's shape but is about a different entity.

Support verifiers judge whether a passage backs a statement; they can pass a
claim about drug X when the passage describes drug Y. This check is cheap and
high precision: it flags named entities from the claim that appear nowhere in
the cited source.
"""

import re

from wordfreq import zipf_frequency

COMMON_ZIPF = 4.0  # roughly: appears at least 10 times per million words

_NAME = r"[A-Z][\w'’-]*(?:\s+\d+\b)?"  # "Ozempic", "GPT-4o", "STEP 1", "Windows 11"
_CAPITALIZED_RUN = re.compile(rf"\b{_NAME}(?:\s+(?:(?:of|de|the|and|&)\s+)?{_NAME})*")
_CONNECTORS = frozenset("of de the and &".split())
_NOT_ENTITIES = frozenset(
    "The A An In On At By For From To Of And But Or If As It Its This That These Those There Their They He She We You I "
    "However Also According Although While When Where Which Who What Why How After Before During Since Despite "
    "Without With Under Over Between Among Through Unlike Like Following Because Unless Until Though Thus Therefore "
    "Both Each Every Many Most Some Several Other Another All Any Such Not No Only Even Then Meanwhile Instead Here Today "
    "January February March April May June July August September October November December "
    "Monday Tuesday Wednesday Thursday Friday Saturday Sunday".split()
)


_EDGE_PUNCT = re.compile(r"^['‘’\"“”]+|(?:['’]s)?['‘’\"“”]*$")  # quotes and possessive 's: "Charles II's" -> "Charles II"


def named_entities(claim: str) -> list[str]:
    found: list[str] = []
    # Where the sentence's first word starts, after any bullet, quote or markdown.
    first_word = next((i for i, ch in enumerate(claim) if ch.isalnum()), 0)
    for m in _CAPITALIZED_RUN.finditer(claim):
        words = [_EDGE_PUNCT.sub("", w) for w in m.group().split()]
        words = [w for w in words if w]
        lead = 0
        while words and (words[0] in _NOT_ENTITIES or words[0] in _CONNECTORS):
            words.pop(0)
            lead += 1
        while words and (words[-1] in _NOT_ENTITIES or words[-1] in _CONNECTORS):
            words.pop()
        if not words:
            continue
        # A lone capitalized word at sentence start may just be grammar
        # ("Researchers found..."). Keep it only if it's an uncommon word
        # (Ozempic, Nvidia) or looks like a name (GPT-4o, NASA).
        name = " ".join(words)
        at_start = m.start() <= first_word and lead == 0
        if at_start and len(words) == 1 and not re.search(r"\d|[A-Z].*[A-Z]|-", name):
            if zipf_frequency(name.lower(), "en") >= COMMON_ZIPF:
                continue
        found.append(name)
    return list(dict.fromkeys(found))


def _present(entity: str, source_text: str) -> bool:
    haystack = source_text.lower()
    if entity.lower() in haystack:
        return True
    # Accept the head word for multi-word names ("Marie Curie" -> "Curie").
    last = entity.split()[-1].lower()
    return len(last) > 3 and re.search(rf"\b{re.escape(last)}\b", haystack) is not None


def missing_entities(claim: str, source_text: str) -> list[str]:
    return [e for e in named_entities(claim) if not _present(e, source_text)]
