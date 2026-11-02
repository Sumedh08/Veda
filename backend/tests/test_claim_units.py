from app.research.claim_units import CLAIM_ATOMIZATION_VERSION, atomize_source_sentence


def test_atomizes_independent_semicolon_clauses_to_exact_non_overlapping_spans():
    sentence = "Exports grew by 5%; employment fell by 2%."

    units = atomize_source_sentence(sentence)

    assert CLAIM_ATOMIZATION_VERSION == 1
    assert [unit.text for unit in units] == ["Exports grew by 5%", "employment fell by 2%."]
    assert [unit.status for unit in units] == ["atomized_exact_span", "atomized_exact_span"]
    assert all(sentence[unit.start : unit.end] == unit.text for unit in units)
    assert units[0].end <= units[1].start


def test_atomizes_contrast_only_when_both_sides_are_explicit_clauses():
    sentence = "Productivity improved, but wage growth remained flat."

    units = atomize_source_sentence(sentence)

    assert [unit.text for unit in units] == ["Productivity improved", "wage growth remained flat."]
    assert all(sentence[unit.start : unit.end] == unit.text for unit in units)


def test_uncertain_compound_sentence_is_preserved_and_marked_unatomized():
    sentence = "Exports grew; according to earlier reports, employment."

    units = atomize_source_sentence(sentence)

    assert len(units) == 1
    assert units[0].text == sentence
    assert units[0].start == 0
    assert units[0].end == len(sentence)
    assert units[0].status == "compound_unatomized"


def test_compound_nouns_and_single_proposition_are_not_split():
    single = "Productivity and output increased in the surveyed firms."
    noun_phrase = "AI adoption and productivity"

    assert [(unit.text, unit.status) for unit in atomize_source_sentence(single)] == [
        (single, "whole_sentence")
    ]
    assert [(unit.text, unit.status) for unit in atomize_source_sentence(noun_phrase)] == [
        (noun_phrase, "whole_sentence")
    ]


def test_offsets_use_unicode_codepoints_and_reconstruct_the_exact_source_unit():
    sentence = "Firms 🚀 expanded sales; employment declined."

    units = atomize_source_sentence(sentence)

    assert [sentence[unit.start : unit.end] for unit in units] == [unit.text for unit in units]
    assert units[1].start == sentence.index("employment")
