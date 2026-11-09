from upheld.quantities import compare, quantities, unit_mismatches
from upheld.verify import LexicalVerifier

EIFFEL = "The tower is 330 m (1,083 ft) tall. Its base is a square 125 metres (410 ft) on a side. It was meant to stand for 20 years."


def parsed(text: str) -> list[tuple[str, float, str]]:
    return [(q.text, q.value, q.unit) for q in quantities(text)]


def test_reads_numbers_with_units_and_leaves_lookalikes_alone():
    assert parsed("330m tall, 1,083 ft, a 68-week trial, 5 km/h") == [
        ("330m", 330.0, "m"),
        ("1,083 ft", 1083.0, "ft"),
        ("68-week", 68.0, "week"),
        ("5 km/h", 5.0, "km/h"),
    ]
    # Not units: "in" as a preposition, decades, money, a capital M for million, BMI's kg/m2.
    assert parsed("5 in 10 people in the 1990s spent $5 m on 3 M users with a BMI of 31.3 kg/m2") == []


def test_a_converted_figure_matches_and_the_same_digits_in_another_unit_dont():
    [metres] = quantities("410 metres")
    [converted] = quantities("about 125 m")
    page = quantities(EIFFEL)
    assert compare(converted, page) == "match"  # 410 ft is 124.97 m
    assert compare(metres, page) == "mismatch"  # the page has 410 ft, never 410 metres
    assert compare(quantities("30 km")[0], page) == "unknown"  # nothing to compare it with
    [same_unit] = quantities("124 m")
    assert compare(same_unit, quantities("125 m")) == "unknown"  # in one unit, numbers must be equal


def test_unit_mismatches_name_what_the_page_says():
    [(claimed, said)] = unit_mismatches("It stood for 20 months.", EIFFEL, EIFFEL)
    assert (claimed.text, said.text) == ("20 months", "20 years")
    # A page that states the claim's quantity elsewhere is no mismatch, whatever the passage says.
    assert unit_mismatches("It is 410 ft wide.", "410 metres", EIFFEL) == []


def test_lexical_compares_quantities_not_digits():
    v = LexicalVerifier()
    answer = "The base is 410 metres wide. The base is 1,345 feet wide. The base is 125 m wide."
    claims = [(0, 28), (29, 57), (58, len(answer))]
    wrong_unit, converted_wrong, converted = v.check(answer, claims, [EIFFEL])
    assert wrong_unit.score == 0.0 and [s.text for s in wrong_unit.spans] == ["410 metres"]
    assert converted_wrong.score == 0.0 and [s.text for s in converted_wrong.spans] == ["1,345"]
    assert converted.score > v.threshold and converted.spans == []
