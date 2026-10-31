from upheld.parse import extract_reference_list, is_claim, split_claims


def test_numeric_markers_attach_to_their_sentence():
    claims, _ = split_claims("Paris is the capital of France [1]. It has about 2.1 million residents.[2][3] Nice.")
    assert [c.cited for c in claims] == [["1"], ["2", "3"], []]
    assert claims[0].text == "Paris is the capital of France."
    assert claims[1].text == "It has about 2.1 million residents."


def test_marker_after_period_and_space_stays_with_its_sentence():
    claims, _ = split_claims("Finn Hudson died in season five of Glee. [1] He was played by Cory Monteith. [2]")
    assert [(c.text, c.cited) for c in claims] == [
        ("Finn Hudson died in season five of Glee.", ["1"]),
        ("He was played by Cory Monteith.", ["2"]),
    ]


def test_markdown_link_can_start_a_sentence():
    claims, _ = split_claims("Paris is large. [Wikipedia](https://en.wikipedia.org/wiki/Paris) lists 2.1 million residents.")
    assert len(claims) == 2


def test_grouped_and_footnote_markers():
    claims, _ = split_claims("Water boils at 100 C at sea level [1, 4]. Ice melts at 0 C at sea level [^2].")
    assert [c.cited for c in claims] == [["1", "4"], ["2"]]


def test_abbreviations_do_not_split():
    claims, _ = split_claims("Some drugs, e.g. Ozempic, reduce appetite in adults [1].")
    assert len(claims) == 1


def test_markdown_links_become_sources():
    claims, sources = split_claims("The Eiffel Tower is 330 m tall ([Wikipedia](https://en.wikipedia.org/wiki/Eiffel_Tower)).")
    assert claims[0].cited == ["https://en.wikipedia.org/wiki/Eiffel_Tower"]
    assert claims[0].text.startswith("The Eiffel Tower is 330 m tall")
    assert sources[0].url == "https://en.wikipedia.org/wiki/Eiffel_Tower"


def test_offsets_point_into_original_answer():
    answer = "First claim here is true [1]. Second claim here is false [2]."
    claims, _ = split_claims(answer)
    assert answer[claims[1].start : claims[1].end] == "Second claim here is false [2]."


def test_reference_list_is_extracted_and_removed():
    answer = (
        "Ozempic reduces weight in adults [1].\n\n"
        "1. Step one of a numbered list in the body.\n\n"
        "Sources:\n"
        "[1] NEJM trial - https://www.nejm.org/doi/full/10.1056/NEJMoa2032183\n"
        "[2] https://example.com/page."
    )
    body, sources = extract_reference_list(answer)
    assert "Sources" not in body and "Step one" in body
    assert [(s.id, s.url) for s in sources] == [
        ("1", "https://www.nejm.org/doi/full/10.1056/NEJMoa2032183"),
        ("2", "https://example.com/page"),
    ]
    assert sources[0].title == "NEJM trial"


def test_is_claim_skips_lead_ins_and_questions():
    assert not is_claim("Here's what I found:")
    assert not is_claim("Want more detail?")
    assert not is_claim("Short line.")
    assert is_claim("The trial enrolled 1,961 adults with obesity.")
