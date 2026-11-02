"""Bounded, section-aware parsing for publisher JATS and OpenAlex GROBID TEI.

This module only parses bytes obtained by a separate rights-aware resolver. It
does not fetch documents, decide that a URL is lawful, or retain document bytes.
"""

from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Literal

MAX_STRUCTURED_DOCUMENT_BYTES = 2_000_000
MAX_STRUCTURED_TEXT_CHARACTERS = 100_000
MAX_STRUCTURED_PARAGRAPHS = 5_000
PARSER_NAME = "veda-structured-xml"
PARSER_VERSION = "1"
_DOCTYPE_RE = re.compile(rb"<!\s*DOCTYPE\b", re.IGNORECASE)
_ENTITY_DECLARATION_RE = re.compile(rb"<!\s*ENTITY\b", re.IGNORECASE)
_EXTERNAL_DOCTYPE_RE = re.compile(
    rb"<!DOCTYPE\s+[A-Za-z_:][A-Za-z0-9_.:-]*\s+(?:"
    rb"SYSTEM\s+(['\"])[^'\"]+\1|"
    rb"PUBLIC\s+(['\"])[^'\"]+\2\s+(['\"])[^'\"]+\3"
    rb")\s*>",
    re.IGNORECASE | re.DOTALL,
)

StructuredFormat = Literal["jats", "tei"]
SectionType = Literal[
    "abstract",
    "introduction",
    "methods",
    "results",
    "discussion",
    "limitations",
    "conclusion",
    "supplement",
    "other",
]
_PASSAGE_SECTION_PRIORITY: tuple[SectionType, ...] = (
    "methods",
    "results",
    "limitations",
    "discussion",
    "introduction",
    "conclusion",
    "supplement",
    "other",
    "abstract",
)
_SENTENCE_ABBREVIATION_RE = re.compile(
    r"\b(?:figs?|eqs?|refs?|e\.g|i\.e|vs|et al)\.$", re.IGNORECASE
)


