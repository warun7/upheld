"""Numbers with units, compared as quantities rather than digits.

"It stands 410 metres tall" shares the digits of a page's "410 ft" and nothing else; "125 m" shares no digits with it
and says the same thing. Units here are the ones that convert without context: length, mass, speed and time. Currency,
temperature and volume (US or imperial gallons?) are left to the digit match.
"""

import re
from dataclasses import dataclass
from typing import Literal

# spelling -> (dimension, size in the dimension's base unit)
UNITS: dict[str, tuple[str, float]] = {}


def _add(dimension: str, size: float, *spellings: str) -> None:
    for s in spellings:
        UNITS[s] = (dimension, size)


_add("length", 0.001, "mm", "millimetre", "millimetres", "millimeter", "millimeters")
_add("length", 0.01, "cm", "centimetre", "centimetres", "centimeter", "centimeters")
_add("length", 1.0, "m", "metre", "metres", "meter", "meters")
_add("length", 1000.0, "km", "kilometre", "kilometres", "kilometer", "kilometers")
_add("length", 0.0254, "inch", "inches")  # not "in": "5 in 10 people"
_add("length", 0.3048, "ft", "foot", "feet")
_add("length", 0.9144, "yd", "yard", "yards")
_add("length", 1609.344, "mi", "mile", "miles")
_add("mass", 1e-6, "mg", "milligram", "milligrams")
_add("mass", 0.001, "g", "gram", "grams")
_add("mass", 1.0, "kg", "kilogram", "kilograms")
_add("mass", 1000.0, "tonne", "tonnes")  # not "ton": short, long or metric
_add("mass", 0.45359237, "lb", "lbs")  # not "pounds", which is as often money
_add("mass", 0.028349523125, "oz", "ounce", "ounces")
_add("speed", 1 / 3.6, "km/h", "kph")
_add("speed", 0.44704, "mph")
_add("speed", 1.0, "m/s")
_add("time", 1.0, "second", "seconds", "sec", "secs")  # not "s": "the 1990s"
_add("time", 60.0, "minute", "minutes", "min", "mins")
_add("time", 3600.0, "hour", "hours", "hr", "hrs")
_add("time", 86400.0, "day", "days")
_add("time", 7 * 86400.0, "week", "weeks", "wk", "wks")
_add("time", 30.436875 * 86400, "month", "months")
_add("time", 365.2425 * 86400, "year", "years", "yr", "yrs")

# Symbols are case-sensitive ("M" is often million); words aren't ("Metres" at the start of a table cell).
_SYMBOLS = {s for s in UNITS if len(s) <= 4 and s not in ("inch", "foot", "feet", "yard", "mile", "gram", "day", "days", "week", "hour", "year")}
_WORDS = set(UNITS) - _SYMBOLS


def _alternation(units: set[str]) -> str:
    return "|".join(sorted(map(re.escape, units), key=len, reverse=True))


_QUANTITY = re.compile(
    r"(?<![\w.,$£€¥])"  # not inside a longer number, and not money
    r"(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"[\s-]?"  # "410 ft", "410ft", "68-week"
    rf"(?P<unit>(?i:{_alternation(_WORDS)})|{_alternation(_SYMBOLS)})"
    r"(?![\w/²³])"
)


@dataclass(frozen=True)
class Quantity:
    start: int
    end: int
    text: str
    value: float
    unit: str
    decimals: int

    @property
    def dimension(self) -> str:
        return UNITS[self.unit][0]

    @property
    def base(self) -> float:
        return self.value * UNITS[self.unit][1]

    def same_as(self, other: "Quantity") -> bool:
        """The same amount. In one unit the numbers must be equal; across units they must agree to this quantity's
        last digit or 1%, whichever is looser, since a converted figure gets rounded ("410 ft" is 124.97 m)."""
        if other.dimension != self.dimension:
            return False
        if UNITS[other.unit][1] == UNITS[self.unit][1]:
            return other.value == self.value
        rounding = 0.5 * 10**-self.decimals * UNITS[self.unit][1]
        return abs(self.base - other.base) <= max(rounding, 0.01 * abs(self.base))


def quantities(text: str) -> list[Quantity]:
    found = []
    for m in _QUANTITY.finditer(text):
        num, unit = m.group("num"), m.group("unit")
        key = unit if unit in UNITS else unit.lower()
        decimals = len(num.split(".")[1]) if "." in num else 0
        found.append(Quantity(m.start(), m.end(), m.group(), float(num.replace(",", "")), key, decimals))
    return found


def compare(q: Quantity, evidence: list[Quantity]) -> Literal["match", "mismatch", "unknown"]:
    """match: the evidence states this quantity, in any unit. mismatch: it has the same number in a different unit of
    the same kind and never this quantity. unknown: neither, so leave it to the digits and the verifier."""
    if any(q.same_as(e) for e in evidence):
        return "match"
    if any(e.dimension == q.dimension and e.value == q.value and UNITS[e.unit][1] != UNITS[q.unit][1] for e in evidence):
        return "mismatch"
    return "unknown"


def unit_mismatches(claim: str, passages: str, page: str) -> list[tuple[Quantity, Quantity]]:
    """Quantities in the claim whose number the passages give in another unit, where the page never states the
    claim's quantity at all: "410 metres" against a page that says "410 ft". Each comes with what the page says."""
    in_passages, on_page = quantities(passages), quantities(page)
    out = []
    for q in quantities(claim):
        if compare(q, in_passages) == "mismatch" and compare(q, on_page) != "match":
            said = next(e for e in in_passages if e.dimension == q.dimension and e.value == q.value)
            out.append((q, said))
    return out
