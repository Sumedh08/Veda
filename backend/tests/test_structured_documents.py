import pytest

from app.research.structured_documents import (
    StructuredDocumentError,
    StructuredParagraph,
    parse_structured_document,
    select_structured_passages,
)


def test_jats_preserves_original_sections_and_classifies_method_results_passages():
    xml = b"""<article><front><article-meta><abstract><p>Abstract text.</p></abstract></article-meta></front><body>
      <sec><title>Materials and Methods</title><p>We randomized 100 participants.</p>
        <sec><title>Participants</title><p>Participants were recruited in 2025.</p></sec>
      </sec><sec><title>Findings</title><p>The treatment group completed tasks faster.</p></sec>
      <sec><title>Limitations</title><p>The sample was small.</p></sec>
    </body></article>"""

    document = parse_structured_document(xml, format_hint="jats")

    assert document.representation_format == "jats"
    assert document.content_sha256
    assert [section.normalized_type for section in document.sections] == [
        "abstract",
        "methods",
        "methods",
        "results",
        "limitations",
    ]
    method = next(p for p in document.paragraphs if "randomized" in p.text)
    nested = next(p for p in document.paragraphs if "recruited" in p.text)
    assert method.section_path == ("Materials and Methods",)
    assert nested.section_path == ("Materials and Methods", "Participants")
    assert method.source_locator.startswith("article/body/sec[")


def test_tei_document_is_parsed_without_losing_heading_or_order():
    xml = b"""<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body>
      <div><head>Methods</head><p>Twenty people completed the task.</p></div>
      <div><head>Results</head><p>Median time was lower.</p></div>
    </body></text></TEI>"""

    document = parse_structured_document(xml, format_hint="tei")

    assert document.representation_format == "tei"
    assert [paragraph.section_type for paragraph in document.paragraphs] == [
        "methods",
        "results",
    ]
    assert document.paragraphs[1].ordinal > document.paragraphs[0].ordinal


def test_legacy_grobid_html_wrapped_tei_without_body_is_supported():
    xml = b"""<html><body><tei><text>
      <div><head>Methods</head><p>Older GROBID output keeps sections below text.</p></div>
      <div><head>Results</head><p>Measured completion time decreased.</p></div>
    </text></tei></body></html>"""

    document = parse_structured_document(xml, format_hint="tei")

    assert [section.normalized_type for section in document.sections] == ["methods", "results"]
    assert [paragraph.text for paragraph in document.paragraphs] == [
        "Older GROBID output keeps sections below text.",
        "Measured completion time decreased.",
    ]
    assert document.paragraphs[0].source_locator.startswith("TEI/text/")


def test_bounded_passage_selection_preserves_methods_and_results_under_abstract_pressure():
    paragraphs = [
        StructuredParagraph(
            section_id="abstract",
            section_type="abstract",
            section_path=("Abstract",),
            paragraph_index=index,
            ordinal=index,
            text=f"Abstract sentence {index} reports background context.",
            source_locator=f"article/abstract/p[{index}]",
        )
        for index in range(1, 13)
    ]
    paragraphs.extend(
        [
            StructuredParagraph(
                section_id="methods",
                section_type="methods",
                section_path=("Methods",),
                paragraph_index=1,
                ordinal=13,
                text="Participants were randomized to two groups.",
                source_locator="article/body/sec[1]/p[1]",
            ),
            StructuredParagraph(
                section_id="results",
                section_type="results",
                section_path=("Results",),
                paragraph_index=1,
                ordinal=14,
                text="Task completion time differed between groups.",
                source_locator="article/body/sec[2]/p[1]",
            ),
        ]
    )

    selected, overlong = select_structured_passages(paragraphs, limit=2)

    assert [(item[0].section_type, item[2]) for item in selected] == [
        ("methods", "Participants were randomized to two groups."),
        ("results", "Task completion time differed between groups."),
    ]
    assert overlong == 0


def test_sentence_selection_does_not_split_figure_or_example_abbreviations():
    paragraph = StructuredParagraph(
        section_id="results",
        section_type="results",
        section_path=("Results",),
        paragraph_index=1,
        ordinal=1,
        text=(
            "Both communities were affected by drought (Fig. 1). "
            "The authors report e.g. a stronger bacterial response."
        ),
        source_locator="article/body/sec[1]/p[1]",
    )

    selected, overlong = select_structured_passages([paragraph], limit=4)

    assert [item[2] for item in selected] == [
        "Both communities were affected by drought (Fig. 1).",
        "The authors report e.g. a stronger bacterial response.",
    ]
    assert overlong == 0


def test_sentence_selection_preserves_private_use_characters_in_source_text():
    paragraph = StructuredParagraph(
        section_id="results",
        section_type="results",
        section_path=("Results",),
        paragraph_index=1,
        ordinal=1,
        text="\ue000 is part of the source text. A second sentence follows.",
        source_locator="article/body/sec[1]/p[1]",
    )

    selected, _ = select_structured_passages([paragraph], limit=2)

    assert [item[2] for item in selected] == [
        "\ue000 is part of the source text.",
        "A second sentence follows.",
    ]


@pytest.mark.parametrize(
    "payload",
    [
        b'<!DOCTYPE x [<!ENTITY e "expanded">]><article><body><p>&e;</p></body></article>',
        b'<!ENTITY e "expanded"><article/>',
    ],
)
def test_structured_document_parser_rejects_internal_entity_declarations(payload):
    with pytest.raises(StructuredDocumentError, match="xml_entity_forbidden"):
        parse_structured_document(payload, format_hint="jats")


def test_external_jats_doctype_is_removed_without_resolving_external_resources():
    xml = b"""<!DOCTYPE article PUBLIC "-//NLM//DTD JATS (Z39.96) Journal Archiving DTD v1.3 20210610//EN" "https://example.invalid/jats-archivearticle1.dtd">
    <article><body><sec><title>Methods</title><p>We randomized forty participants.</p></sec>
    <sec><title>Results</title><p>Task completion time was lower.</p></sec></body></article>"""

    document = parse_structured_document(xml, format_hint="jats")

    assert [section.normalized_type for section in document.sections] == ["methods", "results"]
    assert [paragraph.section_type for paragraph in document.paragraphs] == ["methods", "results"]
    assert document.content_sha256


def test_parser_rejects_oversized_or_malformed_xml_without_partial_evidence():
    with pytest.raises(StructuredDocumentError, match="document_too_large"):
        parse_structured_document(b" " * (2_000_001), format_hint="jats")
    with pytest.raises(StructuredDocumentError, match="malformed_xml"):
        parse_structured_document(b"<article><body><p>unfinished", format_hint="jats")

    with pytest.raises(StructuredDocumentError, match="malformed_xml"):
        parse_structured_document(b"<TEI><text><body><p>unfinished", format_hint="tei")


def test_unsupported_format_and_unexpected_root_fail_closed():
    with pytest.raises(StructuredDocumentError, match="unsupported_format"):
        parse_structured_document(b"<html/>", format_hint="pdf")
    with pytest.raises(StructuredDocumentError, match="unexpected_document_root"):
        parse_structured_document(b"<html><body>not a paper</body></html>", format_hint="jats")