class StructuredDocumentError(ValueError):
    """Sanitized structured-document parser failure."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def split_evidence_sentences(text: str) -> list[str]:
    """Split evidence text without treating common scholarly abbreviations as endings."""
    sentences: list[str] = []
    sentence_start = 0
    for boundary in re.finditer(r"(?<=[.!?])\s+", text):
        punctuation_index = boundary.start() - 1
        if text[punctuation_index] == "." and _SENTENCE_ABBREVIATION_RE.search(
            text[sentence_start : punctuation_index + 1]
        ):
            continue
        sentence = text[sentence_start : boundary.start()].strip()
        if sentence:
            sentences.append(sentence)
        sentence_start = boundary.end()
    remainder = text[sentence_start:].strip()
    if remainder:
        sentences.append(remainder)
    return sentences


@dataclass(frozen=True)
class StructuredSection:
    section_id: str
    original_heading: str
    normalized_type: SectionType
    section_path: tuple[str, ...]
    ordinal: int
    source_locator: str


@dataclass(frozen=True)
class StructuredParagraph:
    section_id: str | None
    section_type: SectionType
    section_path: tuple[str, ...]
    paragraph_index: int
    ordinal: int
    text: str
    source_locator: str


@dataclass(frozen=True)
class StructuredDocument:
    representation_format: StructuredFormat
    content_sha256: str
    parser_name: str
    parser_version: str
    sections: tuple[StructuredSection, ...]
    paragraphs: tuple[StructuredParagraph, ...]
    extraction_warnings: tuple[str, ...]


def select_structured_passages(
    paragraphs: tuple[StructuredParagraph, ...] | list[StructuredParagraph],
    *,
    limit: int,
    max_sentence_characters: int = 600,
) -> tuple[list[tuple[StructuredParagraph, int, str]], int]:
    """Select a bounded, section-stratified sentence sample for evidence storage.

    Methods and Results are considered first, followed by limitations and the
    remaining document sections. Selection is round-robin across section types,
    then restored to document order so stored passage ordinals remain legible.
    This prioritizes study-design and outcome evidence without treating any
    section as inherently credible.
    """
    if limit <= 0:
        return [], 0
    by_section: dict[SectionType, list[tuple[StructuredParagraph, int, str]]] = {
        section_type: [] for section_type in _PASSAGE_SECTION_PRIORITY
    }
    overlong_sentences = 0
    for paragraph in paragraphs:
        sentences = split_evidence_sentences(paragraph.text)
        for sentence_number, sentence in enumerate(sentences, start=1):
            if len(sentence) > max_sentence_characters:
                overlong_sentences += 1
                continue
            by_section.setdefault(paragraph.section_type, []).append(
                (paragraph, sentence_number, sentence)
            )

    selected: list[tuple[StructuredParagraph, int, str]] = []
    round_index = 0
    while len(selected) < limit:
        progressed = False
        for section_type in _PASSAGE_SECTION_PRIORITY:
            candidates = by_section.get(section_type, [])
            if round_index >= len(candidates):
                continue
            selected.append(candidates[round_index])
            progressed = True
            if len(selected) >= limit:
                break
        if not progressed:
            break
        round_index += 1

    selected.sort(key=lambda item: (item[0].ordinal, item[1]))
    return selected, overlong_sentences


_SECTION_RULES: tuple[tuple[SectionType, tuple[str, ...]], ...] = (
    ("abstract", ("abstract", "summary")),
    ("introduction", ("introduction", "background", "related work")),
    (
        "methods",
        (
            "method",
            "methods",
            "methodology",
            "materials and methods",
            "materials methods",
            "study design",
            "experimental design",
            "participants and procedure",
            "data and methods",
        ),
    ),
    ("results", ("results", "findings", "outcomes")),
    ("discussion", ("discussion", "interpretation")),
    ("limitations", ("limitations", "limitations and future work", "study limitations")),
    ("conclusion", ("conclusion", "conclusions", "concluding remarks")),
    ("supplement", ("supplement", "supplementary materials", "appendix", "appendices")),
)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].casefold() if isinstance(tag, str) else ""


def _clean_text(element: ET.Element) -> str:
    return re.sub(r"\s+", " ", "".join(element.itertext())).strip()


def normalize_section_type(heading: str) -> SectionType:
    """Conservatively classify common headings while retaining each original label."""
    normalized = re.sub(r"[^a-z0-9]+", " ", heading.casefold()).strip()
    for section_type, names in _SECTION_RULES:
        if normalized in names or any(
            normalized.startswith(name + " ") or normalized.endswith(" " + name) for name in names
        ):
            return section_type
    return "other"


def parse_structured_document(data: bytes, *, format_hint: str) -> StructuredDocument:
    """Parse JATS or GROBID TEI without resolving DTDs, entities, XIncludes, or URLs.

    Any size, XML, or extraction-boundary failure rejects the complete document;
    callers must not persist a partial parse as complete evidence.
    """
    if format_hint not in {"jats", "tei"}:
        raise StructuredDocumentError("unsupported_format")
    if not isinstance(data, bytes):
        raise StructuredDocumentError("invalid_document_bytes")
    if len(data) > MAX_STRUCTURED_DOCUMENT_BYTES:
        raise StructuredDocumentError("document_too_large")
    if _ENTITY_DECLARATION_RE.search(data):
        raise StructuredDocumentError("xml_entity_forbidden")
    parse_data = data
    if _DOCTYPE_RE.search(data):
        # Public JATS files commonly declare an external DTD. Strip only a
        # syntactically external declaration before parsing; ElementTree never
        # receives a URI to resolve. Internal subsets and malformed declarations
        # are rejected, and entity declarations are rejected above.
        parse_data, replacements = _EXTERNAL_DOCTYPE_RE.subn(b"", data, count=1)
        if replacements != 1 or _DOCTYPE_RE.search(parse_data):
            raise StructuredDocumentError("xml_doctype_forbidden")
    try:
        root = ET.fromstring(parse_data)
    except (ET.ParseError, ValueError, RecursionError):
        raise StructuredDocumentError("malformed_xml") from None

    root_name = _local_name(root.tag)
    if format_hint == "tei" and root_name == "html":
        tei_roots = [node for node in root.iter() if _local_name(node.tag) == "tei"]
        if len(tei_roots) != 1:
            raise StructuredDocumentError("unexpected_document_root")
        root = tei_roots[0]
        root_name = _local_name(root.tag)
    expected_roots = {"jats": {"article", "sub-article"}, "tei": {"tei"}}
    if root_name not in expected_roots[format_hint]:
        raise StructuredDocumentError("unexpected_document_root")

    sections: list[StructuredSection] = []
    paragraphs: list[StructuredParagraph] = []
    warnings: list[str] = []
    total_characters = 0

    def append_paragraph(
        element: ET.Element,
        *,
        section_id: str | None,
        section_type: SectionType,
        section_path: tuple[str, ...],
        paragraph_index: int,
        locator: str,
    ) -> None:
        nonlocal total_characters
        text = _clean_text(element)
        if not text:
            return
        if len(paragraphs) >= MAX_STRUCTURED_PARAGRAPHS:
            raise StructuredDocumentError("extraction_paragraph_limit")
        total_characters += len(text)
        if total_characters > MAX_STRUCTURED_TEXT_CHARACTERS:
            raise StructuredDocumentError("extraction_text_limit")
        paragraphs.append(
            StructuredParagraph(
                section_id=section_id,
                section_type=section_type,
                section_path=section_path,
                paragraph_index=paragraph_index,
                ordinal=len(paragraphs) + 1,
                text=text,
                source_locator=locator,
            )
        )

    def add_section(
        heading: str,
        path: tuple[str, ...],
        locator: str,
        inherited_type: SectionType,
    ) -> StructuredSection:
        normalized_type = normalize_section_type(heading)
        if normalized_type == "other" and inherited_type != "other":
            normalized_type = inherited_type
        section = StructuredSection(
            section_id=f"{format_hint}-section-{len(sections) + 1:04d}",
            original_heading=heading,
            normalized_type=normalized_type,
            section_path=path,
            ordinal=len(sections) + 1,
            source_locator=locator,
        )
        sections.append(section)
        return section

    def warn_tables(element: ET.Element) -> None:
        if any(
            _local_name(node.tag) in {"table-wrap", "table", "figure", "fig"}
            for node in element.iter()
        ):
            if "tables_or_figures_not_extracted" not in warnings:
                warnings.append("tables_or_figures_not_extracted")

    warn_tables(root)

    def walk_jats(
        element: ET.Element,
        path: tuple[str, ...] = (),
        section_id: str | None = None,
        section_type: SectionType = "other",
        base_locator: str = "article",
    ) -> None:
        name = _local_name(element.tag)
        if name in {"back", "ref-list", "references", "fn-group", "permissions"}:
            return
        if name in {"sec", "abstract"}:
            title = next(
                (
                    _clean_text(child)
                    for child in element
                    if _local_name(child.tag) in {"title", "label"}
                ),
                "Abstract" if name == "abstract" else "",
            )
            next_path = path + ((title,) if title else ())
            locator = f"{base_locator}/{name}[{len(sections) + 1}]"
            section = add_section(title, next_path, locator, section_type)
            paragraph_index = 0
            child_counts: dict[str, int] = {}
            for child in element:
                child_name = _local_name(child.tag)
                if child_name in {"title", "label"}:
                    continue
                child_counts[child_name] = child_counts.get(child_name, 0) + 1
                child_locator = f"{locator}/{child_name}[{child_counts[child_name]}]"
                if child_name == "p":
                    paragraph_index += 1
                    append_paragraph(
                        child,
                        section_id=section.section_id,
                        section_type=section.normalized_type,
                        section_path=section.section_path,
                        paragraph_index=paragraph_index,
                        locator=child_locator,
                    )
                elif child_name not in {"table-wrap", "fig", "figure"}:
                    walk_jats(
                        child,
                        section.section_path,
                        section.section_id,
                        section.normalized_type,
                        child_locator,
                    )
            return
        child_counts = {}
        for child in element:
            child_name = _local_name(child.tag)
            child_counts[child_name] = child_counts.get(child_name, 0) + 1
            child_locator = f"{base_locator}/{child_name}[{child_counts[child_name]}]"
            if child_name == "p":
                append_paragraph(
                    child,
                    section_id=section_id,
                    section_type=section_type,
                    section_path=path,
                    paragraph_index=child_counts[child_name],
                    locator=child_locator,
                )
            elif child_name not in {"table-wrap", "fig", "figure"}:
                walk_jats(child, path, section_id, section_type, child_locator)

    def walk_tei(
        element: ET.Element,
        path: tuple[str, ...] = (),
        section_id: str | None = None,
        section_type: SectionType = "other",
        base_locator: str = "TEI/text/body",
    ) -> None:
        name = _local_name(element.tag)
        if name in {"back", "listbibl", "bibliography", "sourceDesc".casefold()}:
            return
        if name == "div":
            heading_element = next(
                (child for child in element if _local_name(child.tag) == "head"), None
            )
            heading = _clean_text(heading_element) if heading_element is not None else ""
            next_path = path + ((heading,) if heading else ())
            locator = f"{base_locator}/div[{len(sections) + 1}]"
            section = add_section(heading, next_path, locator, section_type)
            paragraph_index = 0
            child_counts: dict[str, int] = {}
            for child in element:
                child_name = _local_name(child.tag)
                if child_name == "head":
                    continue
                child_counts[child_name] = child_counts.get(child_name, 0) + 1
                child_locator = f"{locator}/{child_name}[{child_counts[child_name]}]"
                if child_name == "p":
                    paragraph_index += 1
                    append_paragraph(
                        child,
                        section_id=section.section_id,
                        section_type=section.normalized_type,
                        section_path=section.section_path,
                        paragraph_index=paragraph_index,
                        locator=child_locator,
                    )
                else:
                    walk_tei(
                        child,
                        section.section_path,
                        section.section_id,
                        section.normalized_type,
                        child_locator,
                    )
            return
        child_counts = {}
        for child in element:
            child_name = _local_name(child.tag)
            child_counts[child_name] = child_counts.get(child_name, 0) + 1
            child_locator = f"{base_locator}/{child_name}[{child_counts[child_name]}]"
            if child_name == "p":
                append_paragraph(
                    child,
                    section_id=section_id,
                    section_type=section_type,
                    section_path=path,
                    paragraph_index=child_counts[child_name],
                    locator=child_locator,
                )
            else:
                walk_tei(child, path, section_id, section_type, child_locator)

    if format_hint == "jats":
        # Abstract is commonly outside body; parse it first, then body in document order.
        for abstract in root.iter():
            if _local_name(abstract.tag) == "abstract":
                walk_jats(abstract, base_locator="article/front/article-meta")
        body = next((node for node in root.iter() if _local_name(node.tag) == "body"), None)
        if body is not None:
            walk_jats(body, base_locator="article/body")
        if body is None and not paragraphs:
            raise StructuredDocumentError("body_unavailable")
    else:
        text_element = next((node for node in root.iter() if _local_name(node.tag) == "text"), None)
        if text_element is None:
            raise StructuredDocumentError("body_unavailable")
        body = next((node for node in text_element.iter() if _local_name(node.tag) == "body"), None)
        if body is None:
            walk_tei(text_element, base_locator="TEI/text")
        else:
            walk_tei(body)

    return StructuredDocument(
        representation_format=format_hint,
        content_sha256=hashlib.sha256(data).hexdigest(),
        parser_name=PARSER_NAME,
        parser_version=PARSER_VERSION,
        sections=tuple(sections),
        paragraphs=tuple(paragraphs),
        extraction_warnings=tuple(warnings),
    )
