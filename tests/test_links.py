from upheld.links import best_sentence, passage_link, text_fragment

PASSAGE = (
    "Construction began in 1887. The tower is 330 metres (1,083 ft) tall, about the same height as an 81-storey "
    "building, and the tallest structure in Paris. Its base is square."
)


def test_links_to_the_sentence_closest_to_the_claim():
    assert best_sentence(PASSAGE, "The Eiffel Tower is 330 metres tall").startswith("The tower is 330 metres")
    link = passage_link("https://en.wikipedia.org/wiki/Eiffel_Tower", PASSAGE, "The Eiffel Tower is 330 metres tall")
    assert link == "https://en.wikipedia.org/wiki/Eiffel_Tower#:~:text=The%20tower%20is%20330,tallest%20structure%20in%20Paris."


def test_fragment_escapes_what_the_syntax_reserves():
    # "-" marks a prefix or suffix, "," separates start from end, "&" separates directives.
    assert text_fragment("Rock-and-roll, R&B and soul") == ":~:text=Rock%2Dand%2Droll%2C%20R%26B%20and%20soul"
    assert text_fragment("Too short") is None


def test_keeps_an_existing_fragment_and_skips_what_cant_take_one():
    assert passage_link("https://example.com/a#history", "It opened in 1889 to the public.", "opened 1889") == (
        "https://example.com/a#history:~:text=It%20opened%20in%201889%20to%20the%20public."
    )
    assert passage_link("https://example.com/report.PDF?v=2", PASSAGE, "tower") is None
    assert passage_link(None, PASSAGE, "tower") is None
    assert passage_link("ftp://example.com/x", PASSAGE, "tower") is None
